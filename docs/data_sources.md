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
                    <-------   BrokerCsvAdapter (import only)
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
saham update BBCA --days 365          # Fetches BBCA.JK via Yahoo (default)
saham update BBRI --days 730
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
saham update BBCA --days 30 --provider idx              # Uses IDX public API
saham update BBCA --days 30 --provider idx              # Faster for small ranges
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
saham broker fetch BBCA                # Auto-selects IDX (no auth)
saham broker fetch BBCA --days 90
```

### Stockbit

**Provider:** `StockbitPlaywrightBrokerProvider` (auto-selected if authenticated)

- **Data type:** Full per-broker breakdown (top 10 buyers + sellers), exact foreign flow values
- **Source:** Stockbit Exodus API (undocumented)
- **Auth:** Browser session profile from `saham stockbit login`

**Setup:**
```bash
# Browser-based login (recommended)
saham stockbit login
```

**Usage:**
```bash
saham broker fetch BBCA --provider stockbit-session   # Richer per-broker detail
saham broker top BBCA --date 2024-01-15
```

### CSV Import

**Provider:** `BrokerCsvAdapter` (via `saham broker import`)

- **Data type:** Broker summary data from external sources
- **Formats:** SIMPLE (aggregate) or DETAILED (per-broker)
- **Auto-detection:** Format + column mapping via `FormatDetector`

**Supported date formats:** ISO, DD/MM/YYYY, MM/DD/YYYY, DD-MM-YYYY, YYYYMMDD

**Usage:**
```bash
saham broker import data.csv               # Auto-detect format
saham broker import data.csv --preview     # Validate before import
saham broker mappings                      # List available column mappings
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

---

## Data Flow

### Fetch Flow

```
User: saham update BBCA --days 365 --provider yahoo
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

```
User: saham broker fetch BBCA
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

### Analysis Flow

```
User: saham sma BBCA
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
saham update BBCA --days 365 --refresh
```

### Fetch Window

By default, `saham update` downloads 90 days of history:

```bash
# Default: 90 days
saham update BBCA

# Extended: 2 years
saham update BBCA --days 730

# Maximum practical: 5 years
saham update BBCA --days 1825
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

2. **Wire in CLI** - Add provider option to `src/adapters/cli/main.py`:

```python
if data_provider == "new":
    provider = NewProvider()
elif data_provider == "idx":
    provider = IdxMarketDataProvider()
else:
    provider = YahooFinanceProvider()
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
saham update BBCA --days 365 --db /path/to/custom.db
saham sma BBCA --db /path/to/custom.db
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
