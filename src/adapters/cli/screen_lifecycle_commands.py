"""
Lifecycle-oriented candidate discovery commands.

Layer: Adapter
"""

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.screen_accum_commands import accumulation_run
from src.adapters.cli.screen_pre_open_commands import pre_open
from src.application.use_case.compare_screen_snapshots_use_case import (
    ScreenCompareResult,
)
from src.infrastructure.config.app_config import load_app_config

screen_app = typer.Typer(
    name="screen",
    help="Candidate discovery — pre-open movers and accumulation screens.",
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
) -> None:
    """
    List saved screener snapshots or show tickers in a named watchlist.

    Examples:
        saham screen watchlist               # list all saved watchlists
        saham screen watchlist morning-watch  # show tickers in 'morning-watch'
    """
    from src.infrastructure.persistence.sqlite_watchlist_repository import SQLiteWatchlistRepository

    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)
    repo = SQLiteWatchlistRepository(resolved_db)

    if name is None:
        summaries = repo.list_snapshots()
        if not summaries:
            typer.echo("No saved watchlists. Use 'saham screen accum --save NAME' to create one.")
            return
        typer.echo(f"\n  {'NAME':<24} {'TICKERS':>7}  {'WINDOW':>6}  SAVED AT")
        typer.echo(f"  {'─' * 24}  {'─' * 7}  {'─' * 6}  {'─' * 20}")
        for s in summaries:
            saved_str = s["latest_saved_at"][:16].replace("T", " ")
            typer.echo(
                f"  {s['name']:<24} {s['ticker_count']:>7}  {s['window_days']:>5}s  {saved_str}"
            )
        typer.echo("")
        return

    entries = repo.get_latest_snapshot(name)
    if not entries:
        typer.echo(
            typer.style(f"No watchlist named '{name}' found.", fg=typer.colors.YELLOW)
            + " Use 'saham screen accum --save NAME'."
        )
        raise typer.Exit(1)

    saved_str = entries[0].saved_at.strftime("%Y-%m-%d %H:%M")
    typer.echo(f"\n  Watchlist: {name}  |  {len(entries)} tickers  |  saved {saved_str}")
    typer.echo(f"  {'─' * 60}")
    typer.echo(
        f"  {'#':>3}  {'TICKER':<8}  {'CMP':>5}  {'SCORE':>6}  {'STREAK':>6}  {'NET BUY':>7}  BCI"
    )
    typer.echo(f"  {'─' * 3}  {'─' * 8}  {'─' * 5}  {'─' * 6}  {'─' * 6}  {'─' * 7}  {'─' * 10}")
    for e in entries:
        cmp_str = f"{e.composite_score:.0f}" if e.composite_score is not None else "  —"
        bci = e.bci_label or "—"
        typer.echo(
            f"  {e.rank:>3}  {e.ticker:<8}  {cmp_str:>5}  {e.flow_score:>6.1f}"
            f"  {e.consecutive_streak:>6}  {e.net_buy_ratio:>6.0%}  {bci}"
        )
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
) -> None:
    """
    Compare a saved watchlist against a fresh screener run.

    Shows: new entries, dropped tickers, and signal strength changes.

    Examples:
        saham screen compare morning-watch
        saham screen compare morning-watch --universe lq45 --top 30
    """
    from src.application.use_case.compare_screen_snapshots_use_case import compare_screen_snapshots
    from src.infrastructure.persistence.sqlite_watchlist_repository import SQLiteWatchlistRepository

    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)
    repo = SQLiteWatchlistRepository(resolved_db)
    snapshot = repo.get_latest_snapshot(name)

    if not snapshot:
        typer.echo(
            typer.style(f"No saved watchlist named '{name}'.", fg=typer.colors.YELLOW)
            + " Use 'saham screen accum --save NAME' first."
        )
        raise typer.Exit(1)

    saved_universe = snapshot[0].universe if snapshot else universe or "cached"
    run_universe = universe or saved_universe or "cached"
    saved_at_str = snapshot[0].saved_at.strftime("%Y-%m-%d %H:%M")

    typer.echo(
        f"\n  Comparing '{name}' (saved {saved_at_str}) against fresh screen on '{run_universe}'..."
    )

    # Run a fresh screen inline (reuse accumulation_run logic via use case)
    from src.adapters.cli.screen_accum_compare_factory import (
        run_fresh_accumulation_screen_for_compare,
    )
    from src.infrastructure.config.accumulation_screener_config import (
        load_accumulation_screener_config,
    )
    from src.infrastructure.config.swing_config import load_swing_config

    swing_config = load_swing_config()
    screener_config = load_accumulation_screener_config(
        Path(cfg.config_paths.accumulation_screener)
    )

    fresh_result = run_fresh_accumulation_screen_for_compare(
        universe=run_universe,
        window=window,
        top=top,
        db_path=resolved_db,
        screener_config=screener_config,
        swing_config=swing_config,
    )

    if not fresh_result.ok:
        typer.echo(typer.style(f"  {fresh_result.error}", fg=typer.colors.RED))
        raise typer.Exit(1)

    fresh_candidates = fresh_result.candidates
    fresh_tickers = [c.ticker for c in fresh_candidates]
    fresh_scores = {
        c.ticker: (
            c.foreign_flow_score,
            c.signal_assessment.assessment.score if c.signal_assessment else None,
        )
        for c in fresh_candidates
    }
    fresh_ranks = {c.ticker: i + 1 for i, c in enumerate(fresh_candidates)}

    result = compare_screen_snapshots(
        snapshot=snapshot,
        fresh_tickers=fresh_tickers,
        fresh_scores=fresh_scores,
        fresh_ranks=fresh_ranks,
        snapshot_name=name,
    )

    _display_compare_result(result)


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

    typer.echo("")
