from pathlib import Path

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
    dimensions: [score, broker_quality]
    bucket_edges:
      score: [50, 80]
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
    assert loaded.group_dimensions == ("score", "broker_quality")
    assert loaded.buckets.score == (50.0, 80.0)
    assert loaded.buckets.rsi == (35.0, 55.0)


def test_load_accumulation_audit_config_reads_setup_presets(tmp_path: Path):
    config = tmp_path / "accumulation_audit.yaml"
    config.write_text(
        """
accumulation_audit:
  setups:
    foreign-bounce:
      min_score: 72
      take_profits: "4,6"
""",
        encoding="utf-8",
    )

    loaded = load_accumulation_audit_config(config)

    assert loaded.setups["foreign-bounce"]["min_score"] == 72
    assert loaded.setups["foreign-bounce"]["take_profits"] == "4,6"
