"""Regression: pre-open track/status must default omitted session to today WIB.

Cron runs ``saham research pre-open track --broker-confirm`` with no --date.
Filtering observations by parse_session_date(None) == None matches nothing and
prints ``No saved pre-open observations for None`` (2026-07-28 outage).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
import typer

from src.adapters.cli.research_pre_open_paths import (
    parse_session_date,
    resolve_session_date,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE

IDX = ZoneInfo("Asia/Jakarta")


def test_parse_session_date_none_stays_optional() -> None:
    assert parse_session_date(None) is None
    assert parse_session_date("") is None


def test_parse_session_date_iso() -> None:
    assert parse_session_date("2026-07-28") == date(2026, 7, 28)


def test_parse_session_date_rejects_garbage() -> None:
    with pytest.raises(typer.Exit):
        parse_session_date("28-07-2026")


def test_resolve_session_date_defaults_to_today_wib() -> None:
    today = datetime.now(IDX_TIMEZONE).date()
    assert resolve_session_date(None) == today
    assert resolve_session_date("") == today


def test_resolve_session_date_explicit_iso() -> None:
    assert resolve_session_date("2026-07-28") == date(2026, 7, 28)


def test_track_filter_with_none_matches_nothing_with_default_finds_today() -> None:
    """Mirror the observation filter used by research pre-open track."""
    session = date(2026, 7, 28)
    cutoff = datetime(2026, 7, 28, 8, 57, 5, tzinfo=IDX)
    other_day = datetime(2026, 7, 27, 8, 57, 5, tzinfo=IDX)
    naive_utc = datetime(2026, 7, 28, 1, 57, 5, tzinfo=timezone.utc)  # still 08:57 WIB

    rows = [
        SimpleNamespace(
            cutoff_at=cutoff,
            decision_payload={"ticker": "BUMI"},
            observation_id="obs-bumi",
        ),
        SimpleNamespace(
            cutoff_at=other_day,
            decision_payload={"ticker": "OLD"},
            observation_id="obs-old",
        ),
        SimpleNamespace(
            cutoff_at=naive_utc,
            decision_payload={"ticker": "PADI"},
            observation_id="obs-padi",
        ),
    ]

    def filter_for(run_date: date | None) -> list[str]:
        return sorted(
            str(row.decision_payload["ticker"]).upper()
            for row in rows
            if row.cutoff_at.astimezone(IDX_TIMEZONE).date() == run_date
            and isinstance(row.decision_payload.get("ticker"), str)
        )

    # Broken cron path (pre-fix): parse_session_date(None) → None
    assert filter_for(parse_session_date(None)) == []

    # Fixed path: resolve_session_date, with explicit session under test
    assert filter_for(session) == ["BUMI", "PADI"]
    assert filter_for(resolve_session_date("2026-07-28")) == ["BUMI", "PADI"]
