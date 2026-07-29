"""
CLI implementation for saham screen accum command.

Public command registration lives in lifecycle routers:
  saham screen accum

Layer: Adapter
"""

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.effective_session_display import parse_as_of_option
from src.adapters.cli.screen_accum_display import (
    display_multi,
    display_results,
    print_column_guide,
)
from src.adapters.cli.screen_accum_formatters import (
    AccumulationDisplayConfig,
    accumulation_display_config_from_screener,
)
from src.adapters.cli.screen_contract_cli import echo_json, resolve_output_format
from src.adapters.composition.screen_accum_request import build_screen_accum_request
from src.adapters.composition.screen_deps import build_screen_deps
from src.application.dto.screen_accum_payload import (
    build_accum_multi_envelope,
    build_accum_single_envelope,
)
from src.application.services.screen_accum_result_projector import (
    ScreenAccumProjectionError,
)
from src.application.services.screen_judgment_deep_evidence import (
    ScreenJudgmentDeepEvidenceRequest,
)
from src.application.services.universe_loader import (
    UniverseNotFoundError,
    resolve_tickers,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.plan_swing_config import load_plan_swing_config
from src.infrastructure.config.universe_config_loader import YamlUniverseConfigLoader

FOREIGN_BOUNCE_SETUP = "foreign-bounce"


def accumulation_run(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option(
            "--universe",
            "-u",
            help="Universe name or 'cached' — see `saham fetch universe list`",
        ),
    ] = None,
    window: Annotated[
        int,
        typer.Option(
            "--window",
            "-w",
            help="Judgment window in broker sessions (7, 30, or 90)",
            min=3,
        ),
    ] = 7,
    min_streak: Annotated[
        int,
        typer.Option("--min-streak", help="Minimum consecutive buy days required", min=0),
    ] = 0,
    min_accum_score: Annotated[
        Optional[float],
        typer.Option(
            "--min-foreign-flow-score",
            help="Minimum composite foreign-flow score (0-100; config default)",
            min=0,
        ),
    ] = None,
    min_signal_score: Annotated[
        Optional[float],
        typer.Option(
            "--min-signal-score",
            help=(
                "Optional minimum SignalEngine score "
                "(0–100; disabled unless set or enabled in config)"
            ),
            min=0,
            max=100,
        ),
    ] = None,
    min_piotroski: Annotated[
        int,
        typer.Option(
            "--min-piotroski", help="Minimum Piotroski F-Score 0–9 (0 = disabled)", min=0, max=9
        ),
    ] = 0,
    vwap_only: Annotated[
        bool,
        typer.Option("--vwap-only", help="Only show stocks where foreigners are underwater"),
    ] = False,
    squeeze_only: Annotated[
        bool,
        typer.Option(
            "--squeeze-only", help="Only show stocks in BB squeeze (BB width pctile ≤ 20%)"
        ),
    ] = False,
    top: Annotated[
        int,
        typer.Option("--top", help="Show top N results", min=1),
    ] = 20,
    show_top_broker: Annotated[
        bool,
        typer.Option(
            "--top-broker", help="Show top broker-code detail and BCI label when available"
        ),
    ] = False,
    multi: Annotated[
        bool,
        typer.Option("--multi", help="Show scores across multiple windows side-by-side"),
    ] = False,
    windows: Annotated[
        Optional[str],
        typer.Option(
            "--windows",
            help="Comma-separated broker-session windows for --multi (default: 7,30,90)",
        ),
    ] = None,
    sort_by: Annotated[
        str,
        typer.Option(
            "--sort-by",
            help=(
                "Sort order: signal|score|vwap (single); "
                "signal|score|vwap|avg|max|7s|30s|90s (multi; legacy 7d/30d/90d accepted). "
                "Default: signal (SignalEngine total high→low). "
                "score = Accum composite; vwap = deepest Disc% first."
            ),
        ),
    ] = "signal",
    output_format: Annotated[
        Optional[str],
        typer.Option("--format", help="Output format: table or json"),
    ] = None,
    guide: Annotated[
        bool,
        typer.Option("--guide", help="Print column reference guide and exit (no screen needed)"),
    ] = False,
    detail: Annotated[
        bool,
        typer.Option(
            "--detail",
            help="Append run context and scoring definitions after results",
        ),
    ] = False,
    strategy: Annotated[
        Optional[str],
        typer.Option(
            "--strategy",
            "-S",
            help=(
                "Board: strategy signal column. Explicit ticker + deep flags/--full: "
                "also attach strategy backtest diagnostic evidence (does not change Action)."
            ),
        ),
    ] = None,
    setup: Annotated[
        Optional[str],
        typer.Option(
            "--setup",
            help=(
                "Named setup lens for pattern gates (foreign-bounce, …). "
                "Explicit tickers only; diagnostic (MATCH ≠ ENTER)."
            ),
        ),
    ] = None,
    with_flow_detail: Annotated[
        bool,
        typer.Option(
            "--with-flow-detail",
            help=(
                "Include broker flow detail diagnostic evidence "
                "(explicit tickers only; does not change Action)."
            ),
        ),
    ] = False,
    flow_window: Annotated[
        Optional[int],
        typer.Option(
            "--flow-window",
            help="Broker-flow detail window in sessions (default: plan_swing config).",
            min=1,
        ),
    ] = None,
    with_sentiment: Annotated[
        bool,
        typer.Option(
            "--with-sentiment",
            help=(
                "Include news sentiment diagnostic evidence "
                "(explicit tickers only; fail-soft; does not change Action)."
            ),
        ),
    ] = False,
    sentiment_verbose: Annotated[
        bool,
        typer.Option(
            "--sentiment-verbose",
            help="Show sentiment provider errors/noise.",
        ),
    ] = False,
    full: Annotated[
        bool,
        typer.Option(
            "--full",
            help=(
                "All optional diagnostic evidence panels for explicit tickers "
                "(does not change Action; not structure/sizing — use plan swing --capital)."
            ),
        ),
    ] = False,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
    save_name: Annotated[
        Optional[str],
        typer.Option(
            "--save", help="Save results to watchlist under this name (e.g. morning-watch)"
        ),
    ] = None,
    as_of: Annotated[
        Optional[str],
        typer.Option(
            "--as-of",
            help="Point-in-time as-of date YYYY-MM-DD (pins effective session; default: live).",
        ),
    ] = None,
    auto_refresh: Annotated[
        bool,
        typer.Option(
            "--auto-refresh/--no-refresh",
            help=(
                "Refresh candles/broker for explicit ticker args before screen "
                "(ADR-054 S1). Ignored for universe-only runs (keeps board cheap)."
            ),
        ),
    ] = True,
    force_refresh: Annotated[
        bool,
        typer.Option(
            "--force-refresh",
            help=(
                "Force provider refresh for explicit tickers even if cache looks fresh. "
                "Requires ticker arguments (not universe-only)."
            ),
        ),
    ] = False,
) -> None:
    """
    Find and judge foreign-accumulation candidates (ADR-054 judgment desk).

    Product job: rank a universe or deep-judge one ticker. Owns Action / Why /
    pattern match / signal+risk (production evidence) + optional diagnostic
    evidence panels. Does **not** design trade geometry — that is
    ``saham plan swing TICKER`` (horizon / SL / TP / lots).

    Modes:
      --universe / list  → cheap shortlist board (filters, multi-window, patterns)
      TICKER             → judgment case file. Optional diagnostic evidence flags
                           (explicit only): --setup, --with-flow-detail,
                           --with-sentiment, --full.

    Deep flags are rejected with --universe-only or --multi (keep board cheap).

    Next after judgment:
        saham plan swing TICKER --capital 10000000
        saham trade accum log --ticker TICKER --from-plan

    Examples:
        saham screen accum --universe lq45
        saham screen accum BBRI
        saham screen accum BBRI --with-flow-detail --with-sentiment
        saham screen accum BBRI --setup foreign-bounce --full
        saham screen accum BBRI --format json
        saham screen accum --universe lq45 --multi
        saham screen accum --guide
    """
    if guide:
        print_column_guide()
        return

    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)
    output_format = resolve_output_format(output_format or cfg.analysis.format)
    deps = build_screen_deps(resolved_db)

    accumulation_config = deps.screener_config
    display_config = accumulation_display_config_from_screener(accumulation_config)

    try:
        ticker_list = resolve_tickers(
            universe=universe,
            explicit=list(tickers) if tickers else [],
            db_path=resolved_db,
            loader=YamlUniverseConfigLoader(),
            repository=deps.broker_repository,
        )
    except UniverseNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if not ticker_list:
        typer.echo(
            "No tickers to screen. Specify --universe or provide ticker arguments.",
            err=True,
        )
        raise typer.Exit(1)

    universe_label = universe or f"{len(ticker_list)} tickers"
    explicit_tickers = [str(t).upper() for t in (tickers or ())]

    if force_refresh and not explicit_tickers:
        typer.echo(
            "Error: --force-refresh requires explicit ticker arguments "
            "(not universe-only). Universe screens stay cache-cheap.",
            err=True,
        )
        raise typer.Exit(1)

    if strategy and multi:
        typer.echo("Error: --strategy is not supported with --multi.", err=True)
        raise typer.Exit(1)

    include_strategy_overlay = bool(strategy)

    if save_name and multi:
        typer.echo("Error: --save is not supported with --multi.", err=True)
        raise typer.Exit(1)
    save_enabled = bool(save_name)
    as_of_date = parse_as_of_option(as_of)

    # ADR-054 S1: refresh only explicit tickers (judgment desk), never full universe.
    if explicit_tickers and (auto_refresh or force_refresh):
        _refresh_explicit_tickers_for_screen(
            tickers=explicit_tickers,
            db_path=resolved_db,
            force_refresh=force_refresh,
            quiet=output_format == "json",
        )

    resolved_flow_window = (
        flow_window
        if flow_window is not None
        else load_plan_swing_config().flow_detail_window_sessions
    )
    deep_flags = ScreenJudgmentDeepEvidenceRequest(
        setup_name=setup.lower() if setup else None,
        include_flow_detail=with_flow_detail,
        flow_window=resolved_flow_window,
        include_sentiment=with_sentiment,
        sentiment_verbose=sentiment_verbose,
        include_strategy_evidence=bool(strategy) and (full or with_flow_detail or with_sentiment),
        strategy_name=strategy,
        include_full=full,
    )
    if deep_flags.any_enabled:
        if multi:
            typer.echo(
                "Error: deep analysis flags (--setup/--with-flow-detail/"
                "--with-sentiment/--full) are not supported with --multi. "
                "Use explicit tickers without --multi.",
                err=True,
            )
            raise typer.Exit(1)
        if not explicit_tickers:
            typer.echo(
                "Error: deep analysis flags require explicit ticker arguments "
                "(not universe-only). Example: saham screen accum BBRI --full",
                err=True,
            )
            raise typer.Exit(1)

    if multi:
        window_list = [int(w.strip()) for w in (windows or "7,30,90").split(",")]
        if output_format != "json":
            typer.echo(
                f"Screening {len(ticker_list)} tickers | windows: "
                f"{', '.join(str(w) + ' sessions' for w in window_list)}..."
            )
    else:
        window_list = []
        if output_format != "json":
            typer.echo(f"Screening {len(ticker_list)} tickers | {window} sessions...")

    workflow_uc = deps.build_accum_workflow_use_case()

    try:
        result = workflow_uc.execute(
            build_screen_accum_request(
                tickers=ticker_list,
                universe_label=universe_label,
                universe_name=universe,
                window=window,
                min_streak=min_streak,
                min_accum_score=min_accum_score,
                min_signal_score=min_signal_score,
                min_piotroski=min_piotroski,
                strategy_name=strategy,
                include_strategy_overlay=include_strategy_overlay,
                multi=multi,
                windows=window_list,
                top=top,
                save_name=save_name,
                save_enabled=save_enabled,
                vwap_only=vwap_only,
                squeeze_only=squeeze_only,
                sort_by=sort_by,
                as_of_date=as_of_date,
                deep_evidence=deep_flags,
            )
        )
    except ScreenAccumProjectionError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    for warning in result.warnings:
        typer.echo(f"⚠ {warning}", err=True)

    if multi:
        _render_multi(
            result=result,
            universe_label=universe_label,
            output_format=output_format,
            detail=detail,
            display_config=display_config,
        )
        return

    _render_single(
        result=result,
        universe_label=universe_label,
        show_top_broker=show_top_broker,
        output_format=output_format,
        detail=detail,
        strategy=strategy,
        display_config=display_config,
        deep_flags=deep_flags,
    )


def _render_multi(
    *,
    result,
    universe_label: str,
    output_format: str,
    detail: bool,
    display_config: AccumulationDisplayConfig,
) -> None:
    projection = result.multi_projection
    if projection is None:
        return

    if output_format == "json":
        echo_json(
            build_accum_multi_envelope(
                universe_label=universe_label,
                projection=projection,
                multi_results=result.multi_results,
                effective_session=result.effective_session,
                warnings=result.warnings,
            )
        )
        return

    sample_resp = next(iter(result.multi_results.values()), None)
    display_multi(
        rows=projection.rows,
        universe_label=universe_label,
        windows=projection.resolved_windows,
        screened_at=projection.screened_at,
        display_config=display_config,
        total_tickers_checked=sample_resp.total_tickers_checked if sample_resp else 0,
        provider=sample_resp.provider if sample_resp else "",
        include_detail=detail,
        canonical_window=projection.canonical_window,
        effective_session=result.effective_session,
    )


def _render_single(
    *,
    result,
    universe_label: str,
    show_top_broker: bool,
    output_format: str,
    detail: bool,
    strategy: str | None,
    display_config: AccumulationDisplayConfig,
    deep_flags: ScreenJudgmentDeepEvidenceRequest | None = None,
) -> None:
    response = result.response
    projection = result.single_projection
    if response is None or projection is None:
        return

    deep_by_ticker = getattr(result, "deep_evidence_by_ticker", {}) or {}

    if output_format == "json":
        echo_json(
            build_accum_single_envelope(
                universe_label=universe_label,
                response=response,
                projection=projection,
                effective_session=result.effective_session,
                warnings=result.warnings,
                strategy_name=strategy,
                strategy_signals=result.strategy_signals,
                save_result=result.save_result,
                deep_evidence_by_ticker=deep_by_ticker,
            )
        )
        return

    display_results(
        response=response,
        candidates=projection.candidates,
        universe_label=universe_label,
        show_top_broker=show_top_broker,
        display_config=display_config,
        include_detail=detail,
        strategy_signals=result.strategy_signals or None,
        strategy_name=strategy,
        effective_session=result.effective_session,
        market_context=getattr(result, "market_context", None),
        deep_evidence_by_ticker=deep_by_ticker,
        deep_flags=deep_flags,
    )

    if result.save_result:
        typer.echo(
            typer.style(
                f"\n  ✓ Saved {result.save_result.saved_count} tickers "
                f"to watchlist '{result.save_result.name}'",
                fg=typer.colors.GREEN,
            )
        )


def _refresh_explicit_tickers_for_screen(
    *,
    tickers: list[str],
    db_path: Path,
    force_refresh: bool,
    quiet: bool,
) -> None:
    """Refresh candles/broker for explicit tickers only (ADR-054 S1).

    Reuses the same application refresh path as plan swing so cache policy
    cannot diverge. Failures are warnings; screen continues on existing cache.
    """
    from src.adapters.cli.plan_swing_optional_fetchers import auto_refresh_swing_data
    from src.infrastructure.config.plan_swing_config import load_plan_swing_config

    plan_swing_config = load_plan_swing_config()
    for ticker in tickers:
        try:
            notes = auto_refresh_swing_data(
                ticker=ticker,
                db_path=db_path,
                force_refresh=force_refresh,
                plan_swing_config=plan_swing_config,
            )
            if not quiet:
                joined = ", ".join(notes) if notes else "ok"
                typer.echo(f"Refresh {ticker}: {joined}")
        except Exception as exc:
            typer.echo(f"⚠ Refresh {ticker} failed ({exc}); using cached data.", err=True)
