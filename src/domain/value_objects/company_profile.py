"""
CompanyProfile value object.

Holds core company information sourced from Stockbit /emitten/{ticker}/profile.
Includes IPO history, listing board, contact info, and background description.

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CompanyProfile:
    ticker: str
    background: str | None          # company description (Indonesian)
    listing_board: str | None       # "Papan Utama" | "Papan Pengembangan" | "Papan Akselerasi"
    ipo_date: str | None            # "31 May 2000" (kept as-is — locale format)
    ipo_price: int | None           # IDR per share at IPO
    ipo_amount: str | None          # e.g. "927 B" (total IPO proceeds)
    website: str | None
    email: str | None               # primary investor relations email
    office_address: str | None
    fetched_at: datetime | None = None

    def to_dict(self) -> dict:
        d: dict = {"fetched_at": self.fetched_at.isoformat() if self.fetched_at else None}
        if self.background is not None:
            d["background"] = self.background[:200] + "..." if len(self.background or "") > 200 else self.background
        if self.listing_board is not None:
            d["listing_board"] = self.listing_board
        if self.ipo_date is not None:
            d["ipo_date"] = self.ipo_date
        if self.ipo_price is not None:
            d["ipo_price"] = self.ipo_price
        if self.ipo_amount is not None:
            d["ipo_amount"] = self.ipo_amount
        if self.website is not None:
            d["website"] = self.website
        if self.email is not None:
            d["email"] = self.email
        if self.office_address is not None:
            d["office_address"] = self.office_address
        return d
