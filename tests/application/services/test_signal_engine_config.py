from pathlib import Path

import pytest
import yaml

from src.application.services.bootstrap import _resolve_signal_config


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
            "missing_data": {
                "neutral_score": 45.0,
                "coverage_warning_missing_factors": 4,
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
                "seasonality": {
                    "tailwind_min_avg_return_pct": 1.0,
                    "tailwind_min_win_rate_pct": 60.0,
                    "headwind_max_avg_return_pct": -1.0,
                    "headwind_max_win_rate_pct": 40.0,
                },
                "analyst": {
                    "buy_score_max_points": 55.0,
                    "upside_score_max_points": 45.0,
                    "upside_cap_pct": 25.0,
                },
                "forward_pe": {
                    "very_cheap_pe": 8.0,
                    "cheap_pe": 12.0,
                    "fair_pe": 18.0,
                    "expensive_pe": 28.0,
                    "very_cheap_score": 98.0,
                    "cheap_score": 78.0,
                    "fair_score": 48.0,
                    "expensive_score": 18.0,
                    "post_expensive_pe_step": 8.0,
                    "post_expensive_score_decay": 12.0,
                },
            },
            "decision_policy": {
                "regime_policy": {
                    "RISK_ON": {
                        "enter_allowed": True,
                        "enter_threshold": 71,
                        "watch_threshold": 46,
                        "min_coverage": 0.61,
                        "min_conviction": 0.62,
                        "max_decision": "ENTER",
                        "regime_size_multiplier": 1.0,
                    },
                    "NEUTRAL": {
                        "enter_allowed": True,
                        "enter_threshold": 73,
                        "watch_threshold": 52,
                        "min_coverage": 0.65,
                        "min_conviction": 0.66,
                        "max_decision": "ENTER",
                        "regime_size_multiplier": 0.5,
                    },
                    "RISK_OFF": {
                        "enter_allowed": False,
                        "enter_threshold": None,
                        "watch_threshold": 60,
                        "min_coverage": 0.8,
                        "min_conviction": 0.78,
                        "max_decision": "WATCH",
                        "regime_size_multiplier": 0.25,
                    },
                    "VOLATILE": {
                        "enter_allowed": False,
                        "enter_threshold": None,
                        "watch_threshold": 65,
                        "min_coverage": 1.0,
                        "min_conviction": 1.0,
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
    assert resolved.missing_data.neutral_score == 45.0
    assert resolved.missing_data.coverage_warning_missing_factors == 4
    assert resolved.enrichment.insider_lookback_days == 120
    assert resolved.input_mapping.foreign_flow_score.max_score == 150.0
    assert resolved.input_mapping.foreign_flow_score.clamp is False
    assert resolved.scoring.bandar.mandatory_signal_count == 4
    assert resolved.scoring.bandar.signal_score_unit == 3
    assert resolved.scoring.bandar.default_max_range == 12
    assert resolved.scoring.seasonality.tailwind_min_avg_return_pct == 1.0
    assert resolved.scoring.seasonality.tailwind_min_win_rate_pct == 60.0
    assert resolved.scoring.seasonality.headwind_max_avg_return_pct == -1.0
    assert resolved.scoring.seasonality.headwind_max_win_rate_pct == 40.0
    assert resolved.scoring.analyst.buy_score_max_points == 55.0
    assert resolved.scoring.analyst.upside_score_max_points == 45.0
    assert resolved.scoring.analyst.upside_cap_pct == 25.0
    assert resolved.scoring.forward_pe.very_cheap_pe == 8.0
    assert resolved.scoring.forward_pe.expensive_score == 18.0
    assert resolved.scoring.forward_pe.post_expensive_score_decay == 12.0
    assert resolved.decision_policy.regime_policy["RISK_OFF"].enter_allowed is False
    assert resolved.decision_policy.regime_policy["RISK_OFF"].max_decision == "WATCH"
    assert resolved.decision_policy.regime_policy["NEUTRAL"].regime_size_multiplier == 0.5
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


def test_resolve_signal_config_current_file_emits_no_archived_warning(caplog):
    cfg = yaml.safe_load(Path("config/signal_engine.yaml").read_text()) or {}

    _resolve_signal_config(cfg)

    assert not [
        r for r in caplog.records
        if "archived/baseline-only" in r.getMessage()
    ]


def test_resolve_signal_config_warns_when_archived_factor_changes(caplog):
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

    _resolve_signal_config(cfg)

    assert any(
        "signal_engine.factors.bandar_intensity.weight" in r.getMessage()
        and "archived/baseline-only" in r.getMessage()
        for r in caplog.records
    )


def test_resolve_signal_config_warns_when_archived_analyst_scoring_changes(caplog):
    cfg = {
        "signal_engine": {
            "scoring": {
                "analyst": {
                    "buy_score_max_points": 55.0,
                },
            },
        },
    }

    resolved = _resolve_signal_config(cfg)

    assert resolved.scoring.analyst.buy_score_max_points == 55.0
    assert any(
        "signal_engine.scoring.analyst.buy_score_max_points" in r.getMessage()
        and "diagnostic company-quality scorer" in r.getMessage()
        and "company_quality_context remains DIAGNOSTIC" in r.getMessage()
        for r in caplog.records
    )


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
                    "RISK_ON": {"max_decision": "BUY"},
                    "NEUTRAL": {"max_decision": "ENTER"},
                    "RISK_OFF": {"max_decision": "WATCH"},
                    "VOLATILE": {"max_decision": "WATCH"},
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
