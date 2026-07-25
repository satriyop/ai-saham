"""
RecordPreOpenObservationsUseCase — intentional write of pre-open session observations.

PreOpenWorkflowUseCase remains free of required persistence. Callers that need
canonical open_30m observations (research pre-open capture) go through
this use case.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.services.pre_open_observation_persister import (
        PreOpenObservationPersister,
    )
    from src.application.use_case.pre_open_workflow_use_case import (
        PreOpenWorkflowRequest,
        PreOpenWorkflowResponse,
        PreOpenWorkflowUseCase,
    )


@dataclass(frozen=True)
class RecordPreOpenObservationsResult:
    response: "PreOpenWorkflowResponse"
    recorded_count: int


class RecordPreOpenObservationsUseCase:
    """Run pre-open workflow, then save decision observations to the database."""

    def __init__(
        self,
        workflow_use_case: "PreOpenWorkflowUseCase",
        observation_persister: "PreOpenObservationPersister",
    ) -> None:
        self._workflow = workflow_use_case
        self._persister = observation_persister

    def execute(
        self, request: "PreOpenWorkflowRequest"
    ) -> RecordPreOpenObservationsResult:
        response = self._workflow.execute(request)
        count = self._persister.persist(response, request)
        return RecordPreOpenObservationsResult(
            response=response, recorded_count=count
        )

    def persist_only(
        self,
        response: "PreOpenWorkflowResponse",
        request: "PreOpenWorkflowRequest",
    ) -> int:
        """Save an already-built workflow response without re-running the screen."""
        return self._persister.persist(response, request)
