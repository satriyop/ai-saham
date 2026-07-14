from src.application.services.swing_tuning_review_summary import (
    summarize_review_record,
)


def test_summarize_review_record_fully_populated():
    record = {
        "recorded_at": "2026-07-01T10:00:00+07:00",
        "setup": "foreign-bounce",
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
        "sample": {"status": "TRADE_READY", "min_sample_size": 30},
        "backtest_summary": {
            "trade_count": 12,
            "candidate_observation_count": 40,
            "total_return_pct": 4.5,
            "win_rate_pct": 58.3,
        },
        "tuning_config_diff": {
            "status": "PROPOSED_VALUES_DRY_RUN",
            "summary": {"proposed_count": 2, "rejected_count": 1},
        },
        "is_ratio": 0.70,
        "is_end_date": "2026-01-25",
        "oos_backtest_summary": {
            "trade_count": 5,
            "total_return_pct": 2.1,
            "win_rate_pct": 60.0,
        },
    }

    summary = summarize_review_record(record)

    assert summary.recorded_at == "2026-07-01T10:00:00+07:00"
    assert summary.setup == "foreign-bounce"
    assert summary.start_date == "2026-01-01"
    assert summary.end_date == "2026-01-31"
    assert summary.sample_status == "TRADE_READY"
    assert summary.min_sample_size == 30
    assert summary.trade_count == 12
    assert summary.candidate_observation_count == 40
    assert summary.total_return_pct == 4.5
    assert summary.win_rate_pct == 58.3
    assert summary.tuning_diff_status == "PROPOSED_VALUES_DRY_RUN"
    assert summary.proposed_count == 2
    assert summary.rejected_count == 1
    assert summary.is_ratio == 0.70
    assert summary.walk_forward_enforced is True
    assert summary.oos_trade_count == 5
    assert summary.oos_total_return_pct == 2.1
    assert summary.oos_win_rate_pct == 60.0


def test_summarize_review_record_sparse_record_returns_none_fields():
    summary = summarize_review_record({})

    assert summary.recorded_at is None
    assert summary.setup is None
    assert summary.start_date is None
    assert summary.end_date is None
    assert summary.sample_status is None
    assert summary.min_sample_size is None
    assert summary.trade_count is None
    assert summary.candidate_observation_count is None
    assert summary.total_return_pct is None
    assert summary.win_rate_pct is None
    assert summary.tuning_diff_status is None
    assert summary.proposed_count is None
    assert summary.rejected_count is None
    assert summary.is_ratio is None
    assert summary.walk_forward_enforced is False
    assert summary.oos_trade_count is None
    assert summary.oos_total_return_pct is None
    assert summary.oos_win_rate_pct is None


def test_summarize_review_record_tolerates_malformed_numeric_fields():
    summary = summarize_review_record(
        {
            "sample": {"min_sample_size": "not-a-number"},
            "backtest_summary": {"trade_count": "also-not-a-number"},
        }
    )

    assert summary.min_sample_size is None
    assert summary.trade_count is None
