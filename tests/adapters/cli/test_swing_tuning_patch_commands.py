import json

from src.adapters.cli.main import app
from tests.adapters.cli.swing_command_fixtures import (
    _COMPLETE_SOURCE_REVIEW,
    runner,
)


def test_validate_tuning_patch_json_reports_valid_patch(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "signal_engine.yaml").write_text(
        "signal_engine:\n"
        "  classification:\n"
        "    strong_min_score: 70\n",
        encoding="utf-8",
    )
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps({
        "artifact_type": "swing_tuning_patch_review",
        "apply": {"supported": False},
        "source_review": _COMPLETE_SOURCE_REVIEW,
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

    result = runner.invoke(
        app,
        [
            "trade",
            "validate-tuning-patch",
            str(patch_path),
            "--config-root",
            str(tmp_path),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["artifact_type"] == "swing_tuning_patch_validation"
    assert payload["valid"] is True
    assert payload["valid_item_count"] == 1
    assert payload["item_results"][0]["issues"] == []


def test_apply_tuning_patch_requires_explicit_mode(tmp_path):
    patch_path = tmp_path / "patch.json"
    patch_path.write_text("{}")

    result = runner.invoke(
        app,
        [
            "trade",
            "apply-tuning-patch",
            str(patch_path),
        ],
    )

    assert result.exit_code == 1
    assert "use --dry-run to preview, --yes to apply, or --verify to check" in result.output


def test_apply_tuning_patch_dry_run_json_reports_changes(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "signal_engine.yaml").write_text(
        "signal_engine:\n"
        "  classification:\n"
        "    strong_min_score: 70\n",
        encoding="utf-8",
    )
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps({
        "artifact_type": "swing_tuning_patch_review",
        "apply": {"supported": False},
        "source_review": _COMPLETE_SOURCE_REVIEW,
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

    result = runner.invoke(
        app,
        [
            "trade",
            "apply-tuning-patch",
            str(patch_path),
            "--dry-run",
            "--config-root",
            str(tmp_path),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["artifact_type"] == "swing_tuning_patch_dry_run"
    assert payload["ready"] is True
    assert payload["apply"]["performed"] is False
    assert payload["changes"][0]["current_value"] == 70
    assert payload["changes"][0]["proposed_value"] == 71


def test_apply_tuning_patch_verify_json_reports_applied_values(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "signal_engine.yaml").write_text(
        "signal_engine:\n"
        "  classification:\n"
        "    strong_min_score: 71\n",
        encoding="utf-8",
    )
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(json.dumps({
        "artifact_type": "swing_tuning_patch_review",
        "apply": {"supported": False},
        "source_review": _COMPLETE_SOURCE_REVIEW,
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

    result = runner.invoke(
        app,
        [
            "trade",
            "apply-tuning-patch",
            str(patch_path),
            "--verify",
            "--config-root",
            str(tmp_path),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["artifact_type"] == "swing_tuning_patch_verify"
    assert payload["verified"] is True
    assert payload["item_results"][0]["expected_value"] == 71
    assert payload["item_results"][0]["actual_value"] == 71
