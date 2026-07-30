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
    assert 'data-frame="plan"' in html
    assert 'data-frame="paper"' in html
    assert 'data-frame="empty"' in html
    assert 'data-frame="palette"' in html
    # Judge is Enter-from-accum only — not a primary tab
    assert 'data-frame="judge"' not in html


def test_judge_not_digit_hotkey_only_enter_from_accum():
    html = _html()
    assert 'showFrame("judge")' in html
    # digit map must not route a number key to judge
    assert '"2": "judge"' not in html
    assert '"judge"' not in html.split("const map")[1].split("}")[0] if "const map" in html else True
    # primary tabs start at Accum without Judge button label
    assert ">2 Plan<" in html or 'data-frame="plan">2 Plan' in html or "2 Plan" in html


def test_broker_is_first_class_not_toast_only():
    html = _html()
    assert 'id="brokerView"' in html
    assert 'id="brokerTable"' in html
    assert "Code" in html and "DayNet" in html and "Net5" in html
    # Must wire showFrame broker, not only external toast
    assert 'showFrame("broker")' in html
    assert "see tui-broker-desk.html" not in html or 'showFrame("broker")' in html


def test_broker_enter_opens_full_desk_home_not_strip():
    """Radar → Enter → Net hero home (tui-broker-desk IA), not a footer strip only."""
    html = _html()
    assert 'id="brokerRadar"' in html
    assert 'id="brokerHome"' in html
    assert "openBrokerHome" in html
    assert "net-hero" in html
    assert "Day net" in html or "Day net" in html.lower() or "day net" in html.lower()
    assert 'id="brokerHub"' in html
    assert 'data-deep="top"' in html
    assert 'data-deep="flow"' in html
    assert 'data-deep="hist"' in html
    assert 'data-deep="ticker"' in html
    assert "Top buy" in html and "Top sell" in html
    # Reject half-measure: "desk home strip" / "CLI parity later" without hub
    assert "desk home strip" not in html.lower()
    assert "CLI parity later" not in html
    assert "brokerMode" in html


def test_opencode_tokens_present_night_ink_skin_absent():
    html = _html()
    assert "#0b0b0b" in html or "--bg: #0b0b0b" in html
    assert "#c9a68a" in html or "--sel-bg: #c9a68a" in html
    assert "desk-v2" not in html
    assert "Fraunces" not in html
    assert "font-display" not in html


def test_authority_board_enter_is_judge_not_ticker():
    html = _html()
    # Authority is wiring, not repeated chrome slogans
    assert 'showFrame("judge")' in html
    assert "present-only" in html.lower()
    # Enter on accum goes to judge, not ticker
    assert "showFrame(\"judge\")" in html
    # paper write is deliberate (confirm overlay / no silent write)
    assert (
        "no silent write" in html.lower()
        or "no auto-write" in html.lower()
        or "never auto-write" in html.lower()
        or 'id="confirmOverlay"' in html
    )


def test_md_states_opencode_bible_and_broker_in_cockpit():
    text = MD.read_text(encoding="utf-8")
    assert "bible" in text.lower() or "OpenCode" in text
    assert "Broker" in text or "broker" in text
    assert "linked out" not in text.lower() or "in-cockpit" in text.lower() or "7 |" in text


def test_prompt_rail_design_only_above_status():
    html = _html()
    assert 'id="promptRail"' in html
    assert 'id="promptInput"' in html
    assert "wirePromptRail" in html or "submitPromptRail" in html
    assert "design only" in html.lower()
    assert "not wired" in html.lower()
    # grid has prompt + status chrome
    assert "--prompt-h" in html or "prompt-rail" in html


def test_detail_flags_present_for_code_richer_fields():
    html = _html()
    # Judge flags
    for flag in ("stack", "readiness", "named", "mce", "limited"):
        assert f'data-flag="{flag}"' in html or f"data-flag-panel=\"{flag}\"" in html
    assert "judgeLimitedBanner" in html or "Limited judge" in html
    # Accum snapshot badge
    assert "accumSrcBadge" in html
    assert "snapshot" in html.lower()
    # Preopen inspect flags
    assert 'data-flag="auction+"' in html or "auction+" in html
    assert 'data-flag="why"' in html
    # Ticker depth flag
    assert "tickerDepthBody" in html or "tickerDepthToggle" in html
    assert "Secondary · presence" in html or "tickerPresence" in html
    # Broker flags
    assert "partial_net" in html
    assert "from_ticker" in html
    assert "deep.t" in html


def test_preopen_enter_opens_auction_inspect_not_judge():
    html = _html()
    assert 'id="preopenView"' in html
    assert 'id="preopenInspectView"' in html
    assert "openPreopenInspect" in html
    assert "preopenMode" in html
    # Enter path is inspect, not showFrame("judge")
    assert "openPreopenInspect()" in html
    # Still have accum Judge separately
    assert 'showFrame("judge")' in html


def test_plan_frame_is_geometry_triangle():
    html = _html()
    assert 'id="planView"' in html
    assert "geo-hero" in html or "geo-tri" in html
    assert 'id="planEntry"' in html and 'id="planStop"' in html and 'id="planTarget"' in html
    assert 'id="planInherit"' in html
    assert "paintPlanFromFocus" in html
    assert 'id="btnPlanPaper"' in html
    # triangle arrows / Entry Stop Target labels
    assert "Entry" in html and "Stop" in html and "Target" in html


def test_paper_frame_is_notebook_tape_not_log_card():
    html = _html()
    assert 'id="paperView"' in html
    assert 'id="paperTape"' in html
    assert "renderPaperTape" in html
    assert "Notebook tape" in html or "notebook tape" in html.lower()
    # confirm remains overlay for write path
    assert 'id="confirmOverlay"' in html
    assert "no silent write" in html.lower() or "No silent write" in html or "no silent write" in html
    # reject single log-card stage as the only paper UX
    assert "NOTEBOOK · PAPER ONLY" not in html


def test_ticker_frame_is_price_hero_hierarchy_not_flat_cli_only():
    html = _html()
    assert "Secondary presence" not in html
    assert 'id="tickerFullPanels"' in html
    assert 'data-mode="primary"' in html or 'data-mode="full"' in html
    assert 'data-hierarchy="price-hero"' in html
    assert "price-hero" in html
    assert "Price hero" in html or "Last · local close" in html
    assert "tickerDepthBody" in html or 'data-flag="depth"' in html
    # Journey hierarchy markers
    assert "Horizons" in html or "price_structure" in html
    assert "Pulse" in html or "foreign_flow" in html
    # Full field inventory still present (depth + primary)
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
        assert f'data-panel="{key}"' in html, f"missing field slot {key}"
    # Density bars allowed; product charts forbidden as copy claim
    assert "not a live chart" in html.lower() or "not charts" in html.lower() or "density ≠ chart" in html or "density bars" in html.lower()
