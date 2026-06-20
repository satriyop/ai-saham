"""
IntradayBrokerChart value objects.

Holds per-minute cumulative net buy/sell value per stock for a single broker's
top traded stocks on a given day. Sourced from Stockbit broker/activity-chart endpoint.

This is broker-centric (query by broker code, returns their top stocks) — the inverse
of the ticker-centric RunningTradeChart.

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class IntradayBrokerChartPoint:
    time: str          # "09:00"
    net_value: Decimal  # IDR cumulative net buy/sell; negative = net sell


@dataclass(frozen=True)
class IntradayBrokerSymbolChart:
    symbol: str        # ticker, e.g. "EMAS"
    points: tuple[IntradayBrokerChartPoint, ...]

    @property
    def final_net_value(self) -> Decimal:
        """Last point's cumulative value = total net for the session so far."""
        return self.points[-1].net_value if self.points else Decimal(0)

    @property
    def is_accumulating(self) -> bool:
        return self.final_net_value > Decimal(0)

    @property
    def peak_net_value(self) -> Decimal:
        """Maximum cumulative net value (peak buy pressure)."""
        if not self.points:
            return Decimal(0)
        return max(p.net_value for p in self.points)


@dataclass(frozen=True)
class IntradayBrokerChart:
    broker_code: str    # e.g. "XL"
    broker_name: str    # e.g. "Stockbit Sekuritas Digital" (may be empty)
    date: date
    fetched_at: datetime
    symbols: tuple[IntradayBrokerSymbolChart, ...]

    def get_symbol(self, ticker: str) -> IntradayBrokerSymbolChart | None:
        ticker = ticker.upper()
        return next((s for s in self.symbols if s.symbol == ticker), None)

    @property
    def accumulating_symbols(self) -> list[str]:
        return [s.symbol for s in self.symbols if s.is_accumulating]

    @property
    def distributing_symbols(self) -> list[str]:
        return [s.symbol for s in self.symbols if not s.is_accumulating]

    def to_dict(self) -> dict:
        return {
            "broker_code": self.broker_code,
            "broker_name": self.broker_name,
            "date": self.date.isoformat(),
            "fetched_at": self.fetched_at.isoformat(),
            "accumulating": self.accumulating_symbols,
            "distributing": self.distributing_symbols,
        }
