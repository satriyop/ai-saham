"""
Broker quality signal computation.

Classifies named brokers by tier (smart-money / noise / neutral) and computes
a per-ticker flow composition signal from broker summary rows.

This is Application-layer business logic: it makes decisions about what the
broker flow data MEANS, not just how to fetch or display it.

Layer: Application
Depends on: Domain ports only (BrokerDataRepository)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class BrokerQualitySnapshot:
    """Compact broker-flow composition signal for a ticker."""

    label: str          # "smart+" | "noise+" | "noise-" | "smart-" | "mixed" | "dist" | "n/a"
    smart_flow: Decimal
    noise_flow: Decimal
    neutral_flow: Decimal
    sessions: int
    through_date: date
    source: str

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "smart_flow": str(self.smart_flow),
            "noise_flow": str(self.noise_flow),
            "neutral_flow": str(self.neutral_flow),
            "sessions": self.sessions,
            "through": self.through_date.isoformat(),
            "source": self.source,
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


def compute_broker_quality(
    ticker: str,
    broker_repo,
    smart_money_brokers: tuple[str, ...],
    noise_brokers: tuple[str, ...],
    as_of_date: date | None = None,
    window_sessions: int = 5,
) -> BrokerQualitySnapshot | None:
    """
    Compute a broker flow quality snapshot for one ticker.

    Reads the most recent `window_sessions` broker summary rows from the
    repository and aggregates net flow by tier (smart / noise / neutral).

    Returns None if there are no named-broker rows in the window.

    Args:
        broker_repo: Any repository with a `get_broker_summaries(ticker, end_date)` method.
        smart_money_brokers: Broker codes classified as smart-money.
        noise_brokers: Broker codes classified as noise.
        as_of_date: Restrict to summaries on or before this date (None = all).
        window_sessions: How many sessions to look back.
    """
    summaries = broker_repo.get_broker_summaries(ticker, end_date=as_of_date)
    detail_summaries = [
        s for s in summaries if s.top_buyers or s.top_sellers
    ][-window_sessions:]
    if not detail_summaries:
        return None

    smart_flow = Decimal("0")
    noise_flow = Decimal("0")
    neutral_flow = Decimal("0")

    for summary in detail_summaries:
        for tx in summary.top_buyers:
            if tx.net_value > Decimal("0"):
                tier = classify_broker_tier(tx.broker_code, smart_money_brokers, noise_brokers)
                if tier == "smart":
                    smart_flow += tx.net_value
                elif tier == "noise":
                    noise_flow += tx.net_value
                else:
                    neutral_flow += tx.net_value
        for tx in summary.top_sellers:
            if tx.net_value < Decimal("0"):
                tier = classify_broker_tier(tx.broker_code, smart_money_brokers, noise_brokers)
                if tier == "smart":
                    smart_flow += tx.net_value
                elif tier == "noise":
                    noise_flow += tx.net_value
                else:
                    neutral_flow += tx.net_value

    latest = detail_summaries[-1]
    return BrokerQualitySnapshot(
        label=compute_quality_label(smart_flow, noise_flow, neutral_flow),
        smart_flow=smart_flow,
        noise_flow=noise_flow,
        neutral_flow=neutral_flow,
        sessions=len(detail_summaries),
        through_date=latest.date,
        source=latest.source,
    )


def compute_broker_quality_batch(
    tickers: list[str],
    broker_repo,
    smart_money_brokers: tuple[str, ...],
    noise_brokers: tuple[str, ...],
    as_of_date: date | None = None,
) -> dict[str, BrokerQualitySnapshot]:
    """Compute broker quality for multiple tickers. Returns {ticker.upper(): snapshot}."""
    result: dict[str, BrokerQualitySnapshot] = {}
    for ticker in tickers:
        snapshot = compute_broker_quality(
            ticker=ticker,
            broker_repo=broker_repo,
            smart_money_brokers=smart_money_brokers,
            noise_brokers=noise_brokers,
            as_of_date=as_of_date,
        )
        if snapshot is not None:
            result[ticker.upper()] = snapshot
    return result
