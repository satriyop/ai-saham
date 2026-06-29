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
from dataclasses import dataclass, replace
from datetime import date
from typing import TYPE_CHECKING

from src.application.use_case.assess_risk_use_case import (
    AssessRiskRequest,
    AssessRiskResponse,
    AssessRiskTrendResponse,
    AssessRiskUseCase,
)
from src.domain.rules.risk_gate import GateContext, RiskGate
from src.domain.ports.market_data_repository import MarketDataRepository

if TYPE_CHECKING:
    from src.application.services.indicator_evaluator import IndicatorEvaluator
    from src.application.services.indicator_registry import IndicatorRegistry
    from src.domain.rules.technical_gate import TechnicalGateConfig
    from src.domain.ports.fundamentals_provider import FundamentalsProvider
    from src.domain.ports.bandar_detector_provider import BandarDetectorProvider
    from src.domain.ports.shareholding_provider import ShareholdingProvider
    from src.domain.value_objects.market_context import MarketContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RiskIndicatorDefaults:
    sma_period: int = 20
    ema_period: int = 20
    rsi_period: int = 14
    history_days: int = 365
    gate_recent_candle_lookback: int = 20


@dataclass(frozen=True)
class MarketContextGateConfig:
    enabled: bool = True
    block_when_gate_tightening: bool = True
    gate_is_structural: bool = True
    label_prefix: str = "regime"


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
        indicator_evaluator: "IndicatorEvaluator | None" = None,
        indicator_defaults: RiskIndicatorDefaults | None = None,
        market_context_gate: MarketContextGateConfig | None = None,
        technical_gate_config: "TechnicalGateConfig | None" = None,
    ) -> None:
        self._indicator_defaults = indicator_defaults or RiskIndicatorDefaults()
        self._market_context_gate = market_context_gate or MarketContextGateConfig()
        self._indicator_evaluator = indicator_evaluator
        self._technical_gate_config = technical_gate_config
        self._use_case = AssessRiskUseCase(
            repository=repository,
            registry=registry,
            structural_gates=structural_gates,
            execution_gates=execution_gates,
            indicator_evaluator=self._indicator_evaluator,
            indicator_history_days=self._indicator_defaults.history_days,
            gate_recent_candle_lookback=self._indicator_defaults.gate_recent_candle_lookback,
        )
        self._fundamentals_provider = fundamentals_provider
        self._bandar_provider = bandar_provider
        self._shareholding_provider = shareholding_provider

    def assess(
        self,
        ticker: str,
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
            AssessRiskRequest(
                ticker=ticker,
                sma_period=self._indicator_defaults.sma_period,
                ema_period=self._indicator_defaults.ema_period,
                rsi_period=self._indicator_defaults.rsi_period,
                gate_context=gate_ctx,
            )
        )
        return _apply_regime_gate(response, market_context, self._market_context_gate)

    def assess_with_context(
        self,
        ticker: str,
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
            AssessRiskRequest(
                ticker=ticker,
                sma_period=self._indicator_defaults.sma_period,
                ema_period=self._indicator_defaults.ema_period,
                rsi_period=self._indicator_defaults.rsi_period,
                gate_context=gate_context,
            )
        )
        return _apply_regime_gate(response, market_context, self._market_context_gate)

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
        response = self._use_case.execute(self._inject_gate_context(self._apply_request_defaults(request)))
        return _apply_regime_gate(response, market_context, self._market_context_gate)

    def assess_trend(
        self, request: AssessRiskRequest, days: int = 7
    ) -> "AssessRiskTrendResponse":
        """Evaluate risk trend over the last N days."""
        return self._use_case.execute_trend(
            self._inject_gate_context(self._apply_request_defaults(request)),
            days=days,
        )

    @property
    def indicator_evaluator(self) -> "IndicatorEvaluator | None":
        return self._indicator_evaluator

    @property
    def indicator_defaults(self) -> RiskIndicatorDefaults:
        return self._indicator_defaults

    @property
    def technical_gate_config(self) -> "TechnicalGateConfig | None":
        return self._technical_gate_config

    def apply_market_context(
        self,
        response: "AssessRiskResponse",
        market_context: "MarketContext",
    ) -> "AssessRiskResponse":
        """Apply MCE gate tightening to an already-computed raw response (preview path).

        Used by the workflow to compute a what-if risk preview without re-fetching
        provider data. Does not affect canonical risk_response.
        """
        return _apply_regime_gate(response, market_context, self._market_context_gate)

    # ── internals ────────────────────────────────────────────────────────────

    def _inject_gate_context(self, request: AssessRiskRequest) -> AssessRiskRequest:
        """Return request with gate_context populated if it was missing."""
        if request.gate_context is not None:
            return request
        gate_ctx = self._build_gate_context(request.ticker)
        return replace(request, gate_context=gate_ctx)

    def _apply_request_defaults(self, request: AssessRiskRequest) -> AssessRiskRequest:
        defaults = self._indicator_defaults
        updates = {}
        if request.sma_period == AssessRiskRequest.sma_period:
            updates["sma_period"] = defaults.sma_period
        if request.ema_period == AssessRiskRequest.ema_period:
            updates["ema_period"] = defaults.ema_period
        if request.rsi_period == AssessRiskRequest.rsi_period:
            updates["rsi_period"] = defaults.rsi_period
        return replace(request, **updates) if updates else request

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
    config: MarketContextGateConfig | None = None,
) -> AssessRiskResponse:
    """
    Apply regime gate tightening to a risk assessment.

    When gate_tightening=True and no gate has fired yet, injects a regime gate
    trigger so the stock is blocked at the gate layer.
    No-op when market_context is None or gate_tightening is False.
    """
    cfg = config or MarketContextGateConfig()
    if (
        market_context is None
        or not cfg.enabled
        or not cfg.block_when_gate_tightening
        or not market_context.gate_tightening
    ):
        return response
    if response.assessment.gate_triggered is not None:
        # already gated by a domain gate — don't overwrite
        return response

    regime = market_context.regime.value
    gate_label = f"{cfg.label_prefix}:{regime}"
    new_assessment = replace(
        response.assessment,
        gate_triggered=gate_label,
        gate_is_structural=cfg.gate_is_structural,
    )
    return replace(response, assessment=new_assessment)
