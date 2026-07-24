"""Unit tests for shared stock deep-dive view contract helpers."""

from datetime import date

from src.application.dto.view_ticker_contract import (
    ViewResultStatus,
    ViewWindow,
    build_view_envelope,
    missing_ticker_message,
)


def test_build_view_envelope_has_strict_metadata_keys():
    payload = build_view_envelope(
        subject_id="bbca",
        verb="flow",
        status=ViewResultStatus.OK,
        as_of=date(2026, 7, 23),
        window=ViewWindow(days=10, from_date=date(2026, 7, 10), to_date=date(2026, 7, 23)),
        source="idx",
        scope="full",
        scope_note=None,
        fetch_hint="saham fetch market BBCA",
        data={"rows": 3},
    )
    assert payload["subject"] == {"kind": "ticker", "id": "BBCA"}
    assert payload["verb"] == "flow"
    assert payload["as_of"] == "2026-07-23"
    assert payload["window"]["days"] == 10
    assert payload["source"] == "idx"
    assert payload["scope"] == "full"
    assert payload["status"] == "ok"
    assert payload["fetch_hint"] == "saham fetch market BBCA"
    assert payload["data"] == {"rows": 3}


def test_missing_ticker_message_is_actionable():
    msg = missing_ticker_message(
        ticker="bbca",
        what="foreign flow history",
        source="foreign_flow_points",
        fetch_hint="saham fetch broker-history BBCA",
    )
    assert "No cached foreign flow history for BBCA." in msg
    assert "Source: foreign_flow_points" in msg
    assert "Run: saham fetch broker-history BBCA" in msg
