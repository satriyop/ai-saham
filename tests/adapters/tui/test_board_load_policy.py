"""Pure board load/refresh policy decisions."""

from __future__ import annotations

from src.adapters.tui.board_load_policy import (
    recomputing_status_note,
    should_blank_board_for_load,
    snapshot_freshness_note,
)


def test_blank_when_no_rows():
    assert (
        should_blank_board_for_load(
            has_visible_rows=False,
            current_stage="shell",
            current_board_kind="none",
            target_board_kind="accum",
        )
        is True
    )


def test_keep_prior_when_same_kind_ready():
    assert (
        should_blank_board_for_load(
            has_visible_rows=True,
            current_stage="accum",
            current_board_kind="accum",
            target_board_kind="accum",
        )
        is False
    )


def test_blank_when_switching_board_kind():
    assert (
        should_blank_board_for_load(
            has_visible_rows=True,
            current_stage="accum",
            current_board_kind="accum",
            target_board_kind="preopen",
        )
        is True
    )


def test_status_and_freshness_notes():
    assert "recomputing" in recomputing_status_note(row_count=12, summary="12 names")
    note = snapshot_freshness_note(
        as_of="2026-07-25",
        captured_at="2026-07-25T12:00:00+00:00",
        universe="lq45",
    )
    assert "snapshot" in note
    assert "2026-07-25" in note
    assert "lq45" in note
