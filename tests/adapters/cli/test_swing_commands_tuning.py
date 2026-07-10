"""Tuning diff, apply, review, and status tests for swing commands."""

import json
from datetime import date, timedelta

from src.adapters.cli.main import app
from tests.adapters.cli.swing_command_fixtures import (
    _COMPLETE_SOURCE_REVIEW,
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


def test_swing_tuning_review_history_json_reads_saved_runs(tmp_path):
    journal_path = tmp_path / "swing_tuning_reviews.jsonl"
    journal_path.write_text(
        json.dumps({
            "recorded_at": "2026-07-02T10:00:00+07:00",
            "artifact_type": "swing_tuning_review",
            "setup": "foreign-bounce",
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "sample": {"status": "INSUFFICIENT_SAMPLE"},
            "backtest_summary": {
                "trade_count": 0,
                "candidate_observation_count": 2,
                "total_return_pct": 0.0,
                "win_rate_pct": None,
            },
            "tuning_config_diff": {
                "status": "BLOCKED",
                "summary": {"proposed_count": 0, "rejected_count": 3},
            },
        })
        + "\n"
    )

    result = runner.invoke(
        app,
        [
            "trade",
            "review-tuning-swing",
            "--journal",
            str(journal_path),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["artifact_type"] == "swing_tuning_review_history"
    assert payload["journal"] == str(journal_path)
    assert payload["total_records"] == 1
    assert payload["records"][0]["setup"] == "foreign-bounce"
    assert payload["records"][0]["sample_status"] == "INSUFFICIENT_SAMPLE"
    assert payload["records"][0]["rejected_count"] == 3


def test_swing_tuning_review_history_json_can_compare_latest(tmp_path):
    journal_path = tmp_path / "swing_tuning_reviews.jsonl"
    rows = [
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
            "tuning_config_diff": {
                "status": "PROPOSED_VALUES_DRY_RUN",
                "summary": {"proposed_count": 1, "rejected_count": 2},
                "diff_items": [
                    {
                        "target_path": "config/signal_engine.yaml:a",
                        "proposed_value": 60,
                    },
                ],
            },
        },
        {
            "recorded_at": "2026-07-02T10:00:00+07:00",
            "artifact_type": "swing_tuning_review",
            "setup": "foreign-bounce",
            "sample": {"status": "TRADE_READY"},
            "backtest_summary": {
                "trade_count": 12,
                "candidate_observation_count": 35,
                "total_return_pct": 3.0,
                "win_rate_pct": 55.0,
            },
            "tuning_config_diff": {
                "status": "PROPOSED_VALUES_DRY_RUN",
                "summary": {"proposed_count": 1, "rejected_count": 1},
                "diff_items": [
                    {
                        "target_path": "config/risk_engine.yaml:b",
                        "proposed_value": 100,
                    },
                ],
            },
        },
    ]
    journal_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")

    result = runner.invoke(
        app,
        [
            "trade",
            "review-tuning-swing",
            "--journal",
            str(journal_path),
            "--format",
            "json",
            "--compare-latest",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    comparison = payload["comparison"]
    assert comparison["status"] == "READY"
    deltas = {
        item["name"]: item["delta"]
        for item in comparison["metric_deltas"]
    }
    assert deltas["trade_count"] == 2
    assert deltas["total_return_pct"] == 1.5
    assert comparison["newly_proposed_target_paths"] == [
        "config/risk_engine.yaml:b"
    ]
    assert comparison["disappeared_target_paths"] == [
        "config/signal_engine.yaml:a"
    ]


def test_swing_tuning_review_history_json_measures_latest_apply(tmp_path):
    journal_path = tmp_path / "swing_tuning_reviews.jsonl"
    apply_log_path = tmp_path / "swing_tuning_apply_log.jsonl"
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
            "tuning_config_diff": {
                "status": "PROPOSED_VALUES_DRY_RUN",
                "summary": {"proposed_count": 1, "rejected_count": 2},
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
            "tuning_config_diff": {
                "status": "PROPOSED_VALUES_DRY_RUN",
                "summary": {"proposed_count": 1, "rejected_count": 1},
            },
        },
    ]
    apply_rows = [
        {
            "artifact_type": "swing_tuning_patch_apply",
            "applied_at": "2026-07-02T09:00:00+07:00",
            "patch_path": "journals/swing_tuning_patch.json",
            "changes": [
                {
                    "target_path": "config/signal_engine.yaml:x",
                    "old_value": 70,
                    "new_value": 71,
                }
            ],
        }
    ]
    journal_path.write_text(
        "\n".join(json.dumps(row) for row in review_rows) + "\n"
    )
    apply_log_path.write_text(
        "\n".join(json.dumps(row) for row in apply_rows) + "\n"
    )

    result = runner.invoke(
        app,
        [
            "trade",
            "review-tuning-swing",
            "--journal",
            str(journal_path),
            "--apply-log",
            str(apply_log_path),
            "--measure-latest-apply",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    measurement = payload["post_apply_measurement"]
    assert measurement["status"] == "READY"
    assert measurement["applied_patch"]["target_paths"] == [
        "config/signal_engine.yaml:x"
    ]
    deltas = {
        item["name"]: item["delta"]
        for item in measurement["metric_deltas"]
    }
    assert deltas["trade_count"] == 2
    assert deltas["total_return_pct"] == 1.5


def test_swing_tuning_status_json_reports_next_action(tmp_path):
    journal_path = tmp_path / "swing_tuning_reviews.jsonl"
    patch_path = tmp_path / "swing_tuning_patch.json"
    apply_log_path = tmp_path / "swing_tuning_apply_log.jsonl"

    result = runner.invoke(
        app,
        [
            "trade",
            "tuning-status",
            "--journal",
            str(journal_path),
            "--patch",
            str(patch_path),
            "--apply-log",
            str(apply_log_path),
            "--config-root",
            str(tmp_path),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["artifact_type"] == "swing_tuning_loop_status"
    assert payload["status"] == "IN_PROGRESS"
    assert payload["next_action"] == "RUN_TUNE_SWING_SAVE"
    assert payload["review"]["total_records"] == 0
    assert payload["patch"]["exists"] is False
