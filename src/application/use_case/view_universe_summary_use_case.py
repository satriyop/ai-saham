"""
Universe view use case.

Aggregates locally cached market data (candles, broker flow, stock meta) across
all tickers in a named universe. Uses a UniverseSummaryProvider port.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.application.ports.universe_summary_provider import UniverseSummaryProvider
from src.application.services.universe_loader import (
    UNIVERSE_CONFIG_PATH,
    load_universe_entry,
)


@dataclass
class UniverseTickerRow:
    ticker: str
    name: str | None
    sector: str | None
    last_close: Decimal | None
    change_pct: float | None
    volume: int | None
    foreign_net_value: Decimal | None
    foreign_flow_ratio: float | None
    latest_date: date | None


@dataclass
class UniverseViewResult:
    universe_name: str
    ticker_count: int
    updated: str
    as_of_date: date | None
    rows: list[UniverseTickerRow]
    missing_candles: int
    missing_flow: int


def build_universe_view(
    universe_name: str,
    db_path: Path,
    config_path: Path = UNIVERSE_CONFIG_PATH,
    as_of_date: date | None = None,
    provider: UniverseSummaryProvider | None = None,
) -> UniverseViewResult:
    """Aggregate locally cached data for all tickers in a named universe.

    Uses a UniverseSummaryProvider (SQLite implementation by default) to perform
    fast batch retrieval without per-entity hydration overhead.

    Raises:
        UniverseNotFoundError: If universe_name is not in config.
        FileNotFoundError: If universes.yaml does not exist.
    """
    tickers, updated = load_universe_entry(universe_name, config_path)

    if not tickers:
        return UniverseViewResult(
            universe_name=universe_name,
            ticker_count=0,
            updated=updated,
            as_of_date=None,
            rows=[],
            missing_candles=0,
            missing_flow=0,
        )

    if provider is None:
        from src.infrastructure.persistence.sqlite_universe_summary_provider import (
            SQLiteUniverseSummaryProvider,
        )

        provider = SQLiteUniverseSummaryProvider(db_path)

    return provider.build_universe_view(
        universe_name=universe_name,
        tickers=tickers,
        updated=updated,
        as_of_date=as_of_date,
    )
