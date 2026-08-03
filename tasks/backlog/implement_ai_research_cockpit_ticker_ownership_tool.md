# Goal Instruction — Implement `get_ticker_ownership` (float / holders)

**Status:** `IMPLEMENTED`
**Audience:** Implementation agent · **Product term:** AI Research Cockpit (`/`)
**Priority:** 3 of 5 (coverage row 11).

**Binding architecture:**

| Doc | Role |
|---|---|
| [ADR-061](../../docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md) | **Binding** — closed read tool; `side_effect=NONE`, facts-only → task, no new ADR |
| Coverage matrix | [`ai_research_cockpit_tool_coverage.md`](../../docs/roadmap/ai_research_cockpit_tool_coverage.md) (row 11) + honesty policy |
| Reuse | `shareholding_composition` table + `ShareholdingComposition` VO; `TickerDashboardSource.get_ownership` |

## 0. Mission

Expose a ticker's **ownership composition / float** (institution vs individual,
largest holder, total shares) so the model can reason about float tightening — a
direct accumulation signal. Closes coverage **row 11**.

Hard rules:

- `side_effect=NONE`, `approval=NONE`; cache-only; no fetch/write.
- Project the **existing** `ShareholdingComposition` (via
  `TickerDashboardSource.get_ownership`, cache-only). Do not fetch.
- **Facts, not a score:** raw percentages + named top holder + totals; no
  "float-tightness score."
- `UNAVAILABLE` when no cached composition; report `report_date` provenance.
- Descriptive/context only. All stages.

## 1. Layer plan

```md
- Domain: not touched (ShareholdingComposition VO exists)
- Application: AgentToolName.GET_TICKER_OWNERSHIP; result DTO
  (schema agent_tool.ticker_ownership.v1); TickerOwnershipTool over the cache-only
  ownership reader
- Infrastructure: composition wiring (register when tools_enabled + DB present)
- Adapter: none
```

Read first: `src/domain/value_objects/shareholding_composition.py`
(`institution_pct`, `individual_pct`, `top_holder_name`, `top_holder_pct`,
`total_shares`, `report_date`), `src/application/ports/ticker_dashboard_source.py`
(`get_ownership`), `agent_ticker_dashboard_tool.py` pattern.

## 2. Result (facts only)

`ticker`, `report_date`, `institution_pct`, `individual_pct`, `top_holder_name`,
`top_holder_pct`, `total_shares`(+formatted). **Single (latest) composition only** —
`get_ownership` returns one row (`LIMIT 1`) and no port exposes a prior row, so there
is **no prior-period delta** in this tool (see Non-goals). No score.

## 3. Slices

1. Contract: `AgentToolName.GET_TICKER_OWNERSHIP` + frozen result DTO.
2. Tool: `TickerOwnershipTool` — arg `ticker` (required). Read via `get_ownership`.
3. Register in composition when `tools_enabled` + DB present.
4. Tests (offline `pytest.mark.agent`): happy path; missing → `UNAVAILABLE`;
   partial fields → PARTIAL per honesty policy; no-fetch; frozen-result validation;
   no-score guard.
5. Docs: flip coverage row 11 → 🟢; journey changelog row.

## 4. Acceptance

- [x] Returns ownership composition + top holder + totals for a ticker with `report_date`.
- [x] Cache-only via `get_ownership`; no fetch; no score.
- [x] Missing → `UNAVAILABLE`; partial → PARTIAL.
- [x] Offline agent suite green; Ruff green.
- [x] Coverage row 11 → 🟢; completion record filled.

## 5. Non-goals

- Any "float-tightness score".
- **Ownership trend / prior-period delta** — `get_ownership` is single-row (`LIMIT 1`)
  and no port returns a prior composition. Do **not** extend the port or improvise a
  history query here. If ownership-over-time is wanted, it is a **separate follow-up
  task** that adds a `get_ownership_history` port method + SQLite impl (Application +
  Infrastructure), out of scope for this projection tool.
- New provider/fetch; external/elevated; writes.

## 6. Completion record

- Authorizing ADR: ADR-061 (routine closed read tool; no dedicated ADR)
- Implemented date: 2026-08-04
- Code: `src/application/services/agent_ticker_ownership_tool.py`,
  `AgentToolName.GET_TICKER_OWNERSHIP`,
  `build_read_only_ticker_ownership_source` in `view_ticker_deps.py`,
  registration in `agent_model.py`
- Tests: `tests/application/services/test_agent_ticker_ownership_tool.py`;
  updated `registered_tools` assertions in
  `tests/infrastructure/composition/test_agent_model.py`
- Coverage row: 11
- Commits: (pending commit — not yet committed)
