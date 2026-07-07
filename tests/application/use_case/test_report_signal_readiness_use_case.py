from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from src.application.use_case.report_signal_readiness_use_case import (
    ReportSignalReadinessRequest,
    ReportSignalReadinessUseCase,
)
from src.domain.ports.candidate_observations_repository import CandidateObservation
from src.domain.value_objects.signal_forward_label import (
    SignalForwardLabel,
    SignalForwardOutcome,
    SignalLabelHorizon,
    SignalObservationFingerprint,
)

TARGET = "foreign_institutional_accumulation_large_cap_SWING_10D"


class FakeCandidateObservationsRepository:
    def __init__(self, observations_by_date):
        self.observations_by_date = observations_by_date

    def list_snapshot_dates(self):
        return sorted(self.observations_by_date)

    def list_by_date(self, snapshot_date):
        rows = list(self.observations_by_date.get(snapshot_date, ()))
        latest_by_ticker = {}
        for row in rows:
            current = latest_by_ticker.get(row.ticker)
            if current is None or row.captured_at > current.captured_at:
                latest_by_ticker[row.ticker] = row
        return [latest_by_ticker[ticker] for ticker in sorted(latest_by_ticker)]

    def list_all_by_date(self, snapshot_date):
        return list(self.observations_by_date.get(snapshot_date, ()))

    def save_many(self, observations):
        raise AssertionError("not used")

    def get_latest(self, ticker, snapshot_date):
        raise AssertionError("not used")

    def get_at(self, ticker, snapshot_date, captured_at):
        raise AssertionError("not used")

    def list_recent(self, ticker, *, before_date=None, limit=20):
        raise AssertionError("not used")


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
) -> CandidateObservation:
    return CandidateObservation(
        ticker=ticker,
        snapshot_date=snapshot_date,
        captured_at=captured_at,
        payload={
            "schema_version": 1,
            "ticker": ticker,
            "snapshot_date": snapshot_date.isoformat(),
            "sub_signal_fingerprint": fingerprint.to_dict(),
        },
    )


def _label(
    *,
    ticker: str,
    signal_date: date,
    close_return: float,
) -> SignalForwardLabel:
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
        fingerprint=_fingerprint(),
        observation_captured_at=datetime.combine(signal_date, datetime.min.time()),
    )


def _fingerprint(
    *,
    market_cap_bucket: str = "large",
) -> SignalObservationFingerprint:
    return SignalObservationFingerprint(
        setup_family="accumulation",
        ticker_profile_label="foreign_institutional",
        tp_market_cap_bucket=market_cap_bucket,
        alpha_trigger_horizon="SWING_10D",
        market_regime={"regime": "RISK_ON"},
        coverage=0.8,
        conviction=0.8,
    )
