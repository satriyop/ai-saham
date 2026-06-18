"""
BandarDetectorSnapshot value object.

Holds Stockbit's proprietary bandar (institutional operator) accumulation/distribution
signal for a ticker on a given trading session.

`broker_accdist` ("Acc" | "Dis" | "Neutral") is Stockbit's top-level signal.
`today_accdist` / `five_day_accdist` / `top1_accdist` carry intensity labels:
  "Big Acc" > "Normal Acc" > "Small Acc" > "Neutral" > "Small Dis" > "Normal Dis" > "Big Dis"

Sourced from Stockbit /marketdetectors/{ticker}?transaction_type=TRANSACTION_TYPE_NET...

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
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

    _INTENSITY_SCORE: ClassVar[dict[str, int]] = {
        "Big Acc":    3,
        "Normal Acc": 2,
        "Small Acc":  1,
        "Neutral":    0,
        "Small Dis": -1,
        "Normal Dis": -2,
        "Big Dis":   -3,
    }

    @property
    def is_accumulating(self) -> bool:
        return self.broker_accdist == "Acc"

    @property
    def is_distributing(self) -> bool:
        return self.broker_accdist == "Dis"

    @property
    def accumulation_score(self) -> int:
        """Composite intensity score: today + 5-day + top1, range -9 to +9."""
        return sum(
            self._INTENSITY_SCORE.get(x, 0)
            for x in [self.today_accdist, self.five_day_accdist, self.top1_accdist]
        )

    @property
    def label(self) -> str:
        return (
            f"{self.broker_accdist} | today={self.today_accdist} "
            f"| 5d={self.five_day_accdist} | top1={self.top1_accdist}({self.top1_percent:.0f}%)"
        )

    def to_dict(self) -> dict:
        return {
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
        }
