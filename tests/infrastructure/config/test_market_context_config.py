from src.infrastructure.config.market_context_config import load_market_context_config


def test_load_market_context_config_reads_scoring_policy(tmp_path):
    path = tmp_path / "market_context_engine.yaml"
    path.write_text(
        """
market_context_engine:
  scoring:
    neutral_score: 0.45
    stale_business_day_gap: 2
    coverage_warning_unavailable_ratio: 0.75
    labels:
      favorable_min_score: 0.7
      neutral_min_score: 0.4
  factors:
    vix:
      score_anchors:
        very_low: 0.95
        low: 0.8
        elevated: 0.55
        risk_off: 0.3
        high: 0.05
    idx_trend:
      thresholds:
        fast_sma_adjustment: 0.08
    foreign_flow:
      thresholds:
        bearish_diff_ratio: -0.4
        bullish_diff_ratio: 0.6
""",
        encoding="utf-8",
    )

    cfg = load_market_context_config(path)

    assert cfg.scoring.neutral_score == 0.45
    assert cfg.scoring.stale_business_day_gap == 2
    assert cfg.scoring.coverage_warning_unavailable_ratio == 0.75
    assert cfg.scoring.labels.favorable_min_score == 0.7
    assert cfg.scoring.labels.neutral_min_score == 0.4
    assert cfg.vix.very_low_score == 0.95
    assert cfg.vix.low_score == 0.8
    assert cfg.vix.elevated_score == 0.55
    assert cfg.vix.risk_off_score == 0.3
    assert cfg.vix.high_score == 0.05
    assert cfg.idx_trend.fast_sma_adjustment == 0.08
    assert cfg.foreign_flow.bearish_diff_ratio == -0.4
    assert cfg.foreign_flow.bullish_diff_ratio == 0.6
