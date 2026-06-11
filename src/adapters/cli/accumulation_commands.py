"""
CLI commands for foreign accumulation screening and universe management.

Commands:
  saham screen accumulation — scan stocks for foreign accumulation patterns
  saham universe list       — show configured ticker universes
  saham universe update     — refresh universe lists from IDX (future)

Layer: Adapter
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.services.universe_loader import (
    UniverseNotFoundError,
    load_universe_meta,
    resolve_tickers,
)
from src.application.use_case.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenRequest,
    AccumulationScreenResponse,
    AccumulationScreenUseCase,
)
from src.infrastructure.persistence.sqlite_broker_repository import (
    SQLiteBrokerRepository,
)
from src.infrastructure.persistence.sqlite_market_repository import (
    SQLiteMarketRepository,
)

accumulation_app = typer.Typer(
    name="accumulation",
    help="Foreign accumulation screener",
    no_args_is_help=True,
)

universe_app = typer.Typer(
    name="universe",
    help="Manage stock universe lists (LQ45, IDX80, IDXComp100)",
    no_args_is_help=True,
)

DEFAULT_DB_PATH = Path("data.db")


def _format_value(value: Decimal) -> str:
    """Format large IDR values with T/B/M suffix."""
    abs_v = abs(value)
    sign = "+" if value >= 0 else "-"
    if abs_v >= 1_000_000_000_000:
        return f"{sign}{abs_v / 1_000_000_000_000:.1f}T"
    if abs_v >= 1_000_000_000:
        return f"{sign}{abs_v / 1_000_000_000:.1f}B"
    if abs_v >= 1_000_000:
        return f"{sign}{abs_v / 1_000_000:.0f}M"
    return f"{sign}{abs_v:.0f}"


def _display_results(
    response: AccumulationScreenResponse,
    universe_label: str,
    top_n: int,
    granular: bool,
    vwap_only: bool,
) -> None:
    """Render accumulation screener results as terminal table."""
    candidates = response.candidates
    if vwap_only:
        candidates = [c for c in candidates if c.vwap_discount_pct and c.vwap_discount_pct > 0]

    candidates = candidates[:top_n]

    typer.echo("")
    typer.echo("=" * 75)
    typer.echo(
        f"FOREIGN ACCUMULATION — {universe_label.upper()} "
        f"| {response.window_days}d window | {response.screened_at}"
    )
    typer.echo("=" * 75)

    if not candidates:
        typer.echo("No candidates found matching the criteria.")
        typer.echo(
            f"Checked {response.total_tickers_checked} tickers, "
            f"skipped {response.tickers_skipped} (insufficient data)."
        )
        typer.echo("=" * 75)
        return

    header = f"{'#':>3} {'TICKER':<7} {'SCORE':>6} {'STREAK':>7} {'NET_DAYS':>9} {'NET_VALUE':>12} {'VWAP_DISC':>10} {'RSI':>6} {'TREND':>5}"
    typer.echo(header)
    typer.echo("-" * 75)

    for i, c in enumerate(candidates, 1):
        net_days_str = f"{c.net_buy_days}/{c.total_days}"
        vwap_str = f"{c.vwap_discount_pct:+.1f}%" if c.vwap_discount_pct is not None else "  —  "
        rsi_str = f"{c.rsi:.1f}" if c.rsi is not None else "  —"
        streak_str = f"{c.consecutive_streak}d"

        # Color score
        if c.score >= 70:
            score_color = typer.colors.GREEN
        elif c.score >= 40:
            score_color = typer.colors.YELLOW
        else:
            score_color = typer.colors.WHITE

        line = (
            f"{i:>3} {c.ticker:<7} "
            + typer.style(f"{c.score:>6.1f}", fg=score_color)
            + f" {streak_str:>7} {net_days_str:>9} {_format_value(c.total_net_value):>12}"
            + f" {vwap_str:>10} {rsi_str:>6} {c.trend:>5}"
        )
        typer.echo(line)

        if granular and c.top_brokers:
            broker_line = "    " + "  ".join(c.top_brokers[:5])
            if c.institutional_flag:
                broker_line += "  " + typer.style("[★ INSTITUTIONAL]", fg=typer.colors.CYAN)
            typer.echo(broker_line)

    typer.echo("-" * 75)
    typer.echo(
        f"Checked: {response.total_tickers_checked} | "
        f"Shown: {len(candidates)} | "
        f"Skipped (no data): {response.tickers_skipped}"
    )
    typer.echo(f"Provider: {response.provider} (aggregate foreign flow)")
    if response.provider == "idx":
        typer.echo(
            "  For per-broker detail: set Stockbit token via `saham broker auth <token>`"
        )
    typer.echo("")
    typer.echo("VWAP_DISC: positive = price < foreign avg buy (foreigners underwater)")
    typer.echo("Score: 0–100 | streak 30pts | consistency 40pts | VWAP 20pts | RSI 10pts")
    typer.echo("")
    typer.echo("Swing trade watchlist — cross-check with `saham screen pre-open` for intraday entry timing.")
    typer.echo("DISCLAIMER: Analysis only, not trading advice.")
    typer.echo("=" * 75)


@accumulation_app.command("run")
def accumulation_run(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option(
            "--universe", "-u",
            help="Universe: lq45, idx80, idxcomp100, cached",
        ),
    ] = None,
    window: Annotated[
        int,
        typer.Option(
            "--window", "-w",
            help="Analysis window in days (7, 30, or 90)",
            min=3,
        ),
    ] = 7,
    min_streak: Annotated[
        int,
        typer.Option("--min-streak", help="Minimum consecutive buy days required", min=0),
    ] = 0,
    min_score: Annotated[
        float,
        typer.Option("--min-score", help="Minimum composite score (0–100)", min=0),
    ] = 0.0,
    vwap_only: Annotated[
        bool,
        typer.Option("--vwap-only", help="Only show stocks where foreigners are underwater"),
    ] = False,
    top: Annotated[
        int,
        typer.Option("--top", help="Show top N results", min=1),
    ] = 20,
    granular: Annotated[
        bool,
        typer.Option("--granular", help="Show per-broker detail (Stockbit data required)"),
    ] = False,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Screen stocks for foreign accumulation patterns.

    Scores each ticker 0–100 based on: consistency of daily foreign buying,
    consecutive buy streak, whether foreigners are underwater (VWAP vs price),
    and RSI headroom.

    Run `saham update --universe lq45` first to ensure fresh data.

    Examples:
        saham screen accumulation --universe lq45
        saham screen accumulation --universe lq45 --window 30
        saham screen accumulation --universe lq45 --min-score 50 --top 10
        saham screen accumulation BBCA BBRI BMRI --window 7
        saham screen accumulation --universe lq45 --vwap-only
        saham screen accumulation --universe lq45 --granular
        saham screen accumulation --universe lq45 --format json
    """
    resolved_db = db_path or DEFAULT_DB_PATH

    # Resolve tickers
    try:
        ticker_list = resolve_tickers(
            universe=universe,
            explicit=list(tickers) if tickers else [],
            db_path=resolved_db,
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
    typer.echo(
        f"Screening {len(ticker_list)} tickers | {window}d window..."
    )

    broker_repo = SQLiteBrokerRepository(resolved_db)
    market_repo = SQLiteMarketRepository(db_path=resolved_db)
    use_case = AccumulationScreenUseCase(
        broker_repository=broker_repo,
        market_repository=market_repo,
    )

    request = AccumulationScreenRequest(
        tickers=ticker_list,
        window_days=window,
        min_net_buy_days=max(1, min_streak),
        min_score=min_score,
    )

    response = use_case.execute(request)

    # Apply streak filter post-scoring
    if min_streak > 0:
        response.candidates = [
            c for c in response.candidates if c.consecutive_streak >= min_streak
        ]

    if output_format == "json":
        data = {
            "screened_at": str(response.screened_at),
            "window_days": response.window_days,
            "total_checked": response.total_tickers_checked,
            "skipped": response.tickers_skipped,
            "provider": response.provider,
            "candidates": [c.to_dict() for c in response.candidates[:top]],
        }
        typer.echo(json.dumps(data, indent=2, default=str))
        return

    _display_results(
        response=response,
        universe_label=universe_label,
        top_n=top,
        granular=granular,
        vwap_only=vwap_only,
    )


# ---------------------------------------------------------------------------
# Universe management commands
# ---------------------------------------------------------------------------

@universe_app.command("list")
def universe_list(
    config_path: Annotated[
        Optional[Path],
        typer.Option("--config", help="Path to universes.yaml"),
    ] = None,
) -> None:
    """
    List configured ticker universes with last-updated date and ticker count.

    Example:
        saham universe list
    """
    from src.application.services.universe_loader import UNIVERSE_CONFIG_PATH

    resolved_config = config_path or UNIVERSE_CONFIG_PATH
    meta = load_universe_meta(resolved_config)

    if not meta:
        typer.echo(f"No universe config found at '{resolved_config}'.")
        typer.echo("Expected: config/universes.yaml")
        raise typer.Exit(1)

    typer.echo("")
    typer.echo("Configured universes:")
    typer.echo(f"  {'NAME':<14} {'TICKERS':>8}  {'LAST UPDATED'}")
    typer.echo("  " + "-" * 40)
    for name, info in meta.items():
        typer.echo(f"  {name:<14} {info['count']:>8}  {info['updated']}")
    typer.echo("")
    typer.echo(f"Config file: {resolved_config}")
    typer.echo("")
    typer.echo("Usage: saham update --universe <name>")
    typer.echo("       saham screen accumulation --universe <name>")


@universe_app.command("update")
def universe_update(
    universe_name: Annotated[
        Optional[str],
        typer.Option("--universe", "-u", help="Universe to update (lq45, idx80, idxcomp100)"),
    ] = None,
) -> None:
    """
    Refresh universe ticker lists from IDX website.

    Currently prints instructions — automatic scraping from IDX
    will be implemented in a future release.

    Example:
        saham universe update --universe lq45
    """
    typer.echo("")
    typer.echo("Universe auto-update from IDX website is not yet implemented.")
    typer.echo("")
    typer.echo("To update manually:")
    typer.echo("  1. Visit https://www.idx.co.id/en/market-data/indexes/")
    typer.echo("  2. Download the latest LQ45 / IDX80 constituent list")
    typer.echo("  3. Edit config/universes.yaml with the new tickers")
    typer.echo("  4. Update the 'updated' date field")
    typer.echo("")
    typer.echo("IDX rebalances indices every February and August.")
