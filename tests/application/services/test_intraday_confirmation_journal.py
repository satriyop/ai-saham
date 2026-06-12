"""Tests for intraday confirmation journal service."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from src.application.services.intraday_confirmation_journal import (
    IntradayConfirmationJournalService,
)
from src.domain.entities.candle import Candle
from src.domain.value_objects.intraday_confirmation import (
    IntradayConfirmationJournalEntry,
)


def _entry(
    ticker="BBCA",
    decision="ENTER",
    confirmed_at=date(2026, 6, 12),
    planned_entry=Decimal("9050"),
    stop=Decimal("8900"),
    stop_pct=Decimal("1.7"),
    rsi=Decimal("52"),
    gap=Decimal("0.6"),
    accum="BACKED",
    fvwap=Decimal("2.4"),
) -> IntradayConfirmationJournalEntry:
    return IntradayConfirmationJournalEntry(
        confirmed_at=confirmed_at,
        ticker=ticker,
        decision=decision,
        reason_codes=("open inside entry range",),
        opening_price=planned_entry,
        planned_entry=planned_entry,
        stop_loss_price=stop,
        stop_pct=stop_pct,
        iev=450000,
        trend="BULLISH",
        rsi=rsi,
        gap_pct=gap,
        accum_tag=accum,
        fvwap_discount_pct=fvwap,
    )


def _candle(
    ticker="BBCA",
    d=date(2026, 6, 12),
    open_price="9050",
    high="9225",
    low="9000",
    close="9200",
) -> Candle:
    return Candle(
        ticker=ticker,
        date=d,
        open=Decimal(open_price),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=1000000,
    )


def test_review_groups_by_decision_and_context_buckets():
    store = MagicMock()
    store.read_all.return_value = [_entry()]
    repo = MagicMock()
    repo.get_candles.return_value = [_candle()]

    service = IntradayConfirmationJournalService(store=store, repository=repo)
    report = service.review()

    assert report.total_entries == 1
    assert report.entries_with_data == 1
    assert report.decision_buckets[0].bucket == "decision:ENTER"
    assert report.decision_buckets[0].target_1r_hit_count == 1
    assert report.decision_buckets[0].avg_close_r == Decimal("1.00")
    assert report.context_buckets["gap"][0].bucket == "gap:0-1"
    assert report.context_buckets["rsi"][0].bucket == "rsi:30-55"
    assert report.context_buckets["fvwap"][0].bucket == "fvwap:positive"


def test_review_counts_stop_hit_from_daily_low_proxy():
    store = MagicMock()
    store.read_all.return_value = [_entry()]
    repo = MagicMock()
    repo.get_candles.return_value = [_candle(low="8890", close="8950")]

    service = IntradayConfirmationJournalService(store=store, repository=repo)
    report = service.review()

    assert report.decision_buckets[0].stop_hit_count == 1
    assert report.decision_buckets[0].avg_close_r == Decimal("-0.67")


def test_review_handles_empty_store_without_repository_calls():
    store = MagicMock()
    store.read_all.return_value = []
    repo = MagicMock()

    service = IntradayConfirmationJournalService(store=store, repository=repo)
    report = service.review()

    assert report.total_entries == 0
    assert report.entries_with_data == 0
    repo.get_candles.assert_not_called()


def test_record_outcome_updates_matching_entry_with_r_multiple():
    entry = _entry()
    store = MagicMock()
    store.read_all.return_value = [entry]
    store.update_outcome.return_value = True
    repo = MagicMock()

    service = IntradayConfirmationJournalService(store=store, repository=repo)
    updated, outcome_r = service.record_outcome(
        confirmed_at=date(2026, 6, 12),
        ticker="BBCA",
        actual_entry_price=Decimal("9050"),
        actual_exit_price=Decimal("9200"),
        outcome_result="target",
        notes="manual exit",
    )

    assert updated is True
    assert outcome_r == Decimal("1.00")
    store.update_outcome.assert_called_once()


def test_review_prefers_manual_outcome_without_repository_call():
    entry = _entry()
    manual_entry = IntradayConfirmationJournalEntry(
        confirmed_at=entry.confirmed_at,
        ticker=entry.ticker,
        decision=entry.decision,
        reason_codes=entry.reason_codes,
        opening_price=entry.opening_price,
        planned_entry=entry.planned_entry,
        stop_loss_price=entry.stop_loss_price,
        stop_pct=entry.stop_pct,
        iev=entry.iev,
        trend=entry.trend,
        rsi=entry.rsi,
        gap_pct=entry.gap_pct,
        accum_tag=entry.accum_tag,
        fvwap_discount_pct=entry.fvwap_discount_pct,
        actual_entry_price=Decimal("9050"),
        actual_exit_price=Decimal("9200"),
        outcome_result="target",
        outcome_r=Decimal("1.00"),
    )
    store = MagicMock()
    store.read_all.return_value = [manual_entry]
    repo = MagicMock()

    service = IntradayConfirmationJournalService(store=store, repository=repo)
    report = service.review()

    assert report.entries_with_data == 1
    assert report.decision_buckets[0].avg_close_r == Decimal("1.00")
    assert report.decision_buckets[0].target_1r_hit_count == 1
    repo.get_candles.assert_not_called()
