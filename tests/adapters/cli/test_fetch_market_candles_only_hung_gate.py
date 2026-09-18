"""CLI hung-gate: candles-only exit 0 when DB already has session candles."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from typer import Typer
from typer.testing import CliRunner

import src.adapters.cli.fetch_market_commands as fetch_market_commands
from src.adapters.cli.fetch_market_commands import fetch_market
from src.application.use_case.fetch_market_command_workflow_use_case import (
    FetchMarketCommandWorkflowResult,
)
from src.application.use_case.fetch_market_refresh_use_case import (
    BrokerFetchResult,
    FetchMarketRefreshResponse,
    FetchMarketTickerResult,
)
from src.domain.entities.candle import Candle
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

SESSION = date(2026, 9, 15)


def _candle(ticker: str, session: date = SESSION) -> Candle:
    return Candle(
        ticker=ticker,
        date=session,
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("105"),
        volume=1000,
    )


def _ticker_result(ticker: str, candles_status: str) -> FetchMarketTickerResult:
    hung = candles_status.startswith("ERR:")
    return FetchMarketTickerResult(
        ticker=ticker,
        candles_status=candles_status,
        broker_result=BrokerFetchResult(summaries="skip", flow="skip"),
        meta_status="skip",
        enrichment_status="skip",
        any_error=hung,
        all_cached=not hung,
    )


def _hung_result(*, stock_tickers: list[str]) -> FetchMarketCommandWorkflowResult:
    hung_stocks = [_ticker_result(ticker, "ERR:deadline") for ticker in stock_tickers]
    return FetchMarketCommandWorkflowResult(
        response=FetchMarketRefreshResponse(
            ticker_list=["IHSG", *stock_tickers],
            stock_tickers_only=list(stock_tickers),
            ticker_results=[_ticker_result("IHSG", "✓(2026-09-15)"), *hung_stocks],
            ok_count=1,
            fail_count=len(stock_tickers),
            failures=list(stock_tickers),
            hang_count=len(stock_tickers),
            hang_attempted=len(stock_tickers) + 1,
        ),
        header=None,
        calendar_status="skip",
        macro_calendar_status="skip",
        expected_trading_day=SESSION,
        context_statuses=(),
    )


class _FakeWorkflow:
    def __init__(self, result: FetchMarketCommandWorkflowResult) -> None:
        self._result = result

    def execute(self, request, on_ticker_complete=None, on_start=None):
        return self._result


@pytest.fixture
def _hung_gate_patches(monkeypatch, tmp_path: Path):
    """Stub fetch-market I/O so the hung gate is the only live path."""
    monkeypatch.setattr(
        fetch_market_commands,
        "create_broker_provider",
        lambda name: (object(), "idx"),
    )
    monkeypatch.setattr(fetch_market_commands, "print_table_summary", lambda **kwargs: None)
    monkeypatch.setattr(
        "src.application.services.bounded_call.log_hang_rate",
        lambda record, path=None: path,
    )
    db = tmp_path / "market.db"
    return db


def _invoke(db: Path, workflow: _FakeWorkflow, monkeypatch) -> object:
    monkeypatch.setattr(
        fetch_market_commands,
        "create_workflow_use_case",
        lambda **kwargs: workflow,
    )
    app = Typer()
    app.command()(fetch_market)
    runner = CliRunner()
    return runner.invoke(
        app,
        [
            "--universe",
            "lq45",
            "--candles-only",
            "--no-enrichment",
            "--no-meta",
            "--no-calendar",
            "--no-macro-calendar",
            "--db",
            str(db),
        ],
    )


def test_hung_candles_only_exits_0_when_db_has_session_candles(
    _hung_gate_patches: Path, monkeypatch
) -> None:
    db = _hung_gate_patches
    repo = SQLiteMarketRepository(db)
    repo.save_candles([_candle("BBCA"), _candle("BBRI"), _candle("IHSG")])
    result = _invoke(
        db,
        _FakeWorkflow(_hung_result(stock_tickers=["BBCA", "BBRI"])),
        monkeypatch,
    )

    out = result.stdout + result.stderr
    assert result.exit_code == 0
    assert "Same-session OHLC unavailable: BBCA, BBRI" in out
    assert "hung-fetch:" in out
    assert "same-session OHLC unavailable: BBCA, BBRI" in out


def test_hung_candles_only_exits_1_when_a_stock_candle_is_missing(
    _hung_gate_patches: Path, monkeypatch
) -> None:
    db = _hung_gate_patches
    repo = SQLiteMarketRepository(db)
    repo.save_candles([_candle("BBCA"), _candle("IHSG")])
    result = _invoke(
        db,
        _FakeWorkflow(_hung_result(stock_tickers=["BBCA", "BBRI"])),
        monkeypatch,
    )

    out = result.stdout + result.stderr
    assert result.exit_code == 1
    assert "Same-session OHLC unavailable: BBCA, BBRI" in out
    assert "hung-fetch:" in out


def test_hung_candles_only_exits_1_when_coverage_query_fails(
    _hung_gate_patches: Path, monkeypatch
) -> None:
    db = _hung_gate_patches
    db.write_bytes(b"")
    result = _invoke(
        db,
        _FakeWorkflow(_hung_result(stock_tickers=["BBCA"])),
        monkeypatch,
    )

    assert result.exit_code == 1
    assert "Same-session OHLC unavailable: BBCA" in result.stdout + result.stderr


def test_candles_only_without_hangs_exits_0_even_if_session_candle_missing(
    _hung_gate_patches: Path, monkeypatch
) -> None:
    db = _hung_gate_patches
    repo = SQLiteMarketRepository(db)
    repo.save_candles([_candle("IHSG")])
    workflow_result = FetchMarketCommandWorkflowResult(
        response=FetchMarketRefreshResponse(
            ticker_list=["IHSG", "BBCA"],
            stock_tickers_only=["BBCA"],
            ticker_results=[
                _ticker_result("IHSG", "✓(2026-09-15)"),
                _ticker_result("BBCA", "✓(2026-09-15)"),
            ],
            ok_count=2,
            fail_count=0,
            hang_count=0,
            hang_attempted=2,
        ),
        header=None,
        calendar_status="skip",
        macro_calendar_status="skip",
        expected_trading_day=SESSION,
        context_statuses=(),
    )
    result = _invoke(db, _FakeWorkflow(workflow_result), monkeypatch)

    assert result.exit_code == 0
    assert "Same-session OHLC unavailable" not in result.stdout + result.stderr
