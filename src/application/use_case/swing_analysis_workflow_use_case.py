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
from src.application.services.signal_context_builder import (
    build_signal_context_from_candidate,
)
from src.application.services.strategy_loader import StrategyLoader, StrategyNotFoundError
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
    sensitivity: str
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
    risk_strategy: str | None
    db_path: Path
    with_technical_gate: bool = False


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
    strategy_risk_level: str | None
    strategy_risk_name: str | None
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
    modules: dict[str, bool] | None = None
    warnings: tuple[str, ...] = ()


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
                    benchmark=request.benchmark,
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
                    bandar_is_distributing=bandar.is_distributing if bandar else False,
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
                        sensitivity=request.sensitivity,
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
                    profile=request.sensitivity,
                    gate_context=gate_ctx,
                    market_context=None,
                )
            elif self._risk_engine is not None:
                risk_response = self._risk_engine.assess(
                    ticker=request.ticker,
                    profile=request.sensitivity,
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
                        sensitivity=request.sensitivity,
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

        strategy_risk_level = None
        strategy_risk_name = request.risk_strategy
        if request.risk_strategy:
            try:
                loader = StrategyLoader(registry=self._registry)
                rules_path = loader.resolve(request.risk_strategy)
                strategy_risk_use_case = AssessRiskUseCase(
                    repository=self._market_repo,
                    registry=self._registry,
                )
                strategy_response = strategy_risk_use_case.execute(
                    AssessRiskRequest(
                        ticker=request.ticker,
                        rules_file=rules_path,
                    )
                )
                strategy_risk_level = (
                    "HIGH_RISK"
                    if strategy_response.assessment.gate_triggered
                    else "LOW_RISK"
                )
            except StrategyNotFoundError:
                warnings.append(
                    f"Risk strategy '{request.risk_strategy}' not found - gate skipped."
                )
            except Exception as exc:
                warnings.append(f"Risk strategy unavailable: {exc}")

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
            strategy_risk_level=strategy_risk_level,
            strategy_risk_name=strategy_risk_name,
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
