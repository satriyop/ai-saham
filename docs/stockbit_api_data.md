# Stockbit Exodus API — Data Reference

Base URL: `https://exodus.stockbit.com`  
Auth: Bearer RS256 token (intercepted from browser session, not extractable from localStorage).  
Run `saham stockbit login` then `saham stockbit spy` to capture live responses.

---

## Authentication Notes

- All endpoints require `Authorization: Bearer <token>` header
- Token is RS256 JWT issued by Stockbit identity server — NOT the HS256 token stored in localStorage
- Reliable extraction: intercept from outgoing requests after navigating to `https://stockbit.com/orderbook`
- Token TTL: ~8–12 hours. In-process cache safe for ~30 minutes between batch calls
- 401 response → session expired → run `saham stockbit login`

---

## Per-Ticker Endpoints

### 1. Company Info
```
GET /emitten/{ticker}/info
```
**Data available:**
- Company name, short name, ticker/code
- ISIN, listing date, board type (Main/Development/Acceleration)
- Industry, sub-industry classification
- Market capitalization, shares outstanding, free float
- Company status (active, delisted, suspended)
- Registered address, website, phone, email
- NPWPnumber, NPWP date

---

### 2. Company Profile
```
GET /emitten/{ticker}/profile
```
**Data available:**
- Long-form company description / business overview
- Management board (directors, commissioners) with names and positions
- Company subsidiaries list
- Business activities (main and secondary)
- Employee count
- Key milestones / company history snippet

---

### 3. Shareholding Composition
```
GET /insider/shareholding/composition/companies/{ticker}
```
**Data available:**
- Ownership breakdown by investor type (public, institutional, government, foreign)
- Percentage held by each category
- Top shareholders: name, share count, ownership percentage
- Source type (KSEIDirect / IDX reporting)
- Report date

---

### 4. Corporate Action (Per Ticker)
```
GET /corpaction/{ticker}?limit=30
```
**Data available:**
- Action type: dividend, stock split, rights issue, warrant, bonus share, tender offer, RUPS, IPO
- Announcement date, cum date, ex date, recording date, payment/distribution date
- Cash dividend: amount per share (IDR), yield percentage
- Stock split ratio (e.g., 1:5)
- Rights issue: subscription price, ratio, proceeds
- Action status (announced, completed)

---

### 5. Major Holder / Insider Activity (Per Ticker)
```
GET /insider/company/majorholder?symbols={ticker}&date_start=...&date_end=...&page=1&limit=20&action_type=ACTION_TYPE_UNSPECIFIED&source_type=SOURCE_TYPE_UNSPECIFIED
```
**Params:**
- `period_type`: `PERIOD_TYPE_1_YEAR`, `PERIOD_TYPE_6_MONTH`, etc.
- `action_type`: `ACTION_TYPE_BUY`, `ACTION_TYPE_SELL`, `ACTION_TYPE_UNSPECIFIED`
- `source_type`: IDX filing source filter

**Data available:**
- Insider name and role (director, commissioner, >5% holder)
- Transaction type: buy / sell
- Transaction date
- Number of shares transacted
- Price per share (if disclosed)
- Percentage ownership before and after transaction
- Filing source (IDX / KSEI)

---

### 6. Order Book
```
GET /company-price-feed/v2/orderbook/companies/{ticker}
```
**Confirmed response shape (2026-06-13):**
```
data.iepiev.best_bid_offer.bid.price.raw      → best bid price (int, IDR)
data.iepiev.best_bid_offer.bid.quantity.raw   → best bid quantity (lots)
data.iepiev.best_bid_offer.offer.price.raw    → best offer price (int, IDR)
data.iepiev.best_bid_offer.offer.quantity.raw → best offer quantity (lots)
data.bid[]                                    → full bid depth list
  .price  (string, IDR)
  .volume (int, shares — divide by 100 for lots)
data.offer[]                                  → full offer depth list
  .price  (string, IDR)
  .volume (int, shares)
```
**Data available:**
- Best bid price and quantity (top of book, pre-open IEP)
- Best offer price and quantity
- Full bid depth (5–10 price levels)
- Full offer depth (5–10 price levels)
- IEP (Indicative Equilibrium Price) — expected call-auction clearing price
- IEV (Indicative Equivalent Volume) — via iepiev_detail (see market-mover endpoint)

---

### 7. Historical Price Summary (OHLCV)
```
GET /company-price-feed/historical/summary/{ticker}?period=HS_PERIOD_DAILY&start_date=...&end_date=...&limit=12&page=1
```
**Params:**
- `period`: `HS_PERIOD_DAILY`, `HS_PERIOD_WEEKLY`, `HS_PERIOD_MONTHLY`

**Data available:**
- Date
- Open, High, Low, Close prices (IDR)
- Volume (shares or lots)
- Value (IDR, total traded value)
- Frequency (number of trades)
- Adjusted close (for splits/dividends)
- Foreign net buy/sell volume (sometimes included)

---

### 8. Running Trade (Live Tape)
```
GET /order-trade/running-trade?symbols[]={ticker}&sort=DESC&limit=80&order_by=RUNNING_TRADE_ORDER_BY_TIME
```
**Data available:**
- Individual trade ticks: price, lot size, time
- Buyer broker code, seller broker code
- Trade type (regular/negotiated/cash)
- Investor type (foreign/domestic)
- Sequence number / trade ID

---

### 9. Running Trade Chart (Intraday Volume Profile)
```
GET /order-trade/running-trade/chart/{ticker}?period=RT_PERIOD_LAST_1_DAY&investor_type=INVESTOR_TYPE_ALL&market_board=BOARD_TYPE_REGULAR
```
**Params:**
- `investor_type`: `INVESTOR_TYPE_ALL`, `INVESTOR_TYPE_FOREIGN`, `INVESTOR_TYPE_LOCAL`
- `market_board`: `BOARD_TYPE_REGULAR`, `BOARD_TYPE_NEGOTIATED`

**Data available:**
- Time-bucketed intraday chart (OHLCV per interval)
- Buy volume vs. sell volume per bucket
- Foreign buy vs. domestic buy split per bucket
- Price trend chart data points (for candlestick or line chart)
- Cumulative net value over the day

---

### 10. Market Detector (Named Broker Breakdown Per Ticker)
```
GET /marketdetectors/{ticker}?transaction_type=TRANSACTION_TYPE_NET&market_board=MARKET_BOARD_REGULER&investor_type=INVESTOR_TYPE_ALL&limit=25&period=BROKER_SUMMARY_PERIOD_LATEST
```
**Params:**
- `period`: `BROKER_SUMMARY_PERIOD_LATEST`, `BROKER_SUMMARY_PERIOD_LAST_7_DAYS`, `BROKER_SUMMARY_PERIOD_LAST_1_MONTH`, `BROKER_SUMMARY_PERIOD_LAST_3_MONTHS`, `BROKER_SUMMARY_PERIOD_LAST_6_MONTHS`, `BROKER_SUMMARY_PERIOD_LAST_1_YEAR`
- `transaction_type`: `TRANSACTION_TYPE_NET`, `TRANSACTION_TYPE_BUY`, `TRANSACTION_TYPE_SELL`

**Confirmed response shape (2026-06-13):**
```
data.broker_summary.brokers_buy[]
  netbs_broker_code   → broker code (e.g. "AK")
  blot                → buy lots (int)
  bval                → buy value (IDR)
  netbs_buy_avg_price → average buy price (IDR)
  type                → "Asing" (foreign) or "Lokal" (domestic)
  netbs_date          → trading date (YYYYMMDD)

data.broker_summary.brokers_sell[]
  netbs_broker_code   → broker code
  slot                → sell lots (int, negative)
  sval                → sell value (IDR, negative)
  netbs_sell_avg_price→ average sell price
  type                → "Asing" / "Lokal"
```
**Data available:**
- Top 25 net buyer brokers for the stock: code, lots, value, avg price, type
- Top 25 net seller brokers: code, lots, value, avg price, type
- Broker type classification (foreign / domestic)
- Period-aggregated (not per-day) — use historical endpoint for daily series

---

### 11. Broker Distribution
```
GET /order-trade/broker/distribution?date=&symbol={ticker}&investor_type=INVESTOR_TYPE_ALL&market_board=MARKET_TYPE_REGULER&data_type=BROKER_DISTRIBUTION_DATA_TYPE_VALUE&period=TB_PERIOD_LAST_1_DAY
```
**Params:**
- `data_type`: `BROKER_DISTRIBUTION_DATA_TYPE_VALUE`, `BROKER_DISTRIBUTION_DATA_TYPE_VOLUME`
- `period`: `TB_PERIOD_LAST_1_DAY`, `TB_PERIOD_LAST_1_WEEK`, `TB_PERIOD_LAST_1_MONTH`

**Data available:**
- Broker-level distribution chart data for one stock
- Each broker's share of total value or volume (pie/bar chart source)
- Investor type breakdown (foreign vs. domestic per broker)
- Concentration metric: top-5 broker dominance

---

### 12. Broker Activity Historical (Per Ticker, Per Broker, Daily Series)
```
GET /order-trade/broker/activity/historical?interval=INTERVAL_DAILY&broker_codes={code}&symbols={ticker}&market_board=BOARD_TYPE_REGULAR&investor_type=INVESTOR_TYPE_ALL&pagination.page=1&pagination.limit=100
```
**Confirmed response shape (2026-06-13):**
```
data.broker_name                    → full broker name
data.records[].date                 → "YYYY-MM-DD"
data.records[].trade_activity
  .buy_summary.lot                  → buy lots
  .buy_summary.value                → buy value (IDR)
  .buy_summary.avg_price            → avg buy price
  .sell_summary.lot                 → sell lots
  .sell_summary.value               → sell value (IDR)
  .sell_summary.avg_price           → avg sell price
  .net_summary.lot                  → net lots (positive=net buy, negative=net sell)
  .net_summary.value                → net value (IDR)
  .net_summary.avg_price            → avg net price
  .total_buy_lot.pct                → this broker's share of total market buy (%)
  .total_sell_lot.pct               → this broker's share of total market sell (%)
data.records[].price_activity
  .close_price                      → stock close price that day (fallback)
data.pagination.has_next            → boolean, for pagination
```
**Data available:**
- Daily buy/sell/net lots and values per broker per stock — full time series
- Average buy and sell price per day
- Broker market share percentage (buy and sell)
- Pagination support (100 records/page, up to 365 days back)
- Multiple broker codes supported (separate API calls per code)

---

### 13. Seasonality
```
GET /company-price-feed/seasonality/{ticker}?year=2026&back_year=5
```
**Data available:**
- Monthly average return over the past N years
- Best and worst performing months historically
- Monthly win-rate (% of years with positive return in that month)
- Average return per month: Jan–Dec
- Year-by-year monthly breakdown

---

### 14. Analyst Consensus
```
GET /analyst-ratings/{ticker}/consensus
```
**Data available:**
- Consensus rating: Strong Buy / Buy / Hold / Sell / Strong Sell
- Number of analysts (total, buy, hold, sell count)
- Consensus target price (average, median, high, low)
- Implied upside/downside from current price (%)
- Rating distribution breakdown
- Last updated date

---

### 15. Analyst Ratings (Individual)
```
GET /analyst-ratings/{ticker}
```
**Data available:**
- Per-analyst ratings list
- Analyst name, firm/institution
- Rating (Buy/Hold/Sell)
- Target price (IDR)
- Rating date
- Research note title/link (if available)
- Previous rating and price target for comparison

---

### 16. Company Financial Statements
```
GET /findata-view/company/financial?symbol={ticker}&data_type=1&report_type=1&statement_type=1
```
**Params:**
- `data_type`: 1=Annual, 2=Quarterly, 3=TTM
- `report_type`: 1=IDR, 2=USD
- `statement_type`: 1=Income Statement, 2=Balance Sheet, 3=Cash Flow

**Data available:**
- Income Statement: Revenue, COGS, Gross Profit, EBITDA, EBIT, Net Income, EPS
- Balance Sheet: Total Assets, Total Liabilities, Total Equity, Cash, Debt
- Cash Flow: Operating CF, Investing CF, Financing CF, Free Cash Flow
- Multi-period data (annual: 5–10 years; quarterly: 12–20 quarters)
- Growth rates YoY / QoQ (sometimes computed server-side)

---

### 17. Key Statistics / Financial Ratios
```
GET /keystats/ratio/v1/{ticker}?year_limit=10
```
**Data available:**
- Valuation ratios: P/E, P/B, P/S, EV/EBITDA, EV/Revenue
- Profitability: ROE, ROA, ROIC, Net Margin, Operating Margin, Gross Margin
- Leverage: Debt/Equity, Debt/EBITDA, Current Ratio, Quick Ratio
- Growth: Revenue Growth YoY, Net Income Growth, EPS Growth
- Dividend: DPS, Dividend Yield, Payout Ratio
- Per-share: BVS (Book Value per Share), EPS, DPS
- Historical ratio series (up to 10 years)

---

### 18. Earnings (EPS Recap — Per Ticker)
```
GET /earnings?search={ticker}&quarter=4&year=2025&sort_column=4&order=desc&page=1
```
**Data available:**
- Quarterly EPS: actual vs. estimate (if consensus available)
- EPS surprise (actual minus estimate, %)
- Revenue: actual vs. estimate
- Earnings announcement date
- Fiscal quarter/year
- YoY EPS growth
- Earnings beat/miss/meet classification

---

## General / Market-Wide Endpoints

### 19. Market Time
```
GET /company-price-feed/market-time
```
**Data available:**
- Current market session: Pre-Open, Opening Call Auction, Regular, Pre-Closing, Closing, Post-Market
- Session open and close times (WIB)
- Market open/closed status (boolean)
- Next session timing

---

### 20. Sector and Sub-Sector Lists
```
GET /emitten/sectors
GET /emitten/sectors/{sector_id}/subsectors
GET /emitten/v3/sector/{sector_id}/subsector/{subsector_id}/company
```
**Data available (sectors):**
- Sector ID, sector name
- Number of listed companies in sector
- Sector index code and current index value

**Data available (subsectors):**
- Subsector ID, subsector name, parent sector
- Company count in subsector

**Data available (company list per subsector):**
- Ticker, company name, board type
- Current price, change, % change
- Market cap rank within subsector

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

---

### 21. Corporate Action Calendar (Market-Wide)
```
GET /corpaction/dividend
GET /corpaction/stocksplit
GET /corpaction/rightissue
GET /corpaction/warrant
GET /corpaction/bonus
GET /corpaction/tenderoffer
GET /corpaction/rups
GET /corpaction/pubex
GET /corpaction/ipo
```
**Data available (all types):**
- Ticker, company name
- Action type
- Announcement date, cum date, ex date, recording date, payment date
- Amount (IDR for dividend, ratio for split/rights)
- Action status

---

### 22. IEV Market Movers (Pre-Open Screener)
```
GET /order-trade/market-mover?mover_type=MOVER_TYPE_IEV_TOP_GAINER&filter_stocks=FILTER_STOCKS_TYPE_MAIN_BOARD&filter_stocks=FILTER_STOCKS_TYPE_DEVELOPMENT_BOARD...
```
**Params:**
- `mover_type`: `MOVER_TYPE_IEV_TOP_GAINER`, `MOVER_TYPE_TOP_GAINER`, `MOVER_TYPE_TOP_LOSER`, `MOVER_TYPE_MOST_ACTIVE_VOLUME`, `MOVER_TYPE_MOST_ACTIVE_VALUE`
- `filter_stocks`: `FILTER_STOCKS_TYPE_MAIN_BOARD`, `FILTER_STOCKS_TYPE_DEVELOPMENT_BOARD`, `FILTER_STOCKS_TYPE_ACCELERATION_BOARD`, `FILTER_STOCKS_TYPE_NEW_ECONOMY_BOARD`, `FILTER_STOCKS_TYPE_SPECIAL_MONITORING_BOARD`

**Confirmed response shape (2026-06-13):**
```
data.mover_list[].stock_detail.code         → ticker symbol
data.mover_list[].iepiev_detail.iev.raw     → IEV (Indicative Equivalent Volume, lots)
data.mover_list[].iepiev_detail.iep.raw     → IEP (Indicative Equilibrium Price, IDR)
```
**Data available:**
- Ranked list of stocks by IEV (pre-open order imbalance signal)
- IEV: total lots queued at the indicated opening price (higher = more interest)
- IEP: expected call-auction clearing price at 09:00 WIB
- Board type classification per ticker
- Supports separate calls for main boards and special monitoring board

---

### 23. Insider Activity (All Tickers, Market-Wide)
```
GET /insider/company/majorholder?date_start=...&date_end=...&page=1&limit=20&action_type=ACTION_TYPE_UNSPECIFIED&source_type=SOURCE_TYPE_UNSPECIFIED
```
**Data available:**
- All insider transactions across all tickers in date range
- Insider name, company, role
- Transaction type (buy/sell), shares, price, date
- Sorted by date descending — useful for scanning recent insider buying

---

### 24. Earnings Recap (All Tickers)
```
GET /earnings?sort_column=4&order=desc&page=1
GET /earnings?quarter=4&year=2025&sort_column=4&order=desc&page=1
```
**Data available:**
- Market-wide EPS results sorted by column (e.g., surprise magnitude)
- Ticker, company name, quarter, year
- EPS actual, estimate, surprise
- Revenue actual, estimate
- Earnings release date
- YoY growth

---

### 25. Valuation Tool
```
GET /valuation/company/{ticker}/metrics   → inputs
GET /valuation/company/{ticker}           → computed result
```
**Data available (metrics):**
- DCF inputs: risk-free rate, market risk premium, beta, WACC
- Growth assumptions: short-term, long-term revenue growth
- Margin assumptions

**Data available (result):**
- Intrinsic value estimate (IDR per share)
- Bull / base / bear scenario values
- Implied P/E, EV/EBITDA at each scenario
- Margin of safety vs. current price

---

### 26. Broker List
```
GET /findata-view/marketdetectors/brokers?page=1&limit=150
```
**Data available:**
- Full list of active IDX brokers
- Broker code (2-3 letter), broker name
- Investor type classification (domestic, foreign, state-owned)
- License status
- Up to 150 brokers per page

---

### 27. Top Broker (Market-Wide)
```
GET /order-trade/broker/top?sort=TB_SORT_BY_TOTAL_VALUE&order=ORDER_BY_DESC&period=TB_PERIOD_LAST_1_DAY&market_type=MARKET_TYPE_ALL&eod_only=true
```
**Params:**
- `sort`: `TB_SORT_BY_TOTAL_VALUE`, `TB_SORT_BY_BUY_VALUE`, `TB_SORT_BY_SELL_VALUE`, `TB_SORT_BY_TOTAL_VOLUME`
- `period`: `TB_PERIOD_LAST_1_DAY`, `TB_PERIOD_LAST_1_WEEK`, `TB_PERIOD_LAST_1_MONTH`
- `market_type`: `MARKET_TYPE_ALL`, `MARKET_TYPE_REGULER`

**Data available:**
- Market-wide broker ranking by value/volume
- Broker code, name
- Total buy value, sell value, net value
- Total buy lots, sell lots, net lots
- Market share percentage
- Ranking position

---

### 28. Broker Activity (Universe Scan — Broker-Centric)
```
GET /order-trade/broker/activity?broker_code={code}&transaction_type=TRANSACTION_TYPE_NET&investor_type=INVESTOR_TYPE_ALL&limit=20&market_board=MARKET_TYPE_REGULER&page=1&period=RT_PERIOD_LAST_1_DAY&net_val_period=NET_VAL_PERIOD_7D
```
**Params:**
- `broker_code`: multiple values supported (e.g., `broker_code=AK&broker_code=ZP`)
- `period`: `RT_PERIOD_LAST_1_DAY`, `RT_PERIOD_LAST_3_DAYS`, `RT_PERIOD_LAST_7_DAYS`, `RT_PERIOD_LAST_1_MONTH`, `RT_PERIOD_LAST_3_MONTHS`, `RT_PERIOD_YEAR_TO_DATE`, `RT_PERIOD_LAST_1_YEAR`
- `net_val_period`: `NET_VAL_PERIOD_7D`, `NET_VAL_PERIOD_30D`
- Can also use `from` and `to` date params instead of `period`

**Confirmed response shape (2026-06-13):**
```
data.broker_activity_transaction.brokers_buy[]
  stock_code   → ticker
  value        → net buy value (IDR, positive)
  lot          → net buy lots (positive)
  avg_price    → average buy price (IDR)
  type         → investor type
  date         → ISO date string

data.broker_activity_transaction.brokers_sell[]
  stock_code   → ticker
  value        → net sell value (IDR, negative)
  lot          → net sell lots (negative)
  avg_price    → average sell price
```
**Data available:**
- Which stocks a set of brokers collectively bought/sold the most (universe scan)
- Net value and lots per stock for the broker group
- Average price of transactions
- Supports aggregating multiple broker codes in one call (foreign flow proxy)
- Most useful for: "what stocks are foreign/institutional brokers accumulating?"

---

## Summary: Use Case → Endpoint Mapping

| Use Case | Endpoint |
|----------|----------|
| Pre-open screener (IEV ranking) | `/order-trade/market-mover` |
| Live order book depth + IEP | `/company-price-feed/v2/orderbook/companies/{ticker}` |
| Which brokers bought/sold a stock | `/marketdetectors/{ticker}` |
| Which stocks foreign brokers are buying | `/order-trade/broker/activity` (multi broker_code) |
| Daily broker flow time-series for a stock | `/order-trade/broker/activity/historical` |
| Live trade tape (tick data) | `/order-trade/running-trade` |
| Historical OHLCV | `/company-price-feed/historical/summary/{ticker}` |
| Fundamental financials | `/findata-view/company/financial` |
| Key ratios (P/E, ROE, etc.) | `/keystats/ratio/v1/{ticker}` |
| Analyst consensus + target price | `/analyst-ratings/{ticker}/consensus` |
| Dividend / split calendar | `/corpaction/{ticker}` or `/corpaction/dividend` |
| Insider buying activity | `/insider/company/majorholder` |
| Shareholder ownership breakdown | `/insider/shareholding/composition/companies/{ticker}` |
| Current market session status | `/company-price-feed/market-time` |
| Stock universe (LQ45, IDX30, etc.) | `/emitten/v3/sector/88/subsector/{id}/company` |
| Sector classification | `/emitten/sectors` → `/emitten/sectors/{id}/subsectors` |
| Market-wide broker ranking | `/order-trade/broker/top` |
| Full broker list (codes + names) | `/findata-view/marketdetectors/brokers` |
| Earnings surprise screening | `/earnings` |
| Seasonal pattern analysis | `/company-price-feed/seasonality/{ticker}` |
| Intrinsic value estimate | `/valuation/company/{ticker}` |
