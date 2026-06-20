"""
RunningTradeChart value objects.

Holds per-minute intraday price bars and top-broker cumulative net value lines
for a single ticker and trading day. Sourced from Stockbit running-trade/chart endpoint.

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class IntradayPriceBar:
    time: str        # "09:00" — minute-level timestamp
    close: int       # value.raw (IDR price)
    open: int | None
    high: int | None
    low: int | None


@dataclass(frozen=True)
class IntradayBrokerBar:
    broker_code: str
    time: str        # "09:00"
    net_value: Decimal   # IDR cumulative net buy/sell; negative = net seller


@dataclass(frozen=True)
class RunningTradeChart:
    ticker: str
    date: date
    fetched_at: datetime
    price_bars: tuple[IntradayPriceBar, ...]
    broker_bars: tuple[IntradayBrokerBar, ...]  # all brokers flattened, sorted by (broker_code, time)

    @property
    def top_broker_codes(self) -> list[str]:
        """Unique broker codes in order of first appearance."""
        seen: list[str] = []
        for bar in self.broker_bars:
            if bar.broker_code not in seen:
                seen.append(bar.broker_code)
        return seen

    @property
    def open_price(self) -> int | None:
        return self.price_bars[0].open if self.price_bars else None

    @property
    def close_price(self) -> int | None:
        return self.price_bars[-1].close if self.price_bars else None

    def broker_final_net(self, broker_code: str) -> Decimal:
        """Last recorded cumulative net value for a broker (= total session net)."""
        bars = [b for b in self.broker_bars if b.broker_code == broker_code]
        return bars[-1].net_value if bars else Decimal(0)

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "date": self.date.isoformat(),
            "fetched_at": self.fetched_at.isoformat(),
            "bar_count": len(self.price_bars),
            "broker_codes": self.top_broker_codes,
            "open_price": self.open_price,
            "close_price": self.close_price,
        }
