"""
Service for building swing broker details and quality notes.

Layer: Application (Service)
"""

from datetime import date
from decimal import Decimal
from typing import Any

from src.application.dto.swing_broker_detail import BrokerDetail
from src.application.services.broker_detail_aggregation import (
    BrokerFlowRow,
    aggregate_broker_detail_rows,
)

# Compatibility re-exports — no implementation logic.
from src.application.services.swing_broker_quality_note_policy import (  # noqa: F401
    build_broker_quality_note,
)
from src.application.services.swing_flow_detail_builder import build_flow_detail  # noqa: F401


def build_broker_detail_from_daily_flows(
    ticker: str,
    daily_flows: list,
    window_sessions: int,
    as_of_date: date | None,
    *,
    smart_money_brokers: set[str],
    noise_brokers: set[str],
    broker_weights: dict[str, Decimal],
    smart_share_threshold_pct: float,
) -> BrokerDetail | None:
    """Build BrokerDetail from real per-day per-broker flow records."""
    all_dates = sorted({f.date for f in daily_flows}, reverse=True)
    window_dates = set(all_dates[:window_sessions])
    window_flows = [f for f in daily_flows if f.date in window_dates]
    if not window_flows:
        return None

    rows = [
        BrokerFlowRow(
            broker_code=f.broker_code,
            broker_name=f.broker_name,
            broker_type="unknown",
            signed_value=f.net_value,
            session_date=f.date,
        )
        for f in window_flows
    ]

    net_flow = sum((f.net_value for f in window_flows), Decimal("0"))
    agg = aggregate_broker_detail_rows(
        rows,
        latest_net_flow=net_flow,
        smart_money_brokers=smart_money_brokers,
        noise_brokers=noise_brokers,
        broker_weights=broker_weights,
        smart_share_threshold_pct=smart_share_threshold_pct,
    )

    through_date = max(f.date for f in window_flows)

    if not agg.buyers:
        quality = "no buyer detail"
    elif agg.top_buyer_share_pct is not None and agg.top_buyer_share_pct >= 60:
        quality = "concentrated accumulation"
    elif len(agg.buyers) >= 3 and len(window_dates) >= 3:
        quality = "broad accumulation"
    elif agg.smart_flow < Decimal("0"):
        quality = "recent distribution"
    else:
        quality = "limited accumulation detail"

    return BrokerDetail(
        window_sessions=window_sessions,
        detail_sessions=len(window_dates),
        through_date=through_date,
        source="stockbit",
        top_buyers=agg.buyers,
        top_sellers=agg.sellers,
        top_buyer_share_pct=agg.top_buyer_share_pct,
        top_seller_share_pct=agg.top_seller_share_pct,
        smart_flow=agg.smart_flow,
        noise_flow=agg.noise_flow,
        neutral_flow=agg.neutral_flow,
        weighted_net_flow=agg.weighted_net_flow,
        smart_share_pct=agg.smart_share_pct,
        broker_weight_quality=agg.broker_weight_quality,
        quality=quality,
    )


def build_broker_detail(
    ticker: str,
    broker_repo: Any,
    window_sessions: int = 5,
    as_of_date: date | None = None,
    *,
    smart_money_brokers: set[str],
    noise_brokers: set[str],
    broker_weights: dict[str, Decimal],
    smart_share_threshold_pct: float,
) -> BrokerDetail | None:
    daily_flows = (
        broker_repo.get_broker_daily_flows(ticker, end_date=as_of_date)
        if hasattr(broker_repo, "get_broker_daily_flows")
        else []
    )

    if daily_flows:
        return build_broker_detail_from_daily_flows(
            ticker,
            daily_flows,
            window_sessions,
            as_of_date,
            smart_money_brokers=smart_money_brokers,
            noise_brokers=noise_brokers,
            broker_weights=broker_weights,
            smart_share_threshold_pct=smart_share_threshold_pct,
        )

    summaries = broker_repo.get_broker_summaries(ticker, end_date=as_of_date)
    detail_summaries = [
        summary for summary in summaries if summary.top_buyers or summary.top_sellers
    ][-window_sessions:]
    if not detail_summaries:
        return None

    rows: list[BrokerFlowRow] = []
    for summary in detail_summaries:
        for tx in summary.top_buyers:
            if tx.net_value > Decimal("0"):
                rows.append(
                    BrokerFlowRow(
                        broker_code=tx.broker_code,
                        broker_name=tx.broker_name,
                        broker_type=tx.broker_type.value,
                        signed_value=tx.net_value,
                        session_date=summary.date,
                    )
                )
        for tx in summary.top_sellers:
            if tx.net_value < Decimal("0"):
                rows.append(
                    BrokerFlowRow(
                        broker_code=tx.broker_code,
                        broker_name=tx.broker_name,
                        broker_type=tx.broker_type.value,
                        signed_value=tx.net_value,
                        session_date=summary.date,
                    )
                )

    latest = detail_summaries[-1]
    agg = aggregate_broker_detail_rows(
        rows,
        latest_net_flow=latest.foreign_net_value,
        smart_money_brokers=smart_money_brokers,
        noise_brokers=noise_brokers,
        broker_weights=broker_weights,
        smart_share_threshold_pct=smart_share_threshold_pct,
    )

    if latest.foreign_net_value < Decimal("0"):
        quality = "recent distribution"
    elif agg.top_buyer_share_pct is not None and agg.top_buyer_share_pct >= 60:
        quality = "concentrated accumulation"
    elif len(agg.buyers) >= 3 and len(detail_summaries) >= 3:
        quality = "broad accumulation"
    elif agg.buyers:
        quality = "limited accumulation detail"
    else:
        quality = "no buyer detail"

    return BrokerDetail(
        window_sessions=window_sessions,
        detail_sessions=len(detail_summaries),
        through_date=latest.date,
        source=latest.source,
        top_buyers=agg.buyers,
        top_sellers=agg.sellers,
        top_buyer_share_pct=agg.top_buyer_share_pct,
        top_seller_share_pct=agg.top_seller_share_pct,
        smart_flow=agg.smart_flow,
        noise_flow=agg.noise_flow,
        neutral_flow=agg.neutral_flow,
        weighted_net_flow=agg.weighted_net_flow,
        smart_share_pct=agg.smart_share_pct,
        broker_weight_quality=agg.broker_weight_quality,
        quality=quality,
    )
