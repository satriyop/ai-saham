"""Unit tests for screen discovery envelope contract."""

from datetime import date

from src.application.dto.screen_contract import (
    ScreenResultStatus,
    ScreenSubjectKind,
    build_screen_envelope,
    missing_screen_message,
)


def test_build_screen_envelope_keys():
    payload = build_screen_envelope(
        verb="accum",
        status=ScreenResultStatus.OK,
        subject_kind=ScreenSubjectKind.UNIVERSE,
        subject_id="lq45",
        as_of=date(2026, 7, 23),
        source="accumulation_screen",
        scope="single",
        window_days=7,
        fetch_hint="saham fetch market --universe lq45",
        data={"candidates": []},
    )
    assert set(payload.keys()) == {
        "subject",
        "verb",
        "as_of",
        "window",
        "source",
        "scope",
        "scope_note",
        "status",
        "fetch_hint",
        "data",
    }
    assert payload["subject"] == {"kind": "universe", "id": "LQ45"}
    assert payload["verb"] == "accum"
    assert payload["window"] == {"days": 7}
    assert payload["data"]["candidates"] == []


def test_missing_screen_message():
    msg = missing_screen_message(
        what="watchlist",
        name="morning",
        source="screen_snapshots",
        fetch_hint="saham screen accum --save NAME",
    )
    assert "No cached watchlist 'morning'." in msg
    assert "Source: screen_snapshots" in msg
    assert "Run: saham screen accum --save NAME" in msg
