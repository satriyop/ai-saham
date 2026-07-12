"""Walk-forward validation and enforcement tests for swing tuning."""

import json

from src.application.services.swing_tuning_patch_validator import (
    SwingTuningPatchValidator,
)
from src.infrastructure.config.swing_tuning_document_loader import (
    swing_tuning_document_loader,
)
from src.application.services.swing_tuning_review_journal import (
    SwingTuningReviewJournal,
    _summarize_record,
)
from src.infrastructure.persistence.swing_tuning_review_jsonl_writer import (
    SwingTuningReviewJsonlWriter,
)
from tests.application.services.swing_tuning_guardrail_fixtures import (
    _COMPLETE_SOURCE_REVIEW,
    _write_config,
)


def test_summary_without_is_ratio_is_not_walk_forward_enforced():
    summary = _summarize_record({})
    assert summary.is_ratio is None
    assert summary.walk_forward_enforced is False


def test_summary_with_split_is_walk_forward_enforced():
    summary = _summarize_record({"is_ratio": 0.70, "is_end_date": "2026-04-01"})
    assert summary.is_ratio == 0.70
    assert summary.walk_forward_enforced is True


def test_summary_with_is_ratio_but_no_is_end_date_is_not_enforced():
    summary = _summarize_record({"is_ratio": 0.70})
    assert summary.is_ratio == 0.70
    assert summary.walk_forward_enforced is False


def test_compare_latest_notes_when_walk_forward_not_enforced(tmp_path):
    path = tmp_path / "journals" / "swing_tuning_reviews.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    store = SwingTuningReviewJsonlWriter(path)
    store.append(
        {
            "recorded_at": "2026-07-01T10:00:00+07:00",
            "artifact_type": "swing_tuning_review",
            "setup": "foreign-bounce",
            "is_ratio": 0.70,
            "backtest_summary": {"trade_count": 10},
        }
    )
    store.append(
        {
            "recorded_at": "2026-07-02T10:00:00+07:00",
            "artifact_type": "swing_tuning_review",
            "setup": "foreign-bounce",
            "is_ratio": 1.0,
            "backtest_summary": {"trade_count": 12},
        }
    )

    comparison = SwingTuningReviewJournal(store).compare_latest()

    assert comparison.status == "READY"
    assert comparison.candidate.is_ratio == 1.0
    assert comparison.candidate.walk_forward_enforced is False
    assert any(note.startswith("walk_forward_not_enforced") for note in comparison.notes)


def test_patch_with_walk_forward_false_fails_validation(tmp_path):
    _write_config(tmp_path)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "artifact_type": "swing_tuning_patch_review",
                "apply": {"supported": False},
                "source_review": {"walk_forward_enforced": False},
                "patch_items": [],
            }
        )
    )
    report = SwingTuningPatchValidator(document_loader=swing_tuning_document_loader(tmp_path)).validate(patch_path)
    assert report.valid is False
    assert any("walk_forward_not_enforced" in issue for issue in report.issues)


def test_patch_with_walk_forward_true_but_missing_oos_fails(tmp_path):
    _write_config(tmp_path)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "artifact_type": "swing_tuning_patch_review",
                "apply": {"supported": False},
                "source_review": {
                    "walk_forward_enforced": True,
                    "is_ratio": 0.70,
                    "is_end_date": "2026-04-01",
                    "oos_start_date": "2026-04-02",
                    "full_end_date": "2026-07-01",
                },
                "patch_items": [],
            }
        )
    )
    report = SwingTuningPatchValidator(document_loader=swing_tuning_document_loader(tmp_path)).validate(patch_path)
    assert report.valid is False
    assert any("walk_forward_not_enforced" in issue for issue in report.issues)


def test_patch_with_complete_source_review_passes_validation(tmp_path):
    _write_config(tmp_path)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "artifact_type": "swing_tuning_patch_review",
                "apply": {"supported": False},
                "source_review": _COMPLETE_SOURCE_REVIEW,
                "patch_items": [],
            }
        )
    )
    report = SwingTuningPatchValidator(document_loader=swing_tuning_document_loader(tmp_path)).validate(patch_path)
    assert report.valid is True
    assert all("walk_forward_not_enforced" not in issue for issue in report.issues)


def test_truthy_string_walk_forward_fails(tmp_path):
    _write_config(tmp_path)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "artifact_type": "swing_tuning_patch_review",
                "apply": {"supported": False},
                "source_review": {
                    **_COMPLETE_SOURCE_REVIEW,
                    "walk_forward_enforced": "true",
                },
                "patch_items": [],
            }
        )
    )
    report = SwingTuningPatchValidator(document_loader=swing_tuning_document_loader(tmp_path)).validate(patch_path)
    assert report.valid is False
    assert any("walk_forward_not_enforced" in issue for issue in report.issues)


def test_malformed_oos_start_date_fails(tmp_path):
    _write_config(tmp_path)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "artifact_type": "swing_tuning_patch_review",
                "apply": {"supported": False},
                "source_review": {
                    **_COMPLETE_SOURCE_REVIEW,
                    "oos_start_date": "not-a-date",
                },
                "patch_items": [],
            }
        )
    )
    report = SwingTuningPatchValidator(document_loader=swing_tuning_document_loader(tmp_path)).validate(patch_path)
    assert report.valid is False
    assert any("walk_forward_not_enforced" in issue for issue in report.issues)


def test_oos_start_date_not_after_is_end_date_fails(tmp_path):
    _write_config(tmp_path)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "artifact_type": "swing_tuning_patch_review",
                "apply": {"supported": False},
                "source_review": {
                    **_COMPLETE_SOURCE_REVIEW,
                    "oos_start_date": "2026-04-01",
                },
                "patch_items": [],
            }
        )
    )
    report = SwingTuningPatchValidator(document_loader=swing_tuning_document_loader(tmp_path)).validate(patch_path)
    assert report.valid is False
    assert any("walk_forward_not_enforced" in issue for issue in report.issues)
