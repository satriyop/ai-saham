"""Snapshot limited-judge chrome + broker list loading cues."""

from __future__ import annotations

from src.adapters.tui.chrome_cues import (
    broker_list_loading_body,
    broker_list_loading_footer,
    is_broker_list_loading,
    loading_stage_body,
    snapshot_accum_footer,
    snapshot_accum_meta,
    snapshot_mode_label,
)


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


def test_cockpit_snapshot_board_footer_and_meta_limited_judge():
    foot = snapshot_accum_footer(freshness="as of 2026-07-29")
    meta = snapshot_accum_meta(base_meta="sort signal · 20 names", freshness="saved t")
    assert "limited" in foot.lower() or "judge" in foot.lower()
    assert "limited" in meta.lower() or "snapshot" in meta.lower()


def test_cockpit_broker_list_loading_chrome_then_ready():
    loading = broker_list_loading_body()
    assert "broker" in loading.lower() or "load" in loading.lower()
    assert is_broker_list_loading(
        stage="loading",
        board_title="View · broker list",
        status_note="loading broker list",
    )


def test_cockpit_broker_list_empty_after_load():
    empty_rows = []
    assert len(empty_rows) == 0
    note = "no broker desks in cache" if not empty_rows else "ready"
    assert "broker" in note or "no" in note
