"""Tests for SQLiteIEVRepository."""

import tempfile
from datetime import date
from pathlib import Path

import pytest

from src.infrastructure.persistence.sqlite_iev_repository import SQLiteIEVRepository


@pytest.fixture
def repo(tmp_path):
    return SQLiteIEVRepository(tmp_path / "test.db")


D1 = date(2026, 6, 10)
D2 = date(2026, 6, 11)

MOVERS = [("BBCA", 450_000), ("BBRI", 320_000), ("BMRI", 210_000)]


def test_schema_created_on_init(tmp_path):
    db = tmp_path / "new.db"
    repo = SQLiteIEVRepository(db)
    assert db.exists()
    assert not repo.has_snapshot(D1)


def test_save_and_retrieve_snapshot(repo):
    written = repo.save_snapshot(D1, MOVERS)
    assert written == 3

    rows = repo.get_snapshot(D1)
    assert len(rows) == 3
    assert rows[0].ticker == "BBCA"
    assert rows[0].iev == 450_000
    assert rows[0].rank == 1
    assert rows[1].ticker == "BBRI"
    assert rows[1].rank == 2
    assert rows[2].ticker == "BMRI"
    assert rows[2].rank == 3


def test_has_snapshot_true_after_save(repo):
    assert not repo.has_snapshot(D1)
    repo.save_snapshot(D1, MOVERS)
    assert repo.has_snapshot(D1)


def test_top_n_filter(repo):
    repo.save_snapshot(D1, MOVERS)
    top2 = repo.get_snapshot(D1, top_n=2)
    assert len(top2) == 2
    assert [r.ticker for r in top2] == ["BBCA", "BBRI"]


def test_upsert_updates_existing(repo):
    repo.save_snapshot(D1, [("BBCA", 100_000)])
    repo.save_snapshot(D1, [("BBCA", 999_000)])  # update same date/ticker
    rows = repo.get_snapshot(D1)
    assert rows[0].iev == 999_000


def test_multiple_dates_isolated(repo):
    repo.save_snapshot(D1, [("BBCA", 450_000)])
    repo.save_snapshot(D2, [("BBRI", 320_000), ("BMRI", 200_000)])

    d1_rows = repo.get_snapshot(D1)
    d2_rows = repo.get_snapshot(D2)
    assert len(d1_rows) == 1
    assert d1_rows[0].ticker == "BBCA"
    assert len(d2_rows) == 2


def test_get_snapshot_dates(repo):
    repo.save_snapshot(D1, MOVERS)
    repo.save_snapshot(D2, MOVERS)
    dates = repo.get_snapshot_dates()
    assert dates == [D1, D2]


def test_get_coverage(repo):
    assert repo.get_coverage()["total_dates"] == 0

    repo.save_snapshot(D1, MOVERS)
    repo.save_snapshot(D2, [("BBCA", 1)])

    cov = repo.get_coverage()
    assert cov["total_dates"] == 2
    assert cov["first_date"] == D1.isoformat()
    assert cov["last_date"] == D2.isoformat()
    assert cov["avg_movers_per_day"] == 2.0  # (3 + 1) / 2


def test_empty_movers_list_writes_zero_rows(repo):
    written = repo.save_snapshot(D1, [])
    assert written == 0
    assert not repo.has_snapshot(D1)
