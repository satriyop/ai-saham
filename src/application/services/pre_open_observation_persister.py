"""Persist pre-open session observations to CandidateObservationsRepository.

Reuse shared candidate_observations store with workflow=screen_pre_open and
observation_contract=pre-open-open-30m (ADR-048). Fail closed on write errors.

Layer: Application
"""

from __future__ import annotations

from datetime import datetime, time
from typing import TYPE_CHECKING

from src.application.services.pre_open_observation_payload import (
    PRE_OPEN_OBSERVATION_CONTRACT,
    PRE_OPEN_WORKFLOW,
    build_pre_open_observation_payload,
    compute_pre_open_config_hash,
    compute_pre_open_semantic_compatibility_id,
    derive_pre_open_screen_result,
)
from src.application.services.pre_open_signal_config import PreOpenSignalConfig
from src.domain.ports.candidate_observations_repository import CandidateObservation
from src.domain.value_objects.idx_market import IDX_TIMEZONE

if TYPE_CHECKING:
    from src.application.use_case.pre_open_workflow_use_case import (
        PreOpenWorkflowRequest,
        PreOpenWorkflowResponse,
    )
    from src.domain.ports.candidate_observations_repository import (
        CandidateObservationsRepository,
    )


class PreOpenObservationPersister:
    """Write observation payloads for every screened pre-open candidate."""

    def __init__(
        self,
        repository: "CandidateObservationsRepository | None",
        signal_config: PreOpenSignalConfig | None = None,
    ) -> None:
        self._repo = repository
        self._signal_config = signal_config or PreOpenSignalConfig()

    def persist(
        self,
        response: "PreOpenWorkflowResponse",
        request: "PreOpenWorkflowRequest",
        *,
        captured_at: datetime | None = None,
    ) -> int:
        """Save observations for this session. Returns count written. Fail closed."""
        if self._repo is None:
            return 0
        candidates = response.result.candidates
        filter_rejects = list(response.filter_rejects or ())
        if not candidates and not filter_rejects:
            return 0

        if self._signal_config.rendering not in ("cascade", "composite"):
            raise ValueError(f"invalid signal rendering {self._signal_config.rendering!r}")

        now = captured_at or datetime.now(tz=IDX_TIMEZONE)
        if now.tzinfo is None:
            now = now.replace(tzinfo=IDX_TIMEZONE)

        # NCP symbolic decision clock when capture is locked; else wall clock.
        if request.capture_phase == "NCP_LOCKED" or (
            response.source_status.value == "SNAPSHOT_SUCCESS"
        ):
            decision_at = datetime.combine(
                response.result.screened_date, time(8, 57), tzinfo=IDX_TIMEZONE
            )
        else:
            decision_at = now
        config_hash = compute_pre_open_config_hash(
            signal_config=self._signal_config,
            iev_min=response.result.iev_min,
            top_n=request.config.top_n,
        )
        compat = compute_pre_open_semantic_compatibility_id(
            signal_config=self._signal_config,
            iev_min=response.result.iev_min,
            top_n=request.config.top_n,
        )

        observations: list[CandidateObservation] = []
        capture_phase = (
            request.capture_phase
            if request.capture_phase != "UNKNOWN"
            else (
                "NCP_LOCKED"
                if response.source_status.value == "SNAPSHOT_SUCCESS"
                else "UNKNOWN"
            )
        )

        def _row(
            *,
            ticker: str,
            screen_result: str,
            candidate: object,
            sig: object | None,
            risk: object | None,
            trade: object | None,
        ) -> CandidateObservation:
            payload = build_pre_open_observation_payload(
                ticker=ticker,
                snapshot_date=response.result.screened_date,
                captured_at=now,
                screen_result=screen_result,
                candidate=candidate,
                signal_summary=sig,
                risk_summary=risk,
                trade_setup=trade,
                capture_phase=capture_phase,
                source_status=response.source_status.value,
                source_snapshot_ref=response.source_snapshot_ref,
                iev_min=response.result.iev_min,
            )
            return CandidateObservation(
                ticker=ticker,
                snapshot_date=response.result.screened_date,
                captured_at=now,
                payload=payload,
                workflow=PRE_OPEN_WORKFLOW,
                window_sessions=0,
                data_as_of_date=response.result.screened_date,
                config_hash=config_hash,
                decision_at=decision_at,
                latest_completed_session=response.result.screened_date,
                analysis_as_of=response.result.screened_date,
                market_session_name="pre_open",
                observation_contract=PRE_OPEN_OBSERVATION_CONTRACT,
                semantic_compatibility_id=compat,
            )

        for candidate in candidates:
            ticker = candidate.ticker
            sig = (
                response.signal_by_ticker.get(ticker)
                if response.signal_by_ticker is not None
                else None
            )
            risk = (
                response.risk_by_ticker.get(ticker)
                if response.risk_by_ticker is not None
                else None
            )
            trade = (
                response.trade_setup_by_ticker.get(ticker)
                if response.trade_setup_by_ticker is not None
                else None
            )
            screen_result = derive_pre_open_screen_result(
                has_entry_range=candidate.entry_range_low is not None,
                signal_summary=sig,
                trade_setup=trade,
            )
            observations.append(
                _row(
                    ticker=ticker,
                    screen_result=screen_result,
                    candidate=candidate,
                    sig=sig,
                    risk=risk,
                    trade=trade,
                )
            )

        # Hard-filter rejects (negative samples; no signal/risk)
        for rej in filter_rejects:
            stub = {
                "ticker": rej.ticker,
                "iev": rej.iev,
                "filter_reason": rej.reason,
            }
            observations.append(
                _row(
                    ticker=rej.ticker,
                    screen_result=rej.screen_result,
                    candidate=stub,
                    sig=None,
                    risk=None,
                    trade=None,
                )
            )

        # Fail closed: save_many errors propagate
        self._repo.save_many(observations)
        return len(observations)
