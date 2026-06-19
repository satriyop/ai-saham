# Claude's Response to DeepSeek CLI Reorganization Recommendation

**Date:** 2026-06-18  
**Source reviewed:** `docs/deepseek_recommendation_command_organization_180626.md`  
**Method:** Full codebase read — actual file contents, SQLite row counts, import graphs, line counts, live journal files, active shell scripts — not just docs.

---

## Current Implementation Status

This document is Claude's review of the DeepSeek recommendation plus an
implementation ledger. Some sections below describe historical concerns or
future design options; the current accepted implementation is:

- Lifecycle top-level groups are implemented: `today`, `fetch`, `screen`,
  `learn`, `view`, `indicator`, `analyze`, `strategy`, `trade`.
- `saham indicator` remains top-level by design.
- `saham view broker ...` remains a documented depth exception.
- `saham trade log intraday` and `saham trade log swing` remain separate.
- `saham trade review intraday` and `saham trade review swing` remain separate.
- `saham trade backtest-swing` and `saham trade backtest-intraday` remain
  separate; no `trade simulate` merge was adopted.
- `saham fetch stockbit browse`, `saham fetch stockbit fetch-top5`, and
  `saham fetch universe inspect` remain public.
- IEV and sentiment remain SQLite-backed; no Phase 1.5 migration to JSON-only
  session files was adopted.
- Rich display has been implemented for the main CLI output surfaces covered in
  the implementation phase.
- `saham trade confirm` now reports per-ticker opening-price resolution progress
  and unresolved reasons.

Current phase status:

| Phase | Status |
|-------|--------|
| Phase 0 — design decisions | Complete |
| Phase 1 — lifecycle groups | Complete |
| Phase 2 — rename/remove legacy paths | Complete for runtime contract |
| Phase 3 — Rich display | Implemented for current target surfaces |
| Interactive wizards | Deferred |
| Unified `trades.jsonl` journal | Deferred |
| Docs sync | In progress |

---

## Executive Summary

DeepSeek's conceptual framework is **correct and worth adopting**. The lifecycle-based grouping (`fetch / screen / analyze / learn / trade / strategy`) is the right mental model. The problems it identifies are real.

However, the implementation plan contains one genuinely dangerous proposal (Phase 1.5: SQLite → file migration), one structural contradiction (`view` violates its own max-2-levels rule), two command merges that are wrong rather than premature (backtests differ at the use-case level; journals have incompatible schemas), and several claims stated as facts that code inspection shows differently.

---

## Where I Agree

### 1. The Five-Group Mental Model Is Correct

```
fetch → screen → analyze → learn → trade
```

This maps to the actual user workflow and resolves the confusion between `analyze` (passive inspection) and `trade swing analyze` (actionable). **Strong agree.**

### 2. `saham today` — High-Value Addition

A read-only orchestrator that shows regime + top movers + next action is the highest UX gain in the entire proposal. No architecture risk (purely additive). Should be Phase 1, done first.

### 3. Remove Duplicate `confirm-*` Aliases

**Verified:** `confirm-log`/`log`, `confirm-review`/`review`, `confirm-outcome`/`outcome` are all registered with dual decorators in `screen_commands.py:1315`, `1388`, `1431`. These are dead weight. Remove the `confirm-*` prefixes — the `intraday` parent group already provides context.

### 4. `saham learn` for Opening Loop

Moving `trade opening` to `learn` is semantically correct. Opening session's purpose is improving prediction accuracy, not executing trades.

**Verified:** The `data/opening/YYYYMMDD/` file tree is already live. `data/opening/20260617/` exists with `snapshot.json`, `track_*.json`, `grade.json`, `grade.md`, `prompt.md`, `tune.json`, `tune.md`. The `learn` data model is already implemented — the rename is surfacing what is already there.

**Correction to DeepSeek's data model diagram:** The document shows `data/opening/YYYY-MM-DD/`. The actual directory format is `data/opening/YYYYMMDD/` (no hyphens). Any implementation must match this existing convention.

**Watch out:** The `--phase` flag is premature. Only `opening` exists today. `saham learn snapshot --phase opening` is more verbose than `saham opening snapshot` with zero benefit until a second phase ships. Introduce `--phase` only when `mid` or `close` phases are actually implemented.

### 5. `saham screen` as a Top-Level Group

**Clarified (not just agreed):** DeepSeek says "`saham screen` is dead — old docs mention it, CLI returns error." This needs correction. The **code** is fully alive:
- `screen_commands.py` — 2,132 lines
- `accumulation_commands.py` — 2,154 lines

What is dead is the **top-level `screen_app` group registration**. There is no `screen_app` imported or wired in `main.py`. The individual commands (`pre-open`, etc.) run fine under `trade intraday`. The move is correct; the "dead" framing is not.

### 6. `saham view` for Raw Broker Browsing

Separating raw data display from data fetch and from analysis is a correct design cut. The current `data broker flow` mixes retrieval and display under the same verb. **Agree — with a structural caveat below.**

### 7. Hide `save-session` Deprecated Command

**Verified:** `screen_commands.py:2121` registers `save-session` and it appears in `--help`. Set `hidden=True`. Zero risk, immediate polish.

### 8. `saham trade` Flattened

The current `trade > swing > *` and `trade > intraday > *` nesting forces 4-level paths. Flattening is correct. **Disagree with the log merge — see below.**

---

## Where I Disagree or Have Verified Concerns

### ❌ Phase 1.5: SQLite → File Migration for IEV and Sentiment — Do Not Do This

**Verified database state:**

| Table | Rows | Notes |
|-------|------|-------|
| `iev_snapshots` | 142 | Canonical per-day IEV ranking |
| `iev_snapshot_history` | 120 | Per-run audit trail |
| `sentiment_logs` | 23 | Live sentiment records |
| `sentiment_audits` | 0 | Empty |

`SQLiteIEVRepository` exposes five cross-session query methods that the file-based design cannot replicate without loading all JSON files and filtering in Python:

| Method | What it does |
|--------|-------------|
| `get_iev_delta()` | Delta between two snapshot timestamps |
| `get_ncp_snapshot()` | NCP-locked rows filtered by criteria |
| `get_coverage()` | Date-range coverage stats |
| `get_snapshot_dates()` | All dates with data |
| `has_snapshot()` | Idempotency guard |

DeepSeek's claim that "cross-session file tree makes lookback analysis trivially possible" is wrong in this direction. `SELECT * FROM iev_snapshots WHERE date BETWEEN x AND y` is trivially possible. Scanning `data/iev/*/iev.json` and filtering in Python is not — it is slower, not atomic, and loses the multi-run-per-day audit trail that `iev_snapshot_history` provides.

**The `data/opening/` file pattern works because each session is one bounded observation.** IEV has multiple runs per day (fetch at 08:57, re-fetch if missed). SQLite is the right shape for that.

**Sentiment:** `domain/ports/sentiment_repository.py` exists and is a domain port. Moving sentiment to files would move infrastructure decisions out of the infrastructure layer and break the hexagonal architecture the project explicitly requires.

**Verdict:** Keep IEV and sentiment in SQLite. Drop Phase 1.5 entirely.

---

### ❌ `trade simulate` Merging Swing + Intraday Backtests — These Are Different Domain Objects

**Verified:** These are separate use cases with incompatible designs:

| | Swing Backtest | Intraday Backtest |
|--|---------------|-------------------|
| Use case class | `SwingBacktestUseCase` | `IntradayBacktestUseCase` |
| Core dependency | `AccumulationScreenUseCase` | `ConfirmIntradayOpenUseCase` |
| Holding period | Multi-day | Same day only |
| Exit logic | Target/stop over N days | `candle.low` vs `candle.high` same session |
| IEV handling | Not used (no historical IEV) | IEV intentionally omitted in backtest proxy |
| Portfolio model | Walk-forward multi-position | Single-session per-ticker |

There is also a third backtest: `BacktestUseCase` used by `strategy backtest` (YAML rules testing). Three different use cases, three different computations. Merging them into `trade simulate` with a `--mode` flag would be more confusing than the current structure.

**Verdict:** Keep them named distinctly. Under the flattened `trade` group: `trade backtest-swing`, `trade backtest-intraday`. Or keep them in `strategy` and `trade` respectively as they are. Do not merge.

---

### ❌ `trade log` Merging Swing + Intraday Journals — Schemas Are Incompatible

**Verified:** Three active journal files exist with data:

| File | Last written | Schema columns |
|------|-------------|---------------|
| `journals/accumulation.csv` | Jun 13 | 25 cols: `logged_at, ticker, window_days, score, streak, flow_pct, vwap_disc_pct, bb_pctile, rsi, trend, pattern, preset, classification, failed_gates, regime, planned_entry, planned_stop, planned_target, max_hold_days, actual_close_5d/10d/20d, max/min_close_in_horizon` |
| `journals/intraday-confirmations.csv` | Jun 17 | 19 cols: `confirmed_at, ticker, decision, reason_codes, opening_price, planned_entry, stop_loss_price, stop_pct, iev, trend, rsi, gap_pct, accum_tag, fvwap_discount_pct, actual_entry_price, actual_exit_price, outcome_result, outcome_r, outcome_notes` |
| `journals/pre-open.csv` | Jun 17 | Pre-open sidecar format (different again) |

These are not schema variants of the same concept. Swing journals track multi-day accumulation patterns with forward-return columns. Intraday journals track same-day confirmation decisions with immediate P&L. Merging them would require a superset schema with many nullable columns — a worse UX than two separate commands.

**Verdict:** Keep `trade log` as two distinct subcommands: `trade log swing` and `trade log intraday`. Or keep them separate. Do not merge into one `trade log` command.

---

### ⚠️ `saham view` Violates Its Own "Max 2 Levels" Rule

The document states: *"Predictable depth — Never >2 levels."*

Then proposes:
```
saham view broker flow BBRI    ← 3 levels
saham view broker top BBRI     ← 3 levels
saham view broker history BBRI ← 3 levels
```

This is a structural contradiction within the same document. Two options:

- **Option A (consistent):** Drop the `broker` sub-group: `saham view flow BBRI`, `saham view top BBRI`, `saham view history BBRI`
- **Option B (pragmatic):** Accept the `broker` sub-group and document the exception explicitly

This needs a decision before implementation. Silently breaking the stated principle will cause the same confusion the reorganization is meant to fix.

---

### ⚠️ `saham indicator` → `saham strategy indicator` Buries a Top-Use Command

`indicator` is used standalone for ad-hoc exploration throughout actual usage:

```
saham indicator compute BBCA rsi --periods 14
saham indicator snapshot BBCA
```

Moving to `saham strategy indicator compute BBCA rsi` adds 15 characters to the most common exploratory operation and implies it is only for strategy authoring. The `indicator` group is not strategy-specific.

**Verdict:** Keep `indicator` at top level. If `strategy` needs to reference indicators, add a cross-reference in help text rather than moving the group.

---

### ⚠️ "Clean Breaks — No Deprecation Period" — Confirmed Callers Will Break

**Verified callers of old CLI paths:**

**`loop_intraday.sh`** (active, runs during market hours) calls:
- `trade intraday collect-iev --top-n 50 --no-headless`
- `trade intraday pre-open --top 5 --no-headless` (called 3–4 times per session in a loop)
- `trade intraday pre-open-log`

This script is not a curiosity — it is the automation layer for the morning intraday workflow. Breaking it silently in a "clean break" commit means the next market morning the workflow produces no output.

**Docs with hardcoded CLI paths** (will need updates in the same commit):
- `docs/data_sources.md` — ~30 references to `saham data`, `saham trade intraday pre-open`, `saham analyze sentiment`
- `docs/how_to_swing_trading.md` — ~20 references to `saham trade swing analyze`, `saham data update`, `saham analyze regime`
- `docs/gemini_recommendation/*.md` — references to `saham screen`, `saham trade swing`
- `plugins/indicators/relative_strength.py` — references `saham fetch` in docstring (already uses new name — may be ahead of the refactor)
- `tests/adapters/cli/test_compute_command.py:117` — asserts `"saham data update BBCA --days 365"` in output

**Verdict:** The "clean break" principle is right for the final state. But the required pre-work is: update `loop_intraday.sh`, update all docs, update test assertion strings — all in the same commit as the rename. Otherwise the first market morning after the commit breaks silently.

---

## Summary Scorecard

| Recommendation | Verdict | Verified Risk |
|---------------|---------|--------------|
| `saham today` orchestrator | ✅ Strong agree | None |
| Five-group conceptual model | ✅ Strong agree | None |
| `saham learn` for opening loop | ✅ Agree | Drop `--phase` until second phase ships; fix dir format in DeepSeek doc (YYYYMMDD not YYYY-MM-DD) |
| `saham screen` group | ✅ Agree | "Dead code" language is wrong — code is alive, only group registration is missing |
| Remove `confirm-*` aliases | ✅ Agree | None |
| Hide `save-session` | ✅ Agree | None |
| `saham view` for broker browsing | ✅ Agree | Must resolve 3-level depth contradiction before implementing |
| Rename `data` → `fetch` | ✅ Agree | `loop_intraday.sh` and docs must update in same commit |
| Flatten `saham trade` | ✅ Agree | Keep log and backtest commands separate — see below |
| Phase 1.5: IEV → file migration | ❌ Disagree | Destroys 5 cross-session query methods; 142 rows of existing history |
| Phase 1.5: sentiment → file migration | ❌ Disagree | Breaks domain port; architecture regression |
| `trade simulate` merging both backtests | ❌ Disagree | `SwingBacktestUseCase` and `IntradayBacktestUseCase` are different domain objects with different dependencies |
| `trade log` merging swing + intraday | ❌ Disagree | 25-col vs 19-col schemas are incompatible; both journals have live data |
| `indicator` → `strategy indicator` | ⚠️ Disagree | Buries top-use ad-hoc exploration command unnecessarily |
| "Clean breaks, no deprecation" | ⚠️ Conditional | `loop_intraday.sh` (3 confirmed calls), 50+ doc references, 1 test assertion must all update in the same commit |

---

## What Would Make the DeepSeek Recommendation Fully Valid

Four categories of work are needed. None require abandoning the conceptual framework — they fix the parts where the proposal doesn't match the actual codebase.

---

### Category 1 — Correct Two Factual Errors in the Doc (no code changes)

**1a. Fix the directory format claim**
The doc says `data/opening/YYYY-MM-DD/`. The actual format on disk is `data/opening/YYYYMMDD/` (no hyphens, verified: `data/opening/20260617/`). Any implementation using hyphens creates a parallel directory tree alongside existing session data — a silent split.

**1b. Fix the "saham screen is dead" claim**
The doc implies `screen_commands.py` is dead code. It is 2,132 lines of live logic. What is dead is only the top-level group registration in `main.py`. The correct framing: "the `screen` group is not wired — commands need to be re-routed, not rewritten."

---

### Category 2 — Drop or Redesign Phase 1.5 (the SQLite migration)

This is the blocking issue. The current proposal deletes `iev_snapshots`, `iev_snapshot_history`, `sentiment_logs`, and `sentiment_audits` and replaces them with JSON files.

**Why it fails:** Four IEV query methods are called from live command handlers and from `IntradayBacktestUseCase`:

| Call site | Method used |
|-----------|------------|
| `screen_commands.py:1931` | `get_coverage()` |
| `screen_commands.py:2076` | `get_iev_delta()` |
| `screen_commands.py:2111` | `get_coverage()` |
| `opening_commands.py:125` | `get_ncp_snapshot()` |
| `intraday_backtest.py:513–514` | `has_snapshot()`, `get_ncp_snapshot()` |
| `intraday_backtest.py:696` | `get_snapshot_dates()` |

The last one is the hard blocker: `IntradayBacktestUseCase` calls `get_snapshot_dates()` to iterate over all historical IEV dates for walk-forward replay. This cannot work with per-day JSON files without loading every file and sorting in Python — no atomicity, no efficient range queries.

**Two valid paths:**

**Option A — Drop Phase 1.5 entirely.** Keep IEV and sentiment in SQLite. The `data/opening/` file pattern is already the right model for the learning loop. IEV and sentiment are the right shape for a database (cross-session queries, multi-run history per day). Phase 1.5 solves a schema-migration problem that doesn't actually exist in practice.

**Option B — Dual-store model (gives DeepSeek's stated benefit without losing query capability).** `fetch iev` writes to SQLite (unchanged) AND writes a `data/iev/YYYYMMDD/iev.json` sidecar for human inspection. `IntradayBacktestUseCase` continues to use SQLite. `learn collect` can read either. No table deletions, no data migration risk, files are still inspectable and diffable.

---

### Category 3 — Design Tasks That Unlock the Two Blocked Merges

These merges can't happen until missing specifications are written. They are not blocked by code complexity.

**3a. Journal unification design — required before `trade log` can be a single command**

The two live journals have no overlap in review-time columns:

| Journal | File | Columns |
|---------|------|---------|
| Swing | `journals/accumulation.csv` | 25 cols — accumulation signals + multi-day forward returns (`actual_close_5d/10d/20d`) |
| Intraday | `journals/intraday-confirmations.csv` | 19 cols — confirmation decision + same-day P&L (`outcome_result`, `outcome_r`) |

Schema decision: **JSON Lines (`journals/trades.jsonl`)** with a `--type` flag — see *Unified Trade Journal Schema* section below.

**3b. Backtest — rename only, no interface merge needed**

`SwingBacktestUseCase` (multi-day portfolio, `AccumulationScreenUseCase` dependency) and `IntradayBacktestUseCase` (same-day OHLC proxy, `ConfirmIntradayOpenUseCase` dependency) are different domain objects. A shared `simulate` command with `--mode swing|intraday` would be more confusing than the current structure.

The actual goal is just getting them out of the deep nesting. Rename to `trade backtest-swing` and `trade backtest-intraday` under the flattened `trade` group. Same use cases, shallower paths. No interface design needed.

---

### Category 4 — Pre-Work Before Phase 2 Can Be "Clean Break"

The "no deprecation period" principle is valid, but requires one atomic preparation step. All of the following must change in the same commit as the CLI rename:

| Caller | Old path | New path |
|--------|----------|----------|
| `loop_intraday.sh` | `trade intraday collect-iev` | `fetch iev` |
| `loop_intraday.sh` | `trade intraday pre-open` (called 3–4× in loop) | `screen pre-open` |
| `loop_intraday.sh` | `trade intraday pre-open-log` | `trade log` (after schema decision) |
| `docs/data_sources.md` | ~30 `saham data …` references | `saham fetch …` |
| `docs/how_to_swing_trading.md` | ~20 `saham trade swing …` references | new paths |
| `tests/adapters/cli/test_compute_command.py:117` | asserts `"saham data update BBCA --days 365"` | `"saham fetch market BBCA --days 365"` (or whatever the new form is) |

Missing any of these in the "clean break" commit means the first market morning after deploy runs `loop_intraday.sh` against non-existent paths.

---

### Revised Phase Plan

If DeepSeek's doc incorporated all of the above, the phases become:

| Phase | Content | Prerequisite |
|-------|---------|--------------|
| **Phase 0** | Design decisions only: unified journal schema (superset vs polymorphic) + `view` depth (2 vs 3 levels) | None — no code |
| **Phase 1** | Additive: wire `today`, `screen`, `learn`, `view`, `fetch` groups alongside existing paths | None |
| **Phase 2** | Atomic rename commit: update `loop_intraday.sh` + all docs + test assertions + delete old paths | Phase 1 stable |
| **Phase 3** *(optional, replaces 1.5)* | Add JSON sidecar export to `fetch iev` and `analyze sentiment` as human-readable audit trail alongside SQLite — no table deletions | Phase 2 complete |
| **Phase 4** *(was Phase 3)* | Rich display + interactive wizards | Phase 2 stable |

The recommendation becomes fully valid with two changes: drop the SQLite table deletion from Phase 1.5 (or replace it with Option B dual-store), and add Phase 0 design decisions for journal schema and `view` depth.

---

## Recommended Implementation Order

### Phase 0 — Design Decisions ✅ Complete

Schema and structure decisions made in this document:
- Unified journal: `journals/trades.jsonl` with `--type` flag
- Pre-open screener log: delete (redundant with `learn grade`)
- `view` depth: resolved to broker sub-group (pragmatic exception to 2-level rule)
- `--phase` flag: deferred until second phase ships

---

### Phase 1 — Additive ✅ Complete

Verified from the current implementation:

| Item | Evidence |
|------|----------|
| `saham fetch` group | `src/adapters/cli/fetch_commands.py` (new) |
| `saham screen` group | `src/adapters/cli/screen_lifecycle_commands.py` (new) |
| `saham learn` group | `src/adapters/cli/learn_commands.py` (new) |
| `saham view` group | `src/adapters/cli/view_commands.py` (new) |
| `saham today` command | `src/adapters/cli/today_commands.py` + `src/application/use_case/daily_briefing.py` (new) |
| New `main.py` structure | `src/adapters/cli/main.py` (modified — wires all new groups) |
| `data_commands.py` removed | `src/adapters/cli/data_commands.py` (deleted) |

**Bonus addition not in original plan:** `src/adapters/cli/status_commands.py` — data provider health and freshness check. Aligns with `saham status` UX recommendation.

---

### Phase 2 — Rename ✅ Complete for Runtime Contract

**Done:**

| Item | Evidence |
|------|----------|
| `data` → `fetch` rename | `data_commands.py` deleted, `fetch_commands.py` wired |
| `loop_intraday.sh` updated | Modified (manual script, not canonical — see note below) |
| Crontab updated | 5 broken entries fixed: `trade intraday collect-iev` → `fetch iev`; `trade opening *` → `learn *` |
| Docs status | Recommendation docs framed with current implementation status; broader docs sync is separate |
| `trade backtest-swing` / `trade backtest-intraday` | Confirmed in `trade_commands.py:66-67` |
| `trade` group flattened | `trade confirm`, `trade outcome`, `trade size` all flat in `trade_commands.py` |
| `indicator` kept at top level | Present in `main.py` |
| New use cases | `pre_open_workflow.py`, `fetch_market_refresh.py`, `refresh_broker_data.py`, `resolve_opening_prices.py`, `data_update_status.py` (all new) |

**Runtime cleanup complete:**

| Item | Current State | Action Needed |
|------|--------------|---------------|
| `confirm-*` aliases | ✅ Already gone — `screen_commands.py` no longer uses `@intraday_app.command` decorators | — |
| `save-session` | ✅ Already gone — not present in any CLI file | — |
| `pre-open-log` / `pre-open-review` | ✅ Removed — unregistered from `trade_commands.py`, functions deleted from `screen_commands.py`, stale call removed from `loop_intraday.sh` | — |

> **Note on `loop_intraday.sh`:** This is a manual convenience script, not the canonical automated workflow. The canonical scheduler is the **crontab** (5 entries, Mon-Fri), which was also broken after Phase 2 and has now been fixed. `run_intraday_loop.py` is a separate experimental Python loop also updated (`trade intraday confirm-open` → `trade confirm`).

**Deferred by design:**

| Item | Current State | Action Needed |
|------|--------------|---------------|
| `trade log` sub-app | Keep `trade log intraday/swing` subcommands | Future task only if `trades.jsonl` schema is implemented |
| Unified trade journal | Not implemented | Deferred design option, not required for current CLI contract |

---

### Phase 3 — Rich Display ✅ Implemented for Current Target Surfaces

Implemented for the current CLI output surfaces covered by the rich-display
phase, including `today`, accumulation screening, swing analysis, broker views,
pre-open screening, `trade confirm`, and intraday review output. Interactive
wizards remain deferred.

---

## Unified Trade Journal Schema

### Storage: `journals/trades.jsonl` (JSON Lines)

One JSON object per line. Chosen over CSV because:
- Swing-specific fields would force intraday rows to carry 15 empty string fields in CSV
- Lists require delimiter hacks in CSV (`"TREND|RSI"`, `"GATE_1; GATE_2"`) — native arrays in JSON
- Every numeric field needs string-to-Decimal parsing from CSV; JSON preserves native types
- Adding a field to one trade type doesn't require migrating all rows
- Consistent with `data/opening/YYYYMMDD/*.json` project convention

**Append** = write one line, no rewrite. **Update** = read all + rewrite (same pattern as current CSV writers).

### CLI: `saham trade log --type <type>`

Single command, `--type` flag — not subcommands. Extensible: new types (options, futures) require no CLI shape changes.

```bash
saham trade log --type swing    --ticker BBCA --from-analysis
saham trade log --type intraday --ticker BBRI --from-confirm
```

The `trade_log_app` sub-typer is replaced by a single `@trade_app.command("log")`.

### Schema Fields

**Section 1 — Identity (all records)**

| Field | JSON type | Replaces |
|-------|-----------|----------|
| `trade_type` | string | NEW — `"swing"` or `"intraday"`, from `--type` flag |
| `logged_at` | string (ISO date) | `logged_at` (swing) / `confirmed_at` (intraday) |
| `ticker` | string | both |

**Section 2 — Market Context (all records)**

| Field | JSON type | Replaces | Notes |
|-------|-----------|----------|-------|
| `regime` | string | swing only | Intraday: auto-populated from `MarketRegimeUseCase` at log time |
| `trend` | string | both | `"UP"` / `"DOWN"` / `"FLAT"` |
| `rsi` | number | both | Native float |

**Section 3 — Trade Plan, Shared (all records)**

| Field | JSON type | Replaces | Notes |
|-------|-----------|----------|-------|
| `decision` | string | `classification` / `decision` | WATCH/HOLD/PASS or ENTER/WAIT/SKIP |
| `planned_entry` | number | both | — |
| `planned_stop` | number | `planned_stop` / `stop_loss_price` | Unified name |
| `planned_target` | number or null | swing only currently | — |
| `stop_pct` | number or null | intraday only | Omitted from swing records |

**Section 4 — Swing-Specific Signals (omitted from intraday records)**

| Field | JSON type | Replaces |
|-------|-----------|----------|
| `entry_price` | number | `entry_price` |
| `window_days` | integer | `window_days` |
| `accum_score` | number | `score` |
| `accum_streak` | integer | `streak` |
| `flow_pct` | number | `flow_pct` |
| `vwap_disc_pct` | number | `vwap_disc_pct` |
| `bb_pctile` | number or null | `bb_pctile` |
| `pattern` | string | `pattern` |
| `preset` | string or null | `preset` |
| `failed_gates` | array of strings | `failed_gates` (was `"GATE_1; GATE_2"`) |
| `max_hold_days` | integer | `max_hold_days` |

**Section 5 — Intraday-Specific Signals (omitted from swing records)**

| Field | JSON type | Replaces |
|-------|-----------|----------|
| `iev` | integer | `iev` |
| `gap_pct` | number | `gap_pct` |
| `accum_tag` | string | `accum_tag` |
| `fvwap_discount_pct` | number | `fvwap_discount_pct` |
| `opening_price` | number | `opening_price` |
| `reason_codes` | array of strings | `reason_codes` (was `"TREND\|RSI"`) |

**Section 6 — Outcome (all types, populated on `saham trade outcome`)**

| Field | JSON type | Notes |
|-------|-----------|-------|
| `actual_entry_price` | number or null | Both types adopt this |
| `actual_exit_price` | number or null | Both types adopt this |
| `outcome_result` | string or null | `"WIN"` / `"LOSS"` / `"SCRATCH"` / `"OPEN"` |
| `outcome_r` | number or null | R-multiple |
| `outcome_notes` | string or null | Free-form |

**Section 7 — Swing Forward-Return Analytics (omitted from intraday records)**

| Field | JSON type |
|-------|-----------|
| `actual_close_5d` | number or null |
| `actual_close_10d` | number or null |
| `actual_close_20d` | number or null |
| `max_close_in_horizon` | number or null |
| `min_close_in_horizon` | number or null |

### Example Records

**Swing:**
```json
{"trade_type": "swing", "logged_at": "2026-06-13", "ticker": "GOTO", "regime": "BEAR", "trend": "SIDE", "rsi": 37.64, "decision": "WATCH", "planned_entry": 51.0, "planned_stop": 47.0, "planned_target": 60.0, "stop_pct": null, "entry_price": 50.0, "window_days": 7, "accum_score": 68.9, "accum_streak": 3, "flow_pct": 83.23, "vwap_disc_pct": 0.0, "bb_pctile": null, "pattern": "sustained", "preset": "foreign-bounce", "failed_gates": ["RSI_OVERSOLD"], "max_hold_days": 20, "actual_entry_price": null, "actual_exit_price": null, "outcome_result": null, "outcome_r": null, "outcome_notes": null, "actual_close_5d": null, "actual_close_10d": null, "actual_close_20d": null, "max_close_in_horizon": null, "min_close_in_horizon": null}
```

**Intraday (sparse — swing sections omitted):**
```json
{"trade_type": "intraday", "logged_at": "2026-06-17", "ticker": "BBCA", "regime": "BEAR", "trend": "NEUTRAL", "rsi": 59.42, "decision": "WAIT", "planned_entry": 6400.0, "planned_stop": 6067.0, "planned_target": null, "stop_pct": 5.2, "iev": 239076, "gap_pct": 3.59, "accum_tag": "UNCONFIRMED", "fvwap_discount_pct": -14.19, "opening_price": 6400.0, "reason_codes": ["open inside entry range", "stop 5.2% within max 7.0%", "pre-open trend is not bullish"], "actual_entry_price": null, "actual_exit_price": null, "outcome_result": null, "outcome_r": null, "outcome_notes": null}
```

### Idempotency Key

```
swing:    (trade_type, logged_at, ticker, window_days)
intraday: (trade_type, logged_at, ticker)
```

Swing retains `window_days` because the same ticker can be logged twice on the same day with different window lengths. The writer branches on `trade_type`.

### Writer Pattern

```python
def _dedup_key(r: dict) -> tuple:
    if r["trade_type"] == "swing":
        return (r["trade_type"], r["logged_at"], r["ticker"], r.get("window_days"))
    return (r["trade_type"], r["logged_at"], r["ticker"])

# Append — no rewrite
def append(self, record: dict) -> bool:
    existing = self._read_all()
    if any(_dedup_key(r) == _dedup_key(record) for r in existing):
        return False
    with open(self._path, "a") as f:
        f.write(json.dumps(record) + "\n")
    return True

# Update outcome/review fields — full rewrite (same as current CSV writers)
def update(self, updated: dict) -> bool:
    records = self._read_all()
    key = _dedup_key(updated)
    matched = False
    for i, r in enumerate(records):
        if _dedup_key(r) == key:
            records[i] = updated
            matched = True
    if matched:
        self._path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return matched
```

### Migration from Existing Files

- `journals/accumulation.csv` → read with `AccumulationJournalCsvWriter.read_all()`, write to `journals/trades.jsonl` with `trade_type="swing"`, rename: `score→accum_score`, `streak→accum_streak`, `classification→decision`
- `journals/intraday-confirmations.csv` → read with `IntradayConfirmationCsvStore.read_all()`, write to `journals/trades.jsonl` with `trade_type="intraday"`, rename: `confirmed_at→logged_at`, `stop_loss_price→planned_stop`
- Old files preserved as `.bak` until verified

---

## Pre-Open Screener Log — Delete, Not Migrate

The DeepSeek recommendation proposes deleting all `src/infrastructure/persistence/csv_*.py` files. Three exist:

| File | Action |
|------|--------|
| `accumulation_journal_csv_writer.py` | Replace → `trades.jsonl` (above) |
| `intraday_confirmation_csv.py` | Replace → `trades.jsonl` (above) |
| `journal_csv_writer.py` | **Delete — redundant with `learn grade`** |

`journal_csv_writer.py` backs `journals/pre-open.csv` — the pre-open screener output log, written by `pre-open-log` and read by `pre-open-review`. It exists to track entry range hit rate and direction accuracy over time.

**Verified overlap with `learn grade`:**

| Metric | `pre-open-review` | `learn grade` |
|--------|------------------|---------------|
| Entry range hit rate | ✓ | ✓ |
| Direction accuracy 1d | ✓ | ✓ (`trend_accuracy_T5`) |
| Direction accuracy 5d | ✓ | ✓ (`trend_accuracy_T30`) |
| Clean trade rate | — | ✓ |
| Breakdown by verdict | — | ✓ |
| IEP accuracy | — | ✓ |
| Per-ticker detail | — | ✓ |
| Config snapshot for tuning | — | ✓ |

`learn grade` covers everything `pre-open-review` computes, and more. The screener log predates the learning loop and was never removed when `learn` was built.

**Decision: Delete entirely.** No JSONL replacement needed.

**What to remove:**
- `src/infrastructure/persistence/journal_csv_writer.py`
- `src/application/services/` — whichever service backs `pre-open-review`
- `pre-open-log` and `pre-open-review` CLI commands from `screen_commands.py`
- The `pre-open-log` call in `loop_intraday.sh` (line 48)
- `journals/pre-open.csv` (archive as `.bak` before deleting)

**Canonical replacement:** `saham learn snapshot → track → grade` is the complete learning loop that supersedes this.
