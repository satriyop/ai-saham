"""
CLI commands for viewing broker data.

Provides commands to view broker summary, configuration, and flow statistics.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.view_broker_display import (
    display_broker_flow,
    display_broker_history,
    display_broker_top,
    display_broker_top_foreign_snapshots,
)
from src.application.use_case.fetch_broker_data_use_case import (
    GetBrokerDataUseCase,
)
from src.domain.ports.broker_data_provider import (
    BrokerDataProvider,
)
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.csv import MappingLoader
from src.infrastructure.persistence.sqlite_broker_repository import (
    SQLiteBrokerRepository,
)

DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)
_DEFAULT_PROFILE_DIR = Path(APP_CFG.storage.stockbit_profile_dir)
DEFAULT_PROVIDER = APP_CFG.broker.provider
PROVIDERS = ("idx", "stockbit")


def _create_provider(provider_name: str) -> BrokerDataProvider:
    """Stub provider factory for test monkeypatch compatibility."""
    raise NotImplementedError("Network providers are not supported in view-only commands.")


def broker_status() -> None:
    """
    Check broker data provider status.

    Shows status of all available providers.
    """
    # IDX provider (always available)
    typer.echo("IDX provider: " + typer.style("Available", fg=typer.colors.GREEN)
               + " (public API, no auth required)")

    # Stockbit Playwright session provider
    try:
        from src.infrastructure.browser.stockbit_api_client import create_stockbit_api_client
        from src.infrastructure.browser.playwright_stockbit_provider import StockbitBrokerProvider
        session_provider = StockbitBrokerProvider(create_stockbit_api_client())
        if session_provider.is_authenticated():
            marker = _DEFAULT_PROFILE_DIR / ".logged_in_at"
            age_h: float | None = None
            if marker.exists():
                import time as _time
                try:
                    age_h = round((_time.time() - float(marker.read_text())) / 3600, 1)
                except Exception:
                    pass
            age_str = f" ({age_h}h old)" if age_h is not None else ""
            typer.echo(
                "Stockbit-Session provider: "
                + typer.style(f"Active{age_str}", fg=typer.colors.GREEN)
                + " — use --provider stockbit"
            )
        else:
            typer.echo(
                "Stockbit-Session provider: "
                + typer.style("No session", fg=typer.colors.YELLOW)
                + " (run 'saham fetch stockbit login' to set up)"
            )
    except ImportError:
        typer.echo(
            "Stockbit-Session provider: "
            + typer.style("playwright not installed", fg=typer.colors.YELLOW)
        )

    typer.echo(f"\nDefault provider: {DEFAULT_PROVIDER}")


def broker_flow(
    ticker: Annotated[
        str,
        typer.Argument(help="Stock ticker symbol (e.g., BBCA)"),
    ],
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days to show"),
    ] = 10,
    db_path: Annotated[
        Path,
        typer.Option("--db", help="Database path"),
    ] = DEFAULT_DB_PATH,
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = APP_CFG.analysis.format,
) -> None:
    """
    Show foreign flow summary for a stock.

    Displays cached broker data. Use 'saham fetch broker' first to load data.

    Example:
        saham view broker flow BBCA --days 20
        saham view broker flow BBCA --format json
    """
    repository = SQLiteBrokerRepository(db_path)
    use_case = GetBrokerDataUseCase(repository)

    end_date = date.today()
    start_date = end_date - timedelta(days=days + 10)  # Extra buffer for weekends

    summaries = use_case.execute(ticker, start_date, end_date)

    if not summaries:
        typer.echo(
            typer.style("No data found. ", fg=typer.colors.YELLOW)
            + f"Run 'saham fetch broker {ticker}' first."
        )
        raise typer.Exit(1)

    # Take last N days
    summaries = summaries[-days:]

    if fmt == "json":
        import json as _json
        typer.echo(_json.dumps([s.to_dict() for s in summaries], indent=2, default=str))
        return

    display_broker_flow(ticker, summaries)


def broker_top(
    ticker: Annotated[
        str,
        typer.Argument(help="Stock ticker symbol (e.g., BBCA)"),
    ],
    target_date: Annotated[
        Optional[str],
        typer.Option("--date", "-d", help="Date (YYYY-MM-DD), default: latest"),
    ] = None,
    db_path: Annotated[
        Path,
        typer.Option("--db", help="Database path"),
    ] = DEFAULT_DB_PATH,
) -> None:
    """
    Show top brokers for a stock on a specific date.

    Example:
        saham view broker top BBCA
        saham view broker top BBCA --date 2024-01-15
    """
    repository = SQLiteBrokerRepository(db_path)

    if target_date:
        query_date = date.fromisoformat(target_date)
        summary = repository.get_broker_summary(ticker, query_date)
    else:
        # Get latest
        summaries = repository.get_broker_summaries(ticker)
        if not summaries:
            typer.echo(
                typer.style("No data found. ", fg=typer.colors.YELLOW)
                + f"Run 'saham fetch broker {ticker}' first."
            )
            raise typer.Exit(1)
        summary = summaries[-1]

    if not summary:
        typer.echo(typer.style("No data for that date.", fg=typer.colors.YELLOW))
        raise typer.Exit(1)

    display_broker_top(ticker, summary)


def broker_history_view(
    ticker: Annotated[str, typer.Argument(help="Stock ticker (e.g. BBCA)")],
    days: Annotated[
        int,
        typer.Option("--days", help="How many recent trading days to show", min=1, max=365),
    ] = 30,
    source: Annotated[
        str,
        typer.Option("--source", help="Cached source to read: stockbit, idx, or auto"),
    ] = "auto",
    db_path: Annotated[
        Path,
        typer.Option("--db", help="SQLite database path"),
    ] = DEFAULT_DB_PATH,
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = APP_CFG.analysis.format,
) -> None:
    """
    Show cached daily foreign broker flow history for a stock.

    This is a read-only view of data already stored by 'saham fetch broker-history'
    or market refresh commands. It never calls remote providers.

    Examples:
        saham view broker history BBCA --days 30
        saham view broker history BBCA --source stockbit --format json
    """
    selected_source = None if source == "auto" else source
    if source not in {"auto", "stockbit", "idx"}:
        typer.echo(typer.style("Unknown source. Use: auto, stockbit, or idx", fg=typer.colors.RED))
        raise typer.Exit(1)

    repo = SQLiteBrokerRepository(db_path)
    points = repo.get_foreign_flow_points(ticker, source=selected_source)
    if not points:
        typer.echo(
            typer.style("No cached history found. ", fg=typer.colors.YELLOW)
            + f"Run 'saham fetch broker-history {ticker.upper()}' first."
        )
        raise typer.Exit(1)

    points = points[-days:]
    if fmt == "json":
        import json as _json
        payload = [
            {
                "ticker": p.ticker,
                "date": p.date.isoformat(),
                "source": p.source,
                "net_val": str(p.net_val),
                "net_lot": p.net_lot,
                "avg_price": str(p.avg_price),
            }
            for p in points
        ]
        typer.echo(_json.dumps(payload, indent=2))
        return
    if fmt != "table":
        typer.echo(typer.style("Unknown format. Use: table or json", fg=typer.colors.RED))
        raise typer.Exit(1)

    display_broker_history(ticker, points)


def broker_top_foreign_view(
    snapshot_date: Annotated[
        Optional[str],
        typer.Option("--date", "-d", help="Snapshot date (YYYY-MM-DD), default: today"),
    ] = None,
    days: Annotated[
        int,
        typer.Option("--days", help="Cached look-back window used by fetch", min=1, max=365),
    ] = 7,
    limit: Annotated[
        int,
        typer.Option("--limit", help="Max stocks to show", min=1, max=50),
    ] = 20,
    db_path: Annotated[
        Path,
        typer.Option("--db", help="SQLite database path"),
    ] = DEFAULT_DB_PATH,
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = APP_CFG.analysis.format,
) -> None:
    """
    Show cached foreign-broker top stock snapshots.

    This is a read-only view of data already stored by
    'saham fetch broker-top-foreign'. It never calls remote providers.

    Examples:
        saham view broker top-foreign --days 7
        saham view broker top-foreign --date 2024-01-15 --limit 10
    """
    query_date = date.fromisoformat(snapshot_date) if snapshot_date else date.today()
    repo = SQLiteBrokerRepository(db_path)
    snapshots = repo.get_foreign_flow_snapshots(query_date, period_days=days)
    if not snapshots:
        typer.echo(
            typer.style("No cached top-foreign snapshot found. ", fg=typer.colors.YELLOW)
            + "Run 'saham fetch broker-top-foreign' first."
        )
        raise typer.Exit(1)

    snapshots = snapshots[:limit]
    if fmt == "json":
        import json as _json
        payload = [
            {
                "ticker": s.ticker,
                "snapshot_date": query_date.isoformat(),
                "period_days": days,
                "net_val": str(s.net_val),
                "net_lot": s.net_lot,
                "direction": "buy" if s.is_accumulating else "sell",
            }
            for s in snapshots
        ]
        typer.echo(_json.dumps(payload, indent=2))
        return
    if fmt != "table":
        typer.echo(typer.style("Unknown format. Use: table or json", fg=typer.colors.RED))
        raise typer.Exit(1)

    display_broker_top_foreign_snapshots(
        snapshots=snapshots,
        query_date=query_date,
        days=days,
    )


def broker_distribution_view(
    ticker: Annotated[str, typer.Argument(help="Ticker symbol (e.g. BBCA)")],
    db_path: Annotated[
        Path,
        typer.Option("--db", help="SQLite database path"),
    ] = DEFAULT_DB_PATH,
) -> None:
    """
    Show cross-broker counterparty distribution for a ticker.

    Reveals which brokers bought FROM whom and sold TO whom today,
    exposing institutional rotation and smart-money accumulation patterns.

    Examples:
        saham view broker distribution BBCA
        saham view broker distribution GOTO --db /path/to/data.db
    """
    from src.infrastructure.browser.stockbit_broker_distribution import (
        StockbitBrokerDistributionProvider,
    )

    prov = StockbitBrokerDistributionProvider(api_client=None, db_path=db_path)
    snapshot = prov.get_distribution(ticker.upper())

    if snapshot is None:
        typer.echo(
            typer.style(f"No broker distribution data cached for {ticker.upper()}. ", fg=typer.colors.YELLOW)
            + "Run 'saham fetch market' with Stockbit first."
        )
        raise typer.Exit(1)

    _display_distribution(snapshot)


def _fmt_idr(amount: int) -> str:
    """Format IDR amount as compact string (e.g. 510.5B, 88.4M)."""
    abs_amt = abs(amount)
    if abs_amt >= 1_000_000_000_000:
        return f"{amount / 1_000_000_000_000:.1f}T"
    if abs_amt >= 1_000_000_000:
        return f"{amount / 1_000_000_000:.1f}B"
    if abs_amt >= 1_000_000:
        return f"{amount / 1_000_000:.1f}M"
    return f"{amount:,}"


def _broker_label(code: str, btype: str) -> str:
    tag = "A" if btype.lower() == "asing" else ("G" if btype.lower() == "pemerintah" else "L")
    return f"{code}[{tag}]"


def _display_distribution(snapshot: "BrokerDistributionSnapshot") -> None:
    """Render ASCII cross-broker distribution table."""
    from src.domain.value_objects.broker_distribution import (
        BrokerDistributionSnapshot,  # noqa: F401
    )

    acc_signal = ""
    if snapshot.foreign_buying_from_domestic:
        acc_signal = typer.style("  ★ Foreign accumulating from domestic (smart money signal)", fg=typer.colors.GREEN)
    elif snapshot.net_foreign_buyer_dominance:
        acc_signal = typer.style("  ● Foreign brokers dominate buy side", fg=typer.colors.CYAN)

    typer.echo(f"\n  {snapshot.ticker} — Broker Distribution  ({snapshot.date})")
    typer.echo(f"  {'─' * 64}")
    if acc_signal:
        typer.echo(acc_signal)

    def _render_side(entries, side_label: str, arrow: str) -> None:
        if not entries:
            return
        typer.echo(f"\n  {side_label}")
        typer.echo(f"  {'─' * 60}")
        for entry in entries[:5]:
            total_str = _fmt_idr(entry.amount_idr)
            label = _broker_label(entry.broker_code, entry.broker_type)
            color = typer.colors.GREEN if side_label.startswith("TOP BUYERS") else typer.colors.RED
            header = typer.style(f"  {label:<10} {total_str:>8}", fg=color)
            typer.echo(header)
            for cp in entry.counterparties[:4]:
                cp_label = _broker_label(cp.broker_code, cp.broker_type)
                pct = cp.amount_idr / entry.amount_idr * 100 if entry.amount_idr else 0
                cp_color = (
                    typer.colors.YELLOW if cp.broker_type.lower() == "lokal" else typer.colors.BRIGHT_BLACK
                )
                typer.echo(
                    typer.style(
                        f"    {arrow} {cp_label:<10} {_fmt_idr(cp.amount_idr):>8}  ({pct:.0f}%)",
                        fg=cp_color,
                    )
                )

    _render_side(snapshot.top_buyers, "TOP BUYERS  (bought FROM →)", "←")
    _render_side(snapshot.top_sellers, "TOP SELLERS (sold TO →)", "→")
    typer.echo("")


def broker_mappings() -> None:
    """
    List available CSV mapping configurations.

    Mappings define how CSV columns map to expected fields.
    Create custom mappings in config/csv_mappings/
    """
    loader = MappingLoader()
    mappings = loader.list_available()

    typer.echo("Available CSV Mappings:")
    typer.echo("-" * 40)

    for name in mappings:
        if name == "default":
            typer.echo(f"  {name} (built-in auto-detection)")
        else:
            typer.echo(f"  {name}")

    typer.echo("-" * 40)
    typer.echo("\nUse with: saham fetch broker-import data.csv --mapping <name>")
    typer.echo("Custom mappings: config/csv_mappings/<name>.yaml")
