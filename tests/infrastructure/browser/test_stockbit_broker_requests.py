"""Tests for pure Stockbit broker URL construction."""

from datetime import date

from src.infrastructure.browser.stockbit_broker_requests import (
    build_broker_daily_flow_url,
    build_broker_summary_url,
    build_foreign_flow_history_url,
    build_foreign_top_stocks_url,
    build_historical_summary_url,
)
from src.infrastructure.config.stockbit_config import (
    load_stockbit_config,
)


def test_build_broker_summary_url_contains_endpoint_ticker_period_limit():
    _CFG = load_stockbit_config()
    url = build_broker_summary_url(
        "bbca", "BROKER_SUMMARY_PERIOD_LAST_7_DAYS", limit=25, stockbit_config=_CFG
    )
    assert url.startswith(_CFG.marketdetectors_url)
    assert "/BBCA" in url
    assert "period=BROKER_SUMMARY_PERIOD_LAST_7_DAYS" in url
    assert "limit=25" in url


def test_build_foreign_top_stocks_url_repeats_broker_code_and_has_page_limit():
    _CFG = load_stockbit_config()
    url = build_foreign_top_stocks_url(
        ["AK", "ZP", "YP"],
        "RT_PERIOD_LAST_7_DAYS",
        limit=20,
        page=1,
        stockbit_config=_CFG,
    )
    assert url.startswith(_CFG.broker_activity_url)
    assert url.count("broker_code=AK") == 1
    assert url.count("broker_code=ZP") == 1
    assert url.count("broker_code=YP") == 1
    assert "period=RT_PERIOD_LAST_7_DAYS" in url
    assert "limit=20" in url
    assert "page=1" in url
    assert "net_val_period=NET_VAL_PERIOD_7D" in url


def test_build_foreign_flow_history_url_repeats_broker_codes_and_caps_days():
    _CFG = load_stockbit_config()
    url = build_foreign_flow_history_url("bbca", ["AK", "ZP"], days=500, stockbit_config=_CFG)
    assert url.startswith(_CFG.broker_historical_url)
    assert url.count("broker_codes=AK") == 1
    assert url.count("broker_codes=ZP") == 1
    assert "symbols=BBCA" in url
    assert "pagination.limit=365" in url  # capped at min(days, 365)


def test_build_foreign_flow_history_url_uses_actual_days_when_below_cap():
    _CFG = load_stockbit_config()
    url = build_foreign_flow_history_url("bbca", ["AK"], days=30, stockbit_config=_CFG)
    assert "pagination.limit=30" in url


def test_build_historical_summary_url_formats_ticker_and_dates():
    _CFG = load_stockbit_config()
    url = build_historical_summary_url(
        "bbca",
        date(2026, 6, 17),
        date(2026, 6, 18),
        page=2,
        limit=50,
        stockbit_config=_CFG,
    )
    assert _CFG.historical_summary_url.format(ticker="BBCA") in url
    assert "start_date=2026-06-17" in url
    assert "end_date=2026-06-18" in url
    assert "limit=50" in url
    assert "page=2" in url


def test_build_broker_daily_flow_url_uses_single_broker_codes_param():
    _CFG = load_stockbit_config()
    url = build_broker_daily_flow_url("bbca", "AK", page=1, limit=100, stockbit_config=_CFG)
    assert url.startswith(_CFG.broker_historical_url)
    assert "broker_codes=AK" in url
    assert "symbols=BBCA" in url
    assert "pagination.page=1" in url
    assert "pagination.limit=100" in url
