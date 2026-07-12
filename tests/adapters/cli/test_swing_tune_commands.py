import json
from datetime import date, timedelta

from src.adapters.cli.main import app
from tests.adapters.cli.swing_command_fixtures import (
    _patch_swing_backtest_command,
    runner,
)


def test_swing_tune_json_exposes_first_class_tuning_review(monkeypatch):
    _patch_swing_backtest_command(monkeypatch)

    result = runner.invoke(
        app,
        [
            "trade",
            "tune-swing",
            "BBCA",
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

    assert payload["artifact_type"] == "swing_tuning_review"
    assert payload["intent"] == (
        "deterministic_backtest_attribution_to_config_review_no_apply"
    )
    assert payload["tuning_plan"]["can_propose_changes"] is True
    assert payload["tuning_proposal"]["requires_human_review"] is True
    assert payload["tuning_config_diff"]["can_apply"] is False
    assert payload["tuning_config_diff"]["requires_human_review"] is True
    assert payload["apply"] == {
        "supported": False,
        "reason": "This command is review-only. Edit YAML manually after human review.",
    }


def test_swing_tune_save_writes_review_journal(monkeypatch, tmp_path):
    _patch_swing_backtest_command(monkeypatch)
    journal_path = tmp_path / "swing_tuning_reviews.jsonl"

    result = runner.invoke(
        app,
        [
            "trade",
            "tune-swing",
            "BBCA",
            "--format",
            "json",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-31",
            "--save",
            "--journal",
            str(journal_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["persistence"]["saved"] is True
    assert payload["persistence"]["path"] == str(journal_path)
    records = [json.loads(line) for line in journal_path.read_text().splitlines()]
    assert len(records) == 1
    assert records[0]["recorded_at"] == payload["persistence"]["recorded_at"]
    assert records[0]["artifact_type"] == "swing_tuning_review"
    assert records[0]["apply"]["supported"] is False


def test_swing_tune_export_patch_writes_review_only_patch(monkeypatch, tmp_path):
    _patch_swing_backtest_command(monkeypatch)
    patch_path = tmp_path / "swing_tuning_patch.json"

    result = runner.invoke(
        app,
        [
            "trade",
            "tune-swing",
            "BBCA",
            "--format",
            "json",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-31",
            "--export-patch",
            str(patch_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    patch_payload = json.loads(patch_path.read_text())
    assert payload["patch_export"]["path"] == str(patch_path)
    assert payload["patch_export"]["item_count"] == patch_payload["item_count"]
    assert patch_payload["artifact_type"] == "swing_tuning_patch_review"
    assert patch_payload["apply"]["supported"] is False
    assert patch_payload["patch_items"]
    assert all(
        item["proposed_value"] is not None
        for item in patch_payload["patch_items"]
    )
    assert patch_payload["source_review"]["setup"] == payload["setup"]


def test_swing_tune_is_ratio_patch_has_non_overlapping_split_dates(monkeypatch, tmp_path):
    _patch_swing_backtest_command(monkeypatch)
    patch_path = tmp_path / "patch.json"

    result = runner.invoke(
        app,
        [
            "trade", "tune-swing", "BBCA",
            "--format", "json",
            "--start", "2026-01-01",
            "--end", "2026-12-31",
            "--is-ratio", "0.70",
            "--export-patch", str(patch_path),
        ],
    )

    assert result.exit_code == 0, result.output
    patch_payload = json.loads(patch_path.read_text())
    sr = patch_payload["source_review"]
    assert sr.get("is_end_date") is not None
    assert sr.get("oos_start_date") is not None
    is_end = date.fromisoformat(sr["is_end_date"])
    oos_start = date.fromisoformat(sr["oos_start_date"])
    assert oos_start == is_end + timedelta(days=1), (
        f"oos_start_date {oos_start} must be exactly one day after is_end_date {is_end}"
    )


def test_tune_swing_is_ratio_without_end_exits():
    result = runner.invoke(
        app, ["trade", "tune-swing", "BBCA", "--is-ratio", "0.70"]
    )
    assert result.exit_code != 0
    assert "--is-ratio requires --end" in result.output


def test_tune_swing_invalid_is_ratio_exits():
    result = runner.invoke(
        app,
        ["trade", "tune-swing", "BBCA", "--is-ratio", "1.5",
         "--start", "2026-01-01", "--end", "2026-07-01"],
    )
    assert result.exit_code != 0
    assert "--is-ratio must be in range" in result.output


def test_tune_swing_start_equals_end_exits():
    result = runner.invoke(
        app,
        ["trade", "tune-swing", "BBCA", "--is-ratio", "0.70",
         "--start", "2026-01-01", "--end", "2026-01-01"],
    )
    assert result.exit_code != 0
    assert "--start must be before --end" in result.output


def test_tune_swing_too_short_range_for_split_exits():
    result = runner.invoke(
        app,
        ["trade", "tune-swing", "BBCA", "--is-ratio", "0.50",
         "--start", "2026-01-01", "--end", "2026-01-02"],
    )
    assert result.exit_code != 0
    assert "non-empty IS and OOS windows" in result.output
