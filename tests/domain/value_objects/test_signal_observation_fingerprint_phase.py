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
