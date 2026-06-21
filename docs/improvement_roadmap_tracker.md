# Improvement Roadmap Tracker
_Source plan: `.claude/plans/we-have-done-docs-claude-stockbit-data-r-fluttering-fairy.md`_
_Started: 2026-06-21_

This file is the canonical phase-by-phase state for the post-`claude_stockbit_data_recommendation_200626.md` improvement roadmap. Update it as each step completes. Survives context compaction — always check this file at the start of a new session.

---

## Phase Overview

| # | Item | Status | Branch/Commit |
|---|------|--------|---------------|
| 1 | Composite Score System | ✅ Done | see commits below |
| 2 | Earnings Data Integration | 🔲 Not Started | — |
| 3 | Stockbit OHLC Fallback | 🔲 Not Started | — |
| 4 | CLI Adapter Thinness Phase 1 | 🔲 Not Started | — |
| 5 | Piotroski Quality Gate | 🔲 Not Started | — |
| 6 | Broker Distribution Matrix | 🔲 Not Started | — |
| 7 | Split playwright_stockbit.py | 🔲 Not Started | — |
| 8 | Watchlist + Saved Screener | 🔲 Not Started | — |
| 9 | Valuation Metrics | 🔲 Not Started | — |

**Status legend:** 🔲 Not Started · 🔄 In Progress · ✅ Done · ⏸️ Deferred

---

## Phase 1: Composite Score System

**Goal:** Combine bandar detector, foreign flow, Piotroski F-Score, seasonality, analyst consensus, and forward EPS into a single `CompositeSignalScore` (0–100). Wire as primary sort key in `saham screen accum` and show as progress bar in `saham analyze swing TICKER`.

**Status:** ✅ Done

### Sub-steps

- [x] 1.1 Read existing enrichment value objects + accumulation screener to understand current data shapes
- [x] 1.2 Create domain value object `CompositeSignalScore` in `src/domain/value_objects/composite_signal_score.py`
- [x] 1.3 `_composite_score()` function inline in `accumulation_screen.py` (application layer, called after all enrichment attached)
- [x] 1.4 Wire into `saham screen accum` — added `Cmp` column (primary sort), composite breakdown in `--breakdown` mode
- [ ] 1.5 Wire into `saham analyze swing TICKER` — deferred to next session
- [x] 1.6 Write unit tests — 6 new tests, all 1624 total pass
- [ ] 1.7 Verify end-to-end with live data — deferred to next session

### Files Changed
- `src/domain/value_objects/composite_signal_score.py` — new
- `src/application/use_case/accumulation_screen.py` — `_composite_score()`, `forward_estimates` + `composite_signal` fields, `ForwardEstimatesProvider` param, updated sort
- `src/adapters/cli/accumulation_commands.py` — wired `StockbitForwardEstimatesProvider`, added to `StockbitProviders`
- `src/adapters/cli/accumulation_display.py` — `Cmp` column + composite breakdown detail line

### Scoring Weights (confirmed)
| Sub-signal | Max pts | Source field |
|---|---|---|
| Bandar accumulation score (-9 to +9) | 20 | `bandar_detector_cache.score` |
| Foreign flow streak + 7/30d net value | 20 | `foreign_flow_snapshots` + `broker_summaries` |
| Piotroski F-Score (0–9) | 20 | `fundamentals_cache.piotroski_score` |
| Seasonality: current month win rate | 15 | `seasonality_cache` |
| Analyst consensus % buy + target premium | 15 | `analyst_ratings_cache` |
| Forward EPS growth estimate | 10 | `forward_estimates_cache` |
| **Total** | **100** | |

---

## Phase 2: Earnings Data Integration

**Goal:** New provider `stockbit_earnings.py` for `/earnings` endpoint. Cache EPS/revenue actuals vs consensus. Wire into swing view + new `saham analyze earnings TICKER` command.

**Status:** 🔲 Not Started

### Sub-steps
- [ ] 2.1 Probe `/earnings?ticker=BBCA` to confirm live field names (or use existing probe doc)
- [ ] 2.2 Create `src/infrastructure/browser/stockbit_earnings.py`
- [ ] 2.3 Add `earnings_cache` table to SQLite schema
- [ ] 2.4 Add port `StockbitEarningsProvider` in `src/domain/ports/`
- [ ] 2.5 Wire into `RefreshStockbitEnrichmentUseCase`
- [ ] 2.6 Display in `saham analyze swing TICKER`
- [ ] 2.7 Add `saham analyze earnings TICKER` command
- [ ] 2.8 Tests

---

## Phase 3: Stockbit OHLC Fallback

**Goal:** `StockbitHistoricalProvider` implementing `MarketDataProvider`. Use when Yahoo returns < 80% coverage. Also ingests foreign flow in same call.

**Status:** 🔲 Not Started

### Sub-steps
- [ ] 3.1 Read `RefreshMarketDataUseCase` + `MarketDataProvider` port
- [ ] 3.2 Create `src/infrastructure/data_providers/stockbit_historical.py`
- [ ] 3.3 Update `RefreshMarketDataUseCase` to accept provider priority list with fallback
- [ ] 3.4 Wire into `FetchMarketRefreshUseCase`
- [ ] 3.5 Tests

---

## Phase 4: CLI Adapter Thinness Phase 1

**Goal:** Move workflow/orchestration logic out of `fetch_market_commands.py`, `analyze_commands.py`, `screen_commands.py` into Application use cases. CLI becomes: parse → call use case → format output.

**Status:** 🔲 Not Started

### Sub-steps
- [ ] 4.1 Audit `fetch_market_commands.py` — identify non-adapter logic
- [ ] 4.2 Extract orchestration to use case(s)
- [ ] 4.3 Repeat for `analyze_commands.py`
- [ ] 4.4 Repeat for `screen_commands.py`
- [ ] 4.5 Regression test all affected commands

---

## Phase 5: Piotroski Quality Gate

**Goal:** `--min-piotroski INT` flag in `saham screen accum`. Filter candidates below threshold before display.

**Status:** 🔲 Not Started

### Sub-steps
- [ ] 5.1 Add `--min-piotroski` option to `screen_commands.py`
- [ ] 5.2 Pass threshold to `AccumulationScreenUseCase` (or filter in adapter)
- [ ] 5.3 Validate Piotroski field path in `fundamentals_cache`

---

## Phase 6: Broker Distribution Matrix

**Goal:** New provider for `/order-trade/broker/distribution`. ASCII heatmap in `saham view broker`.

**Status:** 🔲 Not Started

---

## Phase 7: Split playwright_stockbit.py

**Goal:** Separate browser lifecycle from JSON parsers. Target: `playwright_stockbit_browser.py` + `playwright_stockbit_broker.py`.

**Status:** 🔲 Not Started

---

## Phase 8: Watchlist + Saved Screener

**Goal:** `saham screen save`, `saham screen compare`, `saham view watchlist` commands.

**Status:** 🔲 Not Started

---

## Phase 9: Valuation Metrics

**Goal:** New provider for `/valuation/company/{ticker}/metrics`. Wire into `saham analyze swing TICKER`.

**Status:** 🔲 Not Started

---

## Notes / Decisions Log

_Append decisions, blockers, or scope changes here as they come up._

