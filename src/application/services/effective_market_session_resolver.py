"""
Canonical IDX effective-session resolver.

Single application-layer authority for "what IDX trading session is
effective at a given decision timestamp". Prefers the cached IHSG benchmark
candle series (the true IDX trading calendar, weekends/holidays already
excluded by the data itself) and only falls back to Mon-Fri weekday
arithmetic when no cached IHSG data bounds the decision date.

This resolver does not decide freshness/staleness policy for a specific
ticker (see `data_freshness_service.py`) or cache-refresh tolerance (see
`market_freshness_service.py`). It answers one narrower question: which
IDX session was the latest *completed* session as of a given decision
timestamp. All IHSG lookups are bounded by the decision date so no future
cached session can leak into a past-dated decision.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.benchmark_symbol import BenchmarkTickerAliases
from src.domain.value_objects.idx_market import (
    IDX_TIMEZONE,
    MARKET_CLOSE,
    PRE_CLOSE_START,
    PRE_OPEN_START,
    REGULAR_OPEN,
)
from src.domain.value_objects.trading_calendar import last_weekday

DEFAULT_BENCHMARK_ALIASES = BenchmarkTickerAliases(canonical="IHSG", legacy="^JKSE")


@dataclass(frozen=True)
class EffectiveMarketSession:
    """Resolved IDX session state for one decision timestamp."""

    run_at: datetime
    decision_at: datetime
    latest_completed_session: date | None
    analysis_as_of: date | None
    market_session_name: str
    is_eod_pending: bool
    resolution_source: str
    notes: tuple[str, ...] = ()


class EffectiveMarketSessionResolver:
    """Resolve the effective completed IDX session for a decision timestamp."""

    def __init__(
        self,
        market_repository: MarketDataRepository,
        benchmark: BenchmarkTickerAliases = DEFAULT_BENCHMARK_ALIASES,
    ) -> None:
        self._market_repository = market_repository
        self._benchmark = benchmark

    def resolve(
        self,
        *,
        run_at: datetime,
        decision_at: datetime | None = None,
    ) -> EffectiveMarketSession:
        effective_decision_at = decision_at if decision_at is not None else run_at

        if run_at.tzinfo is None:
            raise ValueError("run_at must be timezone-aware")
        if effective_decision_at.tzinfo is None:
            raise ValueError("decision_at must be timezone-aware")

        run_at_wib = run_at.astimezone(IDX_TIMEZONE)
        decision_at_wib = effective_decision_at.astimezone(IDX_TIMEZONE)
        decision_date = decision_at_wib.date()
        decision_time = decision_at_wib.time()

        notes: list[str] = []

        if decision_date.weekday() >= 5:
            latest_completed_session, resolution_source = self._resolve_weekend(
                decision_date, notes
            )
            market_session_name = "WEEKEND"
            is_eod_pending = False
        elif decision_time < MARKET_CLOSE:
            latest_completed_session, resolution_source = self._resolve_before_close(
                decision_date, notes
            )
            market_session_name = self._weekday_pre_close_session_name(decision_time)
            is_eod_pending = True
        else:
            latest_completed_session, resolution_source, is_eod_pending = (
                self._resolve_after_close(decision_date, notes)
            )
            market_session_name = "AFTER_CLOSE"

        return EffectiveMarketSession(
            run_at=run_at_wib,
            decision_at=decision_at_wib,
            latest_completed_session=latest_completed_session,
            analysis_as_of=latest_completed_session,
            market_session_name=market_session_name,
            is_eod_pending=is_eod_pending,
            resolution_source=resolution_source,
            notes=tuple(notes),
        )

    @staticmethod
    def _weekday_pre_close_session_name(decision_time: time) -> str:
        """Classify a weekday time strictly before `MARKET_CLOSE` into the
        finer-grained pre-open/regular/pre-closing bands DQ-002 requires.
        `latest_completed_session`/`is_eod_pending` are identical across all
        of these bands (prior cached session, pending) — only the label
        distinguishes them for callers/observability.
        """
        if decision_time < PRE_OPEN_START:
            return "BEFORE_OPEN"
        if decision_time < REGULAR_OPEN:
            return "PRE_OPEN"
        if decision_time < PRE_CLOSE_START:
            return "REGULAR"
        return "PRE_CLOSING"

    def _resolve_weekend(
        self, decision_date: date, notes: list[str]
    ) -> tuple[date, str]:
        cached = self._bounded_ihsg_session(end_date=decision_date)
        if cached is not None:
            return cached, "ihsg_cache_weekend"
        notes.append(
            "IHSG cache unavailable through the decision date; used weekday "
            "fallback to resolve the weekend session."
        )
        return last_weekday(decision_date), "weekday_fallback_weekend"

    def _resolve_before_close(
        self, decision_date: date, notes: list[str]
    ) -> tuple[date, str]:
        cached = self._bounded_ihsg_session(end_date=decision_date - timedelta(days=1))
        if cached is not None:
            return cached, "ihsg_cache_prior_session"
        notes.append(
            "IHSG cache unavailable before the decision date; used weekday "
            "fallback to resolve the prior completed session."
        )
        return last_weekday(decision_date - timedelta(days=1)), "weekday_fallback_prior_session"

    def _resolve_after_close(
        self, decision_date: date, notes: list[str]
    ) -> tuple[date, str, bool]:
        cached = self._bounded_ihsg_session(end_date=decision_date)
        if cached is None:
            notes.append(
                "IHSG cache unavailable through the decision date; used weekday "
                "fallback after market close."
            )
            return last_weekday(decision_date), "weekday_fallback_post_close", False
        if cached == decision_date:
            return cached, "ihsg_cache_same_day", False
        notes.append(
            f"IHSG cache latest session ({cached.isoformat()}) is earlier than the "
            f"decision date ({decision_date.isoformat()}); this may be a stale cache "
            "or a non-trading day (holiday), and the earlier cached session is used "
            "as the latest completed session."
        )
        return cached, "ihsg_cache_stale_or_holiday", False

    def _bounded_ihsg_session(self, *, end_date: date) -> date | None:
        """Latest cached IHSG session on or before `end_date`, or None if uncached.

        Bounded (not `get_date_range`'s unbounded latest) so a decision_at in
        the past can never observe a cached session that is chronologically
        after it.
        """
        candles = self._market_repository.get_candles(
            self._benchmark.canonical, end_date=end_date
        )
        if not candles and self._benchmark.legacy:
            candles = self._market_repository.get_candles(
                self._benchmark.legacy, end_date=end_date
            )
        if not candles:
            return None
        return candles[-1].date
