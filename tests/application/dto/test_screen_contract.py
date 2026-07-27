"""Unit tests for screen discovery envelope contract."""

from datetime import date

from src.application.dto.screen_contract import (
    ScreenResultStatus,
    ScreenSubjectKind,
    build_screen_envelope,
    missing_screen_message,
    related_actions_for_accum,
    resolve_accum_result_status,
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


def test_resolve_accum_result_status_empty_when_no_results():
    assert resolve_accum_result_status(result_count=0) is ScreenResultStatus.EMPTY


def test_resolve_accum_result_status_ok_when_results_present():
    assert resolve_accum_result_status(result_count=1) is ScreenResultStatus.OK
    assert resolve_accum_result_status(result_count=20) is ScreenResultStatus.OK


def test_related_actions_for_accum_includes_view_analyze_and_compare():
    actions = related_actions_for_accum(
        tickers=["bbca", "BBRI", "bbca"],
        saved_watchlist_name="morning-watch",
    )
    assert actions[0] == {
        "verb": "view",
        "label": "Open BBCA",
        "command": "saham view BBCA",
    }
    assert actions[1] == {
        "verb": "analyze",
        "label": "Analyze BBCA",
        "command": "saham plan swing BBCA",
    }
    assert actions[2]["command"] == "saham view BBRI"
    assert actions[-1] == {
        "verb": "compare",
        "label": "Compare watchlist morning-watch",
        "command": "saham screen compare morning-watch",
    }


def test_related_actions_for_accum_caps_tickers():
    tickers = [f"T{i:02d}" for i in range(10)]
    actions = related_actions_for_accum(tickers=tickers, max_tickers=2)
    # 2 tickers * (view + analyze) = 4
    assert len(actions) == 4
    assert actions[0]["command"] == "saham view T00"
    assert actions[2]["command"] == "saham view T01"
