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
| 3 | Plan | Structure | **Geometry triangle** Entry→Stop→Target · inherit Action · `l` paper confirm |
| 4 | Paper | Notebook | **Notebook tape** (date · ticker · E/S/T · status) · write via plan `l` confirm |
| 5 | Pre-open | Auction | IEP board → **Enter** auction **inspect** (not accum Judge) |
| 6 | Ticker | Browse | **Price hero** hierarchy (IA: ticker-desk) · full fields |
| 7 | Broker | Browse | Desk **radar** → **Enter** **Net hero** home (top/flow/hist hub) |
| 8 | Health | Honesty | Empty / zero / lag / ready posters |
| 9 | Palette | Nav | Ctrl+P · peach selection · no scenario tabs |

---

## Authority

| Path | Keys | Must not |
|------|------|----------|
| **Action** | Board `Enter` → Judge · `p` Plan · `l` Paper | Ticker/broker invent Action |
| **Browse** | `v t` ticker · `v b` broker radar · broker `Enter` desk home · `t`/`f`/`h` deep · `v` jump ticker | ENTER/WATCH/AVOID authority |
| **Paper** | Confirm after geometry | Auto-write · corpus · orders |
| **Pre-open** | `Enter` → auction inspect stage | Same frame as accum Judge / TradeSetup Action |

**Chrome noise:** authority lives in this table and in **key wiring** (Enter → Judge, browse paths). Do **not** stamp every stage with “not Action / not judgment / not a re-score.” Operators already know where judgment lives.

### Pre-open contract (frame 5 · design-final for TUI)

IA source: [`tui-preopen-board.html`](./tui-preopen-board.html).

| Mode | Keys | Stage |
|------|------|--------|
| **Board** | `s p` / frame 5 · `↑↓` | Auction strip + IEP table (cols 1:1) |
| **Inspect** | **Enter** from board | Grade · risk · IEP hero · IEV/NCP/ΔIEV · auction trail |
| **Back** | `esc` | Inspect → board → accum |

**Why not Judge?** Accum Judge is **TradeSetup Action** (ENTER/WATCH/AVOID) present-only. Pre-open is **auction / IEV evidence** only. Same key (`Enter`), different authority — never open frame 2 Judge from pre-open.

### Plan contract (frame 3 · design-final for TUI)

IA source: [`tui-plan-desk.html`](./tui-plan-desk.html) · chrome = OpenCode.

| Block | Content |
|-------|---------|
| **Inherit** | Board Action (WATCH/ENTER/…) · structure does not re-score |
| **Geometry hero** | Entry → Stop → Target triangle + lots · risk% · plan id · horizon |
| **Board context** | Signal · Accum · Gate · source row |
| **Actions** | `l` paper log confirm · `p` re-run · `esc` board |
| **Write** | Confirm overlay (same as paper path) — not silent |

Reject: one-line summary only · second analysis report · confirm embedded as the whole stage.

### Paper contract (frame 4 · design-final for TUI)

IA source: [`tui-paper-journal.html`](./tui-paper-journal.html) · chrome = OpenCode.

| Mode | What |
|------|------|
| **Stage** | Chronological **notebook tape** — day · ticker · frozen geometry · status (`logged` / `duplicate`) |
| **Empty** | “no paper notes yet · plan then l confirm” |
| **Write** | Plan desk `l` → confirm overlay → append row (no silent write) |
| **Source** | `trade accum log --from-plan` / swing_trade_plan |

Reject: paper stage as a single “log this ticker” card that *is* the confirm UI. Confirm is overlay; stage is the tape.

---

## Visual (OpenCode only)

- `#0b0b0b` / `#141414` / `#1c1c1c` borders  
- Peach `#c9a68a` selection (palette / row focus)  
- Semantic green / amber / red for pass · watch · block  
- Hierarchy = weight and first-line Action / price / net — not Fraunces display type  

### Density bars ≠ graphs

Cockpit may show **mono density tracks** (Net5 amp, horizon width, buy/sell heat, EPS density). Rules:

| Allowed | Forbidden |
|---------|-----------|
| 1-D track width from a **scalar** already on the DTO (`|Net5|`, `% change`, EPS) | Live price charts, plotted candles, multi-series graphs |
| Same OpenCode hairline / mint-coral semantics | Chart libraries, sparkline engines, “TA chart” product surface |
| Honest empty when scalar missing | Inventing a series to fill a bar |

Textual can render density with characters or ProgressBar — still not a graph product.

### Ticker contract (frame 6 · design-final for TUI)

IA source: [`tui-ticker-desk.html`](./tui-ticker-desk.html) · chrome = OpenCode.

| Stage | Content |
|-------|---------|
| **Identity** | Code · name · board · sector · tradeable · as_of |
| **Freshness** | ok / miss / stale pills from `freshness[]` |
| **Price hero** | Monumental `latest_close` + 1d · horizons 1d/5d/20d · 52w **range position** |
| **Ribbon** | PE · PBV · MCap · ROE · Div · F-Score (`fundamentals` or —) |
| **Pulse trio** | Foreign flow · structure · bandar |
| **Earnings** | ≤4Q EPS + YoY |
| **Depth** | Remaining `FULL_PANEL_ORDER` (analyst · ownership · sector_macro · corp · insider · seasonality · iev · sentiment · profile · candles table) |

Reject: flat CLI panel dump as the only stage (no Harga landscape).  
Reject: presence-only strip instead of full fields.  
Reject: treating 52w range position as a return.  
Parallel to broker: **price** is ticker landscape; **day net** is desk landscape.

### Broker contract (frame 7 · design-final for TUI)

| Mode | Keys | Stage |
|------|------|--------|
| **Radar** | `v b` land · `↑↓` · **Enter** | Tracked desk table · Net5 amp · cols 1:1 |
| **Home** | Enter from radar | Net hero (day net landscape) · identity · side stats |
| **Hub** | `t` top · `f` flow · `h` history · `v` ticker | Buy/sell heat · day flow · hist table · jump ticker |
| **Back** | `esc` on home → radar · `esc` on radar → board | Trail language |

Reject: radar with a thin “selected strip” instead of full desk home.  
Reject: deep panels only as “CLI later” labels with no UI.  
IA source: [`tui-broker-desk.html`](./tui-broker-desk.html) · chrome = OpenCode.

### Reject in this file
- Night-ink / brass marketing CSS as primary stage skin (`desk-v2`, Fraunces body UI)  
- Broker only as toast (“see other HTML”)  
- Broker Enter only painting a footer strip (must open full Net hero home)  
- Enter on accum opening ticker  

---

## Related

- ADR: [`ADR-051`](../adr/ADR-051-tui-opencode-cockpit-clean-break.md)  
- Journey inspiration: hub + desk HTML files  
- E2E: [`end-to-end-journey.html`](./end-to-end-journey.html)  
