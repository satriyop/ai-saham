import pytest

from src.application.services.agent_data_honesty import (
    AgentNoteSeverity,
    format_agent_more_notes,
    format_agent_status_strip,
    normalize_agent_data_notes,
)

pytestmark = pytest.mark.agent


def test_normalize_ranks_warn_before_info_and_caps_primary() -> None:
    raw = (
        "SESSION_ALIGNED_LATE_WITHIN_LAG",
        "Risk snapshot 2026-07-31 differs from decision as-of 2026-08-03; "
        "risk is shown as diagnostic only",
        "Incomplete signal authority coverage — flow_confirmation: present but "
        "not source-authoritative",
        "bandar_detector",
        "observed_through is 1 trading session(s) behind the latest completed "
        "session (2026-07-31), within the expected 1-session settlement lag.",
        "Provider cutoff (2026-07-31T20:00:00+07:00) has passed",
    )
    view = normalize_agent_data_notes(raw, max_primary=3)
    assert view.raw_count == 6
    codes = [n.code for n in view.primary]
    # WARN notes rank before INFO
    assert set(codes[:2]) == {"RISK_SNAPSHOT_LAG", "AUTHORITY_INCOMPLETE"}
    all_codes = [n.code for n in view.primary + view.more]
    assert all_codes.count("SETTLEMENT_LATE_WITHIN_LAG") == 1
    assert len(view.primary) == 3
    assert view.more


def test_risk_and_settlement_have_operator_do_lines() -> None:
    view = normalize_agent_data_notes(
        (
            "Risk snapshot 2026-07-31 differs from decision as-of 2026-08-03",
            "SESSION_ALIGNED_LATE_WITHIN_LAG",
        )
    )
    by_code = {n.code: n for n in view.primary + view.more}
    assert "secondary" in by_code["RISK_SNAPSHOT_LAG"].do_line.lower() or "refresh" in by_code[
        "RISK_SNAPSHOT_LAG"
    ].do_line.lower()
    assert by_code["SETTLEMENT_LATE_WITHIN_LAG"].severity is AgentNoteSeverity.INFO
    assert "wait" in by_code["SETTLEMENT_LATE_WITHIN_LAG"].do_line.lower()


def test_status_strip_and_more_format() -> None:
    notes = normalize_agent_data_notes(
        (
            "Risk snapshot 2026-07-31 differs from decision as-of 2026-08-03",
            "SESSION_ALIGNED_LATE_WITHIN_LAG",
            "bandar_detector",
            "OTHER_TOKEN",
        ),
        max_primary=2,
    )
    strip = format_agent_status_strip(
        turn_ok=True,
        ticker="UNVR",
        as_of="2026-08-03",
        notes=notes,
    )
    assert "Turn  OK · UNVR · as-of 2026-08-03" in strip
    assert "Data  " in strip
    assert "RISK_SNAPSHOT_LAG:" in strip or "Risk lag" in strip
    more = format_agent_more_notes(notes)
    assert more.startswith("More data notes")
