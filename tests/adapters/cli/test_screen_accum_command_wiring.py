"""CLI wiring tests — verify correct request fields are passed to workflow use case."""

import json
from datetime import date
from types import SimpleNamespace

from src.adapters.cli import screen_accum_commands as accum_cli
from src.adapters.cli.main import app
from src.application.dto.accumulation_screen import AccumulationScreenResponse


def _screen_payload(raw: dict) -> dict:
    """Clean-break envelope: artifact lives under data."""
    if "verb" in raw and "data" in raw and isinstance(raw["data"], dict):
        return raw["data"]
    return raw


from tests.adapters.cli.screen_accum_test_fixtures import (
    _candidate,
    _fake_workflow_result,
    runner,
)


def test_screen_accum_delegates_workflow_construction_to_builder(monkeypatch):
    captured = {}

    def fake_workflow_uc(**kwargs):
        captured["factory_kwargs"] = kwargs
        uc = SimpleNamespace()
        uc.execute = lambda req: (
            captured.update(request=req)
            or _fake_workflow_result(
                response=AccumulationScreenResponse(
                    candidates=[_candidate()],
                    screened_at=date(2026, 6, 28),
                    window_days=getattr(req, "window", 7),
                    total_tickers_checked=len(req.tickers),
                    tickers_skipped=0,
                    provider="fake",
                )
            )
        )
        return uc

    monkeypatch.setattr(
        "src.adapters.cli.screen_deps.create_run_accumulation_screen_workflow_use_case",
        fake_workflow_uc,
    )

    result = runner.invoke(app, ["screen", "accum", "BBCA", "--format", "json"])

    assert result.exit_code == 0
    payload = _screen_payload(json.loads(result.output))
    assert payload["artifact_type"] == "accumulation_screen"
    req = captured["request"]
    assert req.tickers == ["BBCA"]
    assert req.multi is False


def test_screen_accum_single_table_mode_sets_strategy_overlay(monkeypatch):
    """--strategy in single table mode must set include_strategy_overlay=True."""
    captured = {}

    def fake_uc(**kwargs):
        uc = SimpleNamespace()
        uc.execute = lambda req: (
            captured.update(request=req)
            or _fake_workflow_result(
                response=AccumulationScreenResponse(
                    candidates=[_candidate()],
                    screened_at=date(2026, 6, 28),
                    window_days=getattr(req, "window", 7),
                    total_tickers_checked=len(req.tickers),
                    tickers_skipped=0,
                    provider="fake",
                )
            )
        )
        return uc

    monkeypatch.setattr(
        "src.adapters.cli.screen_deps.create_run_accumulation_screen_workflow_use_case",
        fake_uc,
    )

    result = runner.invoke(
        app,
        ["screen", "accum", "BBCA", "--strategy", "test-strat"],
    )

    assert result.exit_code == 0, result.output
    req = captured["request"]
    assert req.include_strategy_overlay is True
    assert req.strategy_name == "test-strat"
    assert req.save_enabled is False


def test_screen_accum_strategy_with_json_includes_overlay(monkeypatch):
    """--strategy --format json runs the overlay and emits strategy fields."""
    captured: dict = {}

    def fake_uc(**kwargs):
        uc = SimpleNamespace()

        def execute(req):
            captured["request"] = req
            return _fake_workflow_result(
                response=AccumulationScreenResponse(
                    candidates=[_candidate(ticker="BBCA")],
                    screened_at=date(2026, 6, 28),
                    window_days=getattr(req, "window", 7),
                    total_tickers_checked=len(req.tickers),
                    tickers_skipped=0,
                    provider="fake",
                ),
                strategy_signals={"BBCA": "OPEN"},
            )

        uc.execute = execute
        return uc

    monkeypatch.setattr(
        "src.adapters.cli.screen_deps.create_run_accumulation_screen_workflow_use_case",
        fake_uc,
    )

    result = runner.invoke(
        app,
        ["screen", "accum", "BBCA", "--strategy", "test-strat", "--format", "json"],
    )

    assert result.exit_code == 0, result.output
    req = captured["request"]
    assert req.include_strategy_overlay is True
    assert req.strategy_name == "test-strat"
    payload = _screen_payload(json.loads(result.output))
    assert payload["strategy_name"] == "test-strat"
    assert payload["strategy_signals"] == {"BBCA": "OPEN"}


def test_screen_accum_strategy_with_multi_fails_explicitly(monkeypatch):
    """--strategy --multi is an unsupported combo — must fail clearly,
    not silently drop the strategy overlay (S2)."""

    def fake_uc(**kwargs):
        raise AssertionError("workflow use case must not run for a rejected combo")

    monkeypatch.setattr(
        "src.adapters.cli.screen_deps.create_run_accumulation_screen_workflow_use_case",
        fake_uc,
    )

    result = runner.invoke(
        app,
        ["screen", "accum", "BBCA", "--multi", "--strategy", "test-strat"],
    )

    assert result.exit_code != 0
    assert "--strategy" in result.output
    assert "--multi" in result.output


def test_screen_accum_single_table_mode_sets_save_enabled(monkeypatch):
    """--save in single table mode must set save_enabled=True and save_name."""
    captured = {}

    def fake_uc(**kwargs):
        uc = SimpleNamespace()
        uc.execute = lambda req: (
            captured.update(request=req)
            or _fake_workflow_result(
                response=AccumulationScreenResponse(
                    candidates=[_candidate()],
                    screened_at=date(2026, 6, 28),
                    window_days=getattr(req, "window", 7),
                    total_tickers_checked=len(req.tickers),
                    tickers_skipped=0,
                    provider="fake",
                ),
                save_result=SimpleNamespace(saved_count=1, name="mywatch"),
            )
        )
        return uc

    monkeypatch.setattr(
        "src.adapters.cli.screen_deps.create_run_accumulation_screen_workflow_use_case",
        fake_uc,
    )

    result = runner.invoke(
        app,
        ["screen", "accum", "BBCA", "--save", "mywatch"],
    )

    assert result.exit_code == 0, result.output
    req = captured["request"]
    assert req.save_enabled is True
    assert req.save_name == "mywatch"
    assert req.include_strategy_overlay is False


def test_screen_accum_multi_sets_correct_request_fields(monkeypatch):
    captured = {}

    def fake_workflow_uc(**kwargs):
        captured["factory_kwargs"] = kwargs
        uc = SimpleNamespace()
        uc.execute = lambda req: (
            captured.update(request=req)
            or _fake_workflow_result(
                multi_results={
                    7: AccumulationScreenResponse(
                        candidates=[_candidate(window_days=7)],
                        screened_at=date(2026, 6, 28),
                        window_days=7,
                        total_tickers_checked=len(req.tickers),
                        tickers_skipped=0,
                        provider="fake",
                    ),
                    30: AccumulationScreenResponse(
                        candidates=[_candidate(window_days=30)],
                        screened_at=date(2026, 6, 28),
                        window_days=30,
                        total_tickers_checked=len(req.tickers),
                        tickers_skipped=0,
                        provider="fake",
                    ),
                },
            )
        )
        return uc

    monkeypatch.setattr(
        "src.adapters.cli.screen_deps.create_run_accumulation_screen_workflow_use_case",
        fake_workflow_uc,
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "accum",
            "BBCA",
            "--multi",
            "--windows",
            "7,30",
            "--min-piotroski",
            "5",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    req = captured["request"]
    assert req.multi is True
    assert req.windows == [7, 30]
    assert req.include_strategy_overlay is False
    assert req.save_enabled is False
    assert req.min_piotroski == 5


def test_screen_accum_threads_as_of_date_to_workflow_request(monkeypatch):
    captured = {}

    def fake_workflow_uc(**kwargs):
        uc = SimpleNamespace()
        uc.execute = lambda req: (
            captured.update(request=req)
            or _fake_workflow_result(
                response=AccumulationScreenResponse(
                    candidates=[_candidate()],
                    screened_at=date(2026, 6, 28),
                    window_days=getattr(req, "window", 7),
                    total_tickers_checked=len(req.tickers),
                    tickers_skipped=0,
                    provider="fake",
                )
            )
        )
        return uc

    monkeypatch.setattr(
        "src.adapters.cli.screen_deps.create_run_accumulation_screen_workflow_use_case",
        fake_workflow_uc,
    )

    result = runner.invoke(
        app,
        ["screen", "accum", "BBCA", "--as-of", "2026-07-23", "--format", "json"],
    )

    assert result.exit_code == 0, result.output
    assert captured["request"].as_of_date == date(2026, 7, 23)


def test_screen_accum_rejects_invalid_as_of(monkeypatch):
    def fake_workflow_uc(**kwargs):
        raise AssertionError("workflow must not run when --as-of is invalid")

    monkeypatch.setattr(
        "src.adapters.cli.screen_deps.create_run_accumulation_screen_workflow_use_case",
        fake_workflow_uc,
    )

    result = runner.invoke(
        app,
        ["screen", "accum", "BBCA", "--as-of", "not-a-date"],
    )

    assert result.exit_code == 1
    assert "Invalid --as-of" in result.stderr


def test_screen_accum_json_includes_effective_session(monkeypatch):
    def fake_workflow_uc(**kwargs):
        uc = SimpleNamespace()
        uc.execute = lambda req: _fake_workflow_result(
            response=AccumulationScreenResponse(
                candidates=[_candidate()],
                screened_at=date(2026, 6, 28),
                window_days=getattr(req, "window", 7),
                total_tickers_checked=len(req.tickers),
                tickers_skipped=0,
                provider="fake",
            )
        )
        return uc

    monkeypatch.setattr(
        "src.adapters.cli.screen_deps.create_run_accumulation_screen_workflow_use_case",
        fake_workflow_uc,
    )

    result = runner.invoke(
        app,
        ["screen", "accum", "BBCA", "--format", "json"],
    )

    assert result.exit_code == 0, result.output
    payload = _screen_payload(json.loads(result.output))
    assert payload["effective_session"]["analysis_as_of"] == "2026-06-28"
    assert payload["effective_session"]["is_eod_pending"] is False


def test_screen_accum_help_exposes_as_of():
    result = runner.invoke(app, ["screen", "accum", "--help"])

    assert result.exit_code == 0
    assert "--as-of" in result.stdout
