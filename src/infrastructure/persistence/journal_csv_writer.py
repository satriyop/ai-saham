"""
JournalCsvWriter — CSV-backed implementation of JournalStore.

Appends rows to a CSV file. Idempotent: (screened_at, ticker) is the
deduplication key — re-running log for the same day never doubles rows.

Layer: Infrastructure
"""

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.domain.ports.journal_store import JournalStore
from src.domain.value_objects.journal_entry import JournalEntry

_COLUMNS = [
    "screened_at", "ticker", "iev", "gap_pct",
    "entry_range_low", "entry_range_high", "suggested_entry", "atr_stop",
    "trend", "rsi",
    "actual_open", "actual_close_1d", "actual_close_5d",
]


def _to_str(val) -> str:
    return "" if val is None else str(val)


def _from_str(s: str) -> Decimal | None:
    return Decimal(s) if s else None


def _from_int_str(s: str) -> int | None:
    return int(s) if s else None


class JournalCsvWriter(JournalStore):
    """Reads and appends JournalEntry rows to a CSV file."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def append(self, entries: list[JournalEntry]) -> None:
        """Append entries, skipping any (screened_at, ticker) already present."""
        existing_keys: set[tuple] = set()
        if self._path.exists():
            with open(self._path, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    existing_keys.add((row["screened_at"], row["ticker"]))

        self._path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not self._path.exists()

        new_entries = [
            e for e in entries
            if (str(e.screened_at), e.ticker) not in existing_keys
        ]
        if not new_entries:
            return

        with open(self._path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_COLUMNS)
            if write_header:
                writer.writeheader()
            for e in new_entries:
                writer.writerow({
                    "screened_at": str(e.screened_at),
                    "ticker": e.ticker,
                    "iev": e.iev,
                    "gap_pct": _to_str(e.gap_pct),
                    "entry_range_low": _to_str(e.entry_range_low),
                    "entry_range_high": _to_str(e.entry_range_high),
                    "suggested_entry": _to_str(e.suggested_entry),
                    "atr_stop": _to_str(e.atr_stop),
                    "trend": _to_str(e.trend),
                    "rsi": _to_str(e.rsi),
                    "actual_open": _to_str(e.actual_open),
                    "actual_close_1d": _to_str(e.actual_close_1d),
                    "actual_close_5d": _to_str(e.actual_close_5d),
                })

    def read_all(self) -> list[JournalEntry]:
        """Return all stored entries sorted by screened_at ascending."""
        if not self._path.exists():
            return []

        entries: list[JournalEntry] = []
        with open(self._path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                entries.append(JournalEntry(
                    screened_at=date.fromisoformat(row["screened_at"]),
                    ticker=row["ticker"],
                    iev=int(row["iev"]),
                    gap_pct=_from_str(row["gap_pct"]),
                    entry_range_low=_from_str(row["entry_range_low"]),
                    entry_range_high=_from_str(row["entry_range_high"]),
                    suggested_entry=_from_str(row["suggested_entry"]),
                    atr_stop=_from_str(row["atr_stop"]),
                    trend=row["trend"] or None,
                    rsi=_from_str(row["rsi"]),
                    actual_open=_from_str(row["actual_open"]),
                    actual_close_1d=_from_str(row["actual_close_1d"]),
                    actual_close_5d=_from_str(row["actual_close_5d"]),
                ))

        return sorted(entries, key=lambda e: e.screened_at)
