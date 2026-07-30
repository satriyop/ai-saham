# Daily Cockpit TUI — OpenCode visual bible (end-to-end)

**Status:** design mock · ADR-051 · complete stage map in one file  
**Mock:** [`tui-cockpit-opencode.html`](./tui-cockpit-opencode.html)  
**Journey hub (IA inspiration only):** [`tui-journey-hub.html`](./tui-journey-hub.html)

---

## Design authority

| Source | Authority | Use for |
|--------|-----------|---------|
| **OpenCode taste** | **Bible for TUI visuals** | Black-on-black, peach selection, mono density, hairlines, cards/tables |
| **Journey / desk HTML** | **Inspiration only** | Stage map, keys, Action vs browse, column contracts, hierarchy *ideas* |

Ship Textual against **this cockpit mock**. Standalone journey HTML may stay “elevated web vision”; it is **not** the live TUI skin.

---

## End-to-end frames (hotkeys 1–9)

| # | Frame | Path | What you see (OpenCode) |
|---|--------|------|-------------------------|
| 1 | Accum | Action discover | Signal radar table · cols 1:1 TUI · Action chips |
| 2 | Judge | Action present-only | Action/Gate first · scores · phase · compact cards |
| 3 | Plan | Structure | Entry/Stop/Target · inherit Action · no order |
| 4 | Paper | Notebook | Geometry confirm · paper only · not learning |
| 5 | Pre-open | Auction | IEP board · inspect ≠ accum Judge |
| 6 | Ticker | Browse | Price-first hierarchy · pulse strip · not Action |
| 7 | Broker | Browse | Desk radar table + Net strip · not Action |
| 8 | Health | Honesty | Empty / zero / lag / ready posters |
| 9 | Palette | Nav | Ctrl+P · peach selection · no scenario tabs |

---

## Authority

| Path | Keys | Must not |
|------|------|----------|
| **Action** | Board `Enter` → Judge · `p` Plan · `l` Paper | Ticker/broker invent Action |
| **Browse** | `v t` ticker · `v b` broker | ENTER/WATCH/AVOID authority |
| **Paper** | Confirm after geometry | Auto-write · corpus · orders |
| **Pre-open** | Inspect ≠ accum Judge | Same Enter as accum Judge |

---

## Visual (OpenCode only)

- `#0b0b0b` / `#141414` / `#1c1c1c` borders  
- Peach `#c9a68a` selection (palette / row focus)  
- Semantic green / amber / red for pass · watch · block  
- Hierarchy = weight and first-line Action/price — not Fraunces display type  

### Reject in this file
- Night-ink / brass marketing CSS as primary stage skin (`desk-v2`, Fraunces body UI)  
- Broker only as toast (“see other HTML”)  
- Enter on accum opening ticker  

---

## Related

- ADR: [`ADR-051`](../adr/ADR-051-tui-opencode-cockpit-clean-break.md)  
- Journey inspiration: hub + desk HTML files  
- E2E: [`end-to-end-journey.html`](./end-to-end-journey.html)  
