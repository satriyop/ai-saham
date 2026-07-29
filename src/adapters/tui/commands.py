"""Command palette registry for the daily cockpit (ADR-051).

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CockpitCommand:
    section: str
    command_id: str
    label: str
    shortcut: str
    description: str = ""


# Order is palette order. Suggested lists equal pre-open / accum citizens.
COCKPIT_COMMANDS: tuple[CockpitCommand, ...] = (
    CockpitCommand(
        "Suggested",
        "screen-accum",
        "Screen accumulation",
        "s a",
        "Daily accum candidates from local cache",
    ),
    CockpitCommand(
        "Suggested",
        "screen-preopen",
        "Screen pre-open",
        "s p",
        "IEP board from local IEV snapshot · Enter inspect",
    ),
    CockpitCommand(
        "Suggested",
        "plan-swing",
        "Plan swing structure",
        "p",
        "Structure desk for focus · SL/TP/lots · inherit Action · no order",
    ),
    CockpitCommand(
        "Daily",
        "view-ticker",
        "View ticker",
        "",
        "CLI parity: saham view ticker show · cache dashboard (not board inspect)",
    ),
    CockpitCommand(
        "Daily",
        "view-broker",
        "View broker",
        "",
        "list → Enter desk home · t/f/h deep · v stock · saham view broker",
    ),
    CockpitCommand(
        "Daily",
        "assess-preopen",
        "Assess pre-open",
        "a",
        "Grade auction evidence for focus (CLI parity later)",
    ),
    CockpitCommand(
        "Data",
        "fetch",
        "Fetch market data",
        "",
        "Online · explicit · never on open",
    ),
    CockpitCommand(
        "Data",
        "refresh-local",
        "Refresh local screen",
        "r",
        "Recompute current board from cache only",
    ),
    CockpitCommand(
        "Data",
        "empty-demo",
        "Show empty cache state",
        "",
        "Honest empty stage (design frame 4)",
    ),
    CockpitCommand(
        "Lab",
        "bt-accum",
        "Backtest screen accum",
        "",
        "CLI: saham backtest screen accum",
    ),
    CockpitCommand(
        "Lab",
        "bt-swing",
        "Backtest portfolio swing",
        "",
        "CLI: saham backtest portfolio swing",
    ),
    CockpitCommand(
        "Session",
        "toggle-sidebar",
        "Hide sidebar",
        "ctrl+b",
        "Toggle context rail",
    ),
    CockpitCommand(
        "Session",
        "help",
        "Help",
        "?",
        "Key map and product locks",
    ),
)


def filter_commands(query: str) -> list[CockpitCommand]:
    q = query.strip().lower()
    if not q:
        return list(COCKPIT_COMMANDS)
    return [
        c
        for c in COCKPIT_COMMANDS
        if q in c.command_id.lower()
        or q in c.label.lower()
        or q in c.section.lower()
        or q in c.description.lower()
        or q in c.shortcut.lower()
    ]
