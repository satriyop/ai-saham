"""
Stockbit broker/foreign-flow data provider.

BrokerDataProvider implementation backed entirely by StockbitApiClient — no
Playwright dependency (per ADR-036, Playwright is retained only for
interactive commands and the on-401 token refresh helper, neither of which
this provider touches).

Extracted from playwright_stockbit_provider.py.

Layer: Infrastructure
Depends on: StockbitApiClient, BrokerDataProvider port
"""

from __future__ import annotations

import logging
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.domain.entities.broker_flow import (
    BrokerDailyFlow,
    BrokerSummary,
    ForeignFlowPoint,
    ForeignFlowSnapshot,
)
from src.domain.ports.broker_data_provider import BrokerDataProvider
from src.infrastructure.browser.stockbit_api_client import StockbitApiClient
from src.infrastructure.browser.stockbit_broker_parsers import (
    _dict_dec,
    _dict_int,
    _parse_foreign_flow_history,
    _parse_foreign_top_stocks,
    _parse_historical_summary_flow,
    _parse_marketdetectors_response,
)
from src.infrastructure.browser.stockbit_browser_context import DEFAULT_PROFILE_DIR
from src.infrastructure.config.stockbit_config import STOCKBIT_CFG

logger = logging.getLogger(__name__)

# ── Stockbit API config — driven by config/stockbit.yaml ─────────────────
_sb = STOCKBIT_CFG

_MARKETDETECTORS_API   = _sb.marketdetectors_url
_BROKER_ACTIVITY_API   = _sb.broker_activity_url
_BROKER_HISTORICAL_API  = _sb.broker_historical_url
_HISTORICAL_SUMMARY_API = _sb.historical_summary_url
_INSTITUTIONAL_PROXY_CODES = list(_sb.institutional_proxy_codes)
TRACKED_BROKER_CODES       = list(_sb.tracked_broker_codes)


# ── API-client-backed BrokerDataProvider ──────────────────────────────────

class StockbitBrokerProvider(BrokerDataProvider):
    """
    BrokerDataProvider backed by StockbitApiClient (no Playwright needed for data).

    Replaces StockbitPlaywrightBrokerProvider.

    Usage:
        from src.infrastructure.browser.stockbit_api_client import create_stockbit_api_client
        api_client = create_stockbit_api_client()
        provider = StockbitBrokerProvider(api_client=api_client)
        summaries = provider.fetch_broker_summaries("BBCA", date(2026,1,1), date.today())
    """

    def __init__(
        self,
        api_client: StockbitApiClient,
        profile_dir: Path = DEFAULT_PROFILE_DIR,
    ) -> None:
        self._api_client = api_client
        self._profile_dir = profile_dir

    @property
    def provider_name(self) -> str:
        return "stockbit"

    @property
    def api_client(self) -> StockbitApiClient:
        return self._api_client

    def is_authenticated(self) -> bool:
        """True if a persistent profile exists and its login marker is < 72h old."""
        marker = self._profile_dir / ".logged_in_at"
        if not (self._profile_dir.exists() and marker.exists()):
            return False
        try:
            age_hours = (time.time() - float(marker.read_text())) / 3600
            return age_hours < 72
        except Exception:
            return False

    def fetch_broker_summary(
        self,
        ticker: str,
        target_date: date,
    ) -> BrokerSummary | None:
        summaries = self.fetch_broker_summaries(ticker, target_date, target_date)
        return summaries[0] if summaries else None

    def fetch_broker_summaries(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[BrokerSummary]:
        """
        Fetch named broker breakdown for a specific ticker via marketdetectors endpoint.

        Uses the stock-centric Exodus API (confirmed 2026-06-13) which returns
        which named brokers bought/sold the stock in the requested period.
        Maps the date range to the closest supported period parameter.
        """
        days = (end_date - start_date).days
        # All confirmed valid as of 2026-06-13
        if days <= 1:
            period = "BROKER_SUMMARY_PERIOD_LATEST"
        elif days <= 7:
            period = "BROKER_SUMMARY_PERIOD_LAST_7_DAYS"
        elif days <= 30:
            period = "BROKER_SUMMARY_PERIOD_LAST_1_MONTH"
        elif days <= 90:
            period = "BROKER_SUMMARY_PERIOD_LAST_3_MONTHS"
        elif days <= 180:
            period = "BROKER_SUMMARY_PERIOD_LAST_6_MONTHS"
        else:
            period = "BROKER_SUMMARY_PERIOD_LAST_1_YEAR"
        url = (
            f"{_MARKETDETECTORS_API}/{ticker.upper()}"
            f"?transaction_type=TRANSACTION_TYPE_NET"
            f"&market_board=MARKET_BOARD_REGULER"
            f"&investor_type=INVESTOR_TYPE_ALL"
            f"&limit=25"
            f"&period={period}"
        )
        body = self._api_client.get(url)
        if not body:
            logger.warning(
                "No broker data for %s (%s–%s). "
                "Run: saham fetch stockbit spy --target stock --ticker %s",
                ticker, start_date, end_date, ticker,
            )
            return []

        real_total = _fetch_historical_summary_totals(
            ticker, start_date, end_date, self._api_client
        )
        if real_total is None:
            logger.warning(
                "fetch_broker_summaries/%s: historical/summary unavailable, "
                "total_value will be synthetic (top-broker subset only)",
                ticker,
            )
        summaries = _parse_marketdetectors_response(ticker, end_date, body, real_total=real_total)
        if summaries:
            logger.info("Stockbit named broker data: %s → %d entry", ticker, len(summaries))
        else:
            logger.debug(
                "marketdetectors/%s returned data but no parseable broker rows. "
                "Run spy to inspect the response shape.",
                ticker,
            )
        return summaries

    def fetch_foreign_top_stocks(
        self,
        start_date: date,
        end_date: date,
        limit: int = 20,
    ) -> list[ForeignFlowSnapshot]:
        """
        Return stocks most actively traded by foreign brokers in the period.

        Uses the broker-centric Exodus API: given the 10 known foreign broker codes,
        returns which stocks they collectively bought/sold the most. Useful for
        universe-level screening ("is this IEV mover in foreign top buys?").
        """
        days = (end_date - start_date).days
        # Confirmed valid periods (2026-06-13): 1D, 3D, 7D, 1M, 3M, 1Y
        # LAST_1_WEEK and LAST_6_MONTHS are not valid values
        if days <= 1:
            period = "RT_PERIOD_LAST_1_DAY"
        elif days <= 3:
            period = "RT_PERIOD_LAST_3_DAYS"
        elif days <= 7:
            period = "RT_PERIOD_LAST_7_DAYS"
        elif days <= 30:
            period = "RT_PERIOD_LAST_1_MONTH"
        elif days <= 90:
            period = "RT_PERIOD_LAST_3_MONTHS"
        else:
            period = "RT_PERIOD_LAST_1_YEAR"
        broker_params = "&".join(f"broker_code={c}" for c in _INSTITUTIONAL_PROXY_CODES)
        url = (
            f"{_BROKER_ACTIVITY_API}?{broker_params}"
            f"&transaction_type=TRANSACTION_TYPE_NET"
            f"&investor_type=INVESTOR_TYPE_ALL"
            f"&limit={limit}&market_board=MARKET_TYPE_REGULER&page=1"
            f"&period={period}"
            f"&net_val_period=NET_VAL_PERIOD_7D"
        )
        body = self._api_client.get(url)
        if not body:
            logger.warning("No response from broker-centric scan endpoint")
            return []
        snapshots = _parse_foreign_top_stocks(end_date, body)
        logger.info("Foreign top stocks scan: %d stocks returned", len(snapshots))
        return snapshots

    def fetch_foreign_flow_history(
        self,
        ticker: str,
        days: int = 365,
    ) -> list[ForeignFlowPoint]:
        """
        Return daily foreign broker flow for a stock, up to `days` back.

        Uses the stock-centric historical Exodus API. Returns daily N.Val/N.Lot
        time-series for trend context and backfilling the foreign-flow table.
        """
        codes_params = "&".join(f"broker_codes={c}" for c in _INSTITUTIONAL_PROXY_CODES)
        url = (
            f"{_BROKER_HISTORICAL_API}?interval=INTERVAL_DAILY"
            f"&period=RT_PERIOD_LAST_1_YEAR"
            f"&{codes_params}"
            f"&symbols={ticker.upper()}"
            f"&market_board=BOARD_TYPE_REGULAR"
            f"&investor_type=INVESTOR_TYPE_ALL"
            f"&pagination.page=1&pagination.limit={min(days, 365)}"
        )
        body = self._api_client.get(url)
        if not body:
            logger.debug("No response from foreign flow history endpoint for %s", ticker)
            return []
        points = _parse_foreign_flow_history(ticker, body)
        logger.info("Foreign flow history: %s → %d data points", ticker, len(points))
        return points

    def fetch_foreign_flow_from_summary(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[ForeignFlowPoint]:
        """
        Fetch per-day foreign flow from the historical summary endpoint.

        One API call vs. many calls on the broker/activity/historical path.
        Use for bulk date-range backfills; reserve broker/activity/historical for
        per-broker detail or when you need net_lot accuracy.
        """
        all_points: list[ForeignFlowPoint] = []
        page = 1
        try:
            while True:
                url = (
                    f"{_HISTORICAL_SUMMARY_API.format(ticker=ticker.upper())}"
                    f"?period=HS_PERIOD_DAILY"
                    f"&start_date={start_date.isoformat()}"
                    f"&end_date={end_date.isoformat()}"
                    f"&limit=50&page={page}"
                )
                body = self._api_client.get(url)
                if not body:
                    break
                rows = (body.get("data") or {}).get("result") or []
                if not rows:
                    break

                points = _parse_historical_summary_flow(ticker, body)
                all_points.extend(points)

                if len(rows) < 50:
                    break
                page += 1

            return sorted(all_points, key=lambda p: p.date)
        except Exception as e:
            logger.warning("fetch_foreign_flow_from_summary %s failed: %s", ticker, e)
            return []

    def fetch_broker_daily_flows(
        self,
        ticker: str,
        broker_codes: list[str] | None = None,
        days: int = 365,
    ) -> list[BrokerDailyFlow]:
        """
        Fetch real per-day per-broker flow for a stock.

        Calls /order-trade/broker/activity/historical once per broker code with
        pagination (max 100 records/page). Returns one BrokerDailyFlow per
        (date, broker_code) — never an aggregate.

        Args:
            ticker: Stock ticker symbol.
            broker_codes: Which broker codes to fetch. Defaults to TRACKED_BROKER_CODES.
            days: Max calendar days to look back (capped at 365 by the API).
        """
        codes = broker_codes if broker_codes is not None else TRACKED_BROKER_CODES
        all_flows: list[BrokerDailyFlow] = []

        for code in codes:
            flows = _fetch_broker_daily_flows_for_code(self._api_client, ticker, code, days)
            all_flows.extend(flows)
            logger.debug(
                "fetch_broker_daily_flows: %s/%s → %d records", ticker, code, len(flows)
            )

        logger.info(
            "fetch_broker_daily_flows: %s → %d total records across %d codes",
            ticker, len(all_flows), len(codes),
        )
        return all_flows


def _fetch_broker_daily_flows_for_code(
    api_client: StockbitApiClient,
    ticker: str,
    broker_code: str,
    days: int,
) -> list[BrokerDailyFlow]:
    """
    Fetch all daily flow records for one broker code on one ticker, with pagination.

    The API caps at 100 records per page (confirmed 2026-06-14). Uses has_next
    to determine when to stop. Stops early if the oldest returned date is older
    than `days` back from today.
    """
    from datetime import date as date_type
    from datetime import timedelta

    cutoff = date_type.today() - timedelta(days=days)
    page = 1
    results: list[BrokerDailyFlow] = []
    broker_name = broker_code  # default; overwritten from first response

    while True:
        url = (
            f"{_BROKER_HISTORICAL_API}"
            f"?broker_codes={broker_code}"
            f"&symbols={ticker.upper()}"
            f"&market_board=BOARD_TYPE_REGULAR"
            f"&investor_type=INVESTOR_TYPE_ALL"
            f"&interval=INTERVAL_DAILY"
            f"&period=RT_PERIOD_LAST_1_YEAR"
            f"&pagination.page={page}"
            f"&pagination.limit=100"
        )
        body = api_client.get(url)
        if not body:
            break

        data = body.get("data") or {}
        # broker_name is only present when a single code is requested
        if data.get("broker_name"):
            broker_name = data["broker_name"]

        records = data.get("records") or []
        if not records:
            break

        for item in records:
            if not isinstance(item, dict):
                continue
            date_str = str(item.get("date") or "")
            try:
                flow_date = date_type.fromisoformat(date_str[:10])
            except (ValueError, TypeError):
                continue

            if flow_date < cutoff:
                return results  # older than requested window — stop paginating

            trade = item.get("trade_activity") or {}
            buy = trade.get("buy_summary") or {}
            sell = trade.get("sell_summary") or {}
            net = trade.get("net_summary") or {}
            total_buy = trade.get("total_buy_lot") or {}
            total_sell = trade.get("total_sell_lot") or {}

            buy_lot = _dict_int(buy, "lot") or 0
            sell_lot = _dict_int(sell, "lot") or 0
            net_lot = _dict_int(net, "lot") or 0
            buy_value = _dict_dec(buy, "value")
            sell_value = _dict_dec(sell, "value")
            net_value = _dict_dec(net, "value")
            avg_buy_price = _dict_dec(buy, "avg_price")
            avg_sell_price = _dict_dec(sell, "avg_price")
            avg_price = _dict_dec(net, "avg_price")

            try:
                results.append(BrokerDailyFlow(
                    ticker=ticker.upper(),
                    date=flow_date,
                    broker_code=broker_code.upper(),
                    broker_name=broker_name,
                    source="stockbit",
                    buy_lot=abs(buy_lot),
                    sell_lot=abs(sell_lot),
                    net_lot=net_lot,
                    buy_value=abs(buy_value),
                    sell_value=abs(sell_value),
                    net_value=net_value,
                    avg_buy_price=avg_buy_price,
                    avg_sell_price=avg_sell_price,
                    avg_price=avg_price,
                    buy_pct=float(total_buy.get("pct") or 0),
                    sell_pct=float(total_sell.get("pct") or 0),
                ))
            except Exception as e:
                logger.debug("Could not parse BrokerDailyFlow %s/%s %s: %s",
                             ticker, broker_code, date_str, e)

        pagination = data.get("pagination") or {}
        if not pagination.get("has_next"):
            break
        page += 1

    return results


def _fetch_historical_summary_totals(
    ticker: str,
    start_date: date,
    end_date: date,
    api_client: StockbitApiClient,
) -> tuple[Decimal, int] | None:
    """
    Return (total_value_IDR, total_lot) from /company-price-feed/historical/summary/{ticker}.

    Sums all daily rows in [start_date, end_date]. Returns None on any failure so
    the caller can fall back to the synthetic marketdetectors total.

    Confirmed response shape (live probe 2026-06-20):
      data.result[].value  → total traded value (IDR, int)
      data.result[].volume → total traded lots (int, already in lots — NOT shares)
    """
    total_value = Decimal("0")
    total_lot = 0
    page = 1
    has_rows = False

    try:
        while True:
            url = (
                f"{_HISTORICAL_SUMMARY_API.format(ticker=ticker.upper())}"
                f"?period=HS_PERIOD_DAILY"
                f"&start_date={start_date.isoformat()}"
                f"&end_date={end_date.isoformat()}"
                f"&limit=50&page={page}"
            )
            body = api_client.get(url)
            if not body:
                break
            rows = (body.get("data") or {}).get("result") or []
            if not rows:
                break
            has_rows = True
            for r in rows:
                if isinstance(r, dict):
                    total_value += Decimal(str(r.get("value") or 0))
                    total_lot += int(r.get("volume") or 0)
            if len(rows) < 50:
                break
            page += 1

        if not has_rows or total_value <= 0:
            return None
        return total_value, total_lot
    except Exception as e:
        logger.debug("historical/summary totals failed for %s: %s", ticker, e)
        return None
