"""Tests for pre-open screen CLI helpers."""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

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
from src.domain.value_objects.screener_result import PreOpenScreenResult, ScreenerCandidate

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
