"""Tests for the `saham trade tune-swing` CLI command."""

import json
from datetime import date
from decimal import Decimal

from typer.testing import CliRunner

from src.adapters.cli import trade_swing_tuning_commands
from src.adapters.cli.trade_commands import trade_app
from src.application.services.swing_backtest_attribution import (
    summarize_swing_backtest_attribution,
)
from src.application.use_case.run_swing_tuning_review_use_case import (
    RunSwingTuningReviewResult,
)
from src.application.use_case.swing_backtest_use_case import SwingBacktestResponse

runner = CliRunner()


def _response(**overrides) -> SwingBacktestResponse:
    defaults = dict(
        setup="foreign-bounce",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 10),
        initial_capital=Decimal("100000000"),
        cost_bps=Decimal("20"),
        final_equity=Decimal("105000000"),
        total_return_pct=5.0,
        max_drawdown_pct=0.0,
        trade_count=1,
        win_rate_pct=100.0,
        avg_trade_return_pct=5.0,
        profit_factor=2.0,
        exposure_pct=50.0,
        skipped_no_cash=0,
        skipped_duplicate=0,
        skipped_no_forward_data=0,
        skipped_by_regime=0,
        attribution_summary=summarize_swing_backtest_attribution((), ()),
    )
    defaults.update(overrides)
    return SwingBacktestResponse(**defaults)


def _base_payload():
    return {
        "schema_version": 1,
        "artifact_type": "swing_tuning_review",
        "intent": "deterministic_backtest_attribution_to_config_review_no_apply",
        "setup": "foreign-bounce",
        "start_date": "2026-01-01",
        "end_date": "2026-01-10",
    }


def _result(
    response=None,
    payload=None,
    patch_payload=None,
    persistence=None,
    patch_export=None,
    is_split_message=None,
) -> RunSwingTuningReviewResult:
    return RunSwingTuningReviewResult(
        response=response or _response(),
        payload=payload if payload is not None else _base_payload(),
        patch_payload=patch_payload,
        persistence=persistence,
        patch_export=patch_export,
        is_split_message=is_split_message,
    )


class FakeWorkflow:
    """Stands in for RunSwingTuningReviewUseCase: returns a result or raises."""

    def __init__(self, outcome):
        self.outcome = outcome
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _patch_workflow(monkeypatch, outcome):
    workflow = FakeWorkflow(outcome)
    captured_kwargs = {}

    def _fake_factory(*, journal_path):
        captured_kwargs["journal_path"] = journal_path
        return workflow

    monkeypatch.setattr(
        trade_swing_tuning_commands,
        "create_run_swing_tuning_review_workflow",
        _fake_factory,
    )
    return workflow, captured_kwargs


def _patch_display(monkeypatch):
    calls = []

    def _fake_display(response, **kwargs):
        calls.append({"response": response, **kwargs})

    monkeypatch.setattr(
        trade_swing_tuning_commands, "display_swing_backtest", _fake_display
    )
    return calls


def test_command_delegates_to_workflow_factory_with_journal_path(monkeypatch, tmp_path):
    workflow, captured_kwargs = _patch_workflow(monkeypatch, _result())
    _patch_display(monkeypatch)
    journal_path = tmp_path / "journal.jsonl"

    res = runner.invoke(
        trade_app, ["tune-swing", "BBCA", "--journal", str(journal_path)]
    )

    assert res.exit_code == 0
    assert captured_kwargs["journal_path"] == journal_path
    assert len(workflow.requests) == 1


def test_request_dto_contains_raw_cli_intent_values_unchanged(monkeypatch):
    workflow, _ = _patch_workflow(monkeypatch, _result())
    _patch_display(monkeypatch)

    res = runner.invoke(
        trade_app,
        ["tune-swing", "BBCA", "--setup", "foreign-bounce", "--start", "2026-01-01"],
    )

    assert res.exit_code == 0
    sent = workflow.requests[0]
    assert sent.tickers == ["BBCA"]
    assert sent.setup == "foreign-bounce"
    assert sent.start == "2026-01-01"
    assert sent.capital is None
    assert sent.risk_pct is None
    assert sent.max_positions is None
    assert sent.take_profit is None
    assert sent.stop_loss is None
    assert sent.max_hold is None
    assert sent.cost_bps is None
    assert sent.is_ratio is None
    assert sent.save is False
    assert sent.export_patch is False


def test_workflow_value_error_maps_to_error_prefix_and_exit_1(monkeypatch):
    _patch_workflow(monkeypatch, ValueError("--start must be before --end."))
    _patch_display(monkeypatch)

    res = runner.invoke(trade_app, ["tune-swing", "BBCA"])

    assert res.exit_code == 1
    assert "Error: --start must be before --end." in res.output


def test_json_mode_prints_payload_and_does_not_call_display(monkeypatch):
    payload = _base_payload()
    _patch_workflow(monkeypatch, _result(payload=payload))
    display_calls = _patch_display(monkeypatch)

    res = runner.invoke(trade_app, ["tune-swing", "BBCA", "--format", "json"])

    assert res.exit_code == 0
    printed = json.loads(res.stdout)
    assert printed == payload
    assert display_calls == []


def test_table_mode_calls_display_swing_backtest_with_fixed_flags(monkeypatch):
    response = _response()
    _patch_workflow(monkeypatch, _result(response=response))
    display_calls = _patch_display(monkeypatch)

    res = runner.invoke(trade_app, ["tune-swing", "BBCA"])

    assert res.exit_code == 0
    assert len(display_calls) == 1
    call = display_calls[0]
    assert call["response"] is response
    assert call["show_trades"] == 0
    assert call["show_attribution"] is True
    assert call["show_tuning_plan"] is True
    assert call["show_tuning_proposal"] is True
    assert call["show_tuning_diff"] is True


def test_split_message_echoed_in_table_mode_when_present(monkeypatch):
    message = "Walk-forward split: IS 2026-01-01 -> 2026-01-08  OOS 2026-01-09 -> 2026-01-11"
    _patch_workflow(monkeypatch, _result(is_split_message=message))
    _patch_display(monkeypatch)

    res = runner.invoke(trade_app, ["tune-swing", "BBCA"])

    assert res.exit_code == 0
    assert message in res.output


def test_split_message_not_echoed_when_none(monkeypatch):
    _patch_workflow(monkeypatch, _result(is_split_message=None))
    _patch_display(monkeypatch)

    res = runner.invoke(trade_app, ["tune-swing", "BBCA"])

    assert res.exit_code == 0
    assert "Walk-forward split" not in res.output


def test_save_confirmation_printed_only_in_table_mode(monkeypatch, tmp_path):
    persistence = {"saved": True, "record_count": 4, "recorded_at": "2026-01-01T00:00:00"}
    payload = _base_payload()
    _patch_workflow(monkeypatch, _result(payload=payload, persistence=persistence))
    _patch_display(monkeypatch)
    journal_path = tmp_path / "journal.jsonl"

    res = runner.invoke(
        trade_app, ["tune-swing", "BBCA", "--save", "--journal", str(journal_path)]
    )

    assert res.exit_code == 0
    assert f"Saved swing tuning review -> {journal_path} (records=4)" in res.output


def test_save_confirmation_not_printed_in_json_mode(monkeypatch, tmp_path):
    persistence = {"saved": True, "record_count": 4, "recorded_at": "2026-01-01T00:00:00"}
    payload = _base_payload()
    _patch_workflow(monkeypatch, _result(payload=payload, persistence=persistence))
    _patch_display(monkeypatch)
    journal_path = tmp_path / "journal.jsonl"

    res = runner.invoke(
        trade_app,
        [
            "tune-swing",
            "BBCA",
            "--save",
            "--journal",
            str(journal_path),
            "--format",
            "json",
        ],
    )

    assert res.exit_code == 0
    assert "Saved swing tuning review" not in res.output
    printed = json.loads(res.stdout)
    assert printed["persistence"]["path"] == str(journal_path)
    assert printed["persistence"]["record_count"] == 4


def test_export_patch_calls_writer_and_prints_confirmation_in_table_mode(
    monkeypatch, tmp_path
):
    patch_payload = {"artifact_type": "swing_tuning_patch_review", "item_count": 2}
    _patch_workflow(
        monkeypatch, _result(payload=_base_payload(), patch_payload=patch_payload)
    )
    _patch_display(monkeypatch)
    export_path = tmp_path / "patch.json"
    captured = {}

    def _fake_write(*, patch_payload, path):
        captured["patch_payload"] = patch_payload
        captured["path"] = path
        return {"path": str(path), "item_count": 2, "artifact_type": "swing_tuning_patch_review"}

    monkeypatch.setattr(
        trade_swing_tuning_commands, "write_swing_tuning_patch_export", _fake_write
    )

    res = runner.invoke(
        trade_app, ["tune-swing", "BBCA", "--export-patch", str(export_path)]
    )

    assert res.exit_code == 0
    assert captured["patch_payload"] == patch_payload
    assert captured["path"] == export_path
    assert f"Exported swing tuning patch -> {export_path} (items=2)" in res.output


def test_json_mode_with_export_patch_includes_patch_export_and_skips_display(
    monkeypatch, tmp_path
):
    patch_payload = {"artifact_type": "swing_tuning_patch_review", "item_count": 3}
    payload = _base_payload()
    _patch_workflow(
        monkeypatch, _result(payload=payload, patch_payload=patch_payload)
    )
    display_calls = _patch_display(monkeypatch)
    export_path = tmp_path / "patch.json"

    def _fake_write(*, patch_payload, path):
        return {
            "path": str(path),
            "item_count": patch_payload["item_count"],
            "artifact_type": patch_payload["artifact_type"],
        }

    monkeypatch.setattr(
        trade_swing_tuning_commands, "write_swing_tuning_patch_export", _fake_write
    )

    res = runner.invoke(
        trade_app,
        [
            "tune-swing",
            "BBCA",
            "--export-patch",
            str(export_path),
            "--format",
            "json",
        ],
    )

    assert res.exit_code == 0
    assert display_calls == []
    printed = json.loads(res.stdout)
    assert printed["patch_export"] == {
        "path": str(export_path),
        "item_count": 3,
        "artifact_type": "swing_tuning_patch_review",
    }
