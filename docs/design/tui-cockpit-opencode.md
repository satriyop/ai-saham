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
| Row labels `Deep` · `Hub` · `Density` · `List` · `Flags` | Chip text only · see Chip bar contract |

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
| **Shipped TUI code** | **Data richness** | Density duals **brief ↔ detail (`[d] detail`)**; chip bars open jobs / options |

Ship Textual against **`.app` inside this mock**. Design-tools strip is for reviewing frames in browser only.

---

## End-to-end frames (primary tabs · hotkeys 1–8)

| # | Frame | Path | What you see (OpenCode) |
|---|--------|------|-------------------------|
| 1 | Accum | Action discover | Signal radar · **snapshot\|live** badge · Action chips · Enter → Judge |
| 2 | Plan | Structure | Geometry triangle · inherit Action · `l` paper confirm |
| 3 | Paper | Notebook | Notebook tape · write via plan `l` confirm |
| 4 | Pre-open | Auction | IEP board → Enter **inspect** (option chips) |
| 5 | Ticker | Browse | **brief / detail (`[d]`)** · job chips with brass keycaps → CLI siblings |
| 6 | Broker | Browse | Radar → Enter desk home · list options · desk job chips |
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
| **Judge** | Accum **Enter** only | Verdict hero · **brief (default) / detail (`d`)** · limited = **banner** only |
| Pre-open inspect | Pre-open board Enter | IEP hero + option chips |
| Broker home | Broker radar Enter | Net hero + job chip bar |

**Reject:** Judge as a top frame-switch button or number key.  
**Reject:** Judge multi-chip wall (`stack` · `readiness` · `named` · `mce` · `phase+` · `limited` pills).

---

## Density duals (CLI multi-surface) — one dual everywhere

| Surface | Default | Toggle | CLI analog |
|---------|---------|--------|------------|
| **Judge** (Action · screen-shaped) | **brief** | `d` → **detail** | without / with `--detail` |
| **Ticker show** (browse · view-shaped) | **brief** | `d` → **detail** | `show --brief` / full `show` |

**Vocabulary (shared)**

| Term | Means | Not |
|------|--------|-----|
| **brief / detail** | Density dual on Judge **and** Ticker | limited state · job chips |
| **limited** | Snapshot / no candidate on Judge | density mode |
| **Job chip** | Sibling CLI / desk page for focus entity | density expand |
| **Option chip** | Optional panel or list filter | density · Action |
| **Chip bar** | Shared horizontal control row | free-floating one-off buttons |

**Locked rules (shared)**

1. **`limited` ≠ `brief`.**  
2. Density is **one dual per surface**: **brief (default) ↔ detail (`d`)**. Same words on Judge and Ticker.  
3. Density control = **one** affordance: chip **`[d] detail`** and/or key **`d`** — not a panel-name wall.  
4. Empty sections omit or honest empty — do not invent.  
5. Diagnostic never Action authority.  
6. Density bars = scalar sugar only — not charts.  
7. Job / option chips are **not** density. Labels stand alone — **no** row-label chrome.

---

## 1. Shared Chip bar contract (foundation)

**Authority:** every stage that exposes density, jobs, or options uses **this** interaction model.  
**Order:** implement foundation first in TUI (shared widget), then wire stage inventories.  
**Workflow:** design + mock first · Textual only after explicit go.  
**Lock (2026-08-01):** power key is **visible on the chip** — bold brass `[k]` leading the product word.

### Placement & chrome

| Rule | Spec |
|------|------|
| Placement | One horizontal row under the stage section label (or under mast if no separate title) |
| Contents | Chips only · **no density status text** after the bar |
| Row labels | **Forbidden** in product UI: `Deep`, `Hub`, `Density`, `List`, `Detail`, `Flags` |
| Chip label | **`[k] word`** — see Keycap-in-chip (below) |
| Order | **Jobs / options first** (left → right) · **density last** when present |
| Missing data | Chip **dim** (still focusable) or omit — honest; never invent content |
| Density state | **`[d] detail` chip `is-on` = detail** · default (not on) = brief — **no** `brief` / `detail` meta label |

### Keycap-in-chip (locked)

Every chip that has a **power letter** paints that letter **on the chip**, not only in a footer legend.

| Rule | Spec |
|------|------|
| Pattern | **`[k] label`** — brackets + single letter, then product / CLI word |
| Position | **Leading** only — never trailing (`foreign [o]` forbidden) |
| Weight | **Bold** on the keycap token `[k]` only · label normal weight |
| Color | **Brass** (`#d4b06a` / design token `--brass`) on the keycap · label mute/ash |
| Space | One space after `]`: `[f] flow` |
| Density | **`[d] detail`** only — not `detail · d` · **never** a second word `brief` on the bar |
| No power key | Option chips without a letter stay **label-only** (pre-open `why` · `auction+` · `warn`) — no fake `[—]` |
| is-on | Chip fills **peach**; keycap stays bold — use dark ink on peach so `[k]` remains readable (not brass-on-peach mud) |
| Dim | Keycap + label both dim · still honest |

**Density is a toggle, not a status essay:**

| State | Paint | Operator reads |
|-------|--------|----------------|
| Brief (default) | `[d] detail` **not** `is-on` | “press d / chip for more” |
| Detail | `[d] detail` **`is-on`** (peach) | “detail is on · d to leave” |

**Reject:** meta/status after chips: `brief` · `detail` · `brief \| detail`. Noise — state is the chip.  
**Reject:** crumb or as-of lines that restate `brief ·` / `detail ·` for density (use `local cache` honesty only).

**Brass = navigation language (TUI-wide):**

| Token | Role | Examples |
|-------|------|----------|
| **Brass / amber** | “What to press” — keys, chip keycaps, footer `kbd` | `[b]`, footer `↑↓` key chips |
| **Peach** | Selection / active surface | row select · chip `is-on` · focus ring |
| **Mint / coral** | Data sign (pos / neg) — not navigation | nets · % · Action never from key color |

Do **not** use peach for key glyphs or brass for signed data. One scan dialect: **brass means keyboard**.

```text
[ b ] brokers   [ f ] flow   [ o ] foreign   [ x ] dist   [ n ] fin   [ d ] detail
  ^ brass bold    ^ label mute
```

**Reject:** bare product words with hidden power keys.  
**Reject:** trailing letter soup (`detail · d` as the only teaching form).  
**Reject:** inventing keycaps for option chips that have no power letter.

### Navigation (locked — plain Tab)

| Input | Behavior |
|-------|----------|
| **Mouse click** | Activate chip (toggle or open job) · focus moves to that chip |
| **Tab** | Next focusable control in the normal app/stage chain (**plain** focus chain) |
| **Shift+Tab** | Previous focusable control |
| **Enter** / **Space** | Activate **focused** chip |
| **Power letter** | Stage-local shortcut when listed below — same effect as click · **same letter as chip keycap** |
| **`d`** | Density only (Judge + Ticker **show**) — never a job letter |
| **Digits `1`–`8`** | Primary frames only — **never** chips |
| **`esc`** | Trail nested job / inspect / home; does not wipe unrelated toggles unless stage says so |

**Reject:** roving ←/→ chip groups (not this product).  
**Reject:** trapping Tab forever inside the bar — Tab may leave into body / sidebar / prompt.  
**Reject:** digits as job shortcuts (collides with frame map).

### Visual states

| State | Paint |
|-------|--------|
| Default | Hairline chip · brass bold `[k]` · mute label |
| Hover | Brighter border (pointer) · keycap stays brass |
| **Focus** (Tab) | Peach outline / focus ring — keyboard-visible |
| **Active / on** | Peach fill · dark bold `[k]` · dark label |
| Dim / unavailable | Reduced opacity · still honest |

### Semantics by chip kind

| Kind | Activate means | Label examples |
|------|----------------|----------------|
| **Density** | Toggle brief ↔ detail on current stage body | **`[d] detail`** |
| **Job** | Open sibling CLI / desk page · `esc` trail back | **`[b] brokers`** · **`[f] flow`** · **`[t] buy/sell`** |
| **Option** | Toggle optional panel (no power letter) | `why` · `auction+` · `warn` |

Jobs never invent Action. Options never re-score.

### TUI implementer notes (later · order)

1. Shared `ChipBar` + `FlagChip` — `key` + `label` → paint `[k] label` (brass bold key).  
2. Each chip: focusable control · click + Enter/Space.  
3. Rely on Textual **default Tab** focus chain — do not reimplement Tab.  
4. Stage `on_key` only for **documented power letters** + global `d` / `p` / `esc` — letter must match keycap.  
5. Wire stages in inventory order: Judge → Ticker → Pre-open inspect → Broker list → Broker home.  
6. Visual tokens match mock `.flag-chip` + `.chip-key` (brass) · peach focus/`is-on`.  
7. Footer `kbd` uses the **same brass** as chip keys (navigation dialect).

---

## 2. Consistent chip navigation (all stages)

Every row below is a **chip bar** under the Shared Chip bar contract.  
Power keys are **stage-local** (only while that stage owns input).

### Judge (nested)

| Chip (paint) | Kind | Power | Effect |
|--------------|------|-------|--------|
| **`[d] detail`** | density | `d` | toggle detail on/off (`is-on` = detail) |

- **No** meta `brief`/`detail` after the bar.  
- **No** multi-chip wall. Limited = **banner** only · not a chip.  
- Nav: click · Tab · Enter/Space · `d` (keycap + `is-on` teach state).

### Ticker show (`v t`)

| Chip (paint) | Kind | Power | CLI / effect |
|--------------|------|-------|----------------|
| **`[b] brokers`** | job | **`b`** | `view ticker top-brokers` |
| **`[f] flow`** | job | **`f`** | `view ticker flow` (foreign flow summary / `broker_summaries`) |
| **`[o] foreign`** | job | **`o`** | `view ticker foreign-history` |
| **`[x] dist`** | job | **`x`** | `view ticker distribution` |
| **`[n] fin`** | job | **`n`** | `view ticker financials` |
| **`[d] detail`** | density | **`d`** | toggle detail on **show** body (`is-on` = detail) |

- Word **`flow`** kept (CLI verb); keycap **`[f]`** is the scan target.  
- Job → sub-stage titled with CLI job name · bar remains · switch via chip or letter · `esc` → show.  
- **`d` only when show body is visible** (not while a job table is front). Prefer: `esc` first, then `d`.  
- Also: `p` plan · `esc` trail.  
- Nav: click · Tab · Enter/Space · **`b f o x n d`** (letters match keycaps).  
- **No** density meta text. Optional footer keys only: brass `b f o x n d · esc` (no “brief” word).

### Pre-open inspect

| Chip (paint) | Kind | Power | Effect |
|--------------|------|-------|--------|
| **why** | option | — | toggle why panel |
| **auction+** | option | — | toggle auction+ panel |
| **warn** | option | — | toggle warn panel |

- Nav: click · Tab · Enter/Space only (no letter soup · **no fake keycaps**).

### Broker list / stock desks (radar) — **no chip bar**

Honesty lives in **title + meta + footer**, not cryptic chips.

| Surface | Title | Meta / footer honesty |
|---------|-------|------------------------|
| Tracked radar (`v b`) | `View · broker list` | `{n} desks · tracked · Enter home` |
| From stock (`b` on ticker) | `View · desks · BBCA` | `{n} desks · top brokers · Enter home` |
| Thin Net windows | (same title) | append **`· thin NetX (partial sessions)`** when any desk lacks full Net3/5/… sample |

**Reject:** operator chips named `partial_net` / `from_ticker` (code keys as chrome).  
**Reject:** status chips that look like filters but do not change the table.

### Broker home (desk) — **TUI is design authority for richness**

Shipped `BrokerDesk` / desk models outrank a thinner mock. Design mock must stay at least as rich as:

| Block | Content (from TUI model) |
|-------|---------------------------|
| Identity | Code · name · **Foreign\|Local** · as of · ticker count |
| Scope | Tracked desk only · not market foreign total |
| Hero | **Day net** signed + unit · sub: lot · desk · tickers · tracked |
| Side pulse | **Net5** (sessions) · **Buy streak** · **Δ1** · **Top buy** |
| Dual heat | Top buy/sell stocks · bar + amount (mint/coral) |
| Chip bar | `[t] buy/sell` · `[f] flow` · `[c] calendar` · `[h] history` · `[m] top 5` |
| Legend | brass kbd: `t f c h m · v ticker · esc trail` |

| Chip (paint) | Kind | Power | Effect |
|--------------|------|-------|--------|
| **`[t] buy/sell`** | job | **`t`** | latest session dual heat |
| **`[f] flow`** | job | **`f`** | this desk day-net series |
| **`[c] calendar`** | job | **`c`** | ~1 month desk calendar |
| **`[h] history`** | job | **`h`** | per-ticker daily for desk |
| **`[m] top 5`** | job | **`m`** | multi-window top-5 matrix |

- Same chip bar model + **keycap-in-chip** (brass `[k]`); no “Hub” word in UI.  
- `v` → view ticker for desk top (1s #1) — not a chip.  
- Ticker `f` ≠ broker `f` (different stages — both valid; keycaps still show `[f]`).  
- Nav: click · Tab · Enter/Space · **`t f c h m`**.

### Stages without chip bar

Accum (source badge only) · Broker list / stock desks (honesty in meta) · Plan · Paper · Health · Palette.

---

## Ticker stage (content lock)

**Chip bar rules:** §2 Ticker show only — do not fork navigation here.  
**Lock date:** 2026-08-01 · multi-surface with `view ticker *`.

### Default: brief (consistent with Judge)

- Open density = **brief** (implementer word — **not** painted as bar meta).  
- Panel set: `BRIEF_PANEL_KEYS` via  
  `src/application/services/ticker_dashboard_layout.py` · `panel_keys_for_mode(brief=True)`.  
- CLI: brief ≈ `saham view ticker show TICKER --brief`.  
- **`d` / `[d] detail`** `is-on` → detail = `FULL_PANEL_ORDER` / full show without `--brief`.  
- Honesty line: **`local cache` only** — never restate density as `brief ·` / `detail ·` / `full`.  
- Paint may re-group hierarchy around panel keys (multi-surface keys stay).

### Panel inventory (authority = layout module)

| Mode | Keys (order preserved from `FULL_PANEL_ORDER`) |
|------|--------------------------------------------------|
| **Brief** (default) | identity · freshness · valuation · price_structure · earnings · bandar · foreign_flow |
| **Detail** (`d`) | + analyst · ownership · sector_macro · corp_actions · insider · seasonality · iev · **sentiment** · profile · candles (remainder) |

- `sector_macro` = diagnostic (ADR-053) · detail only.  
- **sentiment** panel = detail only · honest empty when not cached.

### Freshness grid — no cryptic labels

| Keep (short, readable) | Drop |
|------------------------|------|
| Price · Flow · Bandar · Earn · Fund · Analyst · Own · IEV · Insider | **`Sent`** |

- If news freshness later: **`News`** or full **`Sentiment`**, never `Sent`.

### Job sub-stage chrome

| Piece | Spec |
|-------|------|
| Title | `View · ticker · BBCA · flow` (CLI job name) |
| Body | **Job desk** (below) — not monospaced CLI dump |
| Trail | `esc` → show · chips / letters switch job |
| Meta | `local cache` · never Action |

---

## 3. Ticker job desks (design lock · 2026-08-01)

**Authority:** mock `.app` in `tui-cockpit-opencode.html` · multi-surface use cases unchanged.  
**All five jobs** (**brokers · flow · foreign · dist · fin**) stay **on-ticker** under the same chip bar.  
Brokers = stock desks radar body · **not** an independent stage · `esc` → ticker show · chips switch jobs.

### Shared shell (all four on-ticker jobs)

```text
View · ticker · BBCA · {job}          {job} · local cache
[ [b] brokers ][ [f] flow* ][ [o] foreign ][ [x] dist ][ [n] fin ][ [d] detail ]

┌─ HERO (elevated · peach left accent) ──────────────────┐
│  LAB (uppercase job story)                              │
│  BIG primary fact (signed net / latest / slogan)        │
│  sub: window · source · honesty                         │
└─────────────────────────────────────────────────────────┘
┌ pulse ┐ ┌ pulse ┐ ┌ pulse ┐ ┌ pulse ┐   (3–4 scalars)
SECTION · table or dual heat
footer: esc show · chips switch · CLI verb · browse only
```

| Layer | Spec |
|-------|------|
| Chip bar | Same as show · active job `is-on` · `d` does not apply on job body |
| Hero | One story · mint/coral for signed values |
| Pulses | Metric cards (`oc-metrics` / `oc-metric`) — not essays |
| Body | Table or dual column · density bars only as scalar sugar |
| Empty | Honest empty + fetch hint in hero sub or body |
| Loading | In-place body only · never unmask accum board |
| Reject | Flat monospaced dump as product UI · charts · Action invent |

### `flow` · `view ticker flow`

| Block | Content |
|-------|---------|
| Hero lab | `FOREIGN FLOW · 10d` |
| Hero big | Window total foreign net (signed) |
| Hero sub | `last N sessions · broker_summaries · as of DATE` |
| Pulses | Buy days · Sell days · Consec buy · Latest net |
| Body | Day table: `Date · Net · Ratio · Top buyer · Top seller` |
| Sugar | Optional bar on Net column (flow-day tracks) |

### `foreign` · `view ticker foreign-history`

| Block | Content |
|-------|---------|
| Hero lab | `FOREIGN HISTORY` |
| Hero big | Latest day foreign net (signed) |
| Hero sub | `source={stockbit\|idx} · last N days · foreign net only` |
| Pulses | 5d net · 20d net (from series) · # days · source |
| Body | `Date · Source · Net · Lot · Avg price` |

**Not the same job as flow:** summaries + top desks vs point series.

### `dist` · `view ticker distribution`

| Block | Content |
|-------|---------|
| Hero lab | `DISTRIBUTION · TICKER` |
| Hero big / slogan | Only if true: `★ Foreign buying from domestic` or `● Foreign dominate buys` — else omit slogan |
| Hero sub | `as of DATE · counterparty · local cache` |
| Type tags | **`F` = Foreign · `L` = Local** — never `A` (Asing) · pill badges |
| Pulses | Buy sides · Sell sides · Top buy desk · Top sell desk |
| Body | **Dual heat** (mint left / coral right) · rank · code · type pill · amount · CP rows with share **bars** |

```text
TOP BUYERS (from →)                 TOP SELLERS (to →)
1 YP [F]              128.4B        1 CC [L]               41.0B
  ← XL [L]  40.1B 31% ████          → YP [F]  18.2B 44% ████
  ← CC [L]  22.0B 17% ██            → AK [F]  10.1B 25% ██
```

Cap top 5 sides · top 4 counterparties. Share bar = % of that side’s amount.

### `fin` · `view ticker financials`

| Block | Content |
|-------|---------|
| Hero lab | `FINANCIALS` |
| Hero big | Latest income period label (e.g. `Q1 2026`) |
| Hero sub | `quarter · source=yahoo · local cache` |
| Body | **Three cards** (always show; honest empty per kind): |

| Card | Default metrics (compact rows) |
|------|--------------------------------|
| Income | Revenue · NI · EPS |
| Balance | Assets · Equity · Debt |
| Cashflow | Op CF · FCF · CapEx |

No full spreadsheet. Expand-to-wide columns is optional later — not show brief/detail dual.

### `brokers` · stock desks radar (**on-ticker job · same shell as flow/…**)

Not a 3-row mini top table. Chip **brokers** / `b` opens radar **under the ticker chip bar** (same job contract as flow/foreign/dist/fin):

| Piece | Spec |
|-------|------|
| Title | `View · ticker · TICKER · brokers` (job title · chip shell) |
| Hero | `STOCK DESKS · TICKER` · N desks · as of · top brokers · local cache |
| Meta | `view ticker top-brokers · local cache` · **partial NetX** when any desk partial |
| Body | Radar rows: `Code · Type · Role · DayNet · Net5 · Stk · Δ1` (richer NetX ok) |
| Type | **Foreign** / **Local** (words; not cryptic A) |
| Role | `buy` / `sell` from top-brokers ranking |
| NetX | Stock-scoped multi-session · partial marked |
| Keys | `↑↓` select · **Enter** desk home · **esc** ticker show · **chips switch job** |
| Reject | Independent `ticker-desks` stage that drops the chip bar · “leaves shell” |

### TUI implement order (after design accept)

1. Shared `TickerJobDesk` shell (hero + pulses + body slot)  
2. **flow** desk (highest daily use)  
3. **foreign** · **dist** · **fin**  
4. Keep loaders / use cases; replace monospaced paint only  

---

## Authority

| Path | Keys | Must not |
|------|------|----------|
| **Action** | Board `Enter` → Judge · `p` Plan · `l` Paper | Ticker/broker invent Action |
| **Browse** | `v t` · `v b` · broker Enter home · chip bar jobs | ENTER/WATCH/AVOID authority |
| **Paper** | Confirm after geometry | Auto-write · corpus · orders |
| **Pre-open** | Enter → auction inspect | Same stage as accum Judge |

**Chrome noise:** authority in this table + key wiring. Do not stamp every stage with “not Action / not judgment.”

---

## Contracts (summary)

### Judge (nested · screen-shaped)
- **Brief (default):** Action · Gate · Signal · Accum · Authority% · Family · Why · phase timeline · primary cards  
- **Detail (`d`):** + decision stack · phase ledger · secondary / diagnostic cards (fixed order; omit if no data)  
- Chip bar: **`[d] detail`** only · **`is-on` = detail** · **no** brief/detail meta text  
- CLI: without / with `--detail`  
- **Limited:** banner only · `j` / `r` — not a chip · not density meta

### Accum
- Cols 1:1 `BOARD_COLUMN_LABELS`  
- Badge: snapshot · limited judge until j/r  ↔  live · full present-only judge  

### Pre-open inspect
- Primary: grade · risk · IEP · levels  
- Chip bar options: why · auction+ · warn (Tab / click; no power letters)  

### Ticker (`v t` · multi-surface with `view ticker *`)
- **Brief (default)** / **Detail (`d`)** — same dual as Judge  
- Freshness: Price · Flow · Bandar · Earn · Fund · Analyst · Own · IEV · Insider — **no `Sent`**  
- Chip bar jobs: **`[b] brokers` · `[f] flow` · `[o] foreign` · `[x] dist` · `[n] fin`** + **`[d] detail`**  
- Power: **`b f o x n d`** · `p` plan · `esc` trail  
- Price mast: last · local close · chg **baseline-aligned**  
- **Job desks:** shared hero · pulses · body (§3) — not monospaced dump  
  - brokers → stock desks list · flow / foreign / dist / fin → on-ticker job desk  
- **TUI:** shared ChipBar · then TickerJobDesk widgets after design accept  

### Broker (`v b` · desk-centric)
- Radar / stock desks: **no chip bar** · title `View · desks · TICKER` or `View · broker list` · meta honesty for thin NetX
- Home: day net for desk code · job chips **buy/sell · flow · calendar · history · top 5** · keys **`t f c h m`**  
- Matrix cell: ticker · streak · net · avg buy · click → ticker  
- `v` → view ticker desk top · not a chip  
- Never market foreign total  

### Plan / Paper / Health
- Plan geometry · paper tape · health posters (unchanged)

---

## Visual (OpenCode only)

- `#0b0b0b` / `#141414` / `#1c1c1c` · peach `#c9a68a`  
- Semantic green / amber / red  
- Hierarchy by weight — not Fraunces  
- Chip **focus ring** = peach (keyboard path must be visible)

### Reject
- Night-ink as ship skin  
- Judge as primary tab  
- Flat CLI dump as only ticker stage without hierarchy  
- Judge multi-chip density wall  
- Ticker density inverted vs Judge (must be **brief default · detail `d`**)  
- Row chrome noise (`Deep`, `Hub`, `Density`, `List`, …)  
- Roving ←/→ chip bars (plain Tab only)  
- Density chips that invent panel names  
- Cryptic freshness labels (**`Sent`**, etc.)  
- Confusing **limited** with **brief**  
- Job chips that re-score or invent Action  
- Digits for chips  
- Product charts  

---

## Related

- ADR: [`ADR-051`](../adr/ADR-051-tui-opencode-cockpit-clean-break.md)  
- Journey: [`tui-journey-hub.html`](./tui-journey-hub.html)  
- Code (later): `src/adapters/tui/` shared ChipBar · stage desks · presenters  
