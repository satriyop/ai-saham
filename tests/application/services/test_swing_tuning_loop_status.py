import json

_COMPLETE_SOURCE_REVIEW = {
    "readiness_state": "PATCH_ELIGIBLE",
    "walk_forward_enforced": True,
    "is_ratio": 0.70,
    "is_end_date": "2026-04-01",
    "oos_start_date": "2026-04-02",
    "full_end_date": "2026-07-01",
    "sample": {"status": "TRADE_READY", "min_sample_size": 30},
    "backtest_summary": {"trade_count": 60},
    "oos_backtest_summary": {
        "trade_count": 30,
        "total_return_pct": 3.2,
        "average_return_pct": 0.2,
        "win_rate_pct": 50.0,
        "profit_factor": 1.5,
        "drawdown_regression_pct": 0.0,
    },
    "attribution": {
        "market_regime": {
            "buckets": [
                {"key": "RISK_ON", "oos_trade_count": 15, "oos_profit": 1.0},
                {"key": "NEUTRAL", "oos_trade_count": 15, "oos_profit": 0.8},
            ],
        },
        "signal_authority_coverage_bucket": {"buckets": [{"key": "HIGH", "observation_count": 30}]},
        "setup_readiness_status": {"buckets": [{"key": "READY", "observation_count": 30}]},
    },
}

from src.application.services.swing_tuning_loop_status import (
    SwingTuningLoopStatusService,
)
from src.infrastructure.config.swing_tuning_document_loader import (
    swing_tuning_document_loader,
)
from src.infrastructure.persistence.swing_tuning_review_jsonl_writer import (
    SwingTuningReviewJsonlWriter,
)


def test_swing_tuning_loop_status_starts_with_save_review_action(tmp_path):
    journal_path = tmp_path / "journals" / "swing_tuning_reviews.jsonl"

    report = SwingTuningLoopStatusService(
        SwingTuningReviewJsonlWriter(journal_path),
        document_loader=swing_tuning_document_loader(tmp_path),
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
        "source_review": _COMPLETE_SOURCE_REVIEW,
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
        document_loader=swing_tuning_document_loader(tmp_path),
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


def test_swing_tuning_loop_status_handles_empty_patch_from_insufficient_sample(tmp_path):
    journal_dir = tmp_path / "journals"
    journal_dir.mkdir()
    journal_path = journal_dir / "swing_tuning_reviews.jsonl"
    patch_path = journal_dir / "swing_tuning_patch.json"
    apply_log_path = journal_dir / "swing_tuning_apply_log.jsonl"
    review_row = {
        "recorded_at": "2026-07-03T10:00:00+07:00",
        "artifact_type": "swing_tuning_review",
        "setup": "foreign-bounce",
        "sample": {"status": "INSUFFICIENT_SAMPLE", "min_sample_size": 30},
        "backtest_summary": {
            "trade_count": 0,
            "candidate_observation_count": 20,
            "total_return_pct": 0.0,
            "win_rate_pct": None,
        },
        "tuning_config_diff": {
            "status": "BLOCKED",
            "summary": {"proposed_count": 0, "rejected_count": 16},
        },
    }
    patch_payload = {
        "artifact_type": "swing_tuning_patch_review",
        "apply": {"supported": False},
        "source_review": _COMPLETE_SOURCE_REVIEW,
        "patch_items": [],
    }
    journal_path.write_text(json.dumps(review_row) + "\n", encoding="utf-8")
    patch_path.write_text(json.dumps(patch_payload), encoding="utf-8")

    report = SwingTuningLoopStatusService(
        SwingTuningReviewJsonlWriter(journal_path),
        document_loader=swing_tuning_document_loader(tmp_path),
    ).status(
        review_journal_path=journal_path,
        patch_path=patch_path,
        apply_log_path=apply_log_path,
        apply_records=[],
    )

    assert report.status == "IN_PROGRESS"
    assert report.next_action == "RUN_TUNE_SWING_WITH_LARGER_SAMPLE"
    assert report.patch.validation is not None
    assert report.patch.validation.item_count == 0
    assert report.review.latest_review is not None
    assert report.review.latest_review.sample_status == "INSUFFICIENT_SAMPLE"
    assert report.review.latest_review.min_sample_size == 30
