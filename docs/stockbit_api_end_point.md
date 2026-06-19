Stockbit API End Point
======================

data per ticker
---------------
### company data
"Successfully retrieved company data"
https://exodus.stockbit.com/emitten/{ticker/info

### profile
"Successfully retrieved company profile data"
https://exodus.stockbit.com/emitten/{ticker}/profile

### composition
"Successfully fetched composition by company symbol"
https://exodus.stockbit.com/insider/shareholding/composition/companies/{ticker}

### corp action
"Successfully retrieved corporate action data"
https://exodus.stockbit.com/corpaction/{tiker}?limit=30

## major holder
"Successfully majorholder data"
https://exodus.stockbit.com/insider/company/majorholder?symbols=BBCA&date_start=2025-06-16&date_end=2026-06-16&limit=20&action_type=ACTION_TYPE_UNSPECIFIED&source_type=SOURCE_TYPE_UNSPECIFIED&period_type=PERIOD_TYPE_1_YEAR&page=1

### order book
"Successfully get company orderbook"
https://exodus.stockbit.com/company-price-feed/v2/orderbook/companies/{ticker}


### historical summary
"Successfully get the historical summary"
https://exodus.stockbit.com/company-price-feed/historical/summary/{ticker}?period=HS_PERIOD_DAILY&start_date=2025-06-16&end_date=2026-06-16&limit=12&page=1

### running trade
"Successfully loaded running trade data"
https://exodus.stockbit.com/order-trade/running-trade?symbols%5B%5D={ticker}&sort=DESC&limit=80&order_by=RUNNING_TRADE_ORDER_BY_TIME

### running trade chart
"Successfully loaded tradebook data chart"
https://exodus.stockbit.com/order-trade/running-trade/chart/{ticker}?period=RT_PERIOD_LAST_1_DAY&investor_type=INVESTOR_TYPE_ALL&market_board=BOARD_TYPE_REGULAR


### Broker data per ticker
#### market detector
"Successfully retrieved market detector data"
https://exodus.stockbit.com/marketdetectors/{ticker}?transaction_type=TRANSACTION_TYPE_NET&market_board=MARKET_BOARD_REGULER&investor_type=INVESTOR_TYPE_ALL&limit=25&period=BROKER_SUMMARY_PERIOD_LATEST


#### broker distribution
"Successfully loaded Broker Distribution data"
https://exodus.stockbit.com/order-trade/broker/distribution?date=&symbol={ticker}&investor_type=INVESTOR_TYPE_ALL&market_board=MARKET_TYPE_REGULER&data_type=BROKER_DISTRIBUTION_DATA_TYPE_VALUE&period=TB_PERIOD_LAST_1_DAY


#### broker activity historically
"Successfully loaded broker activity historical data"
https://exodus.stockbit.com/order-trade/broker/activity/historical?interval=INTERVAL_DAILY&date_from=2026-05-01&date_to=2026-06-30&broker_codes=XL&symbols={ticker}&market_board=BOARD_TYPE_REGULAR&investor_type=INVESTOR_TYPE_ALL&net_interval=INTERVAL_MONTHLY


### Prediction data
#### seasonality
"Success"
https://exodus.stockbit.com/company-price-feed/seasonality/{ticker}?year=2026&back_year=5

#### analyst consensus
"Successfully retrieved analyst consensus data"
https://exodus.stockbit.com/analyst-ratings/{ticker}/consensus

#### analyst rating
"Successfully retrieved analyst ratings data"
https://exodus.stockbit.com/analyst-ratings/{ticker}


#### insider activity per ticker
https://exodus.stockbit.com/insider/company/majorholder?symbols={ticker}&date_start=2026-05-16&date_end=2026-06-16&page=1&limit=20&action_type=ACTION_TYPE_UNSPECIFIED&source_type=SOURCE_TYPE_UNSPECIFIED

### Fundamental data
#### financial
"Successfully retrieved company financial"
https://exodus.stockbit.com/findata-view/company/financial?symbol={ticker}&data_type=1&report_type=1&statement_type=1

#### keystat
"Successfully retrieved company keystats"
https://exodus.stockbit.com/keystats/ratio/v1/{ticker}?year_limit=10

#### earnings per ticker (Quarterly EPS Recap)
https://exodus.stockbit.com/earnings?search={ticker}&quarter=4&year=2025&sort_column=4&order=desc&page=1


General all ticker data
-----------------------
### market time
"get market time data"
https://exodus.stockbit.com/company-price-feed/market-time

### sector
" retrieved list sector "
https://exodus.stockbit.com/emitten/sectors

- Indeks Sektoral
"retrieved list sub sector name"
https://exodus.stockbit.com/emitten/sectors/70/subsectors

- Keuangan
" retrieved list sub sector name"
https://exodus.stockbit.com/emitten/sectors/3/subsectors

- List of companies on the Keuangan sector
" retrieved list sub sector company"
https://exodus.stockbit.com/emitten/v3/sector/3/subsector/12/company





### global index
https://exodus.stockbit.com/emitten/sectors/78/subsectors
https://exodus.stockbit.com/emitten/v3/sector/78/subsector/79/company

### indonesia ihsg subsector index (from here you get several valuable index/universe)
https://exodus.stockbit.com/emitten/sectors/88/subsectors


- ihsg index
https://exodus.stockbit.com/emitten/v3/sector/88/subsector/467/company

-  lq45
https://exodus.stockbit.com/emitten/v3/sector/88/subsector/550/company

- idx30
https://exodus.stockbit.com/emitten/v3/sector/88/subsector/559/company

- jii
https://exodus.stockbit.com/emitten/v3/sector/88/subsector/551/company
 
- mbx
https://exodus.stockbit.com/emitten/v3/sector/88/subsector/552/company


-bumn20
https://exodus.stockbit.com/emitten/v3/sector/88/subsector/1000000011/company

and many more


### corp action calendar 
https://exodus.stockbit.com/corpaction/dividend
https://exodus.stockbit.com/corpaction/stocksplit
https://exodus.stockbit.com/corpaction/rightissue
https://exodus.stockbit.com/corpaction/warrant
https://exodus.stockbit.com/corpaction/bonus
https://exodus.stockbit.com/corpaction/tenderoffer
https://exodus.stockbit.com/corpaction/rups
https://exodus.stockbit.com/corpaction/pubex
https://exodus.stockbit.com/corpaction/ipo


### insider activity all ticker sorted by date
"Successfully majorholder data"
https://exodus.stockbit.com/insider/company/majorholder?&date_start=2026-05-16&date_end=2026-06-16&page=1&limit=20&action_type=ACTION_TYPE_UNSPECIFIED&source_type=SOURCE_TYPE_UNSPECIFIED


### earnings (Quarterly EPS Recap)
https://exodus.stockbit.com/earnings?sort_column=4&order=desc&page=1
https://exodus.stockbit.com/earnings?quarter=4&year=2025&sort_column=4&order=desc&page=1


### valuation tool
https://exodus.stockbit.com/valuation/company/{ticker}/metrics
https://exodus.stockbit.com/valuation/company/{ticker} (result)


### broker list
"Successfully retrieved broker list"
https://exodus.stockbit.com/findata-view/marketdetectors/brokers?page=1&limit=150

"Successfully get top broker"
https://exodus.stockbit.com/order-trade/broker/top?sort=TB_SORT_BY_TOTAL_VALUE&order=ORDER_BY_DESC&period=TB_PERIOD_LAST_1_DAY&market_type=MARKET_TYPE_ALL&eod_only=true


### top broker
"Successfully get top broker"
https://exodus.stockbit.com/order-trade/broker/top?sort=TB_SORT_BY_TOTAL_VALUE&order=ORDER_BY_DESC&period=TB_PERIOD_LAST_1_DAY&market_type=MARKET_TYPE_ALL&eod_only=true

"1 week"
https://exodus.stockbit.com/order-trade/broker/activity?broker_code=XL&transaction_type=TRANSACTION_TYPE_NET&investor_type=INVESTOR_TYPE_ALL&limit=20&market_board=MARKET_TYPE_REGULER&page=1&period=RT_PERIOD_LAST_1_DAY&net_val_period=NET_VAL_PERIOD_7D

"1 month"
https://exodus.stockbit.com/order-trade/broker/activity?broker_code=XL&transaction_type=TRANSACTION_TYPE_NET&investor_type=INVESTOR_TYPE_ALL&limit=20&market_board=MARKET_TYPE_REGULER&page=1&period=RT_PERIOD_LAST_1_MONTH&net_val_period=NET_VAL_PERIOD_7D

"3 months"
https://exodus.stockbit.com/order-trade/broker/activity?broker_code=XL&transaction_type=TRANSACTION_TYPE_NET&investor_type=INVESTOR_TYPE_ALL&limit=20&market_board=MARKET_TYPE_REGULER&page=1&period=RT_PERIOD_LAST_3_MONTHS&net_val_period=NET_VAL_PERIOD_7D


Activity Data per broker
-------------------------
"Successfully loaded Broker Activity data"
https://exodus.stockbit.com/order-trade/broker/activity?broker_code={broker_code}&transaction_type=TRANSACTION_TYPE_NET&investor_type=INVESTOR_TYPE_ALL&limit=20&market_board=MARKET_TYPE_REGULER&page=1&period=RT_PERIOD_LAST_1_DAY&net_val_period=NET_VAL_PERIOD_7D

"Successfully loaded Broker Activity data" (by period)
https://exodus.stockbit.com/order-trade/broker/activity?broker_code={broker_code}&limit=50&page=1&transaction_type=TRANSACTION_TYPE_NET&market_board=MARKET_TYPE_REGULER&investor_type=INVESTOR_TYPE_ALL&period=RT_PERIOD_LAST_1_DAY

https://exodus.stockbit.com/order-trade/broker/activity?broker_code=XL&limit=50&page=1&transaction_type=TRANSACTION_TYPE_NET&market_board=MARKET_TYPE_REGULER&investor_type=INVESTOR_TYPE_ALL&period=RT_PERIOD_LAST_7_DAYS

https://exodus.stockbit.com/order-trade/broker/activity?broker_code=XL&limit=50&page=1&transaction_type=TRANSACTION_TYPE_NET&market_board=MARKET_TYPE_REGULER&investor_type=INVESTOR_TYPE_ALL&period=RT_PERIOD_LAST_1_MONTH

https://exodus.stockbit.com/order-trade/broker/activity?broker_code=XL&limit=50&page=1&transaction_type=TRANSACTION_TYPE_NET&market_board=MARKET_TYPE_REGULER&investor_type=INVESTOR_TYPE_ALL&period=RT_PERIOD_LAST_3_MONTHS

https://exodus.stockbit.com/order-trade/broker/activity?broker_code=XL&limit=50&page=1&transaction_type=TRANSACTION_TYPE_NET&market_board=MARKET_TYPE_REGULER&investor_type=INVESTOR_TYPE_ALL&period=RT_PERIOD_YEAR_TO_DATE

https://exodus.stockbit.com/order-trade/broker/activity?broker_code=XL&limit=50&page=1&transaction_type=TRANSACTION_TYPE_NET&market_board=MARKET_TYPE_REGULER&investor_type=INVESTOR_TYPE_ALL&period=RT_PERIOD_LAST_1_YEAR

"Successfully loaded Broker Activity data" (by date)

https://exodus.stockbit.com/order-trade/broker/activity?broker_code=XL&limit=50&page=1&transaction_type=TRANSACTION_TYPE_NET&market_board=MARKET_TYPE_REGULER&investor_type=INVESTOR_TYPE_ALL&from=2025-06-01&to=2025-06-07



"Successfully loaded Broker Activity data" (by multiple broker)
https://exodus.stockbit.com/order-trade/broker/activity?broker_code=AK&broker_code=ZP&broker_code=YP&broker_code=BK&broker_code=YU&broker_code=CP&broker_code=DR&broker_code=HD&broker_code=KK&broker_code=KZ&transaction_type=TRANSACTION_TYPE_NET&investor_type=INVESTOR_TYPE_ALL&limit=20&market_board=MARKET_TYPE_REGULER&page=1&period=RT_PERIOD_LAST_1_DAY&net_val_period=NET_VAL_PERIOD_7D

"Successfully loaded Broker Activity data" (by multiple broker , by date)

https://exodus.stockbit.com/order-trade/broker/activity?broker_code=XL&broker_code=AK&limit=50&page=1&transaction_type=TRANSACTION_TYPE_NET&market_board=MARKET_TYPE_REGULER&investor_type=INVESTOR_TYPE_ALL&from=2025-06-01&to=2025-06-07











