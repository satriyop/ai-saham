"""Characterization tests protecting the section-split of
signal_observation_fingerprint_serialization.py.

These tests pin the persisted schema (keys, aliases, defaults) so the
setup/strategy/flow/regime/context/alpha-trigger/volatility section modules
stay behavior-identical to the pre-split warehouse file.
"""

from src.domain.value_objects.signal_observation_fingerprint import (
    SignalObservationFingerprint,
)


def test_to_dict_contains_all_section_keys():
    fp = SignalObservationFingerprint()
    data = fp.to_dict()

    expected_keys = {
        # setup
        "setup_family",
        "matched_setup_families",
        "primary_setup_family",
        "setup_family_source",
        "setup_family_rationale",
        "setup_name",
        "setup_phase",
        "setup_phase_previous",
        "phase_sequence_valid",
        "phase_age_sessions",
        "phase_strength",
        "phase_reasons",
        "phase_history",
        "phase_coverage_score",
        "phase_conviction_score",
        # strategy
        "strategy_name",
        "strategy_rule_name",
        "strategy_rule_outcome",
        "strategy_evidence_route",
        "strategy_evidence_outcome",
        "strategy_coverage_score",
        "strategy_conviction_score",
        "strategy_freshness_score",
        "strategy_rationale",
        # flow
        "rsi",
        "bb_width_pctile",
        "vwap_position",
        "volume_ratio",
        "volume_dry_up_ratio",
        "volume_expansion_ratio",
        "volume_dry_up_confirmed",
        "volume_expansion_confirmed",
        "volume_trigger_confirmed",
        "cnfb",
        "foreign_participation",
        "foreign_concentration",
        "domestic_broker_accumulation",
        # regime
        "market_regime",
        "market_regime_at_signal",
        "regime_confidence_at_signal",
        "regime_stability_at_signal",
        "days_in_regime_at_signal",
        "regime_transition_warning_at_signal",
        "regime_detection_method_at_signal",
        "coverage",
        "conviction",
        # institutional accumulation
        "institutional_accumulation_status",
        "ia_foreign_participation",
        "ia_coverage_score",
        "ia_conviction_score",
        # ticker profile
        "ticker_profile_label",
        "tp_market_tier",
        "tp_coverage_score",
        "tp_epoch",
        # sector context
        "sc_sector",
        "sc_coverage_score",
        # company quality
        "cq_valuation_score",
        "cq_coverage_score",
        "cq_present_axis_count",
        # alpha/trigger
        "alpha_score",
        "trigger_score",
        "alpha_trigger_route_metadata",
        "alpha_trigger_unavailable_reasons",
        # volatility
        "atr_at_signal",
        "atr_pct_at_signal",
        "volatility_bucket_at_signal",
        "volatility_size_multiplier_at_signal",
        # benchmark excess return
        "benchmark_excess_return_5_session",
        "benchmark_excess_return_20_session",
        "benchmark_excess_return_authority_status",
    }

    missing = expected_keys - data.keys()
    assert not missing, f"missing persisted keys after split: {missing}"


def test_from_dict_accepts_legacy_flow_aliases():
    fp = SignalObservationFingerprint.from_dict(
        {
            "rsi_at_signal": 45.0,
            "bb_width_pctile_at_signal": 0.25,
            "vwap_position_at_signal": 1.02,
            # Legacy Task HIGH-1 field: must NOT be deserialized into the
            # corrected contract — SignalObservationFingerprint carries no
            # rs_vs_ihsg-shaped attribute to fall back into.
            "rs_vs_ihsg_20d_at_signal": -0.05,
            "volume_ratio_at_signal": 1.5,
            "volume_dry_up_ratio_at_signal": 0.4,
            "volume_expansion_ratio_at_signal": 2.0,
            "cnfb_20d_at_signal": 0.002,
            "foreign_participation_at_signal": 0.45,
            "foreign_concentration_at_signal": 0.6,
            "domestic_broker_accumulation_at_signal": 0.1,
        }
    )

    assert fp.rsi == 45.0
    assert fp.bb_width_pctile == 0.25
    assert fp.vwap_position == 1.02
    assert not hasattr(fp, "rs_vs_ihsg")
    assert "rs_vs_ihsg" not in fp.to_dict()
    assert fp.volume_ratio == 1.5
    assert fp.volume_dry_up_ratio == 0.4
    assert fp.volume_expansion_ratio == 2.0
    assert fp.cnfb == 0.002
    assert fp.foreign_participation == 0.45
    assert fp.foreign_concentration == 0.6
    assert fp.domestic_broker_accumulation == 0.1


def test_from_dict_reconstructs_nested_market_regime():
    fp = SignalObservationFingerprint.from_dict(
        {
            "market_regime": {
                "regime": "RISK_OFF",
                "regime_confidence": 0.4,
                "regime_stability": "TRANSITIONING",
                "days_in_regime": 0,
                "transition_warning": "narrowing",
            }
        }
    )

    assert fp.market_regime_at_signal == "RISK_OFF"
    assert fp.regime_confidence_at_signal == 0.4
    assert fp.regime_stability_at_signal == "TRANSITIONING"
    assert fp.days_in_regime_at_signal == 0
    assert fp.days_in_regime_at_signal is not None
    assert fp.regime_transition_warning_at_signal == "narrowing"


def test_flat_market_regime_at_signal_wins_over_nested_dict():
    fp = SignalObservationFingerprint.from_dict(
        {
            "market_regime_at_signal": "RISK_ON",
            "market_regime": {"regime": "RISK_OFF"},
        }
    )

    assert fp.market_regime_at_signal == "RISK_ON"


def test_phase_history_round_trips_list_of_dicts():
    fp = SignalObservationFingerprint.from_dict(
        {
            "phase_history": [
                {"phase": "COMPRESSION", "age_sessions": 3},
                {"phase": "BREAKOUT_CONFIRMATION", "age_sessions": 1},
            ]
        }
    )

    assert fp.phase_history == (
        {"phase": "COMPRESSION", "age_sessions": 3},
        {"phase": "BREAKOUT_CONFIRMATION", "age_sessions": 1},
    )

    round_tripped = SignalObservationFingerprint.from_dict(fp.to_dict())
    assert round_tripped.phase_history == fp.phase_history
    assert isinstance(fp.to_dict()["phase_history"], list)
    assert fp.to_dict()["phase_history"] == [
        {"phase": "COMPRESSION", "age_sessions": 3},
        {"phase": "BREAKOUT_CONFIRMATION", "age_sessions": 1},
    ]


def test_alpha_trigger_route_metadata_round_trips_list_and_tuple_of_dicts():
    fp = SignalObservationFingerprint.from_dict(
        {
            "alpha_trigger_route_metadata": [
                {"route": "alpha_led", "weight": 0.6},
                {"route": "trigger_led", "weight": 0.4},
            ]
        }
    )

    assert fp.alpha_trigger_route_metadata == (
        {"route": "alpha_led", "weight": 0.6},
        {"route": "trigger_led", "weight": 0.4},
    )

    serialized = fp.to_dict()
    assert isinstance(serialized["alpha_trigger_route_metadata"], list)
    assert serialized["alpha_trigger_route_metadata"] == [
        {"route": "alpha_led", "weight": 0.6},
        {"route": "trigger_led", "weight": 0.4},
    ]

    round_tripped = SignalObservationFingerprint.from_dict(serialized)
    assert round_tripped.alpha_trigger_route_metadata == fp.alpha_trigger_route_metadata


def test_volatility_aliases_round_trip():
    fp = SignalObservationFingerprint.from_dict(
        {
            "atr_20": 4.5,
            "atr_pct": 4.5,
            "volatility_bucket": "NORMAL",
            "volatility_size_multiplier": 1.0,
        }
    )

    assert fp.atr_at_signal == 4.5
    assert fp.atr_pct_at_signal == 4.5
    assert fp.volatility_bucket_at_signal == "NORMAL"
    assert fp.volatility_size_multiplier_at_signal == 1.0

    round_tripped = SignalObservationFingerprint.from_dict(fp.to_dict())
    assert round_tripped.atr_at_signal == 4.5
    assert round_tripped.atr_pct_at_signal == 4.5
    assert round_tripped.volatility_bucket_at_signal == "NORMAL"
    assert round_tripped.volatility_size_multiplier_at_signal == 1.0


def test_benchmark_excess_return_serialization_round_trips():
    from src.domain.value_objects.benchmark_excess_return import BenchmarkExcessReturn, BenchmarkExcessReturnStatus
    from datetime import date
    r5 = BenchmarkExcessReturn(
        benchmark="IHSG",
        window_sessions=5,
        ticker_return_pct=10.0,
        benchmark_return_pct=2.0,
        excess_return_pct=8.0,
        window_start=date(2026, 7, 10),
        window_end=date(2026, 7, 17),
        common_session_count=6,
        status=BenchmarkExcessReturnStatus.AVAILABLE,
    )
    r20 = BenchmarkExcessReturn.unavailable(
        benchmark="IHSG",
        window_sessions=20,
        reason="insufficient_aligned_closes",
        common_session_count=15,
    )

    fp = SignalObservationFingerprint(
        benchmark_excess_return_5_session=r5,
        benchmark_excess_return_20_session=r20,
        benchmark_excess_return_authority_status="DIAGNOSTIC_UNVALIDATED",
    )

    serialized = fp.to_dict()
    assert serialized["benchmark_excess_return_5_session"] == {
        "benchmark": "IHSG",
        "window_sessions": 5,
        "ticker_return_pct": 10.0,
        "benchmark_return_pct": 2.0,
        "excess_return_pct": 8.0,
        "window_start": "2026-07-10",
        "window_end": "2026-07-17",
        "common_session_count": 6,
        "status": "AVAILABLE",
        "unavailable_reason": None,
    }
    assert serialized["benchmark_excess_return_20_session"] == {
        "benchmark": "IHSG",
        "window_sessions": 20,
        "ticker_return_pct": None,
        "benchmark_return_pct": None,
        "excess_return_pct": None,
        "window_start": None,
        "window_end": None,
        "common_session_count": 15,
        "status": "UNAVAILABLE",
        "unavailable_reason": "insufficient_aligned_closes",
    }
    assert serialized["benchmark_excess_return_authority_status"] == "DIAGNOSTIC_UNVALIDATED"

    round_tripped = SignalObservationFingerprint.from_dict(serialized)
    assert round_tripped.benchmark_excess_return_5_session == r5
    assert round_tripped.benchmark_excess_return_20_session == r20
    assert round_tripped.benchmark_excess_return_authority_status == "DIAGNOSTIC_UNVALIDATED"
