"""Generate deterministic forward labels for saved signal observations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from src.domain.ports.candidate_observations_repository import (
    CandidateObservation,
    CandidateObservationsRepository,
)
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.ports.signal_forward_labels_repository import (
    SignalForwardLabelsRepository,
)
from src.domain.value_objects.signal_forward_label import (
    SignalForwardLabel,
    SignalForwardOutcome,
    SignalLabelHorizon,
    SignalObservationFingerprint,
)


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


@dataclass(frozen=True)
class GenerateEligibleSignalForwardLabelsRequest:
    horizon: SignalLabelHorizon = SignalLabelHorizon.SWING_10D


class GenerateSignalForwardLabelsUseCase:
    """Label the latest saved candidate observation using local candles only."""

    def __init__(
        self,
        *,
        candidate_observations_repository: CandidateObservationsRepository,
        market_data_repository: MarketDataRepository,
        signal_forward_labels_repository: SignalForwardLabelsRepository,
    ) -> None:
        self._observations = candidate_observations_repository
        self._market = market_data_repository
        self._labels = signal_forward_labels_repository

    def execute(
        self, request: GenerateSignalForwardLabelsRequest
    ) -> GenerateSignalForwardLabelsResponse:
        ticker = request.ticker.upper()
        if request.observation_captured_at is not None:
            observation = self._observations.get_at(
                ticker,
                request.signal_date,
                request.observation_captured_at,
            )
        else:
            observation = self._observations.get_latest(ticker, request.signal_date)
        if observation is None:
            return GenerateSignalForwardLabelsResponse()

        labels = tuple(self._build_label(observation, horizon) for horizon in request.horizons)
        self._labels.save_many(list(labels))
        return GenerateSignalForwardLabelsResponse(
            labels=labels,
            observation=observation,
        )

    def execute_all(
        self, request: GenerateAllSignalForwardLabelsRequest
    ) -> GenerateAllSignalForwardLabelsResponse:
        observations = self._observations.list_by_date(request.signal_date)
        labels = self._build_labels_for_observations(observations, request.horizons)
        self._labels.save_many(labels)
        unavailable_count = _unavailable_count(labels)
        return GenerateAllSignalForwardLabelsResponse(
            labels=tuple(labels),
            observation_count=len(observations),
            generated_count=len(labels),
            unavailable_count=unavailable_count,
            generated_dates=(request.signal_date,) if labels else (),
        )

    def execute_eligible_dates(
        self, request: GenerateEligibleSignalForwardLabelsRequest
    ) -> GenerateAllSignalForwardLabelsResponse:
        labels: list[SignalForwardLabel] = []
        observation_count = 0
        generated_dates: list[date] = []
        skipped_dates: list[date] = []
        for signal_date in self._observations.list_snapshot_dates():
            observations = self._observations.list_by_date(signal_date)
            if not observations:
                skipped_dates.append(signal_date)
                continue
            if not self._has_complete_forward_window(observations, request.horizon):
                skipped_dates.append(signal_date)
                continue
            observation_count += len(observations)
            labels.extend(
                self._build_labels_for_observations(
                    observations,
                    (request.horizon,),
                )
            )
            generated_dates.append(signal_date)
        self._labels.save_many(labels)
        return GenerateAllSignalForwardLabelsResponse(
            labels=tuple(labels),
            observation_count=observation_count,
            generated_count=len(labels),
            unavailable_count=_unavailable_count(labels),
            generated_dates=tuple(generated_dates),
            skipped_dates=tuple(skipped_dates),
        )

    def _build_labels_for_observations(
        self,
        observations: list[CandidateObservation],
        horizons: tuple[SignalLabelHorizon, ...],
    ) -> list[SignalForwardLabel]:
        labels: list[SignalForwardLabel] = []
        for observation in observations:
            labels.extend(
                self._build_label(observation, horizon)
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
    ) -> SignalForwardLabel:
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
            )

        window = forward_candles[:required]
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
            unavailable_reason=None,
            fingerprint=fingerprint,
            observation_captured_at=observation.captured_at,
        )


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
