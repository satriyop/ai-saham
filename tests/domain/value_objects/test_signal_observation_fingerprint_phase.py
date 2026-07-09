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
