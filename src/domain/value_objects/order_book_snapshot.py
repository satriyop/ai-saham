"""
OrderBookSnapshot value object.

Captures key metrics from a full order book fetch for one ticker at one moment.
Used by the opening track workflow to monitor bid/offer depth and live foreign flow.

Fields:
  total_bid_lots / total_offer_lots  — aggregate across ALL price levels (not just top-of-book)
  bid_pressure_ratio                 — total_bid / (total_bid + total_offer); >0.5 = bid-side dominant
  fnet_intraday                      — live running foreign net value for today (IDR)
  depth_ratio_5                      — bid depth top-5 levels / offer depth top-5 levels
  iep / iev                          — pre-open Indicative Equilibrium Price/Volume (None during regular session)

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class OrderBookSnapshot:
    ticker: str
    captured_at: datetime
    last_price: float
    best_bid_price: float
    best_offer_price: float
    total_bid_lots: int               # ALL bid queue lots across all price levels
    total_offer_lots: int             # ALL offer queue lots across all price levels
    bid_depth_5: int                  # sum of bid volume at top-5 price levels (nearest last price)
    offer_depth_5: int                # sum of offer volume at top-5 price levels
    fnet_intraday: float | None       # live running foreign net value today (IDR)
    fbuy_intraday: float | None       # live foreign buy value today
    fsell_intraday: float | None      # live foreign sell value today
    iep: float | None = None          # Indicative Equilibrium Price (pre-open only)
    iev: int | None = None            # Indicative Equilibrium Volume lots (pre-open only)
    ara_price: float | None = None    # auto-reject ceiling (IDR; hard daily price cap)
    arb_price: float | None = None    # auto-reject floor (IDR; hard daily price floor)
    foreign_pct: float | None = None  # % of total daily value from foreign investors
    domestic_pct: float | None = None # % of total daily value from domestic investors

    @property
    def bid_pressure_ratio(self) -> float | None:
        total = self.total_bid_lots + self.total_offer_lots
        return round(self.total_bid_lots / total, 4) if total > 0 else None

    @property
    def depth_ratio_5(self) -> float | None:
        if self.offer_depth_5 > 0:
            return round(self.bid_depth_5 / self.offer_depth_5, 3)
        return None

    @property
    def spread(self) -> float:
        return self.best_offer_price - self.best_bid_price

    @property
    def label(self) -> str:
        bp = self.bid_pressure_ratio
        fnet = self.fnet_intraday
        parts = []
        if bp is not None:
            side = "BID" if bp > 0.5 else "OFFER"
            parts.append(f"Pressure {bp:.0%} {side}")
        if fnet is not None:
            sign = "+" if fnet >= 0 else ""
            parts.append(f"F.Net {sign}{fnet/1e9:.1f}B")
        if self.iep:
            parts.append(f"IEP {self.iep:,.0f} IEV {self.iev or 0:,}L")
        return " | ".join(parts) if parts else "N/A"

    def to_dict(self) -> dict:
        d = {
            "last_price": self.last_price,
            "best_bid": self.best_bid_price,
            "best_offer": self.best_offer_price,
            "spread": self.spread,
            "total_bid_lots": self.total_bid_lots,
            "total_offer_lots": self.total_offer_lots,
            "bid_pressure_ratio": self.bid_pressure_ratio,
            "bid_depth_5": self.bid_depth_5,
            "offer_depth_5": self.offer_depth_5,
            "depth_ratio_5": self.depth_ratio_5,
            "fnet_intraday": self.fnet_intraday,
            "fbuy_intraday": self.fbuy_intraday,
            "fsell_intraday": self.fsell_intraday,
            "iep": self.iep,
            "iev": self.iev,
        }
        if self.ara_price is not None:
            d["ara_price"] = self.ara_price
        if self.arb_price is not None:
            d["arb_price"] = self.arb_price
        if self.foreign_pct is not None:
            d["foreign_pct"] = self.foreign_pct
        if self.domestic_pct is not None:
            d["domestic_pct"] = self.domestic_pct
        return d
