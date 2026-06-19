"""
DTOs for post-update database status reporting.

Layer: Application
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DataUpdateTableStatus:
    """Read-only summary of one database table after a data update run."""

    table: str
    source: str
    rows: int | None
    tickers: int | None
    range_label: str
    status: str
    contains: str
    impact: str
    issue: str | None = None
