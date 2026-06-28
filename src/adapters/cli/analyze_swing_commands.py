"""
CLI implementation functions for saham analyze swing commands.

Public command registration lives in lifecycle routers:
  saham analyze swing
  saham analyze swing-compare

Layer: Adapter
"""

import json
import logging
from contextlib import contextmanager, nullcontext, redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
from typing import Annotated, Any, Optional

import typer

from src.adapters.cli.analyze_swing_broker_display import (
    BrokerDetail,
    BrokerQualityNote,
    FlowDetail,
    build_broker_detail,
    build_broker_quality_note,
    build_flow_detail,
)
from src.adapters.cli.analyze_swing_display import (
    SwingDisplayConfig,
    display_swing_compare,
)
from src.application.services.bootstrap import (
    create_indicator_registry,
    create_risk_engine,
    create_signal_engine,
)
from src.application.services.accumulation_screen_factory import (
    create_accumulation_screen_use_case,
)
from src.application.services.universe_loader import (
    UniverseNotFoundError,
    resolve_tickers,
)
from src.application.services.swing_setup_catalog import build_swing_setup_catalog_config
from src.application.use_case.accumulation_screen_use_case import (
    AccumulationCandidate,
    AccumulationScreenRequest,
    resolve_setup_targets,
)
from src.application.use_case.evaluate_swing_setup_use_case import (
    AVAILABLE_SWING_SETUPS,
    EvaluateSwingSetupRequest,
    EvaluateSwingSetupUseCase,
    FOREIGN_BOUNCE_SETUP,
    SwingSetupCatalogConfig,
)
from src.application.use_case.fetch_sentiment_use_case import (
    FetchSentimentRequest,
    FetchSentimentUseCase,
)
from src.domain.value_objects.market_context import MarketContext
from src.application.use_case.swing_analysis_workflow_use_case import (
    SwingAnalysisDataUnavailable,
    SwingAnalysisWorkflowRequest,
    SwingAnalysisWorkflowUseCase,
)
from src.domain.rules.bandar_gate import BandarGate
from src.domain.rules.free_float_gate import FreeFloatGate
from src.domain.rules.fundamental_gate import FundamentalGate
from src.domain.rules.liquidity_gate import LiquidityGate
from src.application.use_case.swing_backtest_use_case import (
    SwingBacktestRequest,
    SwingBacktestResponse,
    SwingBacktestUseCase,
)
from src.application.use_case.swing_backtest_use_case import (
    FOREIGN_BOUNCE_SETUP as BACKTEST_FOREIGN_BOUNCE_SETUP,
)
from src.domain.value_objects.setup_evaluation import SetupEvaluation
from src.infrastructure.browser.stockbit_provider_bundle import (
    create_readonly_stockbit_providers,
)
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.config.analyze_swing_config import (
    load_analyze_swing_config as _load_analyze_swing_config,
)
from src.infrastructure.config.swing_backtest_config import (
    load_swing_backtest_config as _load_swing_backtest_config,
)
from src.infrastructure.config.user_config import get_swing_default
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository
from src.infrastructure.sentiment import SentimentFactory

DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)
_W = 70  # display width

FOREIGN_BOUNCE_SETUP_NAME = FOREIGN_BOUNCE_SETUP

# Fixed fallback constants kept for backtest use; analyze/screen use resolve_setup_targets().
FOREIGN_BOUNCE_TAKE_PROFIT = Decimal("5")
FOREIGN_BOUNCE_STOP_LOSS = Decimal("5")

def _load_swing_workflow_config():
    """Load typed swing workflow config from split YAML policy files."""
    return _load_swing_config_typed()

SWING_COMPARE_VARIANTS: dict[str, tuple[str, ...]] = {
    "baseline": (),
    "sideways_only": ("NEUTRAL", "RISK_ON"),
    "weak_plus": ("VOLATILE", "NEUTRAL", "RISK_ON"),
}

from src.infrastructure.config.swing_config import (  # noqa: E402
    load_swing_config as _load_swing_config_typed,
)

# Load split swing workflow config; fall back to _SwingConfig defaults on any error.
_SC = _load_swing_config_typed()
_BT = _load_swing_backtest_config()
_AS = _load_analyze_swing_config()
_DISPLAY_CONFIG = SwingDisplayConfig(
    enter_min_score=_SC.enter_min_score,
    watch_min_score=_SC.watch_min_score,
    coiled_spring_bb_pctile=_SC.coiled_spring_bb_pctile,
    coiled_spring_min_score=_SC.coiled_spring_min_score,
    strong_min_score=_SC.strong_min_score,
    strong_min_streak=_SC.strong_min_streak,
    building_min_score=_SC.building_min_score,
    building_min_streak=_SC.building_min_streak,
    foreign_bounce_max_hold_days=_BT.max_hold_days,
)

SMART_MONEY_BROKERS = set(_SC.smart_money_brokers)
NOISE_BROKERS       = set(_SC.noise_brokers)


BROKER_WEIGHTS: dict[str, Decimal] = {
    **{code: _SC.smart_weight for code in SMART_MONEY_BROKERS},
    **{code: _SC.noise_weight for code in NOISE_BROKERS},
}


@dataclass(frozen=True)
class DataFreshness:
    """Cached source data dates used by a swing analysis run."""

    as_of_date: date
    candle_start: date | None
    candle_end: date | None
    broker_start: date | None
    broker_end: date | None
    warnings: tuple[str, ...]
    refresh_actions: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "as_of_date": self.as_of_date.isoformat(),
            "candles_from": self.candle_start.isoformat() if self.candle_start else None,
            "candles_through": self.candle_end.isoformat() if self.candle_end else None,
            "broker_flow_from": self.broker_start.isoformat() if self.broker_start else None,
            "broker_flow_through": self.broker_end.isoformat() if self.broker_end else None,
            "refresh_actions": list(self.refresh_actions),
            "warnings": list(self.warnings),
        }


def _expected_weekday_data_date(as_of_date: date) -> date:
    """Latest regular weekday session expected for a given analysis date."""
    if as_of_date.weekday() == 5:  # Saturday
        return as_of_date - timedelta(days=1)
    if as_of_date.weekday() == 6:  # Sunday
        return as_of_date - timedelta(days=2)
    return as_of_date


def _weekday_session_lag(latest: date | None, as_of_date: date) -> int | None:
    """Count regular weekday sessions from latest data through expected date."""
    if latest is None:
        return None
    expected = _expected_weekday_data_date(as_of_date)
    if latest >= expected:
        return 0
    current = latest + timedelta(days=1)
    lag = 0
    while current <= expected:
        if current.weekday() < 5:
            lag += 1
        current += timedelta(days=1)
    return lag


def _build_data_freshness(
    ticker: str,
    as_of_date: date,
    market_repo: SQLiteMarketRepository,
    broker_repo: SQLiteBrokerRepository,
    refresh_actions: tuple[str, ...] = (),
) -> DataFreshness:
    candle_range = market_repo.get_date_range(ticker)
    broker_range = broker_repo.get_date_range(ticker)
    candle_start, candle_end = candle_range if candle_range else (None, None)
    broker_start, broker_end = broker_range if broker_range else (None, None)

    warnings: list[str] = []
    if candle_end is None:
        warnings.append(f"No cached candle data for {ticker}.")
    else:
        lag = _weekday_session_lag(candle_end, as_of_date)
        if lag and lag > 0:
            warnings.append(
                f"Latest candle is {lag} trading session(s) before expected data date "
                f"({_expected_weekday_data_date(as_of_date)})."
            )

    if broker_end is None:
        warnings.append(f"No cached broker flow data for {ticker}.")
    else:
        lag = _weekday_session_lag(broker_end, as_of_date)
        if lag and lag > 0:
            warnings.append(
                f"Latest broker flow is {lag} trading session(s) before expected data date "
                f"({_expected_weekday_data_date(as_of_date)})."
            )

    if candle_end and broker_end and candle_end != broker_end:
        warnings.append(
            f"Candle date ({candle_end}) and broker flow date ({broker_end}) differ."
        )
    for action in refresh_actions:
        if "ERR:" in action:
            warnings.append(f"Refresh issue: {action}")

    return DataFreshness(
        as_of_date=as_of_date,
        candle_start=candle_start,
        candle_end=candle_end,
        broker_start=broker_start,
        broker_end=broker_end,
        warnings=tuple(warnings),
        refresh_actions=refresh_actions,
    )


def _auto_refresh_swing_data(
    ticker: str,
    db_path: Path,
    force_refresh: bool,
) -> tuple[str, ...]:
    """Refresh only the requested ticker for swing analysis."""
    from src.adapters.cli.fetch_market_commands import (
        _create_broker_provider,
        _fetch_broker,
        _fetch_candles,
    )

    actions: list[str] = []
    candles_status = _fetch_candles(
        ticker=ticker,
        days=_AS.market_refresh_days,
        db_path=db_path,
        provider_name="yahoo",
        refresh=force_refresh,
    )
    actions.append(f"candles={candles_status}")

    broker_provider, broker_provider_name = _create_broker_provider(None)
    broker_status = _fetch_broker(
        ticker=ticker,
        days=_AS.broker_refresh_days,
        db_path=db_path,
        broker_provider=broker_provider,
        refresh=force_refresh,
    )
    actions.append(f"broker({broker_provider_name})={broker_status}")

    return tuple(actions)


@contextmanager
def _quiet_sentiment_fetch(enabled: bool):
    """Suppress optional sentiment provider noise in composite swing output."""
    if not enabled:
        with nullcontext():
            yield
        return

    previous_disable = logging.root.manager.disable
    sink = StringIO()
    try:
        logging.disable(logging.CRITICAL)
        with redirect_stdout(sink), redirect_stderr(sink):
            yield
    finally:
        logging.disable(previous_disable)


def _fetch_swing_sentiment(
    ticker: str,
    sentiment_verbose: bool,
):
    """Fetch optional sentiment context without leaking provider noise by default."""
    try:
        with _quiet_sentiment_fetch(enabled=not sentiment_verbose):
            news_provider = SentimentFactory.create_news_provider()
            classifier = SentimentFactory.create_classifier(use_ai=False)
            sent_uc = FetchSentimentUseCase(
                news_provider=news_provider,
                classifier=classifier,
            )
            response = sent_uc.execute(FetchSentimentRequest(
                ticker=ticker,
                max_headlines=_AS.sentiment_max_headlines,
                days=_AS.sentiment_days,
            ))
        return response, response.warning
    except Exception as exc:
        if sentiment_verbose:
            return None, f"Sentiment fetch failed: {exc}"
        return None, "News unavailable (provider fetch failed)."


def _parse_compare_variants(value: str) -> tuple[str, ...]:
    variants = tuple(part.strip().lower() for part in value.split(",") if part.strip())
    if not variants:
        raise typer.BadParameter("--variants must contain at least one variant")
    invalid = [variant for variant in variants if variant not in SWING_COMPARE_VARIANTS]
    if invalid:
        available = ", ".join(SWING_COMPARE_VARIANTS)
        raise typer.BadParameter(
            f"Unknown variants: {', '.join(invalid)}. Available: {available}"
        )
    return variants


def _setup_config() -> SwingSetupCatalogConfig:
    return build_swing_setup_catalog_config(_SC)


def _evaluate_swing_setup(
    setup_name: str,
    accum: AccumulationCandidate | None,
    broker_detail: BrokerDetail | None = None,
) -> SetupEvaluation:
    """Evaluate audited setup fit for one accumulation candidate."""
    return EvaluateSwingSetupUseCase().execute(
        EvaluateSwingSetupRequest(
            setup_name=setup_name,
            candidate=accum,
            config=_setup_config(),
            broker_detail=broker_detail,
        )
    )


def _evaluate_foreign_bounce_setup(
    accum: "AccumulationCandidate | None",
    broker_detail: "BrokerDetail | None" = None,
) -> "SetupEvaluation":
    """Convenience wrapper: evaluate the foreign-bounce setup for one candidate."""
    return _evaluate_swing_setup(FOREIGN_BOUNCE_SETUP_NAME, accum, broker_detail)


def _print_swing_output(
    ticker: str,
    today: date,
    strategy_name: str,
    data_freshness: DataFreshness,
    flow_detail: FlowDetail | None,
    broker_detail: BrokerDetail | None,
    window: int,
    accum: "AccumulationCandidate | None",
    risk_resp,
    atr_value: "Decimal | None",
    sizing: "SizingResult | None",
    setup_eval: "SetupEvaluation | None",
    setup_sizing: "PercentSizingResult | None",
    broker_quality_note: BrokerQualityNote | None,
    market_regime: "MarketContext | None",
    capital: "int | None",
    backtest_result,
    sentiment_resp,
    sentiment_warning: str | None,
    sentiment_verbose: bool,
    include_strategy: bool,
    include_sentiment: bool,
    include_flow_detail: bool,
    include_signal_detail: bool,
    include_risk_detail: bool,
    include_market_detail: bool,
    strategy_risk_level: str | None = None,
    strategy_risk_name: str | None = None,
    signal_assessment=None,
    trade_setup=None,
    market_context_signal_preview=None,
    market_context_risk_preview=None,
    market_context_trade_setup_preview=None,
    with_technical_gate: bool = False,
) -> None:
    from src.adapters.cli.analyze_swing_display import print_swing_output

    print_swing_output(
        ticker=ticker,
        today=today,
        strategy_name=strategy_name,
        data_freshness=data_freshness,
        flow_detail=flow_detail,
        broker_detail=broker_detail,
        window=window,
        accum=accum,
        risk_resp=risk_resp,
        atr_value=atr_value,
        sizing=sizing,
        setup_eval=setup_eval,
        setup_sizing=setup_sizing,
        broker_quality_note=broker_quality_note,
        market_regime=market_regime,
        capital=capital,
        backtest_result=backtest_result,
        sentiment_resp=sentiment_resp,
        sentiment_warning=sentiment_warning,
        sentiment_verbose=sentiment_verbose,
        include_strategy=include_strategy,
        include_sentiment=include_sentiment,
        include_flow_detail=include_flow_detail,
        include_signal_detail=include_signal_detail,
        include_risk_detail=include_risk_detail,
        include_market_detail=include_market_detail,
        strategy_risk_level=strategy_risk_level,
        strategy_risk_name=strategy_risk_name,
        signal_assessment=signal_assessment,
        trade_setup=trade_setup,
        market_context_signal_preview=market_context_signal_preview,
        market_context_risk_preview=market_context_risk_preview,
        market_context_trade_setup_preview=market_context_trade_setup_preview,
        config=_DISPLAY_CONFIG,
        with_technical_gate=with_technical_gate,
    )


# ─── swing command ───────────────────────────────────────────────────────────

def swing(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBRI)")],
    strategy: Annotated[
        Optional[str],
        typer.Option(
            "--strategy",
            "-S",
            help="Strategy/backtest evidence name; omitted means strategy evidence is skipped",
        ),
    ] = None,
    setup: Annotated[
        Optional[str],
        typer.Option("--setup", help="Swing setup to evaluate; omitted means no setup lens"),
    ] = None,
    window: Annotated[
        int,
        typer.Option("--window", "-w", help="Accumulation analysis window in broker sessions"),
    ] = APP_CFG.swing.window,
    flow_window: Annotated[
        int,
        typer.Option("--flow-window", help="Broker-flow detail window in broker sessions", min=1),
    ] = _AS.flow_detail_window_sessions,
    capital: Annotated[
        Optional[int],
        typer.Option("--capital", "-c", help="Capital in IDR — enables position sizing block"),
    ] = None,
    risk_pct: Annotated[
        float,
        typer.Option("--risk-pct", help="% of capital at risk per trade"),
    ] = APP_CFG.swing.risk_pct,
    entry_price: Annotated[
        Optional[float],
        typer.Option("--entry", help="Entry price in IDR (default: latest close)"),
    ] = None,
    atr_mult: Annotated[
        float,
        typer.Option("--atr-mult", help="ATR multiplier for stop distance"),
    ] = APP_CFG.swing.atr_mult,
    rr: Annotated[
        float,
        typer.Option("--rr", help="Reward:risk ratio for target"),
    ] = APP_CFG.swing.rr,
    no_sentiment: Annotated[
        bool,
        typer.Option("--no-sentiment", help="Deprecated no-op; sentiment is off by default"),
    ] = False,
    with_sentiment: Annotated[
        bool,
        typer.Option("--with-sentiment", help="Include news sentiment evidence"),
    ] = False,
    with_flow_detail: Annotated[
        bool,
        typer.Option("--with-flow-detail", help="Include broker flow and attribution evidence"),
    ] = False,
    with_signal_detail: Annotated[
        bool,
        typer.Option("--with-signal-detail", help="Include signal factor detail"),
    ] = False,
    with_risk_detail: Annotated[
        bool,
        typer.Option("--with-risk-detail", help="Include risk indicator and gate detail"),
    ] = False,
    with_market_detail: Annotated[
        bool,
        typer.Option("--with-market-detail", help="Include full market-context factor detail"),
    ] = False,
    explain: Annotated[
        bool,
        typer.Option("--explain", help="Shortcut for signal, risk, and market details"),
    ] = False,
    full: Annotated[
        bool,
        typer.Option(
            "--full",
            help=(
                "Include all optional evidence except named setup; uses "
                "foreign-accumulation for strategy evidence when --strategy is omitted"
            ),
        ),
    ] = False,
    sentiment_verbose: Annotated[
        bool,
        typer.Option("--sentiment-verbose", help="Show sentiment provider errors/noise"),
    ] = False,
    no_backtest: Annotated[
        bool,
        typer.Option("--no-backtest", help="Deprecated compatibility; conflicts with --strategy"),
    ] = False,
    auto_refresh: Annotated[
        bool,
        typer.Option(
            "--auto-refresh/--no-refresh",
            help="Refresh this ticker's candles and broker flow before analysis",
        ),
    ] = True,
    force_refresh: Annotated[
        bool,
        typer.Option("--force-refresh", help="Force provider refresh even if cached data is fresh"),
    ] = False,
    with_market_context: Annotated[
        bool,
        typer.Option(
            "--with-market-context",
            help="Build MCE and display a what-if impact preview (does not change final TradeSetup)",
        ),
    ] = False,
    with_technical_gate: Annotated[
        bool,
        typer.Option(
            "--with-technical-gate",
            help="Enable the optional TechnicalGate (SMA/EMA/RSI) execution gate. Off by default.",
        ),
    ] = False,
    regime_universe: Annotated[
        str,
        typer.Option("--regime-universe", help="Universe for breadth context"),
    ] = APP_CFG.analysis.regime_universe,
    benchmark: Annotated[
        str,
        typer.Option("--benchmark", help="Benchmark ticker for regime context"),
    ] = APP_CFG.analysis.benchmark,
    risk_strategy: Annotated[
        Optional[str],
        typer.Option(
            "--risk-strategy",
            help=(
                "Deprecated compatibility risk gate. Prefer core RiskEngine verdict. "
                "If strategy signals HIGH_RISK, marks the setup plan as blocked/avoid."
            ),
        ),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = APP_CFG.analysis.format,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Unified composite swing trade analysis for a single stock.

    Core verdict: SignalEngine + RiskEngine -> TradeSetup.
    Market context, strategy, setup, sentiment, and detailed flow panels are opt-in evidence.

    Replaces the multi-command morning workflow:
      saham screen accum, saham analyze risk, saham indicator compute,
      saham trade backtest-swing, saham analyze sentiment — all in one.

    Examples:
        saham analyze swing BBRI
        saham analyze swing BBRI --setup foreign-bounce --capital 10000000
        saham analyze swing BBRI --capital 10000000 --risk-pct 1
        saham analyze swing BBRI --strategy foreign-accumulation
        saham analyze swing BBRI --with-flow-detail --explain
        saham analyze swing BBRI --force-refresh
        saham analyze swing BBRI --capital 10000000 --entry 4825 --rr 2.5
    """
    resolved_db = db_path or DEFAULT_DB_PATH
    ticker_upper = ticker.upper()
    today = date.today()

    if capital is None:
        _cfg = get_swing_default("capital")
        if _cfg is not None:
            capital = int(_cfg)

    setup_name = setup.lower() if setup else None
    if setup_name is not None and setup_name not in AVAILABLE_SWING_SETUPS:
        typer.echo(
            f"Unknown swing setup '{setup}'. Available setups: {', '.join(AVAILABLE_SWING_SETUPS)}",
            err=True,
        )
        raise typer.Exit(1)
    strategy_evidence_name = strategy or ("foreign-accumulation" if full else None)
    if strategy_evidence_name and no_backtest:
        typer.echo(
            "Conflict: strategy/backtest evidence is enabled, "
            "so it cannot be combined with deprecated --no-backtest.",
            err=True,
        )
        raise typer.Exit(1)

    include_sentiment = with_sentiment or full
    include_flow_detail = with_flow_detail or full
    include_signal_detail = with_signal_detail or explain or full
    include_risk_detail = with_risk_detail or explain or full
    include_market_detail = with_market_detail or explain or full

    market_repo = SQLiteMarketRepository(db_path=resolved_db)
    broker_repo = SQLiteBrokerRepository(resolved_db)
    registry = create_indicator_registry(
        broker_repository=broker_repo,
        market_repository=market_repo,
    )

    def _build_accumulation_candidate(ticker: str, window: int):
        _sb = create_readonly_stockbit_providers(resolved_db)
        accum_uc = create_accumulation_screen_use_case(
            broker_repository=broker_repo,
            market_repository=market_repo,
            stockbit_providers=_sb,
        )
        accum_resp = accum_uc.execute(
            AccumulationScreenRequest(
                tickers=[ticker],
                window_days=window,
                min_net_buy_days=_AS.candidate_min_net_buy_days,
                min_score=_AS.candidate_min_score,
                tier1_broker_codes=_SC.tier1_broker_codes,
                bci_cluster_min_count=_SC.bci_cluster_min_count,
                bci_stable_min_count=_SC.bci_stable_min_count,
                resistance_gate_enabled=_SC.resistance_gate_enabled,
                resistance_headroom_min_pct=_SC.resistance_headroom_min_pct,
                ex_date_warning_days=_SC.ex_date_warning_days,
            )
        )
        return accum_resp.candidates[0] if accum_resp.candidates else None

    workflow = SwingAnalysisWorkflowUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        registry=registry,
        refresh_data=_auto_refresh_swing_data,
        build_data_freshness=_build_data_freshness,
        build_flow_detail=build_flow_detail,
        build_broker_detail=lambda ticker, broker_repo, window_sessions=5, as_of_date=None: build_broker_detail(
            ticker=ticker,
            broker_repo=broker_repo,
            window_sessions=window_sessions,
            as_of_date=as_of_date,
            smart_money_brokers=SMART_MONEY_BROKERS,
            noise_brokers=NOISE_BROKERS,
            broker_weights=BROKER_WEIGHTS,
            smart_share_threshold_pct=_SC.smart_share_threshold_pct,
        ),
        build_accumulation_candidate=_build_accumulation_candidate,
        evaluate_setup=lambda candidate, broker_detail: _evaluate_swing_setup(
            setup_name,
            candidate,
            broker_detail,
        ),
        build_broker_quality_note=lambda broker_detail, setup_eval: build_broker_quality_note(
            broker_detail,
            setup_eval,
            smart_sell_min_share_pct=_SC.smart_sell_min_share_pct,
        ),
        fetch_sentiment=_fetch_swing_sentiment,
        load_swing_config=_load_swing_workflow_config,
        resolve_setup_targets=resolve_setup_targets,
        structural_gates=[FundamentalGate(), LiquidityGate(), FreeFloatGate()],
        execution_gates=[BandarGate()],
        signal_engine=create_signal_engine(db_path=resolved_db, with_enrichment=True),
        risk_engine=create_risk_engine(db_path=resolved_db, with_enrichment=True),
    )
    try:
        workflow_response = workflow.execute(
            SwingAnalysisWorkflowRequest(
                ticker=ticker_upper,
                today=today,
                sensitivity="balanced",
                strategy_name=strategy_evidence_name,
                setup_name=setup_name,
                window=window,
                flow_window=flow_window,
                capital=capital,
                risk_pct=risk_pct,
                entry_price=entry_price,
                atr_mult=atr_mult,
                rr=rr,
                include_sentiment=include_sentiment,
                include_flow_detail=include_flow_detail,
                include_signal_detail=include_signal_detail,
                include_risk_detail=include_risk_detail,
                include_market_detail=include_market_detail,
                sentiment_verbose=sentiment_verbose,
                auto_refresh=auto_refresh,
                force_refresh=force_refresh,
                with_market_context=with_market_context,
                regime_universe=regime_universe,
                benchmark=benchmark,
                risk_strategy=risk_strategy,
                db_path=resolved_db,
                with_technical_gate=with_technical_gate,
            )
        )
    except SwingAnalysisDataUnavailable:
        typer.echo(
            f"No data for {ticker_upper}. Run: saham fetch market {ticker_upper} --days 365",
            err=True,
        )
        raise typer.Exit(1)

    data_freshness = workflow_response.data_freshness
    flow_detail = workflow_response.flow_detail
    broker_detail = workflow_response.broker_detail
    accum_candidate = workflow_response.accumulation_candidate
    risk_resp = workflow_response.risk_response
    strategy_risk_level = workflow_response.strategy_risk_level
    strategy_risk_name = workflow_response.strategy_risk_name
    atr_value = workflow_response.atr_value
    sizing = workflow_response.sizing
    setup_eval = workflow_response.setup_eval
    setup_sizing = workflow_response.setup_sizing
    broker_quality_note = workflow_response.broker_quality_note
    backtest_result = workflow_response.backtest_result
    sentiment_resp = workflow_response.sentiment_response
    sentiment_warning = workflow_response.sentiment_warning
    market_regime = workflow_response.market_regime
    _tp_pct = workflow_response.take_profit_pct
    _sl_pct = workflow_response.stop_loss_pct
    _regime_label = workflow_response.regime_label

    if output_format == "json":
        data_out = data_freshness.to_dict()
        if market_regime is not None:
            data_out["regime_as_of"] = market_regime.as_of_date.isoformat()
        out: dict = {
            "ticker": ticker_upper,
            "date": str(today),
            "modules": workflow_response.modules or {},
            "data": data_out,
            "flow_detail": flow_detail.to_dict() if flow_detail else None,
            "broker_detail": broker_detail.to_dict() if broker_detail else None,
            "broker_quality_note": (
                broker_quality_note.to_dict() if broker_quality_note else None
            ),
            "accumulation": {
                "score": accum_candidate.score if accum_candidate else None,
                "streak": accum_candidate.consecutive_streak if accum_candidate else None,
                "trend": accum_candidate.trend if accum_candidate else None,
                "flow_pct": accum_candidate.avg_flow_ratio if accum_candidate else None,
                "vwap_disc_pct": accum_candidate.vwap_discount_pct if accum_candidate else None,
                "bb_width_pctile": accum_candidate.bb_width_pctile if accum_candidate else None,
                "dividend_risk": accum_candidate.dividend_risk if accum_candidate else False,
                "rights_issue_risk": accum_candidate.rights_issue_risk if accum_candidate else False,
                "upcoming_rups": accum_candidate.upcoming_rups if accum_candidate else [],
                "seasonal_score": (
                    accum_candidate.seasonal_edge.score
                    if accum_candidate and accum_candidate.seasonal_edge else None
                ),
                "seasonal_label": (
                    accum_candidate.seasonal_edge.label
                    if accum_candidate and accum_candidate.seasonal_edge else None
                ),
                "insider_buying": accum_candidate.insider_buying if accum_candidate else False,
                "recent_insider_buys": accum_candidate.recent_insider_buys if accum_candidate else [],
                "analyst_consensus": (
                    accum_candidate.analyst_consensus.to_dict()
                    if accum_candidate and accum_candidate.analyst_consensus else None
                ),
                "shareholding": (
                    accum_candidate.shareholding.to_dict()
                    if accum_candidate and accum_candidate.shareholding else None
                ),
                "bandar_detector": (
                    accum_candidate.bandar_detector.to_dict()
                    if accum_candidate and accum_candidate.bandar_detector else None
                ),
                "fundamentals": (
                    accum_candidate.fundamentals.to_dict()
                    if accum_candidate and accum_candidate.fundamentals else None
                ),
                "ticker_notation": (
                    accum_candidate.ticker_notation.to_dict()
                    if accum_candidate and accum_candidate.ticker_notation else None
                ),
            },
            "setup": {
                "name": setup_eval.name if setup_eval else None,
                "passed": setup_eval.passed if setup_eval else None,
                "match": setup_eval.match.value if setup_eval else None,
                "failed_reasons": list(setup_eval.failed_reasons) if setup_eval else [],
                "plan": {
                    "take_profit_pct": float(_tp_pct) if setup_eval else None,
                    "stop_loss_pct": float(_sl_pct) if setup_eval else None,
                    "regime": _regime_label,
                    "max_hold_days": _BT.max_hold_days if setup_eval else None,
                },
            } if setup_eval else None,
            "risk": {
                "level": risk_resp.assessment.risk_level_name if risk_resp else None,
                "confidence": risk_resp.assessment.confidence if risk_resp else None,
                "sma20": float(risk_resp.assessment.indicators.sma) if risk_resp else None,
                "ema20": float(risk_resp.assessment.indicators.ema) if risk_resp else None,
                "rsi14": float(risk_resp.assessment.indicators.rsi) if risk_resp else None,
            },
            "sizing": {
                "entry": float(
                    setup_sizing.entry_price if setup_sizing
                    else sizing.entry_price
                ) if (setup_sizing or sizing) else None,
                "stop": float(
                    setup_sizing.stop_price if setup_sizing
                    else sizing.stop_price
                ) if (setup_sizing or sizing) else None,
                "target": float(
                    setup_sizing.target_price if setup_sizing
                    else sizing.target_price
                ) if (setup_sizing or sizing) else None,
                "lots": (
                    setup_sizing.lots if setup_sizing
                    else sizing.lots if sizing else None
                ),
                "atr": float(atr_value) if atr_value else None,
            },
            "strategy_evidence": {
                "name": strategy_evidence_name,
                "win_rate": float(backtest_result.win_rate) if backtest_result else None,
                "profit_factor": float(backtest_result.profit_factor) if backtest_result else None,
                "max_drawdown_pct": (
                    float(backtest_result.max_drawdown_pct)
                    if backtest_result else None
                ),
                "trade_count": backtest_result.trade_count if backtest_result else None,
            } if strategy_evidence_name else None,
            "sentiment": {
                "call": (
                    sentiment_resp.snapshot.overall_sentiment.value
                    if sentiment_resp and not sentiment_resp.warning else None
                ),
                "warning": sentiment_warning,
                "total_headlines": (
                    sentiment_resp.snapshot.total_count
                    if sentiment_resp and not sentiment_resp.warning else None
                ),
                "confidence_pct": (
                    sentiment_resp.snapshot.confidence_pct
                    if sentiment_resp and not sentiment_resp.warning else None
                ),
            } if include_sentiment else None,
            "market_regime": market_regime.to_dict() if market_regime else None,
            "signal_assessment": {
                "score": workflow_response.signal_assessment.assessment.score,
                "strength": workflow_response.signal_assessment.assessment.strength.value,
                "entry_quality": workflow_response.signal_assessment.assessment.entry_quality.value,
                "breakdown": workflow_response.signal_assessment.assessment.breakdown_dict,
                "coverage_warning": workflow_response.signal_assessment.coverage_warning,
            } if workflow_response.signal_assessment else None,
            "trade_setup": workflow_response.trade_setup.to_dict() if workflow_response.trade_setup else None,
            "market_context_preview": {
                "signal_preview": {
                    "score": _mcs.assessment.score,
                    "strength": _mcs.assessment.strength.value,
                    "entry_quality": _mcs.assessment.entry_quality.value,
                } if (_mcs := workflow_response.market_context_signal_preview) else None,
                "risk_preview": {
                    "level": _mcr.assessment.risk_level_name,
                    "gate_triggered": _mcr.assessment.gate_triggered,
                } if (_mcr := workflow_response.market_context_risk_preview) else None,
                "trade_setup_preview": (
                    workflow_response.market_context_trade_setup_preview.to_dict()
                    if workflow_response.market_context_trade_setup_preview else None
                ),
            } if market_regime else None,
        }
        typer.echo(json.dumps(out, indent=2, default=str))
        return

    _print_swing_output(
        ticker=ticker_upper,
        today=today,
        strategy_name=strategy_evidence_name or "-",
        data_freshness=data_freshness,
        flow_detail=flow_detail,
        broker_detail=broker_detail,
        window=window,
        accum=accum_candidate,
        risk_resp=risk_resp,
        atr_value=atr_value,
        sizing=sizing,
        setup_eval=setup_eval,
        setup_sizing=setup_sizing,
        broker_quality_note=broker_quality_note,
        market_regime=market_regime,
        capital=capital,
        backtest_result=backtest_result,
        sentiment_resp=sentiment_resp,
        sentiment_warning=sentiment_warning,
        sentiment_verbose=sentiment_verbose,
        include_strategy=strategy_evidence_name is not None,
        include_sentiment=include_sentiment,
        include_flow_detail=include_flow_detail,
        include_signal_detail=include_signal_detail,
        include_risk_detail=include_risk_detail,
        include_market_detail=include_market_detail,
        strategy_risk_level=strategy_risk_level,
        strategy_risk_name=strategy_risk_name,
        signal_assessment=workflow_response.signal_assessment,
        trade_setup=workflow_response.trade_setup,
        market_context_signal_preview=workflow_response.market_context_signal_preview,
        market_context_risk_preview=workflow_response.market_context_risk_preview,
        market_context_trade_setup_preview=workflow_response.market_context_trade_setup_preview,
        with_technical_gate=with_technical_gate,
    )


def swing_compare(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option("--universe", "-u", help="Universe name or 'cached' — see `saham fetch universe list`"),
    ] = None,
    variants: Annotated[
        str,
        typer.Option(
            "--variants",
            help="Comma-separated variants: baseline, sideways_only, weak_plus",
        ),
    ] = "baseline,sideways_only,weak_plus",
    setup: Annotated[
        str,
        typer.Option("--setup", help="Swing setup to validate"),
    ] = BACKTEST_FOREIGN_BOUNCE_SETUP,
    start: Annotated[
        str,
        typer.Option("--start", help="Backtest start date, YYYY-MM-DD"),
    ] = APP_CFG.backtest.start_date,
    end: Annotated[
        Optional[str],
        typer.Option("--end", help="Backtest end date, YYYY-MM-DD (default: today)"),
    ] = None,
    capital: Annotated[
        int,
        typer.Option("--capital", "-c", help="Initial capital in IDR", min=1),
    ] = _BT.capital,
    risk_pct: Annotated[
        float,
        typer.Option("--risk-pct", help="% of capital risked per trade", min=0.01),
    ] = _BT.risk_pct,
    max_positions: Annotated[
        int,
        typer.Option("--max-positions", help="Maximum concurrent open positions", min=1),
    ] = _BT.max_positions,
    take_profit: Annotated[
        float,
        typer.Option("--take-profit", help="Take-profit percentage", min=0.01),
    ] = _BT.take_profit_pct,
    stop_loss: Annotated[
        float,
        typer.Option("--stop-loss", help="Stop-loss percentage", min=0.01),
    ] = _BT.stop_loss_pct,
    max_hold: Annotated[
        int,
        typer.Option("--max-hold", help="Maximum holding period in trading days", min=1),
    ] = _BT.max_hold_days,
    cost_bps: Annotated[
        float,
        typer.Option(
            "--cost-bps",
            help="One-way transaction cost in basis points (20 ~= 0.20%)",
            min=0,
        ),
    ] = _BT.cost_bps,
    benchmark: Annotated[
        str,
        typer.Option("--benchmark", help="Benchmark ticker for regime context"),
    ] = APP_CFG.analysis.benchmark,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = APP_CFG.analysis.format,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Compare swing backtest regime variants side-by-side.

    Variants use the same portfolio simulation as `saham trade backtest-swing`;
    only the allowed entry regimes differ.
    """
    setup_name = setup.lower()
    if setup_name not in AVAILABLE_SWING_SETUPS:
        typer.echo(
            f"Unknown swing setup '{setup}'. "
            f"Available setups: {', '.join(AVAILABLE_SWING_SETUPS)}",
            err=True,
        )
        raise typer.Exit(1)

    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end) if end else date.today()
        variant_names = _parse_compare_variants(variants)
    except ValueError as e:
        typer.echo(f"Error: invalid date format: {e}", err=True)
        raise typer.Exit(1)
    except typer.BadParameter as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    resolved_db = db_path or DEFAULT_DB_PATH
    try:
        ticker_list = resolve_tickers(
            universe=universe,
            explicit=list(tickers) if tickers else [],
            db_path=resolved_db,
        )
    except (UniverseNotFoundError, FileNotFoundError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if not ticker_list:
        typer.echo(
            "No tickers to compare. Specify --universe or provide ticker arguments.",
            err=True,
        )
        raise typer.Exit(1)

    typer.echo(
        f"Comparing {len(variant_names)} variants over {len(ticker_list)} tickers | "
        f"{start_date} to {end_date}..."
    )

    use_case = SwingBacktestUseCase(
        broker_repository=SQLiteBrokerRepository(resolved_db),
        market_repository=SQLiteMarketRepository(db_path=resolved_db),
    )
    rows: list[tuple[str, SwingBacktestResponse]] = []
    try:
        for variant in variant_names:
            allowed_regimes = SWING_COMPARE_VARIANTS[variant]
            response = use_case.execute(SwingBacktestRequest(
                tickers=ticker_list,
                start_date=start_date,
                end_date=end_date,
                setup=setup_name,
                capital=Decimal(str(capital)),
                risk_pct=Decimal(str(risk_pct)) / Decimal("100"),
                max_positions=max_positions,
                take_profit_pct=Decimal(str(take_profit)),
                stop_loss_pct=Decimal(str(stop_loss)),
                max_hold_days=max_hold,
                cost_bps=Decimal(str(cost_bps)),
                include_regime=True,
                benchmark_ticker=benchmark,
                allowed_regimes=allowed_regimes,
                setup_config=_setup_config(),
                resistance_gate_enabled=_SC.resistance_gate_enabled,
                resistance_headroom_min_pct=_SC.resistance_headroom_min_pct,
                ex_date_warning_days=_SC.ex_date_warning_days,
                forward_data_lookahead_days=_BT.forward_data_lookahead_days,
                same_day_exit_priority=_BT.same_day_exit_priority,
            ))
            rows.append((variant, response))
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if output_format == "json":
        typer.echo(json.dumps({
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "ticker_count": len(ticker_list),
            "variants": [
                {
                    "name": name,
                    "allowed_regimes": list(SWING_COMPARE_VARIANTS[name]),
                    "cost_bps": str(response.cost_bps),
                    "total_return_pct": response.total_return_pct,
                    "max_drawdown_pct": response.max_drawdown_pct,
                    "trade_count": response.trade_count,
                    "win_rate_pct": response.win_rate_pct,
                    "profit_factor": response.profit_factor,
                    "exposure_pct": response.exposure_pct,
                    "skipped_by_regime": response.skipped_by_regime,
                }
                for name, response in rows
            ],
        }, indent=2, default=str))
        return

    display_swing_compare(
        rows=rows,
        start_date=start_date,
        end_date=end_date,
        universe_label=universe or "explicit",
        variants_by_name=SWING_COMPARE_VARIANTS,
    )
