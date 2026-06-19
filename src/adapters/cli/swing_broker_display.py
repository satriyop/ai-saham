"""
Broker-flow display helpers for swing CLI commands.

Layer: Adapter
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class BrokerQualityNote:
    """Non-authoritative named-broker confirmation note for preset review."""

    level: str
    message: str

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "message": self.message,
        }


@dataclass(frozen=True)
class FlowDetail:
    """Broker-flow detail for the current ticker over recent broker sessions."""

    window_sessions: int
    available_sessions: int
    from_date: date | None
    through_date: date | None
    total_net_flow: Decimal
    buy_sessions: int
    sell_sessions: int
    consecutive_buy_sessions: int
    avg_flow_ratio_pct: float | None
    latest_net_flow: Decimal | None
    latest_flow_ratio_pct: float | None
    latest_date: date | None

    def to_dict(self) -> dict:
        return {
            "window_sessions": self.window_sessions,
            "available_sessions": self.available_sessions,
            "from": self.from_date.isoformat() if self.from_date else None,
            "through": self.through_date.isoformat() if self.through_date else None,
            "total_net_flow": str(self.total_net_flow),
            "buy_sessions": self.buy_sessions,
            "sell_sessions": self.sell_sessions,
            "consecutive_buy_sessions": self.consecutive_buy_sessions,
            "avg_flow_ratio_pct": self.avg_flow_ratio_pct,
            "latest_net_flow": (
                str(self.latest_net_flow) if self.latest_net_flow is not None else None
            ),
            "latest_flow_ratio_pct": self.latest_flow_ratio_pct,
            "latest_date": self.latest_date.isoformat() if self.latest_date else None,
        }


@dataclass(frozen=True)
class BrokerDetailLine:
    broker_code: str
    broker_name: str
    broker_type: str
    net_value: Decimal
    active_sessions: int

    def to_dict(self) -> dict:
        return {
            "broker_code": self.broker_code,
            "broker_name": self.broker_name,
            "broker_type": self.broker_type,
            "net_value": str(self.net_value),
            "active_sessions": self.active_sessions,
        }


@dataclass(frozen=True)
class BrokerDetail:
    """Named broker confirmation context from Stockbit-style broker summaries."""

    window_sessions: int
    detail_sessions: int
    through_date: date
    source: str
    top_buyers: tuple[BrokerDetailLine, ...]
    top_sellers: tuple[BrokerDetailLine, ...]
    top_buyer_share_pct: float | None
    top_seller_share_pct: float | None
    smart_flow: Decimal
    noise_flow: Decimal
    neutral_flow: Decimal
    weighted_net_flow: Decimal
    smart_share_pct: float | None
    broker_weight_quality: str
    quality: str

    def to_dict(self) -> dict:
        return {
            "window_sessions": self.window_sessions,
            "detail_sessions": self.detail_sessions,
            "through": self.through_date.isoformat(),
            "source": self.source,
            "top_buyers": [row.to_dict() for row in self.top_buyers],
            "top_sellers": [row.to_dict() for row in self.top_sellers],
            "top_buyer_share_pct": self.top_buyer_share_pct,
            "top_seller_share_pct": self.top_seller_share_pct,
            "smart_flow": str(self.smart_flow),
            "noise_flow": str(self.noise_flow),
            "neutral_flow": str(self.neutral_flow),
            "weighted_net_flow": str(self.weighted_net_flow),
            "smart_share_pct": self.smart_share_pct,
            "broker_weight_quality": self.broker_weight_quality,
            "quality": self.quality,
        }


def build_broker_quality_note(
    broker_detail: BrokerDetail | None,
    preset_eval: Any | None,
) -> BrokerQualityNote | None:
    """Build a display-only broker-quality note without changing preset gates."""
    if broker_detail is None or preset_eval is None:
        return None

    smart_flow = broker_detail.smart_flow
    noise_flow = broker_detail.noise_flow
    quality = broker_detail.broker_weight_quality

    if smart_flow < Decimal("0"):
        return BrokerQualityNote(
            level="warning",
            message=(
                "Broker quality warning: smart-money selling conflicts with "
                "the accumulation setup."
            ),
        )

    if preset_eval.classification == "ENTER" and (
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

    if preset_eval.classification == "WATCH" and smart_flow > Decimal("0"):
        return BrokerQualityNote(
            level="support",
            message=(
                "Broker quality support: smart-money buying supports "
                "watchlist priority."
            ),
        )

    if preset_eval.classification == "ENTER" and smart_flow > Decimal("0"):
        return BrokerQualityNote(
            level="support",
            message=(
                "Broker quality support: smart-money buying confirms the "
                "preset setup."
            ),
        )

    return None


def fmt_money_short(value: Decimal) -> str:
    abs_value = abs(value)
    if abs_value >= Decimal("1000000000000"):
        return f"{value / Decimal('1000000000000'):.2f}T"
    if abs_value >= Decimal("1000000000"):
        return f"{value / Decimal('1000000000'):.2f}B"
    if abs_value >= Decimal("1000000"):
        return f"{value / Decimal('1000000'):.2f}M"
    if abs_value >= Decimal("1000"):
        return f"{value / Decimal('1000'):.2f}K"
    return f"{value:.2f}"


def fmt_money_short_signed(value: Decimal) -> str:
    sign = "+" if value > Decimal("0") else ""
    return f"{sign}{fmt_money_short(value)}"


def fmt_broker_detail_lines(lines: tuple[BrokerDetailLine, ...]) -> str:
    if not lines:
        return "none"
    parts = []
    for line in lines[:3]:
        parts.append(
            f"{line.broker_code} {fmt_money_short(line.net_value)} "
            f"({line.active_sessions}s)"
        )
    return ", ".join(parts)


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

    buyer_values: dict[str, Decimal] = {}
    buyer_names: dict[str, str] = {}
    buyer_sessions: dict[str, set] = {}
    seller_values: dict[str, Decimal] = {}
    seller_names: dict[str, str] = {}
    seller_sessions: dict[str, set] = {}
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

    for f in window_flows:
        if f.net_value > Decimal("0"):
            buyer_values[f.broker_code] = buyer_values.get(f.broker_code, Decimal("0")) + f.net_value
            buyer_names[f.broker_code] = f.broker_name
            buyer_sessions.setdefault(f.broker_code, set()).add(f.date)
            add_weighted_flow(f.broker_code, f.net_value)
        elif f.net_value < Decimal("0"):
            seller_values[f.broker_code] = seller_values.get(f.broker_code, Decimal("0")) + abs(f.net_value)
            seller_names[f.broker_code] = f.broker_name
            seller_sessions.setdefault(f.broker_code, set()).add(f.date)
            add_weighted_flow(f.broker_code, f.net_value)

    buyers = tuple(sorted(
        (
            BrokerDetailLine(
                broker_code=code,
                broker_name=buyer_names.get(code, code),
                broker_type="unknown",
                net_value=value,
                active_sessions=len(buyer_sessions.get(code, set())),
            )
            for code, value in buyer_values.items()
        ),
        key=_broker_line_sort_key,
        reverse=True,
    )[:5])
    sellers = tuple(sorted(
        (
            BrokerDetailLine(
                broker_code=code,
                broker_name=seller_names.get(code, code),
                broker_type="unknown",
                net_value=-value,
                active_sessions=len(seller_sessions.get(code, set())),
            )
            for code, value in seller_values.items()
        ),
        key=_broker_line_sort_key,
        reverse=True,
    )[:5])

    total_buy = sum(buyer_values.values(), Decimal("0"))
    total_sell = sum(seller_values.values(), Decimal("0"))
    top_buyer_share = (
        round(float(abs(buyers[0].net_value) / total_buy * Decimal("100")), 1)
        if buyers and total_buy > Decimal("0") else None
    )
    top_seller_share = (
        round(float(abs(sellers[0].net_value) / total_sell * Decimal("100")), 1)
        if sellers and total_sell > Decimal("0") else None
    )

    through_date = max(f.date for f in window_flows)
    smart_share = _smart_share_pct(smart_flow, noise_flow, neutral_flow)
    broker_weight_quality = _broker_weight_quality(
        smart_flow=smart_flow,
        noise_flow=noise_flow,
        neutral_flow=neutral_flow,
        latest_net_flow=smart_flow + noise_flow + neutral_flow,
        smart_share_pct=smart_share,
        smart_share_threshold_pct=smart_share_threshold_pct,
    )

    if not buyers:
        quality = "no buyer detail"
    elif top_buyer_share is not None and top_buyer_share >= 60:
        quality = "concentrated accumulation"
    elif len(buyers) >= 3 and len(window_dates) >= 3:
        quality = "broad accumulation"
    elif smart_flow < Decimal("0"):
        quality = "recent distribution"
    else:
        quality = "limited accumulation detail"

    return BrokerDetail(
        window_sessions=window_sessions,
        detail_sessions=len(window_dates),
        through_date=through_date,
        source="stockbit",
        top_buyers=buyers,
        top_sellers=sellers,
        top_buyer_share_pct=top_buyer_share,
        top_seller_share_pct=top_seller_share,
        smart_flow=smart_flow,
        noise_flow=noise_flow,
        neutral_flow=neutral_flow,
        weighted_net_flow=weighted_net_flow,
        smart_share_pct=smart_share,
        broker_weight_quality=broker_weight_quality,
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
        summary
        for summary in summaries
        if summary.top_buyers or summary.top_sellers
    ][-window_sessions:]
    if not detail_summaries:
        return None

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

    for summary in detail_summaries:
        for tx in summary.top_buyers:
            if tx.net_value > Decimal("0"):
                buyer_values[tx.broker_code] = (
                    buyer_values.get(tx.broker_code, Decimal("0")) + tx.net_value
                )
                buyer_names[tx.broker_code] = tx.broker_name
                buyer_types[tx.broker_code] = tx.broker_type.value
                buyer_sessions.setdefault(tx.broker_code, set()).add(summary.date)
                add_weighted_flow(tx.broker_code, tx.net_value)
        for tx in summary.top_sellers:
            if tx.net_value < Decimal("0"):
                signed_value = tx.net_value
                seller_values[tx.broker_code] = (
                    seller_values.get(tx.broker_code, Decimal("0")) + abs(signed_value)
                )
                seller_names[tx.broker_code] = tx.broker_name
                seller_types[tx.broker_code] = tx.broker_type.value
                seller_sessions.setdefault(tx.broker_code, set()).add(summary.date)
                add_weighted_flow(tx.broker_code, signed_value)

    buyers = tuple(sorted(
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
    )[:5])
    sellers = tuple(sorted(
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
    )[:5])

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

    latest = detail_summaries[-1]
    smart_share = _smart_share_pct(
        smart_flow=smart_flow,
        noise_flow=noise_flow,
        neutral_flow=neutral_flow,
    )
    broker_weight_quality = _broker_weight_quality(
        smart_flow=smart_flow,
        noise_flow=noise_flow,
        neutral_flow=neutral_flow,
        latest_net_flow=latest.foreign_net_value,
        smart_share_pct=smart_share,
        smart_share_threshold_pct=smart_share_threshold_pct,
    )
    if latest.foreign_net_value < Decimal("0"):
        quality = "recent distribution"
    elif top_buyer_share is not None and top_buyer_share >= 60:
        quality = "concentrated accumulation"
    elif len(buyers) >= 3 and len(detail_summaries) >= 3:
        quality = "broad accumulation"
    elif buyers:
        quality = "limited accumulation detail"
    else:
        quality = "no buyer detail"

    return BrokerDetail(
        window_sessions=window_sessions,
        detail_sessions=len(detail_summaries),
        through_date=latest.date,
        source=latest.source,
        top_buyers=buyers,
        top_sellers=sellers,
        top_buyer_share_pct=top_buyer_share,
        top_seller_share_pct=top_seller_share,
        smart_flow=smart_flow,
        noise_flow=noise_flow,
        neutral_flow=neutral_flow,
        weighted_net_flow=weighted_net_flow,
        smart_share_pct=smart_share,
        broker_weight_quality=broker_weight_quality,
        quality=quality,
    )
