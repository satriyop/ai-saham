"""
Policy for building broker quality notes.

Layer: Application (Service)
"""

from decimal import Decimal
from typing import Any

from src.application.dto.swing_broker_detail import BrokerDetail, BrokerQualityNote


def build_broker_quality_note(
    broker_detail: BrokerDetail | None,
    setup_eval: Any | None,
    *,
    smart_sell_min_share_pct: float = 15.0,
) -> BrokerQualityNote | None:
    """Build a display-only broker-quality note without changing setup gates."""
    if broker_detail is None or setup_eval is None:
        return None

    smart_flow = broker_detail.smart_flow
    noise_flow = broker_detail.noise_flow
    quality = broker_detail.broker_weight_quality

    if smart_flow < Decimal("0"):
        total_abs = abs(smart_flow) + abs(noise_flow) + abs(broker_detail.neutral_flow)
        smart_sell_share = abs(smart_flow) / total_abs if total_abs > Decimal("0") else Decimal("0")
        if smart_sell_share >= Decimal(str(smart_sell_min_share_pct)) / Decimal("100"):
            pct_str = f"{float(smart_sell_share) * 100:.0f}%"
            return BrokerQualityNote(
                level="warning",
                message=(
                    f"Broker quality warning: smart-money net selling "
                    f"({pct_str} of tracked flow) conflicts with the accumulation setup."
                ),
            )

    if setup_eval.match.value == "MATCH" and (
        quality == "noisy accumulation"
        or (noise_flow > Decimal("0") and noise_flow > smart_flow)
    ):
        return BrokerQualityNote(
            level="warning",
            message=(
                "Broker quality warning: accumulation is noise-led; require "
                "stronger chart confirmation."
            ),
        )

    if setup_eval.match.value == "PARTIAL" and smart_flow > Decimal("0"):
        return BrokerQualityNote(
            level="support",
            message=(
                "Broker quality support: smart-money buying supports "
                "watchlist priority."
            ),
        )

    if setup_eval.match.value == "MATCH" and smart_flow > Decimal("0"):
        return BrokerQualityNote(
            level="support",
            message=(
                "Broker quality support: smart-money buying confirms the "
                "setup match."
            ),
        )

    return None
