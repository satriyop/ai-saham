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
from typing import Any

from src.application.services.position_sizer import (
    PercentSizingResult,
    SizingResult,
    compute_percent_position_size,
    compute_position_size,
)
from src.application.services.strategy_loader import StrategyLoader, StrategyNotFoundError
from src.application.services.universe_loader import resolve_tickers
from src.application.use_case.assess_risk_use_case import AssessRiskRequest, AssessRiskUseCase
from src.domain.rules.risk_gate import GateContext, RiskGate
from src.application.use_case.backtest_use_case import BacktestRequest, BacktestUseCase
from src.application.use_case.market_regime_use_case import (
    MarketRegimeRequest,
    MarketRegimeResponse,
    MarketRegimeUseCase,
)
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository


@dataclass(frozen=True)
class SwingAnalysisWorkflowRequest:
    ticker: str
    today: date
    profile: str
    strategy: str
    preset_name: str | None
    window: int
    flow_window: int
    capital: int | None
    risk_pct: float
    entry_price: float | None
    atr_mult: float
    rr: float
    no_sentiment: bool
    sentiment_verbose: bool
    no_backtest: bool
    auto_refresh: bool
    force_refresh: bool
    with_regime: bool
    regime_universe: str
    benchmark: str
    risk_strategy: str | None
    db_path: Path


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
    preset_eval: Any | None
    preset_sizing: PercentSizingResult | None
    broker_quality_note: Any | None
    backtest_result: Any | None
    sentiment_response: Any | None
    sentiment_warning: str | None
    market_regime: MarketRegimeResponse | None
    take_profit_pct: Decimal
    stop_loss_pct: Decimal
    regime_label: str | None
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
        evaluate_preset: Callable[..., Any | None],
        build_broker_quality_note: Callable[..., Any | None],
        fetch_sentiment: Callable[..., tuple[Any | None, str | None]],
        load_swing_config: Callable[[], dict],
        resolve_preset_targets: Callable[[str | None, dict], tuple[Decimal, Decimal]],
        structural_gates: list[RiskGate] | None = None,
        execution_gates: list[RiskGate] | None = None,
    ) -> None:
        self._market_repo = market_repository
        self._broker_repo = broker_repository
        self._registry = registry
        self._refresh_data = refresh_data
        self._build_data_freshness = build_data_freshness
        self._build_flow_detail = build_flow_detail
        self._build_broker_detail = build_broker_detail
        self._build_accumulation_candidate = build_accumulation_candidate
        self._evaluate_preset = evaluate_preset
        self._build_broker_quality_note = build_broker_quality_note
        self._fetch_sentiment = fetch_sentiment
        self._load_swing_config = load_swing_config
        self._resolve_preset_targets = resolve_preset_targets
        self._structural_gates: list[RiskGate] = structural_gates or []
        self._execution_gates: list[RiskGate] = execution_gates or []

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
        flow_detail = self._build_flow_detail(
            ticker=request.ticker,
            broker_repo=self._broker_repo,
            window_sessions=request.flow_window,
            as_of_date=request.today,
        )
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

        risk_response = None
        try:
            risk_use_case = AssessRiskUseCase(
                repository=self._market_repo,
                registry=self._registry,
                structural_gates=self._structural_gates or None,
                execution_gates=self._execution_gates or None,
            )
            gate_ctx: GateContext | None = None
            if (self._structural_gates or self._execution_gates) and accumulation_candidate is not None:
                fund = accumulation_candidate.fundamentals
                bandar = accumulation_candidate.bandar_detector
                gate_ctx = GateContext(
                    ticker=request.ticker,
                    snapshot_date=request.today,
                    piotroski_f_score=fund.piotroski_f_score if fund else None,
                    market_cap_idr=fund.market_cap_idr if fund else None,
                    five_day_accdist=bandar.five_day_accdist if bandar else None,
                    bandar_is_distributing=bandar.is_distributing if bandar else False,
                )
            risk_response = risk_use_case.execute(
                AssessRiskRequest(
                    ticker=request.ticker,
                    profile=request.profile,
                    gate_context=gate_ctx,
                )
            )
        except Exception as exc:
            warnings.append(f"Risk assessment unavailable: {exc}")

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
                strategy_risk_level = strategy_response.assessment.risk_level_name
            except StrategyNotFoundError:
                warnings.append(
                    f"Risk strategy '{request.risk_strategy}' not found - gate skipped."
                )
            except Exception as exc:
                warnings.append(f"Risk strategy unavailable: {exc}")

        atr_value = self._compute_atr(candles)
        sizing: SizingResult | None = None
        preset_eval = None
        preset_sizing: PercentSizingResult | None = None
        if request.preset_name is not None:
            preset_eval = self._evaluate_preset(accumulation_candidate)

        broker_quality_note = self._build_broker_quality_note(
            broker_detail=broker_detail,
            preset_eval=preset_eval,
        )

        preset_entry: Decimal | None = None
        if request.capital is not None and preset_eval is not None and preset_eval.passed:
            preset_entry = (
                Decimal(str(request.entry_price))
                if request.entry_price
                else latest_close
            )
        elif request.capital is not None and atr_value and preset_eval is None:
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
        if not request.no_backtest:
            try:
                loader = StrategyLoader(registry=self._registry)
                rules_path = loader.resolve(request.strategy)
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
        if not request.no_sentiment:
            sentiment_response, sentiment_warning = self._fetch_sentiment(
                ticker=request.ticker,
                sentiment_verbose=request.sentiment_verbose,
            )

        market_regime = None
        if request.with_regime:
            try:
                market_regime = self._build_market_regime(request)
            except Exception as exc:
                warnings.append(f"Market regime unavailable: {exc}")

        swing_config = self._load_swing_config()
        regime_label = market_regime.label if market_regime else None
        take_profit_pct, stop_loss_pct = self._resolve_preset_targets(
            regime_label,
            swing_config,
        )
        if preset_entry is not None and request.capital is not None:
            try:
                preset_sizing = compute_percent_position_size(
                    entry=preset_entry,
                    capital=Decimal(str(request.capital)),
                    risk_pct=Decimal(str(request.risk_pct)) / Decimal("100"),
                    stop_loss_pct=stop_loss_pct,
                    take_profit_pct=take_profit_pct,
                )
            except ValueError as exc:
                warnings.append(f"Preset sizing unavailable: {exc}")

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
            preset_eval=preset_eval,
            preset_sizing=preset_sizing,
            broker_quality_note=broker_quality_note,
            backtest_result=backtest_result,
            sentiment_response=sentiment_response,
            sentiment_warning=sentiment_warning,
            market_regime=market_regime,
            take_profit_pct=take_profit_pct,
            stop_loss_pct=stop_loss_pct,
            regime_label=regime_label,
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

    def _build_market_regime(
        self,
        request: SwingAnalysisWorkflowRequest,
    ) -> MarketRegimeResponse:
        tickers = resolve_tickers(
            universe=request.regime_universe,
            explicit=[],
            db_path=request.db_path,
        )
        use_case = MarketRegimeUseCase(
            market_repository=self._market_repo,
            broker_repository=self._broker_repo,
        )
        return use_case.execute(
            MarketRegimeRequest(
                universe=tickers,
                benchmark_ticker=request.benchmark,
                as_of_date=request.today,
            )
        )


class SwingAnalysisDataUnavailable(Exception):
    """Raised when a ticker has no local candle data for swing analysis."""

    def __init__(self, ticker: str) -> None:
        super().__init__(ticker)
        self.ticker = ticker
