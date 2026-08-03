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
- **Single-session only** (both backing reads are single-day): no multi-day
  aggregation. Bounded output: hard caps on `limit` (≤ 10) and result bytes.
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
   `target_date` (default = latest summary date, mirrors
   `ViewTickerTopBrokersRequest`), optional `limit` (cap 10). Compose
   `ViewTickerTopBrokersUseCase` for the named desks + the cache-only bandar reader
   (see §2a) for counts + built-in multi-window consistency labels, loaded at the
   tops' **resolved** `session_date`. Cap
   output bytes; return `UNAVAILABLE` with a typed error when backing data is
   missing. **No multi-day aggregation** — consistency comes from the snapshot's
   `five_day/top1/3/5/10_accdist` labels, not from looping days.
3. **Register:** in composition, add the tool when `tools_enabled` and its backing
   use case/DB are available (mirror `TickerDashboardTool`/`BrokerDeskTool`).
4. **Tests (offline, `pytest.mark.agent`):** happy path (named desks + counts +
   consistency labels); default `target_date` = latest and an explicit past date;
   `limit` cap enforced; missing-data → `UNAVAILABLE` (no fabrication); result byte
   cap; frozen-dataclass result validation; registration gated by flags.
   - **bandar session alignment:** bandar is read at the tops' resolved
     `session_date` (not the raw `target_date`); a fake source asserts the date
     passed to `get_bandar` equals `tops_result.date`.
   - **no-fetch:** the tool uses the cache-only source, never
     `BandarDetectorProvider`/browser (no network in offline tests).
5. **Docs:** flip coverage-matrix rows 1/2/4 to 🟢, and row 5 to 🟢 (avg-price was
   its last open sub-part; volume/net already covered), with tool+field citations;
   add a journey SSOT changelog row.

## 2a. Bandar load path (decided)

- **Reader:** `TickerDashboardSource.get_bandar(ticker, session_date)` — **cache-only**
  (`SQLiteTickerDashboardSource`).
- **Composition:** via the `view_ticker_deps` family — reuse
  `ViewTickerTopBrokersUseCase` + a `SQLiteTickerDashboardSource`, through a thin
  factory, mirroring the other tools in `composition/agent_model.py`.
- **🚫 Do NOT use `BandarDetectorProvider` / `stockbit_bandar`** — that is the
  browser/**fetch** path and would violate `side_effect=NONE` / cache-only.
- **⚠️ session_date alignment (correctness):** call
  `get_bandar(ticker, tops_result.date)` — the **resolved** date from
  `ViewTickerTopBrokersResult.date`, **not** the raw request `target_date`
  (`None`=latest). Misalignment makes bandar counts/labels describe a different
  session than the named desks. `get_bandar` None for that date →
  PARTIAL + `BANDAR_SNAPSHOT_UNAVAILABLE`.

## 2b. Partial-data honesty (follow the shared policy)

Apply the shared [partial-data honesty policy](../../docs/roadmap/ai_research_cockpit_tool_coverage.md#partial-data-honesty-policy-all-read-tools).
Tool-specific mapping:

| Case | Status |
|---|---|
| No summary + no bandar for ticker/date | UNAVAILABLE |
| Summary present, tops genuinely empty (full-summary source) | SUCCESS + INFO `NO_NET_TOPS` |
| Only one side has net desks | SUCCESS + INFO `NO_DISTRIBUTION_SIDE` / `NO_ACCUMULATION_SIDE` |
| Named tops present, bandar snapshot missing | PARTIAL + WARN `BANDAR_SNAPSHOT_UNAVAILABLE` (null bandar fields) |
| Bandar present, no named tops | PARTIAL + WARN `NAMED_TOPS_UNAVAILABLE` (empty desk lists) |
| Tops empty only via tracked-broker fallback | PARTIAL + WARN `TOPS_FALLBACK_EMPTY` (use `tops_scope`) |

Never fabricate desks; empty stays empty; null stays null. UNAVAILABLE is last resort.

## 3. Acceptance

- [ ] `get_ticker_broker_flow` returns named accumulating **and** distributing
  desks for a ticker, with buyer/seller counts and multi-window consistency labels.
- [ ] Single-session; `target_date` defaults to latest; `limit` ≤ 10 and result
  bytes enforced. No multi-day aggregation.
- [ ] Partial-data honesty per §2b: UNAVAILABLE only with no data; empty/one-sided
  tops → SUCCESS+INFO; missing bandar or tops dimension → PARTIAL+coded WARN; no
  fabrication.
- [ ] Missing backing data → `UNAVAILABLE`, never a fabricated desk list.
- [ ] `side_effect=NONE`, no confirm; cache-only; no fetch/scrape/write.
- [ ] Offered on all stages; deterministic Action authority untouched.
- [ ] Offline agent suite + golden UX pilot green; Ruff green.
- [ ] Coverage matrix rows 1/2/4 → 🟢, and row 5 → 🟢 (avg-price closes its last
  sub-part; volume/net already covered); completion record filled.

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
- **Multi-day per-desk aggregation / streak (row 3 "how many days/months")** — this
  is the **sibling** [`get_ticker_desk_flow_history` task](implement_ai_research_cockpit_ticker_desk_flow_history_tool.md)
  (≤60-session window, facts-not-score), not part of this single-session tool.
  This tool still surfaces the single-session 5-day/top-N smoothed labels;
  `judge_accumulation_ticker.consecutive_streak` covers the daily streak.
- Per-broker average price / monthly aggregation (revisit if asked).
- External/network or elevated access; model-invented tools.
- Any write/fetch/refresh.

## 6. Completion record (fill when done)

- Authorizing ADR: ADR-061 (routine closed read tool; no dedicated ADR)
- Implemented date:
- Commits:
- Coverage rows flipped: 1, 2, 4, 5 (avg-price sub-part; volume/net already covered)
