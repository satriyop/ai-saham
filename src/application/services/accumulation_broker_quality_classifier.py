"""
Broker-quality classification for accumulation-audit replay.

Layer: Application
Depends on: BrokerDataRepository port
AI usage: None
"""

from datetime import date
from decimal import Decimal

from src.domain.ports.broker_data_repository import BrokerDataRepository

SMART_MONEY_BROKERS = {"AK", "BK", "KZ", "ZP", "RX", "MS", "DB", "CS", "ML", "YU"}
NOISE_BROKERS = {"YP", "PD", "XL", "XC"}


class AccumulationBrokerQualityClassifier:
    """Classify recent named top-broker flow available at a signal date."""

    def __init__(self, broker_repository: BrokerDataRepository) -> None:
        self._broker_repo = broker_repository

    def classify(
        self,
        ticker: str,
        signal_date: date,
        window_sessions: int = 5,
    ) -> str:
        """Classify recent named top-broker flow available at signal date."""
        summaries = self._broker_repo.get_broker_summaries(
            ticker=ticker,
            end_date=signal_date,
        )
        detail_summaries = [
            summary for summary in summaries if summary.top_buyers or summary.top_sellers
        ][-window_sessions:]
        if not detail_summaries:
            return "no_detail"

        smart_flow = Decimal("0")
        noise_flow = Decimal("0")
        neutral_flow = Decimal("0")

        def add_flow(code: str, signed_value: Decimal) -> None:
            nonlocal smart_flow, noise_flow, neutral_flow
            code_upper = code.upper()
            if code_upper in SMART_MONEY_BROKERS:
                smart_flow += signed_value
            elif code_upper in NOISE_BROKERS:
                noise_flow += signed_value
            else:
                neutral_flow += signed_value

        for summary in detail_summaries:
            for tx in summary.top_buyers:
                if tx.net_value > Decimal("0"):
                    add_flow(tx.broker_code, tx.net_value)
            for tx in summary.top_sellers:
                if tx.net_value < Decimal("0"):
                    add_flow(tx.broker_code, tx.net_value)

        return classify_broker_quality_from_flows(
            smart_flow=smart_flow,
            noise_flow=noise_flow,
            neutral_flow=neutral_flow,
        )


def classify_broker_quality_from_flows(
    *,
    smart_flow: Decimal,
    noise_flow: Decimal,
    neutral_flow: Decimal,
) -> str:
    positive_total = sum(
        value
        for value in (smart_flow, noise_flow, neutral_flow)
        if value > Decimal("0")
    )
    negative_total = sum(
        abs(value)
        for value in (smart_flow, noise_flow, neutral_flow)
        if value < Decimal("0")
    )

    if positive_total == Decimal("0") and negative_total == Decimal("0"):
        return "no_detail"
    if negative_total > positive_total:
        if smart_flow < Decimal("0") and abs(smart_flow) >= abs(noise_flow):
            return "smart-"
        if noise_flow < Decimal("0"):
            return "noise-"
        return "mixed"
    if smart_flow > Decimal("0") and smart_flow >= noise_flow and smart_flow >= neutral_flow:
        return "smart+"
    if noise_flow > Decimal("0") and noise_flow >= smart_flow and noise_flow >= neutral_flow:
        return "noise+"
    return "mixed"
