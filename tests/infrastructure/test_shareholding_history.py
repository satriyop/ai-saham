"""
get_history — dedupe-per-period + PIT filter for StockbitShareholdingProvider.

Verifies the dedupe rule (re-fetches of the same report period collapse to the
latest fetched_date) and the as_of_date cutoff applied before dedupe/limit.
"""

import sqlite3
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.infrastructure.browser.stockbit_shareholding import StockbitShareholdingProvider

_TICKER = "AADI"


def _insert_row(
    db_path: Path,
    ticker: str,
    fetched_date: str,
    report_date: str | None,
    *,
    institution_pct: float = 40.0,
    top_holder_pct: float = 30.0,
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO shareholding_composition "
            "(ticker, fetched_date, report_date, institution_pct, individual_pct, "
            "top_holder_name, top_holder_pct, total_shares, total_shares_formatted) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                ticker,
                fetched_date,
                report_date,
                institution_pct,
                25.0,
                "DWIMURIA",
                top_holder_pct,
                100_000_000,
                "100M",
            ),
        )


@pytest.fixture
def provider(tmp_path) -> StockbitShareholdingProvider:
    mock_broker = MagicMock()
    return StockbitShareholdingProvider(api_client=mock_broker, db_path=tmp_path / "test.db")


def test_dedupes_refetches_of_same_period(provider, tmp_path):
    db = tmp_path / "test.db"
    # Two re-fetches of the same Q1 filing, plus one Q2 filing.
    _insert_row(db, _TICKER, "2026-04-01T00:00:00", "2026-03-31", institution_pct=38.0)
    _insert_row(db, _TICKER, "2026-04-15T00:00:00", "2026-03-31", institution_pct=40.0)
    _insert_row(db, _TICKER, "2026-07-10T00:00:00", "2026-06-30", institution_pct=41.0)

    history = provider.get_history(_TICKER, limit=8)

    assert len(history) == 2  # not 3 — re-fetch collapsed
    assert history[0].report_date == date(2026, 6, 30)
    assert history[1].report_date == date(2026, 3, 31)
    # Latest fetched_date row wins for the deduped period.
    assert history[1].institution_pct == 40.0


def test_orders_newest_period_first(provider, tmp_path):
    db = tmp_path / "test.db"
    _insert_row(db, _TICKER, "2025-10-01T00:00:00", "2025-09-30")
    _insert_row(db, _TICKER, "2026-01-05T00:00:00", "2025-12-31")
    _insert_row(db, _TICKER, "2026-04-05T00:00:00", "2026-03-31")

    history = provider.get_history(_TICKER, limit=8)

    assert [c.report_date for c in history] == [
        date(2026, 3, 31),
        date(2025, 12, 31),
        date(2025, 9, 30),
    ]


def test_limit_caps_result_count(provider, tmp_path):
    db = tmp_path / "test.db"
    for month in range(1, 6):
        _insert_row(
            db,
            _TICKER,
            f"2026-{month:02d}-15T00:00:00",
            f"2026-{month:02d}-01",
        )

    history = provider.get_history(_TICKER, limit=2)

    assert len(history) == 2
    assert history[0].report_date == date(2026, 5, 1)
    assert history[1].report_date == date(2026, 4, 1)


def test_as_of_date_cutoff_applied_before_dedupe_and_limit(provider, tmp_path):
    db = tmp_path / "test.db"
    _insert_row(db, _TICKER, "2025-10-01T00:00:00", "2025-09-30")
    _insert_row(db, _TICKER, "2026-01-05T00:00:00", "2025-12-31")
    _insert_row(db, _TICKER, "2026-04-05T00:00:00", "2026-03-31")  # look-ahead in this backtest

    history = provider.get_history(_TICKER, limit=8, as_of_date=date(2026, 1, 15))

    assert [c.report_date for c in history] == [date(2025, 12, 31), date(2025, 9, 30)]


def test_empty_when_no_rows(provider):
    assert provider.get_history(_TICKER, limit=8) == ()


def test_falls_back_to_fetched_date_when_report_date_absent(provider, tmp_path):
    db = tmp_path / "test.db"
    _insert_row(db, _TICKER, "2026-02-01T00:00:00", None)
    _insert_row(db, _TICKER, "2026-05-01T00:00:00", "2026-03-31")

    history = provider.get_history(_TICKER, limit=8)

    assert len(history) == 2
    assert history[0].report_date == date(2026, 3, 31)
    assert history[1].report_date is None
