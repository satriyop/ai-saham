from datetime import date
from decimal import Decimal

from src.domain.value_objects.accumulation_journal_entry import AccumulationJournalEntry
from src.infrastructure.persistence.accumulation_journal_csv_writer import (
    AccumulationJournalCsvWriter,
)


def _entry() -> AccumulationJournalEntry:
    return AccumulationJournalEntry(
        logged_at=date(2026, 6, 13),
        ticker="BBRI",
        entry_price=Decimal("4840"),
        window_days=7,
        score=75.0,
        streak=6,
        flow_pct=Decimal("18"),
        vwap_disc_pct=Decimal("4.5"),
        bb_pctile=Decimal("0.15"),
        rsi=Decimal("42"),
        trend="SIDE",
        pattern="building",
        setup="foreign-bounce",
        setup_match="PARTIAL",
        failed_gates=("trend: DOWN (required SIDE)", "flow_pct: 2.0% (required >= +5%)"),
        regime="SIDEWAYS",
        planned_entry=Decimal("4840"),
        planned_stop=Decimal("4598"),
        planned_target=Decimal("5082"),
        max_hold_days=10,
    )


def test_append_and_read_round_trips_analysis_decision_fields(tmp_path):
    path = tmp_path / "accumulation.csv"
    store = AccumulationJournalCsvWriter(path)

    assert store.append([_entry()]) == 1
    rows = store.read_all()

    assert len(rows) == 1
    row = rows[0]
    assert row.setup == "foreign-bounce"
    assert row.setup_match == "PARTIAL"
    assert row.failed_gates == (
        "trend: DOWN (required SIDE)",
        "flow_pct: 2.0% (required >= +5%)",
    )
    assert row.regime == "SIDEWAYS"
    assert row.planned_entry == Decimal("4840")
    assert row.planned_stop == Decimal("4598")
    assert row.planned_target == Decimal("5082")
    assert row.max_hold_days == 10


def test_read_all_accepts_csv_without_setup_columns(tmp_path):
    path = tmp_path / "minimal.csv"
    path.write_text(
        "logged_at,ticker,entry_price,window_days,score,streak,flow_pct,"
        "vwap_disc_pct,bb_pctile,rsi,trend,pattern,actual_close_5d,"
        "actual_close_10d,actual_close_20d,max_close_in_horizon,"
        "min_close_in_horizon\n"
        "2026-06-13,BBRI,4840,7,75,6,18,4.5,0.15,42,SIDE,building,,,,,\n"
    )
    store = AccumulationJournalCsvWriter(path)

    row = store.read_all()[0]

    assert row.ticker == "BBRI"
    assert row.setup is None
    assert row.setup_match is None
    assert row.failed_gates == ()


def test_append_and_read_preserves_none_score_and_streak(tmp_path):
    path = tmp_path / "accumulation.csv"
    store = AccumulationJournalCsvWriter(path)
    entry = AccumulationJournalEntry(
        **{
            **_entry().__dict__,
            "score": None,
            "streak": None,
        }
    )

    assert store.append([entry]) == 1
    row = store.read_all()[0]

    assert row.score is None
    assert row.streak is None


def test_update_review_fields_preserves_analysis_decision_fields(tmp_path):
    path = tmp_path / "accumulation.csv"
    store = AccumulationJournalCsvWriter(path)
    original = _entry()
    store.append([original])

    enriched = AccumulationJournalEntry(
        **{
            **original.__dict__,
            "actual_close_10d": Decimal("5082"),
            "max_close_in_horizon": Decimal("5200"),
            "min_close_in_horizon": Decimal("4700"),
        }
    )
    assert store.update_review_fields([enriched]) == 1

    row = store.read_all()[0]
    assert row.setup_match == "PARTIAL"
    assert row.failed_gates == original.failed_gates
    assert row.planned_stop == Decimal("4598")
    assert row.actual_close_10d == Decimal("5082")
