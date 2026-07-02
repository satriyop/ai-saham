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
