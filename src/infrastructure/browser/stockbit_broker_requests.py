"""
Pure URL construction for Stockbit broker/foreign-flow endpoints.

Builds query strings for the Exodus API endpoints used by
StockbitBrokerProvider. No network I/O — only string assembly against
StockbitConfig values.

Extracted from stockbit_broker_provider.py (audit finding 16).

Layer: Infrastructure
"""

from __future__ import annotations

from datetime import date

from src.infrastructure.config.stockbit_config import (
    StockbitConfig,
    load_stockbit_config,
)


def build_broker_summary_url(
    ticker: str,
    period: str,
    limit: int = 25,
    *,
    stockbit_config: StockbitConfig | None = None,
) -> str:
    """URL for the stock-centric marketdetectors named-broker breakdown."""
    cfg = stockbit_config or load_stockbit_config()
    return (
        f"{cfg.marketdetectors_url}/{ticker.upper()}"
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
    *,
    stockbit_config: StockbitConfig | None = None,
) -> str:
    """URL for the broker-centric activity scan (foreign top movers)."""
    cfg = stockbit_config or load_stockbit_config()
    broker_params = "&".join(f"broker_code={c}" for c in broker_codes)
    return (
        f"{cfg.broker_activity_url}?{broker_params}"
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
    *,
    stockbit_config: StockbitConfig | None = None,
) -> str:
    """URL for the stock-centric historical daily foreign flow series."""
    cfg = stockbit_config or load_stockbit_config()
    codes_params = "&".join(f"broker_codes={c}" for c in broker_codes)
    return (
        f"{cfg.broker_historical_url}?interval=INTERVAL_DAILY"
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
    *,
    stockbit_config: StockbitConfig | None = None,
) -> str:
    """URL for the per-day historical summary endpoint (totals + flow)."""
    cfg = stockbit_config or load_stockbit_config()
    return (
        f"{cfg.historical_summary_url.format(ticker=ticker.upper())}"
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
    *,
    stockbit_config: StockbitConfig | None = None,
) -> str:
    """URL for per-broker per-day flow (broker/activity/historical, single code)."""
    cfg = stockbit_config or load_stockbit_config()
    return (
        f"{cfg.broker_historical_url}"
        f"?broker_codes={broker_code}"
        f"&symbols={ticker.upper()}"
        f"&market_board=BOARD_TYPE_REGULAR"
        f"&investor_type=INVESTOR_TYPE_ALL"
        f"&interval=INTERVAL_DAILY"
        f"&period=RT_PERIOD_LAST_1_YEAR"
        f"&pagination.page={page}"
        f"&pagination.limit={limit}"
    )
