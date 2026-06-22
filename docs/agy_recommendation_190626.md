# AGY Data Storage & Quality Recommendations — Implementation Status

This document tracks the recommendations for data storage and quality improvements, updated with their current implementation status based on the latest codebase review and SQLite database inspection as of June 20, 2026.

---

## 1. Executive Summary of Statuses

A series of major commits (up to commit `1c7b88d`) have resolved the high-priority data consistency bugs and implemented several silent data gaps. Other feature-expansion recommendations have been safely deferred to maintain architecture boundaries and prevent duplicate schemas.

---

## 2. Recommendation Status List

### 1. Unified Volume Normalization (Candles Table)
*   **Recommendation**: Standardise volume units between Yahoo Finance (shares) and IDX (lots) or add a volume unit tracker.
*   **Current Status**: **✅ RESOLVED / CLOSED**
*   **Details**: 
    *   Cross-checks of actual trades confirm both yfinance and IDX write daily candle volumes in **shares** (no 100x lot-calculation bug exists in the active providers).
    *   The `candles` table schema has been migrated to include `source`, `volume_unit`, and `price_adjustment_policy` columns.
    *   21,420 historical candle rows have been successfully backfilled/tagged with `volume_unit='shares'` and `source='yahoo_inferred'`, and new daily fetches automatically write `source='yahoo'` with `volume_unit='shares'`.

---

### 2. DCF Valuation & Scenario Caching (`valuation_cache`)
*   **Recommendation**: Cache intrinsic DCF values, scenarios (Bull/Bear), and margins of safety to allow fundamental screening.
*   **Current Status**: **💤 DEFERRED (Feature Expansion)**
*   **Details**: Stockbit’s `/valuation/company/{ticker}` endpoint shape remains unprobed/unverified. To avoid coding speculative schemas, this has been deferred.

---

### 3. Broker Concentration & Dominance Cache (`broker_concentration_cache`)
*   **Recommendation**: Store CR5/CR10 broker volume dominance ratios to track institutional concentration.
*   **Current Status**: **✅ RESOLVED / DEFERRED**
*   **Details**: Already fully implemented under the `bandar_detector` table and the `StockbitBandarDetectorProvider`, which caches `top1_percent`, `total_buyer`, and `total_seller`. To avoid duplicate schemas and maintenance bloat, creating a new `broker_concentration_cache` table has been deferred as redundant.

---

### 4. Dynamic Broker Directory (`broker_directory`)
*   **Recommendation**: Cache full broker code-to-name mapping from Stockbit to avoid hardcoded broker sets in source code.
*   **Current Status**: **💤 DEFERRED**
*   **Details**: The current configuration-driven YAML setup (`config/data_sources.yaml` and `config/universes.yaml`) is sufficient and less complex.

---

### 5. Quarterly Earnings Surprises (`earnings_surprises`)
*   **Recommendation**: Cache historical EPS actuals vs. estimates and surprise percentages.
*   **Current Status**: **💤 DEFERRED (Feature Expansion)**
*   **Details**: The endpoint remains unprobed; deferred until the strategy use case requires it.

---

### 6. Historical Analyst Price Target Revisions (`analyst_ratings_history`)
*   **Recommendation**: Store individual analyst updates chronologically to track price target momentum.
*   **Current Status**: **❌ NOT POSSIBLE / DEFERRED**
*   **Details**: 
    *   The `/analyst-ratings/{ticker}` endpoint was live-probed and verified on June 20, 2026.
    *   It returns strictly aggregate consensus data (`total_buy`, `total_hold`, `total_sell`, `price_target` average/low/high, `last_updated`).
    *   It does *not* contain individual analyst names, rating cards, or historical timeline data. Without a separate, detailed individual ratings endpoint, caching analyst revisions history is not feasible.

---

## 3. Recently Implemented Stockbit Silent Data Gaps (Priority 2)

As of June 20, 2026, the following high-priority data gaps from the API probes have been implemented in the codebase (Commit `d2c04d8`):

*   **Market Time Session Parsing**: Corrected path references for `/market-time` (properly reads the exchange session status using `body["data"]["market"]["status"]` and sub-session status keys).
*   **Stock Split Action Types**: Fixed `_TYPE_MAP` in `stockbit_corp_action.py` to recognise the `"stocksplit"` key sent by the API, preventing splits from being dropped.
*   **Bandar Detector Enrichment**: Extended `BandarDetectorSnapshot` to parse and store `top3`, `top5`, `top10` acc/dist metrics and overall broker numbers, rather than just `top1`.
*   **ARA/ARB auto-reject limits**: Added `ara_price` and `arb_price` boundaries to `OrderBookSnapshot` and domain logic.
*   **Intraday Foreign/Domestic split**: Extracted `foreign_pct` and `domestic_pct` from order book responses.
*   **Single-Call Foreign Flow Backfill**: Integrated `/company-price-feed/historical/summary/{ticker}` to read exact aggregated daily foreign flow in a single API call, reducing backfill time by ~15x.
*   **Forward Estimates Consensus**: Built `StockbitForwardEstimatesProvider` to parse `/consensus` list data and cache forward EPS/Revenue estimates.
