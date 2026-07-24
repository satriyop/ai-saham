"""
Lifecycle-oriented candidate discovery commands.

Layer: Adapter
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.screen_accum_commands import accumulation_run
from src.adapters.cli.screen_contract_cli import (
    echo_json,
    exit_missing_screen_data,
    resolve_output_format,
)
from src.adapters.cli.screen_deps import build_screen_deps
from src.adapters.cli.screen_pre_open_commands import pre_open
from src.application.dto.screen_contract import (
    ScreenResultStatus,
    ScreenSubjectKind,
    build_screen_envelope,
    default_screen_fetch_hint,
)
from src.application.use_case.compare_screen_snapshots_use_case import (
    ScreenCompareResult,
)
from src.application.use_case.compare_screen_watchlist_use_case import (
    CompareScreenWatchlistRequest,
    WatchlistNotFoundError,
)
from src.application.use_case.list_screen_watchlists_use_case import (
    ListScreenWatchlistsRequest,
)
from src.application.use_case.run_accumulation_screen_workflow_use_case import (
    RunAccumulationScreenWorkflowRequest,
)
from src.application.services.universe_loader import resolve_tickers
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.universe_config_loader import YamlUniverseConfigLoader

screen_app = typer.Typer(
    name="screen",
    help=(
        "Candidate discovery — pre-open movers and accumulation screens.\n\n"
        "Discover: `pre-open`, `accum`.\n"
        "Lifecycle: `watchlist`, `compare`.\n"
        "Inspect a hit next: `saham view BBCA`."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

screen_app.command("pre-open")(pre_open)
screen_app.command("accum")(accumulation_run)


@screen_app.command("watchlist")
def screen_watchlist(
    name: Annotated[
        Optional[str],
        typer.Argument(help="Watchlist name to show (omit to list all saved watchlists)"),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
    fmt: Annotated[
        Optional[str],
        typer.Option("--format", help="Output format: table or json"),
    ] = None,
) -> None:
    """
    List saved screener snapshots or show tickers in a named watchlist.

    Examples:
        saham screen watchlist               # list all saved watchlists
        saham screen watchlist morning-watch  # show tickers in 'morning-watch'
        saham screen watchlist --format json
    """
    cfg = load_app_config()
    output_format = resolve_output_format(fmt or "table")
    deps = build_screen_deps(db_path or Path(cfg.storage.db_path))
    result = deps.list_watchlists.execute(ListScreenWatchlistsRequest(name=name))

    if name is None:
        if not result.summaries:
            if output_format == "json":
                echo_json(
                    build_screen_envelope(
                        verb="watchlist",
                        status=ScreenResultStatus.EMPTY,
                        subject_kind=ScreenSubjectKind.SCREEN,
                        subject_id="watchlist",
                        source="screen_snapshots",
                        fetch_hint="saham screen accum --universe lq45 --save NAME",
                        data={"summaries": []},
                    )
                )
                return
            typer.echo(
                "No saved watchlists. Use 'saham screen accum --save NAME' to create one."
            )
            return

        if output_format == "json":
            echo_json(
                build_screen_envelope(
                    verb="watchlist",
                    status=ScreenResultStatus.OK,
                    subject_kind=ScreenSubjectKind.SCREEN,
                    subject_id="watchlist",
                    source="screen_snapshots",
                    data={
                        "summaries": [
                            {
                                "name": s.name,
                                "latest_saved_at": s.latest_saved_at.isoformat(),
                                "universe": s.universe,
                                "window_days": s.window_days,
                                "ticker_count": s.ticker_count,
                            }
                            for s in result.summaries
                        ]
                    },
                )
            )
            return

        typer.echo(f"\n  {'NAME':<24} {'TICKERS':>7}  {'WINDOW':>6}  SAVED AT")
        typer.echo(f"  {'─' * 24}  {'─' * 7}  {'─' * 6}  {'─' * 20}")
        for s in result.summaries:
            saved_str = s.latest_saved_at.isoformat()[:16].replace("T", " ")
            typer.echo(
                f"  {s.name:<24} {s.ticker_count:>7}  {s.window_days:>5}s  {saved_str}"
            )
        typer.echo("")
        return

    if not result.selected_entries:
        exit_missing_screen_data(
            what="watchlist",
            name=name,
            source="screen_snapshots",
            fetch_hint="saham screen accum --save NAME",
        )

    entries = result.selected_entries
    if output_format == "json":
        echo_json(
            build_screen_envelope(
                verb="watchlist",
                status=ScreenResultStatus.OK,
                subject_kind=ScreenSubjectKind.WATCHLIST,
                subject_id=name,
                as_of=entries[0].saved_at,
                source="screen_snapshots",
                window_days=entries[0].window_days,
                data={
                    "name": name,
                    "saved_at": entries[0].saved_at.isoformat(),
                    "universe": entries[0].universe,
                    "window_days": entries[0].window_days,
                    "entries": [
                        {
                            "rank": e.rank,
                            "ticker": e.ticker,
                            "signal_score": e.signal_score,
                            "accum_score": e.accum_score,
                            "consecutive_streak": e.consecutive_streak,
                            "net_buy_ratio": e.net_buy_ratio,
                            "bci_label": e.bci_label,
                        }
                        for e in entries
                    ],
                },
            )
        )
        return

    saved_str = entries[0].saved_at.strftime("%Y-%m-%d %H:%M")
    typer.echo(f"\n  Watchlist: {name}  |  {len(entries)} tickers  |  saved {saved_str}")
    typer.echo(f"  {'─' * 60}")
    typer.echo(
        f"  {'#':>3}  {'TICKER':<8}  {'SIGNAL':>6}  {'ACCUM':>6}  {'STREAK':>6}  {'NET BUY':>7}  BCI"
    )
    typer.echo(f"  {'─' * 3}  {'─' * 8}  {'─' * 6}  {'─' * 6}  {'─' * 6}  {'─' * 7}  {'─' * 10}")
    for e in entries:
        signal_str = f"{e.signal_score:.0f}" if e.signal_score is not None else "  —"
        bci = e.bci_label or "—"
        typer.echo(
            f"  {e.rank:>3}  {e.ticker:<8}  {signal_str:>6}  {e.accum_score:>6.1f}"
            f"  {e.consecutive_streak:>6}  {e.net_buy_ratio:>6.0%}  {bci}"
        )
    typer.echo("")
    typer.echo("  Next: saham view <TICKER>  ·  saham screen compare " + name)
    typer.echo("")


@screen_app.command("compare")
def screen_compare(
    name: Annotated[
        str,
        typer.Argument(help="Saved watchlist name to compare against"),
    ],
    universe: Annotated[
        Optional[str],
        typer.Option("--universe", "-u", help="Universe to screen now (default: same as saved)"),
    ] = None,
    window: Annotated[
        int,
        typer.Option("--window", "-w", help="Broker-session window", min=1),
    ] = 7,
    top: Annotated[
        int,
        typer.Option("--top", help="Top N results to compare", min=1),
    ] = 20,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
    fmt: Annotated[
        Optional[str],
        typer.Option("--format", help="Output format: table or json"),
    ] = None,
) -> None:
    """
    Compare a saved watchlist against a fresh screener run.

    Shows: new entries, dropped tickers, and signal strength changes.

    Examples:
        saham screen compare morning-watch
        saham screen compare morning-watch --universe lq45 --top 30
        saham screen compare morning-watch --format json
    """
    cfg = load_app_config()
    output_format = resolve_output_format(fmt or "table")
    deps = build_screen_deps(db_path or Path(cfg.storage.db_path))

    # Peek snapshot for universe default before full compare workflow.
    peek = deps.list_watchlists.execute(ListScreenWatchlistsRequest(name=name))
    if not peek.selected_entries:
        exit_missing_screen_data(
            what="watchlist",
            name=name,
            source="screen_snapshots",
            fetch_hint="saham screen accum --save NAME",
        )

    saved_universe = peek.selected_entries[0].universe
    run_universe = universe or saved_universe or "cached"
    saved_at_str = peek.selected_entries[0].saved_at.strftime("%Y-%m-%d %H:%M")

    if output_format != "json":
        typer.echo(
            f"\n  Comparing '{name}' (saved {saved_at_str}) against fresh screen on '{run_universe}'..."
        )

    try:
        ticker_list = resolve_tickers(
            universe=run_universe,
            explicit=[],
            db_path=deps.db_path,
            loader=YamlUniverseConfigLoader(),
            repository=deps.broker_repository,
        )
    except Exception as exc:
        typer.echo(typer.style(f"  {exc}", fg=typer.colors.RED), err=True)
        raise typer.Exit(1) from exc

    if not ticker_list:
        typer.echo(
            typer.style(
                f"  No tickers resolved for universe '{run_universe}'.",
                fg=typer.colors.RED,
            ),
            err=True,
        )
        raise typer.Exit(1)

    screen_request = RunAccumulationScreenWorkflowRequest(
        tickers=list(ticker_list),
        universe_label=run_universe,
        universe_name=run_universe,
        window=window,
        min_streak=0,
        min_accum_score=None,
        min_signal_score=None,
        min_piotroski=0,
        strategy_name=None,
        include_strategy_overlay=False,
        multi=False,
        windows=[],
        top=top,
        save_name=None,
        save_enabled=False,
        vwap_only=False,
        squeeze_only=False,
        sort_by="score",
        as_of_date=None,
    )

    try:
        compare_result = deps.build_compare_watchlist_use_case().execute(
            CompareScreenWatchlistRequest(name=name, screen_request=screen_request)
        )
    except WatchlistNotFoundError:
        exit_missing_screen_data(
            what="watchlist",
            name=name,
            source="screen_snapshots",
            fetch_hint="saham screen accum --save NAME",
        )
    except Exception as exc:
        typer.echo(
            typer.style(
                f"  Fresh accumulation screen failed: {type(exc).__name__}: {exc}",
                fg=typer.colors.RED,
            ),
            err=True,
        )
        raise typer.Exit(1) from exc

    if output_format == "json":
        comparison = compare_result.comparison
        echo_json(
            build_screen_envelope(
                verb="compare",
                status=ScreenResultStatus.OK,
                subject_kind=ScreenSubjectKind.WATCHLIST,
                subject_id=name,
                as_of=compare_result.saved_summary.latest_saved_at,
                source="screen_snapshots+accumulation_screen",
                scope=run_universe,
                window_days=window,
                fetch_hint=default_screen_fetch_hint(universe=run_universe),
                data={
                    "snapshot_name": comparison.snapshot_name,
                    "snapshot_count": comparison.snapshot_count,
                    "fresh_count": comparison.fresh_count,
                    "new_tickers": list(comparison.new_tickers),
                    "dropped_tickers": list(comparison.dropped_tickers),
                    "warnings": list(comparison.warnings),
                    "strengthening": [
                        {
                            "ticker": c.ticker,
                            "old_rank": c.old_rank,
                            "new_rank": c.new_rank,
                            "flow_delta": c.flow_delta,
                            "composite_delta": c.composite_delta,
                        }
                        for c in comparison.strengthening
                    ],
                    "weakening": [
                        {
                            "ticker": c.ticker,
                            "old_rank": c.old_rank,
                            "new_rank": c.new_rank,
                            "flow_delta": c.flow_delta,
                            "composite_delta": c.composite_delta,
                        }
                        for c in comparison.weakening
                    ],
                    "unchanged": [
                        {
                            "ticker": c.ticker,
                            "old_rank": c.old_rank,
                            "new_rank": c.new_rank,
                        }
                        for c in comparison.unchanged
                    ],
                },
            )
        )
        return

    _display_compare_result(compare_result.comparison)


def _signal_change_row(c) -> str:
    delta = c.composite_delta
    signal_str = f"signal {delta:+.1f}" if delta is not None else "signal N/A"
    return (
        f"    {c.ticker:<8} rank #{c.old_rank}→#{c.new_rank}"
        f"  flow {c.flow_delta:+.1f}  {signal_str}"
    )


def _display_compare_result(result: ScreenCompareResult) -> None:
    typer.echo(
        f"\n  Snapshot: {result.snapshot_name} ({result.snapshot_count} tickers)  →  "
        f"Fresh: {result.fresh_count} tickers"
    )

    for warning in result.warnings:
        typer.echo(typer.style(f"\n  ⚠ {warning}", fg=typer.colors.YELLOW))

    if result.new_tickers:
        typer.echo(
            typer.style(f"\n  ✦ NEW  ({len(result.new_tickers)} entries)", fg=typer.colors.GREEN)
        )
        for t in result.new_tickers:
            typer.echo(f"    + {t}")

    if result.dropped_tickers:
        typer.echo(
            typer.style(
                f"\n  ✗ DROPPED  ({len(result.dropped_tickers)} entries)", fg=typer.colors.RED
            )
        )
        for t in result.dropped_tickers:
            typer.echo(f"    - {t}")

    strengthening = result.strengthening
    if strengthening:
        typer.echo(
            typer.style(
                f"\n  ↑ STRENGTHENING  ({len(strengthening)} signals)", fg=typer.colors.CYAN
            )
        )
        for c in sorted(strengthening, key=lambda x: x.rank_delta, reverse=True)[:10]:
            typer.echo(_signal_change_row(c))

    weakening = result.weakening
    if weakening:
        typer.echo(
            typer.style(
                f"\n  ↓ WEAKENING  ({len(weakening)} signals)", fg=typer.colors.MAGENTA
            )
        )
        for c in sorted(weakening, key=lambda x: x.rank_delta)[:10]:
            typer.echo(_signal_change_row(c))

    unchanged = result.unchanged
    if unchanged:
        typer.echo(
            typer.style(
                f"\n  · UNCHANGED  ({len(unchanged)} signals)", fg=typer.colors.BRIGHT_BLACK
            )
        )
        for c in unchanged[:10]:
            typer.echo(_signal_change_row(c))

    if not result.new_tickers and not result.dropped_tickers and not result.changed:
        typer.echo(
            typer.style(
                "\n  ≈ No significant changes since last save.", fg=typer.colors.BRIGHT_BLACK
            )
        )

    typer.echo("\n  Next: saham view <TICKER>  ·  saham analyze swing <TICKER>")
    typer.echo("")
