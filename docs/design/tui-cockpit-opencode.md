# Daily Cockpit TUI — OpenCode visual standard

**Status:** design mock + ADR-051 cockpit implemented (Phases 0–5)  
**Mock:** [`tui-cockpit-opencode.html`](./tui-cockpit-opencode.html)  
**Swing-desk design hub (full journey):** [`tui-journey-hub.html`](./tui-journey-hub.html)  
**Ticker desk vision (Harga Mast):** [`tui-ticker-desk.html`](./tui-ticker-desk.html)  
**Broker desk vision (Radar / Net Mast):** [`tui-broker-desk.html`](./tui-broker-desk.html)  
**Judge / Plan / Board:** [`tui-judge-desk.html`](./tui-judge-desk.html) · [`tui-plan-desk.html`](./tui-plan-desk.html) · [`tui-accum-board.html`](./tui-accum-board.html)  
**ADR:** [`ADR-051`](../adr/ADR-051-tui-opencode-cockpit-clean-break.md)  
**Reference:** OpenCode command palette + full stage + right context rail  
**Whole product spine (not TUI-only):** [`end-to-end-journey.html`](./end-to-end-journey.html)

### View · ticker desk (Harga Mast)

Frame **5** in the cockpit mock is no longer a dull inspect card stack.
Target experience for `v t` / `view ticker show`:

| Principle | Choice |
|-----------|--------|
| Signature | Monumental **last price** (the landscape) |
| Language | Night ink + brass + mint/coral semantics — not Rich box-drawing |
| Hierarchy | Hero → metric ribbon → flow/structure/bandar pulse → expandable depth |
| Authority | Cache dashboard only · **not** Action / Judge |
| Data | Same `GetTickerDashboardUseCase` as CLI; presentation only changes |

Full-bleed design thesis + compare “reject CLI dump vs adopt desk”: open `tui-ticker-desk.html`.

### View · broker desk (Desk Radar / Net Mast)

Sibling instrument to ticker desk (same night-ink family). Target for `v b` + desk hub:

| Surface | Signature | Job |
|---------|-----------|-----|
| **List** | Desk **Radar** — Net5 amplitude bars (center = 0) | Scout tracked desks by \|Net5\| |
| **Show** | **Net Mast** — monumental day net | One desk home (parallel to harga mast) |
| **Hub** | t top / f flow / h history / v ticker | Deep without leaving the instrument |
| **Trail** | v → Ticker Desk (Harga Mast) | Stock ↔ desk navigation |

Not CLI Rich tables pasted into the stage. Ranking/policy stay in use cases; amplitude is presentation of Net5 only.

Open `tui-broker-desk.html` (keys 1–4 for frames).

---

## Product locks (encoded in mock)

| Decision | Choice |
|----------|--------|
| Role | Daily **cockpit**, not IDE |
| Layout | **B** — full main display + thin right sidebar |
| Navigation | **No scenario tabs** — `Ctrl+P` palette is the nav |
| Enter | **View** ticker / inspect surface |
| Plan | **Deliberate** (`p` or palette) — never bound to Enter |
| Pre-open vs accum | Equal citizens in Suggested |
| Lab | Present in palette, not chrome |
| Online | Explicit only (`Fetch market data`) · local-first default |

---

## Visual language (from OpenCode)

### Chrome
- Near-black stage (`#0b0b0b`), not blue-gray IDE chrome
- Hairline borders (`#1c1c1c`), almost no card stacks
- Thin right **Context** rail — session, today counts, focus, keys
- Bottom status strip: mode · focus · `ctrl+p commands`

### Palette (signature)
- Centered floating dialog, elevated surface (`#1a1a1a`)
- Title row: `Commands` + `esc`
- Search field with dim icon
- Sections in muted purple labels (`Suggested`, `Daily`, `Lab`, `Data`, `Session`)
- **Peach selection bar** (`#c9a68a`) with dark text — the OpenCode tell
- Shortcuts right-aligned, muted
- Foot: `↑↓` `↵` `esc` · “no tabs · palette is the nav”

### Type
- **IBM Plex Mono** for all UI (terminal density, still readable)
- 12.5–13px body, 11px labels
- Tabular nums for scores / RSI / vol

### Color discipline
- One accent for selection (peach)
- Semantic badges only: pass / watch / block
- Purple section labels (palette + cards)
- Green reserved for live / pass — never decorative

### Motion
- 100–120ms open only
- Respect `prefers-reduced-motion`

---

## Layout B (ASCII)

```
┌─────────────────────────────────────────────┬──────────────┐
│ Screen · accumulation          local-first  │ Session      │
│─────────────────────────────────────────────│ as_of · mode │
│ Candidates                                  │              │
│ BBRI  …  86  52.1  1.62×  swing  PASS       │ Today        │
│ BBCA  …  84  48.2  1.48×  swing  WATCH  ◀   │ pre-open 12  │
│ …                                           │ accum 48     │
│                                             │              │
│ ↑↓ move · Enter view · p plan · Ctrl+P      │ Keys         │
├─────────────────────────────────────────────┤ ctrl+p …     │
│ Cockpit · screen accum · BBCA · ctrl+p …    │              │
└─────────────────────────────────────────────┴──────────────┘

              ┌─ Commands ──────────── esc ─┐
              │ ⌕ Search commands…           │
              │ Suggested                    │
              │ ▌Screen accumulation    s a  │  ← peach bar
              │  Screen pre-open        s p  │
              │  Plan swing             p    │
              │ Daily / Lab / Data …         │
              │ ↑↓  ↵  esc · no tabs         │
              └──────────────────────────────┘
```

---

## Interaction map

| Key | List | Detail | Palette |
|-----|------|--------|---------|
| `Ctrl+P` | open palette | open palette | toggle |
| `↑` `↓` / `j` `k` | move row | — | move cmd |
| `Enter` | **view** | — | run cmd |
| `p` | plan swing (deliberate) | — | — |
| `Esc` | — | back to list | close |
| `Ctrl+B` | toggle sidebar | same | — |

---

## What this is *not*

- Not multi-panel IDE with file tree
- Not tab strip for Pre-open / Accum / Lab
- Not “Enter plans the trade”
- Not online-by-default

---

## Design frames (in mock)

Switch with top-left strip or keys `1`–`6`:

| # | Frame | What it proves |
|---|--------|----------------|
| 1 | **Accum** | Default daily board · spacious rows · Enter=view |
| 2 | **Pre-open** | Dense IEP board · auction strip · focus evidence · short window |
| 3 | **Plan confirm** | Deliberate modal · same OpenCode surface language as palette · Enter confirms only *here* |
| 4 | **Empty cache** | Local-first honesty · no invented rows · Fetch explicit |
| 5 | **Ticker view** | Inspect surface after Enter |
| 6 | **Palette** | Ctrl+P nav · peach selection · no tabs |

### Pre-open density rules
- Tighter row padding and more numeric columns (IEP, Δ%, IEV, NCP, ΔIEV, grade)
- Auction strip above the board (session / universe / pass-watch-block / clock)
- Evidence strip follows selection — not a second page
- Grade badges A/B/C use restrained color, not rainbow chrome

### Plan confirm rules
- Same elevated dialog family as Commands (not a browser `alert`)
- Facts block: ticker, profile, setup, as_of, source, horizon
- Amber note: no broker order · audit artifact only
- Foot: `↵` confirm · `esc` cancel · primary peach button
- **Cannot open** from empty cache

### Empty cache rules
- Quiet icon, one sentence problem, one primary action (Fetch)
- Secondary: open palette
- Sidebar shows `Cache empty` and dashes for today counts
- Status: `no data · empty`
- Copy explains *why* (no silent network), not apology

---

## Implementation note (later)

When building: Textual (or similar) should match **density and selection language** first; exact hex is secondary. Palette component is the quality bar — if the palette feels clunky, the whole TUI fails the OpenCode standard. Plan confirm must reuse the palette shell so deliberate actions feel like the same product.
