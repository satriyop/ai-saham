"""
MacroCalendarEvent — immutable value object for a single macroeconomic calendar event.

Distinct from CorporateActionCalendarEvent: no ticker, no CA date roles, no
price-distortion semantics. Used by `saham fetch macro-calendar` (Stockbit
economic endpoint and future macro sources).

Layer: Domain
Dependencies: None (pure value objects, zero I/O imports)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class MacroEventCategory(str, Enum):
    """Normalized macro event categories for filtering and P2 consumers."""

    BI_RATE = "bi_rate"
    INFLATION = "inflation"
    GROWTH = "growth"
    TRADE = "trade"
    OTHER = "other"


@dataclass(frozen=True)
class MacroCalendarEvent:
    """A market-wide macroeconomic calendar event (no ticker).

    `source_event_id` is required and must be stable across re-syncs (prefer
    provider id; fall back to a deterministic hash in the provider/parser).
    Value fields (actual/previous/forecast) stay as raw strings — Stockbit
    returns mixed formats like ``"12.0%"``.
    """

    source_event_id: str
    event_date: date
    category: MacroEventCategory
    title: str
    event_time: str | None = None
    timezone: str | None = None
    country: str = "ID"
    actual: str | None = None
    previous: str | None = None
    forecast: str | None = None
    reference_period: str | None = None
    source: str = "stockbit"
    raw_payload_json: str = "{}"
    fetched_at: str = ""  # ISO datetime string

    def __post_init__(self) -> None:
        if not self.source_event_id or not str(self.source_event_id).strip():
            raise ValueError("source_event_id is required")
        title = (self.title or "").strip()
        if not title:
            raise ValueError("title is required")
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "source_event_id", str(self.source_event_id).strip())
        country = (self.country or "").strip() or "ID"
        object.__setattr__(self, "country", country)
