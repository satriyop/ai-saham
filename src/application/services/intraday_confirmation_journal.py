"""
Intraday confirmation journal service.

Logs post-open confirmation decisions and reviews their next-session outcomes.

Layer: Application
"""

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Protocol

from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.intraday_confirmation import (
    IntradayConfirmation,
    IntradayConfirmationJournalEntry,
)


class IntradayConfirmationStore(Protocol):
    def append(self, entries: list[IntradayConfirmationJournalEntry]) -> int:
        """Append entries and return count written."""

    def read_all(self) -> list[IntradayConfirmationJournalEntry]:
        """Read all entries."""

    def update_outcome(
        self,
        *,
        confirmed_at,
        ticker: str,
        actual_entry_price: Decimal,
        actual_exit_price: Decimal,
        outcome_result: str,
        outcome_r: Decimal | None,
        outcome_notes: str | None,
    ) -> bool:
        """Update manual outcome fields for an existing entry."""


@dataclass(frozen=True)
class IntradayOutcome:
    entry: IntradayConfirmationJournalEntry
    actual_open: Decimal
    actual_high: Decimal
    actual_low: Decimal
    actual_close: Decimal
    close_r: Decimal | None
    stop_hit: bool | None
    target_1r_hit: bool | None

    @property
    def direction(self) -> str:
        if self.actual_close > self.actual_open:
            return "UP"
        if self.actual_close < self.actual_open:
            return "DOWN"
        return "FLAT"


@dataclass(frozen=True)
class IntradayBucketStats:
    bucket: str
    total: int
    with_data: int
    enter_count: int
    up_count: int
    stop_hit_count: int
    target_1r_hit_count: int
    avg_close_r: Decimal | None


@dataclass(frozen=True)
class IntradayConfirmationReview:
    total_entries: int
    entries_with_data: int
    decision_buckets: list[IntradayBucketStats] = field(default_factory=list)
    context_buckets: dict[str, list[IntradayBucketStats]] = field(default_factory=dict)


class IntradayConfirmationJournalService:
    """Log and review post-open intraday confirmation decisions."""

    def __init__(
        self,
        store: IntradayConfirmationStore,
        repository: MarketDataRepository,
    ) -> None:
        self._store = store
        self._repository = repository

    def log_confirmations(
        self,
        confirmations: tuple[IntradayConfirmation, ...],
        confirmed_at,
    ) -> int:
        entries = [
            IntradayConfirmationJournalEntry(
                confirmed_at=confirmed_at,
                ticker=confirmation.ticker,
                decision=confirmation.decision.value,
                reason_codes=confirmation.reasons,
                opening_price=confirmation.opening_price,
                planned_entry=confirmation.planned_entry,
                stop_loss_price=confirmation.stop_loss_price,
                stop_pct=confirmation.stop_pct,
                iev=confirmation.iev,
                trend=confirmation.trend,
                rsi=confirmation.rsi,
                gap_pct=confirmation.gap_pct,
                accum_tag=confirmation.accum_tag,
                fvwap_discount_pct=confirmation.fvwap_discount_pct,
            )
            for confirmation in confirmations
        ]
        return self._store.append(entries)

    def review(self) -> IntradayConfirmationReview:
        entries = self._store.read_all()
        if not entries:
            return IntradayConfirmationReview(total_entries=0, entries_with_data=0)

        outcomes = [outcome for entry in entries if (outcome := self._outcome(entry))]
        return IntradayConfirmationReview(
            total_entries=len(entries),
            entries_with_data=len(outcomes),
            decision_buckets=self._bucket(
                entries=entries,
                outcomes=outcomes,
                key_fn=lambda entry: f"decision:{entry.decision}",
            ),
            context_buckets={
                "gap": self._bucket(entries, outcomes, lambda entry: entry.gap_bucket),
                "rsi": self._bucket(entries, outcomes, lambda entry: entry.rsi_bucket),
                "stop": self._bucket(entries, outcomes, lambda entry: entry.stop_bucket),
                "accum": self._bucket(
                    entries,
                    outcomes,
                    lambda entry: f"accum:{entry.accum_tag or 'missing'}",
                ),
                "fvwap": self._bucket(entries, outcomes, lambda entry: entry.fvwap_bucket),
            },
        )

    def record_outcome(
        self,
        *,
        confirmed_at,
        ticker: str,
        actual_entry_price: Decimal,
        actual_exit_price: Decimal,
        outcome_result: str,
        notes: str | None = None,
    ) -> tuple[bool, Decimal | None]:
        entries = self._store.read_all()
        ticker_upper = ticker.upper()
        entry = next(
            (
                row
                for row in entries
                if row.confirmed_at == confirmed_at and row.ticker.upper() == ticker_upper
            ),
            None,
        )
        if entry is None:
            return False, None

        outcome_r = self._compute_outcome_r(
            entry=entry,
            actual_entry_price=actual_entry_price,
            actual_exit_price=actual_exit_price,
        )
        updated = self._store.update_outcome(
            confirmed_at=confirmed_at,
            ticker=ticker_upper,
            actual_entry_price=actual_entry_price,
            actual_exit_price=actual_exit_price,
            outcome_result=outcome_result,
            outcome_r=outcome_r,
            outcome_notes=notes,
        )
        return updated, outcome_r

    def _outcome(self, entry: IntradayConfirmationJournalEntry) -> IntradayOutcome | None:
        if entry.has_manual_outcome:
            actual_entry = entry.actual_entry_price
            actual_exit = entry.actual_exit_price
            if actual_entry is None or actual_exit is None:
                return None
            stop_hit = entry.outcome_result == "stop"
            target_hit = entry.outcome_result == "target"
            return IntradayOutcome(
                entry=entry,
                actual_open=actual_entry,
                actual_high=max(actual_entry, actual_exit),
                actual_low=min(actual_entry, actual_exit),
                actual_close=actual_exit,
                close_r=entry.outcome_r,
                stop_hit=stop_hit,
                target_1r_hit=target_hit,
            )

        end_date = entry.confirmed_at + timedelta(days=14)
        candles = self._repository.get_candles(
            entry.ticker,
            start_date=entry.confirmed_at,
            end_date=end_date,
        )
        trading_candles = [c for c in candles if c.date >= entry.confirmed_at]
        if not trading_candles:
            return None

        candle = trading_candles[0]
        actual_open = entry.opening_price or candle.open
        close_r = None
        stop_hit = None
        target_hit = None

        if (
            entry.planned_entry is not None
            and entry.stop_loss_price is not None
            and entry.stop_loss_price < entry.planned_entry
        ):
            risk = entry.planned_entry - entry.stop_loss_price
            if risk > 0:
                close_r = ((candle.close - entry.planned_entry) / risk).quantize(
                    Decimal("0.01")
                )
                stop_hit = candle.low <= entry.stop_loss_price
                target_hit = candle.high >= entry.planned_entry + risk

        return IntradayOutcome(
            entry=entry,
            actual_open=actual_open,
            actual_high=candle.high,
            actual_low=candle.low,
            actual_close=candle.close,
            close_r=close_r,
            stop_hit=stop_hit,
            target_1r_hit=target_hit,
        )

    @staticmethod
    def _compute_outcome_r(
        *,
        entry: IntradayConfirmationJournalEntry,
        actual_entry_price: Decimal,
        actual_exit_price: Decimal,
    ) -> Decimal | None:
        stop = entry.stop_loss_price
        if stop is None or stop >= actual_entry_price:
            return None
        risk = actual_entry_price - stop
        if risk <= 0:
            return None
        return ((actual_exit_price - actual_entry_price) / risk).quantize(Decimal("0.01"))

    @staticmethod
    def _bucket(
        entries: list[IntradayConfirmationJournalEntry],
        outcomes: list[IntradayOutcome],
        key_fn,
    ) -> list[IntradayBucketStats]:
        outcomes_by_key: dict[tuple, IntradayOutcome] = {
            (outcome.entry.confirmed_at, outcome.entry.ticker): outcome
            for outcome in outcomes
        }
        all_keys = sorted({key_fn(entry) for entry in entries})
        stats: list[IntradayBucketStats] = []

        for key in all_keys:
            group_entries = [entry for entry in entries if key_fn(entry) == key]
            group_outcomes = [
                outcomes_by_key[(entry.confirmed_at, entry.ticker)]
                for entry in group_entries
                if (entry.confirmed_at, entry.ticker) in outcomes_by_key
            ]
            close_rs = [
                outcome.close_r for outcome in group_outcomes if outcome.close_r is not None
            ]
            avg_close_r = None
            if close_rs:
                avg_close_r = (
                    sum(close_rs, Decimal("0")) / Decimal(str(len(close_rs)))
                ).quantize(Decimal("0.01"))

            stats.append(
                IntradayBucketStats(
                    bucket=key,
                    total=len(group_entries),
                    with_data=len(group_outcomes),
                    enter_count=sum(1 for entry in group_entries if entry.decision == "ENTER"),
                    up_count=sum(1 for outcome in group_outcomes if outcome.direction == "UP"),
                    stop_hit_count=sum(
                        1 for outcome in group_outcomes if outcome.stop_hit is True
                    ),
                    target_1r_hit_count=sum(
                        1 for outcome in group_outcomes if outcome.target_1r_hit is True
                    ),
                    avg_close_r=avg_close_r,
                )
            )

        return stats
