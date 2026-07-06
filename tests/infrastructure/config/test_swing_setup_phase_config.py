from pathlib import Path

from src.infrastructure.config.swing_config import load_swing_config


def test_load_swing_config_parses_setup_phase_section(tmp_path: Path):
    path = tmp_path / "swing_setups.yaml"
    path.write_text(
        """
setup_phase:
  thresholds:
    compression_max_bb_width_pctile: 0.15
    breakout_min_volume_ratio: 1.5
  rs_policy_by_setup_family:
    foreign-bounce:
      lag_warning_below: -2.0
      hard_exclude_below: -5.0
      warning_max_decision: WATCH
      hard_exclude_max_decision: AVOID
  volume_trigger:
    require_trusted_volume: true
    trusted_benchmark_volume_sources: ["stockbit", "idx"]
    min_valid_20d_sessions: 19
    zero_volume_tolerance: 0
""",
        encoding="utf-8",
    )

    cfg = load_swing_config(path)

    assert cfg.setup_phase_config.thresholds.compression_max_bb_width_pctile == 0.15
    assert cfg.setup_phase_config.thresholds.breakout_min_volume_ratio == 1.5
    assert cfg.setup_phase_config.volume_trigger.require_trusted_volume is True
    assert cfg.setup_phase_config.volume_trigger.trusted_benchmark_volume_sources == ("stockbit", "idx")
    assert cfg.setup_phase_config.volume_trigger.min_valid_20d_sessions == 19
    assert cfg.setup_phase_config.volume_trigger.zero_volume_tolerance == 0
    assert (
        cfg.setup_phase_config.rs_policy_for("foreign-bounce").hard_exclude_below
        == -5.0
    )
