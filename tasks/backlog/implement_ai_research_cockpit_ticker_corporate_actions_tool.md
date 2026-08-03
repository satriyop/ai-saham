# Goal Instruction — Implement `get_ticker_corporate_actions` (closed read tool)

**Status:** `READY FOR AGENT`
**Audience:** Implementation agent (any coding agent in this repo)
**Product term:** **AI Research Cockpit** (`/`)

**Binding architecture:**

| Doc | Role |
|---|---|
| [ADR-061](../../docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md) | **Binding** — closed read-tool registry authorization (routine `side_effect=NONE` addition; no new ADR) |
| Coverage matrix | [`docs/roadmap/ai_research_cockpit_tool_coverage.md`](../../docs/roadmap/ai_research_cockpit_tool_coverage.md) (row 8) |
| Reference tools | `agent_ticker_dashboard_tool.py`, `agent_broker_desk_tool.py` (copy their shape) |

**Do not invent product behavior.** If a contract detail is unspecified, choose the
**safer, smaller** option and document it.

## 0. Mission

Expose **upcoming/recent corporate actions for a ticker** (dividend, split, RUPS,
etc.) as one closed OUR read tool, over the **existing local** corp-action data.
`side_effect=NONE`, no confirm, cache-only. Closes coverage matrix **row 8**
(a projection gap — data already local).

Hard rules:

- `side_effect=NONE`, `approval=NONE`; cache-only; no fetch/scrape/write.
- Wrap **existing** read path: `SQLiteCorporateActionCalendarRepository` /
  `CorporateActionCalendarEvent` (`corp_action_cache` / `corporate_action_events`).
- Bounded output: hard caps on events returned and result bytes.
- `UNAVAILABLE` when no cached corp-action data — never fabricate.
- Results are context only; deterministic Action authority untouched.
- Offered on all stages (flat registry). Offline agent suite green.

## 1. Layer plan

```md
- Domain: not touched (CorporateActionCalendarEvent exists)
- Application: AgentToolName.GET_TICKER_CORPORATE_ACTIONS; result DTO
  (schema agent_tool.ticker_corp_action.v1); TickerCorporateActionsTool over the
  existing corporate-action calendar repository (read-only)
- Infrastructure: composition wiring (register when tools_enabled + corp-action repo/DB present)
- Adapter: none beyond existing tool-trace rendering
```

Read first:
`src/infrastructure/persistence/sqlite_corporate_action_calendar_repository.py`,
`src/domain/value_objects/corporate_action_calendar.py`,
`src/application/ports/corporate_action_calendar_repository.py`,
`src/application/services/agent_ticker_dashboard_tool.py` (tool pattern),
`corp_action_cache` schema in `data/market.db`.

## 2. Slices

1. **Contract:** `AgentToolName.GET_TICKER_CORPORATE_ACTIONS`; frozen result DTO
   (`agent_tool.ticker_corp_action.v1`): events — `event_type`, `ex_date`,
   `cum_date`, `record_date`, `payment_date`, `announcement_date`; grouped
   upcoming vs recent relative to an `as_of`. Provenance + sync freshness.
2. **Tool:** `TickerCorporateActionsTool` — args `ticker` (required), optional
   `window_days` (hard cap), `limit` (hard cap). Read-only over the repository.
3. **Register:** in composition when `tools_enabled` + corp-action repo/DB present.
4. **Tests (offline `pytest.mark.agent`):** happy path (upcoming + recent); caps
   enforced; missing data → `UNAVAILABLE`; result byte cap; frozen-result
   validation; flag gating.
5. **Docs:** flip coverage-matrix row 8 → 🟢 with tool+field citation; journey
   changelog row.

## 3. Acceptance

- [ ] Returns upcoming/recent corporate actions for a ticker with dated milestones.
- [ ] Caps enforced; missing data → `UNAVAILABLE` (no fabrication).
- [ ] `side_effect=NONE`, no confirm; cache-only; no fetch/write.
- [ ] Offline agent suite + golden UX pilot green; Ruff green.
- [ ] Coverage row 8 → 🟢; completion record filled.

## 4. Non-goals

- New corp-action **provider** or sync/fetch (data is already cached locally;
  `sync_corporate_action_calendar_use_case` owns fetch separately).
- Corp-action **risk** interpretation (that is `assess_corporate_action_event_risk`);
  this tool only projects the calendar as context.
- External/network or elevated access; model-invented tools; any write.

## 5. Completion record (fill when done)

- Authorizing ADR: ADR-061 (routine closed read tool)
- Implemented date:
- Commits:
- Coverage row flipped: 8
