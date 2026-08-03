# Goal Instruction — Implement `get_ticker_foreign_flow` (foreign net trend)

**Status:** `READY FOR AGENT`
**Audience:** Implementation agent · **Product term:** AI Research Cockpit (`/`)
**Priority:** 1 of 5 (coverage row 9) — most on-thesis gap for IDX accumulation.

**Binding architecture:**

| Doc | Role |
|---|---|
| [ADR-061](../../docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md) | **Binding** — closed read-tool registry; `side_effect=NONE`, facts-only → task, no new ADR |
| Coverage matrix | [`ai_research_cockpit_tool_coverage.md`](../../docs/roadmap/ai_research_cockpit_tool_coverage.md) (row 9) + **Partial-data honesty policy** |
| Reference tools | `agent_ticker_dashboard_tool.py`, `agent_broker_desk_tool.py` |
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
- Bounded: `days` hard cap (align with the use case's 365 ceiling; default 30, cockpit cap e.g. 60), result bytes.
- `UNAVAILABLE` when no cached foreign points; PARTIAL per the honesty policy.
- Descriptive/context only; deterministic Action authority untouched. All stages.

## 1. Layer plan

```md
- Domain: not touched
- Application: AgentToolName.GET_TICKER_FOREIGN_FLOW; result DTO
  (schema agent_tool.ticker_foreign_flow.v1); TickerForeignFlowTool wrapping
  ViewTickerForeignHistoryUseCase
- Infrastructure: composition wiring (register when tools_enabled + DB present)
- Adapter: none
```

Read first: `src/application/use_case/view_ticker_foreign_history_use_case.py`
(`ViewTickerForeignHistoryRequest/Result`, `points: tuple[ForeignFlowPoint,...]`),
`src/domain/...ForeignFlowPoint`, and the `agent_ticker_dashboard_tool.py` pattern.

## 2. Result (facts only)

`ticker`, `as_of`, `days`, `resolved_source`; a bounded series or its summary:
`cumulative_net`, `net_buy_sessions` / `active_sessions`, `latest_net`,
`trend_direction` (rising/falling/flat computed from the series, descriptive), and
a capped tail of `(date, net_value)` points. No score.

## 3. Slices

1. Contract: `AgentToolName.GET_TICKER_FOREIGN_FLOW` + frozen result DTO.
2. Tool: `TickerForeignFlowTool` — args `ticker` (required), optional `days`
   (default 30, cap 60). Wrap the use case; bound the point tail + bytes.
3. Register in composition when `tools_enabled` + DB present.
4. Tests (offline `pytest.mark.agent`): happy path; `days` cap; source resolution
   surfaced; missing data → `UNAVAILABLE`; byte cap; frozen-result validation;
   no-score guard; no network.
5. Docs: flip coverage row 9 → 🟢; journey changelog row.

## 4. Acceptance

- [ ] Returns foreign net trend (cumulative/latest/direction + capped points) for a ticker.
- [ ] Wraps `ViewTickerForeignHistoryUseCase`; cache-only, no fetch.
- [ ] `days` cap + byte cap; missing → `UNAVAILABLE`; no score field.
- [ ] Offline agent suite + golden UX pilot green; Ruff green.
- [ ] Coverage row 9 → 🟢; completion record filled.

## 5. Non-goals

- Any foreign "strength/quality score"; per-broker foreign attribution (that is
  `get_ticker_broker_flow`); new provider/fetch; external/elevated; writes.

## 6. Completion record (fill when done)

- Authorizing ADR: ADR-061 · Implemented date: · Commits: · Coverage row: 9
