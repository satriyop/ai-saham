"""CLI: research accum capture --require-session fail-closed gate."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.application.use_case.backfill_signal_observations_use_case import (
    BackfillSignalObservationsResponse,
)

runner = CliRunner()
SESSION = "2026-08-25"


def _empty_write_response() -> BackfillSignalObservationsResponse:
    return BackfillSignalObservationsResponse(
        requested_date_count=0,
        processed_date_count=0,
        skipped_date_count=0,
        saved_observation_count=0,
        generated_label_count=0,
        unavailable_label_count=0,
        notes=("ihsg_calendar_unavailable",),
    )


def _patch_capture_io(
    monkeypatch,
    *,
    ihsg: bool,
    iev: bool,
    captured: frozenset[date] = frozenset(),
) -> None:
    monkeypatch.setattr(
        "src.adapters.cli.research_accum_capture_commands.load_app_config",
        lambda: type("Cfg", (), {"storage": type("S", (), {"db_path": Path("data.db")})()})(),
    )
    monkeypatch.setattr(
        "src.adapters.cli.research_accum_capture_commands._ihsg_has_session",
        lambda db, session_date: ihsg,
    )
    monkeypatch.setattr(
        "src.adapters.cli.research_accum_capture_commands._same_day_auction_evidence",
        lambda db, session_date: iev,
    )
    monkeypatch.setattr(
        "src.adapters.cli.research_accum_capture_commands._captured_accum_sessions",
        lambda db: captured,
    )
    monkeypatch.setattr(
        "src.adapters.cli.research_accum_capture_commands.run_signal_observation_corpus_write",
        lambda **kwargs: _empty_write_response(),
    )


def test_require_session_fails_on_eod_lag(monkeypatch) -> None:
    _patch_capture_io(monkeypatch, ihsg=False, iev=True)
    result = runner.invoke(
        app,
        ["research", "accum", "capture", "-u", "lq45", "--session", SESSION, "--format", "json"],
    )
    assert result.exit_code == 2
    assert "EOD data is not yet available" in (result.stderr or result.output)


def test_require_session_allows_holiday(monkeypatch) -> None:
    _patch_capture_io(monkeypatch, ihsg=False, iev=False)
    result = runner.invoke(
        app,
        ["research", "accum", "capture", "-u", "lq45", "--session", SESSION, "--format", "json"],
    )
    assert result.exit_code == 0
    assert '"processed_date_count": 0' in result.stdout


def test_already_captured_session_skips_write(monkeypatch) -> None:
    writes: list[object] = []

    def _write(**kwargs):
        writes.append(kwargs)
        return _empty_write_response()

    _patch_capture_io(
        monkeypatch,
        ihsg=True,
        iev=True,
        captured=frozenset({date(2026, 8, 25)}),
    )
    monkeypatch.setattr(
        "src.adapters.cli.research_accum_capture_commands.run_signal_observation_corpus_write",
        _write,
    )
    result = runner.invoke(
        app,
        ["research", "accum", "capture", "-u", "lq45", "--session", SESSION, "--format", "json"],
    )
    assert result.exit_code == 0
    assert writes == []
    assert '"processed_date_count": 1' in result.stdout
    assert "session_already_captured" in result.stdout
