"""
Daily briefing command.

Layer: Adapter
"""

from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer

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

    typer.echo("")
    typer.echo(f"Daily Briefing · {response.as_of_date.isoformat()} · {response.universe}")
    typer.echo("=" * 72)
    typer.echo(f"Universe: {response.universe_count} tickers")

    fresh_count = response.universe_count - response.stale_count
    typer.echo(f"Cached candles current for date: {fresh_count}/{response.universe_count}")

    if response.regime is not None:
        regime = response.regime
        typer.echo("")
        typer.echo(f"Market regime: {regime.label} ({regime.score}/7)")
        if regime.breadth_above_sma20_pct is not None:
            typer.echo(f"Breadth above SMA20: {regime.breadth_above_sma20_pct:.0%}")
        if regime.foreign_flow_breadth_pct is not None:
            typer.echo(f"Foreign flow breadth: {regime.foreign_flow_breadth_pct:.0%}")

    typer.echo("")
    typer.echo("Top pre-open candidates")
    if response.opening_candidates:
        for candidate in response.opening_candidates:
            iev = f"{candidate.iev:,}" if candidate.iev is not None else "-"
            iep = f"{candidate.iep:,}" if candidate.iep is not None else "-"
            typer.echo(
                f"  {candidate.ticker:<8} {candidate.verdict:<6} "
                f"IEV={iev:>12} IEP={iep:>8} trend={candidate.trend or '-'}"
            )
    else:
        typer.echo("  No saved opening snapshot. Run: saham learn snapshot --force")

    typer.echo("")
    typer.echo("Top accumulation candidates")
    if response.accumulation_candidates:
        for candidate in response.accumulation_candidates:
            typer.echo(
                f"  {candidate.ticker:<8} score={candidate.score:>5.1f} "
                f"streak={candidate.consecutive_streak:<2} trend={candidate.trend:<4}"
            )
    else:
        typer.echo("  No cached accumulation candidates. Run: saham screen accum --universe lq45")

    if response.warnings:
        typer.echo("")
        typer.echo("Warnings")
        for warning in response.warnings[:5]:
            typer.echo(f"  - {warning}")

    typer.echo("")
    typer.echo("Next: saham screen accum --universe lq45 | saham analyze swing TICKER")
