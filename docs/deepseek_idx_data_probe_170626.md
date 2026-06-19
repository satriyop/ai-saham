# IDX Public API Probe — 2026-06-17

Probe of the Indonesia Stock Exchange (idx.co.id) public API endpoints.
Conducted on 2026-06-17 using Python httpx with browser-like headers.

---

## Probe Method

All requests sent to `https://www.idx.co.id/primary/TradingSummary/*` with:

```python
headers = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.idx.co.id/en/market-data/trading-summary/stock-summary/",
    "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}
```

Query pattern: `?start=0&length=N&date=YYYYMMDD` (DataTables-style pagination).
Date used: `20260615` (Monday, IDX trading day).

### Note on curl vs httpx

`curl` with identical headers returns **403** for all IDX endpoints.
Python `httpx.Client(follow_redirects=True)` succeeds with **200**.
Likely cause: IDX servers fingerprint the TLS library or handle redirects differently.
**Always use `httpx` (not `curl`) for IDX API probes.**

---

## Available Endpoints (200 OK)

### 1. GetStockSummary

**Per-stock trading summary — the primary IDX data source.**

| Field | Sample | Type | Notes |
|-------|--------|------|-------|
| `StockCode` | `AADI` | string | Ticker symbol |
| `StockName` | `Adaro Andalan Indonesia Tbk.` | string | Company name |
| `OpenPrice` | `8600.0` | float | Opening price |
| `High` | `8600.0` | float | Day high |
| `Low` | `8250.0` | float | Day low |
| `Close` | `8275.0` | float | Closing price |
| `Previous` | `8650.0` | float | Previous close |
| `Change` | `-375.0` | float | Price change |
| `ForeignBuy` | `3057800.0` | float | **Shares** bought by foreign (÷100 = lots) |
| `ForeignSell` | `6892600.0` | float | **Shares** sold by foreign (÷100 = lots) |
| `Volume` | `22860400.0` | float | Total volume in shares |
| `Value` | `193020177500.0` | float | Total value in IDR |
| `Frequency` | `15750.0` | float | Trade count |
| `Bid` | `8275.0` | float | Best bid price |
| `BidVolume` | `9400.0` | float | Best bid volume (shares) |
| `Offer` | `8300.0` | float | Best offer price |
| `OfferVolume` | `8100.0` | float | Best offer volume (shares) |
| `ListedShares` | `7786891760.0` | float | Total listed shares |
| `TradebleShares` | `7786891760.0` | float | Tradeable shares |
| `IndexIndividual` | `149.1` | float | Individual index contribution |
| `WeightForIndex` | `1486517637.0` | float | Weight for index calc |
| `FirstTrade` | `8600.0` | float | First trade price |
| `NonRegularVolume` | `65111.0` | float | Non-regular market volume |
| `NonRegularValue` | `550302325.0` | float | Non-regular market value |
| `NonRegularFrequency` | `8.0` | float | Non-regular trade count |
| `Date` | `2026-06-15T00:00:00` | string | Trading date (slice first 10 chars) |
| `Remarks` | `XDMO1SD0F10000A121------------` | string | Corporate action flag |
| `DelistingDate` | (empty) | string | Delisting date if applicable |
| `IDStockSummary` | `4032632` | int | Internal row ID |
| `No` | `1` | int | Row number in response |
| `percentage` | `None` | null | (unknown — always null) |
| `persen` | `None` | null | (unknown — always null) |

**URL:** `/primary/TradingSummary/GetStockSummary?start=0&length=9999&date=YYYYMMDD`

**Records:** 959 (all listed stocks)

**Currently used by app:** ✅ Yes (`IdxBrokerDataProvider` in `src/infrastructure/data_providers/idx.py`)

---

### 2. GetBrokerSummary

**Market-wide broker aggregate totals — no per-stock breakdown, no buy/sell split.**

| Field | Sample | Type | Notes |
|-------|--------|------|-------|
| `IDFirm` | `AD` | string | Broker code |
| `FirmName` | `Sukadana Prima Sekuritas` | string | Broker legal name |
| `Volume` | `34889300.0` | float | Total volume (shares) across all stocks |
| `Value` | `2297240900.0` | float | Total value (IDR) across all stocks |
| `Frequency` | `264.0` | float | Total trade count |
| `Date` | `2026-06-15T00:00:00` | string | Trading date |
| `IDBrokerSummary` | `957376` | int | Internal row ID |
| `No` | `1` | int | Row number |

**URL:** `/primary/TradingSummary/GetBrokerSummary?start=0&length=9999&date=YYYYMMDD`

**Records:** 88 (all brokers)

**Currently used by app:** ❌ No

**Why not useful:** Aggregate broker volume/value with no buy/sell split or per-stock breakdown. Stockbit Exodus API is vastly richer for broker-level analysis.

---

### 3. GetIndexSummary

**Index data — all 45 IDX indices including IHSG and sectorals.**

| Field | Sample | Type | Notes |
|-------|--------|------|-------|
| `IndexCode` | `COMPOSITE` | string | Index code (see full list below) |
| `Close` | `6254.966` | float | Closing value |
| `Previous` | `6007.656` | float | Previous close |
| `Change` | `247.31` | float | Point change |
| `Highest` | `6345.799` | float | Day high |
| `Lowest` | `6118.076` | float | Day low |
| `NumberOfStock` | `913.0` | float | Constituent count |
| `Volume` | `50192600835.0` | float | Total volume |
| `Value` | `30093724135013.0` | float | Total value |
| `Frequency` | `3188422.0` | float | Total frequency |
| `MarketCapital` | `1.09028803301227e+16` | float | Market cap |
| `Date` | `2026-06-15T00:00:00` | string | Trading date |
| `IndexSummaryID` | `193050` | int | Internal row ID |
| `No` | `1` | int | Row number |

**URL:** `/primary/TradingSummary/GetIndexSummary?start=0&length=50&date=YYYYMMDD`

**Records:** 45

**Currently used by app:** ❌ No (regime context uses Yahoo Finance `^JKSE`)

#### All 45 Indices

```
COMPOSITE    Close=6254.966  Prev=6007.656  Stocks=913   ← IHSG
LQ45         Close= 624.682  Prev= 597.448  Stocks=45    ← 45 largest
IDXLQ45LCL   Close=  91.442  Prev=  87.187  Stocks=37
IDX30        Close= 354.188  Prev= 338.988  Stocks=30
IDX80        Close=  93.979  Prev=  89.678  Stocks=80
IDXESGL      Close= 113.584  Prev= 108.276  Stocks=30
IDXQ30       Close= 113.686  Prev= 109.096  Stocks=30
IDXV30       Close= 115.863  Prev= 112.967  Stocks=30
IDXG30       Close= 120.146  Prev= 115.209  Stocks=30
IDXHIDIV20   Close= 434.987  Prev= 417.569  Stocks=20
IDXBUMN20    Close= 329.790  Prev= 314.929  Stocks=20
JII70        Close= 146.458  Prev= 140.233  Stocks=70
ISSI         Close= 213.164  Prev= 206.134  Stocks=576
JII          Close= 377.425  Prev= 359.060  Stocks=30
IDXMESBUMN   Close=  79.031  Prev=  76.268  Stocks=17
IDXSHAGROW   Close=  86.179  Prev=  82.494  Stocks=30
IDXSMC-LIQ   Close= 285.465  Prev= 278.538  Stocks=60
IDXSMC-COM   Close= 380.595  Prev= 370.271  Stocks=452
MBX          Close=1577.916  Prev=1512.196  Stocks=270
DBX          Close=2935.838  Prev=2849.058  Stocks=490
ABX          Close=2870.257  Prev=2786.445  Stocks=39
KOMPAS100    Close= 830.976  Prev= 793.970  Stocks=100
INFOBANK15   Close= 858.030  Prev= 815.075  Stocks=15
BISNIS-27    Close= 436.252  Prev= 414.441  Stocks=27
Investor33   Close= 346.497  Prev= 331.658  Stocks=33
SRI-KEHATI   Close= 305.457  Prev= 291.253  Stocks=25
ESGSKEHATI   Close= 104.433  Prev=  99.768  Stocks=49
ESGQKEHATI   Close= 103.380  Prev=  98.657  Stocks=45
SMinfra18    Close= 224.585  Prev= 218.012  Stocks=18
MNC36        Close= 276.539  Prev= 262.715  Stocks=36
I-GRADE      Close= 157.970  Prev= 150.410  Stocks=30
PRIMBANK10   Close= 155.454  Prev= 146.969  Stocks=10
ECONOMIC30   Close=  87.446  Prev=  82.086  Stocks=30
IDXVESTA28   Close= 128.702  Prev= 125.718  Stocks=28
IDXENERGY    Close=2918.867  Prev=2851.889  Stocks=91   ← Energy sector
IDXBASIC     Close=1686.695  Prev=1572.531  Stocks=112  ← Basic materials
IDXINDUST    Close=1611.579  Prev=1542.022  Stocks=63   ← Industrial
IDXNONCYC    Close= 644.840  Prev= 627.689  Stocks=123  ← Non-cyclicals
IDXCYCLIC    Close= 923.376  Prev= 889.051  Stocks=148  ← Cyclicals
IDXHEALTH    Close=1387.671  Prev=1397.081  Stocks=38   ← Healthcare
IDXFINANCE   Close=1384.689  Prev=1315.689  Stocks=106  ← Financials
IDXPROPERT   Close= 766.614  Prev= 751.362  Stocks=88   ← Property
IDXTECHNO    Close=6695.325  Prev=6583.501  Stocks=40   ← Technology
IDXINFRA     Close=1818.677  Prev=1766.988  Stocks=67   ← Infrastructure
IDXTRANS     Close=1749.403  Prev=1699.284  Stocks=37   ← Transportation
```

---

## Unavailable Endpoints (503 Service Unavailable)

| Endpoint | URL Pattern | Status |
|----------|-------------|--------|
| `GetSectorSummary` | `/primary/TradingSummary/GetSectorSummary` | 503 |
| `GetBoardSummary` | `/primary/TradingSummary/GetBoardSummary` | 503 |
| `GetMostActive` | `/primary/TradingSummary/GetMostActive` | 503 |
| `GetStockList` | `/primary/MarketData/GetStockList` | 503 |

These endpoints exist but return 503. They may require different parameters, a different base path, or be temporarily disabled. Worth re-testing periodically.

---

## Quick Reference Table

| Endpoint | URL (relative) | Records | Key Data | Auth | Used? | Status | Use Case |
|----------|----------------|---------|----------|------|-------|--------|----------|
| `GetStockSummary` | `/primary/TradingSummary/GetStockSummary` | 959 | Stock-level OHLC + foreign flow (shares) + bid/offer | Public | ✅ Yes | ✅ 200 | Core — all foreign flow data |
| `GetBrokerSummary` | `/primary/TradingSummary/GetBrokerSummary` | 88 | Broker aggregate volume/value/freq | Public | ❌ No | ✅ 200 | Low value — no per-stock or buy/sell |
| `GetIndexSummary` | `/primary/TradingSummary/GetIndexSummary` | 45 | Index OHLC + constituent count + market cap | Public | ❌ No | ✅ 200 | **Potential** — regime detection with real IDX data vs Yahoo `^JKSE` |
| `GetSectorSummary` | `/primary/TradingSummary/GetSectorSummary` | ? | ? | Public | ❌ No | ❌ 503 | Re-test periodically |
| `GetBoardSummary` | `/primary/TradingSummary/GetBoardSummary` | ? | ? | Public | ❌ No | ❌ 503 | Re-test periodically |
| `GetMostActive` | `/primary/TradingSummary/GetMostActive` | ? | ? | Public | ❌ No | ❌ 503 | Re-test periodically |
| `GetStockList` | `/primary/MarketData/GetStockList` | ? | ? | Public | ❌ No | ❌ 503 | Different base path |

---

## Key Gotchas

1. **Foreign flow is in shares, not lots.** Divide `ForeignBuy` / `ForeignSell` by 100 for lots.
2. **Foreign flow value must be estimated.** IDX provides foreign buy/sell in shares only. Value is estimated as `shares × close_price`. This is an approximation.
3. **Date format:** `YYYYMMDD` in query params, `YYYY-MM-DDT00:00:00` in response (slice first 10 chars).
4. **403 = no data for this date.** IDX returns 403 when it has no data to serve for the queried date. Do NOT interpret this as "holiday" — 403 has multiple causes (missing/wrong headers, date with no published data, other). The canonical source to determine if IDX market is open or closed is Stockbit `GET /company-price-feed/market-time` → `data.market.status` (`STATUS_OPEN` | `STATUS_CLOSE`).
5. **Rate limit:** 1 req/s recommended. 429 possible with rapid requests.
6. **DataTables wrapper:** All responses use `{"draw":0, "recordsTotal":N, "recordsFiltered":N, "data":[...]}`.
7. **curl won't work.** Browser-like headers + httpx required. curl returns 403 even with identical headers.
8. **No `search[value]` filtering.** Attempting to filter by stock code returns 403. Always fetch all and filter client-side.

---

## Claude Response

Reviewed against: `src/infrastructure/data_providers/idx.py`, `src/infrastructure/data_providers/idx_market.py`, `src/application/use_case/market_regime.py`, and the existing `.claude/skills/idx-public-api/` skill.

### ✅ Confirmed Claims

All core gotchas (1–8) are accurate and match what's already implemented:

- Foreign flow ÷ 100 for lots → exact match at `idx.py:217–218`
- Value estimation via `shares × close_price` → exact match at `idx.py:223–224`
- `Date[:10]` slice → exact match at `idx.py:209`, `idx_market.py:170`
- 403 → IDX returns no data for this date → behavior of skipping it is correct, but the "holiday" interpretation was **wrong** and has been removed from the code. Canonical market open/close oracle: Stockbit `GET /company-price-feed/market-time`
- 1 req/s rate limit → `REQUEST_DELAY_SECONDS = 1.0` in both providers
- DataTables wrapper and no `search[value]` filtering → consistent with existing skill
- GetBrokerSummary has no buy/sell split → correct, that's why it's unused
- GetIndexSummary not currently used → confirmed; `market_regime.py:23` uses `benchmark_ticker = "^JKSE"` via Yahoo Finance

### ⚠️ Issues & Corrections

**1. OMISSION — `GetStockSummary` has two consumers, not one.**

The document marks GetStockSummary as "Used by `IdxBrokerDataProvider`" only. This is incomplete. `IdxMarketDataProvider` (`src/infrastructure/data_providers/idx_market.py`) also hits the same `GetStockSummary` endpoint — for OHLCV candles. Any caching or rate-limit strategy must account for both callers independently instantiating `httpx.Client` per request with no shared state.

**2. `sec-ch-ua` header is subtly wrong in the probe.**

DeepSeek's probe used:
```
"sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120"'
```
The production codebase (and the project's IDX skill) uses:
```
"sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"'
```
The extra `"Google Chrome";v="120"` token is present in both `idx.py:59` and `idx_market.py:59`. The probe's explanation for why curl fails ("TLS fingerprinting") is plausible, but the missing `Google Chrome` brand token is a more likely differentiator — IDX may be checking for a real Chrome UA client hint triplet. Do not use the probe's header verbatim as a copy-paste template.

**3. `Remarks` field is a corporate action flag — currently untapped.**

The sample value `XDMO1SD0F10000A121------------` is IDX's internal corporate action encoding (dividend flag, rights issue, etc.). The swing screener already has a dividend risk filter (fed from Stockbit). The IDX-native `Remarks` field could serve as a zero-dependency fallback for that filter — but neither provider currently reads or surfaces it.

**4. `NonRegularVolume` / `NonRegularValue` fields — unremarked opportunity.**

These track negotiated/crossing transactions (block trades outside the regular order book). An elevated `NonRegularValue` relative to `Value` can signal institutional block activity not visible in retail order flow. The screeners don't use this yet.

**5. Float representation of share counts.**

DeepSeek documents `ForeignBuy` as `float` (e.g., `3057800.0`). The code correctly casts to `int` before dividing. For share counts approaching 2^53 (≈ 9 quadrillion) IEEE 754 would lose precision, but IDX listed share counts stay well within safe range (`ListedShares` sample `7786891760.0` ≈ 7.8 billion — safe).

**6. Record count: 959 vs 955.**

DeepSeek probed on `20260615` and found 959 records. The existing skill documents 955. The difference is likely new listings between when the skill was written and the probe date. Not an error, but worth noting that `length=9999` is the correct ceiling regardless.

### 🔍 Actionable Gap: `GetIndexSummary` for Regime Detection

DeepSeek correctly flags GetIndexSummary as a potential upgrade over Yahoo Finance `^JKSE`. The concrete benefits for this codebase:

1. **Same-day availability** — IDX data is available during/after market hours; Yahoo Finance `^JKSE` has a T+1 lag for some fields.
2. **11 sectoral indices** (IDXENERGY, IDXBASIC, IDXINDUST, etc.) provide sector breadth signals that are currently fetched per-stock and aggregated expensively — this would give pre-computed sector-level OHLC directly from IDX.
3. **No external dependency** — removes the `yfinance` dependency from the regime detection path, making offline-first operation more complete.

The endpoint is already confirmed 200 OK. The migration path is: implement `IdxIndexProvider` behind the existing `MarketDataProvider` port, swap `benchmark_ticker` wire-up in `bootstrap.py`, and add sectoral index fetching to regime context.

### Summary

DeepSeek's probe is accurate and trustworthy for all core operational facts. The two things to be careful of before reusing its output directly: use the three-brand `sec-ch-ua` header from the codebase (not the two-brand version from the probe), and treat `IdxMarketDataProvider` as a second independent consumer of `GetStockSummary` when designing any shared client or caching layer.
