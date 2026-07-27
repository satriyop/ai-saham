"""
MarketStatus — IDX market session state value object.

Returned by MarketStatusProvider implementations. Carries the canonical
Stockbit STATUS_OPEN / STATUS_CLOSE contract plus the current session name
so callers can distinguish Pre-Open from Regular trading.

Layer: Domain (value object)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MarketStatus:
    status: str  # "STATUS_OPEN" | "STATUS_CLOSE"
    session_name: str  # "Pre-Open" | "Opening Call Auction" | "Regular" |
    # "Pre-Closing" | "Closing" | "Post-Market" |
    # "Weekend" | "Unknown"
    is_open: bool  # True only during STATUS_OPEN sessions
    session_open: str | None  # WIB time string, e.g. "08:45"
    session_close: str | None  # WIB time string, e.g. "09:00"
    fetched_at: datetime
    source: str  # "stockbit" | "local_clock"

    @property
    def is_pre_open(self) -> bool:
        name = self.session_name.lower()
        return "pre-open" in name or "pre open" in name or name == "pre-open"

    @property
    def is_regular(self) -> bool:
        return "regular" in self.session_name.lower()

    @property
    def is_weekend(self) -> bool:
        return self.session_name.lower() == "weekend"

    def __str__(self) -> str:
        return (
            f"MarketStatus({self.status} / {self.session_name} / "
            f"is_open={self.is_open} / source={self.source})"
        )
