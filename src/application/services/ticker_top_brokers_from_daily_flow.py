"""
Rank tracked-broker daily flow rows into top buyers / sellers for a stock.

`broker_daily_flow` only covers configured tracked broker codes — not full-market
top composition. Callers must surface that scope when displaying results.

Foreign/local type is not stored on daily-flow rows. When
``foreign_broker_codes`` is supplied, type is classified from that config set
(same rule as institutional accumulation: in set → FOREIGN, else LOCAL).

Layer: Application (Service)
Depends on: Domain entities, institutional_flow_broker_metrics
"""

from __future__ import annotations

from decimal import Decimal

from src.application.services.institutional_flow_broker_metrics import is_foreign_broker
from src.domain.entities.broker_flow import (
    BrokerDailyFlow,
    BrokerTransaction,
    BrokerType,
)

TRACKED_TOPS_SCOPE = "tracked_brokers"
TRACKED_TOPS_SOURCE = "broker_daily_flow"
TRACKED_TOPS_NOTE = "Tracked brokers (not full market top)"


def classify_daily_flow_broker_type(
    broker_code: str,
    foreign_broker_codes: frozenset[str] | None,
) -> BrokerType:
    """Classify type from config foreign codes; UNKNOWN if no classification set."""
    if foreign_broker_codes is None:
        return BrokerType.UNKNOWN
    if is_foreign_broker(broker_code, foreign_broker_codes):
        return BrokerType.FOREIGN
    return BrokerType.LOCAL


def daily_flow_to_transaction(
    flow: BrokerDailyFlow,
    *,
    foreign_broker_codes: frozenset[str] | None = None,
) -> BrokerTransaction:
    """Map a daily-flow row to BrokerTransaction for display reuse.

    broker_daily_flow has no foreign/local column; type is classified from
    ``foreign_broker_codes`` when provided, otherwise UNKNOWN.
    """
    return BrokerTransaction(
        broker_code=flow.broker_code,
        broker_name=flow.broker_name or flow.broker_code,
        broker_type=classify_daily_flow_broker_type(
            flow.broker_code,
            foreign_broker_codes,
        ),
        buy_lot=flow.buy_lot,
        sell_lot=flow.sell_lot,
        buy_value=flow.buy_value,
        sell_value=flow.sell_value,
        avg_buy_price=flow.avg_buy_price,
        avg_sell_price=flow.avg_sell_price,
    )


def rank_top_brokers_from_daily_flows(
    flows: list[BrokerDailyFlow],
    *,
    limit: int = 10,
    foreign_broker_codes: frozenset[str] | None = None,
) -> tuple[tuple[BrokerTransaction, ...], tuple[BrokerTransaction, ...]]:
    """
    Rank net buyers and net sellers from tracked daily-flow rows for one day.

    Buyers: net_value > 0, descending by net_value.
    Sellers: net_value < 0, ascending by net_value (most negative first).
    Flat net (0) rows are omitted from both sides.
    """
    if limit < 1:
        raise ValueError("limit must be >= 1")

    buyers = sorted(
        (f for f in flows if f.net_value > Decimal("0")),
        key=lambda f: f.net_value,
        reverse=True,
    )
    sellers = sorted(
        (f for f in flows if f.net_value < Decimal("0")),
        key=lambda f: f.net_value,
    )
    return (
        tuple(
            daily_flow_to_transaction(f, foreign_broker_codes=foreign_broker_codes)
            for f in buyers[:limit]
        ),
        tuple(
            daily_flow_to_transaction(f, foreign_broker_codes=foreign_broker_codes)
            for f in sellers[:limit]
        ),
    )
