"""Structural contract: cockpit design mock is end-to-end OpenCode + full journey map.

Drives the shipped artifact docs/design/tui-cockpit-opencode.html (not a reimplementation).
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COCKPIT = ROOT / "docs" / "design" / "tui-cockpit-opencode.html"
MD = ROOT / "docs" / "design" / "tui-cockpit-opencode.md"


def _html() -> str:
    assert COCKPIT.is_file(), f"missing {COCKPIT}"
    return COCKPIT.read_text(encoding="utf-8")


def test_all_journey_stage_containers_exist():
    html = _html()
    required = {
        "accumView": "accum board",
        "judgeView": "judge present-only",
        "planView": "plan structure",
        "paperView": "paper notebook",
        "preopenView": "pre-open auction",
        "detailView": "view ticker",
        "brokerView": "view broker",
        "emptyView": "session health",
    }
    for dom_id, purpose in required.items():
        assert f'id="{dom_id}"' in html, f"missing stage {dom_id} ({purpose})"


def test_frame_switcher_includes_broker_and_ticker():
    html = _html()
    assert 'data-frame="broker"' in html
    assert 'data-frame="detail"' in html
    assert 'data-frame="judge"' in html
    assert 'data-frame="plan"' in html
    assert 'data-frame="paper"' in html
    assert 'data-frame="empty"' in html
    assert 'data-frame="palette"' in html


def test_broker_is_first_class_not_toast_only():
    html = _html()
    assert 'id="brokerView"' in html
    assert 'id="brokerTable"' in html
    assert "Code" in html and "DayNet" in html and "Net5" in html
    # Must wire showFrame broker, not only external toast
    assert 'showFrame("broker")' in html
    assert "see tui-broker-desk.html" not in html or 'showFrame("broker")' in html


def test_opencode_tokens_present_night_ink_skin_absent():
    html = _html()
    assert "#0b0b0b" in html or "--bg: #0b0b0b" in html
    assert "#c9a68a" in html or "--sel-bg: #c9a68a" in html
    assert "desk-v2" not in html
    assert "Fraunces" not in html
    assert "font-display" not in html


def test_authority_board_enter_is_judge_not_ticker():
    html = _html()
    # accum Enter opens judge
    assert 'showFrame("judge")' in html
    # copy
    assert "not Action" in html
    assert "present-only" in html or "present-only" in html.lower()
    # paper not auto
    assert "no auto-write" in html.lower() or "never auto-write" in html.lower() or "No auto-write" in html


def test_md_states_opencode_bible_and_broker_in_cockpit():
    text = MD.read_text(encoding="utf-8")
    assert "bible" in text.lower() or "OpenCode" in text
    assert "Broker" in text or "broker" in text
    assert "linked out" not in text.lower() or "in-cockpit" in text.lower() or "7 |" in text


def test_ticker_frame_is_full_cli_panels_not_presence_only():
    html = _html()
    assert "Secondary presence" not in html
    assert 'id="tickerFullPanels"' in html
    assert 'data-mode="full"' in html
    # FULL_PANEL_ORDER keys must appear as data-panel slots
    for key in (
        "identity",
        "freshness",
        "valuation",
        "price_structure",
        "analyst",
        "earnings",
        "ownership",
        "bandar",
        "foreign_flow",
        "sector_macro",
        "corp_actions",
        "insider",
        "seasonality",
        "iev",
        "sentiment",
        "profile",
        "candles",
    ):
        assert f'data-panel="{key}"' in html, f"missing full panel slot {key}"
    assert "FULL_PANEL_ORDER" in html or "full panels" in html.lower()
