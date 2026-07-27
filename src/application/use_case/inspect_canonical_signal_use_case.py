"""Read-only canonical SignalEngine inspection (DQ-007 lean).

Reuses the accumulation-flow screen path (same assessor →
``CanonicalSignalEvidenceInput`` → contextual ``SignalEngine`` policy).
Does not persist. Does not invent a parallel scorer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol

from src.application.dto.inspect_canonical_signal import (
    InspectCanonicalSignalContract,
    InspectCanonicalSignalRequest,
    InspectCanonicalSignalResponse,
    InspectCanonicalSignalStatus,
    InspectEffectiveSessionView,
)
from src.application.dto.signal_evidence_execution_context import (
    SignalEvidenceExecutionContext,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE, MARKET_CLOSE

_FLOW_ONLY_NOTE = (
    "contract=accumulation-flow: setup evidence is intentionally absent "
    "(same boundary as the accumulation screen assessor)."
)
_READ_ONLY_NOTE = "Read-only inspection: no observation, label, tuning, or promotion writes."
_PROVISIONAL_CLI_NOTE = (
    "CLI surface: saham inspect signal accum "
    "(accumulation-flow contract only; not pre-open or swing TradeSetup)."
)
_LEGACY_NOTE = (
    "legacy_conditioned_score is regime conditioning on the canonical path, "
    "not the retired six-factor score."
)


class ScreenRequestBuilder(Protocol):
    def build(
        self,
        *,
        tickers: list[str],
        window_days: int,
        as_of_date: date | None = None,
        market_context: Any = None,
    ) -> Any: ...


class AccumulationScreenRunner(Protocol):
    def execute(
        self,
        request: Any,
        *,
        execution_context: SignalEvidenceExecutionContext,
    ) -> Any: ...


class SessionResolver(Protocol):
    def resolve(self, *, run_at: datetime) -> EffectiveMarketSession: ...


@dataclass
class InspectCanonicalSignalUseCase:
    """Explain live canonical scoring for one ticker at an effective session."""

    screen_use_case: AccumulationScreenRunner
    screen_request_builder: ScreenRequestBuilder
    session_resolver: SessionResolver

    def execute(self, request: InspectCanonicalSignalRequest) -> InspectCanonicalSignalResponse:
        ticker = request.ticker.strip().upper()
        if not ticker:
            return InspectCanonicalSignalResponse(
                status=InspectCanonicalSignalStatus.ERROR,
                contract=request.contract,
                ticker="",
                as_of_date=request.as_of_date or date.today(),
                reasons=("ticker_required",),
                notes=(_READ_ONLY_NOTE,),
            )
        if request.contract is not InspectCanonicalSignalContract.ACCUMULATION_FLOW:
            return InspectCanonicalSignalResponse(
                status=InspectCanonicalSignalStatus.ERROR,
                contract=request.contract,
                ticker=ticker,
                as_of_date=request.as_of_date or date.today(),
                reasons=(f"unsupported_contract:{request.contract.value}",),
                notes=(_READ_ONLY_NOTE, _PROVISIONAL_CLI_NOTE),
            )
        if request.window_days < 1:
            return InspectCanonicalSignalResponse(
                status=InspectCanonicalSignalStatus.ERROR,
                contract=request.contract,
                ticker=ticker,
                as_of_date=request.as_of_date or date.today(),
                reasons=("window_days_must_be_positive",),
                notes=(_READ_ONLY_NOTE,),
            )

        as_of = request.as_of_date or date.today()
        effective_session = self.session_resolver.resolve(
            run_at=datetime.combine(as_of, MARKET_CLOSE, tzinfo=IDX_TIMEZONE)
        )
        session_view = _session_view(effective_session)
        pit_as_of = effective_session.analysis_as_of
        notes = (
            _FLOW_ONLY_NOTE,
            _READ_ONLY_NOTE,
            _PROVISIONAL_CLI_NOTE,
            _LEGACY_NOTE,
            f"point_in_time analysis_as_of={pit_as_of.isoformat()}",
        )

        screen_request = self.screen_request_builder.build(
            tickers=[ticker],
            window_days=int(request.window_days),
            as_of_date=pit_as_of,
        )
        context = SignalEvidenceExecutionContext(
            effective_session=effective_session,
            source_availability_use_case=None,
        )
        try:
            screen_response = self.screen_use_case.execute(
                screen_request, execution_context=context
            )
        except Exception as exc:  # noqa: BLE001 — map to UNAVAILABLE reason
            return InspectCanonicalSignalResponse(
                status=InspectCanonicalSignalStatus.UNAVAILABLE,
                contract=request.contract,
                ticker=ticker,
                as_of_date=pit_as_of,
                effective_session=session_view,
                reasons=(f"missing_local_source_data:{type(exc).__name__}",),
                notes=notes,
            )

        observation = _find_observation_candidate(
            getattr(screen_response, "observation_candidates", ()) or (),
            ticker,
        )
        candidate = None if observation is None else observation.candidate
        if candidate is None:
            # Fall back to primary candidates list if observation bag empty.
            for row in getattr(screen_response, "candidates", ()) or ():
                if getattr(row, "ticker", "").upper() == ticker:
                    candidate = row
                    break

        if candidate is None or candidate.signal_assessment is None:
            return InspectCanonicalSignalResponse(
                status=InspectCanonicalSignalStatus.UNAVAILABLE,
                contract=request.contract,
                ticker=ticker,
                as_of_date=pit_as_of,
                effective_session=session_view,
                screen_result=(None if observation is None else observation.screen_result),
                reasons=("missing_local_source_data",),
                notes=notes,
            )

        screen_result = None if observation is None else observation.screen_result
        return InspectCanonicalSignalResponse(
            status=InspectCanonicalSignalStatus.OK,
            contract=request.contract,
            ticker=ticker,
            as_of_date=pit_as_of,
            effective_session=session_view,
            assessment=candidate.signal_assessment,
            screen_result=screen_result,
            notes=notes,
        )


def _session_view(session: EffectiveMarketSession) -> InspectEffectiveSessionView:
    return InspectEffectiveSessionView(
        run_at=session.run_at,
        decision_at=session.decision_at,
        latest_completed_session=session.latest_completed_session,
        analysis_as_of=session.analysis_as_of,
        market_session_name=session.market_session_name,
        is_eod_pending=session.is_eod_pending,
        resolution_source=session.resolution_source,
        notes=tuple(session.notes),
    )


def _find_observation_candidate(rows: Any, ticker: str) -> Any | None:
    target = ticker.upper()
    for row in rows:
        candidate = getattr(row, "candidate", None)
        if candidate is not None and getattr(candidate, "ticker", "").upper() == target:
            return row
    return None
