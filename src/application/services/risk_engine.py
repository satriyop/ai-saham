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

if TYPE_CHECKING:
    from src.application.services.indicator_registry import IndicatorRegistry
    from src.domain.ports.fundamentals_provider import FundamentalsProvider
    from src.domain.ports.bandar_detector_provider import BandarDetectorProvider

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
    ) -> None:
        self._use_case = AssessRiskUseCase(
            repository=repository,
            registry=registry,
            structural_gates=structural_gates,
            execution_gates=execution_gates,
        )
        self._fundamentals_provider = fundamentals_provider
        self._bandar_provider = bandar_provider

    def assess(
        self,
        ticker: str,
        profile: str = "balanced",
        as_of_date: date | None = None,
    ) -> AssessRiskResponse:
        """
        Full self-contained assessment.

        Builds GateContext from injected providers where available.
        Gates skip gracefully when provider data is absent:
          - FundamentalGate: skips if piotroski_f_score is None
          - LiquidityGate:   always fires (uses candles from repository)
          - BandarGate:      skips if five_day_accdist is None
        """
        gate_ctx = self._build_gate_context(ticker)
        if as_of_date is not None:
            gate_ctx = replace(gate_ctx, snapshot_date=as_of_date)
        return self._use_case.execute(
            AssessRiskRequest(ticker=ticker, profile=profile, gate_context=gate_ctx)
        )

    def assess_with_context(
        self,
        ticker: str,
        profile: str,
        gate_context: GateContext,
    ) -> AssessRiskResponse:
        """
        Pipeline path: caller supplies pre-loaded GateContext.

        Used by AccumulationScreenUseCase._run_risk_funnel() where candidate
        data is already loaded — avoids N+1 provider fetches across 800+ tickers.
        """
        return self._use_case.execute(
            AssessRiskRequest(ticker=ticker, profile=profile, gate_context=gate_context)
        )

    def assess_request(self, request: AssessRiskRequest) -> AssessRiskResponse:
        """
        Advanced path: caller provides a full AssessRiskRequest.

        Injects gate_context automatically when the caller hasn't supplied one.
        Use this when the caller needs control over sma_period, ema_period,
        rsi_period, rules_file, or sentiment fields.
        """
        return self._use_case.execute(self._inject_gate_context(request))

    def assess_all_profiles(self, request: AssessRiskRequest) -> "AssessAllProfilesResponse":
        """Run assessment across all risk profiles (conservative/balanced/aggressive)."""
        return self._use_case.execute_all_profiles(self._inject_gate_context(request))

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

    def _build_gate_context(self, ticker: str) -> GateContext:
        """Fetch enrichment data from injected providers and build a GateContext."""
        today = date.today()

        piotroski: int | None = None
        market_cap: int | None = None
        if self._fundamentals_provider is not None:
            try:
                fund = self._fundamentals_provider.get_fundamentals(ticker)
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

        return GateContext(
            ticker=ticker,
            snapshot_date=today,
            piotroski_f_score=piotroski,
            market_cap_idr=market_cap,
            five_day_accdist=five_day,
        )
