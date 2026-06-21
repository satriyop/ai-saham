"""Ticker notation/status context from exchange-facing metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class TickerNotation:
    code: str
    description: str

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "description": self.description,
        }


@dataclass(frozen=True)
class TickerNotationSnapshot:
    ticker: str
    status: str | None = None
    tradeable: bool | None = None
    listing_board: str | None = None
    sector: str | None = None
    sub_sector: str | None = None
    haircut_percentage: str | None = None
    notations: list[TickerNotation] = field(default_factory=list)
    market_status: str | None = None
    suspend_info: str | None = None
    corp_action_active: bool | None = None
    has_uma: bool | None = None
    catalogs: list[str] = field(default_factory=list)
    source: str = "stockbit"
    fetched_at: datetime | None = None

    @property
    def codes(self) -> list[str]:
        return [n.code for n in self.notations if n.code]

    @property
    def codes_label(self) -> str:
        return ",".join(self.codes) if self.codes else "-"

    @property
    def has_warning(self) -> bool:
        return bool(
            self.notations
            or self.status not in (None, "", "STATUS_ACTIVE")
            or self.tradeable is False
            or self.suspend_info
            or self.has_uma
        )

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "status": self.status,
            "tradeable": self.tradeable,
            "listing_board": self.listing_board,
            "sector": self.sector,
            "sub_sector": self.sub_sector,
            "haircut_percentage": self.haircut_percentage,
            "notations": [n.to_dict() for n in self.notations],
            "market_status": self.market_status,
            "suspend_info": self.suspend_info,
            "corp_action_active": self.corp_action_active,
            "has_uma": self.has_uma,
            "catalogs": self.catalogs,
            "source": self.source,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }
