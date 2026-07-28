"""
CLI implementation functions for saham plan swing.

Public command registration lives in lifecycle routers:
  saham plan swing

Layer: Adapter
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.effective_session_display import parse_as_of_option
from src.adapters.cli.plan_swing_command_config import (
    PlanSwingCommandConfig,
    load_plan_swing_command_config,
)
from src.adapters.cli.plan_swing_display import (
    SwingDisplayConfig,
    SwingOutputDisplayContext,
    SwingOutputDisplayOptions,
    print_swing_output,
)
from src.adapters.cli.plan_swing_optional_fetchers import (
    fetch_swing_sentiment as _fetch_swing_sentiment_with_config,
)
from src.adapters.cli.plan_swing_workflow_factory import (
    create_swing_analysis_workflow,
)
from src.application.dto.accumulation_screen import AccumulationCandidate
from src.application.dto.swing_analysis import SwingAnalysisWorkflowRequest
from src.application.dto.swing_broker_detail import BrokerDetail
from src.application.use_case.evaluate_swing_setup_use_case import (
    AVAILABLE_SWING_SETUPS,
    FOREIGN_BOUNCE_SETUP,
    EvaluateSwingSetupRequest,
    EvaluateSwingSetupUseCase,
)
from src.application.use_case.swing_analysis_workflow_use_case import SwingAnalysisDataUnavailable
from src.domain.value_objects.setup_evaluation import SetupEvaluation
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.user_config import get_swing_default

_W = 70  # display width

FOREIGN_BOUNCE_SETUP_NAME = FOREIGN_BOUNCE_SETUP

# Fixed fallback constants kept for backtest use; analyze/screen use resolve_setup_targets().
FOREIGN_BOUNCE_TAKE_PROFIT = Decimal("5")
FOREIGN_BOUNCE_STOP_LOSS = Decimal("5")


def _fetch_swing_sentiment(
    ticker: str,
    sentiment_verbose: bool,
):
    """Compatibility wrapper for tests and helper imports."""
    cfg = load_plan_swing_command_config()
    return _fetch_swing_sentiment_with_config(
        ticker=ticker,
        sentiment_verbose=sentiment_verbose,
        analyze_config=cfg.analyze_swing_config,
    )


def _evaluate_swing_setup(
    setup_name: str,
    accum: AccumulationCandidate | None,
    broker_detail: BrokerDetail | None = None,
    cfg: PlanSwingCommandConfig | None = None,
) -> SetupEvaluation:
    """Evaluate audited setup fit for one accumulation candidate."""
    if cfg is None:
        cfg = load_plan_swing_command_config()
    return EvaluateSwingSetupUseCase().execute(
        EvaluateSwingSetupRequest(
            setup_name=setup_name,
            candidate=accum,
            config=cfg.setup_config,
            broker_detail=broker_detail,
        )
    )


def _evaluate_foreign_bounce_setup(
    accum: "AccumulationCandidate | None",
    broker_detail: "BrokerDetail | None" = None,
    cfg: PlanSwingCommandConfig | None = None,
) -> "SetupEvaluation":
    """Convenience wrapper: evaluate the foreign-bounce setup for one candidate."""
    return _evaluate_swing_setup(FOREIGN_BOUNCE_SETUP_NAME, accum, broker_detail, cfg)


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
        typer.Option(
            "--setup",
            help=(
                "Named setup for structure gates / target template "
                "(foreign-bounce, coiled-spring, …); omitted = no setup lens"
            ),
        ),
    ] = None,
    window: Annotated[
        Optional[int],
        typer.Option("--window", "-w", help="Accumulation analysis window in broker sessions"),
    ] = None,
    flow_window: Annotated[
        Optional[int],
        typer.Option("--flow-window", help="Broker-flow detail window in broker sessions", min=1),
    ] = None,
    capital: Annotated[
        Optional[int],
        typer.Option(
            "--capital",
            "-c",
            help="Capital in IDR — enables structure sizing (lots / risk budget)",
        ),
    ] = None,
    risk_pct: Annotated[
        Optional[float],
        typer.Option("--risk-pct", help="% of capital at risk per trade (structure)"),
    ] = None,
    entry_price: Annotated[
        Optional[float],
        typer.Option("--entry", help="Structure entry price in IDR (default: latest close)"),
    ] = None,
    atr_mult: Annotated[
        Optional[float],
        typer.Option("--atr-mult", help="ATR multiplier for stop distance (structure)"),
    ] = None,
    rr: Annotated[
        Optional[float],
        typer.Option("--rr", help="Reward:risk ratio for target (structure)"),
    ] = None,
    with_sentiment: Annotated[
        bool,
        typer.Option("--with-sentiment", help="Include news sentiment evidence"),
    ] = False,
    with_flow_detail: Annotated[
        bool,
        typer.Option("--with-flow-detail", help="Include broker flow and attribution evidence"),
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
            help="Refresh this ticker's candles and broker flow before plan",
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
            help="Build MCE and condition the canonical signal/trade setup with market regime",
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
        Optional[str],
        typer.Option("--regime-universe", help="Universe for breadth context"),
    ] = None,
    benchmark: Annotated[
        Optional[str],
        typer.Option("--benchmark", help="Benchmark ticker for regime context"),
    ] = None,
    output_format: Annotated[
        Optional[str],
        typer.Option("--format", help="Output format: table or json"),
    ] = None,
    as_of: Annotated[
        Optional[str],
        typer.Option(
            "--as-of",
            help="Point-in-time as-of date YYYY-MM-DD (pins effective session; "
            "default: live today).",
        ),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Trade structure for a chosen swing candidate (ADR-054).

    Product job: design horizon / stop / target / lots for a name you already
    judged. Deep judgment (Action, Why, pattern match) is
    ``saham screen accum TICKER`` — do not use plan as a second screener.

    Still composes SignalEngine + RiskEngine -> TradeSetup (shared judgment path
    during migration). Core engine panels remain for context; strategy,
    sentiment, and flow detail stay opt-in evidence and do not override action.

    Structure-first examples:
        saham plan swing BBRI --capital 10000000
        saham plan swing BBRI --setup foreign-bounce --capital 10000000
        saham plan swing BBRI --capital 10000000 --risk-pct 1 --entry 4825 --rr 2.5
        saham plan swing BBRI --setup foreign-bounce --capital 10000000 --with-market-context

    Judgment first (recommended):
        saham screen accum BBRI
        saham plan swing BBRI --capital 10000000
    """
    app_cfg = load_app_config()
    resolved_db = db_path or Path(app_cfg.storage.db_path)
    window = window if window is not None else app_cfg.swing.window
    risk_pct = risk_pct if risk_pct is not None else app_cfg.swing.risk_pct
    atr_mult = atr_mult if atr_mult is not None else app_cfg.swing.atr_mult
    rr = rr if rr is not None else app_cfg.swing.rr
    regime_universe = regime_universe or app_cfg.analysis.regime_universe
    benchmark = benchmark or app_cfg.analysis.benchmark
    output_format = output_format or app_cfg.analysis.format
    ticker_upper = ticker.upper()
    today = parse_as_of_option(as_of) or date.today()

    cfg = load_plan_swing_command_config()

    resolved_flow_window = (
        flow_window
        if flow_window is not None
        else cfg.analyze_swing_config.flow_detail_window_sessions
    )

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
    # ADR-054 S4: structure-first — engine detail panels only with --full
    # (market detail also when --with-market-context for regime structure).
    include_signal_detail = full
    include_risk_detail = full
    include_market_detail = full or with_market_context

    smart_money_brokers = set(cfg.swing_config.smart_money_brokers)
    noise_brokers = set(cfg.swing_config.noise_brokers)
    broker_weights: dict[str, Decimal] = {
        **{code: cfg.swing_config.smart_weight for code in smart_money_brokers},
        **{code: cfg.swing_config.noise_weight for code in noise_brokers},
    }

    workflow = create_swing_analysis_workflow(
        db_path=resolved_db,
        setup_name=setup_name,
        swing_config=cfg.swing_config,
        analyze_config=cfg.analyze_swing_config,
        smart_money_brokers=smart_money_brokers,
        noise_brokers=noise_brokers,
        broker_weights=broker_weights,
    )
    try:
        workflow_response = workflow.execute(
            SwingAnalysisWorkflowRequest(
                ticker=ticker_upper,
                today=today,
                strategy_name=strategy_evidence_name,
                setup_name=setup_name,
                window=window,
                flow_window=resolved_flow_window,
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

    atr_value = workflow_response.atr_value
    sizing = workflow_response.sizing
    setup_sizing = workflow_response.setup_sizing

    trade_plan, plan_file = _build_and_persist_swing_trade_plan(
        ticker=ticker_upper,
        today=today,
        workflow_response=workflow_response,
        capital=capital,
        risk_pct=risk_pct,
        setup_name=setup_name,
        max_hold_days=cfg.swing_backtest_config.max_hold_days,
        with_market_context=with_market_context,
        with_technical_gate=with_technical_gate,
    )

    if output_format == "json":
        out = workflow_response.to_dict(
            strategy_name=strategy_evidence_name,
            max_hold_days=cfg.swing_backtest_config.max_hold_days,
            include_sentiment=include_sentiment,
        )
        out["swing_trade_plan"] = trade_plan.to_dict()
        out["swing_trade_plan_path"] = str(plan_file)
        typer.echo(json.dumps(out, indent=2, default=str))
        return

    display_config = SwingDisplayConfig(
        enter_min_score=cfg.swing_config.enter_min_score,
        watch_min_score=cfg.swing_config.watch_min_score,
        coiled_spring_bb_pctile=cfg.swing_config.coiled_spring_bb_pctile,
        coiled_spring_min_score=cfg.swing_config.coiled_spring_min_score,
        strong_min_score=cfg.swing_config.strong_min_score,
        strong_min_streak=cfg.swing_config.strong_min_streak,
        building_min_score=cfg.swing_config.building_min_score,
        building_min_streak=cfg.swing_config.building_min_streak,
        foreign_bounce_max_hold_days=cfg.swing_backtest_config.max_hold_days,
    )

    ctx = SwingOutputDisplayContext(
        ticker=ticker_upper,
        today=today,
        strategy_name=strategy_evidence_name or "-",
        window=window,
        verdict=verdict,
        evidence=evidence,
        diagnostics=diagnostics,
        options=SwingOutputDisplayOptions(
            include_strategy=strategy_evidence_name is not None,
            include_sentiment=include_sentiment,
            include_flow_detail=include_flow_detail,
            include_signal_detail=include_signal_detail,
            include_risk_detail=include_risk_detail,
            include_market_detail=include_market_detail,
            with_technical_gate=with_technical_gate,
            sentiment_verbose=sentiment_verbose,
        ),
        config=display_config,
        atr_value=atr_value,
        sizing=sizing,
        effective_session=workflow_response.effective_session,
        setup_sizing=setup_sizing,
        capital=capital,
    )
    print_swing_output(ctx)
    _echo_structure_desk_footer(
        ticker=ticker_upper,
        capital=capital,
        setup_name=setup_name,
        output_format=output_format or "table",
        plan_path=plan_file if trade_plan.is_complete else None,
        plan_id=trade_plan.plan_id,
    )


def _build_and_persist_swing_trade_plan(
    *,
    ticker: str,
    today,
    workflow_response,
    capital: int | None,
    risk_pct: float | None,
    setup_name: str | None,
    max_hold_days: int | None,
    with_market_context: bool,
    with_technical_gate: bool,
):
    """Build ADR-054 S5 artifact and persist latest plan file for --from-plan."""
    from src.application.services.swing_trade_plan_builder import build_swing_trade_plan
    from src.application.services.swing_trade_plan_store import (
        plans_dir_from_journal_path,
        save_swing_trade_plan,
    )
    from src.infrastructure.config.app_config import load_app_config

    cfg = load_app_config()
    plan = build_swing_trade_plan(
        ticker=ticker,
        as_of=today,
        trade_setup=workflow_response.trade_setup
        or (workflow_response.verdict.trade_setup if workflow_response.verdict else None),
        setup_eval=workflow_response.setup_eval,
        setup_name=setup_name,
        sizing=workflow_response.sizing,
        setup_sizing=workflow_response.setup_sizing,
        capital=capital,
        risk_pct=risk_pct,
        take_profit_pct=workflow_response.take_profit_pct,
        stop_loss_pct=workflow_response.stop_loss_pct,
        max_hold_days=max_hold_days,
        with_market_context=with_market_context,
        with_technical_gate=with_technical_gate,
        latest_close=workflow_response.latest_close,
    )
    plans_dir = plans_dir_from_journal_path(Path(cfg.storage.accum_journal))
    plan_file = save_swing_trade_plan(plan, plans_dir)
    return plan, plan_file


def _echo_structure_desk_footer(
    *,
    ticker: str,
    capital: int | None,
    setup_name: str | None,
    output_format: str,
    plan_path=None,
    plan_id: str | None = None,
) -> None:
    """ADR-054: structure desk footer + S5 plan handoff."""
    if output_format == "json":
        return
    typer.echo("")
    typer.echo("Structure desk (ADR-054): horizon / SL / TP / lots — not a second analysis desk.")
    typer.echo(
        "  Default Action inherits screen judgment; recompute only with "
        "--with-market-context or --with-technical-gate (S3)."
    )
    typer.echo(f"  Judgment case file:  saham screen accum {ticker}")
    if capital is None:
        typer.echo(
            f"  Structure sizing:    saham plan swing {ticker} --capital <IDR>"
            + (f" --setup {setup_name}" if setup_name else "")
        )
    else:
        typer.echo(f"  Paper notebook:      saham trade accum log --ticker {ticker} --from-plan")
    if plan_path is not None:
        typer.echo(f"  Plan artifact:       {plan_path}" + (f"  id={plan_id}" if plan_id else ""))
