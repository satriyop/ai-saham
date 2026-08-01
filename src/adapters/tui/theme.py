"""OpenCode visual bible tokens for the daily cockpit.

Authority: docs/design/tui-cockpit-opencode.md + mock `.app` tokens.
Near-black surfaces, peach selection, hairline borders.
No journey night-ink skin, no design-tools strip.

Layer: Adapter
"""

# Canonical OpenCode token map (mock :root)
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

COCKPIT_CSS = """
Screen {
    background: #0b0b0b;
    color: #d8d8d8;
}

#workspace {
    width: 100%;
    height: 1fr;
}

#main {
    width: 1fr;
    height: 100%;
    border-right: solid #1c1c1c;
    padding: 0 1;
    background: #0b0b0b;
}

/* Layout B: header · stage · footer · prompt · (status outside main) */
#main-header {
    height: 3;
    padding: 1 1 0 1;
    border-bottom: solid #181818;
    background: #0b0b0b;
}

#view-title {
    text-style: bold;
    color: #e8e8e8;
    height: 1;
}

#view-meta {
    color: #555555;
    height: 1;
}

#mode-pill {
    color: #c9a68a;
    text-align: right;
    height: 1;
}

#stage {
    height: 1fr;
    padding: 1 1;
    background: #0b0b0b;
}

#stage-scroll {
    height: 1fr;
    scrollbar-color: #3a3a3a #121212;
    scrollbar-size-vertical: 1;
    background: #0b0b0b;
}

#stage-body {
    height: auto;
    width: 100%;
    color: #7a7a7a;
    background: #0b0b0b;
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
    color: #6b6b6b;
    background: #141414;
    border: none;
    border-left: solid #555555;
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
    color: #6b6b6b;
    background: #0b0b0b;
}
#board-flag-lab {
    width: auto;
    color: #6b6b6b;
    text-style: bold;
    padding-right: 1;
}

#board-source-badge.snap {
    color: #d4b06a;
    background: #1a1810;
    border: none;
    border-left: solid #d4b06a;
}

#board-source-badge.live {
    color: #6fbf8a;
    background: #121a14;
    border: none;
    border-left: solid #6fbf8a;
}

#board-table {
    height: 1fr;
    background: #0b0b0b;
    color: #d8d8d8;
}

#board-table > .datatable--cursor {
    background: #c9a68a;
    color: #1a120c;
    text-style: bold;
}

#board-table > .datatable--hover {
    background: #161616;
}

#board-table > .datatable--header {
    color: #555555;
    text-style: bold;
    background: #101010;
}

#board-footer {
    height: auto;
    color: #555555;
    padding-top: 1;
    background: #0b0b0b;
}

/* Prompt rail · OpenCode chrome (non-Action) */
#prompt-rail {
    height: 3;
    border-top: solid #181818;
    padding: 0 1;
    background: #0e0e0e;
    align: left middle;
}

#prompt-rail.is-focus {
    border-top: solid #c9a68a;
}

#prompt-affordance {
    width: 2;
    color: #c9a68a;
    text-style: bold;
}

#prompt-input {
    width: 1fr;
    background: #0e0e0e;
    /* Kill Textual Input tall border (empty green box on stage) */
    border: none !important;
    color: #d8d8d8;
    padding: 0 1;
    height: 1;
}

#prompt-input:focus {
    background: #141414;
    border: none !important;
}

#prompt-mode {
    width: auto;
    min-width: 8;
    color: #9b8fb8;
    text-align: right;
    padding: 0 1;
}

#prompt-mode.is-agent {
    color: #c9a68a;
}

#prompt-mode.is-cli {
    color: #6fbf8a;
}

#evidence-strip {
    height: auto;
    max-height: 14;
    border-top: solid #181818;
    padding-top: 1;
    color: #7a7a7a;
    background: #0b0b0b;
}

#sidebar {
    width: 28;
    height: 100%;
    background: #0e0e0e;
    padding: 1 1;
    border-left: solid #181818;
}

#sidebar.hidden {
    display: none;
    width: 0;
    padding: 0;
}

.side-title {
    text-style: bold;
    color: #d8d8d8;
    margin-top: 1;
}

.side-title.first {
    margin-top: 0;
}

.side-line {
    color: #555555;
}

.section-label {
    color: #9b8fb8;
    text-style: bold;
}

#status {
    height: 1;
    background: #090909;
    color: #555555;
    padding: 0 1;
    border-top: solid #1c1c1c;
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
    background: #141414;
    border: solid #1c1c1c;
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
    color: #7a7a7a;
    text-style: bold;
}

#palette-esc, #confirm-esc, #help-esc {
    width: auto;
    color: #555555;
    text-align: right;
}

#palette-input {
    margin-bottom: 1;
    background: #101010;
    border: solid #1c1c1c;
    color: #d8d8d8;
}

#palette-list, #help-body, #confirm-body {
    height: auto;
    max-height: 22;
    margin-bottom: 1;
    color: #d8d8d8;
}

#palette-foot, #confirm-foot, #help-foot {
    height: auto;
    border-top: solid #1c1c1c;
    padding-top: 1;
    color: #555555;
}

.warn-line {
    color: #d4b06a;
    background: #1a1810;
    padding: 0 1;
}

.pass { color: #6fbf8a; }
.watch { color: #d4b06a; }
.block { color: #c97a72; }
.dim { color: #555555; }
"""
