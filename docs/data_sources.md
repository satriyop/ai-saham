# Data Sources

AI Saham uses a provider abstraction to fetch market data. This document explains how data flows through the system.

---

## Supported Providers

### Yahoo Finance (Default)

**Provider:** `YahooFinanceProvider`

- **Data type:** Daily OHLCV (Open, High, Low, Close, Volume)
- **Source:** Yahoo Finance (unofficial API via yfinance)
- **Market suffix:** `.JK` for Indonesia Stock Exchange

**Limitations:**
- Data may be delayed (not real-time)
- Unofficial source (no SLA)
- Daily data only (no intraday)

**Usage:**
```bash
saham fetch BBCA          # Fetches BBCA.JK
saham fetch BBRI --days 730
```

---

## Provider Architecture

The system uses a port/adapter pattern for data providers:

```
Domain Port                    Infrastructure Adapter
-----------                    ----------------------
MarketDataProvider  <-------   YahooFinanceProvider
                    <-------   (Future) IDXProvider
                    <-------   (Future) AlphaVantageProvider
```

This allows:
- Swapping providers without changing domain logic
- Supporting multiple data sources
- Testing with mock providers

---

## Caching Strategy

### Local-First Caching

Data is cached locally after first fetch to enable **offline analysis**.

**Storage:** SQLite database at `~/.ai-saham/data.db`

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
User: saham fetch BBCA
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
   YahooFinanceProvider    Return cached
         |
         v
   Download from Yahoo
         |
         v
   Save to cache
         |
         v
   Return data
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
saham fetch BBCA --refresh
```

### Fetch Window

By default, `saham fetch` downloads 365 days of history:

```bash
# Default: 1 year
saham fetch BBCA

# Extended: 2 years
saham fetch BBCA --days 730

# Maximum practical: 5 years
saham fetch BBCA --days 1825
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
class NewProvider:
    def fetch(self, ticker: str, days: int) -> list[Candle]:
        # Implement fetching logic
        ...
```

2. **Wire in adapter** - Update CLI to use new provider

3. **Test thoroughly** - Ensure data format matches expectations

---

## Database Location

### Default Path

```
~/.ai-saham/data.db
```

### Custom Path

```bash
saham fetch BBCA --db /path/to/custom.db
saham sma BBCA --db /path/to/custom.db
```

### Database Management

```bash
# View database size
ls -lh ~/.ai-saham/data.db

# Backup database
cp ~/.ai-saham/data.db ~/backup/

# Reset (delete all cached data)
rm ~/.ai-saham/data.db
```

---

## Future Data Sources

Planned providers (not yet implemented):

| Provider | Status | Use Case |
|----------|--------|----------|
| IDX Direct | Planned | Official IDX data |
| Alpha Vantage | Planned | Alternative source |
| CSV Import | Planned | Custom data files |
| Local Files | Planned | Offline data loading |
