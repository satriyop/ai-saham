"""Tests for pre-open screen CLI helpers."""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.adapters.cli.screen_pre_open_commands import (
    DEFAULT_PRE_OPEN_CONFIG_PATH,
    _build_intraday_run_guard,
)
from src.adapters.cli.screen_pre_open_display import (
    display_results as _display_results,
)
from src.application.use_case.pre_open_workflow_use_case import PreOpenDataFreshness
from src.domain.value_objects.market_status import MarketStatus
from src.domain.value_objects.screener_result import ScreenerCandidate

runner = CliRunner()


def _candidate(ticker: str) -> ScreenerCandidate:
    return ScreenerCandidate(
        ticker=ticker,
        iev=150000,
        entry_price=Decimal("1000"),
        stop_loss_price=Decimal("950"),
        capital=Decimal("3000000"),
    )


def _local_clock_status(session_name: str, is_open: bool, dt: datetime) -> MarketStatus:
    """Build a local_clock MarketStatus for guard tests — isolated from file cache."""
    return MarketStatus(
        status="STATUS_OPEN" if is_open else "STATUS_CLOSE",
        session_name=session_name,
        is_open=is_open,
        session_open=None,
        session_close=None,
        fetched_at=dt,
        source="local_clock",
    )


def test_pre_open_guard_blocks_weekends_without_override():
    dt = datetime(2026, 6, 13, 8, 50, tzinfo=ZoneInfo("Asia/Jakarta"))
    guard = _build_intraday_run_guard(
        dt,
        allow_non_trading_day=False,
        market_status=_local_clock_status("Weekend", False, dt),
    )

    assert guard.error is not None
    assert "weekend" in guard.error


def test_pre_open_guard_allows_weekend_dry_run_with_warning():
    dt = datetime(2026, 6, 13, 8, 50, tzinfo=ZoneInfo("Asia/Jakarta"))
    guard = _build_intraday_run_guard(
        dt,
        allow_non_trading_day=True,
        market_status=_local_clock_status("Weekend", False, dt),
    )

    assert guard.error is None
    assert any("weekend" in warning for warning in guard.warnings)


def test_pre_open_guard_warns_outside_pre_open_window():
    dt = datetime(2026, 6, 12, 10, 15, tzinfo=ZoneInfo("Asia/Jakarta"))
    guard = _build_intraday_run_guard(
        dt,
        allow_non_trading_day=False,
        market_status=_local_clock_status("Regular", True, dt),
    )

    assert guard.error is None
    assert any("outside IDX pre-open window" in warning for warning in guard.warnings)


def test_default_pre_open_config_lives_under_config():
    assert DEFAULT_PRE_OPEN_CONFIG_PATH == Path("config/pre_open_screener.yaml")
    assert DEFAULT_PRE_OPEN_CONFIG_PATH.exists()


def test_pre_open_strategy_alias_is_deprecated():
    result = runner.invoke(
        app,
        [
            "screen", "pre-open",
            "--movers-json",
            '[{"ticker":"BBCA","iev":150000}]',
            "--fast",
            "--strategy",
            str(DEFAULT_PRE_OPEN_CONFIG_PATH),
        ],
    )

    assert "Warning: --strategy is deprecated" in result.output




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
    assert "PRE-OPEN CANDIDATE PLAN" in out
    assert "PLAN:" in out
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
