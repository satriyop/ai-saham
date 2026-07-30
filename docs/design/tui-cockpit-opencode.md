# Daily Cockpit TUI — OpenCode visual bible (end-to-end)

**Status:** design mock · ADR-051 · complete stage map in one file  
**Mock:** [`tui-cockpit-opencode.html`](./tui-cockpit-opencode.html)  
**Journey hub (IA inspiration only):** [`tui-journey-hub.html`](./tui-journey-hub.html)

### What ships vs mock-only

| Layer | Ships in Textual TUI? | Notes |
|-------|----------------------|--------|
| **`.app` shell** (header · stage · sidebar · prompt rail · status) | **Yes — product bible** | OpenCode black/peach · layout B |
| **`.design-tools`** (1–8 stage buttons · rev stamp) | **No** | HTML mock only · above app · never over sidebar |
| Journey night-ink desk HTML | No | IA / hierarchy inspiration only |

### Chrome noise (do not paint in product UI)

Put implementer notes **only in this doc** (or code comments). Never as stage body labels.

| Bad (not in UI) | Where it lives instead |
|-----------------|------------------------|
| `Candidates · option-B columns (1:1 TUI)` | Accum cols = `BOARD_COLUMN_LABELS` (below) |
| `IA tui-*.html` · `JudgeDeskModel` · `FULL_PANEL_ORDER` | This doc · code modules |
| `cols 1:1 TUI` · `Evidence strip · focus row` | Column contracts below |
| Design jargon as operator copy (`Price hero` in body titles) | Use product titles: View · ticker · BBCA |

### Column contracts (implementer)

| Stage | Columns / fields |
|-------|------------------|
| Accum | `Ticker · Signal · Accum · Action · Phase · Streak · RSI · Net% · Disc% · Price · Gate` (`BOARD_COLUMN_LABELS`) |
| Pre-open | `Tkr · IEP · Δ% · IEV · NCP · ΔIEV · Grd · Risk` |
| Broker list | `Code · Type · AsOf · DayNet · Net5 · Stk · Δ1 · # · Top` |

---

## Design authority

| Source | Authority | Use for |
|--------|-----------|---------|
| **OpenCode taste** | **Bible for TUI visuals** | Black-on-black, peach selection, mono density, hairlines, cards/tables |
| **Journey / desk HTML** | **Inspiration only** | Stage map, keys, Action vs browse, column contracts, hierarchy *ideas* |
| **Shipped TUI code** | **Data richness** | When code DTOs are richer than primary stage, design uses **detail flags** (expand), not always-on walls |

Ship Textual against **`.app` inside this mock**. Design-tools strip is for reviewing frames in browser only.

---

## End-to-end frames (primary tabs · hotkeys 1–8)

| # | Frame | Path | What you see (OpenCode) |
|---|--------|------|-------------------------|
| 1 | Accum | Action discover | Signal radar · **snapshot\|live** badge · Action chips · Enter → Judge |
| 2 | Plan | Structure | Geometry triangle · inherit Action · `l` paper confirm |
| 3 | Paper | Notebook | Notebook tape · write via plan `l` confirm |
| 4 | Pre-open | Auction | IEP board → Enter **inspect** (flags: why / auction+ / warn) |
| 5 | Ticker | Browse | Price hero · presence · **depth** flag for full panels |
| 6 | Broker | Browse | Radar → Enter net hero · flags partial_net / from_ticker · deep.t\|f\|h |
| 7 | Health | Honesty | Empty / zero / lag / ready posters |
| 8 | Palette | Nav | Ctrl+P · peach selection |

### Prompt rail (footer · design only)

| Piece | Spec |
|-------|------|
| Placement | Row **above** status bar (OpenCode-style chrome) |
| Affordance | `›` + mono input + mode chip (`idle` · `agent` · `cli`) |
| Focus | click rail · `:` or `/` |
| Keys | `↵` submit mock · `esc` blur/clear · Ctrl+P still palette |
| Later | agent adapter · CLI passthrough · never Action authority |
| Now | toast `prompt · design only · not wired` |

Not a chat bubble. Not a second palette. Free text only until hooked.

### Nested (no tab · no digit hotkey)

| Stage | Enter from | What |
|-------|------------|------|
| **Judge** | Accum **Enter** only | Verdict hero + **detail flags** (stack · readiness · named · mce · phase+ · limited) |
| Pre-open inspect | Pre-open board Enter | IEP hero + auction flags |
| Broker home | Broker radar Enter | Net hero + hub · deep table flags |

**Reject:** Judge as a top frame-switch button or number key.

---

## Detail flags (code-richer data)

Primary stage stays scannable. Richer DTO fields hang on **chips** (mono pills). Expand only when data exists (or limited/snapshot is true).

| Stage | Flags | Code source |
|-------|-------|-------------|
| Accum | `snapshot` \| `live` badge | `board_source` / chrome_cues |
| Judge | **`d` / `detail`** = all panels (CLI `--detail`) · singles: `stack` · `readiness` · `named` · `mce` · `phase+` · `limited` | `JudgeDeskModel` / `decision_display` · screen accum `--detail` |
| Pre-open inspect | `why` · `auction+` · `warn` | `preopen_engine_inspect_presenter` |
| Ticker | **`d` / `detail`** = full CLI panels (inverse of `view ticker --brief`) | Primary = dashboard hierarchy; detail = remaining FULL_PANEL_ORDER |
| Broker list | `partial_net` · `from_ticker` | `has_partial_netx` · `ticker-desks` stage |
| Broker home | `deep.t` · `deep.f` · `deep.h` | ViewBrokerDesk top/flow/history loaders |

**Rules**

1. Chip visible when data/state can exist; dim when not loaded.  
2. Expand = more panels in-stage (scroll), not a new Action path.  
3. Diagnostic (`mce`, named setups, sector_macro) never implies ENTER.  
4. Density bars = scalar sugar only — not charts.

---

## Authority

| Path | Keys | Must not |
|------|------|----------|
| **Action** | Board `Enter` → Judge · `p` Plan · `l` Paper | Ticker/broker invent Action |
| **Browse** | `v t` · `v b` · broker Enter home · `t`/`f`/`h` | ENTER/WATCH/AVOID authority |
| **Paper** | Confirm after geometry | Auto-write · corpus · orders |
| **Pre-open** | Enter → auction inspect | Same stage as accum Judge |

**Chrome noise:** authority in this table + key wiring. Do not stamp every stage with “not Action / not judgment.”

---

## Contracts (summary)

### Judge (nested)
- Primary: Action · Gate · Signal · Accum · Authority% · Family · Why · phase timeline · primary cards  
- **`d`** (or chip `detail · d`): toggle **all** detail panels — same idea as CLI `screen accum --detail` / full vs compact  
- Single chips still work for one panel at a time  
- `limited` is **state** (snapshot / no candidate), not part of `--detail`; `j` / `r` recover full object  
- Detail expand never invents fields when limited

### Accum
- Cols 1:1 `BOARD_COLUMN_LABELS`  
- Badge: snapshot · limited judge until j/r  ↔  live · full present-only judge  

### Pre-open inspect
- Primary: grade · risk · IEP · levels  
- Flags: why · auction+ (trend · broker tag · backing_score · buy_streak) · warn  

### Ticker (`v t` · on par with `saham view ticker show`)
- **Primary (default):** identity · freshness · last close · horizons · fundamentals · pulse · earnings  
  — matches TUI desk / operational dashboard (CLI `--brief`-class density)  
- **`d` (detail):** expand full panel inventory (analyst · ownership · sector · corp · insider · seasonality · iev · sentiment · profile · candles)  
  — same idea as CLI **without** `--brief`, or accum/judge **`--detail` / `d`**  
- Header meta: `local cache` or `full · local cache` — no design jargon  
- Footer: `b` desks · `p` plan · `esc` · `d` detail

### Broker (`v b` · desk-centric)
- Radar + Enter home: **day net for that desk code** (tracked `broker_daily_flow`)  
- Hub:
  - **`t` buy/sell** — dual heat **latest session only** (buy + sell sides)
  - **`f` flow** — this desk’s day-net series (`ViewBrokerDeskFlow`)
  - **`c` calendar** — ~1 month: top stock collected + desk net + B/S per session day
  - **`h` history** — per-ticker daily for this desk
  - **`m` top 5** — **matrix** of top **5 net buy** names across windows **1s · 3s · 5s · 10s · 20s** (default emphasis **1s**); metric = desk net buy sum; click cell → view ticker  
  - **`v`** — open view ticker for desk’s current top (1s #1), not a hub tab  
- Never market foreign total  
- **Session vs multi-window:** `t` = latest dual · `m` = multi-session top-5 net buy

### Plan / Paper / Health
- Plan geometry triangle · paper tape · health posters (unchanged contracts)

---

## Visual (OpenCode only)

- `#0b0b0b` / `#141414` / `#1c1c1c` · peach `#c9a68a`  
- Semantic green / amber / red  
- Hierarchy by weight — not Fraunces  

### Reject
- Night-ink as ship skin  
- Judge as primary tab  
- Flat CLI dump as only ticker stage  
- Always-on full depth wall without `depth` flag  
- Product charts  

---

## Related

- ADR: [`ADR-051`](../adr/ADR-051-tui-opencode-cockpit-clean-break.md)  
- Journey: [`tui-journey-hub.html`](./tui-journey-hub.html)  
- Code: `src/adapters/tui/` (`JudgeDeskModel`, `TickerDeskModel`, presenters, `main.py` stages)  
