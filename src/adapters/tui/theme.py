"""OpenCode visual bible tokens for the daily cockpit.

Authority: docs/design/tui-cockpit-opencode.md + mock `.app` tokens.
Near-black surfaces, peach selection, hairline borders.
No journey night-ink skin, no design-tools strip.

Single source of truth for TUI colors:
- Tier 1: ``OPENCODE_TOKENS`` (canonical 22)
- Tier 2: ``OPENCODE_DERIVED`` (named chrome/washes/scalar track)
- CSS: bake ``$oc_*`` via :func:`bake_css` (import-time substitute; avoids
  f-string brace collision with Textual rule blocks)
- Rich markup: :data:`OC` Python constants from the same maps

Layer: Adapter
"""

from __future__ import annotations

import re
from pathlib import Path
from string import Template
from types import SimpleNamespace

# Canonical OpenCode token map (mock :root) — Tier 1
OPENCODE_TOKENS: dict[str, str] = {
    "bg": "#0b0b0b",
    "bg_elevated": "#141414",
    "bg_panel": "#101010",
    "bg_sidebar": "#0e0e0e",
    "bg_row_hover": "#161616",
    "border": "#1c1c1c",
    "border_soft": "#181818",
    "text": "#d8d8d8",
    "text_bright": "#e8e8e8",
    "text_dim": "#7a7a7a",
    "text_mute": "#555555",
    "text_faint": "#3d3d3d",
    "sel_bg": "#c9a68a",
    "sel_text": "#1a120c",
    "sel_dim": "#a8896f",
    "green": "#6fbf8a",
    "amber": "#d4b06a",
    "red": "#c97a72",
    "blue": "#7aa2c4",
    "purple": "#9b8fb8",
}

# Tier 2 — named derived shades (role comments; not casual hex)
OPENCODE_DERIVED: dict[str, str] = {
    # chrome
    "scrollbar": "#3a3a3a",  # scrollbar thumb
    "track_inactive": "#121212",  # scrollbar track / inactive rail
    "hairline_strong": "#2a2a2a",  # stronger hairline than border
    "status_bg": "#090909",  # status strip under stage
    "dim": "#6b6b6b",  # secondary dim (between text_dim and text_mute)
    # semantic washes (bg behind status lines)
    "warn_bg": "#1a1810",
    "ok_bg": "#121a14",
    "fail_bg": "#1a1212",
    # scalar bar contract (bible-locked track)
    "scalar_track": "#1a1a1a",
}

# Forbidden journey / night-ink product chrome markers (tests assert absence)
FORBIDDEN_PRODUCT_MARKERS: tuple[str, ...] = (
    "Fraunces",
    "desk-v2",
    "font-display",
    "design-tools",
    "#080b12",
    "#0d121c",
    "#121a28",
    "#1c2430",
)

_HEX_RE = re.compile(r"#[0-9a-fA-F]{6}")


def _oc_template_map() -> dict[str, str]:
    """``$oc_<name>`` → hex for :func:`bake_css` / string.Template."""
    out: dict[str, str] = {}
    for key, value in OPENCODE_TOKENS.items():
        out[f"oc_{key}"] = value
    for key, value in OPENCODE_DERIVED.items():
        out[f"oc_{key}"] = value
    # friendly aliases used in widgets
    out["oc_mint"] = OPENCODE_TOKENS["green"]
    out["oc_coral"] = OPENCODE_TOKENS["red"]
    out["oc_brass"] = OPENCODE_TOKENS["amber"]
    out["oc_peach"] = OPENCODE_TOKENS["sel_bg"]
    return out


def bake_css(template: str) -> str:
    """Substitute ``$oc_*`` placeholders into Textual CSS at class-definition time.

    Prefer this over f-strings (Textual CSS rule blocks use ``{ }``) and over
    runtime Theme ``$vars`` when registration order is unreliable.
    """
    return Template(template).safe_substitute(_oc_template_map())


def _build_oc_namespace() -> SimpleNamespace:
    """Python constants for Rich ``[#hex]`` markup — same values as the maps."""
    ns: dict[str, str] = {}
    ns.update(OPENCODE_TOKENS)
    ns.update(OPENCODE_DERIVED)
    ns["mint"] = OPENCODE_TOKENS["green"]
    ns["coral"] = OPENCODE_TOKENS["red"]
    ns["brass"] = OPENCODE_TOKENS["amber"]
    ns["peach"] = OPENCODE_TOKENS["sel_bg"]
    return SimpleNamespace(**ns)


OC = _build_oc_namespace()


def palette_allowlist() -> frozenset[str]:
    """Hex values legal in product TUI CSS/markup (case-normalized lowercase)."""
    values = set(OPENCODE_TOKENS.values()) | set(OPENCODE_DERIVED.values())
    return frozenset(v.lower() for v in values)


def palette_exception_hexes() -> frozenset[str]:
    """Hexes allowed only as ban-list documentation (FORBIDDEN markers)."""
    return frozenset(m.lower() for m in FORBIDDEN_PRODUCT_MARKERS if m.startswith("#"))


def collect_hexes_in_text(text: str) -> list[str]:
    """All ``#rrggbb`` occurrences in *text* (original case preserved)."""
    return _HEX_RE.findall(text)


def off_palette_hexes_in_tree(
    root: Path | None = None,
) -> list[tuple[str, str, int]]:
    """Scan ``src/adapters/tui/**/*.py`` for hexes outside the allowlist.

    Returns list of ``(path, hex, line_no)`` for each off-allowlist hit.
    Exception: ``FORBIDDEN_PRODUCT_MARKERS`` hexes are allowed only inside
    ``theme.py`` (the ban list itself).
    """
    base = root or Path("src/adapters/tui")
    allow = palette_allowlist()
    exceptions = palette_exception_hexes()
    hits: list[tuple[str, str, int]] = []
    for path in sorted(base.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        rel = str(path)
        is_theme = path.name == "theme.py"
        for lineno, line in enumerate(text.splitlines(), start=1):
            for raw in collect_hexes_in_text(line):
                low = raw.lower()
                if low in allow:
                    continue
                if is_theme and low in exceptions:
                    continue
                hits.append((rel, raw, lineno))
    return hits


COCKPIT_CSS = bake_css("""
Screen {
    background: $oc_bg;
    color: $oc_text;
}

#workspace {
    width: 100%;
    height: 1fr;
}

#main {
    width: 1fr;
    height: 100%;
    border-right: solid $oc_border;
    padding: 0 1;
    background: $oc_bg;
}

/* Layout B: header · stage · footer · prompt · (status outside main) */
#main-header {
    height: 3;
    padding: 1 1 0 1;
    border-bottom: solid $oc_border_soft;
    background: $oc_bg;
}

#view-title {
    text-style: bold;
    color: $oc_text_bright;
    height: 1;
}

#view-meta {
    color: $oc_text_mute;
    height: 1;
}

#mode-pill {
    color: $oc_peach;
    text-align: right;
    height: 1;
}

#stage {
    height: 1fr;
    padding: 1 1;
    background: $oc_bg;
}

#stage-scroll {
    height: 1fr;
    scrollbar-color: $oc_scrollbar $oc_track_inactive;
    scrollbar-size-vertical: 1;
    background: $oc_bg;
}

#stage-body {
    height: auto;
    width: 100%;
    color: $oc_text_dim;
    background: $oc_bg;
}

/* Boards: OpenCode radar, peach selection wash */
/*
 * src-badge: NEVER full solid border + height:1 — Textual gutter eats content
 * height (border top+bottom) → content height 0 → empty green hollow box.
 * Use left accent only; height auto so the label always paints.
 */
#board-source-badge {
    height: auto;
    width: auto;
    max-width: 100%;
    margin: 0 0 1 0;
    padding: 0 1;
    color: $oc_dim;
    background: $oc_bg_elevated;
    border: none;
    border-left: solid $oc_text_mute;
}

#board-source-badge.hide {
    display: none !important;
    height: 0;
    width: 0;
    min-width: 0;
    max-width: 0;
    margin: 0;
    padding: 0;
    border: none !important;
}

#board-flag-row {
    height: auto;
    width: 100%;
    margin: 0 0 1 0;
    padding: 0 1;
    color: $oc_dim;
    background: $oc_bg;
}
#board-flag-lab {
    width: auto;
    color: $oc_dim;
    text-style: bold;
    padding-right: 1;
}

#board-source-badge.snap {
    color: $oc_brass;
    background: $oc_warn_bg;
    border: none;
    border-left: solid $oc_brass;
}

#board-source-badge.live {
    color: $oc_mint;
    background: $oc_ok_bg;
    border: none;
    border-left: solid $oc_mint;
}

#board-table {
    height: 1fr;
    background: $oc_bg;
    color: $oc_text;
}

#board-table > .datatable--cursor {
    background: $oc_peach;
    color: $oc_sel_text;
    text-style: bold;
}

#board-table > .datatable--hover {
    background: $oc_bg_row_hover;
}

#board-table > .datatable--header {
    color: $oc_text_mute;
    text-style: bold;
    background: $oc_bg_panel;
}

#board-footer {
    height: auto;
    color: $oc_text_mute;
    padding-top: 1;
    background: $oc_bg;
}

/* Prompt rail · OpenCode 2-row composer (prominent · non-Action)
 *
 * Design lock: docs/design/tui-cockpit-opencode.md § Prompt rail
 * Reject: 1-line hairline · tight flush text · no left accent.
 * Adopt: elevated card · left brass bar · roomy pad above/below · row1+row2.
 */
#prompt-rail {
    /* 6 cells: pad · input · air · meta · pad · border air (OpenCode roomy) */
    height: 6;
    width: 100%;
    margin: 0 0 0 0;
    padding: 1 1;
    background: $oc_track_inactive;
    border-top: solid $oc_hairline_strong;
    border-bottom: solid $oc_hairline_strong;
    border-left: solid $oc_peach;
    border-right: solid $oc_hairline_strong;
}

#prompt-rail.is-focus {
    background: $oc_warn_bg;
    border-top: solid $oc_warn_bg;
    border-bottom: solid $oc_warn_bg;
    border-left: solid $oc_peach;
    border-right: solid $oc_warn_bg;
}

#prompt-row-input {
    height: 1;
    width: 100%;
    align: left middle;
    padding: 0;
    margin-top: 0;
}

/* Spacer between typed line and mode meta (OpenCode air) */
#prompt-row-gap {
    height: 1;
    width: 100%;
    background: transparent;
}

#prompt-row-meta {
    height: 1;
    width: 100%;
    align: left middle;
    padding: 0 0 0 2;
    color: $oc_text_mute;
}

#prompt-affordance {
    width: 2;
    color: $oc_peach;
    text-style: bold;
}

#prompt-input {
    width: 1fr;
    background: $oc_track_inactive;
    /* Kill Textual Input tall border (empty green box on stage) */
    border: none !important;
    color: $oc_text_bright;
    padding: 0 1;
    height: 1;
}

#prompt-input:focus {
    background: $oc_warn_bg;
    border: none !important;
}

#prompt-rail.is-focus #prompt-input {
    background: $oc_warn_bg;
}

#prompt-mode {
    width: auto;
    min-width: 6;
    color: $oc_sel_dim;
    text-style: bold;
    text-align: left;
    padding: 0 0 0 0;
}

#prompt-mode.is-agent {
    color: $oc_peach;
}

#prompt-mode.is-cli {
    color: $oc_mint;
}

#prompt-sub {
    width: 1fr;
    color: $oc_text_dim;
    padding: 0 0 0 1;
}

#evidence-strip {
    height: auto;
    max-height: 14;
    border-top: solid $oc_border_soft;
    padding-top: 1;
    color: $oc_text_dim;
    background: $oc_bg;
}

#sidebar {
    width: 28;
    height: 100%;
    background: $oc_bg_sidebar;
    padding: 1 1;
    border-left: solid $oc_border_soft;
}

#sidebar.hidden {
    display: none;
    width: 0;
    padding: 0;
}

.side-title {
    text-style: bold;
    color: $oc_text;
    margin-top: 1;
}

.side-title.first {
    margin-top: 0;
}

.side-line {
    color: $oc_text_mute;
}

.section-label {
    color: $oc_purple;
    text-style: bold;
}

#status {
    height: 1;
    background: $oc_status_bg;
    color: $oc_text_mute;
    padding: 0 1;
    border-top: solid $oc_border;
}

/* Overlays share OpenCode dialog language */
CommandPalette, PlanConfirmModal, HelpModal, FetchConfirmModal, PaperLogConfirmModal {
    align: center middle;
    background: rgba(0, 0, 0, 0.45);
}

.dialog-card {
    width: 64;
    max-width: 92%;
    height: auto;
    max-height: 85%;
    background: $oc_bg_elevated;
    border: solid $oc_border;
    padding: 1 1;
}

.dialog-card.narrow {
    width: 52;
}

#palette-head, #confirm-head, #help-head {
    height: 1;
    margin-bottom: 1;
}

#palette-title, #confirm-title, #help-title {
    width: 1fr;
    color: $oc_text_dim;
    text-style: bold;
}

#palette-esc, #confirm-esc, #help-esc {
    width: auto;
    color: $oc_text_mute;
    text-align: right;
}

#palette-input {
    margin-bottom: 1;
    background: $oc_bg_panel;
    border: solid $oc_border;
    color: $oc_text;
}

#palette-list, #help-body, #confirm-body {
    height: auto;
    max-height: 22;
    margin-bottom: 1;
    color: $oc_text;
}

#palette-foot, #confirm-foot, #help-foot {
    height: auto;
    border-top: solid $oc_border;
    padding-top: 1;
    color: $oc_text_mute;
}

.warn-line {
    color: $oc_brass;
    background: $oc_warn_bg;
    padding: 0 1;
}

.pass { color: $oc_mint; }
.watch { color: $oc_brass; }
.block { color: $oc_coral; }
.dim { color: $oc_text_mute; }
""")
