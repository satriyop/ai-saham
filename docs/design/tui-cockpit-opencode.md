# Daily Cockpit TUI — OpenCode chrome + journey desks

**Status:** design mock · ADR-051 shell + night-ink desk frames  
**Mock:** [`tui-cockpit-opencode.html`](./tui-cockpit-opencode.html)  
**Journey hub (canonical order):** [`tui-journey-hub.html`](./tui-journey-hub.html)

## Role of this mock

| Layer | Owns |
|-------|------|
| **This file** | Layout B shell · palette · sidebar · status · how stages mount |
| **Journey desk mocks** | Visual language of each instrument (Harga / Verdict / Geometry / …) |

OpenCode chrome (near-black, peach palette selection) stays the **shell**.  
Night-ink desk mocks stay the **stage instruments**. Do not collapse them into one dull table dump.

## Journey frames (hotkeys 1–8)

| # | Frame | Path | Full mock |
|---|--------|------|-----------|
| 1 | Accum | Action discover · Signal radar · cols 1:1 TUI | [`tui-accum-board.html`](./tui-accum-board.html) |
| 2 | Judge | Action present-only · Verdict mast · `Enter` from board | [`tui-judge-desk.html`](./tui-judge-desk.html) |
| 3 | Plan | Structure · Geometry mast · inherits Action · no order | [`tui-plan-desk.html`](./tui-plan-desk.html) |
| 4 | Paper | Notebook tape · confirm from geometry · not learning | [`tui-paper-journal.html`](./tui-paper-journal.html) |
| 5 | Pre-open | Auction · ≠ accum Judge | [`tui-preopen-board.html`](./tui-preopen-board.html) |
| 6 | Ticker | Browse · Harga mast · TickerDashboard contract | [`tui-ticker-desk.html`](./tui-ticker-desk.html) |
| 7 | Health | Empty / zero / lag / ready posters | [`tui-session-health.html`](./tui-session-health.html) |
| 8 | Palette | Ctrl+P nav (no scenario tabs) | this mock |

**Broker** is linked out: [`tui-broker-desk.html`](./tui-broker-desk.html) (list radar / net mast).

## Authority (do not blur)

| Path | Enter / keys | Must not |
|------|----------------|----------|
| **Action** | Board `Enter` → Judge · `p` Plan · `l` Paper | Ticker must not set Action |
| **Browse** | `v t` ticker · `v b` broker | Invent ENTER/WATCH/AVOID |
| **Paper** | Confirm only after plan geometry | Auto-write · learning corpus · orders |
| **Pre-open** | Inspect ≠ accum Judge | Same Enter semantics as accum Judge |

## Product locks

| Decision | Choice |
|----------|--------|
| Role | Daily **cockpit**, not IDE |
| Layout | **B** — full main + thin right sidebar |
| Navigation | **No scenario tabs** — `Ctrl+P` palette |
| Online | Explicit fetch only · local-first default |
| Desk data | Present-only / cache DTO · never invent missing cells |

## Visual language

### Shell (OpenCode)
- Near-black `#0b0b0b`, hairline borders, peach selection in palette
- Thin context rail · status strip

### Stage (Night ink · journey desks)
- Brass / mint / coral semantics
- Signature masts: **Verdict** · **Geometry** · **Harga** · **Net**
- Reject: equal-weight CLI Rich dump as the stage

## Related

- ADR: [`ADR-051`](../adr/ADR-051-tui-opencode-cockpit-clean-break.md)
- E2E spine: [`end-to-end-journey.html`](./end-to-end-journey.html)
