"""
Pure URL construction for Stockbit broker/foreign-flow endpoints.

Builds query strings for the Exodus API endpoints used by
StockbitBrokerProvider. No network I/O — only string assembly against
STOCKBIT_CFG endpoint templates.

Extracted from stockbit_broker_provider.py (audit finding 16).

Layer: Infrastructure
"""

from __future__ import annotations

from datetime import date

from src.infrastructure.config.stockbit_config import STOCKBIT_CFG

_sb = STOCKBIT_CFG

_MARKETDETECTORS_API = _sb.marketdetectors_url
_BROKER_ACTIVITY_API = _sb.broker_activity_url
_BROKER_HISTORICAL_API = _sb.broker_historical_url
_HISTORICAL_SUMMARY_API = _sb.historical_summary_url


def build_broker_summary_url(ticker: str, period: str, limit: int = 25) -> str:
    """URL for the stock-centric marketdetectors named-broker breakdown."""
    return (
        f"{_MARKETDETECTORS_API}/{ticker.upper()}"
        f"?transaction_type=TRANSACTION_TYPE_NET"
        f"&market_board=MARKET_BOARD_REGULER"
        f"&investor_type=INVESTOR_TYPE_ALL"
        f"&limit={limit}"
        f"&period={period}"
    )


def build_foreign_top_stocks_url(
    broker_codes: list[str] | tuple[str, ...],
    period: str,
    limit: int,
    page: int = 1,
) -> str:
    """URL for the broker-centric activity scan (foreign top movers)."""
    broker_params = "&".join(f"broker_code={c}" for c in broker_codes)
    return (
        f"{_BROKER_ACTIVITY_API}?{broker_params}"
        f"&transaction_type=TRANSACTION_TYPE_NET"
        f"&investor_type=INVESTOR_TYPE_ALL"
        f"&limit={limit}&market_board=MARKET_TYPE_REGULER&page={page}"
        f"&period={period}"
        f"&net_val_period=NET_VAL_PERIOD_7D"
    )


def build_foreign_flow_history_url(
    ticker: str,
    broker_codes: list[str] | tuple[str, ...],
    days: int,
) -> str:
    """URL for the stock-centric historical daily foreign flow series."""
    codes_params = "&".join(f"broker_codes={c}" for c in broker_codes)
    return (
        f"{_BROKER_HISTORICAL_API}?interval=INTERVAL_DAILY"
        f"&period=RT_PERIOD_LAST_1_YEAR"
        f"&{codes_params}"
        f"&symbols={ticker.upper()}"
        f"&market_board=BOARD_TYPE_REGULAR"
        f"&investor_type=INVESTOR_TYPE_ALL"
        f"&pagination.page=1&pagination.limit={min(days, 365)}"
    )


def build_historical_summary_url(
    ticker: str,
    start_date: date,
    end_date: date,
    page: int,
    limit: int = 50,
) -> str:
    """URL for the per-day historical summary endpoint (totals + flow)."""
    return (
        f"{_HISTORICAL_SUMMARY_API.format(ticker=ticker.upper())}"
        f"?period=HS_PERIOD_DAILY"
        f"&start_date={start_date.isoformat()}"
        f"&end_date={end_date.isoformat()}"
        f"&limit={limit}&page={page}"
    )


def build_broker_daily_flow_url(
    ticker: str,
    broker_code: str,
    page: int,
    limit: int = 100,
) -> str:
    """URL for per-broker per-day flow (broker/activity/historical, single code)."""
    return (
        f"{_BROKER_HISTORICAL_API}"
        f"?broker_codes={broker_code}"
        f"&symbols={ticker.upper()}"
        f"&market_board=BOARD_TYPE_REGULAR"
        f"&investor_type=INVESTOR_TYPE_ALL"
        f"&interval=INTERVAL_DAILY"
        f"&period=RT_PERIOD_LAST_1_YEAR"
        f"&pagination.page={page}"
        f"&pagination.limit={limit}"
    )
