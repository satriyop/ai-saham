import json
from datetime import datetime

from src.application.services.swing_tuning_patch_validator import (
    SwingTuningPatchApplier,
    SwingTuningPatchDryRunPlanner,
    SwingTuningPatchValidator,
)


def _write_config(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "signal_engine.yaml").write_text(
        "signal_engine:\n"
        "  classification:\n"
        "    strong_min_score: 70\n",
        encoding="utf-8",
    )


def test_swing_tuning_patch_validator_accepts_matching_current_value(tmp_path):
    _write_config(tmp_path)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps({
        "artifact_type": "swing_tuning_patch_review",
        "apply": {"supported": False},
        "patch_items": [
            {
                "target_path": (
                    "config/signal_engine.yaml:"
                    "signal_engine.classification.strong_min_score"
                ),
                "current_value": 70,
                "proposed_value": 71,
            },
        ],
    }))

    report = SwingTuningPatchValidator(config_root=tmp_path).validate(patch_path)

    assert report.valid is True
    assert report.valid_item_count == 1
    assert report.item_results[0].issues == ()


def test_swing_tuning_patch_validator_rejects_stale_current_value(tmp_path):
    _write_config(tmp_path)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps({
        "artifact_type": "swing_tuning_patch_review",
        "apply": {"supported": False},
        "patch_items": [
            {
                "target_path": (
                    "config/signal_engine.yaml:"
                    "signal_engine.classification.strong_min_score"
                ),
                "current_value": 69,
                "proposed_value": 71,
            },
        ],
    }))

    report = SwingTuningPatchValidator(config_root=tmp_path).validate(patch_path)

    assert report.valid is False
    assert report.item_results[0].issues == ("current_value_mismatch",)


def test_swing_tuning_patch_validator_rejects_applyable_artifact(tmp_path):
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps({
        "artifact_type": "swing_tuning_patch_review",
        "apply": {"supported": True},
        "patch_items": [],
    }))

    report = SwingTuningPatchValidator(config_root=tmp_path).validate(patch_path)

    assert report.valid is False
    assert report.issues == ("apply_supported_must_be_false",)


def test_swing_tuning_patch_dry_run_plans_yaml_changes(tmp_path):
    _write_config(tmp_path)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps({
        "artifact_type": "swing_tuning_patch_review",
        "apply": {"supported": False},
        "patch_items": [
            {
                "target_path": (
                    "config/signal_engine.yaml:"
                    "signal_engine.classification.strong_min_score"
                ),
                "current_value": 70,
                "proposed_value": 71,
            },
        ],
    }))

    report = SwingTuningPatchDryRunPlanner(config_root=tmp_path).plan(patch_path)

    assert report.ready is True
    assert report.issues == ()
    assert len(report.changes) == 1
    assert report.changes[0].current_value == 70
    assert report.changes[0].proposed_value == 71


def test_swing_tuning_patch_dry_run_rejects_empty_patch(tmp_path):
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps({
        "artifact_type": "swing_tuning_patch_review",
        "apply": {"supported": False},
        "patch_items": [],
    }))

    report = SwingTuningPatchDryRunPlanner(config_root=tmp_path).plan(patch_path)

    assert report.ready is False
    assert report.issues == ("patch_has_no_items",)


def test_swing_tuning_patch_apply_writes_yaml_and_audit_log(tmp_path):
    _write_config(tmp_path)
    patch_path = tmp_path / "patch.json"
    log_path = tmp_path / "journals" / "swing_tuning_apply_log.jsonl"
    patch_path.write_text(json.dumps({
        "artifact_type": "swing_tuning_patch_review",
        "apply": {"supported": False},
        "patch_items": [
            {
                "target_path": (
                    "config/signal_engine.yaml:"
                    "signal_engine.classification.strong_min_score"
                ),
                "current_value": 70,
                "proposed_value": 71,
            },
        ],
    }))

    report = SwingTuningPatchApplier(
        config_root=tmp_path,
        clock=lambda: datetime(2026, 7, 3, 9, 0, 0),
    ).apply(patch_path, confirmed=True, log_path=log_path)

    assert report.applied is True
    assert report.issues == ()
    assert report.changes[0].old_value == 70
    assert report.changes[0].new_value == 71
    config_text = (tmp_path / "config" / "signal_engine.yaml").read_text(
        encoding="utf-8"
    )
    assert "strong_min_score: 71" in config_text

    log_payload = json.loads(log_path.read_text(encoding="utf-8"))
    assert log_payload["artifact_type"] == "swing_tuning_patch_apply"
    assert log_payload["applied_at"] == "2026-07-03T09:00:00"
    assert log_payload["changes"][0]["old_value"] == 70
    assert log_payload["changes"][0]["new_value"] == 71


def test_swing_tuning_patch_apply_rejects_without_confirmation(tmp_path):
    _write_config(tmp_path)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps({
        "artifact_type": "swing_tuning_patch_review",
        "apply": {"supported": False},
        "patch_items": [
            {
                "target_path": (
                    "config/signal_engine.yaml:"
                    "signal_engine.classification.strong_min_score"
                ),
                "current_value": 70,
                "proposed_value": 71,
            },
        ],
    }))

    report = SwingTuningPatchApplier(config_root=tmp_path).apply(
        patch_path,
        confirmed=False,
        log_path=tmp_path / "apply.jsonl",
    )

    assert report.applied is False
    assert report.issues == ("apply_confirmation_required",)
    config_text = (tmp_path / "config" / "signal_engine.yaml").read_text(
        encoding="utf-8"
    )
    assert "strong_min_score: 70" in config_text


def test_swing_tuning_patch_apply_rejects_dirty_target(tmp_path):
    _write_config(tmp_path)
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps({
        "artifact_type": "swing_tuning_patch_review",
        "apply": {"supported": False},
        "patch_items": [
            {
                "target_path": (
                    "config/signal_engine.yaml:"
                    "signal_engine.classification.strong_min_score"
                ),
                "current_value": 70,
                "proposed_value": 71,
            },
        ],
    }))

    report = SwingTuningPatchApplier(
        config_root=tmp_path,
        target_dirty_checker=lambda _path: True,
    ).apply(patch_path, confirmed=True, log_path=tmp_path / "apply.jsonl")

    assert report.applied is False
    assert report.issues == ("target_config_dirty:config/signal_engine.yaml",)
    config_text = (tmp_path / "config" / "signal_engine.yaml").read_text(
        encoding="utf-8"
    )
    assert "strong_min_score: 70" in config_text
