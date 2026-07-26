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

from src.domain.value_objects.pre_open_signal_evidence import AuctionNcpProvenance

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
        self,
        request: "PreOpenWorkflowRequest",
    ) -> RecordPreOpenObservationsResult:
        response = self._workflow.execute(request)
        provenance = AuctionNcpProvenance(
            ticker="CAPTURE",
            collection_started_at=response.collection_started_at,
            decision_at=response.decision_at,
            capture_phase=response.capture_phase,
            source_is_live=response.source_is_live,
            snapshot_ref=response.decision_snapshot_ref,
            trade_date=response.result.screened_date,
        )
        if not provenance.is_production_ncp:
            raise ValueError(
                "Pre-open decision capture requires a verified live source, a "
                "timezone-aware collection window wholly inside the requested "
                "session's 08:56–08:58 NCP_LOCKED input phase, and a snapshot "
                "reference."
            )
        count = self._persister.persist(response, request)
        return RecordPreOpenObservationsResult(
            response=response,
            recorded_count=count,
        )

    def persist_only(
        self,
        response: "PreOpenWorkflowResponse",
        request: "PreOpenWorkflowRequest",
    ) -> int:
        """Save an already-built workflow response without re-running the screen."""
        return self._persister.persist(response, request)
