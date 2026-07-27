"""
Pure parsers for Stockbit broker/foreign-flow JSON payloads.

Extracted from playwright_stockbit_provider.py. These functions do no network,
browser, DB, or token-store I/O — they only transform already-fetched response
bodies into domain entities.

Layer: Infrastructure
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from src.domain.entities.broker_flow import (
    BrokerSummary,
    BrokerTransaction,
    BrokerType,
    ForeignFlowPoint,
    ForeignFlowSnapshot,
)

logger = logging.getLogger(__name__)


def _dict_int(d: dict | None, *keys: str) -> int:
    """Extract an integer from a dict, trying multiple key names."""
    for k in keys:
        v = (d or {}).get(k)
        if v is not None:
            try:
                return int(float(str(v)))
            except (ValueError, TypeError):
                pass
    return 0


def _dict_dec(d: dict | None, *keys: str) -> Decimal:
    """Extract a Decimal from a dict, trying multiple key names."""
    for k in keys:
        v = (d or {}).get(k)
        if v is not None:
            try:
                return Decimal(str(v))
            except Exception:
                pass
    return Decimal("0")


def _parse_broker_tx(item: dict) -> BrokerTransaction | None:
    """
    Parse a single named-broker row from a marketdetectors response item.

    Handles two common shapes:
      Shape A (nested):  item.buy.lot / item.sell.lot
      Shape B (flat):    item.buy_lot / item.sell_lot
    """
    broker_node = item.get("broker") or {}
    code = broker_node.get("code") or item.get("broker_code") or item.get("code") or ""
    name = broker_node.get("name") or item.get("broker_name") or item.get("name") or code
    if not code:
        return None

    inv_type = (item.get("investor_type") or "").upper()
    if "FOREIGN" in inv_type or "ASING" in inv_type:
        broker_type = BrokerType.FOREIGN
    elif "LOCAL" in inv_type or "LOKAL" in inv_type or "DOMESTIC" in inv_type:
        broker_type = BrokerType.LOCAL
    else:
        broker_type = BrokerType.UNKNOWN

    buy_node = item.get("buy") or {}
    sell_node = item.get("sell") or {}

    buy_lot = _dict_int(buy_node, "lot", "lots") or _dict_int(item, "buy_lot")
    sell_lot = _dict_int(sell_node, "lot", "lots") or _dict_int(item, "sell_lot")
    buy_val = _dict_dec(buy_node, "value") or _dict_dec(item, "buy_value")
    sell_val = _dict_dec(sell_node, "value") or _dict_dec(item, "sell_value")
    avg_buy = _dict_dec(buy_node, "avg_price", "avg") or _dict_dec(item, "avg_buy_price")
    avg_sell = _dict_dec(sell_node, "avg_price", "avg") or _dict_dec(item, "avg_sell_price")

    try:
        return BrokerTransaction(
            broker_code=str(code).upper(),
            broker_name=str(name),
            broker_type=broker_type,
            buy_lot=abs(buy_lot),
            sell_lot=abs(sell_lot),
            buy_value=abs(buy_val),
            sell_value=abs(sell_val),
            avg_buy_price=avg_buy,
            avg_sell_price=avg_sell,
        )
    except Exception as e:
        logger.debug("Could not parse broker tx %s: %s", code, e)
        return None


def _parse_historical_summary_flow(
    ticker: str,
    body: dict,
) -> list[ForeignFlowPoint]:
    """
    Extract per-day ForeignFlowPoint from /company-price-feed/historical/summary response.

    Confirmed response shape (2026-06-20):
      data.result[].date         → "YYYY-MM-DD"
      data.result[].foreign_buy  → int IDR
      data.result[].foreign_sell → int IDR
      data.result[].net_foreign  → int IDR
      data.result[].volume       → int lots (total volume, used as proxy for net_lot)
      data.result[].close        → float (close price)
    """
    rows = (body.get("data") or {}).get("result") or []
    points: list[ForeignFlowPoint] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            d = date.fromisoformat(str(row.get("date") or "")[:10])
        except (ValueError, TypeError):
            continue
        net_val = Decimal(str(row.get("net_foreign") or 0))
        net_lot = int(row.get("volume") or 0)
        close_price = Decimal(str(row.get("close") or 0))
        points.append(
            ForeignFlowPoint(
                ticker=ticker.upper(),
                date=d,
                net_val=net_val,
                net_lot=net_lot,
                avg_price=close_price,
                source="stockbit_summary",
            )
        )
    return sorted(points, key=lambda p: p.date)


def _parse_marketdetectors_response(
    ticker: str,
    trading_date: date,
    body: dict,
    real_total: tuple[Decimal, int] | None = None,
) -> list[BrokerSummary]:
    """
    Parse the stock-centric /marketdetectors/{ticker} response into a BrokerSummary.

    Confirmed response shape (2026-06-13):
      data.broker_summary.brokers_buy[]  — net buyer rows
        netbs_broker_code, blot, bval, netbs_buy_avg_price, type, netbs_date (YYYYMMDD)
      data.broker_summary.brokers_sell[] — net seller rows
        netbs_broker_code, slot (neg), sval (neg), netbs_sell_avg_price, type
    """
    data = body.get("data") if isinstance(body, dict) else body
    if not isinstance(data, dict):
        return []

    broker_summary = data.get("broker_summary") or {}
    if not isinstance(broker_summary, dict):
        return []

    buy_items: list = broker_summary.get("brokers_buy") or []
    sell_items: list = broker_summary.get("brokers_sell") or []

    if not buy_items and not sell_items:
        logger.debug("marketdetectors/%s: no brokers_buy/brokers_sell in response", ticker)
        return []

    def _broker_type(item: dict) -> BrokerType:
        return BrokerType.FOREIGN if item.get("type") == "Asing" else BrokerType.LOCAL

    def _parse_yyyymmdd(s: str) -> date:
        """Parse YYYYMMDD date string."""
        s = str(s or "").strip()
        if len(s) == 8:
            try:
                return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
            except (ValueError, TypeError):
                pass
        return trading_date

    buyers: list[BrokerTransaction] = []
    for item in buy_items:
        if not isinstance(item, dict):
            continue
        code = str(item.get("netbs_broker_code") or "").strip()
        if not code:
            continue
        try:
            buyers.append(
                BrokerTransaction(
                    broker_code=code,
                    broker_name=code,
                    broker_type=_broker_type(item),
                    buy_lot=abs(_dict_int(item, "blot")),
                    sell_lot=0,
                    buy_value=abs(_dict_dec(item, "bval")),
                    sell_value=Decimal("0"),
                    avg_buy_price=_dict_dec(item, "netbs_buy_avg_price"),
                    avg_sell_price=Decimal("0"),
                )
            )
        except Exception as e:
            logger.debug("Could not parse buy broker %s: %s", code, e)

    sellers: list[BrokerTransaction] = []
    for item in sell_items:
        if not isinstance(item, dict):
            continue
        code = str(item.get("netbs_broker_code") or "").strip()
        if not code:
            continue
        try:
            sellers.append(
                BrokerTransaction(
                    broker_code=code,
                    broker_name=code,
                    broker_type=_broker_type(item),
                    buy_lot=0,
                    sell_lot=abs(_dict_int(item, "slot")),
                    buy_value=Decimal("0"),
                    sell_value=abs(_dict_dec(item, "sval")),
                    avg_buy_price=Decimal("0"),
                    avg_sell_price=_dict_dec(item, "netbs_sell_avg_price"),
                )
            )
        except Exception as e:
            logger.debug("Could not parse sell broker %s: %s", code, e)

    if not buyers and not sellers:
        return []

    # Actual trading date from first item (YYYYMMDD field)
    first_item = buy_items[0] if buy_items else sell_items[0]
    actual_date = _parse_yyyymmdd(first_item.get("netbs_date", ""))

    all_txns = buyers + sellers
    foreign_txns = [t for t in all_txns if t.is_foreign]

    foreign_buy_val = sum((t.buy_value for t in foreign_txns), Decimal("0"))
    foreign_sell_val = sum((t.sell_value for t in foreign_txns), Decimal("0"))
    foreign_buy_lot = sum(t.buy_lot for t in foreign_txns)
    foreign_sell_lot = sum(t.sell_lot for t in foreign_txns)

    if real_total is not None:
        total_val, total_lot = real_total
    else:
        total_val = sum((t.buy_value + t.sell_value for t in all_txns), Decimal("0"))
        total_lot = sum(t.buy_lot + t.sell_lot for t in all_txns)
        logger.warning(
            "marketdetectors/%s: using synthetic total_value (historical/summary unavailable)",
            ticker,
        )

    try:
        return [
            BrokerSummary(
                ticker=ticker.upper(),
                date=actual_date,
                top_buyers=tuple(buyers[:10]),
                top_sellers=tuple(sellers[:10]),
                foreign_buy_value=foreign_buy_val,
                foreign_sell_value=foreign_sell_val,
                foreign_buy_lot=foreign_buy_lot,
                foreign_sell_lot=foreign_sell_lot,
                total_value=total_val,
                total_lot=total_lot,
                source="stockbit",
            )
        ]
    except Exception as e:
        logger.debug("Could not build BrokerSummary for %s: %s", ticker, e)
        return []


def _parse_nval_trend(ticker: str, trend_raw: list) -> tuple[ForeignFlowPoint, ...]:
    """Parse nval_trend[] array embedded in broker activity universe scan items."""
    points: list[ForeignFlowPoint] = []
    for row in trend_raw or []:
        if not isinstance(row, dict):
            continue
        try:
            d = date.fromisoformat(str(row.get("date") or "")[:10])
            net_val = Decimal(str(row.get("nval") or 0))
            net_lot = int(row.get("nvol") or 0)
            points.append(
                ForeignFlowPoint(
                    ticker=ticker,
                    date=d,
                    net_val=net_val,
                    net_lot=net_lot,
                    avg_price=Decimal(str(row.get("close") or 0)),
                    source="stockbit_trend",
                )
            )
        except Exception:
            pass
    return tuple(sorted(points, key=lambda p: p.date))


def _parse_foreign_top_stocks(
    snapshot_date: date,
    body: dict,
) -> list[ForeignFlowSnapshot]:
    """
    Parse the broker-centric /order-trade/broker/activity response.

    Confirmed response shape (2026-06-13):
      data.broker_activity_transaction.brokers_buy[]  — net buyer stocks
        stock_code, value (net val), lot, avg_price, type, nval_trend[]
      data.broker_activity_transaction.brokers_sell[] — net seller stocks
        stock_code, value (negative), lot (negative), avg_price, type, nval_trend[]
    """
    data = body.get("data") if isinstance(body, dict) else body
    if not isinstance(data, dict):
        return []

    txn = data.get("broker_activity_transaction") or {}
    if not isinstance(txn, dict):
        logger.debug("_parse_foreign_top_stocks: no broker_activity_transaction in response")
        return []

    buy_items: list = txn.get("brokers_buy") or []
    sell_items: list = txn.get("brokers_sell") or []

    snapshots: list[ForeignFlowSnapshot] = []
    seen: set[str] = set()

    for item in buy_items:
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("stock_code") or "").upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        try:
            net_val = _dict_dec(item, "value")
            net_lot = _dict_int(item, "lot")
            item_date_str = str(item.get("date") or "")
            try:
                item_date = date.fromisoformat(item_date_str[:10])
            except (ValueError, TypeError):
                item_date = snapshot_date
            nval_trend = _parse_nval_trend(ticker, item.get("nval_trend") or [])
            snapshots.append(
                ForeignFlowSnapshot(
                    ticker=ticker,
                    date=item_date,
                    net_val=net_val,
                    net_lot=net_lot,
                    nval_trend=nval_trend,
                )
            )
        except Exception as e:
            logger.debug("Could not parse foreign flow snapshot for %s: %s", ticker, e)

    for item in sell_items:
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("stock_code") or "").upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        try:
            # sell values are negative in the response
            net_val = _dict_dec(item, "value")
            net_lot = _dict_int(item, "lot")
            item_date_str = str(item.get("date") or "")
            try:
                item_date = date.fromisoformat(item_date_str[:10])
            except (ValueError, TypeError):
                item_date = snapshot_date
            nval_trend = _parse_nval_trend(ticker, item.get("nval_trend") or [])
            snapshots.append(
                ForeignFlowSnapshot(
                    ticker=ticker,
                    date=item_date,
                    net_val=net_val,
                    net_lot=net_lot,
                    nval_trend=nval_trend,
                )
            )
        except Exception as e:
            logger.debug("Could not parse foreign flow snapshot for %s: %s", ticker, e)

    return sorted(snapshots, key=lambda s: abs(s.net_val), reverse=True)


def _parse_foreign_flow_history(
    ticker: str,
    body: dict,
) -> list[ForeignFlowPoint]:
    """
    Parse the stock-centric /order-trade/broker/activity/historical response.

    Confirmed response shape (2026-06-13):
      data.records[].date                              — "YYYY-MM-DD"
      data.records[].trade_activity.net_summary.lot   — net lot (can be negative)
      data.records[].trade_activity.net_summary.value — net value (can be negative)
      data.records[].trade_activity.net_summary.avg_price
      data.records[].price_activity.close_price       — fallback price
    """
    data = body.get("data") if isinstance(body, dict) else body
    if not isinstance(data, dict):
        return []

    rows = data.get("records")
    if not isinstance(rows, list) or not rows:
        logger.debug("broker_flow_history/%s: no 'records' list in response", ticker)
        return []

    points: list[ForeignFlowPoint] = []
    for item in rows:
        if not isinstance(item, dict):
            continue

        date_str = str(item.get("date") or "")
        try:
            point_date = date.fromisoformat(date_str[:10])
        except (ValueError, TypeError):
            continue

        trade = item.get("trade_activity") or {}
        net = trade.get("net_summary") or {}
        price_activity = item.get("price_activity") or {}

        net_val = _dict_dec(net, "value")
        net_lot = _dict_int(net, "lot")
        avg_price = _dict_dec(net, "avg_price") or _dict_dec(price_activity, "close_price")

        try:
            points.append(
                ForeignFlowPoint(
                    ticker=ticker.upper(),
                    date=point_date,
                    net_val=net_val,
                    net_lot=net_lot,
                    avg_price=avg_price,
                )
            )
        except Exception as e:
            logger.debug("Could not parse flow point for %s %s: %s", ticker, date_str, e)

    return sorted(points, key=lambda p: p.date)
