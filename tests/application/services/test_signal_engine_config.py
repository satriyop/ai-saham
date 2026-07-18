from pathlib import Path

import pytest
import yaml

from src.application.services.bootstrap import _resolve_signal_config
from src.application.services.signal_engine_config import DecisionPolicyConfig


def _valid_promotion(
    *,
    evidence_name: str = "market_context",
    promoted_to: str = "LOW_WEIGHT",
) -> dict:
    return {
        "target": "foreign_institutional_accumulation_large_cap_SWING_10D",
        "evidence_name": evidence_name,
        "promoted_to": promoted_to,
        "promoted_by": "manual",
        "promoted_date": "2026-07-08",
        "attribution_ref": "journals/signal-readiness/phase-i-report.json",
        "requirements": {
            "min_is_labels": 60,
            "min_oos_labels": 30,
            "min_oos_profit_factor": 1.15,
            "min_oos_avg_return_pct": 0.0,
            "max_drawdown_regression_pct": 0.0,
        },
    }


def test_resolve_signal_config_reads_policy_blocks():
    cfg = {
        "signal_engine": {
            "classification": {
                "strong_min_score": 80,
                "moderate_min_score": 55,
            },
            "enrichment": {
                "insider_lookback_days": 120,
            },
            "input_mapping": {
                "foreign_flow_score": {
                    "max_score": 150.0,
                    "clamp": False,
                },
            },
            "scoring": {
                "bandar": {
                    "mandatory_signal_count": 4,
                    "signal_score_unit": 3,
                    "default_max_range": 12,
                },
            },
            "decision_policy": {
                "regime_policy": {
                    "RISK_ON": {
                        "enter_allowed": True,
                        "enter_threshold": 71,
                        "watch_threshold": 46,
                        "min_signal_authority_coverage": 0.61,
                        "max_decision": "ENTER",
                        "regime_size_multiplier": 1.0,
                    },
                    "NEUTRAL": {
                        "enter_allowed": True,
                        "enter_threshold": 73,
                        "watch_threshold": 52,
                        "min_signal_authority_coverage": 0.65,
                        "max_decision": "ENTER",
                        "regime_size_multiplier": 0.5,
                    },
                    "RISK_OFF": {
                        "enter_allowed": False,
                        "enter_threshold": None,
                        "watch_threshold": 60,
                        "min_signal_authority_coverage": 0.8,
                        "max_decision": "WATCH",
                        "regime_size_multiplier": 0.25,
                    },
                    "VOLATILE": {
                        "enter_allowed": False,
                        "enter_threshold": None,
                        "watch_threshold": 65,
                        "min_signal_authority_coverage": 1.0,
                        "max_decision": "WATCH",
                        "regime_size_multiplier": 0.0,
                    },
                },
                "setup_regime_policy": {
                    "foreign_bounce": {
                        "RISK_OFF": "allowed_if_flow_confirmation_strong",
                    },
                },
                "setup_regime_actions": {
                    "allowed_if_flow_confirmation_strong": {
                        "max_decision": "ENTER",
                    },
                },
            },
            "alpha_trigger": {
                "default_horizon": "TACTICAL_3D",
                "low_weight_cap": 0.15,
                "group_weights": {
                    "setup_quality": 0.40,
                    "institutional_flow": 0.25,
                    "market_context": 0.25,
                    "company_quality_context": 0.10,
                },
                "horizon_alpha_weights": {
                    "TACTICAL_3D": 0.25,
                },
                "route_fractions": {
                    "TACTICAL_3D": {
                        "institutional_flow": {"alpha_fraction": 0.65},
                    },
                },
                "evidence_registrations": {
                    "market_context": {
                        "status": "LOW_WEIGHT",
                        "low_weight_cap": 0.05,
                        "promotion": _valid_promotion(),
                    },
                },
            },
        }
    }

    resolved = _resolve_signal_config(cfg)

    assert resolved.classification.strong_min_score == 80
    assert resolved.classification.moderate_min_score == 55
    assert resolved.enrichment.insider_lookback_days == 120
    assert resolved.input_mapping.foreign_flow_score.max_score == 150.0
    assert resolved.input_mapping.foreign_flow_score.clamp is False
    assert resolved.scoring.bandar.mandatory_signal_count == 4
    assert resolved.scoring.bandar.signal_score_unit == 3
    assert resolved.scoring.bandar.default_max_range == 12
    assert resolved.decision_policy.regime_policy["RISK_OFF"].enter_allowed is False
    assert resolved.decision_policy.regime_policy["RISK_OFF"].max_decision == "WATCH"
    assert resolved.decision_policy.regime_policy["NEUTRAL"].regime_size_multiplier == 0.5
    assert (
        resolved.decision_policy.regime_policy["RISK_ON"].min_signal_authority_coverage
        == 0.61
    )
    assert (
        resolved.decision_policy.setup_regime_policy["foreign_bounce"]["RISK_OFF"]
        == "allowed_if_flow_confirmation_strong"
    )
    assert resolved.alpha_trigger.default_horizon == "TACTICAL_3D"
    assert resolved.alpha_trigger.low_weight_cap == 0.15
    assert resolved.alpha_trigger.group_weights["setup_quality"] == 0.40
    assert resolved.alpha_trigger.group_weights["institutional_flow"] == 0.25
    assert resolved.alpha_trigger.group_weights["market_context"] == 0.25
    assert resolved.alpha_trigger.group_weights["company_quality_context"] == 0.10
    assert resolved.alpha_trigger.horizon_alpha_weights["TACTICAL_3D"] == 0.25
    assert (
        resolved.alpha_trigger.route_fractions["TACTICAL_3D"]["institutional_flow"]
        == 0.65
    )
    assert (
        resolved.alpha_trigger.evidence_registrations["market_context"].status.value
        == "LOW_WEIGHT"
    )


def test_resolve_signal_config_current_file_passes():
    cfg = yaml.safe_load(Path("config/signal_engine.yaml").read_text()) or {}

    resolved = _resolve_signal_config(cfg)

    assert (
        resolved.alpha_trigger.evidence_registrations["setup_quality"].status.value
        == "PRODUCTION"
    )
    assert (
        resolved.alpha_trigger.evidence_registrations["institutional_flow"].status.value
        == "PRODUCTION"
    )
    assert (
        resolved.alpha_trigger.evidence_registrations["market_context"].status.value
        == "DIAGNOSTIC"
    )
    assert (
        resolved.alpha_trigger.evidence_registrations[
            "company_quality_context"
        ].status.value
        == "DIAGNOSTIC"
    )
    # HIGH-2 Finding 1: production RISK_ON/NEUTRAL enforce a 0.70
    # signal_authority_coverage floor (config/signal_engine.yaml) — the
    # code-level DecisionPolicyConfig() default must match exactly so a
    # caller that constructs SignalEngine() without an explicit config
    # cannot silently fall back to an unenforced (0.0) floor.
    assert (
        resolved.decision_policy.regime_policy["RISK_ON"].min_signal_authority_coverage
        == 0.70
    )
    assert (
        resolved.decision_policy.regime_policy["NEUTRAL"].min_signal_authority_coverage
        == 0.70
    )


def test_decision_policy_config_defaults_match_canonical_yaml_floor():
    """HIGH-2 Finding 1: DecisionPolicyConfig()'s bare Python defaults (used
    whenever a caller builds SignalEngine()/SignalEngineConfig() without
    loading config/signal_engine.yaml) must already carry the same
    min_signal_authority_coverage floor the YAML declares for RISK_ON and
    NEUTRAL — otherwise an unconfigured engine would silently authorize
    ENTER at coverage levels the real policy forbids."""
    config = DecisionPolicyConfig()

    assert config.regime_policy["RISK_ON"].min_signal_authority_coverage == 0.70
    assert config.regime_policy["NEUTRAL"].min_signal_authority_coverage == 0.70
    assert config.regime_policy["RISK_OFF"].min_signal_authority_coverage == 0.80
    assert config.regime_policy["VOLATILE"].min_signal_authority_coverage == 1.00


def test_resolve_signal_config_rejects_removed_factors_key():
    cfg = {
        "signal_engine": {
            "factors": {
                "bandar_intensity": {
                    "enabled": True,
                    "weight": 0.25,
                },
            },
        },
    }

    with pytest.raises(ValueError, match="signal_engine.factors"):
        _resolve_signal_config(cfg)


def test_resolve_signal_config_rejects_removed_missing_data_key():
    cfg = {
        "signal_engine": {
            "missing_data": {
                "neutral_score": 45.0,
            },
        },
    }

    with pytest.raises(ValueError, match="signal_engine.missing_data"):
        _resolve_signal_config(cfg)


@pytest.mark.parametrize("removed_scoring_key", ["seasonality", "analyst", "forward_pe"])
def test_resolve_signal_config_rejects_removed_scoring_key(removed_scoring_key):
    cfg = {
        "signal_engine": {
            "scoring": {
                removed_scoring_key: {"some_field": 1.0},
            },
        },
    }

    with pytest.raises(
        ValueError, match=f"signal_engine.scoring.{removed_scoring_key}"
    ):
        _resolve_signal_config(cfg)


def test_resolve_signal_config_rejects_market_context_production_without_promotion():
    cfg = {
        "signal_engine": {
            "alpha_trigger": {
                "evidence_registrations": {
                    "market_context": {"status": "PRODUCTION"},
                },
            },
        },
    }

    with pytest.raises(ValueError, match="market_context\\.promotion is required"):
        _resolve_signal_config(cfg)


def test_resolve_signal_config_rejects_company_quality_low_weight_without_promotion():
    cfg = {
        "signal_engine": {
            "alpha_trigger": {
                "evidence_registrations": {
                    "company_quality_context": {"status": "LOW_WEIGHT"},
                },
            },
        },
    }

    with pytest.raises(
        ValueError,
        match="company_quality_context\\.promotion is required",
    ):
        _resolve_signal_config(cfg)


def test_resolve_signal_config_rejects_unknown_promoted_group_without_promotion():
    cfg = {
        "signal_engine": {
            "alpha_trigger": {
                "group_weights": {"new_diagnostic_group": 0.05},
                "evidence_registrations": {
                    "new_diagnostic_group": {"status": "LOW_WEIGHT"},
                },
            },
        },
    }

    with pytest.raises(
        ValueError,
        match="new_diagnostic_group\\.promotion is required",
    ):
        _resolve_signal_config(cfg)


def test_resolve_signal_config_rejects_promotion_evidence_name_mismatch():
    cfg = {
        "signal_engine": {
            "alpha_trigger": {
                "evidence_registrations": {
                    "market_context": {
                        "status": "LOW_WEIGHT",
                        "promotion": _valid_promotion(
                            evidence_name="company_quality_context"
                        ),
                    },
                },
            },
        },
    }

    with pytest.raises(ValueError, match="evidence_name must match"):
        _resolve_signal_config(cfg)


def test_resolve_signal_config_rejects_promotion_status_mismatch():
    cfg = {
        "signal_engine": {
            "alpha_trigger": {
                "evidence_registrations": {
                    "market_context": {
                        "status": "PRODUCTION",
                        "promotion": _valid_promotion(promoted_to="LOW_WEIGHT"),
                    },
                },
            },
        },
    }

    with pytest.raises(ValueError, match="promoted_to must equal status"):
        _resolve_signal_config(cfg)


def test_resolve_signal_config_rejects_invalid_promotion_date():
    promotion = _valid_promotion()
    promotion["promoted_date"] = "2026/07/08"
    cfg = {
        "signal_engine": {
            "alpha_trigger": {
                "evidence_registrations": {
                    "market_context": {
                        "status": "LOW_WEIGHT",
                        "promotion": promotion,
                    },
                },
            },
        },
    }

    with pytest.raises(ValueError, match="promoted_date must be a valid ISO date"):
        _resolve_signal_config(cfg)


@pytest.mark.parametrize(
    ("gate", "invalid_value", "message"),
    (
        ("min_is_labels", 59, "min_is_labels must be >= 60"),
        ("min_oos_labels", 29, "min_oos_labels must be >= 30"),
        (
            "min_oos_profit_factor",
            1.14,
            "min_oos_profit_factor must be >= 1.15",
        ),
        ("min_oos_avg_return_pct", -0.01, "min_oos_avg_return_pct must be >= 0"),
        (
            "max_drawdown_regression_pct",
            0.01,
            "max_drawdown_regression_pct must be <= 0",
        ),
    ),
)
def test_resolve_signal_config_rejects_promotion_below_phase_i_gates(
    gate,
    invalid_value,
    message,
):
    promotion = _valid_promotion()
    promotion["requirements"][gate] = invalid_value
    cfg = {
        "signal_engine": {
            "alpha_trigger": {
                "evidence_registrations": {
                    "market_context": {
                        "status": "LOW_WEIGHT",
                        "promotion": promotion,
                    },
                },
            },
        },
    }

    with pytest.raises(ValueError, match=message):
        _resolve_signal_config(cfg)


def test_resolve_signal_config_complete_valid_promotion_record_passes():
    cfg = {
        "signal_engine": {
            "alpha_trigger": {
                "evidence_registrations": {
                    "market_context": {
                        "status": "LOW_WEIGHT",
                        "promotion": _valid_promotion(),
                    },
                },
            },
        },
    }

    resolved = _resolve_signal_config(cfg)

    promotion = resolved.alpha_trigger.evidence_registrations[
        "market_context"
    ].promotion
    assert promotion is not None
    assert promotion.evidence_name == "market_context"
    assert promotion.promoted_to.value == "LOW_WEIGHT"


def test_resolve_signal_config_rejects_missing_decision_policy_regime():
    cfg = {
        "signal_engine": {
            "decision_policy": {
                "regime_policy": {
                    "RISK_ON": {"max_decision": "ENTER"},
                    "NEUTRAL": {"max_decision": "ENTER"},
                    "RISK_OFF": {"max_decision": "WATCH"},
                },
            },
        },
    }

    with pytest.raises(ValueError, match="missing regimes: VOLATILE"):
        _resolve_signal_config(cfg)


def test_resolve_signal_config_rejects_invalid_decision_name():
    cfg = {
        "signal_engine": {
            "decision_policy": {
                "regime_policy": {
                    "RISK_ON": {"max_decision": "BUY", "min_signal_authority_coverage": 0.70},
                    "NEUTRAL": {"max_decision": "ENTER", "min_signal_authority_coverage": 0.70},
                    "RISK_OFF": {"max_decision": "WATCH", "min_signal_authority_coverage": 0.80},
                    "VOLATILE": {"max_decision": "WATCH", "min_signal_authority_coverage": 1.0},
                },
            },
        },
    }

    with pytest.raises(ValueError, match="Invalid max_decision"):
        _resolve_signal_config(cfg)


def test_resolve_signal_config_rejects_invalid_alpha_fraction():
    cfg = {
        "signal_engine": {
            "alpha_trigger": {
                "route_fractions": {
                    "SWING_10D": {
                        "setup_quality": {"alpha_fraction": 1.5},
                    },
                },
            },
        },
    }

    with pytest.raises(ValueError, match="alpha_fraction"):
        _resolve_signal_config(cfg)


def test_resolve_signal_config_rejects_negative_alpha_trigger_group_weight():
    cfg = {
        "signal_engine": {
            "alpha_trigger": {
                "group_weights": {
                    "market_context": -0.10,
                },
            },
        },
    }

    with pytest.raises(ValueError, match="group_weights.market_context"):
        _resolve_signal_config(cfg)


# ── HIGH-2: evidence-group config fail-closed validation ────────────────────


def test_resolve_signal_config_rejects_non_positive_evidence_group_weight():
    cfg = {
        "signal_engine": {
            "evidence_groups": {
                "setup_quality": {"weight": 0.0},
            },
        },
    }

    with pytest.raises(ValueError, match="evidence_groups.setup_quality.weight must be > 0"):
        _resolve_signal_config(cfg)


def test_resolve_signal_config_rejects_empty_authority_registration():
    cfg = {
        "signal_engine": {
            "evidence_groups": {
                "flow_confirmation": {"authority_registration": ""},
            },
        },
    }

    with pytest.raises(
        ValueError,
        match="evidence_groups.flow_confirmation.authority_registration cannot be empty",
    ):
        _resolve_signal_config(cfg)


def test_resolve_signal_config_rejects_unknown_authority_registration():
    # Not a "resolve to diagnostic" case — a misspelled registration name
    # must fail closed at config-load time, never silently pass through.
    cfg = {
        "signal_engine": {
            "evidence_groups": {
                "setup_quality": {"authority_registration": "setup_qualty"},
            },
        },
    }

    with pytest.raises(
        ValueError,
        match=r"authority_registration='setup_qualty' does not exist",
    ):
        _resolve_signal_config(cfg)


def test_resolve_signal_config_rejects_non_boolean_required_for_authority():
    cfg = {
        "signal_engine": {
            "evidence_groups": {
                "setup_quality": {"required_for_authority": "yes"},
            },
        },
    }

    with pytest.raises(
        ValueError,
        match="evidence_groups.setup_quality.required_for_authority must be a boolean",
    ):
        _resolve_signal_config(cfg)


def test_resolve_signal_config_rejects_out_of_range_min_signal_authority_coverage():
    cfg = {
        "signal_engine": {
            "decision_policy": {
                "regime_policy": {
                    "RISK_ON": {"max_decision": "ENTER", "min_signal_authority_coverage": 1.5},
                    "NEUTRAL": {"max_decision": "ENTER", "min_signal_authority_coverage": 0.70},
                    "RISK_OFF": {"max_decision": "WATCH", "min_signal_authority_coverage": 0.80},
                    "VOLATILE": {"max_decision": "WATCH", "min_signal_authority_coverage": 1.0},
                },
            },
        },
    }

    with pytest.raises(
        ValueError,
        match=r"RISK_ON\.min_signal_authority_coverage must be within \[0\.0, 1\.0\]",
    ):
        _resolve_signal_config(cfg)


def test_resolve_signal_config_rejects_omitted_min_signal_authority_coverage():
    """HIGH-2 Finding 1 (post-review): the resolver must not fail open to 0.0
    when min_signal_authority_coverage is omitted from a regime's config
    block. A silent 0.0 default would recreate the original unenforced-floor
    bypass for any config that accidentally drops this key, even though the
    RISK_ON/NEUTRAL DecisionPolicyConfig() dataclass defaults are correctly
    0.70. All four regimes are present (so the missing-regime check does not
    fire first); only NEUTRAL omits the key."""
    cfg = {
        "signal_engine": {
            "decision_policy": {
                "regime_policy": {
                    "RISK_ON": {"max_decision": "ENTER", "min_signal_authority_coverage": 0.70},
                    "NEUTRAL": {"max_decision": "ENTER"},
                    "RISK_OFF": {"max_decision": "WATCH", "min_signal_authority_coverage": 0.80},
                    "VOLATILE": {"max_decision": "WATCH", "min_signal_authority_coverage": 1.0},
                },
            },
        },
    }

    with pytest.raises(
        ValueError,
        match=(
            r"signal_engine\.decision_policy\.regime_policy\.NEUTRAL\."
            r"min_signal_authority_coverage is required"
        ),
    ):
        _resolve_signal_config(cfg)


def test_resolve_signal_config_accepts_valid_evidence_group_config():
    cfg = {
        "signal_engine": {
            "evidence_groups": {
                "setup_quality": {
                    "weight": 0.55,
                    "authority_registration": "setup_quality",
                    "required_for_authority": True,
                },
                "flow_confirmation": {
                    "weight": 0.45,
                    "authority_registration": "institutional_flow",
                    "required_for_authority": True,
                },
            },
        },
    }

    resolved = _resolve_signal_config(cfg)
    assert resolved.evidence_groups.setup_quality.weight == 0.55
    assert resolved.evidence_groups.setup_quality.authority_registration == "setup_quality"
    assert resolved.evidence_groups.flow_confirmation.weight == 0.45
