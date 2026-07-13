"""
CLI implementation functions for saham analyze swing.

Public command registration lives in lifecycle routers:
  saham analyze swing

Layer: Adapter
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.analyze_swing_command_config import (
    AnalyzeSwingCommandConfig,
    load_analyze_swing_command_config,
)
from src.adapters.cli.analyze_swing_display import (
    SwingDisplayConfig,
    SwingOutputDisplayContext,
    SwingOutputDisplayOptions,
    print_swing_output,
)
from src.adapters.cli.analyze_swing_workflow_factory import (
    _fetch_swing_sentiment as _fetch_swing_sentiment_with_config,
)
from src.adapters.cli.analyze_swing_workflow_factory import (
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
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.config.user_config import get_swing_default

DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)
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
    cfg = load_analyze_swing_command_config()
    return _fetch_swing_sentiment_with_config(
        ticker=ticker,
        sentiment_verbose=sentiment_verbose,
        analyze_config=cfg.analyze_swing_config,
    )


def _evaluate_swing_setup(
    setup_name: str,
    accum: AccumulationCandidate | None,
    broker_detail: BrokerDetail | None = None,
    cfg: AnalyzeSwingCommandConfig | None = None,
) -> SetupEvaluation:
    """Evaluate audited setup fit for one accumulation candidate."""
    if cfg is None:
        cfg = load_analyze_swing_command_config()
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
    cfg: AnalyzeSwingCommandConfig | None = None,
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
        typer.Option("--setup", help="Swing setup to evaluate; omitted means no setup lens"),
    ] = None,
    window: Annotated[
        int,
        typer.Option("--window", "-w", help="Accumulation analysis window in broker sessions"),
    ] = APP_CFG.swing.window,
    flow_window: Annotated[
        Optional[int],
        typer.Option("--flow-window", help="Broker-flow detail window in broker sessions", min=1),
    ] = None,
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

    cfg = load_analyze_swing_command_config()

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
    include_signal_detail = with_signal_detail or explain or full
    include_risk_detail = with_risk_detail or explain or full
    include_market_detail = with_market_detail or explain or full

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

    if output_format == "json":
        out = workflow_response.to_dict(
            strategy_name=strategy_evidence_name,
            max_hold_days=cfg.swing_backtest_config.max_hold_days,
            include_sentiment=include_sentiment,
        )
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
        setup_sizing=setup_sizing,
        capital=capital,
    )
    print_swing_output(ctx)
