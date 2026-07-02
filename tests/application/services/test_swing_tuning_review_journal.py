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
