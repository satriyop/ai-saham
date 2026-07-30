"""OpenCode-faithful Textual CSS for the daily cockpit.

Tokens match docs/design/tui-cockpit-opencode.md (near-black, peach selection,
purple section labels, hairline borders).

Layer: Adapter
"""

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
}

#main-header {
    height: auto;
    min-height: 3;
    padding: 1 1 0 1;
    border-bottom: solid #181818;
}

#view-title {
    text-style: bold;
    color: #e8e8e8;
}

#view-meta {
    color: #5c6575;
    height: auto;
}

#mode-pill {
    color: #d4b06a;
    text-align: right;
}

#stage {
    height: 1fr;
    padding: 1 1;
}

/* Scrollable text stages (inspect, view ticker, plan, empty, loading). */
#stage-scroll {
    height: 1fr;
    scrollbar-color: #3a3a3a #121212;
    scrollbar-size-vertical: 1;
}

#stage-body {
    height: auto;
    width: 100%;
    color: #7a7a7a;
}

#board-table {
    height: 1fr;
    background: #080b12;
    color: #c9c3b8;
}

/* Signal radar focus: brass wash (design tui-accum-board.html is-on) */
#board-table > .datatable--cursor {
    background: #1a160e;
    color: #f0ebe3;
    text-style: bold;
}

#board-table > .datatable--hover {
    background: #0d121c;
}

#board-table > .datatable--header {
    color: #5c6575;
    text-style: bold;
    background: #080b12;
}

#board-footer {
    height: auto;
    color: #5c6575;
    padding-top: 1;
}

#evidence-strip {
    height: auto;
    max-height: 14;
    border-top: solid #181818;
    padding-top: 1;
    color: #7a7a7a;
}

#sidebar {
    width: 28;
    height: 100%;
    background: #0e0e0e;
    padding: 1 1;
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
    background: #1a1a1a;
    border: solid #2a2a2a;
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
    background: #121212;
    border: solid #252525;
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
    border-top: solid #252525;
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
