# Goal Instruction — Implement `get_preopen_iev` (pre-open indicative value)

**Status:** `READY FOR AGENT`
**Audience:** Implementation agent · **Product term:** AI Research Cockpit (`/`)
**Priority:** 4 of 5 (coverage row 12) — the core pre-open signal; pairs with the
`preopen_screen` cockpit stage (ADR-066).

**Binding architecture:**

| Doc | Role |
|---|---|
| [ADR-061](../../docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md) | **Binding** — closed read tool; `side_effect=NONE`, facts-only → task, no new ADR |
| Coverage matrix | [`ai_research_cockpit_tool_coverage.md`](../../docs/roadmap/ai_research_cockpit_tool_coverage.md) (row 12) + honesty policy |
| Reuse | `SQLiteIEVRepository` (`get_ncp_snapshot`, `get_iev_delta`, `get_locked_iev_baseline`, `get_snapshot`) over `iev_snapshots` |
| Domain context | Pre-open / IDX NCP semantics (ADR-048); the 08:56 NCP snapshot is highest-signal |

## 0. Mission

Expose the **pre-open indicative equilibrium value (IEV)** for a ticker/session:
latest/NCP snapshot, delta vs the locked baseline, and auction context — so the
model can reason about pre-open positioning. Closes coverage **row 12**.

Hard rules:

- `side_effect=NONE`, `approval=NONE`; cache-only over `SQLiteIEVRepository`; no fetch/write.
- **Facts, not a directive:** IEV values, deltas, NCP snapshot fields, coverage —
  raw numbers; no enter/skip instruction.
- PIT: read the snapshot for the requested session ≤ `as_of`; never future.
- Respect IDX NCP semantics — label which capture (e.g. 08:56 NCP) the reading is from.
- `UNAVAILABLE` when no IEV snapshot for the ticker/date; `iev_move_since_lock=None`
  (+INFO) when no post-lock reading (honesty policy). Most relevant on `preopen_screen`.

## 1. Layer plan

```md
- Domain: not touched
- Application: AgentToolName.GET_PREOPEN_IEV; result DTO
  (schema agent_tool.preopen_iev.v1); PreopenIevTool composing SQLiteIEVRepository reads
- Infrastructure: **one-line repo fix** — `get_ncp_snapshot` locked-batch path sets
  `is_ncp_locked=1` (F2); composition wiring (register when tools_enabled + IEV DB present)
- Adapter: none
```

Read first: `src/infrastructure/persistence/sqlite_iev_repository.py`
(`IEVSnapshot`, `get_ncp_snapshot`, `get_iev_delta`, `get_locked_iev_baseline`,
`get_snapshot`, `get_coverage`), pre-open design/ADR-048 for NCP semantics,
`agent_ticker_dashboard_tool.py` pattern.

## 2. Result (facts only)

`ticker`, `session_date`, `iev`, `iep`, `rank`, `is_ncp_locked`, `locked_baseline_iev`,
`iev_move_since_lock` (`int | None`), and coverage/provenance. No directive.

**⚠️ F1 — `iev_delta` was mislabeled; use the clean baseline (decided).**
`get_iev_delta()` is **diagnostic** (last−first over the whole session; its own
docstring: "can mix pre-NCP, locked-input, and matching-period snapshots… not
production signal evidence"). Do **NOT** expose it as `iev_delta`/"vs locked
baseline". The honest baseline-anchored value is:

- `locked_baseline_iev` = the 08:56 NCP locked value (`ncp_baseline_iev(date)[ticker]`,
  a projection over `get_ncp_snapshot`).
- `iev_move_since_lock` = `current_iev − locked_baseline_iev`, present **only when a
  distinct later reading exists** (else `None` + INFO `NO_POST_LOCK_MOVE`).
- The diagnostic `get_iev_delta` is **out of scope** for this facts tool.

**⚠️ Access pattern (verified):** `SQLiteIEVRepository` is **date-keyed, not
ticker-keyed** — `get_ncp_snapshot(snapshot_date, top_n)` → **list** of `IEVSnapshot`
(all tickers), `ncp_baseline_iev(date)` → dict `{ticker: iev}`, `get_snapshot(date)`
→ latest per ticker. Resolve `session_date` (default = latest via
`get_snapshot_dates()`), call the date-keyed reads, then **extract this `ticker`**.
Ticker absent for that date → `UNAVAILABLE`. `IEVSnapshot` fields:
`date, ticker, iev, rank, iep, is_ncp_locked`.

**⚠️ F2 — repository fix required (is_ncp_locked mislabel).** `get_ncp_snapshot`
filters `is_ncp_locked = 1` in SQL but omits the flag when building `IEVSnapshot`,
so locked rows default to `is_ncp_locked=0`. The tool's "which capture" label depends
on it. **Fix in the repository, one line, on the locked-batch path only** (set
`is_ncp_locked=1` there — the `get_snapshot()` fallback rows are NOT guaranteed
locked, do not blanket them). Shared fix (briefing/CLI benefit). Add a repo test.

**⚠️ F3 — future `session_date` (decided).** If `session_date > today`, return
`UNAVAILABLE` with `error_code=SESSION_DATE_IN_FUTURE` — **not** a turn-failing
validation error and **not** a generic "no snapshot" (distinguishes an impossible
request from a real absent past date). Non-fatal; the model can correct.

## 3. Slices

1. `fix(iev)`: `get_ncp_snapshot` locked-batch path sets `is_ncp_locked=1` (F2) +
   repo test asserting locked rows report `is_ncp_locked=1` and the fallback path
   is unchanged.
2. Contract: `AgentToolName.GET_PREOPEN_IEV` + frozen result DTO (fields per §2).
3. Tool: `PreopenIevTool` — args `ticker` (required), optional `session_date`
   (default = latest via `get_snapshot_dates()`). Resolve date, extract `ticker`
   from NCP snapshot + `ncp_baseline_iev` + latest `get_snapshot`; compute
   `iev_move_since_lock` only when a distinct later reading exists. Bound bytes.
4. Register in composition when `tools_enabled` + IEV DB present.
5. Tests (offline `pytest.mark.agent`): happy path (locked NCP snapshot with
   `is_ncp_locked=1`); `iev_move_since_lock` present vs `None`+`NO_POST_LOCK_MOVE`;
   **F3** future date → `UNAVAILABLE`+`SESSION_DATE_IN_FUTURE`; ticker absent →
   `UNAVAILABLE`; **never uses `get_iev_delta`**; no-fetch; frozen-result; no-directive.
6. Docs: flip coverage row 12 → 🟢; journey changelog row.

## 4. Acceptance

- [ ] Returns locked NCP IEV (with `is_ncp_locked=1`), `locked_baseline_iev`, and
  `iev_move_since_lock` (or `None`+INFO) for a ticker/session — **not** `get_iev_delta`.
- [ ] F2 repo fix: `get_ncp_snapshot` locked rows report `is_ncp_locked=1`; fallback unchanged.
- [ ] F3: future `session_date` → `UNAVAILABLE`+`SESSION_DATE_IN_FUTURE`.
- [ ] Cache-only via `SQLiteIEVRepository`; PIT respected; no fetch; no directive.
- [ ] Ticker absent → `UNAVAILABLE`; partial → PARTIAL.
- [ ] Offline agent suite + golden UX pilot green; Ruff green.
- [ ] Coverage row 12 → 🟢; completion record filled.

## 5. Non-goals

- Any enter/skip directive or scenario verdict; recomputing IEV; new provider/fetch;
  external/elevated; writes.
- Exposing the diagnostic `get_iev_delta` (contaminated; not baseline-anchored).

## 6. Completion record (fill when done)

- Authorizing ADR: ADR-061 · Implemented date: · Commits: · Coverage row: 12
