"""ADR-054 S1: explicit-ticker refresh for screen accum judgment desk."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.application.dto.accumulation_screen import AccumulationScreenResponse
from tests.adapters.cli.screen_accum_test_fixtures import _candidate, _fake_workflow_result

runner = CliRunner()


def _patch_workflow(monkeypatch, captured: dict) -> None:
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
                )
            )

        uc.execute = execute
        return uc

    monkeypatch.setattr(
        "src.adapters.composition.screen_deps.create_run_accumulation_screen_workflow_use_case",
        fake_uc,
    )


def test_force_refresh_universe_only_rejected(monkeypatch) -> None:
    captured: dict = {}
    _patch_workflow(monkeypatch, captured)
    refresh = MagicMock(return_value=None)
    monkeypatch.setattr(
        "src.adapters.cli.screen_accum_commands._refresh_explicit_tickers_for_screen",
        refresh,
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_accum_commands.resolve_tickers",
        lambda **kwargs: ["BBCA", "BBRI"],
    )
    result = runner.invoke(
        app,
        ["screen", "accum", "--universe", "lq45", "--force-refresh", "--format", "json"],
    )
    assert result.exit_code != 0
    combined = (result.output + (result.stderr or "")).lower()
    assert "force-refresh" in combined or "explicit" in combined
    refresh.assert_not_called()


def test_explicit_ticker_calls_refresh_by_default(monkeypatch) -> None:
    captured: dict = {}
    _patch_workflow(monkeypatch, captured)
    refresh = MagicMock()
    monkeypatch.setattr(
        "src.adapters.cli.screen_accum_commands._refresh_explicit_tickers_for_screen",
        refresh,
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_accum_commands.resolve_tickers",
        lambda **kwargs: ["BBCA"],
    )
    result = runner.invoke(app, ["screen", "accum", "BBCA", "--format", "json"])
    assert result.exit_code == 0, result.output
    refresh.assert_called_once()
    kwargs = refresh.call_args.kwargs
    assert kwargs["tickers"] == ["BBCA"]
    assert kwargs["force_refresh"] is False


def test_no_refresh_skips_explicit_ticker_refresh(monkeypatch) -> None:
    captured: dict = {}
    _patch_workflow(monkeypatch, captured)
    refresh = MagicMock()
    monkeypatch.setattr(
        "src.adapters.cli.screen_accum_commands._refresh_explicit_tickers_for_screen",
        refresh,
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_accum_commands.resolve_tickers",
        lambda **kwargs: ["BBCA"],
    )
    result = runner.invoke(
        app,
        ["screen", "accum", "BBCA", "--no-refresh", "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    refresh.assert_not_called()


def test_universe_only_does_not_refresh(monkeypatch) -> None:
    captured: dict = {}
    _patch_workflow(monkeypatch, captured)
    refresh = MagicMock()
    monkeypatch.setattr(
        "src.adapters.cli.screen_accum_commands._refresh_explicit_tickers_for_screen",
        refresh,
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_accum_commands.resolve_tickers",
        lambda **kwargs: ["BBCA", "BBRI"],
    )
    result = runner.invoke(
        app,
        ["screen", "accum", "--universe", "lq45", "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    refresh.assert_not_called()


def test_refresh_helper_fail_closed_continues(monkeypatch, tmp_path) -> None:
    """Provider failure must not abort the screen."""
    from src.adapters.cli.screen_accum_commands import _refresh_explicit_tickers_for_screen

    def boom(**kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(
        "src.adapters.cli.plan_swing_optional_fetchers.auto_refresh_swing_data",
        boom,
    )
    _refresh_explicit_tickers_for_screen(
        tickers=["BBCA"],
        db_path=tmp_path / "x.db",
        force_refresh=False,
        quiet=True,
    )
