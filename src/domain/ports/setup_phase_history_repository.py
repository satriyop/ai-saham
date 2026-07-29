"""Port for closed-session setup phase production memory (sequence history).

Layer: Domain (port)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Protocol, Sequence

from src.domain.value_objects.setup_phase import SetupPhaseState

# Stored when screen did not resolve a primary family. Read path treats this
# as "generic screen history" (same role as missing family on observations).
GENERIC_SETUP_FAMILY = ""

SOURCE_WORKFLOW_SCREEN_ACCUM = "screen_accum"

SCHEMA_VERSION_V1 = 1


@dataclass(frozen=True)
class SetupPhaseLedgerRow:
    """One as-of phase fact for sequence validation."""

    entry_id: str
    ticker: str
    as_of_date: date
    phase: SetupPhaseState
    setup_family: str  # normalized; "" = generic / unresolved primary
    source_workflow: str
    recorded_at: str
    schema_version: int = SCHEMA_VERSION_V1
    observation_id: str | None = None


class SetupPhaseRecordResult(str, Enum):
    INSERTED = "inserted"
    UPDATED = "updated"
    SKIPPED_IDENTICAL = "skipped_identical"
    SKIPPED_POLICY = "skipped_policy"


class SetupPhaseHistoryRepository(Protocol):
    """Append/upsert closed-session phase facts; query by ticker and cutoff."""

    def list_rows_before(
        self,
        *,
        ticker: str,
        before_date: date,
        limit: int | None = None,
    ) -> Sequence[SetupPhaseLedgerRow]: ...

    def list_rows_before_many(
        self,
        *,
        tickers: Sequence[str],
        before_date: date,
    ) -> Sequence[SetupPhaseLedgerRow]: ...

    def record_phase(
        self,
        *,
        ticker: str,
        as_of_date: date,
        phase: SetupPhaseState,
        setup_family: str | None,
        source_workflow: str,
        observation_id: str | None = None,
    ) -> SetupPhaseRecordResult: ...
