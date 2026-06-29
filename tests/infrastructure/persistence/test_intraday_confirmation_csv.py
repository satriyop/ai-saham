"""Tests for intraday confirmation CSV store."""

from datetime import date
from decimal import Decimal

from src.domain.value_objects.intraday_confirmation import (
    IntradayConfirmationJournalEntry,
)
from src.infrastructure.persistence.intraday_confirmation_csv import (
    IntradayConfirmationCsvStore,
)


def _entry(ticker="BBCA") -> IntradayConfirmationJournalEntry:
    return IntradayConfirmationJournalEntry(
        confirmed_at=date(2026, 6, 12),
        ticker=ticker,
        decision="ENTER",
        reason_codes=("open inside entry range", "pre-open trend is BULLISH"),
        opening_price=Decimal("9050"),
        planned_entry=Decimal("9050"),
        stop_loss_price=Decimal("8900"),
        stop_pct=Decimal("1.7"),
        iev=450000,
        trend="BULLISH",
        rsi=Decimal("52"),
        gap_pct=Decimal("0.6"),
        opening_broker_backing_tag="BACKED",
        fvwap_discount_pct=Decimal("2.4"),
    )


def test_append_and_read_round_trip(tmp_path):
    path = tmp_path / "confirmations.csv"
    store = IntradayConfirmationCsvStore(path)

    assert store.append([_entry()]) == 1

    rows = store.read_all()
    assert len(rows) == 1
    assert rows[0].ticker == "BBCA"
    assert rows[0].decision == "ENTER"
    assert rows[0].reason_codes == (
        "open inside entry range",
        "pre-open trend is BULLISH",
    )
    assert rows[0].opening_price == Decimal("9050")
    assert rows[0].fvwap_discount_pct == Decimal("2.4")


def test_append_is_idempotent_by_date_and_ticker(tmp_path):
    path = tmp_path / "confirmations.csv"
    store = IntradayConfirmationCsvStore(path)

    assert store.append([_entry()]) == 1
    assert store.append([_entry()]) == 0
    assert len(store.read_all()) == 1


def test_update_outcome_enriches_existing_row(tmp_path):
    path = tmp_path / "confirmations.csv"
    store = IntradayConfirmationCsvStore(path)
    store.append([_entry()])

    updated = store.update_outcome(
        confirmed_at=date(2026, 6, 12),
        ticker="BBCA",
        actual_entry_price=Decimal("9050"),
        actual_exit_price=Decimal("9200"),
        outcome_result="target",
        outcome_r=Decimal("1.00"),
        outcome_notes="manual exit",
    )

    assert updated is True
    row = store.read_all()[0]
    assert row.actual_entry_price == Decimal("9050")
    assert row.actual_exit_price == Decimal("9200")
    assert row.outcome_result == "target"
    assert row.outcome_r == Decimal("1")
    assert row.outcome_notes == "manual exit"
