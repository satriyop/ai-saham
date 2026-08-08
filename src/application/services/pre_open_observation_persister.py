"""Persist pre-open session observations to CandidateObservationsRepository.

Reuse shared candidate_observations store with workflow=screen_pre_open and
observation_contract=pre-open-open-30m.v3 (ADR-048). Fail closed on write errors.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from src.application.services.pre_open_observation_payload import (
    PRE_OPEN_WORKFLOW,
    build_pre_open_observation_payload,
    compute_pre_open_config_hash,
    compute_pre_open_semantic_compatibility_id,
    derive_pre_open_screen_result,
)
from src.application.services.signal_engine_config import (
    PreOpenDirectionalBaselineConfig,
    SignalClassificationConfig,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LearningContractId,
    LearningObservation,
)
from src.domain.value_objects.pre_open_signal_evidence import AuctionNcpProvenance

if TYPE_CHECKING:
    from src.application.use_case.pre_open_workflow_use_case import (
        PreOpenWorkflowRequest,
        PreOpenWorkflowResponse,
    )
    from src.domain.ports.learning_artifact_repositories import (
        LearningObservationRepository,
    )


@dataclass(frozen=True)
class PreOpenPersistedObservation:
    """One observation row after capture persist (inserted or idempotent)."""

    observation_id: str
    ticker: str
    screen_result: str
    inserted: bool


@dataclass(frozen=True)
class PreOpenPersistResult:
    recorded_count: int
    observations: tuple[PreOpenPersistedObservation, ...]


class PreOpenObservationPersister:
    """Write observation payloads for every screened pre-open candidate."""

    def __init__(
        self,
        repository: "LearningObservationRepository | None",
        signal_config: PreOpenDirectionalBaselineConfig | None = None,
        classification_config: SignalClassificationConfig | None = None,
        *,
        producer_source_revision: str = "ai-saham@pre-open",
    ) -> None:
        self._repo = repository
        self._signal_config = signal_config or PreOpenDirectionalBaselineConfig()
        self._classification_config = classification_config or SignalClassificationConfig()
        revision = str(producer_source_revision or "").strip()
        if not revision:
            raise ValueError("producer_source_revision must be non-empty")
        self._producer_source_revision = revision

    def persist(
        self,
        response: "PreOpenWorkflowResponse",
        request: "PreOpenWorkflowRequest",
        *,
        captured_at: datetime | None = None,
    ) -> PreOpenPersistResult:
        """Save observations for this session. Returns IDs + insert counts. Fail closed."""
        if self._repo is None:
            return PreOpenPersistResult(recorded_count=0, observations=())
        candidates = response.result.candidates
        filter_rejects = list(response.filter_rejects or ())
        if not candidates and not filter_rejects:
            return PreOpenPersistResult(recorded_count=0, observations=())

        now = captured_at or datetime.now(tz=IDX_TIMEZONE)
        if now.tzinfo is None:
            now = now.replace(tzinfo=IDX_TIMEZONE)

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
                "Pre-open observation persistence requires a verified live source "
                "and proven collection window wholly inside the same-session "
                "08:56–08:58 NCP_LOCKED input phase."
            )
        decision_at = response.decision_at
        collection_started_at = response.collection_started_at
        decision_snapshot_ref = response.decision_snapshot_ref
        assert decision_at is not None
        assert collection_started_at is not None
        assert decision_snapshot_ref is not None
        config_hash = compute_pre_open_config_hash(
            signal_config=self._signal_config,
            classification_config=self._classification_config,
            iev_min=response.result.iev_min,
            top_n=request.config.top_n,
        )
        compat = compute_pre_open_semantic_compatibility_id(
            signal_config=self._signal_config,
            classification_config=self._classification_config,
            iev_min=response.result.iev_min,
            top_n=request.config.top_n,
        )

        observations: list[LearningObservation] = []
        capture_phase = response.capture_phase

        def _row(
            *,
            ticker: str,
            screen_result: str,
            candidate: object,
            sig: object | None,
            risk: object | None,
            trade: object | None,
        ) -> LearningObservation:
            payload = build_pre_open_observation_payload(
                ticker=ticker,
                snapshot_date=response.result.screened_date,
                captured_at=now,
                collection_started_at=collection_started_at,
                decision_at=decision_at,
                decision_snapshot_ref=decision_snapshot_ref,
                screen_result=screen_result,
                candidate=candidate,
                signal_summary=sig,
                risk_summary=risk,
                trade_setup=trade,
                capture_phase=capture_phase,
                source_status=response.source_status.value,
                source_snapshot_ref=response.source_snapshot_ref,
                iev_min=response.result.iev_min,
                market_regime=response.market_regime,
            )
            payload["observation_contract"] = LearningContractId.PRE_OPEN_OBSERVATION.value
            payload["provenance"] = {
                "workflow": PRE_OPEN_WORKFLOW,
                "config_hash": config_hash,
                "decision_at": decision_at.isoformat(),
                "collection_started_at": collection_started_at.isoformat(),
                "decision_snapshot_ref": decision_snapshot_ref,
            }
            return LearningObservation.create(
                purpose=AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
                policy_contract="pre_open_directional_baseline.v2",
                horizon_contract="open_30m",
                compatibility_id=str(compat),
                cutoff_at=decision_at,
                universe_id=f"iev:{response.result.screened_date.isoformat()}",
                window_id=f"{ticker}:{response.result.screened_date.isoformat()}",
                decision_payload=payload,
                captured_at=now,
                producer_source_revision=self._producer_source_revision,
            )

        for candidate in candidates:
            ticker = candidate.ticker
            sig = (
                response.signal_by_ticker.get(ticker)
                if response.signal_by_ticker is not None
                else None
            )
            risk = (
                response.risk_by_ticker.get(ticker) if response.risk_by_ticker is not None else None
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

        rows: list[PreOpenPersistedObservation] = []
        inserted_count = 0
        for observation in observations:
            inserted = bool(self._repo.add_observation(observation))
            if inserted:
                inserted_count += 1
            ticker = str(
                observation.decision_payload.get("ticker") or observation.window_id.split(":", 1)[0]
            ).upper()
            screen_result = str(observation.decision_payload.get("screen_result") or "")
            rows.append(
                PreOpenPersistedObservation(
                    observation_id=observation.observation_id,
                    ticker=ticker,
                    screen_result=screen_result,
                    inserted=inserted,
                )
            )
        return PreOpenPersistResult(
            recorded_count=inserted_count,
            observations=tuple(rows),
        )
