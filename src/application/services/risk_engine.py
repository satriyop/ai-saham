"""
RiskEngine — first-class application service for risk assessment.

Self-sufficient: callers never instantiate gates, build GateContext,
or wire AssessRiskUseCase. Two entry points:

  assess()              — self-fetches enrichment data; for commands
                          with no pre-loaded context (analyze risk, compare)
  assess_with_context() — pipeline path; for screener with pre-loaded
                          candidate data to avoid N+1 fetches

Layer: Application
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import date
from typing import TYPE_CHECKING

from src.application.use_case.assess_risk_use_case import (
    AssessRiskRequest,
    AssessRiskResponse,
    AssessAllProfilesResponse,
    AssessRiskTrendResponse,
    AssessRiskUseCase,
)
from src.domain.rules.risk_gate import GateContext, RiskGate
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.risk_signal import RiskLevel

if TYPE_CHECKING:
    from src.application.services.indicator_registry import IndicatorRegistry
    from src.domain.ports.fundamentals_provider import FundamentalsProvider
    from src.domain.ports.bandar_detector_provider import BandarDetectorProvider
    from src.domain.ports.shareholding_provider import ShareholdingProvider
    from src.domain.value_objects.market_context import MarketContext

logger = logging.getLogger(__name__)


class RiskEngine:
    """
    Self-sufficient risk evaluation service.

    Owns gate configuration. Callers never see RiskGate, GateContext,
    AssessRiskUseCase, or gate imports — they call assess() and get
    an AssessRiskResponse.
    """

    def __init__(
        self,
        repository: MarketDataRepository,
        registry: "IndicatorRegistry",
        structural_gates: list[RiskGate],
        execution_gates: list[RiskGate],
        fundamentals_provider: "FundamentalsProvider | None" = None,
        bandar_provider: "BandarDetectorProvider | None" = None,
        shareholding_provider: "ShareholdingProvider | None" = None,
    ) -> None:
        self._use_case = AssessRiskUseCase(
            repository=repository,
            registry=registry,
            structural_gates=structural_gates,
            execution_gates=execution_gates,
        )
        self._fundamentals_provider = fundamentals_provider
        self._bandar_provider = bandar_provider
        self._shareholding_provider = shareholding_provider

    def assess(
        self,
        ticker: str,
        profile: str = "balanced",
        as_of_date: date | None = None,
        market_context: "MarketContext | None" = None,
    ) -> AssessRiskResponse:
        """
        Full self-contained assessment.

        Builds GateContext from injected providers where available.
        Gates skip gracefully when provider data is absent:
          - FundamentalGate: skips if piotroski_f_score is None
          - LiquidityGate:   always fires (uses candles from repository)
          - BandarGate:      skips if five_day_accdist is None

        market_context: when gate_tightening=True, HIGH_RISK assessments are
        additionally blocked by a regime gate.
        """
        gate_ctx = self._build_gate_context(ticker, as_of_date)
        if as_of_date is not None:
            gate_ctx = replace(gate_ctx, snapshot_date=as_of_date)
        response = self._use_case.execute(
            AssessRiskRequest(ticker=ticker, profile=profile, gate_context=gate_ctx)
        )
        return _apply_regime_gate(response, market_context)

    def assess_with_context(
        self,
        ticker: str,
        profile: str,
        gate_context: GateContext,
        market_context: "MarketContext | None" = None,
    ) -> AssessRiskResponse:
        """
        Pipeline path: caller supplies pre-loaded GateContext.

        Intended for screener loops (800+ tickers) where candidate data is
        already loaded — avoids N+1 provider fetches per ticker.
        Wire up by passing this engine to the screener instead of AssessRiskUseCase.
        """
        response = self._use_case.execute(
            AssessRiskRequest(ticker=ticker, profile=profile, gate_context=gate_context)
        )
        return _apply_regime_gate(response, market_context)

    def assess_request(
        self,
        request: AssessRiskRequest,
        market_context: "MarketContext | None" = None,
    ) -> AssessRiskResponse:
        """
        Advanced path: caller provides a full AssessRiskRequest.

        Injects gate_context automatically when the caller hasn't supplied one.
        Skips gate injection when rules_file is set — the custom-rules branch
        in the use case returns before gate evaluation, so the fetch is wasted.
        """
        if request.rules_file is not None:
            return self._use_case.execute(request)
        response = self._use_case.execute(self._inject_gate_context(request))
        return _apply_regime_gate(response, market_context)

    def assess_all_profiles(
        self,
        request: AssessRiskRequest,
        market_context: "MarketContext | None" = None,
    ) -> "AssessAllProfilesResponse":
        """Run assessment across all risk profiles (conservative/balanced/aggressive)."""
        result = self._use_case.execute_all_profiles(self._inject_gate_context(request))
        if market_context is not None and market_context.gate_tightening:
            gate_label = f"regime:{market_context.regime.value}"
            gated = [
                replace(a, gate_triggered=gate_label, gate_is_structural=True)
                if a.risk_level == RiskLevel.HIGH_RISK and a.gate_triggered is None
                else a
                for a in result.assessments
            ]
            result = replace(result, assessments=gated)
        return result

    def assess_trend(
        self, request: AssessRiskRequest, days: int = 7
    ) -> "AssessRiskTrendResponse":
        """Evaluate risk trend over the last N days."""
        return self._use_case.execute_trend(self._inject_gate_context(request), days=days)

    # ── internals ────────────────────────────────────────────────────────────

    def _inject_gate_context(self, request: AssessRiskRequest) -> AssessRiskRequest:
        """Return request with gate_context populated if it was missing."""
        if request.gate_context is not None:
            return request
        gate_ctx = self._build_gate_context(request.ticker)
        return replace(request, gate_context=gate_ctx)

    def _build_gate_context(self, ticker: str, as_of_date: date | None = None) -> GateContext:
        """Fetch enrichment data from injected providers and build a GateContext.

        as_of_date: when set (backtest mode), providers return only data available
        on or before that date, preventing look-ahead bias.
        """
        today = date.today()

        piotroski: int | None = None
        market_cap: int | None = None
        if self._fundamentals_provider is not None:
            try:
                fund = self._fundamentals_provider.get_fundamentals(ticker, as_of_date)
                if fund is not None:
                    piotroski = fund.piotroski_f_score
                    market_cap = fund.market_cap_idr
            except Exception as exc:
                logger.debug("RiskEngine: fundamentals unavailable for %s: %s", ticker, exc)

        five_day: str | None = None
        if self._bandar_provider is not None:
            try:
                bandar = self._bandar_provider.get_snapshot(ticker)
                if bandar is not None:
                    five_day = bandar.five_day_accdist
            except Exception as exc:
                logger.debug("RiskEngine: bandar snapshot unavailable for %s: %s", ticker, exc)

        free_float: float | None = None
        if self._shareholding_provider is not None:
            try:
                comp = self._shareholding_provider.get_composition(ticker, as_of_date)
                if comp is not None:
                    free_float = comp.free_float_pct
            except Exception as exc:
                logger.debug("RiskEngine: shareholding unavailable for %s: %s", ticker, exc)

        return GateContext(
            ticker=ticker,
            snapshot_date=today,
            piotroski_f_score=piotroski,
            market_cap_idr=market_cap,
            free_float_pct=free_float,
            five_day_accdist=five_day,
        )


# ── Market context post-processing ───────────────────────────────────────────

def _apply_regime_gate(
    response: AssessRiskResponse,
    market_context: "MarketContext | None",
) -> AssessRiskResponse:
    """
    Apply regime gate tightening to a risk assessment.

    When gate_tightening=True and the assessment is HIGH_RISK, injects a
    regime gate trigger so the stock is blocked at the gate layer.
    No-op when market_context is None or gate_tightening is False.
    """
    if market_context is None or not market_context.gate_tightening:
        return response
    if response.assessment.risk_level != RiskLevel.HIGH_RISK:
        return response
    if response.assessment.gate_triggered is not None:
        # already gated by a domain gate — don't overwrite
        return response

    regime = market_context.regime.value
    gate_label = f"regime:{regime}"
    new_assessment = replace(response.assessment, gate_triggered=gate_label, gate_is_structural=True)
    return replace(response, assessment=new_assessment)
