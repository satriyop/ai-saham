"""StockMeta domain entity — static metadata for a listed stock."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class StockMeta:
    ticker: str
    name: str | None
    sector: str | None
    sector_key: str | None
    industry: str | None
    industry_key: str | None
    source: str              # 'yahoo' | 'idxic' — tracks classification origin
    fetched_at: datetime
    checksum: str            # sha1(sector|industry) — change detection
