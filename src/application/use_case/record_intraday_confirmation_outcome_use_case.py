"""
RecordIntradayConfirmationOutcomeUseCase — record a manual trade outcome.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.application.services.intraday_confirmation_journal import (
    IntradayConfirmationJournalService,
)


@dataclass(frozen=True)
class RecordIntradayConfirmationOutcomeRequest:
    confirmed_at: date
    ticker: str
    actual_entry_price: Decimal
    actual_exit_price: Decimal
    outcome_result: str
    notes: str | None = None


@dataclass(frozen=True)
class RecordIntradayConfirmationOutcomeResponse:
    updated: bool
    outcome_r: Decimal | None


class RecordIntradayConfirmationOutcomeUseCase:
    """Record a manual trade outcome for a logged intraday confirmation."""

    def __init__(self, journal_service: IntradayConfirmationJournalService) -> None:
        self._journal_service = journal_service

    def execute(
        self,
        request: RecordIntradayConfirmationOutcomeRequest,
    ) -> RecordIntradayConfirmationOutcomeResponse:
        updated, outcome_r = self._journal_service.record_outcome(
            confirmed_at=request.confirmed_at,
            ticker=request.ticker,
            actual_entry_price=request.actual_entry_price,
            actual_exit_price=request.actual_exit_price,
            outcome_result=request.outcome_result,
            notes=request.notes,
        )
        return RecordIntradayConfirmationOutcomeResponse(
            updated=updated, outcome_r=outcome_r,
        )
