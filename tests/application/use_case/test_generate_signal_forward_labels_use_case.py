from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from src.application.use_case.generate_signal_forward_labels_use_case import (
    GenerateAllSignalForwardLabelsRequest,
    GenerateEligibleSignalForwardLabelsRequest,
    GenerateSignalForwardLabelsRequest,
    GenerateSignalForwardLabelsUseCase,
    SignalLabelGenerationSkipReason,
)
from src.domain.entities.candle import Candle
from src.domain.ports.candidate_observations_repository import CandidateObservation
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)
from src.domain.value_objects.signal_forward_label import (
    SignalForwardOutcome,
    SignalLabelHorizon,
)


class FakeCandidateObservationsRepository:
    def __init__(self, observation=None, observations=None, observations_by_date=None):
        self.observation = observation
        self.observations = observations if observations is not None else []
        self.observations_by_date = observations_by_date or {}
        self.calls = []
        self.at_calls = []
        self.list_by_date_calls = []
        self.list_canonical_by_date_calls = []
        self.list_snapshot_dates_calls = 0

    def get_latest(self, ticker, snapshot_date):
        self.calls.append((ticker, snapshot_date))
        return self.observation

    def get_at(self, ticker, snapshot_date, captured_at):
        self.at_calls.append((ticker, snapshot_date, captured_at))
        return self.observation

    def list_by_date(self, snapshot_date):
        self.list_by_date_calls.append(snapshot_date)
        if self.observations_by_date:
            return list(self.observations_by_date.get(snapshot_date, ()))
        return list(self.observations)

    def list_canonical_by_date(self, snapshot_date):
        self.list_canonical_by_date_calls.append(snapshot_date)
        source = (
            self.observations_by_date.get(snapshot_date, ())
            if self.observations_by_date
            else self.observations
        )
        return [obs for obs in source if obs.config_hash]

    def list_snapshot_dates(self):
        self.list_snapshot_dates_calls += 1
        return sorted(self.observations_by_date)


class FakeMarketDataRepository:
    def __init__(self, candles):
        self.candles = candles
        self.calls = []

    def get_candles(self, ticker, start_date=None, end_date=None):
        self.calls.append((ticker, start_date, end_date))
        return [
            c
            for c in self.candles
            if c.ticker == ticker.upper()
            and (start_date is None or c.date >= start_date)
            and (end_date is None or c.date <= end_date)
        ]

    def save_candles(self, candles):
        raise AssertionError("not used")

    def has_data(self, ticker, start_date, end_date):
        raise AssertionError("not used")

    def get_date_range(self, ticker):
        raise AssertionError("not used")


class SpySignalForwardLabelsRepository:
    def __init__(self):
        self.saved = []
        self.save_many_call_count = 0

    def save_many(self, labels):
        self.save_many_call_count += 1
        self.saved.extend(labels)

    def get(self, ticker, signal_date, horizon):
        return None


def test_generates_swing_10d_success_label_from_saved_observation():
    signal_date = date(2026, 7, 1)
    observation = _observation(
        signal_date,
        {
            "candidate": {"current_price": "100"},
            "sub_signal_fingerprint": _fingerprint(),
        },
    )
    candles = [_candle(signal_date, "100")]
    candles.extend(_candle(signal_date + timedelta(days=i), str(100 + i)) for i in range(1, 11))
    labels_repo = SpySignalForwardLabelsRepository()

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(observation),
        market_data_repository=FakeMarketDataRepository(candles),
        signal_forward_labels_repository=labels_repo,
    ).execute(GenerateSignalForwardLabelsRequest(ticker="bbca", signal_date=signal_date))

    assert len(response.labels) == 1
    label = response.labels[0]
    assert label.horizon == SignalLabelHorizon.SWING_10D
    assert label.outcome_label == SignalForwardOutcome.SUCCESS
    assert label.close_return == 10.0
    assert label.max_forward_return == 10.0
    assert label.max_adverse_excursion == 1.0
    assert label.days_to_peak == 10
    assert label.days_to_trough == 1
    assert label.fingerprint.setup_family == "foreign_bounce"
    assert label.fingerprint.market_regime["regime"] == "RISK_ON"
    assert label.fingerprint.coverage is None
    assert label.fingerprint.conviction is None
    assert label.fingerprint.signal_authority_coverage == 0.5
    assert label.fingerprint.setup_readiness_status == "READY"
    assert label.fingerprint.setup_readiness_current_phase == "ACCUMULATION"
    assert label.fingerprint.setup_readiness_missing_required_inputs == ()
    assert label.fingerprint.setup_readiness_failed_requirements == ()
    assert label.fingerprint.phase_detection_strength == 0.8
    assert label.fingerprint.phase_input_coverage == 1.0
    assert labels_repo.saved == [label]

    from src.domain.value_objects.signal_artifact_schema import (
        SIGNAL_FORWARD_LABEL_SCHEMA_VERSION,
    )

    assert label.schema_version == SIGNAL_FORWARD_LABEL_SCHEMA_VERSION


def test_label_generator_output_serialization():
    signal_date = date(2026, 7, 1)
    observation = _observation(
        signal_date,
        {
            "candidate": {"current_price": "100"},
            "sub_signal_fingerprint": _fingerprint(),
        },
    )
    candles = [_candle(signal_date, "100")]
    candles.extend(_candle(signal_date + timedelta(days=i), str(100 + i)) for i in range(1, 11))

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(observation),
        market_data_repository=FakeMarketDataRepository(candles),
        signal_forward_labels_repository=SpySignalForwardLabelsRepository(),
    ).execute(GenerateSignalForwardLabelsRequest(ticker="bbca", signal_date=signal_date))

    assert len(response.labels) == 1
    label = response.labels[0]

    from src.domain.value_objects.signal_artifact_schema import (
        SIGNAL_FORWARD_LABEL_SCHEMA_VERSION,
    )
    assert label.schema_version == SIGNAL_FORWARD_LABEL_SCHEMA_VERSION

    # Serialize it
    payload = label.to_dict()
    fingerprint_payload = payload["fingerprint"]

    # Assert canonical authority/readiness fields are present
    assert fingerprint_payload["signal_authority_coverage"] == 0.5
    assert fingerprint_payload["setup_readiness_status"] == "READY"
    assert fingerprint_payload["setup_readiness_current_phase"] == "ACCUMULATION"
    assert fingerprint_payload["setup_readiness_missing_required_inputs"] == []
    assert fingerprint_payload["setup_readiness_failed_requirements"] == []
    assert fingerprint_payload["phase_detection_strength"] == 0.8
    assert fingerprint_payload["phase_input_coverage"] == 1.0

    # Assert none of the five forbidden aliases are present
    forbidden_keys = [
        "coverage",
        "conviction",
        "phase_strength",
        "phase_coverage_score",
        "phase_conviction_score",
    ]
    for key in forbidden_keys:
        assert key not in fingerprint_payload


def test_small_positive_swing_return_is_neutral_not_success():
    signal_date = date(2026, 7, 1)
    observation = _observation(
        signal_date,
        {"candidate": {"current_price": "100"}, "sub_signal_fingerprint": _fingerprint()},
    )
    candles = [_candle(signal_date + timedelta(days=i), "100.1") for i in range(1, 11)]

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(observation),
        market_data_repository=FakeMarketDataRepository(candles),
        signal_forward_labels_repository=SpySignalForwardLabelsRepository(),
    ).execute(GenerateSignalForwardLabelsRequest(ticker="BBCA", signal_date=signal_date))

    assert response.labels[0].close_return == 0.1
    assert response.labels[0].outcome_label == SignalForwardOutcome.NEUTRAL


def test_swing_failure_when_adverse_threshold_hits_before_target():
    signal_date = date(2026, 7, 1)
    observation = _observation(
        signal_date,
        {"candidate": {"current_price": "100"}, "sub_signal_fingerprint": _fingerprint()},
    )
    candles = [
        _candle(signal_date + timedelta(days=1), "99", low="95.9", high="101"),
        _candle(signal_date + timedelta(days=2), "104", low="99", high="104.1"),
    ]
    candles.extend(_candle(signal_date + timedelta(days=i), "103") for i in range(3, 11))

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(observation),
        market_data_repository=FakeMarketDataRepository(candles),
        signal_forward_labels_repository=SpySignalForwardLabelsRepository(),
    ).execute(GenerateSignalForwardLabelsRequest(ticker="BBCA", signal_date=signal_date))

    label = response.labels[0]
    assert label.stop_would_trigger is True
    assert label.target_would_trigger is True
    assert label.outcome_label == SignalForwardOutcome.FAILURE


def test_swing_success_when_target_hits_before_adverse_threshold():
    signal_date = date(2026, 7, 1)
    observation = _observation(
        signal_date,
        {"candidate": {"current_price": "100"}, "sub_signal_fingerprint": _fingerprint()},
    )
    candles = [
        _candle(signal_date + timedelta(days=1), "104", low="99", high="104.1"),
        _candle(signal_date + timedelta(days=2), "99", low="95.9", high="101"),
    ]
    candles.extend(_candle(signal_date + timedelta(days=i), "101") for i in range(3, 11))

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(observation),
        market_data_repository=FakeMarketDataRepository(candles),
        signal_forward_labels_repository=SpySignalForwardLabelsRepository(),
    ).execute(GenerateSignalForwardLabelsRequest(ticker="BBCA", signal_date=signal_date))

    label = response.labels[0]
    assert label.stop_would_trigger is True
    assert label.target_would_trigger is True
    assert label.outcome_label == SignalForwardOutcome.SUCCESS


def test_swing_same_day_target_stop_collision_is_conservative_failure():
    signal_date = date(2026, 7, 1)
    observation = _observation(
        signal_date,
        {"candidate": {"current_price": "100"}, "sub_signal_fingerprint": _fingerprint()},
    )
    candles = [
        _candle(signal_date + timedelta(days=1), "101", low="95.9", high="104.1"),
    ]
    candles.extend(_candle(signal_date + timedelta(days=i), "101") for i in range(2, 11))

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(observation),
        market_data_repository=FakeMarketDataRepository(candles),
        signal_forward_labels_repository=SpySignalForwardLabelsRepository(),
    ).execute(GenerateSignalForwardLabelsRequest(ticker="BBCA", signal_date=signal_date))

    label = response.labels[0]
    assert label.stop_would_trigger is True
    assert label.target_would_trigger is True
    assert label.outcome_label == SignalForwardOutcome.FAILURE


def test_request_can_target_specific_observation_capture_time():
    signal_date = date(2026, 7, 1)
    captured_at = datetime(2026, 7, 1, 9, 0, 0)
    observation = _observation(
        signal_date,
        {"candidate": {"current_price": "100"}, "sub_signal_fingerprint": _fingerprint()},
    )
    repo = FakeCandidateObservationsRepository(observation)
    candles = [_candle(signal_date + timedelta(days=i), "101") for i in range(1, 11)]

    GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=repo,
        market_data_repository=FakeMarketDataRepository(candles),
        signal_forward_labels_repository=SpySignalForwardLabelsRepository(),
    ).execute(
        GenerateSignalForwardLabelsRequest(
            ticker="BBCA",
            signal_date=signal_date,
            observation_captured_at=captured_at,
        )
    )

    assert repo.calls == []
    assert repo.at_calls == [("BBCA", signal_date, captured_at)]


def test_marks_incomplete_forward_window_unavailable_with_reason():
    signal_date = date(2026, 7, 1)
    observation = _observation(signal_date, {"candidate": {"current_price": "100"}})
    candles = [_candle(signal_date + timedelta(days=1), "101")]

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(observation),
        market_data_repository=FakeMarketDataRepository(candles),
        signal_forward_labels_repository=SpySignalForwardLabelsRepository(),
    ).execute(GenerateSignalForwardLabelsRequest(ticker="BBCA", signal_date=signal_date))

    label = response.labels[0]
    assert label.outcome_label == SignalForwardOutcome.UNAVAILABLE
    assert label.unavailable_reason == (
        "incomplete_forward_window: required 10 trading days, found 1"
    )
    assert label.close_return is None


def test_marks_missing_entry_price_unavailable_without_fetching_candles():
    signal_date = date(2026, 7, 1)
    observation = _observation(signal_date, {"candidate": {}})
    market_repo = FakeMarketDataRepository([])

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(observation),
        market_data_repository=market_repo,
        signal_forward_labels_repository=SpySignalForwardLabelsRepository(),
    ).execute(GenerateSignalForwardLabelsRequest(ticker="BBCA", signal_date=signal_date))

    label = response.labels[0]
    assert label.outcome_label == SignalForwardOutcome.UNAVAILABLE
    assert label.unavailable_reason == "missing_entry_reference_price"
    assert label.entry_reference_price is None
    assert market_repo.calls == []


@pytest.mark.parametrize(
    "schema_value",
    [1, 2, 3, 4, 6, None, "4", True],
)
def test_incompatible_observation_schema_produces_no_label_artifacts(schema_value):
    """HIGH-2 Finding 2: only an exact current-schema observation may produce
    a canonical forward label. Any other schema — old (incl. schema 4), future,
    missing, or a malformed non-int value like a numeric string or a bool —
    must be skipped entirely: no label, no fingerprint parse, no candle read,
    no repository write."""
    signal_date = date(2026, 7, 1)
    payload = {"candidate": {"current_price": "100"}, "schema_version": schema_value}
    # Deliberately malformed: if fingerprint parsing ran, this would raise
    # AttributeError (str has no .get) instead of being silently skipped.
    payload["sub_signal_fingerprint"] = "not-a-dict"
    observation = _observation(signal_date, payload)
    candles = [_candle(signal_date, "100")]
    candles.extend(_candle(signal_date + timedelta(days=i), str(100 + i)) for i in range(1, 11))
    labels_repo = SpySignalForwardLabelsRepository()
    market_repo = FakeMarketDataRepository(candles)

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(observation),
        market_data_repository=market_repo,
        signal_forward_labels_repository=labels_repo,
    ).execute(GenerateSignalForwardLabelsRequest(ticker="BBCA", signal_date=signal_date))

    assert response.labels == ()
    assert response.observation is observation
    assert (
        response.skip_reason
        is SignalLabelGenerationSkipReason.INCOMPATIBLE_OBSERVATION_SCHEMA
    )
    assert labels_repo.saved == []
    assert labels_repo.save_many_call_count == 0
    assert market_repo.calls == []


def test_incompatible_schema_response_reports_source_schema_version():
    signal_date = date(2026, 7, 1)
    observation = _observation(
        signal_date,
        {"schema_version": 2, "candidate": {"current_price": "100"}},
    )

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(observation),
        market_data_repository=FakeMarketDataRepository([]),
        signal_forward_labels_repository=SpySignalForwardLabelsRepository(),
    ).execute(GenerateSignalForwardLabelsRequest(ticker="BBCA", signal_date=signal_date))

    assert response.source_schema_version == 2


def test_new_labels_use_schema_2_and_only_schema_3_observations_are_eligible():
    """HIGH-2: new labels use SIGNAL_FORWARD_LABEL_SCHEMA_VERSION (2), and a
    canonical label can only be generated from a schema-3 observation."""
    from src.domain.value_objects.signal_artifact_schema import (
        SIGNAL_FORWARD_LABEL_SCHEMA_VERSION,
    )

    signal_date = date(2026, 7, 1)
    observation = _observation(
        signal_date,
        {"candidate": {"current_price": "100"}, "sub_signal_fingerprint": _fingerprint()},
    )
    candles = [_candle(signal_date, "100")]
    candles.extend(_candle(signal_date + timedelta(days=i), str(100 + i)) for i in range(1, 11))

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(observation),
        market_data_repository=FakeMarketDataRepository(candles),
        signal_forward_labels_repository=SpySignalForwardLabelsRepository(),
    ).execute(GenerateSignalForwardLabelsRequest(ticker="BBCA", signal_date=signal_date))

    label = response.labels[0]
    assert label.schema_version == SIGNAL_FORWARD_LABEL_SCHEMA_VERSION
    assert label.outcome_label == SignalForwardOutcome.SUCCESS
    assert response.skip_reason is None


def test_empty_horizons_request_performs_no_reads_or_writes():
    signal_date = date(2026, 7, 1)
    observation = _observation(
        signal_date,
        {"candidate": {"current_price": "100"}, "sub_signal_fingerprint": _fingerprint()},
    )
    labels_repo = SpySignalForwardLabelsRepository()
    market_repo = FakeMarketDataRepository([])

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(observation),
        market_data_repository=market_repo,
        signal_forward_labels_repository=labels_repo,
    ).execute(
        GenerateSignalForwardLabelsRequest(
            ticker="BBCA",
            signal_date=signal_date,
            horizons=(),
        )
    )

    assert response.labels == ()
    assert response.observation is observation
    assert response.skip_reason is None
    assert market_repo.calls == []
    assert labels_repo.saved == []
    assert labels_repo.save_many_call_count == 0


def test_generate_all_labels_latest_observations_for_date():
    signal_date = date(2026, 7, 1)
    observations = (
        _observation(
            signal_date,
            {"candidate": {"current_price": "100"}, "sub_signal_fingerprint": _fingerprint()},
            ticker="BBCA",
            captured_at=datetime(2026, 7, 1, 19, 0, 0),
        ),
        _observation(
            signal_date,
            {"candidate": {"current_price": "200"}, "sub_signal_fingerprint": _fingerprint()},
            ticker="BBRI",
            captured_at=datetime(2026, 7, 1, 19, 1, 0),
        ),
    )
    candles = []
    for ticker, entry in (("BBCA", 100), ("BBRI", 200)):
        candles.extend(
            _candle(signal_date + timedelta(days=i), str(entry + i), ticker=ticker)
            for i in range(1, 11)
        )
    observations_repo = FakeCandidateObservationsRepository(observations=observations)
    labels_repo = SpySignalForwardLabelsRepository()

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=observations_repo,
        market_data_repository=FakeMarketDataRepository(candles),
        signal_forward_labels_repository=labels_repo,
    ).execute_all(GenerateAllSignalForwardLabelsRequest(signal_date=signal_date))

    assert observations_repo.list_canonical_by_date_calls == [signal_date]
    assert response.observation_count == 2
    assert response.generated_count == 2
    assert response.unavailable_count == 0
    assert {label.ticker for label in response.labels} == {"BBCA", "BBRI"}
    assert labels_repo.saved == list(response.labels)


def test_generate_all_marks_incomplete_windows_unavailable():
    signal_date = date(2026, 7, 1)
    observation = _observation(
        signal_date,
        {"candidate": {"current_price": "100"}},
        ticker="BBCA",
    )

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(
            observations=[observation]
        ),
        market_data_repository=FakeMarketDataRepository(
            [_candle(signal_date + timedelta(days=1), "101", ticker="BBCA")]
        ),
        signal_forward_labels_repository=SpySignalForwardLabelsRepository(),
    ).execute_all(GenerateAllSignalForwardLabelsRequest(signal_date=signal_date))

    assert response.observation_count == 1
    assert response.generated_count == 1
    assert response.unavailable_count == 1
    assert response.labels[0].outcome_label is SignalForwardOutcome.UNAVAILABLE
    assert response.labels[0].unavailable_reason == (
        "incomplete_forward_window: required 10 trading days, found 1"
    )


def test_generate_all_labels_only_schema_3_observations_in_mixed_batch():
    """A batch mixing a canonical schema-3 observation with an incompatible
    schema-2 observation must label only the schema-3 row; the schema-2 row
    contributes zero labels, zero candle reads, and is excluded from
    observation_count, while being reflected in the skipped-incompatible
    count."""
    signal_date = date(2026, 7, 1)
    canonical = _observation(
        signal_date,
        {"candidate": {"current_price": "100"}, "sub_signal_fingerprint": _fingerprint()},
        ticker="BBCA",
    )
    incompatible = _observation(
        signal_date,
        {"schema_version": 2, "candidate": {"current_price": "200"}},
        ticker="BBRI",
    )
    candles = [
        _candle(signal_date + timedelta(days=i), str(100 + i), ticker="BBCA")
        for i in range(1, 11)
    ]
    observations_repo = FakeCandidateObservationsRepository(
        observations=[canonical, incompatible]
    )
    labels_repo = SpySignalForwardLabelsRepository()
    market_repo = FakeMarketDataRepository(candles)

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=observations_repo,
        market_data_repository=market_repo,
        signal_forward_labels_repository=labels_repo,
    ).execute_all(GenerateAllSignalForwardLabelsRequest(signal_date=signal_date))

    assert response.observation_count == 1
    assert response.generated_count == 1
    assert response.skipped_incompatible_observation_count == 1
    assert {label.ticker for label in response.labels} == {"BBCA"}
    assert labels_repo.saved == list(response.labels)
    assert all(call[0] == "BBCA" for call in market_repo.calls)


def test_generate_all_batch_of_only_incompatible_observations_writes_nothing():
    signal_date = date(2026, 7, 1)
    incompatible = _observation(
        signal_date,
        {"schema_version": 1, "candidate": {"current_price": "100"}},
        ticker="BBCA",
    )
    labels_repo = SpySignalForwardLabelsRepository()
    market_repo = FakeMarketDataRepository([])

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(
            observations=[incompatible]
        ),
        market_data_repository=market_repo,
        signal_forward_labels_repository=labels_repo,
    ).execute_all(GenerateAllSignalForwardLabelsRequest(signal_date=signal_date))

    assert response.labels == ()
    assert response.observation_count == 0
    assert response.generated_count == 0
    assert response.skipped_incompatible_observation_count == 1
    assert labels_repo.saved == []
    assert labels_repo.save_many_call_count == 0
    assert market_repo.calls == []


def test_generate_all_labels_covers_every_canonical_window_not_just_latest():
    """S1 regression: a ticker recorded across several window_sessions (e.g.
    7/30/90 from --multi-window backfill) must get a label for each canonical
    row, not just the most-recently-captured one. execute_all() must use
    list_canonical_by_date(), not list_by_date()'s latest-per-ticker collapse."""
    signal_date = date(2026, 7, 1)
    observations = (
        _observation(
            signal_date,
            {"candidate": {"current_price": "100"}, "sub_signal_fingerprint": _fingerprint()},
            ticker="BBCA",
            captured_at=datetime(2026, 7, 1, 19, 0, 0),
            window_sessions=7,
        ),
        _observation(
            signal_date,
            {"candidate": {"current_price": "100"}, "sub_signal_fingerprint": _fingerprint()},
            ticker="BBCA",
            captured_at=datetime(2026, 7, 1, 19, 1, 0),
            window_sessions=30,
        ),
        _observation(
            signal_date,
            {"candidate": {"current_price": "100"}, "sub_signal_fingerprint": _fingerprint()},
            ticker="BBCA",
            captured_at=datetime(2026, 7, 1, 19, 2, 0),
            window_sessions=90,
        ),
    )
    candles = [
        _candle(signal_date + timedelta(days=i), str(100 + i), ticker="BBCA")
        for i in range(1, 11)
    ]
    observations_repo = FakeCandidateObservationsRepository(observations=observations)
    labels_repo = SpySignalForwardLabelsRepository()

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=observations_repo,
        market_data_repository=FakeMarketDataRepository(candles),
        signal_forward_labels_repository=labels_repo,
    ).execute_all(GenerateAllSignalForwardLabelsRequest(signal_date=signal_date))

    # list_by_date() would have collapsed these 3 rows to 1 (latest captured_at).
    assert observations_repo.list_canonical_by_date_calls == [signal_date]
    assert observations_repo.list_by_date_calls == []
    assert response.observation_count == 3
    assert response.generated_count == 3
    assert len(labels_repo.saved) == 3


def test_generate_eligible_dates_skips_dates_without_forward_window():
    early = date(2026, 7, 1)
    recent = date(2026, 7, 10)
    observations_by_date = {
        early: [
            _observation(
                early,
                {"candidate": {"current_price": "100"}},
                ticker="BBCA",
            )
        ],
        recent: [
            _observation(
                recent,
                {"candidate": {"current_price": "100"}},
                ticker="BBRI",
            )
        ],
    }
    candles = [
        _candle(early + timedelta(days=i), str(100 + i), ticker="BBCA")
        for i in range(1, 11)
    ]
    candles.append(_candle(recent + timedelta(days=1), "101", ticker="BBRI"))
    observations_repo = FakeCandidateObservationsRepository(
        observations_by_date=observations_by_date
    )
    labels_repo = SpySignalForwardLabelsRepository()

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=observations_repo,
        market_data_repository=FakeMarketDataRepository(candles),
        signal_forward_labels_repository=labels_repo,
    ).execute_eligible_dates(
        GenerateEligibleSignalForwardLabelsRequest(horizon=SignalLabelHorizon.SWING_10D)
    )

    assert observations_repo.list_snapshot_dates_calls == 1
    assert response.generated_dates == (early,)
    assert response.skipped_dates == (recent,)
    assert response.observation_count == 1
    assert response.generated_count == 1
    assert response.unavailable_count == 0
    assert response.labels[0].ticker == "BBCA"
    assert labels_repo.saved == list(response.labels)


def test_generate_eligible_dates_excludes_incompatible_observations_from_batch():
    signal_date = date(2026, 7, 1)
    canonical = _observation(
        signal_date,
        {"candidate": {"current_price": "100"}, "sub_signal_fingerprint": _fingerprint()},
        ticker="BBCA",
    )
    incompatible = _observation(
        signal_date,
        {"schema_version": 3, "candidate": {"current_price": "200"}},
        ticker="BBRI",
    )
    candles = [
        _candle(signal_date + timedelta(days=i), str(100 + i), ticker="BBCA")
        for i in range(1, 11)
    ]
    observations_repo = FakeCandidateObservationsRepository(
        observations_by_date={signal_date: [canonical, incompatible]}
    )
    labels_repo = SpySignalForwardLabelsRepository()

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=observations_repo,
        market_data_repository=FakeMarketDataRepository(candles),
        signal_forward_labels_repository=labels_repo,
    ).execute_eligible_dates(
        GenerateEligibleSignalForwardLabelsRequest(horizon=SignalLabelHorizon.SWING_10D)
    )

    assert response.observation_count == 1
    assert response.generated_count == 1
    assert response.skipped_incompatible_observation_count == 1
    assert {label.ticker for label in response.labels} == {"BBCA"}
    assert labels_repo.saved == list(response.labels)


def test_build_label_raises_on_non_canonical_observation_as_a_programmer_error():
    """_build_label() is a private helper that every public entrypoint must
    filter before calling. If it is ever reached with a non-canonical
    observation, that is a contract violation in this use case's own code,
    not ordinary missing data — it must raise, not return an UNAVAILABLE
    label."""
    signal_date = date(2026, 7, 1)
    incompatible = _observation(signal_date, {"schema_version": 2})
    use_case = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(),
        market_data_repository=FakeMarketDataRepository([]),
        signal_forward_labels_repository=SpySignalForwardLabelsRepository(),
    )

    with pytest.raises(ValueError):
        use_case._build_label(incompatible, SignalLabelHorizon.SWING_10D)


def test_available_label_copies_provenance_from_source_observation():
    signal_date = date(2026, 7, 1)
    observation = _observation(
        signal_date,
        {
            "candidate": {"current_price": "100"},
            "sub_signal_fingerprint": _fingerprint(),
        },
        decision_at=datetime(2026, 7, 1, 16, 0, 0),
        latest_completed_session=signal_date,
        analysis_as_of=signal_date,
        market_session_name="AFTER_CLOSE",
        is_eod_pending=False,
        resolution_source="ihsg_cache_same_day",
        resolution_notes=("a note",),
    )
    candles = [_candle(signal_date + timedelta(days=i), str(100 + i)) for i in range(1, 11)]

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(observation),
        market_data_repository=FakeMarketDataRepository(candles),
        signal_forward_labels_repository=SpySignalForwardLabelsRepository(),
    ).execute(GenerateSignalForwardLabelsRequest(ticker="BBCA", signal_date=signal_date))

    label = response.labels[0]
    assert label.outcome_label != SignalForwardOutcome.UNAVAILABLE
    assert label.decision_at == observation.decision_at
    assert label.latest_completed_session == observation.latest_completed_session
    assert label.analysis_as_of == observation.analysis_as_of
    assert label.market_session_name == observation.market_session_name
    assert label.is_eod_pending == observation.is_eod_pending
    assert label.resolution_source == observation.resolution_source
    assert label.resolution_notes == observation.resolution_notes


def test_unavailable_label_copies_provenance_from_source_observation():
    signal_date = date(2026, 7, 1)
    observation = _observation(
        signal_date,
        {"candidate": {}},
        decision_at=datetime(2026, 7, 1, 16, 0, 0),
        latest_completed_session=signal_date,
        analysis_as_of=signal_date,
        market_session_name="AFTER_CLOSE",
        is_eod_pending=False,
        resolution_source="ihsg_cache_same_day",
        resolution_notes=("a note",),
    )

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(observation),
        market_data_repository=FakeMarketDataRepository([]),
        signal_forward_labels_repository=SpySignalForwardLabelsRepository(),
    ).execute(GenerateSignalForwardLabelsRequest(ticker="BBCA", signal_date=signal_date))

    label = response.labels[0]
    assert label.outcome_label == SignalForwardOutcome.UNAVAILABLE
    assert label.decision_at == observation.decision_at
    assert label.latest_completed_session == observation.latest_completed_session
    assert label.analysis_as_of == observation.analysis_as_of
    assert label.market_session_name == observation.market_session_name
    assert label.is_eod_pending == observation.is_eod_pending
    assert label.resolution_source == observation.resolution_source
    assert label.resolution_notes == observation.resolution_notes


def test_label_generation_does_not_resolve_a_new_session():
    """Provenance must be copied from the observation, never derived from
    signal_date or produced by a fresh resolver lookup during labeling.

    The labeler has no ``EffectiveMarketSessionResolver`` dependency; it
    inherits the originating observation's effective-session contract and
    propagates those exact values onto the label. A canonical swing
    observation under the clean-break contract always carries provenance
    equal to its snapshot_date.
    """
    signal_date = date(2026, 7, 1)
    decision_at = datetime(2026, 7, 1, 16, 0, 0)
    observation = _observation(
        signal_date,
        {"candidate": {"current_price": "100"}, "sub_signal_fingerprint": _fingerprint()},
        decision_at=decision_at,
        market_session_name="AFTER_CLOSE",
        is_eod_pending=False,
        resolution_source="ihsg_cache_same_day",
        resolution_notes=("a note",),
    )
    candles = [_candle(signal_date + timedelta(days=i), str(100 + i)) for i in range(1, 11)]

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(observation),
        market_data_repository=FakeMarketDataRepository(candles),
        signal_forward_labels_repository=SpySignalForwardLabelsRepository(),
    ).execute(GenerateSignalForwardLabelsRequest(ticker="BBCA", signal_date=signal_date))

    label = response.labels[0]
    # No resolver was injected into GenerateSignalForwardLabelsUseCase at all
    # (its constructor has no such dependency) — the label's provenance must
    # be inherited verbatim from the observation, not backfilled or re-resolved.
    assert label.decision_at == decision_at
    assert label.latest_completed_session == signal_date
    assert label.analysis_as_of == signal_date
    assert label.market_session_name == "AFTER_CLOSE"
    assert label.is_eod_pending is False
    assert label.resolution_source == "ihsg_cache_same_day"
    assert label.resolution_notes == ("a note",)


def test_real_producer_to_label_repository_round_trip_emits_only_sector_context(tmp_path):
    """SECTOR-CONTEXT-IDENTITY (Finding 2): a full real round trip —
    AssessSignalResponse -> observation payload builder -> SQLite observation
    repository -> label generator -> SQLite label repository -> readback — must
    actually generate and persist a label whose fingerprint route metadata
    carries sector_context only, never market_context."""
    from src.application.services.accumulation_observation_fingerprint import (
        build_candidate_observation_payload,
    )
    from src.domain.value_objects.setup_phase import SetupPhaseState
    from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
        SQLiteCandidateObservationsRepository,
    )
    from src.infrastructure.persistence.sqlite_signal_forward_labels_repository import (
        SQLiteSignalForwardLabelsRepository,
    )
    from tests.application.services.test_accumulation_observation_fingerprint_split import (
        _minimal_candidate,
        _minimal_request,
    )
    from tests.application.use_case.signal_evidence_fixtures import (
        _flow_evidence,
        _phase_state,
        _req,
        _sector_context,
        _setup_evidence,
        _use_case,
    )

    day = date(2026, 7, 1)

    # 1. Real signal assessment producing a sector_context Alpha/Trigger group.
    response = _use_case().execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(capped_strength=0.50),
            setup_phase=_phase_state(SetupPhaseState.BREAKOUT_CONFIRMATION),
            sector_context_evidence=_sector_context("BULLISH"),
        )
    )
    assert response.alpha_trigger_score is not None

    # 2. Real observation payload builder (schema 4).
    candidate = _minimal_candidate(
        ticker="BBCA",
        current_price=Decimal("1000"),
        signal_assessment=response,
    )
    payload = build_candidate_observation_payload(
        candidate=candidate,
        screen_result="pass",
        flow_ev=None,
        setup_phase=None,
        snapshot_date=day,
        captured_at=datetime(2026, 7, 1, 10, 30, 0),
        request=_minimal_request(),
        sc_evidence=_sector_context("BULLISH"),
    )
    assert payload["schema_version"] == CANDIDATE_OBSERVATION_SCHEMA_VERSION

    # 3. Persist through the real SQLite observation repository.
    db_path = tmp_path / "round_trip.db"
    observations_repo = SQLiteCandidateObservationsRepository(db_path)
    observations_repo.save_many(
        [
            CandidateObservation(
                ticker="BBCA",
                snapshot_date=day,
                captured_at=datetime(2026, 7, 1, 10, 30, 0),
                payload=payload,
                window_sessions=7,
                data_as_of_date=day,
                config_hash="round-trip-hash",
                decision_at=datetime(2026, 7, 1, 16, 0, 0),
                latest_completed_session=day,
                analysis_as_of=day,
            )
        ]
    )

    # 4. Generate a real label from rising forward candles.
    candles = [
        _candle(day, "1000", ticker="BBCA"),
        *[_candle(day + timedelta(days=i), "1050", ticker="BBCA") for i in range(1, 15)],
    ]
    labels_repo = SQLiteSignalForwardLabelsRepository(db_path)
    generator = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=observations_repo,
        market_data_repository=FakeMarketDataRepository(candles),
        signal_forward_labels_repository=labels_repo,
    )
    response_labels = generator.execute(
        GenerateSignalForwardLabelsRequest(ticker="BBCA", signal_date=day)
    )
    assert response_labels.skip_reason is None
    assert len(response_labels.labels) == 1

    # 5. Read the persisted label back and assert the route identity.
    persisted = tuple(labels_repo.list(signal_date=day))
    assert len(persisted) == 1
    groups = {
        entry["group"]
        for entry in persisted[0].fingerprint.alpha_trigger_route_metadata
    }
    assert "sector_context" in groups
    assert "market_context" not in groups


_PROVENANCE_DEFAULT = object()


def _observation(
    signal_date: date,
    payload: dict,
    *,
    ticker: str = "BBCA",
    captured_at: datetime = datetime(2026, 7, 1, 9, 0, 0),
    window_sessions: int = 7,
    config_hash: str = "test-hash",
    decision_at: datetime | None = None,
    latest_completed_session: date | None | object = _PROVENANCE_DEFAULT,
    analysis_as_of: date | None | object = _PROVENANCE_DEFAULT,
    market_session_name: str | None = None,
    is_eod_pending: bool | None = None,
    resolution_source: str | None = None,
    resolution_notes: tuple[str, ...] = (),
) -> CandidateObservation:
    # When omitted, default session provenance to signal_date so the
    # observation satisfies the canonical swing effective-session contract.
    # Pass `None` explicitly to construct an observation missing provenance
    # (e.g. for skip-reason tests).
    resolved_latest = (
        signal_date if latest_completed_session is _PROVENANCE_DEFAULT
        else latest_completed_session
    )
    resolved_as_of = (
        signal_date if analysis_as_of is _PROVENANCE_DEFAULT
        else analysis_as_of
    )
    payload = {
        "schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION,
        "artifact_type": "candidate_observation",
        "ticker": ticker,
        "snapshotDate": signal_date.isoformat(),
        **payload,
    }
    return CandidateObservation(
        ticker=ticker,
        snapshot_date=signal_date,
        captured_at=captured_at,
        payload=payload,
        window_sessions=window_sessions,
        data_as_of_date=signal_date,
        config_hash=config_hash,
        decision_at=decision_at,
        latest_completed_session=resolved_latest,
        analysis_as_of=resolved_as_of,
        market_session_name=market_session_name,
        is_eod_pending=is_eod_pending,
        resolution_source=resolution_source,
        resolution_notes=resolution_notes,
    )


def _candle(
    day: date,
    close: str,
    *,
    high: str | None = None,
    low: str | None = None,
    ticker: str = "BBCA",
) -> Candle:
    value = Decimal(close)
    return Candle(
        ticker=ticker,
        date=day,
        open=value,
        high=Decimal(high) if high is not None else value,
        low=Decimal(low) if low is not None else value,
        close=value,
        volume=1_000,
    )


def _fingerprint() -> dict:
    return {
        "setup_family": "foreign_bounce",
        "rsi_at_signal": 55.5,
        "bb_width_pctile_at_signal": 0.2,
        "vwap_position_at_signal": -1.5,
        "volume_ratio_at_signal": 12.3,
        "cnfb_20d_at_signal": 1_000_000,
        "foreign_participation_at_signal": 0.7,
        "foreign_concentration_at_signal": 0.6,
        "market_regime_at_signal": "RISK_ON",
        "signal_authority_coverage": 0.5,
        "setup_readiness_status": "READY",
        "setup_readiness_current_phase": "ACCUMULATION",
        "setup_readiness_missing_required_inputs": [],
        "setup_readiness_failed_requirements": [],
        "phase_detection_strength": 0.8,
        "phase_input_coverage": 1.0,
    }


class AdversarialCandidateObservationsRepository(FakeCandidateObservationsRepository):
    def list_canonical_by_date(self, snapshot_date):
        self.list_canonical_by_date_calls.append(snapshot_date)
        # Deliberately return the unfiltered list, allowing empty hashes and invalid schemas
        source = (
            self.observations_by_date.get(snapshot_date, ())
            if self.observations_by_date
            else self.observations
        )
        return list(source)


def test_single_path_canonical_observation_generates_labels():
    # 1. Exact schema 3 plus non-empty string config_hash still generates labels.
    day = date(2026, 7, 1)
    obs = CandidateObservation(
        ticker="BBCA",
        snapshot_date=day,
        captured_at=datetime(2026, 7, 1, 16, 0),
        payload={"schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION, "candidate": {"current_price": 100}},
        config_hash="valid_hash",
        latest_completed_session=day,
        analysis_as_of=day,
    )
    repo = FakeCandidateObservationsRepository(observation=obs)
    candles = [
        _candle(date(2026, 7, 1), "100", ticker="BBCA"),
        *[_candle(date(2026, 7, 1) + timedelta(days=i), "105", ticker="BBCA") for i in range(1, 15)]
    ]
    market = FakeMarketDataRepository(candles)
    labels_repo = SpySignalForwardLabelsRepository()
    use_case = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=repo,
        market_data_repository=market,
        signal_forward_labels_repository=labels_repo,
    )

    response = use_case.execute(
        GenerateSignalForwardLabelsRequest(ticker="BBCA", signal_date=date(2026, 7, 1))
    )
    assert response.skip_reason is None
    assert len(response.labels) == 1
    assert labels_repo.save_many_call_count == 1
    assert len(market.calls) > 0


def test_single_path_current_schema_empty_hash_rejected():
    # 2. Current schema plus config_hash="":
    # - returns no labels;
    # - returns NON_CANONICAL_OBSERVATION_IDENTITY;
    # - reports the current source schema version;
    # - performs zero candle reads;
    # - performs zero label writes.
    obs = CandidateObservation(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 1),
        captured_at=datetime(2026, 7, 1, 16, 0),
        payload={"schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION, "candidate": {"current_price": 100}},
        config_hash="",
    )
    repo = FakeCandidateObservationsRepository(observation=obs)
    market = FakeMarketDataRepository([])
    labels_repo = SpySignalForwardLabelsRepository()
    use_case = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=repo,
        market_data_repository=market,
        signal_forward_labels_repository=labels_repo,
    )

    response = use_case.execute(
        GenerateSignalForwardLabelsRequest(ticker="BBCA", signal_date=date(2026, 7, 1))
    )
    assert response.skip_reason == SignalLabelGenerationSkipReason.NON_CANONICAL_OBSERVATION_IDENTITY
    assert len(response.labels) == 0
    assert response.source_schema_version == CANDIDATE_OBSERVATION_SCHEMA_VERSION
    assert len(market.calls) == 0
    assert labels_repo.save_many_call_count == 0


@pytest.mark.parametrize(
    "bad_hash",
    [None, 0, False, b"hash"]
)
def test_single_path_parameterized_malformed_identity(bad_hash):
    # 3. Parameterize malformed identity values
    obs = CandidateObservation(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 1),
        captured_at=datetime(2026, 7, 1, 16, 0),
        payload={"schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION, "candidate": {"current_price": 100}},
        config_hash=bad_hash,
    )
    repo = FakeCandidateObservationsRepository(observation=obs)
    market = FakeMarketDataRepository([])
    labels_repo = SpySignalForwardLabelsRepository()
    use_case = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=repo,
        market_data_repository=market,
        signal_forward_labels_repository=labels_repo,
    )

    response = use_case.execute(
        GenerateSignalForwardLabelsRequest(ticker="BBCA", signal_date=date(2026, 7, 1))
    )
    assert response.skip_reason == SignalLabelGenerationSkipReason.NON_CANONICAL_OBSERVATION_IDENTITY
    assert len(response.labels) == 0
    assert response.source_schema_version == CANDIDATE_OBSERVATION_SCHEMA_VERSION
    assert len(market.calls) == 0
    assert labels_repo.save_many_call_count == 0


def test_single_path_current_schema_with_removed_market_context_is_invalid_contract():
    # SECTOR-CONTEXT-IDENTITY: a stored schema-4 observation whose route
    # metadata still carries the removed market_context group is a contract
    # violation. The use case must not trust the repository to have validated
    # payload contents: it skips with INVALID_OBSERVATION_CONTRACT, parses no
    # fingerprint, reads no candles, and writes no labels.
    obs = CandidateObservation(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 1),
        captured_at=datetime(2026, 7, 1, 16, 0),
        payload={
            "schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION,
            "candidate": {"current_price": 100},
            "sub_signal_fingerprint": {
                "alpha_trigger_route_metadata": [
                    {"group": "market_context", "score": 75.0},
                ],
            },
        },
        config_hash="valid_hash",
    )
    repo = FakeCandidateObservationsRepository(observation=obs)
    market = FakeMarketDataRepository([])
    labels_repo = SpySignalForwardLabelsRepository()
    use_case = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=repo,
        market_data_repository=market,
        signal_forward_labels_repository=labels_repo,
    )

    response = use_case.execute(
        GenerateSignalForwardLabelsRequest(ticker="BBCA", signal_date=date(2026, 7, 1))
    )
    assert response.skip_reason == SignalLabelGenerationSkipReason.INVALID_OBSERVATION_CONTRACT
    assert len(response.labels) == 0
    assert response.source_schema_version == CANDIDATE_OBSERVATION_SCHEMA_VERSION
    assert len(market.calls) == 0
    assert labels_repo.save_many_call_count == 0


def test_single_path_schema_2_non_empty_hash_rejected_as_incompatible():
    # 4. Schema 2 plus non-empty config_hash remains INCOMPATIBLE_OBSERVATION_SCHEMA.
    obs = CandidateObservation(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 1),
        captured_at=datetime(2026, 7, 1, 16, 0),
        payload={"schema_version": 2, "candidate": {"current_price": 100}},
        config_hash="valid_hash",
    )
    repo = FakeCandidateObservationsRepository(observation=obs)
    market = FakeMarketDataRepository([])
    labels_repo = SpySignalForwardLabelsRepository()
    use_case = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=repo,
        market_data_repository=market,
        signal_forward_labels_repository=labels_repo,
    )

    response = use_case.execute(
        GenerateSignalForwardLabelsRequest(ticker="BBCA", signal_date=date(2026, 7, 1))
    )
    assert response.skip_reason == SignalLabelGenerationSkipReason.INCOMPATIBLE_OBSERVATION_SCHEMA
    assert response.source_schema_version == 2


def test_single_path_schema_2_empty_hash_precedence():
    # 5. Schema 2 plus empty config_hash returns the schema reason, proving precedence.
    obs = CandidateObservation(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 1),
        captured_at=datetime(2026, 7, 1, 16, 0),
        payload={"schema_version": 2, "candidate": {"current_price": 100}},
        config_hash="",
    )
    repo = FakeCandidateObservationsRepository(observation=obs)
    market = FakeMarketDataRepository([])
    labels_repo = SpySignalForwardLabelsRepository()
    use_case = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=repo,
        market_data_repository=market,
        signal_forward_labels_repository=labels_repo,
    )

    response = use_case.execute(
        GenerateSignalForwardLabelsRequest(ticker="BBCA", signal_date=date(2026, 7, 1))
    )
    assert response.skip_reason == SignalLabelGenerationSkipReason.INCOMPATIBLE_OBSERVATION_SCHEMA
    assert response.source_schema_version == 2


def test_single_path_get_at_follows_same_guard():
    # 6. get_at() follows exactly the same identity guard as get_latest().
    obs = CandidateObservation(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 1),
        captured_at=datetime(2026, 7, 1, 16, 0),
        payload={"schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION, "candidate": {"current_price": 100}},
        config_hash="",
    )
    repo = FakeCandidateObservationsRepository(observation=obs)
    market = FakeMarketDataRepository([])
    labels_repo = SpySignalForwardLabelsRepository()
    use_case = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=repo,
        market_data_repository=market,
        signal_forward_labels_repository=labels_repo,
    )

    # Trigger execute with explicit captured_at (which calls get_at())
    response = use_case.execute(
        GenerateSignalForwardLabelsRequest(
            ticker="BBCA",
            signal_date=date(2026, 7, 1),
            observation_captured_at=datetime(2026, 7, 1, 16, 0),
        )
    )
    assert response.skip_reason == SignalLabelGenerationSkipReason.NON_CANONICAL_OBSERVATION_IDENTITY
    assert len(repo.at_calls) == 1
    assert len(market.calls) == 0
    assert labels_repo.save_many_call_count == 0


def test_batch_path_defense_in_depth():
    # For execute_all(), prove:
    # - only the valid observation is labeled;
    # - invalid row increments skipped_incompatible_observation_count;
    # - no candle read occurs for the invalid ticker;
    # - persisted labels belong only to the valid observation.
    day = date(2026, 7, 1)
    valid_obs = CandidateObservation(
        ticker="BBCA",
        snapshot_date=day,
        captured_at=datetime(2026, 7, 1, 16, 0),
        payload={"schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION, "candidate": {"current_price": 100}},
        config_hash="valid_hash",
        latest_completed_session=day,
        analysis_as_of=day,
    )
    invalid_obs = CandidateObservation(
        ticker="BUMI",
        snapshot_date=date(2026, 7, 1),
        captured_at=datetime(2026, 7, 1, 16, 0),
        payload={"schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION, "candidate": {"current_price": 100}},
        config_hash="",
    )
    repo = AdversarialCandidateObservationsRepository(
        observations=[valid_obs, invalid_obs]
    )

    candles = [
        _candle(date(2026, 7, 1), "100", ticker="BBCA"),
        *[_candle(date(2026, 7, 1) + timedelta(days=i), "105", ticker="BBCA") for i in range(1, 15)]
    ]
    market = FakeMarketDataRepository(candles)
    labels_repo = SpySignalForwardLabelsRepository()
    use_case = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=repo,
        market_data_repository=market,
        signal_forward_labels_repository=labels_repo,
    )

    response = use_case.execute_all(
        GenerateAllSignalForwardLabelsRequest(signal_date=date(2026, 7, 1))
    )

    assert response.skipped_incompatible_observation_count == 1
    assert response.observation_count == 1
    assert response.generated_count == 1
    assert len(response.labels) == 1
    assert response.labels[0].ticker == "BBCA"

    # Assert invalid rows do not trigger candle reads
    assert "BUMI" not in [c[0] for c in market.calls]
    assert "BBCA" in [c[0] for c in market.calls]

    # Assert persisted labels belong only to valid observation
    assert len(labels_repo.saved) == 1
    assert labels_repo.saved[0].ticker == "BBCA"


def test_eligible_date_path_defense_in_depth():
    # Using the same adversarial behavior, prove:
    # - the invalid identity is excluded;
    # - the valid observation is processed normally;
    # - skipped count includes the invalid row;
    # - no label is persisted for the invalid row.
    day = date(2026, 7, 1)
    valid_obs = CandidateObservation(
        ticker="BBCA",
        snapshot_date=day,
        captured_at=datetime(2026, 7, 1, 16, 0),
        payload={"schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION, "candidate": {"current_price": 100}},
        config_hash="valid_hash",
        latest_completed_session=day,
        analysis_as_of=day,
    )
    invalid_obs = CandidateObservation(
        ticker="BUMI",
        snapshot_date=date(2026, 7, 1),
        captured_at=datetime(2026, 7, 1, 16, 0),
        payload={"schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION, "candidate": {"current_price": 100}},
        config_hash="",
    )
    repo = AdversarialCandidateObservationsRepository(
        observations_by_date={
            date(2026, 7, 1): [valid_obs, invalid_obs]
        }
    )

    candles = [
        _candle(date(2026, 7, 1), "100", ticker="BBCA"),
        *[_candle(date(2026, 7, 1) + timedelta(days=i), "105", ticker="BBCA") for i in range(1, 15)]
    ]
    market = FakeMarketDataRepository(candles)
    labels_repo = SpySignalForwardLabelsRepository()
    use_case = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=repo,
        market_data_repository=market,
        signal_forward_labels_repository=labels_repo,
    )

    response = use_case.execute_eligible_dates(
        GenerateEligibleSignalForwardLabelsRequest()
    )

    assert response.skipped_incompatible_observation_count == 1
    assert response.observation_count == 1
    assert response.generated_count == 1
    assert len(response.labels) == 1
    assert response.labels[0].ticker == "BBCA"

    # Assert invalid rows do not trigger candle reads
    assert "BUMI" not in [c[0] for c in market.calls]
    assert "BBCA" in [c[0] for c in market.calls]

    # Assert persisted labels belong only to valid observation
    assert len(labels_repo.saved) == 1
    assert labels_repo.saved[0].ticker == "BBCA"


def test_direct_builder_guard():
    # Call _build_label() with schema 3 and empty config_hash and assert it raises ValueError containing: non-empty config_hash
    obs = CandidateObservation(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 1),
        captured_at=datetime(2026, 7, 1, 16, 0),
        payload={"schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION, "candidate": {"current_price": 100}},
        config_hash="",
    )
    repo = FakeCandidateObservationsRepository(observation=obs)
    market = FakeMarketDataRepository([])
    labels_repo = SpySignalForwardLabelsRepository()
    use_case = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=repo,
        market_data_repository=market,
        signal_forward_labels_repository=labels_repo,
    )
    with pytest.raises(ValueError, match="non-empty config_hash"):
        use_case._build_label(obs, SignalLabelHorizon.SWING_10D)


def test_predicate_tests():
    # Directly test _is_canonical_observation():
    # schema 3 + non-empty string hash + provenance -> True
    # schema 3 + empty hash                        -> False
    # schema 2 + non-empty hash                     -> False
    from src.application.use_case.generate_signal_forward_labels_use_case import (
        _is_canonical_observation,
    )

    day = date(2026, 7, 1)
    obs_ok = CandidateObservation(
        ticker="BBCA",
        snapshot_date=day,
        captured_at=datetime(2026, 7, 1, 16, 0),
        payload={"schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION, "candidate": {"current_price": 100}},
        config_hash="valid_hash",
        latest_completed_session=day,
        analysis_as_of=day,
    )
    obs_empty = CandidateObservation(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 1),
        captured_at=datetime(2026, 7, 1, 16, 0),
        payload={"schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION, "candidate": {"current_price": 100}},
        config_hash="",
    )
    obs_schema2 = CandidateObservation(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 1),
        captured_at=datetime(2026, 7, 1, 16, 0),
        payload={"schema_version": 2, "candidate": {"current_price": 100}},
        config_hash="valid_hash",
    )

    assert _is_canonical_observation(obs_ok) is True
    assert _is_canonical_observation(obs_empty) is False
    assert _is_canonical_observation(obs_schema2) is False


# ── ARTIFACT-IDENTITY Slice 4: labels produced by the use case carry no identity ──


def test_generated_label_has_artifact_identity_none():
    """Labels produced by GenerateSignalForwardLabelsUseCase must have
    artifact_identity is None — no resolver or identity injection is wired."""
    signal_date = date(2026, 7, 1)
    observation = _observation(
        signal_date,
        {
            "candidate": {"current_price": "100"},
            "sub_signal_fingerprint": _fingerprint(),
        },
    )
    candles = [_candle(signal_date, "100")]
    candles.extend(_candle(signal_date + timedelta(days=i), str(100 + i)) for i in range(1, 11))

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(observation),
        market_data_repository=FakeMarketDataRepository(candles),
        signal_forward_labels_repository=SpySignalForwardLabelsRepository(),
    ).execute(GenerateSignalForwardLabelsRequest(ticker="bbca", signal_date=signal_date))

    assert len(response.labels) == 1
    assert response.labels[0].artifact_identity is None


# ── DQ-002 criterion 1: one application-layer effective-session contract ─────


def test_observation_missing_provenance_skipped_with_invalid_contract_reason():
    """A canonical-schema observation that lacks latest_completed_session or
    analysis_as_of cannot prove its point-in-time session provenance. Under
    the clean-break contract it must be rejected with
    INVALID_OBSERVATION_CONTRACT: no label, no candle read, no write."""
    signal_date = date(2026, 7, 1)
    observation = _observation(
        signal_date,
        {"candidate": {"current_price": "100"}, "sub_signal_fingerprint": _fingerprint()},
        latest_completed_session=None,
        analysis_as_of=None,
    )
    market_repo = FakeMarketDataRepository([])
    labels_repo = SpySignalForwardLabelsRepository()

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(observation),
        market_data_repository=market_repo,
        signal_forward_labels_repository=labels_repo,
    ).execute(GenerateSignalForwardLabelsRequest(ticker="BBCA", signal_date=signal_date))

    assert response.labels == ()
    assert response.skip_reason is SignalLabelGenerationSkipReason.INVALID_OBSERVATION_CONTRACT
    assert response.observation is observation
    assert market_repo.calls == []
    assert labels_repo.save_many_call_count == 0


def test_observation_with_snapshot_date_ahead_of_latest_completed_session_skipped():
    """A swing observation whose snapshot_date is later than its
    latest_completed_session is not anchored on the closed session — it is
    either intraday, stale, or corruptly written. It must be rejected as
    INVALID_OBSERVATION_CONTRACT."""
    signal_date = date(2026, 7, 2)
    observation = _observation(
        signal_date,
        {"candidate": {"current_price": "100"}, "sub_signal_fingerprint": _fingerprint()},
        latest_completed_session=date(2026, 7, 1),
        analysis_as_of=signal_date,
    )
    market_repo = FakeMarketDataRepository([])
    labels_repo = SpySignalForwardLabelsRepository()

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(observation),
        market_data_repository=market_repo,
        signal_forward_labels_repository=labels_repo,
    ).execute(GenerateSignalForwardLabelsRequest(ticker="BBCA", signal_date=signal_date))

    assert response.labels == ()
    assert response.skip_reason is SignalLabelGenerationSkipReason.INVALID_OBSERVATION_CONTRACT
    assert market_repo.calls == []


def test_observation_with_analysis_as_of_behind_snapshot_date_skipped():
    """A swing observation whose analysis_as_of is behind snapshot_date
    means analysis was performed at a different session than the snapshot.
    Reject it as INVALID_OBSERVATION_CONTRACT."""
    signal_date = date(2026, 7, 2)
    observation = _observation(
        signal_date,
        {"candidate": {"current_price": "100"}, "sub_signal_fingerprint": _fingerprint()},
        latest_completed_session=signal_date,
        analysis_as_of=date(2026, 7, 1),
    )
    market_repo = FakeMarketDataRepository([])
    labels_repo = SpySignalForwardLabelsRepository()

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(observation),
        market_data_repository=market_repo,
        signal_forward_labels_repository=labels_repo,
    ).execute(GenerateSignalForwardLabelsRequest(ticker="BBCA", signal_date=signal_date))

    assert response.labels == ()
    assert response.skip_reason is SignalLabelGenerationSkipReason.INVALID_OBSERVATION_CONTRACT
    assert market_repo.calls == []


def test_label_inherits_observation_effective_session_contract():
    """DQ-002 criterion 1: label generation must inherit and validate the
    originating observation's effective-session contract rather than
    independently resolving another session. The label's
    latest_completed_session and analysis_as_of must equal the
    observation's exactly, with no fresh resolution."""
    signal_date = date(2026, 7, 1)
    observation = _observation(
        signal_date,
        {"candidate": {"current_price": "100"}, "sub_signal_fingerprint": _fingerprint()},
        decision_at=datetime(2026, 7, 1, 16, 0, 0),
        market_session_name="AFTER_CLOSE",
        is_eod_pending=False,
        resolution_source="ihsg_cache_same_day",
    )
    candles = [_candle(signal_date + timedelta(days=i), str(100 + i)) for i in range(1, 11)]

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(observation),
        market_data_repository=FakeMarketDataRepository(candles),
        signal_forward_labels_repository=SpySignalForwardLabelsRepository(),
    ).execute(GenerateSignalForwardLabelsRequest(ticker="BBCA", signal_date=signal_date))

    label = response.labels[0]
    assert label.latest_completed_session == observation.latest_completed_session
    assert label.analysis_as_of == observation.analysis_as_of
    assert label.latest_completed_session == label.analysis_as_of == signal_date
    assert label.decision_at == observation.decision_at
    assert label.market_session_name == observation.market_session_name
    assert label.resolution_source == observation.resolution_source


def test_execute_all_skips_observations_missing_provenance_without_candle_reads():
    """execute_all() must filter out observations missing session provenance
    before any candle read or label write. The skipped count reflects them
    alongside other incompatible observations."""
    signal_date = date(2026, 7, 1)
    valid = _observation(
        signal_date,
        {"candidate": {"current_price": "100"}, "sub_signal_fingerprint": _fingerprint()},
        ticker="BBCA",
    )
    missing_provenance = _observation(
        signal_date,
        {"candidate": {"current_price": "200"}, "sub_signal_fingerprint": _fingerprint()},
        ticker="BUMI",
        latest_completed_session=None,
        analysis_as_of=None,
    )
    candles = [
        _candle(signal_date + timedelta(days=i), str(100 + i), ticker="BBCA")
        for i in range(1, 11)
    ]
    observations_repo = FakeCandidateObservationsRepository(
        observations=[valid, missing_provenance]
    )
    market_repo = FakeMarketDataRepository(candles)
    labels_repo = SpySignalForwardLabelsRepository()

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=observations_repo,
        market_data_repository=market_repo,
        signal_forward_labels_repository=labels_repo,
    ).execute_all(GenerateAllSignalForwardLabelsRequest(signal_date=signal_date))

    assert response.observation_count == 1
    assert response.generated_count == 1
    assert response.skipped_incompatible_observation_count == 1
    assert {label.ticker for label in response.labels} == {"BBCA"}
    # The missing-provenance ticker never reaches the candle repository.
    assert all(call[0] == "BBCA" for call in market_repo.calls)
    assert labels_repo.saved == list(response.labels)


def test_forward_window_excludes_candle_at_signal_date():
    """Leakage regression: a candle whose date equals the observation's
    signal_date is in-session data — not a forward session — and must
    never appear in the label's forward window. The forward-candle slice
    relies on `c.date > signal_date`, which combined with the swing
    equality rule `signal_date == latest_completed_session` keeps the
    in-session candle out of the outcome calculation."""
    signal_date = date(2026, 7, 1)
    observation = _observation(
        signal_date,
        {"candidate": {"current_price": "100"}, "sub_signal_fingerprint": _fingerprint()},
    )
    # A same-day candle with a wildly different close must NOT move the
    # label's close_return, which is computed from the entry price and the
    # 10th forward-session close.
    same_day = _candle(signal_date, "999")
    forward = [_candle(signal_date + timedelta(days=i), str(100 + i)) for i in range(1, 11)]
    candles = [same_day, *forward]

    response = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(observation),
        market_data_repository=FakeMarketDataRepository(candles),
        signal_forward_labels_repository=SpySignalForwardLabelsRepository(),
    ).execute(GenerateSignalForwardLabelsRequest(ticker="BBCA", signal_date=signal_date))

    label = response.labels[0]
    assert label.outcome_label == SignalForwardOutcome.SUCCESS
    assert label.close_return == 10.0
    assert label.label_window_start == signal_date + timedelta(days=1)
    assert label.label_window_end == signal_date + timedelta(days=10)


def test_build_label_raises_on_observation_missing_provenance_as_programmer_error():
    """_build_label() is a private helper whose public entrypoints must
    filter invalid observations first. If it is ever reached with a
    provenance-missing observation, that is a contract violation in this
    use case's own code — it must raise, not silently produce an
    UNAVAILABLE label."""
    signal_date = date(2026, 7, 1)
    observation = _observation(
        signal_date,
        {"candidate": {"current_price": "100"}, "sub_signal_fingerprint": _fingerprint()},
        latest_completed_session=None,
        analysis_as_of=None,
    )
    use_case = GenerateSignalForwardLabelsUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(),
        market_data_repository=FakeMarketDataRepository([]),
        signal_forward_labels_repository=SpySignalForwardLabelsRepository(),
    )

    with pytest.raises(ValueError):
        use_case._build_label(observation, SignalLabelHorizon.SWING_10D)
