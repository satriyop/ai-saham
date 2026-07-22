"""Generate deterministic forward labels for saved signal observations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

from src.application.ports.corporate_action_calendar_repository import (
    CorporateActionCalendarRepository,
)
from src.domain.ports.candidate_observations_repository import (
    CandidateObservation,
    CandidateObservationsRepository,
)
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.ports.signal_forward_labels_repository import (
    SignalForwardLabelsRepository,
)
from src.domain.value_objects.corporate_action_calendar import (
    CorporateActionDateRole,
    CorporateActionType,
)
from src.domain.value_objects.canonical_swing_session_contract import (
    CanonicalSwingSessionContract,
)
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
    validate_current_alpha_trigger_identity,
)
from src.domain.value_objects.signal_forward_label import (
    SignalForwardLabel,
    SignalForwardOutcome,
    SignalLabelHorizon,
    SignalObservationFingerprint,
)


class SignalLabelGenerationSkipReason(str, Enum):
    INCOMPATIBLE_OBSERVATION_SCHEMA = "INCOMPATIBLE_OBSERVATION_SCHEMA"
    NON_CANONICAL_OBSERVATION_IDENTITY = "NON_CANONICAL_OBSERVATION_IDENTITY"
    INVALID_OBSERVATION_CONTRACT = "INVALID_OBSERVATION_CONTRACT"


@dataclass(frozen=True)
class GenerateSignalForwardLabelsRequest:
    ticker: str
    signal_date: date
    observation_captured_at: datetime | None = None
    horizons: tuple[SignalLabelHorizon, ...] = (SignalLabelHorizon.SWING_10D,)


@dataclass(frozen=True)
class GenerateSignalForwardLabelsResponse:
    labels: tuple[SignalForwardLabel, ...] = field(default_factory=tuple)
    observation: CandidateObservation | None = None
    skip_reason: SignalLabelGenerationSkipReason | None = None
    source_schema_version: int | None = None


@dataclass(frozen=True)
class GenerateAllSignalForwardLabelsRequest:
    signal_date: date
    horizons: tuple[SignalLabelHorizon, ...] = (SignalLabelHorizon.SWING_10D,)


@dataclass(frozen=True)
class GenerateAllSignalForwardLabelsResponse:
    labels: tuple[SignalForwardLabel, ...] = field(default_factory=tuple)
    observation_count: int = 0
    generated_count: int = 0
    unavailable_count: int = 0
    generated_dates: tuple[date, ...] = field(default_factory=tuple)
    skipped_dates: tuple[date, ...] = field(default_factory=tuple)
    skipped_incompatible_observation_count: int = 0


@dataclass(frozen=True)
class GenerateEligibleSignalForwardLabelsRequest:
    horizon: SignalLabelHorizon = SignalLabelHorizon.SWING_10D


class GenerateSignalForwardLabelsUseCase:
    """Label the latest saved candidate observation using local candles only."""

    # Mechanical corporate-action types whose EX_DATE inside a label window
    # distorts raw returns and must fail the label closed. DIVIDEND is
    # deliberately excluded (deferred per the DQ-004 amendment).
    _INVALIDATING_ACTION_TYPES: tuple[CorporateActionType, ...] = (
        CorporateActionType.STOCK_SPLIT,
        CorporateActionType.REVERSE_SPLIT,
        CorporateActionType.RIGHTS_ISSUE,
        CorporateActionType.BONUS,
    )

    def __init__(
        self,
        *,
        candidate_observations_repository: CandidateObservationsRepository,
        market_data_repository: MarketDataRepository,
        signal_forward_labels_repository: SignalForwardLabelsRepository,
        corporate_action_calendar_repository: CorporateActionCalendarRepository,
    ) -> None:
        self._observations = candidate_observations_repository
        self._market = market_data_repository
        self._labels = signal_forward_labels_repository
        self._corp_cal = corporate_action_calendar_repository

    def execute(
        self, request: GenerateSignalForwardLabelsRequest
    ) -> GenerateSignalForwardLabelsResponse:
        ticker = request.ticker.upper()
        # A repository that validates payloads on read (e.g. the canonical
        # SQLite implementation) raises ValueError for a stored observation that
        # violates the current contract — before the object ever reaches the
        # skip-reason check below. Treat that as INVALID_OBSERVATION_CONTRACT so
        # the outcome is identical whether or not the repository self-validates.
        try:
            if request.observation_captured_at is not None:
                observation = self._observations.get_at(
                    ticker,
                    request.signal_date,
                    request.observation_captured_at,
                )
            else:
                observation = self._observations.get_latest(ticker, request.signal_date)
        except ValueError:
            return GenerateSignalForwardLabelsResponse(
                skip_reason=SignalLabelGenerationSkipReason.INVALID_OBSERVATION_CONTRACT,
            )
        if observation is None:
            return GenerateSignalForwardLabelsResponse()

        skip_reason = _canonical_observation_skip_reason(observation)
        if skip_reason is not None:
            return GenerateSignalForwardLabelsResponse(
                labels=(),
                observation=observation,
                skip_reason=skip_reason,
                source_schema_version=_observation_schema_version(observation),
            )

        # Coarse global-sync coverage gate — evaluate ONCE per call (global
        # state, not per observation). See _build_label for how it combines with
        # per-event detection.
        coverage_available = self._corp_cal.has_any_sync_marker()
        labels = tuple(
            self._build_label(observation, horizon, coverage_available=coverage_available)
            for horizon in request.horizons
        )
        if labels:
            self._labels.save_many(list(labels))
        return GenerateSignalForwardLabelsResponse(
            labels=labels,
            observation=observation,
        )

    def execute_all(
        self, request: GenerateAllSignalForwardLabelsRequest
    ) -> GenerateAllSignalForwardLabelsResponse:
        # Canonical rows, not list_by_date()'s latest-per-ticker collapse —
        # a ticker recorded across several window_sessions must get a label
        # for each one, not just the most recently captured window.
        observations = self._observations.list_canonical_by_date(request.signal_date)
        eligible_observations = [obs for obs in observations if _is_canonical_observation(obs)]
        skipped_incompatible_observation_count = len(observations) - len(eligible_observations)
        # Global-sync coverage gate — evaluate ONCE per call, not per observation.
        coverage_available = self._corp_cal.has_any_sync_marker()
        labels = self._build_labels_for_observations(
            eligible_observations, request.horizons, coverage_available=coverage_available
        )
        if labels:
            self._labels.save_many(labels)
        unavailable_count = _unavailable_count(labels)
        return GenerateAllSignalForwardLabelsResponse(
            labels=tuple(labels),
            observation_count=len(eligible_observations),
            generated_count=len(labels),
            unavailable_count=unavailable_count,
            generated_dates=(request.signal_date,) if labels else (),
            skipped_incompatible_observation_count=skipped_incompatible_observation_count,
        )

    def execute_eligible_dates(
        self, request: GenerateEligibleSignalForwardLabelsRequest
    ) -> GenerateAllSignalForwardLabelsResponse:
        labels: list[SignalForwardLabel] = []
        observation_count = 0
        generated_dates: list[date] = []
        skipped_dates: list[date] = []
        skipped_incompatible_observation_count = 0
        # Global-sync coverage gate — evaluate ONCE per call, not per observation
        # or per date.
        coverage_available = self._corp_cal.has_any_sync_marker()
        for signal_date in self._observations.list_snapshot_dates():
            observations = self._observations.list_canonical_by_date(signal_date)
            eligible_observations = [
                obs for obs in observations if _is_canonical_observation(obs)
            ]
            skipped_incompatible_observation_count += len(observations) - len(
                eligible_observations
            )
            if not eligible_observations:
                skipped_dates.append(signal_date)
                continue
            if not self._has_complete_forward_window(eligible_observations, request.horizon):
                skipped_dates.append(signal_date)
                continue
            observation_count += len(eligible_observations)
            labels.extend(
                self._build_labels_for_observations(
                    eligible_observations,
                    (request.horizon,),
                    coverage_available=coverage_available,
                )
            )
            generated_dates.append(signal_date)
        if labels:
            self._labels.save_many(labels)
        return GenerateAllSignalForwardLabelsResponse(
            labels=tuple(labels),
            observation_count=observation_count,
            generated_count=len(labels),
            unavailable_count=_unavailable_count(labels),
            generated_dates=tuple(generated_dates),
            skipped_dates=tuple(skipped_dates),
            skipped_incompatible_observation_count=skipped_incompatible_observation_count,
        )

    def _build_labels_for_observations(
        self,
        observations: list[CandidateObservation],
        horizons: tuple[SignalLabelHorizon, ...],
        *,
        coverage_available: bool,
    ) -> list[SignalForwardLabel]:
        labels: list[SignalForwardLabel] = []
        for observation in observations:
            labels.extend(
                self._build_label(observation, horizon, coverage_available=coverage_available)
                for horizon in horizons
            )
        return labels

    def _has_complete_forward_window(
        self,
        observations: list[CandidateObservation],
        horizon: SignalLabelHorizon,
    ) -> bool:
        required = horizon.trading_days
        for observation in observations:
            candles = self._market.get_candles(
                observation.ticker.upper(),
                start_date=observation.snapshot_date,
            )
            forward_candles = [c for c in candles if c.date > observation.snapshot_date]
            if len(forward_candles) >= required:
                return True
        return False

    def _build_label(
        self,
        observation: CandidateObservation,
        horizon: SignalLabelHorizon,
        *,
        coverage_available: bool,
    ) -> SignalForwardLabel:
        if not _is_canonical_observation(observation):
            raise ValueError(
                "_build_label requires a canonical candidate observation with "
                f"schema_version={CANDIDATE_OBSERVATION_SCHEMA_VERSION} and non-empty config_hash"
            )

        payload = observation.payload
        ticker = observation.ticker.upper()
        signal_date = observation.snapshot_date
        fingerprint = _fingerprint_from_payload(payload)

        entry = _entry_reference_price(payload)

        if entry is None:
            return _unavailable_label(
                ticker=ticker,
                signal_date=signal_date,
                horizon=horizon,
                observation_captured_at=observation.captured_at,
                fingerprint=fingerprint,
                reason="missing_entry_reference_price",
                entry_reference_price=None,
                observation=observation,
            )

        candles = self._market.get_candles(ticker, start_date=signal_date)
        forward_candles = [c for c in candles if c.date > signal_date]
        required = horizon.trading_days
        if len(forward_candles) < required:
            return _unavailable_label(
                ticker=ticker,
                signal_date=signal_date,
                horizon=horizon,
                observation_captured_at=observation.captured_at,
                fingerprint=fingerprint,
                reason=(
                    f"incomplete_forward_window: required {required} trading days, "
                    f"found {len(forward_candles)}"
                ),
                entry_reference_price=entry,
                label_window_start=forward_candles[0].date if forward_candles else None,
                label_window_end=forward_candles[-1].date if forward_candles else None,
                observation=observation,
            )

        window = forward_candles[:required]
        window_start = window[0].date
        window_end = window[-1].date

        # Corporate-action coverage & detection (DQ-004 Slice D4-1). The complete
        # window is resolved above; decide invalidation before computing any
        # returns so a distorted number is never produced.
        if coverage_available:
            # Gate open: run real per-event EX_DATE detection. Detection beats the
            # open gate — a detected mechanical action always invalidates.
            detected = self._detect_corporate_action(ticker, window_start, window_end)
            if detected is not None:
                ex_date, action_type = detected
                return _unavailable_label(
                    ticker=ticker,
                    signal_date=signal_date,
                    horizon=horizon,
                    observation_captured_at=observation.captured_at,
                    fingerprint=fingerprint,
                    reason=f"corporate_action_in_window:{action_type.value}@{ex_date.isoformat()}",
                    entry_reference_price=entry,
                    label_window_start=window_start,
                    label_window_end=window_end,
                    observation=observation,
                )
        else:
            # Gate closed: the calendar has never been synced, so we cannot
            # disprove a corporate action in this window. Fail closed.
            return _unavailable_label(
                ticker=ticker,
                signal_date=signal_date,
                horizon=horizon,
                observation_captured_at=observation.captured_at,
                fingerprint=fingerprint,
                reason="corporate_action_coverage_unavailable",
                entry_reference_price=entry,
                label_window_start=window_start,
                label_window_end=window_end,
                observation=observation,
            )

        close_return = _pct_change(window[-1].close, entry)
        high_returns = [_pct_change(c.high, entry) for c in window]
        low_returns = [_pct_change(c.low, entry) for c in window]
        max_forward_return = max(high_returns)
        max_adverse_excursion = min(low_returns)
        days_to_peak = high_returns.index(max_forward_return) + 1
        days_to_trough = low_returns.index(max_adverse_excursion) + 1

        policy = _threshold_policy(horizon)
        stop_would_trigger = any(v <= policy["adverse_failure"] for v in low_returns)
        target_would_trigger = _target_triggered(
            horizon=horizon,
            close_return=close_return,
            high_returns=high_returns,
        )
        outcome = _outcome_label(
            horizon=horizon,
            close_return=close_return,
            high_returns=high_returns,
            low_returns=low_returns,
        )

        return SignalForwardLabel(
            ticker=ticker,
            signal_date=signal_date,
            horizon=horizon,
            entry_reference_price=entry,
            label_window_start=window[0].date,
            label_window_end=window[-1].date,
            close_return=close_return,
            max_forward_return=max_forward_return,
            max_adverse_excursion=max_adverse_excursion,
            days_to_peak=days_to_peak,
            days_to_trough=days_to_trough,
            stop_would_trigger=stop_would_trigger,
            target_would_trigger=target_would_trigger,
            outcome_label=outcome,
            outcome_basis="raw_market",
            unavailable_reason=None,
            fingerprint=fingerprint,
            observation_captured_at=observation.captured_at,
            decision_at=observation.decision_at,
            latest_completed_session=observation.latest_completed_session,
            analysis_as_of=observation.analysis_as_of,
            market_session_name=observation.market_session_name,
            is_eod_pending=observation.is_eod_pending,
            resolution_source=observation.resolution_source,
            resolution_notes=observation.resolution_notes,
        )

    def _detect_corporate_action(
        self,
        ticker: str,
        window_start: date,
        window_end: date,
    ) -> tuple[date, CorporateActionType] | None:
        """Return the earliest mechanical corporate-action (ex_date, type) whose
        EX_DATE falls inside [window_start, window_end], or None.

        Queried WITHOUT `as_of_fetched_at`: labels are computed after the fact,
        so seeing a split that *did* occur is conservative invalidation, never
        decision-time leakage.
        """
        events = self._corp_cal.get_events_for_ticker(
            ticker,
            window_start,
            window_end,
            event_types=self._INVALIDATING_ACTION_TYPES,
        )
        hits: list[tuple[date, CorporateActionType]] = []
        for event in events:
            for dated in event.dates:
                if (
                    dated.date_role is CorporateActionDateRole.EX_DATE
                    and window_start <= dated.event_date <= window_end
                ):
                    hits.append((dated.event_date, event.event_type))
        if not hits:
            return None
        return min(hits, key=lambda hit: hit[0])


def _observation_schema_version(observation: CandidateObservation) -> int | None:
    raw = observation.payload.get("schema_version")
    return raw if type(raw) is int else None


def _canonical_observation_skip_reason(
    observation: CandidateObservation,
) -> SignalLabelGenerationSkipReason | None:
    schema_version = _observation_schema_version(observation)

    if schema_version != CANDIDATE_OBSERVATION_SCHEMA_VERSION:
        return SignalLabelGenerationSkipReason.INCOMPATIBLE_OBSERVATION_SCHEMA

    if not isinstance(observation.config_hash, str) or observation.config_hash == "":
        return SignalLabelGenerationSkipReason.NON_CANONICAL_OBSERVATION_IDENTITY

    # Do not assume the repository implementation validated payload contents.
    # A stored schema-4 observation carrying the removed market_context group is
    # a contract violation: skip it here rather than parsing its fingerprint,
    # reading candles, or writing any label.
    try:
        validate_current_alpha_trigger_identity(
            schema_version=schema_version,
            alpha_trigger_route_metadata=(
                observation.payload.get("sub_signal_fingerprint") or {}
            ).get("alpha_trigger_route_metadata"),
        )
    except ValueError:
        return SignalLabelGenerationSkipReason.INVALID_OBSERVATION_CONTRACT

    # DQ-002 criterion 1: a canonical swing observation must carry the
    # originating effective-session contract inherited from one
    # application-layer resolver. Missing or mismatched session provenance
    # means the observation cannot be reproduced as a defensible point-in-time
    # artifact and must not produce a canonical forward label.
    try:
        CanonicalSwingSessionContract.from_observation_fields(
            snapshot_date=observation.snapshot_date,
            latest_completed_session=observation.latest_completed_session,
            analysis_as_of=observation.analysis_as_of,
        )
    except ValueError:
        return SignalLabelGenerationSkipReason.INVALID_OBSERVATION_CONTRACT

    return None


def _is_canonical_observation(
    observation: CandidateObservation,
) -> bool:
    return _canonical_observation_skip_reason(observation) is None


def _unavailable_label(
    *,
    ticker: str,
    signal_date: date,
    horizon: SignalLabelHorizon,
    observation_captured_at,
    fingerprint: SignalObservationFingerprint,
    reason: str,
    entry_reference_price: Decimal | None,
    label_window_start: date | None = None,
    label_window_end: date | None = None,
    observation: CandidateObservation | None = None,
) -> SignalForwardLabel:
    return SignalForwardLabel(
        ticker=ticker,
        signal_date=signal_date,
        horizon=horizon,
        entry_reference_price=entry_reference_price,
        label_window_start=label_window_start,
        label_window_end=label_window_end,
        close_return=None,
        max_forward_return=None,
        max_adverse_excursion=None,
        days_to_peak=None,
        days_to_trough=None,
        stop_would_trigger=None,
        target_would_trigger=None,
        outcome_label=SignalForwardOutcome.UNAVAILABLE,
        unavailable_reason=reason,
        fingerprint=fingerprint,
        observation_captured_at=observation_captured_at,
        decision_at=observation.decision_at if observation else None,
        latest_completed_session=observation.latest_completed_session if observation else None,
        analysis_as_of=observation.analysis_as_of if observation else None,
        market_session_name=observation.market_session_name if observation else None,
        is_eod_pending=observation.is_eod_pending if observation else None,
        resolution_source=observation.resolution_source if observation else None,
        resolution_notes=observation.resolution_notes if observation else (),
    )


def _unavailable_count(labels: list[SignalForwardLabel]) -> int:
    return sum(
        1
        for label in labels
        if label.outcome_label is SignalForwardOutcome.UNAVAILABLE
    )


def _outcome_label(
    *,
    horizon: SignalLabelHorizon,
    close_return: float,
    high_returns: list[float],
    low_returns: list[float],
) -> SignalForwardOutcome:
    policy = _threshold_policy(horizon)
    stop_day = _first_index_at_or_below(low_returns, policy["adverse_failure"])
    target_day = _target_day(horizon=horizon, close_return=close_return, high_returns=high_returns)

    # Daily OHLC cannot prove intraday order. Treat same-candle target/stop
    # collisions conservatively as failure until intraday data is available.
    if stop_day is not None and (target_day is None or stop_day <= target_day):
        return SignalForwardOutcome.FAILURE
    if target_day is not None and (stop_day is None or target_day < stop_day):
        return SignalForwardOutcome.SUCCESS
    if close_return <= policy["close_failure"]:
        return SignalForwardOutcome.FAILURE
    return SignalForwardOutcome.NEUTRAL


def _entry_reference_price(payload: dict[str, Any]) -> Decimal | None:
    trade_setup = payload.get("trade_setup") or {}
    for value in (
        trade_setup.get("entry_reference_price"),
        trade_setup.get("entry_price"),
        (payload.get("candidate") or {}).get("current_price"),
    ):
        parsed = _optional_decimal(value)
        if parsed is not None and parsed > 0:
            return parsed
    return None


def _fingerprint_from_payload(payload: dict[str, Any]) -> SignalObservationFingerprint:
    return SignalObservationFingerprint.from_dict(payload.get("sub_signal_fingerprint") or {})


def _threshold_policy(horizon: SignalLabelHorizon) -> dict[str, float]:
    return {
        SignalLabelHorizon.TACTICAL_3D: {
            "target_return": 2.0,
            "adverse_failure": -2.5,
            "close_failure": -1.0,
        },
        SignalLabelHorizon.SWING_10D: {
            "target_return": 4.0,
            "adverse_failure": -4.0,
            "close_failure": -2.0,
        },
        SignalLabelHorizon.ACCUM_20D: {
            "target_return": 5.0,
            "adverse_failure": -6.0,
            "close_failure": -3.0,
        },
    }[horizon]


def _target_triggered(
    *,
    horizon: SignalLabelHorizon,
    close_return: float,
    high_returns: list[float],
) -> bool:
    return (
        _target_day(
            horizon=horizon,
            close_return=close_return,
            high_returns=high_returns,
        )
        is not None
    )


def _target_day(
    *,
    horizon: SignalLabelHorizon,
    close_return: float,
    high_returns: list[float],
) -> int | None:
    policy = _threshold_policy(horizon)
    if horizon == SignalLabelHorizon.ACCUM_20D:
        return len(high_returns) - 1 if close_return >= policy["target_return"] else None
    return _first_index_at_or_above(high_returns, policy["target_return"])


def _first_index_at_or_above(values: list[float], threshold: float) -> int | None:
    for idx, value in enumerate(values):
        if value >= threshold:
            return idx
    return None


def _first_index_at_or_below(values: list[float], threshold: float) -> int | None:
    for idx, value in enumerate(values):
        if value <= threshold:
            return idx
    return None


def _pct_change(value: Decimal, base: Decimal) -> float:
    return float((value - base) / base * Decimal("100"))


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
