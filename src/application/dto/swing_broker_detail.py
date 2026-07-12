"""
DTOs for swing broker details.

Layer: Application (DTO)
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class BrokerQualityNote:
    """Non-authoritative named-broker confirmation note for setup review."""

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
