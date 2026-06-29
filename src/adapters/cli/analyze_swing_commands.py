"""
CLI implementation functions for saham analyze swing commands.

Public command registration lives in lifecycle routers:
  saham analyze swing
  saham analyze swing-compare

Layer: Adapter
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Optional

import typer

from src.adapters.cli.analyze_swing_broker_display import (
    BrokerDetail,
    BrokerQualityNote,
    FlowDetail,
)
from src.adapters.cli.analyze_swing_display import (
    SwingDisplayConfig,
    display_swing_compare,
)
from src.adapters.cli.analyze_swing_workflow_factory import (
    create_swing_analysis_workflow,
    _fetch_swing_sentiment as _fetch_swing_sentiment_with_config,
)
from src.application.services.swing_data_freshness import (
    SwingDataFreshness as DataFreshness,
    expected_weekday_data_date as _expected_weekday_data_date,
    weekday_session_lag as _weekday_session_lag,
)
from src.application.services.universe_loader import (
    UniverseNotFoundError,
    resolve_tickers,
)
from src.application.services.swing_setup_catalog import build_swing_setup_catalog_config
from src.application.use_case.accumulation_screen_use_case import (
    AccumulationCandidate,
)
from src.application.use_case.evaluate_swing_setup_use_case import (
    AVAILABLE_SWING_SETUPS,
    EvaluateSwingSetupRequest,
    EvaluateSwingSetupUseCase,
    FOREIGN_BOUNCE_SETUP,
    SwingSetupCatalogConfig,
)
from src.domain.value_objects.market_context import MarketContext
from src.application.use_case.swing_analysis_workflow_use_case import (
    SwingAnalysisDataUnavailable,
    SwingAnalysisWorkflowRequest,
)
from src.application.use_case.swing_backtest_use_case import (
    SwingBacktestRequest,
    SwingBacktestResponse,
    SwingBacktestUseCase,
)
from src.application.use_case.swing_backtest_use_case import (
    FOREIGN_BOUNCE_SETUP as BACKTEST_FOREIGN_BOUNCE_SETUP,
)
from src.domain.value_objects.setup_evaluation import SetupEvaluation
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


def _fetch_swing_sentiment(
    ticker: str,
    sentiment_verbose: bool,
):
    """Compatibility wrapper for tests and helper imports."""
    return _fetch_swing_sentiment_with_config(
        ticker=ticker,
        sentiment_verbose=sentiment_verbose,
        analyze_config=_AS,
    )


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

    include_sentiment = with_sentiment or full
    include_flow_detail = with_flow_detail or full
    include_signal_detail = with_signal_detail or explain or full
    include_risk_detail = with_risk_detail or explain or full
    include_market_detail = with_market_detail or explain or full

    workflow = create_swing_analysis_workflow(
        db_path=resolved_db,
        setup_name=setup_name,
        swing_config=_SC,
        analyze_config=_AS,
        smart_money_brokers=SMART_MONEY_BROKERS,
        noise_brokers=NOISE_BROKERS,
        broker_weights=BROKER_WEIGHTS,
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

    verdict = workflow_response.verdict
    evidence = workflow_response.evidence
    diagnostics = workflow_response.diagnostics
    if verdict is None or evidence is None or diagnostics is None:
        typer.echo(
            "Internal error: swing workflow returned an incomplete grouped response.",
            err=True,
        )
        raise typer.Exit(1)

    data_freshness = diagnostics.data_freshness
    flow_detail = diagnostics.flow_detail
    broker_detail = diagnostics.broker_detail
    accum_candidate = evidence.accumulation_candidate
    risk_resp = verdict.risk_response
    atr_value = workflow_response.atr_value
    sizing = workflow_response.sizing
    setup_eval = evidence.setup_eval
    setup_sizing = workflow_response.setup_sizing
    broker_quality_note = diagnostics.broker_quality_note
    backtest_result = evidence.backtest_result
    sentiment_resp = evidence.sentiment_response
    sentiment_warning = evidence.sentiment_warning
    market_regime = verdict.market_regime

    if output_format == "json":
        out = workflow_response.to_dict(
            strategy_name=strategy_evidence_name,
            max_hold_days=_BT.max_hold_days,
            include_sentiment=include_sentiment,
        )
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
        signal_assessment=verdict.signal_assessment,
        trade_setup=verdict.trade_setup,
        market_context_signal_preview=verdict.market_context_signal_preview,
        market_context_risk_preview=verdict.market_context_risk_preview,
        market_context_trade_setup_preview=verdict.market_context_trade_setup_preview,
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

    if output_format != "json":
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
            "schema_version": 1,
            "artifact_type": "swing_compare",
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
