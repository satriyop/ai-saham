"""
Tracked-broker flow signal computation.

Classifies configured tracked-broker codes by tier (smart-money / noise /
neutral) and computes a per-ticker flow composition signal from
`broker_daily_flow` rows.

IMPORTANT SEMANTIC NOTE: `broker_daily_flow` only covers a configured subset
of tracked broker codes (see BrokerDailyFlow's imbalance note) — it is NOT
full-market broker composition. This module must never be described as
"broker quality" in the full-market sense. If full top-broker composition is
ever needed, it is a separate concept sourced from
`broker_summaries.top_buyers/top_sellers`, not this module.

This is Application-layer business logic: it makes decisions about what the
tracked-broker flow data MEANS, not just how to fetch or display it.

Layer: Application
Depends on: Domain ports only (BrokerDataRepository)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class TrackedBrokerFlowSnapshot:
    """Compact tracked-broker flow composition signal for a ticker.

    Sourced exclusively from `broker_daily_flow` (configured tracked broker
    codes) — `scope` is always "tracked_brokers" to make this explicit to
    every consumer, including JSON.
    """

    label: str          # "smart+" | "noise+" | "noise-" | "smart-" | "mixed" | "dist" | "n/a"
    smart_flow: Decimal
    noise_flow: Decimal
    neutral_flow: Decimal
    sessions: int
    through_date: date
    source: str          # fixed "broker_daily_flow" — the data-product name, not the raw provider
    scope: str = "tracked_brokers"

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "smart_flow": str(self.smart_flow),
            "noise_flow": str(self.noise_flow),
            "neutral_flow": str(self.neutral_flow),
            "sessions": self.sessions,
            "through": self.through_date.isoformat(),
            "source": self.source,
            "scope": self.scope,
        }


def classify_broker_tier(
    code: str,
    smart_money_brokers: tuple[str, ...],
    noise_brokers: tuple[str, ...],
) -> str:
    """Return "smart", "noise", or "neutral" for a broker code."""
    code_upper = code.upper()
    if code_upper in smart_money_brokers:
        return "smart"
    if code_upper in noise_brokers:
        return "noise"
    return "neutral"


def compute_quality_label(
    smart_flow: Decimal,
    noise_flow: Decimal,
    neutral_flow: Decimal,
) -> str:
    """Derive a compact quality label from signed flow values."""
    positive_total = sum(v for v in (smart_flow, noise_flow, neutral_flow) if v > Decimal("0"))
    negative_total = sum(abs(v) for v in (smart_flow, noise_flow, neutral_flow) if v < Decimal("0"))

    if negative_total > positive_total:
        if smart_flow < Decimal("0") and abs(smart_flow) >= abs(noise_flow):
            return "smart-"
        if noise_flow < Decimal("0"):
            return "noise-"
        return "dist"

    if smart_flow > Decimal("0") and smart_flow >= noise_flow and smart_flow >= neutral_flow:
        return "smart+"
    if noise_flow > Decimal("0") and noise_flow >= smart_flow and noise_flow >= neutral_flow:
        return "noise+"
    if neutral_flow != Decimal("0"):
        return "mixed"
    return "n/a"


def compute_tracked_broker_flow(
    ticker: str,
    broker_repo,
    smart_money_brokers: tuple[str, ...],
    noise_brokers: tuple[str, ...],
    as_of_date: date | None = None,
    window_sessions: int = 5,
) -> TrackedBrokerFlowSnapshot | None:
    """
    Compute a tracked-broker flow snapshot for one ticker.

    Reads `broker_daily_flow` rows (configured tracked broker codes only —
    NOT full-market broker composition) up to `as_of_date`, restricts to the
    most recent `window_sessions` distinct trading dates, and aggregates net
    flow by tier (smart / noise / neutral).

    Returns None if there are no tracked-broker rows in range.

    Args:
        broker_repo: Any repository with a
            `get_broker_daily_flows(ticker, end_date)` method.
        smart_money_brokers: Broker codes classified as smart-money.
        noise_brokers: Broker codes classified as noise.
        as_of_date: Restrict to flows on or before this date (None = all).
        window_sessions: How many distinct trading dates to look back.
    """
    flows = broker_repo.get_broker_daily_flows(ticker, end_date=as_of_date)
    if not flows:
        return None

    recent_dates = sorted({f.date for f in flows})[-window_sessions:]
    if not recent_dates:
        return None
    recent_dates_set = set(recent_dates)
    recent_flows = [f for f in flows if f.date in recent_dates_set]
    if not recent_flows:
        return None

    smart_flow = Decimal("0")
    noise_flow = Decimal("0")
    neutral_flow = Decimal("0")

    for flow in recent_flows:
        tier = classify_broker_tier(flow.broker_code, smart_money_brokers, noise_brokers)
        if tier == "smart":
            smart_flow += flow.net_value
        elif tier == "noise":
            noise_flow += flow.net_value
        else:
            neutral_flow += flow.net_value

    latest = max(recent_flows, key=lambda f: f.date)
    return TrackedBrokerFlowSnapshot(
        label=compute_quality_label(smart_flow, noise_flow, neutral_flow),
        smart_flow=smart_flow,
        noise_flow=noise_flow,
        neutral_flow=neutral_flow,
        sessions=len(recent_dates),
        through_date=latest.date,
        # Fixed data-product label, not the raw provider (e.g. "stockbit") —
        # CLI/JSON consumers must be able to tell at a glance that this
        # value came from the tracked-broker-subset table, not a raw feed.
        source="broker_daily_flow",
    )


def compute_tracked_broker_flow_batch(
    tickers: list[str],
    broker_repo,
    smart_money_brokers: tuple[str, ...],
    noise_brokers: tuple[str, ...],
    as_of_date: date | None = None,
) -> dict[str, TrackedBrokerFlowSnapshot]:
    """Compute tracked-broker flow for multiple tickers.

    Returns {ticker.upper(): snapshot}.
    """
    result: dict[str, TrackedBrokerFlowSnapshot] = {}
    for ticker in tickers:
        snapshot = compute_tracked_broker_flow(
            ticker=ticker,
            broker_repo=broker_repo,
            smart_money_brokers=smart_money_brokers,
            noise_brokers=noise_brokers,
            as_of_date=as_of_date,
        )
        if snapshot is not None:
            result[ticker.upper()] = snapshot
    return result
