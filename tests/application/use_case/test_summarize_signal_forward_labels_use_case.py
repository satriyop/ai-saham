from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from src.application.use_case.summarize_signal_forward_labels_use_case import (
    SummarizeSignalForwardLabelsRequest,
    SummarizeSignalForwardLabelsUseCase,
)
from src.domain.value_objects.signal_forward_label import (
    SignalForwardLabel,
    SignalForwardOutcome,
    SignalLabelHorizon,
    SignalObservationFingerprint,
)


class FakeSignalForwardLabelsRepository:
    def __init__(self, labels):
        self.labels = labels
        self.calls = []

    def list(self, *, signal_date=None, horizon=None, ticker=None):
        self.calls.append((signal_date, horizon, ticker))
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


def test_summarize_uses_saved_label_fingerprints_for_attribution():
    day = date(2026, 7, 1)
    labels = [
        _label(
            ticker="BBCA",
            day=day,
            outcome=SignalForwardOutcome.SUCCESS,
            setup_family="foreign_bounce",
            regime="RISK_ON",
            coverage=0.8,
            conviction=0.9,
            close_return=5.0,
        ),
        _label(
            ticker="BBRI",
            day=day,
            outcome=SignalForwardOutcome.FAILURE,
            setup_family="foreign_bounce",
            regime="RISK_OFF",
            coverage=0.5,
            conviction=0.3,
            close_return=-3.0,
        ),
    ]
    repo = FakeSignalForwardLabelsRepository(labels)

    response = SummarizeSignalForwardLabelsUseCase(repo).execute(
        SummarizeSignalForwardLabelsRequest(
            signal_date=day,
            horizon=SignalLabelHorizon.SWING_10D,
        )
    )

    assert repo.calls == [(day, SignalLabelHorizon.SWING_10D, None)]
    by_group = {(bucket.group, bucket.key): bucket for bucket in response.buckets}
    assert by_group[("setup_family", "foreign_bounce")].observation_count == 2
    assert by_group[("setup_family", "foreign_bounce")].success_count == 1
    assert by_group[("setup_family", "foreign_bounce")].failure_count == 1
    assert by_group[("market_regime", "RISK_ON")].success_count == 1
    assert by_group[("market_regime", "RISK_OFF")].failure_count == 1
    assert by_group[("coverage_bucket", "HIGH")].observation_count == 1
    assert by_group[("coverage_bucket", "MEDIUM")].observation_count == 1
    assert by_group[("conviction_bucket", "HIGH")].observation_count == 1
    assert by_group[("conviction_bucket", "LOW")].observation_count == 1


def test_summarize_groups_by_setup_phase_and_sequence_validity():
    day = date(2026, 7, 1)
    label = _label(
        ticker="BBCA",
        day=day,
        outcome=SignalForwardOutcome.SUCCESS,
        setup_family="foreign_bounce",
        regime="RISK_ON",
        coverage=0.8,
        conviction=0.9,
        close_return=5.0,
    )
    label = SignalForwardLabel(
        **{
            **label.to_dict(),
            "signal_date": label.signal_date,
            "horizon": label.horizon,
            "entry_reference_price": label.entry_reference_price,
            "label_window_start": label.label_window_start,
            "label_window_end": label.label_window_end,
            "outcome_label": label.outcome_label,
            "fingerprint": SignalObservationFingerprint(
                setup_family="foreign_bounce",
                setup_phase="BREAKOUT_CONFIRMATION",
                phase_sequence_valid=True,
            ),
        }
    )
    repo = FakeSignalForwardLabelsRepository([label])

    response = SummarizeSignalForwardLabelsUseCase(repo).execute(
        SummarizeSignalForwardLabelsRequest()
    )

    by_group = {(bucket.group, bucket.key): bucket for bucket in response.buckets}
    assert by_group[("setup_phase", "BREAKOUT_CONFIRMATION")].observation_count == 1
    assert by_group[("phase_sequence_valid", "True")].observation_count == 1


def test_summarize_groups_by_saved_strategy_evidence_fields():
    day = date(2026, 7, 1)
    label = SignalForwardLabel(
        ticker="BBCA",
        signal_date=day,
        horizon=SignalLabelHorizon.SWING_10D,
        entry_reference_price=Decimal("100"),
        label_window_start=date(2026, 7, 2),
        label_window_end=date(2026, 7, 15),
        close_return=4.0,
        max_forward_return=5.0,
        max_adverse_excursion=-1.0,
        days_to_peak=2,
        days_to_trough=1,
        stop_would_trigger=False,
        target_would_trigger=True,
        outcome_label=SignalForwardOutcome.SUCCESS,
        unavailable_reason=None,
        fingerprint=SignalObservationFingerprint(
            strategy_name="Price Breakout",
            strategy_rule_name="close_breakout",
            strategy_evidence_outcome="MATCHED",
            strategy_evidence_route="strategy_yaml_supportive",
        ),
    )
    repo = FakeSignalForwardLabelsRepository([label])

    response = SummarizeSignalForwardLabelsUseCase(repo).execute(
        SummarizeSignalForwardLabelsRequest()
    )

    by_group = {(bucket.group, bucket.key): bucket for bucket in response.buckets}
    assert by_group[("strategy_name", "Price Breakout")].observation_count == 1
    assert by_group[("strategy_rule", "close_breakout")].observation_count == 1
    assert by_group[("strategy_outcome", "MATCHED")].observation_count == 1
    assert by_group[("strategy_route", "strategy_yaml_supportive")].observation_count == 1


def _label(
    *,
    ticker: str,
    day: date,
    outcome: SignalForwardOutcome,
    setup_family: str,
    regime: str,
    coverage: float,
    conviction: float,
    close_return: float,
) -> SignalForwardLabel:
    return SignalForwardLabel(
        ticker=ticker,
        signal_date=day,
        horizon=SignalLabelHorizon.SWING_10D,
        entry_reference_price=Decimal("100"),
        label_window_start=date(2026, 7, 2),
        label_window_end=date(2026, 7, 15),
        close_return=close_return,
        max_forward_return=max(close_return, 0.0),
        max_adverse_excursion=min(close_return, 0.0),
        days_to_peak=1,
        days_to_trough=1,
        stop_would_trigger=False,
        target_would_trigger=outcome == SignalForwardOutcome.SUCCESS,
        outcome_label=outcome,
        unavailable_reason=None,
        fingerprint=SignalObservationFingerprint(
            setup_family=setup_family,
            market_regime={"regime": regime},
            coverage=coverage,
            conviction=conviction,
        ),
        observation_captured_at=datetime(2026, 7, 1, 9, 0, 0),
    )
