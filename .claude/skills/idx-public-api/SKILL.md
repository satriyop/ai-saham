---
name: idx-public-api
description: IDX (idx.co.id) public API patterns, endpoints, headers, and gotchas. Use when working with Indonesia Stock Exchange data fetching, broker data, stock summaries, or market data from IDX.
---

# IDX Public API

## Browser Headers Required

IDX API returns 403 Forbidden without proper browser-like headers. Always include:

```python
IDX_HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.idx.co.id/en/market-data/trading-summary/stock-summary/",
    "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}
```

Missing `sec-ch-ua` or `Referer` headers will result in 403.

## Endpoint Reference

### GetStockSummary (Per-Stock Data)

```
GET https://www.idx.co.id/primary/TradingSummary/GetStockSummary
  ?start=0&length=9999&date=YYYYMMDD
```

**Returns per-stock data including:**
- `StockCode`, `StockName`
- `ForeignBuy`, `ForeignSell` (in **shares**, not lots; divide by 100 for lots)
- `Volume` (shares), `Value` (IDR), `Frequency`
- OHLC prices: `OpenPrice`, `High`, `Low`, `Close`, `Previous`, `Change`
- `ListedShares`, `TradebleShares`

**Use this for:** Per-stock foreign flow analysis.

### GetBrokerSummary (Market-Wide Broker Totals)

```
GET https://www.idx.co.id/primary/TradingSummary/GetBrokerSummary
  ?start=0&length=9999&date=YYYYMMDD
```

**Returns market-wide broker data:**
- `IDFirm` (broker code), `FirmName`
- `Volume`, `Value`, `Frequency` (aggregated across all stocks)

**Limitation:** No per-stock breakdown, no buy/sell split. Only useful for market-wide broker activity ranking.

## Key Gotchas

### Foreign Flow is in Shares, Not Lots
`ForeignBuy` and `ForeignSell` values from GetStockSummary are in **shares** (not lots). IDX standard lot = 100 shares.

```python
foreign_buy_lot = int(data["ForeignBuy"]) // 100
```

### Foreign Flow Values Must Be Estimated
IDX API does not provide foreign buy/sell **values in IDR**. Standard practice is to estimate using closing price:

```python
foreign_buy_value = Decimal(str(foreign_buy_shares)) * Decimal(str(close_price))
```

This is an approximation since actual transaction prices vary throughout the day.

### Date Format
IDX API uses `YYYYMMDD` format (no separators):
```python
params = {"date": target_date.strftime("%Y%m%d")}
```

### Response Wrapper
All responses use DataTables-style wrapper:
```json
{
  "draw": 0,
  "recordsTotal": 955,
  "recordsFiltered": 955,
  "data": [...]
}
```

### Date Field Format
Date fields in response include time: `"2025-01-24T00:00:00"`. Slice first 10 chars for date parsing:
```python
trading_date = date.fromisoformat(data["Date"][:10])
```

### Rate Limiting
Recommended: 1 request/second. IDX may return 429 if requests are too frequent. Use exponential backoff on 429 and 5xx errors.

### No Stock-Level Filtering
The `search[value]` parameter returns 403. Always fetch all stocks (`length=9999`) and filter client-side.

### 403 Has Multiple Causes — Do NOT Assume Holiday
IDX returns 403 in at least three situations:
1. Missing or wrong browser headers (`sec-ch-ua`, `Referer`)
2. `search[value]` filtering attempt
3. No data published for the queried date

**Never interpret IDX 403 as "non-trading day" or "holiday"** — live probes confirm trading days can also return 403 from GetStockSummary while GetIndexSummary returns valid data for the same date.

### Canonical Market Open/Closed Check
Use Stockbit `GET /company-price-feed/market-time` (requires Bearer token):

```python
# Response shape:
{
  "data": {
    "market": {"status": "STATUS_OPEN"},      # or "STATUS_CLOSE"
    "iepiev_regular": {"status": "STATUS_CLOSE"},
    "iepiev_fca": {"status": "STATUS_OPEN"}
  }
}
```

`data.market.status == "STATUS_OPEN"` is the canonical trading-day signal.

Existing implementation: `src/infrastructure/browser/stockbit_market_time.py`
Domain value object: `src/domain/value_objects/market_status.py`
Port: `src/domain/ports/market_status_provider.py`

## Implementation Reference

The IDX provider is implemented at: `src/infrastructure/data_providers/idx.py`
Tests at: `tests/infrastructure/test_idx_broker_provider.py`
