# Goal Instruction — Implement `get_ticker_ownership` (float / holders)

**Status:** `READY FOR AGENT`
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
`top_holder_pct`, `total_shares`(+formatted). Optional: prior-period delta **only if**
a prior composition is cached (else omit — do not fabricate a trend). No score.

## 3. Slices

1. Contract: `AgentToolName.GET_TICKER_OWNERSHIP` + frozen result DTO.
2. Tool: `TickerOwnershipTool` — arg `ticker` (required). Read via `get_ownership`.
3. Register in composition when `tools_enabled` + DB present.
4. Tests (offline `pytest.mark.agent`): happy path; missing → `UNAVAILABLE`;
   partial fields → PARTIAL per honesty policy; no-fetch; frozen-result validation;
   no-score guard.
5. Docs: flip coverage row 11 → 🟢; journey changelog row.

## 4. Acceptance

- [ ] Returns ownership composition + top holder + totals for a ticker with `report_date`.
- [ ] Cache-only via `get_ownership`; no fetch; no score.
- [ ] Missing → `UNAVAILABLE`; partial → PARTIAL.
- [ ] Offline agent suite + golden UX pilot green; Ruff green.
- [ ] Coverage row 11 → 🟢; completion record filled.

## 5. Non-goals

- Any "float-tightness score"; fabricated ownership trend without cached history;
  new provider/fetch; external/elevated; writes.

## 6. Completion record (fill when done)

- Authorizing ADR: ADR-061 · Implemented date: · Commits: · Coverage row: 11
