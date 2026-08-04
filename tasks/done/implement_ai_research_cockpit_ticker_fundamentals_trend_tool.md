# Goal Instruction — `get_ticker_fundamentals_trend` (earnings/quality over quarters)

**Status:** `READY FOR AGENT`
**Audience:** Implementation agent · **Product term:** AI Research Cockpit (`/`)
**Menu:** D (deepens `get_ticker_dashboard`, which shows only latest) · Depth policy.

**Binding architecture:**

| Doc | Role |
|---|---|
| [ADR-061](../../docs/adr/ADR-061-closed-read-tool-orchestration-for-context-agent.md) | Closed read tool; descriptive, read-only |
| Depth policy + READY gate | [`ai_research_cockpit_tool_coverage.md`](../../docs/roadmap/ai_research_cockpit_tool_coverage.md) |
| Reuse | `TickerDashboardSource.get_earnings_history(ticker, quarters)` → `list[EarningsRecord]`; `get_fundamentals`; `get_forward_estimates` |

## 0. Mission

`get_ticker_dashboard` shows only the **latest** fundamentals. Expose the **trend**
over quarters (earnings/margin/quality) so the model can tell a durable accumulation
candidate from a one-quarter blip. Shared use case (CLI/TUI/agent).

## 1. Verified data facts (signature trace)

- `TickerDashboardSource.get_earnings_history(ticker, quarters) -> list[EarningsRecord]`
  **exists** (cache-only). `EarningsRecord` in `src/domain/value_objects/earnings_record.py`
  (confirm fields at implement: period, revenue, net_profit, eps, margins as available).
- `get_fundamentals` / `get_forward_estimates` exist for latest ratios + forward EPS.
- Tables: `earnings_cache`, `company_financials`, `forward_estimates_cache`.

## 2. Layer plan

```md
- Domain: not touched (EarningsRecord VO exists)
- Application: ViewTickerFundamentalsTrendUseCase — earnings series + derived
  QoQ/YoY deltas + trend direction (descriptive) + latest ratios + forward estimate;
  SHARED by CLI/TUI/agent
- Infrastructure: cache-only reads via TickerDashboardSource (no new provider)
- Adapter: agent tool GET_TICKER_FUNDAMENTALS_TREND + optional CLI/TUI view
```

## 3. Result (facts only)

`ticker`, `quarters[]` (period + revenue/net_profit/eps/margin as available),
derived `revenue_yoy`/`eps_yoy`/`margin_trend` (direction, descriptive), latest
ratios (`pe`, `pbv`, `roe`, `piotroski`), `forward_eps_1y`, provenance. **No**
"quality score"/verdict (Piotroski is a published metric, passed through as-is —
not a cockpit-invented score).

## 4. Slices

1. Contract: `AgentToolName.GET_TICKER_FUNDAMENTALS_TREND` + frozen result DTO.
2. Use case: `ViewTickerFundamentalsTrendUseCase` — series + deltas + latest + forward.
3. Tool: args `ticker` (required), optional `quarters` (cap, e.g. ≤ 8). Bound bytes.
4. Register in composition when `tools_enabled` + DB present.
5. Tests: series + YoY math; missing quarters → PARTIAL/`UNAVAILABLE` per honesty;
   no-fetch; frozen-result; no-invented-score guard.
6. Docs: add coverage row (fundamentals trend); journey changelog.

## 5. Acceptance

- [ ] Earnings/quality trend over quarters + latest ratios + forward estimate.
- [ ] Cache-only via existing source; read-only; no invented score.
- [ ] Missing → `UNAVAILABLE`/PARTIAL; Offline agent + golden UX green; Ruff green.

## 6. Non-goals

- Cockpit-invented quality/valuation score; writes/fetch; external/elevated.

## 7. Completion record

- Authorizing ADR: ADR-061 · Implemented date: · Commits:
