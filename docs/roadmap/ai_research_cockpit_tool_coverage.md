# AI Research Cockpit — Tool Coverage Matrix

**Role:** Audit whether OUR closed tools cover the **canonical accum/preopen
research questions** operators actually ask. This is the static half of the
[ADR-065](../adr/ADR-065-ai-research-cockpit-external-and-ro-data-l4.md) learning
loop: rows that are **GAP** become the backlog for new OUR tools (each via its own
ADR). The behavioral half is the runtime `TOOL_GAP` clue.

**Keep this file honest:** a question is only **Covered** when the datum both
**exists** and is **exposed** in an agent-facing result. See the three states.

## Coverage states (fix cost differs sharply)

| State | Meaning | Fix cost |
|---|---|---|
| 🟢 **Covered** | Datum exists **and** is exposed in a tool result / stage projection | none |
| 🟡 **Projection gap** | Datum exists in our data/domain but is **not** projected to the agent | cheap — widen a projection field, no new provider/tool |
| 🔴 **Capability gap** | Datum does **not** exist locally at all | expensive — new provider + new OUR tool + ADR (or `web_research` stopgap under L4 confirm) |

## Current tool catalog (carriers)

| Tool | Tier | Key result carriers |
|---|---|---|
| `get_visible_cockpit_result` | OUR / NONE | active stage projection (polymorphic, ADR-066) |
| `get_ticker_dashboard` | OUR / NONE | price/volume/fundamentals cache summary |
| `judge_accumulation_ticker` | OUR / NONE | `AgentAccumulationFacts` (`consecutive_streak`, `net_buy_ratio`, `bb_width_pctile`, `bci_label`, `bci_tier1_count`), `AgentSetupPhaseFacts` (`current_phase`, `phase_age_sessions`, `detection_strength`) |
| `get_broker_desk` | OUR / NONE | **desk→ticker** views (SHOW/TOP_STOCKS/TOP_MATRIX/FLOW/CALENDAR/HISTORY) |
| `web_research` | External / NETWORK_READ | external snippets (confirm) |
| `ro_data_query` | Elevated / LOCAL_READ_ELEVATED | 3 allowlisted shapes: ticker close, ticker volume, broker day net (confirm) |

Domain data that exists but is **not** fully exposed to the agent today:
`BandarDetectorSnapshot` (`total_buyer/total_seller`, `top1/3/5/10_accdist`,
`top1_percent`, `number_broker_buysell`, `total_volume`), and
`ViewTickerTopBrokersUseCase` (named `top_buyers`/`top_sellers` per ticker).

## Matrix — "is this ticker being accumulated or distributed?"

| # | Canonical question | Required datum | Carrier (tool · field) | State |
|---|---|---|---|---|
| 1 | **Which** desks are accumulating this ticker (named) | ticker→named brokers, buy side | *none yet* — `get_broker_desk` is desk-centric; `ViewTickerTopBrokersUseCase.top_buyers` exists but is not a tool | 🔴→ [ADR-067](../adr/ADR-067-ai-research-cockpit-ticker-broker-flow-tool.md) `get_ticker_broker_flow` |
| 2 | **How many** desks accumulating | `total_buyer` / `number_broker_buysell` | exists in `BandarDetectorSnapshot`; agent sees only `bci_tier1_count` | 🟡 projection |
| 3 | **Consistency** — streak (days), months | daily streak; multi-window smoothing; monthly agg | days ✅ `AgentAccumulationFacts.consecutive_streak`; multi-window `five_day/top-N accdist` exists unexposed; **monthly not aggregated** | 🟡 / 🔴 (months) |
| 4 | All of 1–3 for **distribution/selling** | ticker→named sellers; `Dis` labels; `total_seller` | `top_sellers` exists (no tool); `broker_accdist="Dis"`, `total_seller` unexposed | 🔴→ [ADR-067](../adr/ADR-067-ai-research-cockpit-ticker-broker-flow-tool.md) + 🟡 |
| 5 | All of 1–4 on **volume / qty / price avg** | per-ticker volume; per-broker net; per-broker avg price | volume ✅ dashboard; per-broker net ✅ `get_broker_desk`/`ro_data_query`; **per-broker avg price: verify — likely gap** | 🟡 / 🔴 (avg price) |
| 6 | Phase **compression / breakout** | setup phase; BB width percentile | ✅ `AgentSetupPhaseFacts.current_phase`; ✅ `AgentAccumulationFacts.bb_width_pctile` | 🟢 covered |
| 7 | Recent **insider activity** | insider transaction feed | no local data, no tool | 🔴 capability (needs provider; `web_research` stopgap) |
| 8 | Upcoming **corporate action** | corp-action calendar (div/split/RUPS) | only `dividend_yield` ratio; no event calendar | 🔴 capability (needs provider; `web_research` stopgap) |

**Headline:** Q1/Q2/Q4 are one missing tool — a **stock-centric** ticker→desks
view — and the data already exists (`ViewTickerTopBrokersUseCase` +
`BandarDetectorSnapshot`). See [ADR-067](../adr/ADR-067-ai-research-cockpit-ticker-broker-flow-tool.md). The orchestrator already emits this exact
`TOOL_GAP` at runtime.

## Guard test spec (regression + routing)

Two offline tests keep this matrix from silently rotting:

1. **Projection-field guard** (`tests/application/services/test_agent_tool_coverage_fields.py`):
   assert the named carrier fields above still exist on their DTOs — e.g.
   `AgentAccumulationFacts` has `consecutive_streak`, `bb_width_pctile`,
   `bci_tier1_count`; `AgentSetupPhaseFacts` has `current_phase`. A rename/removal
   fails the test, forcing this matrix to be updated in the same change.
2. **Coverage corpus routing** (`tests/.../test_agent_tool_coverage_corpus.py`):
   a checked-in list of the canonical questions with the **expected tool or
   expected GAP**. Offline, assert on registry routing / tool availability (not
   model choice). New FAQ → add a row here + in the matrix.

Behavioral capture (optional, live): run the corpus through the cockpit and collect
emitted `TOOL_GAP` clues — the runtime half of the audit.

## Maintenance rule

- New frequently-asked question → add a matrix row + a corpus row.
- A row that is 🔴 → open a follow-up ADR for the new OUR tool (or provider).
- A row that flips to 🟢 → cite the tool/field + the ADR that closed it.
- Never mark 🟢 on data that exists but is unexposed — that is 🟡 by definition.
