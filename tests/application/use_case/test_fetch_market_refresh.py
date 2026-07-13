"""Tests for fetch market refresh orchestration."""

from pathlib import Path
from unittest.mock import MagicMock

from src.application.use_case.fetch_market_refresh_use_case import (
    BENCHMARK_TICKER,
    BrokerFetchResult,
    FetchMarketRefreshRequest,
    FetchMarketRefreshUseCase,
)


def _request(**overrides) -> FetchMarketRefreshRequest:
    values = {
        "tickers": ["BBCA", "BBRI"],
        "universe": None,
        "days": 90,
        "db_path": Path("data.db"),
        "candles_provider": "yahoo",
        "broker_provider": object(),
        "broker_provider_name": "idx",
        "refresh": False,
        "candles_only": False,
        "broker_only": False,
        "no_meta": False,
        "no_enrichment": True,
    }
    values.update(overrides)
    return FetchMarketRefreshRequest(**values)


def test_fetch_market_refresh_adds_benchmark_first():
    calls: list[tuple[str, str]] = []

    def fetch_candles(**kwargs):
        calls.append(("candles", kwargs["ticker"]))
        return "✓(2026-06-18)"

    def fetch_broker(**kwargs):
        calls.append(("broker", kwargs["ticker"]))
        return BrokerFetchResult(summaries="✓(2026-06-18)", flow="✓(2026-06-18)")

    use_case = FetchMarketRefreshUseCase(
        fetch_candles=fetch_candles,
        fetch_broker=fetch_broker,
        fetch_meta=lambda ticker, db_path: "cached(1d)",
        fetch_enrichment=lambda ticker, db_path, broker_provider, force_refresh=False: "skip",
        universe_loader=MagicMock(),
    )

    response = use_case.execute(_request())

    assert response.ticker_list == [BENCHMARK_TICKER, "BBCA", "BBRI"]
    assert response.stock_tickers_only == ["BBCA", "BBRI"]
    assert calls[:2] == [("candles", BENCHMARK_TICKER), ("broker", BENCHMARK_TICKER)]
    assert response.ok_count == 3
    assert response.fail_count == 0


def test_fetch_market_refresh_normalizes_legacy_benchmark_alias():
    use_case = FetchMarketRefreshUseCase(
        fetch_candles=lambda **kwargs: "✓(2026-06-18)",
        fetch_broker=lambda **kwargs: BrokerFetchResult("n/a:index", "n/a:index"),
        fetch_meta=lambda ticker, db_path: "cached(1d)",
        fetch_enrichment=lambda ticker, db_path, broker_provider, force_refresh=False: "skip",
        universe_loader=MagicMock(),
    )

    response = use_case.execute(_request(tickers=["^JKSE", "BBCA"]))

    assert response.ticker_list == [BENCHMARK_TICKER, "BBCA"]


def test_fetch_market_refresh_empty_input_returns_empty_response():
    use_case = FetchMarketRefreshUseCase(
        fetch_candles=lambda **kwargs: "unexpected",
        fetch_broker=lambda **kwargs: BrokerFetchResult("unexpected", "unexpected"),
        fetch_meta=lambda ticker, db_path: "unexpected",
        fetch_enrichment=lambda ticker, db_path, broker_provider, force_refresh=False: "unexpected",
        universe_loader=MagicMock(),
    )

    response = use_case.execute(_request(tickers=[]))

    assert response.ticker_list == []
    assert response.ticker_results == []
    assert response.ok_count == 0


def test_fetch_market_refresh_honors_skip_flags_and_collects_notes():
    candle_notes: list[str] = []

    def fetch_candles(**kwargs):
        kwargs["short_history"].append(f"  candles {kwargs['ticker']}")
        candle_notes.append(kwargs["ticker"])
        return "backfill+1rows/span=1d"

    use_case = FetchMarketRefreshUseCase(
        fetch_candles=fetch_candles,
        fetch_broker=lambda **kwargs: BrokerFetchResult("skip", "skip"),
        fetch_meta=lambda ticker, db_path: "skip",
        fetch_enrichment=lambda ticker, db_path, broker_provider, force_refresh=False: "skip",
        universe_loader=MagicMock(),
    )

    response = use_case.execute(
        _request(candles_only=True, no_meta=True, tickers=["BBCA"])
    )

    assert candle_notes == [BENCHMARK_TICKER, "BBCA"]
    assert response.candle_short_history == [
        f"  candles {BENCHMARK_TICKER}",
        "  candles BBCA",
    ]
    assert all(result.broker_result.flow == "skip" for result in response.ticker_results)


def test_fetch_market_refresh_counts_failures_and_meta_changes():
    def fetch_candles(**kwargs):
        return "ERR:timeout" if kwargs["ticker"] == "BBCA" else "✓(2026-06-18)"

    def fetch_meta(ticker, db_path):
        return "changed->Finance" if ticker == "BBRI" else "cached(1d)"

    use_case = FetchMarketRefreshUseCase(
        fetch_candles=fetch_candles,
        fetch_broker=lambda **kwargs: BrokerFetchResult("✓(2026-06-18)", "✓(2026-06-18)"),
        fetch_meta=fetch_meta,
        fetch_enrichment=lambda ticker, db_path, broker_provider, force_refresh=False: "skip",
        universe_loader=MagicMock(),
    )

    response = use_case.execute(_request())

    assert response.ok_count == 2
    assert response.fail_count == 1
    assert response.failures == ["BBCA"]
    assert response.meta_changed == ["  BBRI: changed->Finance"]


def test_fetch_market_refresh_passes_refresh_to_enrichment():
    force_values: list[bool] = []

    def fetch_enrichment(ticker, db_path, broker_provider, force_refresh=False):
        force_values.append(force_refresh)
        return "analyst"

    use_case = FetchMarketRefreshUseCase(
        fetch_candles=lambda **kwargs: "✓(2026-06-18)",
        fetch_broker=lambda **kwargs: BrokerFetchResult("✓(2026-06-18)", "✓(2026-06-18)"),
        fetch_meta=lambda ticker, db_path: "cached(1d)",
        fetch_enrichment=fetch_enrichment,
        universe_loader=MagicMock(),
    )

    use_case.execute(_request(
        tickers=["BBCA"],
        broker_provider_name="stockbit",
        no_enrichment=False,
        refresh=True,
    ))

    assert force_values == [True, True]
