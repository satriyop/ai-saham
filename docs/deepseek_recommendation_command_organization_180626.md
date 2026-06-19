# CLI Command Organization — UX Recommendation

Date: 2026-06-18
Goal: Consistent, discoverable CLI for the IDX trading lifecycle.

---

## Implementation Status

This document is the original DeepSeek UX recommendation, not the final
implementation spec. The current CLI follows the lifecycle model, with a few
intentional deviations based on codebase review and later implementation work.

Current top-level command contract:

```
saham
├── today
├── fetch
├── screen
├── learn
├── view
├── indicator
├── analyze
├── strategy
└── trade
```

Implemented and aligned:

- `saham data` was replaced by `saham fetch`.
- `saham screen pre-open` and `saham screen accum` are the candidate discovery paths.
- `saham analyze swing` is the swing evaluation path.
- `saham learn snapshot/track/grade/prompt/tune` own the opening feedback loop.
- `saham view broker ...` owns read-only broker browsing.
- `saham trade confirm`, `trade log intraday/swing`, `trade review intraday/swing`,
  `trade outcome`, `trade size`, `trade backtest-swing`, and
  `trade backtest-intraday` are the paper-trade workspace paths.
- Rich display has been implemented for the main screen/analyze/trade outputs.
- `trade confirm` now reports per-ticker opening-price resolution progress and
  unresolved reasons.

Intentional deviations from this original recommendation:

- Keep `saham indicator` as a top-level group. It is an exploratory tool, not
  only a strategy-authoring subcommand.
- Do not merge swing and intraday backtests into `trade simulate`; they use
  different application use cases and assumptions.
- Do not merge swing and intraday logs into a single `trade log` command yet;
  current journal schemas remain separate.
- Keep `saham fetch stockbit browse`, `saham fetch stockbit fetch-top5`, and
  `saham fetch universe inspect` public.
- Keep IEV and sentiment persistence in SQLite; no SQLite-to-session-file
  migration was adopted.
- Accept `saham view broker ...` as a pragmatic depth exception.
- Interactive wizards remain deferred.

---

## Current Structure (7 top-level)

```
saham
├── data          fetch candles, broker, stockbit data
│   ├── update, status, broker, stockbit (login/status/spy/test/browse/fetch-top5), universe
├── indicator     technical indicator management (compute, snapshot, create, list)
├── analyze       single-indicator tools (risk, compare, sentiment, audit, regime, chart)
├── strategy      backtest strategy packages (init, validate, create, backtest)
├── trade
│   ├── swing     screen, analyze, size, backtest, audit, log, review
│   ├── intraday  pre-open, confirm-open, log, review, outcome, collect-iev, backtest
│   └── opening   snapshot, track, grade, prompt, tune
└── skill         AI documentation (generate, check, index)
```

## UX Problems Identified

| Problem | Example | Impact |
|---------|---------|--------|
| `analyze` vs `trade swing analyze` | Both have "analyze" — different scope | User doesn't know which to run |
| `saham screen` is dead | Old docs mention it, CLI returns error | Dead path breeds distrust |
| `data stockbit fetch-top5` misfiled | Opening session data under `data stockbit` | Related things not together |
| `trade intraday` vs `trade opening` overlap | Both do pre-open work | Unclear boundary |
| 4-level nesting | `saham analyze chart price BBRI` | Cognitive load |
| Inconsistent flags | `--with-regime` vs `--regime`, `--no-sentiment` vs `--sentiment false` | Hard to remember |
| Wall-of-text output | Primary signals compete with secondary data | Slow scanning |

---

## Recommended Structure

Flat hierarchy, max 2 levels, lifecycle-based grouping.

```
saham
├── today           daily briefing — regime + top movers in one pass
│
├── fetch           all data in one place
│   ├── market      --universe lq45 (was data update/status)
│   ├── broker      --ticker BBCA --days 30 (was data broker)
│   ├── universe    list, update (was data universe)
│   ├── iev         raw IEV data fetch (was trade intraday collect-iev / data stockbit fetch-top5)
│   └── stockbit    login, status, spy, test, browse (was data stockbit *)
│
├── view             read-only data browsing — no signal, no computation
│   ├── broker flow <stock>       (was data broker flow)
│   ├── broker top <stock>        (was data broker top)
│   ├── broker top-foreign <stock> (was data broker top-foreign)
│   ├── broker history <stock>    (was data broker history)
│   ├── broker mappings           (was data broker mappings)
│   └── broker status             (was data broker status)
│
├── screen           candidate discovery
│   ├── pre-open    (was trade intraday pre-open)
│   └── accum       --universe lq45 (was trade swing screen)
│
├── analyze          ticker evaluation
│   ├── risk        (as-is)
│   ├── sentiment   (as-is)
│   ├── audit       sentiment accuracy audit (was analyze audit)
│   ├── regime      (as-is)
│   ├── chart       (as-is)
│   ├── swing       (was trade swing analyze)
│   └── compare     (as-is)
│
├── learn            learning loop — improve prediction accuracy
│   ├── collect     --phase opening  (orchestrator: IEV + orderbook + running trades)
│   ├── snapshot    --phase opening
│   ├── track       --phase opening
│   ├── grade       --phase opening
│   ├── prompt      --phase opening
│   └── tune        --phase opening
│
├── trade            paper trading workspace
│   ├── confirm     (was intraday confirm-open)
│   ├── log         flags always available; interactive fallback when omitted
│   ├── outcome     flags always available; interactive fallback when omitted
│   ├── review      --horizon 5
│   ├── size        --capital 10000000 (was swing size)
│   └── simulate    walk-forward paper trading sim (was trade swing/intraday backtest)
│
└── strategy         packages + indicators + AI docs
    ├── init
    ├── validate
    ├── list          (was strategy list)
    ├── create        AI-generated from intent (was strategy create)
    ├── backtest      rules-based historical sim (was strategy backtest)
    ├── indicator     (was saham indicator)
    └── skill         (was saham skill)
```

---

## `saham today` — Daily Briefing

Composite orchestration command: one pass, read-only, no state mutation.

| Step | What | Source |
|------|------|--------|
| 1 | Data freshness check (stale → auto-fetch) | `saham fetch market --universe lq45` |
| 2 | Market regime summary (3 lines) | `saham analyze regime` |
| 3 | Top pre-open movers (top 3) | `saham screen pre-open --top 3` |
| 4 | Top swing candidates (top 3) | `saham screen accum --universe lq45 --top 3` |
| 5 | Prompt: "Next: analyze BBRI / log trade / exit" | Interactive selector |

```
saham today
```

| Pro | Con |
|-----|-----|
| One command replaces 4-5 | New orchestration use case |
| Guided starting point | Power users use individual commands |
| Teaches lifecycle: fetch→screen→analyze | — |

---

## `saham learn` — Learning Loop

The opening learning loop moves from `trade` to `learn` because its purpose is
improving prediction accuracy, not executing trades.

Future-proofed with `--phase` flag:

| Command | Today | Future |
|---------|-------|--------|
| `saham learn collect --phase opening` | Orchestrator: IEV + orderbook + running trades | `--phase mid`, `--phase close` |
| `saham learn snapshot --phase opening` | Opening pre-NCP capture | Same pattern |
| `saham learn track --phase opening` | 5-min orderbook tracking | Same pattern |
| `saham learn grade --phase opening` | Accuracy report | Same pattern |
| `saham learn prompt --phase opening` | AI tuning prompt | Same pattern |
| `saham learn tune --phase opening` | Config recommendations | Same pattern |

Without `--phase`, interactive fallback: "Learning phase? (opening / mid / close)"

**`learn collect` vs `fetch iev`:** `fetch iev` is the low-level, idempotent data
fetch — "go get IEV data now." `learn collect` is the orchestrator that gathers
everything a learning phase needs (IEV + orderbook + running trades) in one pass.
Same relationship as `saham today` orchestrating `fetch` + `screen` + `analyze`. `learn collect`
internally calls `fetch iev`, `fetch market`, etc. — the user shouldn't need to
call both.

**Design rule:** `learn` is about the feedback cycle — predict → observe → measure → tune.
It owns the data (`data/opening/`, `data/mid/`, etc.) and the AI interaction.
It does NOT execute or journal trades.

---

## `saham learn` — Data Model

All `learn` commands operate on session files, not raw SQLite. This ensures
data is inspectable, diffable, deletable, and free of schema migrations:

```
data/
├── iev/YYYY-MM-DD/
│   └── iev.json              (raw IEV data, produced by fetch iev)
├── opening/YYYYMMDD/
│   ├── snapshot.json          (NCP screener predictions)
│   ├── track_*.json           (5-min orderbook snapshots)
│   ├── grade.json             (accuracy report for tune)
│   ├── grade.md               (human-readable grade)
│   ├── prompt.md              (AI tuning prompt)
│   ├── tune.json              (config recommendations)
│   └── tune.md                (narrative recommendations)
├── sentiment/YYYY-MM-DD/
│   └── TICKER.json            (sentiment snapshot, produced by analyze sentiment)
└── ...                        (future: mid, close, etc.)
```

The `iev/` directory bridges `fetch` and `learn` — `fetch iev` writes the raw
data, `learn collect --phase opening` reads it alongside other sources.
This is the only exception to "`learn` writes its own phase directory":
IEV data is shared between `fetch`, `screen`, and `learn`.

**Cross-session learning:** The per-session file tree makes lookback analysis
trivially possible in the future: `learn tune --phase opening --lookback 30`
would scan `data/opening/*/grade.json` to detect recurring patterns.

**Phases:** `opening` today, extends to `mid`, `close`, `sentiment`, or any
future learning phase. Every phase follows the same file-per-session pattern.
No SQLite dependency from the `learn` layer.

---

## `saham trade` — Paper Trading Workspace

Honest naming: no live trade execution. All commands are journaling, sizing,
simulating, and the confirm gate.

| Command | Purpose | Flag rule |
|---------|---------|-----------|
| `confirm` | Opening price gate check | Flags always work |
| `log` | Record paper trade to journal; `--from-sidecar` imports pre-open session | Flags always work; interactive when omitted |
| `outcome` | Record actual result | Flags always work; interactive when omitted |
| `review` | Review journal hit-rate and accuracy | Flags always work |
| `size` | ATR position sizing | Flags always work |
| `simulate` | Walk-forward paper workflow sim (was swing/intraday backtest) | Flags always work |

**`trade simulate` vs `strategy backtest`:**
- `trade simulate` replays the paper trading workflow — screening, sizing, journaling — to show "what if I had traded my setups?" It is walk-forward, not a fixed-rule backtest.
- `strategy backtest` tests a strategy.yaml rules file against historical candles. It is a fixed-rule historical simulation.
- Both are valid. The naming avoids confusion: `simulate` for workflow, `backtest` for rules.

**Flag rule:** Every command that accepts flags MUST work identically whether
called by a human or a script/machine. Interactive wizard is an additive layer
that kicks in when no flags are provided — never a replacement.

---

## `saham view` — Read-Only Data Browsing

Pure display of raw broker data. No signal, no verdict, no computation.
Separated from `fetch` because the data is already loaded — you're browsing,
not importing. Separated from `analyze` because there's no interpretation.

| Command | Displays | Why not `analyze` |
|---------|----------|-------------------|
| `saham view broker flow BBRI` | Raw buy/sell flow rows | No signal, no aggregation |
| `saham view broker top BBRI` | Top broker list, sorted | Just a sorted table |
| `saham view broker history BBRI` | Historical broker activity | Time-series dump |
| `saham view broker mappings` | Broker name → code table | Configuration dump |
| `saham view broker status` | Last fetch + row count | Health check |

**Design rule:** `view` is for browsing already-fetched data. If you need to
fetch first, run `saham fetch broker --ticker BBRI --days 30` first.

---

## `saham screen` — Candidate Discovery

Two screeners, one clear purpose: find candidates before you analyze.

| Command | Filters | Output |
|---------|---------|--------|
| `saham screen pre-open` | IEV movers, IEP, gap %, liquidity | VERDICT: PRIME/WATCH/SKIP |
| `saham screen accum --universe lq45` | Foreign flow, streak, VWAP, BCI | Score 0–120 + enrichment signals |

These are the only two screeners. A dedicated `screen` group signals that
screening is a distinct lifecycle phase (discovery), separate from analysis
and trading.

---

## Principles

| Principle | Applied as |
|-----------|------------|
| Machine-first flags | Every flag command works identically for humans and scripts. Interactive wizard is additive, never replaces flags. |
| Predictable depth | Never >2 levels. `analyze swing BBRI`, not `trade swing analyze BBRI`. |
| One thing per group | `fetch` = data, `screen` = discovery, `analyze` = evaluation, `learn` = feedback, `trade` = paper execution. |
| Honest naming | `trade` is paper trading. `learn` is learning loop. No aspirational names. |
| Clean breaks | No deprecation period. Old paths are removed in one commit. No aliases that rot. |
| Progressive disclosure | `today` for beginners, individual commands for power users. |
| Session-file data model | `learn` data lives in `data/<phase>/YYYY-MM-DD/` as versioned, inspectable files. No SQLite dependency. No schema migrations. Data is bounded by session date — delete the directory, delete the session. `fetchiev` writes to `data/iev/` as shared data between `fetch`, `screen`, and `learn`. `analyze sentiment` writes to `data/sentiment/`. |

---

## Implementation Plan

### Phase 1 — Create new groups (additive, no deletions)

| Task | Files affected |
|------|---------------|
| Create `saham today` use case + CLI entry | New: `today_commands.py`, `daily_briefing.py` |
| Create `saham learn` CLI group | New: `learn_commands.py` |
| Wire `saham learn snapshot/track/grade/prompt/tune` with `--phase` | New + move from `opening_commands.py` |
| Create `saham view` CLI group | New: `view_commands.py` |
| Move `saham analyze swing` as new CLI entry (re-route existing use case) | `analyze_commands.py` |

### Phase 1.5 — Refactor to session-file data model

Align `analyze sentiment` and `fetch iev` with the file-based convention
before the move.

| Task | Files affected |
|------|---------------|
| Refactor `FetchSentimentUseCase` to write `data/sentiment/YYYY-MM-DD/TICKER.json` instead of SQLite `sentiment_logs` | `fetch_sentiment.py` |
| Refactor `AuditSentimentUseCase` → `learn grade --type sentiment` to read from session files + market data | `audit_sentiment.py`, `opening_grade.py` |
| Refactor `collect-iev` / `fetch iev` to write `data/iev/YYYY-MM-DD/iev.json` instead of SQLite `iev_snapshots` | `screen_commands.py`, `sqlite_iev_repository.py` |
| Delete SQLite tables: `sentiment_logs`, `sentiment_audits`, `iev_snapshots`, `iev_snapshot_history` | schema migration |
| Update `screen pre-open` to read IEV from `data/iev/` instead of SQLite | `pre_open_screen.py` |

### Phase 2 — Move and rename (delete old paths)

| Old path | New path | Action |
|----------|----------|--------|
| `saham trade intraday pre-open` | `saham screen pre-open` | Move use case, delete old CLI |
| `saham trade swing screen` | `saham screen accum` | Move use case, delete old CLI |
| `saham trade swing analyze` | `saham analyze swing` | Delete old CLI (Phase 1 already created new) |
| `saham trade intraday confirm-open` | `saham trade confirm` | Rename CLI entry |
| `saham trade intraday log` | `saham trade log` | Merge with swing log |
| `saham trade swing log` | `saham trade log` | Merge |
| `saham trade swing size` | `saham trade size` | Move CLI entry |
| `saham trade swing backtest` | `saham trade simulate` | Merge swing + intraday backtest |
| `saham trade intraday backtest` | `saham trade simulate` | Merge |
| `saham trade swing compare` | `saham analyze compare` | Already exists — delete old |
| `saham trade intraday pre-open-log` | `saham trade log --from-sidecar` | Merge into trade log |
| `saham trade intraday pre-open-review` | `saham trade review` | Same command — delete old CLI entry |
| `saham trade intraday save-session` | — | Delete (deprecated, already shows stub message) |
| `saham trade opening *` | `saham learn * --phase opening` | Move use cases |
| `saham data` | `saham fetch` | Rename group |
| `saham data broker import` | — | Delete (user doesn't want manual CSV import) |
| `saham indicator` | `saham strategy indicator` | Move group |
| `saham skill` | `saham strategy skill` | Move group |
| `saham strategy list` | `saham strategy list` | Keep as-is |
| `saham strategy create` | `saham strategy create` | Keep as-is |
| `saham strategy backtest` | `saham strategy backtest` | Keep as-is (rules-based, different from trade simulate) |
| `saham data stockbit fetch-top5` | `saham fetch iev` | Re-route (part of fetch iev) |
| `saham trade intraday collect-iev` | `saham fetch iev` + `saham learn collect --phase opening` | Split into raw fetch + orchestrator |
| `saham data universe list` | `saham fetch universe list` | Move CLI entry |
| `saham data universe update` | `saham fetch universe update` | Move CLI entry |
| `saham data stockbit login` | `saham fetch stockbit login` | Move CLI entry |
| `saham data stockbit status` | `saham fetch stockbit status` | Move CLI entry |
| `saham data stockbit spy` | `saham fetch stockbit spy` | Move CLI entry |
| `saham data stockbit test` | `saham fetch stockbit test` | Move CLI entry |
| `saham data stockbit browse` | `saham fetch stockbit` | Merge into default command |
| `saham data broker flow` | `saham view broker flow` | Move CLI entry |
| `saham data broker top` | `saham view broker top` | Move CLI entry |
| `saham data broker top-foreign` | `saham view broker top-foreign` | Move CLI entry |
| `saham data broker history` | `saham view broker history` | Move CLI entry |
| `saham data broker mappings` | `saham view broker mappings` | Move CLI entry |
| `saham data broker status` | `saham view broker status` | Move CLI entry |

### Phase 3 — Rich display + interactive wizards

| Task | Priority |
|------|----------|
| Integrate `rich` panels on `saham analyze swing` output | High (richest output) |
| Integrate `rich` on `saham today` output | High (first impression) |
| Add interactive fallback to `saham trade log` | Medium |
| Add interactive fallback to `saham trade outcome` | Medium |
| Phase-based `--help` grouping | Low (cosmetic) |

### `accumulation_commands.py` — Redistribution (not deletion)

The file is kept. Only the standalone `accumulation_app` typer wrapper (name="accumulation")
is stripped — it was never wired in `main.py`. The 4 live functions + `universe_app` are
imported and re-routed:

| Function | Used by | New home |
|----------|---------|----------|
| `accumulation_run` | `saham swing screen` | `saham screen accum` |
| `accumulation_audit` | `saham swing audit` | `saham analyze accum-audit` |
| `accumulation_log` | `saham swing log` | `saham trade log` (merged) |
| `accumulation_review` | `saham swing review` | `saham trade review` (merged) |
| `universe_app` | `saham data universe` | `saham fetch universe list/update` |

---

### File Deletion (same commit as Phase 2 rename)

```
src/adapters/cli/screen_commands.py              → delete (split into screen/ and trade/)
src/adapters/cli/opening_commands.py             → delete (moved to learn_commands/)
src/adapters/cli/accumulation_commands.py        → NOT deleted (4 live functions + universe_app re-used elsewhere). Strip accumulation_app typer wrapper only.
src/adapters/cli/swing_commands.py               → delete (split into analyze/ and trade/)
src/infrastructure/persistence/csv_*.py          → delete (replaced by SQLite)
```
