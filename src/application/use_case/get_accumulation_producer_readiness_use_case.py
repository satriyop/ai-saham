"""Read-only producer readiness for accumulation challenge corpus (P0).

Layer: Application. Projects per-cohort status from observations, labels, and
policy snapshots. Never writes or repairs data.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Protocol, Sequence

from src.application.services.accumulation_producer_readiness import (
    CohortProducerReadiness,
    bound_economic_session,
    cohort_to_dict,
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
    LearningContractId,
    LearningObservation,
    ProductionPolicySnapshot,
)
from src.domain.value_objects.signal_observation_contracts import (
    ACCUMULATION_DISCOVERY_OBSERVATION_CONTRACT,
)

# H20 horizon + weekend slack so first-N proof can reach label endpoints.
_SESSION_CALENDAR_FORWARD_BUFFER_DAYS = 40

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


class GetAccumulationProducerReadinessUseCase:
    """Project producer readiness for ACCUMULATION_DISCOVERY cohorts.

    Read-only: lists observations/labels/snapshots and classifies. Must not call
    add_* repository methods.
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
        # Authoritative market sessions for path-label window proof (fail closed
        # when absent — never fall back to weekday-length arithmetic).
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
        session_calendar = self._resolve_session_calendar(observations)

        by_compat: dict[str, list] = {}
        for obs in observations:
            key = obs.compatibility_id or ""
            by_compat.setdefault(key, []).append(obs)

        cohorts: list[CohortProducerReadiness] = []
        for compatibility_id in sorted(by_compat):
            cohort_obs = tuple(by_compat[compatibility_id])
            obs_ids = {o.observation_id for o in cohort_obs}
            cohort_labels = tuple(lb for lb in labels if lb.observation_id in obs_ids)
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

    def _resolve_session_calendar(
        self,
        observations: Sequence[LearningObservation],
    ) -> KnownTradingSessionCalendar | None:
        """Prefer an explicit calendar; else load a proven span covering labels."""
        if self._session_calendar is not None:
            return self._session_calendar
        if self._session_calendar_loader is None or not observations:
            return None
        sessions: list[date] = []
        for obs in observations:
            bound = bound_economic_session(obs)
            if bound is not None:
                sessions.append(bound[1])
        if not sessions:
            return None
        coverage_start = min(sessions)
        coverage_end = max(sessions) + timedelta(days=_SESSION_CALENDAR_FORWARD_BUFFER_DAYS)
        return self._session_calendar_loader(coverage_start, coverage_end)
