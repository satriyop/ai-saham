"""Ports for immutable database-owned learning artifacts."""

from __future__ import annotations

from typing import Protocol, Sequence

from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LearningEvaluation,
    LearningObservation,
    LearningOutcomeLabel,
    LearningPolicyApplication,
    LearningPolicyProposal,
    LearningPolicyValidation,
    LearningTrackSnapshot,
)


class LearningObservationRepository(Protocol):
    def add(self, artifact: LearningObservation) -> bool: ...

    def get(self, observation_id: str) -> LearningObservation | None: ...

    def list_for_purpose(
        self, purpose: AssessmentPurpose, *, compatibility_id: str | None = None
    ) -> Sequence[LearningObservation]: ...


class LearningTrackSnapshotRepository(Protocol):
    def add(self, artifact: LearningTrackSnapshot) -> bool: ...

    def list_for_observation(self, observation_id: str) -> Sequence[LearningTrackSnapshot]: ...


class LearningOutcomeLabelRepository(Protocol):
    def add(self, artifact: LearningOutcomeLabel) -> bool: ...

    def list_for_observations(
        self, observation_ids: Sequence[str]
    ) -> Sequence[LearningOutcomeLabel]: ...


class LearningEvaluationRepository(Protocol):
    def add(self, artifact: LearningEvaluation) -> bool: ...

    def get(self, evaluation_id: str) -> LearningEvaluation | None: ...

    def list_for_purpose(self, purpose: AssessmentPurpose) -> Sequence[LearningEvaluation]: ...


class LearningPolicyProposalRepository(Protocol):
    def add(self, artifact: LearningPolicyProposal) -> bool: ...

    def get(self, proposal_id: str) -> LearningPolicyProposal | None: ...


class LearningPolicyValidationRepository(Protocol):
    def add(self, artifact: LearningPolicyValidation) -> bool: ...

    def get_for_proposal(self, proposal_id: str) -> LearningPolicyValidation | None: ...


class LearningPolicyApplicationRepository(Protocol):
    def add(self, artifact: LearningPolicyApplication) -> bool: ...

    def get_for_proposal(self, proposal_id: str) -> LearningPolicyApplication | None: ...

