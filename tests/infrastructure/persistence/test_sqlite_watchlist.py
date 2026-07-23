"""Tests for SQLiteWatchlistRepository and compare_screen_snapshots."""

from datetime import datetime

import pytest

from src.application.use_case.compare_screen_snapshots_use_case import (
    compare_screen_snapshots,
)
from src.domain.value_objects.screen_snapshot import ScreenSnapshotEntry
from src.infrastructure.persistence.sqlite_watchlist_repository import (
    SQLiteWatchlistRepository,
)


def _entry(ticker: str, rank: int, flow: float = 80.0, comp: float | None = 65.0,
           name: str = "test", saved_at: datetime | None = None) -> ScreenSnapshotEntry:
    return ScreenSnapshotEntry(
        name=name,
        saved_at=saved_at or datetime(2026, 6, 20, 9, 0),
        universe="lq45",
        window_days=7,
        ticker=ticker,
        rank=rank,
        accum_score=flow,
        signal_score=comp,
        consecutive_streak=3,
        net_buy_ratio=0.71,
        bci_label="CLUSTER",
    )


@pytest.fixture
def repo(tmp_path):
    return SQLiteWatchlistRepository(tmp_path / "test.db")


# ── Schema ────────────────────────────────────────────────────────────────────

def test_schema_created(repo):
    with repo._get_conn() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='screen_snapshots'"
        ).fetchone()
    assert row is not None


# ── Save / read round-trip ────────────────────────────────────────────────────

def test_save_and_retrieve_snapshot(repo):
    entries = [_entry("BBCA", 1), _entry("BBRI", 2), _entry("BMRI", 3)]
    repo.save_snapshot(entries)

    result = repo.get_latest_snapshot("test")
    assert len(result) == 3
    assert result[0].ticker == "BBCA"
    assert result[0].rank == 1
    assert result[1].ticker == "BBRI"


def test_latest_snapshot_returns_most_recent(repo):
    old_entries = [_entry("BBCA", 1, saved_at=datetime(2026, 6, 19, 9, 0))]
    new_entries = [_entry("BBRI", 1, saved_at=datetime(2026, 6, 20, 9, 0))]
    repo.save_snapshot(old_entries)
    repo.save_snapshot(new_entries)

    result = repo.get_latest_snapshot("test")
    assert len(result) == 1
    assert result[0].ticker == "BBRI"


def test_list_snapshots_returns_all_names(repo):
    repo.save_snapshot([_entry("BBCA", 1, name="morning")])
    repo.save_snapshot([_entry("BBRI", 1, name="evening")])

    summaries = repo.list_snapshots()
    names = {s["name"] for s in summaries}
    assert "morning" in names
    assert "evening" in names


def test_list_snapshots_counts_latest_run_only(repo):
    entries_a = [
        ScreenSnapshotEntry(
            name="multi-run", saved_at=datetime(2026, 7, 1, 9, 0),
            universe="lq45", window_days=7,
            ticker="BBCA", rank=1, accum_score=70.0, signal_score=65.0,
            consecutive_streak=3, net_buy_ratio=0.5, bci_label="CLUSTER",
        ),
        ScreenSnapshotEntry(
            name="multi-run", saved_at=datetime(2026, 7, 1, 9, 0),
            universe="lq45", window_days=7,
            ticker="BBRI", rank=2, accum_score=60.0, signal_score=55.0,
            consecutive_streak=2, net_buy_ratio=0.4, bci_label="CLUSTER",
        ),
        ScreenSnapshotEntry(
            name="multi-run", saved_at=datetime(2026, 7, 1, 9, 0),
            universe="lq45", window_days=7,
            ticker="BMRI", rank=3, accum_score=50.0, signal_score=45.0,
            consecutive_streak=1, net_buy_ratio=0.3, bci_label="CLUSTER",
        ),
    ]
    entries_b = [
        ScreenSnapshotEntry(
            name="multi-run", saved_at=datetime(2026, 7, 2, 9, 0),
            universe="idx80", window_days=30,
            ticker="BBCA", rank=1, accum_score=80.0, signal_score=70.0,
            consecutive_streak=4, net_buy_ratio=0.6, bci_label="SMART",
        ),
        ScreenSnapshotEntry(
            name="multi-run", saved_at=datetime(2026, 7, 2, 9, 0),
            universe="idx80", window_days=30,
            ticker="BBRI", rank=2, accum_score=75.0, signal_score=65.0,
            consecutive_streak=3, net_buy_ratio=0.5, bci_label="SMART",
        ),
    ]
    entries_c = [
        ScreenSnapshotEntry(
            name="multi-run", saved_at=datetime(2026, 7, 3, 9, 0),
            universe="custom", window_days=90,
            ticker="BBCA", rank=1, accum_score=90.0, signal_score=80.0,
            consecutive_streak=5, net_buy_ratio=0.7, bci_label="SMART",
        ),
        ScreenSnapshotEntry(
            name="multi-run", saved_at=datetime(2026, 7, 3, 9, 0),
            universe="custom", window_days=90,
            ticker="BBRI", rank=2, accum_score=85.0, signal_score=75.0,
            consecutive_streak=4, net_buy_ratio=0.6, bci_label="SMART",
        ),
        ScreenSnapshotEntry(
            name="multi-run", saved_at=datetime(2026, 7, 3, 9, 0),
            universe="custom", window_days=90,
            ticker="BMRI", rank=3, accum_score=80.0, signal_score=70.0,
            consecutive_streak=3, net_buy_ratio=0.5, bci_label="SMART",
        ),
        ScreenSnapshotEntry(
            name="multi-run", saved_at=datetime(2026, 7, 3, 9, 0),
            universe="custom", window_days=90,
            ticker="GOTO", rank=4, accum_score=75.0, signal_score=65.0,
            consecutive_streak=2, net_buy_ratio=0.4, bci_label="NOISE",
        ),
    ]
    repo.save_snapshot(entries_a)
    repo.save_snapshot(entries_b)
    repo.save_snapshot(entries_c)

    summaries = repo.list_snapshots()
    assert len(summaries) == 1
    s = summaries[0]
    assert s["name"] == "multi-run"
    assert s["ticker_count"] == 4


def test_list_snapshots_uses_latest_universe_and_window_days(repo):
    old = [
        ScreenSnapshotEntry(
            name="morning-watch", saved_at=datetime(2026, 7, 1, 9, 0),
            universe="lq45", window_days=7,
            ticker="BBCA", rank=1, accum_score=70.0, signal_score=65.0,
            consecutive_streak=3, net_buy_ratio=0.5, bci_label="CLUSTER",
        ),
    ]
    latest = [
        ScreenSnapshotEntry(
            name="morning-watch", saved_at=datetime(2026, 7, 3, 9, 0),
            universe="custom", window_days=90,
            ticker="BBCA", rank=1, accum_score=90.0, signal_score=80.0,
            consecutive_streak=5, net_buy_ratio=0.7, bci_label="SMART",
        ),
    ]
    repo.save_snapshot(old)
    repo.save_snapshot(latest)

    summaries = repo.list_snapshots()
    assert len(summaries) == 1
    s = summaries[0]
    assert s["universe"] == "custom"
    assert s["window_days"] == 90


def test_list_snapshots_orders_by_latest_saved_at_desc(repo):
    early = [
        ScreenSnapshotEntry(
            name="alpha", saved_at=datetime(2026, 7, 1, 9, 0),
            universe="lq45", window_days=7,
            ticker="BBCA", rank=1, accum_score=70.0, signal_score=65.0,
            consecutive_streak=3, net_buy_ratio=0.5, bci_label="CLUSTER",
        ),
    ]
    late = [
        ScreenSnapshotEntry(
            name="beta", saved_at=datetime(2026, 7, 3, 9, 0),
            universe="lq45", window_days=7,
            ticker="BBCA", rank=1, accum_score=90.0, signal_score=80.0,
            consecutive_streak=5, net_buy_ratio=0.7, bci_label="SMART",
        ),
    ]
    repo.save_snapshot(early)
    repo.save_snapshot(late)

    summaries = repo.list_snapshots()
    assert len(summaries) == 2
    assert summaries[0]["name"] == "beta"
    assert summaries[1]["name"] == "alpha"


def test_snapshot_exists(repo):
    assert repo.snapshot_exists("nonexistent") is False
    repo.save_snapshot([_entry("BBCA", 1)])
    assert repo.snapshot_exists("test") is True


def test_save_empty_is_noop(repo):
    repo.save_snapshot([])
    assert repo.get_latest_snapshot("test") == []


def test_signal_score_none_persisted(repo):
    entries = [_entry("GOTO", 1, comp=None)]
    repo.save_snapshot(entries)
    result = repo.get_latest_snapshot("test")
    assert result[0].signal_score is None


def test_legacy_flow_score_columns_dual_read(tmp_path):
    """ADR-043: rows written before accum_score/signal_score columns remain readable."""
    db_path = tmp_path / "legacy_watchlist.db"
    # Build a pre-ADR-043 schema directly (old column names only).
    import sqlite3

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE screen_snapshots (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                name              TEXT    NOT NULL,
                saved_at          TEXT    NOT NULL,
                universe          TEXT    NOT NULL DEFAULT '',
                window_days       INTEGER NOT NULL DEFAULT 7,
                ticker            TEXT    NOT NULL,
                rank              INTEGER NOT NULL,
                flow_score        REAL    NOT NULL,
                composite_score   REAL,
                consecutive_streak INTEGER NOT NULL DEFAULT 0,
                net_buy_ratio     REAL    NOT NULL DEFAULT 0,
                bci_label         TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO screen_snapshots
                (name, saved_at, universe, window_days, ticker, rank,
                 flow_score, composite_score, consecutive_streak, net_buy_ratio, bci_label)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy",
                "2026-06-01T09:00:00",
                "lq45",
                7,
                "BBCA",
                1,
                77.5,
                62.0,
                4,
                0.55,
                "CLUSTER",
            ),
        )

    from src.infrastructure.persistence.sqlite_watchlist_repository import (
        SQLiteWatchlistRepository,
    )

    repo = SQLiteWatchlistRepository(db_path=db_path)
    result = repo.get_latest_snapshot("legacy")
    assert len(result) == 1
    assert result[0].accum_score == 77.5
    assert result[0].signal_score == 62.0


# ── compare_screen_snapshots ──────────────────────────────────────────────────

def _snap(tickers: list[str]) -> list[ScreenSnapshotEntry]:
    return [_entry(t, i + 1) for i, t in enumerate(tickers)]


def test_compare_identifies_new_tickers():
    snapshot = _snap(["BBCA", "BBRI"])
    fresh = ["BBCA", "BMRI"]
    result = compare_screen_snapshots(
        snapshot=snapshot,
        fresh_tickers=fresh,
        fresh_scores={"BBCA": (80.0, 65.0), "BMRI": (75.0, 60.0)},
        fresh_ranks={"BBCA": 1, "BMRI": 2},
        snapshot_name="test",
    )
    assert "BMRI" in result.new_tickers
    assert "BBCA" not in result.new_tickers


def test_compare_identifies_dropped_tickers():
    snapshot = _snap(["BBCA", "BBRI"])
    fresh = ["BBCA"]
    result = compare_screen_snapshots(
        snapshot=snapshot,
        fresh_tickers=fresh,
        fresh_scores={"BBCA": (80.0, 65.0)},
        fresh_ranks={"BBCA": 1},
        snapshot_name="test",
    )
    assert "BBRI" in result.dropped_tickers


def test_compare_changed_tracks_movement():
    snapshot = _snap(["BBCA", "BBRI"])
    fresh = ["BBCA", "BBRI"]
    result = compare_screen_snapshots(
        snapshot=snapshot,
        fresh_tickers=fresh,
        fresh_scores={"BBCA": (95.0, 80.0), "BBRI": (70.0, 55.0)},
        fresh_ranks={"BBCA": 1, "BBRI": 2},
        snapshot_name="test",
    )
    bbca_change = next(c for c in result.changed if c.ticker == "BBCA")
    assert bbca_change.new_composite == pytest.approx(80.0)
    assert bbca_change.composite_delta == pytest.approx(15.0)


def test_compare_strengthening_flag():
    from src.application.use_case.compare_screen_snapshots_use_case import SignalChange
    change = SignalChange(
        ticker="BBCA", old_rank=8, new_rank=2,
        old_composite=60.0, new_composite=75.0,
        old_flow=80.0, new_flow=95.0,
    )
    assert change.rank_delta == 6
    assert change.composite_delta == pytest.approx(15.0)
    assert change.strengthening is True


def test_compare_counts_match():
    snapshot = _snap(["BBCA", "BBRI", "BMRI"])
    fresh = ["BBCA", "GOTO"]
    result = compare_screen_snapshots(
        snapshot=snapshot,
        fresh_tickers=fresh,
        fresh_scores={"BBCA": (80.0, 65.0), "GOTO": (70.0, 55.0)},
        fresh_ranks={"BBCA": 1, "GOTO": 2},
        snapshot_name="test",
    )
    assert result.snapshot_count == 3
    assert result.fresh_count == 2
    assert result.new_tickers == ["GOTO"]
    assert set(result.dropped_tickers) == {"BBRI", "BMRI"}
