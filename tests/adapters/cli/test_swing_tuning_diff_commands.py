import json

from src.adapters.cli.main import app
from tests.adapters.cli.swing_command_fixtures import (
    _patch_swing_backtest_command,
    runner,
)


def test_swing_backtest_tuning_diff_json_exposes_guardrails(monkeypatch):
    _patch_swing_backtest_command(monkeypatch)

    result = runner.invoke(
        app,
        [
            "trade",
            "backtest-swing",
            "BBCA",
            "--with-tuning-diff",
            "--format",
            "json",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-31",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    tuning_diff = payload["tuning_config_diff"]

    assert tuning_diff["status"] == "PROPOSED_VALUES_DRY_RUN"
    assert tuning_diff["can_apply"] is False
    assert tuning_diff["requires_human_review"] is True
    assert tuning_diff["diff_items"]
    assert tuning_diff["rejected_items"] == []
    assert tuning_diff["summary"]["resolved_count"] == len(
        tuning_diff["diff_items"]
    )
    assert tuning_diff["summary"]["proposed_count"] > 0
    assert (
        tuning_diff["summary"]["value_policy_counts"][
            "DETERMINISTIC_VALUE_SELECTED"
        ]
        > 0
    )
    assert "review_checklist" in tuning_diff
    assert (
        "Review every proposed value before editing YAML manually."
        in tuning_diff["review_checklist"]
    )
    assert tuning_diff["review_checklist"][-1] == (
        "Do not apply automatically; edit YAML manually only after review."
    )
    item = tuning_diff["diff_items"][0]
    assert item["current_value"] is not None
    assert item["proposed_value"] is not None
    assert item["status"] == "PROPOSED_VALUE_SELECTED"
    assert item["value_selection_policy"] == "DETERMINISTIC_VALUE_SELECTED"
    assert item["interpretation"] == "proposed guarded value"
    assert item["target_classification"]["target_family"]
    assert item["target_classification"]["target_kind"]
    assert item["target_classification"]["target_parameter"]
    assert item["evidence_snapshot"]["sample_count"] > 0
    assert item["evidence_snapshot"]["evidence_strength"] == "HIGH"
    assert item["evidence_snapshot"]["proposed_action"] == (
        "review_threshold_or_weight_no_yaml_diff"
    )
    assert item["evidence_snapshot"]["evidence_buckets"]
    assert item["evidence_dimensions"]


def test_swing_backtest_tuning_diff_table_exposes_policy(monkeypatch):
    _patch_swing_backtest_command(monkeypatch)

    result = runner.invoke(
        app,
        [
            "trade",
            "backtest-swing",
            "BBCA",
            "--with-tuning-diff",
            "--show-trades",
            "0",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-31",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "TUNING CONFIG DIFF DRAFT" in result.output
    assert "PROPOSED_VALUES_DRY_RUN" in result.output
    assert "PROPOSED_VALUE_SELECTED" in result.output
    assert "DETERMINISTIC_VALUE_SELECTED" in result.output
    assert "proposed guarded value" in result.output
    assert "Value Policies" in result.output
    assert "Evidence Coverage" in result.output
    assert "Class" in result.output
    assert "Trace" in result.output
    assert "Review Checklist" in result.output
    assert "Can Apply" in result.output
