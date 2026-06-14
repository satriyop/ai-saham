"""Tests for SQLiteIEVRepository."""

from datetime import date

import pytest

from src.domain.value_objects.screener_result import MoverData
from src.infrastructure.persistence.sqlite_iev_repository import SQLiteIEVRepository


@pytest.fixture
def repo(tmp_path):
    return SQLiteIEVRepository(tmp_path / "test.db")


D1 = date(2026, 6, 10)
D2 = date(2026, 6, 11)

MOVERS = [
    MoverData(ticker="BBCA", iev=450_000, iep=5_925),
    MoverData(ticker="BBRI", iev=320_000, iep=3_200),
    MoverData(ticker="BMRI", iev=210_000, iep=4_290),
]

MOVERS_NO_IEP = [
    MoverData(ticker="BBCA", iev=450_000),  # iep=None
    MoverData(ticker="BBRI", iev=320_000),
]


def test_schema_created_on_init(tmp_path):
    db = tmp_path / "new.db"
    repo = SQLiteIEVRepository(db)
    assert db.exists()
    assert not repo.has_snapshot(D1)


def test_save_and_retrieve_snapshot_with_iep(repo):
    written = repo.save_snapshot(D1, MOVERS)
    assert written == 3

    rows = repo.get_snapshot(D1)
    assert len(rows) == 3
    assert rows[0].ticker == "BBCA"
    assert rows[0].iev == 450_000
    assert rows[0].iep == 5_925
    assert rows[0].rank == 1
    assert rows[1].ticker == "BBRI"
    assert rows[1].iep == 3_200
    assert rows[1].rank == 2
    assert rows[2].ticker == "BMRI"
    assert rows[2].iep == 4_290
    assert rows[2].rank == 3


def test_iep_none_stored_gracefully(repo):
    repo.save_snapshot(D1, MOVERS_NO_IEP)
    rows = repo.get_snapshot(D1)
    assert all(r.iep is None for r in rows)


def test_has_snapshot_true_after_save(repo):
    assert not repo.has_snapshot(D1)
    repo.save_snapshot(D1, MOVERS)
    assert repo.has_snapshot(D1)


def test_top_n_filter(repo):
    repo.save_snapshot(D1, MOVERS)
    top2 = repo.get_snapshot(D1, top_n=2)
    assert len(top2) == 2
    assert [r.ticker for r in top2] == ["BBCA", "BBRI"]


def test_upsert_updates_iep_on_second_run(repo):
    # 08:50 run: IEP not yet available
    repo.save_snapshot(D1, [MoverData("BBCA", 450_000, iep=None)])
    rows = repo.get_snapshot(D1)
    assert rows[0].iep is None

    # 08:55 run: IEP now captured (more settled)
    repo.save_snapshot(D1, [MoverData("BBCA", 455_000, iep=5_950)])
    rows = repo.get_snapshot(D1)
    assert rows[0].iev == 455_000
    assert rows[0].iep == 5_950


def test_multiple_dates_isolated(repo):
    repo.save_snapshot(D1, [MoverData("BBCA", 450_000, iep=5_925)])
    repo.save_snapshot(D2, [MoverData("BBRI", 320_000), MoverData("BMRI", 200_000)])

    d1_rows = repo.get_snapshot(D1)
    d2_rows = repo.get_snapshot(D2)
    assert len(d1_rows) == 1
    assert d1_rows[0].ticker == "BBCA"
    assert d1_rows[0].iep == 5_925
    assert len(d2_rows) == 2


def test_get_snapshot_dates(repo):
    repo.save_snapshot(D1, MOVERS)
    repo.save_snapshot(D2, MOVERS)
    dates = repo.get_snapshot_dates()
    assert dates == [D1, D2]


def test_get_coverage_includes_iep_fill_rate(repo):
    assert repo.get_coverage()["total_dates"] == 0

    repo.save_snapshot(D1, MOVERS)                             # 3 rows, all with IEP
    repo.save_snapshot(D2, [MoverData("BBCA", 1, iep=None)])  # 1 row, no IEP

    cov = repo.get_coverage()
    assert cov["total_dates"] == 2
    assert cov["first_date"] == D1.isoformat()
    assert cov["last_date"] == D2.isoformat()
    assert cov["avg_movers_per_day"] == 2.0   # (3 + 1) / 2
    assert cov["iep_fill_pct"] == 75.0         # 3 of 4 rows have IEP


def test_empty_movers_list_writes_zero_rows(repo):
    written = repo.save_snapshot(D1, [])
    assert written == 0
    assert not repo.has_snapshot(D1)


def test_migration_adds_iep_to_existing_table(tmp_path):
    """Repo initialised twice — second init should add iep column without error."""
    db = tmp_path / "migrate.db"
    repo1 = SQLiteIEVRepository(db)
    # Simulate old schema without iep column by dropping it
    import sqlite3
    with sqlite3.connect(str(db)) as conn:
        conn.execute("ALTER TABLE iev_snapshots DROP COLUMN iep")
    # Re-init should re-add the column via migration
    repo2 = SQLiteIEVRepository(db)
    repo2.save_snapshot(D1, [MoverData("BBCA", 100_000, iep=5_000)])
    rows = repo2.get_snapshot(D1)
    assert rows[0].iep == 5_000
