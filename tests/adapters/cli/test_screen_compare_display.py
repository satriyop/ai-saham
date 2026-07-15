"""S9: display tests for `saham screen compare` — weakening/unchanged buckets,
flow+signal deltas, and specific fresh-screen error reporting.

Read-only regression coverage lives in test_screen_accum_compare_factory.py
(test_compare_writes_zero_candidate_observations).
"""

from pathlib import Path
from types import SimpleNamespace

from src.adapters.cli.screen_accum_compare_factory import (
    FreshAccumulationScreenForCompareResult,
)
from src.adapters.cli.screen_lifecycle_commands import (
    _display_compare_result,
    screen_app,
)
from src.application.use_case.compare_screen_snapshots_use_case import (
    ScreenCompareResult,
    SignalChange,
)
from tests.adapters.cli.screen_accum_test_fixtures import runner


def _change(ticker, old_rank, new_rank, old_comp, new_comp, old_flow, new_flow):
    return SignalChange(
        ticker=ticker,
        old_rank=old_rank,
        new_rank=new_rank,
        old_composite=old_comp,
        new_composite=new_comp,
        old_flow=old_flow,
        new_flow=new_flow,
    )


def test_display_includes_weakening_bucket(capsys):
    result = ScreenCompareResult(
        snapshot_name="test",
        new_tickers=[],
        dropped_tickers=[],
        changed=[_change("ASII", 2, 8, 70.0, 55.0, 80.0, 72.0)],
        snapshot_count=1,
        fresh_count=1,
    )
    _display_compare_result(result)
    out = capsys.readouterr().out
    assert "WEAKENING" in out
    assert "ASII" in out


def test_display_includes_unchanged_bucket(capsys):
    result = ScreenCompareResult(
        snapshot_name="test",
        new_tickers=[],
        dropped_tickers=[],
        changed=[_change("BMRI", 3, 3, 65.0, 65.5, 80.0, 81.0)],
        snapshot_count=1,
        fresh_count=1,
    )
    _display_compare_result(result)
    out = capsys.readouterr().out
    assert "UNCHANGED" in out
    assert "BMRI" in out


def test_display_shows_flow_and_signal_deltas(capsys):
    result = ScreenCompareResult(
        snapshot_name="test",
        new_tickers=[],
        dropped_tickers=[],
        changed=[_change("BBCA", 8, 2, 60.0, 75.0, 80.0, 95.0)],
        snapshot_count=1,
        fresh_count=1,
    )
    _display_compare_result(result)
    out = capsys.readouterr().out
    assert "flow +15.0" in out
    assert "signal +15.0" in out


def test_display_shows_signal_na_when_composite_none(capsys):
    result = ScreenCompareResult(
        snapshot_name="test",
        new_tickers=[],
        dropped_tickers=[],
        changed=[_change("NEWCO", 10, 2, None, None, 60.0, 65.0)],
        snapshot_count=1,
        fresh_count=1,
    )
    _display_compare_result(result)
    out = capsys.readouterr().out
    assert "signal N/A" in out


def test_display_shows_legacy_warning(capsys):
    result = ScreenCompareResult(
        snapshot_name="test",
        new_tickers=[],
        dropped_tickers=[],
        changed=[],
        snapshot_count=1,
        fresh_count=1,
        warnings=("Saved snapshot 'test' uses legacy 0-120 score scale; values normalized.",),
    )
    _display_compare_result(result)
    out = capsys.readouterr().out
    assert "legacy 0-120" in out


_FAKE_SWING = SimpleNamespace(
    tier1_broker_codes=frozenset(),
    bci_cluster_min_count=3,
    bci_stable_min_count=1,
    resistance_gate_enabled=False,
    resistance_headroom_min_pct=5.0,
    ex_date_warning_days=10,
)


def test_compare_command_shows_specific_fresh_screen_error(monkeypatch, tmp_path):
    from src.infrastructure.persistence.sqlite_watchlist_repository import (
        SQLiteWatchlistRepository,
    )
    from src.domain.value_objects.screen_snapshot import ScreenSnapshotEntry
    from datetime import datetime

    db_path = tmp_path / "test.db"
    repo = SQLiteWatchlistRepository(db_path)
    repo.save_snapshot([
        ScreenSnapshotEntry(
            name="morning-watch",
            saved_at=datetime(2026, 6, 20, 9, 0),
            universe="lq45",
            window_days=7,
            ticker="BBCA",
            rank=1,
            flow_score=80.0,
            composite_score=65.0,
            consecutive_streak=3,
            net_buy_ratio=0.71,
            bci_label="CLUSTER",
        )
    ])

    monkeypatch.setattr(
        "src.adapters.cli.screen_accum_compare_factory.run_fresh_accumulation_screen_for_compare",
        lambda **kwargs: FreshAccumulationScreenForCompareResult(
            candidates=[],
            error="Fresh accumulation screen failed: ValueError: bad data",
        ),
    )

    result = runner.invoke(
        screen_app,
        ["compare", "morning-watch", "--db", str(db_path)],
    )

    assert "Fresh accumulation screen failed: ValueError: bad data" in result.stdout
    assert "Could not run fresh screen" not in result.stdout
