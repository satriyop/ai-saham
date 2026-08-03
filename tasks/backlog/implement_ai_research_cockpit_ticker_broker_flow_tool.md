# Goal Instruction — Implement `get_ticker_broker_flow` (stock-centric broker tool)

**Status:** `READY FOR AGENT`
**Audience:** Implementation agent (any coding agent in this repo)
**Product term:** **AI Research Cockpit** (`/`)

**Binding architecture (read before coding):**

| Doc | Role |
|---|---|
| [ADR-061](../../docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md) | **Binding** — closed read-tool registry authorization (this tool is a routine `side_effect=NONE` addition, no new ADR) |
| Coverage matrix | [`docs/roadmap/ai_research_cockpit_tool_coverage.md`](../../docs/roadmap/ai_research_cockpit_tool_coverage.md) (rows 1/2/4/5-avgprice) |
| Reference tools | `agent_ticker_dashboard_tool.py`, `agent_broker_desk_tool.py` (copy their shape) |

**Do not invent product behavior.** If ADR and code conflict, stop and ask. If a
contract detail is unspecified, choose the **safer, smaller** option and document it.

## 0. Mission

Add one **OUR closed read tool** `get_ticker_broker_flow` that answers the most
frequent research family — *who is accumulating/distributing this ticker, how many
desks, how consistently* — by composing **existing** read-only paths. No new
authority, no new provider, no confirm.

Hard rules:

- `side_effect=NONE`, `approval=NONE`; cache-only; **no fetch/scrape/write**.
- Wrap existing read-only composition: `ViewTickerTopBrokersUseCase` (named
  desks) + `BandarDetectorSnapshot` (counts + multi-window consistency) when present.
- Bounded output: hard caps on `window_days` (≤ 20), `limit` (≤ 10), result bytes.
- Available on all stages (flat registry); `UNAVAILABLE` when backing data absent —
  **never** a fabricated desk list.
- Results are context only; deterministic Action authority untouched.
- Multi-commit contextual; AGENT_QUICKSTART lint gate; offline
  `pytest -m "agent and not agent-live-call"` green without network.

## 1. Preflight

```md
Layer plan:
- Domain: not touched
- Application: AgentToolName.GET_TICKER_BROKER_FLOW; result DTO
  (schema agent_tool.ticker_broker_flow.v1); TickerBrokerFlowTool composing
  ViewTickerTopBrokersUseCase + BandarDetectorSnapshot (read-only)
- Infrastructure: composition wiring (register when tools_enabled + backing use case/DB present)
- Adapter (TUI): none beyond existing tool-trace rendering
```

Read before editing:

- `src/application/use_case/view_ticker_top_brokers_use_case.py`
  (`ViewTickerTopBrokersRequest/Result`, `top_buyers/top_sellers`)
- `src/domain/value_objects/bandar_detector_snapshot.py` (counts + accdist labels)
- `src/application/services/agent_ticker_dashboard_tool.py` +
  `agent_broker_desk_tool.py` (tool + result DTO + registration pattern)
- `src/application/dto/agent_tools.py` (`AgentToolName`, `AgentToolDefinition`,
  result envelope, `create()`)
- `src/infrastructure/composition/agent_model.py` (tool registration block)

## 2. Slices

1. **Contract:** add `AgentToolName.GET_TICKER_BROKER_FLOW`; define the frozen
   result payload DTO (`schema_id = agent_tool.ticker_broker_flow.v1`): named top
   accumulating/distributing desks with net + side + **avg buy/sell price**
   (`broker_flow.avg_buy_price/avg_sell_price` — closes coverage row 5);
   `total_buyers`/`total_sellers`/`number_broker_buysell`; `broker_accdist` +
   `five_day/top1/3/5/10_accdist`; provenance `tops_source`/`tops_scope`; `as_of`.
2. **Tool:** `TickerBrokerFlowTool` — args `ticker` (required), optional
   `window_days` (cap 20), `limit` (cap 10). Compose `ViewTickerTopBrokersUseCase`
   (+ bandar snapshot when available). Cap output bytes; return `UNAVAILABLE` with a
   typed error when backing data is missing.
3. **Register:** in composition, add the tool when `tools_enabled` and its backing
   use case/DB are available (mirror `TickerDashboardTool`/`BrokerDeskTool`).
4. **Tests (offline, `pytest.mark.agent`):** happy path (named desks + counts +
   consistency labels); `window_days`/`limit` caps enforced; missing-data →
   `UNAVAILABLE` (no fabrication); result byte cap; frozen-dataclass result
   validation; registration gated by flags.
5. **Docs:** flip coverage-matrix rows 1/2/4 to 🟢 with tool+field citations; add a
   journey SSOT changelog row.

## 3. Acceptance

- [ ] `get_ticker_broker_flow` returns named accumulating **and** distributing
  desks for a ticker, with buyer/seller counts and multi-window consistency labels.
- [ ] Caps enforced (`window_days` ≤ 20, `limit` ≤ 10, result bytes).
- [ ] Missing backing data → `UNAVAILABLE`, never a fabricated desk list.
- [ ] `side_effect=NONE`, no confirm; cache-only; no fetch/scrape/write.
- [ ] Offered on all stages; deterministic Action authority untouched.
- [ ] Offline agent suite + golden UX pilot green; Ruff green.
- [ ] Coverage matrix rows 1/2/4 → 🟢 (row 5 avg-price too); completion record filled.

## 4. Verification

```bash
.venv/bin/python -m pytest -m "agent and not agent-live-call" -q
.venv/bin/python -m pytest tests/adapters/tui/test_agent_stage_ux_golden.py -q
.venv/bin/python -m pytest tests/architecture/test_layer_boundaries.py -q
ruff check src/ tests/
ruff format --check src/ tests/
```

## 5. Non-goals

- Insider (row 7) and corporate action (row 8) — their data is also local but they
  are **separate sibling tasks** under ADR-061, not part of this one.
- Per-broker average price / monthly aggregation (revisit if asked).
- External/network or elevated access; model-invented tools.
- Any write/fetch/refresh.

## 6. Completion record (fill when done)

- Authorizing ADR: ADR-061 (routine closed read tool; no dedicated ADR)
- Implemented date:
- Commits:
- Coverage rows flipped: 1, 2, 4
