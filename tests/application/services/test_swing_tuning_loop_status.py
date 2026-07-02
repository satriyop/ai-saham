import json

from src.application.services.swing_tuning_loop_status import (
    SwingTuningLoopStatusService,
)
from src.infrastructure.persistence.swing_tuning_review_jsonl_writer import (
    SwingTuningReviewJsonlWriter,
)


def test_swing_tuning_loop_status_starts_with_save_review_action(tmp_path):
    journal_path = tmp_path / "journals" / "swing_tuning_reviews.jsonl"

    report = SwingTuningLoopStatusService(
        SwingTuningReviewJsonlWriter(journal_path),
        config_root=tmp_path,
    ).status(
        review_journal_path=journal_path,
        patch_path=tmp_path / "journals" / "swing_tuning_patch.json",
        apply_log_path=tmp_path / "journals" / "swing_tuning_apply_log.jsonl",
        apply_records=[],
    )

    assert report.status == "IN_PROGRESS"
    assert report.next_action == "RUN_TUNE_SWING_SAVE"
    assert report.review.total_records == 0
    assert report.patch.exists is False


def test_swing_tuning_loop_status_reports_ready_measurement(tmp_path):
    config_dir = tmp_path / "config"
    journal_dir = tmp_path / "journals"
    config_dir.mkdir()
    journal_dir.mkdir()
    (config_dir / "signal_engine.yaml").write_text(
        "signal_engine:\n"
        "  classification:\n"
        "    strong_min_score: 71\n",
        encoding="utf-8",
    )
    journal_path = journal_dir / "swing_tuning_reviews.jsonl"
    patch_path = journal_dir / "swing_tuning_patch.json"
    apply_log_path = journal_dir / "swing_tuning_apply_log.jsonl"
    review_rows = [
        {
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
        },
        {
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
        },
    ]
    patch_payload = {
        "artifact_type": "swing_tuning_patch_review",
        "apply": {"supported": False},
        "patch_items": [
            {
                "target_path": (
                    "config/signal_engine.yaml:"
                    "signal_engine.classification.strong_min_score"
                ),
                "current_value": 71,
                "proposed_value": 71,
            }
        ],
    }
    apply_records = [
        {
            "artifact_type": "swing_tuning_patch_apply",
            "applied_at": "2026-07-02T09:00:00+07:00",
            "patch_path": str(patch_path),
            "changes": [
                {
                    "target_path": (
                        "config/signal_engine.yaml:"
                        "signal_engine.classification.strong_min_score"
                    ),
                    "old_value": 70,
                    "new_value": 71,
                }
            ],
        }
    ]
    journal_path.write_text(
        "\n".join(json.dumps(row) for row in review_rows) + "\n",
        encoding="utf-8",
    )
    patch_path.write_text(json.dumps(patch_payload), encoding="utf-8")

    report = SwingTuningLoopStatusService(
        SwingTuningReviewJsonlWriter(journal_path),
        config_root=tmp_path,
    ).status(
        review_journal_path=journal_path,
        patch_path=patch_path,
        apply_log_path=apply_log_path,
        apply_records=apply_records,
    )

    assert report.status == "READY"
    assert report.next_action == "REVIEW_POST_APPLY_MEASUREMENT"
    assert report.patch.exists is True
    assert report.patch.validation is not None
    assert report.patch.validation.valid is True
    assert report.patch.verify is not None
    assert report.patch.verify.verified is True
    assert report.apply.post_apply_measurement.status == "READY"
