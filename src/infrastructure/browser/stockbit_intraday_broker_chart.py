"""
StockbitIntradayBrokerChartProvider — per-minute broker flow chart from Stockbit.

Calls /order-trade/broker/activity-chart (broker-centric, not ticker-centric) and
returns an IntradayBrokerChart with per-minute cumulative net value per top stock.

Actual API shape (confirmed 2026-06-12, broker XL):
  data.broker_code               → list e.g. ["XL"] (queried broker code)
  data.broker_name               → str (may be empty)
  data.from                      → "2026-06-12" (trading date)
  data.chart_data[]              → list of {type, symbols[], charts[]}
    type "TYPE_CHART_VALUE"      → net buy/sell IDR (use this)
    type "TYPE_CHART_VOLUME"     → net lot volume (not used here)
  data.chart_data[i].charts[]   → [{symbol, chart[]}]
  data.chart_data[i].charts[j].symbol  → "EMAS"
  data.chart_data[i].charts[j].chart[] → [{date, time, value.raw, datetime_label}]
  value.raw is a string — negative for net sellers, e.g. "-395667500"

No caching — real-time intraday data.

Layer: Infrastructure
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from src.domain.ports.intraday_broker_chart_provider import IntradayBrokerChartProvider
from src.domain.value_objects.intraday_broker_chart import (
    IntradayBrokerChart,
    IntradayBrokerChartPoint,
    IntradayBrokerSymbolChart,
)

if TYPE_CHECKING:
    from src.infrastructure.browser.playwright_stockbit import StockbitPlaywrightBrokerProvider

logger = logging.getLogger(__name__)

from src.infrastructure.config.stockbit_config import STOCKBIT_CFG

_CHART_URL = STOCKBIT_CFG.intraday_broker_chart_url


def _parse_chart(broker_code: str, body: dict) -> IntradayBrokerChart | None:
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        return None

    # broker_code in response is a list e.g. ["XL"]
    raw_code = data.get("broker_code")
    if isinstance(raw_code, list):
        response_code = str(raw_code[0]).upper() if raw_code else broker_code.upper()
    else:
        response_code = str(raw_code or broker_code).upper()

    broker_name = str(data.get("broker_name") or "")

    date_str = str(data.get("from") or "")
    try:
        chart_date = date.fromisoformat(date_str[:10])
    except (ValueError, TypeError):
        chart_date = date.today()

    # Find the TYPE_CHART_VALUE section
    value_section: dict | None = None
    for section in data.get("chart_data") or []:
        if isinstance(section, dict) and section.get("type") == "TYPE_CHART_VALUE":
            value_section = section
            break

    if value_section is None:
        return None

    symbol_charts: list[IntradayBrokerSymbolChart] = []
    for entry in value_section.get("charts") or []:
        if not isinstance(entry, dict):
            continue
        symbol = str(entry.get("symbol") or "").upper()
        if not symbol:
            continue
        points: list[IntradayBrokerChartPoint] = []
        for pt in entry.get("chart") or []:
            if not isinstance(pt, dict):
                continue
            time = str(pt.get("time") or pt.get("datetime_label") or "")
            raw_val = (pt.get("value") or {}).get("raw")
            try:
                net_value = Decimal(str(raw_val)) if raw_val is not None else Decimal(0)
            except Exception:
                net_value = Decimal(0)
            points.append(IntradayBrokerChartPoint(time=time, net_value=net_value))
        if points:
            symbol_charts.append(IntradayBrokerSymbolChart(
                symbol=symbol,
                points=tuple(points),
            ))

    if not symbol_charts:
        return None

    return IntradayBrokerChart(
        broker_code=response_code,
        broker_name=broker_name,
        date=chart_date,
        fetched_at=datetime.now(),
        symbols=tuple(symbol_charts),
    )


class StockbitIntradayBrokerChartProvider(IntradayBrokerChartProvider):
    """Fetches per-minute broker flow chart from Stockbit activity-chart endpoint.

    Broker-centric: returns the broker's top stocks and their intraday net flows.
    No caching — data is live intraday.
    """

    def __init__(self, broker_provider: "StockbitPlaywrightBrokerProvider") -> None:
        self._provider = broker_provider

    def fetch_chart(self, broker_code: str) -> IntradayBrokerChart | None:
        try:
            from src.infrastructure.browser.playwright_stockbit import _exodus_get
            token = self._provider._get_token()
            url = _CHART_URL.format(broker_code=broker_code.upper())
            body = _exodus_get(url, token)
            if not body:
                logger.debug("Empty intraday broker chart response for %s", broker_code)
                return None
            result = _parse_chart(broker_code, body)
            if result:
                logger.debug(
                    "IntradayBrokerChart %s → %d symbols (acc=%s, dist=%s)",
                    broker_code,
                    len(result.symbols),
                    result.accumulating_symbols,
                    result.distributing_symbols,
                )
            return result
        except Exception as e:
            logger.warning("Intraday broker chart fetch failed for %s: %s", broker_code, e)
            return None
