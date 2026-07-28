"""CLI gates for screen accum deep analysis flags (ADR-054 S1 complete)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from src.adapters.cli.main import app
from src.application.dto.accumulation_screen import AccumulationScreenResponse
from tests.adapters.cli.screen_accum_test_fixtures import (
    _candidate,
    _fake_workflow_result,
    runner,
)


def _patch_workflow(monkeypatch, captured: dict):
    def fake_uc(**kwargs):
        uc = SimpleNamespace()

        def execute(req):
            captured["request"] = req
            return _fake_workflow_result(
                response=AccumulationScreenResponse(
                    candidates=[_candidate()],
                    screened_at=__import__("datetime").date(2026, 6, 28),
                    window_days=getattr(req, "window", 7),
                    total_tickers_checked=len(req.tickers),
                    tickers_skipped=0,
                    provider="fake",
                )
            )

        uc.execute = execute
        return uc

    monkeypatch.setattr(
        "src.adapters.composition.screen_deps.create_run_accumulation_screen_workflow_use_case",
        fake_uc,
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_accum_commands._refresh_explicit_tickers_for_screen",
        MagicMock(),
    )


def test_deep_flags_rejected_for_universe_only(monkeypatch):
    captured: dict = {}
    _patch_workflow(monkeypatch, captured)
    result = runner.invoke(
        app,
        ["screen", "accum", "--universe", "lq45", "--with-flow-detail"],
    )
    assert result.exit_code != 0
    assert (
        "explicit ticker" in (result.output + result.stderr).lower()
        or "explicit" in (result.output + str(result.exception)).lower()
    )


def test_deep_flags_rejected_with_multi(monkeypatch):
    captured: dict = {}
    _patch_workflow(monkeypatch, captured)
    result = runner.invoke(
        app,
        ["screen", "accum", "BBCA", "--multi", "--full"],
    )
    assert result.exit_code != 0
    assert "multi" in (result.output + result.stderr).lower() or result.exit_code == 1


def test_deep_flags_accepted_for_explicit_ticker(monkeypatch):
    captured: dict = {}
    _patch_workflow(monkeypatch, captured)
    result = runner.invoke(
        app,
        [
            "screen",
            "accum",
            "BBCA",
            "--with-flow-detail",
            "--with-sentiment",
            "--setup",
            "foreign-bounce",
            "--format",
            "json",
            "--no-refresh",
        ],
    )
    assert result.exit_code == 0, result.output
    req = captured["request"]
    assert req.deep_evidence.include_flow_detail is True
    assert req.deep_evidence.include_sentiment is True
    assert req.deep_evidence.setup_name == "foreign-bounce"


def test_full_flag_sets_include_full(monkeypatch):
    captured: dict = {}
    _patch_workflow(monkeypatch, captured)
    result = runner.invoke(
        app,
        ["screen", "accum", "BBRI", "--full", "--format", "json", "--no-refresh"],
    )
    assert result.exit_code == 0, result.output
    assert captured["request"].deep_evidence.include_full is True


def test_help_lists_deep_flags():
    result = runner.invoke(app, ["screen", "accum", "--help"])
    assert result.exit_code == 0
    out = result.output
    assert "--with-flow-detail" in out
    assert "--with-sentiment" in out
    assert "--setup" in out
    assert "--full" in out
