# ADR-067: AI Research Cockpit — stock-centric ticker→broker flow tool

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — architecture authorization only; runtime activation gated

**Date:** 2026-08-03

**Amends:** [ADR-061](ADR-061-closed-read-tool-orchestration-for-context-agent.md)

**Depends on:** [ADR-003](ADR-003-hexagonal-ports-adapters-architecture.md),
[ADR-042](ADR-042-deterministic-champion-and-optional-model-challengers.md),
[ADR-060](ADR-060-read-only-tui-context-agent.md),
[ADR-061](ADR-061-closed-read-tool-orchestration-for-context-agent.md),
[ADR-065](ADR-065-ai-research-cockpit-external-and-ro-data-l4.md)

**Product vocabulary:** **AI Research Cockpit** (`/`)

**Coverage driver:**
[`docs/roadmap/ai_research_cockpit_tool_coverage.md`](../roadmap/ai_research_cockpit_tool_coverage.md)
(rows 1, 2, 4)

**Implementation task:**
[`tasks/backlog/implement_ai_research_cockpit_ticker_broker_flow_tool.md`](../../tasks/backlog/implement_ai_research_cockpit_ticker_broker_flow_tool.md)

## Context

The most frequent accum/preopen research questions are **stock-centric** — "who is
accumulating/distributing *this ticker*, how many desks, how consistently?" The
current registry cannot answer them directly:

- `get_broker_desk` is **desk-centric** (`broker_code → tickers`), the wrong
  direction.
- `judge_accumulation_ticker` exposes only aggregate bandar signals
  (`bci_label`, `bci_tier1_count`) — not the **named** desks or buyer/seller counts.

The runtime already **self-flags** this: the orchestrator's planning-only failure
message reads *"we may need a ticker→top brokers tool (get_broker_desk is desk-code
centric, not stock-centric)."* That is a standing `TOOL_GAP` clue (ADR-065 loop).

Crucially, the **data and a read-only use case already exist**:

- `ViewTickerTopBrokersUseCase` → `top_buyers` / `top_sellers` (named
  `BrokerTransaction`s per ticker+date) with source/scope provenance.
- `BandarDetectorSnapshot` → `total_buyer`/`total_seller`, `number_broker_buysell`,
  `top1/3/5/10_accdist`, `top1_percent`, `total_volume`.

So this is not new authority or a new provider — it is a **thin closed tool** over
existing read-only composition, exactly like `TickerDashboardTool` and
`BrokerDeskTool`.

## Decision

### Authorization boundary

Add one **OUR local read tool** to the closed registry:
`get_ticker_broker_flow` — a **stock-centric** projection of who is
accumulating/distributing a ticker. `side_effect=NONE`, `approval=NONE`
(no confirm — ordinary ADR-061 class). Gated by `ai.tools_enabled` plus the
per-tool availability of its backing use case + DB, like the other DB-backed tools.

This ADR does **not**: add authority, writes, external/network access, new data
providers, or model-invented tools. Results are **context only** and never enter
Signal/Risk/MCE/`TradeSetup`/sizing/observations/labels/tuning/promotion.

### Tool contract (locked intent)

- **Name:** `get_ticker_broker_flow` (add to `AgentToolName`).
- **Args (closed, typed):**
  - `ticker: str` (required)
  - optional `window_days: int` with a **hard cap** (e.g. ≤ 20) for the
    consistency window; default = latest session only.
  - optional `limit: int` for top-N desks with a **hard cap** (e.g. ≤ 10).
- **Result (frozen typed projection, `schema_id` `agent_tool.ticker_broker_flow.v1`):**
  - `ticker`, `as_of` date, `tops_source`/`tops_scope` provenance (from the use case);
  - **top accumulating desks** (named): broker code, net value, and side;
  - **top distributing desks** (named): same shape;
  - **counts**: `total_buyers`, `total_sellers`, `number_broker_buysell`
    (from bandar snapshot when available);
  - **consistency labels**: `broker_accdist`, `five_day_accdist`,
    `top1/3/5/10_accdist` (multi-window smoothing) when available;
  - optional per-window streak summary when `window_days` is set.
- **Composition:** wraps `ViewTickerTopBrokersUseCase` (named desks) and, when
  present, `BandarDetectorSnapshot` (counts + consistency). Both are read-only.
- **Freshness/limits:** cache-only, no fetch/scrape; respect per-tool
  `max_result_bytes` and `timeout_ms` like other tools; bounded top-N.

### Coverage closed

| Coverage-matrix row | Effect |
|---|---|
| 1 which desks accumulating (named) | 🔴 → 🟢 |
| 2 how many desks accumulating | 🟡 → 🟢 (counts surfaced here) |
| 4 which desks distributing (named) | 🔴 → 🟢 |
| 3 consistency (streak/multi-window) | improved (daily streak already in judgment; multi-window labels now surfaced) |
| 5 per-broker net/value | improved (named desk net values) |

Per-broker **average price**, **monthly** aggregation, insider (7), and corporate
action (8) remain out of scope (separate rows / ADRs).

## Hard invariants

1. Registry stays closed; this adds one named, typed, read-only tool.
2. `side_effect=NONE`, no confirm; cache-only; no fetch/scrape/write.
3. Results are context only; deterministic Action authority untouched.
4. Bounded output: hard caps on `window_days`, `limit`, and result bytes.
5. Available on all stages (flat registry, ADR-066); returns `UNAVAILABLE` when its
   backing data is absent — never a fabricated desk list.

## Non-goals

- New data providers (insider, corp-action) — separate ADRs.
- Per-broker average-price or monthly aggregation (revisit if asked).
- External/network or elevated access (that is ADR-065's `web_research`/RO).
- Model-invented tools.

## Consequences

### Positive

- Answers the single most-frequent research family (who/how-many/how-consistent)
  from existing data; closes coverage rows 1/2/4 and the standing runtime gap.
- Thin, low-risk: composes two existing read-only paths.

### Costs

- One result DTO + tool + registration + tests.
- Consistency-window semantics must be locked (cap + meaning) in code and tests.

### Follow-up

- Implement `implement_ai_research_cockpit_ticker_broker_flow_tool.md`.
- Update the coverage matrix rows 1/2/4 to 🟢 with tool+field citations on landing.
- Insider (row 7) and corporate action (row 8) remain open capability gaps.
