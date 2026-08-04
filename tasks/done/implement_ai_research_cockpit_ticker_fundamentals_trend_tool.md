# Goal Instruction — `get_ticker_fundamentals_trend` (EPS series + latest ratios)

**Status:** `IMPLEMENTED`
**Menu:** D · Depth policy · ADR-061

## Locked decisions (operator 2026-08-04 — A + recommended)

| # | Decision |
|---|---|
| Scope | **EPS history** (`EarningsRecord`) + latest `CompanyFundamentals` + `ForwardEstimates` |
| Not in v1 | Multi-period revenue/margin statement series (financials UC follow-up) |
| `quarters` | default **4**, hard max **8** |
| Trend | half-window compare of `eps_actual` → rising/falling/flat/unknown |
| Scores | No invented quality score; Piotroski pass-through as published metric only |
| Adapters | Agent tool + composition this task |

## Result (facts only)

- `quarters[]`: period_label, eps_actual/estimate, surprise, yoy_growth_pct, beat
- `eps_trend_direction`
- `latest_fundamentals`: pe, pbv, roe, npm, revenue_yoy (latest snapshot), piotroski, …
- `forward`: forward_eps_1y, revenue_forward_1y, forward_pe
- PARTIAL when a branch is missing; UNAVAILABLE only if all missing

## Completion record

- Authorizing ADR: ADR-061
- Implemented date: 2026-08-04
- Code: `view_ticker_fundamentals_trend_use_case.py`, `agent_ticker_fundamentals_trend_tool.py`
- Tests: `test_view_ticker_fundamentals_trend_use_case.py`, `test_agent_ticker_fundamentals_trend_tool.py`
- Commits: `7c714b60`
