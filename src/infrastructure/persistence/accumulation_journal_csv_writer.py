"""
AccumulationJournalCsvWriter — CSV-backed implementation of AccumulationJournalStore.

Appends rows to a CSV file. Idempotent: (logged_at, ticker, window_days) is the
deduplication key.

Layer: Infrastructure
"""

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.domain.ports.accumulation_journal_store import AccumulationJournalStore
from src.domain.value_objects.accumulation_journal_entry import AccumulationJournalEntry

_COLUMNS = [
    # Log-time fields
    "logged_at", "ticker", "entry_price", "window_days",
    "score", "streak", "flow_pct", "vwap_disc_pct", "bb_pctile", "rsi",
    "trend", "pattern",
    "setup", "setup_match", "failed_gates", "regime",
    "planned_entry", "planned_stop", "planned_target", "max_hold_days",
    # Review-time fields
    "actual_close_5d", "actual_close_10d", "actual_close_20d",
    "max_close_in_horizon", "min_close_in_horizon",
]


def _to_str(val) -> str:
    if val is None:
        return ""
    if isinstance(val, Decimal):
        quantized = val.quantize(Decimal("0.0001"))
        s = format(quantized, "f")
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return s
    return str(val)


def _from_str(s: str) -> Decimal | None:
    return Decimal(s) if s else None


def _from_float_str(s: str) -> float | None:
    return float(s) if s else None


def _from_int_str(s: str) -> int | None:
    return int(s) if s else None


def _row_to_entry(row: dict[str, str]) -> AccumulationJournalEntry:
    return AccumulationJournalEntry(
        logged_at=date.fromisoformat(row["logged_at"]),
        ticker=row["ticker"],
        entry_price=_from_str(row["entry_price"]) or Decimal("0"),
        window_days=int(row["window_days"]),
        score=float(row["score"]) if row["score"] else 0.0,
        streak=int(row["streak"]) if row["streak"] else 0,
        flow_pct=_from_str(row["flow_pct"]),
        vwap_disc_pct=_from_str(row["vwap_disc_pct"]),
        bb_pctile=_from_str(row["bb_pctile"]),
        rsi=_from_str(row["rsi"]),
        trend=row["trend"] or None,
        pattern=row["pattern"] or None,
        setup=row.get("setup") or None,
        setup_match=row.get("setup_match") or None,
        failed_gates=tuple(
            part.strip()
            for part in (row.get("failed_gates") or "").split(";")
            if part.strip()
        ),
        regime=row.get("regime") or None,
        planned_entry=_from_str(row.get("planned_entry", "")),
        planned_stop=_from_str(row.get("planned_stop", "")),
        planned_target=_from_str(row.get("planned_target", "")),
        max_hold_days=_from_int_str(row.get("max_hold_days", "")),
        actual_close_5d=_from_str(row.get("actual_close_5d", "")),
        actual_close_10d=_from_str(row.get("actual_close_10d", "")),
        actual_close_20d=_from_str(row.get("actual_close_20d", "")),
        max_close_in_horizon=_from_str(row.get("max_close_in_horizon", "")),
        min_close_in_horizon=_from_str(row.get("min_close_in_horizon", "")),
    )


def _entry_to_row(e: AccumulationJournalEntry) -> dict[str, str | int | float]:
    return {
        "logged_at": str(e.logged_at),
        "ticker": e.ticker,
        "entry_price": _to_str(e.entry_price),
        "window_days": e.window_days,
        "score": e.score,
        "streak": e.streak,
        "flow_pct": _to_str(e.flow_pct),
        "vwap_disc_pct": _to_str(e.vwap_disc_pct),
        "bb_pctile": _to_str(e.bb_pctile),
        "rsi": _to_str(e.rsi),
        "trend": e.trend or "",
        "pattern": e.pattern or "",
        "setup": e.setup or "",
        "setup_match": e.setup_match or "",
        "failed_gates": "; ".join(e.failed_gates),
        "regime": e.regime or "",
        "planned_entry": _to_str(e.planned_entry),
        "planned_stop": _to_str(e.planned_stop),
        "planned_target": _to_str(e.planned_target),
        "max_hold_days": e.max_hold_days or "",
        "actual_close_5d": _to_str(e.actual_close_5d),
        "actual_close_10d": _to_str(e.actual_close_10d),
        "actual_close_20d": _to_str(e.actual_close_20d),
        "max_close_in_horizon": _to_str(e.max_close_in_horizon),
        "min_close_in_horizon": _to_str(e.min_close_in_horizon),
    }


class AccumulationJournalCsvWriter(AccumulationJournalStore):

    def __init__(self, path: Path) -> None:
        self._path = path

    def append(self, entries: list[AccumulationJournalEntry]) -> int:
        existing_keys: set[tuple] = set()
        if self._path.exists():
            with open(self._path, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    existing_keys.add((row["logged_at"], row["ticker"], row["window_days"]))

        self._path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not self._path.exists()

        new_entries = [
            e for e in entries
            if (str(e.logged_at), e.ticker, str(e.window_days)) not in existing_keys
        ]
        if not new_entries:
            return 0

        with open(self._path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_COLUMNS)
            if write_header:
                writer.writeheader()
            for e in new_entries:
                writer.writerow(_entry_to_row(e))
        return len(new_entries)

    def read_all(self) -> list[AccumulationJournalEntry]:
        if not self._path.exists():
            return []

        entries: list[AccumulationJournalEntry] = []
        with open(self._path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                entries.append(_row_to_entry(row))

        return sorted(entries, key=lambda e: e.logged_at)

    def update_review_fields(
        self, entries: list[AccumulationJournalEntry]
    ) -> int:
        """Rewrite CSV updating review fields for matching (logged_at, ticker, window_days)."""
        if not self._path.exists():
            return 0

        existing = self.read_all()
        lookup: dict[tuple, AccumulationJournalEntry] = {
            (str(e.logged_at), e.ticker, str(e.window_days)): e
            for e in entries
        }

        updated = 0
        merged: list[AccumulationJournalEntry] = []
        for e in existing:
            key = (str(e.logged_at), e.ticker, str(e.window_days))
            if key in lookup:
                merged.append(lookup[key])
                updated += 1
            else:
                merged.append(e)

        # Rewrite entire file
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_COLUMNS)
            writer.writeheader()
            for e in merged:
                writer.writerow(_entry_to_row(e))
        return updated
