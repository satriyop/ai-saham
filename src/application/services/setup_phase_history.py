"""Read persisted setup phase history for deterministic sequence validation.

Production memory is the setup phase ledger (not learning observations).
Family / generic-screen matching rules preserve prior observation-mining
semantics.

Layer: Application
Depends on: repository port + domain value objects only.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from src.domain.ports.setup_phase_history_repository import (
    GENERIC_SETUP_FAMILY,
    SOURCE_WORKFLOW_SCREEN_ACCUM,
    SetupPhaseHistoryRepository,
    SetupPhaseLedgerRow,
    SetupPhaseRecordResult,
)
from src.domain.value_objects.setup_phase import SetupPhaseState

CANONICAL_PHASE_LEDGER_WINDOW = 7


@dataclass(frozen=True)
class SetupPhaseHistoryIndex:
    """Run-scoped batch of ledger rows keyed by ticker (oldest→newest per ticker)."""

    rows_by_ticker: Mapping[str, tuple[SetupPhaseLedgerRow, ...]]

    @classmethod
    def from_rows(cls, rows: Sequence[SetupPhaseLedgerRow]) -> SetupPhaseHistoryIndex:
        grouped: dict[str, list[SetupPhaseLedgerRow]] = defaultdict(list)
        for row in rows:
            grouped[row.ticker.upper()].append(row)
        return cls(rows_by_ticker={ticker: tuple(items) for ticker, items in grouped.items()})

    @classmethod
    def empty(cls) -> SetupPhaseHistoryIndex:
        return cls(rows_by_ticker={})

    def rows_for(self, ticker: str) -> tuple[SetupPhaseLedgerRow, ...]:
        return self.rows_by_ticker.get(str(ticker).upper(), ())


def build_setup_phase_history_index(
    repository: SetupPhaseHistoryRepository | None,
    *,
    tickers: Sequence[str],
    before_date: date,
) -> SetupPhaseHistoryIndex:
    """Load all prior phase rows for a multi-ticker screen run once."""
    if repository is None or not tickers:
        return SetupPhaseHistoryIndex.empty()
    rows = repository.list_rows_before_many(tickers=tickers, before_date=before_date)
    return SetupPhaseHistoryIndex.from_rows(rows)


def load_previous_setup_phases(
    repository: SetupPhaseHistoryRepository | None = None,
    *,
    ticker: str,
    before_date: date,
    setup_family: str | None = None,
    limit: int = 20,
    history_index: SetupPhaseHistoryIndex | None = None,
    # Backward-compatible unused kwargs (old observation path).
    **_legacy: Any,
) -> tuple[SetupPhaseState, ...]:
    """Return prior persisted phases oldest-to-newest for sequence validation.

    Prefer ``history_index`` (run-scoped batch). Fall back to repository
    single-ticker list. Empty when neither is available.
    """
    if history_index is not None:
        rows = history_index.rows_for(ticker)
    elif repository is not None:
        rows = tuple(repository.list_rows_before(ticker=ticker, before_date=before_date))
    else:
        return ()

    # Index may contain rows at/after before_date if reused incorrectly; enforce.
    rows = tuple(r for r in rows if r.as_of_date < before_date)

    expected_family = _normalize_setup_family(setup_family)
    phases: list[SetupPhaseState] = []
    for row in rows:
        if not _row_matches_family(row, expected_family):
            continue
        phases.append(row.phase)

    if limit > 0:
        phases = phases[-limit:]
    return tuple(phases)


def record_setup_phase_for_screen(
    repository: SetupPhaseHistoryRepository | None,
    *,
    ticker: str,
    as_of_date: date,
    phase: SetupPhaseState | None,
    setup_family: str | None,
    window_days: int | None,
    source_workflow: str = SOURCE_WORKFLOW_SCREEN_ACCUM,
    observation_id: str | None = None,
    canonical_window: int = CANONICAL_PHASE_LEDGER_WINDOW,
) -> SetupPhaseRecordResult | None:
    """Write closed-session phase fact from assess path (canonical window only)."""
    if repository is None or phase is None:
        return None
    if window_days is not None and int(window_days) != int(canonical_window):
        return SetupPhaseRecordResult.SKIPPED_POLICY
    if phase is SetupPhaseState.NONE:
        return SetupPhaseRecordResult.SKIPPED_POLICY
    return repository.record_phase(
        ticker=ticker,
        as_of_date=as_of_date,
        phase=phase,
        setup_family=setup_family,
        source_workflow=source_workflow,
        observation_id=observation_id,
    )


def _row_matches_family(
    row: SetupPhaseLedgerRow,
    expected_family: str | None,
) -> bool:
    if expected_family is None:
        return True
    observed = _normalize_setup_family(row.setup_family) or None
    if observed is None or observed == GENERIC_SETUP_FAMILY:
        # Generic / unresolved primary — same allowance as missing family on
        # historical observations.
        return _allows_generic_screen_history(
            source_workflow=row.source_workflow,
            expected_family=expected_family,
            phase=row.phase,
        )
    return observed == expected_family


def _normalize_setup_family(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower().replace("_", "-")
    if not text:
        return None
    return text


def _allows_generic_screen_history(
    *,
    source_workflow: str,
    expected_family: str,
    phase: SetupPhaseState | None,
) -> bool:
    workflow = (source_workflow or "").strip().lower()
    # screen_accum and research_accum_capture both assess via screen path;
    # capture stores workflow research_accum_capture on observations but ledger
    # writes use screen_accum. Accept both for generic history.
    if workflow not in {
        SOURCE_WORKFLOW_SCREEN_ACCUM,
        "research_accum_capture",
        "screen_accum",
    }:
        return False
    if expected_family in {"accumulation", "foreign-bounce"}:
        return True
    if expected_family in {"breakout", "coiled-spring"}:
        # Only COMPRESSION is accepted generically (see prior observation path).
        return phase == SetupPhaseState.COMPRESSION
    return False
