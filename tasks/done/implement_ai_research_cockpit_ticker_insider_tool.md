# Goal Instruction — Implement `get_ticker_insider_activity` (closed read tool)

**Status:** `IMPLEMENTED`
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

- [x] Returns recent insider transactions + bounded summary for a ticker.
- [x] Caps enforced (`window_days` ≤ 90, `limit` ≤ 20); missing data →
  `UNAVAILABLE` (no fabrication); a genuinely quiet window with older cached
  activity is `SUCCESS`+`NO_INSIDER_ACTIVITY_IN_WINDOW` INFO, not fabricated
  absence (honesty policy — mirrors `classify_sequence`'s MISSING vs EMPTY).
- [x] `side_effect=NONE`, no confirm; cache-only; no fetch/write. Reads go
  through the **domain** `InsiderActivityProvider` port via a new narrow
  `api_client=None` composition builder — **not** the `TickerDashboardSource`
  wrapper — plus explicit `action_type="ALL"` and `as_of_date=today()` on every
  call, so the read is provably cache-only regardless of composition wiring
  elsewhere (the concrete `StockbitInsiderActivityProvider` can hit live HTTP
  when `as_of_date=None` and `api_client` is set — verified in
  `stockbit_insider.py`, avoided here by construction and by argument).
- [x] Offline agent suite (`pytest -m agent`) + full suite (`not tui` and
  `tui`) green; Ruff (`check` + `format --check`) green whole-repo.
- [x] Coverage row 7 → 🟢; completion record filled.

## 4. Non-goals

- New insider **provider** or fetch (data is already cached locally).
- External/network or elevated access; model-invented tools; any write.

## 5. Completion record (fill when done)

- Authorizing ADR: ADR-061 (routine closed read tool)
- Implemented date: 2026-08-04
- Coverage row flipped: 7
- Files:
  - `AgentToolName.GET_TICKER_INSIDER_ACTIVITY` — `src/application/dto/agent_tools.py`
  - `TickerInsiderActivityTool`, `TickerInsiderArguments`, `TickerInsiderResultData` —
    `src/application/services/agent_ticker_insider_tool.py`
  - `build_read_only_ticker_insider_source` (new, domain `InsiderActivityProvider`
    port, `api_client=None`) — `view_ticker_deps.py`; registration in `agent_model.py`
- Tests: `tests/application/services/test_agent_ticker_insider_tool.py` (happy
  path buy+sell, `action_type="ALL"`/`as_of_date` call-argument proof, limit
  truncation, empty-window-with-history INFO, never-fetched UNAVAILABLE, read
  failures on both the primary and `ever_fetched` fallback reads, argument
  parsing/validation). Updated `registered_tools` assertions in
  `tests/infrastructure/composition/test_agent_model.py` (also backfilled a gap
  left by concurrent `get_ticker_sector_context` work, which had landed without
  updating these same two exact-tuple tests).
- Verification: `pytest -m agent`, whole-repo `pytest -m "not tui"` (6338
  passed) and `pytest -m tui` (73 passed) both green; `ruff check`/`ruff format
  --check` whole-repo green (also fixed one pre-existing unrelated unused-import
  lint failure in `test_build_ticker_sector_context_use_case.py` from concurrent
  work, since whole-repo Ruff is this task's own close gate too).
- CLI/TUI adapter surface: not built this task (optional per §1 layer plan).
- Commits: (pending commit — not yet committed)
