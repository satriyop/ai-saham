import json

from src.adapters.cli.main import app
from tests.adapters.cli.swing_command_fixtures import runner


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
