# Daily Cockpit TUI — OpenCode visual bible

**Status:** design mock · ADR-051  
**Mock:** [`tui-cockpit-opencode.html`](./tui-cockpit-opencode.html)  
**Journey hub (structure inspiration only):** [`tui-journey-hub.html`](./tui-journey-hub.html)

---

## Design authority (read this first)

| Source | Authority | Use for |
|--------|-----------|---------|
| **OpenCode taste** | **Bible for TUI visuals** | Black-on-black chrome, palette, selection, density, type, borders, status strip |
| **Journey / desk HTML** | **Inspiration only** | Which stages exist, Action vs browse authority, column contracts, hierarchy *ideas* (mast, chips, posters) |

**Do not** re-skin the cockpit as Fraunces / night-ink “web trading floor.”  
**Do** keep OpenCode: near-black surfaces, hairline borders, peach selection, mono density.

Journey mocks (judge / plan / ticker / …) may use richer web fonts for **product vision** slides.  
**Implementable TUI** = OpenCode shell + journey *structure*, translated into OpenCode tokens.

```
Journey inspiration          OpenCode bible (ship this)
─────────────────          ──────────────────────────
Verdict mast idea    →     Action/Gate first in mono stage
Geometry triangle    →     Entry/Stop/Target hierarchy, same palette
Harga mast idea      →     Price-first layout, #d8d8d8 / peach focus
Signal radar chips   →     Action/Gate color in DataTable (green/amber/red)
Health posters       →     Distinct empty copy, still OpenCode empty stage
```

---

## Role of this mock

| Layer | Owns |
|-------|------|
| **Shell** | Layout B · Ctrl+P palette · sidebar · status · black-on-black OpenCode |
| **Stage frames** | Journey *flow* (accum → judge → plan → paper · pre-open · ticker · health) rendered **in OpenCode taste** |
| **Standalone journey HTML** | Optional elevated vision; not a second skin for Textual |

---

## Journey frames (hotkeys 1–8) — structure only

| # | Frame | Inspired by (flow) | Visual skin |
|---|--------|--------------------|-------------|
| 1 | Accum | Signal radar · cols 1:1 TUI | OpenCode table |
| 2 | Judge | Present-only · Action first | OpenCode stage hierarchy |
| 3 | Plan | Structure · inherit Action | OpenCode stage hierarchy |
| 4 | Paper | Notebook confirm from geometry | OpenCode modal / stage |
| 5 | Pre-open | Auction · ≠ accum Judge | OpenCode dense table |
| 6 | Ticker | Cache dashboard · not Action | OpenCode price-first stage |
| 7 | Health | Empty / zero / lag / ready | OpenCode empty posters |
| 8 | Palette | Commands | **OpenCode signature** |

**Broker:** [`tui-broker-desk.html`](./tui-broker-desk.html) — same rule: OpenCode in TUI; journey HTML is IA inspiration.

---

## Authority (from journey — product, not palette)

| Path | Keys | Must not |
|------|------|----------|
| **Action** | Board `Enter` → Judge · `p` Plan · `l` Paper | Ticker invent Action |
| **Browse** | `v t` · `v b` | ENTER/WATCH/AVOID authority |
| **Paper** | Confirm after geometry | Auto-write · corpus · orders |
| **Pre-open** | Inspect ≠ accum Judge | Same Enter as accum Judge |

---

## Product locks

| Decision | Choice |
|----------|--------|
| Role | Daily **cockpit**, not IDE |
| Layout | **B** — full main + thin right sidebar |
| Navigation | **No scenario tabs** — `Ctrl+P` |
| **Visual** | **OpenCode black-on-black (mandatory)** |
| **IA / stages** | Inspired by journey hub |
| Online | Explicit fetch · local-first |

---

## Visual language (OpenCode — bible)

### Chrome
- Background `#0b0b0b` / elevated `#141414` — not blue-gray IDE, not brass night-ink web
- Hairline borders `#1c1c1c`
- Thin context rail · bottom status strip
- **Peach selection** `#c9a68a` on dark text — palette tell

### Type
- **IBM Plex Mono** for UI density (TUI reality)
- Tabular nums for prices / scores
- Hierarchy = size/weight/color in mono, not Fraunces display

### Stage semantics (colors only, still OpenCode)
- Pass / open: soft green `#6fbf8a`
- Watch / lag: amber `#d4b06a`
- Avoid / block: red `#c97a72`
- Dim labels: `#7a7a7a` / `#555555`

### Reject
- Fraunces + Outfit “product landing” as the live TUI skin
- Equal-weight CLI dump with no hierarchy
- Blurring OpenCode shell with journey marketing CSS

---

## Related

- ADR: [`ADR-051`](../adr/ADR-051-tui-opencode-cockpit-clean-break.md)
- Journey (inspiration): [`tui-journey-hub.html`](./tui-journey-hub.html)
- E2E: [`end-to-end-journey.html`](./end-to-end-journey.html)
