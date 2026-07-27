"""AnalyzePreOpenUseCase — post-open assessment of an NCP pre-open plan.

Reads immutable learning observations + linked track snapshots, reconstructs
PreOpenPostOpenCandidate rows, and applies PreOpenPostOpenGatesUseCase.

Does not write journals, sidecars, or live-fetch prices.

Layer: Application
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Sequence

from src.application.dto.analyze_pre_open import (
    AnalyzePreOpenAmbiguityError,
    AnalyzePreOpenContractError,
    AnalyzePreOpenLine,
    AnalyzePreOpenNotFoundError,
    AnalyzePreOpenRequest,
    AnalyzePreOpenResult,
    AnalyzePreOpenSnapshotError,
    AnalyzePreOpenStatus,
)
from src.application.services.pre_open_post_open_candidate_mapper import (
    extract_market_regime_label,
    extract_opening_price_from_track_payload,
    format_sampled_at_iso,
    project_pre_open_state,
    reconstruct_pre_open_post_open_candidate,
)
from src.application.services.pre_open_screen_config import PreOpenScreenConfig
from src.application.use_case.pre_open_post_open_gates_use_case import (
    PreOpenPostOpenGatesRequest,
    PreOpenPostOpenGatesUseCase,
)
from src.domain.ports.learning_artifact_repositories import (
    LearningObservationRepository,
    LearningTrackSnapshotRepository,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE, REGULAR_OPEN
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LearningContractId,
    LearningObservation,
    LearningTrackSnapshot,
)
from src.domain.value_objects.pre_open_post_open_assessment import (
    PreOpenPostOpenAssessment,
    PreOpenPostOpenCandidate,
    PreOpenPostOpenDecision,
)

_PRE_OPEN_PURPOSE = AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION
_PRE_OPEN_CONTRACT = LearningContractId.PRE_OPEN_OBSERVATION


class AnalyzePreOpenUseCase:
    """Database-identified post-open assess of pre-open plan(s)."""

    def __init__(
        self,
        observations: LearningObservationRepository,
        tracks: LearningTrackSnapshotRepository,
        *,
        pre_open_config: PreOpenScreenConfig | None = None,
        confirm_use_case: PreOpenPostOpenGatesUseCase | None = None,
        clock_date: date | None = None,
    ) -> None:
        self._observations = observations
        self._tracks = tracks
        self._config = pre_open_config or PreOpenScreenConfig()
        self._confirm = confirm_use_case or PreOpenPostOpenGatesUseCase()
        self._clock_date = clock_date

    def execute(self, request: AnalyzePreOpenRequest) -> AnalyzePreOpenResult:
        session = request.session_date or self._clock_date or date.today()
        selected = self._select_observations(request, session)
        if not selected:
            raise AnalyzePreOpenNotFoundError(
                f"No pre-open observations for session {session.isoformat()}"
            )

        regime_label, regime_warning = extract_market_regime_label(selected[0].decision_payload)
        warnings: list[str] = []
        if regime_warning:
            warnings.append(regime_warning)
            regime_label = "RISK_OFF"

        # Explicit snapshot only valid for a single observation target
        if request.opening_snapshot_id and len(selected) != 1:
            raise AnalyzePreOpenSnapshotError(
                "--opening-snapshot-id requires exactly one observation (pass --observation-id)"
            )

        lines: list[AnalyzePreOpenLine] = []
        candidates = []
        for obs in selected:
            line, candidate = self._build_line(
                obs,
                session=session,
                opening_snapshot_id=request.opening_snapshot_id,
            )
            lines.append(line)
            candidates.append(candidate)

        confirm_result = self._confirm.execute(
            PreOpenPostOpenGatesRequest(
                candidates=candidates,
                run_date=session,
                max_stop_pct=self._config.max_stop_pct,
                tick_friction_gate=self._config.tick_friction_gate,
                min_target_ticks=self._config.min_target_ticks,
                min_stop_ticks=self._config.min_stop_ticks,
                regime=regime_label,
                regime_gate_enabled=self._config.regime_gate_enabled,
                tighten_in_regimes=tuple(self._config.tighten_in_regimes),
                gap_pct_tightening_factor=Decimal(str(self._config.gap_pct_tightening_factor)),
                require_backed_in_weak=self._config.require_backed_in_weak,
            )
        )

        by_ticker = {c.ticker: c for c in confirm_result.confirmations}
        final_lines: list[AnalyzePreOpenLine] = []
        for line in lines:
            conf = by_ticker.get(line.ticker)
            if conf is None:
                # Should not happen; fail closed with insufficient data shape
                conf = line.confirmation
            final_lines.append(
                AnalyzePreOpenLine(
                    observation_id=line.observation_id,
                    opening_snapshot_id=line.opening_snapshot_id,
                    ticker=line.ticker,
                    pre_open=line.pre_open,
                    confirmation=conf,
                    price_provenance=line.price_provenance,
                    cutoff_at=line.cutoff_at,
                    compatibility_id=line.compatibility_id,
                    contract_id=line.contract_id,
                )
            )

        status = self._status(final_lines)
        return AnalyzePreOpenResult(
            session_date=session,
            status=status,
            market_regime=regime_label,
            max_stop_pct=confirm_result.max_stop_pct,
            lines=tuple(final_lines),
            warnings=tuple(warnings),
            policy_identity={
                "max_stop_pct": str(self._config.max_stop_pct),
                "tick_friction_gate": self._config.tick_friction_gate,
                "regime_gate_enabled": self._config.regime_gate_enabled,
                "tighten_in_regimes": list(self._config.tighten_in_regimes),
                "gap_pct_tightening_factor": self._config.gap_pct_tightening_factor,
                "require_backed_in_weak": self._config.require_backed_in_weak,
            },
        )

    def _select_observations(
        self,
        request: AnalyzePreOpenRequest,
        session: date,
    ) -> list[LearningObservation]:
        if request.observation_id:
            obs = self._observations.get_observation(request.observation_id)
            if obs is None:
                raise AnalyzePreOpenNotFoundError(
                    f"Observation not found: {request.observation_id}"
                )
            self._assert_pre_open_contract(obs)
            obs_session = obs.cutoff_at.astimezone(IDX_TIMEZONE).date()
            if request.session_date is not None and obs_session != request.session_date:
                raise AnalyzePreOpenContractError(
                    f"Observation session {obs_session.isoformat()} does not match "
                    f"--session {request.session_date.isoformat()}"
                )
            return [obs]

        rows = list(self._observations.list_observations(_PRE_OPEN_PURPOSE))
        session_rows = [o for o in rows if o.cutoff_at.astimezone(IDX_TIMEZONE).date() == session]
        for o in session_rows:
            self._assert_pre_open_contract(o)

        if not session_rows:
            return []

        compat_ids = {o.compatibility_id for o in session_rows}
        if len(compat_ids) > 1:
            raise AnalyzePreOpenAmbiguityError(
                "Multiple pre-open compatibility cohorts for session "
                f"{session.isoformat()}; pass --observation-id. "
                f"Found: {sorted(compat_ids)}"
            )
        return sorted(session_rows, key=lambda o: (o.window_id, o.observation_id))

    def _assert_pre_open_contract(self, obs: LearningObservation) -> None:
        if obs.purpose is not _PRE_OPEN_PURPOSE:
            raise AnalyzePreOpenContractError(
                f"Observation {obs.observation_id} purpose is {obs.purpose.value}, "
                f"expected {_PRE_OPEN_PURPOSE.value}"
            )
        if obs.contract_id is not _PRE_OPEN_CONTRACT:
            raise AnalyzePreOpenContractError(
                f"Observation {obs.observation_id} contract is {obs.contract_id.value}, "
                f"expected {_PRE_OPEN_CONTRACT.value}"
            )

    def _build_line(
        self,
        obs: LearningObservation,
        *,
        session: date,
        opening_snapshot_id: str | None,
    ) -> tuple[AnalyzePreOpenLine, PreOpenPostOpenCandidate]:
        snapshot = self._resolve_opening_snapshot(
            obs, session=session, opening_snapshot_id=opening_snapshot_id
        )
        price: Decimal | None = None
        source: str | None = None
        confidence: str | None = None
        snap_id: str | None = None
        sampled_at: datetime | None = None
        if snapshot is not None:
            snap_id = snapshot.snapshot_id
            sampled_at = snapshot.sampled_at
            price, source, confidence = extract_opening_price_from_track_payload(
                snapshot.snapshot_payload
            )

        ts = format_sampled_at_iso(sampled_at)
        candidate = reconstruct_pre_open_post_open_candidate(
            obs,
            opening_price=price,
            opening_price_source=source,
            opening_price_confidence=confidence,
            opening_price_timestamp=ts,
        )
        # Placeholder replaced after bulk PreOpenPostOpenGatesUseCase run.
        placeholder = PreOpenPostOpenAssessment(
            ticker=candidate.ticker,
            decision=PreOpenPostOpenDecision.SKIP_INSUFFICIENT_DATA,
            opening_price=candidate.opening_price,
            planned_entry=None,
            stop_loss_price=None,
            stop_pct=None,
            reasons=(),
        )
        line = AnalyzePreOpenLine(
            observation_id=obs.observation_id,
            opening_snapshot_id=snap_id,
            ticker=candidate.ticker,
            pre_open=project_pre_open_state(obs),
            confirmation=placeholder,
            price_provenance={
                "opening_price": str(price) if price is not None else None,
                "opening_price_source": source,
                "opening_price_confidence": confidence,
                "sampled_at": ts,
                "opening_snapshot_id": snap_id,
            },
            cutoff_at=obs.cutoff_at,
            compatibility_id=obs.compatibility_id,
            contract_id=obs.contract_id.value,
        )
        return line, candidate

    def _resolve_opening_snapshot(
        self,
        obs: LearningObservation,
        *,
        session: date,
        opening_snapshot_id: str | None,
    ) -> LearningTrackSnapshot | None:
        snaps: Sequence[LearningTrackSnapshot] = list(
            self._tracks.list_track_snapshots(obs.observation_id)
        )
        if opening_snapshot_id:
            matches = [s for s in snaps if s.snapshot_id == opening_snapshot_id]
            if not matches:
                # May belong to another observation — hard error
                raise AnalyzePreOpenSnapshotError(
                    f"Opening snapshot {opening_snapshot_id} is not linked to "
                    f"observation {obs.observation_id}"
                )
            return matches[0]

        open_window = [s for s in snaps if self._is_open_window_sample(s.sampled_at, session)]
        if not open_window:
            return None

        open_window.sort(key=lambda s: (s.sampled_at, s.snapshot_id))
        earliest_ts = open_window[0].sampled_at
        ties = [s for s in open_window if s.sampled_at == earliest_ts]
        if len(ties) > 1:
            raise AnalyzePreOpenSnapshotError(
                f"Ambiguous earliest open-window snapshots for "
                f"{obs.observation_id} at {earliest_ts.isoformat()}; "
                "pass --opening-snapshot-id"
            )
        return ties[0]

    @staticmethod
    def _is_open_window_sample(sampled_at: datetime, session: date) -> bool:
        local = sampled_at.astimezone(IDX_TIMEZONE)
        if local.date() != session:
            return False
        return local.timetz().replace(tzinfo=None) >= REGULAR_OPEN

    @staticmethod
    def _status(lines: Sequence[AnalyzePreOpenLine]) -> AnalyzePreOpenStatus:
        if not lines:
            return AnalyzePreOpenStatus.UNAVAILABLE_OPENING
        has_price = [line.price_provenance.get("opening_price") is not None for line in lines]
        if all(has_price):
            return AnalyzePreOpenStatus.OK
        if any(has_price):
            return AnalyzePreOpenStatus.PARTIAL
        return AnalyzePreOpenStatus.UNAVAILABLE_OPENING
