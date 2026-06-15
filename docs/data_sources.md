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
                    <-------   (Planned) AlphaVantageProvider

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
saham data update BBCA --days 365          # Fetches BBCA.JK via Yahoo (default)
saham data update BBRI --days 730
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

**Usage:**
```bash
saham data update BBCA --days 30 --provider idx              # Uses IDX public API
saham data update BBCA --days 30 --provider idx              # Faster for small ranges
```

---

## Broker Data Providers (Foreign Flow)

### IDX Public API

**Provider:** `IdxBrokerDataProvider` (auto-selected when no Stockbit session found)

- **Data type:** Foreign buy/sell lots, estimated foreign flow value
- **Source:** IDX TradingSummary API (`idx.co.id`)
- **Auth:** None required

**Limitations:**
- Per-broker breakdown (`top_buyers` / `top_sellers`) is not available
- Foreign flow values are estimated as `volume * closing price` (IDX provides share volumes, not transaction values)
- Foreign flow lots are exact (from `ForeignBuy` / `ForeignSell` fields)

**Usage:**
```bash
saham data broker fetch BBCA                # Defaults to IDX (no auth, --provider idx)
saham data broker fetch BBCA --days 90
```

### Stockbit

**Provider:** `StockbitPlaywrightBrokerProvider` (auto-selected if authenticated)

- **Data type:** Full per-broker breakdown (top 10 buyers + sellers), exact foreign flow values
- **Source:** Stockbit Exodus API (undocumented)
- **Auth:** Browser session profile from `saham data stockbit login`

**Setup:**
```bash
# Browser-based login (recommended)
saham data stockbit login
```

**Usage:**
```bash
saham data broker fetch BBCA --provider stockbit-session   # Richer per-broker detail
saham data broker top BBCA --date 2024-01-15
```

### CSV Import

**Provider:** `BrokerCsvAdapter` (via `saham data broker import`)

- **Data type:** Broker summary data from external sources
- **Formats:** SIMPLE (aggregate) or DETAILED (per-broker)
- **Auto-detection:** Format + column mapping via `FormatDetector`

**Supported date formats:** ISO, DD/MM/YYYY, MM/DD/YYYY, DD-MM-YYYY, YYYYMMDD

**Usage:**
```bash
saham data broker import data.csv               # Auto-detect format
saham data broker import data.csv --preview     # Validate before import
saham data broker mappings                      # List available column mappings
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

> `saham data update` has two independent provider flags:
> - `--provider` → candles source (default: `yahoo`)
> - `--broker-provider` → broker flow source (default: auto-detect Stockbit → IDX)

| Data | Default Source | Command | Table |
|------|---------------|---------|-------|
| **Daily OHLCV prices** | Yahoo Finance | `saham data update TICKER` | `candles` |
| **Daily OHLCV prices (IDX)** | IDX TradingSummary API | `saham data update TICKER --provider idx` | `candles` |
| **Foreign flow aggregate** | IDX (always uses IDX for accurate `total_value`) | `saham data update --broker-provider …` / `saham data broker fetch` | `broker_summaries` |
| **Per-broker daily flow** | Stockbit Exodus API (only source with per-broker data) | `saham data update` (auto when Stockbit available) / `saham data broker fetch --provider stockbit-session` | `broker_daily_flow` |
| **Foreign flow time-series** | IDX (broker_summaries) / Stockbit (historical API) | `saham data update` / `saham data broker fetch` | `foreign_flow_points` |
| **Foreign flow N-day snapshot** | Stockbit Exodus API (top foreign stocks) | `saham data broker top-foreign` | `foreign_flow_snapshots` |
| **Pre-open IEV + order books** | Stockbit Exodus API (Playwright) | `saham trade intraday pre-open` | `iev_snapshots` |
| **AI sentiment classification** | DeepSeek/Claude classifier | `saham analyze sentiment` | `sentiment_logs` |
| **Sentiment price outcome** | Computed from sentiment_logs + candles | `saham analyze audit` | `sentiment_audits` |

| SQLite Table | Columns | Sample Row |
|-------------|---------|------------|
| `candles` | `ticker, date, open, high, low, close, volume, created_at` | `BBCA\|2025-12-30\|7950\|8175\|7950\|8075\|101995600\|2026-01-25 19:19:09` |
| `broker_summaries` | `ticker, date, source, foreign_buy_value, foreign_sell_value, foreign_buy_lot, foreign_sell_lot, total_value, total_lot, top_buyers_json, top_sellers_json, created_at` | `BBCA\|2026-01-26\|idx\|546023340000\|1338621480000\|713756\|1749832\|1617763560000\|2130441\|[]\|[]\|2026-01-27 07:20:14` |
| `broker_daily_flow` | `ticker, date, broker_code, broker_name, source, buy_lot, sell_lot, net_lot, buy_value, sell_value, net_value, avg_price, buy_pct, sell_pct, created_at, avg_buy_price, avg_sell_price` | `BBCA\|2026-06-12\|AK\|UBS Sekuritas Indonesia\|stockbit\|943983\|848655\|95328\|567271847500\|510120457500\|57151390000\|6009.34\|52.66\|47.34\|2026-06-14 11:39:12\|6009.34\|6010.93` |
| `foreign_flow_points` | `ticker, date, source, net_val, net_lot, avg_price, created_at` | `AALI\|2026-06-12\|stockbit\|-8654047500\|-13975\|6185.62\|2026-06-13 23:18:26` |
| `foreign_flow_snapshots` | `ticker, snapshot_date, period_days, source, net_val, net_lot, created_at` | (populated on demand) |
| `iev_snapshots` | `date, ticker, iev, rank, iep, fetched_at` | `2026-06-15\|BUMI\|1602630\|1\|165\|2026-06-15 05:53:44` |
| `sentiment_logs` | `id, date, ticker, sentiment, catalyst, score` | `1\|2026-06-12\|AUDIT\|neutral\|general\|1.0` |
| `sentiment_audits` | `log_id, days_after, price_delta_pct, audited_at` | (populated on demand) |

### Default Source per Table

| Table | Default Source | Controlled By | Command(s) |
|-------|---------------|--------------|------------|
| `candles` | Yahoo Finance | `--provider` | `saham data update TICKER` (use `--provider idx` for IDX) |
| `broker_summaries` | IDX (always accurate `total_value`) | `--broker-provider` (IDX always used for summaries regardless) | `saham data update` / `saham data broker fetch` |
| `broker_daily_flow` | Stockbit Exodus API (IDX has no per-broker data) | `--broker-provider` | `saham data update` (auto when Stockbit available) / `saham data broker fetch --provider stockbit-session` |
| `foreign_flow_points` | IDX (from summaries) or Stockbit (historical API) | `--broker-provider` | `saham data update` / `saham data broker fetch` |
| `foreign_flow_snapshots` | Stockbit Exodus API | (dedicated command) | `saham data broker top-foreign` |
| `iev_snapshots` | Stockbit Exodus API (Playwright) | (dedicated command) | `saham trade intraday pre-open` |
| `sentiment_logs` | DeepSeek / Claude classifier | (dedicated command) | `saham analyze sentiment` |
| `sentiment_audits` | Derived from sentiment_logs + candles | (dedicated command) | `saham analyze audit` |

> [!NOTE]
> `foreign_flow_points` is populated by **two independent code paths** that run during
> `saham data update`:
>
> 1. **Path A — Derived from broker_summaries** (`fetch_broker_data.py:119-130`): Every
>    time broker_summaries are fetched and saved, a `ForeignFlowPoint` is created from
>    each `BrokerSummary.foreign_net_value` and `foreign_net_lot`. Summaries always use
>    the IDX provider (accurate `total_value`), so Path A always writes **IDX-sourced**
>    points.
>
> 2. **Path B — Direct historical fetch** (`update_commands.py:365-369`): If the active
>    broker provider implements `fetch_foreign_flow_history()`, the CLI calls it to get
>    richer per-date data (buy_vol, sell_vol, etc.). Only Stockbit provides this, so
>    Path B writes **Stockbit-sourced** points.
>
> **Result:** The table holds data from both sources keyed by `(ticker, date, source)`.
> IDX points (`source='idx'`) exist for every date summaries were fetched; Stockbit
> points (`source='stockbit'`) exist only when Stockbit was the active provider. The
> repository stores both — no overwrite, no merge. Downstream consumers (VWAP, trend
> analysis) can pick by source or prefer one over the other.

---

## Data Flow

### Fetch Flow

```
User: saham data update BBCA --days 365 --provider yahoo
         |
         v
CLI Adapter
         |
         v
FetchMarketDataUseCase
         |
         +---> Check cache (SQLiteRepository)
         |           |
         |           v
         |     Has recent data?
         |           |
         |     No    |    Yes (and not --refresh)
         |           |           |
         v           v           v
   Provider selected by --provider flag
         |
         +--- Yahoo? ---> YahooFinanceProvider
         |                     |
         |                     v
         |              Download from Yahoo
         |
         +--- IDX?   ---> IdxMarketDataProvider
                               |
                               v
                        Download from IDX API
         |
         v
   Save to cache (SQLiteRepository)
         |
         v
   Return data
```

### Broker Fetch Flow

For `saham data update` (auto-detects provider):

```
User: saham data update BBCA --days 90
         |
         v
CLI Adapter
         |
         v
FetchBrokerDataUseCase
         |
         v
   Auto-select provider:
         |
          +--- Stockbit session exists + valid?
         |       |
         |       v
         |   StockbitPlaywrightBrokerProvider  (per-broker detail, exact values)
         |
         +--- Otherwise:
                 |
                 v
             IdxBrokerDataProvider  (no auth, estimated values)
         |
         v
   Save to cache (SQLiteBrokerRepository)
         |
         v
   Return BrokerSummary[]
```

For `saham data broker fetch` (uses explicit `--provider` flag):

```
User: saham data broker fetch BBCA --provider stockbit-session
         |
         v
   Provider selected by --provider flag:
         |
          +--- --provider idx (default)?
         |       v
         |   IdxBrokerDataProvider
         |
          +--- --provider stockbit-session?
                 v
             StockbitPlaywrightBrokerProvider
         |
         v
   Save to cache (SQLiteBrokerRepository)
         |
         v
   Return BrokerSummary[]
```

Default for `saham data broker fetch` is `--provider idx` (no auth, estimated values).
Use `--provider stockbit-session` for per-broker detail and exact values.

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
saham data update BBCA --days 365 --refresh
```

### Fetch Window

By default, `saham data update` downloads 90 days of history:

```bash
# Default: 90 days
saham data update BBCA

# Extended: 2 years
saham data update BBCA --days 730

# Maximum practical: 5 years
saham data update BBCA --days 1825
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
| Split adjustments | Historical prices adjusted | Use adjusted close |
| Missing days | Holidays/weekends excluded | Expected behavior |

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

   - **Candle data:** `src/adapters/cli/update_commands.py` (search for `_fetch_candles`)
   - **Broker data:** `src/adapters/cli/update_commands.py` (search for `_create_broker_provider`)
   - **Explicit broker fetch:** `src/adapters/cli/broker_commands.py` (search for `_create_provider`)

   Example pattern (from `update_commands.py`):

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
saham data update BBCA --days 365 --db /path/to/custom.db
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
