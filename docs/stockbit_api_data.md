# Stockbit Exodus API — Data Reference

Base URL: `https://exodus.stockbit.com`  
Auth: Bearer RS256 token (intercepted from browser session, not extractable from localStorage).  
Run `saham fetch stockbit login` then `saham fetch stockbit spy` to capture live responses.

---

## Response Shape Source Legend

Response shapes in this doc come from two different sources. Always check which label applies
before trusting a field name:

| Label | Meaning |
|-------|---------|
| **`[live-probed YYYY-MM-DD]`** | Field names captured directly from a real API response (via `saham fetch stockbit spy` or network interception). Highest confidence. |
| **`[from-parser YYYY-MM]`** | Field names extracted by reading the Python parser source code in `src/infrastructure/browser/`. The parser may only access a subset of fields the API actually returns. Confidence = as good as the parser implementation. |
| **`[unconfirmed]`** | No parser and no live probe exists. Shape is inferred or unknown — do not rely on it. |

**Note:** Sections added in the 2026-06 doc revision use `[from-parser]`. The original five
sections that already had "Confirmed response shape (2026-06-13)" tags were carried forward from
a prior version of this doc — their original confirmation source is unknown (likely live-probed,
but not verified).

---

## Authentication Notes

- All endpoints require `Authorization: Bearer <token>` header
- Token is RS256 JWT issued by Stockbit identity server — NOT the HS256 token stored in localStorage
- Reliable extraction: intercept from outgoing requests after navigating to `https://stockbit.com/orderbook`
- Token TTL: ~8–12 hours. In-process cache safe for ~30 minutes between batch calls
- 401 response → session expired → run `saham fetch stockbit login`

Required headers for all Exodus API requests:
```
Authorization: Bearer {RS256_TOKEN}
accept: application/json, text/plain, */*
x-platform: web
origin: https://stockbit.com
referer: https://stockbit.com/
```

---

## Parser Gotchas

These traps have bitten real parsers in this codebase — read before writing a new one.

| Field | Issue | Fix |
|-------|-------|-----|
| `price` in running trade | Comma-string: `"6,400"` | `int(s.replace(",",""))` |
| `lot` in running trade | Fractional string: `"0.98"` | `float(s)` then round |
| `date` in insider, `last_updated` in analyst | `"25 Mar 26"` (DD Mon YY, not ISO 8601) | `strptime(s, "%d %b %y")` |
| Broker sell `lot`/`value` in marketdetectors | May be negative in response | `abs()` when storing |
| `iep.raw` during regular session (09:00–15:49 WIB) | Returns `0` (no call auction) | Guard: `if iep > 0` |
| Notation field name | Stockbit sends `"notation"` OR `"notations"` | `data.get("notation") or data.get("notations")` |
| `fitem.value` in keystats | String with `%` and commas: `"14.3%"` | Strip `%` and `,` then cast float |
| `data` in corp action response | Flat list, not `data.items` or `data.records` | `data = body["data"]; assert isinstance(data, list)` |
| `changes.value` in insider | Signed comma-string: `"+147,933"` | Strip `+`, `-`, `,` then `int()` |
| `total_bid_offer.bid.lot` in order book | Comma-string: `"49,960,400"` | Strip commas |
| Running trade tick date | Time only, no date: `"09:15:32"` | Combine with current IDX market date |
| `type` in marketdetectors broker row | `"Asing"` = foreign, `"Lokal"` = domestic | Map explicitly |

---

## Per-Ticker Endpoints

### 1. Company Info
```
GET /emitten/{ticker}/info
```
**Response shape [from-parser 2026-06]:**
```
data.status                               → trading status string (e.g. "active", "suspended")
data.tradeable                            → bool
data.sector                               → sector name (string)
data.sub_sector                           → sub-sector name (string)
data.trading_limit_info.haircut_percentage→ margin haircut % (string or null)
data.notation[] / data.notations[]        → list (try both key names):
  [].notation_code / [].code             → notation code (e.g. "E", "B", "X")
  [].notation_desc / [].description      → human-readable label
data.market_hour.status                   → per-stock market status string
data.market_hour.suspend_info             → suspension reason string (null if not suspended)
data.corp_action.active / data.corpaction.active → bool (upcoming corp action flag)
data.has_uma / data.uma                   → bool (UMA — Unusual Market Activity)
data.catalogs[]                           → list of index/board memberships:
  [].catalog_name / [].company_symbol    → catalog or index name
  [].company_type                        → "listing-board" for board type entries
  [].show                                → bool (false = hidden, skip when rendering)
```
**Implementation:** `src/infrastructure/browser/stockbit_ticker_notation.py`  
**Cache:** SQLite `ticker_notation_cache`, 1-day TTL.

---

### 2. Company Profile
```
GET /emitten/{ticker}/profile
```
**Not yet implemented — JSON shape unknown.**  
To capture: `saham fetch stockbit spy`, then navigate to a company profile page in Stockbit.

---

### 3. Shareholding Composition
```
GET /insider/shareholding/composition/companies/{ticker}
```
**Response shape [from-parser 2026-06]:**
```
data.periods[]                            → list of reporting periods (newest first, use [0])
  [0].report_date                        → "YYYY-MM-DD" (IDX filing date)
  [0].compositions[]                     → ownership breakdown list:
    [].label                             → category name (string):
                                           Named entity: e.g. "DWIMURIA INVESTAMA ANDALAN"
                                           Category values: "Mutual Funds", "Individual",
                                           "Pension Funds", "Insurance", "Bank",
                                           "Exchange Traded Funds", "Hedge Fund",
                                           "Government", "State Owned Enterprises",
                                           "Securities Company", "Corporate",
                                           "Investment Manager", "Private Equity",
                                           "Foundation", "Cooperatives", etc.
    [].percentage.raw                    → float (ownership %, e.g. 54.3)
```
**Aggregation pattern:** `institution_pct` = sum of all known category labels. Entries whose
label is NOT in the known-category set are treated as named controlling shareholders.  
**Implementation:** `src/infrastructure/browser/stockbit_shareholding.py`  
**Cache:** SQLite `shareholding_composition`, 7-day TTL (filings land quarterly).

---

### 4. Corporate Action (Per Ticker)
```
GET /corpaction/{ticker}?limit=50
```
**Response shape [from-parser 2026-06]:**
```
data[]                                    → FLAT list of action objects (not data.items or data.records)
  [].action_type                         → "dividend" | "rups" | "rightissue" | "split" |
                                           "bonus" | "warrant" | "ipo" | "tenderoffer"
                                           (also: "dividen", "hmetd" in the wild)
  [].action_info                         → dict keyed by action_type string:

    # Dividend
    .dividend.dividend_exdate            → "YYYY-MM-DD"
    .dividend.dividend_cumdate           → "YYYY-MM-DD"
    .dividend.dividend_recdate           → "YYYY-MM-DD"
    .dividend.dividend_paydate           → "YYYY-MM-DD"
    .dividend.dividend_created           → "YYYY-MM-DD" (announcement date)
    .dividend.dividend_value             → IDR per share (string or number)
    .dividend.corp_action_active         → bool

    # RUPS (General Meeting)
    .rups.rups_date                      → "YYYY-MM-DD" (AGM date — stored as ex_date)
    .rups.rups_time                      → "HH:MM" string
    .rups.rups_venue                     → venue name string
    .rups.rups_created                   → "YYYY-MM-DD"
    .rups.corp_action_active             → bool

    # Rights Issue (HMETD)
    .rightissue.rightissue_exdate        → "YYYY-MM-DD" (also try "ex_date")
    .rightissue.rightissue_cumdate       → "YYYY-MM-DD" (also try "cum_date")
    .rightissue.rightissue_recdate       → "YYYY-MM-DD"
    .rightissue.rightissue_paydate       → "YYYY-MM-DD"
    .rightissue.rightissue_price         → IDR subscription price (also "subscription_price")

    # Split
    .split.split_exdate                  → "YYYY-MM-DD" (also try "ex_date")
    .split.split_ratio                   → ratio string, e.g. "1:5" (also "ratio")
```
**Gotcha:** `data` is a flat list — parse with `items = body["data"] if isinstance(body["data"], list)`.  
**Implementation:** `src/infrastructure/browser/stockbit_corp_action.py`  
**Cache:** SQLite `corp_action_cache`, 1-day TTL.

---

### 5. Major Holder / Insider Activity (Per Ticker)
```
GET /insider/company/majorholder?symbols={ticker}&date_start=YYYY-MM-DD&date_end=YYYY-MM-DD
    &page=1&limit=50&action_type=ACTION_TYPE_UNSPECIFIED&source_type=SOURCE_TYPE_UNSPECIFIED
```
**Params:**
- `action_type`: `ACTION_TYPE_BUY`, `ACTION_TYPE_SELL`, `ACTION_TYPE_UNSPECIFIED`
- `source_type`: `SOURCE_TYPE_UNSPECIFIED` (IDX filing source filter)

**Response shape [from-parser 2026-06]:**
```
data.movement[]                           → list of transactions (newest first):
  [].name                                → insider full name (string)
  [].symbol                              → ticker (string)
  [].date                                → "25 Mar 26"  ← DD Mon YY — NOT ISO 8601
  [].action_type                         → "ACTION_TYPE_BUY" | "ACTION_TYPE_SELL"
  [].changes.value                       → "+147,933" (signed, comma-formatted shares string)
  [].changes.formatted_value             → same value (fallback field name)
  [].price_formatted                     → "6,982" (IDR per share, comma-formatted string)
  [].previous.percentage                 → "0.0002" (ownership % before, as string)
  [].current.percentage                  → "0.0003" (ownership % after, as string)
  [].badges[]                            → ["SHAREHOLDER_BADGE_DIREKTUR"] |
                                           ["SHAREHOLDER_BADGE_KOMISARIS"] | []
```
**Gotcha:** Date format is `"%d %b %y"` — e.g. `"25 Mar 26"`.  
**Gotcha:** All numeric values (shares, price, percentages) arrive as comma-formatted strings.  
**Implementation:** `src/infrastructure/browser/stockbit_insider.py`  
**Cache:** SQLite `insider_cache`, 1-day TTL.

---

### 6. Order Book
```
GET /company-price-feed/v2/orderbook/companies/{ticker}
```
**Response shape [prior-doc, source unknown — likely live-probed 2026-06-13]:**
```
data.iepiev.best_bid_offer.bid.price.raw      → best bid price (int, IDR)
data.iepiev.best_bid_offer.bid.quantity.raw   → best bid quantity (int, already in lots)
data.iepiev.best_bid_offer.offer.price.raw    → best offer price (int, IDR)
data.iepiev.best_bid_offer.offer.quantity.raw → best offer quantity (int, lots)
data.iepiev.iep.raw                           → IEP (int, IDR; 0 during regular session)
data.iepiev.iev.raw                           → IEV (int, lots; 0 during regular session)
data.bid[]                                    → full bid depth list:
  [].price                                   → price (string, IDR)
  [].volume                                  → volume (int, SHARES — divide by 100 for lots)
  [].que_num                                 → queue order number (int)
  [].change_percentage                       → price change % (string)
data.offer[]                                  → full offer depth list (same shape as bid[])
data.total_bid_offer.bid.lot                  → total bid lots (comma-string: "49,960,400")
data.total_bid_offer.offer.lot                → total offer lots (comma-string)
data.lastprice                                → last traded price (int, IDR)
data.fnet                                     → running foreign net value today (float, IDR)
data.fbuy                                     → running foreign buy value today (float, IDR)
data.fsell                                    → running foreign sell value today (float, IDR)
```
**Gotcha:** `bid[].volume` is in SHARES — divide by 100 for lots. `best_bid_offer.quantity.raw` is already in lots.  
**Implementation:** `src/infrastructure/browser/stockbit_order_book.py`

---

### 7. Historical Price Summary (OHLCV)
```
GET /company-price-feed/historical/summary/{ticker}?period=HS_PERIOD_DAILY&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&limit=12&page=1
```
**Params:**
- `period`: `HS_PERIOD_DAILY`, `HS_PERIOD_WEEKLY`, `HS_PERIOD_MONTHLY`

**Not yet implemented — JSON shape unknown.**  
Likely follows standard paginated shape: `data.list[]` with OHLCV fields and `data.pagination.has_next`.

---

### 8. Running Trade (Live Tape)
```
GET /order-trade/running-trade?symbols[]={ticker}&sort=DESC&limit=80&order_by=RUNNING_TRADE_ORDER_BY_TIME
```
**Response shape [from-parser 2026-06]:**
```
data.running_trade[]                      → list of tick objects (newest first):
  [].time                                → "HH:MM:SS"  ← time only, NO date
  [].price                               → "6,400"  ← IDR, comma-formatted STRING
  [].lot                                 → "0.98"  ← STRING, may be fractional (NG board)
  [].code                                → ticker (string)
  [].buyer                               → buyer broker code ("" when is_broker_exists=false)
  [].seller                              → seller broker code (string)
  [].buyer_type                          → "BROKER_TYPE_UNSPECIFIED" or broker code
  [].seller_type                         → broker code
  [].is_broker_exists                    → bool (false = anonymous tick)
  [].market_board                        → "RG" (regular) | "NG" (negotiated) | "TN" (tunai/cash)
  [].value.raw                           → int (IDR trade value)
```
**Gotcha:** `price` and `lot` are strings — cast after stripping commas. No cache — real-time only.  
**Gotcha:** Ticks have no date — combine `time` with today's IDX market date.  
**Implementation:** `src/infrastructure/browser/stockbit_running_trade.py`

---

### 9. Running Trade Chart (Intraday Volume Profile)
```
GET /order-trade/running-trade/chart/{ticker}?period=RT_PERIOD_LAST_1_DAY&investor_type=INVESTOR_TYPE_ALL&market_board=BOARD_TYPE_REGULAR
```
**Params:**
- `investor_type`: `INVESTOR_TYPE_ALL`, `INVESTOR_TYPE_FOREIGN`, `INVESTOR_TYPE_LOCAL`
- `market_board`: `BOARD_TYPE_REGULAR`, `BOARD_TYPE_NEGOTIATED`

**Not yet implemented — JSON shape unknown.**

---

### 10. Market Detector (Named Broker Breakdown Per Ticker)
```
GET /marketdetectors/{ticker}?transaction_type=TRANSACTION_TYPE_NET&market_board=MARKET_BOARD_REGULER&investor_type=INVESTOR_TYPE_ALL&limit=25&period=BROKER_SUMMARY_PERIOD_LATEST
```
**Params:**
- `period`: `BROKER_SUMMARY_PERIOD_LATEST`, `BROKER_SUMMARY_PERIOD_LAST_7_DAYS`, `BROKER_SUMMARY_PERIOD_LAST_1_MONTH`, `BROKER_SUMMARY_PERIOD_LAST_3_MONTHS`, `BROKER_SUMMARY_PERIOD_LAST_6_MONTHS`, `BROKER_SUMMARY_PERIOD_LAST_1_YEAR`
- `transaction_type`: `TRANSACTION_TYPE_NET`, `TRANSACTION_TYPE_BUY`, `TRANSACTION_TYPE_SELL`

**Response shape [prior-doc, source unknown — likely live-probed 2026-06-13]:**
```
data.broker_summary.brokers_buy[]         → top net buyer brokers:
  [].netbs_broker_code                   → broker code (e.g. "AK")
  [].blot                                → net buy lots (int)
  [].bval                                → net buy value (IDR, Decimal)
  [].netbs_buy_avg_price                 → average buy price (IDR, Decimal)
  [].type                                → "Asing" (foreign) | "Lokal" (domestic)
  [].netbs_date                          → trading date (YYYYMMDD string)

data.broker_summary.brokers_sell[]        → top net seller brokers:
  [].netbs_broker_code                   → broker code
  [].slot                                → sell lots (int, may be negative)
  [].sval                                → sell value (IDR, may be negative)
  [].netbs_sell_avg_price                → average sell price
  [].type                                → "Asing" | "Lokal"
  [].netbs_date                          → trading date (YYYYMMDD)
```
**Note:** This same endpoint also carries `data.bandar_detector.*` — see §10b below.  
**Implementation:** `src/infrastructure/browser/playwright_stockbit.py` (`_parse_marketdetectors_response`)  
**Cache:** SQLite `broker_summaries`.

---

### 10b. Bandar Detector Signal
```
GET /marketdetectors/{ticker}?transaction_type=TRANSACTION_TYPE_NET&market_board=MARKET_BOARD_REGULER&investor_type=INVESTOR_TYPE_ALL&limit=25&period=BROKER_SUMMARY_PERIOD_LATEST
```
Same URL as §10 — different response path within the same JSON body.

**Response shape [from-parser 2026-06]:**
```
data.bandar_detector.broker_accdist       → "Acc" | "Dis" | "Neutral"
data.bandar_detector.avg.accdist          → today's intensity label (string)
data.bandar_detector.avg.percent          → float (avg net % of total daily volume)
data.bandar_detector.avg5.accdist         → 5-session intensity label (string)
data.bandar_detector.top1.accdist         → top operator's label (string)
data.bandar_detector.top1.percent         → float (top operator concentration %)
data.bandar_detector.total_buyer          → int (number of net buying brokers)
data.bandar_detector.total_seller         → int (number of net selling brokers)
```
**Implementation:** `src/infrastructure/browser/stockbit_bandar.py`  
**Cache:** SQLite keyed by `(ticker, session_date)` — fixed after market close.

---

### 11. Broker Distribution
```
GET /order-trade/broker/distribution?date=&symbol={ticker}&investor_type=INVESTOR_TYPE_ALL&market_board=MARKET_TYPE_REGULER&data_type=BROKER_DISTRIBUTION_DATA_TYPE_VALUE&period=TB_PERIOD_LAST_1_DAY
```
**Params:**
- `data_type`: `BROKER_DISTRIBUTION_DATA_TYPE_VALUE`, `BROKER_DISTRIBUTION_DATA_TYPE_VOLUME`
- `period`: `TB_PERIOD_LAST_1_DAY`, `TB_PERIOD_LAST_1_WEEK`, `TB_PERIOD_LAST_1_MONTH`

**Not yet implemented — JSON shape unknown.**

---

### 12. Broker Activity Historical (Per Ticker, Per Broker, Daily Series)
```
GET /order-trade/broker/activity/historical?interval=INTERVAL_DAILY&broker_codes={code}&symbols={ticker}&market_board=BOARD_TYPE_REGULAR&investor_type=INVESTOR_TYPE_ALL&period=RT_PERIOD_LAST_1_YEAR&pagination.page=1&pagination.limit=100
```
**Response shape [prior-doc, source unknown — likely live-probed 2026-06-13]:**
```
data.broker_name                          → full broker name (string; only when single code)
data.records[]                            → daily records (paginated, 100/page):
  [].date                                → "YYYY-MM-DD"
  [].trade_activity.buy_summary.lot      → buy lots (int)
  [].trade_activity.buy_summary.value    → buy value (IDR, Decimal)
  [].trade_activity.buy_summary.avg_price→ avg buy price (Decimal)
  [].trade_activity.sell_summary.lot     → sell lots (int)
  [].trade_activity.sell_summary.value   → sell value (IDR, Decimal)
  [].trade_activity.sell_summary.avg_price→ avg sell price (Decimal)
  [].trade_activity.net_summary.lot      → net lots (positive=net buy, negative=net sell)
  [].trade_activity.net_summary.value    → net value (IDR, can be negative)
  [].trade_activity.net_summary.avg_price→ avg net price (Decimal)
  [].trade_activity.total_buy_lot.pct    → broker's share of total market buy volume (%)
  [].trade_activity.total_sell_lot.pct   → broker's share of total market sell volume (%)
  [].price_activity.close_price          → stock close price that day (fallback for avg_price)
data.pagination.has_next                  → bool (true = more pages available)
```
**Implementation:** `src/infrastructure/browser/playwright_stockbit.py` (`_parse_foreign_flow_history`)  
**Cache:** SQLite `broker_daily_flows`.

---

### 13. Seasonality
```
GET /company-price-feed/seasonality/{ticker}?year=2026&back_year=5
```
**Response shape [from-parser 2026-06]:**
```
data.avg.columns[]                        → avg monthly return: [{name: "Jun", value: "0.87"}]
data.prob.columns[]                       → win rate %:         [{name: "Jun", value: "60"}]
data.up.columns[]                         → positive year count: [{name: "Jun", value: "3"}]
data.total_months.columns[]               → total year count:    [{name: "Jun", value: "5"}]
data.default_last_year                    → int (back years actually used)
```
Each section has `columns[]` with 12 entries, one per month. Each entry: `{name: "<3-letter abbrev>", value: "<number as string>"}`.  
**Pattern:** A single API call returns all 12 months — extract the target month by matching `name`.  
**Implementation:** `src/infrastructure/browser/stockbit_seasonality.py`  
**Cache:** SQLite `seasonality_cache`, monthly TTL (data only changes when a new month completes).

---

### 14. Analyst Consensus
```
GET /analyst-ratings/{ticker}/consensus
```
**Not yet implemented — JSON shape unknown.** See §15 for the implemented individual-ratings endpoint.

---

### 15. Analyst Ratings
```
GET /analyst-ratings/{ticker}
```
**Response shape [from-parser 2026-06]:**
```
data.recommendation                       → "Buy" | "Hold" | "Sell" (string)
data.total_buy                            → int (number of buy-rated analysts)
data.total_hold                           → int
data.total_sell                           → int
data.total_analyst                        → int
data.price_target.best_target             → int (IDR, consensus average target price)
data.price_target.current_price           → int (IDR, last price at fetch time)
data.last_updated                         → "15 Jun 26"  ← DD Mon YY format
```
**Gotcha:** `last_updated` uses `"%d %b %y"` format — same quirk as insider `date` field.  
**Implementation:** `src/infrastructure/browser/stockbit_analyst.py`  
**Cache:** SQLite, 1-day TTL.

---

### 16. Company Financial Statements
```
GET /findata-view/company/financial?symbol={ticker}&data_type=1&report_type=1&statement_type=1
```
**Params:**
- `data_type`: `1`=Annual, `2`=Quarterly, `3`=TTM
- `report_type`: `1`=IDR, `2`=USD
- `statement_type`: `1`=Income Statement, `2`=Balance Sheet, `3`=Cash Flow

**Not yet implemented — JSON shape unknown.**

---

### 17. Key Statistics / Financial Ratios
```
GET /keystats/ratio/v1/{ticker}?year_limit=10
```
**Response shape [from-parser 2026-06]:**
```
data.closure_fin_items_results[]          → list of financial category groups:
  [].fin_name_results[]                  → list of individual metrics:
    [].fitem.name                        → metric name (string):
                                           "Return on Equity (TTM)"
                                           "Current PE Ratio (TTM)"
                                           "Net Profit Margin (Quarter)"
                                           "Revenue (Quarter YoY Growth)"
                                           "Piotroski F-Score"
                                           "Dividend Yield"
                                           "52 Week High"
                                           "52 Week Low"
                                           "Rank (Near 52 Weeks High)"
    [].fitem.value                       → metric value (STRING — may contain "%" and ",")
```
**Extraction pattern:** Flatten `closure_fin_items_results[].fin_name_results[]` and match on `fitem.name`. Value is always a string — cast to float after stripping `%` and `,`.  
**Implementation:** `src/infrastructure/browser/stockbit_fundamentals.py`  
**Cache:** SQLite, 7-day TTL.

---

### 18. Earnings (EPS Recap — Per Ticker)
```
GET /earnings?search={ticker}&quarter=4&year=2025&sort_column=4&order=desc&page=1
```
**Not yet implemented — JSON shape unknown.**

---

## General / Market-Wide Endpoints

### 19. Market Time
```
GET /company-price-feed/market-time
```
**Partial — exact field names not confirmed via spy.** Implementation falls back to wall-clock when API unavailable.
```
data.status / market_status / marketStatus  → session status string (naming uncertain)
data.session_name / sessionName / session   → session label (naming uncertain)
data.open_time / openTime / session_open    → session open time (naming uncertain)
data.close_time / closeTime / session_close → session close time (naming uncertain)
```
**Action:** Run `saham fetch stockbit spy` and navigate to orderbook page to capture exact field names.  
**Implementation:** `src/infrastructure/browser/stockbit_market_time.py`

---

### 20. Sector and Sub-Sector Lists
```
GET /emitten/sectors
GET /emitten/sectors/{sector_id}/subsectors
GET /emitten/v3/sector/{sector_id}/subsector/{subsector_id}/company
```
**Partially confirmed (2026-06):**
```
# Sector list
data[]                                    → list of sector objects:
  [].id                                  → sector id (int)
  [].name                                → sector name (string)

# Company list per subsector
data.companies[]                          → list of companies:
  [].symbol                             → ticker (string)
  [].company_name                       → full company name (string)
```

**Known sector IDs:**
| Sector | ID |
|--------|----|
| Indeks Sektoral | 70 |
| Keuangan (Finance) | 3 |
| Global Indices | 78 |
| Indonesia Index Universes | 88 |

**Known index universe subsectors (under sector 88):**
| Universe | Subsector ID |
|----------|-------------|
| IHSG (all) | 467 |
| LQ45 | 550 |
| IDX30 | 559 |
| JII | 551 |
| MBX | 552 |
| BUMN20 | 1000000011 |

**Implementation:** `src/infrastructure/browser/stockbit_universe.py`

---

### 21. Corporate Action Calendar (Market-Wide)
```
GET /corpaction/dividend
GET /corpaction/stocksplit
GET /corpaction/reversesplit
GET /corpaction/rightissue
GET /corpaction/bonus
GET /corpaction/tenderoffer
GET /corpaction/rups
GET /corpaction/pubex
GET /corpaction/ipo
```
**v1 supported (implemented 2026-07):** dividend, stocksplit → `stock_split`, reversesplit → `reverse_split`,
rightissue → `rights_issue`, bonus, tenderoffer → `tender_offer`, rups, pubex, ipo.

**Explicitly NOT fetched in v1:**
```
GET /corpaction/warrant   — per-ticker warrant series, not a calendar concept, out of scope
GET /corpaction/economic  — macroeconomic calendar, unrelated to corporate actions, out of scope
```

**Implementation:** `src/infrastructure/browser/stockbit_corporate_action_calendar.py`
(`StockbitCorporateActionCalendarProvider`) + `src/infrastructure/persistence/sqlite_corporate_action_calendar_repository.py`.
**Storage:** SQLite `corporate_action_events` / `corporate_action_event_dates` / `corporate_action_calendar_sync`
(market-wide — distinct from the per-ticker `corp_action_cache` table in §4 above).
**CLI:** `saham fetch calendar`; also synced once per `saham fetch market` run (see `docs/data_sources.md`
"Market-Wide Corporate Action Calendar" section for the full table/query/freshness reference).

---

#### `/corpaction/dividend` — ~463 items
```
data:
  today: "2026-07-10"        ← reference date the API uses
  dividend[]:
    company_id, company_symbol
    corp_action_active        → bool
    dividend_cumdate          → "2026-07-08"  (YYYY-MM-DD)
    dividend_exdate           → "2026-07-09"
    dividend_recdate          → "2026-07-10"
    dividend_paydate          → "2026-07-31"
    dividend_value            → "25.65" (string, raw value per share)
    dividend_value_formatted  → "Rp 25.65"
    lastprice                 → "468" (string, current price)
    lastprice_formatted       → "468"
    dividend_currency         → "CURRENCY_IDR"
    dividend_fiscal_year      → int
    dividend_value_adjusted   → int
    dividend_id, dividend_datahash, dividend_lock, dividend_created
    event_note                → string, optional
```

---

#### `/corpaction/stocksplit` — ~9 items
```
data:
  stocksplit[]:
    company_id, company_symbol
    corp_action_active        → bool
    stocksplit_cumdate        → "2026-07-28"
    stocksplit_exdate         → "2026-07-29"
    stocksplit_recdate        → "2026-07-30"
    stocksplit_ratio          → "1 : 25" (string: "old : new")
    stocksplit_factor         → "25" (string)
    stocksplit_old            → "1"
    stocksplit_new            → "25"
    stocksplit_new_price      → int (0 if unknown)
    stocksplit_new_share      → int
    stocksplit_id, stocksplit_created, stocksplit_lock, event_note
```

---

#### `/corpaction/reversesplit` — ~0 items (rare)
Same field shape as stocksplit with `stock_reverse_*` prefix under `data.stock_reverse[]`.

---

#### `/corpaction/rightissue` — ~23 items
```
data:
  rightissue[]:
    company_id, company_symbol
    corp_action_active        → bool
    rightissue_cumdate        → "2026-08-24"
    rightissue_exdate         → "2026-08-26"
    rightissue_recdate        → "2026-08-27"
    rightissue_subdate        → "" (subscription date)
    rightissue_trading_start  → "2026-08-31"
    rightissue_trading_end    → "2026-09-04"
    rightissue_ratio          → "2 : 1" (string: "old : new")
    rightissue_factor         → "1.5"
    rightissue_old            → "2"
    rightissue_new            → "1"
    rightissue_price          → 500 (int; formatted string also in rightissue_price_formatted)
    rightissue_adj_factor     → int
    rightissue_foreign_percentage → int
    rightissue_local_percentage   → int
    rightissue_number_of_securities
    rightissue_id, rightissue_created, rightissue_lock, event_note
```

---

#### `/corpaction/warrant` — ~1,315 items (all warrant series across all tickers)
```
data:
  warrant[]:
    company_id, company_symbol
    corp_action_active        → bool
    wrant_serie               → "" (warrant series label, e.g. "Seri I")
    wrant_trading_from        → "2026-07-14" (trading start)
    wrant_trading_end         → "2031-07-09" (trading end)
    wrant_exc_from            → "2027-01-14" (exercise start)
    wrant_exc_end             → "2031-07-14" (exercise end)
    wrant_exc_price           → "145" (string, exercise price)
    wrant_exc_price_formatted
    wrant_total               → "" (total warrants, string)
    wrant_foreign_percentage, wrant_local_percentage
    wrant_number_of_securities
    wrant_id, wrant_lastupdate, event_note
```
**Note:** ~1,315 items is very large (all warrant series). Consider filtering by `?symbol=` or paginating.

---

#### `/corpaction/bonus` — ~10 items
```
data:
  bonus[]:
    company_id, company_symbol
    corp_action_active        → bool
    sahabonus_ratio           → "100 : 30" (string)
    sahabonus_id, sahabonus_iqp_id
    sahabonus_new_price, sahabonus_new_share
    stocksplit_cumdate        → "2026-07-08"  (note: reuses stocksplit field names)
    stocksplit_exdate         → "2026-07-09"
    stocksplit_recdate        → "2026-07-10"
    stocksplit_paymentdate    → "2026-07-30"
    stocksplit_factor         → "1.3"
    stocksplit_old, stocksplit_new
    event_note
```

---

#### `/corpaction/tenderoffer` — ~42 items
```
data:
  tender[]:
    company_id, company_name, company_symbol
    corp_action_active        → bool
    tender_start              → "2026-07-09" (offer start)
    tender_end                → "2026-08-07" (offer end)
    tender_paydate            → "2026-08-14"
    tender_price              → "523" (string)
    tender_price_formatted
    tender_shares             → "994442000" (string, total shares sought)
    tender_percentage         → "35.00" (string, % of outstanding)
    tender_created, tender_datahash
    tender_id, event_note
```

---

#### `/corpaction/rups` — ~964 items
```
data:
  rups[]:
    company_id, company_symbol, company_name
    corp_action_active        → bool
    rups_date                 → "2026-08-18"
    rups_time                 → "10:00"
    rups_venue                → "Kantor Pusat ..." (full address string)
    rups_eligible_date        → "2026-07-22"
    rups_iqp_agenda, rups_iqp_type, rups_iqp_result
    rups_iqp_remark, rups_iqp_rec_dt, rups_iqp_revised_date
    rups_created, rups_datahash, rups_id
    company_icon_url
```

---

#### `/corpaction/pubex` — ~400 items
```
data:
  pubex[]:
    company_id, company_symbol
    corp_action_active        → bool
    puexp_date                → "2026-07-23"
    puexp_time                → "15:00:00"
    puexp_venue               → "dilakukan secara online" (string)
    puexp_id, puexp_lastupdate
```

---

#### `/corpaction/ipo` — ~15 items
```
data:
  ipo[]:
    ipo_id, company_id, company_symbol, company_name
    corp_action_active        → bool
    ipo_listing_date          → "2026-07-10"
    ipo_price                 → { minimum: 0, maximum: 0, final: 170 }
    ipo_data                  → JSON string (raw): {"%":"20.02","Offering Start":"...", ...}
    ipo_data_detail           → structured object:
      price, shares, percentage, offering_start, offering_end,
      allotment_date, refund_date, listing_board, underwriter[], bureau_administration
    ipo_created, ipo_iqp_id
```

---

#### `/corpaction/economic` — ~135 items (macroeconomic calendar)
```
data:
  today: "2026-07-10"
  timezone: int
  economic[]:
    econcal_id
    econcal_date              → "2026-07-10"
    econcal_time              → "07:00:00"
    econcal_month             → "JUN"
    econcal_item              → "Car Sales YoY" (event name)
    econcal_actual            → "12.0%" (actual value string)
    econcal_previous          → "14.0%" (previous value string)
    econcal_forecast          → "" (forecast value string)
    econcal_lastdate          → "2026-07-10T21:00:06+07:00"
```

---

### 22. IEV Market Movers (Pre-Open Screener)
```
GET /order-trade/market-mover?mover_type=MOVER_TYPE_IEV_TOP_GAINER&filter_stocks=FILTER_STOCKS_TYPE_MAIN_BOARD&filter_stocks=FILTER_STOCKS_TYPE_DEVELOPMENT_BOARD...
```
**Params:**
- `mover_type`: `MOVER_TYPE_IEV_TOP_GAINER`, `MOVER_TYPE_TOP_GAINER`, `MOVER_TYPE_TOP_LOSER`, `MOVER_TYPE_MOST_ACTIVE_VOLUME`, `MOVER_TYPE_MOST_ACTIVE_VALUE`
- `filter_stocks`: `FILTER_STOCKS_TYPE_MAIN_BOARD`, `FILTER_STOCKS_TYPE_DEVELOPMENT_BOARD`, `FILTER_STOCKS_TYPE_ACCELERATION_BOARD`, `FILTER_STOCKS_TYPE_NEW_ECONOMY_BOARD`, `FILTER_STOCKS_TYPE_SPECIAL_MONITORING_BOARD`

**Note:** Main boards and Special Monitoring Board must be separate API calls — they cannot be combined in one request.

**Response shape [prior-doc, source unknown — likely live-probed 2026-06-13]:**
```
data.mover_list[]                         → ranked list:
  [].stock_detail.code                   → ticker symbol (string)
  [].iepiev_detail.iev.raw               → IEV (Indicative Equivalent Volume, int, lots)
  [].iepiev_detail.iep.raw               → IEP (Indicative Equilibrium Price, int, IDR; may be absent)
```
**Implementation:** `src/infrastructure/browser/playwright_stockbit.py` (`_parse_iev_response`)

---

### 23. Insider Activity (All Tickers, Market-Wide)
```
GET /insider/company/majorholder?date_start=YYYY-MM-DD&date_end=YYYY-MM-DD&page=1&limit=20&action_type=ACTION_TYPE_UNSPECIFIED&source_type=SOURCE_TYPE_UNSPECIFIED
```
Same response shape as §5 (per-ticker insider) — same `data.movement[]` structure.  
**Not yet implemented as a standalone market-wide scan.**

---

### 24. Earnings Recap (All Tickers)
```
GET /earnings?sort_column=4&order=desc&page=1
GET /earnings?quarter=4&year=2025&sort_column=4&order=desc&page=1
```
**Not yet implemented — JSON shape unknown.**

---

### 25. Valuation Tool
```
GET /valuation/company/{ticker}/metrics   → DCF input assumptions
GET /valuation/company/{ticker}           → computed intrinsic value result
```
**Not yet implemented — JSON shape unknown.**

---

### 26. Broker List
```
GET /findata-view/marketdetectors/brokers?page=1&limit=150
```
**Not yet implemented — JSON shape unknown.**  
Up to 150 brokers per page. Broker codes are 2–3 uppercase letters.

---

### 27. Top Broker (Market-Wide)
```
GET /order-trade/broker/top?sort=TB_SORT_BY_TOTAL_VALUE&order=ORDER_BY_DESC&period=TB_PERIOD_LAST_1_DAY&market_type=MARKET_TYPE_ALL&eod_only=true
```
**Params:**
- `sort`: `TB_SORT_BY_TOTAL_VALUE`, `TB_SORT_BY_BUY_VALUE`, `TB_SORT_BY_SELL_VALUE`, `TB_SORT_BY_TOTAL_VOLUME`
- `period`: `TB_PERIOD_LAST_1_DAY`, `TB_PERIOD_LAST_1_WEEK`, `TB_PERIOD_LAST_1_MONTH`
- `market_type`: `MARKET_TYPE_ALL`, `MARKET_TYPE_REGULER`

**Not yet implemented — JSON shape unknown.**

---

### 28. Broker Activity (Universe Scan — Broker-Centric)
```
GET /order-trade/broker/activity?broker_code={code}&transaction_type=TRANSACTION_TYPE_NET&investor_type=INVESTOR_TYPE_ALL&limit=20&market_board=MARKET_TYPE_REGULER&page=1&period=RT_PERIOD_LAST_1_DAY&net_val_period=NET_VAL_PERIOD_7D
```
**Params:**
- `broker_code`: multiple values supported — e.g. `broker_code=AK&broker_code=ZP&broker_code=YP`
- `period`: `RT_PERIOD_LAST_1_DAY`, `RT_PERIOD_LAST_3_DAYS`, `RT_PERIOD_LAST_7_DAYS`, `RT_PERIOD_LAST_1_MONTH`, `RT_PERIOD_LAST_3_MONTHS`, `RT_PERIOD_YEAR_TO_DATE`, `RT_PERIOD_LAST_1_YEAR`
- `net_val_period`: `NET_VAL_PERIOD_7D`, `NET_VAL_PERIOD_30D`
- Alternative to `period`: use `from=YYYY-MM-DD&to=YYYY-MM-DD` for exact date range

**Response shape [prior-doc, source unknown — likely live-probed 2026-06-13]:**
```
data.broker_activity_transaction.brokers_buy[]  → net buying stocks:
  [].stock_code                              → ticker (string)
  [].value                                   → net buy value (IDR, positive, Decimal)
  [].lot                                     → net buy lots (positive, int)
  [].avg_price                               → average buy price (IDR, Decimal)
  [].type                                    → investor type string
  [].date                                    → ISO date string

data.broker_activity_transaction.brokers_sell[] → net selling stocks:
  [].stock_code                              → ticker (string)
  [].value                                   → net sell value (IDR, negative)
  [].lot                                     → net sell lots (negative)
  [].avg_price                               → average sell price
```
**Use case:** "What stocks are foreign/institutional brokers collectively accumulating?"  
**Implementation:** `src/infrastructure/browser/playwright_stockbit.py` (`_parse_foreign_top_stocks`)

---

## Summary: Use Case → Endpoint Mapping

| Use Case | Endpoint | Status |
|----------|----------|--------|
| Pre-open screener (IEV ranking) | `/order-trade/market-mover` | ✓ Implemented |
| Live order book depth + IEP | `/company-price-feed/v2/orderbook/companies/{ticker}` | ✓ Implemented |
| Which brokers bought/sold a stock | `/marketdetectors/{ticker}` | ✓ Implemented |
| Bandar detector (operator concentration) | `/marketdetectors/{ticker}` (different response path) | ✓ Implemented |
| Which stocks foreign brokers are buying | `/order-trade/broker/activity` (multi broker_code) | ✓ Implemented |
| Daily broker flow time-series for a stock | `/order-trade/broker/activity/historical` | ✓ Implemented |
| Live trade tape (tick data) | `/order-trade/running-trade` | ✓ Implemented |
| Stock notation/status/UMA flags | `/emitten/{ticker}/info` | ✓ Implemented |
| Shareholding composition | `/insider/shareholding/composition/companies/{ticker}` | ✓ Implemented |
| Corporate actions (per ticker) | `/corpaction/{ticker}` | ✓ Implemented |
| Insider buying activity (per ticker) | `/insider/company/majorholder` | ✓ Implemented |
| Analyst ratings + target price | `/analyst-ratings/{ticker}` | ✓ Implemented |
| Key ratios (P/E, ROE, etc.) | `/keystats/ratio/v1/{ticker}` | ✓ Implemented |
| Seasonal return pattern | `/company-price-feed/seasonality/{ticker}` | ✓ Implemented |
| Current market session status | `/company-price-feed/market-time` | ✓ Implemented (partial) |
| Stock universe (LQ45, IDX30, etc.) | `/emitten/v3/sector/88/subsector/{id}/company` | ✓ Implemented |
| Historical OHLCV | `/company-price-feed/historical/summary/{ticker}` | ✗ Not implemented |
| Intraday volume profile chart | `/order-trade/running-trade/chart/{ticker}` | ✗ Not implemented |
| Broker distribution (pie chart data) | `/order-trade/broker/distribution` | ✗ Not implemented |
| Analyst consensus (separate endpoint) | `/analyst-ratings/{ticker}/consensus` | ✗ Not implemented |
| Company profile (management, description) | `/emitten/{ticker}/profile` | ✗ Not implemented |
| Financial statements (IS/BS/CF) | `/findata-view/company/financial` | ✗ Not implemented |
| Earnings surprise screening | `/earnings` | ✗ Not implemented |
| Intrinsic value estimate | `/valuation/company/{ticker}` | ✗ Not implemented |
| Market-wide broker ranking | `/order-trade/broker/top` | ✗ Not implemented |
| Full broker list (codes + names) | `/findata-view/marketdetectors/brokers` | ✗ Not implemented |
| Corporate action calendar (market-wide, 9 v1 types) | `/corpaction/dividend` etc. | ✓ Implemented |
| Insider buying scan (all tickers) | `/insider/company/majorholder` (no symbols param) | ✗ Not implemented |
