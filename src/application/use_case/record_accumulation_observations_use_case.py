"""
RecordAccumulationObservationsUseCase — the sole intentional entrypoint for
persisting accumulation-screen candidate observations.

AccumulationScreenUseCase.execute() is read-only. Callers that need canonical
observations recorded (explicit backfill/observation-generation commands) go
through this use case instead of relying on execute() as a side effect.
Ordinary manual `saham screen accum` runs, `--multi`, `screen compare`, and
`DailyBriefingUseCase` never construct this — they only call execute().

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.dto.accumulation_screen import (
        AccumulationScreenRequest,
        AccumulationScreenResponse,
    )
    from src.application.dto.signal_evidence_execution_context import (
        SignalEvidenceExecutionContext,
    )
    from src.application.services.accumulation_candidate_observation_persister import (
        AccumulationCandidateObservationPersister,
    )
    from src.application.use_case.accumulation_screen_use_case import AccumulationScreenUseCase


@dataclass(frozen=True)
class RecordAccumulationObservationsResult:
    response: "AccumulationScreenResponse"
    recorded_count: int


class RecordAccumulationObservationsUseCase:
    """Run the screen once, then persist its evaluated results canonically."""

    def __init__(
        self,
        screen_use_case: "AccumulationScreenUseCase",
        observation_persister: "AccumulationCandidateObservationPersister",
    ) -> None:
        self._screen_use_case = screen_use_case
        self._observation_persister = observation_persister

    def execute(
        self,
        request: "AccumulationScreenRequest",
        *,
        execution_context: "SignalEvidenceExecutionContext",
    ) -> RecordAccumulationObservationsResult:
        response = self._screen_use_case.execute(
            request,
            execution_context=execution_context,
        )
        recorded_count = self._observation_persister.persist(
            response.observation_candidates,
            response.screened_at,
            request,
            effective_session=execution_context.effective_session,
            observation_contract=execution_context.observation_contract,
            semantic_compatibility_id=execution_context.semantic_compatibility_id,
        )
        return RecordAccumulationObservationsResult(
            response=response, recorded_count=recorded_count
        )
