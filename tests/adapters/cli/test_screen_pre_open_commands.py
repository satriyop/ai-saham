"""Tests for pre-open screen CLI helpers."""

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.adapters.cli.screen_pre_open_commands import _default_pre_open_config_path
from src.adapters.cli.screen_pre_open_display import (
    display_results as _display_results,
)
from src.adapters.cli.screen_pre_open_workflow_factory import (
    PreOpenBrowserPlan,
    PreOpenCliWorkflow,
)
from src.application.use_case.pre_open_workflow_use_case import (
    PreOpenDataFreshness,
    PreOpenWorkflowResponse,
)
from src.domain.ports.browser_data_provider import BrowserInteractionRequired
from src.domain.value_objects.market_status import MarketStatus
from src.domain.value_objects.pre_open_source_status import PreOpenSourceStatus
from src.domain.value_objects.screener_result import (
    MoverData,
    PreOpenScreenResult,
    ScreenerCandidate,
)
from src.infrastructure.persistence.sqlite_iev_repository import SQLiteIEVRepository

runner = CliRunner()

_BYPASS_GUARD_STATUS = MarketStatus(
    status="STATUS_OPEN",
    session_name="Pre-Open",
    is_open=False,
    session_open=None,
    session_close=None,
    fetched_at=datetime(2026, 6, 12, 8, 50),
    source="stockbit",
)


def _candidate(ticker: str) -> ScreenerCandidate:
    return ScreenerCandidate(
        ticker=ticker,
        iev=150000,
        entry_price=Decimal("1000"),
        stop_loss_price=Decimal("950"),
        capital=Decimal("3000000"),
    )


def test_default_pre_open_config_lives_under_config():
    assert _default_pre_open_config_path() == Path("config/pre_open_screener.yaml")
    assert _default_pre_open_config_path().exists()


def test_pre_open_strategy_alias_is_removed():
    result = runner.invoke(
        app,
        [
            "screen", "pre-open",
            "--movers-json",
            '[{"ticker":"BBCA","iev":150000}]',
            "--fast",
            "--strategy",
            str(_default_pre_open_config_path()),
        ],
    )

    assert result.exit_code != 0


def test_pre_open_results_render_rich_summary_panel(capsys):
    _display_results(
        candidates=[_candidate("BBCA")],
        screened_date=date(2026, 6, 12),
        iev_min=100_000,
        total_movers_seen=3,
        warnings=["manual smoke warning"],
        data_freshness=PreOpenDataFreshness(
            analysis_date=date(2026, 6, 12),
            candle_end=date(2026, 6, 11),
            broker_end=date(2026, 6, 10),
            warnings=("freshness warning",),
        ),
    )

    out = capsys.readouterr().out
    assert "Pre-Open Screener" in out
    assert "Session Summary" in out
    assert "PRE-OPEN OPENING SETUP" in out
    assert "SETUP:" in out
    assert "VERDICT:" not in out
    assert "Watchlist" in out
    assert "BBCA" in out
    assert "manual smoke warning" in out
    assert "Candles through" in out
    assert "2026-06-11" in out
    assert "freshness warning" in out


def test_pre_open_empty_results_points_to_fetch_iev(capsys):
    _display_results(
        candidates=[],
        screened_date=date(2026, 6, 12),
        iev_min=100_000,
        total_movers_seen=3,
        warnings=[],
    )

    out = capsys.readouterr().out
    assert "Run: saham fetch iev" in out
    assert "fetch-top5" not in out


def test_pre_open_results_always_show_source_status(capsys):
    _display_results(
        candidates=[_candidate("BBCA")],
        screened_date=date(2026, 6, 12),
        iev_min=100_000,
        total_movers_seen=1,
        warnings=[],
        source_status=PreOpenSourceStatus.LIVE_SUCCESS,
    )

    out = capsys.readouterr().out
    assert "LIVE" in out


def test_pre_open_empty_unavailable_does_not_look_like_valid_empty(capsys):
    _display_results(
        candidates=[],
        screened_date=date(2026, 6, 12),
        iev_min=100_000,
        total_movers_seen=0,
        warnings=[],
        source_status=PreOpenSourceStatus.UNAVAILABLE,
        source_message="auth failure",
    )

    out = capsys.readouterr().out
    assert "unavailable" in out.lower()
    assert "auth failure" in out
    assert "No candidates passed the IEV filter." not in out


def test_pre_open_empty_outside_window_does_not_look_like_valid_empty(capsys):
    _display_results(
        candidates=[],
        screened_date=date(2026, 6, 12),
        iev_min=100_000,
        total_movers_seen=0,
        warnings=[],
        source_status=PreOpenSourceStatus.OUTSIDE_WINDOW,
        source_message="Outside the pre-open live window (08:45-09:00 WIB).",
    )

    out = capsys.readouterr().out
    assert "outside" in out.lower()
    assert "No candidates passed the IEV filter." not in out


def test_pre_open_empty_confirmed_states_valid_empty_payload(capsys):
    _display_results(
        candidates=[],
        screened_date=date(2026, 6, 12),
        iev_min=100_000,
        total_movers_seen=0,
        warnings=[],
        source_status=PreOpenSourceStatus.EMPTY_CONFIRMED,
    )

    out = capsys.readouterr().out
    assert "valid empty mover list" in out


def test_pre_open_snapshot_state_visibly_labeled(capsys):
    _display_results(
        candidates=[_candidate("BBCA")],
        screened_date=date(2026, 6, 12),
        iev_min=100_000,
        total_movers_seen=1,
        warnings=[],
        source_status=PreOpenSourceStatus.SNAPSHOT_SUCCESS,
        source_snapshot_ref="data/iev/20260714/iev.json",
    )

    out = capsys.readouterr().out
    assert "SNAPSHOT" in out
    assert "data/iev/20260714/iev.json" in out


def test_pre_open_format_json_emits_envelope(monkeypatch):
    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 6, 12, 8, 50, tzinfo=tz)

    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.datetime", _FixedDatetime
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.resolve_pre_open_market_status",
        lambda: _BYPASS_GUARD_STATUS,
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.resolve_pre_open_browser_plan",
        lambda **kwargs: PreOpenBrowserPlan(
            provider=object(), autonomous=True, session_missing=False
        ),
    )

    response = PreOpenWorkflowResponse(
        result=PreOpenScreenResult(
            screened_date=date(2026, 6, 12),
            iev_min=100_000,
            total_movers_seen=1,
            candidates=[_candidate("BBCA")],
        ),
        warnings=[],
        raw_movers=[],
        data_freshness=PreOpenDataFreshness(
            analysis_date=date(2026, 6, 12),
            candle_end=date(2026, 6, 11),
            broker_end=date(2026, 6, 10),
        ),
        source_status=PreOpenSourceStatus.LIVE_SUCCESS,
    )
    workflow = SimpleNamespace(execute=lambda req: response)
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.create_pre_open_cli_workflow",
        lambda **kwargs: PreOpenCliWorkflow(
            workflow=workflow,
            market_repository=None,
            broker_repository=None,
            ai_warnings=[],
        ),
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.write_pre_open_sidecar",
        lambda **kwargs: None,
    )

    result = runner.invoke(
        app,
        [
            "screen",
            "pre-open",
            "--movers-json",
            '[{"ticker":"BBCA","iev":150000}]',
            "--fast",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["verb"] == "pre-open"
    assert payload["status"] == "ok"
    assert payload["data"]["candidates"][0]["ticker"] == "BBCA"
    assert "Pre-Open Screener" not in result.output


def test_pre_open_missing_session_json_status_missing(monkeypatch):
    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 6, 12, 8, 50, tzinfo=tz)

    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.datetime", _FixedDatetime
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.resolve_pre_open_market_status",
        lambda: _BYPASS_GUARD_STATUS,
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.resolve_pre_open_browser_plan",
        lambda **kwargs: PreOpenBrowserPlan(
            provider=None, autonomous=False, session_missing=True
        ),
    )

    result = runner.invoke(app, ["screen", "pre-open", "--format", "json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "missing"
    assert payload["fetch_hint"] == "saham fetch stockbit login"


def test_pre_open_invalid_movers_json_exits_1(monkeypatch):
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.resolve_pre_open_market_status",
        lambda: _BYPASS_GUARD_STATUS,
    )

    result = runner.invoke(
        app,
        ["screen", "pre-open", "--movers-json", "{not valid json"],
    )

    assert result.exit_code == 1


def test_pre_open_non_array_movers_json_exits_1(monkeypatch):
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.resolve_pre_open_market_status",
        lambda: _BYPASS_GUARD_STATUS,
    )

    result = runner.invoke(
        app,
        ["screen", "pre-open", "--movers-json", '{"ticker": "BBCA"}'],
    )

    assert result.exit_code == 1


def test_pre_open_missing_playwright_session_prints_plan_and_exits_0(monkeypatch):
    """Provider missing + inside pre-open window -> still prints browser plan."""

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 6, 12, 8, 50, tzinfo=tz)

    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.datetime", _FixedDatetime
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.resolve_pre_open_market_status",
        lambda: _BYPASS_GUARD_STATUS,
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.resolve_pre_open_browser_plan",
        lambda **kwargs: PreOpenBrowserPlan(
            provider=None, autonomous=False, session_missing=True
        ),
    )

    result = runner.invoke(app, ["screen", "pre-open"])

    assert result.exit_code == 0
    assert "Playwright installed but no session found." in result.output
    assert "Run: saham fetch stockbit login" in result.output


def test_pre_open_missing_provider_outside_window_with_snapshot_skips_browser_plan(
    monkeypatch, tmp_path
):
    """Provider missing + outside window + saved snapshot -> SNAPSHOT, no browser plan."""
    db_path = tmp_path / "data.db"
    snapshot_date = date(2026, 6, 12)
    SQLiteIEVRepository(db_path).save_snapshot(
        snapshot_date, [MoverData(ticker="BBCA", iev=150_000, iep=9000)]
    )

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 6, 12, 10, 15, tzinfo=tz)

    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.datetime", _FixedDatetime
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.resolve_pre_open_market_status",
        lambda: _BYPASS_GUARD_STATUS,
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.resolve_pre_open_browser_plan",
        lambda **kwargs: PreOpenBrowserPlan(
            provider=None, autonomous=False, session_missing=True
        ),
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands._default_sidecar_path",
        lambda: tmp_path / "sidecar.json",
    )
    sidecar_calls = []
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.write_pre_open_sidecar",
        lambda **kwargs: sidecar_calls.append(kwargs),
    )

    result = runner.invoke(app, ["screen", "pre-open", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "SNAPSHOT" in result.output
    assert snapshot_date.isoformat() in result.output
    assert "BROWSER ACTION PLAN" not in result.output
    assert "Playwright installed but no session found." not in result.output
    assert sidecar_calls == []


def test_pre_open_missing_provider_outside_window_no_snapshot_skips_browser_plan(
    monkeypatch, tmp_path
):
    """Provider missing + outside window + no snapshot -> OUTSIDE WINDOW, no browser plan."""
    db_path = tmp_path / "data.db"

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 6, 12, 10, 15, tzinfo=tz)

    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.datetime", _FixedDatetime
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.resolve_pre_open_market_status",
        lambda: _BYPASS_GUARD_STATUS,
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.resolve_pre_open_browser_plan",
        lambda **kwargs: PreOpenBrowserPlan(
            provider=None, autonomous=False, session_missing=True
        ),
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands._default_sidecar_path",
        lambda: tmp_path / "sidecar.json",
    )
    sidecar_calls = []
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.write_pre_open_sidecar",
        lambda **kwargs: sidecar_calls.append(kwargs),
    )

    result = runner.invoke(app, ["screen", "pre-open", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "OUTSIDE WINDOW" in result.output
    assert "BROWSER ACTION PLAN" not in result.output
    assert "Playwright installed but no session found." not in result.output
    assert sidecar_calls == []


def test_pre_open_delegates_workflow_construction_and_writes_sidecar(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.resolve_pre_open_market_status",
        lambda: _BYPASS_GUARD_STATUS,
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.resolve_pre_open_browser_plan",
        lambda **kwargs: PreOpenBrowserPlan(
            provider=object(), autonomous=False, session_missing=False
        ),
    )

    fake_response = PreOpenWorkflowResponse(
        result=PreOpenScreenResult(
            screened_date=date(2026, 6, 12),
            iev_min=100_000,
            total_movers_seen=1,
            candidates=[_candidate("BBCA")],
        ),
        warnings=[],
        raw_movers=[],
        data_freshness=PreOpenDataFreshness(
            analysis_date=date(2026, 6, 12),
            candle_end=None,
            broker_end=None,
        ),
    )

    calls = {"factory": None, "execute": 0, "sidecar": None}

    class _FakeWorkflow:
        def execute(self, request):
            calls["execute"] += 1
            return fake_response

    def _fake_create_pre_open_cli_workflow(**kwargs):
        calls["factory"] = kwargs
        return PreOpenCliWorkflow(
            workflow=_FakeWorkflow(),
            market_repository=None,
            broker_repository=None,
        )

    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.create_pre_open_cli_workflow",
        _fake_create_pre_open_cli_workflow,
    )

    def _fake_write_sidecar(**kwargs):
        calls["sidecar"] = kwargs

    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.write_pre_open_sidecar",
        _fake_write_sidecar,
    )

    result = runner.invoke(
        app,
        ["screen", "pre-open", "--movers-json", '[{"ticker":"BBCA","iev":150000}]'],
    )

    assert result.exit_code == 0, result.output
    assert calls["factory"] is not None
    assert calls["execute"] == 1
    assert calls["sidecar"] is not None
    assert calls["sidecar"]["candidates"] == fake_response.result.candidates


def test_pre_open_browser_interaction_required_maps_to_exit_1(monkeypatch):
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.resolve_pre_open_market_status",
        lambda: _BYPASS_GUARD_STATUS,
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.resolve_pre_open_browser_plan",
        lambda **kwargs: PreOpenBrowserPlan(
            provider=object(), autonomous=False, session_missing=False
        ),
    )

    class _RaisingWorkflow:
        def execute(self, request):
            raise BrowserInteractionRequired(
                url="https://stockbit.com", instructions="log in manually"
            )

    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.create_pre_open_cli_workflow",
        lambda **kwargs: PreOpenCliWorkflow(
            workflow=_RaisingWorkflow(), market_repository=None, broker_repository=None
        ),
    )

    result = runner.invoke(
        app,
        ["screen", "pre-open", "--movers-json", '[{"ticker":"BBCA","iev":150000}]'],
    )

    assert result.exit_code == 1
    assert "Browser action required" in result.output


def _invoke_with_response(monkeypatch, response: PreOpenWorkflowResponse) -> tuple:
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.resolve_pre_open_market_status",
        lambda: _BYPASS_GUARD_STATUS,
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.resolve_pre_open_browser_plan",
        lambda **kwargs: PreOpenBrowserPlan(
            provider=object(), autonomous=False, session_missing=False
        ),
    )

    class _FakeWorkflow:
        def execute(self, request):
            return response

    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.create_pre_open_cli_workflow",
        lambda **kwargs: PreOpenCliWorkflow(
            workflow=_FakeWorkflow(), market_repository=None, broker_repository=None
        ),
    )

    calls = {"sidecar": None}

    def _fake_write_sidecar(**kwargs):
        calls["sidecar"] = kwargs

    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.write_pre_open_sidecar",
        _fake_write_sidecar,
    )

    result = runner.invoke(
        app,
        ["screen", "pre-open", "--movers-json", '[{"ticker":"BBCA","iev":150000}]'],
    )
    return result, calls


def test_pre_open_writes_sidecar_for_empty_confirmed(monkeypatch):
    response = PreOpenWorkflowResponse(
        result=PreOpenScreenResult(
            screened_date=date(2026, 6, 12),
            iev_min=100_000,
            total_movers_seen=0,
            candidates=[],
        ),
        warnings=[],
        raw_movers=[],
        data_freshness=PreOpenDataFreshness(
            analysis_date=date(2026, 6, 12), candle_end=None, broker_end=None
        ),
        source_status=PreOpenSourceStatus.EMPTY_CONFIRMED,
        source_message="Provider returned a valid empty mover list.",
    )

    result, calls = _invoke_with_response(monkeypatch, response)

    assert result.exit_code == 0, result.output
    assert calls["sidecar"] is not None
    assert "EMPTY" in result.output


def test_pre_open_suppresses_sidecar_for_unavailable(monkeypatch):
    response = PreOpenWorkflowResponse(
        result=PreOpenScreenResult(
            screened_date=date(2026, 6, 12),
            iev_min=100_000,
            total_movers_seen=0,
            candidates=[],
        ),
        warnings=[],
        raw_movers=[],
        data_freshness=PreOpenDataFreshness(
            analysis_date=date(2026, 6, 12), candle_end=None, broker_end=None
        ),
        source_status=PreOpenSourceStatus.UNAVAILABLE,
        source_message="connection reset",
    )

    result, calls = _invoke_with_response(monkeypatch, response)

    assert result.exit_code == 0, result.output
    assert calls["sidecar"] is None
    assert "unavailable" in result.output.lower()
    assert "No candidates passed the IEV filter." not in result.output


def test_pre_open_suppresses_sidecar_for_outside_window(monkeypatch):
    response = PreOpenWorkflowResponse(
        result=PreOpenScreenResult(
            screened_date=date(2026, 6, 12),
            iev_min=100_000,
            total_movers_seen=0,
            candidates=[],
        ),
        warnings=[],
        raw_movers=[],
        data_freshness=PreOpenDataFreshness(
            analysis_date=date(2026, 6, 12), candle_end=None, broker_end=None
        ),
        source_status=PreOpenSourceStatus.OUTSIDE_WINDOW,
        source_message="Outside the pre-open live window.",
    )

    result, calls = _invoke_with_response(monkeypatch, response)

    assert result.exit_code == 0, result.output
    assert calls["sidecar"] is None
    assert "outside" in result.output.lower()
    assert "No candidates passed the IEV filter." not in result.output


def test_pre_open_suppresses_sidecar_for_snapshot_success(monkeypatch):
    response = PreOpenWorkflowResponse(
        result=PreOpenScreenResult(
            screened_date=date(2026, 6, 12),
            iev_min=100_000,
            total_movers_seen=1,
            candidates=[_candidate("BBCA")],
        ),
        warnings=[],
        raw_movers=[],
        data_freshness=PreOpenDataFreshness(
            analysis_date=date(2026, 6, 12), candle_end=None, broker_end=None
        ),
        source_status=PreOpenSourceStatus.SNAPSHOT_SUCCESS,
        source_snapshot_ref="data/iev/20260714/iev.json",
    )

    result, calls = _invoke_with_response(monkeypatch, response)

    assert result.exit_code == 0, result.output
    assert calls["sidecar"] is None
    assert "SNAPSHOT" in result.output


def test_pre_open_outside_window_passed_to_workflow_request_for_autonomous_run(
    monkeypatch,
):
    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 6, 12, 10, 15, tzinfo=tz)

    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.datetime", _FixedDatetime
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.resolve_pre_open_market_status",
        lambda: _BYPASS_GUARD_STATUS,
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.resolve_pre_open_browser_plan",
        lambda **kwargs: PreOpenBrowserPlan(provider=object(), autonomous=True, session_missing=False),
    )

    fake_response = PreOpenWorkflowResponse(
        result=PreOpenScreenResult(
            screened_date=date(2026, 6, 12),
            iev_min=100_000,
            total_movers_seen=0,
            candidates=[],
        ),
        warnings=[],
        raw_movers=[],
        data_freshness=PreOpenDataFreshness(
            analysis_date=date(2026, 6, 12), candle_end=None, broker_end=None
        ),
        source_status=PreOpenSourceStatus.OUTSIDE_WINDOW,
    )

    captured = {"request": None}

    class _FakeWorkflow:
        def execute(self, request):
            captured["request"] = request
            return fake_response

    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.create_pre_open_cli_workflow",
        lambda **kwargs: PreOpenCliWorkflow(
            workflow=_FakeWorkflow(), market_repository=None, broker_repository=None
        ),
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.write_pre_open_sidecar",
        lambda **kwargs: None,
    )

    result = runner.invoke(app, ["screen", "pre-open"])

    assert result.exit_code == 0, result.output
    assert captured["request"] is not None
    assert captured["request"].outside_window is True


def test_pre_open_outside_window_with_saved_snapshot_yields_snapshot_success_end_to_end(
    monkeypatch, tmp_path
):
    """Full workflow (real factory, real SQLiteIEVRepository) — not a hand-built fake response."""
    db_path = tmp_path / "data.db"
    snapshot_date = date(2026, 6, 12)
    SQLiteIEVRepository(db_path).save_snapshot(
        snapshot_date, [MoverData(ticker="BBCA", iev=150_000, iep=9000)]
    )

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 6, 12, 10, 15, tzinfo=tz)

    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.datetime", _FixedDatetime
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.resolve_pre_open_market_status",
        lambda: _BYPASS_GUARD_STATUS,
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.resolve_pre_open_browser_plan",
        lambda **kwargs: PreOpenBrowserPlan(
            provider=object(), autonomous=True, session_missing=False
        ),
    )
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands._default_sidecar_path",
        lambda: tmp_path / "sidecar.json",
    )

    sidecar_calls = []
    monkeypatch.setattr(
        "src.adapters.cli.screen_pre_open_commands.write_pre_open_sidecar",
        lambda **kwargs: sidecar_calls.append(kwargs),
    )

    result = runner.invoke(app, ["screen", "pre-open", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "SNAPSHOT" in result.output
    assert snapshot_date.isoformat() in result.output
    assert sidecar_calls == []
