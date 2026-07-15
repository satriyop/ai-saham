"""
CLI implementation for saham screen accum command.

Public command registration lives in lifecycle routers:
  saham screen accum

Layer: Adapter
"""

import json
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.screen_accum_display import (
    display_multi,
    display_results,
    print_column_guide,
)
from src.adapters.cli.screen_accum_formatters import (
    AccumulationDisplayConfig,
    accumulation_display_config_from_screener,
)
from src.adapters.cli.screen_accum_workflow_factory import (
    create_run_accumulation_screen_workflow_use_case,
)
from src.application.services.screen_accum_result_projector import (
    ScreenAccumProjectionError,
)
from src.application.services.universe_loader import (
    UniverseNotFoundError,
    resolve_tickers,
)
from src.application.use_case.run_accumulation_screen_workflow_use_case import (
    RunAccumulationScreenWorkflowRequest,
)
from src.infrastructure.config.accumulation_screener_config import (
    load_accumulation_screener_config as _load_accumulation_screener_config,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.swing_config import load_swing_config as _load_swing_config
from src.infrastructure.config.universe_config_loader import YamlUniverseConfigLoader
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository

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
            help="Analysis window in broker sessions (7, 30, or 90)",
            min=3,
        ),
    ] = 7,
    min_streak: Annotated[
        int,
        typer.Option("--min-streak", help="Minimum consecutive buy days required", min=0),
    ] = 0,
    min_foreign_flow_score: Annotated[
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
                "In --multi mode, sort by: avg|max|7s|30s|90s "
                "(legacy 7d/30d/90d also accepted; default: avg)"
            ),
        ),
    ] = "avg",
    output_format: Annotated[
        Optional[str],
        typer.Option("--format", help="Output format: table or json"),
    ] = None,
    guide: Annotated[
        bool,
        typer.Option("--guide", help="Print column reference guide and exit (no screen needed)"),
    ] = False,
    explain: Annotated[
        bool,
        typer.Option("--explain", help="Append run context and scoring definitions after results"),
    ] = False,
    strategy: Annotated[
        Optional[str],
        typer.Option(
            "--strategy",
            "-S",
            help=(
                "Show strategy signal column alongside foreign-flow score "
                "(e.g. williams-r-bounce)"
            ),
        ),
    ] = None,
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
) -> None:
    """
    Screen stocks for foreign accumulation patterns.

    Computes composite foreign-flow score 0-100 based on: consistency of daily foreign buying,
    consecutive buy streak, whether foreigners are underwater (VWAP vs price),
    RSI headroom, and foreign flow as % of total turnover. BB Width is shown as a
    setup/phase diagnostic and does not contribute to the score by default.

    Run `saham fetch market --universe lq45` first to ensure fresh data.

    Examples:
        saham screen accum --universe lq45
        saham screen accum --universe lq45 --window 30
        saham screen accum --universe lq45 --multi
        saham screen accum --universe lq45 --multi --sort-by 30s
        saham screen accum --universe lq45 --min-foreign-flow-score 50 --top 10
        saham screen accum --universe lq45 --min-signal-score 55 --top 10
        saham screen accum BBCA BBRI BMRI --window 7
        saham screen accum --universe lq45 --vwap-only
        saham screen accum --universe lq45 --squeeze-only
        saham screen accum --universe lq45 --top-broker
        saham screen accum --universe lq45 --explain
        saham screen accum --guide
        saham screen accum --universe lq45 --format json
    """
    if guide:
        print_column_guide()
        return

    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)
    output_format = output_format or cfg.analysis.format

    swing_config = _load_swing_config()
    accumulation_config = _load_accumulation_screener_config(
        Path(cfg.config_paths.accumulation_screener)
    )
    display_config = accumulation_display_config_from_screener(accumulation_config)

    try:
        ticker_list = resolve_tickers(
            universe=universe,
            explicit=list(tickers) if tickers else [],
            db_path=resolved_db,
            loader=YamlUniverseConfigLoader(),
            repository=SQLiteBrokerRepository(resolved_db),
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

    if strategy and multi:
        typer.echo("Error: --strategy is not supported with --multi.", err=True)
        raise typer.Exit(1)
    if strategy and output_format == "json":
        typer.echo("Error: --strategy is not supported with --format json.", err=True)
        raise typer.Exit(1)

    include_strategy_overlay = bool(strategy)

    if save_name and output_format == "json":
        typer.echo("Error: --save is not supported with --format json.", err=True)
        raise typer.Exit(1)
    if save_name and multi:
        typer.echo("Error: --save is not supported with --multi.", err=True)
        raise typer.Exit(1)
    save_enabled = bool(save_name)

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

    workflow_uc = create_run_accumulation_screen_workflow_use_case(
        db_path=resolved_db,
        screener_config=accumulation_config,
        swing_config=swing_config,
    )

    try:
        result = workflow_uc.execute(
            RunAccumulationScreenWorkflowRequest(
                tickers=ticker_list,
                universe_label=universe_label,
                universe_name=universe,
                window=window,
                min_streak=min_streak,
                min_foreign_flow_score=min_foreign_flow_score,
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
            explain=explain,
            display_config=display_config,
        )
        return

    _render_single(
        result=result,
        universe_label=universe_label,
        show_top_broker=show_top_broker,
        output_format=output_format,
        explain=explain,
        strategy=strategy,
        display_config=display_config,
    )


def _render_multi(
    *,
    result,
    universe_label: str,
    output_format: str,
    explain: bool,
    display_config: AccumulationDisplayConfig,
) -> None:
    projection = result.multi_projection
    if projection is None:
        return

    if output_format == "json":
        tickers_payload: dict = {}
        for row in projection.rows:
            entry = {
                f"{w}_sessions": (c.to_dict() if c is not None else None)
                for w, c in row.candidates_by_window.items()
            }
            entry["pattern"] = row.pattern
            entry["trend"] = row.trend
            entry["broker_quality"] = (
                row.broker_quality.to_dict() if row.broker_quality else None
            )
            tickers_payload[row.ticker] = entry
        partial_result = any(
            resp.tickers_skipped > 0 for resp in result.multi_results.values()
        )
        typer.echo(
            json.dumps(
                {
                    "schema_version": 1,
                    "artifact_type": "accumulation_screen_multi",
                    "mode": "multi",
                    "universe": universe_label,
                    "windows": [f"{w}_sessions" for w in projection.resolved_windows],
                    "screened_at": str(projection.screened_at),
                    "tickers": tickers_payload,
                    "warnings": list(result.warnings),
                    "partial_result": partial_result,
                    **projection.to_dict(),
                },
                indent=2,
                default=str,
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
        include_explanation=explain,
    )


def _render_single(
    *,
    result,
    universe_label: str,
    show_top_broker: bool,
    output_format: str,
    explain: bool,
    strategy: str | None,
    display_config: AccumulationDisplayConfig,
) -> None:
    response = result.response
    projection = result.single_projection
    if response is None or projection is None:
        return

    if output_format == "json":
        data = {
            "schema_version": 1,
            "artifact_type": "accumulation_screen",
            "universe": universe_label,
            "screened_at": str(response.screened_at),
            "window_days": response.window_days,
            "total_checked": response.total_tickers_checked,
            "skipped": response.tickers_skipped,
            "provider": response.provider,
            "candidates": [c.to_dict() for c in projection.candidates],
            "warnings": list(result.warnings),
            "partial_result": response.tickers_skipped > 0,
            **projection.to_dict(),
        }
        typer.echo(json.dumps(data, indent=2, default=str))
        return

    display_results(
        response=response,
        candidates=projection.candidates,
        universe_label=universe_label,
        show_top_broker=show_top_broker,
        display_config=display_config,
        include_explanation=explain,
        strategy_signals=result.strategy_signals or None,
        strategy_name=strategy,
    )

    if result.save_result:
        typer.echo(
            typer.style(
                f"\n  ✓ Saved {result.save_result.saved_count} tickers "
                f"to watchlist '{result.save_result.name}'",
                fg=typer.colors.GREEN,
            )
        )
