"""Unit tests for shared effective-session CLI display helpers."""

from datetime import date, datetime

import pytest
import typer

from src.adapters.cli.effective_session_display import (
    effective_session_to_json,
    format_effective_session_label,
    format_effective_session_line,
    parse_as_of_option,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE, MARKET_CLOSE


def _session(*, is_eod_pending: bool, analysis_as_of: date) -> EffectiveMarketSession:
    run_at = datetime.combine(analysis_as_of, MARKET_CLOSE, tzinfo=IDX_TIMEZONE)
    return EffectiveMarketSession(
        run_at=run_at,
        decision_at=run_at,
        latest_completed_session=analysis_as_of,
        analysis_as_of=analysis_as_of,
        market_session_name="AFTER_CLOSE" if not is_eod_pending else "REGULAR",
        is_eod_pending=is_eod_pending,
        resolution_source="test",
    )


def test_format_effective_session_label_settled():
    session = _session(is_eod_pending=False, analysis_as_of=date(2026, 7, 23))
    assert format_effective_session_label(session) == "2026-07-23 (settled)"


def test_format_effective_session_label_live_eod_pending():
    session = _session(is_eod_pending=True, analysis_as_of=date(2026, 7, 24))
    assert format_effective_session_label(session) == "2026-07-24 (live · EOD pending)"


def test_format_effective_session_line_prefixes_label():
    session = _session(is_eod_pending=False, analysis_as_of=date(2026, 7, 23))
    assert format_effective_session_line(session) == (
        "Effective session: 2026-07-23 (settled)"
    )


def test_effective_session_to_json_round_trips_fields():
    session = _session(is_eod_pending=True, analysis_as_of=date(2026, 7, 24))
    payload = effective_session_to_json(session)
    assert payload is not None
    assert payload["analysis_as_of"] == "2026-07-24"
    assert payload["is_eod_pending"] is True


def test_effective_session_to_json_none():
    assert effective_session_to_json(None) is None


def test_parse_as_of_option_none():
    assert parse_as_of_option(None) is None


def test_parse_as_of_option_valid():
    assert parse_as_of_option("2026-07-23") == date(2026, 7, 23)


def test_parse_as_of_option_invalid_fails_closed(capsys):
    with pytest.raises(typer.Exit) as exc:
        parse_as_of_option("not-a-date")
    assert exc.value.exit_code == 1
    captured = capsys.readouterr()
    assert "Invalid --as-of" in captured.err
