from src.domain.value_objects.signal_forward_label import SignalObservationFingerprint


def test_signal_observation_fingerprint_parses_setup_phase_fields():
    fp = SignalObservationFingerprint.from_dict(
        {
            "setup_family": "foreign-bounce",
            "setup_phase_current": "BREAKOUT_CONFIRMATION",
            "setup_phase_previous": "COMPRESSION",
            "phase_sequence_valid": True,
            "phase_age_sessions": 2,
            "phase_strength": 0.8,
            "phase_reasons": ["breakout: VWAP reclaim"],
            "phase_history": [{"phase": "COMPRESSION", "age_sessions": 3}],
            "phase_coverage_score": 1.0,
            "phase_conviction_score": 0.8,
        }
    )

    assert fp.setup_phase == "BREAKOUT_CONFIRMATION"
    assert fp.setup_phase_previous == "COMPRESSION"
    assert fp.phase_sequence_valid is True
    assert fp.phase_age_sessions == 2
    assert fp.phase_strength == 0.8
    assert fp.phase_reasons == ("breakout: VWAP reclaim",)
    assert fp.phase_history == ({"phase": "COMPRESSION", "age_sessions": 3},)
    assert fp.phase_coverage_score == 1.0
    assert fp.phase_conviction_score == 0.8
    assert fp.to_dict()["phase_sequence_valid"] is True
    assert fp.to_dict()["phase_history"] == [{"phase": "COMPRESSION", "age_sessions": 3}]


def test_signal_observation_fingerprint_preserves_setup_name_separately_from_family():
    """setup_name (the named setup, e.g. 'coiled-spring') must survive a
    to_dict/from_dict round trip independently of setup_family (e.g.
    'accumulation') — needed so replay/attribution can tell which named setup
    produced an observation, not just its broader family."""
    fp = SignalObservationFingerprint.from_dict(
        {
            "setup_family": "accumulation",
            "setup_name": "coiled-spring",
        }
    )

    assert fp.setup_family == "accumulation"
    assert fp.setup_name == "coiled-spring"

    round_tripped = SignalObservationFingerprint.from_dict(fp.to_dict())
    assert round_tripped.setup_name == "coiled-spring"
    assert round_tripped.setup_family == "accumulation"


def test_signal_observation_fingerprint_setup_name_defaults_to_none():
    fp = SignalObservationFingerprint.from_dict({"setup_family": "accumulation"})

    assert fp.setup_name is None
    assert fp.to_dict()["setup_name"] is None


def test_signal_observation_fingerprint_preserves_setup_family_resolution_fields():
    """matched_setup_families / primary_setup_family / setup_family_source /
    setup_family_rationale (PrimarySetupFamilyResolver's output) must survive
    a to_dict/from_dict round trip so replay/attribution can reconstruct how
    setup_family was resolved for a persisted observation."""
    fp = SignalObservationFingerprint.from_dict(
        {
            "matched_setup_families": ["breakout", "pullback"],
            "primary_setup_family": "breakout",
            "setup_family_source": "detected_screen_evidence",
            "setup_family_rationale": [
                "setup 'coiled-spring' matched screen gates -> family=breakout"
            ],
        }
    )

    assert fp.matched_setup_families == ("breakout", "pullback")
    assert fp.primary_setup_family == "breakout"
    assert fp.setup_family_source == "detected_screen_evidence"
    assert fp.setup_family_rationale == (
        "setup 'coiled-spring' matched screen gates -> family=breakout",
    )

    round_tripped = SignalObservationFingerprint.from_dict(fp.to_dict())
    assert round_tripped.matched_setup_families == ("breakout", "pullback")
    assert round_tripped.primary_setup_family == "breakout"
    assert round_tripped.setup_family_source == "detected_screen_evidence"
    assert round_tripped.setup_family_rationale == (
        "setup 'coiled-spring' matched screen gates -> family=breakout",
    )


def test_signal_observation_fingerprint_preserves_volume_trigger_evidence_fields():
    """volume_dry_up_ratio / volume_expansion_ratio / volume_dry_up_confirmed /
    volume_expansion_confirmed / volume_trigger_confirmed (Point 3 explicit
    dry-up/expansion volume trigger evidence) must survive a to_dict/from_dict
    round trip. The two float fields support the dual-key `_at_signal`
    fallback (matching rs_vs_ihsg/rs_vs_ihsg_20d_at_signal); the three boolean
    fields use a plain key with no `_at_signal` fallback."""
    fp = SignalObservationFingerprint.from_dict(
        {
            "volume_dry_up_ratio_at_signal": 0.4,
            "volume_expansion_ratio_at_signal": 2.0,
            "volume_dry_up_confirmed": True,
            "volume_expansion_confirmed": True,
            "volume_trigger_confirmed": True,
        }
    )

    assert fp.volume_dry_up_ratio == 0.4
    assert fp.volume_expansion_ratio == 2.0
    assert fp.volume_dry_up_confirmed is True
    assert fp.volume_expansion_confirmed is True
    assert fp.volume_trigger_confirmed is True

    round_tripped = SignalObservationFingerprint.from_dict(fp.to_dict())
    assert round_tripped.volume_dry_up_ratio == 0.4
    assert round_tripped.volume_expansion_ratio == 2.0
    assert round_tripped.volume_dry_up_confirmed is True
    assert round_tripped.volume_expansion_confirmed is True
    assert round_tripped.volume_trigger_confirmed is True


def test_signal_observation_fingerprint_volume_trigger_dual_key_fallback():
    """Proves the dual-key fallback works both ways: the non-suffixed key
    (as written by to_dict()) is read directly, without needing the
    `_at_signal` suffix."""
    fp = SignalObservationFingerprint.from_dict(
        {
            "volume_dry_up_ratio": 0.4,
            "volume_expansion_ratio": 2.0,
        }
    )

    assert fp.volume_dry_up_ratio == 0.4
    assert fp.volume_expansion_ratio == 2.0


def test_signal_observation_fingerprint_preserves_regime_attribution_fields():
    """market_regime_at_signal / regime_confidence_at_signal /
    regime_stability_at_signal / days_in_regime_at_signal /
    regime_transition_warning_at_signal / regime_detection_method_at_signal
    (Phase: regime confidence/stability/days-in-regime/transition-warning/
    detection-method attribution fingerprint) must survive a
    to_dict/from_dict round trip unchanged."""
    fp = SignalObservationFingerprint(
        market_regime_at_signal="BULLISH",
        regime_confidence_at_signal=0.72,
        regime_stability_at_signal="STABLE",
        days_in_regime_at_signal=4,
        regime_transition_warning_at_signal=None,
        regime_detection_method_at_signal=None,
    )

    round_tripped = SignalObservationFingerprint.from_dict(fp.to_dict())

    assert round_tripped.market_regime_at_signal == "BULLISH"
    assert round_tripped.regime_confidence_at_signal == 0.72
    assert round_tripped.regime_stability_at_signal == "STABLE"
    assert round_tripped.days_in_regime_at_signal == 4
    assert round_tripped.regime_transition_warning_at_signal is None
    assert round_tripped.regime_detection_method_at_signal is None


def test_signal_observation_fingerprint_regime_confidence_and_days_survive_zero_values():
    """Proves the `is not None` handling for regime_confidence_at_signal and
    days_in_regime_at_signal: a real 0.0 / 0 must survive a to_dict/from_dict
    round trip and must NOT be dropped or coerced to None by truthiness
    checks (`0.0` and `0` are falsy in Python but are valid, meaningful
    values here)."""
    fp = SignalObservationFingerprint(
        days_in_regime_at_signal=0,
        regime_confidence_at_signal=0.0,
    )

    assert fp.days_in_regime_at_signal == 0
    assert fp.regime_confidence_at_signal == 0.0

    round_tripped = SignalObservationFingerprint.from_dict(fp.to_dict())

    assert round_tripped.days_in_regime_at_signal == 0
    assert round_tripped.days_in_regime_at_signal is not None
    assert round_tripped.regime_confidence_at_signal == 0.0
    assert round_tripped.regime_confidence_at_signal is not None


def test_signal_observation_fingerprint_regime_attribution_backward_compat_nested_dict():
    """Backward-compat: older persisted payloads only had the nested
    `market_regime` dict (no flat `*_at_signal` keys). from_dict must derive
    the new flat regime-attribution fields from that nested dict, including
    days_in_regime_at_signal == 0 (not None) to prove the numeric fallback
    also uses `is not None`, not truthiness."""
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
    # No nested-dict fallback exists for detection-method (MarketContext
    # never had this field, so there's nothing to reconstruct from).
    assert fp.regime_detection_method_at_signal is None


def test_signal_observation_fingerprint_regime_attribution_flat_key_precedence():
    """When both the flat key and the nested `market_regime` dict are
    present, the flat key must win."""
    fp = SignalObservationFingerprint.from_dict(
        {
            "market_regime_at_signal": "RISK_ON",
            "market_regime": {"regime": "RISK_OFF"},
        }
    )

    assert fp.market_regime_at_signal == "RISK_ON"


def test_signal_observation_fingerprint_preserves_volatility_context_fields():
    """atr_at_signal / atr_pct_at_signal / volatility_bucket_at_signal /
    volatility_size_multiplier_at_signal (shared VolatilityContext fingerprint)
    must survive a to_dict/from_dict round trip unchanged."""
    fp = SignalObservationFingerprint(
        atr_at_signal=3.0,
        atr_pct_at_signal=3.0,
        volatility_bucket_at_signal="NORMAL",
        volatility_size_multiplier_at_signal=1.0,
    )

    round_tripped = SignalObservationFingerprint.from_dict(fp.to_dict())

    assert round_tripped.atr_at_signal == 3.0
    assert round_tripped.atr_pct_at_signal == 3.0
    assert round_tripped.volatility_bucket_at_signal == "NORMAL"
    assert round_tripped.volatility_size_multiplier_at_signal == 1.0


def test_signal_observation_fingerprint_volatility_context_defaults_to_none():
    """Missing volatility fields entirely (e.g. from_dict({})) must default
    all 4 new fields to None."""
    fp = SignalObservationFingerprint.from_dict({})

    assert fp.atr_at_signal is None
    assert fp.atr_pct_at_signal is None
    assert fp.volatility_bucket_at_signal is None
    assert fp.volatility_size_multiplier_at_signal is None


def test_signal_observation_fingerprint_volatility_context_aliases_analyze_swing_keys():
    """Old analyze-swing-style keys (atr_20/atr_pct/volatility_bucket/
    volatility_size_multiplier) must still parse into the new canonical
    `*_at_signal` field names."""
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


def test_signal_observation_fingerprint_volatility_context_canonical_key_precedence():
    """When both the new canonical name and the old analyze-swing alias are
    present in the dict, the canonical name must win."""
    fp = SignalObservationFingerprint.from_dict(
        {
            "atr_at_signal": 9.0,
            "atr_20": 1.0,
        }
    )

    assert fp.atr_at_signal == 9.0


def test_signal_observation_fingerprint_imports():
    from src.domain.value_objects.signal_forward_label import (
        SignalObservationFingerprint as Compat,
    )
    from src.domain.value_objects.signal_observation_fingerprint import (
        SignalObservationFingerprint as Canonical,
    )
    assert Canonical is Compat


def test_signal_observation_fingerprint_legacy_aliases_and_conversions():
    from src.domain.value_objects.signal_observation_fingerprint import SignalObservationFingerprint

    # 1. Test legacy aliases mapping
    data = {
        "setup_phase_current": "ACCUMULATION",
        "rsi_at_signal": 45.0,
        "bb_width_pctile_at_signal": 0.25,
        "vwap_position_at_signal": 1.02,
        "rs_vs_ihsg_20d_at_signal": -0.05,
        "volume_ratio_at_signal": 1.5,
        "cnfb_20d_at_signal": 0.002,
        "foreign_participation_at_signal": 0.45,
        "foreign_concentration_at_signal": 0.6,
        "domestic_broker_accumulation_at_signal": 0.1,
    }
    fp = SignalObservationFingerprint.from_dict(data)
    assert fp.setup_phase == "ACCUMULATION"
    assert fp.rsi == 45.0
    assert fp.bb_width_pctile == 0.25
    assert fp.vwap_position == 1.02
    assert fp.rs_vs_ihsg == -0.05
    assert fp.volume_ratio == 1.5
    assert fp.cnfb == 0.002
    assert fp.foreign_participation == 0.45
    assert fp.foreign_concentration == 0.6
    assert fp.domestic_broker_accumulation == 0.1

    # 2. Test market_regime reconstruction from flat fields
    data_regime = {
        "market_regime_at_signal": "BULL_MARKET",
        "regime_confidence_at_signal": 0.85,
        "regime_stability_at_signal": "HIGH",
        "decision_constraints": {"min_score": 0.4},
    }
    fp_regime = SignalObservationFingerprint.from_dict(data_regime)
    assert fp_regime.market_regime == {
        "regime": "BULL_MARKET",
        "regime_confidence": 0.85,
        "regime_stability": "HIGH",
        "decision_constraints": {"min_score": 0.4},
    }
    assert fp_regime.market_regime_at_signal == "BULL_MARKET"
    assert fp_regime.regime_confidence_at_signal == 0.85
    assert fp_regime.regime_stability_at_signal == "HIGH"

    # 3. Test tuple/list fields still round-trip as tuples internally and lists in to_dict()
    data_collections = {
        "matched_setup_families": ["breakout", "coiled-spring"],
        "setup_family_rationale": ["matched some criteria"],
        "phase_reasons": ["first reason", "second reason"],
        "strategy_rationale": ["strategy description"],
    }
    fp_coll = SignalObservationFingerprint.from_dict(data_collections)
    assert isinstance(fp_coll.matched_setup_families, tuple)
    assert fp_coll.matched_setup_families == ("breakout", "coiled-spring")

    serialized = fp_coll.to_dict()
    assert isinstance(serialized["matched_setup_families"], list)
    assert serialized["matched_setup_families"] == ["breakout", "coiled-spring"]

    # 4. Test exact round-trip equivalence
    round_tripped = SignalObservationFingerprint.from_dict(fp_coll.to_dict())
    assert round_tripped == fp_coll
    assert round_tripped.to_dict() == fp_coll.to_dict()
