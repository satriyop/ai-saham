from src.application.services.swing_tuning_post_apply_measurement import (
    measure_post_apply,
)

_REVIEW_BEFORE = {
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
    },
}

_REVIEW_AFTER = {
    "recorded_at": "2026-07-03T10:00:00+07:00",
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
    },
}

_APPLY_RECORD = {
    "artifact_type": "swing_tuning_patch_apply",
    "applied_at": "2026-07-02T09:00:00+07:00",
    "patch_path": "journals/swing_tuning_patch.json",
    "changes": [
        {
            "target_path": "config/signal_engine.yaml:x",
            "old_value": 70,
            "new_value": 71,
        }
    ],
}


def test_measure_post_apply_no_apply_log():
    measurement = measure_post_apply([], [_REVIEW_BEFORE, _REVIEW_AFTER])

    assert measurement.status == "NO_APPLY_LOG"
    assert measurement.applied_patch is None
    assert measurement.baseline is None
    assert measurement.candidate is None
    assert measurement.metric_deltas == ()
    assert measurement.notes == ("No swing_tuning_patch_apply records were found.",)


def test_measure_post_apply_invalid_apply_log_missing_applied_at():
    apply_records = [
        {
            "artifact_type": "swing_tuning_patch_apply",
            "patch_path": "journals/swing_tuning_patch.json",
            "changes": [],
        }
    ]

    measurement = measure_post_apply(apply_records, [_REVIEW_BEFORE, _REVIEW_AFTER])

    assert measurement.status == "APPLY_LOG_INVALID"
    assert measurement.applied_patch is not None
    assert measurement.baseline is None
    assert measurement.candidate is None
    assert measurement.metric_deltas == ()


def test_measure_post_apply_insufficient_review_history():
    measurement = measure_post_apply([_APPLY_RECORD], [_REVIEW_BEFORE])

    assert measurement.status == "INSUFFICIENT_REVIEW_HISTORY"
    assert measurement.applied_patch is not None
    assert measurement.baseline is not None
    assert measurement.candidate is None
    assert measurement.metric_deltas == ()


def test_measure_post_apply_ready_with_metric_deltas():
    measurement = measure_post_apply(
        [_APPLY_RECORD], [_REVIEW_BEFORE, _REVIEW_AFTER]
    )

    assert measurement.status == "READY"
    assert measurement.applied_patch.change_count == 1
    assert measurement.applied_patch.target_paths == ("config/signal_engine.yaml:x",)
    assert measurement.baseline.recorded_at == "2026-07-01T10:00:00+07:00"
    assert measurement.candidate.recorded_at == "2026-07-03T10:00:00+07:00"
    deltas = {delta.name: delta.delta for delta in measurement.metric_deltas}
    assert deltas["trade_count"] == 2
    assert deltas["total_return_pct"] == 1.5
