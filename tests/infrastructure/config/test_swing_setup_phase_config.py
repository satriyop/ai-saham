from pathlib import Path

import pytest

from src.application.services.setup_phase_detector import SetupPhaseConfig
from src.domain.value_objects.setup_phase import SetupPhaseState
from src.infrastructure.config.swing_config import load_swing_config


def test_load_swing_config_parses_setup_phase_section(tmp_path: Path):
    path = tmp_path / "swing_setups.yaml"
    path.write_text(
        """
setup_phase:
  thresholds:
    compression_max_bb_width_pctile: 0.15
    breakout_min_volume_ratio: 1.5
  # rs_policy_by_setup_family removed (Task HIGH-1): a leftover key here must
  # be silently ignored, not error and not gain any parsed effect.
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
    dry_up_lookback_sessions: 4
    dry_up_reference_sessions: 18
    dry_up_max_ratio: 0.40
    expansion_min_ratio: 1.75
    expansion_requires_positive_close: false
""",
        encoding="utf-8",
    )

    cfg = load_swing_config(path)

    assert cfg.setup_phase_config.thresholds.compression_max_bb_width_pctile == 0.15
    assert cfg.setup_phase_config.thresholds.breakout_min_volume_ratio == 1.5
    assert cfg.setup_phase_config.volume_trigger.require_trusted_volume is True
    assert (
        cfg.setup_phase_config.volume_trigger.trusted_benchmark_volume_sources
        == ("stockbit", "idx")
    )
    assert cfg.setup_phase_config.volume_trigger.min_valid_20d_sessions == 19
    assert cfg.setup_phase_config.volume_trigger.zero_volume_tolerance == 0
    assert cfg.setup_phase_config.volume_trigger.dry_up_lookback_sessions == 4
    assert cfg.setup_phase_config.volume_trigger.dry_up_reference_sessions == 18
    assert cfg.setup_phase_config.volume_trigger.dry_up_max_ratio == 0.40
    assert cfg.setup_phase_config.volume_trigger.expansion_min_ratio == 1.75
    assert cfg.setup_phase_config.volume_trigger.expansion_requires_positive_close is False
    assert not hasattr(cfg.setup_phase_config, "rs_policy_for")
    assert not hasattr(cfg.setup_phase_config, "rs_policy_by_setup_family")


def test_load_swing_config_parses_setup_phase_requirements(tmp_path: Path):
    path = tmp_path / "swing_setups.yaml"
    path.write_text(
        """
setup_phase:
  requirements:
    breakout:
      required_sequence: [COMPRESSION, BREAKOUT_CONFIRMATION]
      enter_phases: [BREAKOUT_CONFIRMATION]
    pullback:
      required_sequence: []
      requires_reclaim_or_pivot: true
      enter_phases: [BREAKOUT_CONFIRMATION]
""",
        encoding="utf-8",
    )

    cfg = load_swing_config(path)

    assert cfg.setup_phase_config.requirement_for("breakout").required_sequence == (
        SetupPhaseState.COMPRESSION,
        SetupPhaseState.BREAKOUT_CONFIRMATION,
    )
    assert cfg.setup_phase_config.requirement_for("pullback").requires_reclaim_or_pivot is True


def test_load_swing_config_invalid_phase_name_raises(tmp_path: Path):
    # A typo'd phase name in setup_phase.requirements must fail loudly, not
    # silently degrade to default phase requirements/entry-authority rules —
    # a misconfigured setup-phase guardrail that "looks like it loaded" is
    # worse than one that errors. This is a deliberate carve-out from the
    # loader's generic fail-soft-to-defaults contract, which still applies to
    # every other malformed field (bad numeric strings, bad enums, etc.).
    path = tmp_path / "swing_setups.yaml"
    path.write_text(
        """
setup_phase:
  requirements:
    breakout:
      required_sequence: [NOT_A_REAL_PHASE]
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid setup phase name"):
        load_swing_config(path)


def test_load_swing_config_missing_requirements_key_uses_defaults(tmp_path: Path):
    path = tmp_path / "swing_setups.yaml"
    path.write_text(
        """
setup_phase:
  thresholds:
    compression_max_bb_width_pctile: 0.15
  volume_trigger:
    require_trusted_volume: true
""",
        encoding="utf-8",
    )

    cfg = load_swing_config(path)

    assert (
        cfg.setup_phase_config.requirements_by_family
        == SetupPhaseConfig().requirements_by_family
    )
    assert (
        cfg.setup_phase_config.requirement_for("accumulation")
        == SetupPhaseConfig().requirement_for("accumulation")
    )


def test_load_swing_config_derives_setup_name_alias_from_family(tmp_path: Path):
    path = tmp_path / "swing_setups.yaml"
    path.write_text(
        """
setups:
  coiled-spring:
    enabled: true
    family: breakout
    entry_authority: true
    can_enter_from_phases: [BREAKOUT_CONFIRMATION]
    gates: {}

setup_phase:
  requirements:
    breakout:
      required_sequence: [COMPRESSION, BREAKOUT_CONFIRMATION]
""",
        encoding="utf-8",
    )

    cfg = load_swing_config(path)

    assert (
        cfg.setup_phase_config.requirement_for("coiled-spring").required_sequence
        == cfg.setup_phase_config.requirement_for("breakout").required_sequence
    )


def test_load_swing_config_production_split_config_loads_setup_phase_requirements():
    # Regression guard for the merge-gap fix: SWING_SETUPS_CONFIG_PATH's
    # "setup_phase" key was previously never merged into the split-config
    # dict, so setup_phase.requirements silently never loaded in production.
    # Calling load_swing_config() with no argument exercises the real
    # split-config path against the actual repo config/swing_setups.yaml.
    cfg = load_swing_config()

    assert cfg.setup_phase_config.requirement_for("coiled-spring").required_sequence == (
        SetupPhaseState.COMPRESSION,
        SetupPhaseState.BREAKOUT_CONFIRMATION,
    )
    assert cfg.setup_phase_config.requirement_for("foreign-bounce").required_sequence == (
        SetupPhaseState.ACCUMULATION,
        SetupPhaseState.COMPRESSION,
        SetupPhaseState.BREAKOUT_CONFIRMATION,
    )
