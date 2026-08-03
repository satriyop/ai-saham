# Goal Instruction — Implement `get_ticker_insider_activity` (closed read tool)

**Status:** `READY FOR AGENT`
**Audience:** Implementation agent (any coding agent in this repo)
**Product term:** **AI Research Cockpit** (`/`)

**Binding architecture:**

| Doc | Role |
|---|---|
| [ADR-061](../../docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md) | **Binding** — closed read-tool registry authorization (routine `side_effect=NONE` addition; no new ADR) |
| Coverage matrix | [`docs/roadmap/ai_research_cockpit_tool_coverage.md`](../../docs/roadmap/ai_research_cockpit_tool_coverage.md) (row 7) |
| Reference tools | `agent_ticker_dashboard_tool.py`, `agent_broker_desk_tool.py` (copy their shape) |

**Do not invent product behavior.** If a contract detail is unspecified, choose the
**safer, smaller** option and document it.

## 0. Mission

Expose **recent insider activity for a ticker** as one closed OUR read tool, over
the **existing local** insider data. `side_effect=NONE`, no confirm, cache-only.
Closes coverage matrix **row 7** (a projection gap — data already local).

Hard rules:

- `side_effect=NONE`, `approval=NONE`; cache-only; no fetch/scrape/write.
- Wrap **existing** read paths: `insider_cache` via `InsiderActivityProvider` /
  `InsiderTransaction` (already read through `ticker_dashboard_source`).
- Bounded output: hard caps on rows returned and result bytes.
- `UNAVAILABLE` when no cached insider data — never fabricate.
- Results are context only; deterministic Action authority untouched.
- Offered on all stages (flat registry). Offline agent suite green.

## 1. Layer plan

```md
- Domain: not touched (InsiderTransaction VO exists)
- Application: AgentToolName.GET_TICKER_INSIDER_ACTIVITY; result DTO
  (schema agent_tool.ticker_insider.v1); TickerInsiderActivityTool over the
  existing insider read path
- Infrastructure: composition wiring (register when tools_enabled + insider source/DB present)
- Adapter: none beyond existing tool-trace rendering
```

Read first: `src/domain/value_objects/insider_transaction.py`,
`src/domain/ports/insider_activity_provider.py`,
`src/application/ports/ticker_dashboard_source.py` (insider read),
`src/application/services/agent_ticker_dashboard_tool.py` (tool pattern),
`insider_cache` schema in `data/market.db`.

## 2. Slices

1. **Contract:** `AgentToolName.GET_TICKER_INSIDER_ACTIVITY`; frozen result DTO
   (`agent_tool.ticker_insider.v1`): recent transactions — `name`, `action_type`
   (buy/sell), `shares`, `price`, `transaction_date`; plus a bounded summary
   (net buy/sell shares over window, count). `as_of` + provenance.
2. **Tool:** `TickerInsiderActivityTool` — args `ticker` (required), optional
   `window_days` (hard cap, e.g. ≤ 90), `limit` (hard cap, e.g. ≤ 20). Read-only.
3. **Register:** in composition when `tools_enabled` + insider source/DB present.
4. **Tests (offline `pytest.mark.agent`):** happy path; caps enforced; missing
   data → `UNAVAILABLE`; result byte cap; frozen-result validation; flag gating.
5. **Docs:** flip coverage-matrix row 7 → 🟢 with tool+field citation; journey
   changelog row.

## 3. Acceptance

- [ ] Returns recent insider transactions + bounded summary for a ticker.
- [ ] Caps enforced; missing data → `UNAVAILABLE` (no fabrication).
- [ ] `side_effect=NONE`, no confirm; cache-only; no fetch/write.
- [ ] Offline agent suite + golden UX pilot green; Ruff green.
- [ ] Coverage row 7 → 🟢; completion record filled.

## 4. Non-goals

- New insider **provider** or fetch (data is already cached locally).
- External/network or elevated access; model-invented tools; any write.

## 5. Completion record (fill when done)

- Authorizing ADR: ADR-061 (routine closed read tool)
- Implemented date:
- Commits:
- Coverage row flipped: 7
