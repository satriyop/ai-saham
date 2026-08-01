"""Database-owned accumulation and pre-open label/evaluation lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from statistics import mean
from typing import Any, Protocol, Sequence

from src.domain.ports.learning_artifact_repositories import (
    LearningEvaluationRepository,
    LearningObservationRepository,
    LearningOutcomeLabelRepository,
    LearningTrackSnapshotRepository,
)
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    EvaluationMethod,
    EvaluationReadiness,
    LabelAvailability,
    LearningContractError,
    LearningContractId,
    LearningEvaluation,
    LearningObservation,
    LearningOutcomeLabel,
    OutcomeBasis,
    artifact_digest,
)
from src.domain.value_objects.trading_session_calendar_snapshot import (
    PATH_LABEL_METRICS_SCHEMA_VERSION,
    TradingSessionCalendarSnapshot,
    label_window_digest,
)


class LearningMarketDataRepository(Protocol):
    def get_candles(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> Sequence[Any]: ...


class LearningCorporateActionCalendarRepository(Protocol):
    def has_any_sync_marker(self) -> bool: ...

    def get_events_for_ticker(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
        *,
        event_types: Sequence[Any],
    ) -> Sequence[Any]: ...


@dataclass(frozen=True)
class GenerateLearningLabelsRequest:
    purpose: AssessmentPurpose
    compatibility_id: str
    label_contract: LearningContractId
    labeled_at: datetime


@dataclass(frozen=True)
class GenerateLearningLabelsResult:
    observation_count: int
    inserted_count: int
    idempotent_count: int
    unavailable_count: int
    labels: tuple[LearningOutcomeLabel, ...]
    # Observations not labeled yet (horizon/coverage/entry not ready). No row written.
    skipped_count: int = 0
    # Same label_id already stored with a different digest (legacy / clock clash).
    # Batch continues; first write remains authority.
    conflict_count: int = 0
    conflict_label_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvaluateLearningCohortRequest:
    purpose: AssessmentPurpose
    compatibility_id: str
    evaluated_at: datetime
    split_contract: str = "chronological_sessions.v1"


@dataclass(frozen=True)
class LearningStatus:
    purpose: AssessmentPurpose
    observation_count: int
    label_count: int
    available_label_count: int
    evaluation_count: int
    compatibility_ids: tuple[str, ...]


_HORIZON_DAYS = {
    LearningContractId.ACCUM_3D_LABEL: 3,
    LearningContractId.ACCUM_10D_LABEL: 10,
    LearningContractId.ACCUM_20D_LABEL: 20,
}

# Primary path grade for ACCUMULATION_DISCOVERY (ADR-056).
ACCUM_PRIMARY_LABEL_CONTRACT = LearningContractId.ACCUM_10D_LABEL

# All accum path label contracts (for CLI --all-label-contracts / cron).
ACCUM_PATH_LABEL_CONTRACTS: tuple[LearningContractId, ...] = (
    LearningContractId.ACCUM_3D_LABEL,
    LearningContractId.ACCUM_10D_LABEL,
    LearningContractId.ACCUM_20D_LABEL,
)


def _observation_ticker(observation: LearningObservation) -> str:
    ticker = observation.decision_payload.get("ticker")
    if not isinstance(ticker, str) or not ticker.strip():
        raise LearningContractError("learning observation decision payload requires ticker")
    return ticker.strip().upper()


def _observation_ids_with_contract(
    labels: LearningOutcomeLabelRepository,
    observation_ids: Sequence[str],
    contract_id: LearningContractId,
) -> set[str]:
    """Return observation ids that already have a terminal label for contract_id."""
    if not observation_ids:
        return set()
    return {
        label.observation_id
        for label in labels.list_labels(observation_ids)
        if label.contract_id == contract_id
    }


def _try_add_label(
    labels: LearningOutcomeLabelRepository,
    label: LearningOutcomeLabel,
    *,
    conflicts: list[str],
) -> bool:
    """Insert label; on immutable digest conflict, record and continue (no raise)."""
    try:
        return labels.add_label(label)
    except LearningContractError as exc:
        message = str(exc)
        if "immutable artifact conflict" not in message:
            raise
        conflicts.append(label.label_id)
        return False


def _entry_reference(payload: dict[str, Any] | Any) -> Decimal | None:
    """Signal-day entry for accumulation price-path labels (ADR-056).

    Authority order:
    1. ``shared.current_price`` (v2 session observation — preferred)
    2. ``candidate.current_price`` (legacy single-window payload; tests only until purge)
    """
    if not isinstance(payload, dict):
        return None
    shared = payload.get("shared")
    if isinstance(shared, dict):
        raw = shared.get("current_price")
        if raw is not None:
            try:
                value = Decimal(str(raw))
            except Exception:
                value = None
            else:
                if value is not None and value > 0:
                    return value
    candidate = payload.get("candidate")
    if isinstance(candidate, dict):
        raw = candidate.get("current_price")
        if raw is not None:
            try:
                value = Decimal(str(raw))
            except Exception:
                return None
            if value > 0:
                return value
    return None


def _pct_change(value: Any, base: Decimal) -> float:
    return round((float(value) - float(base)) / float(base) * 100.0, 6)


class GenerateAccumulationPricePathLabelsUseCase:
    """Generate immutable forward price-path labels from saved observations.

    Terminal labels only are persisted:
    - AVAILABLE outcomes (SUCCESS/FAILURE/NEUTRAL)
    - UNAVAILABLE when a mechanical corporate action invalidates the window

    Provisional conditions (missing entry, incomplete horizon, missing session
    calendar, missing ticker candle on a market session, missing corporate-action
    coverage) skip without writing a row so a later run can insert the terminal
    label when data is ready.

    Session axis: bind each AVAILABLE window to an immutable
    TradingSessionCalendarSnapshot (same identity readiness reloads by ID).
    First N market sessions after signal; one ticker candle required per exact
    session date — never skip a hole to a later ticker candle.
    """

    def __init__(
        self,
        *,
        observations: LearningObservationRepository,
        labels: LearningOutcomeLabelRepository,
        market_data: LearningMarketDataRepository,
        corporate_actions: LearningCorporateActionCalendarRepository,
        session_snapshot: TradingSessionCalendarSnapshot | None = None,
        session_snapshot_resolver: (
            Callable[[date, int], TradingSessionCalendarSnapshot | None] | None
        ) = None,
    ) -> None:
        self._observations = observations
        self._labels = labels
        self._market = market_data
        self._corporate_actions = corporate_actions
        self._session_snapshot = session_snapshot
        self._session_snapshot_resolver = session_snapshot_resolver

    def execute(self, request: GenerateLearningLabelsRequest) -> GenerateLearningLabelsResult:
        if request.purpose is not AssessmentPurpose.ACCUMULATION_DISCOVERY:
            raise LearningContractError("accumulation label generator received wrong purpose")
        horizon_days = _HORIZON_DAYS.get(request.label_contract)
        if horizon_days is None:
            raise LearningContractError("unsupported accumulation label contract")
        observations = tuple(
            self._observations.list_observations(
                request.purpose,
                compatibility_id=request.compatibility_id,
            )
        )
        already_labeled = _observation_ids_with_contract(
            self._labels,
            [observation.observation_id for observation in observations],
            request.label_contract,
        )
        labels: list[LearningOutcomeLabel] = []
        inserted = 0
        unavailable = 0
        skipped = 0
        conflicts: list[str] = []
        coverage_available = self._corporate_actions.has_any_sync_marker()
        for observation in observations:
            if observation.observation_id in already_labeled:
                # First write wins; re-runs must not rewrite terminal labels.
                skipped += 1
                continue
            label = self._label_one(
                observation,
                contract_id=request.label_contract,
                horizon_days=horizon_days,
                labeled_at=request.labeled_at,
                coverage_available=coverage_available,
            )
            if label is None:
                skipped += 1
                continue
            labels.append(label)
            if label.availability is LabelAvailability.UNAVAILABLE:
                unavailable += 1
            if _try_add_label(self._labels, label, conflicts=conflicts):
                inserted += 1
        conflict_ids = tuple(conflicts)
        return GenerateLearningLabelsResult(
            observation_count=len(observations),
            inserted_count=inserted,
            idempotent_count=max(0, len(labels) - inserted - len(conflict_ids)),
            unavailable_count=unavailable,
            skipped_count=skipped,
            labels=tuple(labels),
            conflict_count=len(conflict_ids),
            conflict_label_ids=conflict_ids,
        )

    def _label_one(
        self,
        observation: LearningObservation,
        *,
        contract_id: LearningContractId,
        horizon_days: int,
        labeled_at: datetime,
        coverage_available: bool,
    ) -> LearningOutcomeLabel | None:
        ticker = _observation_ticker(observation)
        signal_date = observation.cutoff_at.date()
        entry = _entry_reference(dict(observation.decision_payload))
        fingerprint_payload = {
            "observation_id": observation.observation_id,
            "decision_digest": observation.artifact_digest,
            "label_contract": contract_id,
        }
        fingerprint = artifact_digest(fingerprint_payload)
        if entry is None:
            # Provisional: capture bug or incomplete payload — do not lock a row.
            return None
        if not coverage_available:
            # Provisional: corporate-action calendar may appear later.
            return None
        snapshot = self._resolve_session_snapshot(signal_date, horizon_days)
        if snapshot is None:
            # Provisional: no immutable calendar snapshot covers this horizon.
            return None
        expected_sessions = snapshot.first_n_sessions_after(signal_date, horizon_days)
        if expected_sessions is None:
            # Provisional: insufficient proven market sessions after signal.
            return None
        candles = self._market.get_candles(
            ticker,
            start_date=expected_sessions[0],
            end_date=expected_sessions[-1],
        )
        by_date = {c.date: c for c in candles}
        window: list[Any] = []
        for session in expected_sessions:
            candle = by_date.get(session)
            if candle is None:
                # Missing ticker candle on a valid market session: provisional.
                # Do not skip forward to a later candle.
                return None
            window.append(candle)
        if self._has_mechanical_corporate_action(
            ticker, expected_sessions[0], expected_sessions[-1]
        ):
            return self._unavailable(
                observation,
                contract_id,
                fingerprint,
                labeled_at,
                "corporate_action_in_window",
            )
        close_return = _pct_change(window[-1].close, entry)
        high_returns = [_pct_change(candle.high, entry) for candle in window]
        low_returns = [_pct_change(candle.low, entry) for candle in window]
        max_forward = max(high_returns)
        max_adverse = min(low_returns)
        if max_adverse <= -5.0:
            outcome = "FAILURE"
        elif close_return >= 3.0 or max_forward >= 5.0:
            outcome = "SUCCESS"
        elif close_return <= -2.0:
            outcome = "FAILURE"
        else:
            outcome = "NEUTRAL"
        session_isos = [session.isoformat() for session in expected_sessions]
        contract_value = (
            contract_id.value if isinstance(contract_id, LearningContractId) else str(contract_id)
        )
        window_digest = label_window_digest(
            calendar_snapshot_id=snapshot.snapshot_id,
            label_contract_id=contract_value,
            signal_date=signal_date,
            sessions=expected_sessions,
        )
        metrics = {
            "ticker": ticker,
            "signal_date": signal_date.isoformat(),
            "label_window_start": expected_sessions[0].isoformat(),
            "label_window_end": expected_sessions[-1].isoformat(),
            "label_window_sessions": session_isos,
            "calendar_snapshot_id": snapshot.snapshot_id,
            "calendar_contract_id": snapshot.contract_id,
            "calendar_source_revision": snapshot.source_revision,
            "label_window_digest": window_digest,
            "path_label_metrics_schema_version": PATH_LABEL_METRICS_SCHEMA_VERSION,
            "entry_reference_price": float(entry),
            "close_return_pct": close_return,
            "max_forward_return_pct": max_forward,
            "max_adverse_excursion_pct": max_adverse,
            "days_to_peak": high_returns.index(max_forward) + 1,
            "days_to_trough": low_returns.index(max_adverse) + 1,
        }
        return LearningOutcomeLabel.create(
            contract_id=contract_id,
            observation_id=observation.observation_id,
            outcome_basis=OutcomeBasis.PRICE_PATH_ONLY,
            availability=LabelAvailability.AVAILABLE,
            outcome=outcome,
            metrics=metrics,
            fingerprint=fingerprint,
            labeled_at=labeled_at,
        )

    def _resolve_session_snapshot(
        self,
        signal_date: date,
        horizon_days: int,
    ) -> TradingSessionCalendarSnapshot | None:
        if self._session_snapshot is not None:
            if self._session_snapshot.first_n_sessions_after(signal_date, horizon_days) is None:
                return None
            return self._session_snapshot
        if self._session_snapshot_resolver is not None:
            return self._session_snapshot_resolver(signal_date, horizon_days)
        return None

    def _has_mechanical_corporate_action(self, ticker: str, start: date, end: date) -> bool:
        from src.domain.value_objects.corporate_action_calendar import (
            CorporateActionDateRole,
            CorporateActionType,
        )

        invalidating = (
            CorporateActionType.STOCK_SPLIT,
            CorporateActionType.REVERSE_SPLIT,
            CorporateActionType.RIGHTS_ISSUE,
            CorporateActionType.BONUS,
        )
        events = self._corporate_actions.get_events_for_ticker(
            ticker,
            start,
            end,
            event_types=invalidating,
        )
        return any(
            dated.date_role is CorporateActionDateRole.EX_DATE and start <= dated.event_date <= end
            for event in events
            for dated in event.dates
        )

    @staticmethod
    def _unavailable(
        observation: LearningObservation,
        contract_id: LearningContractId,
        fingerprint: str,
        labeled_at: datetime,
        reason: str,
    ) -> LearningOutcomeLabel:
        return LearningOutcomeLabel.create(
            contract_id=contract_id,
            observation_id=observation.observation_id,
            outcome_basis=OutcomeBasis.PRICE_PATH_ONLY,
            availability=LabelAvailability.UNAVAILABLE,
            outcome=None,
            metrics={"unavailable_reason": reason},
            fingerprint=fingerprint,
            labeled_at=labeled_at,
        )


class GeneratePreOpenOutcomeLabelsUseCase:
    """Generate open-30m labels once from persisted tracks and observations.

    Terminal AVAILABLE outcomes are persisted only when track prices exist.
    Missing tracks is provisional (skip, no row) so a later run can label after
    track collection. Observations that already have a label for this contract
    are skipped so daily cron re-runs do not conflict on labeled_at digests.
    """

    def __init__(
        self,
        *,
        observations: LearningObservationRepository,
        tracks: LearningTrackSnapshotRepository,
        labels: LearningOutcomeLabelRepository,
    ) -> None:
        self._observations = observations
        self._tracks = tracks
        self._labels = labels

    def execute(self, request: GenerateLearningLabelsRequest) -> GenerateLearningLabelsResult:
        if request.purpose is not AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION:
            raise LearningContractError("pre-open label generator received wrong purpose")
        if request.label_contract is not LearningContractId.PRE_OPEN_LABEL:
            raise LearningContractError("pre-open generator requires price_path.open_30m.v1")
        observations = tuple(
            self._observations.list_observations(
                request.purpose,
                compatibility_id=request.compatibility_id,
            )
        )
        already_labeled = _observation_ids_with_contract(
            self._labels,
            [observation.observation_id for observation in observations],
            request.label_contract,
        )
        output: list[LearningOutcomeLabel] = []
        inserted = 0
        unavailable = 0
        skipped = 0
        conflicts: list[str] = []
        for observation in observations:
            if observation.observation_id in already_labeled:
                skipped += 1
                continue
            label = self._label_one(observation, request.labeled_at)
            if label is None:
                skipped += 1
                continue
            output.append(label)
            if label.availability is LabelAvailability.UNAVAILABLE:
                unavailable += 1
            if _try_add_label(self._labels, label, conflicts=conflicts):
                inserted += 1
        conflict_ids = tuple(conflicts)
        return GenerateLearningLabelsResult(
            observation_count=len(observations),
            inserted_count=inserted,
            idempotent_count=max(0, len(output) - inserted - len(conflict_ids)),
            unavailable_count=unavailable,
            skipped_count=skipped,
            labels=tuple(output),
            conflict_count=len(conflict_ids),
            conflict_label_ids=conflict_ids,
        )

    def _label_one(
        self, observation: LearningObservation, labeled_at: datetime
    ) -> LearningOutcomeLabel | None:
        tracks = tuple(self._tracks.list_track_snapshots(observation.observation_id))
        fingerprint = artifact_digest(
            {
                "observation_id": observation.observation_id,
                "track_digests": [track.artifact_digest for track in tracks],
            }
        )
        prices = [
            price for track in tracks if (price := _track_price(track.snapshot_payload)) is not None
        ]
        if not prices:
            # Provisional: tracks not collected yet — do not lock UNAVAILABLE.
            return None
        opening = prices[0]
        close_proxy = prices[-1]
        close_return = round((close_proxy - opening) / opening * 100.0, 4)
        if close_return > 0.15:
            outcome = "SUCCESS"
        elif close_return < -0.15:
            outcome = "FAILURE"
        else:
            outcome = "NEUTRAL"
        metrics = {
            "ticker": _observation_ticker(observation),
            "opening_price": opening,
            "peak_09_30": max(prices),
            "trough_09_30": min(prices),
            "close_proxy_09_30": close_proxy,
            "open_to_close_return_pct": close_return,
            "max_favorable_excursion_pct": round((max(prices) - opening) / opening * 100.0, 4),
            "max_adverse_excursion_pct": round((min(prices) - opening) / opening * 100.0, 4),
        }
        return LearningOutcomeLabel.create(
            contract_id=LearningContractId.PRE_OPEN_LABEL,
            observation_id=observation.observation_id,
            outcome_basis=OutcomeBasis.PRICE_PATH_ONLY,
            availability=LabelAvailability.AVAILABLE,
            outcome=outcome,
            metrics=metrics,
            fingerprint=fingerprint,
            labeled_at=labeled_at,
        )


def _track_price(payload: Any) -> float | None:
    if not isinstance(payload, dict):
        return None
    for key in ("opening_price", "last_price", "mid_price", "best_bid"):
        raw = payload.get(key)
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


class EvaluateLearningCohortUseCase:
    """Persist one compatible chronological evaluation from labels only."""

    def __init__(
        self,
        *,
        observations: LearningObservationRepository,
        labels: LearningOutcomeLabelRepository,
        evaluations: LearningEvaluationRepository,
    ) -> None:
        self._observations = observations
        self._labels = labels
        self._evaluations = evaluations

    def execute(self, request: EvaluateLearningCohortRequest) -> LearningEvaluation:
        observations = tuple(
            self._observations.list_observations(
                request.purpose,
                compatibility_id=request.compatibility_id,
            )
        )
        if not observations:
            raise LearningContractError("compatible cohort has no observations")
        if any(
            observation.compatibility_id != request.compatibility_id for observation in observations
        ):
            raise LearningContractError("evaluation cohort has incompatible observations")
        labels = tuple(
            self._labels.list_labels([observation.observation_id for observation in observations])
        )
        if not labels:
            raise LearningContractError("compatible cohort has no persisted labels")
        expected_contract = (
            LearningContractId.PRE_OPEN_LABEL
            if request.purpose is AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION
            else ACCUM_PRIMARY_LABEL_CONTRACT
        )
        labels = tuple(label for label in labels if label.contract_id is expected_contract)
        if not labels:
            raise LearningContractError("cohort has no labels for the required contract")
        available = tuple(
            label for label in labels if label.availability is LabelAvailability.AVAILABLE
        )
        sessions = {observation.cutoff_at.date().isoformat() for observation in observations}
        readiness = (
            EvaluationReadiness.DESCRIPTIVE_READY
            if len(sessions) <= 1
            else EvaluationReadiness.OOS_DIAGNOSTIC_READY
        )
        returns = [
            value for label in available if (value := _metric_return(label.metrics)) is not None
        ]
        histogram: dict[str, int] = {}
        for label in available:
            assert label.outcome is not None
            histogram[label.outcome] = histogram.get(label.outcome, 0) + 1
        dataset_fingerprint = artifact_digest(
            {
                "observation_ids": [item.observation_id for item in observations],
                "label_digests": [item.artifact_digest for item in labels],
            }
        )
        method = (
            EvaluationMethod.SESSION_OUTCOME_COHORT
            if request.purpose is AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION
            else EvaluationMethod.FORWARD_OUTCOME_COHORT
        )
        evaluation = LearningEvaluation.create(
            purpose=request.purpose,
            method=method,
            compatibility_id=request.compatibility_id,
            dataset_fingerprint=dataset_fingerprint,
            split_contract=request.split_contract,
            population={
                "observation_ids": [item.observation_id for item in observations],
                "label_ids": [item.label_id for item in labels],
                "session_count": len(sessions),
            },
            exclusions={
                "unavailable_label_ids": [
                    item.label_id
                    for item in labels
                    if item.availability is LabelAvailability.UNAVAILABLE
                ]
            },
            metrics={
                "available_count": len(available),
                "unavailable_count": len(labels) - len(available),
                "outcome_histogram": histogram,
                "average_return_pct": mean(returns) if returns else None,
            },
            outcome_basis=OutcomeBasis.PRICE_PATH_ONLY,
            readiness=readiness,
            evaluated_at=request.evaluated_at,
        )
        self._evaluations.add_evaluation(evaluation)
        return evaluation


def _metric_return(metrics: Any) -> float | None:
    if not isinstance(metrics, dict):
        return None
    for key in ("close_return_pct", "open_to_close_return_pct"):
        raw = metrics.get(key)
        if raw is not None:
            try:
                return float(raw)
            except (TypeError, ValueError):
                return None
    return None


class GetLearningStatusUseCase:
    def __init__(
        self,
        *,
        observations: LearningObservationRepository,
        labels: LearningOutcomeLabelRepository,
        evaluations: LearningEvaluationRepository,
    ) -> None:
        self._observations = observations
        self._labels = labels
        self._evaluations = evaluations

    def execute(self, purpose: AssessmentPurpose) -> LearningStatus:
        observations = tuple(self._observations.list_observations(purpose))
        labels = tuple(
            self._labels.list_labels([observation.observation_id for observation in observations])
        )
        evaluations = tuple(self._evaluations.list_evaluations(purpose))
        return LearningStatus(
            purpose=purpose,
            observation_count=len(observations),
            label_count=len(labels),
            available_label_count=sum(
                label.availability is LabelAvailability.AVAILABLE for label in labels
            ),
            evaluation_count=len(evaluations),
            compatibility_ids=tuple(
                sorted({observation.compatibility_id for observation in observations})
            ),
        )


@dataclass(frozen=True)
class PreOpenSessionObservationLine:
    observation_id: str
    ticker: str
    screen_result: str | None
    track_count: int
    has_opening_price: bool
    opening_snapshot_id: str | None
    label_available: bool
    readiness: str  # NO_TRACK | MISSING_OPEN | READY_TO_ANALYZE | LABELED


@dataclass(frozen=True)
class PreOpenSessionStatus:
    """Session-scoped readiness for pre-open capture → track → analyze → labels."""

    session_date: date
    observation_count: int
    with_opening_price: int
    missing_opening_price: int
    labeled_count: int
    lines: tuple[PreOpenSessionObservationLine, ...]
    next_actions: tuple[str, ...]
    corpus: LearningStatus


class GetPreOpenSessionStatusUseCase:
    """Session readiness: capture present, tracks, explicit open, labels."""

    def __init__(
        self,
        *,
        observations: LearningObservationRepository,
        tracks: LearningTrackSnapshotRepository,
        labels: LearningOutcomeLabelRepository,
        evaluations: LearningEvaluationRepository,
    ) -> None:
        self._observations = observations
        self._tracks = tracks
        self._labels = labels
        self._evaluations = evaluations

    def execute(self, session_date: date) -> PreOpenSessionStatus:
        from src.domain.value_objects.idx_market import IDX_TIMEZONE, REGULAR_OPEN

        corpus = GetLearningStatusUseCase(
            observations=self._observations,
            labels=self._labels,
            evaluations=self._evaluations,
        ).execute(AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION)

        all_obs = tuple(
            self._observations.list_observations(AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION)
        )
        session_obs = tuple(
            o for o in all_obs if o.cutoff_at.astimezone(IDX_TIMEZONE).date() == session_date
        )
        labels_by_obs = {
            label.observation_id: label
            for label in self._labels.list_labels([o.observation_id for o in session_obs])
        }

        lines: list[PreOpenSessionObservationLine] = []
        with_open = 0
        missing_open = 0
        labeled = 0

        for obs in sorted(session_obs, key=lambda o: (o.window_id, o.observation_id)):
            try:
                ticker = _observation_ticker(obs)
            except LearningContractError:
                ticker = str(obs.window_id).split(":", 1)[0].upper()
            screen_result = obs.decision_payload.get("screen_result")
            if screen_result is not None:
                screen_result = str(screen_result)
            snaps = list(self._tracks.list_track_snapshots(obs.observation_id))
            open_window = [
                s
                for s in snaps
                if s.sampled_at.astimezone(IDX_TIMEZONE).date() == session_date
                and s.sampled_at.astimezone(IDX_TIMEZONE).timetz().replace(tzinfo=None)
                >= REGULAR_OPEN
            ]
            open_window.sort(key=lambda s: (s.sampled_at, s.snapshot_id))
            opening_snapshot_id: str | None = None
            has_open = False
            for snap in open_window:
                payload = snap.snapshot_payload or {}
                if "opening_price" not in payload:
                    continue
                try:
                    if float(payload["opening_price"]) > 0:
                        has_open = True
                        opening_snapshot_id = snap.snapshot_id
                        break
                except (TypeError, ValueError):
                    continue
            if not has_open and open_window:
                opening_snapshot_id = open_window[0].snapshot_id

            label = labels_by_obs.get(obs.observation_id)
            label_ok = label is not None and label.availability is LabelAvailability.AVAILABLE
            if has_open:
                with_open += 1
            elif snaps:
                missing_open += 1
            if label_ok:
                labeled += 1

            if not snaps:
                readiness = "NO_TRACK"
            elif not has_open:
                readiness = "MISSING_OPEN"
            elif label_ok:
                readiness = "LABELED"
            else:
                readiness = "READY_TO_ANALYZE"

            lines.append(
                PreOpenSessionObservationLine(
                    observation_id=obs.observation_id,
                    ticker=ticker,
                    screen_result=screen_result,
                    track_count=len(snaps),
                    has_opening_price=has_open,
                    opening_snapshot_id=opening_snapshot_id,
                    label_available=label_ok,
                    readiness=readiness,
                )
            )

        next_actions = self._next_actions(
            session_date=session_date,
            observation_count=len(session_obs),
            with_open=with_open,
            missing_open=missing_open,
            labeled=labeled,
            lines=lines,
        )
        return PreOpenSessionStatus(
            session_date=session_date,
            observation_count=len(session_obs),
            with_opening_price=with_open,
            missing_opening_price=missing_open,
            labeled_count=labeled,
            lines=tuple(lines),
            next_actions=next_actions,
            corpus=corpus,
        )

    @staticmethod
    def _next_actions(
        *,
        session_date: date,
        observation_count: int,
        with_open: int,
        missing_open: int,
        labeled: int,
        lines: Sequence[PreOpenSessionObservationLine],
    ) -> tuple[str, ...]:
        actions: list[str] = []
        day = session_date.isoformat()
        if observation_count == 0:
            actions.append(
                f"No capture for {day}: run `saham research pre-open capture` "
                "(NCP window) or check cron/logs."
            )
            return tuple(actions)
        no_track = sum(1 for line in lines if line.readiness == "NO_TRACK")
        if no_track:
            actions.append(
                f"{no_track} observation(s) have no track: `saham research pre-open track`."
            )
        if missing_open:
            actions.append(
                f"{missing_open} observation(s) have track but MISSING_OPEN "
                "(no explicit opening_price): re-run track after open or wait "
                "for last_price; analyze will not invent mid."
            )
        ready = [line for line in lines if line.readiness == "READY_TO_ANALYZE"]
        if ready:
            actions.append(
                f"{len(ready)} ready to analyze: "
                "`saham analyze pre-open --session "
                f"{day}` (or --observation-id …)."
            )
            sample = ready[0]
            actions.append(
                f"Example log: saham trade log --type pre-open "
                f"--observation-id {sample.observation_id} "
                f"--opening-snapshot-id {sample.opening_snapshot_id or '…'}"
            )
        if with_open and labeled < with_open:
            actions.append(
                f"Labels incomplete ({labeled}/{with_open} with open): "
                "`saham research pre-open labels` then `evaluate`."
            )
        if labeled and labeled == observation_count:
            actions.append("Session labels present: `saham research pre-open evaluate`.")
        if not actions:
            actions.append("Session looks complete for captured observations.")
        return tuple(actions)
