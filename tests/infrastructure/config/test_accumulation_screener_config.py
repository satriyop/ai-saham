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
  filters:
    min_accum_score:
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
    assert loaded.min_accum_score.enabled is True
    assert loaded.min_accum_score.value == 55.0
    assert loaded.min_signal_score.enabled is True
    assert loaded.min_signal_score.value == 60.0
