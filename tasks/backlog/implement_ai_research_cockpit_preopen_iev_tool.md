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
- `UNAVAILABLE` when no IEV snapshot for the ticker/date; PARTIAL when baseline or
  delta missing (honesty policy). Most relevant on the `preopen_screen` stage.

## 1. Layer plan

```md
- Domain: not touched
- Application: AgentToolName.GET_PREOPEN_IEV; result DTO
  (schema agent_tool.preopen_iev.v1); PreopenIevTool composing SQLiteIEVRepository reads
- Infrastructure: composition wiring (register when tools_enabled + IEV DB present)
- Adapter: none
```

Read first: `src/infrastructure/persistence/sqlite_iev_repository.py`
(`IEVSnapshot`, `get_ncp_snapshot`, `get_iev_delta`, `get_locked_iev_baseline`,
`get_snapshot`, `get_coverage`), pre-open design/ADR-048 for NCP semantics,
`agent_ticker_dashboard_tool.py` pattern.

## 2. Result (facts only)

`ticker`, `session_date`, `iev`, `iep`, `rank`, `is_ncp_locked`, `iev_delta`
(vs locked baseline), baseline value, and coverage/provenance. No directive.

**⚠️ Access pattern (verified):** `SQLiteIEVRepository` is **date-keyed, not
ticker-keyed** — `get_ncp_snapshot(snapshot_date, top_n)` returns a **list** of
`IEVSnapshot` (all tickers that date), `get_iev_delta(snapshot_date)` returns a
**dict** `{ticker: ΔIEV}`, `get_locked_iev_baseline(snapshot_date, …)` is per-date.
The tool must: resolve `session_date` (default = latest via `get_snapshot_dates()`),
call the date-keyed reads, then **extract this `ticker`** from the list/dict. If the
ticker is absent for that date → `UNAVAILABLE`. `IEVSnapshot` fields:
`date, ticker, iev, rank, iep, is_ncp_locked`.

## 3. Slices

1. Contract: `AgentToolName.GET_PREOPEN_IEV` + frozen result DTO.
2. Tool: `PreopenIevTool` — args `ticker` (required), optional `session_date`
   (default = latest via `get_snapshot_dates()`). Call the **date-keyed** reads,
   then extract `ticker` from the NCP list / delta dict / baseline (see access
   pattern above). Bound bytes.
3. Register in composition when `tools_enabled` + IEV DB present.
4. Tests (offline `pytest.mark.agent`): happy path (NCP snapshot + delta + baseline);
   PIT (no future session); missing snapshot → `UNAVAILABLE`; missing baseline/delta
   → PARTIAL; no-fetch; frozen-result validation; no-directive guard.
5. Docs: flip coverage row 12 → 🟢; journey changelog row.

## 4. Acceptance

- [ ] Returns IEV snapshot + delta vs baseline + capture label for a ticker/session.
- [ ] Cache-only via `SQLiteIEVRepository`; PIT respected; no fetch; no directive.
- [ ] Missing → `UNAVAILABLE`; partial → PARTIAL.
- [ ] Offline agent suite + golden UX pilot green; Ruff green.
- [ ] Coverage row 12 → 🟢; completion record filled.

## 5. Non-goals

- Any enter/skip directive or scenario verdict; recomputing IEV; new provider/fetch;
  external/elevated; writes.

## 6. Completion record (fill when done)

- Authorizing ADR: ADR-061 · Implemented date: · Commits: · Coverage row: 12
