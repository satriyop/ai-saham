"""
StockbitRunningTradeChartProvider — per-minute intraday chart from Stockbit.

Calls /order-trade/running-trade/chart/{ticker} and returns a RunningTradeChart
with minute-level OHLC price bars and top-broker cumulative net value lines.

Actual API shape (confirmed 2026-06-20, BBCA):
  data.from                          → "2026-06-19" (trading date)
  data.price_chart_data[].time       → "09:00" (minute HH:MM)
  data.price_chart_data[].value.raw  → "6175" (close price, string)
  data.price_chart_data[].open.raw   → "6075" (string or null)
  data.price_chart_data[].high.raw   → "6175" (string or null)
  data.price_chart_data[].low.raw    → "6050" (string or null)
  data.broker_chart_data[].charts[].broker_code → "XL"
  data.broker_chart_data[].charts[].chart[].time        → "09:00"
  data.broker_chart_data[].charts[].chart[].value.raw   → "4996225000" (IDR, string)

No caching — this is real-time intraday data. Callers decide re-fetch frequency.

Layer: Infrastructure
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from src.domain.ports.running_trade_chart_provider import RunningTradeChartProvider
from src.domain.value_objects.running_trade_chart import (
    IntradayBrokerBar,
    IntradayPriceBar,
    RunningTradeChart,
)

if TYPE_CHECKING:
    from src.infrastructure.browser.playwright_stockbit import StockbitPlaywrightBrokerProvider

logger = logging.getLogger(__name__)

from src.infrastructure.config.stockbit_config import STOCKBIT_CFG

_CHART_URL = STOCKBIT_CFG.running_trade_chart_url


def _raw_int(obj: dict | None, key: str = "raw") -> int | None:
    if not isinstance(obj, dict):
        return None
    raw = obj.get(key)
    try:
        return int(str(raw).replace(",", "")) if raw is not None else None
    except (ValueError, TypeError):
        return None


def _parse_chart(ticker: str, body: dict) -> RunningTradeChart | None:
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        return None

    date_str = str(data.get("from") or "")
    try:
        chart_date = date.fromisoformat(date_str[:10])
    except (ValueError, TypeError):
        chart_date = date.today()

    # Price bars
    price_bars: list[IntradayPriceBar] = []
    for bar in data.get("price_chart_data") or []:
        if not isinstance(bar, dict):
            continue
        time = str(bar.get("time") or bar.get("datetime_label") or "")
        close = _raw_int(bar.get("value"))
        if close is None:
            continue
        price_bars.append(IntradayPriceBar(
            time=time,
            close=close,
            open=_raw_int(bar.get("open")),
            high=_raw_int(bar.get("high")),
            low=_raw_int(bar.get("low")),
        ))

    # Broker bars — flatten all brokers from all chart_data sections
    broker_bars: list[IntradayBrokerBar] = []
    for section in data.get("broker_chart_data") or []:
        if not isinstance(section, dict):
            continue
        for chart_entry in section.get("charts") or []:
            if not isinstance(chart_entry, dict):
                continue
            broker_code = str(chart_entry.get("broker_code") or "").upper()
            if not broker_code:
                continue
            for pt in chart_entry.get("chart") or []:
                if not isinstance(pt, dict):
                    continue
                time = str(pt.get("time") or pt.get("datetime_label") or "")
                raw_val = (pt.get("value") or {}).get("raw")
                try:
                    net_value = Decimal(str(raw_val)) if raw_val is not None else Decimal(0)
                except Exception:
                    net_value = Decimal(0)
                broker_bars.append(IntradayBrokerBar(
                    broker_code=broker_code,
                    time=time,
                    net_value=net_value,
                ))

    if not price_bars:
        return None

    return RunningTradeChart(
        ticker=ticker.upper(),
        date=chart_date,
        fetched_at=datetime.now(),
        price_bars=tuple(price_bars),
        broker_bars=tuple(sorted(broker_bars, key=lambda b: (b.broker_code, b.time))),
    )


class StockbitRunningTradeChartProvider(RunningTradeChartProvider):
    """Fetches per-minute intraday chart from Stockbit running-trade endpoint.

    No caching — data is live intraday. Callers are responsible for re-fetch timing.
    """

    def __init__(self, broker_provider: "StockbitPlaywrightBrokerProvider") -> None:
        self._provider = broker_provider

    def fetch_chart(self, ticker: str) -> RunningTradeChart | None:
        try:
            from src.infrastructure.browser.playwright_stockbit import _exodus_get
            token = self._provider._get_token()
            url = _CHART_URL.format(ticker=ticker.upper())
            body = _exodus_get(url, token)
            if not body:
                logger.debug("Empty running trade chart response for %s", ticker)
                return None
            result = _parse_chart(ticker, body)
            if result:
                logger.debug(
                    "RunningTradeChart %s → %d price bars, brokers=%s",
                    ticker,
                    len(result.price_bars),
                    result.top_broker_codes,
                )
            return result
        except Exception as e:
            logger.warning("Running trade chart fetch failed for %s: %s", ticker, e)
            return None
