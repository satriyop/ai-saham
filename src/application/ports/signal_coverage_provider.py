"""
SignalCoverageProvider port — interface for per-factor enrichment coverage queries.

Phase 0 observability: answers "how many tickers have usable data for each
signal factor?" without leaking storage technology into the application layer.

Layer: Application (port only — no sqlite3, no infrastructure imports).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class FactorCoverage:
    factor: str
    total_rows: int
    usable_rows: int  # rows matching the quality filter (or total if no filter)
    total_tickers: int  # distinct ticker count in the table
    note: str | None = field(default=None)
    # note is non-None when usable_rows == total_rows because no directional
    # quality filter exists for this factor (e.g. seasonality, forward estimates).
    # Display should distinguish "cache total" from "usable directional coverage."


@dataclass(frozen=True)
class SignalCoverageReport:
    db_path: str
    as_of: date
    total_tickers_in_db: int
    factors: tuple[FactorCoverage, ...]


class SignalCoverageProvider(ABC):
    """Port: compute enrichment table coverage counts per signal factor."""

    @abstractmethod
    def compute(self, db_path: Path) -> SignalCoverageReport:
        """Return per-factor row/ticker counts from the enrichment cache tables."""
