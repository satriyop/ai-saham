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
    def add_observation(self, artifact: LearningObservation) -> bool: ...

    def get_observation(self, observation_id: str) -> LearningObservation | None: ...

    def list_observations(
        self, purpose: AssessmentPurpose, *, compatibility_id: str | None = None
    ) -> Sequence[LearningObservation]: ...


class LearningTrackSnapshotRepository(Protocol):
    def add_track_snapshot(self, artifact: LearningTrackSnapshot) -> bool: ...

    def list_track_snapshots(
        self, observation_id: str
    ) -> Sequence[LearningTrackSnapshot]: ...


class LearningOutcomeLabelRepository(Protocol):
    def add_label(self, artifact: LearningOutcomeLabel) -> bool: ...

    def list_labels(
        self, observation_ids: Sequence[str]
    ) -> Sequence[LearningOutcomeLabel]: ...


class LearningEvaluationRepository(Protocol):
    def add_evaluation(self, artifact: LearningEvaluation) -> bool: ...

    def get_evaluation(self, evaluation_id: str) -> LearningEvaluation | None: ...

    def list_evaluations(
        self, purpose: AssessmentPurpose
    ) -> Sequence[LearningEvaluation]: ...


class LearningPolicyProposalRepository(Protocol):
    def add_proposal(self, artifact: LearningPolicyProposal) -> bool: ...

    def get_proposal(self, proposal_id: str) -> LearningPolicyProposal | None: ...

    def list_proposals(self) -> Sequence[LearningPolicyProposal]: ...


class LearningPolicyValidationRepository(Protocol):
    def add_validation(self, artifact: LearningPolicyValidation) -> bool: ...

    def get_validation_for_proposal(
        self, proposal_id: str
    ) -> LearningPolicyValidation | None: ...

    def list_validations(self) -> Sequence[LearningPolicyValidation]: ...


class LearningPolicyApplicationRepository(Protocol):
    def add_application(self, artifact: LearningPolicyApplication) -> bool: ...

    def get_application_for_proposal(
        self, proposal_id: str
    ) -> LearningPolicyApplication | None: ...

    def list_applications(self) -> Sequence[LearningPolicyApplication]: ...
