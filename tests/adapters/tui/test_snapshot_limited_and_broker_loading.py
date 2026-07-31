"""Snapshot limited-judge chrome + broker list loading cues."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace

from src.adapters.composition.board_snapshot_store import (
    write_accum_board_snapshot,
)
from src.adapters.tui.board_snapshot import (
    AccumBoardSnapshot,
    AccumBoardSnapshotIdentity,
)
from src.adapters.tui.chrome_cues import (
    broker_list_loading_body,
    broker_list_loading_footer,
    is_broker_list_loading,
    loading_stage_body,
    snapshot_accum_footer,
    snapshot_accum_meta,
    snapshot_mode_label,
)
from src.adapters.tui.main import CockpitApp


def test_snapshot_footer_states_limited_judge_and_escape_hatch():
    text = snapshot_accum_footer(freshness="as of 2026-07-29").lower()
    assert "limited judge" in text
    assert "enter" in text
    assert "j" in text and ("re-judge" in text or "rejudge" in text)
    assert "r" in text and ("live" in text or "recompute" in text or "full" in text)
    # Must not sound like full desk only
    assert "enter = limited" in text or "enter limited" in text.replace(" ", "")


def test_snapshot_meta_and_mode_cue():
    meta = snapshot_accum_meta(base_meta="sort signal · 20 names", freshness="saved t")
    assert "limited judge" in meta.lower()
    assert "j/r" in meta.lower() or "j" in meta.lower()
    assert "snapshot" in snapshot_mode_label().lower()
    assert "limited" in snapshot_mode_label().lower()


def test_broker_loading_copy_names_broker():
    body = broker_list_loading_body().lower()
    assert "broker" in body
    assert "loading" in body
    assert "not hung" in body or "local cache" in body
    foot = broker_list_loading_footer().lower()
    assert "broker" in foot and "loading" in foot
    assert is_broker_list_loading(
        stage="loading",
        board_title="View · broker list",
        status_note="loading broker list",
    )
    assert (
        "broker"
        in loading_stage_body(
            board_title="View · broker list",
            status_note="loading broker list",
            stage="loading",
        ).lower()
    )


def test_cockpit_snapshot_board_footer_and_meta_limited_judge(tmp_path: Path):
    snap_path = tmp_path / "snap.json"
    identity = AccumBoardSnapshotIdentity(
        board_kind="accum",
        universe="lq45",
        window=7,
        sort_by="signal",
        top=20,
        as_of="2026-07-29",
        captured_at="2026-07-29T12:00:00+00:00",
    )
    snap = AccumBoardSnapshot(
        schema_version=1,
        identity=identity,
        meta="sort signal · 1 names",
        cache_label="local",
        summary="1 WATCH",
        columns=("Ticker", "Signal", "Accum", "Action"),
        rows=(
            {
                "ticker": "ITMG",
                "signal": "80",
                "accum": "50",
                "action": "WATCH",
                "phase": "ACCUMULATION",
                "streak": "2",
                "rsi": "50",
                "net_pct": "0.5",
                "disc_pct": "0",
                "price": "1000",
                "gate": "OPEN",
                "name": "ITMG",
            },
        ),
    )
    write_accum_board_snapshot(snap_path, snap)

    async def scenario() -> None:
        app = CockpitApp(board_snapshot_path=snap_path, snapshot_universe="lq45")
        async with app.run_test(size=(140, 36)) as pilot:
            await pilot.pause(0.05)
            restored = app._try_restore_accum_snapshot()
            await pilot.pause(0.05)
            assert restored is True
            assert app._board_source == "snapshot"
            assert app._stage == "accum"
            footer = app._footer_hint().lower()
            assert "limited judge" in footer
            assert "j" in footer
            assert "r" in footer
            # Not only vague "Enter judge"
            assert "limited" in footer
            meta = (app._meta or "").lower()
            assert "limited" in meta
            mode = app._mode_label().lower()
            assert "snapshot" in mode
            assert "limited" in mode
            # Enter judge is limited
            app._open_detail()
            await pilot.pause(0.05)
            assert app._judge_limited is True
            jfoot = app._footer_hint().lower()
            assert "limited judge" in jfoot
            assert "j" in jfoot and "r" in jfoot

    asyncio.run(scenario())


def test_cockpit_broker_list_loading_chrome_then_ready():
    gate = threading.Event()

    def slow_loader():
        gate.wait(timeout=5.0)
        return [
            SimpleNamespace(
                code="YP",
                broker_type="T1",
                as_of="2026-07-29",
                day_net="1",
                net5="2",
                buy_streak="1",
                delta1="0",
                rank="1",
                top_buy="BBCA",
                has_data=True,
            )
        ]

    async def scenario() -> None:
        app = CockpitApp(broker_list_loader=slow_loader)
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause(0.05)
            app._open_view_broker_list()
            await pilot.pause(0.1)
            assert app._stage == "loading"
            body = str(app.query_one("#stage-body").render()).lower()
            assert "broker" in body
            assert "loading" in body
            footer = app._footer_hint().lower()
            assert "broker" in footer and "loading" in footer
            meta = (app._meta or "").lower()
            assert "desk" in meta or "broker" in meta or "loading" in meta
            gate.set()
            for _ in range(80):
                await pilot.pause(0.05)
                if app._stage == "broker-list":
                    break
            assert app._stage == "broker-list"
            assert len(app._broker_rows) == 1
            assert app._broker_rows[0].code == "YP"

    asyncio.run(scenario())


def test_cockpit_broker_list_empty_after_load():
    async def scenario() -> None:
        app = CockpitApp(broker_list_loader=lambda: [])
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause(0.05)
            app._open_view_broker_list()
            for _ in range(40):
                await pilot.pause(0.05)
                if app._stage == "empty":
                    break
            assert app._stage == "empty"
            body = str(app.query_one("#stage-body").render()).lower()
            assert "desk" in body or "broker" in body

    asyncio.run(scenario())
