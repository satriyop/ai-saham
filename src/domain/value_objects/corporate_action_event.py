"""
CorporateActionEvent — immutable value object for a single corporate action.

Covers dividend ex-dates, rights issues, RUPS, splits, and other IDX events.
Sourced from Stockbit /corpaction/{ticker} endpoint.

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class CorporateActionEvent:
    """A single upcoming or recent corporate action for a ticker.

    Attributes:
        ticker:            IDX ticker symbol
        event_type:        Normalised type string (see TYPE_* constants below)
        ex_date:           Ex-date (most relevant for dividend and rights issue)
        cum_date:          Cum-date (last date to hold for entitlement)
        record_date:       Recording/book-close date
        payment_date:      Dividend payment or rights proceeds settlement date
        announcement_date: Date of official announcement
        detail:            Human-readable summary, e.g. "Rp 35/share" or "1:5 split"
        status:            "announced" | "completed" | "cancelled" | "" if unknown
    """

    ticker: str
    event_type: str        # normalised — use TYPE_* constants
    ex_date: date | None = None
    cum_date: date | None = None
    record_date: date | None = None
    payment_date: date | None = None
    announcement_date: date | None = None
    detail: str = ""
    status: str = ""

    # Normalised event_type constants
    TYPE_DIVIDEND     = "DIVIDEND"
    TYPE_RIGHTS_ISSUE = "RIGHTS_ISSUE"
    TYPE_RUPS         = "RUPS"
    TYPE_SPLIT        = "SPLIT"
    TYPE_BONUS        = "BONUS"
    TYPE_WARRANT      = "WARRANT"
    TYPE_IPO          = "IPO"
    TYPE_TENDER_OFFER = "TENDER_OFFER"
    TYPE_OTHER        = "OTHER"

    @property
    def is_dividend(self) -> bool:
        return self.event_type == self.TYPE_DIVIDEND

    @property
    def is_rights_issue(self) -> bool:
        return self.event_type == self.TYPE_RIGHTS_ISSUE

    @property
    def is_rups(self) -> bool:
        return self.event_type == self.TYPE_RUPS

    @property
    def earliest_relevant_date(self) -> date | None:
        """The earliest date that matters for hold-window risk checks."""
        return self.ex_date or self.cum_date or self.record_date or self.announcement_date
