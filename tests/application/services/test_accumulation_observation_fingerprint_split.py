"""Structural parity test for the accumulation observation fingerprint split.

Verifies that after splitting accumulation_observation_fingerprint.py into
section-specific modules, the composed payload preserves every key and value.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.application.services.accumulation_observation_fingerprint import (
    build_candidate_observation_payload,
)
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)

TOP_LEVEL_KEYS = frozenset({
    "schema_version",
    "artifact_type",
    "ticker",
    "snapshot_date",
    "captured_at",
    "workflow",
    "screen_result",
    "request",
    "sub_signal_fingerprint",
    "candidate",
    "signal",
    "trade_setup",
})


def _minimal_request(**overrides):
    values = dict(
        tickers=["BBCA"],
        window_days=7,
        min_net_buy_days=2,
        min_foreign_flow_score=0.0,
        min_signal_score=0.0,
        market_context=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _minimal_candidate(**overrides):
    values = dict(
        ticker="BBCA",
        window_days=7,
        net_buy_days=4,
        total_days=7,
        net_buy_ratio=0.7,
        total_net_value=Decimal("1000000"),
        consecutive_streak=2,
        foreign_vwap=Decimal("1000"),
        current_price=Decimal("1000"),
        vwap_discount_pct=0.0,
        rsi=55.0,
        trend="UP",
        foreign_flow_score=70.0,
        top_brokers=None,
        institutional_flag=False,
        avg_flow_ratio=5.0,
        bb_width_pctile=0.5,
        vwap_pct=2.0,
        bandar_detector=None,
        signal_assessment=None,
        trade_setup=None,
        to_dict=lambda: {"ticker": "BBCA"},
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class TestTopLevelKeysPreserved:
    def test_all_top_level_keys_present(self):
        candidate = _minimal_candidate()
        request = _minimal_request()
        payload = build_candidate_observation_payload(
            candidate=candidate,
            screen_result="pass",
            flow_ev=None,
            setup_phase=None,
            snapshot_date=date(2026, 7, 1),
            captured_at=datetime(2026, 7, 1, 10, 30, 0),
            request=request,
        )
        assert set(payload.keys()) == TOP_LEVEL_KEYS, (
            f"Top-level keys mismatch. "
            f"Extra: {set(payload.keys()) - TOP_LEVEL_KEYS}. "
            f"Missing: {TOP_LEVEL_KEYS - set(payload.keys())}"
        )

    def test_top_level_scalar_values(self):
        candidate = _minimal_candidate()
        request = _minimal_request()
        payload = build_candidate_observation_payload(
            candidate=candidate,
            screen_result="pass",
            flow_ev=None,
            setup_phase=None,
            snapshot_date=date(2026, 7, 1),
            captured_at=datetime(2026, 7, 1, 10, 30, 0),
            request=request,
        )
        assert payload["schema_version"] == CANDIDATE_OBSERVATION_SCHEMA_VERSION
        assert payload["artifact_type"] == "candidate_observation"
        assert payload["ticker"] == "BBCA"
        assert payload["snapshot_date"] == "2026-07-01"
        assert payload["captured_at"] == "2026-07-01T10:30:00"
        assert payload["workflow"] == "screen_accum"
        assert payload["screen_result"] == "pass"
        assert payload["signal"] is None
        assert payload["trade_setup"] is None

    def test_request_keys_preserved(self):
        candidate = _minimal_candidate()
        request = _minimal_request(
            window_days=30,
            min_net_buy_days=3,
            min_foreign_flow_score=40.0,
            min_signal_score=0.0,
        )
        payload = build_candidate_observation_payload(
            candidate=candidate,
            screen_result="pass",
            flow_ev=None,
            setup_phase=None,
            snapshot_date=date(2026, 7, 1),
            captured_at=datetime(2026, 7, 1, 10, 30, 0),
            request=request,
        )
        req = payload["request"]
        assert req["window_days"] == 30
        assert req["min_net_buy_days"] == 3
        assert req["min_foreign_flow_score"] == 40.0

    def test_candidate_dict_in_payload(self):
        candidate = _minimal_candidate()
        request = _minimal_request()
        payload = build_candidate_observation_payload(
            candidate=candidate,
            screen_result="pass",
            flow_ev=None,
            setup_phase=None,
            snapshot_date=date(2026, 7, 1),
            captured_at=datetime(2026, 7, 1, 10, 30, 0),
            request=request,
        )
        assert payload["candidate"] == {"ticker": "BBCA"}


# ── sub_signal_fingerprint section key presence ──
# These tests verify that every section produces its keys even when the
# underlying evidence is None (keys present with None/[], not missing).

class TestSubSignalFingerprintSections:
    """All sections must produce persisted keys even when evidence is None."""

    def test_setup_section_keys_present(self):
        fp = self._build_fingerprint()
        assert fp["setup_phase_current"] is None
        assert fp["setup_phase_previous"] is None
        assert fp["phase_sequence_valid"] is None
        assert fp["phase_age_sessions"] is None
        assert fp["phase_detection_strength"] is None
        assert fp["phase_reasons"] == []
        assert fp["phase_history"] == []
        assert fp["phase_input_coverage"] is None

    def test_volume_keys_present(self):
        fp = self._build_fingerprint()
        assert fp["volume_dry_up_ratio_at_signal"] is None
        assert fp["volume_expansion_ratio_at_signal"] is None
        assert fp["volume_dry_up_confirmed"] is None
        assert fp["volume_expansion_confirmed"] is None
        assert fp["volume_trigger_confirmed"] is None

    def test_strategy_section_keys_present(self):
        fp = self._build_fingerprint()
        assert fp["strategy_name"] is None
        assert fp["strategy_rule_name"] is None
        assert fp["strategy_evidence_route"] is None
        assert fp["strategy_coverage_score"] is None
        assert fp["strategy_conviction_score"] is None
        assert fp["strategy_freshness_score"] is None
        assert fp["strategy_rationale"] == []

    def test_ia_section_keys_present(self):
        fp = self._build_fingerprint()
        assert fp["institutional_accumulation_status"] is None
        assert fp["ia_cnfb_divergence_20d"] is None
        assert fp["ia_foreign_participation"] is None
        assert fp["ia_foreign_cr4"] is None
        assert fp["ia_domestic_broker_consistency"] is None
        assert fp["ia_coverage_score"] is None
        assert fp["ia_conviction_score"] is None

    def test_profile_section_keys_present(self):
        fp = self._build_fingerprint()
        assert fp["ticker_profile_label"] is None
        assert fp["ticker_profile_confidence"] is None
        assert fp["tp_market_cap_bucket"] is None
        assert fp["tp_market_tier"] is None
        assert fp["tp_coverage_score"] is None
        assert fp["tp_epoch"] is None

    def test_sector_section_keys_present(self):
        fp = self._build_fingerprint()
        assert fp["sc_sector"] is None
        assert fp["sc_peer_count"] is None
        assert fp["sc_sector_20d_return"] is None
        assert fp["sc_sector_vs_ihsg_20d"] is None
        assert fp["sc_sector_breadth"] is None
        assert fp["sc_ticker_vs_sector_rs"] is None
        assert fp["sc_sector_regime"] is None
        assert fp["sc_coverage_score"] is None

    def test_company_quality_section_keys_present(self):
        fp = self._build_fingerprint()
        assert fp["cq_valuation_score"] is None
        assert fp["cq_earnings_trend_score"] is None
        assert fp["cq_analyst_score"] is None
        assert fp["cq_insider_score"] is None
        assert fp["cq_seasonality_score"] is None
        assert fp["cq_aggregate_score"] is None
        assert fp["cq_coverage_score"] is None
        assert fp["cq_present_axis_count"] is None

    def test_alpha_trigger_section_keys_present(self):
        fp = self._build_fingerprint()
        assert fp["alpha_score"] is None
        assert fp["trigger_score"] is None
        assert fp["alpha_trigger_final_exact_score"] is None
        assert fp["alpha_trigger_horizon"] is None
        assert fp["alpha_trigger_alpha_weight"] is None
        assert fp["flow_trigger_allowed"] is None
        assert fp["alpha_trigger_route_metadata"] is None
        assert fp["alpha_trigger_unavailable_reasons"] == []

    def test_volatility_section_keys_present(self):
        fp = self._build_fingerprint()
        assert fp["atr_at_signal"] is None
        assert fp["atr_pct_at_signal"] is None
        assert fp["volatility_bucket_at_signal"] is None
        assert fp["volatility_size_multiplier_at_signal"] is None

    def test_market_context_section_keys_present(self):
        fp = self._build_fingerprint()
        assert fp["market_regime_at_signal"] is None
        assert fp["regime_confidence_at_signal"] is None
        assert fp["regime_stability_at_signal"] is None
        assert fp["days_in_regime_at_signal"] is None
        assert fp["regime_transition_warning_at_signal"] is None
        assert fp["regime_detection_method_at_signal"] is None

    def test_raw_candidate_keys_present(self):
        fp = self._build_fingerprint()
        assert fp["rsi_at_signal"] == 55.0
        assert fp["bb_width_pctile_at_signal"] == 0.5
        assert fp["vwap_position_at_signal"] == 2.0
        assert fp["volume_ratio_at_signal"] == 5.0
        assert fp["cnfb_20d_at_signal"] == 1000000.0
        assert fp["foreign_participation_at_signal"] == 0.7
        assert fp["foreign_concentration_at_signal"] is None  # flow_ev is None

    def test_setup_family_keys_present(self):
        fp = self._build_fingerprint()
        assert fp["setup_family"] is None
        assert fp["matched_setup_families"] == []
        assert fp["primary_setup_family"] is None
        assert fp["setup_family_source"] is None
        assert fp["setup_family_rationale"] == []
        assert fp["setup_name"] is None

    def test_signal_authority_coverage_and_readiness_present(self):
        fp = self._build_fingerprint()
        assert fp["signal_authority_coverage"] is None  # signal None → None
        assert fp["setup_readiness_status"] is None
        assert fp["setup_readiness_current_phase"] is None
        assert fp["setup_readiness_missing_required_inputs"] == []
        assert fp["setup_readiness_failed_requirements"] == []

    def test_decision_constraints_present(self):
        fp = self._build_fingerprint()
        assert fp["decision_constraints"] is None

    def test_domestic_broker_accumulation_is_none_when_no_bandar(self):
        fp = self._build_fingerprint()
        assert fp["domestic_broker_accumulation_at_signal"] is None

    def test_benchmark_excess_return_keys_present(self):
        fp = self._build_fingerprint()
        assert "benchmark_excess_return_5_session" in fp
        assert "benchmark_excess_return_20_session" in fp
        assert fp["benchmark_excess_return_5_session"] is None
        assert fp["benchmark_excess_return_20_session"] is None
        assert fp["benchmark_excess_return_authority_status"] == "DIAGNOSTIC_UNVALIDATED"

    # -- helpers --

    def _build_fingerprint(self) -> dict:
        return self._build_payload()["sub_signal_fingerprint"]

    def _build_payload(self) -> dict:
        candidate = _minimal_candidate()
        request = _minimal_request()
        return build_candidate_observation_payload(
            candidate=candidate,
            screen_result="pass",
            flow_ev=None,
            setup_phase=None,
            snapshot_date=date(2026, 7, 1),
            captured_at=datetime(2026, 7, 1, 10, 30, 0),
            request=request,
        )


def test_real_producer_payload_is_schema_4_with_sector_context_only():
    """SECTOR-CONTEXT-IDENTITY (Step 10): the real observation payload builder,
    driven by a real AssessSignalResponse, must emit schema 4 with non-empty
    route metadata containing sector_context and never market_context."""
    from src.domain.value_objects.setup_phase import SetupPhaseState
    from tests.application.use_case.signal_evidence_fixtures import (
        _flow_evidence,
        _phase_state,
        _req,
        _sector_context,
        _setup_evidence,
        _use_case,
    )

    response = _use_case().execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(capped_strength=0.50),
            setup_phase=_phase_state(SetupPhaseState.BREAKOUT_CONFIRMATION),
            sector_context_evidence=_sector_context("BULLISH"),
        )
    )
    assert response.alpha_trigger_score is not None

    candidate = _minimal_candidate(signal_assessment=response)
    payload = build_candidate_observation_payload(
        candidate=candidate,
        screen_result="pass",
        flow_ev=None,
        setup_phase=None,
        snapshot_date=date(2026, 7, 1),
        captured_at=datetime(2026, 7, 1, 10, 30, 0),
        request=_minimal_request(),
        sc_evidence=_sector_context("BULLISH"),
    )

    assert payload["schema_version"] == CANDIDATE_OBSERVATION_SCHEMA_VERSION
    route_metadata = payload["sub_signal_fingerprint"]["alpha_trigger_route_metadata"]
    assert route_metadata  # non-empty
    groups = {entry["group"] for entry in route_metadata}
    assert "sector_context" in groups
    assert "market_context" not in groups


def test_real_producer_schema_4_fingerprint_parses_to_sector_context_route_only():
    """Parsing the schema-4 observation fingerprint (via
    SignalObservationFingerprint.from_dict) round-trips the route identity as
    sector_context only — no market_context leaks through serialization. This is
    a fingerprint-parsing check; the full producer -> observation repo -> label
    generator -> label repo round trip lives in
    test_generate_signal_forward_labels_use_case.py."""
    from src.domain.value_objects.signal_observation_fingerprint import (
        SignalObservationFingerprint,
    )
    from src.domain.value_objects.setup_phase import SetupPhaseState
    from tests.application.use_case.signal_evidence_fixtures import (
        _flow_evidence,
        _phase_state,
        _req,
        _sector_context,
        _setup_evidence,
        _use_case,
    )

    response = _use_case().execute(
        _req(
            setup_evidence=_setup_evidence("MATCH"),
            flow_confirmation_evidence=_flow_evidence(capped_strength=0.50),
            setup_phase=_phase_state(SetupPhaseState.BREAKOUT_CONFIRMATION),
            sector_context_evidence=_sector_context("BULLISH"),
        )
    )
    candidate = _minimal_candidate(signal_assessment=response)
    payload = build_candidate_observation_payload(
        candidate=candidate,
        screen_result="pass",
        flow_ev=None,
        setup_phase=None,
        snapshot_date=date(2026, 7, 1),
        captured_at=datetime(2026, 7, 1, 10, 30, 0),
        request=_minimal_request(),
        sc_evidence=_sector_context("BULLISH"),
    )

    # The label consumes the same fingerprint; round-trip it and confirm the
    # route identity is sector_context only.
    fingerprint = SignalObservationFingerprint.from_dict(payload["sub_signal_fingerprint"])
    groups = {entry["group"] for entry in fingerprint.alpha_trigger_route_metadata}
    assert "sector_context" in groups
    assert "market_context" not in groups
