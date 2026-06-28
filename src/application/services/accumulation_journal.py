"""
AccumulationJournalService — log accumulation candidates and review forward returns.

Usage:
    service.log_candidate(ticker, entry_price, window_days, candidate, logged_at)
    report = service.review(horizon_days=10)

Layer: Application
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from src.application.services.stats import average, win_rate
from src.application.use_case.accumulation_screen_use_case import AccumulationCandidate
from src.domain.ports.accumulation_journal_store import AccumulationJournalStore
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.accumulation_journal_entry import AccumulationJournalEntry


@dataclass
class ScoreBucketStat:
    bucket: str
    n: int
    avg_return_5d: float | None
    avg_return_10d: float | None
    win_rate_10d: float | None


@dataclass
class PatternStat:
    pattern: str
    n: int
    avg_return_10d: float | None
    win_rate_10d: float | None
    avg_max_upside: float | None
    avg_max_drawdown: float | None


@dataclass
class DecisionStat:
    decision: str
    n: int
    avg_return_10d: float | None
    win_rate_10d: float | None
    avg_max_upside: float | None
    avg_max_drawdown: float | None


@dataclass
class SignalDelta:
    """Compares avg 10d return for two groups to assess signal quality."""
    signal: str
    group_a_label: str
    group_a_n: int
    group_a_avg_10d: float | None
    group_b_label: str
    group_b_n: int
    group_b_avg_10d: float | None


@dataclass
class AccumulationJournalReport:
    total_entries: int
    enriched_entries: int
    score_buckets: list[ScoreBucketStat] = field(default_factory=list)
    by_decision: list[DecisionStat] = field(default_factory=list)
    by_pattern: list[PatternStat] = field(default_factory=list)
    signal_deltas: list[SignalDelta] = field(default_factory=list)


def _avg(values: list[float | None]) -> float | None:
    return average(values, precision=2)


def _win_rate(returns: list[float | None]) -> float | None:
    return win_rate(returns, precision=1)


def _group_avg_10d(entries: list[AccumulationJournalEntry]) -> float | None:
    returns = [e.return_10d_pct for e in entries if e.return_10d_pct is not None]
    return _avg(returns)


class AccumulationJournalService:
    """Log accumulation screener candidates and compute forward-return metrics."""

    def __init__(
        self,
        store: AccumulationJournalStore,
        repository: MarketDataRepository,
    ) -> None:
        self._store = store
        self._repository = repository

    def log_candidate(
        self,
        ticker: str,
        entry_price: Decimal,
        window_days: int,
        candidate: AccumulationCandidate | None,
        logged_at: date,
        pattern: str | None = None,
        setup: str | None = None,
        setup_match: str | None = None,
        failed_gates: tuple[str, ...] = (),
        regime: str | None = None,
        planned_entry: Decimal | None = None,
        planned_stop: Decimal | None = None,
        planned_target: Decimal | None = None,
        max_hold_days: int | None = None,
    ) -> int:
        """Build an AccumulationJournalEntry from a screener result and persist it.

        Args:
            ticker: Ticker symbol
            entry_price: Entry price (default = latest close)
            window_days: Accumulation window used for the screen
            candidate: AccumulationCandidate from use case (None = ticker not found)
            logged_at: Date of the log entry
            pattern: Optional multi-window pattern label

        Returns:
            1 if written, 0 if duplicate
        """
        def _d(f: float | None) -> Decimal | None:
            return Decimal(str(round(f, 4))) if f is not None else None

        entry = AccumulationJournalEntry(
            logged_at=logged_at,
            ticker=ticker,
            entry_price=entry_price,
            window_days=window_days,
            score=candidate.score if candidate else None,
            streak=candidate.consecutive_streak if candidate else None,
            flow_pct=_d(candidate.avg_flow_ratio) if candidate else None,
            vwap_disc_pct=_d(candidate.vwap_discount_pct) if candidate else None,
            bb_pctile=_d(candidate.bb_width_pctile) if candidate else None,
            rsi=_d(candidate.rsi) if candidate else None,
            trend=candidate.trend if candidate else None,
            pattern=pattern,
            setup=setup,
            setup_match=setup_match,
            failed_gates=failed_gates,
            regime=regime,
            planned_entry=planned_entry,
            planned_stop=planned_stop,
            planned_target=planned_target,
            max_hold_days=max_hold_days,
        )
        return self._store.append([entry])

    def review(self, horizon_days: int = 10) -> AccumulationJournalReport:
        """Enrich entries with forward returns and compute performance statistics.

        Fills review fields (actual_close_5d/10d/20d, max/min) from local DB.
        Entries already enriched are not re-fetched.

        Args:
            horizon_days: Trading days forward for max/min window

        Returns:
            AccumulationJournalReport with three analysis tables
        """
        raw_entries = self._store.read_all()
        if not raw_entries:
            return AccumulationJournalReport(total_entries=0, enriched_entries=0)

        # Enrich entries that are missing review data
        needs_review = [e for e in raw_entries if e.actual_close_10d is None]
        newly_enriched: list[AccumulationJournalEntry] = []
        for entry in needs_review:
            enriched = self._enrich(entry, horizon_days)
            if enriched.actual_close_10d is not None:
                newly_enriched.append(enriched)

        if newly_enriched:
            self._store.update_review_fields(newly_enriched)

        all_entries = self._store.read_all()
        with_data = [e for e in all_entries if e.actual_close_10d is not None]

        return AccumulationJournalReport(
            total_entries=len(all_entries),
            enriched_entries=len(with_data),
            score_buckets=self._score_buckets(with_data),
            by_decision=self._decision_stats(with_data),
            by_pattern=self._pattern_stats(with_data),
            signal_deltas=self._signal_deltas(with_data),
        )

    # ── enrichment ──────────────────────────────────────────────────────────

    def _enrich(
        self, entry: AccumulationJournalEntry, horizon_days: int
    ) -> AccumulationJournalEntry:
        """Fetch forward candles and fill review fields."""
        # Look far enough ahead to cover 20 trading days + weekends
        end_date = entry.logged_at + timedelta(days=horizon_days + 40)
        candles = self._repository.get_candles(
            entry.ticker,
            start_date=entry.logged_at + timedelta(days=1),
            end_date=end_date,
        )
        if not candles:
            return entry

        trading_candles = [c for c in candles if c.date > entry.logged_at]
        if not trading_candles:
            return entry

        def nth_close(n: int) -> Decimal | None:
            return trading_candles[n - 1].close if len(trading_candles) >= n else None

        close_5d = nth_close(5)
        close_10d = nth_close(10)
        close_20d = nth_close(20)

        horizon_candles = trading_candles[:horizon_days]
        max_close = max(c.close for c in horizon_candles) if horizon_candles else None
        min_close = min(c.close for c in horizon_candles) if horizon_candles else None

        return AccumulationJournalEntry(
            logged_at=entry.logged_at,
            ticker=entry.ticker,
            entry_price=entry.entry_price,
            window_days=entry.window_days,
            score=entry.score,
            streak=entry.streak,
            flow_pct=entry.flow_pct,
            vwap_disc_pct=entry.vwap_disc_pct,
            bb_pctile=entry.bb_pctile,
            rsi=entry.rsi,
            trend=entry.trend,
            pattern=entry.pattern,
            setup=entry.setup,
            setup_match=entry.setup_match,
            failed_gates=entry.failed_gates,
            regime=entry.regime,
            planned_entry=entry.planned_entry,
            planned_stop=entry.planned_stop,
            planned_target=entry.planned_target,
            max_hold_days=entry.max_hold_days,
            actual_close_5d=close_5d,
            actual_close_10d=close_10d,
            actual_close_20d=close_20d,
            max_close_in_horizon=max_close,
            min_close_in_horizon=min_close,
        )

    # ── statistics ──────────────────────────────────────────────────────────

    def _score_buckets(
        self, entries: list[AccumulationJournalEntry]
    ) -> list[ScoreBucketStat]:
        buckets = [
            ("70+", lambda e: e.score is not None and e.score >= 70),
            ("40–69", lambda e: e.score is not None and 40 <= e.score < 70),
            ("0–39", lambda e: e.score is not None and e.score < 40),
        ]
        result = []
        for label, pred in buckets:
            group = [e for e in entries if pred(e)]
            returns_5d = [
                float((e.actual_close_5d - e.entry_price) / e.entry_price * 100)
                for e in group
                if e.actual_close_5d is not None and e.entry_price != 0
            ]
            returns_10d = [e.return_10d_pct for e in group if e.return_10d_pct is not None]
            result.append(ScoreBucketStat(
                bucket=label,
                n=len(group),
                avg_return_5d=_avg(returns_5d),
                avg_return_10d=_avg(returns_10d),
                win_rate_10d=_win_rate(returns_10d),
            ))
        return result

    def _decision_stats(
        self, entries: list[AccumulationJournalEntry]
    ) -> list[DecisionStat]:
        decisions: dict[str, list[AccumulationJournalEntry]] = {}
        for e in entries:
            key = e.setup_match or "unknown"
            decisions.setdefault(key, []).append(e)

        result = []
        for decision, group in sorted(decisions.items(), key=lambda x: -len(x[1])):
            returns_10d = [e.return_10d_pct for e in group if e.return_10d_pct is not None]
            upsides = [e.max_upside_pct for e in group if e.max_upside_pct is not None]
            drawdowns = [e.max_drawdown_pct for e in group if e.max_drawdown_pct is not None]
            result.append(DecisionStat(
                decision=decision,
                n=len(group),
                avg_return_10d=_avg(returns_10d),
                win_rate_10d=_win_rate(returns_10d),
                avg_max_upside=_avg(upsides),
                avg_max_drawdown=_avg(drawdowns),
            ))
        return result

    def _pattern_stats(
        self, entries: list[AccumulationJournalEntry]
    ) -> list[PatternStat]:
        patterns: dict[str, list[AccumulationJournalEntry]] = {}
        for e in entries:
            key = e.pattern or "unknown"
            patterns.setdefault(key, []).append(e)

        result = []
        for pat, group in sorted(patterns.items(), key=lambda x: -len(x[1])):
            returns_10d = [e.return_10d_pct for e in group if e.return_10d_pct is not None]
            upsides = [e.max_upside_pct for e in group if e.max_upside_pct is not None]
            drawdowns = [e.max_drawdown_pct for e in group if e.max_drawdown_pct is not None]
            result.append(PatternStat(
                pattern=pat,
                n=len(group),
                avg_return_10d=_avg(returns_10d),
                win_rate_10d=_win_rate(returns_10d),
                avg_max_upside=_avg(upsides),
                avg_max_drawdown=_avg(drawdowns),
            ))
        return result

    def _signal_deltas(
        self, entries: list[AccumulationJournalEntry]
    ) -> list[SignalDelta]:
        """Compare avg 10d return for four binary signal splits."""
        comparisons = [
            (
                "streak", "≥5d", "streak >= 5",
                "<5d", "streak < 5",
                lambda e: e.streak is not None,
                lambda e: e.streak is not None and e.streak >= 5,
            ),
            (
                "vwap_disc", ">0 (underwater)", "vwap_disc > 0",
                "≤0 (in profit)", "vwap_disc ≤ 0",
                lambda e: e.vwap_disc_pct is not None,
                lambda e: e.vwap_disc_pct is not None and e.vwap_disc_pct > 0,
            ),
            (
                "bb_pctile", "≤20% (squeeze)", "bb_pctile ≤ 20%",
                ">40%", "bb_pctile > 40%",
                lambda e: e.bb_pctile is not None,
                lambda e: e.bb_pctile is not None and e.bb_pctile <= Decimal("0.20"),
            ),
            (
                "flow_pct", "≥15%", "flow ≥ 15%",
                "<15%", "flow < 15%",
                lambda e: e.flow_pct is not None,
                lambda e: e.flow_pct is not None and e.flow_pct >= Decimal("15"),
            ),
        ]
        result = []
        for signal, a_label, _, b_label, __, has_signal, pred in comparisons:
            eligible = [e for e in entries if has_signal(e)]
            group_a = [e for e in eligible if pred(e)]
            group_b = [e for e in eligible if not pred(e)]
            result.append(SignalDelta(
                signal=signal,
                group_a_label=a_label,
                group_a_n=len(group_a),
                group_a_avg_10d=_group_avg_10d(group_a),
                group_b_label=b_label,
                group_b_n=len(group_b),
                group_b_avg_10d=_group_avg_10d(group_b),
            ))
        return result
