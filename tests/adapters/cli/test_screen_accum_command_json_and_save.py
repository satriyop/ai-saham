"""JSON output shape and save-behavior tests."""

import json
from datetime import date
from types import SimpleNamespace

from src.adapters.cli import screen_accum_commands as accum_cli
from src.adapters.cli.main import app
from src.application.dto.accumulation_screen import AccumulationScreenResponse
from tests.adapters.cli.screen_accum_test_fixtures import (
    _candidate,
    _fake_workflow_result,
    runner,
)


def test_screen_accum_json_includes_setup_phase(monkeypatch):
    from src.domain.value_objects.setup_phase import SetupPhaseSnapshot, SetupPhaseState

    setup_phase = SetupPhaseSnapshot(
        current_phase=SetupPhaseState.COMPRESSION,
        previous_phase=SetupPhaseState.ACCUMULATION,
        phase_age_sessions=2,
        phase_strength=0.7,
        coverage_score=0.8,
        conviction_score=0.56,
        sequence_valid=True,
    )

    def fake_uc(**kwargs):
        uc = SimpleNamespace()
        uc.execute = lambda req: _fake_workflow_result(
            response=AccumulationScreenResponse(
                candidates=[_candidate(setup_phase=setup_phase)],
                screened_at=date(2026, 6, 28),
                window_days=getattr(req, "window", 7),
                total_tickers_checked=len(req.tickers),
                tickers_skipped=0,
                provider="fake",
            )
        )
        return uc

    monkeypatch.setattr(
        accum_cli,
        "create_run_accumulation_screen_workflow_use_case",
        fake_uc,
    )

    result = runner.invoke(app, ["screen", "accum", "INDF", "--format", "json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    candidate_json = payload["candidates"][0]
    assert "setup_phase" in candidate_json
    assert candidate_json["setup_phase"]["current_phase"] == "COMPRESSION"
    assert candidate_json["setup_phase"]["previous_phase"] == "ACCUMULATION"


def test_screen_accum_save_calls_use_case(monkeypatch):
    from src.application.use_case.save_screen_watchlist_use_case import (
        SaveScreenWatchlistResult,
    )

    def fake_uc(**kwargs):
        uc = SimpleNamespace()
        uc.execute = lambda req: _fake_workflow_result(
            response=AccumulationScreenResponse(
                candidates=[_candidate(
                    ticker="BBCA", foreign_flow_score=80.0, bci_label="CLUSTER",
                )],
                screened_at=date(2026, 6, 28),
                window_days=getattr(req, "window", 7),
                total_tickers_checked=len(req.tickers),
                tickers_skipped=0,
                provider="fake",
            ),
            save_result=SaveScreenWatchlistResult(
                saved_count=1, name="mywatch"
            ),
        )
        return uc

    monkeypatch.setattr(
        accum_cli,
        "create_run_accumulation_screen_workflow_use_case",
        fake_uc,
    )

    result = runner.invoke(
        app,
        ["screen", "accum", "BBCA", "--save", "mywatch"],
    )

    assert result.exit_code == 0, (
        f"exit {result.exit_code} stdout={result.output!r} exc={result.exception}"
    )
    assert "✓ Saved" in result.output
    assert "mywatch" in result.output


def test_screen_accum_json_skips_save(monkeypatch):
    captured = {}

    def fake_uc(**kwargs):
        uc = SimpleNamespace()
        uc.execute = lambda req: (
            captured.update(request=req)
            or _fake_workflow_result(
                response=AccumulationScreenResponse(
                    candidates=[_candidate(ticker="BBCA")],
                    screened_at=date(2026, 6, 28),
                    window_days=getattr(req, "window", 7),
                    total_tickers_checked=1,
                    tickers_skipped=0,
                    provider="fake",
                ),
            )
        )
        return uc

    monkeypatch.setattr(
        accum_cli,
        "create_run_accumulation_screen_workflow_use_case",
        fake_uc,
    )

    result = runner.invoke(
        app,
        ["screen", "accum", "BBCA", "--format", "json", "--save", "mywatch"],
    )

    assert result.exit_code == 0, result.output
    assert "Saved" not in result.output
    req = captured["request"]
    assert req.save_enabled is False
    assert req.save_name == "mywatch"


def test_screen_accum_multi_skips_save(monkeypatch):
    captured = {}

    def fake_uc(**kwargs):
        uc = SimpleNamespace()
        uc.execute = lambda req: (
            captured.update(request=req)
            or _fake_workflow_result(
                multi_results={
                    7: AccumulationScreenResponse(
                        candidates=[_candidate()],
                        screened_at=date(2026, 6, 28),
                        window_days=7,
                        total_tickers_checked=1,
                        tickers_skipped=0,
                        provider="fake",
                    ),
                },
            )
        )
        return uc

    monkeypatch.setattr(
        accum_cli,
        "create_run_accumulation_screen_workflow_use_case",
        fake_uc,
    )

    result = runner.invoke(
        app,
        ["screen", "accum", "BBCA", "--multi", "--save", "mywatch"],
    )

    assert result.exit_code == 0, result.output
    assert "Saved" not in result.output
    req = captured["request"]
    assert req.save_enabled is False
    assert req.save_name == "mywatch"
