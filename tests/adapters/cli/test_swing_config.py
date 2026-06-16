"""Tests for _SwingConfig YAML loader in swing_commands."""

from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from src.adapters.cli.swing_commands import (
    _SwingConfig,
    _load_swing_screener_config_typed,
    SMART_MONEY_BROKERS,
    NOISE_BROKERS,
    BROKER_WEIGHTS,
    _SC,
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
    result = _load_swing_screener_config_typed(cfg)
    assert result.smart_money_brokers == ("AK", "ZP")


def test_loads_noise_brokers_from_yaml(tmp_path):
    cfg = _write_yaml(tmp_path / "s.yaml", {
        "broker_quality": {"noise": {"brokers": ["YP"], "weight": 0.5}},
    })
    result = _load_swing_screener_config_typed(cfg)
    assert result.noise_brokers == ("YP",)


def test_loads_broker_weights_from_yaml(tmp_path):
    cfg = _write_yaml(tmp_path / "s.yaml", {
        "broker_quality": {
            "smart_money": {"brokers": ["AK"], "weight": 2.0},
            "noise": {"brokers": ["YP"], "weight": 0.3},
        },
    })
    result = _load_swing_screener_config_typed(cfg)
    assert result.smart_weight == Decimal("2.0")
    assert result.noise_weight == Decimal("0.3")


def test_loads_gate_thresholds_from_yaml(tmp_path):
    cfg = _write_yaml(tmp_path / "s.yaml", {
        "foreign_bounce": {
            "gates": {"min_score": 65, "max_rsi": 55, "min_vwap_discount_pct": 2.0,
                      "required_trend": "UP", "min_flow_ratio_pct": 3.0},
            "watch_max_failed_gates": 1,
        },
    })
    result = _load_swing_screener_config_typed(cfg)
    assert result.gate_min_score == 65.0
    assert result.gate_max_rsi == 55.0
    assert result.gate_required_trend == "UP"
    assert result.watch_max_failed_gates == 1


def test_loads_verdict_thresholds_from_yaml(tmp_path):
    cfg = _write_yaml(tmp_path / "s.yaml", {
        "verdicts": {"enter_min_score": 75, "watch_min_score": 45},
    })
    result = _load_swing_screener_config_typed(cfg)
    assert result.enter_min_score == 75.0
    assert result.watch_min_score == 45.0


def test_loads_signal_thresholds_from_yaml(tmp_path):
    cfg = _write_yaml(tmp_path / "s.yaml", {
        "verdicts": {"signals": {"strong_min_streak": 10, "building_min_score": 55.0}},
    })
    result = _load_swing_screener_config_typed(cfg)
    assert result.strong_min_streak == 10
    assert result.building_min_score == 55.0


def test_falls_back_to_defaults_when_file_missing():
    result = _load_swing_screener_config_typed(Path("/nonexistent/swing_screener.yaml"))
    assert result == _SwingConfig()


def test_falls_back_to_defaults_when_yaml_invalid(tmp_path):
    bad = tmp_path / "s.yaml"
    bad.write_text("{ bad yaml: :")
    result = _load_swing_screener_config_typed(bad)
    assert result == _SwingConfig()


def test_falls_back_to_defaults_when_broker_codes_empty(tmp_path):
    cfg = _write_yaml(tmp_path / "s.yaml", {
        "broker_quality": {"smart_money": {"brokers": []}},
    })
    result = _load_swing_screener_config_typed(cfg)
    # Empty list → fall back to hardcoded defaults
    assert result.smart_money_brokers == _SwingConfig().smart_money_brokers


def test_strips_and_uppercases_codes(tmp_path):
    cfg = _write_yaml(tmp_path / "s.yaml", {
        "broker_quality": {"smart_money": {"brokers": ["ak", " zp "]}},
    })
    result = _load_swing_screener_config_typed(cfg)
    assert result.smart_money_brokers == ("AK", "ZP")


def test_partial_yaml_uses_defaults_for_missing_sections(tmp_path):
    """Only one section provided; all other fields stay at defaults."""
    cfg = _write_yaml(tmp_path / "s.yaml", {
        "verdicts": {"enter_min_score": 75},
    })
    result = _load_swing_screener_config_typed(cfg)
    assert result.enter_min_score == 75.0
    assert result.smart_money_brokers == _SwingConfig().smart_money_brokers
    assert result.gate_min_score == _SwingConfig().gate_min_score


def test_live_config_loads_without_error():
    """Smoke test: config/swing_screener.yaml is valid and matches expected values."""
    result = _load_swing_screener_config_typed(Path("config/swing_screener.yaml"))
    assert len(result.smart_money_brokers) > 0
    assert len(result.noise_brokers) > 0
    assert result.gate_min_score == 70.0
    assert result.enter_min_score == 70.0
    assert result.watch_min_score == 40.0
    assert result.strong_min_streak == 8
    assert result.coiled_spring_bb_pctile == 0.20


# ── Module-level constants wired correctly ────────────────────────────────

def test_module_constants_populated():
    assert "AK" in SMART_MONEY_BROKERS
    assert "YP" in NOISE_BROKERS
    assert "AK" not in NOISE_BROKERS
    assert BROKER_WEIGHTS["AK"] == _SC.smart_weight
    assert BROKER_WEIGHTS["YP"] == _SC.noise_weight


def test_broker_weights_derived_from_sc():
    for code in SMART_MONEY_BROKERS:
        assert BROKER_WEIGHTS[code] == _SC.smart_weight
    for code in NOISE_BROKERS:
        assert BROKER_WEIGHTS[code] == _SC.noise_weight
