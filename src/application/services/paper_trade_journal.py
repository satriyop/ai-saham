"""
PaperTradeJournalService — log screener runs and review hit-rate over time.

Usage:
    # After saham screen pre-open writes .last-session.json:
    service.log_session(candidates, screened_at=date.today())

    # After N trading days, check if the entry ranges were accurate:
    report = service.review(horizon_days=5)

Layer: Application
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from src.domain.ports.journal_store import JournalStore
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.journal_entry import JournalEntry
from src.domain.value_objects.screener_result import ScreenerCandidate


@dataclass
class ReviewReport:
    """Aggregated hit-rate report from journal review."""

    total_entries: int
    entries_with_data: int          # entries where actual_open is known
    hit_rate_pct: float | None      # % where actual_open fell in entry range
    direction_accuracy_1d: float | None  # % of BULLISH calls that went UP (1d)
    direction_accuracy_5d: float | None  # % of BULLISH calls that went UP (5d)
    per_trend_breakdown: dict = field(default_factory=dict)
    # {trend: {total, in_range, up_1d, up_5d}}


class PaperTradeJournalService:
    """Log screener sessions and compute forward-validation metrics."""

    def __init__(
        self,
        store: JournalStore,
        repository: MarketDataRepository,
    ) -> None:
        self._store = store
        self._repository = repository

    def log_session(
        self,
        candidates: list[ScreenerCandidate],
        screened_at: date,
    ) -> int:
        """Convert candidates to JournalEntry rows and persist.

        Args:
            candidates: Screener output candidates
            screened_at: Date the screen was run

        Returns:
            Number of rows written (after dedup)
        """
        entries = [
            JournalEntry(
                screened_at=screened_at,
                ticker=c.ticker,
                iev=c.iev,
                gap_pct=c.gap_pct,
                entry_range_low=c.entry_range_low,
                entry_range_high=c.entry_range_high,
                suggested_entry=c.entry_price,
                atr_stop=c.stop_loss_price,
                trend=c.trend_signal,
                rsi=c.rsi,
            )
            for c in candidates
        ]
        self._store.append(entries)
        return len(entries)

    def review(self, horizon_days: int = 5) -> ReviewReport:
        """Enrich journal entries with actual opens/closes and compute hit-rate.

        Args:
            horizon_days: How many trading days after screen date to look for close_Nd

        Returns:
            ReviewReport with aggregated metrics
        """
        raw_entries = self._store.read_all()
        if not raw_entries:
            return ReviewReport(
                total_entries=0,
                entries_with_data=0,
                hit_rate_pct=None,
                direction_accuracy_1d=None,
                direction_accuracy_5d=None,
            )

        enriched: list[JournalEntry] = []
        for entry in raw_entries:
            enriched.append(self._enrich_entry(entry, horizon_days))

        # Compute metrics
        with_open = [e for e in enriched if e.actual_open is not None]
        bullish = [e for e in with_open if e.trend == "BULLISH"]

        in_range_count = sum(1 for e in with_open if e.in_range)
        hit_rate = (
            round(in_range_count / len(with_open) * 100, 1) if with_open else None
        )

        bullish_up_1d = [e for e in bullish if e.direction_1d == "UP"]
        dir_acc_1d = (
            round(len(bullish_up_1d) / len(bullish) * 100, 1) if bullish else None
        )

        bullish_up_5d = [
            e for e in bullish
            if e.actual_close_5d is not None
            and e.actual_open is not None
            and e.actual_close_5d > e.actual_open
        ]
        has_5d = [e for e in bullish if e.actual_close_5d is not None]
        dir_acc_5d = (
            round(len(bullish_up_5d) / len(has_5d) * 100, 1) if has_5d else None
        )

        # Per-trend breakdown
        breakdown: dict = {}
        for trend in ("BULLISH", "BEARISH", "NEUTRAL"):
            group = [e for e in with_open if e.trend == trend]
            breakdown[trend] = {
                "total": len(group),
                "in_range": sum(1 for e in group if e.in_range),
                "up_1d": sum(1 for e in group if e.direction_1d == "UP"),
            }

        return ReviewReport(
            total_entries=len(raw_entries),
            entries_with_data=len(with_open),
            hit_rate_pct=hit_rate,
            direction_accuracy_1d=dir_acc_1d,
            direction_accuracy_5d=dir_acc_5d,
            per_trend_breakdown=breakdown,
        )

    def _enrich_entry(self, entry: JournalEntry, horizon_days: int) -> JournalEntry:
        """Fill actual_open, actual_close_1d, actual_close_5d from local DB."""
        end_date = entry.screened_at + timedelta(days=horizon_days + 14)
        candles = self._repository.get_candles(
            entry.ticker,
            start_date=entry.screened_at,
            end_date=end_date,
        )
        if not candles:
            return entry

        # actual_open = open price of the FIRST candle on or after screened_at
        trading_candles = [c for c in candles if c.date >= entry.screened_at]
        if not trading_candles:
            return entry

        actual_open = trading_candles[0].open
        actual_close_1d = trading_candles[0].close if len(trading_candles) >= 1 else None

        # close_5d = close of 5th trading candle (not calendar days)
        actual_close_5d: Decimal | None = None
        if len(trading_candles) >= horizon_days:
            actual_close_5d = trading_candles[horizon_days - 1].close

        return JournalEntry(
            screened_at=entry.screened_at,
            ticker=entry.ticker,
            iev=entry.iev,
            gap_pct=entry.gap_pct,
            entry_range_low=entry.entry_range_low,
            entry_range_high=entry.entry_range_high,
            suggested_entry=entry.suggested_entry,
            atr_stop=entry.atr_stop,
            trend=entry.trend,
            rsi=entry.rsi,
            actual_open=actual_open,
            actual_close_1d=actual_close_1d,
            actual_close_5d=actual_close_5d,
        )
