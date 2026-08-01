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
| Pre-open | `Tkr · Act · IEP · Δ% · IEV · NCP · ΔIEV · Risk` · session strip (see § Pre-open) |
| Broker list | `Code · Type · AsOf · DayNet · Net3 · Net5 · Net7 · Net10 · Net20 · Stk · Δ1 · # · Top` |

---

## Design authority

| Source | Authority | Use for |
|--------|-----------|---------|
| **OpenCode taste** | **Bible for TUI visuals** | Black-on-black, peach selection, mono density, hairlines, cards/tables |
| **Journey / desk HTML** | **Inspiration only** | Stage map, keys, Action vs browse, column contracts, hierarchy *ideas* |
| **Shipped TUI code** | **Data richness** | Density duals **brief ↔ detail (`[d] detail`)**; chip bars open jobs / options; fin period dual follows design when wired |

Ship Textual against **`.app` inside this mock**. Design-tools strip is for reviewing frames in browser only.

---

## End-to-end frames (primary tabs · hotkeys 1–8)

| # | Frame | Path | What you see (OpenCode) |
|---|--------|------|-------------------------|
| 1 | Accum | Action discover | Signal radar · **snapshot\|live** badge · Action chips · Enter → Judge |
| 2 | Plan | Structure | Geometry triangle · inherit Action · `l` paper confirm |
| 3 | Paper | Notebook | Notebook tape · write via plan `l` confirm |
| 4 | Pre-open | Auction | Session strip · Action board → Enter **inspect** (option chips) |
| 5 | Ticker | Browse | **In-stage chip nav** · brass job chips · density `[d]` · CLI siblings under bar |
| 6 | Broker | Browse | Radar → Enter desk home · **desk home in-stage job chips** |
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
| Pre-open inspect | Pre-open board Enter | Action hero · IEP · chips `why` · `auction+` · `plan` · `warn` |
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
| **Job chip** | Job surface under **same stage** chip bar for focus entity | density expand · **not** independent stage |
| **Option chip** | Optional panel on **same stage** | density · Action |
| **Chip bar** | Shared horizontal control row | free-floating one-off buttons |

**Locked rules (shared)**

1. **`limited` ≠ `brief`.**  
2. Density is **one dual per surface**: **brief (default) ↔ detail (`d`)**. Same words on Judge and Ticker.  
3. Density control = **one** affordance: chip **`[d] detail`** and/or key **`d`** — not a panel-name wall.  
4. Empty sections omit or honest empty — do not invent.  
5. Diagnostic never Action authority.  
6. Density / magnitude bars = **scalar sugar only** — not charts · **and** always carry an explicit **%** (see Scalar bar contract).  
7. Job / option chips are **not** density. Labels stand alone — **no** row-label chrome.

### Scalar bar contract (locked · 2026-08-01)

**Canonical good example:** dist dual heat CP rows — `amount · NN% · track` (Image / mock: `1.7B 13%` then bar).

Whenever a body paints a **magnitude or share bar** (HTML track fill **or** TUI glyph track):

| Rule | Spec |
|------|------|
| **% is mandatory** | Always show a clear integer percent label (`14%`, `42%`) next to the amount or bar — **never a bar alone** |
| **Bar width = that %** | Fill / glyph width is the same number the label shows (0 when empty / missing) |
| **Meaning named once** | Section head, column, or one density note declares the basis — not re-explained every row |
| **Two bases only** | **share** = % of parent total (dist CP of side amount) · **of max** = % of largest \|value\| in the painted window (flow sessions · foreign daily points · horizon sugar) |
| **Tone** | Signed net mint/coral · **% label mute** (`text-mute`) · track `#1a1a1a` |
| **Reject** | Orphan solid blocks without `%` · dual-scale charts · axes · inventing % when value missing · reusing **Ratio** (flow foreign-flow ratio) as the of-max bar label |

**TUI anti-pattern (fix):** foreign/flow solid glyph bars with no percent (mystery sugar).  
**Implement after design accept** — mock + this section are authority first.

```text
# of-max (flow / foreign) — good
Date        ▓▓▓▓░░░░  42%   −27.8B   …

# share (dist) — good  (canonical)
← ZP (F)  1.7B 13%
  ████████░░░░

# bad — bar without %
Date        ████████        −27.8B   …
```

---

## 1. Shared Chip bar contract (foundation)

**Authority:** every stage that exposes density, jobs, or options uses **this** interaction model.  
**Order:** implement foundation first in TUI (shared widget), then wire stage inventories.  
**Workflow:** design + mock first · Textual only after explicit go.  
**Lock (2026-08-01):** power key is **visible on the chip** — bold brass `[k]` leading the product word.  
**Lock (2026-08-01):** **in-stage chip navigation** is mandatory for every multi-chip stage (see below).  
**Lock (2026-08-01):** **keycap = real binding only** — never decorative brackets.  
**Lock (2026-08-01):** **binary toggles** (exactly two modes) use one dedicated power letter each · **flip label** · not a universal `[t]` · not `q` · density stays `[d] detail`.  
**Lock (2026-08-01):** **quiet in-place load** for every chip / job / instrument surface — no plain-text “Loading…” dump flash (see below).

### Vocabulary (use these terms)

| Term | Meaning |
|------|---------|
| **Stage** | One instrument / screen mode (Accum board, View ticker, Broker list, Desk home, Judge, …) |
| **Chip bar** | One horizontal row of **chips** under the stage title (not a “menu” or “tab strip”) |
| **Chip** | One bar control: **job**, **density**, **binary toggle**, or **option** |
| **Job chip** | Opens a sibling product surface for the **same entity** without leaving the stage |
| **Density chip** | Special binary toggle: brief ↔ detail on the **same stage body** (`[d] detail` · `is-on` = detail) |
| **Binary toggle chip** | Exactly **two** modes · one power letter · label shows **current mode** (flip label) · `is-on` = non-default mode |
| **Option chip** | Toggles an optional panel on the **same stage** (e.g. pre-open `why`) — no power letter unless listed |
| **Job surface** | Body under the chip bar while a job chip is `is-on` — still the **same stage** |
| **`is-on` / focus** | Active chip (peach fill) and keyboard focus on the bar |
| **Independent stage** | A *different* stage with its own chrome (title trail, table, **chip bar gone**) — **forbidden** as the result of a chip activate |

**Reference stage:** **View ticker** — chip bar + job surfaces under the bar is the canonical pattern.

### In-stage chip navigation (**mandatory**)

**One-line rule:**

> **Chip-bar stages use in-stage chip navigation: chips switch job / density / binary toggle / option on the same stage under a persistent chip bar; they never open an independent stage.**

Whenever a stage has **more than one chip** (or a density + job set), this is **required**:

| # | Rule |
|---|------|
| 1 | **Same stage** — Activating a chip does **not** open a separate stage |
| 2 | **Chip bar stays mounted** — Same chips, same order; active job/option is **`is-on`** |
| 3 | **Body swaps under the bar** — Default body *or* job surface; no full remount to another instrument |
| 4 | **Switch in place** — Chip click or power letter switches job without resetting the entity trail |
| 5 | **Close in place** — Second press same job **or** `esc` → stage default body (e.g. ticker show) |
| 6 | **Power letter = keycap** — Brass `[k]` matches the **actually bound** letter; stage-local only · **never decoration** |
| 7 | **Drill-in is separate** — e.g. Enter desk home may leave for a **nested** instrument; `esc` returns to **same stage + job** (or show), not a third parallel stage invented by the chip |
| 8 | **Quiet in-place load** — Chip / job activate never flashes a monospaced “Loading job…” essay (see **Quiet in-place load**) |

### Quiet in-place load (**mandatory · all chip-bar + instrument stages**)

**One-line rule:**

> **While a chip, job, or instrument surface loads: set selection immediately, stay on the same stage, never unmask the board under the click, and never replace the body with a plain-text loading dump.**

Applies to: **View ticker jobs**, **broker home jobs**, density/option toggles that re-fetch, and any future chip-bar stage. Board-level first entry (accum / pre-open first paint) may use a dedicated loading stage — that is **not** chip nav.

| # | Rule |
|---|------|
| 1 | **Chip / selection first** — Target chip is **`is-on`** (and focus may move) **immediately** on activate |
| 2 | **Same stage** — Stay on instrument stage (`detail` / desk shell). **Never** `stage=loading` + keep_board that unmasks accum under a chip click |
| 3 | **Hold body until ready** — Keep **show** (or prior honest surface) visible until the new structured payload is ready · **or** a quiet skeleton that matches the final desk chrome |
| 4 | **Meta may say loading** — Status / meta / crumb may include `loading` · not a full-body monospaced essay |
| 5 | **No plain-text load dump** — **Forbidden** as interim UI: `Loading flow…\nsaham view ticker flow …` (or any CLI paste) as the main body |
| 6 | **Swap once** — When ready, paint structured desk (hero · pulses · body) in one update · no intermediate plain-text frame |
| 7 | **Clear stale job payload** — On job switch, drop previous job payload so chrome cannot re-apply the wrong desk under the new chip |
| 8 | **Slow loads only** — Optional delayed cue (e.g. after ~150–200ms) may dim body or show skeleton · still not a text dump |

**Reject:** interim monospaced “Loading {job}…” walls.  
**Reject:** unmasking board table under chip click (accidental Judge).  
**Reject:** inventing fake metrics while loading.

**Canonical shape (View ticker):**

```text
Stage: View · ticker · UNVR
Show bar:  [b] brokers  [f] flow  [o] foreign  [x] dist  [n] fin  [d] detail
Job bar:   [b] brokers* [f] flow  [o] foreign  [x] dist  [n] fin          ← no [d]
Fin bar:   [b] brokers  [f] flow  [o] foreign  [x] dist  [n] fin*  [y] quarterly
                                                              │         ↑ fin sub-chip only
                                                              └─ fin is-on · no [d] on jobs
esc / second press → show body · [y] removed · [d] returns on show
```

**Anti-pattern (forbidden):**

```text
Chip → independent stage (new title, chip bar gone, separate trail)
```

Example of the anti-pattern (historical, **fixed**): brokers → `ticker-desks` stage that dropped the ticker chip bar.

**Stages that must conform**

| Stage | Chip bar | Conformance |
|-------|----------|-------------|
| **View ticker** | jobs + density | **Reference · conforming** |
| **Broker desk home** | `[t] buy/sell` · `[f] flow` · `[c] calendar` · `[h] history` · `[m] top 5` | **Mandatory** (same shell; deep job under bar) |
| **Judge** | `[d] detail` | **Mandatory** (density in-stage; no multi-job wall) |
| **Pre-open inspect** | option chips (`why` · `auction+` · `plan` · `warn`) | **Mandatory** (options in-stage) |
| Accum / Pre-open **board** | no multi job chips | N/A |
| Broker **list** (Ctrl+P) | no chip bar | N/A (list *is* the stage) |

**Intent:** entity stays fixed; depth changes under the bar. One mental model, simple `esc` trail, scannable brass keys.

### Placement & chrome

| Rule | Spec |
|------|------|
| Placement | One horizontal row under the stage section label (or under mast if no separate title) |
| Contents | Chips only · **no density status text** after the bar |
| Row labels | **Forbidden** in product UI: `Deep`, `Hub`, `Density`, `List`, `Detail`, `Flags` |
| Chip label | **`[k] word`** — see Keycap-in-chip (below) |
| Order | **Jobs / options first** (left → right) · **job-local binary toggles** next when armed · **density last** when present |
| Missing data | Chip **dim** (still focusable) or omit — honest; never invent content |
| Density state | **`[d] detail` chip `is-on` = detail** · default (not on) = brief — **no** `brief` / `detail` meta label |
| Binary toggle state | Label = **current mode word** · **`is-on` = non-default mode** · no `(A/B)` parentheses wall |

### Keycap-in-chip (locked)

Every chip that has a **power letter** paints that letter **on the chip**, not only in a footer legend.  
**`[k]` is a binding contract, not decoration.**

| Rule | Spec |
|------|------|
| Pattern | **`[k] label`** — brackets + single letter, then product / CLI / mode word |
| Honesty | Keycap appears **only** if that letter is wired on the current stage (or job-local scope) · unbind → remove keycap |
| Position | **Leading** only — never trailing (`foreign [o]` forbidden) |
| Weight | **Bold** on the keycap token `[k]` only · label normal weight |
| Color | **Brass** (`#d4b06a` / design token `--brass`) on the keycap · label mute/ash |
| Space | One space after `]`: `[f] flow` |
| Density | **`[d] detail`** only — not `detail · d` · **never** a second word `brief` on the bar |
| Binary toggle | **`[k] <current mode>`** — flip the mode word on activate · optional short dual `A\|B` only if both tokens are tiny |
| No power key | Option chips without a letter stay **label-only** (pre-open `why` · `auction+` · `plan` · `warn`) — no fake `[—]` |
| is-on | Chip fills **peach**; keycap stays bold — use dark ink on peach so `[k]` remains readable (not brass-on-peach mud) |
| Dim | Keycap + label both dim · still honest · **dimmed keycap still means the key exists** (unavailable data), not a fake |

### Binary toggles (locked · 2026-08-01)

Exactly **two** modes (e.g. brief/detail, quarterly/annual). Not jobs. Not multi-way menus.

| Rule | Spec |
|------|------|
| Power letter | **One dedicated letter per dual** · stage- or job-local · must match keycap |
| Label paint | **Flip label** — show the **current** mode word after `[k]` (e.g. `[y] quarterly` → press → `[y] annual`) |
| `is-on` | **Non-default** mode is peach; default mode is not `is-on` |
| Density exception | Density keeps fixed target word **`detail`** (not flip to `brief`) · `is-on` = detail — already locked |
| Scope | At most **one armed binary toggle** besides density per surface, unless letters are distinct and documented |
| Placement | Density = always last when present · other duals = **job-local sub-chips** |
| Job-local sub-chip | **Visible only while the owning job is `is-on`** · not painted on show or sibling jobs · not a permanent dim neighbor on the bar |
| CLI | Dual must map to a real CLI flag/arg when the job has one (fin: `--period quarterly\|annual`) |

**Forbidden for binary toggles**

| Reject | Why |
|--------|-----|
| Universal **`[t]`** for every toggle | Collides with broker job **`[t] buy/sell`**; two duals cannot share one letter; invents a second dialect |
| **`[t](Quarterly/Annually)`** / **`[t](Detail/Brief)`** as bar chrome | Parentheses dual wall is meta noise; density already `[d] detail` |
| **`q`** for quarterly | Global **quit** |
| **`p`** for period grain | Ticker/global **`p` = plan** |
| **`d`** for anything but density | Density is product-wide |
| Fake `[k]` with no binding | Confusing; brass means keyboard |
| Restating both modes after the bar | State lives on the chip |
| **Dim-on-bar sub-chip while another job is front** | Looks like global chrome; period grain is **fin context only** — hide / unmount, do not grey-out next to flow/foreign |

**Density is a toggle, not a status essay:**

| State | Paint | Operator reads |
|-------|--------|----------------|
| Brief (default) | `[d] detail` **not** `is-on` | “press d / chip for more” |
| Detail | `[d] detail` **`is-on`** (peach) | “detail is on · d to leave” |

**Period grain (fin job · binary toggle · example of flip label):**

| State | Paint | Operator reads |
|-------|--------|----------------|
| Fin **not** front | **Chip not painted** (hidden) · `y` unbound | no period control in context |
| Quarterly (default) · fin front | `[y] quarterly` **not** `is-on` · **visible only after `[n] fin`** | “quarter statements · y for annual” |
| Annual · fin front | `[y] annual` **`is-on`** (peach) | “annual statements · y back to quarter” |

Power **`y`** = year / annual dual mnemonic. Not `p` (plan), not `q` (quit), not `t` (broker job).  
**Context rule:** `[y]` is a **sub-chip of fin** — it enters the chip bar **only when fin is selected** (`is-on`), between fin and density. Leaving fin (esc, second press, or another job) **removes** it from the bar.

**Reject:** meta/status after chips: `brief` · `detail` · `brief \| detail` · `quarterly \| annual`. Noise — state is the chip.  
**Reject:** crumb or as-of lines that restate `brief ·` / `detail ·` for density (use `local cache` honesty only). Hero/sub may name the **active** grain once (`quarter` / `annual`) as data context — not a second control.

**Brass = navigation language (TUI-wide):**

| Token | Role | Examples |
|-------|------|----------|
| **Brass / amber** | “What to press” — keys, chip keycaps, footer `kbd` | `[b]`, footer `↑↓` key chips |
| **Peach** | Selection / active surface | row select · chip `is-on` · focus ring |
| **Mint / coral** | Data sign (pos / neg) — not navigation | nets · % · Action never from key color |

Do **not** use peach for key glyphs or brass for signed data. One scan dialect: **brass means keyboard**.

**List / board row move (locked · 2026-08-01):**

| Rule | Spec |
|------|------|
| Move | **`↑` / `↓` arrows only** (accum · pre-open · broker list · ticker desks radar · brokers job radar) |
| Footer | Paint **`↑↓ move`** — never `j/k` · never “vim” |
| Reject | **`j` / `k` as list navigation** (vim habit) — conflicts with Judge **`j` re-judge** and product copy |
| `j` | **Judge re-judge only** when Judge detail is front — not board cursor |

Prompt rail is chrome (`:` / `/` focus) · **no tall Input focus border** (ghost empty box is a bug).

```text
# show / non-fin job — no [y]
[ b ] brokers   [ f ] flow   [ o ] foreign   [ x ] dist   [ n ] fin   [ d ] detail

# fin selected — [y] appears as fin sub-chip
[ b ] brokers   [ f ] flow   [ o ] foreign   [ x ] dist   [ n ] fin*  [ y ] quarterly   [ d ] detail
  ^ brass bold    ^ label mute                                             ^ fin-only sub-chip
```

**Reject:** bare product words with hidden power keys.  
**Reject:** trailing letter soup (`detail · d` as the only teaching form).  
**Reject:** inventing keycaps for option chips that have no power letter.  
**Reject:** painting `[k]` as a “badge” when the letter does nothing.

### Navigation (locked — plain Tab)

| Input | Behavior |
|-------|----------|
| **Mouse click** | Activate chip (toggle or open job) · focus moves to that chip |
| **Tab** | Next focusable control in the normal app/stage chain (**plain** focus chain) |
| **Shift+Tab** | Previous focusable control |
| **Enter** / **Space** | Activate **focused** chip |
| **Power letter** | Stage-local shortcut when listed below — same effect as click · **same letter as chip keycap** |
| **`d`** | Density only (Judge + Ticker **show**) — never a job letter · never period grain |
| **`y`** | Fin period grain only while **fin** job surface is front — never a job letter · never plan |
| **`p`** | **Plan** (ticker / board path) — never period grain |
| **`q`** | **Quit** (global) — never quarterly |
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
| **Density** | Toggle brief ↔ detail on **current stage body** (fixed word `detail`) | **`[d] detail`** |
| **Binary toggle** | Flip exactly two modes · label shows **current** mode | **`[y] quarterly`** / **`[y] annual`** (fin) |
| **Job** | Open **job surface under the same chip bar** · `esc` → stage default body | **`[b] brokers`** · **`[f] flow`** · **`[t] buy/sell`** |
| **Option** | Toggle optional panel on **same stage** (no power letter) | `why` · `auction+` · `plan` · `warn` |

Jobs never invent Action. Options never re-score. Binary toggles never open a job surface.  
**Job ≠ independent stage** — see **In-stage chip navigation**.  
**Binary toggle ≠ universal `t`** — each dual has its own letter; density stays `d`.

### TUI implementer notes (later · order)

1. Shared `ChipBar` + `FlagChip` — `key` + `label` → paint `[k] label` (brass bold key) **only when bound**.  
2. Each chip: focusable control · click + Enter/Space.  
3. Rely on Textual **default Tab** focus chain — do not reimplement Tab.  
4. Stage `on_key` only for **documented power letters** + global `d` / `p` / `esc` (+ job-local `y` on fin) — letter must match keycap.  
5. **Never** route a chip activate to a new stage that unmounts the chip bar (in-stage chip navigation).  
6. Wire stages in inventory order: Judge → Ticker → Pre-open inspect → Broker list → Broker home.  
7. Visual tokens match mock `.flag-chip` + `.chip-key` (brass) · peach focus/`is-on`.  
8. Footer `kbd` uses the **same brass** as chip keys (navigation dialect).  
9. Binary toggles: one letter per dual · flip label · arm only in documented scope.

---

## 2. Stage chip inventories (all chip bars)

Every row below is a **chip bar** under the Shared Chip bar contract **and** **in-stage chip navigation**.  
Power keys are **stage-local** (only while that stage owns input).

### Judge (nested) · **in-stage chip navigation · conforming**

| Chip (paint) | Kind | Power | Effect |
|--------------|------|-------|--------|
| **`[d] detail`** | density | `d` | toggle detail on/off (`is-on` = detail) |

- **No** meta `brief`/`detail` after the bar.  
- **No** multi-chip wall. Limited = **banner** only · not a chip.  
- Nav: click · Tab · Enter/Space · `d` (keycap + `is-on` teach state).  
- Density never opens a new stage.

### Ticker show (`v t`) · **reference · conforming**

| Chip (paint) | Kind | Power | CLI / effect |
|--------------|------|-------|----------------|
| **`[b] brokers`** | job | **`b`** | `view ticker top-brokers` · **job surface** (stock desks radar) |
| **`[f] flow`** | job | **`f`** | `view ticker flow` (foreign flow summary / `broker_summaries`) |
| **`[o] foreign`** | job | **`o`** | `view ticker foreign-history` |
| **`[x] dist`** | job | **`x`** | `view ticker distribution` |
| **`[n] fin`** | job | **`n`** | `view ticker financials` |
| **`[y] quarterly`** / **`[y] annual`** | binary toggle · **fin sub-chip** | **`y`** | period grain · **painted only while fin `is-on`** · CLI `--period` |
| **`[d] detail`** | density · **show-only** | **`d`** | toggle detail on **show** body (`is-on` = detail) · **hidden on every job surface** |

- **All five jobs** are **job surfaces under this stage** — never leave for an independent stage.  
- Word **`flow`** kept (CLI verb); keycap **`[f]`** is the scan target.  
- Job → body under bar · `is-on` · switch via chip or letter · `esc` / second press → show.  
- **`[d] detail` is show-context only:** paint **only when no job is front** (show body). Hide (not dim) + unbind `d` while any job surface is front — density expands show panels that are not mounted under jobs.  
- **`[y]` is fin context only:** paint the sub-chip **only when `[n] fin` is selected**; hide (not dim) + unbind `y` on show and every other job.  
- **Drill-in:** brokers job · Enter desk home may nest; `esc` desk → **brokers job again** (not a third stage).  
- Also: `p` plan · `esc` trail to board · **`p` never means period**.  
- Nav: click · Tab · Enter/Space · **`b f o x n`** · **`y` only with fin front** · **`d` only on show**.  
- **No** density / period meta text after bar. Footer: brass `b f o x n · d · p plan · esc` on **show**; on **jobs** omit `d`; add **`y` period** only while fin front.

### Pre-open board + inspect · **in-stage · conforming**

See full **§ Pre-open stage** below (session strip · board semantics · chips · data authority).

| Chip (paint) | Kind | Power | Effect |
|--------------|------|-------|--------|
| **why** | option | — | signal why · conf · quality · ΔIEV missing caution · rejects |
| **auction+** | option | — | book pressure · imbalance · spread · gap source · intensity (true name) |
| **plan** | option | — | entry range · stop% · ATR · capital band |
| **warn** | option | — | notation UMA/SUSP · risk annotate · regime · filter rejects |

- Nav: click · Tab · Enter/Space only (no letter soup · **no fake keycaps**).  
- Options never open an independent stage.  
- Enter inspect is **present-only** — never re-runs screen / never invents Action.

### Broker list (Ctrl+P) — **no chip bar · N/A**

Honesty lives in **title + meta + footer**, not cryptic chips. List *is* the stage.

| Surface | Title | Meta / footer honesty |
|---------|-------|------------------------|
| Tracked radar (`v b`) | `View · broker list` | `{n} desks · tracked · Enter home` |
| Columns | (table) | `Code · Type · AsOf · DayNet · **Net3 · Net5 · Net7 · Net10 · Net20** · Stk · Δ1 · # · Top` — same Net ladder as stock desks |
| Thin Net windows | (same title) | append **`· thin NetX (partial sessions)`** when any desk lacks full Net3/5/… sample · row values may show `*(used/X)` |

Stock-scoped desks from ticker **`[b] brokers`** are **not** this list — they are an **on-ticker job surface** (see §3 · brokers).

**Reject:** operator chips named `partial_net` / `from_ticker` (code keys as chrome).  
**Reject:** status chips that look like filters but do not change the table.

### Broker home (desk) · **in-stage chip navigation · mandatory**

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
| **`[t] buy/sell`** | job | **`t`** | latest session dual heat · **job surface** |
| **`[f] flow`** | job | **`f`** | this desk day-net series · **job surface** |
| **`[c] calendar`** | job | **`c`** | ~1 month desk calendar · **job surface** |
| **`[h] history`** | job | **`h`** | per-ticker daily for desk · **job surface** |
| **`[m] top 5`** | job | **`m`** | multi-window top-5 matrix · **job surface** |

- **Same rule as View ticker:** chip bar stays; jobs swap body under the bar; no independent stage per chip.  
- Same chip bar model + **keycap-in-chip** (brass `[k]`); no “Hub” word in UI.  
- `v` → view ticker for desk top (1s #1) — not a chip · drill-in; `esc` returns to desk home.  
- Ticker `f` ≠ broker `f` (different **stages** — both valid; keycaps still show `[f]`).  
- Nav: click · Tab · Enter/Space · **`t f c h m`**.

### Stages without chip bar (in-stage chip nav N/A)

Accum (source badge only) · Broker list (honesty in meta) · Plan · Paper · Health · Palette.

---

## Ticker stage (content lock)

**Chip bar rules:** §1–2 · **in-stage chip navigation** (reference).  
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
**In-stage chip navigation (mandatory):** all five jobs (**brokers · flow · foreign · dist · fin**) are **job surfaces** under View ticker — same chip bar · `is-on` · `esc` → show · chips switch jobs.  
Brokers = stock desks radar **body** · **not** an independent `ticker-desks` stage.

### Shared shell (all five on-ticker jobs)

```text
View · ticker · BBCA · {job}          {job} · local cache
# job front — no [d] detail (show-only density)
# fin job front only — [y] period; still no [d]
[ [b] brokers ][ [f] flow ][ [o] foreign ][ [x] dist ][ [n] fin* ][ [y] quarterly ]

┌─ HERO (elevated · peach left accent) ──────────────────┐
│  LAB (uppercase job story)                              │
│  BIG primary fact (signed net / latest / slogan)        │
│  sub: window · source · honesty                         │
└─────────────────────────────────────────────────────────┘
┌ pulse ┐ ┌ pulse ┐ ┌ pulse ┐ ┌ pulse ┐   (3–4 scalars)
SECTION · table or dual heat
footer: esc show · chips switch · CLI verb · browse only  (no d)
```

| Layer | Spec |
|-------|------|
| Chip bar | Jobs + fin **`[y]`** when armed · **no `[d] detail`** while any job is front · density returns on show |
| Hero | One story · mint/coral for signed values |
| Pulses | Metric cards (`oc-metrics` / `oc-metric`) — not essays |
| Body | Table or dual column · density/magnitude bars only as scalar sugar **with mandatory %** (Scalar bar contract) |
| Empty | Honest empty + fetch hint in hero sub or body |
| Loading | **Quiet in-place load** (chip is-on · hold show/prior · meta may say loading · **no plain-text dump**) · never unmask accum board |
| Reject | Flat monospaced dump as product UI · interim “Loading job…” essay · charts · Action invent |

### `flow` · `view ticker flow`

| Block | Content |
|-------|---------|
| Hero lab | `FOREIGN FLOW · 10d` |
| Hero big | Window total foreign net (signed) |
| Hero sub | `last N sessions · broker_summaries · as of DATE` |
| Pulses | Buy days · Sell days · Consec buy · Latest net |
| Body head | `SESSIONS · N · of max \|net\| in window · NEWEST FIRST` |
| Body cols | `Date · bar · of-max% · Net · Ratio · Top buyer · Top seller` |
| Sugar | **of-max** bar **with** clear `%` label (Scalar bar contract) — not optional orphan track |
| Ratio | Foreign flow ratio on that session (**separate** from of-max bar %) |

```text
SESSIONS · 5 · of max |net| in window · NEWEST FIRST
Date        bar       %      Net     Ratio  Buyer  Seller
07-29       ▓▓▓▓░░░░  42%   −27.8B    5.0%  YP     AK
07-28       ▓▓▓▓▓▓░░  78%   −62.1B   12.1%  CC     AK
07-25       ▓▓░░░░░░  22%   +12.4B    3.2%  YP     XL
```

**Reject:** solid glyph / track without `%` · using Ratio as the bar fill label.

### `foreign` · `view ticker foreign-history`

| Block | Content |
|-------|---------|
| Hero lab | `FOREIGN HISTORY` |
| Hero big | Latest day foreign net (signed) |
| Hero sub | `source={stockbit\|idx} · last N days · foreign net only` |
| Pulses | 5d net · 20d net (from series) · # days · source |
| Body head | `DAILY POINTS · N · of max \|net\| in window · NEWEST FIRST` |
| Body cols | `Date · bar · of-max% · Source · Net · Lot · Avg` |
| Sugar | **of-max** bar **with** clear `%` label (same contract as flow) |

```text
DAILY POINTS · 30 · of max |net| in window · NEWEST FIRST
Date        bar       %   Source     Net      Lot     Avg
2026-07-31  ▓▓▓▓▓▓▓▓ 100% stockbit  +8.32B  47,613  1,735
2026-07-30  ▓▓▓▓░░░░  42% stockbit  +3.50B  20,502  1,707
2026-07-23  ▓▓▓▓▓▓░░  83% stockbit  −6.89B −40,664  1,696
```

**Not the same job as flow:** summaries + top desks vs point series.  
**Reject:** bar-only solid blocks (mystery magnitude).

### `dist` · `view ticker distribution`

| Block | Content |
|-------|---------|
| Hero lab | `DISTRIBUTION · TICKER` |
| Hero big / slogan | Only if true: `★ Foreign buying from domestic` or `● Foreign dominate buys` — else omit slogan |
| Hero sub | `as of DATE · counterparty · local cache` |
| Type tags | **`F` = Foreign · `L` = Local** — never `A` (Asing) · pill badges |
| Pulses | Buy sides · Sell sides · Top buy desk · Top sell desk |
| Body | **Dual heat** (mint left / coral right) · rank · code · type pill · amount · CP rows with **share** bar + **%** |

```text
TOP BUYERS (from →)                 TOP SELLERS (to →)
1 YP [F]              128.4B        1 CC [L]               41.0B
  ← XL [L]  40.1B 31% ████          → YP [F]  18.2B 44% ████
  ← CC [L]  22.0B 17% ██            → AK [F]  10.1B 25% ██
```

Cap top 5 sides · top 4 counterparties.  
**Share bar** = % of that side’s amount · **% label required** (this is the canonical Scalar bar contract example).

### `fin` · `view ticker financials`

| Block | Content |
|-------|---------|
| Hero lab | `FINANCIALS` |
| Hero big | Latest income period label (e.g. `Q1 2026` or `FY 2025`) |
| Hero sub | **`quarter`** or **`annual`** (active grain once) · `source=yahoo · local cache` |
| Body | **Three cards** (always show; honest empty per kind): |
| Period grain | Binary toggle **`y`** · see below |

| Card | Default metrics (compact rows) |
|------|--------------------------------|
| Income | Revenue · NI · EPS |
| Balance | Assets · Equity · Debt |
| Cashflow | Op CF · FCF · CapEx |

No full spreadsheet. Expand-to-wide columns is optional later — **not** the show brief/detail dual.

#### Period grain (binary toggle · locked)

| Item | Spec |
|------|------|
| Modes | **quarterly** (default) ↔ **annual** — exactly two |
| Power | **`y`** · job-local to fin · keycap always matches |
| Chip paint | Flip label: **`[y] quarterly`** / **`[y] annual`** · `is-on` when annual |
| Placement | **Fin sub-chip only:** on ticker chip bar **only while `[n] fin` is `is-on`** (between fin and density). **Hidden** on show / other jobs — **not** permanently dimmed on the bar |
| Binding | **`y` bound only while fin front**; keycap absent when chip hidden |
| CLI | `view ticker financials … --period quarterly\|annual` (parity) |
| Hero | Sub line reflects active grain once — not a second control strip of both words |
| Reject | permanent dim `[y]` next to all jobs · `q` quarterly · `p` period · universal `t` · `(Quarterly/Annually)` · fake keycap |

**Authority:** `[y]` lives in **fin job context**, not stage-global chrome.

### `brokers` · stock desks radar (**on-ticker job · same shell as flow/…**)

Not a 3-row mini top table. Chip **brokers** / `b` opens radar **under the ticker chip bar** (same job contract as flow/foreign/dist/fin):

| Piece | Spec |
|-------|------|
| Title | `View · ticker · TICKER · brokers` (job title · chip shell) |
| Hero | `STOCK DESKS · TICKER` · **N desks** only |
| Hero sub | **Empty** when data present — no `tops_scope_note` / “Tracked brokers…” / Net window essay |
| Pulses | Desks · Foreign · Buy · As of (scalars only) |
| Body | Radar: `Code · Type · Role · DayNet · **Net3 · Net5 · Net7 · Net10 · Net20** · Stk · Δ1` |
| Type | **Foreign** / **Local** (words; not cryptic A) |
| Role | `buy` / `sell` from top-brokers ranking |
| NetX | Stock-scoped multi-session · all five windows · partial marked on row (`*`) not in hero |
| Keys | `↑↓` select · **Enter** desk home · **esc** ticker show · **chips switch job** |
| Reject | Independent `ticker-desks` stage · hero noise essays · Net5-only table |

### TUI implement order (after design accept)

1. Shared job shell (hero + pulses + body slot) under persistent chip bar  
2. **In-stage chip navigation** for every multi-chip stage (no chip → independent stage)  
3. **flow** · **foreign** · **dist** · **fin** · **brokers** as job surfaces  
4. Broker desk home chips same contract  
5. Keep loaders / use cases; presentation only in adapters  

---

## Pre-open stage (locked · 2026-08-01)

**Related:** [`tui-preopen-board.html`](./tui-preopen-board.html) · CLI `saham screen pre-open` · ADR-048 · multi-surface `screen-preopen`.  
**Mission:** Morning auction scan from **honest** IEV/NCP data + (when available) TradeSetup Action — **not** a thin clone of Accum Judge and **not** letter-grade theater.

### Data plane vs chrome (authority)

| Layer | Owner | Notes |
|-------|--------|------|
| **TradeSetup Action** | Signal + Risk compose (CLI full path) | Only production Action label for pre-open candidates |
| **NCP lock / phase** | Capture window + provider | `NCP_LOCKED` vs discovery-only · never paint intensity as “NCP” |
| **Locked ΔIEV** | Final IEV − earliest NCP baseline | Honest `—` if missing · never fabricate |
| **Risk annotate** | RiskEngine (non-blocking) | ↑ / ↓ / ~ · not local clear/watch/block heuristics as authority |
| **Board paint** | Adapter | Maps real fields; **must not invent** tops, Action, or ΔIEV |
| **TUI snapshot path** | Intentional delta | Local IEV snapshot + present-only inspect; may be discovery-only — **session strip must say so** |

**Reject:** Binding **NCP** column to `iev_intensity`.  
**Reject:** Copying intensity into **ΔIEV**.  
**Reject:** Local A/B/C **Grd** as if it were TradeSetup.  
**Reject:** Silent live browser auction stream under “local snapshot” chrome.

### Session strip (always on board · above table)

Four-cell strip (OpenCode dense stats) — **session honesty**, not row metrics:

| Cell | Content |
|------|---------|
| **Source** | `LIVE` · `SNAPSHOT` · `EMPTY` · `OUTSIDE WINDOW` · `UNAVAILABLE` |
| **Phase** | `NCP_LOCKED` · `discovery-only` (+ short reason if discovery) |
| **Funnel** | scanned · candidates · **ENTER / WATCH** counts (Action counts, not A/B/C) |
| **Clock / window** | Auction clock or “window closed · snapshot as of …” · WIB when known |

Optional second line (focus strip under table or under selection):

| Focus fields | Spec |
|--------------|------|
| Provenance | NCP verified · provider · snapshot ref |
| Imbalance | bid/offer or bid_pressure when book present · honest `—` if `fast` / no book |
| Gap | prior close vs IEP · gap source `IEP` \| `BEST_BID` |
| Notation | UMA / SUSP / NO-TRADE if present |

### Board columns (locked)

```text
Tkr · Act · IEP · Δ% · IEV · NCP · ΔIEV · Risk
```

| Col | Meaning | Empty honesty |
|-----|---------|---------------|
| **Tkr** | Ticker | — |
| **Act** | TradeSetup **Action** (`ENTER` / `WATCH` / …) when workflow path provides it | `—` or omit row from Action funnel if discovery-only and no Action authority |
| **IEP** | Indicative equilibrium price | `—` if missing |
| **Δ%** | Gap vs prior close (prefer IEP gap) | `—` |
| **IEV** | Indicative equilibrium volume (K/M) | required for mover rows |
| **NCP** | **Lock flag / short phase** (`LOCK` · `disc` · `—`) — **not** intensity float | never `0.92` intensity |
| **ΔIEV** | **Locked** final − baseline (signed K/M or %) | `—` if baseline missing · never invent |
| **Risk** | RiskEngine annotate (`↑` `↓` `~`) and/or notation flag | `—` if none |

**Dropped from board chrome:** letter **Grd A/B/C** (was theater; conf/quality live under inspect **why**).  
**Not board columns (inspect / strip):** imbalance, spread, entry/stop, Dir/Conf/Sig, full plan — depth only.

```text
Screen · pre-open · SNAPSHOT · discovery-only
[ Source SNAPSHOT ][ Phase discovery-only ][ 312 · 23 · E3/W7 ][ as of 08:57 WIB ]

Tkr   Act    IEP     Δ%     IEV    NCP   ΔIEV    Risk
BBRI  ENTER  4,820  +1.8  12.4M   LOCK  +2.1M     ~
ADRO  WATCH  2,680  +3.1  22.3M   LOCK  +4.5M     ↑
UNVR  —      2,410  −1.1   3.8M   disc   —        —
```

### Inspect (Enter · present-only)

| Zone | Spec |
|------|------|
| Hero | **Act** badge · Risk · IEP big · Δ% |
| Levels kv | IEV · NCP lock · locked ΔIEV · gap source · session source |
| Chips | **`why` · `auction+` · `plan` · `warn`** (label-only · no power letters) |

| Chip | Content (real fields only) |
|------|----------------------------|
| **why** | Dir · conf · auction quality · Sig score · factor notes · `delta_iev_missing` caution · filter rejects |
| **auction+** | bid/offer imbalance or pressure · spread% · best bid/offer lots · gap source · **iev_intensity** (named intensity, not “NCP”) · broker backing tag/score/streak when cached |
| **plan** | entry range low/high · stop% · ATR · capital band |
| **warn** | ticker_notation · risk annotate detail · regime RISK_OFF · ≤4 snapshot warnings |

**Keys:** `↑↓` board · `Enter` inspect · `esc` board · `p` plan (geometry) · `v` ticker · never same stage as Accum Judge.

### CLI / TUI multi-surface

| Surface | Path | Must show |
|---------|------|-----------|
| **CLI full** | `PreOpenWorkflowUseCase` | Action · Dir · Conf/Q · Sig · Gap · plan · RSI · Risk · source authority |
| **TUI board** | Snapshot loader (intentional thin) | Session strip honesty · board columns with **correct** NCP/ΔIEV semantics · Act when available |
| **TUI inspect** | Present-only from board row | Chips above · no re-screen on Enter |

When TUI cannot run full workflow: **Phase = discovery-only** (or SNAPSHOT) on strip · **Act = —** · still show IEP/IEV from snapshot · never fake ENTER.

### Implementer order (pre-open)

1. Fix NCP / ΔIEV bindings + session strip (honesty first)  
2. Act column when workflow/snapshot can carry Action; else honest `—`  
3. Inspect chips `why` / `auction+` / `plan` / `warn` field map  
4. Optional imbalance when not `fast_mode`  
5. Visual parity with mock strip + board  

---

## Authority

| Path | Keys | Must not |
|------|------|----------|
| **Action** | Accum board `Enter` → Judge · `p` Plan · `l` Paper | Ticker/broker invent Action |
| **Browse** | `v t` · `v b` · broker Enter home · **in-stage** chip jobs | ENTER/WATCH/AVOID authority · **chip → independent stage** |
| **Paper** | Confirm after geometry | Auto-write · corpus · orders |
| **Pre-open** | Enter → auction inspect (present-only) | Same stage as accum Judge · **fake Action / fake NCP lock** · re-screen on Enter |

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

### Pre-open (board + inspect)
- **Session strip:** Source · Phase (NCP_LOCKED / discovery-only) · funnel ENTER/WATCH · clock/window  
- **Board:** `Tkr · Act · IEP · Δ% · IEV · NCP · ΔIEV · Risk`  
- **NCP** = lock/phase flag · **ΔIEV** = locked baseline delta · never intensity  
- **Act** = TradeSetup Action when authoritative · else `—`  
- **Inspect:** Action hero · chips **why · auction+ · plan · warn** (no power letters)  
- **Reject:** Grd A/B/C as authority · silent live stream · re-score on Enter  

### Ticker (`v t` · multi-surface with `view ticker *`)
- **Show density:** brief (default) / detail (`d`) — same dual as Judge · **show body only**  
- Freshness: Price · Flow · Bandar · Earn · Fund · Analyst · Own · IEV · Insider — **no `Sent`**  
- Chip bar jobs: **`[b] brokers` · `[f] flow` · `[o] foreign` · `[x] dist` · `[n] fin`**  
- **`[d] detail`:** painted **only on show** · **hidden on every job surface** (not dim) · `d` unbound while job front  
- Fin sub-chip: **`[y] quarterly|annual`** **only while fin is selected** (hidden otherwise — not dim)  
- Power: **`b f o x n`** · **`y` only with fin front** · **`d` only on show** · **`p` plan** · `esc` trail  
- Keycap honesty: **`[k]` only when bound and painted** · never decorative · never dim fake presence  
- Price mast: last · local close · chg **baseline-aligned**  
- **Job desks:** shared hero · pulses · body (§3) — not monospaced dump  
  - brokers → stock desks list · flow / foreign / dist / fin → on-ticker job desk  
  - fin period grain: binary toggle `y` · fin-context sub-chip · flip label · CLI `--period`  
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
- **Fake keycaps** (`[k]` with no binding)  
- Universal **`[t]`** for all binary toggles · **`[t](A/B)`** parentheses dual walls  
- **`q`** for quarterly · **`p`** for period grain (plan owns `p`)  
- Density rewritten as `[t](Detail/Brief)`  
- **Period `[y]` always on the bar** (even dim) when fin is not selected — **fin sub-chip only**  
- **Plain-text “Loading {job}…” dump** as interim body on chip / job activate  
- Unmasking accum board under chip click  
- Pre-open **NCP** column as intensity float · **ΔIEV** as intensity copy  
- Pre-open letter **Grd** as TradeSetup stand-in  
- Pre-open inventing **ENTER** without NCP authority / workflow Action  
- Pre-open inspect re-running screen on Enter  

---

## Related (pre-open)

- Vision board: [`tui-preopen-board.html`](./tui-preopen-board.html)  
- ADR-048 pre-open signal evidence · multi-surface `screen-preopen`  
- CLI: `saham screen pre-open` · `saham fetch iev` · `saham today` (realized vs IEP)  

---

## Related

- ADR: [`ADR-051`](../adr/ADR-051-tui-opencode-cockpit-clean-break.md)  
- Journey: [`tui-journey-hub.html`](./tui-journey-hub.html)  
- Code (later): `src/adapters/tui/` shared ChipBar · stage desks · presenters  
