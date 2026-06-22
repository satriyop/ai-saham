# Stockbit Data Improvement Recommendations
**Date:** 2026-06-20  
**Based on:** Live API probes (`journals/probe_*.json`) vs. actual source code  
**Ticker used for probing:** BBCA  

---

## How These Were Derived

1. Ran `probe_missing.py` to call all 21 high-priority Stockbit endpoints live (headless Chromium, BBCA ticker)
2. Read actual parser source code in `src/infrastructure/browser/stockbit_*.py` and `playwright_stockbit.py`
3. Read domain objects in `src/domain/value_objects/` and `src/domain/entities/`
4. Compared what the API actually returns vs. what the code currently extracts

Probe responses are stored in `journals/probe_*.json` and documented in `docs/stockbit_api_probe_response.md`.

---

## 🔴 Priority 1 — Bugs (Silent failures)

---

### Bug 1: Market Time Parser Uses Wrong Field Path
> **Status: ✅ Done** — `beb1db5`

**File:** `src/infrastructure/browser/stockbit_market_time.py`

**Problem:**  
The parser tries `data.status`, `data.market_status`, `data.marketStatus` in order — none of these fields exist in the real response. The actual structure is:

```json
{
  "data": {
    "market":         { "status": "STATUS_CLOSE" },
    "iepiev_regular": { "status": "STATUS_CLOSE" },
    "iepiev_fca":     { "status": "STATUS_CLOSE" }
  }
}
```

**Impact:**  
Every market-hours gate in the application silently falls back to `LocalClockMarketStatusProvider` (wall-clock). The application never actually reads the exchange's authoritative session status. The `iepiev_regular` and `iepiev_fca` sub-sessions — which distinguish pre-open call auction from regular trading — are completely unreachable.

**Fix:**
```python
# Replace the multi-fallback field probing with the confirmed paths:
market_status = body["data"]["market"]["status"]
iepiev_regular_status = body["data"]["iepiev_regular"]["status"]
iepiev_fca_status = body["data"]["iepiev_fca"]["status"]
```

**Status enum values confirmed:**  
`"STATUS_CLOSE"` (post-market). Re-probe at 08:45 WIB to capture `STATUS_PRE_OPEN`, `STATUS_OPEN`, `STATUS_PRE_CLOSING`.

---

### Bug 2: Corp Action Parser Misses `stocksplit` Action Type
> **Status: ✅ Done** — `77546ef` (fixed before this doc was written, as part of the live corp action calendar refactor)

**File:** `src/infrastructure/browser/stockbit_corp_action.py` — `_TYPE_MAP`

**Problem:**  
`_TYPE_MAP` has `"split"` and `"stock split"` as keys. The API sends `"stocksplit"` (no space, confirmed in BBCA probe — 30 corp actions across `"dividend"`, `"rups"`, `"stocksplit"`). The payload dict key is also `"stocksplit"`, not `"split"`.

**Impact:**  
All stock split events are silently classified as `TYPE_OTHER` and stored with `detail = "stocksplit"`. The split-risk window check in the screener never fires for any stock. The `action_info` payload for splits is also keyed under `"stocksplit"`, so `split_exdate` and `split_ratio` are never extracted.

**Fix:**
```python
_TYPE_MAP: dict[str, str] = {
    # ... existing entries ...
    "stocksplit":   CorporateActionEvent.TYPE_SPLIT,  # ADD THIS — actual API key
    "split":        CorporateActionEvent.TYPE_SPLIT,  # keep for safety
    "stock split":  CorporateActionEvent.TYPE_SPLIT,
}

# And in _parse_events(), the payload lookup must match:
payload = info.get(raw_type.lower(), {})  # raw_type = "stocksplit" → correct key
```

---

### Bug 3: Bandar Detector Only Reads `top1`, Misses `top3`/`top5`/`top10`
> **Status: ✅ Done** — `beb1db5` (top3/top5/top10 + number_broker_buysell + vwap + total_value + total_volume added; broad_score property uses all 6 signals)

**File:** `src/infrastructure/browser/stockbit_bandar.py`

**Problem:**  
Parser extracts only `top1.accdist` and `top1.percent`. The live API returns five broker-group signals:

```json
"bandar_detector": {
  "avg":   { "accdist": "Neutral",    "amount": -48361996000, "percent": -4.79, "vol": -77092 },
  "avg5":  { "accdist": "Small Dist", "amount": -109973560000,"percent": -10.9, "vol": -175306 },
  "top1":  { "accdist": "Big Dist",   "amount": -324377800000,"percent": -32.15,"vol": -517084 },
  "top3":  { "accdist": "Small Dist", "amount": -103025600000,"percent": -10.21,"vol": -164231 },
  "top5":  { "accdist": "Small Acc",  "amount": 67913175000,  "percent": 6.73,  "vol": 108259  },
  "top10": { "accdist": "Neutral",    "amount": 34552230000,  "percent": 3.42,  "vol": 55079   },
  "broker_accdist": "Acc",
  "number_broker_buysell": -24,
  "total_buyer": 26,
  "total_seller": 50,
  "value": 1008870000000,
  "volume": 1608219,
  "average": 6273.213
}
```

**Impact:**  
`top1` alone (top operator) is a high-volatility signal prone to gaming. `top3`/`top5` smooth it out. `number_broker_buysell` (-24 = 24 more sellers than buyers) is a direct breadth signal. `average` (VWAP) is useful for comparing against IEP during pre-open. All are currently discarded.

**Fix:**  
Extend `BandarDetectorSnapshot` value object:
```python
@dataclass(frozen=True)
class BandarDetectorSnapshot:
    # existing fields ...
    top3_accdist: str | None = None
    top5_accdist: str | None = None
    top10_accdist: str | None = None
    number_broker_buysell: int | None = None   # negative = more sellers
    vwap: Decimal | None = None
    total_value: Decimal | None = None
    total_volume: int | None = None
```

---

### Bug 4: `accdist` Labels Are a 5-Level Ordinal, Not a 3-State Enum
> **Status: ✅ Done** — `beb1db5` (`_INTENSITY_SCORE` keys corrected to "Small Dist"/"Big Dist"; backward-compat aliases retained; score range updated to -6..+6)

**File:** `src/infrastructure/browser/stockbit_bandar.py` + any caller that checks this field

**Problem:**  
The `accdist` field has five distinct values: `"Big Acc"`, `"Small Acc"`, `"Neutral"`, `"Small Dist"`, `"Big Dist"`. Any code checking `accdist == "Acc"` silently misses `"Big Acc"` and `"Small Acc"`.

**Fix:**  
Map to an ordinal in the domain layer:
```python
ACCDIST_SCORE = {
    "Big Acc":   +2,
    "Small Acc": +1,
    "Neutral":    0,
    "Small Dist":-1,
    "Big Dist":  -2,
}

def accdist_score(label: str | None) -> int:
    return ACCDIST_SCORE.get(label or "", 0)
```

---

## 🟠 Priority 2 — High-Value Missing Data (API returns it, code ignores it)

---

### Item 5: Orderbook Missing ARA/ARB Auto-Reject Limits
> **Status: ✅ Done** — `d2c04d8` (`OrderBookSnapshot` gains `ara_price`, `arb_price`; screener candidate wired)

**File:** `src/infrastructure/browser/stockbit_order_book.py`

**API returns:**
```json
"ara": {"value": "7,550", "visible": true},
"arb": {"value": "5,375", "visible": true}
```

**Why it matters:**  
ARA/ARB are the hard daily price ceiling and floor set by IDX. An entry near ARA means the next day opens with a forced auto-reject if price hasn't corrected. The screener currently has no guard against this. For a stock at 7,400 with ARA at 7,550, the suggested entry of 7,500 is only 50 IDR from the ceiling.

**Fix:**  
Add `ara_price: Decimal | None` and `arb_price: Decimal | None` to `OrderBookTopOfBook` and wire into `ScreenerCandidate`. Add a screener warning when `entry_price > ara_price * 0.98`.

---

### Item 6: Orderbook Missing Foreign/Domestic % Split
> **Status: ✅ Done** — `d2c04d8` (`foreign_pct`, `domestic_pct` added to `OrderBookSnapshot`)

**File:** `src/infrastructure/browser/stockbit_order_book.py`

**API returns:**
```json
"foreign": "78.11",
"domestic": "21.89",
"fbuy": 1949692907500,
"fsell": 1632500595000,
"fnet": 317192312500
```

**Why it matters:**  
`fbuy`/`fsell`/`fnet` are already parsed for the pre-open foreign flow context. But `foreign`/`domestic` (% of total daily value) is a fast intraday signal: BBCA at 78% foreign participation is a very different risk profile than at 20%. This field is ready-made and requires no computation.

**Fix:**  
Add `foreign_pct: float | None` to `OrderBookTopOfBook`. Already fetched — just needs extracting.

---

### Item 7: Historical Summary Endpoint Already Contains Per-Day Foreign Flow
> **Status: ✅ Done** — `d2c04d8` (`fetch_foreign_flow_from_summary()` added; parses `data.result[]` → `ForeignFlowPoint` entities; 1 call vs N calls for backfill)

**File:** No parser for this use case exists — `_fetch_historical_summary_totals()` in `playwright_stockbit.py` only reads the aggregate total

**API returns per OHLCV row:**
```json
{
  "date": "2026-06-19",
  "open": 6050, "high": 6300, "low": 6050, "close": 6300,
  "change": 225, "change_percentage": 3.7,
  "volume": 3665955,
  "value": 2293015050000,
  "frequency": 38237,
  "foreign_buy": 1949692907500,
  "foreign_sell": 1632500595000,
  "net_foreign": 317192312500
}
```

**Pagination:** `data.paginate.{page, limit, totalrows, totalpages}` — note: `paginate` not `pagination`

**Why it matters:**  
The current foreign flow backfill loops over 10-15 broker codes, calling `/broker/activity/historical` once per code per ticker. The historical summary endpoint returns the same aggregate foreign flow per day in a single call. Backfilling 1 year of foreign flow for 50 tickers currently takes ~50× 15 = 750 API calls. With this endpoint it becomes 50 calls.

**Fix:**  
Build `StockbitHistoricalSummaryProvider`:
- Parses `data.result[]` (not `data.list[]`)
- Extracts OHLCV into `Candle` entities + `ForeignFlowPoint` entities from the same response
- Use as primary foreign flow backfill; reserve `/broker/activity/historical` only when per-broker attribution is specifically needed

---

### Item 8: Analyst Ratings Missing Price Target Range
> **Status: ✅ Done** — `d2c04d8` (`AnalystConsensus` gains `price_target_low`, `price_target_high`, `target_range_pct` property; SQL migration added)

**File:** `src/infrastructure/browser/stockbit_analyst.py`

**API returns:**
```json
"price_target": {
  "best_target": 8827,
  "best_low_target": 5500,
  "best_high_target": 10900,
  "current_price": 6300
}
```

**Currently parsed:** only `best_target` and `current_price`

**Why it matters:**  
The range (`best_low_target` to `best_high_target`) indicates analyst consensus tightness. A narrow range signals high conviction; a wide range signals deep disagreement. For BBCA: low = 5,500 vs. high = 10,900 — nearly 2× spread, very low consensus, `best_target` alone is misleading.

**Fix:**  
Add `price_target_low: int | None` and `price_target_high: int | None` to `AnalystConsensus` value object.

---

### Item 9: Forward Estimates Endpoint Completely Unimplemented
> **Status: ✅ Done** — `d2c04d8` + `9fb3e25` (new `ForwardEstimates` value object, `StockbitForwardEstimatesProvider`; wired into enrichment pipeline)

**Endpoint:** `GET /analyst-ratings/{ticker}/consensus`  
**File:** No parser exists

**API returns** (it's a list, not a dict — shape is different from `/analyst-ratings/{ticker}`):
```json
[
  {"name": "Revenue",    "items": [{"year": 2025, "is_estimate": false, "value": "118,573 B"}, {"year": 2026, "is_estimate": true, "value": "118,236 B"}]},
  {"name": "Op. Profit", "items": [...]},
  {"name": "Net Income", "items": [...]},
  {"name": "EPS",        "items": [{"year": 2025, "is_estimate": false, "value": "466.74"}, {"year": 2026, "is_estimate": true, "value": "490.46"}]}
]
```

**Why it matters:**  
Forward EPS estimates enable forward PE: `current_price / forward_eps`. For BBCA: current price 6,300 / forward EPS 490.46 = forward PE 12.8x — a higher-quality valuation signal than trailing PE (which uses last year's earnings). This is a standard screener metric used in every professional equity research tool.

**Fix:**  
Build `StockbitForwardEstimatesProvider`. Domain: `ForwardEstimate(ticker, metric, year, value, is_estimate)`. Add `forward_pe_1y` to `CompanyFundamentals`.

---

### Item 10: Keystats `stats` and `info` Sections Completely Ignored
> **Status: ✅ Done** — `d2c04d8` (`CompanyFundamentals` gains `market_cap_idr`, `pbv` from `data.info`; SQL migration added; `near_52w_high_rank` from `data.stats`)

**File:** `src/infrastructure/browser/stockbit_fundamentals.py`

**Currently:** Only iterates `data.closure_fin_items_results[].fin_name_results[].fitem.{name, value}`

**API also returns (same call, same response):**
```json
"stats": {
  "52_week_high": {"label": "52 Week High", "value": "10,400", "change_value": "-3,835", "change_percentage": "-36.88%"},
  "52_week_low":  {"label": "52 Week Low",  "value": "4,870",  "change_value": "+1,430", "change_percentage": "+29.36%"},
  "rank_near_52_week_high": {"label": "Rank (Near 52 Weeks High)", "value": "31.15%", "display_as": "progress_bar"}
},
"info": {
  "shares_outstanding": "123.28 B",
  "market_cap": {"formatted": "776.63 T", "raw": 776634150000000},
  "pbv": {"formatted": "3.00", "raw": 3.0}
},
"dividend_group": {
  "last_dividend_value": "Rp 20",
  "last_dividend_exdate": "17 Jun 26",
  "dividend_yield": "4.78%",
  "payout_ratio": "63.17%"
}
```

**Why it matters:**
- `market_cap.raw` → enables market cap filter in screener (exclude nano-caps with high IEV due to low float)
- `rank_near_52_week_high` → ready-made momentum signal; `31.15%` means price is at 31st percentile of its 52W range
- `dividend_yield` → already in `closure_fin_items_results` as a string; `dividend_group` gives it structured with ex-date
- These require **zero additional API calls** — they're in the same response body already being fetched

**Fix:**  
Add to `CompanyFundamentals` domain object: `market_cap_idr: int | None`, `near_52w_rank_pct: float | None`, `pbv: float | None`. Parse from `data.stats` and `data.info`. Add `min_market_cap_idr` to screener config YAML.

---

### Item 11: `nval_trend[]` in Broker Activity Universe Scan Is Dropped
> **Status: ✅ Done** — `d2c04d8` (`ForeignFlowSnapshot` gains `nval_trend` tuple; `_parse_nval_trend()` extracts per-day net value from universe scan; redundant per-stock historical call skipped)

**File:** `src/infrastructure/browser/playwright_stockbit.py` — `_parse_foreign_top_stocks()`

**API returns** inside each `brokers_buy[]` / `brokers_sell[]` entry:
```json
"nval_trend": [
  {"date": "2026-06-04", "nval": 53408687000, "nvol": 188925, "nfreq": 23891},
  {"date": "2026-06-05", "nval": 44105400000, "nvol": 159800, "nfreq": 19862},
  {"date": "2026-06-08", "nval": 65892517000, "nvol": 248166, "nfreq": 30506},
  {"date": "2026-06-09", "nval": 78054332000, "nvol": 292280, "nfreq": 23524},
  {"date": "2026-06-10", "nval": 73718883000, "nvol": 259706, "nfreq": 26691},
  {"date": "2026-06-11", "nval": 26264456000, "nvol":  91523, "nfreq": 19963},
  {"date": "2026-06-12", "nval": 52415253000, "nvol": 182626, "nfreq": 16046}
]
```

**Why it matters:**  
The current pre-open accumulation screen calls `/broker/activity` to find which stocks foreign brokers bought, then calls `/broker/activity/historical` per stock to get the 7-day trend for the accumulation score. The trend is already embedded in the initial universe scan response. We make a redundant second call for every candidate stock (~20-50 calls per screening run).

**Fix:**  
Parse `nval_trend[]` inside `_parse_foreign_top_stocks()` into `ForeignFlowPoint` entities and return them alongside `ForeignFlowSnapshot`. Skip the per-stock historical call for stocks where only 7-day context is needed; use the full historical call only when computing 30-day+ accumulation windows.

---

## 🟡 Priority 3 — New Capabilities

---

### Item 12: Intraday Broker Chart Provider
> **Status: ✅ Done** — `3322eb1` (`StockbitIntradayBrokerChartProvider` — broker-centric intraday chart, returns top stocks per broker; no cache, real-time)

**Endpoint:** `GET /order-trade/broker/activity-chart` (discovered during probe — not yet in any doc)  
**File:** No implementation exists

**What it returns:**  
Minute-by-minute cumulative net buy/sell value per broker for the current day, for each broker's top stocks. Separate `price_chart_data[]` (per-minute OHLC) and `broker_chart_data[]` (per-broker net value curve).

**Why it matters:**  
Distinguishes planned accumulation (broker starts buying at 09:00:00) from reactive buying (broker enters after a breakout at 09:30). The current `confirm_intraday_open.py` use case can only see if a broker was active today — not *when* during the day they acted.

**Suggested interface:**
```python
class IntradayBrokerChartProvider(Protocol):
    def fetch_broker_intraday_chart(self, ticker: str) -> IntradayBrokerChart | None: ...
```

---

### Item 13: Running Trade Chart Provider
> **Status: ✅ Done** — `3322eb1` (`StockbitRunningTradeChartProvider` — per-minute OHLC + top-broker cumulative net flows for a ticker; no cache)

**Endpoint:** `GET /order-trade/running-trade/chart/{ticker}`  
**File:** No implementation exists

**What it returns:**  
Per-minute OHLC candlestick (`price_chart_data[]`) and top-broker cumulative net value lines (`broker_chart_data[]`) for one ticker for one day.

**Why it matters:**  
Enables intraday surge detection: "did price break out in the first 5 minutes?" combined with "which broker drove it?" is a high-confidence intraday entry signal. Currently the screener only uses pre-open data; intraday confirmation relies on the user watching charts manually.

---

### Item 14: Market Cap Filter in Pre-Open Screener
> **Status: ✅ Done** — `3322eb1` (`min_market_cap_idr` added to `SwingConfig` + `AccumulationScreenRequest`; screener.min_market_cap_idr key in swing_screener.yaml; default 0 = off)

**Source:** `data.info.market_cap.raw` from keystats (already fetched, field ignored — see Item 10)

**Why it matters:**  
High-IEV stocks on the special monitoring board frequently have IEV > 1M lots but market cap < 100B IDR. These are penny stocks with low float where any small order creates a large IEV signal. The screener currently has no way to distinguish these from genuine institutional accumulation signals on large-cap stocks.

**Fix:**  
After parsing `market_cap_idr` from keystats (Item 10), add `min_market_cap_idr` to screener config. Default suggestion: 500B IDR (~mid-cap floor for IDX).

---

### Item 15: Screener Universe Endpoint Replaces Manual Sector Tree Walk
> **Status: ✅ Done** — `3322eb1` (`fetch_universe_map()` added to `StockbitUniverseProvider`; probes `/screener/universe` for flat index map in 1 call)

**Endpoint:** `GET /screener/universe`  
**File:** `src/infrastructure/browser/stockbit_universe.py` uses the sector hierarchy (`/emitten/sectors/{id}/subsectors` → `/emitten/v3/sector/{id}/subsector/{id}/company`)

**What it returns:**  
Complete flat list of all index IDs and names in one call. Contains IDs for every IDX index including DAYTRADE, TRADINGLIMIT, NOTASI-KHUSUS, IDXBUMN20, and 30+ others not currently in the codebase.

**Why it matters:**  
The current `universe_loader.py` makes 2-3 calls to navigate the sector tree for each index. `/screener/universe` returns the full map in one call and includes index IDs that the manual tree traversal misses.

---

### Item 16: Company Profile Endpoint Unimplemented
> **Status: ✅ Done** — `3322eb1` + `9fb3e25` (`StockbitCompanyProfileProvider` — background, listing board, IPO history, contacts; 30-day SQLite cache; wired into enrichment pipeline)

**Endpoint:** `GET /emitten/{ticker}/profile`  
**File:** No implementation exists

**What it returns:**
```json
{
  "background": "PT Bank Central Asia Tbk. ...",
  "history": {"amount": "927 B", "board": "Papan Utama", "date": "31 May 2000", "price": "1,400"},
  "key_executive": [...],
  "address": [{"phone": "...", "email": [...], "website": "...", "office": "..."}]
}
```

**Why it matters:**  
IPO price from `history.price` enables "return since IPO" context. `key_executive[]` enables governance monitoring (flag if CEO changed recently). `background` enables AI context enrichment without web scraping.

---

### Item 17: Total Shares Outstanding Not Captured in Shareholding
> **Status: ✅ Done** — `3322eb1` (`ShareholdingComposition` gains `total_shares`, `total_shares_formatted` from `periods[0].total_shares.raw`; SQL migration added)

**File:** `src/infrastructure/browser/stockbit_shareholding.py`

**API returns:**
```json
"periods": [{
  "report_date": "2026-05-29",
  "total_shares": {"raw": "123275050000", "formatted": "123.28B"},
  "compositions": [...]
}]
```

**Currently captured:** only `compositions[].percentage.raw` — the ownership percentages

**Why it matters:**  
Institution % alone is useful, but institution % × total shares × price = institutional holdings in IDR. This is a more actionable number: "Institutions hold 32% of BBCA" is less useful than "Institutions hold 250T IDR in BBCA, of which 67T IDR is in mutual funds."

**Fix:**  
Add `total_shares: int | None` and `total_shares_formatted: str | None` to `ShareholdingComposition`. Parse from `periods[0].total_shares.raw`.

---

## Implementation Priority Summary

| # | Priority | Effort | Impact | File | Status |
|---|----------|--------|--------|------|--------|
| 1 | 🔴 Bug | 5 min | Market status never reads from exchange | `stockbit_market_time.py` | ✅ `beb1db5` |
| 2 | 🔴 Bug | 5 min | Splits silently dropped from risk window | `stockbit_corp_action.py` | ✅ `77546ef` |
| 3 | 🔴 Bug | 1h | Bandar signal uses 1/5 of available data | `stockbit_bandar.py` + domain | ✅ `beb1db5` |
| 4 | 🔴 Bug | 30 min | Enum check fails for 4 of 5 real values | `stockbit_bandar.py` | ✅ `beb1db5` |
| 5 | 🟠 Data | 2h | No ARA/ARB guard in entry plan | `stockbit_order_book.py` + domain | ✅ `d2c04d8` |
| 6 | 🟠 Data | 1h | No intraday foreign/domestic split | `stockbit_order_book.py` + domain | ✅ `d2c04d8` |
| 7 | 🟠 Data | 3h | 10x API call reduction for backfill | New `StockbitHistoricalSummaryProvider` | ✅ `d2c04d8` |
| 8 | 🟠 Data | 1h | Target range signals analyst conviction | `stockbit_analyst.py` + domain | ✅ `d2c04d8` |
| 9 | 🟠 Data | 3h | Forward PE completely missing | New `StockbitForwardEstimatesProvider` | ✅ `d2c04d8` + `9fb3e25` |
| 10 | 🟠 Data | 2h | Market cap + momentum rank in same call | `stockbit_fundamentals.py` + domain | ✅ `d2c04d8` |
| 11 | 🟠 Data | 2h | ~40 redundant API calls per screening run | `playwright_stockbit.py` | ✅ `d2c04d8` |
| 12 | 🟡 Feature | 4h | Intraday timing of accumulation | New provider + use case | ✅ `3322eb1` |
| 13 | 🟡 Feature | 3h | Intraday surge detection | New provider | ✅ `3322eb1` |
| 14 | 🟡 Feature | 2h | Exclude nano-cap noise from screener | Screener config + fundamentals | ✅ `3322eb1` |
| 15 | 🟡 Feature | 2h | Universe lookup in 1 call vs 3 | New provider, replaces sector tree | ✅ `3322eb1` |
| 16 | 🟡 Feature | 2h | IPO price + executive context | New provider | ✅ `3322eb1` + `9fb3e25` |
| 17 | 🟡 Feature | 1h | Institutional holdings in IDR | `stockbit_shareholding.py` + domain | ✅ `3322eb1` |

**All 17 items completed.** Priority 1 bugs resolved in `beb1db5` (Bug 2 pre-dated this doc in `77546ef`). Priority 2 data gaps resolved in `d2c04d8`. Priority 3 features resolved in `3322eb1`.
