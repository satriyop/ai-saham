# Pre-Open Runbook

**Operator source of truth** for the pre-open lane. If another doc conflicts,
prefer **this file** and live `saham … --help`.

Strategies we run today: **pre-open** (this runbook) and **accum/swing**
(separate docs). There is no third “intraday trading” product family.

Governing: [ADR-048](adr/ADR-048-pre-open-signal-evidence-and-observation-identity.md),
[ADR-049](adr/ADR-049-database-owned-learning-pipeline-clean-break.md).

---

## Two lanes

| Lane | Job | Authority write? |
|------|-----|------------------|
| **1. Signal / plan** | Discover movers; freeze NCP decision | Only `research pre-open capture` |
| **2. Learning** | Track open, label open_30m, evaluate cohorts | Tracks + labels + evaluations in SQLite |

**Beside the lanes (human, not learning truth):**

| Action | Command | Writes |
|--------|---------|--------|
| Post-open assess of frozen plan | `saham assess pre-open` | **Nothing** (stdout only) |
| Paper notebook | `saham trade pre-open log` | CSV + `trades.jsonl` only |

---

## Three artifacts (keep distinct)

| # | Artifact | What it is | What it is not |
|---|----------|------------|----------------|
| 1 | **NCP observation** | Frozen pre-open plan in `learning_observations` | Live screen; post-open price |
| 2 | **Post-open assess** | ENTER / WAIT / SKIP_* from observation + track | Learning label; broker order |
| 3 | **open_30m label** | Outcome truth for the cohort (`price_path.open_30m.v1`) | Same as assess |

```text
capture  →  (1) observation
track    →  opening samples (linked to observation)
analyze  →  (2) post-open assess   [human]
labels   →  (3) open_30m outcome
evaluate →  cohort summary over (3)
log      →  paper notebook only
```

---

## IDX clock (WIB, Mon–Fri)

| Time | What | Who |
|------|------|-----|
| 08:45–08:46 | Optional live screen (keyboard) | Human / `loop_pre_open_screen.sh` |
| 08:47, 50, 53, **56** | `saham fetch iev` multi-tick + NCP stamp | Cron |
| **08:57** | `saham research pre-open capture` (must finish before 08:58) | Cron |
| 08:58–09:00 | Matching — **not** production decision window | — |
| **09:00** | `saham research pre-open track` (samples ~09:00–09:30) | Cron |
| 09:00+ | `saham assess pre-open` then optional paper log | **Human** (no cron) |
| **09:36** | `saham research pre-open labels` | Cron |
| **09:37** | `saham research pre-open evaluate` | Cron |
| **18:30** | `saham fetch market --universe lq45` | Cron (swing/accum candles) |
| **19:15** | `saham research accum capture` | Cron (accum X) |
| **19:45** | `saham research accum labels` | Cron (accum y when horizon allows) |

Install/refresh cron: `./install_cron.sh` (replaces the tagged saham block).

---

## Commands (canonical)

### Lane 1 — signal / plan

```bash
# Live discovery only (no observation write)
saham screen pre-open --top 5

# Production decision write (NCP-locked live provider)
saham research pre-open capture
```

### Lane 2 — learning

```bash
saham research pre-open track --broker-confirm   # usually cron
saham research pre-open labels --format json
saham research pre-open evaluate --format json
saham research pre-open status
```

### Human post-open

```bash
saham assess pre-open --session YYYY-MM-DD
# or: --observation-id … [--opening-snapshot-id …]
# JSON: --format json

saham trade pre-open log \
  --observation-id OBS \
  --opening-snapshot-id SNAP

saham trade pre-open review
saham trade pre-open outcome TICKER --entry … --exit … --result target|stop|manual|breakeven
```

### Retired (do not use)

```text
trade confirm
trade pre-open log (intraday type removed)
research pre-open grade | prompt | tune
```

---

## Fail-closed rules operators must know

1. **Capture** requires live NCP window; manual JSON is discovery-only.
2. **Analyze** reads DB only — no live price fill; no mid-as-open.
3. Opening price = explicit track `opening_price` only; else assess unavailable / SKIP_INSUFFICIENT_DATA.
4. **Log** re-runs the same assess use case from exact IDs (never re-reads live).
5. **Evaluate** reads labels only — never re-derives outcomes from tracks.
6. Price-path labels are not production policy authority.

---

## Minimal daily checklist

- [ ] Cron installed (`./install_cron.sh`); host TZ Asia/Jakarta  
- [ ] Stockbit session valid (`saham fetch stockbit status`)  
- [ ] After 08:57: capture log green; print shows **observation_id** per ticker  
- [ ] After 09:00: track log green  
- [ ] **`saham research pre-open status`** → readiness lines  
  - `READY_TO_ANALYZE` = has explicit open  
  - `MISSING_OPEN` = track without `opening_price` (do not invent mid)  
  - `NO_TRACK` = re-run track  
- [ ] Human: `saham assess pre-open` (use IDs from status/capture) → optional paper log  
- [ ] After 09:37: labels + evaluate; status shows `LABELED`

---

## Related docs

| Doc | Role |
|-----|------|
| This runbook | Operator day path |
| [workflow_pre_open_learning_lifecycle.md](workflow_pre_open_learning_lifecycle.md) | Learning artifact ownership detail |
| [workflow_pre_open_session.md](workflow_pre_open_session.md) | Longer session narrative |
| [pre_open_trading_quick_reference.md](pre_open_trading_quick_reference.md) | Short command table |
| [pre_open_trading_operational_checklist.md](pre_open_trading_operational_checklist.md) | Detailed checklist |
| Live CLI help | Final name authority |

CLI truth always wins if a doc drifts.
