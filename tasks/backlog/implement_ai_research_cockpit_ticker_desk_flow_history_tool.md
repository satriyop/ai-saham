# Goal Instruction — Implement `get_ticker_desk_flow_history` (multi-day desk view)

**Status:** `READY FOR AGENT`
**Audience:** Implementation agent (any coding agent in this repo)
**Product term:** **AI Research Cockpit** (`/`)

**Binding architecture:**

| Doc | Role |
|---|---|
| [ADR-061](../../docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md) | **Binding** — closed read-tool registry authorization. Read-only, `side_effect=NONE`; **descriptive facts only** (no score) → stays a task, no new ADR |
| Coverage matrix | [`docs/roadmap/ai_research_cockpit_tool_coverage.md`](../../docs/roadmap/ai_research_cockpit_tool_coverage.md) (row 3 multi-day) |
| Sibling (single-session) | [`implement_ai_research_cockpit_ticker_broker_flow_tool.md`](../done/implement_ai_research_cockpit_ticker_broker_flow_tool.md) — "who today" (IMPLEMENTED) |
| Reference tools | `agent_ticker_dashboard_tool.py`, `agent_broker_desk_tool.py` (tool shape) |
| Reuse primitives | `institutional_flow_broker_metrics.py` (`_net_by_broker`, `_top_brokers_by_net`), `sqlite_broker_daily_flow_store.get_broker_daily_flows` |

**Do not invent product behavior.** If a contract detail is unspecified, choose the
**safer, smaller** option and document it.

## 0. Mission

Answer "**over the last ~3 months of sessions, which desks persistently accumulate
or distribute this ticker, by magnitude and consistency?**" as one closed OUR read
tool. Complements the single-session `get_ticker_broker_flow` ("who today"). Closes
coverage matrix **row 3** (multi-day consistency) and the "how many months" need.

Locked design decisions (operator, 2026-08-03):

- **Facts, not a score.** Report orthogonal raw numbers per desk; never a blended
  "accumulation quality" score (that would drift toward evidence authority).
- **Two tools** — this is the multi-day one; keep it separate from single-session.
- **Window cap = 60 trading sessions** (~3 months); PIT ≤ `as_of`.

Hard rules:

- `side_effect=NONE`, `approval=NONE`; cache-only; no fetch/scrape/write.
- **Aggregate from RAW `broker_daily_flow`, NOT per-day top-N lists** — the desk
  that is #12 every session is a more consistent accumulator than the one that
  spiked once; aggregating daily tops would lose exactly that signal. Correctness-critical.
- **Sessions, not calendar days** (IDX holidays/weekends); reuse the accum window
  discipline. PIT: never read rows dated after `as_of`.
- Output bounded by **top-N ≤ 10 per side** (buy + sell), so result size is
  independent of the 60-session scan; respect per-tool `max_result_bytes`.
- `UNAVAILABLE` when no cached broker flow for the ticker/window — never fabricate.
- Descriptive/context only; deterministic Action authority untouched.
- Offered on all stages (flat registry). Offline agent suite green.

## 1. Layer plan

```md
- Domain: not touched (BrokerDailyFlow exists)
- Application: AgentToolName.GET_TICKER_DESK_FLOW_HISTORY; result DTO
  (schema agent_tool.ticker_desk_flow_history.v1); a TickerDeskFlowHistory service
  composing get_broker_daily_flows(range) + institutional_flow_broker_metrics net
  aggregation + NEW per-desk streak/frequency calc; TickerDeskFlowHistoryTool
- Infrastructure: composition wiring (register when tools_enabled + broker flow DB present)
- Adapter: none beyond existing tool-trace rendering
```

Read first: `src/infrastructure/persistence/sqlite_broker_daily_flow_store.py`
(`get_broker_daily_flows`, `get_broker_daily_flow_date_range`),
`src/application/services/institutional_flow_broker_metrics.py`
(`_net_by_broker`, `_top_brokers_by_net`), `src/domain/entities/broker_flow.py`
(`net_value`, `avg_buy_price`, `avg_sell_price`, `buy_lot`, `sell_lot`),
the accum evaluator's session-window selection for the PIT/session pattern, and
the foreign/tier-1 broker code config.

## 2. Per-desk facts to compute (the new part)

For each desk in the window, all **descriptive** (no score):

| Fact | Meaning |
|---|---|
| `broker_code`, `is_foreign` | identity + config-driven foreign/tier-1 flag |
| `cumulative_net` | Σ net_value over the window (magnitude) |
| `window_sessions` | total trading sessions in the window |
| `active_sessions` | sessions where the desk had any row (unambiguous frequency denominator) |
| `net_buy_sessions` | sessions the desk was net-buy (→ frequency = net_buy/active) |
| `longest_streak` | longest run of consecutive net-buy sessions (persistence) |
| `avg_buy_price` / `avg_sell_price` | window-weighted, from `broker_flow` |

Rank **buy side** by `cumulative_net` desc, **sell side** by `cumulative_net` asc;
top-N ≤ 10 each side. Report `window_sessions`, `as_of`, and provenance.

## 3. Slices

1. **Contract:** `AgentToolName.GET_TICKER_DESK_FLOW_HISTORY`; frozen result DTO
   (`agent_tool.ticker_desk_flow_history.v1`) with top accumulating + distributing
   desks (fields above) + window meta. **No score field.**
2. **Service:** `TickerDeskFlowHistoryService` — load raw flow for the ≤60-session
   PIT window, aggregate per desk (reuse `_net_by_broker`/`_top_brokers_by_net`),
   compute streak/frequency, rank, bound top-N.
3. **Tool:** `TickerDeskFlowHistoryTool` — args `ticker` (required), optional
   `sessions` (default 60, **hard cap 60**), optional `limit` (cap 10). Read-only.
4. **Register:** in composition when `tools_enabled` + broker flow DB present.
5. **Tests (offline `pytest.mark.agent`):**
   - **raw-not-topN:** a desk net-buy a small amount every session **outranks/appears
     over** a desk that spiked once — proves aggregation uses raw flow.
   - streak + frequency math (gaps, absence) with `active` vs `window` sessions.
   - `sessions` cap 60 + `limit` cap 10 enforced.
   - **PIT:** rows after `as_of` never counted (no look-ahead).
   - missing data → `UNAVAILABLE`; result byte cap; frozen-result validation.
   - **no-score guard:** result DTO has no evaluative score field.
6. **Docs:** flip coverage-matrix row 3 multi-day → 🟢 with tool+field citation;
   journey SSOT changelog row.

## 4. Acceptance

- [ ] Returns top accumulating + distributing desks over a ≤60-session PIT window
  with cumulative net, active/net-buy sessions, longest streak, avg prices, foreign flag.
- [ ] Aggregation from raw daily flow (raw-not-topN test passes).
- [ ] Sessions not calendar days; no look-ahead past `as_of`.
- [ ] Caps enforced; missing data → `UNAVAILABLE`; no score field.
- [ ] `side_effect=NONE`, cache-only, no fetch/write; Action authority untouched.
- [ ] Offline agent suite + golden UX pilot green; Ruff green.
- [ ] Coverage row 3 multi-day → 🟢; completion record filled.

## 5. Non-goals

- Any blended/evaluative **score** (facts only — governance line).
- Per-session or per-week time series / sparkline (aggregate view only; extension later).
- Calendar-month bucketing (window is trading sessions).
- New provider/fetch; external/elevated access; model-invented tools; any write.

## 6. Completion record (fill when done)

- Authorizing ADR: ADR-061 (routine closed read tool; descriptive facts)
- Implemented date:
- Commits:
- Coverage row flipped: 3 (multi-day)
