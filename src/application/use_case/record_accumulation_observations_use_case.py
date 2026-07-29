"""
RecordAccumulationObservationsUseCase — screen + ADR-056 multi-window persist.

AccumulationScreenUseCase.execute() is read-only. Capture/backfill go through
this use case for multi-window session observations (ADR-056).

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
    """Run the screen (optionally multi-window) and persist session observations."""

    def __init__(
        self,
        screen_use_case: "AccumulationScreenUseCase",
        observation_persister: "AccumulationCandidateObservationPersister",
    ) -> None:
        self._screen_use_case = screen_use_case
        self._observation_persister = observation_persister

    def screen(
        self,
        request: "AccumulationScreenRequest",
        *,
        execution_context: "SignalEvidenceExecutionContext",
    ) -> "AccumulationScreenResponse":
        """Read-only screen for one window (no persistence)."""
        return self._screen_use_case.execute(
            request,
            execution_context=execution_context,
        )

    def execute(
        self,
        request: "AccumulationScreenRequest",
        *,
        execution_context: "SignalEvidenceExecutionContext",
    ) -> RecordAccumulationObservationsResult:
        """Backward-compatible single-window entry: screen only (no persist).

        ADR-056 capture must call ``persist_multi_window`` after screening
        all of 7/30/90. This method no longer writes observations so callers
        cannot accidentally reintroduce triple-row identity.
        """
        response = self.screen(request, execution_context=execution_context)
        return RecordAccumulationObservationsResult(response=response, recorded_count=0)

    def persist_multi_window(
        self,
        *,
        window_results: dict,
        snapshot_date,
        execution_context: "SignalEvidenceExecutionContext",
        universe_tickers: list[str],
        canonical_window: int = 7,
    ) -> int:
        """Persist merged session observations after all windows were screened."""
        return self._observation_persister.persist_session_multi_window(
            window_results=window_results,
            snapshot_date=snapshot_date,
            effective_session=execution_context.effective_session,
            observation_contract=execution_context.observation_contract,
            semantic_compatibility_id=execution_context.semantic_compatibility_id,
            universe_tickers=universe_tickers,
            canonical_window=canonical_window,
        )
