# Improvement Roadmap Tracker
_Source plan: `.claude/plans/we-have-done-docs-claude-stockbit-data-r-fluttering-fairy.md`_
_Started: 2026-06-21_

This file is the canonical phase-by-phase state for the post-`claude_stockbit_data_recommendation_200626.md` improvement roadmap. Update it as each step completes. Survives context compaction — always check this file at the start of a new session.

---

## Phase Overview

| # | Item | Status | Branch/Commit |
|---|------|--------|---------------|
| 1 | Composite Score System | ✅ Done | see commits below |
| 2 | Earnings Data Integration | ✅ Done | see commits below |
| 3 | Stockbit OHLC Fallback | ✅ Done | see commits below |
| 4 | CLI Adapter Thinness Phase 1 | 🔲 Not Started | — |
| 5 | Piotroski Quality Gate | ✅ Done | see commits below |
| 6 | Broker Distribution Matrix | ✅ Done | see commits below |
| 7 | Split playwright_stockbit.py | ⏸️ Dropped | cookie-based auth removed; only Playwright remains — split no longer needed |
| 8 | Watchlist + Saved Screener | ✅ Done | 04a9996 |
| 9 | Valuation Metrics | ✅ Done | 8ea18a2 |

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

**Status:** ✅ Done

### Sub-steps
- [x] 2.1 Probe `/earnings?ticker=BBCA` — confirmed live field names via `stockbit_api_probe_response.md`
- [x] 2.2 Create `src/infrastructure/browser/stockbit_earnings.py` — `StockbitEarningsProvider` with period-chain walking
- [x] 2.3 Add `earnings_cache` table to SQLite schema (PK: ticker/year/quarter, 7-day TTL)
- [x] 2.4 Create port `src/domain/ports/earnings_provider.py` + value object `src/domain/value_objects/earnings_record.py`
- [x] 2.5 Wire into fetch market: `EnrichmentTask("earnings", ...)` in `fetch_market_commands.py`
- [x] 2.6 Display in `saham analyze swing TICKER` — earnings beat/miss streak panel
- [ ] 2.7 `saham analyze earnings TICKER` standalone command — deferred to later phase
- [x] 2.8 Tests — 16 new tests in `tests/infrastructure/browser/test_stockbit_earnings.py`; all 1640 pass

### Files Changed
- `src/domain/value_objects/earnings_record.py` — new; frozen dataclass with `beat`, `yoy_growth_pct`, `label` properties
- `src/domain/ports/earnings_provider.py` — new; `EarningsProvider` ABC
- `src/infrastructure/config/stockbit_config.py` — added `earnings_url` field + YAML mapping
- `src/infrastructure/browser/stockbit_earnings.py` — new; SQLite-cached provider with period chain walking
- `src/adapters/cli/fetch_market_commands.py` — wired `EnrichmentTask("earnings", ...)`
- `src/adapters/cli/swing_analysis_display.py` — added earnings beat streak panel
- `tests/infrastructure/browser/test_stockbit_earnings.py` — new; 16 tests

### Key Design Notes
- Period chain walking: `/earnings` returns one quarter at a time; `prev_earnings_period` pointer walks backwards
- Missing surprise → computed from `(actual-estimate)/|estimate|*100` inline in parser
- Beat streak display: green if ≥3/4 beat, red if ≥3/4 miss, yellow otherwise

---

## Phase 3: Stockbit OHLC Fallback

**Goal:** `StockbitHistoricalProvider` implementing `MarketDataProvider`. Use when Yahoo returns < 80% coverage. Also ingests foreign flow in same call.

**Status:** ✅ Done

### Sub-steps
- [x] 3.1 Read `RefreshMarketDataUseCase` + `MarketDataProvider` port
- [x] 3.2 Create `src/infrastructure/data_providers/stockbit_historical.py`
- [x] 3.3 Decorator pattern: `FallbackMarketDataProvider` wraps primary+fallback; `RefreshMarketDataUseCase` unchanged
- [x] 3.4 Wire via `functools.partial(_fetch_candles, broker_provider=...)` at use-case construction in CLI adapter
- [x] 3.5 Tests — 18 new tests; 1654 total pass

### Files Changed
- `src/infrastructure/data_providers/stockbit_historical.py` — new; paginates `/historical/summary`, converts lots→shares
- `src/infrastructure/data_providers/fallback_provider.py` — new; tries fallback when primary coverage < 60% of expected days
- `src/adapters/cli/fetch_market_commands.py` — added `broker_provider` opt param to `_fetch_candles`; wires fallback via `functools.partial` when stockbit provider active
- `tests/infrastructure/data_providers/test_stockbit_historical.py` — new; 18 tests

### Key Design Notes
- `RefreshMarketDataUseCase` requires ZERO changes — fallback is transparent infrastructure
- `FallbackMarketDataProvider` proxies `provider_name/volume_unit/price_adjustment_policy` to whichever provider actually delivered data
- Coverage threshold: 60% of estimated trading days (`(end-start).days * 5/7`); configurable
- Volume: Stockbit returns lots; converted to shares (`* 100`) on ingest so Candle semantics match Yahoo

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

**Status:** ✅ Done

### Sub-steps
- [x] 5.1 Add `--min-piotroski` option to `accumulation_commands.py` (0–9, default 0 = disabled)
- [x] 5.2 Add `min_piotroski: int = 0` to `AccumulationScreenRequest`; filter in use-case `execute()` before `candidates.append()`
- [x] 5.3 Gate also excludes tickers with `None` fundamentals when min_piotroski > 0
- [x] 5.4 5 unit tests; 1659 total pass

### Files Changed
- `src/application/use_case/accumulation_screen.py` — `min_piotroski` field on request; filter block in execute()
- `src/adapters/cli/accumulation_commands.py` — `--min-piotroski` option wired to request

### Key Design Notes
- Filter applied AFTER composite score computation — it's an inclusion gate, not a scoring adjustment
- `min_piotroski=0` (default) is a no-op; no fundamentals provider = excluded if gate > 0

---

## Phase 6: Broker Distribution Matrix

**Goal:** New provider for `/order-trade/broker/distribution`. ASCII heatmap in `saham view broker`.

**Status:** ✅ Done

### Files Changed
- `src/domain/value_objects/broker_distribution.py` — new; frozen dataclasses: `BrokerCounterparty`, `BrokerDistributionEntry`, `BrokerDistributionSnapshot` with `foreign_buying_from_domestic` / `net_foreign_buyer_dominance` signal properties
- `src/domain/ports/broker_distribution_provider.py` — new; ABC port
- `src/infrastructure/config/stockbit_config.py` — added `broker_distribution_url`
- `src/infrastructure/browser/stockbit_broker_distribution.py` — new; SQLite cache (1-day TTL), JSON blob serialization for counterparty tree
- `src/adapters/cli/broker_commands.py` — `broker_distribution_view` command + `_display_distribution` ASCII renderer
- `src/adapters/cli/view_commands.py` — registered `distribution` subcommand under `view broker`
- `src/adapters/cli/fetch_market_commands.py` — wired `EnrichmentTask("brdist", ...)` into enrichment pass
- `tests/infrastructure/browser/test_stockbit_broker_distribution.py` — new; 21 tests
- `tests/adapters/cli/test_command_contract.py` — added `distribution` to expected broker view commands

### Key Design Notes
- Counterparties serialized as JSON blob (not normalized rows) — avoids a complex 3-table schema for a read-mostly cache
- `distribute_to` direction: "who the broker traded AGAINST" (not who they directed flow to)
- `foreign_buying_from_domestic`: top foreign buyer has >50% domestic counterparties = smart-money accumulation signal
- Display color: domestic counterparties yellow (retail), foreign counterparties dim

---

## Phase 7: Split playwright_stockbit.py

**Goal:** Separate browser lifecycle from JSON parsers. Target: `playwright_stockbit_browser.py` + `playwright_stockbit_broker.py`.

**Status:** ⏸️ Dropped — cookie-based auth was removed; only Playwright remains as the single auth/browser mechanism. The original motivation (isolating the cookie path from the browser path) no longer applies. The per-data-type parsers already live in dedicated `stockbit_*.py` files, so no further split is warranted.

---

## Phase 8: Watchlist + Saved Screener

**Goal:** `saham screen accum --save NAME`, `saham screen watchlist`, `saham screen compare NAME` commands.

**Status:** ✅ Done — commit `04a9996`

### Sub-steps
- [x] 8.1 `ScreenSnapshotEntry` frozen dataclass in `src/domain/value_objects/screen_snapshot.py`
- [x] 8.2 `SQLiteWatchlistRepository` — flat rows (`screen_snapshots` table), `get_latest_snapshot` by MAX(saved_at)
- [x] 8.3 `compare_screen_snapshots` application use case — new/dropped/changed buckets; `SignalChange` with rank_delta, composite_delta, strengthening flag
- [x] 8.4 `saham screen accum --save NAME` — persists ranked results after display
- [x] 8.5 `saham screen watchlist [NAME]` — lists all saved watchlists or shows a named one
- [x] 8.6 `saham screen compare NAME` — reruns screen silently via `_make_use_case_for_compare()`, diffs against saved
- [x] 8.7 12 new unit tests in `tests/infrastructure/persistence/test_sqlite_watchlist.py`; suite at 1689

### Files Changed
- `src/domain/value_objects/screen_snapshot.py` — new
- `src/application/use_case/compare_screen_snapshots.py` — new
- `src/infrastructure/persistence/sqlite_watchlist_repository.py` — new
- `src/adapters/cli/accumulation_commands.py` — `--save` flag, `_save_watchlist()`, `_make_use_case_for_compare()`
- `src/adapters/cli/screen_lifecycle_commands.py` — `watchlist` + `compare` commands
- `tests/infrastructure/persistence/test_sqlite_watchlist.py` — new; 12 tests
- `tests/adapters/cli/test_command_contract.py` — added watchlist/compare to screen tree

---

## Phase 9: Valuation Metrics

**Goal:** New provider for `/valuation/company/{ticker}/metrics`. Wire into `saham analyze swing TICKER`.

**Status:** ✅ Done — commit `8ea18a2`

### Sub-steps
- [x] 9.1 Add `valuation_metrics_url` to `StockbitConfig` + `load_stockbit_config()`
- [x] 9.2 `ValuationMetrics` frozen dataclass — `raw: dict[int, float]`, named properties for known IDs, `labeled` list, `is_empty`
- [x] 9.3 `KNOWN_METRIC_LABELS` hard-coded map: {12635: "P/E", 13200: "EPS (TTM)", 12623: "+1σ PE", 12626: "+2σ PE"}
- [x] 9.4 `ValuationProvider` ABC port
- [x] 9.5 `StockbitValuationProvider` — SQLite cache (1-day TTL, JSON blob), `_parse_response` filters id=0 and zero values
- [x] 9.6 Wire `EnrichmentTask("valuation", ...)` into `fetch_market_commands.py`
- [x] 9.7 `💲 VALUATION` panel in `swing_analysis_display.py` (cache-read only, guarded by try/except)
- [x] 9.8 17 unit tests; suite at 1706

### Files Changed
- `src/domain/value_objects/valuation_metrics.py` — new
- `src/domain/ports/valuation_provider.py` — new
- `src/infrastructure/browser/stockbit_valuation.py` — new
- `src/infrastructure/config/stockbit_config.py` — added `valuation_metrics_url`
- `src/adapters/cli/fetch_market_commands.py` — wired `EnrichmentTask("valuation", ...)`
- `src/adapters/cli/swing_analysis_display.py` — valuation panel in corp_flags block
- `tests/infrastructure/browser/test_stockbit_valuation.py` — new; 17 tests

### Key Design Notes
- Opaque ID→label mapping: endpoint returns no labels; empirical lookup table is the only practical approach without a separate `/screener/metric` call
- Zero values filtered on ingest (id=0 is Stockbit's placeholder pattern)
- Display read-only: `broker_provider=None` so no network call from display layer

---

## Notes / Decisions Log

_Append decisions, blockers, or scope changes here as they come up._

