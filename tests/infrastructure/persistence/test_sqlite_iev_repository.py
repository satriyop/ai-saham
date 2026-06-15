"""Tests for SQLiteIEVRepository."""

import sqlite3
from datetime import date, datetime

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
    with sqlite3.connect(str(db)) as conn:
        conn.execute("ALTER TABLE iev_snapshots DROP COLUMN iep")
    # Re-init should re-add the column via migration
    repo2 = SQLiteIEVRepository(db)
    repo2.save_snapshot(D1, [MoverData("BBCA", 100_000, iep=5_000)])
    rows = repo2.get_snapshot(D1)
    assert rows[0].iep == 5_000


# ── History table + collected_at (Step 1) ────────────────────────────────────

AT_0850 = datetime(2026, 6, 10, 8, 50, 0)
AT_0855 = datetime(2026, 6, 10, 8, 55, 59)
AT_0856 = datetime(2026, 6, 10, 8, 56, 0)
AT_0857 = datetime(2026, 6, 10, 8, 57, 0)
AT_0859 = datetime(2026, 6, 10, 8, 59, 0)
AT_0905 = datetime(2026, 6, 10, 9,  5, 0)
AT_0830 = datetime(2026, 6, 10, 8, 30, 0)  # backfill / clock-fudged


def _history_rows(db_path, snapshot_date: date) -> list[sqlite3.Row]:
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT * FROM iev_snapshot_history WHERE date = ? ORDER BY id ASC",
            (snapshot_date.isoformat(),),
        ).fetchall()


def _canonical_rows(db_path, snapshot_date: date) -> list[sqlite3.Row]:
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT * FROM iev_snapshots WHERE date = ?",
            (snapshot_date.isoformat(),),
        ).fetchall()


def test_history_records_every_run(tmp_path):
    db = tmp_path / "h.db"
    repo = SQLiteIEVRepository(db)
    movers_a = [MoverData("BBCA", 400_000, 5900), MoverData("BBRI", 300_000, 3100)]
    movers_b = [MoverData("BBCA", 420_000, 5950), MoverData("BBRI", 310_000, 3150)]

    repo.save_snapshot(D1, movers_a, collected_at=AT_0850)
    repo.save_snapshot(D1, movers_b, collected_at=AT_0857)

    hist = _history_rows(db, D1)
    assert len(hist) == 4  # 2 movers × 2 runs

    canon = _canonical_rows(db, D1)
    assert len(canon) == 2  # still one row per ticker


def test_save_snapshot_no_collected_at_defaults_to_now(tmp_path):
    repo = SQLiteIEVRepository(tmp_path / "t.db")
    before = datetime.now().replace(microsecond=0)
    repo.save_snapshot(D1, [MoverData("BBCA", 100_000, 5000)])
    after = datetime.now().replace(microsecond=0)

    hist = _history_rows(tmp_path / "t.db", D1)
    assert len(hist) == 1
    # stored as seconds-precision ISO string; compare without microseconds
    ts = datetime.fromisoformat(hist[0]["collected_at"])
    assert before <= ts <= after


# ── NCP flag (Step 2) ─────────────────────────────────────────────────────────

def test_ncp_flag_false_before_0856(tmp_path):
    repo = SQLiteIEVRepository(tmp_path / "t.db")
    repo.save_snapshot(D1, [MoverData("BBCA", 100_000)], collected_at=AT_0855)
    hist = _history_rows(tmp_path / "t.db", D1)
    assert hist[0]["is_ncp_locked"] == 0


def test_ncp_flag_true_at_0856(tmp_path):
    repo = SQLiteIEVRepository(tmp_path / "t.db")
    repo.save_snapshot(D1, [MoverData("BBCA", 100_000)], collected_at=AT_0856)
    hist = _history_rows(tmp_path / "t.db", D1)
    assert hist[0]["is_ncp_locked"] == 1


def test_ncp_flag_true_after_0856(tmp_path):
    repo = SQLiteIEVRepository(tmp_path / "t.db")
    repo.save_snapshot(D1, [MoverData("BBCA", 100_000)], collected_at=AT_0905)
    hist = _history_rows(tmp_path / "t.db", D1)
    assert hist[0]["is_ncp_locked"] == 1


def test_canonical_ncp_flag_sticky(tmp_path):
    """Once canonical is_ncp_locked=1, a later pre-NCP backfill must not downgrade it."""
    db = tmp_path / "t.db"
    repo = SQLiteIEVRepository(db)
    repo.save_snapshot(D1, [MoverData("BBCA", 100_000)], collected_at=AT_0857)
    repo.save_snapshot(D1, [MoverData("BBCA", 90_000)],  collected_at=AT_0830)

    canon = _canonical_rows(db, D1)
    assert canon[0]["is_ncp_locked"] == 1


def test_migration_adds_is_ncp_locked_to_old_db(tmp_path):
    db = tmp_path / "old.db"
    repo1 = SQLiteIEVRepository(db)
    with sqlite3.connect(str(db)) as conn:
        conn.execute("ALTER TABLE iev_snapshots DROP COLUMN is_ncp_locked")
    repo2 = SQLiteIEVRepository(db)
    repo2.save_snapshot(D1, [MoverData("BBCA", 100_000)], collected_at=AT_0857)
    canon = _canonical_rows(db, D1)
    assert canon[0]["is_ncp_locked"] == 1


# ── get_iev_delta (Step 3) ───────────────────────────────────────────────────

def test_get_iev_delta_two_runs(tmp_path):
    repo = SQLiteIEVRepository(tmp_path / "t.db")
    repo.save_snapshot(D1, [MoverData("BBCA", 400_000), MoverData("BBRI", 300_000)], collected_at=AT_0850)
    repo.save_snapshot(D1, [MoverData("BBCA", 450_000), MoverData("BBRI", 290_000)], collected_at=AT_0857)

    delta = repo.get_iev_delta(D1)
    assert delta == {"BBCA": 50_000, "BBRI": -10_000}


def test_get_iev_delta_empty_single_run(tmp_path):
    repo = SQLiteIEVRepository(tmp_path / "t.db")
    repo.save_snapshot(D1, [MoverData("BBCA", 400_000)], collected_at=AT_0850)
    assert repo.get_iev_delta(D1) == {}


def test_get_iev_delta_ignores_other_dates(tmp_path):
    repo = SQLiteIEVRepository(tmp_path / "t.db")
    repo.save_snapshot(D1, [MoverData("BBCA", 400_000)], collected_at=AT_0850)
    repo.save_snapshot(D1, [MoverData("BBCA", 450_000)], collected_at=AT_0857)
    repo.save_snapshot(D2, [MoverData("BBCA", 200_000)], collected_at=AT_0850)
    repo.save_snapshot(D2, [MoverData("BBCA", 250_000)], collected_at=AT_0857)

    delta_d1 = repo.get_iev_delta(D1)
    delta_d2 = repo.get_iev_delta(D2)
    assert delta_d1 == {"BBCA": 50_000}
    assert delta_d2 == {"BBCA": 50_000}


# ── get_ncp_snapshot (Step 4) ────────────────────────────────────────────────

def test_get_ncp_snapshot_returns_locked_batch(tmp_path):
    repo = SQLiteIEVRepository(tmp_path / "t.db")
    movers_pre = [MoverData("BBRI", 300_000, 3100)]
    movers_ncp  = [MoverData("BBCA", 450_000, 5950), MoverData("BMRI", 200_000, 4200)]

    repo.save_snapshot(D1, movers_pre, collected_at=AT_0850)
    repo.save_snapshot(D1, movers_ncp,  collected_at=AT_0857)

    result = repo.get_ncp_snapshot(D1)
    tickers = [r.ticker for r in result]
    assert "BBCA" in tickers
    assert "BMRI" in tickers
    assert "BBRI" not in tickers  # pre-NCP only — not in NCP batch


def test_get_ncp_snapshot_fallback_no_history(tmp_path):
    """When history table is empty (old data), fall back to get_snapshot."""
    db = tmp_path / "t.db"
    repo = SQLiteIEVRepository(db)
    # Write to canonical only (simulate pre-NCP-tracking historical data)
    repo.save_snapshot(D1, [MoverData("BBCA", 400_000, 5900)], collected_at=AT_0850)
    # Clear history to simulate "before this feature was deployed"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("DELETE FROM iev_snapshot_history")

    result = repo.get_ncp_snapshot(D1)
    assert len(result) == 1
    assert result[0].ticker == "BBCA"


def test_get_ncp_snapshot_picks_latest_locked(tmp_path):
    repo = SQLiteIEVRepository(tmp_path / "t.db")
    repo.save_snapshot(D1, [MoverData("BBCA", 440_000, 5920)], collected_at=AT_0857)
    repo.save_snapshot(D1, [MoverData("BBCA", 460_000, 5960)], collected_at=AT_0859)

    result = repo.get_ncp_snapshot(D1)
    assert result[0].iev == 460_000  # latest locked batch


def test_get_ncp_snapshot_top_n(tmp_path):
    repo = SQLiteIEVRepository(tmp_path / "t.db")
    movers = [
        MoverData("BBCA", 500_000, 5900),
        MoverData("BBRI", 400_000, 3100),
        MoverData("BMRI", 300_000, 4200),
    ]
    repo.save_snapshot(D1, movers, collected_at=AT_0857)

    result = repo.get_ncp_snapshot(D1, top_n=2)
    assert len(result) == 2
    assert result[0].ticker == "BBCA"
    assert result[1].ticker == "BBRI"
