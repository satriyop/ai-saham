"""Sync immutable Stockbit IHSG trading-session calendar snapshots.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol, Sequence

from src.domain.ports.trading_session_calendar_repository import (
    TradingSessionCalendarSnapshotWriteRepository,
    TradingSessionCalendarSource,
)
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LabelAvailability,
    LearningContractId,
    LearningObservation,
    LearningOutcomeLabel,
)
from src.domain.value_objects.trading_session_calendar_snapshot import (
    validate_active_stockbit_calendar_snapshot,
)

_PATH_LABEL_CONTRACTS: tuple[LearningContractId, ...] = (
    LearningContractId.ACCUM_3D_LABEL,
    LearningContractId.ACCUM_10D_LABEL,
    LearningContractId.ACCUM_20D_LABEL,
)
_CURRENT_ACCUM_PAYLOAD_SCHEMA = 11


@dataclass(frozen=True)
class SyncTradingSessionCalendarRequest:
    coverage_start: date
    coverage_end: date
    captured_at: datetime | None = None


@dataclass(frozen=True)
class SyncTradingSessionCalendarResult:
    snapshot_id: str
    inserted: bool
    session_count: int
    coverage_start: date
    coverage_end: date
    no_op: bool = False
    no_op_reason: str | None = None


class SyncTradingSessionCalendarSnapshotUseCase:
    """Fetch → active-validate → persist one Stockbit calendar snapshot."""

    def __init__(
        self,
        *,
        source: TradingSessionCalendarSource,
        snapshots: TradingSessionCalendarSnapshotWriteRepository,
    ) -> None:
        self._source = source
        self._snapshots = snapshots

    def execute(
        self,
        request: SyncTradingSessionCalendarRequest,
    ) -> SyncTradingSessionCalendarResult:
        if request.coverage_start > request.coverage_end:
            raise ValueError("coverage_start must not be after coverage_end")
        snapshot = self._source.fetch_snapshot(
            request.coverage_start,
            request.coverage_end,
        )
        validate_active_stockbit_calendar_snapshot(snapshot)
        inserted = self._snapshots.add_snapshot(snapshot)
        return SyncTradingSessionCalendarResult(
            snapshot_id=snapshot.snapshot_id,
            inserted=inserted,
            session_count=len(snapshot.ordered_sessions),
            coverage_start=snapshot.coverage_start,
            coverage_end=snapshot.coverage_end,
        )


class _ObservationListPort(Protocol):
    def list_observations(
        self,
        purpose: AssessmentPurpose,
        *,
        compatibility_id: str | None = None,
    ) -> Sequence[LearningObservation]: ...


class _LabelListPort(Protocol):
    def list_labels(
        self,
        observation_ids: Sequence[str],
    ) -> Sequence[LearningOutcomeLabel]: ...


@dataclass(frozen=True)
class ResolveCalendarSyncCoverageRequest:
    end_date: date
    purpose: AssessmentPurpose = AssessmentPurpose.ACCUMULATION_DISCOVERY


@dataclass(frozen=True)
class ResolveCalendarSyncCoverageResult:
    coverage_start: date | None
    coverage_end: date | None
    eligible_observation_count: int
    no_op: bool
    no_op_reason: str | None = None


class ResolveTradingSessionCalendarSyncCoverageUseCase:
    """Coverage for cron sync: earliest unlabeled current-schema obs → end_date.

    Never includes legacy schema-9/10 cohorts. Never uses today + buffer.
    """

    def __init__(
        self,
        *,
        observations: _ObservationListPort,
        labels: _LabelListPort,
    ) -> None:
        self._observations = observations
        self._labels = labels

    def execute(
        self,
        request: ResolveCalendarSyncCoverageRequest,
    ) -> ResolveCalendarSyncCoverageResult:
        observations = tuple(self._observations.list_observations(request.purpose))
        current = [o for o in observations if _is_current_accum_payload(o)]
        if not current:
            return ResolveCalendarSyncCoverageResult(
                coverage_start=None,
                coverage_end=None,
                eligible_observation_count=0,
                no_op=True,
                no_op_reason="no_current_schema_observations",
            )
        obs_ids = [o.observation_id for o in current]
        labels = tuple(self._labels.list_labels(obs_ids))
        labeled: set[tuple[str, LearningContractId]] = {
            (lb.observation_id, lb.contract_id)
            for lb in labels
            if lb.contract_id in _PATH_LABEL_CONTRACTS
            and lb.availability in (LabelAvailability.AVAILABLE, LabelAvailability.UNAVAILABLE)
        }
        needing: list[date] = []
        for obs in current:
            for contract in _PATH_LABEL_CONTRACTS:
                if (obs.observation_id, contract) not in labeled:
                    needing.append(obs.cutoff_at.date())
                    break
        if not needing:
            return ResolveCalendarSyncCoverageResult(
                coverage_start=None,
                coverage_end=None,
                eligible_observation_count=len(current),
                no_op=True,
                no_op_reason="all_path_labels_terminal",
            )
        start = min(needing)
        end = request.end_date
        if start > end:
            return ResolveCalendarSyncCoverageResult(
                coverage_start=None,
                coverage_end=None,
                eligible_observation_count=len(current),
                no_op=True,
                no_op_reason="coverage_start_after_end",
            )
        return ResolveCalendarSyncCoverageResult(
            coverage_start=start,
            coverage_end=end,
            eligible_observation_count=len(current),
            no_op=False,
        )


def _is_current_accum_payload(obs: LearningObservation) -> bool:
    payload = obs.decision_payload
    if not isinstance(payload, dict):
        return False
    return payload.get("schema_version") == _CURRENT_ACCUM_PAYLOAD_SCHEMA
