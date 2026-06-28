from decimal import Decimal
from pathlib import Path

from src.infrastructure.config.pre_open_config import load_pre_open_screen_config


def test_load_pre_open_screen_config_applies_cli_overrides(tmp_path: Path):
    config_path = tmp_path / "pre_open_screener.yaml"
    config_path.write_text(
        """
screener:
  iev_min: 100000
  top_n: 5
  fast_mode: false
entry:
  capital: 3000000
  max_gap_pct: 0.03
risk:
  atr_multiplier: 1.0
  stop_loss_pct: 0.20
""",
        encoding="utf-8",
    )

    config = load_pre_open_screen_config(
        config_path,
        {
            "iev_min": 250000,
            "capital": 5000000,
            "top_n": 10,
            "fast_mode": True,
            "max_gap": 0.02,
            "atr_mult": 0.5,
        },
    )

    assert config.iev_min == 250_000
    assert config.capital == Decimal("5000000")
    assert config.top_n == 10
    assert config.fast_mode is True
    assert config.max_gap_pct == Decimal("0.02")
    assert config.atr_multiplier == Decimal("0.5")
