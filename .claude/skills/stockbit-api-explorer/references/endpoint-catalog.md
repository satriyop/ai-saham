# Stockbit Exodus Endpoint Catalog

Base: `https://exodus.stockbit.com/`

All endpoints require `Authorization: Bearer <token>` header.
Use `_exodus_get(url, token)` — it handles auth and returns parsed JSON.

---

## Per-Ticker Endpoints

### Company Info
```
GET /emitten/{ticker}/info          → company metadata
GET /emitten/{ticker}/profile        → company profile
```

### Price & Order Book
```
GET /company-price-feed/v2/orderbook/companies/{ticker}
    → live order book (bid/ask depth)

GET /company-price-feed/historical/summary/{ticker}
    ?period=HS_PERIOD_DAILY&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&limit=12&page=1
    → historical OHLCV summary
```

### Running Trade
```
GET /order-trade/running-trade
    ?symbols[]={ticker}&sort=DESC&limit=80&order_by=RUNNING_TRADE_ORDER_BY_TIME
    → real-time trade tape

GET /order-trade/running-trade/chart/{ticker}
    ?period=RT_PERIOD_LAST_1_DAY&investor_type=INVESTOR_TYPE_ALL&market_board=BOARD_TYPE_REGULAR
    → trade chart data
```

### Broker / Market Detector
```
GET /marketdetectors/{ticker}
    ?transaction_type=TRANSACTION_TYPE_NET
    &market_board=MARKET_BOARD_REGULER
    &investor_type=INVESTOR_TYPE_ALL
    &limit=25
    &period=BROKER_SUMMARY_PERIOD_LATEST
    → bandar_detector: broker_accdist ("Acc"/"Dis"/"Neutral"), avg/avg5/top1/top3/top5/top10
    [IMPLEMENTED: stockbit_bandar.py]

GET /order-trade/broker/distribution
    ?date=&symbol={ticker}&investor_type=INVESTOR_TYPE_ALL
    &market_board=MARKET_TYPE_REGULER
    &data_type=BROKER_DISTRIBUTION_DATA_TYPE_VALUE
    &period=TB_PERIOD_LAST_1_DAY
    → broker buy/sell distribution
```

### Shareholding & Insider
```
GET /insider/shareholding/composition/companies/{ticker}
    → institution_pct, individual_pct, top_holder_name/pct
    [IMPLEMENTED: stockbit_shareholding.py]

GET /insider/company/majorholder
    ?symbols={ticker}&date_start=YYYY-MM-DD&date_end=YYYY-MM-DD
    &page=1&limit=20
    &action_type=ACTION_TYPE_UNSPECIFIED
    &source_type=SOURCE_TYPE_UNSPECIFIED
    → insider buy/sell transactions
    [IMPLEMENTED: stockbit_insider.py]
```

### Corporate Actions
```
GET /corpaction/{ticker}?limit=30
    → upcoming dividend, split, rights issue events
    [IMPLEMENTED: stockbit_corp_action.py]
```

### Analyst & Predictions
```
GET /analyst-ratings/{ticker}
    → buy/hold/sell counts, price target
    [IMPLEMENTED: stockbit_analyst.py]

GET /analyst-ratings/{ticker}/consensus
    → consensus summary

GET /company-price-feed/seasonality/{ticker}?year=2026&back_year=5
    → monthly seasonality edge (win rate, avg return)
    [IMPLEMENTED: stockbit_seasonality.py]
```

### Fundamentals
```
GET /keystats/ratio/v1/{ticker}?year_limit=10
    → 80+ named ratios as flat list: PE, ROE, NPM, Piotroski F-Score, etc.
    [IMPLEMENTED: stockbit_fundamentals.py]

GET /findata-view/company/financial
    ?symbol={ticker}&data_type=1&report_type=1&statement_type=1
    → full financial statements

GET /earnings?search={ticker}&quarter=4&year=2025&sort_column=4&order=desc&page=1
    → quarterly EPS recap
```

### Valuation
```
GET /valuation/company/{ticker}/metrics   → valuation metrics
GET /valuation/company/{ticker}           → valuation result
```

---

## Market-Wide Endpoints (No Ticker)

### Market Time
```
GET /company-price-feed/market-time   → current market session status
```

### Sectors & Universes
```
GET /emitten/sectors                            → all sectors
GET /emitten/sectors/{sector_id}/subsectors     → subsectors within sector

# Companies in a subsector:
GET /emitten/v3/sector/{sector_id}/subsector/{subsector_id}/company

# Key universe IDs confirmed:
sector_id=88 (IHSG indices):
  subsector 467 → IHSG all
  subsector 550 → LQ45
  subsector 559 → IDX30
  subsector 551 → JII
  subsector 552 → MBX
  subsector 1000000011 → BUMN20

sector_id=3 → Keuangan
sector_id=70 → Indeks Sektoral
sector_id=78 → Global Index
```

### Corp Action Calendar (All Tickers)
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

### Insider Activity (All Tickers, Sorted by Date)
```
GET /insider/company/majorholder
    ?date_start=YYYY-MM-DD&date_end=YYYY-MM-DD&page=1&limit=20
    &action_type=ACTION_TYPE_UNSPECIFIED
    &source_type=SOURCE_TYPE_UNSPECIFIED
```

### Earnings (All Tickers)
```
GET /earnings?sort_column=4&order=desc&page=1
GET /earnings?quarter=4&year=2025&sort_column=4&order=desc&page=1
```

---

## Broker Activity Endpoints

```
# Activity for one broker across all stocks
GET /order-trade/broker/activity
    ?broker_code={code}
    &transaction_type=TRANSACTION_TYPE_NET
    &investor_type=INVESTOR_TYPE_ALL
    &limit=50&page=1
    &market_board=MARKET_TYPE_REGULER
    &period=RT_PERIOD_LAST_1_DAY   # or LAST_7_DAYS, LAST_1_MONTH, LAST_3_MONTHS, YEAR_TO_DATE, LAST_1_YEAR
    → stocks this broker is most active in

# By date range:
    &from=YYYY-MM-DD&to=YYYY-MM-DD   (replaces period param)

# Multiple brokers:
    &broker_code=AK&broker_code=ZP&broker_code=YP   (repeat param)

# Top brokers by value:
GET /order-trade/broker/top
    ?sort=TB_SORT_BY_TOTAL_VALUE&order=ORDER_BY_DESC
    &period=TB_PERIOD_LAST_1_DAY
    &market_type=MARKET_TYPE_ALL&eod_only=true

# Full broker list:
GET /findata-view/marketdetectors/brokers?page=1&limit=150
```

---

## Enum Reference

Common query param values confirmed by probing:

| Parameter | Values |
|-----------|--------|
| `transaction_type` | `TRANSACTION_TYPE_NET`, `TRANSACTION_TYPE_BUY`, `TRANSACTION_TYPE_SELL` |
| `market_board` / `market_type` | `MARKET_BOARD_REGULER`, `MARKET_TYPE_REGULER`, `BOARD_TYPE_REGULAR`, `MARKET_TYPE_ALL` |
| `investor_type` | `INVESTOR_TYPE_ALL`, `INVESTOR_TYPE_DOMESTIC`, `INVESTOR_TYPE_FOREIGN` |
| `period` (broker) | `TB_PERIOD_LAST_1_DAY`, `RT_PERIOD_LAST_1_DAY`, `RT_PERIOD_LAST_7_DAYS`, `RT_PERIOD_LAST_1_MONTH`, `RT_PERIOD_LAST_3_MONTHS`, `YEAR_TO_DATE`, `RT_PERIOD_LAST_1_YEAR`, `BROKER_SUMMARY_PERIOD_LATEST` |
| `action_type` (insider) | `ACTION_TYPE_UNSPECIFIED`, `ACTION_TYPE_BUY`, `ACTION_TYPE_SELL` |
| `HS_PERIOD` | `HS_PERIOD_DAILY`, `HS_PERIOD_WEEKLY`, `HS_PERIOD_MONTHLY` |
