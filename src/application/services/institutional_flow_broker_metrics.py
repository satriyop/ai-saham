"""Broker filtering and generic broker metric helpers."""

from __future__ import annotations

from datetime import date

from src.application.services.institutional_flow_math import (
    _group_by_date,
    _vwap_distance_score,
)
from src.domain.entities.broker_flow import BrokerDailyFlow
from src.domain.entities.candle import Candle


class _Unavailable(Exception):
    """Signals a metric could not be computed (expected, not an error)."""


def is_foreign_broker(broker_code: str, foreign_codes: frozenset[str]) -> bool:
    return broker_code.upper() in foreign_codes


def foreign_flows(
    flows: list[BrokerDailyFlow],
    foreign_codes: frozenset[str],
) -> list[BrokerDailyFlow]:
    return [f for f in flows if is_foreign_broker(f.broker_code, foreign_codes)]


def local_flows(
    flows: list[BrokerDailyFlow],
    foreign_codes: frozenset[str],
) -> list[BrokerDailyFlow]:
    return [f for f in flows if not is_foreign_broker(f.broker_code, foreign_codes)]


def _net_by_broker(session: list[BrokerDailyFlow]) -> dict[str, float]:
    result: dict[str, float] = {}
    for flow in session:
        code = flow.broker_code.upper()
        result[code] = result.get(code, 0.0) + float(flow.net_value)
    return result


def _top_brokers_by_net(
    flows: list[BrokerDailyFlow],
    dates: list[date],
    *,
    count: int,
) -> list[str]:
    date_set = set(dates)
    totals: dict[str, float] = {}
    for flow in flows:
        if flow.date not in date_set:
            continue
        code = flow.broker_code.upper()
        totals[code] = totals.get(code, 0.0) + float(flow.net_value)
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    return [code for code, _ in ranked[:count]]


def _top_brokers_by_volume(
    flows: list[BrokerDailyFlow],
    dates: list[date],
    *,
    count: int,
) -> set[str]:
    date_set = set(dates)
    totals: dict[str, float] = {}
    for flow in flows:
        if flow.date not in date_set:
            continue
        code = flow.broker_code.upper()
        volume = float(flow.buy_value) + float(flow.sell_value)
        totals[code] = totals.get(code, 0.0) + volume
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    return {code for code, _ in ranked[:count]}


def vwap_distance_from_price(
    flows: list[BrokerDailyFlow],
    current_price: float | None,
    days: int,
    min_sessions: int,
) -> float | None:
    if current_price is None:
        raise _Unavailable("no_current_price")
    by_date = _group_by_date(flows)
    recent = sorted(by_date)[-days:]
    total_value = 0.0
    total_shares = 0.0
    valid_sessions = 0
    for d in recent:
        session_value = 0.0
        session_shares = 0.0
        counted = False
        for flow in by_date[d]:
            buy_value = float(flow.buy_value)
            avg_price = float(flow.avg_buy_price)
            if buy_value <= 0 or avg_price <= 0:
                continue
            session_value += buy_value
            session_shares += buy_value / avg_price
            counted = True
        if counted:
            total_value += session_value
            total_shares += session_shares
            valid_sessions += 1
    if valid_sessions < min_sessions or total_shares <= 0:
        raise _Unavailable("insufficient_vwap_sessions")
    vwap = total_value / total_shares
    score = _vwap_distance_score(current_price, vwap)
    if score is None:
        raise _Unavailable("invalid_vwap")
    return score


def vwap_distance(
    flows: list[BrokerDailyFlow],
    candles: list[Candle],
    days: int,
    min_sessions: int,
) -> float | None:
    current_price = float(candles[-1].close) if candles else None
    return vwap_distance_from_price(
        flows, current_price, days, min_sessions
    )
