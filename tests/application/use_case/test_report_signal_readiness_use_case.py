from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from src.application.use_case.report_signal_readiness_use_case import (
    ReportSignalReadinessRequest,
    ReportSignalReadinessUseCase,
    SignalReadinessTarget,
)
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

TARGET = "foreign_institutional_accumulation_large_cap_SWING_10D"
DIAGNOSTIC_TARGET = "foreign_institutional_accumulation_SWING_10D"


def _is_canonical(observation: CandidateObservation) -> bool:
    schema_version = observation.payload.get("schema_version")
    return (
        type(schema_version) is int
        and schema_version == CANDIDATE_OBSERVATION_SCHEMA_VERSION
        and observation.config_hash != ""
    )


class FakeCandidateObservationsRepository:
    def __init__(self, observations_by_date):
        self.observations_by_date = observations_by_date

    def list_canonical_snapshot_dates(self):
        return sorted(
            snapshot_date
            for snapshot_date, rows in self.observations_by_date.items()
            if any(_is_canonical(row) for row in rows)
        )

    def list_latest_canonical_by_date(self, snapshot_date):
        rows = [
            row
            for row in self.observations_by_date.get(snapshot_date, ())
            if _is_canonical(row)
        ]
        latest_by_ticker = {}
        for row in rows:
            current = latest_by_ticker.get(row.ticker)
            if current is None or row.captured_at > current.captured_at:
                latest_by_ticker[row.ticker] = row
        return [latest_by_ticker[ticker] for ticker in sorted(latest_by_ticker)]

    def list_canonical_by_date(self, snapshot_date):
        return [
            row
            for row in self.observations_by_date.get(snapshot_date, ())
            if _is_canonical(row)
        ]

    def save_many(self, observations):
        raise AssertionError("not used")

    def get_latest(self, ticker, snapshot_date):
        raise AssertionError("not used")

    def get_at(self, ticker, snapshot_date, captured_at):
        raise AssertionError("not used")

    def list_recent(self, ticker, *, before_date=None, limit=20):
        raise AssertionError("not used")

    def list_snapshot_dates(self):
        raise AssertionError("readiness must use canonical dates")

    def list_by_date(self, snapshot_date):
        raise AssertionError("readiness must use latest canonical rows")

    def list_all_by_date(self, snapshot_date):
        raise AssertionError("readiness must use raw canonical rows")


class FakeSignalForwardLabelsRepository:
    def __init__(self, labels=()):
        self.labels = list(labels)

    def list(self, *, signal_date=None, horizon=None, ticker=None):
        rows = list(self.labels)
        if signal_date is not None:
            rows = [row for row in rows if row.signal_date == signal_date]
        if horizon is not None:
            rows = [row for row in rows if row.horizon is horizon]
        if ticker is not None:
            rows = [row for row in rows if row.ticker == ticker.upper()]
        return rows

    def save_many(self, labels):
        raise AssertionError("not used")

    def get(self, ticker, signal_date, horizon):
        raise AssertionError("not used")

    def get_at(self, ticker, signal_date, horizon, observation_captured_at):
        raise AssertionError("not used")


def test_readiness_reports_observation_counts_and_label_blockers():
    day = date(2026, 7, 7)
    report = ReportSignalReadinessUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(
            {
                day: [
                    _observation(
                        "BBCA",
                        day,
                        _fingerprint(),
                        captured_at=datetime(2026, 7, 7, 18, 0, 0),
                    ),
                    _observation(
                        "BBCA",
                        day,
                        _fingerprint(),
                        captured_at=datetime(2026, 7, 7, 19, 0, 0),
                    ),
                    _observation("BBRI", day, _fingerprint(market_cap_bucket="mid")),
                ]
            }
        ),
        signal_forward_labels_repository=FakeSignalForwardLabelsRepository(),
    ).execute(ReportSignalReadinessRequest(target=TARGET))

    assert report.observation_dates == (day,)
    assert report.latest_observation_count == 2
    assert report.raw_latest_observation_count == 3
    assert report.target_filter_count == 1
    assert report.raw_target_filter_count == 2
    assert report.notes == (
        "Multi-window observations collapsed to latest per ticker for "
        "readiness to avoid duplicate ticker/day labels.",
    )
    assert report.label_count == 0
    assert report.unavailable_label_count == 0
    assert report.labeled_target_count == 0
    assert report.patch_eligible is False
    assert "no forward labels generated yet" in report.blockers
    assert "no available labels match target filter" in report.blockers


# ---------------------------------------------------------------------------
# HIGH-2 Finding 3: readiness must use only canonical observations
# ---------------------------------------------------------------------------


def test_readiness_reports_nothing_ready_from_legacy_only_observations():
    """A. Legacy-only database state: schema-1/2 or empty-config-hash
    observations must never surface as readiness-eligible."""
    day = date(2026, 7, 7)
    report = ReportSignalReadinessUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(
            {
                day: [
                    _observation("BBCA", day, _fingerprint(), schema_version=2),
                    _observation("BBRI", day, _fingerprint(), config_hash=""),
                ]
            }
        ),
        signal_forward_labels_repository=FakeSignalForwardLabelsRepository(),
    ).execute(ReportSignalReadinessRequest(target=TARGET))

    assert report.observation_dates == ()
    assert report.latest_observation_date is None
    assert report.latest_observation_count == 0
    assert report.raw_latest_observation_count == 0
    assert report.target_filter_count == 0
    assert report.raw_target_filter_count == 0
    assert report.patch_eligible is False


def test_readiness_latest_date_skips_a_newer_legacy_only_date():
    """B. A newer date with only legacy observations must not become the
    latest readiness date — the latest canonical date must win."""
    canonical_day = date(2026, 7, 1)
    legacy_day = date(2026, 7, 2)
    report = ReportSignalReadinessUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(
            {
                canonical_day: [_observation("BBCA", canonical_day, _fingerprint())],
                legacy_day: [
                    _observation(
                        "BBCA", legacy_day, _fingerprint(), schema_version=2
                    )
                ],
            }
        ),
        signal_forward_labels_repository=FakeSignalForwardLabelsRepository(),
    ).execute(ReportSignalReadinessRequest(target=TARGET))

    assert report.observation_dates == (canonical_day,)
    assert report.latest_observation_date == canonical_day


def test_readiness_newer_legacy_row_cannot_displace_canonical_row():
    """C. For the same ticker/date, a later-captured legacy row must not
    displace an earlier canonical row as the 'latest' observation."""
    day = date(2026, 7, 7)
    report = ReportSignalReadinessUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(
            {
                day: [
                    _observation(
                        "BBCA",
                        day,
                        _fingerprint(),
                        captured_at=datetime(2026, 7, 7, 18, 0, 0),
                    ),
                    _observation(
                        "BBCA",
                        day,
                        _fingerprint(),
                        captured_at=datetime(2026, 7, 7, 19, 0, 0),
                        schema_version=2,
                    ),
                ]
            }
        ),
        signal_forward_labels_repository=FakeSignalForwardLabelsRepository(),
    ).execute(ReportSignalReadinessRequest(target=TARGET))

    assert report.latest_observation_count == 1
    assert report.raw_latest_observation_count == 1
    assert report.target_filter_count == 1


def test_readiness_counts_every_canonical_window_raw_but_one_latest_per_ticker():
    """D. Multi-window canonical counts: three canonical windows (7/30/90) for
    one ticker/date — distinct identities because window_sessions differs —
    collapse to one latest-per-ticker row but all three remain in the raw
    canonical count. Rows must differ by window_sessions, not merely
    captured_at, since captured_at alone is metadata and would UPSERT into a
    single identity in the real repository."""
    day = date(2026, 7, 7)
    report = ReportSignalReadinessUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(
            {
                day: [
                    _observation(
                        "BBCA",
                        day,
                        _fingerprint(),
                        captured_at=datetime(2026, 7, 7, 18, 0, 0),
                        window_sessions=7,
                    ),
                    _observation(
                        "BBCA",
                        day,
                        _fingerprint(),
                        captured_at=datetime(2026, 7, 7, 18, 1, 0),
                        window_sessions=30,
                    ),
                    _observation(
                        "BBCA",
                        day,
                        _fingerprint(),
                        captured_at=datetime(2026, 7, 7, 18, 2, 0),
                        window_sessions=90,
                    ),
                ]
            }
        ),
        signal_forward_labels_repository=FakeSignalForwardLabelsRepository(),
    ).execute(ReportSignalReadinessRequest(target=TARGET))

    assert report.latest_observation_count == 1
    assert report.raw_latest_observation_count == 3


def test_readiness_target_counts_exclude_legacy_rows_in_mixed_batch():
    """E. Mixed canonical and legacy targets: only canonical matching
    observations contribute to target_filter_count/raw_target_filter_count."""
    day = date(2026, 7, 7)
    report = ReportSignalReadinessUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(
            {
                day: [
                    _observation("BBCA", day, _fingerprint()),
                    _observation("BBRI", day, _fingerprint(), schema_version=2),
                    _observation("TLKM", day, _fingerprint(), config_hash=""),
                ]
            }
        ),
        signal_forward_labels_repository=FakeSignalForwardLabelsRepository(),
    ).execute(ReportSignalReadinessRequest(target=TARGET))

    assert report.target_filter_count == 1
    assert report.raw_target_filter_count == 1


def test_readiness_can_be_patch_eligible_with_sufficient_is_oos_labels():
    day = date(2026, 7, 7)
    labels = tuple(
        _label(
            ticker=f"T{i:03d}",
            signal_date=day + timedelta(days=i),
            close_return=2.0,
        )
        for i in range(100)
    )

    report = ReportSignalReadinessUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(
            {day: [_observation("BBCA", day, _fingerprint())]}
        ),
        signal_forward_labels_repository=FakeSignalForwardLabelsRepository(labels),
    ).execute(ReportSignalReadinessRequest(target=TARGET))

    assert report.label_count == 100
    assert report.target_label_count == 100
    assert report.labeled_target_count == 100
    assert report.is_count == 70
    assert report.oos_count == 30
    assert report.diagnostic_ready is True
    assert report.patch_eligible is True
    assert report.blockers == ()


def _observation(
    ticker: str,
    snapshot_date: date,
    fingerprint: SignalObservationFingerprint,
    *,
    captured_at: datetime = datetime(2026, 7, 7, 19, 0, 0),
    schema_version: int = CANDIDATE_OBSERVATION_SCHEMA_VERSION,
    config_hash: str = "test-config-hash",
    window_sessions: int = 7,
) -> CandidateObservation:
    return CandidateObservation(
        ticker=ticker,
        snapshot_date=snapshot_date,
        captured_at=captured_at,
        payload={
            "schema_version": schema_version,
            "ticker": ticker,
            "snapshot_date": snapshot_date.isoformat(),
            "sub_signal_fingerprint": fingerprint.to_dict(),
        },
        config_hash=config_hash,
        window_sessions=window_sessions,
    )


def _label(
    *,
    ticker: str,
    signal_date: date,
    close_return: float,
    market_cap_bucket: str = "large",
    setup_family: str | None = "accumulation",
) -> SignalForwardLabel:
    fp = (
        _fingerprint(market_cap_bucket=market_cap_bucket, setup=setup_family)
        if setup_family is not None
        else _fingerprint_no_setup(market_cap_bucket=market_cap_bucket)
    )
    return SignalForwardLabel(
        ticker=ticker,
        signal_date=signal_date,
        horizon=SignalLabelHorizon.SWING_10D,
        entry_reference_price=Decimal("100"),
        label_window_start=signal_date + timedelta(days=1),
        label_window_end=signal_date + timedelta(days=10),
        close_return=close_return,
        max_forward_return=close_return,
        max_adverse_excursion=0.0,
        days_to_peak=1,
        days_to_trough=1,
        stop_would_trigger=False,
        target_would_trigger=True,
        outcome_label=SignalForwardOutcome.SUCCESS,
        unavailable_reason=None,
        fingerprint=fp,
        observation_captured_at=datetime.combine(signal_date, datetime.min.time()),
    )


def _fingerprint(
    *,
    market_cap_bucket: str = "large",
    setup: str = "accumulation",
) -> SignalObservationFingerprint:
    return SignalObservationFingerprint(
        setup_family=setup,
        ticker_profile_label="foreign_institutional",
        tp_market_cap_bucket=market_cap_bucket,
        alpha_trigger_horizon="SWING_10D",
        market_regime={"regime": "RISK_ON"},
        signal_authority_coverage=0.8,
    )


# ---------------------------------------------------------------------------
# Diagnostic target: parse and filter behaviour
# ---------------------------------------------------------------------------


def test_canonical_target_parse_extracts_market_cap_bucket():
    t = SignalReadinessTarget.parse(TARGET)
    assert t.profile == "foreign_institutional"
    assert t.setup_family == "accumulation"
    assert t.market_cap_bucket == "large"
    assert t.horizon is SignalLabelHorizon.SWING_10D
    assert t.is_diagnostic is False


def test_diagnostic_target_parse_has_no_market_cap_bucket():
    t = SignalReadinessTarget.parse(DIAGNOSTIC_TARGET)
    assert t.profile == "foreign_institutional"
    assert t.setup_family == "accumulation"
    assert t.market_cap_bucket is None
    assert t.horizon is SignalLabelHorizon.SWING_10D
    assert t.is_diagnostic is True


def test_invalid_target_still_raises():
    with pytest.raises(ValueError):
        SignalReadinessTarget.parse("bad_target_no_horizon")


def test_diagnostic_target_matches_unknown_cap_observations():
    """Observations with tp_market_cap_bucket=UNKNOWN must match the diagnostic target."""
    day = date(2026, 7, 7)
    report = ReportSignalReadinessUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(
            {
                day: [
                    _observation("BBCA", day, _fingerprint(market_cap_bucket="UNKNOWN")),
                    _observation("BBRI", day, _fingerprint(market_cap_bucket="UNKNOWN")),
                ]
            }
        ),
        signal_forward_labels_repository=FakeSignalForwardLabelsRepository(),
    ).execute(ReportSignalReadinessRequest(target=DIAGNOSTIC_TARGET))

    assert report.target_filter_count == 2


def test_canonical_target_excludes_unknown_cap_observations():
    """The same UNKNOWN-cap observations must NOT match the canonical large-cap target."""
    day = date(2026, 7, 7)
    report = ReportSignalReadinessUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(
            {
                day: [
                    _observation("BBCA", day, _fingerprint(market_cap_bucket="UNKNOWN")),
                    _observation("BBRI", day, _fingerprint(market_cap_bucket="UNKNOWN")),
                ]
            }
        ),
        signal_forward_labels_repository=FakeSignalForwardLabelsRepository(),
    ).execute(ReportSignalReadinessRequest(target=TARGET))

    assert report.target_filter_count == 0


def test_diagnostic_target_is_never_patch_eligible():
    """Even with 100 passing labels the diagnostic target must not be patch-eligible."""
    day = date(2026, 7, 7)
    labels = tuple(
        _label(
            ticker=f"T{i:03d}",
            signal_date=day + timedelta(days=i),
            close_return=2.0,
            market_cap_bucket="UNKNOWN",
        )
        for i in range(100)
    )

    report = ReportSignalReadinessUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(
            {
                day: [
                    _observation("BBCA", day, _fingerprint(market_cap_bucket="UNKNOWN")),
                ]
            }
        ),
        signal_forward_labels_repository=FakeSignalForwardLabelsRepository(labels),
    ).execute(ReportSignalReadinessRequest(target=DIAGNOSTIC_TARGET))

    assert report.diagnostic_ready is True
    assert report.patch_eligible is False


def test_diagnostic_target_note_in_report():
    day = date(2026, 7, 7)
    report = ReportSignalReadinessUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(
            {day: [_observation("BBCA", day, _fingerprint(market_cap_bucket="UNKNOWN"))]}
        ),
        signal_forward_labels_repository=FakeSignalForwardLabelsRepository(),
    ).execute(ReportSignalReadinessRequest(target=DIAGNOSTIC_TARGET))

    assert any("canonical large-cap target remains blocked" in note for note in report.notes)


def test_diagnostic_target_flagged_in_to_dict():
    day = date(2026, 7, 7)
    report = ReportSignalReadinessUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(
            {day: [_observation("BBCA", day, _fingerprint(market_cap_bucket="UNKNOWN"))]}
        ),
        signal_forward_labels_repository=FakeSignalForwardLabelsRepository(),
    ).execute(ReportSignalReadinessRequest(target=DIAGNOSTIC_TARGET))

    d = report.to_dict()
    assert d["is_diagnostic_target"] is True
    assert d["target_components"]["market_cap_bucket"] is None


def test_canonical_target_not_flagged_as_diagnostic_in_to_dict():
    day = date(2026, 7, 7)
    report = ReportSignalReadinessUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(
            {day: [_observation("BBCA", day, _fingerprint())]}
        ),
        signal_forward_labels_repository=FakeSignalForwardLabelsRepository(),
    ).execute(ReportSignalReadinessRequest(target=TARGET))

    d = report.to_dict()
    assert d["is_diagnostic_target"] is False
    assert d["target_components"]["market_cap_bucket"] == "large"


# ---------------------------------------------------------------------------
# Regression: missing setup_family must not match any setup-specific target
# ---------------------------------------------------------------------------


def test_diagnostic_target_excludes_missing_setup_family():
    """A fingerprint with setup_family=None/empty must not match even the diagnostic target."""
    day = date(2026, 7, 7)
    report = ReportSignalReadinessUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(
            {
                day: [
                    _observation("BBCA", day, _fingerprint_no_setup(market_cap_bucket="UNKNOWN")),
                ]
            }
        ),
        signal_forward_labels_repository=FakeSignalForwardLabelsRepository(
            [
                _label(
                    ticker="BBCA",
                    signal_date=day,
                    close_return=1.0,
                    market_cap_bucket="UNKNOWN",
                    setup_family=None,
                )
            ]
        ),
    ).execute(ReportSignalReadinessRequest(target=DIAGNOSTIC_TARGET))

    assert report.target_filter_count == 0
    assert report.labeled_target_count == 0


def test_canonical_target_excludes_missing_setup_family():
    """A fingerprint with setup_family=None/empty must not match the canonical target either."""
    day = date(2026, 7, 7)
    report = ReportSignalReadinessUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(
            {
                day: [
                    _observation("BBCA", day, _fingerprint_no_setup(market_cap_bucket="large")),
                ]
            }
        ),
        signal_forward_labels_repository=FakeSignalForwardLabelsRepository(
            [
                _label(
                    ticker="BBCA",
                    signal_date=day,
                    close_return=1.0,
                    setup_family=None,
                )
            ]
        ),
    ).execute(ReportSignalReadinessRequest(target=TARGET))

    assert report.target_filter_count == 0
    assert report.labeled_target_count == 0


def test_diagnostic_target_includes_unknown_cap_with_explicit_setup_family():
    """Diagnostic target must still match UNKNOWN-cap rows that DO have accumulation setup."""
    day = date(2026, 7, 7)
    report = ReportSignalReadinessUseCase(
        candidate_observations_repository=FakeCandidateObservationsRepository(
            {
                day: [
                    _observation("BBCA", day, _fingerprint(market_cap_bucket="UNKNOWN")),
                    _observation(
                        "BBRI", day, _fingerprint(market_cap_bucket="UNKNOWN", setup="foreign_bounce")
                    ),
                    _observation(
                        "TLKM", day, _fingerprint_no_setup(market_cap_bucket="UNKNOWN")
                    ),
                ]
            }
        ),
        signal_forward_labels_repository=FakeSignalForwardLabelsRepository(),
    ).execute(ReportSignalReadinessRequest(target=DIAGNOSTIC_TARGET))

    # BBCA (accumulation) + BBRI (foreign_bounce) match; TLKM (no setup) does not
    assert report.target_filter_count == 2


def _fingerprint_no_setup(
    *,
    market_cap_bucket: str = "large",
) -> SignalObservationFingerprint:
    return SignalObservationFingerprint(
        setup_family=None,
        ticker_profile_label="foreign_institutional",
        tp_market_cap_bucket=market_cap_bucket,
        alpha_trigger_horizon="SWING_10D",
        market_regime={"regime": "RISK_ON"},
        signal_authority_coverage=0.8,
    )
