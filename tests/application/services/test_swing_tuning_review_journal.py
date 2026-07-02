import json

from src.application.services.swing_tuning_review_journal import (
    SwingTuningReviewJournal,
)
from src.infrastructure.persistence.swing_tuning_review_jsonl_writer import (
    SwingTuningReviewJsonlWriter,
)


def test_swing_tuning_review_journal_appends_jsonl_record(tmp_path):
    path = tmp_path / "journals" / "swing_tuning_reviews.jsonl"
    journal = SwingTuningReviewJournal(SwingTuningReviewJsonlWriter(path))

    result = journal.append_review({
        "schema_version": 1,
        "artifact_type": "swing_tuning_review",
        "setup": "foreign-bounce",
        "tuning_config_diff": {"can_apply": False},
    })

    assert result.saved is True
    assert result.record_count == 1
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["recorded_at"] == result.recorded_at
    assert rows[0]["artifact_type"] == "swing_tuning_review"
    assert rows[0]["tuning_config_diff"]["can_apply"] is False


def test_swing_tuning_review_journal_summarizes_recent_runs(tmp_path):
    path = tmp_path / "journals" / "swing_tuning_reviews.jsonl"
    store = SwingTuningReviewJsonlWriter(path)
    store.append({
        "recorded_at": "2026-07-01T10:00:00+07:00",
        "artifact_type": "swing_tuning_review",
        "setup": "foreign-bounce",
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
        "sample": {"status": "INSUFFICIENT_SAMPLE"},
        "backtest_summary": {
            "trade_count": 0,
            "candidate_observation_count": 3,
            "total_return_pct": 0.0,
            "win_rate_pct": None,
        },
        "tuning_config_diff": {
            "status": "BLOCKED",
            "summary": {"proposed_count": 0, "rejected_count": 5},
        },
    })
    store.append({
        "recorded_at": "2026-07-02T10:00:00+07:00",
        "artifact_type": "swing_tuning_review",
        "setup": "coiled-spring",
        "start_date": "2026-02-01",
        "end_date": "2026-02-28",
        "sample": {"status": "TRADE_READY"},
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
    })

    report = SwingTuningReviewJournal(store).review(limit=1)

    assert report.total_records == 2
    assert len(report.records) == 1
    latest = report.records[0]
    assert latest.setup == "coiled-spring"
    assert latest.sample_status == "TRADE_READY"
    assert latest.trade_count == 12
    assert latest.candidate_observation_count == 40
    assert latest.total_return_pct == 4.5
    assert latest.win_rate_pct == 58.3
    assert latest.tuning_diff_status == "PROPOSED_VALUES_DRY_RUN"
    assert latest.proposed_count == 2
    assert latest.rejected_count == 1


def test_swing_tuning_review_journal_compares_latest_runs(tmp_path):
    path = tmp_path / "journals" / "swing_tuning_reviews.jsonl"
    store = SwingTuningReviewJsonlWriter(path)
    store.append({
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
    })
    store.append({
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
    })

    comparison = SwingTuningReviewJournal(store).compare_latest()

    assert comparison.status == "READY"
    assert comparison.baseline is not None
    assert comparison.candidate is not None
    assert comparison.baseline.recorded_at == "2026-07-01T10:00:00+07:00"
    assert comparison.candidate.recorded_at == "2026-07-02T10:00:00+07:00"
    deltas = {delta.name: delta.delta for delta in comparison.metric_deltas}
    assert deltas["trade_count"] == 2
    assert deltas["candidate_observation_count"] == 5
    assert deltas["total_return_pct"] == 1.5
    assert deltas["win_rate_pct"] == 5.0
    assert comparison.newly_proposed_target_paths == ("config/risk_engine.yaml:b",)
    assert comparison.disappeared_target_paths == ("config/signal_engine.yaml:a",)


def test_swing_tuning_review_journal_measures_latest_apply(tmp_path):
    path = tmp_path / "journals" / "swing_tuning_reviews.jsonl"
    store = SwingTuningReviewJsonlWriter(path)
    store.append({
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
    })
    store.append({
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
    })
    apply_records = [
        {
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
    ]

    measurement = SwingTuningReviewJournal(store).measure_latest_apply(apply_records)

    assert measurement.status == "READY"
    assert measurement.applied_patch is not None
    assert measurement.applied_patch.change_count == 1
    assert measurement.applied_patch.target_paths == ("config/signal_engine.yaml:x",)
    assert measurement.baseline is not None
    assert measurement.candidate is not None
    assert measurement.baseline.recorded_at == "2026-07-01T10:00:00+07:00"
    assert measurement.candidate.recorded_at == "2026-07-03T10:00:00+07:00"
    deltas = {delta.name: delta.delta for delta in measurement.metric_deltas}
    assert deltas["trade_count"] == 2
    assert deltas["total_return_pct"] == 1.5


def test_swing_tuning_review_journal_measurement_requires_apply_log(tmp_path):
    path = tmp_path / "journals" / "swing_tuning_reviews.jsonl"
    store = SwingTuningReviewJsonlWriter(path)

    measurement = SwingTuningReviewJournal(store).measure_latest_apply([])

    assert measurement.status == "NO_APPLY_LOG"
    assert measurement.applied_patch is None
    assert measurement.metric_deltas == ()
