"""Benchmark excess-return calculator.

Layer: Application
Depends on: domain value objects + stdlib only. No repository, provider,
config, or CLI dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from src.domain.value_objects.benchmark_excess_return import (
    BenchmarkExcessReturn,
    BenchmarkExcessReturnStatus,
)

if TYPE_CHECKING:
    from src.domain.entities.candle import Candle

_WINDOW_5_SESSION = 5
_WINDOW_20_SESSION = 20


@dataclass(frozen=True)
class BenchmarkExcessReturnResult:
    """Typed benchmark excess-return evidence for both measured horizons."""

    excess_return_vs_ihsg_5_session: BenchmarkExcessReturn
    excess_return_vs_ihsg_20_session: BenchmarkExcessReturn


class BenchmarkExcessReturnCalculator:
    """Pure calculator: ticker close-to-close return minus benchmark
    close-to-close return, in percentage points, over common aligned IDX
    session dates.

    Never raises. Insufficient aligned closes, a zero base close, or
    conflicting duplicate candles resolve to `BenchmarkExcessReturnStatus.
    UNAVAILABLE` for that window rather than 0.0, a neutral value, or a
    fabricated ratio.
    """

    def calculate(
        self,
        *,
        ticker_candles: list["Candle"],
        benchmark_candles: list["Candle"],
        as_of_date: date,
        benchmark: str = "IHSG",
    ) -> BenchmarkExcessReturnResult:
        ticker_closes, ticker_conflict = self._closes_by_date(ticker_candles, as_of_date)
        benchmark_closes, benchmark_conflict = self._closes_by_date(benchmark_candles, as_of_date)
        conflict_reason = ticker_conflict or benchmark_conflict

        windows: dict[int, BenchmarkExcessReturn] = {}
        for window in (_WINDOW_5_SESSION, _WINDOW_20_SESSION):
            if conflict_reason is not None:
                windows[window] = BenchmarkExcessReturn.unavailable(
                    benchmark=benchmark,
                    window_sessions=window,
                    reason=conflict_reason,
                    common_session_count=0,
                )
            else:
                windows[window] = self._for_window(
                    ticker_closes=ticker_closes,
                    benchmark_closes=benchmark_closes,
                    window=window,
                    benchmark=benchmark,
                )

        return BenchmarkExcessReturnResult(
            excess_return_vs_ihsg_5_session=windows[_WINDOW_5_SESSION],
            excess_return_vs_ihsg_20_session=windows[_WINDOW_20_SESSION],
        )

    @staticmethod
    def _closes_by_date(
        candles: list["Candle"], as_of_date: date
    ) -> tuple[dict[date, Decimal], str | None]:
        """Build a date->close map, excluding rows after as_of_date.

        Conflicting duplicate candles (same date, different close) fail
        closed: the whole series is reported as unusable rather than
        arbitrarily picking one of the conflicting values.
        """
        closes: dict[date, Decimal] = {}
        for candle in candles:
            if candle.date > as_of_date:
                continue
            existing = closes.get(candle.date)
            if existing is not None and existing != candle.close:
                return {}, "conflicting_duplicate_candles"
            closes[candle.date] = candle.close
        return closes, None

    @staticmethod
    def _for_window(
        *,
        ticker_closes: dict[date, Decimal],
        benchmark_closes: dict[date, Decimal],
        window: int,
        benchmark: str,
    ) -> BenchmarkExcessReturn:
        common_dates = sorted(set(ticker_closes) & set(benchmark_closes))
        common_session_count = len(common_dates)
        required = window + 1

        if common_session_count < required:
            return BenchmarkExcessReturn.unavailable(
                benchmark=benchmark,
                window_sessions=window,
                reason=f"insufficient_aligned_closes_{window}_session",
                common_session_count=common_session_count,
            )

        window_start = common_dates[-required]
        window_end = common_dates[-1]
        ticker_then = ticker_closes[window_start]
        ticker_now = ticker_closes[window_end]
        benchmark_then = benchmark_closes[window_start]
        benchmark_now = benchmark_closes[window_end]

        if ticker_then == 0 or benchmark_then == 0:
            return BenchmarkExcessReturn.unavailable(
                benchmark=benchmark,
                window_sessions=window,
                reason="zero_base_close",
                common_session_count=common_session_count,
            )

        ticker_return_pct = float((ticker_now - ticker_then) / ticker_then * Decimal("100"))
        benchmark_return_pct = float(
            (benchmark_now - benchmark_then) / benchmark_then * Decimal("100")
        )
        excess_return_pct = round(ticker_return_pct - benchmark_return_pct, 4)

        return BenchmarkExcessReturn(
            benchmark=benchmark,
            window_sessions=window,
            ticker_return_pct=round(ticker_return_pct, 4),
            benchmark_return_pct=round(benchmark_return_pct, 4),
            excess_return_pct=excess_return_pct,
            window_start=window_start,
            window_end=window_end,
            common_session_count=required,
            status=BenchmarkExcessReturnStatus.AVAILABLE,
            unavailable_reason=None,
        )
