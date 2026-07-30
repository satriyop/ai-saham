# End-to-end product journey

**Status:** design contract (visual companion)  
**HTML map:** [`end-to-end-journey.html`](./end-to-end-journey.html)  
**Swing-desk design hub (elevated mocks):** [`tui-journey-hub.html`](./tui-journey-hub.html)  
**Related:** [`tui-cockpit-opencode.md`](./tui-cockpit-opencode.md) (cockpit chrome)

This document is the **whole product spine**. The TUI design hub is the visual
walkthrough of the daily swing-desk loop (Judge, Plan, boards, browse, health).

---

## Slogan

> **Screen finds and judges.**  
> Plan designs structure.  
> Assess confirms a frozen plan.  
> Trade is paper only.  
> Research is corpus only.  
> Fetch never decides.

---

## Design mock index (swing desk)

Open **[`tui-journey-hub.html`](./tui-journey-hub.html)** first.

| Step | Mock |
|------|------|
| Health / empty / lag | [`tui-session-health.html`](./tui-session-health.html) |
| Cockpit shell | [`tui-cockpit-opencode.html`](./tui-cockpit-opencode.html) |
| Accum board | [`tui-accum-board.html`](./tui-accum-board.html) |
| Judge | [`tui-judge-desk.html`](./tui-judge-desk.html) |
| Plan structure | [`tui-plan-desk.html`](./tui-plan-desk.html) |
| Paper notebook | [`tui-paper-journal.html`](./tui-paper-journal.html) |
| Ticker browse | [`tui-ticker-desk.html`](./tui-ticker-desk.html) |
| Broker browse | [`tui-broker-desk.html`](./tui-broker-desk.html) |
| Pre-open | [`tui-preopen-board.html`](./tui-preopen-board.html) |

Verify links:

```bash
python scripts/check_design_journey_links.py
```

---

## Core operator loop (swing desk)

```text
fetch status / market          →  data health
today  |  tui                  →  orient (read-only / cockpit)
screen accum --universe …      →  discover
screen accum TICKER            →  judge (Action / Why / evidence)
TUI Enter on board             →  present-only judge (j = single-ticker re-judge)
plan swing TICKER              →  structure (SL/TP/capital; inherits Action)
trade accum log …              →  optional paper notebook
view ticker | view broker      →  browse facts (not decisions)
```

Parallel (not Action authority):

```text
research accum capture/labels/evaluate
policy accum tune → review → validate → apply
```

---

## Day spine (WIB-oriented)

| When | Journey | Primary commands |
|------|---------|------------------|
| Pre-open | IEV freeze + capture | `fetch iev`, `research pre-open capture/track` |
| Open +30m | Confirm frozen plan | `assess pre-open`, optional `trade pre-open log` |
| Desk hours | Discover → judge → structure → paper | `today` / `tui`, `screen accum`, `plan swing`, `trade` |
| ~18:30 | EOD candles | `fetch market --universe lq45` |
| ~19:15–45 | Accum corpus | `research accum capture`, `labels` |

---

## Surfaces

| Job | CLI | TUI | Cron |
|-----|-----|-----|------|
| Board / refresh | `screen accum` | `s a`, `r` | via capture assess |
| Pre-open board | research / screen paths | `s p` (IEV snapshot) | capture/track |
| Judge | `screen accum TICKER` | Enter present-only | — |
| Structure | `plan swing` | `p` | — |
| Browse | `view …` | `v t` / `v b` | — |
| Corpus | `research …` | — | evening/morning |
| Policy | `policy accum …` | — | — |

CLI remains automation authority. TUI is optional cockpit (ADR-051).

---

## Authority (ADR-057 / 058)

| Kind | Affects Action? |
|------|-----------------|
| Production evidence (Signal, Risk, readiness, phase ledger sequence) | Yes when in engines / DecisionPolicy |
| Diagnostic (inspect, many `--full` panels, display MCE under policy A) | No |
| Corpus (observations, labels, evaluate) | No |
| Paper journals | No |

Phase sequence history: **`setup_phase_ledger`** (closed sessions).  
One-shot: `saham research accum backfill-phase-ledger`.

---

## Anti-patterns

- Plan as second full analysis  
- Silent fetch on open  
- Labels/corpus driving live Action  
- View as decision surface  
- Inventing board rows on empty cache  
- Broker order execution from the app  

---

## Open in browser

```bash
open docs/design/tui-journey-hub.html
open docs/design/end-to-end-journey.html
```
