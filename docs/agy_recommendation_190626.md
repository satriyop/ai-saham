# AGY Data Storage & Quality Recommendations
Date: 2026-06-19

This document outlines structural database schema and data flow recommendations to resolve current consistency bugs and expand the analytical capabilities of the local SQLite storage using available Stockbit Exodus and public IDX endpoints.

---

## Executive Summary

The system currently possesses a mix of aggregate foreign-flow statistics and specific per-broker transaction detail. However, our vetting of the database and code revealed:
1. **A critical database impurity** where Yahoo Finance stores volume in *shares* while IDX stores it in *lots*.
2. **Opportunities for strategy expansion** using already identified Stockbit endpoints that are currently unutilized, such as DCF valuation metrics, broker concentration ratios, and individual analyst target adjustments.
3. **Hardcoding risks** where broker codes and classifications are hardcoded into Python source code rather than driven by dynamic database references.

Implementing these recommendations will protect mathematical integrity, enhance auditability, and enable sophisticated screening rules.

---

## Technical Recommendations

### 1. Unified Volume Normalization (Candles Table)

*   **Problem**: `candles.volume` holds mixed units. `YahooFinanceProvider` writes raw shares (e.g., 5,000,000) while `IdxMarketDataProvider` writes lots (e.g., 50,000).
*   **Impact**: Any calculation involving volume (e.g., VWAP, Volume breakouts, volume-weighted indicators) behaves unpredictably if providers are mixed.
*   **Proposed Schema Change**: Update [sqlite_market_repository.py](file:///Users/satriyo/dev/ai-saham/src/infrastructure/persistence/sqlite_market_repository.py) to standardise volume or enforce a unit column:
    ```sql
    -- Normalised to raw shares:
    ALTER TABLE candles ADD COLUMN volume_unit TEXT NOT NULL DEFAULT 'shares';
    ```
*   **Resolution Strategy**: Normalise everything to **shares** inside `MarketDataRepository` implementations upon upsert. For IDX, multiply by 100 before saving.

---

### 2. DCF Valuation & Scenario Caching (`valuation_cache`)

*   **Problem**: Stockbit computes sophisticated intrinsic values, WACCs, and margin-of-safety parameters under different scenarios, but these are currently ephemeral and not stored.
*   **Proposed Schema**:
    ```sql
    CREATE TABLE IF NOT EXISTS valuation_cache (
        ticker           TEXT PRIMARY KEY,
        intrinsic_value  TEXT NOT NULL,  -- Base DCF Value (Decimal)
        bull_value       TEXT,           -- Bull scenario (Decimal)
        bear_value       TEXT,           -- Bear scenario (Decimal)
        wacc             REAL,           -- Weighted Average Cost of Capital (e.g. 0.085)
        margin_of_safety REAL,           -- Safety margin % (e.g. 0.18)
        fetched_date     TEXT NOT NULL
    );
    ```
*   **Analytical Value**: Enables fundamental filters (e.g., *Find tickers with positive swing flow AND selling at a >15% margin of safety to DCF intrinsic value*).

---

### 3. Broker Concentration & Dominance Cache (`broker_concentration_cache`)

*   **Problem**: "Bandar" or market maker accumulation is characterized by a small number of brokers controlling the majority of daily volume (CR5/CR10 concentration ratio). The client-side calculator has no database cache to backtest this.
*   **Proposed Schema**:
    ```sql
    CREATE TABLE IF NOT EXISTS broker_concentration_cache (
        ticker       TEXT NOT NULL,
        period       TEXT NOT NULL, -- '1D', '1W', '1M'
        top_5_ratio  REAL NOT NULL, -- CR5 Dominance % (0.0 to 1.0)
        top_10_ratio REAL NOT NULL, -- CR10 Dominance %
        fetched_date TEXT NOT NULL,
        PRIMARY KEY (ticker, period)
    );
    ```
*   **Source Endpoint**: `GET /order-trade/broker/distribution`

---

### 4. Dynamic Broker Directory (`broker_directory`)

*   **Problem**: The list of institutional proxy codes and names is hardcoded into `playwright_stockbit.py`. If a broker license shifts or a domestic code starts behaving as institutional, code edits are required.
*   **Proposed Schema**:
    ```sql
    CREATE TABLE IF NOT EXISTS broker_directory (
        code        TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        type        TEXT NOT NULL,     -- 'Asing' (Foreign) / 'Lokal' (Domestic)
        is_proxy    INTEGER DEFAULT 0, -- 1 = included in institutional proxy flow
        last_update TEXT DEFAULT CURRENT_TIMESTAMP
    );
    ```
*   **Source Endpoint**: `GET /findata-view/marketdetectors/brokers`
*   **Impact**: Decouples domain indicators from static code definitions.

---

### 5. Quarterly Earnings Surprises (`earnings_surprises`)

*   **Problem**: Swing strategies are highly sensitive to earnings announcements. Post-earnings drift can be systematically traded if the surprise percentage is known.
*   **Proposed Schema**:
    ```sql
    CREATE TABLE IF NOT EXISTS earnings_surprises (
        ticker            TEXT NOT NULL,
        year              INTEGER NOT NULL,
        quarter           INTEGER NOT NULL,
        eps_actual        TEXT NOT NULL,
        eps_estimate      TEXT,
        eps_surprise_pct  REAL,
        announcement_date TEXT,
        PRIMARY KEY (ticker, year, quarter)
    );
    ```
*   **Source Endpoint**: `GET /earnings?search={ticker}`

---

### 6. Historical Analyst Price Target Revisions (`analyst_ratings_history`)

*   **Problem**: The existing `analyst_cache` only keeps a snapshot of the current consensus target. We cannot audit target revisions (momentum indicator for target upgrades).
*   **Proposed Schema**:
    ```sql
    CREATE TABLE IF NOT EXISTS analyst_ratings_history (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker        TEXT NOT NULL,
        analyst_name  TEXT NOT NULL,
        firm          TEXT NOT NULL,
        rating        TEXT NOT NULL, -- 'BUY', 'HOLD', 'SELL'
        target_price  TEXT,          -- Target price in IDR
        rating_date   TEXT NOT NULL,
        created_at    TEXT DEFAULT CURRENT_TIMESTAMP
    );
    ```
*   **Source Endpoint**: `GET /analyst-ratings/{ticker}`

---

## Architectural Alignment (Hexagonal Structure)

These improvements should follow the Ports and Adapters architectural layers:

```
┌────────────────────────────────────────────────────────────────────────┐
│                                ADAPTERS                                │
│  - update_commands.py / broker_commands.py                             │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                              APPLICATION                               │
│  - RefreshMarketDataUseCase (orchestrates valuation/concentration)    │
│  - SaveValuationUseCase, SaveBrokerDirectoryUseCase                    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                             INFRASTRUCTURE                             │
│  - SQLiteBrokerRepository (upserts into new cache tables)               │
│  - StockbitPlaywrightBrokerProvider (maps JSON to new Domain entities) │
└────────────────────────────────────────────────────────────────────────┘
```

1.  **Domain Layer**: Define pure immutable Value Objects and Entities for `Valuation`, `BrokerConcentration`, `EarningsSurprise`, and `AnalystRating`.
2.  **Application Layer**: Create use cases to process, validate, and orchestrate the timing/rules of fetches (e.g. `needs_refresh`).
3.  **Infrastructure Layer**: Implement concrete database operations in the repositories (like `SQLiteBrokerRepository`) to save/retrieve from the new tables. Update the Playwright adapters to make the network calls and serialize them into domain models.

## Codex Response

This recommendation is directionally good, especially the first item. The mixed candle volume-unit issue is a real structural risk: Yahoo writes volume as raw shares, while IDX writes volume as lots. Normalizing IDX lots to shares before persistence is the right target.

Main concerns:

1. The document jumps to new feature caches before fixing existing quality gates.
   DCF, earnings, broker concentration, and analyst history are useful, but they should come after source preference, stale data, bad-denominator handling, and candle provenance are fixed. Otherwise, the system adds more signals on top of inconsistent foundations.

2. The candle migration proposal is incomplete.
   Adding `volume_unit DEFAULT 'shares'` does not fix existing IDX rows already stored as lots. The schema should also include `source`, `price_adjustment_policy`, and a migration/audit path. Existing rows may not be safely inferable without provider provenance.

3. `broker_concentration_cache` is not backtest-ready as written.
   The proposed primary key `(ticker, period)` overwrites history. If the goal is backtesting CR5/CR10, the table needs at least `as_of_date` or `session_date`, plus `source`, `market_board`, `investor_type`, and probably `data_type`.

4. The hardcoded broker-code issue is real, but slightly overstated.
   Some broker-code behavior is already config-driven through Stockbit/swing config paths, while `TIER1_FOREIGN_BROKERS` still exists in application code. A `broker_directory` is useful, but classification policy should remain explicit and reviewable, not blindly updated from Stockbit.

5. DCF valuation needs stronger provenance.
   Stockbit-computed intrinsic values should be contextual, not authoritative. The cache should include scenario assumptions, currency, model/source version, current price at fetch, fetched timestamp, and ideally a raw JSON hash. Otherwise, margin-of-safety output can look more deterministic than it really is.

6. The architecture section is mostly aligned, but valuation/concentration orchestration should not be folded into `RefreshMarketDataUseCase`.
   Prefer separate use cases such as `RefreshValuationCacheUseCase`, `RefreshBrokerConcentrationUseCase`, and `RefreshAnalystRatingsHistoryUseCase`. `saham fetch market` can coordinate them, but the market refresh use case should not become a growing monolith.

Recommended sequencing:

1. Fix broker summary source preference consistency.
2. Add deterministic data-quality audit.
3. Add candle provenance and unit normalization.
4. Add stale-data and enrichment-completeness reporting.
5. Add AGY's feature-expansion caches after the quality layer is in place.

Overall: keep this document as a Phase 2 feature-expansion proposal. The immediate Phase 1 should be the quality layer: broker source preference consistency, data audit, candle provenance/unit normalization, stale-data handling, and enrichment completeness reporting.
