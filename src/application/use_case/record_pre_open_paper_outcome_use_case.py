"""
RecordPreOpenPaperOutcomeUseCase — record a manual paper outcome.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.application.services.pre_open_paper_journal import (
    PreOpenPaperJournalService,
)


@dataclass(frozen=True)
class RecordPreOpenPaperOutcomeRequest:
    confirmed_at: date
    ticker: str
    actual_entry_price: Decimal
    actual_exit_price: Decimal
    outcome_result: str
    notes: str | None = None


@dataclass(frozen=True)
class RecordPreOpenPaperOutcomeResponse:
    updated: bool
    outcome_r: Decimal | None


class RecordPreOpenPaperOutcomeUseCase:
    """Record a manual outcome on a pre-open paper journal row."""

    def __init__(self, journal_service: PreOpenPaperJournalService) -> None:
        self._journal_service = journal_service

    def execute(
        self,
        request: RecordPreOpenPaperOutcomeRequest,
    ) -> RecordPreOpenPaperOutcomeResponse:
        updated, outcome_r = self._journal_service.record_outcome(
            confirmed_at=request.confirmed_at,
            ticker=request.ticker,
            actual_entry_price=request.actual_entry_price,
            actual_exit_price=request.actual_exit_price,
            outcome_result=request.outcome_result,
            notes=request.notes,
        )
        return RecordPreOpenPaperOutcomeResponse(
            updated=updated, outcome_r=outcome_r,
        )
