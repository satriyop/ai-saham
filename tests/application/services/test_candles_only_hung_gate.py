"""Unit tests for the candles-only hung-fetch coverage gate."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.application.services.candles_only_hung_gate import (
    candles_only_unavailable_tickers,
    hung_candles_only_fails_closed,
    missing_required_session_candles,
    missing_same_session_candle_tickers,
)
from src.domain.entities.candle import Candle
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository


def test_unavailable_tickers_prefers_response_field_when_present() -> None:
    response = SimpleNamespace(
        unavailable_tickers=["CPIN", "GOTO"],
        ticker_results=[SimpleNamespace(ticker="BBCA", candles_status="ERR:deadline")],
        failures=["BBCA"],
    )
    assert candles_only_unavailable_tickers(response) == ["CPIN", "GOTO"]


def test_unavailable_tickers_uses_empty_response_field_without_falling_back() -> None:
    response = SimpleNamespace(
        unavailable_tickers=[],
        ticker_results=[SimpleNamespace(ticker="BBCA", candles_status="ERR:deadline")],
        failures=["BBCA"],
    )
    assert candles_only_unavailable_tickers(response) == []


def test_unavailable_tickers_derived_from_err_candle_status() -> None:
    response = SimpleNamespace(
        ticker_results=[
            SimpleNamespace(ticker="IHSG", candles_status="✓(2026-09-15)"),
            SimpleNamespace(ticker="BBCA", candles_status="ERR:deadline"),
            SimpleNamespace(ticker="BBRI", candles_status="ERR:timeout"),
        ],
        failures=["BBCA", "BBRI", "EXTRA"],
    )
    assert candles_only_unavailable_tickers(response) == ["BBCA", "BBRI"]


def test_unavailable_tickers_falls_back_to_failures_when_no_err_status() -> None:
    response = SimpleNamespace(
        ticker_results=[SimpleNamespace(ticker="BBCA", candles_status="✓(2026-09-15)")],
        failures=["BBRI"],
    )
    assert candles_only_unavailable_tickers(response) == ["BBRI"]


def test_missing_same_session_candle_tickers_is_case_insensitive() -> None:
    missing = missing_same_session_candle_tickers(
        ["BBCA", "BBRI", "BMRI"],
        ["bbca", "BMRI"],
    )
    assert missing == ("BBRI",)


def test_missing_same_session_candle_tickers_empty_when_coverage_complete() -> None:
    missing = missing_same_session_candle_tickers(["BBCA", "BBRI"], ["BBRI", "BBCA", "IHSG"])
    assert missing == ()


def test_hung_gate_soft_success_when_hung_but_coverage_complete() -> None:
    assert hung_candles_only_fails_closed(hung_count=3, missing_tickers=()) is False


def test_hung_gate_fails_closed_when_hung_and_any_stock_missing() -> None:
    assert hung_candles_only_fails_closed(hung_count=1, missing_tickers=("BBRI",)) is True


def test_hung_gate_does_not_fail_when_not_hung() -> None:
    assert hung_candles_only_fails_closed(hung_count=0, missing_tickers=("BBCA",)) is False


def _candle(ticker: str, session: date) -> Candle:
    return Candle(
        ticker=ticker,
        date=session,
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("105"),
        volume=1000,
    )


def test_missing_required_session_candles_uses_market_repo(tmp_path) -> None:
    session = date(2026, 9, 15)
    repo = SQLiteMarketRepository(tmp_path / "market.db")
    repo.save_candles([_candle("BBCA", session), _candle("IHSG", session)])

    missing = missing_required_session_candles(
        ["BBCA", "BBRI"],
        session,
        repo,
    )

    assert missing == ("BBRI",)
