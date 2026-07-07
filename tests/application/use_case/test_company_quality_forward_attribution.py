"""Company-quality (cq_*) forward-label attribution wiring tests.

Guards the gap where cq_* fields are persisted into candidate observations but
are NOT carried into SignalObservationFingerprint / the summarizer, which would
silently drop them from forward-label attribution.

Covers:
  1. SignalObservationFingerprint.from_dict preserves cq_* and round-trips.
  2. The summarizer groups cq_* buckets from persisted fingerprints.
  3. Missing cq_* fields degrade to UNKNOWN buckets, never crash.
  4. Non-DIAGNOSTIC config still emits DIAGNOSTIC evidence (no promotion path).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from src.application.services.company_quality_context_evidence_builder import (
    CompanyQualityContextConfig,
    CompanyQualityContextEvidenceBuilder,
    CompanyQualityContextRequest,
)
from src.application.use_case.summarize_signal_forward_labels_use_case import (
    SummarizeSignalForwardLabelsRequest,
    SummarizeSignalForwardLabelsUseCase,
)
from src.domain.value_objects.institutional_accumulation_evidence import EvidenceStatus
from src.domain.value_objects.signal_assessment import SignalContext
from src.domain.value_objects.signal_forward_label import (
    SignalForwardLabel,
    SignalForwardOutcome,
    SignalLabelHorizon,
    SignalObservationFingerprint,
)


class _FakeRepo:
    def __init__(self, labels):
        self.labels = labels

    def list(self, *, signal_date=None, horizon=None, ticker=None):
        return list(self.labels)

    def save_many(self, labels):
        raise AssertionError("not used")

    def get(self, ticker, signal_date, horizon):
        raise AssertionError("not used")

    def get_at(self, ticker, signal_date, horizon, observation_captured_at):
        raise AssertionError("not used")


def _label(fingerprint: SignalObservationFingerprint) -> SignalForwardLabel:
    return SignalForwardLabel(
        ticker="BBCA",
        signal_date=date(2026, 7, 1),
        horizon=SignalLabelHorizon.SWING_10D,
        entry_reference_price=Decimal("100"),
        label_window_start=date(2026, 7, 2),
        label_window_end=date(2026, 7, 15),
        close_return=5.0,
        max_forward_return=5.0,
        max_adverse_excursion=0.0,
        days_to_peak=1,
        days_to_trough=1,
        stop_would_trigger=False,
        target_would_trigger=True,
        outcome_label=SignalForwardOutcome.SUCCESS,
        unavailable_reason=None,
        fingerprint=fingerprint,
        observation_captured_at=datetime(2026, 7, 1, 9, 0, 0),
    )


# ── 1. from_dict preserves cq_* and round-trips ───────────────────────────────

def test_fingerprint_from_dict_preserves_cq_aggregate_score():
    fp = SignalObservationFingerprint.from_dict({"cq_aggregate_score": 72.0})
    assert fp.cq_aggregate_score == 72.0


def test_fingerprint_cq_fields_round_trip():
    original = SignalObservationFingerprint(
        cq_valuation_score=95.0,
        cq_earnings_trend_score=None,
        cq_analyst_score=70.0,
        cq_insider_score=60.0,
        cq_seasonality_score=55.0,
        cq_aggregate_score=73.3,
        cq_coverage_score=1.0,
        cq_present_axis_count=4,
    )
    restored = SignalObservationFingerprint.from_dict(original.to_dict())
    assert restored.cq_valuation_score == 95.0
    assert restored.cq_earnings_trend_score is None
    assert restored.cq_analyst_score == 70.0
    assert restored.cq_insider_score == 60.0
    assert restored.cq_seasonality_score == 55.0
    assert restored.cq_aggregate_score == 73.3
    assert restored.cq_coverage_score == 1.0
    assert restored.cq_present_axis_count == 4


def test_fingerprint_from_flat_sub_signal_fingerprint_keys():
    # Mirrors the real persistence path: cq_* land flat in sub_signal_fingerprint.
    flat = {
        "cq_valuation_score": 95.0,
        "cq_analyst_score": 70.0,
        "cq_insider_score": 50.0,
        "cq_seasonality_score": 30.0,
        "cq_aggregate_score": 66.0,
        "cq_coverage_score": 1.0,
        "cq_present_axis_count": 4,
    }
    fp = SignalObservationFingerprint.from_dict(flat)
    assert fp.cq_aggregate_score == 66.0
    assert fp.cq_present_axis_count == 4


# ── 2. summarizer groups cq_* buckets ─────────────────────────────────────────

def test_summarizer_groups_cq_fields():
    fp = SignalObservationFingerprint(
        cq_valuation_score=95.0,     # HIGH (/100)
        cq_analyst_score=30.0,       # LOW
        cq_insider_score=50.0,       # MEDIUM
        cq_seasonality_score=30.0,   # LOW
        cq_aggregate_score=66.0,     # MEDIUM
        cq_coverage_score=1.0,       # HIGH
        cq_present_axis_count=4,
    )
    repo = _FakeRepo([_label(fp)])
    resp = SummarizeSignalForwardLabelsUseCase(repo).execute(
        SummarizeSignalForwardLabelsRequest()
    )
    by_group = {(b.group, b.key): b for b in resp.buckets}
    assert ("cq_valuation_score", "HIGH") in by_group
    assert ("cq_analyst_score", "LOW") in by_group
    assert ("cq_insider_score", "MEDIUM") in by_group
    assert ("cq_seasonality_score", "LOW") in by_group
    assert ("cq_aggregate_score", "MEDIUM") in by_group
    assert ("cq_coverage_score", "HIGH") in by_group
    assert ("cq_present_axis_count", "4") in by_group
    assert by_group[("cq_aggregate_score", "MEDIUM")].success_count == 1


# ── 3. missing cq_* → UNKNOWN, not crash ──────────────────────────────────────

def test_summarizer_missing_cq_fields_bucket_unknown():
    fp = SignalObservationFingerprint()  # no cq_* values
    repo = _FakeRepo([_label(fp)])
    resp = SummarizeSignalForwardLabelsUseCase(repo).execute(
        SummarizeSignalForwardLabelsRequest()
    )
    by_group = {(b.group, b.key): b for b in resp.buckets}
    assert ("cq_aggregate_score", "UNKNOWN") in by_group
    assert ("cq_coverage_score", "UNKNOWN") in by_group
    assert ("cq_present_axis_count", "UNKNOWN") in by_group


# ── 4. non-DIAGNOSTIC config still emits DIAGNOSTIC ────────────────────────────

def test_config_status_is_forced_to_diagnostic_even_when_raw_config_says_production():
    # from_mapping() ignores evidence_status in the raw dict entirely — DIAGNOSTIC
    # is hardcoded in the builder, not configurable from the YAML.
    config = CompanyQualityContextConfig.from_mapping({"evidence_status": "PRODUCTION"})
    assert config.evidence_status == EvidenceStatus.DIAGNOSTIC
    builder = CompanyQualityContextEvidenceBuilder(config)
    ev = builder.build(
        CompanyQualityContextRequest(
            ticker="BBCA",
            snapshot_date=date(2026, 7, 1),
            signal_context=SignalContext(
                ticker="BBCA", snapshot_date=date(2026, 7, 1), forward_pe=8.0
            ),
        )
    )
    assert ev.evidence_status == EvidenceStatus.DIAGNOSTIC
