"""
Pure helpers for desk-centric views over broker_daily_flow.

Tracked brokers only — not full-market composition.

Layer: Application (Service)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.application.services.institutional_flow_broker_metrics import is_foreign_broker
from src.domain.entities.broker_flow import BrokerDailyFlow, BrokerType


@dataclass(frozen=True)
class DeskTickerNet:
    """One ticker's net for a desk on a resolved window."""

    ticker: str
    net_value: Decimal
    net_lot: int
    buy_value: Decimal
    sell_value: Decimal
    sessions: int


@dataclass(frozen=True)
class DeskDayNet:
    """Desk aggregate net across all cached tickers on one date."""

    date: date
    net_value: Decimal
    net_lot: int
    buy_value: Decimal
    sell_value: Decimal
    ticker_count: int


def classify_desk_type(
    broker_code: str,
    foreign_broker_codes: frozenset[str] | None,
) -> BrokerType:
    if foreign_broker_codes is None:
        return BrokerType.UNKNOWN
    if is_foreign_broker(broker_code, foreign_broker_codes):
        return BrokerType.FOREIGN
    return BrokerType.LOCAL


def rank_tickers_for_desk(
    flows: list[BrokerDailyFlow],
    *,
    limit: int = 20,
) -> tuple[tuple[DeskTickerNet, ...], tuple[DeskTickerNet, ...]]:
    """
    Aggregate flows by ticker, split net buyers vs net sellers for the desk.

    Buyers: net_value > 0 DESC; sellers: net_value < 0 ASC (most negative first).
    """
    if limit < 1:
        raise ValueError("limit must be >= 1")

    by_ticker: dict[str, list[BrokerDailyFlow]] = {}
    for flow in flows:
        by_ticker.setdefault(flow.ticker.upper(), []).append(flow)

    nets: list[DeskTickerNet] = []
    for ticker, rows in by_ticker.items():
        nets.append(
            DeskTickerNet(
                ticker=ticker,
                net_value=sum((r.net_value for r in rows), Decimal("0")),
                net_lot=sum(r.net_lot for r in rows),
                buy_value=sum((r.buy_value for r in rows), Decimal("0")),
                sell_value=sum((r.sell_value for r in rows), Decimal("0")),
                sessions=len({r.date for r in rows}),
            )
        )

    buyers = sorted(
        (n for n in nets if n.net_value > Decimal("0")),
        key=lambda n: n.net_value,
        reverse=True,
    )
    sellers = sorted(
        (n for n in nets if n.net_value < Decimal("0")),
        key=lambda n: n.net_value,
    )
    return tuple(buyers[:limit]), tuple(sellers[:limit])


def aggregate_desk_by_date(flows: list[BrokerDailyFlow]) -> tuple[DeskDayNet, ...]:
    """Sum desk activity per calendar date across tickers."""
    by_date: dict[date, list[BrokerDailyFlow]] = {}
    for flow in flows:
        by_date.setdefault(flow.date, []).append(flow)

    days: list[DeskDayNet] = []
    for d in sorted(by_date):
        rows = by_date[d]
        days.append(
            DeskDayNet(
                date=d,
                net_value=sum((r.net_value for r in rows), Decimal("0")),
                net_lot=sum(r.net_lot for r in rows),
                buy_value=sum((r.buy_value for r in rows), Decimal("0")),
                sell_value=sum((r.sell_value for r in rows), Decimal("0")),
                ticker_count=len({r.ticker.upper() for r in rows}),
            )
        )
    return tuple(days)


@dataclass(frozen=True)
class DeskSessionPulse:
    """Multi-session pulse for desk list/show (cache-derived, not a score)."""

    as_of: date
    day_net: Decimal
    net5: Decimal  # sum of last min(5, n) session nets
    sessions_in_net5: int
    buy_streak: int  # consecutive net-buy sessions ending at as_of (0 if latest ≤ 0)
    delta1: Decimal | None  # day_net − prior session net; None if only one session


def desk_session_pulse(
    flows: list[BrokerDailyFlow],
    *,
    net_window: int = 5,
) -> DeskSessionPulse | None:
    """Build DayNet / Net5 / buy-streak / Δ1 from distinct sessions with data.

    Sessions = calendar dates present for the desk (not blank calendar days).
    """
    if net_window < 1:
        raise ValueError("net_window must be >= 1")
    days = aggregate_desk_by_date(flows)
    if not days:
        return None
    latest = days[-1]
    window = days[-net_window:]
    net5 = sum((d.net_value for d in window), Decimal("0"))
    streak = 0
    for d in reversed(days):
        if d.net_value > Decimal("0"):
            streak += 1
        else:
            break
    delta1: Decimal | None = None
    if len(days) >= 2:
        delta1 = days[-1].net_value - days[-2].net_value
    return DeskSessionPulse(
        as_of=latest.date,
        day_net=latest.net_value,
        net5=net5,
        sessions_in_net5=len(window),
        buy_streak=streak,
        delta1=delta1,
    )
