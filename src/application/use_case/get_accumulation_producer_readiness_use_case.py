"""Read-only producer readiness for accumulation challenge corpus (P0).

Layer: Application. Projects per-cohort status from observations, labels, and
policy snapshots. Never writes or repairs data. Never contacts Stockbit.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from src.application.services.accumulation_producer_readiness import (
    ACTIVE_SNAPSHOT_BINDING_CONTRACT,
    CohortProducerReadiness,
    cohort_to_dict,
    project_cohort_readiness,
)
from src.domain.ports.learning_artifact_repositories import (
    LearningObservationRepository,
    LearningOutcomeLabelRepository,
    LearningPolicySnapshotRepository,
)
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LearningContractId,
    ProductionPolicySnapshot,
)
from src.domain.value_objects.signal_observation_contracts import (
    ACCUMULATION_DISCOVERY_OBSERVATION_CONTRACT,
)
from src.domain.value_objects.trading_session_calendar_snapshot import (
    TradingSessionCalendarSnapshot,
)

SessionSnapshotLookup = Callable[[str], TradingSessionCalendarSnapshot | None]


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
    add_* repository methods. Calendar snapshots are loaded by the exact IDs
    bound on labels — never "latest" and never a live Stockbit probe.
    """

    def __init__(
        self,
        *,
        observations: LearningObservationRepository,
        labels: LearningOutcomeLabelRepository,
        policy_snapshots: LearningPolicySnapshotRepository | _WriteRejectingPolicySnapshotPort,
        session_snapshot_lookup: SessionSnapshotLookup | None = None,
    ) -> None:
        self._observations = observations
        self._labels = labels
        self._policy_snapshots = policy_snapshots
        self._session_snapshot_lookup = session_snapshot_lookup

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
                    session_snapshot_lookup=self._session_snapshot_lookup,
                )
            )

        return AccumulationProducerReadinessReport(
            purpose=purpose,
            active_snapshot_binding_contract=ACTIVE_SNAPSHOT_BINDING_CONTRACT,
            observation_count=len(observations),
            cohort_count=len(cohorts),
            cohorts=tuple(cohorts),
        )
