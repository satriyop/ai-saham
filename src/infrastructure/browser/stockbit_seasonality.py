"""
StockbitSeasonalityProvider — monthly seasonality data from Stockbit Exodus API.

Calls /company-price-feed/seasonality/{ticker}?year={year}&back_year={back_years}
and extracts the avg monthly return and win-rate for the requested month.

Caching: in-memory per (ticker, year, month) — data is static within a month,
so SQLite is overkill. Cache survives the process lifetime (one CLI run).

Token: Reuses RS256 Bearer token from StockbitPlaywrightBrokerProvider._get_token().

Layer: Infrastructure
Depends on: playwright_stockbit (for token), SeasonalityProvider port
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.domain.ports.seasonality_provider import SeasonalityProvider
from src.domain.value_objects.seasonal_edge import SeasonalEdge

if TYPE_CHECKING:
    from src.infrastructure.browser.playwright_stockbit import StockbitPlaywrightBrokerProvider

logger = logging.getLogger(__name__)

_SEASONALITY_URL = (
    "https://exodus.stockbit.com/company-price-feed/seasonality/{ticker}"
    "?year={year}&back_year={back_years}"
)

# Stockbit uses abbreviated English month names as column keys
_MONTH_TO_NAME = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


def _col_value(section: dict, month_name: str) -> str | None:
    """Extract the value for a named column from a {columns: [{name, value}]} section."""
    for col in section.get("columns", []):
        if col.get("name") == month_name:
            return col.get("value")
    return None


def _parse_seasonality(ticker: str, month: int, back_years: int, body: dict) -> SeasonalEdge | None:
    """Parse /seasonality/{ticker} response for one target month.

    Actual Stockbit Exodus response shape (confirmed 2026-06):
      data.avg.columns[]         — [{name: "Jun", value: "0.87"}]  avg return %
      data.prob.columns[]        — [{name: "Jun", value: "60"}]    win rate %
      data.up.columns[]          — [{name: "Jun", value: "3"}]     positive years
      data.total_months.columns[]— [{name: "Jun", value: "5"}]     total years
      data.default_last_year     — int, number of back years used
    """
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        logger.debug("Unexpected seasonality response shape for %s", ticker)
        return None

    month_name = _MONTH_TO_NAME.get(month)
    if not month_name:
        return None

    avg_section = data.get("avg", {})
    prob_section = data.get("prob", {})
    up_section = data.get("up", {})
    total_section = data.get("total_months", {})

    raw_avg = _col_value(avg_section, month_name)
    raw_prob = _col_value(prob_section, month_name)
    raw_up = _col_value(up_section, month_name)
    raw_total = _col_value(total_section, month_name)

    try:
        avg_return = float(raw_avg)
    except (TypeError, ValueError):
        logger.debug("No avg return for %s month=%d", ticker, month)
        return None

    try:
        win_rate = float(raw_prob)
    except (TypeError, ValueError):
        win_rate = 0.0

    try:
        positive_years = int(raw_up)
    except (TypeError, ValueError):
        positive_years = round(win_rate / 100.0 * back_years)

    try:
        total_years = int(raw_total)
    except (TypeError, ValueError):
        total_years = data.get("default_last_year", back_years)

    return SeasonalEdge(
        ticker=ticker.upper(),
        month=month,
        avg_monthly_return_pct=round(avg_return, 2),
        win_rate_pct=round(win_rate, 1),
        positive_years=positive_years,
        total_years=total_years,
        back_years=back_years,
        source="stockbit",
    )


class StockbitSeasonalityProvider(SeasonalityProvider):
    """
    Fetches monthly seasonality from Stockbit.

    Uses in-memory cache keyed by (ticker, year, month) — static within a
    CLI session since seasonality data only changes when the month rolls over.

    Args:
        broker_provider: Authenticated StockbitPlaywrightBrokerProvider for token access.
    """

    def __init__(self, broker_provider: "StockbitPlaywrightBrokerProvider") -> None:
        self._provider = broker_provider
        self._cache: dict[tuple[str, int, int], SeasonalEdge | None] = {}

    def get_seasonal_edge(
        self,
        ticker: str,
        year: int,
        month: int,
        back_years: int = 5,
    ) -> SeasonalEdge | None:
        """Return SeasonalEdge for ticker in given year/month, using in-memory cache."""
        key = (ticker.upper(), year, month)
        if key in self._cache:
            return self._cache[key]

        result = self._fetch(ticker, year, month, back_years)
        self._cache[key] = result
        return result

    def _fetch(self, ticker: str, year: int, month: int, back_years: int) -> SeasonalEdge | None:
        try:
            from src.infrastructure.browser.playwright_stockbit import _exodus_get
            token = self._provider._get_token()
            url = _SEASONALITY_URL.format(
                ticker=ticker.upper(),
                year=year,
                back_years=back_years,
            )
            body = _exodus_get(url, token)
            if not body:
                logger.debug("Empty seasonality response for %s", ticker)
                return None
            edge = _parse_seasonality(ticker, month, back_years, body)
            if edge:
                logger.debug("Seasonality %s month=%d → %s", ticker, month, edge.label)
            return edge
        except Exception as e:
            logger.warning("Seasonality fetch failed for %s: %s", ticker, e)
            return None
