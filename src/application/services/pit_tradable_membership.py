"""Point-in-time tradable-universe membership from candle presence.

Layer: Application (policy + orchestration over MarketDataRepository).

Membership for corpus backfill is date-dependent:

* Named universe → today's named list ∩ candle-active in the last N IHSG
  sessions ending at ``as_of_date``.
* ``cached`` / board → pure candle-active (no broker-cache intersection).

This is **tradable** presence only. It does not reconstruct historical index
or eligible-universe membership (parked Slice B).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Sequence

from src.domain.ports.market_data_repository import MarketDataRepository

DEFAULT_BENCHMARK_TICKERS: frozenset[str] = frozenset({"IHSG", "^JKSE"})
DEFAULT_SESSION_PROBE_CALENDAR_DAYS = 60


def session_window_start(
    sessions: Sequence[date],
    as_of: date,
    window_sessions: int,
) -> date | None:
    """Return the inclusive start of the last ``window_sessions`` ending at as_of.

    ``sessions`` must be unique trading-session dates (typically IHSG candle
    dates). Returns ``None`` when ``as_of`` is not a known session.

    When fewer than ``window_sessions`` sessions exist before/at ``as_of``,
    uses the earliest available session (thin-history inclusive behavior).
    """
    if window_sessions < 1:
        raise ValueError(f"window_sessions must be >= 1, got {window_sessions}")
    ordered = tuple(sorted({day for day in sessions if day <= as_of}))
    if as_of not in ordered:
        return None
    end_idx = ordered.index(as_of)
    start_idx = max(0, end_idx - window_sessions + 1)
    return ordered[start_idx]


def resolve_pit_tradable_membership(
    *,
    as_of_date: date,
    window_sessions: int,
    market_repository: MarketDataRepository,
    named_tickers: Sequence[str] | None,
    benchmark_tickers: frozenset[str] = DEFAULT_BENCHMARK_TICKERS,
    session_probe_calendar_days: int = DEFAULT_SESSION_PROBE_CALENDAR_DAYS,
    benchmark_symbol: str = "IHSG",
) -> tuple[str, ...]:
    """Resolve tradable membership as of a session date from candle presence.

    Args:
        as_of_date: Observation session date (must be an IHSG session for a
            non-empty result).
        window_sessions: N trading sessions ending at ``as_of_date`` (inclusive).
        market_repository: Candle cache.
        named_tickers: Today's named-universe tickers for intersection mode, or
            ``None`` for board-wide pure candle-active membership (``cached``).
        benchmark_tickers: Symbols stripped from membership (never screen as
            equities).
        session_probe_calendar_days: Calendar lookback to load IHSG sessions
            for the N-session window (not the activity filter itself).
        benchmark_symbol: Ticker used as the session calendar source.

    Returns:
        Sorted uppercase equity tickers active in the window (after optional
        named intersection). Empty when the session window cannot be proven.
    """
    if window_sessions < 1:
        raise ValueError(f"window_sessions must be >= 1, got {window_sessions}")
    if session_probe_calendar_days < 1:
        raise ValueError(
            f"session_probe_calendar_days must be >= 1, got {session_probe_calendar_days}"
        )

    probe_days = max(session_probe_calendar_days, window_sessions * 4)
    probe_start = as_of_date - timedelta(days=probe_days)
    ihsg_candles = market_repository.get_candles(
        benchmark_symbol,
        start_date=probe_start,
        end_date=as_of_date,
    )
    sessions = tuple(sorted({candle.date for candle in ihsg_candles}))
    window_start = session_window_start(sessions, as_of_date, window_sessions)
    if window_start is None:
        return ()

    active = market_repository.list_tickers_with_candles_between(window_start, as_of_date)
    benchmarks = {t.upper() for t in benchmark_tickers}
    equities = sorted({t.upper() for t in active if t.upper() not in benchmarks})

    if named_tickers is None:
        return tuple(equities)

    named = {t.upper() for t in named_tickers}
    return tuple(ticker for ticker in equities if ticker in named)
