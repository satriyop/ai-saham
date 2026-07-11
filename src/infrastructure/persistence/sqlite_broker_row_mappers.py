"""
Pure serialization and row-mapping helpers for broker SQLite persistence.

Layer: Infrastructure
Depends on: Domain entities only. No DB access.
"""

import json
import sqlite3
from datetime import date
from decimal import Decimal

from src.domain.entities.broker_flow import (
    BrokerDailyFlow,
    BrokerSummary,
    BrokerTransaction,
    ForeignFlowPoint,
    ForeignFlowSnapshot,
)


def serialize_broker_transactions(transactions: tuple[BrokerTransaction, ...]) -> str:
    return json.dumps([t.to_dict() for t in transactions])


def deserialize_broker_transactions(json_str: str | None) -> tuple[BrokerTransaction, ...]:
    if not json_str:
        return ()
    return tuple(BrokerTransaction.from_dict(d) for d in json.loads(json_str))


def row_to_broker_summary(row: sqlite3.Row) -> BrokerSummary:
    return BrokerSummary(
        ticker=row["ticker"],
        date=date.fromisoformat(row["date"]),
        top_buyers=deserialize_broker_transactions(row["top_buyers_json"]),
        top_sellers=deserialize_broker_transactions(row["top_sellers_json"]),
        foreign_buy_value=Decimal(row["foreign_buy_value"]),
        foreign_sell_value=Decimal(row["foreign_sell_value"]),
        foreign_buy_lot=row["foreign_buy_lot"],
        foreign_sell_lot=row["foreign_sell_lot"],
        total_value=Decimal(row["total_value"]),
        total_lot=row["total_lot"],
        source=row["source"],
    )


def row_to_foreign_flow_point(row: sqlite3.Row) -> ForeignFlowPoint:
    return ForeignFlowPoint(
        ticker=row["ticker"],
        date=date.fromisoformat(row["date"]),
        net_val=Decimal(row["net_val"]),
        net_lot=row["net_lot"],
        avg_price=Decimal(row["avg_price"]),
        source=row["source"],
    )


def row_to_foreign_flow_snapshot(row: sqlite3.Row) -> ForeignFlowSnapshot:
    return ForeignFlowSnapshot(
        ticker=row["ticker"],
        date=date.fromisoformat(row["snapshot_date"]),
        net_val=Decimal(row["net_val"]),
        net_lot=row["net_lot"],
    )


def row_to_broker_daily_flow(row: sqlite3.Row) -> BrokerDailyFlow:
    return BrokerDailyFlow(
        ticker=row["ticker"],
        date=date.fromisoformat(row["date"]),
        broker_code=row["broker_code"],
        broker_name=row["broker_name"],
        source=row["source"],
        buy_lot=row["buy_lot"],
        sell_lot=row["sell_lot"],
        net_lot=row["net_lot"],
        buy_value=Decimal(row["buy_value"]),
        sell_value=Decimal(row["sell_value"]),
        net_value=Decimal(row["net_value"]),
        avg_buy_price=Decimal(row["avg_buy_price"] or "0"),
        avg_sell_price=Decimal(row["avg_sell_price"] or "0"),
        avg_price=Decimal(row["avg_price"]),
        buy_pct=row["buy_pct"],
        sell_pct=row["sell_pct"],
    )
