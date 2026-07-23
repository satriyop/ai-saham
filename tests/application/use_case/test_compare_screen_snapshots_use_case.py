"""Tests for S9: weakening/unchanged buckets, flow/composite delta, legacy scale normalization."""

from datetime import datetime

import pytest

from src.application.use_case.compare_screen_snapshots_use_case import (
    compare_screen_snapshots,
)
from src.domain.value_objects.screen_snapshot import ScreenSnapshotEntry


def _entry(
    ticker: str,
    rank: int,
    flow: float = 80.0,
    comp: float | None = 65.0,
    name: str = "test",
) -> ScreenSnapshotEntry:
    return ScreenSnapshotEntry(
        name=name,
        saved_at=datetime(2026, 6, 20, 9, 0),
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


def test_weakening_ticker_appears_in_weakening_bucket():
    snapshot = [_entry("ASII", rank=2, flow=80.0, comp=70.0)]
    result = compare_screen_snapshots(
        snapshot=snapshot,
        fresh_tickers=["ASII"],
        fresh_scores={"ASII": (72.0, 55.0)},
        fresh_ranks={"ASII": 8},
        snapshot_name="test",
    )
    assert len(result.weakening) == 1
    assert result.weakening[0].ticker == "ASII"
    assert result.strengthening == []
    assert result.unchanged == []


def test_strengthening_ticker_appears_in_strengthening_bucket():
    snapshot = [_entry("BBCA", rank=8, flow=80.0, comp=60.0)]
    result = compare_screen_snapshots(
        snapshot=snapshot,
        fresh_tickers=["BBCA"],
        fresh_scores={"BBCA": (85.0, 75.0)},
        fresh_ranks={"BBCA": 2},
        snapshot_name="test",
    )
    assert len(result.strengthening) == 1
    assert result.strengthening[0].ticker == "BBCA"
    assert result.weakening == []
    assert result.unchanged == []


def test_stable_ticker_appears_in_unchanged_bucket():
    snapshot = [_entry("BMRI", rank=3, flow=80.0, comp=65.0)]
    result = compare_screen_snapshots(
        snapshot=snapshot,
        fresh_tickers=["BMRI"],
        fresh_scores={"BMRI": (81.0, 65.5)},
        fresh_ranks={"BMRI": 3},
        snapshot_name="test",
    )
    assert len(result.unchanged) == 1
    assert result.unchanged[0].ticker == "BMRI"
    assert result.strengthening == []
    assert result.weakening == []


def test_flow_delta_and_composite_delta_calculated_separately():
    snapshot = [_entry("BBRI", rank=2, flow=70.0, comp=60.0)]
    result = compare_screen_snapshots(
        snapshot=snapshot,
        fresh_tickers=["BBRI"],
        fresh_scores={"BBRI": (75.0, 72.0)},
        fresh_ranks={"BBRI": 2},
        snapshot_name="test",
    )
    change = result.changed[0]
    assert change.flow_delta == pytest.approx(5.0)
    assert change.composite_delta == pytest.approx(12.0)


def test_legacy_saved_scores_normalized_before_delta():
    # Legacy 0-120 scale: saved flow=120 (-> 100 normalized), comp=108 (-> 90 normalized)
    snapshot = [_entry("GOTO", rank=5, flow=120.0, comp=108.0)]
    result = compare_screen_snapshots(
        snapshot=snapshot,
        fresh_tickers=["GOTO"],
        fresh_scores={"GOTO": (100.0, 90.0)},
        fresh_ranks={"GOTO": 5},
        snapshot_name="test",
    )
    change = result.changed[0]
    assert change.old_flow == pytest.approx(100.0)
    assert change.old_composite == pytest.approx(90.0)
    assert change.flow_delta == pytest.approx(0.0)
    assert change.composite_delta == pytest.approx(0.0)


def test_legacy_normalization_emits_warning():
    snapshot = [_entry("GOTO", rank=5, flow=120.0, comp=108.0)]
    result = compare_screen_snapshots(
        snapshot=snapshot,
        fresh_tickers=["GOTO"],
        fresh_scores={"GOTO": (100.0, 90.0)},
        fresh_ranks={"GOTO": 5},
        snapshot_name="test",
    )
    assert len(result.warnings) == 1
    assert "legacy 0-120" in result.warnings[0]
    assert "normalized" in result.warnings[0]


def test_fresh_scale_not_normalized_when_no_legacy_indicator():
    snapshot = [_entry("BBCA", rank=1, flow=80.0, comp=65.0)]
    result = compare_screen_snapshots(
        snapshot=snapshot,
        fresh_tickers=["BBCA"],
        fresh_scores={"BBCA": (85.0, 70.0)},
        fresh_ranks={"BBCA": 1},
        snapshot_name="test",
    )
    assert result.warnings == ()
    change = result.changed[0]
    assert change.old_flow == pytest.approx(80.0)
    assert change.old_composite == pytest.approx(65.0)


def test_signal_up_but_rank_down_lands_in_one_bucket_only():
    # composite delta +15 (strengthening) but rank moved down (2 -> 8, weakening by rank)
    snapshot = [_entry("BBCA", rank=2, flow=80.0, comp=60.0)]
    result = compare_screen_snapshots(
        snapshot=snapshot,
        fresh_tickers=["BBCA"],
        fresh_scores={"BBCA": (80.0, 75.0)},
        fresh_ranks={"BBCA": 8},
        snapshot_name="test",
    )
    change = result.changed[0]
    assert change.rank_delta == -6
    assert change.composite_delta == pytest.approx(15.0)
    assert change.strengthening is True
    assert change.weakening is False
    assert change in result.strengthening
    assert change not in result.weakening


def test_signal_down_but_rank_up_lands_in_one_bucket_only():
    # composite delta -15 (weakening) but rank moved up (8 -> 2, strengthening by rank)
    snapshot = [_entry("ASII", rank=8, flow=80.0, comp=75.0)]
    result = compare_screen_snapshots(
        snapshot=snapshot,
        fresh_tickers=["ASII"],
        fresh_scores={"ASII": (80.0, 60.0)},
        fresh_ranks={"ASII": 2},
        snapshot_name="test",
    )
    change = result.changed[0]
    assert change.rank_delta == 6
    assert change.composite_delta == pytest.approx(-15.0)
    assert change.weakening is True
    assert change.strengthening is False
    assert change in result.weakening
    assert change not in result.strengthening


def test_composite_missing_uses_rank_fallback_both_directions():
    up = [_entry("NEWCO", rank=10, flow=60.0, comp=None)]
    up_result = compare_screen_snapshots(
        snapshot=up,
        fresh_tickers=["NEWCO"],
        fresh_scores={"NEWCO": (65.0, None)},
        fresh_ranks={"NEWCO": 2},
        snapshot_name="test",
    )
    up_change = up_result.changed[0]
    assert up_change.composite_delta is None
    assert up_change.strengthening is True
    assert up_change.weakening is False

    down = [_entry("OLDCO", rank=2, flow=60.0, comp=None)]
    down_result = compare_screen_snapshots(
        snapshot=down,
        fresh_tickers=["OLDCO"],
        fresh_scores={"OLDCO": (55.0, None)},
        fresh_ranks={"OLDCO": 10},
        snapshot_name="test",
    )
    down_change = down_result.changed[0]
    assert down_change.composite_delta is None
    assert down_change.weakening is True
    assert down_change.strengthening is False


def test_composite_none_does_not_crash_and_classifies_by_rank_only():
    snapshot = [_entry("NEWCO", rank=10, flow=60.0, comp=None)]
    result = compare_screen_snapshots(
        snapshot=snapshot,
        fresh_tickers=["NEWCO"],
        fresh_scores={"NEWCO": (65.0, None)},
        fresh_ranks={"NEWCO": 2},
        snapshot_name="test",
    )
    change = result.changed[0]
    assert change.composite_delta is None
    # rank_delta = 10 - 2 = 8 >= 3 -> strengthening despite missing composite
    assert change.strengthening is True
    assert change in result.strengthening
