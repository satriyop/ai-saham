from src.application.services.swing_tuning_review_comparison import (
    compare_latest_review,
)

_RECORD_A = {
    "recorded_at": "2026-07-01T10:00:00+07:00",
    "artifact_type": "swing_tuning_review",
    "setup": "foreign-bounce",
    "sample": {"status": "TRADE_READY"},
    "backtest_summary": {
        "trade_count": 10,
        "candidate_observation_count": 30,
        "total_return_pct": 1.5,
        "win_rate_pct": 50.0,
    },
    "tuning_config_diff": {
        "status": "PROPOSED_VALUES_DRY_RUN",
        "summary": {"proposed_count": 1, "rejected_count": 2},
        "diff_items": [
            {
                "target_path": "config/signal_engine.yaml:a",
                "proposed_value": 60,
            },
        ],
    },
}

_RECORD_B = {
    "recorded_at": "2026-07-02T10:00:00+07:00",
    "artifact_type": "swing_tuning_review",
    "setup": "foreign-bounce",
    "sample": {"status": "TRADE_READY"},
    "backtest_summary": {
        "trade_count": 12,
        "candidate_observation_count": 35,
        "total_return_pct": 3.0,
        "win_rate_pct": 55.0,
    },
    "tuning_config_diff": {
        "status": "PROPOSED_VALUES_DRY_RUN",
        "summary": {"proposed_count": 1, "rejected_count": 1},
        "diff_items": [
            {
                "target_path": "config/risk_engine.yaml:b",
                "proposed_value": 100,
            },
        ],
    },
    "is_ratio": 0.70,
    "is_end_date": "2026-06-15",
}


def test_compare_latest_review_no_records():
    comparison = compare_latest_review([])

    assert comparison.status == "INSUFFICIENT_HISTORY"
    assert comparison.baseline is None
    assert comparison.candidate is None
    assert comparison.metric_deltas == ()
    assert comparison.notes == ("Need at least two saved tuning reviews to compare.",)


def test_compare_latest_review_single_record():
    comparison = compare_latest_review([_RECORD_A])

    assert comparison.status == "INSUFFICIENT_HISTORY"
    assert comparison.baseline is None
    assert comparison.candidate is not None
    assert comparison.candidate.recorded_at == "2026-07-01T10:00:00+07:00"
    assert comparison.metric_deltas == ()


def test_compare_latest_review_two_records_ready():
    sorted_records = [_RECORD_B, _RECORD_A]  # descending by recorded_at

    comparison = compare_latest_review(sorted_records)

    assert comparison.status == "READY"
    assert comparison.baseline.recorded_at == "2026-07-01T10:00:00+07:00"
    assert comparison.candidate.recorded_at == "2026-07-02T10:00:00+07:00"
    deltas = {delta.name: delta.delta for delta in comparison.metric_deltas}
    assert deltas["trade_count"] == 2
    assert deltas["candidate_observation_count"] == 5
    assert deltas["total_return_pct"] == 1.5
    assert deltas["win_rate_pct"] == 5.0
    assert comparison.newly_proposed_target_paths == ("config/risk_engine.yaml:b",)
    assert comparison.disappeared_target_paths == ("config/signal_engine.yaml:a",)


def test_compare_latest_review_notes_walk_forward_not_enforced():
    candidate_full_data = {**_RECORD_B, "is_ratio": 1.0, "is_end_date": None}
    sorted_records = [candidate_full_data, _RECORD_A]

    comparison = compare_latest_review(sorted_records)

    assert comparison.status == "READY"
    assert any(
        note.startswith("walk_forward_not_enforced") for note in comparison.notes
    )
