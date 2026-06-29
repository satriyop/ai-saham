from src.application.services.bootstrap import _resolve_signal_config


def test_resolve_signal_config_reads_policy_blocks():
    cfg = {
        "signal_engine": {
            "classification": {
                "strong_min_score": 80,
                "moderate_min_score": 55,
            },
            "missing_data": {
                "neutral_score": 45.0,
                "coverage_warning_missing_factors": 4,
            },
            "enrichment": {
                "insider_lookback_days": 120,
            },
            "input_mapping": {
                "foreign_flow_score": {
                    "max_score": 150.0,
                    "clamp": False,
                },
            },
            "scoring": {
                "bandar": {
                    "mandatory_signal_count": 4,
                    "signal_score_unit": 3,
                    "default_max_range": 12,
                },
                "seasonality": {
                    "tailwind_min_avg_return_pct": 1.0,
                    "tailwind_min_win_rate_pct": 60.0,
                    "headwind_max_avg_return_pct": -1.0,
                    "headwind_max_win_rate_pct": 40.0,
                },
                "analyst": {
                    "buy_score_max_points": 55.0,
                    "upside_score_max_points": 45.0,
                    "upside_cap_pct": 25.0,
                },
                "forward_pe": {
                    "very_cheap_pe": 8.0,
                    "cheap_pe": 12.0,
                    "fair_pe": 18.0,
                    "expensive_pe": 28.0,
                    "very_cheap_score": 98.0,
                    "cheap_score": 78.0,
                    "fair_score": 48.0,
                    "expensive_score": 18.0,
                    "post_expensive_pe_step": 8.0,
                    "post_expensive_score_decay": 12.0,
                },
            },
        }
    }

    resolved = _resolve_signal_config(cfg)

    assert resolved.classification.strong_min_score == 80
    assert resolved.classification.moderate_min_score == 55
    assert resolved.missing_data.neutral_score == 45.0
    assert resolved.missing_data.coverage_warning_missing_factors == 4
    assert resolved.enrichment.insider_lookback_days == 120
    assert resolved.input_mapping.foreign_flow_score.max_score == 150.0
    assert resolved.input_mapping.foreign_flow_score.clamp is False
    assert resolved.scoring.bandar.mandatory_signal_count == 4
    assert resolved.scoring.bandar.signal_score_unit == 3
    assert resolved.scoring.bandar.default_max_range == 12
    assert resolved.scoring.seasonality.tailwind_min_avg_return_pct == 1.0
    assert resolved.scoring.seasonality.tailwind_min_win_rate_pct == 60.0
    assert resolved.scoring.seasonality.headwind_max_avg_return_pct == -1.0
    assert resolved.scoring.seasonality.headwind_max_win_rate_pct == 40.0
    assert resolved.scoring.analyst.buy_score_max_points == 55.0
    assert resolved.scoring.analyst.upside_score_max_points == 45.0
    assert resolved.scoring.analyst.upside_cap_pct == 25.0
    assert resolved.scoring.forward_pe.very_cheap_pe == 8.0
    assert resolved.scoring.forward_pe.expensive_score == 18.0
    assert resolved.scoring.forward_pe.post_expensive_score_decay == 12.0
