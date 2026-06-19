"""
Daily briefing command.

Layer: Adapter
"""

from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel
from src.application.use_case.accumulation_screen import AccumulationScreenUseCase
from src.application.use_case.daily_briefing import DailyBriefingRequest, DailyBriefingUseCase
from src.application.use_case.market_regime import MarketRegimeUseCase
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

DEFAULT_DB_PATH = Path("data.db")


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        typer.echo(f"Invalid date format: {value} (expected YYYY-MM-DD)", err=True)
        raise typer.Exit(1)


def today(
    universe: Annotated[str, typer.Option("--universe", "-u", help="Universe to brief")] = "lq45",
    top: Annotated[int, typer.Option("--top", help="Number of candidates per section", min=1)] = 3,
    date_str: Annotated[Optional[str], typer.Option("--date", help="Date YYYY-MM-DD")] = None,
    db_path: Annotated[
        Path,
        typer.Option("--db", help="Path to SQLite database"),
    ] = DEFAULT_DB_PATH,
) -> None:
    """
    Show a read-only daily briefing from local cached data.

    This command does not fetch, tune, or write data. Use `saham fetch ...` and
    `saham screen ...` when you need to update inputs.
    """
    as_of = _parse_date(date_str)
    market_repo = SQLiteMarketRepository(db_path)
    broker_repo = SQLiteBrokerRepository(db_path)
    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        regime_use_case=MarketRegimeUseCase(
            market_repository=market_repo,
            broker_repository=broker_repo,
        ),
        accumulation_use_case=AccumulationScreenUseCase(
            broker_repository=broker_repo,
            market_repository=market_repo,
        ),
    )

    response = use_case.execute(
        DailyBriefingRequest(
            universe=universe,
            top=top,
            as_of_date=as_of,
        )
    )

    from src.infrastructure.browser.stockbit_market_time import (
        format_market_status_line,
        get_current_market_status,
    )
    market_status = get_current_market_status()

    fresh_count = response.universe_count - response.stale_count
    summary = compact_table(show_header=False)
    summary.add_column("Metric", style="bold")
    summary.add_column("Value")
    summary.add_row(
        "Market",
        f"{market_status.session_name}  [{market_status.source}]"
        + ("  ⚠ open" if market_status.is_open else ""),
    )
    summary.add_row("Universe", f"{response.universe.upper()} ({response.universe_count} tickers)")
    summary.add_row("Cached candles current", f"{fresh_count}/{response.universe_count}")
    if response.regime is not None:
        regime = response.regime
        summary.add_row("Market regime", f"{regime.label} ({regime.score}/7)")
        if regime.breadth_above_sma20_pct is not None:
            summary.add_row("Breadth above SMA20", f"{regime.breadth_above_sma20_pct:.0%}")
        if regime.foreign_flow_breadth_pct is not None:
            summary.add_row("Foreign flow breadth", f"{regime.foreign_flow_breadth_pct:.0%}")

    opening = compact_table()
    opening.add_column("Ticker", style="bold")
    opening.add_column("Verdict")
    opening.add_column("IEV", justify="right")
    opening.add_column("IEP", justify="right")
    opening.add_column("Trend")
    if response.opening_candidates:
        for candidate in response.opening_candidates:
            iev = f"{candidate.iev:,}" if candidate.iev is not None else "-"
            iep = f"{candidate.iep:,}" if candidate.iep is not None else "-"
            opening.add_row(candidate.ticker, candidate.verdict, iev, iep, candidate.trend or "-")
    else:
        opening.add_row("-", "No saved opening snapshot", "-", "-", "Run: saham learn snapshot --force")

    accumulation = compact_table()
    accumulation.add_column("Ticker", style="bold")
    accumulation.add_column("Score", justify="right")
    accumulation.add_column("Streak", justify="right")
    accumulation.add_column("Trend")
    if response.accumulation_candidates:
        for candidate in response.accumulation_candidates:
            accumulation.add_row(
                candidate.ticker,
                f"{candidate.score:.1f}",
                str(candidate.consecutive_streak),
                candidate.trend,
            )
    else:
        accumulation.add_row("-", "-", "-", "Run: saham screen accum --universe lq45")

    sections = [
        Text("Data & Regime", style="bold cyan"),
        summary,
        Text("Top Pre-Open Candidates", style="bold cyan"),
        opening,
        Text("Top Accumulation Candidates", style="bold cyan"),
        accumulation,
    ]

    if response.warnings:
        warnings = compact_table(show_header=False)
        warnings.add_column("Warning")
        for warning in response.warnings[:5]:
            warnings.add_row(f"- {warning}")
        sections.extend([Text("Warnings", style="bold yellow"), warnings])

    sections.append(Text("Next: saham screen accum --universe lq45 | saham analyze swing TICKER", style="bold"))
    console().print(
        panel(
            Group(*sections),
            title=f"Daily Briefing - {response.as_of_date.isoformat()}",
            subtitle=response.universe.upper(),
        )
    )
