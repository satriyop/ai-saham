"""Tests for _SwingConfig YAML loader in analyze_swing_commands."""

from decimal import Decimal
from pathlib import Path

import yaml

from src.adapters.cli.analyze_swing_command_config import SWING_CONFIG
from src.adapters.cli.analyze_swing_commands import (
    BROKER_WEIGHTS,
    NOISE_BROKERS,
    SMART_MONEY_BROKERS,
)
from src.infrastructure.config.swing_config import (
    SetupTargetConfig as _SetupTargetConfig,
)
from src.infrastructure.config.swing_config import (
    SwingConfig as _SwingConfig,
)
from src.infrastructure.config.swing_config import (
    load_swing_config as _load_swing_config,
)


def _write_yaml(path: Path, data: dict) -> Path:
    with open(path, "w") as fh:
        yaml.dump(data, fh)
    return path


# ── Loader unit tests ─────────────────────────────────────────────────────

def test_loads_smart_money_brokers_from_yaml(tmp_path):
    cfg = _write_yaml(tmp_path / "s.yaml", {
        "broker_quality": {"smart_money": {"brokers": ["AK", "ZP"], "weight": 1.5}},
    })
    result = _load_swing_config(cfg)
    assert result.smart_money_brokers == ("AK", "ZP")


def test_loads_noise_brokers_from_yaml(tmp_path):
    cfg = _write_yaml(tmp_path / "s.yaml", {
        "broker_quality": {"noise": {"brokers": ["YP"], "weight": 0.5}},
    })
    result = _load_swing_config(cfg)
    assert result.noise_brokers == ("YP",)


def test_loads_broker_weights_from_yaml(tmp_path):
    cfg = _write_yaml(tmp_path / "s.yaml", {
        "broker_quality": {
            "smart_money": {"brokers": ["AK"], "weight": 2.0},
            "noise": {"brokers": ["YP"], "weight": 0.3},
        },
    })
    result = _load_swing_config(cfg)
    assert result.smart_weight == Decimal("2.0")
    assert result.noise_weight == Decimal("0.3")


def test_loads_gate_thresholds_from_yaml(tmp_path):
    cfg = _write_yaml(tmp_path / "s.yaml", {
        "foreign_bounce": {
            "gates": {"min_foreign_flow_score": 65, "max_rsi": 55, "min_vwap_discount_pct": 2.0,
                      "required_trend": "UP", "min_flow_ratio_pct": 3.0},
            "partial_max_failed_gates": 1,
        },
    })
    result = _load_swing_config(cfg)
    assert result.gate_min_foreign_flow_score == 65.0
    assert result.gate_max_rsi == 55.0
    assert result.gate_required_trend == "UP"
    assert result.partial_max_failed_gates == 1


def test_loads_setup_catalog_thresholds_from_yaml(tmp_path):
    cfg = _write_yaml(tmp_path / "s.yaml", {
        "setups": {
            "coiled-spring": {
                "enabled": False,
                "gates": {"min_foreign_flow_score": 61, "max_bb_width_pctile": 0.15},
                "partial_max_failed_gates": 1,
            },
            "smart-money-confirmed": {
                "gates": {
                    "min_smart_flow_idr": 1000000,
                    "min_smart_share_pct": 45,
                    "max_noise_share_pct": 40,
                    "reject_smart_net_selling": False,
                },
            },
            "pullback-continuation": {
                "gates": {"min_rsi": 42, "max_rsi": 63, "required_trend": "UP"},
            },
        },
    })
    result = _load_swing_config(cfg)

    assert result.coiled_spring_enabled is False
    assert result.coiled_spring_gate_min_foreign_flow_score == 61.0
    assert result.coiled_spring_gate_max_bb_width_pctile == 0.15
    assert result.coiled_spring_partial_max_failed_gates == 1
    assert result.smart_money_confirmed_gate_min_smart_flow_idr == Decimal("1000000.0")
    assert result.smart_money_confirmed_gate_min_smart_share_pct == 45.0
    assert result.smart_money_confirmed_gate_max_noise_share_pct == 40.0
    assert result.smart_money_confirmed_reject_smart_net_selling is False
    assert result.pullback_continuation_gate_min_rsi == 42.0
    assert result.pullback_continuation_gate_max_rsi == 63.0
    assert result.pullback_continuation_gate_required_trend == "UP"


def test_loads_setup_entry_authority_metadata_from_yaml(tmp_path):
    cfg = _write_yaml(tmp_path / "s.yaml", {
        "setups": {
            "foreign-bounce": {
                "family": "accumulation",
                "entry_authority": True,
                "can_enter_from_phases": ["BREAKOUT_CONFIRMATION"],
            },
            "smart-money-confirmed": {
                "family": "confirmation",
                "entry_authority": False,
                "can_enter_from_phases": [],
            },
        },
    })
    result = _load_swing_config(cfg)

    assert result.foreign_bounce_family == "accumulation"
    assert result.foreign_bounce_entry_authority is True
    assert result.foreign_bounce_can_enter_from_phases == ("BREAKOUT_CONFIRMATION",)
    assert result.smart_money_confirmed_family == "confirmation"
    assert result.smart_money_confirmed_entry_authority is False
    assert result.smart_money_confirmed_can_enter_from_phases == ()


def test_setup_entry_authority_metadata_falls_back_to_defaults_when_absent(tmp_path):
    cfg = _write_yaml(tmp_path / "s.yaml", {
        "setups": {"foreign-bounce": {"gates": {"max_rsi": 55}}},
    })
    result = _load_swing_config(cfg)

    assert result.foreign_bounce_family == "unknown"
    assert result.foreign_bounce_entry_authority is True
    assert result.foreign_bounce_can_enter_from_phases == ()


def test_live_config_setups_are_explicit_entry_authority_metadata():
    """The shipped config/swing_setups.yaml must declare explicit metadata for
    every setup — defaults exist only for backward compatibility."""
    result = _load_swing_config()
    assert result.foreign_bounce_family == "accumulation"
    assert result.foreign_bounce_entry_authority is True
    assert result.foreign_bounce_can_enter_from_phases == ("BREAKOUT_CONFIRMATION",)
    assert result.coiled_spring_family == "breakout"
    assert result.coiled_spring_entry_authority is True
    assert result.coiled_spring_can_enter_from_phases == ("BREAKOUT_CONFIRMATION",)
    assert result.smart_money_confirmed_family == "confirmation"
    assert result.smart_money_confirmed_entry_authority is False
    assert result.smart_money_confirmed_can_enter_from_phases == ()
    assert result.pullback_continuation_family == "pullback"
    assert result.pullback_continuation_entry_authority is True
    assert result.pullback_continuation_can_enter_from_phases == ("BREAKOUT_CONFIRMATION",)


def test_loads_verdict_thresholds_from_yaml(tmp_path):
    cfg = _write_yaml(tmp_path / "s.yaml", {
        "verdicts": {"enter_min_score": 75, "watch_min_score": 45},
    })
    result = _load_swing_config(cfg)
    assert result.enter_min_score == 75.0
    assert result.watch_min_score == 45.0


def test_loads_signal_thresholds_from_yaml(tmp_path):
    cfg = _write_yaml(tmp_path / "s.yaml", {
        "verdicts": {"signals": {"strong_min_streak": 10, "building_min_score": 55.0}},
    })
    result = _load_swing_config(cfg)
    assert result.strong_min_streak == 10
    assert result.building_min_score == 55.0


def test_loads_resistance_and_corporate_action_thresholds_from_yaml(tmp_path):
    cfg = _write_yaml(tmp_path / "s.yaml", {
        "resistance": {
            "enabled": False,
            "headroom_min_pct": 7.5,
        },
        "corporate_actions": {
            "ex_date_warning_days": 15,
        },
    })
    result = _load_swing_config(cfg)
    assert result.resistance_gate_enabled is False
    assert result.resistance_headroom_min_pct == 7.5
    assert result.ex_date_warning_days == 15


def test_falls_back_to_defaults_when_file_missing():
    result = _load_swing_config(Path("/nonexistent/swing_config.yaml"))
    assert result == _SwingConfig()


def test_falls_back_to_defaults_when_yaml_invalid(tmp_path):
    bad = tmp_path / "s.yaml"
    bad.write_text("{ bad yaml: :")
    result = _load_swing_config(bad)
    assert result == _SwingConfig()


def test_falls_back_to_defaults_when_broker_codes_empty(tmp_path):
    cfg = _write_yaml(tmp_path / "s.yaml", {
        "broker_quality": {"smart_money": {"brokers": []}},
    })
    result = _load_swing_config(cfg)
    # Empty list → fall back to hardcoded defaults
    assert result.smart_money_brokers == _SwingConfig().smart_money_brokers


def test_strips_and_uppercases_codes(tmp_path):
    cfg = _write_yaml(tmp_path / "s.yaml", {
        "broker_quality": {"smart_money": {"brokers": ["ak", " zp "]}},
    })
    result = _load_swing_config(cfg)
    assert result.smart_money_brokers == ("AK", "ZP")


def test_partial_yaml_uses_defaults_for_missing_sections(tmp_path):
    """Only one section provided; all other fields stay at defaults."""
    cfg = _write_yaml(tmp_path / "s.yaml", {
        "verdicts": {"enter_min_score": 75},
    })
    result = _load_swing_config(cfg)
    assert result.enter_min_score == 75.0
    assert result.smart_money_brokers == _SwingConfig().smart_money_brokers
    assert result.gate_min_foreign_flow_score == _SwingConfig().gate_min_foreign_flow_score


def test_live_config_loads_without_error():
    """Smoke test: split swing workflow config is valid and matches expected values."""
    result = _load_swing_config()
    assert len(result.smart_money_brokers) > 0
    assert len(result.noise_brokers) > 0
    assert result.gate_min_foreign_flow_score == 58.3
    assert result.enter_min_score == 58.3
    assert result.watch_min_score == 33.3
    assert result.strong_min_streak == 8
    assert result.coiled_spring_bb_pctile == 0.20
    assert result.resistance_gate_enabled is True
    assert result.resistance_headroom_min_pct == 5.0
    assert result.ex_date_warning_days == 10


# ── Module-level constants wired correctly ────────────────────────────────

def test_module_constants_populated():
    assert "AK" in SMART_MONEY_BROKERS
    assert "YP" in NOISE_BROKERS
    assert "AK" not in NOISE_BROKERS
    assert BROKER_WEIGHTS["AK"] == SWING_CONFIG.smart_weight
    assert BROKER_WEIGHTS["YP"] == SWING_CONFIG.noise_weight


def test_broker_weights_derived_from_sc():
    for code in SMART_MONEY_BROKERS:
        assert BROKER_WEIGHTS[code] == SWING_CONFIG.smart_weight
    for code in NOISE_BROKERS:
        assert BROKER_WEIGHTS[code] == SWING_CONFIG.noise_weight


# ── Tier1 broker codes ────────────────────────────────────────────────────

def test_loads_tier1_brokers_from_yaml(tmp_path):
    cfg = _write_yaml(tmp_path / "s.yaml", {
        "broker_quality": {
            "tier1": {"brokers": ["AK", "BK"], "cluster_min_count": 3, "stable_min_count": 1},
        },
    })
    result = _load_swing_config(cfg)
    assert result.tier1_broker_codes == frozenset({"AK", "BK"})


def test_loads_bci_count_thresholds(tmp_path):
    cfg = _write_yaml(tmp_path / "s.yaml", {
        "broker_quality": {
            "tier1": {"brokers": ["AK"], "cluster_min_count": 4, "stable_min_count": 2},
        },
    })
    result = _load_swing_config(cfg)
    assert result.bci_cluster_min_count == 4
    assert result.bci_stable_min_count == 2


def test_tier1_falls_back_to_defaults_when_empty(tmp_path):
    cfg = _write_yaml(tmp_path / "s.yaml", {
        "broker_quality": {"tier1": {"brokers": []}},
    })
    result = _load_swing_config(cfg)
    assert result.tier1_broker_codes == _SwingConfig().tier1_broker_codes


def test_cs_not_in_tier1_brokers():
    """CS (Credit Suisse) was wound down — must not appear in any broker set."""
    assert "CS" not in SWING_CONFIG.smart_money_brokers
    assert "CS" not in SWING_CONFIG.noise_brokers
    assert "CS" not in SWING_CONFIG.tier1_broker_codes


# ── Setup targets ─────────────────────────────────────────────────────────

def test_loads_setup_targets_from_yaml(tmp_path):
    cfg = _write_yaml(tmp_path / "s.yaml", {
        "setup_targets": {
            "risk_on": {"take_profit_pct": 9.0, "stop_loss_pct": 4.5},
            "default": {"take_profit_pct": 6.0, "stop_loss_pct": 3.0},
        },
    })
    result = _load_swing_config(cfg)
    assert result.setup_targets["risk_on"].take_profit_pct == Decimal("9.0")
    assert result.setup_targets["risk_on"].stop_loss_pct == Decimal("4.5")
    assert result.setup_targets["default"].take_profit_pct == Decimal("6.0")


def test_live_config_loads_tier1_and_setup_targets():
    result = _load_swing_config()
    assert "AK" in result.tier1_broker_codes
    assert "CS" not in result.tier1_broker_codes
    assert set(result.setup_targets) == {"risk_on", "neutral", "volatile", "risk_off", "default"}
    assert result.setup_targets["risk_on"].take_profit_pct == Decimal("8.0")
    assert result.bci_cluster_min_count == 3


# ── Import / facade compatibility tests ─────────────────────────────────


def test_dto_import_matches_facade_defaults():
    """DTO import produces the same default SwingConfig as the facade."""
    from src.application.dto.swing_config import (
        SetupTargetConfig as DtoSetupTargetConfig,
    )
    from src.application.dto.swing_config import (
        SwingConfig as DtoSwingConfig,
    )

    dto = DtoSwingConfig()
    facade = _SwingConfig()
    assert dto == facade
    assert DtoSetupTargetConfig() == _SetupTargetConfig()


def test_facade_still_re_exports_everything():
    """The compatibility facade still exports all public names."""
    from src.infrastructure.config.swing_config import (
        SetupTargetConfig as FacadeSetupTargetConfig,
    )
    from src.infrastructure.config.swing_config import (
        SwingConfig as FacadeSwingConfig,
    )
    from src.infrastructure.config.swing_config import (
        load_swing_config as facade_load,
    )

    assert FacadeSwingConfig is _SwingConfig
    assert FacadeSetupTargetConfig is _SetupTargetConfig
    assert facade_load is _load_swing_config
