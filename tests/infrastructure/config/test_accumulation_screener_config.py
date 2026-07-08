from pathlib import Path

from src.infrastructure.config.accumulation_screener_config import (
    load_accumulation_screener_config,
)


def test_load_accumulation_screener_config_filters_and_weights(tmp_path: Path):
    config = tmp_path / "accumulation_screener.yaml"
    config.write_text(
        """
accumulation_screener:
  evidence:
    components:
      consistency:
        enabled: false
        weight: 12
  derived_features:
    rsi_period: 10
    trend_sma_period: 30
    trend_threshold_pct: 3.5
    bb_period: 18
    bb_history: 45
    market_vwap_period: 15
    resistance_ma_period: 150
    resistance_high_period: 180
    insider_lookback_days: 60
  filters:
    min_foreign_flow_score:
      enabled: true
      value: 55
    min_signal_score:
      enabled: true
      value: 60
""",
        encoding="utf-8",
    )

    loaded = load_accumulation_screener_config(config)

    assert loaded.foreign_flow_score_policy.consistency.enabled is False
    assert loaded.foreign_flow_score_policy.consistency.weight == 12.0
    assert loaded.min_foreign_flow_score.enabled is True
    assert loaded.min_foreign_flow_score.value == 55.0
    assert loaded.min_signal_score.enabled is True
    assert loaded.min_signal_score.value == 60.0
    assert loaded.derived_features.rsi_period == 10
    assert loaded.derived_features.trend_sma_period == 30
    assert loaded.derived_features.trend_threshold_pct == 3.5
    assert loaded.derived_features.bb_period == 18
    assert loaded.derived_features.bb_history == 45
    assert loaded.derived_features.market_vwap_period == 15
    assert loaded.derived_features.resistance_ma_period == 150
    assert loaded.derived_features.resistance_high_period == 180
    assert loaded.derived_features.insider_lookback_days == 60


def test_bb_squeeze_disabled_by_default_in_live_config():
    """BB compression is setup-phase/trigger-readiness diagnostic, not flow
    evidence — the shipped config must not score it by default."""
    loaded = load_accumulation_screener_config()
    assert loaded.foreign_flow_score_policy.bb_squeeze.enabled is False
    # Thresholds/weight are retained for possible future diagnostic/tuning use.
    assert loaded.foreign_flow_score_policy.bb_squeeze.weight == 10.0
    assert loaded.foreign_flow_score_policy.bb_squeeze.tight_pctile == 0.20
    assert loaded.foreign_flow_score_policy.bb_squeeze.loose_pctile == 0.40


def test_bb_squeeze_can_be_explicitly_re_enabled_via_yaml(tmp_path: Path):
    config = tmp_path / "accumulation_screener.yaml"
    config.write_text(
        """
accumulation_screener:
  evidence:
    components:
      bb_squeeze:
        enabled: true
        weight: 8
""",
        encoding="utf-8",
    )

    loaded = load_accumulation_screener_config(config)
    assert loaded.foreign_flow_score_policy.bb_squeeze.enabled is True
    assert loaded.foreign_flow_score_policy.bb_squeeze.weight == 8.0
