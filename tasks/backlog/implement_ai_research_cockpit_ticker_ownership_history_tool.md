# Goal Instruction — Deepen ownership: `get_ticker_ownership_history` (float trend)

**Status:** `READY FOR AGENT`
**Audience:** Implementation agent · **Product term:** AI Research Cockpit (`/`)
**Menu:** A (deepens the shipped `get_ticker_ownership`) · Depth policy 2026-08-04.

**Binding architecture:**

| Doc | Role |
|---|---|
| [ADR-061](../../docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md) | Closed read tool; descriptive, read-only |
| Depth policy + READY gate | [`ai_research_cockpit_tool_coverage.md`](../../docs/roadmap/ai_research_cockpit_tool_coverage.md) |
| Deepens | shipped `get_ticker_ownership` (single latest composition) |

## 0. Mission

Float tightening **over time** is the real ownership signal, not a single snapshot.
Build it as a **shared use case** (CLI/TUI/agent adapters). This is the deferred
"ownership trend" now unblocked by the depth policy — a **new port method + SQLite
read** is in scope.

## 1. Verified data facts (signature trace)

- Table `shareholding_composition` is keyed **`UNIQUE(ticker, fetched_date)`**, NOT
  `report_date`. Tickers have multiple rows, but some are **re-fetches of the same
  report period** (e.g. AADI: 4 rows, 2 distinct `report_date`). ~647 rows / 308
  tickers; many have ≥2 distinct report periods.
- `get_ownership` today is single-row; **no history port method exists** → add one.
- `ShareholdingComposition` VO fields: `report_date`, `institution_pct`,
  `individual_pct`, `top_holder_name`, `top_holder_pct`, `total_shares`, `fetched_at`.

**⚠️ Dedupe rule (correctness):** the history read MUST collapse to **one row per
`report_date`** (latest `fetched_date` wins), then order by `report_date`.
Otherwise re-fetches appear as fake duplicate periods.

## 2. Layer plan

```md
- Domain: not touched (ShareholdingComposition VO exists)
- Application: get_ownership_history on the ownership source port; a
  ViewTickerOwnershipHistoryUseCase producing a DESCRIPTIVE period series +
  period-over-period deltas — SHARED by CLI/TUI/agent
- Infrastructure: SQLite read (dedupe latest-fetch per report_date, ORDER BY
  report_date DESC LIMIT N)
- Adapter: agent tool GET_TICKER_OWNERSHIP_HISTORY + optional CLI/TUI ownership-trend view
```

## 3. Result (facts only)

`ticker`, ordered `periods[]` (each: `report_date`, `institution_pct`,
`individual_pct`, `top_holder_name`, `top_holder_pct`, `total_shares`), and
**period-over-period deltas** where ≥2 periods exist (`institution_pct_change`,
`float_change`, `top_holder_pct_change`). No score/verdict.

## 4. Slices

1. Port + SQLite: `get_ownership_history(ticker, limit)` with the dedupe rule.
2. Use case: `ViewTickerOwnershipHistoryUseCase` — series + deltas; PIT (`≤ as_of` by report_date).
3. Agent tool: `TickerOwnershipHistoryTool` — args `ticker` (required), optional
   `limit` (cap, e.g. ≤ 8 periods). Bound bytes.
4. Register in composition when `tools_enabled` + DB present.
5. Tests: dedupe (re-fetch not a fake period); single-period → SUCCESS+INFO
   `SINGLE_PERIOD_ONLY` (no delta); multi-period deltas; missing → `UNAVAILABLE`;
   no-fetch; frozen-result; no-score.
6. Docs: coverage row 11 → add "history via `get_ticker_ownership_history`"; journey changelog.

## 5. Acceptance

- [ ] Ownership period series + deltas (when ≥2 periods) for a ticker.
- [ ] Dedupe latest-fetch per `report_date`; PIT respected.
- [ ] Shared use case usable by CLI/TUI; no score; read-only; no fetch.
- [ ] Missing → `UNAVAILABLE`; single period → SUCCESS+INFO.
- [ ] Offline agent suite + golden UX pilot green; Ruff green.

## 6. Non-goals

- Any ownership "tightness score"/verdict; writes/fetch; external/elevated.

## 7. Completion record

- Authorizing ADR: ADR-061 · Implemented date: · Commits:
