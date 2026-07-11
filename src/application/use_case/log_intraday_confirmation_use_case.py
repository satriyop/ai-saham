"""
LogIntradayConfirmationUseCase — append confirmation sidecar to the journal.

Layer: Application
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.application.services.intraday_confirmation_journal import (
    IntradayConfirmationStore,
)
from src.domain.ports.trade_journal_store import TradeJournalStore
from src.domain.value_objects.intraday_confirmation import (
    IntradayConfirmationJournalEntry,
)


@dataclass(frozen=True)
class LogIntradayConfirmationRequest:
    confirmation_path: Path
    journal_path: Path


@dataclass(frozen=True)
class LogIntradayConfirmationResponse:
    confirmed_at: date
    logged_count: int
    journal_path: Path
    duplicate: bool


def _decimal_or_none(value) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


class LogIntradayConfirmationUseCase:
    """Read a confirmation sidecar and append entries to CSV + JSONL journals."""

    def __init__(
        self,
        confirmation_store: IntradayConfirmationStore,
        trade_journal_store: TradeJournalStore | None = None,
    ) -> None:
        self._confirmation_store = confirmation_store
        self._trade_journal_store = trade_journal_store

    def execute(
        self,
        request: LogIntradayConfirmationRequest,
    ) -> LogIntradayConfirmationResponse:
        if not request.confirmation_path.exists():
            raise FileNotFoundError(
                f"No confirmation sidecar found at '{request.confirmation_path}'."
            )

        with open(request.confirmation_path) as f:
            data = json.load(f)

        confirmed_at = date.fromisoformat(data["confirmed_at"])
        entries = [
            IntradayConfirmationJournalEntry(
                confirmed_at=confirmed_at,
                ticker=row["ticker"],
                decision=row["decision"],
                reason_codes=tuple(row.get("reasons", [])),
                opening_price=_decimal_or_none(row.get("opening_price")),
                planned_entry=_decimal_or_none(row.get("planned_entry")),
                stop_loss_price=_decimal_or_none(row.get("stop_loss_price")),
                stop_pct=_decimal_or_none(row.get("stop_pct")),
                iev=row.get("iev"),
                trend=row.get("trend"),
                rsi=_decimal_or_none(row.get("rsi")),
                gap_pct=_decimal_or_none(row.get("gap_pct")),
                opening_broker_backing_tag=row.get("opening_broker_backing_tag"),
                fvwap_discount_pct=_decimal_or_none(row.get("fvwap_discount_pct")),
            )
            for row in data.get("confirmations", [])
        ]

        count = self._confirmation_store.append(entries)

        duplicate = count == 0
        if not duplicate and self._trade_journal_store is not None:
            for entry in entries:
                self._trade_journal_store.append(self._entry_to_record(entry))

        return LogIntradayConfirmationResponse(
            confirmed_at=confirmed_at,
            logged_count=count,
            journal_path=request.journal_path,
            duplicate=duplicate,
        )

    @staticmethod
    def _f(v) -> float | None:
        if v is None:
            return None
        return float(v)

    @staticmethod
    def _entry_to_record(entry) -> dict:
        return {
            "trade_type": "intraday",
            "logged_at": str(entry.confirmed_at),
            "ticker": entry.ticker,
            "regime": None,
            "trend": entry.trend,
            "rsi": LogIntradayConfirmationUseCase._f(entry.rsi),
            "decision": entry.decision,
            "planned_entry": LogIntradayConfirmationUseCase._f(entry.planned_entry),
            "planned_stop": LogIntradayConfirmationUseCase._f(entry.stop_loss_price),
            "planned_target": None,
            "stop_pct": LogIntradayConfirmationUseCase._f(entry.stop_pct),
            "iev": entry.iev,
            "gap_pct": LogIntradayConfirmationUseCase._f(entry.gap_pct),
            "opening_broker_backing_tag": entry.opening_broker_backing_tag,
            "fvwap_discount_pct": LogIntradayConfirmationUseCase._f(entry.fvwap_discount_pct),
            "opening_price": LogIntradayConfirmationUseCase._f(entry.opening_price),
            "reason_codes": list(entry.reason_codes),
            "actual_entry_price": LogIntradayConfirmationUseCase._f(entry.actual_entry_price),
            "actual_exit_price": LogIntradayConfirmationUseCase._f(entry.actual_exit_price),
            "outcome_result": entry.outcome_result,
            "outcome_r": LogIntradayConfirmationUseCase._f(entry.outcome_r),
            "outcome_notes": entry.outcome_notes,
        }
