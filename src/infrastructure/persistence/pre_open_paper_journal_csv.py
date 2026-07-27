"""
CSV persistence for intraday confirmation journal rows.

Layer: Infrastructure
"""

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.domain.value_objects.pre_open_post_open_assessment import (
    PreOpenPaperJournalEntry,
)

_COLUMNS = [
    "confirmed_at",
    "ticker",
    "decision",
    "reason_codes",
    "opening_price",
    "planned_entry",
    "stop_loss_price",
    "stop_pct",
    "iev",
    "trend",
    "rsi",
    "gap_pct",
    "opening_broker_backing_tag",
    "fvwap_discount_pct",
    "actual_entry_price",
    "actual_exit_price",
    "outcome_result",
    "outcome_r",
    "outcome_notes",
]


def _to_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        quantized = value.quantize(Decimal("0.0001"))
        text = format(quantized, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    if isinstance(value, tuple):
        return "|".join(str(v) for v in value)
    return str(value)


def _decimal_or_none(value: str) -> Decimal | None:
    return Decimal(value) if value else None


def _int_or_none(value: str) -> int | None:
    return int(value) if value else None


class PreOpenPaperJournalCsvStore:
    """CSV store for intraday confirmation journal entries."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def append(self, entries: list[PreOpenPaperJournalEntry]) -> int:
        existing_keys: set[tuple[str, str]] = set()
        if self._path.exists():
            with open(self._path, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    existing_keys.add((row["confirmed_at"], row["ticker"]))

        new_entries = [
            entry
            for entry in entries
            if (str(entry.confirmed_at), entry.ticker) not in existing_keys
        ]
        if not new_entries:
            return 0

        self._path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not self._path.exists()
        with open(self._path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_COLUMNS)
            if write_header:
                writer.writeheader()
            for entry in new_entries:
                writer.writerow(
                    {
                        "confirmed_at": str(entry.confirmed_at),
                        "ticker": entry.ticker,
                        "decision": entry.decision,
                        "reason_codes": _to_str(entry.reason_codes),
                        "opening_price": _to_str(entry.opening_price),
                        "planned_entry": _to_str(entry.planned_entry),
                        "stop_loss_price": _to_str(entry.stop_loss_price),
                        "stop_pct": _to_str(entry.stop_pct),
                        "iev": _to_str(entry.iev),
                        "trend": _to_str(entry.trend),
                        "rsi": _to_str(entry.rsi),
                        "gap_pct": _to_str(entry.gap_pct),
                        "opening_broker_backing_tag": _to_str(entry.opening_broker_backing_tag),
                        "fvwap_discount_pct": _to_str(entry.fvwap_discount_pct),
                        "actual_entry_price": _to_str(entry.actual_entry_price),
                        "actual_exit_price": _to_str(entry.actual_exit_price),
                        "outcome_result": _to_str(entry.outcome_result),
                        "outcome_r": _to_str(entry.outcome_r),
                        "outcome_notes": _to_str(entry.outcome_notes),
                    }
                )
        return len(new_entries)

    def read_all(self) -> list[PreOpenPaperJournalEntry]:
        if not self._path.exists():
            return []

        entries: list[PreOpenPaperJournalEntry] = []
        with open(self._path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                entries.append(
                    PreOpenPaperJournalEntry(
                        confirmed_at=date.fromisoformat(row["confirmed_at"]),
                        ticker=row["ticker"],
                        decision=row["decision"],
                        reason_codes=tuple(
                            code for code in row["reason_codes"].split("|") if code
                        ),
                        opening_price=_decimal_or_none(row["opening_price"]),
                        planned_entry=_decimal_or_none(row["planned_entry"]),
                        stop_loss_price=_decimal_or_none(row["stop_loss_price"]),
                        stop_pct=_decimal_or_none(row["stop_pct"]),
                        iev=_int_or_none(row["iev"]),
                        trend=row["trend"] or None,
                        rsi=_decimal_or_none(row["rsi"]),
                        gap_pct=_decimal_or_none(row["gap_pct"]),
                        opening_broker_backing_tag=row["opening_broker_backing_tag"] or None,
                        fvwap_discount_pct=_decimal_or_none(row["fvwap_discount_pct"]),
                        actual_entry_price=_decimal_or_none(
                            row.get("actual_entry_price", "")
                        ),
                        actual_exit_price=_decimal_or_none(
                            row.get("actual_exit_price", "")
                        ),
                        outcome_result=row.get("outcome_result", "") or None,
                        outcome_r=_decimal_or_none(row.get("outcome_r", "")),
                        outcome_notes=row.get("outcome_notes", "") or None,
                    )
                )

        return sorted(entries, key=lambda entry: (entry.confirmed_at, entry.ticker))

    def update_outcome(
        self,
        *,
        confirmed_at: date,
        ticker: str,
        actual_entry_price: Decimal,
        actual_exit_price: Decimal,
        outcome_result: str,
        outcome_r: Decimal | None,
        outcome_notes: str | None,
    ) -> bool:
        entries = self.read_all()
        updated = False
        next_entries: list[PreOpenPaperJournalEntry] = []
        ticker_upper = ticker.upper()

        for entry in entries:
            if entry.confirmed_at == confirmed_at and entry.ticker.upper() == ticker_upper:
                updated = True
                next_entries.append(
                    PreOpenPaperJournalEntry(
                        confirmed_at=entry.confirmed_at,
                        ticker=entry.ticker,
                        decision=entry.decision,
                        reason_codes=entry.reason_codes,
                        opening_price=entry.opening_price,
                        planned_entry=entry.planned_entry,
                        stop_loss_price=entry.stop_loss_price,
                        stop_pct=entry.stop_pct,
                        iev=entry.iev,
                        trend=entry.trend,
                        rsi=entry.rsi,
                        gap_pct=entry.gap_pct,
                        opening_broker_backing_tag=entry.opening_broker_backing_tag,
                        fvwap_discount_pct=entry.fvwap_discount_pct,
                        actual_entry_price=actual_entry_price,
                        actual_exit_price=actual_exit_price,
                        outcome_result=outcome_result,
                        outcome_r=outcome_r,
                        outcome_notes=outcome_notes,
                    )
                )
            else:
                next_entries.append(entry)

        if not updated:
            return False

        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_COLUMNS)
            writer.writeheader()
            for entry in next_entries:
                writer.writerow(
                    {
                        "confirmed_at": str(entry.confirmed_at),
                        "ticker": entry.ticker,
                        "decision": entry.decision,
                        "reason_codes": _to_str(entry.reason_codes),
                        "opening_price": _to_str(entry.opening_price),
                        "planned_entry": _to_str(entry.planned_entry),
                        "stop_loss_price": _to_str(entry.stop_loss_price),
                        "stop_pct": _to_str(entry.stop_pct),
                        "iev": _to_str(entry.iev),
                        "trend": _to_str(entry.trend),
                        "rsi": _to_str(entry.rsi),
                        "gap_pct": _to_str(entry.gap_pct),
                        "opening_broker_backing_tag": _to_str(entry.opening_broker_backing_tag),
                        "fvwap_discount_pct": _to_str(entry.fvwap_discount_pct),
                        "actual_entry_price": _to_str(entry.actual_entry_price),
                        "actual_exit_price": _to_str(entry.actual_exit_price),
                        "outcome_result": _to_str(entry.outcome_result),
                        "outcome_r": _to_str(entry.outcome_r),
                        "outcome_notes": _to_str(entry.outcome_notes),
                    }
                )
        return True
