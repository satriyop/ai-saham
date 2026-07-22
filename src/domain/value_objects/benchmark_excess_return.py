"""Benchmark excess-return evidence value object.

Diagnostic, unvalidated measurement of a ticker's close-to-close return minus
the benchmark's close-to-close return over an explicit number of common IDX
trading sessions. Introduced to replace the ambiguous "relative strength"
naming and the independently-sliced candle calculation that could compare
returns over different start/end dates.

This object carries NO decision authority. status=UNAVAILABLE must never be
treated as neutral, zero, passed, or fresh by any consumer.

See tasks/done/audit_signal_refactor_contract.md Task HIGH-1.

Layer: Domain
Depends on: stdlib only (dataclasses, datetime, enum)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class BenchmarkExcessReturnStatus(Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class BenchmarkExcessReturn:
    """Ticker return minus benchmark return over `window_sessions` common sessions.

    `window_sessions=5` means five close-to-close returns and therefore six
    aligned closing prices; `window_start`/`window_end` are identical for the
    ticker and the benchmark leg of the calculation.
    """

    benchmark: str
    window_sessions: int
    ticker_return_pct: float | None
    benchmark_return_pct: float | None
    excess_return_pct: float | None
    window_start: date | None
    window_end: date | None
    common_session_count: int
    status: BenchmarkExcessReturnStatus
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, BenchmarkExcessReturnStatus):
            raise ValueError(
                "BenchmarkExcessReturn status must be a BenchmarkExcessReturnStatus, "
                f"got {self.status!r}"
            )
        if self.status == BenchmarkExcessReturnStatus.AVAILABLE:
            if (
                self.ticker_return_pct is None
                or self.benchmark_return_pct is None
                or self.excess_return_pct is None
                or self.window_start is None
                or self.window_end is None
            ):
                raise ValueError(
                    "AVAILABLE BenchmarkExcessReturn requires component returns, "
                    "excess return, and window_start/window_end"
                )
        elif not self.unavailable_reason:
            raise ValueError("UNAVAILABLE BenchmarkExcessReturn requires unavailable_reason")

    def to_dict(self) -> dict:
        return {
            "benchmark": self.benchmark,
            "window_sessions": self.window_sessions,
            "ticker_return_pct": self.ticker_return_pct,
            "benchmark_return_pct": self.benchmark_return_pct,
            "excess_return_pct": self.excess_return_pct,
            "window_start": self.window_start.isoformat() if self.window_start else None,
            "window_end": self.window_end.isoformat() if self.window_end else None,
            "common_session_count": self.common_session_count,
            "status": self.status.value,
            "unavailable_reason": self.unavailable_reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BenchmarkExcessReturn":
        window_start = data.get("window_start")
        window_end = data.get("window_end")
        return cls(
            benchmark=data["benchmark"],
            window_sessions=int(data["window_sessions"]),
            ticker_return_pct=data.get("ticker_return_pct"),
            benchmark_return_pct=data.get("benchmark_return_pct"),
            excess_return_pct=data.get("excess_return_pct"),
            window_start=date.fromisoformat(window_start) if window_start else None,
            window_end=date.fromisoformat(window_end) if window_end else None,
            common_session_count=int(data.get("common_session_count", 0)),
            status=BenchmarkExcessReturnStatus(data["status"]),
            unavailable_reason=data.get("unavailable_reason"),
        )

    @classmethod
    def unavailable(
        cls,
        *,
        benchmark: str,
        window_sessions: int,
        reason: str,
        common_session_count: int = 0,
    ) -> "BenchmarkExcessReturn":
        return cls(
            benchmark=benchmark,
            window_sessions=window_sessions,
            ticker_return_pct=None,
            benchmark_return_pct=None,
            excess_return_pct=None,
            window_start=None,
            window_end=None,
            common_session_count=common_session_count,
            status=BenchmarkExcessReturnStatus.UNAVAILABLE,
            unavailable_reason=reason,
        )
