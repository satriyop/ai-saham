"""
Corporate action calendar value objects — market-wide calendar events (distinct
from the per-ticker CorporateActionEvent in corporate_action_event.py).

These are fetched once per `saham fetch market` run from Stockbit's market-wide
corporate action endpoints (dividend, split, rights issue, RUPS, IPO, etc.) and
persisted in normalized SQLite tables, queryable by ticker/universe/date-window.

Layer: Domain
Dependencies: None (pure value objects, zero I/O imports)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class CorporateActionType(str, Enum):
    DIVIDEND = "dividend"
    STOCK_SPLIT = "stock_split"
    REVERSE_SPLIT = "reverse_split"
    RIGHTS_ISSUE = "rights_issue"
    BONUS = "bonus"
    TENDER_OFFER = "tender_offer"
    RUPS = "rups"
    PUBEX = "pubex"
    IPO = "ipo"


class CorporateActionDateRole(str, Enum):
    CUM_DATE = "cum_date"
    EX_DATE = "ex_date"
    RECORDING_DATE = "recording_date"
    PAYMENT_DATE = "payment_date"
    SUBSCRIPTION_DATE = "subscription_date"
    TRADING_START = "trading_start"
    TRADING_END = "trading_end"
    OFFER_START = "offer_start"
    OFFER_END = "offer_end"
    RUPS_DATE = "rups_date"
    ELIGIBLE_DATE = "eligible_date"
    PUBEX_DATE = "pubex_date"
    LISTING_DATE = "listing_date"
    ALLOTMENT_DATE = "allotment_date"
    REFUND_DATE = "refund_date"
    OFFERING_START = "offering_start"
    OFFERING_END = "offering_end"


@dataclass(frozen=True)
class CorporateActionCalendarDate:
    """A single dated milestone (role + date) belonging to a calendar event."""

    date_role: CorporateActionDateRole
    event_date: date
    event_time: str | None = None
    timezone: str | None = None


@dataclass(frozen=True)
class CorporateActionCalendarEvent:
    """A market-wide corporate action calendar event for a single ticker.

    One event carries one or more dated milestones (`dates`). The ticker is
    normalized to uppercase; `source_event_id` and `ticker` are required.
    """

    event_type: CorporateActionType
    source_event_id: str
    ticker: str
    dates: tuple[CorporateActionCalendarDate, ...]
    source: str = "stockbit"
    company_id: str | None = None
    company_name: str | None = None
    active: bool = False
    event_note: str | None = None
    amount_value: str | None = None
    amount_currency: str | None = None
    ratio_old: str | None = None
    ratio_new: str | None = None
    price: str | None = None
    raw_payload_json: str = "{}"
    fetched_at: str = ""  # ISO datetime string

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", self.ticker.upper())
        if not self.source_event_id:
            raise ValueError("source_event_id is required")
        if not self.ticker:
            raise ValueError("ticker is required")
