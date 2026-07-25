"""
RecordPreOpenObservationsUseCase — intentional write of pre-open session observations.

PreOpenWorkflowUseCase remains free of required persistence. Callers that need
canonical open_30m observations (research pre-open capture) go through
this use case.

Also writes a non-authority ops day export under data/opening/ when
opening_data_dir is provided (same-run packaging for track/briefing/prompt).

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from src.application.services.pre_open_ops_day_export import write_pre_open_ops_day_export

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
    ops_export_path: str | None = None


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
        *,
        opening_data_dir: Path | None = None,
    ) -> RecordPreOpenObservationsResult:
        response = self._workflow.execute(request)
        count = self._persister.persist(response, request)
        ops_path: str | None = None
        if opening_data_dir is not None:
            day_dir = opening_data_dir / response.result.screened_date.strftime(
                "%Y%m%d"
            )
            written = write_pre_open_ops_day_export(
                response,
                request,
                day_dir,
                recorded_count=count,
            )
            ops_path = str(written)
        return RecordPreOpenObservationsResult(
            response=response,
            recorded_count=count,
            ops_export_path=ops_path,
        )

    def persist_only(
        self,
        response: "PreOpenWorkflowResponse",
        request: "PreOpenWorkflowRequest",
    ) -> int:
        """Save an already-built workflow response without re-running the screen."""
        return self._persister.persist(response, request)
