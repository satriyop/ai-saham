"""Database-owned accumulation and pre-open label/evaluation lifecycle."""

from __future__ import annotations

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
    LearningContractId.TACTICAL_LABEL: 3,
    LearningContractId.SWING_LABEL: 10,
    LearningContractId.ACCUMULATION_LABEL: 20,
}


def _observation_ticker(observation: LearningObservation) -> str:
    ticker = observation.decision_payload.get("ticker")
    if not isinstance(ticker, str) or not ticker.strip():
        raise LearningContractError("learning observation decision payload requires ticker")
    return ticker.strip().upper()


def _entry_reference(payload: dict[str, Any] | Any) -> Decimal | None:
    if not isinstance(payload, dict):
        return None
    candidate = payload.get("candidate")
    if not isinstance(candidate, dict):
        return None
    for key in ("entry_price", "close", "last_price", "price"):
        raw = candidate.get(key)
        if raw is None:
            continue
        try:
            value = Decimal(str(raw))
        except Exception:
            continue
        if value > 0:
            return value
    return None


def _pct_change(value: Any, base: Decimal) -> float:
    return round((float(value) - float(base)) / float(base) * 100.0, 6)


class GenerateAccumulationPricePathLabelsUseCase:
    """Generate immutable forward price-path labels from saved observations."""

    def __init__(
        self,
        *,
        observations: LearningObservationRepository,
        labels: LearningOutcomeLabelRepository,
        market_data: LearningMarketDataRepository,
        corporate_actions: LearningCorporateActionCalendarRepository,
    ) -> None:
        self._observations = observations
        self._labels = labels
        self._market = market_data
        self._corporate_actions = corporate_actions

    def execute(
        self, request: GenerateLearningLabelsRequest
    ) -> GenerateLearningLabelsResult:
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
        labels: list[LearningOutcomeLabel] = []
        inserted = 0
        unavailable = 0
        coverage_available = self._corporate_actions.has_any_sync_marker()
        for observation in observations:
            label = self._label_one(
                observation,
                contract_id=request.label_contract,
                horizon_days=horizon_days,
                labeled_at=request.labeled_at,
                coverage_available=coverage_available,
            )
            labels.append(label)
            if label.availability is LabelAvailability.UNAVAILABLE:
                unavailable += 1
            if self._labels.add_label(label):
                inserted += 1
        return GenerateLearningLabelsResult(
            observation_count=len(observations),
            inserted_count=inserted,
            idempotent_count=len(labels) - inserted,
            unavailable_count=unavailable,
            labels=tuple(labels),
        )
    def _label_one(
        self,
        observation: LearningObservation,
        *,
        contract_id: LearningContractId,
        horizon_days: int,
        labeled_at: datetime,
        coverage_available: bool,
    ) -> LearningOutcomeLabel:
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
            return self._unavailable(
                observation,
                contract_id,
                fingerprint,
                labeled_at,
                "missing_entry_reference_price",
            )
        candles = self._market.get_candles(ticker, start_date=signal_date)
        forward = sorted(
            (c for c in candles if c.date > signal_date),
            key=lambda candle: candle.date,
        )
        if len(forward) < horizon_days:
            return self._unavailable(
                observation,
                contract_id,
                fingerprint,
                labeled_at,
                f"incomplete_forward_window:{len(forward)}/{horizon_days}",
            )
        window = forward[:horizon_days]
        if not coverage_available:
            return self._unavailable(
                observation,
                contract_id,
                fingerprint,
                labeled_at,
                "corporate_action_coverage_unavailable",
            )
        if self._has_mechanical_corporate_action(
            ticker, window[0].date, window[-1].date
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
        metrics = {
            "ticker": ticker,
            "signal_date": signal_date.isoformat(),
            "label_window_start": window[0].date.isoformat(),
            "label_window_end": window[-1].date.isoformat(),
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

    def _has_mechanical_corporate_action(
        self, ticker: str, start: date, end: date
    ) -> bool:
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
            dated.date_role is CorporateActionDateRole.EX_DATE
            and start <= dated.event_date <= end
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
    """Generate open-30m labels once from persisted tracks and observations."""

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

    def execute(
        self, request: GenerateLearningLabelsRequest
    ) -> GenerateLearningLabelsResult:
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
        output: list[LearningOutcomeLabel] = []
        inserted = 0
        unavailable = 0
        for observation in observations:
            label = self._label_one(observation, request.labeled_at)
            output.append(label)
            if label.availability is LabelAvailability.UNAVAILABLE:
                unavailable += 1
            if self._labels.add_label(label):
                inserted += 1
        return GenerateLearningLabelsResult(
            observation_count=len(observations),
            inserted_count=inserted,
            idempotent_count=len(output) - inserted,
            unavailable_count=unavailable,
            labels=tuple(output),
        )

    def _label_one(
        self, observation: LearningObservation, labeled_at: datetime
    ) -> LearningOutcomeLabel:
        tracks = tuple(self._tracks.list_track_snapshots(observation.observation_id))
        fingerprint = artifact_digest(
            {
                "observation_id": observation.observation_id,
                "track_digests": [track.artifact_digest for track in tracks],
            }
        )
        prices = [
            price
            for track in tracks
            if (price := _track_price(track.snapshot_payload)) is not None
        ]
        if not prices:
            return LearningOutcomeLabel.create(
                contract_id=LearningContractId.PRE_OPEN_LABEL,
                observation_id=observation.observation_id,
                outcome_basis=OutcomeBasis.PRICE_PATH_ONLY,
                availability=LabelAvailability.UNAVAILABLE,
                outcome=None,
                metrics={"unavailable_reason": "no_track_prices"},
                fingerprint=fingerprint,
                labeled_at=labeled_at,
            )
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
            "max_favorable_excursion_pct": round(
                (max(prices) - opening) / opening * 100.0, 4
            ),
            "max_adverse_excursion_pct": round(
                (min(prices) - opening) / opening * 100.0, 4
            ),
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
            observation.compatibility_id != request.compatibility_id
            for observation in observations
        ):
            raise LearningContractError("evaluation cohort has incompatible observations")
        labels = tuple(
            self._labels.list_labels(
                [observation.observation_id for observation in observations]
            )
        )
        if not labels:
            raise LearningContractError("compatible cohort has no persisted labels")
        expected_contract = (
            LearningContractId.PRE_OPEN_LABEL
            if request.purpose is AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION
            else LearningContractId.ACCUMULATION_LABEL
        )
        labels = tuple(label for label in labels if label.contract_id is expected_contract)
        if not labels:
            raise LearningContractError("cohort has no labels for the required contract")
        available = tuple(
            label for label in labels if label.availability is LabelAvailability.AVAILABLE
        )
        sessions = {
            observation.cutoff_at.date().isoformat() for observation in observations
        }
        readiness = (
            EvaluationReadiness.DESCRIPTIVE_READY
            if len(sessions) <= 1
            else EvaluationReadiness.OOS_DIAGNOSTIC_READY
        )
        returns = [
            value
            for label in available
            if (
                value := _metric_return(label.metrics)
            )
            is not None
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
            self._labels.list_labels(
                [observation.observation_id for observation in observations]
            )
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
