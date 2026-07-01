"""
Application workflow coordinator for `saham analyze swing`.

Layer: Application
AI usage: Optional sentiment provider, controlled by injected fetcher.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.application.services.risk_engine import RiskEngine
    from src.application.services.signal_engine import SignalEngine
    from src.application.use_case.assess_signal_use_case import AssessSignalResponse

from src.application.services.position_sizer import (
    PercentSizingResult,
    SizingResult,
    compute_percent_position_size,
    compute_position_size,
)
from src.domain.value_objects.benchmark_symbol import canonicalize_ticker
from src.application.services.signal_context_builder import (
    build_signal_context_from_candidate,
)
from src.application.use_case.assess_risk_use_case import AssessRiskRequest, AssessRiskUseCase
from src.domain.rules.risk_gate import GateContext, RiskGate
from src.application.use_case.backtest_use_case import BacktestRequest, BacktestUseCase

if TYPE_CHECKING:
    from src.domain.value_objects.market_context import MarketContext
    from src.domain.value_objects.trade_setup import TradeSetup
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository


@dataclass(frozen=True)
class SwingAnalysisWorkflowRequest:
    ticker: str
    today: date
    strategy_name: str | None
    setup_name: str | None
    window: int
    flow_window: int
    capital: int | None
    risk_pct: float
    entry_price: float | None
    atr_mult: float
    rr: float
    include_sentiment: bool
    include_flow_detail: bool
    include_signal_detail: bool
    include_risk_detail: bool
    include_market_detail: bool
    sentiment_verbose: bool
    auto_refresh: bool
    force_refresh: bool
    with_market_context: bool
    regime_universe: str
    benchmark: str
    db_path: Path
    with_technical_gate: bool = False


@dataclass(frozen=True)
class SwingVerdict:
    """Decision-producing outputs for swing analysis."""

    trade_setup: "TradeSetup | None"
    signal_assessment: "AssessSignalResponse | None"
    risk_response: Any | None
    market_regime: "MarketContext | None"
    market_context_signal_preview: "AssessSignalResponse | None" = None
    market_context_risk_preview: Any | None = None
    market_context_trade_setup_preview: "TradeSetup | None" = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_setup": self.trade_setup.to_dict() if self.trade_setup else None,
            "signal_assessment": _signal_response_to_dict(self.signal_assessment),
            "risk_assessment": _risk_response_to_dict(self.risk_response),
            "market_context": (
                self.market_regime.to_dict() if self.market_regime else None
            ),
            "market_context_preview": {
                "signal_preview": _signal_response_to_dict(
                    self.market_context_signal_preview
                ),
                "risk_preview": _risk_response_to_preview_dict(
                    self.market_context_risk_preview
                ),
                "trade_setup_preview": (
                    self.market_context_trade_setup_preview.to_dict()
                    if self.market_context_trade_setup_preview else None
                ),
            } if self.market_regime else None,
        }


@dataclass(frozen=True)
class SwingEvidence:
    """Supporting evidence that informs or explains swing analysis."""

    accumulation_candidate: Any | None
    setup_eval: Any | None
    backtest_result: Any | None
    sentiment_response: Any | None
    sentiment_warning: str | None
    take_profit_pct: Decimal
    stop_loss_pct: Decimal
    regime_label: str | None

    def to_dict(self, *, strategy_name: str | None = None, max_hold_days: int | None = None) -> dict[str, Any]:
        candidate = self.accumulation_candidate
        setup_eval = self.setup_eval
        backtest_result = self.backtest_result
        sentiment_resp = self.sentiment_response
        return {
            "foreign_flow_evidence": (
                candidate.foreign_flow_evidence.to_dict()
                if candidate and getattr(candidate, "foreign_flow_evidence", None) else None
            ),
            "accumulation": _candidate_accumulation_to_dict(candidate),
            "setup": {
                "name": setup_eval.name if setup_eval else None,
                "passed": setup_eval.passed if setup_eval else None,
                "match": setup_eval.match.value if setup_eval else None,
                "failed_reasons": list(setup_eval.failed_reasons) if setup_eval else [],
                "plan": {
                    "take_profit_pct": float(self.take_profit_pct) if setup_eval else None,
                    "stop_loss_pct": float(self.stop_loss_pct) if setup_eval else None,
                    "regime": self.regime_label,
                    "max_hold_days": max_hold_days if setup_eval else None,
                },
            } if setup_eval else None,
            "strategy_evidence": {
                "name": strategy_name,
                "win_rate": float(backtest_result.win_rate) if backtest_result else None,
                "profit_factor": (
                    float(backtest_result.profit_factor) if backtest_result else None
                ),
                "max_drawdown_pct": (
                    float(backtest_result.max_drawdown_pct)
                    if backtest_result else None
                ),
                "trade_count": backtest_result.trade_count if backtest_result else None,
            } if strategy_name else None,
            "sentiment": {
                "call": (
                    sentiment_resp.snapshot.overall_sentiment.value
                    if sentiment_resp and not sentiment_resp.warning else None
                ),
                "warning": self.sentiment_warning,
                "total_headlines": (
                    sentiment_resp.snapshot.total_count
                    if sentiment_resp and not sentiment_resp.warning else None
                ),
                "confidence_pct": (
                    sentiment_resp.snapshot.confidence_pct
                    if sentiment_resp and not sentiment_resp.warning else None
                ),
            },
        }


@dataclass(frozen=True)
class SwingDiagnostics:
    """Data quality and diagnostic outputs for swing analysis."""

    data_freshness: Any
    flow_detail: Any
    broker_detail: Any
    broker_quality_note: Any | None
    refresh_actions: tuple[str, ...]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data_out = _object_to_dict(self.data_freshness)
        return {
            "data": data_out,
            "flow_detail": _object_to_dict(self.flow_detail),
            "broker_detail": _object_to_dict(self.broker_detail),
            "broker_quality_note": _object_to_dict(self.broker_quality_note),
            "refresh_actions": list(self.refresh_actions),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class SwingAnalysisWorkflowResponse:
    ticker: str
    today: date
    refresh_actions: tuple[str, ...]
    data_freshness: Any
    flow_detail: Any
    broker_detail: Any
    candles: list[Any]
    latest_close: Decimal
    accumulation_candidate: Any | None
    risk_response: Any | None
    atr_value: Decimal | None
    sizing: SizingResult | None
    setup_eval: Any | None
    setup_sizing: PercentSizingResult | None
    broker_quality_note: Any | None
    backtest_result: Any | None
    sentiment_response: Any | None
    sentiment_warning: str | None
    market_regime: "MarketContext | None"
    take_profit_pct: Decimal
    stop_loss_pct: Decimal
    regime_label: str | None
    signal_assessment: "AssessSignalResponse | None" = None
    trade_setup: "TradeSetup | None" = None
    market_context_signal_preview: "AssessSignalResponse | None" = None
    market_context_risk_preview: Any | None = None
    market_context_trade_setup_preview: "TradeSetup | None" = None
    verdict: SwingVerdict | None = None
    evidence: SwingEvidence | None = None
    diagnostics: SwingDiagnostics | None = None
    modules: dict[str, bool] | None = None
    warnings: tuple[str, ...] = ()

    def to_dict(
        self,
        *,
        strategy_name: str | None = None,
        max_hold_days: int | None = None,
        include_sentiment: bool = True,
    ) -> dict[str, Any]:
        verdict = self.verdict or SwingVerdict(
            trade_setup=self.trade_setup,
            signal_assessment=self.signal_assessment,
            risk_response=self.risk_response,
            market_regime=self.market_regime,
            market_context_signal_preview=self.market_context_signal_preview,
            market_context_risk_preview=self.market_context_risk_preview,
            market_context_trade_setup_preview=self.market_context_trade_setup_preview,
        )
        evidence = self.evidence or SwingEvidence(
            accumulation_candidate=self.accumulation_candidate,
            setup_eval=self.setup_eval,
            backtest_result=self.backtest_result,
            sentiment_response=self.sentiment_response,
            sentiment_warning=self.sentiment_warning,
            take_profit_pct=self.take_profit_pct,
            stop_loss_pct=self.stop_loss_pct,
            regime_label=self.regime_label,
        )
        diagnostics = self.diagnostics or SwingDiagnostics(
            data_freshness=self.data_freshness,
            flow_detail=self.flow_detail,
            broker_detail=self.broker_detail,
            broker_quality_note=self.broker_quality_note,
            refresh_actions=self.refresh_actions,
            warnings=self.warnings,
        )
        diagnostics_out = diagnostics.to_dict()
        if (
            isinstance(diagnostics_out.get("data"), dict)
            and verdict.market_regime is not None
        ):
            diagnostics_out["data"]["regime_as_of"] = verdict.market_regime.as_of_date.isoformat()
        evidence_out = evidence.to_dict(
            strategy_name=strategy_name,
            max_hold_days=max_hold_days,
        )
        if not include_sentiment:
            evidence_out["sentiment"] = None

        return {
            "schema_version": 1,
            "artifact_type": "swing_analysis",
            "json_contract": {
                "canonical": ("verdict", "evidence", "diagnostics"),
            },
            "ticker": self.ticker,
            "date": str(self.today),
            "modules": self.modules or {},
            "verdict": verdict.to_dict(),
            "evidence": evidence_out,
            "diagnostics": diagnostics_out,
        }


def _signal_response_to_dict(response: "AssessSignalResponse | None") -> dict[str, Any] | None:
    if response is None:
        return None
    return {
        "score": response.assessment.score,
        "strength": response.assessment.strength.value,
        "entry_quality": response.assessment.entry_quality.value,
        "breakdown": response.assessment.breakdown_dict,
        "coverage_warning": response.coverage_warning,
    }


def _object_to_dict(value: Any | None) -> Any | None:
    if value is None:
        return None
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    return value


def _risk_response_to_dict(response: Any | None) -> dict[str, Any] | None:
    if response is None:
        return None
    assessment = response.assessment
    return {
        "risk_status": assessment.risk_level_name,
        "confidence": assessment.confidence,
        "sma20": float(assessment.indicators.sma),
        "ema20": float(assessment.indicators.ema),
        "rsi14": float(assessment.indicators.rsi),
        "gate_triggered": assessment.gate_triggered,
    }


def _risk_response_to_preview_dict(response: Any | None) -> dict[str, Any] | None:
    if response is None:
        return None
    return {
        "level": response.assessment.risk_level_name,
        "gate_triggered": response.assessment.gate_triggered,
    }


def _candidate_accumulation_to_dict(candidate: Any | None) -> dict[str, Any]:
    if candidate is None:
        return {
            "foreign_flow_score": None,
            "streak": None,
            "trend": None,
            "flow_pct": None,
            "vwap_disc_pct": None,
            "bb_width_pctile": None,
            "foreign_flow_evidence": None,
            "dividend_risk": False,
            "rights_issue_risk": False,
            "upcoming_rups": [],
            "seasonal_score": None,
            "seasonal_label": None,
            "insider_buying": False,
            "recent_insider_buys": [],
            "analyst_consensus": None,
            "shareholding": None,
            "bandar_detector": None,
            "fundamentals": None,
            "ticker_notation": None,
        }
    return {
        "foreign_flow_score": candidate.foreign_flow_score,
        "streak": candidate.consecutive_streak,
        "trend": candidate.trend,
        "flow_pct": candidate.avg_flow_ratio,
        "vwap_disc_pct": candidate.vwap_discount_pct,
        "bb_width_pctile": candidate.bb_width_pctile,
        "foreign_flow_evidence": (
            candidate.foreign_flow_evidence.to_dict()
            if getattr(candidate, "foreign_flow_evidence", None) else None
        ),
        "dividend_risk": candidate.dividend_risk,
        "rights_issue_risk": candidate.rights_issue_risk,
        "upcoming_rups": candidate.upcoming_rups,
        "seasonal_score": (
            candidate.seasonal_edge.score if candidate.seasonal_edge else None
        ),
        "seasonal_label": (
            candidate.seasonal_edge.label if candidate.seasonal_edge else None
        ),
        "insider_buying": candidate.insider_buying,
        "recent_insider_buys": candidate.recent_insider_buys,
        "analyst_consensus": (
            candidate.analyst_consensus.to_dict()
            if candidate.analyst_consensus else None
        ),
        "shareholding": (
            candidate.shareholding.to_dict() if candidate.shareholding else None
        ),
        "bandar_detector": (
            candidate.bandar_detector.to_dict() if candidate.bandar_detector else None
        ),
        "fundamentals": (
            candidate.fundamentals.to_dict() if candidate.fundamentals else None
        ),
        "ticker_notation": (
            candidate.ticker_notation.to_dict() if candidate.ticker_notation else None
        ),
    }


class SwingAnalysisWorkflowUseCase:
    """Run deterministic swing analysis steps and return structured state."""

    def __init__(
        self,
        market_repository: MarketDataRepository,
        broker_repository: BrokerDataRepository,
        registry: Any,
        refresh_data: Callable[..., tuple[str, ...]],
        build_data_freshness: Callable[..., Any],
        build_flow_detail: Callable[..., Any],
        build_broker_detail: Callable[..., Any],
        build_accumulation_candidate: Callable[..., Any | None],
        evaluate_setup: Callable[[Any | None, Any | None], Any | None],
        build_broker_quality_note: Callable[..., Any | None],
        fetch_sentiment: Callable[..., tuple[Any | None, str | None]],
        load_swing_config: Callable[[], Any],
        resolve_setup_targets: Callable[[str | None, Any], tuple[Decimal, Decimal]],
        evaluate_market_context: Callable[..., "MarketContext"] | None = None,
        structural_gates: list[RiskGate] | None = None,
        execution_gates: list[RiskGate] | None = None,
        signal_engine: "SignalEngine | None" = None,
        risk_engine: "RiskEngine | None" = None,
    ) -> None:
        self._market_repo = market_repository
        self._broker_repo = broker_repository
        self._registry = registry
        self._refresh_data = refresh_data
        self._build_data_freshness = build_data_freshness
        self._build_flow_detail = build_flow_detail
        self._build_broker_detail = build_broker_detail
        self._build_accumulation_candidate = build_accumulation_candidate
        self._evaluate_setup = evaluate_setup
        self._build_broker_quality_note = build_broker_quality_note
        self._fetch_sentiment = fetch_sentiment
        self._load_swing_config = load_swing_config
        self._resolve_setup_targets = resolve_setup_targets
        self._evaluate_market_context = evaluate_market_context
        self._structural_gates: list[RiskGate] = structural_gates or []
        self._execution_gates: list[RiskGate] = execution_gates or []
        self._signal_engine = signal_engine
        self._risk_engine = risk_engine

    def execute(
        self,
        request: SwingAnalysisWorkflowRequest,
    ) -> SwingAnalysisWorkflowResponse:
        warnings: list[str] = []

        refresh_actions = ("disabled",)
        if request.auto_refresh:
            refresh_actions = self._refresh_data(
                ticker=request.ticker,
                db_path=request.db_path,
                force_refresh=request.force_refresh,
            )

        data_freshness = self._build_data_freshness(
            ticker=request.ticker,
            as_of_date=request.today,
            market_repo=self._market_repo,
            broker_repo=self._broker_repo,
            refresh_actions=refresh_actions,
        )
        needs_broker_detail = request.include_flow_detail or request.setup_name is not None
        flow_detail = None
        if request.include_flow_detail:
            flow_detail = self._build_flow_detail(
                ticker=request.ticker,
                broker_repo=self._broker_repo,
                window_sessions=request.flow_window,
                as_of_date=request.today,
            )
        broker_detail = None
        if needs_broker_detail:
            broker_detail = self._build_broker_detail(
                ticker=request.ticker,
                broker_repo=self._broker_repo,
                window_sessions=5,
                as_of_date=request.today,
            )

        candles = self._market_repo.get_candles(request.ticker)
        if not candles:
            raise SwingAnalysisDataUnavailable(request.ticker)
        latest_close = candles[-1].close

        accumulation_candidate = None
        try:
            accumulation_candidate = self._build_accumulation_candidate(
                ticker=request.ticker,
                window=request.window,
            )
        except Exception as exc:
            warnings.append(f"Accumulation unavailable: {exc}")

        market_regime = None
        if request.with_market_context:
            try:
                if self._evaluate_market_context is None:
                    raise RuntimeError("Market context evaluator is not configured.")
                market_regime = self._evaluate_market_context(
                    db_path=request.db_path,
                    as_of_date=request.today,
                    universe=request.regime_universe,
                    benchmark=canonicalize_ticker(request.benchmark),
                )
            except Exception as exc:
                warnings.append(f"Market regime unavailable: {exc}")

        risk_response = None
        try:
            gate_ctx: GateContext | None = None
            if (self._structural_gates or self._execution_gates or request.with_technical_gate) and accumulation_candidate is not None:
                fund = accumulation_candidate.fundamentals
                bandar = accumulation_candidate.bandar_detector
                shareholding = accumulation_candidate.shareholding
                gate_ctx = GateContext(
                    ticker=request.ticker,
                    snapshot_date=request.today,
                    piotroski_f_score=fund.piotroski_f_score if fund else None,
                    market_cap_idr=fund.market_cap_idr if fund else None,
                    free_float_pct=shareholding.free_float_pct if shareholding else None,
                    five_day_accdist=bandar.five_day_accdist if bandar else None,
                )
            if request.with_technical_gate:
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
                        ticker=request.ticker,
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
                    ticker=request.ticker,
                    gate_context=gate_ctx,
                    market_context=None,
                )
            elif self._risk_engine is not None:
                risk_response = self._risk_engine.assess(
                    ticker=request.ticker,
                    as_of_date=request.today,
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
                        ticker=request.ticker,
                        gate_context=gate_ctx,
                    )
            )
        except Exception as exc:
            warnings.append(f"Risk assessment unavailable: {exc}")

        signal_assessment = None
        if self._signal_engine is not None:
            try:
                if (
                    accumulation_candidate is not None
                    and accumulation_candidate.signal_assessment is not None
                ):
                    # Fast path: reuse screener's pre-computed raw signal — no recomputation
                    signal_assessment = accumulation_candidate.signal_assessment
                elif accumulation_candidate is not None:
                    # Fallback: candidate exists but screener ran without a signal_engine
                    signal_ctx = build_signal_context_from_candidate(
                        ticker=request.ticker,
                        snapshot_date=request.today,
                        candidate=accumulation_candidate,
                        signal_engine=self._signal_engine,
                    )
                    signal_assessment = self._signal_engine.evaluate_with_context(
                        request.ticker,
                        signal_ctx,
                        market_context=None,
                    )
                else:
                    # No candidate — provider-based standalone evaluation
                    signal_assessment = self._signal_engine.evaluate(
                        request.ticker,
                        request.today,
                        market_context=None,
                    )
            except Exception as exc:
                warnings.append(f"Signal assessment unavailable: {exc}")

        atr_value = self._compute_atr(candles)
        sizing: SizingResult | None = None
        setup_eval = None
        setup_sizing: PercentSizingResult | None = None
        if request.setup_name is not None:
            setup_eval = self._evaluate_setup(accumulation_candidate, broker_detail)

        broker_quality_note = self._build_broker_quality_note(
            broker_detail=broker_detail,
            setup_eval=setup_eval,
        )

        setup_entry: Decimal | None = None
        if request.capital is not None and setup_eval is not None and setup_eval.passed:
            setup_entry = (
                Decimal(str(request.entry_price))
                if request.entry_price
                else latest_close
            )
        elif request.capital is not None and atr_value and setup_eval is None:
            try:
                entry = (
                    Decimal(str(request.entry_price))
                    if request.entry_price
                    else latest_close
                )
                sizing = compute_position_size(
                    entry=entry,
                    atr=atr_value,
                    capital=Decimal(str(request.capital)),
                    risk_pct=Decimal(str(request.risk_pct)) / Decimal("100"),
                    atr_multiplier=Decimal(str(request.atr_mult)),
                    reward_risk=Decimal(str(request.rr)),
                )
            except ValueError as exc:
                warnings.append(f"Position sizing unavailable: {exc}")

        backtest_result = None
        if request.strategy_name is not None:
            try:
                loader = StrategyLoader(registry=self._registry)
                rules_path = loader.resolve(request.strategy_name)
                backtest_use_case = BacktestUseCase(
                    repository=self._market_repo,
                    registry=self._registry,
                )
                backtest_response = backtest_use_case.execute(
                    BacktestRequest(
                        ticker=request.ticker,
                        rules_file=rules_path,
                        initial_capital=Decimal("100000000"),
                    )
                )
                backtest_result = backtest_response.result
            except Exception as exc:
                warnings.append(f"Backtest unavailable: {exc}")

        sentiment_response = None
        sentiment_warning = None
        if request.include_sentiment:
            sentiment_response, sentiment_warning = self._fetch_sentiment(
                ticker=request.ticker,
                sentiment_verbose=request.sentiment_verbose,
            )

        trade_setup = None
        if signal_assessment is not None and risk_response is not None:
            try:
                from src.application.use_case.assess_trade_setup_use_case import (
                    AssessTradeSetupRequest,
                    AssessTradeSetupUseCase,
                )
                trade_setup = AssessTradeSetupUseCase().execute(
                    AssessTradeSetupRequest(
                        ticker=request.ticker,
                        snapshot_date=request.today,
                        signal_response=signal_assessment,
                        risk_response=risk_response,
                        market_context=None,
                    )
                ).setup
            except Exception as exc:
                warnings.append(f"TradeSetup unavailable: {exc}")

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
                market_context_signal_preview = self._signal_engine.apply_market_context(
                    signal_assessment, market_regime
                )
                market_context_risk_preview = self._risk_engine.apply_market_context(
                    risk_response, market_regime
                )
                market_context_trade_setup_preview = AssessTradeSetupUseCase().execute(
                    AssessTradeSetupRequest(
                        ticker=request.ticker,
                        snapshot_date=request.today,
                        signal_response=market_context_signal_preview,
                        risk_response=market_context_risk_preview,
                        market_context=market_regime,
                    )
                ).setup
            except Exception as exc:
                warnings.append(f"Market context preview unavailable: {exc}")

        swing_config = self._load_swing_config()
        regime_label = market_regime.regime.value if market_regime else None
        take_profit_pct, stop_loss_pct = self._resolve_setup_targets(
            regime_label,
            swing_config,
        )
        if setup_entry is not None and request.capital is not None:
            try:
                setup_sizing = compute_percent_position_size(
                    entry=setup_entry,
                    capital=Decimal(str(request.capital)),
                    risk_pct=Decimal(str(request.risk_pct)) / Decimal("100"),
                    stop_loss_pct=stop_loss_pct,
                    take_profit_pct=take_profit_pct,
                )
            except ValueError as exc:
                warnings.append(f"Setup sizing unavailable: {exc}")

        verdict = SwingVerdict(
            trade_setup=trade_setup,
            signal_assessment=signal_assessment,
            risk_response=risk_response,
            market_regime=market_regime,
            market_context_signal_preview=market_context_signal_preview,
            market_context_risk_preview=market_context_risk_preview,
            market_context_trade_setup_preview=market_context_trade_setup_preview,
        )
        evidence = SwingEvidence(
            accumulation_candidate=accumulation_candidate,
            setup_eval=setup_eval,
            backtest_result=backtest_result,
            sentiment_response=sentiment_response,
            sentiment_warning=sentiment_warning,
            take_profit_pct=take_profit_pct,
            stop_loss_pct=stop_loss_pct,
            regime_label=regime_label,
        )
        diagnostics = SwingDiagnostics(
            data_freshness=data_freshness,
            flow_detail=flow_detail,
            broker_detail=broker_detail,
            broker_quality_note=broker_quality_note,
            refresh_actions=refresh_actions,
            warnings=tuple(warnings),
        )

        return SwingAnalysisWorkflowResponse(
            ticker=request.ticker,
            today=request.today,
            refresh_actions=refresh_actions,
            data_freshness=data_freshness,
            flow_detail=flow_detail,
            broker_detail=broker_detail,
            candles=candles,
            latest_close=latest_close,
            accumulation_candidate=accumulation_candidate,
            risk_response=risk_response,
            atr_value=atr_value,
            sizing=sizing,
            setup_eval=setup_eval,
            setup_sizing=setup_sizing,
            broker_quality_note=broker_quality_note,
            backtest_result=backtest_result,
            sentiment_response=sentiment_response,
            sentiment_warning=sentiment_warning,
            market_regime=market_regime,
            take_profit_pct=take_profit_pct,
            stop_loss_pct=stop_loss_pct,
            regime_label=regime_label,
            signal_assessment=signal_assessment,
            trade_setup=trade_setup,
            market_context_signal_preview=market_context_signal_preview,
            market_context_risk_preview=market_context_risk_preview,
            market_context_trade_setup_preview=market_context_trade_setup_preview,
            verdict=verdict,
            evidence=evidence,
            diagnostics=diagnostics,
            modules={
                "setup": request.setup_name is not None,
                "sizing": request.capital is not None,
                "strategy": request.strategy_name is not None,
                "sentiment": request.include_sentiment,
                "flow_detail": request.include_flow_detail,
                "signal_detail": request.include_signal_detail,
                "risk_detail": request.include_risk_detail,
                "market_detail": request.include_market_detail,
                "market_context": request.with_market_context,
                "technical_gate": request.with_technical_gate,
            },
            warnings=tuple(warnings),
        )

    def _compute_atr(self, candles: list[Any]) -> Decimal | None:
        try:
            atr_values = self._registry.compute("ATR", candles, 14)
            if atr_values:
                return atr_values[-1][1]
        except Exception:
            return None
        return None

class SwingAnalysisDataUnavailable(Exception):
    """Raised when a ticker has no local candle data for swing analysis."""

    def __init__(self, ticker: str) -> None:
        super().__init__(ticker)
        self.ticker = ticker
