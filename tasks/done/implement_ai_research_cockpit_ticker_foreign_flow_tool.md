# Goal Instruction — Implement `get_ticker_foreign_flow` (foreign net trend)

**Status:** `IMPLEMENTED`
**Audience:** Implementation agent · **Product term:** AI Research Cockpit (`/`)
**Priority:** 1 of 5 (coverage row 9) — most on-thesis gap for IDX accumulation.

**Binding architecture:**

| Doc | Role |
|---|---|
| [ADR-061](../../docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md) | **Binding** — closed read-tool registry; `side_effect=NONE`, facts-only → task, no new ADR |
| Coverage matrix | [`ai_research_cockpit_tool_coverage.md`](../../docs/roadmap/ai_research_cockpit_tool_coverage.md) (row 9) + **Partial-data honesty policy** |
| Reference tools | `agent_ticker_dashboard_tool.py`, `agent_ticker_broker_flow_tool.py` |
| Reuse | `ViewTickerForeignHistoryUseCase` (cache-only), `foreign_flow_points` |

## 0. Mission

Expose the **aggregate foreign net-flow trend** for a ticker (is foreign money
coming in, and for how long) as one closed OUR read tool over the **existing**
`ViewTickerForeignHistoryUseCase`. Closes coverage **row 9**.

Hard rules:

- `side_effect=NONE`, `approval=NONE`; cache-only; no fetch/scrape/write.
- Wrap `ViewTickerForeignHistoryUseCase` (already read-only, `days` param, source
  resolution). Do not re-implement foreign aggregation.
- **Facts, not a score:** net values / cumulative net / net-buy-session count /
  trend direction as raw numbers; no "foreign strength score."
- Bounded: `days` default **30**, hard cap **60**; point tail ≤ **30**; result bytes.
- `UNAVAILABLE` when no cached foreign points; PARTIAL when window shorter than
  requested days (`FOREIGN_WINDOW_SHORT`).
- Descriptive/context only; deterministic Action authority untouched. All stages.

## 0a. Locked decisions (operator 2026-08-04)

| # | Decision |
|---|---|
| `days` | default **30**, hard max **60** |
| `trend_direction` | half-window cumulative compare → `rising` / `falling` / `flat` |
| Point tail | last **min(active, 30)** points `(date, net_value_idr)` only |
| `source` | always **auto**; surface `resolved_source` in result |
| Short window | **PARTIAL** + `FOREIGN_WINDOW_SHORT` |

## 1. Layer plan

```md
- Domain: not touched
- Application: AgentToolName.GET_TICKER_FOREIGN_FLOW; result DTO
  (schema agent_tool.ticker_foreign_flow.v1); TickerForeignFlowTool wrapping
  ViewTickerForeignHistoryUseCase
- Infrastructure: composition wiring (register when tools_enabled + DB present)
- Adapter: none
```

## 2–4. Acceptance

- [x] Returns foreign net trend (cumulative/latest/direction + capped points) for a ticker.
- [x] Wraps `ViewTickerForeignHistoryUseCase`; cache-only, no fetch.
- [x] `days` cap + byte cap; missing → `UNAVAILABLE`; no score field.
- [x] Offline agent tests green; Ruff green.
- [x] Coverage row 9 → 🟢; completion record filled.

## 5. Non-goals

- Any foreign "strength/quality score"; per-broker foreign attribution (that is
  `get_ticker_broker_flow`); new provider/fetch; external/elevated; writes.

## 6. Completion record

- Authorizing ADR: ADR-061
- Implemented date: 2026-08-04
- Code: `src/application/services/agent_ticker_foreign_flow_tool.py`,
  `build_read_only_ticker_foreign_history_use_case`, registration in `agent_model.py`
- Tests: `tests/application/services/test_agent_ticker_foreign_flow_tool.py`
- Coverage row: 9
- Commits: `292f7234`
