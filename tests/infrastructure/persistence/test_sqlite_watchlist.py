"""Tests for SQLiteWatchlistRepository and compare_screen_snapshots."""

from datetime import datetime

import pytest

from src.application.use_case.compare_screen_snapshots import (
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
        flow_score=flow,
        composite_score=comp,
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


def test_snapshot_exists(repo):
    assert repo.snapshot_exists("nonexistent") is False
    repo.save_snapshot([_entry("BBCA", 1)])
    assert repo.snapshot_exists("test") is True


def test_save_empty_is_noop(repo):
    repo.save_snapshot([])
    assert repo.get_latest_snapshot("test") == []


def test_composite_score_none_persisted(repo):
    entries = [_entry("GOTO", 1, comp=None)]
    repo.save_snapshot(entries)
    result = repo.get_latest_snapshot("test")
    assert result[0].composite_score is None


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
    from src.application.use_case.compare_screen_snapshots import SignalChange
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
