"""
Service for building swing flow detail.

Layer: Application (Service)
"""

from datetime import date
from decimal import Decimal
from typing import Any

from src.application.dto.swing_broker_detail import FlowDetail


def build_flow_detail(
    ticker: str,
    broker_repo: Any,
    window_sessions: int,
    as_of_date: date,
) -> FlowDetail | None:
    summaries = broker_repo.get_broker_summaries(ticker, end_date=as_of_date)
    summaries = summaries[-window_sessions:]
    if not summaries:
        return None

    total_net_flow = sum(
        (summary.foreign_net_value for summary in summaries),
        Decimal("0"),
    )
    buy_sessions = sum(1 for summary in summaries if summary.is_foreign_accumulating)
    sell_sessions = len(summaries) - buy_sessions

    consecutive_buy_sessions = 0
    for summary in reversed(summaries):
        if summary.is_foreign_accumulating:
            consecutive_buy_sessions += 1
        else:
            break

    ratios = [float(summary.foreign_flow_ratio) for summary in summaries]
    latest = summaries[-1]
    return FlowDetail(
        window_sessions=window_sessions,
        available_sessions=len(summaries),
        from_date=summaries[0].date,
        through_date=latest.date,
        total_net_flow=total_net_flow,
        buy_sessions=buy_sessions,
        sell_sessions=sell_sessions,
        consecutive_buy_sessions=consecutive_buy_sessions,
        avg_flow_ratio_pct=(sum(ratios) / len(ratios)) if ratios else None,
        latest_net_flow=latest.foreign_net_value,
        latest_flow_ratio_pct=float(latest.foreign_flow_ratio),
        latest_date=latest.date,
    )
