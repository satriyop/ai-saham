"""
Relative strength vs IHSG calculator.

Computes ticker return minus benchmark return over N trading sessions, as
percentage points (e.g. ticker +4.0%, IHSG +1.5% => 2.5). This is deliberately
NOT the RS_IHSG indicator plugin's ratio formula (stock_return / ihsg_return,
1.0 fallback for missing data) — that formula and its missing-data fallback
are wrong for observation/attribution use: a fabricated 1.0 would be
indistinguishable from genuine "matches IHSG exactly" evidence. This
calculator returns None, never a fabricated number, when data is
insufficient.

Layer: Application
Depends on: domain entities (Candle) + stdlib only. No IO, repositories,
providers, CLI, or AI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.entities.candle import Candle

_DEFAULT_WINDOWS: tuple[int, ...] = (5, 20)


@dataclass(frozen=True)
class RelativeStrengthResult:
    """Ticker return minus benchmark return over each configured window."""

    rs_vs_ihsg_5d: float | None
    rs_vs_ihsg_20d: float | None
    unavailable_reasons: tuple[str, ...] = ()


class RelativeStrengthCalculator:
    """Pure calculator: ticker return vs benchmark return, in percentage points.

    Never raises. Missing/insufficient candles or a zero base close resolve to
    None for that window rather than 0.0 or a fabricated ratio.
    """

    def calculate(
        self,
        *,
        ticker_candles: list["Candle"],
        benchmark_candles: list["Candle"],
        as_of_date: date,
        windows: tuple[int, ...] = _DEFAULT_WINDOWS,
    ) -> RelativeStrengthResult:
        ticker_closes = self._closes_as_of(ticker_candles, as_of_date)
        benchmark_closes = self._closes_as_of(benchmark_candles, as_of_date)

        values: dict[int, float | None] = {}
        reasons: list[str] = []
        for window in windows:
            value, window_reasons = self._rs_for_window(
                ticker_closes=ticker_closes,
                benchmark_closes=benchmark_closes,
                window=window,
            )
            values[window] = value
            reasons.extend(window_reasons)

        return RelativeStrengthResult(
            rs_vs_ihsg_5d=values.get(5),
            rs_vs_ihsg_20d=values.get(20),
            unavailable_reasons=tuple(reasons),
        )

    @staticmethod
    def _closes_as_of(candles: list["Candle"], as_of_date: date) -> list[Decimal]:
        valid = [c for c in candles if c.date <= as_of_date]
        valid.sort(key=lambda c: c.date)
        return [c.close for c in valid]

    @staticmethod
    def _rs_for_window(
        *,
        ticker_closes: list[Decimal],
        benchmark_closes: list[Decimal],
        window: int,
    ) -> tuple[float | None, list[str]]:
        required = window + 1
        if len(ticker_closes) < required:
            return None, [f"insufficient_ticker_candles_{window}d"]
        if len(benchmark_closes) < required:
            return None, [f"insufficient_benchmark_candles_{window}d"]

        ticker_now, ticker_then = ticker_closes[-1], ticker_closes[-required]
        benchmark_now, benchmark_then = benchmark_closes[-1], benchmark_closes[-required]

        if ticker_then == 0 or benchmark_then == 0:
            return None, [f"zero_base_close_{window}d"]

        ticker_return_pct = (ticker_now - ticker_then) / ticker_then * Decimal("100")
        benchmark_return_pct = (
            (benchmark_now - benchmark_then) / benchmark_then * Decimal("100")
        )
        rs = ticker_return_pct - benchmark_return_pct
        return round(float(rs), 4), []
