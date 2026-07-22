"""DQ-004 Slice D4-2 — golden reconciliation + verification tests.

Proves existing raw-label behavior against independent hand-computed candle math.
Does not modify generator, summarizer, repo, or value objects.

Corporate-action gate: every golden/collision scenario injects a gate-open,
event-free calendar (`has_any_sync_marker() -> True`, no events) so coverage
detection does not short-circuit to UNAVAILABLE before raw math runs.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from src.application.use_case.generate_signal_forward_labels_use_case import (
    GenerateSignalForwardLabelsRequest,
    GenerateSignalForwardLabelsUseCase,
)
from src.application.use_case.summarize_signal_forward_labels_use_case import (
    SummarizeSignalForwardLabelsRequest,
    SummarizeSignalForwardLabelsUseCase,
)
from src.domain.entities.candle import Candle
from src.domain.ports.candidate_observations_repository import CandidateObservation
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)
from src.domain.value_objects.signal_forward_label import (
    SignalForwardLabel,
    SignalForwardOutcome,
    SignalLabelHorizon,
    SignalObservationFingerprint,
)
from src.infrastructure.persistence.sqlite_signal_forward_labels_repository import (
    SQLiteSignalForwardLabelsRepository,
)

# Reuse D4-1 fakes — do not reinvent alternate calendar/market semantics.
from tests.application.use_case.test_generate_signal_forward_labels_use_case import (
    FakeCandidateObservationsRepository,
    FakeMarketDataRepository,
    SpySignalForwardLabelsRepository,
    _candle,
    _fingerprint,
    _gate_open_calendar,
    _observation,
)

# --------------------------------------------------------------------------- #
# Hand-computed helpers (independent of the generator)
# --------------------------------------------------------------------------- #

_ENTRY = Decimal("100")
_SIGNAL_DATE = date(2026, 1, 2)
# SWING_10D thresholds (hand-locked to match _threshold_policy; not imported):
#   target_return=+4.0, adverse_failure=-4.0, close_failure=-2.0
_HORIZON = SignalLabelHorizon.SWING_10D


def _approx(value: float):
    return pytest.approx(value, abs=1e-9)


def _pct_change_hand(value: Decimal, entry: Decimal = _ENTRY) -> float:
    """Independent pct-change: (value - entry) / entry * 100."""
    return float((value - entry) / entry * Decimal("100"))


def _forward_dates(n: int = 10) -> list[date]:
    return [_SIGNAL_DATE + timedelta(days=i) for i in range(1, n + 1)]


def _pad_window(
    bars: list[tuple[str, str, str]],
    *,
    fill_high: str = "101",
    fill_low: str = "99",
    fill_close: str = "100",
) -> list[Candle]:
    """Build signal-day + exactly 10 forward candles from (high, low, close) triples.

    Forward bars beyond ``bars`` are filled with the fill_* prices so the
    incomplete-window path is never triggered accidentally.
    """
    dates = _forward_dates(10)
    candles = [_candle(_SIGNAL_DATE, "100")]
    for i, day in enumerate(dates):
        if i < len(bars):
            high, low, close = bars[i]
        else:
            high, low, close = fill_high, fill_low, fill_close
        candles.append(_candle(day, close, high=high, low=low))
    return candles


def _obs(
    *,
    entry: str = "100",
    captured_at: datetime = datetime(2026, 1, 2, 9, 0, 0),
    ticker: str = "BBCA",
) -> CandidateObservation:
    """Canonical observation carrying entry via trade_setup.entry_reference_price.

    Includes decision_at so persisted labels satisfy the repo's canonical
    list() provenance predicate (decision_at + session fields + captured_at).
    """
    return _observation(
        _SIGNAL_DATE,
        {
            "trade_setup": {"entry_reference_price": entry},
            "sub_signal_fingerprint": _fingerprint(),
        },
        ticker=ticker,
        captured_at=captured_at,
        decision_at=datetime(2026, 1, 2, 16, 0, 0),
    )


def _run_generate(
    observation: CandidateObservation,
    candles: list[Candle],
    *,
    labels_repo=None,
    calendar=None,
    observation_captured_at: datetime | None = None,
) -> object:
    """Run generator with gate-open, event-free calendar (required for raw math)."""
    if calendar is None:
        # Gate open + no events: coverage available, detection finds nothing.
        calendar = _gate_open_calendar()
    if labels_repo is None:
        labels_repo = SpySignalForwardLabelsRepository()
    return GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(
            observation
        ),
        market_data_repository=FakeMarketDataRepository(candles),
        signal_forward_labels_repository=labels_repo,
        corporate_action_calendar_repository=calendar,
    ).execute(
        GenerateSignalForwardLabelsRequest(
            ticker=observation.ticker,
            signal_date=observation.snapshot_date,
            observation_captured_at=observation_captured_at,
            horizons=(_HORIZON,),
        )
    )


def _assert_available_fields(label: SignalForwardLabel, expected: dict) -> None:
    assert label.outcome_label == expected["outcome_label"]
    assert label.outcome_basis == "raw_market"
    assert label.unavailable_reason is None
    assert label.entry_reference_price == _ENTRY
    assert label.close_return == _approx(expected["close_return"])
    assert label.max_forward_return == _approx(expected["max_forward_return"])
    assert label.max_adverse_excursion == _approx(expected["max_adverse_excursion"])
    assert label.days_to_peak == expected["days_to_peak"]
    assert label.days_to_trough == expected["days_to_trough"]
    assert label.stop_would_trigger is expected["stop_would_trigger"]
    assert label.target_would_trigger is expected["target_would_trigger"]
    assert label.label_window_start == expected["label_window_start"]
    assert label.label_window_end == expected["label_window_end"]


# =========================================================================== #
# Criterion 1 — golden reconciliation (hand-computed field-by-field)
# =========================================================================== #


def test_golden_success_reconciles_every_field():
    """SUCCESS: target (+4%) hits day 1; stop never fires; close ends +3%.

    Forward OHLC (entry=100):
      d1: H=105 L=99  C=102  → high +5.0, low -1.0
      d2–d9: H=102 L=100 C=101
      d10: H=103 L=100 C=103 → close_return +3.0

    Hand math:
      high_returns = [5, 2, 2, 2, 2, 2, 2, 2, 2, 3]
      low_returns  = [-1, 0, 0, 0, 0, 0, 0, 0, 0, 0]
      max_forward_return = 5.0 (day 1), days_to_peak = 1
      max_adverse_excursion = -1.0 (day 1), days_to_trough = 1
      stop_would_trigger = False (−1 > −4)
      target_would_trigger = True (5 ≥ 4 on day 1)
      stop_day=None, target_day=0 → SUCCESS
    """
    bars = [("105", "99", "102")] + [("102", "100", "101")] * 8 + [("103", "100", "103")]
    candles = _pad_window(bars)
    # Rebuild explicitly so pad fill is not used — bars already length 10.
    assert len([c for c in candles if c.date > _SIGNAL_DATE]) == 10

    response = _run_generate(_obs(), candles)
    label = response.labels[0]

    dates = _forward_dates(10)
    _assert_available_fields(
        label,
        {
            "outcome_label": SignalForwardOutcome.SUCCESS,
            "close_return": _pct_change_hand(Decimal("103")),
            "max_forward_return": _pct_change_hand(Decimal("105")),
            "max_adverse_excursion": _pct_change_hand(Decimal("99")),
            "days_to_peak": 1,
            "days_to_trough": 1,
            "stop_would_trigger": False,
            "target_would_trigger": True,
            "label_window_start": dates[0],
            "label_window_end": dates[-1],
        },
    )


def test_golden_failure_reconciles_every_field():
    """FAILURE: adverse stop (−4%) hits day 1; target never reached.

    Forward OHLC (entry=100):
      d1: H=101 L=95 C=96   → high +1.0, low −5.0 (stop)
      d2–d9: H=101 L=98 C=99
      d10: H=100 L=97 C=98 → close_return −2.0

    Hand math:
      max_forward_return = 1.0, days_to_peak = 1
      max_adverse_excursion = −5.0, days_to_trough = 1
      stop_would_trigger = True; target_would_trigger = False
      stop_day=0 → FAILURE
    """
    bars = [("101", "95", "96")] + [("101", "98", "99")] * 8 + [("100", "97", "98")]
    candles = _pad_window(bars)

    response = _run_generate(_obs(), candles)
    label = response.labels[0]

    dates = _forward_dates(10)
    _assert_available_fields(
        label,
        {
            "outcome_label": SignalForwardOutcome.FAILURE,
            "close_return": _pct_change_hand(Decimal("98")),
            "max_forward_return": _pct_change_hand(Decimal("101")),
            "max_adverse_excursion": _pct_change_hand(Decimal("95")),
            "days_to_peak": 1,
            "days_to_trough": 1,
            "stop_would_trigger": True,
            "target_would_trigger": False,
            "label_window_start": dates[0],
            "label_window_end": dates[-1],
        },
    )


def test_golden_neutral_reconciles_every_field():
    """NEUTRAL: neither target nor stop; close above close_failure (−2%).

    All 10 days: H=101 L=99 C=100.5
      close_return = +0.5
      max_forward_return = +1.0
      max_adverse_excursion = −1.0
      no stop (−1 > −4), no target (1 < 4), close 0.5 > −2 → NEUTRAL
    """
    bars = [("101", "99", "100.5")] * 10
    candles = _pad_window(bars)

    response = _run_generate(_obs(), candles)
    label = response.labels[0]

    dates = _forward_dates(10)
    _assert_available_fields(
        label,
        {
            "outcome_label": SignalForwardOutcome.NEUTRAL,
            "close_return": _pct_change_hand(Decimal("100.5")),
            "max_forward_return": _pct_change_hand(Decimal("101")),
            "max_adverse_excursion": _pct_change_hand(Decimal("99")),
            "days_to_peak": 1,
            "days_to_trough": 1,
            "stop_would_trigger": False,
            "target_would_trigger": False,
            "label_window_start": dates[0],
            "label_window_end": dates[-1],
        },
    )


def test_golden_unavailable_incomplete_window():
    """UNAVAILABLE: only 3 forward candles for SWING_10D (required 10).

    Gate is open/event-free — incompleteness is the sole UNAVAILABLE reason.
    """
    dates = _forward_dates(3)
    candles = [_candle(_SIGNAL_DATE, "100")]
    candles.extend(_candle(d, "101") for d in dates)

    # Gate-open, event-free so we prove incomplete-window, not coverage gate.
    response = _run_generate(_obs(), candles, calendar=_gate_open_calendar())
    label = response.labels[0]

    assert label.outcome_label == SignalForwardOutcome.UNAVAILABLE
    assert label.outcome_basis == "raw_market"
    assert label.unavailable_reason == (
        "incomplete_forward_window: required 10 trading days, found 3"
    )
    assert label.entry_reference_price == _ENTRY
    assert label.close_return is None
    assert label.max_forward_return is None
    assert label.max_adverse_excursion is None
    assert label.days_to_peak is None
    assert label.days_to_trough is None
    assert label.stop_would_trigger is None
    assert label.target_would_trigger is None
    assert label.label_window_start == dates[0]
    assert label.label_window_end == dates[-1]


# =========================================================================== #
# Criterion 2 — target/stop collision policy
# =========================================================================== #


def test_collision_same_day_target_and_stop_is_conservative_failure():
    """Same forward candle: high ≥ +4% AND low ≤ −4% → FAILURE.

    Policy: stop_day <= target_day → FAILURE (intraday order unknowable).
    Gate-open, event-free calendar so raw collision math runs.
    """
    # d1: both thresholds on the same bar; remaining days flat.
    bars = [("105", "95", "100")] + [("101", "99", "100")] * 9
    candles = _pad_window(bars)

    response = _run_generate(_obs(), candles)
    label = response.labels[0]

    assert label.stop_would_trigger is True
    assert label.target_would_trigger is True
    assert label.outcome_label == SignalForwardOutcome.FAILURE
    assert label.outcome_basis == "raw_market"
    assert label.max_forward_return == _approx(_pct_change_hand(Decimal("105")))
    assert label.max_adverse_excursion == _approx(_pct_change_hand(Decimal("95")))
    assert label.days_to_peak == 1
    assert label.days_to_trough == 1


def test_collision_target_day_strictly_before_stop_is_success():
    """Target on day 1, stop on day 2 → SUCCESS (ordering not inverted).

    Gate-open, event-free calendar so raw ordering math runs.
    """
    bars = [
        ("105", "99", "102"),  # target day 1 (index 0)
        ("101", "95", "96"),  # stop day 2 (index 1)
    ] + [("101", "99", "100")] * 8
    candles = _pad_window(bars)

    response = _run_generate(_obs(), candles)
    label = response.labels[0]

    assert label.target_would_trigger is True
    assert label.stop_would_trigger is True
    assert label.outcome_label == SignalForwardOutcome.SUCCESS
    assert label.outcome_basis == "raw_market"
    assert label.days_to_peak == 1
    assert label.days_to_trough == 2


# =========================================================================== #
# Criterion 6 — summary excludes UNAVAILABLE from outcome buckets and averages
# =========================================================================== #


def _summary_label(
    *,
    ticker: str,
    outcome: SignalForwardOutcome,
    close_return: float | None,
    max_forward_return: float | None,
    max_adverse_excursion: float | None,
    unavailable_reason: str | None = None,
) -> SignalForwardLabel:
    return SignalForwardLabel(
        ticker=ticker,
        signal_date=_SIGNAL_DATE,
        horizon=_HORIZON,
        entry_reference_price=_ENTRY if outcome != SignalForwardOutcome.UNAVAILABLE else _ENTRY,
        label_window_start=_SIGNAL_DATE + timedelta(days=1),
        label_window_end=_SIGNAL_DATE + timedelta(days=10),
        close_return=close_return,
        max_forward_return=max_forward_return,
        max_adverse_excursion=max_adverse_excursion,
        days_to_peak=1 if close_return is not None else None,
        days_to_trough=1 if close_return is not None else None,
        stop_would_trigger=False if close_return is not None else None,
        target_would_trigger=(outcome == SignalForwardOutcome.SUCCESS)
        if close_return is not None
        else None,
        outcome_label=outcome,
        unavailable_reason=unavailable_reason,
        fingerprint=SignalObservationFingerprint(
            setup_family="foreign_bounce",
            market_regime={"regime": "RISK_ON"},
        ),
        observation_captured_at=datetime(2026, 1, 2, 9, 0, 0),
        outcome_basis="raw_market",
    )


class _FakeSummaryLabelsRepo:
    def __init__(self, labels):
        self.labels = labels

    def list(self, *, signal_date=None, horizon=None, ticker=None):
        return [
            label
            for label in self.labels
            if (signal_date is None or label.signal_date == signal_date)
            and (horizon is None or label.horizon == horizon)
            and (ticker is None or label.ticker == ticker.upper())
        ]

    def save_many(self, labels):
        raise AssertionError("not used")

    def get(self, ticker, signal_date, horizon):
        raise AssertionError("not used")

    def get_at(self, ticker, signal_date, horizon, observation_captured_at):
        raise AssertionError("not used")


def test_summary_excludes_unavailable_from_outcome_buckets_and_averages():
    """PROOF: UNAVAILABLE counted only in unavailable_count; averages skip None.

    Mix: 1 SUCCESS (close=5, max_fwd=6, mae=-1),
         1 FAILURE (close=-3, max_fwd=1, mae=-5),
         1 NEUTRAL (close=0.5, max_fwd=1, mae=-1),
         1 UNAVAILABLE (all returns None).

    Expected over available only:
      avg_close = (5 + -3 + 0.5) / 3 = 0.8333
      avg_max_fwd = (6 + 1 + 1) / 3 = 2.6667
      avg_mae = (-1 + -5 + -1) / 3 = -2.3333
    """
    labels = [
        _summary_label(
            ticker="BBCA",
            outcome=SignalForwardOutcome.SUCCESS,
            close_return=5.0,
            max_forward_return=6.0,
            max_adverse_excursion=-1.0,
        ),
        _summary_label(
            ticker="BBRI",
            outcome=SignalForwardOutcome.FAILURE,
            close_return=-3.0,
            max_forward_return=1.0,
            max_adverse_excursion=-5.0,
        ),
        _summary_label(
            ticker="BMRI",
            outcome=SignalForwardOutcome.NEUTRAL,
            close_return=0.5,
            max_forward_return=1.0,
            max_adverse_excursion=-1.0,
        ),
        _summary_label(
            ticker="ASII",
            outcome=SignalForwardOutcome.UNAVAILABLE,
            close_return=None,
            max_forward_return=None,
            max_adverse_excursion=None,
            unavailable_reason="incomplete_forward_window: required 10 trading days, found 3",
        ),
    ]

    response = SummarizeSignalForwardLabelsUseCase(
        _FakeSummaryLabelsRepo(labels)
    ).execute(
        SummarizeSignalForwardLabelsRequest(
            signal_date=_SIGNAL_DATE,
            horizon=_HORIZON,
        )
    )

    by_group = {(b.group, b.key): b for b in response.buckets}
    # Same setup_family → one bucket containing all four labels.
    bucket = by_group[("setup_family", "foreign_bounce")]

    assert bucket.observation_count == 4
    assert bucket.success_count == 1
    assert bucket.failure_count == 1
    assert bucket.neutral_count == 1
    assert bucket.unavailable_count == 1
    # Outcome buckets must not fold UNAVAILABLE into success/failure/neutral.
    assert (
        bucket.success_count
        + bucket.failure_count
        + bucket.neutral_count
        + bucket.unavailable_count
        == bucket.observation_count
    )
    # Averages over available returns only (UNAVAILABLE contributes None → excluded).
    assert bucket.average_close_return == pytest.approx(0.8333, abs=1e-4)
    assert bucket.average_max_forward_return == pytest.approx(2.6667, abs=1e-4)
    assert bucket.average_max_adverse_excursion == pytest.approx(-2.3333, abs=1e-4)


# =========================================================================== #
# Criterion 5 — observation binding via observation_captured_at
# =========================================================================== #


class _VersionedCandidateObservationsRepository:
    """Lookup by exact captured_at — required to prove binding, not latest-wins."""

    def __init__(self, observations: list[CandidateObservation]):
        self._by_key = {
            (o.ticker.upper(), o.snapshot_date, o.captured_at): o for o in observations
        }
        self.at_calls = []

    def get_latest(self, ticker, snapshot_date):
        raise AssertionError("binding tests must use get_at via observation_captured_at")

    def get_at(self, ticker, snapshot_date, captured_at):
        self.at_calls.append((ticker, snapshot_date, captured_at))
        return self._by_key.get((ticker.upper(), snapshot_date, captured_at))

    def list_by_date(self, snapshot_date):
        raise AssertionError("not used")

    def list_canonical_by_date(self, snapshot_date):
        raise AssertionError("not used")

    def list_snapshot_dates(self):
        raise AssertionError("not used")


def test_distinct_observation_versions_produce_distinct_label_rows(tmp_path: Path):
    """Two captured_at versions → two label rows; neither clobbers the other.

    Awareness (DQ-006 territory): one ticker/date can have several window
    observations; we use distinct captured_at so this exercises binding only.
    Gate-open, event-free calendar so labels compute as SUCCESS.
    """
    captured_a = datetime(2026, 1, 2, 9, 0, 0)
    captured_b = datetime(2026, 1, 2, 10, 0, 0)
    obs_a = _obs(entry="100", captured_at=captured_a)
    obs_b = _obs(entry="100", captured_at=captured_b)

    # Rising window → SUCCESS for both (same candles; binding is via captured_at).
    bars = [("105", "99", "102")] + [("102", "100", "101")] * 8 + [("103", "100", "103")]
    candles = _pad_window(bars)

    db_path = tmp_path / "labels.db"
    labels_repo = SQLiteSignalForwardLabelsRepository(db_path)
    observations_repo = _VersionedCandidateObservationsRepository([obs_a, obs_b])
    calendar = _gate_open_calendar()  # gate open, event-free

    use_case = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=observations_repo,
        market_data_repository=FakeMarketDataRepository(candles),
        signal_forward_labels_repository=labels_repo,
        corporate_action_calendar_repository=calendar,
    )

    resp_a = use_case.execute(
        GenerateSignalForwardLabelsRequest(
            ticker="BBCA",
            signal_date=_SIGNAL_DATE,
            observation_captured_at=captured_a,
            horizons=(_HORIZON,),
        )
    )
    resp_b = use_case.execute(
        GenerateSignalForwardLabelsRequest(
            ticker="BBCA",
            signal_date=_SIGNAL_DATE,
            observation_captured_at=captured_b,
            horizons=(_HORIZON,),
        )
    )

    assert resp_a.labels[0].observation_captured_at == captured_a
    assert resp_b.labels[0].observation_captured_at == captured_b
    # Outcome cannot attach to a different captured_at than the observation used.
    assert resp_a.observation is not None
    assert resp_a.observation.captured_at == captured_a
    assert resp_a.labels[0].observation_captured_at == resp_a.observation.captured_at
    assert resp_b.observation is not None
    assert resp_b.observation.captured_at == captured_b
    assert resp_b.labels[0].observation_captured_at == resp_b.observation.captured_at

    listed = labels_repo.list(
        signal_date=_SIGNAL_DATE, horizon=_HORIZON, ticker="BBCA"
    )
    assert len(listed) == 2
    captured_ats = {label.observation_captured_at for label in listed}
    assert captured_ats == {captured_a, captured_b}

    exact_a = labels_repo.get_at("BBCA", _SIGNAL_DATE, _HORIZON, captured_a)
    exact_b = labels_repo.get_at("BBCA", _SIGNAL_DATE, _HORIZON, captured_b)
    assert exact_a is not None and exact_a.observation_captured_at == captured_a
    assert exact_b is not None and exact_b.observation_captured_at == captured_b
    # Wrong captured_at must not return the other version's row.
    assert exact_a.observation_captured_at != exact_b.observation_captured_at


def test_relabel_same_observation_replaces_via_on_conflict(tmp_path: Path):
    """Re-labeling the same captured_at replaces the row (UNIQUE upsert), no dup.

    Gate-open, event-free calendar throughout.
    """
    captured_at = datetime(2026, 1, 2, 9, 0, 0)
    observation = _obs(entry="100", captured_at=captured_at)

    # First pass: SUCCESS window.
    success_bars = (
        [("105", "99", "102")] + [("102", "100", "101")] * 8 + [("103", "100", "103")]
    )
    success_candles = _pad_window(success_bars)

    # Second pass: FAILURE window (same observation identity).
    failure_bars = (
        [("101", "95", "96")] + [("101", "98", "99")] * 8 + [("100", "97", "98")]
    )
    failure_candles = _pad_window(failure_bars)

    db_path = tmp_path / "labels.db"
    labels_repo = SQLiteSignalForwardLabelsRepository(db_path)
    calendar = _gate_open_calendar()

    def _execute(candles: list[Candle]):
        return GenerateSignalForwardLabelsUseCase(
            candidate_observations_repository=FakeCandidateObservationsRepository(
                observation
            ),
            market_data_repository=FakeMarketDataRepository(candles),
            signal_forward_labels_repository=labels_repo,
            corporate_action_calendar_repository=calendar,
        ).execute(
            GenerateSignalForwardLabelsRequest(
                ticker="BBCA",
                signal_date=_SIGNAL_DATE,
                observation_captured_at=captured_at,
                horizons=(_HORIZON,),
            )
        )

    first = _execute(success_candles)
    assert first.labels[0].outcome_label == SignalForwardOutcome.SUCCESS
    assert first.labels[0].observation_captured_at == captured_at

    second = _execute(failure_candles)
    assert second.labels[0].outcome_label == SignalForwardOutcome.FAILURE
    assert second.labels[0].observation_captured_at == captured_at

    listed = labels_repo.list(
        signal_date=_SIGNAL_DATE, horizon=_HORIZON, ticker="BBCA"
    )
    assert len(listed) == 1
    assert listed[0].outcome_label == SignalForwardOutcome.FAILURE
    assert listed[0].observation_captured_at == captured_at
    assert listed[0].close_return == _approx(_pct_change_hand(Decimal("98")))
