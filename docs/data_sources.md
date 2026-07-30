# Data Sources

AI Saham uses a provider abstraction to fetch market data. This document explains how data flows through the system.

---

## Provider Ports

The system uses two port interfaces for data access, both following the port/adapter pattern:

| Port | Purpose | Implementations |
|------|---------|-----------------|
| `MarketDataProvider` | OHLCV candle data | YahooFinanceProvider, IdxMarketDataProvider |
| `BrokerDataProvider` | Foreign flow + broker breakdown | IdxBrokerDataProvider, StockbitPlaywrightBrokerProvider |

```
Domain Port                    Infrastructure Adapters
-----------                    -----------------------
MarketDataProvider  <-------   YahooFinanceProvider 
                    <-------   IdxMarketDataProvider

BrokerDataProvider  <-------   IdxBrokerDataProvider
                    <-------   StockbitPlaywrightBrokerProvider

CsvBrokerParser     <-------   BrokerCsvAdapter (import only)
```

This allows:
- Swapping providers without changing domain logic
- Supporting multiple data sources
- Testing with mock providers

---

## Market Data Providers (OHLCV)

### Yahoo Finance (Default)

**Provider:** `YahooFinanceProvider`

- **Data type:** Daily OHLCV (Open, High, Low, Close, Volume)
- **Source:** Yahoo Finance (unofficial API via yfinance)
- **Market suffix:** `.JK` for Indonesia Stock Exchange (auto-appended)

**Limitations:**
- Data may be delayed (not real-time)
- Unofficial source (no SLA)
- Daily data only (no intraday)

**Usage:**
```bash
saham fetch market BBCA --days 365          # Fetches BBCA.JK via Yahoo (default)
saham fetch market BBRI --days 730
```

### IDX Public API

**Provider:** `IdxMarketDataProvider`

- **Data type:** Daily OHLCV (Open, High, Low, Close, Volume) — raw (unadjusted) prices
- **Source:** IDX TradingSummary API (`idx.co.id`)
- **Auth:** None required

**Advantages over Yahoo:**
- Same-day availability (data published on trading day)
- Raw prices (no adjustment artifacts)
- No `.JK` suffix needed

**Tradeoffs:**
- Slower for large date ranges (one HTTP request per trading day, rate-limited to 1s delay)
- Non-trading days return 403 (handled silently)
- Volume is normalized to raw shares before persistence, matching Yahoo's stored unit.

**Usage:**
```bash
saham fetch market BBCA --days 30 --provider idx              # Uses IDX public API
saham fetch market BBCA --days 30 --provider idx              # Faster for small ranges
```

---

## Broker Data Providers (Foreign Flow)

The system has **two tiers** of broker/foreign-flow data with different granularity and accuracy.
All four SQLite broker tables and their exact column schemas are documented below.

### Provider Comparison

| Capability | IDX (`IdxBrokerDataProvider`) | Stockbit (`StockbitPlaywrightBrokerProvider`) | CSV Import (`BrokerCsvAdapter`) |
|---|---|---|---|
| Auth required | None | Browser session (`saham fetch stockbit login`) | None (file-based) |
| Foreign buy/sell lots | **Exact** (from `ForeignBuy`/`ForeignSell` fields, ÷100 for lots) | **Exact** | If provided |
| Foreign buy/sell value | **Estimated** (volume × closing price × 100) | **Exact** (from broker transactions) | If provided |
| Total trading value | **Exact** (from `Value` field) | **Synthetic** (sum of broker values, ~72% of true) | If provided |
| Per-broker breakdown | **Not available** (empty top_buyers/top_sellers) | **Yes** (up to 25 per side, top 10 stored in JSON) | SIMPLE=no, DETAILED=yes |
| Per-day per-broker time-series | **Not available** | **Yes** (15 tracked brokers, 365d history via paginated API) | **Not available** |
| Source tag written to DB | `"idx"` | `"stockbit"` | `"csv-idx"` / `"csv-stockbit"` |

### IDX Public API

**Provider:** `IdxBrokerDataProvider`

- **Endpoint:** `https://www.idx.co.id/primary/TradingSummary/GetStockSummary?date=YYYYMMDD`
- **Rate limit:** 1s between requests, 3 retries with backoff
- **Data for each ticker on each date:** `ForeignBuy` (shares), `ForeignSell` (shares), `Value` (IDR), `Volume` (shares)
- **Foreign flow value is estimated** because IDX only provides share counts, not transaction values. The provider computes `foreign_buy_value = ForeignBuy × ClosePrice` and `foreign_sell_value = ForeignSell × ClosePrice`.
- **Foreign flow lots are exact** (`ForeignBuy / 100`, `ForeignSell / 100`).
- **Per-broker breakdown NOT available** — `top_buyers` and `top_sellers` are always empty tuples `()`.

**Usage:**
```bash
saham fetch broker BBCA                # Defaults to IDX (no auth, --provider idx)
saham fetch broker BBCA --days 90
```

### Stockbit

**Provider:** `StockbitPlaywrightBrokerProvider`

- **Data source:** Stockbit Exodus API (`exodus.stockbit.com`), accessed via Bearer token extracted from browser session
- **Auth:** Playwright persistent browser profile (`.stockbit_profile/`). Token TTL ~8-12h, in-process cache 30min.
- **3 distinct API endpoints** used, each serving different data:

| Endpoint | Used For | Writes Table |
|---|---|---|
| `/marketdetectors/{ticker}` | Per-stock top 25 net buyers/sellers | `broker_summaries` (source=`"stockbit"`) |
| `/order-trade/broker/activity/historical?broker_codes={code}&symbols={ticker}` | Per-broker per-day timeseries (15 tracked brokers) | `broker_daily_flow` (source=`"stockbit"`) |
| Same historical endpoint, but aggregated across 10 institutional proxy broker codes | Daily net foreign flow time-series | `foreign_flow_points` (source=`"stockbit"`) |

**Setup:**
```bash
saham fetch stockbit login
```

**Usage:**
```bash
saham fetch broker BBCA --provider stockbit   # Richer per-broker detail
saham view ticker top-brokers BBCA --date 2024-01-15
```

### CSV Import

**Provider:** `BrokerCsvAdapter` (via `saham fetch broker-import FILE`)

- **Formats:** SIMPLE (aggregate flow) or DETAILED (per-broker transactions)
- **Auto-detection:** FormatDetector compares header sets against known patterns
- **Source tag:** `"csv-idx"` for SIMPLE, `"csv-stockbit"` for DETAILED
- **Date formats supported:** ISO, DD/MM/YYYY, MM/DD/YYYY, DD-MM-YYYY, YYYYMMDD

**Usage:**
```bash
saham fetch broker-import data.csv               # Auto-detect format
saham fetch broker-import data.csv --preview     # Validate before import
saham view broker mappings                      # List available column mappings
```

---

## Caching Strategy

### Local-First Caching

Data is cached locally after first fetch to enable **offline analysis**.

**Storage:** SQLite database at `./data.db` (configurable via `--db`)

**Cache behavior:**

| Action | Network Required | Result |
|--------|------------------|--------|
| First fetch | Yes | Downloads and caches |
| Subsequent analysis | No | Uses cached data |
| `--refresh` flag | Yes | Re-downloads and updates cache |

### Cache Structure

```sql
-- Each ticker gets its own data
SELECT ticker, date, open, high, low, close, volume
FROM candles
WHERE ticker = 'BBCA'
ORDER BY date;
```

### Data Source Reference

> `saham fetch market` has two independent provider flags:
> - `--provider` → candles source (default: `yahoo`)
> - `--broker-provider` → broker flow source (default: auto-detect Stockbit → IDX)

| Data | Written By (Command) | Written By | Table |
|------|---------------------|------------|-------|
| **Daily OHLCV prices** | `saham fetch market` | `RefreshMarketDataUseCase` | `candles` |
| **Daily OHLCV prices (IDX)** | `saham fetch market --provider idx` | `RefreshMarketDataUseCase` | `candles` |
| **Aggregated foreign flow + summary** | `saham fetch market` / `saham fetch broker TICKER` | `RefreshBrokerDataUseCase` / `FetchBrokerDataUseCase` | `broker_summaries` |
| **Per-broker per-day time-series** | `saham fetch market` (auto) / `saham fetch broker TICKER --provider stockbit` | `FetchBrokerDailyFlowsUseCase` | `broker_daily_flow` |
| **Net foreign flow time-series** | `saham fetch market` / `saham fetch broker TICKER` / `saham fetch broker-history TICKER` | Derived from summaries (Path A) + Stockbit historical (Path B) | `foreign_flow_points` |
| **Foreign broker universe scan** | `saham fetch broker-top-foreign` | `StockbitPlaywrightBrokerProvider.fetch_foreign_top_stocks()` | `foreign_flow_snapshots` |
| **Pre-open IEV snapshot (latest)** | `saham fetch iev` | `collect_iev()` (CLI adapter calls infrastructure directly) | `iev_snapshots` |
| **IEV snapshot history (append log)** | `saham fetch iev` | `collect_iev()` (appended on every run) | `iev_snapshot_history` |
| **Sector/industry metadata** | `saham fetch market` | `FetchMarketRefreshUseCase._fetch_meta()` | `stock_meta` |
| **Ticker notation, listing board, UMA** | `saham fetch market` (enrichment) | `StockbitTickerNotationProvider` | `ticker_notation_cache` |
| **Analyst consensus (buy/hold/sell)** | `saham fetch market` (enrichment) | `StockbitAnalystConsensusProvider` | `analyst_cache` |
| **Insider transactions** | `saham fetch market` (enrichment) | `StockbitInsiderActivityProvider` | `insider_cache` |
| **Seasonality (monthly return patterns)** | `saham fetch market` (enrichment) | `StockbitSeasonalityProvider` | `seasonality_cache` |
| **Corporate action calendar** | `saham fetch market` (enrichment) | `StockbitCorporateActionRepository` | `corp_action_cache` |
| **Shareholding composition** | `saham fetch market` (enrichment) | `StockbitShareholdingProvider` | `shareholding_composition` |
| **Bandar detector (acc/dist scores)** | `saham fetch market` (enrichment) | `StockbitBandarDetectorProvider` | `bandar_detector` |
| **Fundamental ratios (P/E, ROE, etc.)** | `saham fetch market` (enrichment) | `StockbitFundamentalsProvider` | `company_fundamentals` |
| **AI sentiment classification** | `saham analyze sentiment` | `SentimentAnalysisUseCase` | `sentiment_logs` |
| **Sentiment price outcome** | `saham analyze audit` | `SentimentAuditUseCase` | `sentiment_audits` |

---

## Broker Data Flow — Detailed Trace

### Four SQLite Tables for Broker Data

#### 1. `broker_summaries` — Daily Aggregated Foreign Flow

**PK:** `(ticker, date, source)` — multiple sources can coexist for same (ticker, date)

| Column | Type | Content | Source Detail |
|--------|------|---------|---------------|
| `ticker` | TEXT | Stock code | |
| `date` | TEXT | Trading date (ISO) | |
| `source` | TEXT | `"idx"` / `"stockbit"` / `"csv-idx"` / `"csv-stockbit"` | **IDX** = public API; **stockbit** = Stockbit marketdetectors endpoint (source=`"stockbit"` via `provider_name`) |
| `foreign_buy_value` | TEXT (Decimal) | Total foreign buy IDR | IDX: estimated (shares * close); Stockbit: exact |
| `foreign_sell_value` | TEXT (Decimal) | Total foreign sell IDR | Same estimation difference |
| `foreign_buy_lot` | INTEGER | Foreign buy lots (shares/100) | Both exact |
| `foreign_sell_lot` | INTEGER | Foreign sell lots | |
| `total_value` | TEXT (Decimal) | Total market trade value IDR | IDX: **exact**; Stockbit: synthetic (sum of broker values, ~72% accuracy) |
| `total_lot` | INTEGER | Total lots | |
| `top_buyers_json` | TEXT (JSON null) | Top 10 net buyers `[BrokerTransaction]` | IDX: **null** (no per-broker data); Stockbit: populated |
| `top_sellers_json` | TEXT (JSON null) | Top 10 net sellers | Same |
| `created_at` | TEXT | Insert/update timestamp | Auto |

**Writes to this table:**

| Command | Provider | Source | top_buyers_json |
|---------|----------|--------|-----------------|
| `saham fetch market` (via `RefreshBrokerDataUseCase`) | `IdxBrokerDataProvider` **always** | `"idx"` | `null` |
| `saham fetch broker TICKER` (via `FetchBrokerDataUseCase`) | `--provider idx` | `"idx"` | `null` |
| `saham fetch broker TICKER --provider stockbit` | `StockbitPlaywrightBrokerProvider` | `"stockbit"` | populated |
| `saham fetch broker-import FILE` (SIMPLE) | `BrokerCsvAdapter` | `"csv-idx"` | `null` |
| `saham fetch broker-import FILE` (DETAILED) | `BrokerCsvAdapter` | `"csv-stockbit"` | populated |

**Reads from this table:**

| Command / Use Case | How | What Columns/Fields Used |
|--------------------|-----|--------------------------|
| `saham screen accum` (via `AccumulationScreenUseCase`) | `get_broker_summaries(ticker)` with `source=None` → dedup to 1 row per date, prefers IDX (`MIN(source)` = `"idx"`) | `foreign_buy_value`, `foreign_sell_value` → **foreign_net_value** (for streak, ratio, VWAP); `foreign_buy_lot` → VWAP denom; `total_value` → flow ratio; `date` → window filter |
| `saham analyze swing TICKER` (via `build_flow_detail`) | `get_broker_summaries(ticker, end_date=as_of)` | `foreign_net_value` → total net flow, buy/sell session count, streak; `foreign_flow_ratio` → avg ratio |
| `saham analyze swing TICKER` (via `build_broker_detail`, **fallback**) | `get_broker_summaries(ticker)` if `broker_daily_flow` empty | `top_buyers_json`, `top_sellers_json` → deserialized to `BrokerTransaction[]` for per-broker attribution |
| `saham view ticker flow TICKER` (via `GetBrokerDataUseCase`) | `get_broker_summaries(ticker, ...)` | All columns → display |
| `saham view ticker top-brokers TICKER` | `get_broker_summary(ticker, target_date)` | `top_buyers_json`, `top_sellers_json` → top buyers/sellers list |
| `saham analyze regime` (via `MarketRegimeUseCase._foreign_flow_breadth`) | `get_broker_summaries(ticker)` for each universe ticker | Only `summaries[-1].foreign_net_value` (latest date only) for foreign flow breadth % |
| `saham screen pre-open` (via `PreOpenScreenUseCase._assess_broker_signals`) | `get_broker_summaries(ticker, start=cutoff)` | `is_foreign_accumulating` → buy day count & streak tag; `foreign_buy_value` + `foreign_buy_lot` → Foreign VWAP |

**Source preference when reading:** IDX (`"idx"`) is preferred over Stockbit because IDX `total_value` is exact. The repository uses `MIN(source)` per (ticker, date) — alphabetically `"csv-idx"` < `"idx"` < `"stockbit"`. Stockbit rows are **deleted** when a matching IDX row exists for the same (ticker, date).

---

#### 2. `broker_daily_flow` — Tracked-Broker Per-Day Time-Series

**PK:** `(ticker, date, broker_code, source)`

**Scope:** This table stores Stockbit per-day rows for the configured tracked
broker codes only. It is **not** exhaustive full-market broker composition and
must not be used or displayed as if it covers every broker. User-facing outputs
should call derived values "tracked broker flow" unless a separate full
top-broker source is used.

| Column | Type | Content |
|--------|------|---------|
| `ticker` | TEXT | Stock code |
| `date` | TEXT | Trading date (ISO) |
| `broker_code` | TEXT | Broker identifier (e.g. `"AK"`, `"YP"`, `"MS"`) |
| `broker_name` | TEXT | Human-readable name |
| `source` | TEXT | Always `"stockbit"` |
| `buy_lot` | INTEGER | Lots bought by this broker |
| `sell_lot` | INTEGER | Lots sold |
| `net_lot` | INTEGER | Net lots (positive = net buyer) |
| `buy_value` | TEXT (Decimal) | Buy value IDR |
| `sell_value` | TEXT (Decimal) | Sell value IDR |
| `net_value` | TEXT (Decimal) | Net value IDR |
| `avg_buy_price` | TEXT (Decimal) | Avg buy price per share |
| `avg_sell_price` | TEXT (Decimal) | Avg sell price per share |
| `avg_price` | TEXT (Decimal) | Avg net price (dominant side) |
| `buy_pct` | REAL | Broker's buy lots as % of total market buy lots |
| `sell_pct` | REAL | Broker's sell lots as % of total market sell lots |
| `created_at` | TEXT | Timestamp |

**Writes:** ONLY `StockbitPlaywrightBrokerProvider` via `FetchBrokerDailyFlowsUseCase`. Triggered by:
- `saham fetch market` (auto when Stockbit provider active)
- `saham analyze swing TICKER --auto-refresh` (same path)
- NOT available from standalone `saham fetch broker TICKER` (which only writes `broker_summaries`)

The provider queries `/order-trade/broker/activity/historical` once per tracked broker code (configured subset), paginated (100 records/page), up to 365 days. Source=`"stockbit"`.

**Reads:**

| Command / Use Case | How | What Used |
|--------------------|-----|-----------|
| `saham screen accum` (via `AccumulationScreenUseCase._broker_quality_by_ticker`) | `get_broker_daily_flows(ticker, end_date)` | `broker_code` → BCI tier classification (CLUSTER/STABLE/RETAIL); `net_lot` → per-broker net aggregation |
| `saham analyze swing TICKER` (via `build_broker_detail`, **preferred path**) | `get_broker_daily_flows(ticker, end_date)` | `broker_code`, `broker_name`, `net_value` → classified as "smart money", "noise", or "neutral" via named broker sets; `buy_value`, `sell_value` → buyer/seller detail display |

---

#### 3. `foreign_flow_points` — Net Foreign Flow Time-Series

**PK:** `(ticker, date, source)`

| Column | Type | Content |
|--------|------|---------|
| `ticker` | TEXT | Stock code |
| `date` | TEXT | Trading date (ISO) |
| `source` | TEXT | `"idx"` or `"stockbit"` |
| `net_val` | TEXT (Decimal) | Net foreign value (positive = net buy) |
| `net_lot` | INTEGER | Net foreign lots |
| `avg_price` | TEXT (Decimal) | Average price. IDX: always `0`; Stockbit: exact from API |
| `created_at` | TEXT | Timestamp |

**Populated by TWO independent code paths:**

| Path | Trigger | Source | avg_price | Description |
|------|---------|--------|-----------|-------------|
| **A (Derived from summaries)** | Every `FetchBrokerDataUseCase.execute()` — always runs when `broker_summaries` are saved | `"idx"` (from IDX provider) | `0` | `ForeignFlowPoint(ticker, date, net_val=foreign_buy_value-foreign_sell_value, net_lot=foreign_buy_lot-foreign_sell_lot, avg_price=0, source="idx")` |
| **B (Stockbit historical)** | `RefreshBrokerDataUseCase._refresh_foreign_flow_history()` — runs during `saham fetch market` and `saham fetch broker-history TICKER` | `"stockbit"` (from Stockbit provider name) | **Exact** | Fetched from Stockbit `/order-trade/broker/activity/historical?broker_codes=AK,ZP,...&symbols={ticker}` aggregated across 10 institutional proxy codes |

When called via standalone `saham fetch broker TICKER --provider stockbit`, the derived path (A) writes with source=`"stockbit"` (drawn from `StockbitPlaywrightBrokerProvider.provider_name`).

**Reads from this table:**
- `saham view ticker foreign-history TICKER` — the **only** reader of `foreign_flow_points`. Displays foreign net time-series.
- `RefreshBrokerDataUseCase` — reads it only for status reporting (count rows before/after).

**No analysis/screening command directly reads `foreign_flow_points`.** All accumulation, swing, regime, and pre-open analysis reads from `broker_summaries` instead.

---

#### 4. `foreign_flow_snapshots` — Universe Scan Cache

**PK:** `(ticker, snapshot_date, period_days, source)`

| Column | Type | Content |
|--------|------|---------|
| `ticker` | TEXT | Stock code |
| `snapshot_date` | TEXT | Date of snapshot |
| `period_days` | INTEGER | Lookback window (e.g. 7) |
| `source` | TEXT | Always `"stockbit"` |
| `net_val` | TEXT (Decimal) | Net foreign flow in period |
| `net_lot` | INTEGER | Net foreign lots |
| `created_at` | TEXT | Timestamp |

**Writes:** `saham fetch broker-top-foreign` → `StockbitPlaywrightBrokerProvider.fetch_foreign_top_stocks()` → queries `/order-trade/broker/activity?broker_code=AK,ZP,...` for top foreign-broker traded stocks across the universe.

**Reads:** `saham view broker top-foreign` — displays cached snapshot.

---

### Summary: Which Tables Each Analysis Command Reads

| Command | `broker_summaries` | `broker_daily_flow` | `foreign_flow_points` | `foreign_flow_snapshots` |
|---------|:---:|:---:|:---:|:---:|
| `saham screen accum` | **CORE** — net_buy_days, streak, VWAP, flow_ratio | **BCI** — per-broker tier analysis | — | — |
| `saham analyze swing TICKER` | **CORE** — flow detail stats | **PREFERRED** — per-broker attribution | — | — |
| `saham analyze regime` | **YES** — latest foreign_net_value per ticker | — | — | — |
| `saham screen pre-open` | **YES** — accumulation tag + Foreign VWAP | — | — | — |
| `saham trade backtest-swing` | **CORE** (via AccumulationScreenUseCase) | **BCI** (via AccumulationScreenUseCase) | — | — |
| `saham analyze swing-compare` | (via SwingBacktestUseCase) | (via SwingBacktestUseCase) | — | — |
| `saham research accum evaluate` | (via AccumulationAuditUseCase) | — | — | — |
| `saham view ticker flow` | **YES** — display | — | — | — |
| `saham view broker top` | **YES** — display top_buyers/sellers | — | — | — |
| `saham view ticker foreign-history` | — | — | **YES** — display | — |
| `saham view broker top-foreign` | — | — | — | **YES** — display |

### Source Preference When Reading

| Table | Preferred Source | Why |
|-------|----------------|-----|
| `broker_summaries` | **IDX** (`MIN(source)` → `"idx"`) | IDX `total_value` is exact; Stockbit synthetic ~72% of true. Stockbit rows are deleted when IDX row exists for same (ticker,date). |
| `foreign_flow_points` | **Stockbit** (`MAX(source)` → `"stockbit"`) | Stockbit `avg_price` is exact; IDX `avg_price` is always 0. Both sources coexist per (ticker,date). |

### Staleness Detection

The only TTL check is in `RefreshBrokerDataUseCase._summary_fetch_ranges()`:
1. Reads `get_date_range(ticker, source="idx")` → earliest and latest cached summary dates
2. If `earliest > requested_start + 7 days`: triggers **backfill** fetch from `requested_start` to `earliest - 1`
3. If `latest < last_trading_day` (determined from `^JKSE` candles): triggers **forward-fill** from `latest + 1` to `end_date`
4. If no data at all: **initial** full-range fetch

Analysis commands (`screen accum`, `analyze swing`, `screen pre-open`) have **no TTL checks** — they always read cached data only. Staleness is the caller's responsibility:
- `saham analyze swing` auto-refreshes by default (`--auto-refresh`)
- `saham screen accum` reads only — requires pre-warming via `saham fetch market`

### Foreign Flow Data Paths Diagram

For `saham fetch market BBCA` (the primary write path):

```
RefreshMarketDataUseCase::execute()
  │
  ├─ _fetch_candles() ─── YahooFinanceProvider ───→ candles table
  │
  └─ _fetch_broker() ─── RefreshBrokerDataUseCase::execute()
       │
       ├─ 1. _refresh_daily_flow() ─── FetchBrokerDailyFlowsUseCase
       │    └─ StockbitPlaywrightBrokerProvider.fetch_broker_daily_flows()
       │         └─ /order-trade/broker/activity/historical (15 broker codes)
       │         └─ UPSERT INTO broker_daily_flow (source="stockbit")
       │                      ↓
       │              [ONLY when Stockbit available]
       │
       ├─ 2. _summary_fetch_ranges() ─── checks broker_summaries date range for source="idx"
       │    └─ Computes backfill/forward/initial ranges
       │    └─ For each range: FetchBrokerDataUseCase(self._idx_summary_provider, repo)
       │         ├─ IdxBrokerDataProvider.fetch_broker_summaries()
       │         │    └─ GET /GetStockSummary?date=YYYYMMDD (1s rate-limited)
       │         ├─ UPSERT INTO broker_summaries (source="idx")
       │         └─ Derive ForeignFlowPoint from each summary
       │              └─ UPSERT INTO foreign_flow_points (source="idx", avg_price=0)
       │
       └─ 3. _refresh_foreign_flow_history() ─── StockbitPlaywrightBrokerProvider
            └─ fetch_foreign_flow_history(ticker, days)
                 └─ /order-trade/broker/activity/historical (10 institutional codes)
                 └─ UPSERT INTO foreign_flow_points (source="stockbit", avg_price=exact)
```

For standalone `saham fetch broker BBCA --provider stockbit`:

```
FetchBrokerDataUseCase::execute()
  │
  ├─ StockbitPlaywrightBrokerProvider.fetch_broker_summaries()
  │    └─ /marketdetectors/{ticker}?period=BROKER_SUMMARY_PERIOD_...
  │    └─ Returns BrokerSummary with top_buyers[10] + top_sellers[10]
  │
  ├─ UPSERT INTO broker_summaries (source="stockbit", top_buyers_json=populated)
  │
  └─ Derive ForeignFlowPoint from each summary
       └─ UPSERT INTO foreign_flow_points (source="stockbit", avg_price=0)
```

For standalone `saham fetch broker BBCA` (default, IDX):

```
FetchBrokerDataUseCase::execute()
  │
  ├─ IdxBrokerDataProvider.fetch_broker_summaries()
  │    └─ GET /GetStockSummary?date=YYYYMMDD
  │    └─ Returns BrokerSummary with empty top_buyers/top_sellers
  │
  ├─ UPSERT INTO broker_summaries (source="idx", top_buyers_json=null)
  │
  └─ Derive ForeignFlowPoint from each summary
       └─ UPSERT INTO foreign_flow_points (source="idx", avg_price=0)
```

---

## Data Flow

### Candle Fetch Flow

```
User: saham fetch market BBCA --days 365 --provider yahoo
         |
         v
CLI Adapter → FetchMarketRefreshUseCase
         |
         v
   RefreshMarketDataUseCase._fetch_candles()
         |
         +---> Check cache (SQLiteRepository)
         |           |
         |           v
         |     Has recent data + not --refresh?
         |           |
         |     No    |    Yes
         |           |        |
         v           v        v
   Provider selected by --provider flag
         |
         +--- Yahoo? ---> YahooFinanceProvider (Yahoo Finance API, .JK suffix)
         |
         +--- IDX?   ---> IdxMarketDataProvider (IDX TradingSummary API)
         |
         v
   Save to candles table (SQLiteRepository)
         |
         v
   Return Candle[]
```

### Broker Fetch Flow — `saham fetch market` (orchestrated batch)

```
User: saham fetch market BBCA --days 90 --broker-provider auto
         |
         v
CLI Adapter
         |
         v
RefreshBrokerDataUseCase (3 independent streams)
         |
         ├── 1. Daily per-broker flow ─── FetchBrokerDailyFlowsUseCase
         │        │
         │        └── StockbitPlaywrightBrokerProvider.fetch_broker_daily_flows()
         │             (15 broker codes, paginated to 365d)
         │             └── UPSERT broker_daily_flow (source="stockbit")
         │             [skipped if Stockbit not available]
         │
         ├── 2. IDX summaries ─── FetchBrokerDataUseCase(self._idx_summary_provider)
         │        │               ALWAYS uses IdxBrokerDataProvider
         │        │               Checks gaps: backfill old + forward-fill recent
         │        │
         │        └── IdxBrokerDataProvider.fetch_broker_summaries()
         │             (GET /GetStockSummary, 1s rate-limit, 3 retries)
         │             │
         │             ├── UPSERT broker_summaries (source="idx", top_buyers=null)
         │             └── Derive ForeignFlowPoint → UPSERT foreign_flow_points (source="idx", avg_price=0)
         │
         └── 3. Stockbit flow history ─── fetch_foreign_flow_history()
                  │
                  └── StockbitPlaywrightBrokerProvider.fetch_foreign_flow_history()
                       (10 institutional proxy codes, aggregated)
                       └── UPSERT foreign_flow_points (source="stockbit", avg_price=exact)
                       [skipped if Stockbit not available]
```

For `saham fetch broker TICKER` (standalone, single provider):

```
User: saham fetch broker BBCA --provider stockbit
         |
         v
FetchBrokerDataUseCase.execute()
         |
          ├── 1. Check cache for source="stockbit"
         │       └── Cached + not --refresh? Return from cache
         │
         ├── 2. Check auth
         │       └── is_authenticated() — Stockbit: browser session check
         │
         ├── 3. Fetch from provider
         │       └── StockbitPlaywrightBrokerProvider.fetch_broker_summaries()
         │            (/marketdetectors/{ticker}, top 25 buyers/sellers)
         │
          ├── 4. Save summaries
          │       └── UPSERT broker_summaries (source="stockbit",
          │            top_buyers_json=populated, top_sellers_json=populated)
          │
          └── 5. Derive flow points
                   └── UPSERT foreign_flow_points (source="stockbit", avg_price=0)
```

Default for `saham fetch broker TICKER` is `--provider idx` (no auth, estimated values, no per-broker detail).
Use `--provider stockbit` for per-broker detail and exact foreign values.

Note: `saham fetch market` and `saham fetch broker` use **different write paths**:
- `fetch market` always uses `IdxBrokerDataProvider` for summaries → source=`"idx"`
- `fetch broker` uses the selected provider → source varies by `--provider` flag

---

## IEV / Pre-Open Data

**Two related tables** store IEV (Indicative Equilibrium Value) mover rankings captured during the IDX pre-open auction window (08:45–09:00 WIB).

| Table | Type | Purpose |
|-------|------|---------|
| `iev_snapshots` | Upsert (canonical) | One row per (date, ticker) — always the latest snapshot. Backward-compatible reader table. |
| `iev_snapshot_history` | Append-only log | New row inserted on every `saham fetch iev` run. The earliest valid [08:56, 08:58) row supplies the locked baseline; all-session deltas remain diagnostic only. |

Both tables share the same columns: `date`, `ticker`, `iev` (volume), `rank`,
`iep` (price, nullable), `is_ncp_locked` (1 only inside the locked-input
[08:56, 08:58) window). The history table adds an auto-increment `id` and
`collected_at` timestamp. Matching-period rows from 08:58 onward are not locked
input and cannot supply production `delta_iev`.

**NCP sticky rule:** Once `is_ncp_locked` is set to 1 for a (date, ticker) in the canonical table, later pre-NCP runs cannot downgrade it to 0.

**Write path:** `saham fetch iev` calls `collect_iev()` in
`fetch_iev_commands.py`; the CLI adapter wires `PlaywrightStockbitProvider` and
`SQLiteIEVRepository`. The application pre-open workflow reads the locked
baseline through its narrow provider port.

---

## Stockbit Enrichment Caches

When `saham fetch market` runs with a Stockbit provider available, `_fetch_enrichment()` pre-populates 8 cache tables per ticker. These are **read-only** by analysis commands and have provider-specific TTL logic. An additional `stock_meta` table is populated by `_fetch_meta()`.

| Table | Populated By | TTL | Content |
|-------|-------------|-----|---------|
| `stock_meta` | `FetchMarketRefreshUseCase._fetch_meta()` | — | Sector/industry classification from Yahoo or IDX |
| `ticker_notation_cache` | `StockbitTickerNotationProvider` | Varies | Listing board (Main/Development/Acceleration), UMA flag, suspension info, corporate action status |
| `analyst_cache` | `StockbitAnalystConsensusProvider` | Varies | Buy/hold/sell counts + average price target |
| `insider_cache` | `StockbitInsiderActivityProvider` | Varies | Director/commissioner transactions (last 365 days) |
| `seasonality_cache` | `StockbitSeasonalityProvider` | Varies | Monthly average return %, win rate %, backtest window |
| `corp_action_cache` | `StockbitCorporateActionRepository` | Varies | Dividend/split/rights/warrant/bonus/tender events |
| `shareholding_composition` | `StockbitShareholdingProvider` | 7 days | Institutional vs individual ownership %, top holder |
| `bandar_detector` | `StockbitBandarDetectorProvider` | Daily | Broker accumulation/distribution scores |
| `company_fundamentals` | `StockbitFundamentalsProvider` | 7 days | P/E TTM, ROE, net profit margin, Piotroski F-Score, 52w high/low |

All enrichment tables are **per-ticker** caches. They are fetched during `saham fetch market` enrichment phase and consumed by analysis commands (`saham analyze swing`, `saham screen accum`, etc.) without network calls.

---

## Market-Wide Corporate Action Calendar

Distinct from the per-ticker `corp_action_cache` table above, `saham fetch calendar` (and `saham fetch market`, once per run) syncs Stockbit's **market-wide** corporate action calendar endpoints — one API call per event type covering every listed ticker at once, rather than one call per ticker.

**Supported v1 event types:** `dividend`, `stock_split`, `reverse_split`, `rights_issue`, `bonus`, `tender_offer`, `rups`, `pubex`, `ipo`.

**Explicitly not fetched in v1:** `warrant` (per-ticker warrant series, not a calendar concept) and `economic` (macro calendar, unrelated to corporate actions). Requesting either via `--types` is rejected with a CLI error.

**Tables:**

| Table | Purpose |
|-------|---------|
| `corporate_action_events` | One row per source event (dividend, split, rights issue, etc.), keyed by `(source, event_type, source_event_id, ticker)` |
| `corporate_action_event_dates` | One row per dated milestone of an event (`cum_date`, `ex_date`, `payment_date`, `rups_date`, etc.), keyed by `(source, event_type, source_event_id, ticker, date_role)` — an event may have several date rows |
| `corporate_action_calendar_sync` | Sync marker recording whether today's market-wide sync already ran for a given set of event types, so re-running `saham fetch market` does not re-hit the network |

**Write path:**

| Command | Trigger | Frequency |
|---------|---------|-----------|
| `saham fetch calendar` | Explicit, user-invoked | Once per invocation |
| `saham fetch market --universe lq45` | Automatic, when `broker_provider_name == stockbit` and neither `--no-enrichment` nor `--no-calendar` is set | Once per invocation (not once per ticker) |

**Freshness:** `saham fetch calendar` / `saham fetch market` skip the remote fetch when today's calendar has already been synced for the requested event types (tracked in `corporate_action_calendar_sync`). Use `--refresh` to force a remote re-fetch; `--refresh` re-fetches and upserts matching events, replacing their date rows, but never truncates the table or touches unrelated historical rows. A sync marked `"partial"` (some event types failed) does not count as synced — the next run automatically retries without needing `--refresh`.

**Read path:** query by ticker, by universe, or by date role via `CorporateActionCalendarRepository.get_events_for_ticker()` / `get_events_for_universe()` / `get_events_by_date_role()`.

**Limitation:** this data is stored as context only. It does not alter `SignalEngine`, `RiskEngine`, or any trading/screening decision.

### Event-Risk Context (`saham analyze swing TICKER`)

`AssessCorporateActionEventRiskUseCase` (`src/application/use_case/assess_corporate_action_event_risk_use_case.py`) turns the raw calendar rows above into a deterministic, config-driven event-risk assessment for a single ticker as of a date. It is read entirely from the local calendar tables — **no network call** — and is surfaced in `saham analyze swing TICKER` as a **Corporate Calendar** panel.

**Context only, not decision authority.** Corporate calendar event risk never changes `SignalEngine` scores, `RiskEngine` gates, or `TradeSetup.action`. The swing verdict chain remains exclusively `SignalEngine + RiskEngine -> TradeSetup` (ADR-026, ADR-032, ADR-033). This assessment is diagnostics/display evidence only, exactly like sentiment or sector context.

**Policy config:** `config/corporate_action_policy.yaml`, loaded by `src/infrastructure/config/corporate_action_policy_config.py`. For each event type, each relevant date role declares a `severity` (`none` / `info` / `warning` / `blocking`), a `lookback_days` / `lookahead_days` inclusion window, and zero or more risk `flags` (`price_distortion`, `volume_distortion`, `liquidity_distortion`, `special_situation`, `governance_context`, `disclosure_context`, `new_listing`). A missing config file falls back to deterministic defaults (identical to the shipped YAML); an existing-but-invalid config (unknown event type/date role/severity/flag, or a negative window) fails loudly at load time rather than silently falling back.

**Supported event types and date roles (defaults):**

| Event type | Date role(s) | Severity | Flags |
|---|---|---|---|
| `dividend` | `ex_date` | warning | `price_distortion` |
| `dividend` | `cum_date` | warning | `liquidity_distortion` |
| `rights_issue` | `cum_date`, `ex_date`, `trading_start` | warning | `price_distortion`, `liquidity_distortion` |
| `stock_split` / `reverse_split` / `bonus` | `ex_date` | warning | `price_distortion`, `volume_distortion` |
| `tender_offer` | `offer_start`, `offer_end` | warning | `special_situation` |
| `rups` | `rups_date` | info | `governance_context` |
| `pubex` | `pubex_date` | info | `disclosure_context` |
| `ipo` | `listing_date` | info | `new_listing` |

A date role not listed for its event type (e.g. dividend `payment_date`) is intentionally not matched — date roles are not interchangeable within an event type.

**Example output:**

```
Corporate Calendar
WARNING  dividend ex_date 2026-07-15 (+2d) price_distortion
INFO     rups rups_date 2026-07-18 (+5d) governance_context
```

When no configured event risk falls inside the assessment window: `Corporate Calendar: no configured event risk in window`.

### Analysis Flow

```
User: saham indicator compute SMA BBCA
         |
         v
CLI Adapter
         |
         v
ComputeSMAUseCase
         |
         v
SQLiteRepository.get_candles()
         |
         v
Domain: Calculate SMA
         |
         v
Return results
```

Analysis commands **never** hit the network - they use cached data only.

---

## Refresh Strategy

### When to Refresh

- **Daily use:** Refresh once per trading day
- **Historical analysis:** No refresh needed
- **Missing data:** Fetch with `--refresh`

### Manual Refresh

```bash
# Force re-download even if cached
saham fetch market BBCA --days 365 --refresh
```

### Fetch Window

By default, `saham fetch market` downloads 90 days of history:

```bash
# Default: 90 days
saham fetch market BBCA

# Extended: 2 years
saham fetch market BBCA --days 730

# Maximum practical: 5 years
saham fetch market BBCA --days 1825
```

---

## Data Quality

### Validation

The system validates incoming data:
- All OHLCV fields must be present
- Dates must be parseable
- Prices must be positive
- Duplicates are handled (latest wins)

### Known Issues

| Issue | Impact | Workaround |
|-------|--------|------------|
| Yahoo delays | Data may be 15-20min delayed | Accept for daily analysis |
| Yahoo `^JKSE` volume | Yahoo index volume is not authoritative for IHSG benchmark analysis and may be zero or use provider-specific units | Use canonical `IHSG` persisted from Stockbit `/company-price-feed/historical/summary/IHSG`; Yahoo `^JKSE` is only a provider alias/fallback |
| Split adjustments | Historical prices adjusted | Use adjusted close |
| Missing days | Holidays/weekends excluded | Expected behavior |
| Legacy candle provenance | Older databases may contain candle rows written before `source`, `volume_unit`, and `price_adjustment_policy` existed. Those rows are migrated with `unknown` provenance until refreshed. | Run `saham fetch audit` to identify unknown provenance, then refresh affected tickers. New Yahoo and IDX candle fetches persist volume in raw shares with explicit provider metadata. |

### Sector macro series quality (ADR-053 / DIAGNOSTIC)

Sector-macro drivers are Yahoo (or virtual) series routed by
`config/sector_macro_context.yaml`. Authority is **DIAGNOSTIC only** — weak or
proxy series must stay documented, not silently treated as cash-flow truth.

Smoke reference: local `data/db/data.db` + Yahoo chart API (2026-07-30).

| Series | Role in SMC | Quality notes | Do **not** use |
|--------|-------------|---------------|----------------|
| `CL=F` | Oil support (`oil_proxy`) and oil cost (`oil_cost`, invert) | Liquid NYMEX future; solid volume | — |
| `IDR=X` | Exporter FX (`usd_idr`) or risk FX (`usd_idr_risk`, invert) | Live FX; volume often zero (normal for Yahoo FX) | — |
| `COAL` | Thermal coal map (`coal_proxy`) | **Range Global Coal Index ETF** — liquid equity basket, not Newcastle FOB / API2. Imperfect for IDX thermal cash flows; best usable Yahoo stand-in after dead coal futures | `MTF=F` (API2 alt — no OHLCV bars), single US coal equities as the sole map driver without a product decision |
| `CPO=F` | Plantation map (`cpo`) | CME **ALTSYMBOL** palm-linked series: OHLC usually present for session returns, **volume mostly zero** (thin/synthetic). Yahoo `regularMarketPrice` can disagree with chart last (feed quirk) | `KO=F` (legacy CPO — 404), treating prints as exchange-floor CPO |
| `HG=F` / `GC=F` | Metals / gold | Liquid COMEX futures | — |
| `ZC=F` / `ZS=F` | Poultry feed cost (invert) | Liquid CBOT grains | Chicken-price model (not a series we have) |
| `BI_RATE` | Domestic rates maps (`bi_rate_policy`) | Virtual series from macro calendar steps (Stockbit economic), not Yahoo | Continuous SBN/INDONIA without a separate rates product (P2b) |
| `^TNX` | Library only (`us_10y`) | Live after Track B **not** on live sector maps | Re-adding to domestic IDX maps without policy change |

**Palm / CPO alternatives considered (not adopted):**

| Candidate | Why not live-mapped |
|-----------|---------------------|
| `KO=F` | Dead / HTTP 404 on Yahoo |
| `FCPO.KL` | Not available (404) |
| `ZL=F` (soybean oil) | Liquid, but **different soft-oil complex** — would rebrand plantation driver from palm to veg-oil; needs explicit product decision |
| KL equity proxies (e.g. SDG) | Single-name equity, not a commodity series |

**Coal alternatives considered (not adopted):**

| Candidate | Why not live-mapped |
|-----------|---------------------|
| `MTF=F` | No usable chart bars (stale ALTSYMBOL) |
| `KOL` | No usable bars on Yahoo chart API (2026-07 smoke) |
| `BTU` / miners | Single equities — more idiosyncratic than the `COAL` basket |

**Operator impact:** plantation and coal SECTOR MACRO labels can be **noisy**.
Fail-soft still applies (missing candles → factor UNAVAILABLE). Prefer reading
composite + coverage, not a single thin factor, when judging names in those maps.

**MCE note:** optional `commodity_composite` in `market_context_engine.yaml` may
still list legacy `KO=F` / `MTF=F` while **disabled**. That factor stays off by
default and is independent of sector-macro live maps (ADR-053).

---

## Adding New Providers

To add a new data provider:

1. **Implement the port** in `src/infrastructure/data_providers/`:

```python
from datetime import date
from src.domain.ports.market_data_provider import MarketDataProvider, MarketDataProviderError
from src.domain.entities.candle import Candle

class NewProvider(MarketDataProvider):
    def fetch_daily_ohlcv(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[Candle]:
        # Implement fetching logic
        # Return Candle objects sorted by date ascending
        ...
```

2. **Wire in CLI** - Add provider option to the appropriate command file. Provider selection logic lives in:

   - **Candle data:** `src/adapters/cli/fetch_market_commands.py` (search for `_fetch_candles`)
   - **Broker data:** `src/adapters/cli/broker_commands.py` (search for `_create_broker_provider`)
   - **Explicit broker fetch:** `src/adapters/cli/broker_commands.py` (search for `_create_provider`)

   Example pattern (from `fetch_market_commands.py`):

```python
if provider_name == "yahoo":
    provider = YahooFinanceProvider()
elif provider_name == "idx":
    provider = IdxMarketDataProvider()
else:
    raise ValueError(f"Unknown provider: {provider_name}")
```

3. **Test thoroughly** - Ensure data format matches expectations

---

## Database Location

### Default Path

```
./data.db
```

### Custom Path

```bash
saham fetch market BBCA --days 365 --db /path/to/custom.db
saham indicator compute SMA BBCA --db /path/to/custom.db
```

### Database Management

```bash
# View database size
ls -lh data.db

# Backup database
cp data.db data.db.backup

# Reset (delete all cached data)
rm data.db
```

---

## Future Data Sources

Providers not yet implemented:

| Provider | Status | Use Case |
|----------|--------|----------|
| Alpha Vantage | Planned | Alternative OHLCV source |
| Local Files (non-CSV) | Planned | Offline data loading from custom formats |
