"""Last-run accum board snapshot write/read (presentation cache)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from src.adapters.tui.board_snapshot import (
    AccumBoardSnapshotIdentity,
    board_view_from_snapshot,
    default_accum_snapshot_path,
    identity_from_live_payload,
    invalidate_accum_board_snapshot,
    read_accum_board_snapshot,
    snapshot_from_board_view,
    write_accum_board_snapshot,
)
from src.adapters.tui.presenters.accum_presenter import AccumPresenter


def _fake_result():
    c = SimpleNamespace(
        ticker="BBCA",
        accum_score=55.0,
        rsi=50.0,
        consecutive_streak=3,
        net_buy_ratio=0.6,
        vwap_discount_pct=1.0,
        current_price=9000,
        setup_phase=SimpleNamespace(current_phase=SimpleNamespace(value="COMPRESSION")),
        trade_setup=SimpleNamespace(
            action=SimpleNamespace(value="WATCH", short="WATCH"),
            rationale="t",
        ),
        signal_assessment=SimpleNamespace(
            assessment=SimpleNamespace(score=70, strength=SimpleNamespace(value="MODERATE"))
        ),
        risk_assessment=SimpleNamespace(
            gate_triggered=None,
            gate_is_structural=False,
            rationale=("ok",),
        ),
        name="BBCA",
    )
    projection = SimpleNamespace(
        candidates=[c],
        window_days=7,
        data_as_of={"latest_candle_date": "2026-07-25"},
        applied_filters=SimpleNamespace(sort_by="signal", top=20),
    )
    return SimpleNamespace(single_projection=projection, multi_projection=None, warnings=())


def test_roundtrip_snapshot_identity_and_rows(tmp_path: Path):
    payload = _fake_result()
    view = AccumPresenter().present(payload)
    identity = identity_from_live_payload(payload, view, universe="lq45")
    assert identity.is_complete()
    assert identity.as_of == "2026-07-25"
    assert identity.window == 7
    snap = snapshot_from_board_view(view, identity)
    assert snap.is_restorable()
    path = tmp_path / "tui_last_accum_board.json"
    write_accum_board_snapshot(path, snap)
    loaded = read_accum_board_snapshot(path)
    assert loaded is not None
    restored = board_view_from_snapshot(loaded)
    assert len(restored.rows) == 1
    assert restored.rows[0].ticker == "BBCA"
    assert restored.rows[0].signal == view.rows[0].signal
    assert restored.rows[0].source is None


def test_corrupt_and_incomplete_snapshots_refused(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    assert read_accum_board_snapshot(path) is None

    path.write_text('{"schema_version": 1, "rows": []}', encoding="utf-8")
    assert read_accum_board_snapshot(path) is None

    empty_ident = AccumBoardSnapshotIdentity(
        board_kind="accum",
        universe="",
        window=7,
        sort_by="signal",
        top=20,
        as_of="",
        captured_at="",
    )
    assert empty_ident.is_complete() is False


def test_default_snapshot_path_beside_db(tmp_path: Path):
    db = tmp_path / "data" / "db" / "data.db"
    db.parent.mkdir(parents=True)
    p = default_accum_snapshot_path(db)
    assert p.name == "tui_last_accum_board.json"
    assert p.parent == db.parent.resolve()


def test_invalidate_removes_restorable_snapshot(tmp_path: Path):
    payload = _fake_result()
    view = AccumPresenter().present(payload)
    identity = identity_from_live_payload(payload, view, universe="lq45")
    path = tmp_path / "snap.json"
    write_accum_board_snapshot(path, snapshot_from_board_view(view, identity))
    assert read_accum_board_snapshot(path) is not None
    assert invalidate_accum_board_snapshot(path) is True
    assert read_accum_board_snapshot(path) is None
    assert invalidate_accum_board_snapshot(path) is False
    assert invalidate_accum_board_snapshot(None) is False
