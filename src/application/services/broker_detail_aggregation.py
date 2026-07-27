"""
Pure broker-detail aggregation from normalized signed flow rows.

Layer: Application (Service)
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.application.dto.swing_broker_detail import BrokerDetailLine


@dataclass(frozen=True)
class BrokerFlowRow:
    broker_code: str
    broker_name: str
    broker_type: str
    signed_value: Decimal
    session_date: date


@dataclass(frozen=True)
class BrokerDetailAggregation:
    buyers: tuple[BrokerDetailLine, ...]
    sellers: tuple[BrokerDetailLine, ...]
    top_buyer_share_pct: float | None
    top_seller_share_pct: float | None
    smart_flow: Decimal
    noise_flow: Decimal
    neutral_flow: Decimal
    weighted_net_flow: Decimal
    smart_share_pct: float | None
    broker_weight_quality: str


def _broker_line_sort_key(line: BrokerDetailLine) -> Decimal:
    return abs(line.net_value)


def _broker_tier(code: str, smart_money_brokers: set[str], noise_brokers: set[str]) -> str:
    code_upper = code.upper()
    if code_upper in smart_money_brokers:
        return "smart"
    if code_upper in noise_brokers:
        return "noise"
    return "neutral"


def _broker_weight(code: str, broker_weights: dict[str, Decimal]) -> Decimal:
    return broker_weights.get(code.upper(), Decimal("1.0"))


def _smart_share_pct(
    smart_flow: Decimal,
    noise_flow: Decimal,
    neutral_flow: Decimal,
) -> float | None:
    total = abs(smart_flow) + abs(noise_flow) + abs(neutral_flow)
    if total == Decimal("0"):
        return None
    return round(float(abs(smart_flow) / total * Decimal("100")), 1)


def _broker_weight_quality(
    smart_flow: Decimal,
    noise_flow: Decimal,
    neutral_flow: Decimal,
    latest_net_flow: Decimal,
    smart_share_pct: float | None,
    smart_share_threshold_pct: float,
) -> str:
    if latest_net_flow < Decimal("0") and smart_flow < Decimal("0"):
        return "smart distribution"
    if latest_net_flow < Decimal("0") and smart_flow > Decimal("0"):
        return "smart distribution watch"
    if smart_flow > Decimal("0") and (smart_share_pct or 0) >= smart_share_threshold_pct:
        return "smart accumulation"
    if noise_flow > Decimal("0") and smart_flow <= Decimal("0"):
        return "noisy accumulation"
    if smart_flow > Decimal("0"):
        return "smart support"
    if smart_flow < Decimal("0"):
        return "smart selling pressure"
    if neutral_flow > Decimal("0"):
        return "neutral accumulation"
    return "neutral detail"


def aggregate_broker_detail_rows(
    rows: list[BrokerFlowRow],
    *,
    latest_net_flow: Decimal,
    smart_money_brokers: set[str],
    noise_brokers: set[str],
    broker_weights: dict[str, Decimal],
    smart_share_threshold_pct: float,
    top_n: int = 5,
) -> BrokerDetailAggregation:
    buyer_values: dict[str, Decimal] = {}
    buyer_names: dict[str, str] = {}
    buyer_types: dict[str, str] = {}
    buyer_sessions: dict[str, set[date]] = {}
    seller_values: dict[str, Decimal] = {}
    seller_names: dict[str, str] = {}
    seller_types: dict[str, str] = {}
    seller_sessions: dict[str, set[date]] = {}
    smart_flow = Decimal("0")
    noise_flow = Decimal("0")
    neutral_flow = Decimal("0")
    weighted_net_flow = Decimal("0")

    def add_weighted_flow(code: str, signed_value: Decimal) -> None:
        nonlocal smart_flow, noise_flow, neutral_flow, weighted_net_flow
        tier = _broker_tier(code, smart_money_brokers, noise_brokers)
        if tier == "smart":
            smart_flow += signed_value
        elif tier == "noise":
            noise_flow += signed_value
        else:
            neutral_flow += signed_value
        weighted_net_flow += signed_value * _broker_weight(code, broker_weights)

    for row in rows:
        if row.signed_value > Decimal("0"):
            buyer_values[row.broker_code] = (
                buyer_values.get(row.broker_code, Decimal("0")) + row.signed_value
            )
            buyer_names[row.broker_code] = row.broker_name
            buyer_types[row.broker_code] = row.broker_type
            buyer_sessions.setdefault(row.broker_code, set()).add(row.session_date)
            add_weighted_flow(row.broker_code, row.signed_value)
        elif row.signed_value < Decimal("0"):
            seller_values[row.broker_code] = seller_values.get(row.broker_code, Decimal("0")) + abs(
                row.signed_value
            )
            seller_names[row.broker_code] = row.broker_name
            seller_types[row.broker_code] = row.broker_type
            seller_sessions.setdefault(row.broker_code, set()).add(row.session_date)
            add_weighted_flow(row.broker_code, row.signed_value)

    buyers = tuple(
        sorted(
            (
                BrokerDetailLine(
                    broker_code=code,
                    broker_name=buyer_names.get(code, code),
                    broker_type=buyer_types.get(code, "unknown"),
                    net_value=value,
                    active_sessions=len(buyer_sessions.get(code, set())),
                )
                for code, value in buyer_values.items()
            ),
            key=_broker_line_sort_key,
            reverse=True,
        )[:top_n]
    )
    sellers = tuple(
        sorted(
            (
                BrokerDetailLine(
                    broker_code=code,
                    broker_name=seller_names.get(code, code),
                    broker_type=seller_types.get(code, "unknown"),
                    net_value=-value,
                    active_sessions=len(seller_sessions.get(code, set())),
                )
                for code, value in seller_values.items()
            ),
            key=_broker_line_sort_key,
            reverse=True,
        )[:top_n]
    )

    total_buy = sum(buyer_values.values(), Decimal("0"))
    total_sell = sum(seller_values.values(), Decimal("0"))
    top_buyer_share = (
        round(float(abs(buyers[0].net_value) / total_buy * Decimal("100")), 1)
        if buyers and total_buy > Decimal("0")
        else None
    )
    top_seller_share = (
        round(float(abs(sellers[0].net_value) / total_sell * Decimal("100")), 1)
        if sellers and total_sell > Decimal("0")
        else None
    )

    smart_share = _smart_share_pct(smart_flow, noise_flow, neutral_flow)
    quality = _broker_weight_quality(
        smart_flow=smart_flow,
        noise_flow=noise_flow,
        neutral_flow=neutral_flow,
        latest_net_flow=latest_net_flow,
        smart_share_pct=smart_share,
        smart_share_threshold_pct=smart_share_threshold_pct,
    )

    return BrokerDetailAggregation(
        buyers=buyers,
        sellers=sellers,
        top_buyer_share_pct=top_buyer_share,
        top_seller_share_pct=top_seller_share,
        smart_flow=smart_flow,
        noise_flow=noise_flow,
        neutral_flow=neutral_flow,
        weighted_net_flow=weighted_net_flow,
        smart_share_pct=smart_share,
        broker_weight_quality=quality,
    )
