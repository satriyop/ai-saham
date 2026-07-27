"""
ForwardEstimates value object.

Holds next-year analyst estimates for EPS and Revenue sourced from Stockbit
/analyst-ratings/{ticker}/consensus endpoint. Forward PE is derived.

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


def derive_forward_pe(
    forward_eps_1y: float | None,
    current_price: float | None,
) -> float | None:
    """Derive forward P/E from EPS and price when both are usable."""
    if forward_eps_1y and current_price and forward_eps_1y > 0:
        return round(current_price / forward_eps_1y, 1)
    return None


@dataclass(frozen=True)
class ForwardEstimates:
    ticker: str
    forward_eps_1y: float | None  # next-year EPS estimate (IDR per share)
    revenue_forward_1y: (
        float | None
    )  # next-year revenue estimate (IDR, billions "B" suffix stripped)
    current_price: float | None  # close price at time of estimate fetch
    forward_pe: float | None  # current_price / forward_eps_1y
    fetched_at: datetime | None = None

    @classmethod
    def compute(
        cls,
        ticker: str,
        forward_eps_1y: float | None,
        revenue_forward_1y: float | None,
        current_price: float | None,
        fetched_at: datetime | None = None,
    ) -> "ForwardEstimates":
        fpe = derive_forward_pe(forward_eps_1y, current_price)
        return cls(
            ticker=ticker,
            forward_eps_1y=forward_eps_1y,
            revenue_forward_1y=revenue_forward_1y,
            current_price=current_price,
            forward_pe=fpe,
            fetched_at=fetched_at,
        )

    def with_current_price(self, current_price: float | None) -> "ForwardEstimates":
        """Return a copy using a canonical analysis price for derived forward P/E."""
        return self.compute(
            ticker=self.ticker,
            forward_eps_1y=self.forward_eps_1y,
            revenue_forward_1y=self.revenue_forward_1y,
            current_price=current_price,
            fetched_at=self.fetched_at,
        )

    def to_dict(self) -> dict:
        d: dict = {"fetched_at": self.fetched_at.isoformat() if self.fetched_at else None}
        if self.forward_eps_1y is not None:
            d["forward_eps_1y"] = self.forward_eps_1y
        if self.revenue_forward_1y is not None:
            d["revenue_forward_1y"] = self.revenue_forward_1y
        if self.current_price is not None:
            d["current_price"] = self.current_price
        if self.forward_pe is not None:
            d["forward_pe"] = self.forward_pe
        return d
