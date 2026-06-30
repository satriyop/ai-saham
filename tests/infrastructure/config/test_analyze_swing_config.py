from pathlib import Path

from src.infrastructure.config.analyze_swing_config import load_analyze_swing_config


def test_load_analyze_swing_config_reads_workflow_defaults(tmp_path: Path):
    config = tmp_path / "analyze_swing.yaml"
    config.write_text(
        """
analyze_swing:
  auto_refresh:
    market_days: 250
    broker_days: 60
  sentiment:
    max_headlines: 12
    days: 5
  evidence:
    flow_detail_window_sessions: 20
  candidate:
    min_net_buy_days: 1
    min_foreign_flow_score: 35
""",
        encoding="utf-8",
    )

    loaded = load_analyze_swing_config(config)

    assert loaded.market_refresh_days == 250
    assert loaded.broker_refresh_days == 60
    assert loaded.sentiment_max_headlines == 12
    assert loaded.sentiment_days == 5
    assert loaded.flow_detail_window_sessions == 20
    assert loaded.candidate_min_net_buy_days == 1
    assert loaded.candidate_min_foreign_flow_score == 35.0
