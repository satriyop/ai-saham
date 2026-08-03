# ADR-051: TUI OpenCode Cockpit Clean Break

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — Phases 0–5 implemented (2026-07-28)  
**Date:** 2026-07-28  
**Amended by:** [ADR-060](ADR-060-read-only-tui-context-agent.md), which permits
one bounded, optional, read-only context assistant without changing cockpit or
deterministic decision authority  
**Token enforcement (2026-08-03):** Phase 1 theme is consumed only via
`src/adapters/tui/theme.py` (`OPENCODE_TOKENS` · `OPENCODE_DERIVED` ·
`bake_css($oc_*)` for CSS · `OC.*` for Rich). CI visual-parity tests fail on
off-map hex. Detail: design bible § Visual → *Token implementation*. Not a new
product surface — adapter presentation only.  
**Depends on:** [ADR-011](ADR-011-offline-capable-cli-as-primary-interface.md),
[ADR-040](ADR-040-manual-dependency-injection-and-composition-roots.md),
[ADR-050](ADR-050-cli-verb-contracts.md)  
**Supersedes (product UX):** Historical multi-route TUI phases (Today / Screen tabs /
Ticker Workbench research workspace) documented under `tasks/done/tui_phase_*`  
**Design source of truth:**
[`docs/design/tui-cockpit-opencode.md`](../design/tui-cockpit-opencode.md),
[`docs/design/tui-cockpit-opencode.html`](../design/tui-cockpit-opencode.html)

## Context

The optional Textual TUI grew into a multi-route research workspace (Daily command
center, Screen workspace with Universe / Accumulation / Saved tabs, ticker
workbench). That chrome conflicts with the product decision that the TUI is a
**daily cockpit**, not an IDE:

- no scenario tabs — `Ctrl+P` command palette is navigation
- layout B — full main stage + thin context sidebar
- Enter = **view**, not plan
- Plan is deliberate (confirm modal)
- pre-open and accumulation are equal citizens
- online fetch is explicit; local-first default

Evolving the old screens in place would preserve clunky tab/button chrome and
cost more than a greenfield shell that reuses application use cases.

## Decision

1. **Clean-break retire** the multi-route research TUI adapter implementation.
2. Rebuild `saham tui` as an **OpenCode-style daily cockpit** matching the design
   mock (visual language + interaction map).
3. Keep contracts that still hold:
   - optional `.[tui]` extra; lazy CLI import; exact missing-Textual message
   - single composition root may import infrastructure
   - generation-safe worker state (`ScreenStateTracker`)
   - adapter thinness (no fetch/cache policy in widgets)
4. Reuse existing application use cases (`screen accum`, `screen pre-open`,
   `plan swing`, refresh/preview, etc.) via composition injection — do not
   reimplement analysis in the adapter.
5. Do **not** restore Today multi-panel, Screen tab bar, or workbench as home UX.
   Watchlist save/compare and Lab backtests stay CLI-first until explicitly added
   as palette items later.

## Consequences

### Positive

- One visual/interaction standard (OpenCode mock)
- Smaller adapter surface; easier keyboard-first iteration
- CLI remains the full power tool; TUI is the daily board

### Negative / follow-through

- Old TUI journey tests and modules are deleted, not migrated line-by-line
- Users of the previous Screen workspace tabs must use CLI until palette items
  reintroduce those jobs
- Delivery is phased (shell → palette → accum → pre-open → plan/fetch → harden)

## Non-goals

- Making Textual mandatory
- Broker execution
- General AI chat, agent tools, or AI authority inside the cockpit. ADR-060
  permits only its bounded read-only context-assistant contract.
- Domain/scoring semantic changes (`NON_SEMANTIC` adapter work)

## Implementation phases (summary)

| Phase | Outcome |
|-------|---------|
| 0 | Retire old tree; minimal layout-B shell launches |
| 1 | Theme + command palette + empty-cache chrome |
| 2 | Accumulation board + ticker view |
| 3 | Pre-open dense board |
| 4 | Plan confirm + explicit fetch |
| 5 | Hardening, docs, release notes |

## References

- Product design: `docs/design/tui-cockpit-opencode.md`
- Interactive mock: `docs/design/tui-cockpit-opencode.html`
- CLI verbs: ADR-050
