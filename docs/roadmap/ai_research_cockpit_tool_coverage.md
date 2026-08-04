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

## Depth policy (2026-08-04)

Thinness is **no longer a constraint.** Tools may be backed by real
**application use cases** with genuine computation, new port methods, and new
SQLite reads. **Build the depth as a shared `application/use_case` so CLI, TUI, and
the agent are all thin adapters over it** — do not build agent-only analytics.

What still binds (these are governance, not style):

- **Descriptive, not authority.** A tool result stays context; it must not become
  an evaluative verdict/score competing with `TradeSetup` (ADR-042 champion).
  A genuinely scored output is allowed only via the **evidence-promotion lane
  (its own ADR)**, then projected descriptively with provenance — never smuggled
  into a read tool.
- **Read-only** (no writes — Phase 5), **PIT** correctness, and the
  **signature-trace READY gate** below (deeper = more surface = more verification).
- A new shared use case that adds real capability/analysis may warrant its **own
  ADR** when it crosses a boundary (new authority, new provider, new evidence);
  a descriptive read use case remains under ADR-061.

## Current tool catalog (carriers)

| Tool | Tier | Key result carriers |
|---|---|---|
| `get_visible_cockpit_result` | OUR / NONE | active stage projection (polymorphic, ADR-066) |
| `get_ticker_dashboard` | OUR / NONE | price/volume/fundamentals cache summary |
| `judge_accumulation_ticker` | OUR / NONE | `AgentAccumulationFacts` (`consecutive_streak`, `net_buy_ratio`, `bb_width_pctile`, `bci_label`, `bci_tier1_count`), `AgentSetupPhaseFacts` (`current_phase`, `phase_age_sessions`, `detection_strength`) |
| `get_broker_desk` | OUR / NONE | **desk→ticker** views (SHOW/TOP_STOCKS/TOP_MATRIX/FLOW/CALENDAR/HISTORY) |
| `get_ticker_broker_flow` | OUR / NONE | **ticker→desks** single-session: `top_accumulating`/`top_distributing` (net + avg buy/sell price), `bandar.total_buyers`/`total_sellers`/`number_broker_buysell`, `broker_accdist` + `five_day`/`top1`/`top3`/`top5`/`top10_accdist`, `tops_source`/`tops_scope`, `as_of` |
| `get_ticker_foreign_flow` | OUR / NONE | foreign net series: `cumulative_net_idr`, `latest_net_idr`, `net_buy_sessions`/`active_sessions`, `trend_direction` (rising/falling/flat), capped `(date, net_value_idr)` tail, `resolved_source` |
| `get_ticker_desk_flow_history` | OUR / NONE | multi-session desks: `top_accumulating`/`top_distributing` (cumulative_net, active/net_buy sessions, longest_streak, avg prices, weekly_net), rotation, foreign/local split |
| `get_ticker_ownership` | OUR / NONE | `institution_pct`, `individual_pct`, `top_holder_name`/`top_holder_pct`, `total_shares`(+formatted), `report_date` |
| `get_ticker_ownership_history` | OUR / NONE | deduped `periods[]` (`report_date`, `institution_pct`, `individual_pct`, `free_float_pct`, `top_holder_name`/`top_holder_pct`, `total_shares`), latest-vs-previous `institution_pct_change`/`float_change`/`top_holder_pct_change`; PIT via `as_of_date` |
| `get_preopen_iev` | OUR / NONE | `iev`/`iep`/`rank`/`is_ncp_locked` (canonical current reading), `locked_baseline_iev` (08:56 NCP lock), `iev_move_since_lock` (`None`+`NO_POST_LOCK_MOVE` INFO when no lock exists); future `session_date` → typed `SESSION_DATE_IN_FUTURE` UNAVAILABLE |
| `get_ticker_corporate_actions` | OUR / NONE | `upcoming[]`/`recent[]` calendar events (relative to today) each with **role-keyed** `dates[]` (`role`/`event_date`/`event_time`, incl. `rups_date`/`pubex_date` — not the lossy 5-field flatten), `event_type`, `amount_value`/`amount_currency`, `ratio_old`/`ratio_new`, `price`, `event_note`, `active`, `company_name`; `event_count`; dateless events → `NO_DATED_MILESTONES` INFO |
| `get_ticker_sector_context` | OUR / NONE | L2a peer_context + L2b macro_context (labels/values; no composite score) |
| `get_ticker_insider_activity` | OUR / NONE | recent cached `transactions[]` (`name`, `action_type`, `shares`, `price`, `transaction_date`; newest first, bounded window/limit) + `buy_count`/`sell_count`/`net_shares`/`net_buy_ratio`; empty-in-window vs never-cached distinguished (`NO_INSIDER_ACTIVITY_IN_WINDOW` INFO vs `UNAVAILABLE`) |
| `get_ticker_fundamentals_trend` | OUR / NONE | multi-quarter EPS series + latest ratios + forward; `eps_trend_direction` |
| `get_market_regime` | OUR / NONE | market-wide tape: `regime`, `conviction`, `regime_confidence` (nullable), factor value/label/rationale (no factor scores), `signal_multiplier`/`gate_tightening` as stored readings, optional stability/days, `cohort_id` |
| `get_ticker_research_brief` | OUR / NONE | composed one-shot: judge Action (surfaced) + broker/foreign/ownership/corp/regime sections; per-section status; **no minted verdict** (ADR-042) |
| `web_research` | External / NETWORK_READ | external snippets (confirm) |
| `ro_data_query` | Elevated / LOCAL_READ_ELEVATED | 3 allowlisted shapes: ticker close, ticker volume, broker day net (confirm) |

**Correction (2026-08-03):** rows 5, 7, 8 were first mis-graded 🔴 capability gaps
by auditing only agent-facing DTOs. The underlying data is **local** — they are
🟡 projection gaps (rows 1/2/4/5 closed by `get_ticker_broker_flow`). There are
currently **no true capability gaps** in this list.

## Matrix — "is this ticker being accumulated or distributed?"

| # | Canonical question | Required datum | Carrier (tool · field) | State |
|---|---|---|---|---|
| 1 | **Which** desks are accumulating this ticker (named) | ticker→named brokers, buy side | ✅ `get_ticker_broker_flow.top_accumulating` (`broker_code`, `net_value_idr`, `avg_buy_price`) | 🟢 covered |
| 2 | **How many** desks accumulating | `total_buyer` / `number_broker_buysell` | ✅ `get_ticker_broker_flow.bandar.total_buyers` / `number_broker_buysell` | 🟢 covered |
| 3 | **Consistency** — streak (days), months | daily streak; multi-window smoothing; multi-day per-desk agg | days ✅ `AgentAccumulationFacts.consecutive_streak`; single-session `five_day/top-N accdist` ✅ `get_ticker_broker_flow.bandar.*_accdist`; multi-day per-desk ✅ `get_ticker_desk_flow_history` (cumulative_net, longest_streak, net_buy_sessions, rotation) | 🟢 covered |
| 4 | All of 1–3 for **distribution/selling** | ticker→named sellers; `Dis` labels; `total_seller` | ✅ `get_ticker_broker_flow.top_distributing`; `bandar.broker_accdist` / `total_sellers` | 🟢 covered |
| 5 | All of 1–4 on **volume / qty / price avg** | per-ticker volume; per-broker net; per-broker avg price | volume ✅ dashboard; per-broker net ✅ desk/RO + `get_ticker_broker_flow` net fields; avg price ✅ `top_*.avg_buy_price` / `avg_sell_price` | 🟢 covered |
| 6 | Phase **compression / breakout** | setup phase; BB width percentile | ✅ `AgentSetupPhaseFacts.current_phase`; ✅ `AgentAccumulationFacts.bb_width_pctile` | 🟢 covered |
| 7 | Recent **insider activity** | insider transactions | ✅ `get_ticker_insider_activity` — `transactions[]` (name/action_type/shares/price/transaction_date, newest first) + `buy_count`/`sell_count`/`net_shares`/`net_buy_ratio` over `InsiderActivityProvider` (cache-only, `api_client=None` composition + explicit `as_of_date`) | 🟢 covered |
| 8 | Upcoming **corporate action** | corp-action calendar (div/split/RUPS) | ✅ `get_ticker_corporate_actions` — `upcoming[]`/`recent[]` events with role-keyed `dates[]` (incl. `rups_date`/`pubex_date`) over `SQLiteCorporateActionCalendarRepository` / `CorporateActionCalendarEvent` | 🟢 covered |

**Headline:** Q1/Q2/Q4/Q5 (avg-price) are closed by **`get_ticker_broker_flow`**
(single-session stock-centric ticker→desks + bandar). Insider (7) closed by
`get_ticker_insider_activity`; corp-action (8) closed by
`get_ticker_corporate_actions`; multi-day desk history (row 3) closed. No open
projection gaps remain in this matrix.

## Matrix — broader accum/preopen research context

Beyond "who's accumulating," these are the next highest-impact research questions.
All data is **local** (🟡 projection gaps) → each an implement task under ADR-061,
`side_effect=NONE`, **facts-not-score**.

| # | Canonical question | Required datum | Carrier (exists) → tool | State |
|---|---|---|---|---|
| 9 | Is **foreign/smart money** accumulating (net trend over weeks)? | `foreign_flow_points` series | ✅ `get_ticker_foreign_flow` (`cumulative_net_idr`, `latest_net_idr`, `trend_direction`, `net_buy_sessions`, point tail) — complements dashboard window summaries | 🟢 covered |
| 10 | What's the current **market regime / breadth**? | `market_context_snapshots` + `regime_observations` | ✅ `get_market_regime` — cohort-scoped cache snapshot (`regime`, `conviction`, `regime_confidence`, factor value/label/rationale, `signal_multiplier`/`gate_tightening`, optional stability/days, `cohort_id`); never recomputes MCE | 🟢 covered |
| 11 | Is the **float tightening** / who owns it? | `shareholding_composition` (`institution_pct`, `individual_pct`, `top_holder_*`, `total_shares`) | ✅ `get_ticker_ownership` (single latest); history via `get_ticker_ownership_history` (`periods[]`, `institution_pct_change`, `float_change`, `top_holder_pct_change`) | 🟢 covered |
| 12 | **Pre-open IEV** / NCP snapshot / IEV delta? | `iev_snapshots` | ✅ `get_preopen_iev` (`iev`/`iep`/`rank`/`is_ncp_locked` from `get_snapshot`, `locked_baseline_iev` via `ncp_baseline_iev`, `iev_move_since_lock`) | 🟢 covered |
| 13 | **Sector** strength / rotation / peers? | L2a peers + L2b sector-macro | ✅ `get_ticker_sector_context` (`peer_context` returns/breadth/RS/regime; `macro_context` factors value/label/rationale, `macro_regime`) — no composite/factor scores | 🟢 covered |

**Honorable mentions (not yet tasked):** `get_macro_calendar` (`macro_calendar_events`).

## Deepenings (menu A–E, Depth policy 2026-08-04)

Depth over thinness — each built as a **shared use case** (CLI/TUI/agent adapters),
descriptive (no authority/score):

| Menu | Deepening | Task |
|---|---|---|
| A | Ownership **history / float trend** (new port `get_ownership_history` + dedupe per `report_date`) | ✅ `get_ticker_ownership_history` (IMPLEMENTED; see `tasks/done/…ownership_history…`) |
| B | Sector context as a **shared use case** (`BuildTickerSectorContextUseCase`) | ✅ `get_ticker_sector_context` (IMPLEMENTED) |
| C | Desk flow **rotation + foreign/local split + weekly trajectory** | ✅ `get_ticker_desk_flow_history` (IMPLEMENTED; see `tasks/done/…desk_flow_history…`) |
| D | Fundamentals / **earnings trend** over quarters | ✅ `get_ticker_fundamentals_trend` (IMPLEMENTED) |
| E | **Ticker research brief** — one composed, PIT-aligned bundle (surfaces Judge Action; **no minted verdict**, ADR-042) | ✅ `get_ticker_research_brief` (IMPLEMENTED; shared `BuildTickerResearchBriefUseCase`; agent tool this slice; CLI/TUI thin adapters deferred) |

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

## Task READY gate — signature trace (planner discipline)

Before a tool task is marked `READY FOR AGENT`, **every arg and every result field
must trace to a concrete method signature that already returns it** — a named port
or use-case method, verified in source. Specifically:

- An "optional / if-available" field with **no read path** is **dead spec** (it
  always omits) or **hidden scope** (it silently forces a port extension). Drop it
  or scope the extension explicitly. *(Caught late: `window_days`, ownership delta.)*
- Confirm the access **shape** matches the tool's args: a ticker-keyed tool cannot
  wrap a date-keyed repository without an extract step. *(Caught: `get_preopen_iev`
  — IEV repo is date-keyed.)*
- Confirm the reuse target is **descriptive**, not a **scored/evidence** VO
  (facts-not-score). *(Caught: `get_ticker_foreign_flow` must use `ForeignFlowPoint`,
  not `ForeignFlowEvidence`; `get_ticker_sector_context` ships descriptive L2a+L2b projection — rescoped and closed.)*
- Confirm the read is **cache-only** (not a fetch/browser provider) and the
  named factory actually exposes it. *(Caught: bandar via dashboard source, not
  the browser `BandarDetectorProvider`.)*

If any trace fails, the task is `NEEDS RESCOPE`, not `READY`.
