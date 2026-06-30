from pathlib import Path

import yaml

from src.infrastructure.config.accumulation_audit_config import (
    load_accumulation_audit_config,
    load_accumulation_audit_policy,
)


def test_load_accumulation_audit_policy_reads_measurement_and_grouping(tmp_path: Path):
    config = tmp_path / "accumulation_audit.yaml"
    config.write_text(
        """
accumulation_audit:
  measurement:
    forward_return_horizons: [3, 8]
    forward_fetch_buffer_days: 12
  exit_simulation:
    fetch_buffer_days: 9
    same_day_priority: target_first
  grouping:
    broker_quality_window_sessions: 3
    dimensions: [foreign_flow_score, broker_quality]
    bucket_edges:
      foreign_flow_score: [50, 80]
      rsi: [35, 55]
""",
        encoding="utf-8",
    )

    loaded = load_accumulation_audit_policy(config)

    assert loaded.forward_return_horizons == (3, 8)
    assert loaded.forward_fetch_buffer_days == 12
    assert loaded.exit_fetch_buffer_days == 9
    assert loaded.same_day_exit_priority == "target_first"
    assert loaded.broker_quality_window_sessions == 3
    assert loaded.group_dimensions == ("foreign_flow_score", "broker_quality")
    assert loaded.buckets.foreign_flow_score == (50.0, 80.0)
    assert loaded.buckets.rsi == (35.0, 55.0)


def test_load_accumulation_audit_config_reads_setup_presets(tmp_path: Path):
    config = tmp_path / "accumulation_audit.yaml"
    config.write_text(
        """
accumulation_audit:
  setups:
    foreign-bounce:
      min_foreign_flow_score: 72
      take_profits: "4,6"
""",
        encoding="utf-8",
    )

    loaded = load_accumulation_audit_config(config)

    assert loaded.setups["foreign-bounce"]["min_foreign_flow_score"] == 72
    assert loaded.setups["foreign-bounce"]["take_profits"] == "4,6"


def test_accumulation_audit_setup_thresholds_match_live_swing_setups():
    swing = yaml.safe_load(Path("config/swing_setups.yaml").read_text())["setups"]
    audit = yaml.safe_load(Path("config/accumulation_audit.yaml").read_text())[
        "accumulation_audit"
    ]["setups"]

    key_map = {
        "min_foreign_flow_score": "min_foreign_flow_score",
        "min_vwap_discount_pct": "min_vwap_disc",
        "required_trend": "trend",
        "min_flow_ratio_pct": "min_flow_pct",
        "max_rsi": "max_rsi",
        "min_rsi": "min_rsi",
        "max_bb_width_pctile": "max_bb_width_pctile",
    }

    for setup_name, live_setup in swing.items():
        live_gates = live_setup["gates"]
        audit_setup = audit[setup_name]
        for live_key, audit_key in key_map.items():
            if live_key in live_gates:
                assert audit_setup[audit_key] == live_gates[live_key]
