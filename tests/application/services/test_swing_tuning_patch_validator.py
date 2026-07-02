import json

from src.application.services.swing_tuning_patch_validator import (
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
