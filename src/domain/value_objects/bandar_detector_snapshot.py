"""
BandarDetectorSnapshot value object.

Holds Stockbit's proprietary bandar (institutional operator) accumulation/distribution
signal for a ticker on a given trading session.

`broker_accdist` ("Acc" | "Dis" | "Neutral") is Stockbit's top-level signal.
`today_accdist` / `five_day_accdist` / `top1_accdist` / `top3_accdist` / `top5_accdist` /
`top10_accdist` carry intensity labels (confirmed from API probe 2026-06-20, BBCA):
  "Big Acc" > "Small Acc" > "Neutral" > "Small Dist" > "Big Dist"

Sourced from Stockbit /marketdetectors/{ticker}?transaction_type=TRANSACTION_TYPE_NET...

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import ClassVar


@dataclass(frozen=True)
class BandarDetectorSnapshot:
    ticker: str
    session_date: date
    broker_accdist: str        # "Acc" | "Dis" | "Neutral"
    today_accdist: str         # avg.accdist — today's intensity label
    five_day_accdist: str      # avg5.accdist — 5-session moving label
    top1_accdist: str          # top1.accdist — single-largest operator pattern
    top1_percent: float        # top1.percent — concentration % of largest operator
    today_percent: float       # avg.percent — avg net % of total volume
    total_buyer: int           # number of broker codes on buy side
    total_seller: int          # number of broker codes on sell side

    # Extended fields (added 2026-06-20 from API probe)
    top3_accdist: str | None = None    # top3.accdist — top-3 brokers smoothed signal
    top5_accdist: str | None = None    # top5.accdist — top-5 brokers smoothed signal
    top10_accdist: str | None = None   # top10.accdist — top-10 brokers smoothed signal
    number_broker_buysell: int | None = None  # negative = more sellers than buyers
    vwap: Decimal | None = None        # average — VWAP for the session
    total_value: Decimal | None = None # value — total traded value (IDR)
    total_volume: int | None = None    # volume — total traded volume (lots)

    # Confirmed 5-level ordinal from API probe 2026-06-20.
    # Backward-compat aliases ("Dis", "Normal" variants) retained for cached rows.
    _INTENSITY_SCORE: ClassVar[dict[str, int]] = {
        "Big Acc":    2,
        "Small Acc":  1,
        "Neutral":    0,
        "Small Dist": -1,
        "Big Dist":   -2,
        # backward-compat aliases
        "Small Dis":  -1,
        "Big Dis":    -2,
        "Normal Acc": 1,
        "Normal Dis": -1,
    }

    @property
    def is_accumulating(self) -> bool:
        return self.broker_accdist == "Acc"

    @property
    def is_distributing(self) -> bool:
        return self.broker_accdist in {"Dis", "Dist"}

    @property
    def accumulation_score(self) -> int:
        """Composite intensity score: today + 5-day + top1, range -6 to +6."""
        return sum(
            self._INTENSITY_SCORE.get(x, 0)
            for x in [self.today_accdist, self.five_day_accdist, self.top1_accdist]
        )

    @property
    def broad_score(self) -> int:
        """Score using all available accdist signals (today, 5d, top1, top3, top5, top10)."""
        return sum(
            self._INTENSITY_SCORE.get(x, 0)
            for x in [
                self.today_accdist, self.five_day_accdist,
                self.top1_accdist, self.top3_accdist,
                self.top5_accdist, self.top10_accdist,
            ]
            if x is not None
        )

    @property
    def label(self) -> str:
        return (
            f"{self.broker_accdist} | today={self.today_accdist} "
            f"| 5d={self.five_day_accdist} | top1={self.top1_accdist}({self.top1_percent:.0f}%)"
        )

    def to_dict(self) -> dict:
        d = {
            "session_date": self.session_date.isoformat(),
            "broker_accdist": self.broker_accdist,
            "today_accdist": self.today_accdist,
            "five_day_accdist": self.five_day_accdist,
            "top1_accdist": self.top1_accdist,
            "top1_percent": round(self.top1_percent, 2),
            "today_percent": round(self.today_percent, 2),
            "total_buyer": self.total_buyer,
            "total_seller": self.total_seller,
            "accumulation_score": self.accumulation_score,
            "broad_score": self.broad_score,
        }
        if self.top3_accdist is not None:
            d["top3_accdist"] = self.top3_accdist
        if self.top5_accdist is not None:
            d["top5_accdist"] = self.top5_accdist
        if self.top10_accdist is not None:
            d["top10_accdist"] = self.top10_accdist
        if self.number_broker_buysell is not None:
            d["number_broker_buysell"] = self.number_broker_buysell
        if self.vwap is not None:
            d["vwap"] = float(self.vwap)
        if self.total_value is not None:
            d["total_value"] = float(self.total_value)
        if self.total_volume is not None:
            d["total_volume"] = self.total_volume
        return d
