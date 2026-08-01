"""Read-only producer readiness for accumulation challenge corpus (P0).

Layer: Application. Projects per-cohort status from observations, labels, and
policy snapshots. Never writes or repairs data.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Protocol, Sequence

from src.application.services.accumulation_producer_readiness import (
    CohortProducerReadiness,
    cohort_to_dict,
    parse_canonical_session_date,
    project_cohort_readiness,
)
from src.application.services.lean_observation_identity import (
    POLICY_SNAPSHOT_BINDING_CONTRACT_V2,
)
from src.domain.ports.learning_artifact_repositories import (
    LearningObservationRepository,
    LearningOutcomeLabelRepository,
    LearningPolicySnapshotRepository,
)
from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LabelAvailability,
    LearningContractId,
    LearningObservation,
    LearningOutcomeLabel,
    ProductionPolicySnapshot,
)
from src.domain.value_objects.signal_observation_contracts import (
    ACCUMULATION_DISCOVERY_OBSERVATION_CONTRACT,
)

SessionCalendarLoader = Callable[[date, date], KnownTradingSessionCalendar | None]


class _WriteRejectingPolicySnapshotPort(Protocol):
    def list_policy_snapshots(
        self,
        *,
        purpose: AssessmentPurpose,
        compatibility_id: str,
    ) -> Sequence[ProductionPolicySnapshot]: ...


@dataclass(frozen=True)
class AccumulationProducerReadinessReport:
    """Purpose-level readiness report with explicit per-cohort rows."""

    purpose: AssessmentPurpose
    active_snapshot_binding_contract: str
    observation_count: int
    cohort_count: int
    cohorts: tuple[CohortProducerReadiness, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": "accumulation_producer_readiness",
            "purpose": self.purpose.value,
            "active_snapshot_binding_contract": self.active_snapshot_binding_contract,
            "observation_count": self.observation_count,
            "cohort_count": self.cohort_count,
            "compatibility_ids": [c.compatibility_id for c in self.cohorts],
            "cohorts": [cohort_to_dict(c) for c in self.cohorts],
        }


def coverage_from_available_labels(
    labels: Sequence[LearningOutcomeLabel],
) -> tuple[date, date] | None:
    """Coverage for session-calendar load from AVAILABLE labels only.

    coverage_start = min signal_date; coverage_end = max label_window_end.
    No AVAILABLE labels → None (no calendar required yet; COLLECTING path).
    """
    starts: list[date] = []
    ends: list[date] = []
    for label in labels:
        if label.availability is not LabelAvailability.AVAILABLE:
            continue
        metrics = label.metrics if isinstance(label.metrics, Mapping) else {}
        signal = parse_canonical_session_date(metrics.get("signal_date"))
        win_end = parse_canonical_session_date(metrics.get("label_window_end"))
        if signal is None or win_end is None:
            continue
        starts.append(signal)
        ends.append(win_end)
    if not starts:
        return None
    return min(starts), max(ends)


class GetAccumulationProducerReadinessUseCase:
    """Project producer readiness for ACCUMULATION_DISCOVERY cohorts.

    Read-only: lists observations/labels/snapshots and classifies. Must not call
    add_* repository methods. Session calendar loaders must also be read-only.
    """

    def __init__(
        self,
        *,
        observations: LearningObservationRepository,
        labels: LearningOutcomeLabelRepository,
        policy_snapshots: LearningPolicySnapshotRepository | _WriteRejectingPolicySnapshotPort,
        session_calendar: KnownTradingSessionCalendar | None = None,
        session_calendar_loader: SessionCalendarLoader | None = None,
    ) -> None:
        self._observations = observations
        self._labels = labels
        self._policy_snapshots = policy_snapshots
        self._session_calendar = session_calendar
        self._session_calendar_loader = session_calendar_loader

    def execute(
        self,
        purpose: AssessmentPurpose = AssessmentPurpose.ACCUMULATION_DISCOVERY,
    ) -> AccumulationProducerReadinessReport:
        if purpose is not AssessmentPurpose.ACCUMULATION_DISCOVERY:
            raise ValueError(
                "GetAccumulationProducerReadinessUseCase only supports "
                f"{AssessmentPurpose.ACCUMULATION_DISCOVERY.value}, got {purpose.value}"
            )

        observations = tuple(self._observations.list_observations(purpose))
        labels = tuple(self._labels.list_labels([o.observation_id for o in observations]))

        by_compat: dict[str, list[LearningObservation]] = {}
        for obs in observations:
            key = obs.compatibility_id or ""
            by_compat.setdefault(key, []).append(obs)

        cohorts: list[CohortProducerReadiness] = []
        for compatibility_id in sorted(by_compat):
            cohort_obs = tuple(by_compat[compatibility_id])
            obs_ids = {o.observation_id for o in cohort_obs}
            cohort_labels = tuple(lb for lb in labels if lb.observation_id in obs_ids)
            # Per-cohort coverage from AVAILABLE labels only (never newest obs + 40d).
            session_calendar = self._resolve_session_calendar_for_labels(cohort_labels)
            if compatibility_id:
                snapshots = tuple(
                    self._policy_snapshots.list_policy_snapshots(
                        purpose=purpose,
                        compatibility_id=compatibility_id,
                    )
                )
            else:
                snapshots = ()
            cohorts.append(
                project_cohort_readiness(
                    compatibility_id=compatibility_id or "(missing)",
                    observations=cohort_obs,
                    labels=cohort_labels,
                    snapshots=snapshots,
                    purpose_value=purpose.value,
                    expected_learning_observation_contract_id=(
                        LearningContractId.ACCUMULATION_OBSERVATION.value
                    ),
                    expected_producer_observation_contract=(
                        ACCUMULATION_DISCOVERY_OBSERVATION_CONTRACT
                    ),
                    session_calendar=session_calendar,
                )
            )

        return AccumulationProducerReadinessReport(
            purpose=purpose,
            active_snapshot_binding_contract=POLICY_SNAPSHOT_BINDING_CONTRACT_V2,
            observation_count=len(observations),
            cohort_count=len(cohorts),
            cohorts=tuple(cohorts),
        )

    def _resolve_session_calendar_for_labels(
        self,
        labels: Sequence[LearningOutcomeLabel],
    ) -> KnownTradingSessionCalendar | None:
        if self._session_calendar is not None:
            return self._session_calendar
        if self._session_calendar_loader is None:
            return None
        coverage = coverage_from_available_labels(labels)
        if coverage is None:
            return None
        coverage_start, coverage_end = coverage
        return self._session_calendar_loader(coverage_start, coverage_end)
