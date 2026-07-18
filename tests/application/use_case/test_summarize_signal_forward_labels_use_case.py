from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from src.application.use_case.summarize_signal_forward_labels_use_case import (
    SummarizeSignalForwardLabelsRequest,
    SummarizeSignalForwardLabelsUseCase,
)
from src.domain.value_objects.signal_artifact_schema import (
    SIGNAL_FORWARD_LABEL_SCHEMA_VERSION,
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
            close_return=5.0,
        ),
        _label(
            ticker="BBRI",
            day=day,
            outcome=SignalForwardOutcome.FAILURE,
            setup_family="foreign_bounce",
            regime="RISK_OFF",
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
    assert ("coverage_bucket", "HIGH") not in by_group
    assert ("conviction_bucket", "HIGH") not in by_group


def test_summarize_groups_by_regime_attribution_fingerprint():
    """market_regime_at_signal / regime_confidence_bucket /
    regime_stability_at_signal / days_in_regime_bucket /
    regime_detection_method_at_signal buckets must be built from the
    persisted regime-attribution fingerprint fields."""
    day = date(2026, 7, 1)
    label = _label(
        ticker="BBCA",
        day=day,
        outcome=SignalForwardOutcome.SUCCESS,
        setup_family="foreign_bounce",
        regime="RISK_ON",
        close_return=5.0,
        regime_at_signal="BULLISH",
        regime_confidence_at_signal=0.85,
        regime_stability_at_signal="STABLE",
        days_in_regime_at_signal=4,
        regime_detection_method_at_signal=None,
    )
    repo = FakeSignalForwardLabelsRepository([label])

    response = SummarizeSignalForwardLabelsUseCase(repo).execute(
        SummarizeSignalForwardLabelsRequest(
            signal_date=day,
            horizon=SignalLabelHorizon.SWING_10D,
        )
    )

    by_group = {(bucket.group, bucket.key): bucket for bucket in response.buckets}
    assert by_group[("market_regime_at_signal", "BULLISH")].observation_count == 1
    assert by_group[("market_regime_at_signal", "BULLISH")].success_count == 1
    assert by_group[("regime_confidence_bucket", "HIGH")].observation_count == 1
    assert by_group[("regime_stability_at_signal", "STABLE")].observation_count == 1
    assert by_group[("days_in_regime_bucket", "D3_5")].observation_count == 1
    assert by_group[("regime_detection_method_at_signal", "UNKNOWN")].observation_count == 1
    # The pre-existing market_regime bucket (sourced from the nested dict
    # field, not the new flat field) is untouched by this change: _label()
    # only populated market_regime={"regime": "RISK_ON"} on the fingerprint,
    # so that bucket still works as before.
    assert by_group[("market_regime", "RISK_ON")].observation_count == 1
    assert by_group[("market_regime", "RISK_ON")].success_count == 1


def test_summarize_groups_by_setup_phase_and_sequence_validity():
    day = date(2026, 7, 1)
    label = _label(
        ticker="BBCA",
        day=day,
        outcome=SignalForwardOutcome.SUCCESS,
        setup_family="foreign_bounce",
        regime="RISK_ON",
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


def test_summarize_groups_by_saved_alpha_trigger_buckets():
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
            alpha_score=82.0,
            trigger_score=62.0,
            alpha_trigger_final_exact_score=70.0,
            alpha_trigger_horizon="SWING_10D",
            flow_trigger_allowed=True,
        ),
    )
    repo = FakeSignalForwardLabelsRepository([label])

    response = SummarizeSignalForwardLabelsUseCase(repo).execute(
        SummarizeSignalForwardLabelsRequest()
    )

    by_group = {(bucket.group, bucket.key): bucket for bucket in response.buckets}
    assert by_group[("alpha_bucket", "HIGH")].observation_count == 1
    assert by_group[("trigger_bucket", "MEDIUM")].observation_count == 1
    assert by_group[("alpha_trigger_final_bucket", "HIGH")].observation_count == 1
    assert by_group[("alpha_trigger_horizon", "SWING_10D")].observation_count == 1
    assert by_group[("flow_trigger_allowed", "True")].observation_count == 1


def test_summarize_groups_by_saved_institutional_accumulation_buckets():
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
            ia_foreign_track_coverage=0.8,
            ia_domestic_track_coverage=0.5,
            ia_foreign_track_conviction=0.3,
            ia_domestic_track_conviction=None,
        ),
    )
    repo = FakeSignalForwardLabelsRepository([label])

    response = SummarizeSignalForwardLabelsUseCase(repo).execute(
        SummarizeSignalForwardLabelsRequest()
    )

    by_group = {(bucket.group, bucket.key): bucket for bucket in response.buckets}
    assert by_group[("ia_foreign_track_coverage", "HIGH")].observation_count == 1
    assert by_group[("ia_domestic_track_coverage", "MEDIUM")].observation_count == 1
    assert by_group[("ia_foreign_track_conviction", "LOW")].observation_count == 1
    assert by_group[("ia_domestic_track_conviction", "UNKNOWN")].observation_count == 1


def test_summarize_groups_by_saved_ticker_profile_buckets():
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
            ticker_profile_label="foreign_institutional",
            tp_market_cap_bucket="large",
            tp_market_tier="blue_chip",
            tp_coverage_score=0.6,
        ),
    )
    repo = FakeSignalForwardLabelsRepository([label])

    response = SummarizeSignalForwardLabelsUseCase(repo).execute(
        SummarizeSignalForwardLabelsRequest()
    )

    by_group = {(bucket.group, bucket.key): bucket for bucket in response.buckets}
    assert by_group[("ticker_profile_label", "foreign_institutional")].observation_count == 1
    assert by_group[("tp_market_cap_bucket", "large")].observation_count == 1
    assert by_group[("tp_market_tier", "blue_chip")].observation_count == 1
    assert by_group[("tp_coverage_score", "MEDIUM")].observation_count == 1


def test_summarize_groups_by_volume_trigger_confirmation_buckets():
    day = date(2026, 7, 1)
    confirmed_label = SignalForwardLabel(
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
            volume_dry_up_confirmed=True,
            volume_expansion_confirmed=True,
            volume_trigger_confirmed=True,
        ),
    )
    unconfirmed_label = SignalForwardLabel(
        ticker="BBRI",
        signal_date=day,
        horizon=SignalLabelHorizon.SWING_10D,
        entry_reference_price=Decimal("100"),
        label_window_start=date(2026, 7, 2),
        label_window_end=date(2026, 7, 15),
        close_return=-2.0,
        max_forward_return=0.0,
        max_adverse_excursion=-2.0,
        days_to_peak=1,
        days_to_trough=2,
        stop_would_trigger=True,
        target_would_trigger=False,
        outcome_label=SignalForwardOutcome.FAILURE,
        unavailable_reason=None,
        fingerprint=SignalObservationFingerprint(
            volume_dry_up_confirmed=False,
            volume_expansion_confirmed=False,
            volume_trigger_confirmed=False,
        ),
    )
    unknown_label = SignalForwardLabel(
        ticker="TLKM",
        signal_date=day,
        horizon=SignalLabelHorizon.SWING_10D,
        entry_reference_price=Decimal("100"),
        label_window_start=date(2026, 7, 2),
        label_window_end=date(2026, 7, 15),
        close_return=1.0,
        max_forward_return=1.0,
        max_adverse_excursion=0.0,
        days_to_peak=1,
        days_to_trough=1,
        stop_would_trigger=False,
        target_would_trigger=False,
        outcome_label=SignalForwardOutcome.NEUTRAL,
        unavailable_reason=None,
        fingerprint=SignalObservationFingerprint(),
    )
    repo = FakeSignalForwardLabelsRepository(
        [confirmed_label, unconfirmed_label, unknown_label]
    )

    response = SummarizeSignalForwardLabelsUseCase(repo).execute(
        SummarizeSignalForwardLabelsRequest()
    )

    by_group = {(bucket.group, bucket.key): bucket for bucket in response.buckets}
    assert by_group[("volume_dry_up_confirmed", "True")].observation_count == 1
    assert by_group[("volume_dry_up_confirmed", "False")].observation_count == 1
    assert by_group[("volume_dry_up_confirmed", "UNKNOWN")].observation_count == 1
    assert by_group[("volume_expansion_confirmed", "True")].observation_count == 1
    assert by_group[("volume_expansion_confirmed", "False")].observation_count == 1
    assert by_group[("volume_expansion_confirmed", "UNKNOWN")].observation_count == 1
    assert by_group[("volume_trigger_confirmed", "True")].observation_count == 1
    assert by_group[("volume_trigger_confirmed", "False")].observation_count == 1
    assert by_group[("volume_trigger_confirmed", "UNKNOWN")].observation_count == 1
    assert by_group[("volume_trigger_confirmed", "True")].success_count == 1
    assert by_group[("volume_trigger_confirmed", "False")].failure_count == 1


def test_summarize_missing_phase_i_fields_as_unknown():
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
        fingerprint=SignalObservationFingerprint(),
    )
    repo = FakeSignalForwardLabelsRepository([label])

    response = SummarizeSignalForwardLabelsUseCase(repo).execute(
        SummarizeSignalForwardLabelsRequest()
    )

    by_group = {(bucket.group, bucket.key): bucket for bucket in response.buckets}
    assert by_group[("ia_foreign_track_coverage", "UNKNOWN")].observation_count == 1
    assert by_group[("ticker_profile_label", "UNKNOWN")].observation_count == 1
    assert by_group[("tp_market_cap_bucket", "UNKNOWN")].observation_count == 1
    assert by_group[("alpha_trigger_final_bucket", "UNKNOWN")].observation_count == 1
    assert by_group[("volume_dry_up_confirmed", "UNKNOWN")].observation_count == 1
    assert by_group[("volume_expansion_confirmed", "UNKNOWN")].observation_count == 1
    assert by_group[("volume_trigger_confirmed", "UNKNOWN")].observation_count == 1
    assert by_group[("signal_authority_coverage_bucket", "UNKNOWN")].observation_count == 1
    assert by_group[("setup_readiness_status", "UNKNOWN")].observation_count == 1
    assert by_group[("setup_readiness_current_phase", "UNKNOWN")].observation_count == 1
    assert by_group[("setup_readiness_missing_required_input", "NONE")].observation_count == 1
    assert by_group[("setup_readiness_failed_requirement", "NONE")].observation_count == 1


def test_summarize_groups_by_volatility_context_buckets():
    """volatility_bucket_at_signal / atr_pct_bucket / volatility_size_multiplier_bucket
    must be built from the persisted VolatilityContext fingerprint fields
    (atr_pct_at_signal=1.5 -> LT_2, atr_pct_at_signal=6.0 -> D5_8;
    volatility_size_multiplier_bucket formatted as f"{value:.2f}")."""
    day = date(2026, 7, 1)
    normal_label = SignalForwardLabel(
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
            atr_at_signal=1.5,
            atr_pct_at_signal=1.5,
            volatility_bucket_at_signal="NORMAL",
            volatility_size_multiplier_at_signal=1.0,
        ),
    )
    high_label = SignalForwardLabel(
        ticker="BBRI",
        signal_date=day,
        horizon=SignalLabelHorizon.SWING_10D,
        entry_reference_price=Decimal("100"),
        label_window_start=date(2026, 7, 2),
        label_window_end=date(2026, 7, 15),
        close_return=-2.0,
        max_forward_return=0.0,
        max_adverse_excursion=-2.0,
        days_to_peak=1,
        days_to_trough=2,
        stop_would_trigger=True,
        target_would_trigger=False,
        outcome_label=SignalForwardOutcome.FAILURE,
        unavailable_reason=None,
        fingerprint=SignalObservationFingerprint(
            atr_at_signal=6.0,
            atr_pct_at_signal=6.0,
            volatility_bucket_at_signal="HIGH",
            volatility_size_multiplier_at_signal=0.75,
        ),
    )
    unknown_label = SignalForwardLabel(
        ticker="TLKM",
        signal_date=day,
        horizon=SignalLabelHorizon.SWING_10D,
        entry_reference_price=Decimal("100"),
        label_window_start=date(2026, 7, 2),
        label_window_end=date(2026, 7, 15),
        close_return=1.0,
        max_forward_return=1.0,
        max_adverse_excursion=0.0,
        days_to_peak=1,
        days_to_trough=1,
        stop_would_trigger=False,
        target_would_trigger=False,
        outcome_label=SignalForwardOutcome.NEUTRAL,
        unavailable_reason=None,
        fingerprint=SignalObservationFingerprint(),
    )
    repo = FakeSignalForwardLabelsRepository([normal_label, high_label, unknown_label])

    response = SummarizeSignalForwardLabelsUseCase(repo).execute(
        SummarizeSignalForwardLabelsRequest()
    )

    by_group = {(bucket.group, bucket.key): bucket for bucket in response.buckets}

    assert by_group[("volatility_bucket_at_signal", "NORMAL")].observation_count == 1
    assert by_group[("volatility_bucket_at_signal", "NORMAL")].success_count == 1
    assert by_group[("volatility_bucket_at_signal", "HIGH")].observation_count == 1
    assert by_group[("volatility_bucket_at_signal", "HIGH")].failure_count == 1
    assert by_group[("volatility_bucket_at_signal", "UNKNOWN")].observation_count == 1

    assert by_group[("atr_pct_bucket", "LT_2")].observation_count == 1
    assert by_group[("atr_pct_bucket", "D5_8")].observation_count == 1
    assert by_group[("atr_pct_bucket", "UNKNOWN")].observation_count == 1

    assert by_group[("volatility_size_multiplier_bucket", "1.00")].observation_count == 1
    assert by_group[("volatility_size_multiplier_bucket", "0.75")].observation_count == 1
    assert by_group[("volatility_size_multiplier_bucket", "UNKNOWN")].observation_count == 1


# ---------------------------------------------------------------------------
# HIGH-2 Finding 4: canonical forward-label attribution
# ---------------------------------------------------------------------------


def test_summarize_excludes_legacy_schema_labels_from_canonical_attribution():
    """Test A: a schema-1 label with an extreme return must not enter the
    response or contaminate any bucket's counts/returns."""
    day = date(2026, 7, 1)
    canonical_label = _label(
        ticker="BBCA",
        day=day,
        outcome=SignalForwardOutcome.SUCCESS,
        setup_family="foreign_bounce",
        regime="RISK_ON",
        close_return=5.0,
    )
    assert canonical_label.schema_version == SIGNAL_FORWARD_LABEL_SCHEMA_VERSION
    legacy_label = SignalForwardLabel(
        ticker="BBRI",
        signal_date=day,
        horizon=SignalLabelHorizon.SWING_10D,
        entry_reference_price=Decimal("100"),
        label_window_start=date(2026, 7, 2),
        label_window_end=date(2026, 7, 15),
        close_return=999.0,
        max_forward_return=999.0,
        max_adverse_excursion=0.0,
        days_to_peak=1,
        days_to_trough=1,
        stop_would_trigger=False,
        target_would_trigger=True,
        outcome_label=SignalForwardOutcome.SUCCESS,
        unavailable_reason=None,
        fingerprint=SignalObservationFingerprint(setup_family="foreign_bounce"),
        schema_version=1,
    )
    repo = FakeSignalForwardLabelsRepository([canonical_label, legacy_label])

    response = SummarizeSignalForwardLabelsUseCase(repo).execute(
        SummarizeSignalForwardLabelsRequest(signal_date=day)
    )

    assert response.labels == (canonical_label,)
    by_group = {(bucket.group, bucket.key): bucket for bucket in response.buckets}
    bucket = by_group[("setup_family", "foreign_bounce")]
    assert bucket.observation_count == 1
    assert bucket.average_close_return == 5.0


def test_summarize_never_falls_back_to_legacy_coverage_or_conviction():
    """Test B: signal_authority_coverage drives the canonical bucket even
    when legacy coverage/conviction fields disagree; no legacy bucket must
    be emitted at all."""
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
            signal_authority_coverage=0.30,
            coverage=0.95,
            conviction=0.95,
        ),
    )
    repo = FakeSignalForwardLabelsRepository([label])

    response = SummarizeSignalForwardLabelsUseCase(repo).execute(
        SummarizeSignalForwardLabelsRequest()
    )

    by_group = {(bucket.group, bucket.key): bucket for bucket in response.buckets}
    assert by_group[("signal_authority_coverage_bucket", "LOW")].observation_count == 1
    assert not any(group == "coverage_bucket" for group, _ in by_group)
    assert not any(group == "conviction_bucket" for group, _ in by_group)


def test_summarize_returns_empty_when_only_legacy_labels_exist():
    """Test C: schema-1-only repository input must produce an empty
    response, never legacy labels surfaced as UNKNOWN buckets."""
    day = date(2026, 7, 1)
    legacy_label = SignalForwardLabel(
        ticker="BBCA",
        signal_date=day,
        horizon=SignalLabelHorizon.SWING_10D,
        entry_reference_price=Decimal("100"),
        label_window_start=date(2026, 7, 2),
        label_window_end=date(2026, 7, 15),
        close_return=1.0,
        max_forward_return=1.0,
        max_adverse_excursion=0.0,
        days_to_peak=1,
        days_to_trough=1,
        stop_would_trigger=False,
        target_would_trigger=False,
        outcome_label=SignalForwardOutcome.NEUTRAL,
        unavailable_reason=None,
        fingerprint=SignalObservationFingerprint(),
        schema_version=1,
    )
    repo = FakeSignalForwardLabelsRepository([legacy_label])

    response = SummarizeSignalForwardLabelsUseCase(repo).execute(
        SummarizeSignalForwardLabelsRequest()
    )

    assert response.labels == ()
    assert response.buckets == ()


def test_summarize_groups_by_typed_setup_readiness_attribution():
    """Test D: setup_readiness_status/current_phase/missing-required-input/
    failed-requirement attribution — absent maps to UNKNOWN, empty
    membership tuples map to NONE, duplicate/blank membership values
    collapse to one normalized entry per label, and bucket ordering is
    deterministic (sorted by group then key)."""
    day = date(2026, 7, 1)
    ready_label = SignalForwardLabel(
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
            setup_readiness_status="READY",
            setup_readiness_current_phase="BREAKOUT_CONFIRMATION",
        ),
    )
    incomplete_label = SignalForwardLabel(
        ticker="BBRI",
        signal_date=day,
        horizon=SignalLabelHorizon.SWING_10D,
        entry_reference_price=Decimal("100"),
        label_window_start=date(2026, 7, 2),
        label_window_end=date(2026, 7, 15),
        close_return=-2.0,
        max_forward_return=0.0,
        max_adverse_excursion=-2.0,
        days_to_peak=1,
        days_to_trough=2,
        stop_would_trigger=True,
        target_would_trigger=False,
        outcome_label=SignalForwardOutcome.FAILURE,
        unavailable_reason=None,
        fingerprint=SignalObservationFingerprint(
            setup_readiness_status="INCOMPLETE",
            setup_readiness_current_phase="ACCUMULATION_BASE",
            # Duplicate and blank values must collapse to one normalized
            # entry each; group totals may exceed the label count because
            # this single label contributes to two missing-input buckets.
            setup_readiness_missing_required_inputs=(
                "volume_confirmation",
                "  ",
                "volume_confirmation",
                "regime_check",
            ),
            setup_readiness_failed_requirements=("rsi_below_70", "", "rsi_below_70"),
        ),
    )
    unknown_label = SignalForwardLabel(
        ticker="TLKM",
        signal_date=day,
        horizon=SignalLabelHorizon.SWING_10D,
        entry_reference_price=Decimal("100"),
        label_window_start=date(2026, 7, 2),
        label_window_end=date(2026, 7, 15),
        close_return=1.0,
        max_forward_return=1.0,
        max_adverse_excursion=0.0,
        days_to_peak=1,
        days_to_trough=1,
        stop_would_trigger=False,
        target_would_trigger=False,
        outcome_label=SignalForwardOutcome.NEUTRAL,
        unavailable_reason=None,
        fingerprint=SignalObservationFingerprint(),
    )
    repo = FakeSignalForwardLabelsRepository([ready_label, incomplete_label, unknown_label])

    response = SummarizeSignalForwardLabelsUseCase(repo).execute(
        SummarizeSignalForwardLabelsRequest()
    )

    by_group = {(bucket.group, bucket.key): bucket for bucket in response.buckets}
    assert by_group[("setup_readiness_status", "READY")].observation_count == 1
    assert by_group[("setup_readiness_status", "INCOMPLETE")].observation_count == 1
    assert by_group[("setup_readiness_status", "UNKNOWN")].observation_count == 1
    assert by_group[("setup_readiness_current_phase", "BREAKOUT_CONFIRMATION")].observation_count == 1
    assert by_group[("setup_readiness_current_phase", "ACCUMULATION_BASE")].observation_count == 1
    assert by_group[("setup_readiness_current_phase", "UNKNOWN")].observation_count == 1

    # ready_label and unknown_label both have empty membership tuples -> NONE.
    assert by_group[("setup_readiness_missing_required_input", "NONE")].observation_count == 2
    assert by_group[("setup_readiness_missing_required_input", "regime_check")].observation_count == 1
    assert by_group[("setup_readiness_missing_required_input", "volume_confirmation")].observation_count == 1
    assert by_group[("setup_readiness_failed_requirement", "NONE")].observation_count == 2
    assert by_group[("setup_readiness_failed_requirement", "rsi_below_70")].observation_count == 1

    missing_input_keys = [
        bucket.key
        for bucket in response.buckets
        if bucket.group == "setup_readiness_missing_required_input"
    ]
    assert missing_input_keys == sorted(missing_input_keys)
    assert missing_input_keys == ["NONE", "regime_check", "volume_confirmation"]


def _label(
    *,
    ticker: str,
    day: date,
    outcome: SignalForwardOutcome,
    setup_family: str,
    regime: str,
    close_return: float,
    regime_at_signal: str | None = None,
    regime_confidence_at_signal: float | None = None,
    regime_stability_at_signal: str | None = None,
    days_in_regime_at_signal: int | None = None,
    regime_detection_method_at_signal: str | None = None,
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
            market_regime_at_signal=regime_at_signal,
            regime_confidence_at_signal=regime_confidence_at_signal,
            regime_stability_at_signal=regime_stability_at_signal,
            days_in_regime_at_signal=days_in_regime_at_signal,
            regime_detection_method_at_signal=regime_detection_method_at_signal,
        ),
        observation_captured_at=datetime(2026, 7, 1, 9, 0, 0),
    )
