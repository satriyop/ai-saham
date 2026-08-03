# AI Research Cockpit — Tool Coverage Matrix

**Role:** Audit whether OUR closed tools cover the **canonical accum/preopen
research questions** operators actually ask. This is the static half of the
[ADR-065](../adr/ADR-065-ai-research-cockpit-external-and-ro-data-l4.md) learning
loop: rows that are **GAP** become the backlog for new OUR tools — each an
**implement task under [ADR-061](../adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md)**
(a new ADR only if the tool needs new authority / a new `side_effect` class, as
ADR-065 did). The behavioral half is the runtime `TOOL_GAP` clue.

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
| `get_ticker_broker_flow` | OUR / NONE | **ticker→desks** single-session: `top_accumulating`/`top_distributing` (net + avg buy/sell price), `bandar.total_buyers`/`total_sellers`/`number_broker_buysell`, `broker_accdist` + `five_day`/`top1`/`top3`/`top5`/`top10_accdist`, `tops_source`/`tops_scope`, `as_of` |
| `web_research` | External / NETWORK_READ | external snippets (confirm) |
| `ro_data_query` | Elevated / LOCAL_READ_ELEVATED | 3 allowlisted shapes: ticker close, ticker volume, broker day net (confirm) |

Domain data that exists locally but is **not** exposed to the agent today (all
🟡 projection gaps — the data is in the DB / domain, just not projected):

- **`insider_cache`** table + `InsiderTransaction` VO + `InsiderActivityProvider`
  port (`name`, `action_type`, `shares`, `price`, `transaction_date`); already
  read via `ticker_dashboard_source`.
- **`corp_action_cache`** table + `SQLiteCorporateActionCalendarRepository` +
  `CorporateActionCalendarEvent` (`event_type`, `ex_date`, `cum_date`,
  `record_date`, `payment_date`, `announcement_date`).
- Multi-day per-desk persistence over a session window (row 3 remainder) —
  sibling tool task `get_ticker_desk_flow_history`.

**Correction (2026-08-03):** rows 5, 7, 8 were first mis-graded 🔴 capability gaps
by auditing only agent-facing DTOs. The underlying data is **local** — they are
🟡 projection gaps (rows 1/2/4/5 closed by `get_ticker_broker_flow`). There are
currently **no true capability gaps** in this list.

## Matrix — "is this ticker being accumulated or distributed?"

| # | Canonical question | Required datum | Carrier (tool · field) | State |
|---|---|---|---|---|
| 1 | **Which** desks are accumulating this ticker (named) | ticker→named brokers, buy side | ✅ `get_ticker_broker_flow.top_accumulating` (`broker_code`, `net_value_idr`, `avg_buy_price`) | 🟢 covered |
| 2 | **How many** desks accumulating | `total_buyer` / `number_broker_buysell` | ✅ `get_ticker_broker_flow.bandar.total_buyers` / `number_broker_buysell` | 🟢 covered |
| 3 | **Consistency** — streak (days), months | daily streak; multi-window smoothing; multi-day per-desk agg | days ✅ `AgentAccumulationFacts.consecutive_streak`; single-session `five_day/top-N accdist` ✅ `get_ticker_broker_flow.bandar.*_accdist`; multi-day per-desk over ≤60 sessions → [`get_ticker_desk_flow_history` task](../../tasks/backlog/implement_ai_research_cockpit_ticker_desk_flow_history_tool.md) | 🟡 (multi-day remainder) |
| 4 | All of 1–3 for **distribution/selling** | ticker→named sellers; `Dis` labels; `total_seller` | ✅ `get_ticker_broker_flow.top_distributing`; `bandar.broker_accdist` / `total_sellers` | 🟢 covered |
| 5 | All of 1–4 on **volume / qty / price avg** | per-ticker volume; per-broker net; per-broker avg price | volume ✅ dashboard; per-broker net ✅ desk/RO + `get_ticker_broker_flow` net fields; avg price ✅ `top_*.avg_buy_price` / `avg_sell_price` | 🟢 covered |
| 6 | Phase **compression / breakout** | setup phase; BB width percentile | ✅ `AgentSetupPhaseFacts.current_phase`; ✅ `AgentAccumulationFacts.bb_width_pctile` | 🟢 covered |
| 7 | Recent **insider activity** | insider transactions | **exists** — `insider_cache` + `InsiderTransaction` + `InsiderActivityProvider` (via `ticker_dashboard_source`); no agent tool/projection | 🟡 projection |
| 8 | Upcoming **corporate action** | corp-action calendar (div/split/RUPS) | **exists** — `corp_action_cache` + `SQLiteCorporateActionCalendarRepository` + `CorporateActionCalendarEvent`; no agent tool/projection | 🟡 projection |

**Headline:** Q1/Q2/Q4/Q5 (avg-price) are closed by **`get_ticker_broker_flow`**
(single-session stock-centric ticker→desks + bandar). Remaining open projection
work: multi-day desk history (row 3), insider (7), corp-action (8).

## Matrix — broader accum/preopen research context

Beyond "who's accumulating," these are the next highest-impact research questions.
All data is **local** (🟡 projection gaps) → each an implement task under ADR-061,
`side_effect=NONE`, **facts-not-score**.

| # | Canonical question | Required datum | Carrier (exists) → tool | State |
|---|---|---|---|---|
| 9 | Is **foreign/smart money** accumulating (net trend over weeks)? | `foreign_flow_points` series | `ViewTickerForeignHistoryUseCase` (cache-only, `days`) → [`get_ticker_foreign_flow` task](../../tasks/backlog/implement_ai_research_cockpit_ticker_foreign_flow_tool.md) | 🟡→ task |
| 10 | What's the current **market regime / breadth**? | `market_context_snapshots` + `regime_observations` | `BuildMarketContextUseCase` (stored snapshot) → [`get_market_regime` task](../../tasks/backlog/implement_ai_research_cockpit_market_regime_tool.md) | 🟡→ task |
| 11 | Is the **float tightening** / who owns it? | `shareholding_composition` (`institution_pct`, `individual_pct`, `top_holder_*`, `total_shares`) | → [`get_ticker_ownership` task](../../tasks/backlog/implement_ai_research_cockpit_ticker_ownership_tool.md) | 🟡→ task |
| 12 | **Pre-open IEV** / NCP snapshot / IEV delta? | `iev_snapshots` | `SQLiteIEVRepository` (`get_ncp_snapshot`, `get_iev_delta`, `get_locked_iev_baseline`) → [`get_preopen_iev` task](../../tasks/backlog/implement_ai_research_cockpit_preopen_iev_tool.md) | 🟡→ task |
| 13 | **Sector** strength / rotation / peers? | sector macro context evidence (ADR-053) | `candidate_sector_macro_context_evidence_assembler` → [`get_ticker_sector_context` task](../../tasks/backlog/implement_ai_research_cockpit_ticker_sector_context_tool.md) | 🟡→ task |

**Honorable mentions (not yet tasked):** fundamentals/earnings trend (partial
overlap with `get_ticker_dashboard`); `get_macro_calendar` (`macro_calendar_events`).

## Partial-data honesty policy (all read tools)

Every cockpit read tool follows one policy so status is consistent and never lies.
It aligns with the `AgentToolExecutionResult` contract (`agent_tools.py`): SUCCESS =
`data`, no error; PARTIAL = `data` + non-empty `warnings`; UNAVAILABLE = `data=None`
+ `error_code`+`error_message`.

**Rule: SUCCESS vs PARTIAL is about *dimensions delivered*, not *rows returned*.
Emptiness that is a true finding is SUCCESS; a promised dimension that is missing
is PARTIAL. UNAVAILABLE only when there is nothing truthful to return.**

| Case | Status |
|---|---|
| No backing data at all for the subject | UNAVAILABLE (data=None + error) |
| Subject present, a result set genuinely empty (flat/one-sided) | SUCCESS + INFO note (e.g. `NO_NET_TOPS`, `NO_DISTRIBUTION_SIDE`) |
| One promised dimension missing, others present | PARTIAL + coded WARN (e.g. `BANDAR_SNAPSHOT_UNAVAILABLE`, `NAMED_TOPS_UNAVAILABLE`) |
| Only a degraded/fallback source yielded nothing | PARTIAL + coded WARN (e.g. `TOPS_FALLBACK_EMPTY`) |

Guardrails: **UNAVAILABLE is last resort** — if any real datum exists, prefer
SUCCESS/PARTIAL; **never fabricate** (empty lists stay empty, missing fields stay
null); use **stable warning codes** (U7 honesty strip ranks WARN before INFO).
Each tool task names its own dimension-specific codes.

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
- A row that is 🟡/🔴 → add an implement task under ADR-061 for the new OUR tool
  (a new ADR only for new authority / a new provider).
- A row that flips to 🟢 → cite the tool/field + the ADR that closed it.
- Never mark 🟢 on data that exists but is unexposed — that is 🟡 by definition.
