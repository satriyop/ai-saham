"""Risk assessment and TradeSetup composition for swing analysis workflow.

Layer: Application

Owns the risk-response branch (technical gate opt-in, context-aware
RiskEngine, fallback AssessRiskUseCase), canonical TradeSetup composition,
market-context risk/trade-setup preview, and recomposition after the
evidence-enriched signal re-score. Extracted from
`SwingAnalysisWorkflowUseCase` to keep the use case as orchestration only.
"""

from datetime import date
from typing import TYPE_CHECKING, Any

from src.application.use_case.assess_risk_use_case import AssessRiskRequest, AssessRiskUseCase
from src.domain.rules.risk_gate import GateContext, RiskGate

if TYPE_CHECKING:
    from src.application.services.risk_engine import RiskEngine
    from src.application.services.signal_engine import SignalEngine
    from src.application.dto.assess_signal import AssessSignalResponse
    from src.domain.value_objects.market_context import MarketContext
    from src.domain.value_objects.trade_setup import TradeSetup


class SwingAnalysisRiskTradeSetupComposer:
    """Owns risk assessment and TradeSetup composition for swing analysis."""

    def __init__(
        self,
        market_repository: Any,
        registry: Any,
        structural_gates: list[RiskGate],
        execution_gates: list[RiskGate],
        signal_engine: "SignalEngine | None",
        risk_engine: "RiskEngine | None",
    ) -> None:
        self._market_repo = market_repository
        self._registry = registry
        self._structural_gates = structural_gates
        self._execution_gates = execution_gates
        self._signal_engine = signal_engine
        self._risk_engine = risk_engine

    def build_gate_context(
        self,
        *,
        ticker: str,
        snapshot_date: date,
        accumulation_candidate: Any | None,
        with_technical_gate: bool,
    ) -> GateContext | None:
        if (
            self._structural_gates or self._execution_gates or with_technical_gate
        ) and accumulation_candidate is not None:
            fund = accumulation_candidate.fundamentals
            bandar = accumulation_candidate.bandar_detector
            shareholding = accumulation_candidate.shareholding
            return GateContext(
                ticker=ticker,
                snapshot_date=snapshot_date,
                piotroski_f_score=fund.piotroski_f_score if fund else None,
                market_cap_idr=fund.market_cap_idr if fund else None,
                free_float_pct=shareholding.free_float_pct if shareholding else None,
                five_day_accdist=bandar.five_day_accdist if bandar else None,
            )
        return None

    def assess_initial(
        self,
        *,
        ticker: str,
        snapshot_date: date,
        with_technical_gate: bool,
        gate_ctx: GateContext | None,
    ) -> tuple[Any | None, list[str]]:
        warnings: list[str] = []
        risk_response = None
        try:
            if with_technical_gate:
                # Opt-in TechnicalGate path: route through a use case that
                # appends TechnicalGate to the execution tier.
                from src.application.services.indicator_evaluator import IndicatorEvaluator
                from src.domain.rules.technical_gate import TechnicalGate

                evaluator = (
                    self._risk_engine.indicator_evaluator
                    if self._risk_engine is not None
                    else None
                ) or IndicatorEvaluator()
                indicator_defaults = (
                    self._risk_engine.indicator_defaults
                    if self._risk_engine is not None
                    else None
                )
                technical_gate_config = (
                    self._risk_engine.technical_gate_config
                    if self._risk_engine is not None
                    else None
                )
                execution_gates = list(self._execution_gates) + [
                    TechnicalGate(evaluator, technical_gate_config)
                ]
                risk_use_case = AssessRiskUseCase(
                    repository=self._market_repo,
                    registry=self._registry,
                    structural_gates=self._structural_gates or None,
                    execution_gates=execution_gates,
                    indicator_evaluator=evaluator,
                    indicator_history_days=indicator_defaults.history_days
                    if indicator_defaults is not None else 365,
                    gate_recent_candle_lookback=indicator_defaults.gate_recent_candle_lookback
                    if indicator_defaults is not None else 20,
                )
                risk_response = risk_use_case.execute(
                    AssessRiskRequest(
                        ticker=ticker,
                        sma_period=indicator_defaults.sma_period
                        if indicator_defaults is not None else 20,
                        ema_period=indicator_defaults.ema_period
                        if indicator_defaults is not None else 20,
                        rsi_period=indicator_defaults.rsi_period
                        if indicator_defaults is not None else 14,
                        gate_context=gate_ctx,
                    )
                )
            elif self._risk_engine is not None and gate_ctx is not None:
                risk_response = self._risk_engine.assess_with_context(
                    ticker=ticker,
                    gate_context=gate_ctx,
                    market_context=None,
                )
            elif self._risk_engine is not None:
                risk_response = self._risk_engine.assess(
                    ticker=ticker,
                    as_of_date=snapshot_date,
                    market_context=None,
                )
            else:
                risk_use_case = AssessRiskUseCase(
                    repository=self._market_repo,
                    registry=self._registry,
                    structural_gates=self._structural_gates or None,
                    execution_gates=self._execution_gates or None,
                )
                risk_response = risk_use_case.execute(
                    AssessRiskRequest(
                        ticker=ticker,
                        gate_context=gate_ctx,
                    )
                )
        except Exception as exc:
            warnings.append(f"Risk assessment unavailable: {exc}")
        return risk_response, warnings

    def compose_trade_setup(
        self,
        *,
        ticker: str,
        snapshot_date: date,
        signal_assessment: "AssessSignalResponse | None",
        risk_response: Any | None,
    ) -> tuple["TradeSetup | None", list[str]]:
        warnings: list[str] = []
        trade_setup = None
        if signal_assessment is not None and risk_response is not None:
            try:
                from src.application.use_case.assess_trade_setup_use_case import (
                    AssessTradeSetupRequest,
                    AssessTradeSetupUseCase,
                )
                trade_setup = AssessTradeSetupUseCase().execute(
                    AssessTradeSetupRequest(
                        ticker=ticker,
                        snapshot_date=snapshot_date,
                        signal_response=signal_assessment,
                        risk_response=risk_response,
                        market_context=None,
                    )
                ).setup
            except Exception as exc:
                warnings.append(f"TradeSetup unavailable: {exc}")
        return trade_setup, warnings

    def compose_market_context_preview(
        self,
        *,
        ticker: str,
        snapshot_date: date,
        market_regime: "MarketContext | None",
        signal_assessment: "AssessSignalResponse | None",
        risk_response: Any | None,
    ) -> tuple[
        "AssessSignalResponse | None",
        Any | None,
        "TradeSetup | None",
        list[str],
    ]:
        warnings: list[str] = []
        market_context_signal_preview = None
        market_context_risk_preview = None
        market_context_trade_setup_preview = None
        if (
            market_regime is not None
            and signal_assessment is not None
            and risk_response is not None
            and self._signal_engine is not None
            and self._risk_engine is not None
        ):
            try:
                from src.application.use_case.assess_trade_setup_use_case import (
                    AssessTradeSetupRequest,
                    AssessTradeSetupUseCase,
                )
                # Phase 5: canonical signal already includes regime conditioning.
                # MCE preview still differs via risk_preview (regime-adjusted risk).
                market_context_signal_preview = signal_assessment
                market_context_risk_preview = self._risk_engine.apply_market_context(
                    risk_response, market_regime
                )
                market_context_trade_setup_preview = AssessTradeSetupUseCase().execute(
                    AssessTradeSetupRequest(
                        ticker=ticker,
                        snapshot_date=snapshot_date,
                        signal_response=market_context_signal_preview,
                        risk_response=market_context_risk_preview,
                        market_context=market_regime,
                    )
                ).setup
            except Exception as exc:
                warnings.append(f"Market context preview unavailable: {exc}")
        return (
            market_context_signal_preview,
            market_context_risk_preview,
            market_context_trade_setup_preview,
            warnings,
        )

    def recompose_after_signal_rescore(
        self,
        *,
        ticker: str,
        snapshot_date: date,
        signal_assessment: "AssessSignalResponse | None",
        risk_response: Any | None,
        market_context_risk_preview: Any | None,
        market_regime: "MarketContext | None",
        fallback_trade_setup: "TradeSetup | None",
        fallback_market_context_signal_preview: "AssessSignalResponse | None",
        fallback_market_context_trade_setup_preview: "TradeSetup | None",
    ) -> tuple["TradeSetup | None", "AssessSignalResponse | None", "TradeSetup | None", list[str]]:
        warnings: list[str] = []
        new_trade_setup = fallback_trade_setup
        new_mce_signal = fallback_market_context_signal_preview
        new_mce_trade_preview = fallback_market_context_trade_setup_preview

        if risk_response is not None:
            try:
                from src.application.use_case.assess_trade_setup_use_case import (
                    AssessTradeSetupRequest,
                    AssessTradeSetupUseCase,
                )
                new_trade_setup = AssessTradeSetupUseCase().execute(
                    AssessTradeSetupRequest(
                        ticker=ticker,
                        snapshot_date=snapshot_date,
                        signal_response=signal_assessment,
                        risk_response=risk_response,
                        market_context=None,
                    )
                ).setup
            except Exception as exc:
                warnings.append(f"TradeSetup re-composition unavailable: {exc}")

        if market_context_risk_preview is not None:
            try:
                from src.application.use_case.assess_trade_setup_use_case import (
                    AssessTradeSetupRequest,
                    AssessTradeSetupUseCase,
                )
                # Phase 5: canonical signal already includes regime — no
                # separate apply_market_context() needed for signal preview.
                new_mce_signal = signal_assessment
                new_mce_trade_preview = AssessTradeSetupUseCase().execute(
                    AssessTradeSetupRequest(
                        ticker=ticker,
                        snapshot_date=snapshot_date,
                        signal_response=new_mce_signal,
                        risk_response=market_context_risk_preview,
                        market_context=market_regime,
                    )
                ).setup
            except Exception as exc:
                warnings.append(f"MCE preview re-computation unavailable: {exc}")

        return new_trade_setup, new_mce_signal, new_mce_trade_preview, warnings
