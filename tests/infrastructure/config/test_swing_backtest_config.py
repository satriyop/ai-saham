from pathlib import Path

from src.infrastructure.config.swing_backtest_config import load_swing_backtest_config


def test_load_swing_backtest_config_reads_portfolio_and_execution(tmp_path: Path):
    config = tmp_path / "swing_backtest.yaml"
    config.write_text(
        """
swing_backtest:
  portfolio:
    capital: 50000000
    risk_pct: 1.5
    max_positions: 3
  execution:
    take_profit_pct: 6
    stop_loss_pct: 4
    max_hold_days: 12
    cost_bps: 15
    entry_timing: same_day_close
    forward_data_lookahead_days: 30
    same_day_exit_priority: target_first
  attribution:
    score_buckets:
      high_min_score: 80
      mid_min_score: 60
""",
        encoding="utf-8",
    )

    loaded = load_swing_backtest_config(config)

    assert loaded.capital == 50_000_000
    assert loaded.risk_pct == 1.5
    assert loaded.max_positions == 3
    assert loaded.take_profit_pct == 6.0
    assert loaded.stop_loss_pct == 4.0
    assert loaded.max_hold_days == 12
    assert loaded.cost_bps == 15.0
    assert loaded.entry_timing == "same_day_close"
    assert loaded.forward_data_lookahead_days == 30
    assert loaded.same_day_exit_priority == "target_first"
    assert loaded.attribution_high_min_score == 80.0
    assert loaded.attribution_mid_min_score == 60.0
