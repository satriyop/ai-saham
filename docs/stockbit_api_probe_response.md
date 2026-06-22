# Stockbit Exodus API — Live Probe Responses

This document contains **actual raw JSON responses** captured from live Stockbit API calls.  
It is a companion to `stockbit_api_data.md` which provides field-level annotations.

**Purpose:** Zero ambiguity on real field names, types, nesting, and enum values.  
When implementing a new parser, always check this file first.

**Sources:**
- `journals/stockbit-notation-probe.json` — probed 2026-06-19 via `_exodus_get` directly
- `journals/broker-daily-XL-BBCA.json` — captured 2026-06-12 (XL broker, BBCA ticker)
- `journals/broker-scan-spy.json` — captured 2026-06-12 via browser network spy
- `journals/stockbit-spy.json` — captured 2026-06-15 via browser network spy

**How to add new probes:**
```bash
saham fetch stockbit login          # ensure session active
saham fetch stockbit spy            # captures all network traffic to journals/stockbit-spy.json
# Then navigate Stockbit pages to trigger the endpoints you want to capture
```

**Notation:** Responses are trimmed to representative samples. `[... N more items ...]` marks truncation.

---

## PROBED RESPONSES

---

### `/emitten/{ticker}/info`
**Probe date:** 2026-06-19 | **Source:** `journals/stockbit-notation-probe.json`  
**Note:** This endpoint returns `data` directly (not wrapped in a list). Below is the raw
`data` object. The outer envelope is `{"message": "...", "data": {...}}`.

#### BBCA (healthy blue-chip, no notations)
```json
{
  "aum": "",
  "average": "267874966.00",
  "change": "+125.00",
  "country": "ID",
  "created": "0001-01-01T00:00:00Z",
  "date": "19 Jun 2026",
  "exchange": "IDX",
  "followed": 1,
  "followers": 3177021,
  "formatted_price": "6,200",
  "id": "54",
  "indexes": ["TRADINGLIMIT", "IDXVESTA28", "ECONOMIC30", "DAYTRADE", "PRIMBANK10",
               "IDXLQ45LCL", "I-GRADE", "ESGQKEHATI", "ESGSKEHATI", "IDXFINANCE",
               "IDX80", "IDXESGL", "IDXQ30", "IDXG30", "IDXHIDIV20", "MNC36",
               "Investor33", "INFOBANK15", "IDX30", "SRI-KEHATI", "KOMPAS100",
               "BISNIS-27", "MBX", "LQ45", "IHSG"],
  "indexes_data": [
    {"company_symbol": "TRADINGLIMIT", "company_type": "indeks"},
    {"company_symbol": "IDXFINANCE",   "company_type": "indeks-sektoral"}
  ],
  "is_holding_exist": true,
  "is_price_alert_exist": true,
  "market_hour": {
    "status": "open",
    "time_left": 0,
    "formatted_time_left": "0 jam 0 menit 0 detik",
    "suspend_info": ""
  },
  "name": "Bank Central Asia Tbk.",
  "notation": [],
  "orderbook": {
    "bid":   {"price": "6175.000000", "volume": "4553000.000000"},
    "offer": {"price": "6200.000000", "volume": "5364600.000000"}
  },
  "percentage": 2.06,
  "previous": "6075",
  "price": "6200",
  "prices": [],
  "sector": "Keuangan",
  "sentiment": {"end_value": 0, "period": "", "start_value": 0, "value": 0},
  "status": "STATUS_ACTIVE",
  "sub_sector": "Bank",
  "symbol": "BBCA",
  "symbol_2": "BBCA",
  "symbol_3": "BBCA",
  "tabs": ["stream","news","keystats","orderbook","analyst","analysis","financials",
           "fundachart","seasonality","chartbit","comparison","corp.action","insider",
           "profile","EPS Estimate"],
  "time": "Fri 14:07",
  "trade_type": "",
  "tradeable": 1,
  "type_company": "Saham",
  "updated": "2026-06-19T08:00:03+07:00",
  "value": "NA",
  "volume": "98394300",
  "uma": false,
  "day_trade_multiplier": "5",
  "day_trade_info": {"is_show_multiplier": true, "multiplier": "5"},
  "trading_limit_info": {"is_trading_limit": true, "haircut_percentage": "10%"},
  "margin_info": {"is_margin_trading": false, "percentage": "0%", "percentage_raw": 0},
  "corp_action": {
    "active": true,
    "icon": "https://assets.stockbit.com/images/corp_action_event_icon.svg",
    "text": "Perusahaan Memiliki Corporate Action",
    "detail": null
  },
  "icon_url": "https://assets.stockbit.com/logos/companies/BBCA.png",
  "catalogs": [
    {"company_symbol": "Bank",         "catalog_name": "Bank",         "id": "20",   "parent": "3",  "company_type": "sub_sector",    "show": true},
    {"company_symbol": "DAYTRADE",     "catalog_name": "Day Trade",    "id": "1000004658", "parent": "88", "company_type": "indeks", "show": true},
    {"company_symbol": "Papan Utama",  "catalog_name": "Papan Utama",  "id": "5",    "parent": "89", "company_type": "listing-board", "show": true},
    {"company_symbol": "TRADINGLIMIT", "catalog_name": "TRADINGLIMIT", "id": "1000005139", "parent": "88", "company_type": "indeks", "show": true},
    {"company_symbol": "IDXVESTA28",   "catalog_name": "IDXVESTA28",   "id": "1000004998", "parent": "88", "company_type": "indeks", "show": true},
    {"company_symbol": "ECONOMIC30",   "catalog_name": "ECONOMIC30",   "id": "1000004908", "parent": "88", "company_type": "indeks", "show": true},
    {"company_symbol": "IDXFINANCE",   "catalog_name": "IDXFINANCE",   "id": "1000003295", "parent": "70", "company_type": "indeks-sektoral", "show": false},
    {"company_symbol": "IDX30",        "catalog_name": "IDX30",        "id": "559",  "parent": "88", "company_type": "indeks",       "show": false},
    {"company_symbol": "LQ45",         "catalog_name": "LQ45",         "id": "550",  "parent": "88", "company_type": "indeks",       "show": false},
    {"company_symbol": "IHSG",         "catalog_name": "IHSG",         "id": "467",  "parent": "88", "company_type": "indeks",       "show": false}
  ]
}
```

#### GOTO (with notation "N" — multiple voting rights)
```json
{
  "name": "GoTo Gojek Tokopedia Tbk.",
  "sector": "Teknologi",
  "sub_sector": "Perangkat Lunak & Jasa TI",
  "status": "STATUS_ACTIVE",
  "tradeable": 1,
  "uma": false,
  "notation": [
    {
      "notation_code": "N",
      "notation_desc": "Perusahaan Tercatat merupakan Emiten yang menerapkan Saham Dengan Hak Suara Multipel",
      "icon_url": {
        "light_mode": "https://assets.stockbit.com/logos/notations/light/N.png",
        "dark_mode":  "https://assets.stockbit.com/logos/notations/dark/N.png"
      }
    }
  ],
  "trading_limit_info": {"is_trading_limit": true, "haircut_percentage": "100%"},
  "catalogs": [
    {"company_symbol": "Perangkat Lunak & Jasa TI", "catalog_name": "Teknologi",          "company_type": "sub_sector",    "show": true},
    {"company_symbol": "Papan Pengembangan",         "catalog_name": "Papan Pengembangan", "company_type": "listing-board", "show": true},
    {"company_symbol": "TRADINGLIMIT",               "catalog_name": "TRADINGLIMIT",       "company_type": "indeks",        "show": true},
    {"company_symbol": "NOTASI-KHUSUS",              "catalog_name": "NOTASI-KHUSUS",      "company_type": "indeks",        "show": true}
  ]
}
```

**Key fields not parsed by current implementation (potential additions):**
- `data.name` → full company name
- `data.followers` → Stockbit follower count (int)
- `data.indexes[]` → flat list of index codes the stock belongs to
- `data.indexes_data[]` → `{company_symbol, company_type}` — same as indexes but typed
- `data.orderbook.bid/offer.{price, volume}` → lightweight top-of-book snapshot (string, shares)
- `data.sentiment.{value, start_value, end_value, period}` → Stockbit sentiment score
- `data.day_trade_multiplier` → string ("5", "4", "0")
- `data.day_trade_info.{is_show_multiplier, multiplier}`
- `data.margin_info.{is_margin_trading, percentage, percentage_raw}`
- `data.tabs[]` → list of available tab IDs for this stock (determines feature availability)
- `data.price` / `data.previous` / `data.change` / `data.percentage` / `data.volume` / `data.average` → live quote data (all strings)
- `data.formatted_price` → price with thousand-separator commas
- `data.type_company` → "Saham" (stock type label)
- `data.corp_action.icon` → SVG URL for the corp action icon
- `data.notation[].icon_url.{light_mode, dark_mode}` → notation icon URLs

---

### `/order-trade/market-mover`
**Probe date:** 2026-06-19 | **Source:** `journals/stockbit-notation-probe.json`

#### Main board — single mover item (full shape)
```json
{
  "change": "...",
  "frequency": "...",
  "net_buy": "...",
  "net_foreign_buy": "...",
  "net_foreign_sell": "...",
  "net_sell": "...",
  "price": "...",
  "value": "...",
  "volume": "...",
  "iepiev_detail": {
    "iev": {"raw": 1681192},
    "iep": {"raw": 172}
  },
  "stock_detail": {
    "code": "BUMI",
    "name": "Bumi Resources Tbk",
    "icon_url": "https://assets.stockbit.com/logos/companies/BUMI.png?version=...",
    "has_uma": false,
    "notations": [],
    "corpaction": {
      "active": true,
      "icon_url": "https://assets.stockbit.com/images/corp_action_event_icon.svg",
      "text": "Perusahaan Memiliki Corporate Action"
    }
  }
}
```

#### Special monitoring board — mover with multiple notations
```json
{
  "stock_detail": {
    "code": "MTFN",
    "name": "Capitalinc Investment Tbk.",
    "has_uma": false,
    "notations": [
      {"code": "E", "description": "Laporan keuangan terakhir menunjukkan ekuitas negatif"},
      {"code": "L", "description": "Perusahaan Tercatat belum menyampaikan laporan keuangan"},
      {"code": "X", "description": "Efek Bersifat Ekuitas Dalam Pemantauan Khusus"}
    ],
    "corpaction": {"active": false, "icon_url": "...", "text": "..."}
  }
}
```

**Key fields not currently parsed from market-mover:**
- `mover_list[].change` → price change string
- `mover_list[].frequency` → trade frequency string
- `mover_list[].net_buy` / `net_sell` → net buy/sell value strings
- `mover_list[].net_foreign_buy` / `net_foreign_sell` → foreign flow strings
- `mover_list[].price` → current price string
- `mover_list[].value` → total traded value string
- `mover_list[].volume` → total traded volume string
- `mover_list[].stock_detail.name` → company full name
- `mover_list[].stock_detail.notations[].{code, description}` — note: uses `code`/`description` NOT `notation_code`/`notation_desc` (different from `/emitten/{ticker}/info`)
- `mover_list[].stock_detail.corpaction.{active, icon_url, text}` — note: `icon_url` (not `icon`) here

**⚠️ Inconsistency:** `/emitten/{ticker}/info` uses `notation_code` / `notation_desc` in the notation objects, but `/order-trade/market-mover` uses `code` / `description`. Parser must handle both.

---

### `/order-trade/broker/activity/historical`
**Probe date:** 2026-06-12 | **Source:** `journals/broker-daily-XL-BBCA.json`

```json
{
  "message": "Successfully loaded broker activity historical data",
  "data": {
    "date_from": "2025-06-12",
    "date_to": "2026-06-12",
    "symbols": ["BBCA"],
    "broker_codes": ["XL"],
    "broker_name": "Stockbit Sekuritas Digital",
    "records": [
      {
        "date": "2026-06-12",
        "broker_code": "",
        "trade_activity": {
          "net_summary": {
            "avg_price": 6013.124139724929,
            "freq": 11470,
            "lot": -80310,
            "value": -48192677500
          },
          "buy_summary": {
            "avg_price": 6018.148413922266,
            "freq": 15299,
            "lot": 196491,
            "value": 118251200000
          },
          "sell_summary": {
            "avg_price": 6013.124139724929,
            "freq": 11470,
            "lot": 276801,
            "value": 166443877500
          },
          "foreign_summary": {
            "foreign_buy": 0,
            "foreign_sell": 0,
            "net_foreign": 0
          },
          "total_buy_lot": {
            "amount": 196491,
            "pct": 41.51580842270734
          },
          "total_sell_lot": {
            "amount": 276801,
            "pct": 58.48419157729266
          }
        },
        "price_activity": {
          "close_price": "5925",
          "return_summary": {
            "amount": -88.12413972492868,
            "pct": -1.4873272527414123
          }
        }
      }
    ],
    "pagination": {
      "page": 1,
      "limit": 25,
      "has_next": true,
      "has_prev": false
    },
    "summary": {
      "group_type": "INTERVAL_TYPE_UNSPECIFIED",
      "data": [
        {
          "date_from": "2025-06-12",
          "date_to": "2026-06-12",
          "net_summary": {
            "avg_price": 7176.700589329905,
            "freq": 2157586,
            "lot": 8846048,
            "value": 6146882152000
          }
        }
      ]
    }
  }
}
```

**Key fields not currently parsed:**
- `data.date_from` / `data.date_to` — actual date range of records returned
- `data.symbols[]` — echo of requested symbols
- `data.broker_codes[]` — echo of requested broker codes
- `data.records[].broker_code` — empty string `""` when single broker requested (name is in `data.broker_name`)
- `data.records[].trade_activity.foreign_summary.{foreign_buy, foreign_sell, net_foreign}` — foreign flow breakdown within broker
- `data.records[].trade_activity.buy_summary.freq` / `sell_summary.freq` / `net_summary.freq` — trade frequency
- `data.records[].trade_activity.total_buy_lot.amount` — absolute lot amount (same as `buy_summary.lot`)
- `data.records[].price_activity.return_summary.{amount, pct}` — price return for that day
- `data.pagination.has_prev` — bool
- `data.pagination.limit` — records per page (int)
- `data.summary[]` — aggregate summary over entire date range (net lot/value/avg_price/freq)

---

### `/order-trade/broker/activity` (Universe Scan — Broker-Centric)
**Probe date:** 2026-06-12 | **Source:** `journals/broker-scan-spy.json`

```json
{
  "message": "Successfully loaded Broker Activity data",
  "data": {
    "broker_activity_transaction": {
      "brokers_buy": [
        {
          "stock_code": "BBRI",
          "broker_code": "XL",
          "type": "BROKER_TYPE_LOCAL",
          "date": "2026-06-12",
          "value": 52415253000,
          "lot": 182626,
          "avg_price": 2871.6057704567165,
          "freq": 16046,
          "company_detail": {
            "icon_url": "https://assets.stockbit.com/logos/companies/BBRI.png",
            "corpaction": {"active": false, "icon": "", "text": ""},
            "notation": []
          },
          "nval_trend": [
            {"date": "2026-06-04", "nval": 53408687000, "nvol": 188925, "nfreq": 23891},
            {"date": "2026-06-05", "nval": 44105400000, "nvol": 159800, "nfreq": 19862},
            {"date": "2026-06-08", "nval": 65892517000, "nvol": 248166, "nfreq": 30506},
            {"date": "2026-06-09", "nval": 78054332000, "nvol": 292280, "nfreq": 23524},
            {"date": "2026-06-10", "nval": 73718883000, "nvol": 259706, "nfreq": 26691},
            {"date": "2026-06-11", "nval": 26264456000, "nvol":  91523, "nfreq": 19963},
            {"date": "2026-06-12", "nval": 52415253000, "nvol": 182626, "nfreq": 16046}
          ]
        }
      ],
      "brokers_sell": [
        {
          "stock_code": "EMAS",
          "broker_code": "XL",
          "type": "BROKER_TYPE_LOCAL",
          "date": "2026-06-12",
          "value": -8201352000,
          "lot": -46225,
          "avg_price": 6988.18976343645,
          "freq": 3678,
          "company_detail": {"icon_url": "...", "corpaction": {...}, "notation": []},
          "nval_trend": [...]
        }
      ]
    },
    "from": "2026-06-12",
    "to": "2026-06-12",
    "broker_code": "XL",
    "broker_name": "Stockbit Sekuritas Digital"
  }
}
```

**Key fields not currently parsed:**
- `data.from` / `data.to` — date range of the scan
- `data.broker_code` — echo of request (string)
- `data.broker_name` — full broker name
- `data.broker_activity_transaction.brokers_buy[].broker_code` — echo per row
- `data.broker_activity_transaction.brokers_buy[].freq` — trade frequency
- `data.broker_activity_transaction.brokers_buy[].company_detail.{icon_url, corpaction, notation}`
- `data.broker_activity_transaction.brokers_buy[].nval_trend[]` — **7-day daily net value trend** for this stock from this broker: `{date, nval, nvol, nfreq}`. Currently **not parsed at all**. Extremely useful for spotting accumulation pattern over a week.

---

### `/order-trade/broker/activity-chart` ⚠️ NEW — NOT IN `stockbit_api_data.md`
**Probe date:** 2026-06-12 | **Source:** `journals/broker-scan-spy.json`  
**URL:** `GET /order-trade/broker/activity-chart?period=RT_PERIOD_LAST_1_DAY&brokers_code={code}&investor_type=INVESTOR_TYPE_ALL&market_board=MARKET_TYPE_REGULER`

Returns intraday cumulative net buy/sell value per minute, for a broker's top traded stocks.

```json
{
  "message": "Successfully loaded broker activity chart",
  "data": {
    "from": "2026-06-12",
    "to": "2026-06-12",
    "data_last_updated": "2026-06-12T00:00:00Z",
    "broker_code": "XL",
    "broker_name": "Stockbit Sekuritas Digital",
    "chart_data": [
      {
        "type": "TYPE_CHART_VALUE",
        "symbols": ["BBRI", "BRPT", "EMAS", "BBCA", "TPIA", "AMMN"],
        "charts": [
          {
            "symbol": "EMAS",
            "chart": [
              {
                "date": "2026-06-12",
                "time": "09:00",
                "value": {
                  "raw": "-395667500",
                  "formatted": "(395.7M)"
                },
                "datetime_label": "09:00"
              },
              {
                "date": "2026-06-12",
                "time": "09:01",
                "value": {"raw": "-1287070000", "formatted": "(1.3B)"},
                "datetime_label": "09:01"
              }
            ]
          }
        ]
      }
    ],
    "date_session_info": {}
  }
}
```

**What this is useful for:** Seeing intraday broker accumulation/distribution curve per stock,
minute by minute. Useful for detecting when a broker started accumulating vs. the IEP signal.

---

### `/order-trade/broker/top`
**Probe date:** 2026-06-15 (spy), 2026-06-12 (scan) | **Source:** `journals/stockbit-spy.json`, `journals/broker-scan-spy.json`

```json
{
  "message": "Successfully get top broker",
  "data": {
    "date": {
      "from": "2026-06-15",
      "to": "2026-06-15",
      "idx": "2026-06-15"
    },
    "list": [
      {
        "code": "XL",
        "name": "Stockbit Sekuritas Digital",
        "investor_type": "INVESTOR_TYPE_UNSPECIFIED",
        "total_value": "7720636411716",
        "net_value": "37096908300",
        "buy_value": "3878866660008",
        "sell_value": "3841769751708",
        "total_volume": "22650037374",
        "total_frequency": "1946454",
        "group": "BROKER_GROUP_LOCAL"
      },
      {
        "code": "AK",
        "name": "UBS Sekuritas Indonesia",
        "investor_type": "INVESTOR_TYPE_UNSPECIFIED",
        "total_value": "6817827889350",
        "net_value": "-188832464000",
        "buy_value": "3314497712675",
        "sell_value": "3503330176675",
        "total_volume": "9441180126",
        "total_frequency": "490963",
        "group": "BROKER_GROUP_FOREIGN"
      },
      {
        "code": "CC",
        "name": "Mandiri Sekuritas",
        "investor_type": "INVESTOR_TYPE_UNSPECIFIED",
        "total_value": "7000862727820",
        "net_value": "-357477044100",
        "buy_value": "3321692841860",
        "sell_value": "3679169885960",
        "total_volume": "10617377704",
        "total_frequency": "634030",
        "group": "BROKER_GROUP_GOVERNMENT"
      }
    ]
  }
}
```

**`group` enum values observed:** `BROKER_GROUP_LOCAL`, `BROKER_GROUP_FOREIGN`, `BROKER_GROUP_GOVERNMENT`  
**All values are strings** (even numeric ones like `total_value`).

---

### `/screener/universe` ⚠️ NOT IN `stockbit_api_data.md`
**Probe date:** 2026-06-15 | **Source:** `journals/stockbit-spy.json`  
**URL:** `GET /screener/universe`

Returns the full index universe list used in Stockbit screener, with associated IDs.

```json
{
  "data": {
    "index": [
      {
        "id": "0",
        "name": "IHSG",
        "scope": "IHSG",
        "list": [
          {"id": "559",          "name": "IDX30",       "scope": "idx"},
          {"id": "550",          "name": "LQ45",        "scope": "idx"},
          {"id": "557",          "name": "SRI-KEHATI",  "scope": "idx"},
          {"id": "551",          "name": "JII",         "scope": "idx"},
          {"id": "558",          "name": "ISSI",        "scope": "idx"},
          {"id": "1000004908",   "name": "ECONOMIC30",  "scope": "idx"},
          {"id": "1000004351",   "name": "PRIMBANK10",  "scope": "idx"},
          {"id": "560",          "name": "INFOBANK15",  "scope": "idx"},
          {"id": "554",          "name": "BISNIS-27",   "scope": "idx"},
          {"id": "1868",         "name": "MNC36",       "scope": "idx"},
          {"id": "1000003585",   "name": "I-GRADE",     "scope": "idx"},
          {"id": "1000003185",   "name": "IDXESGL",     "scope": "idx"},
          {"id": "1000003847",   "name": "IDXLQ45LCL",  "scope": "idx"},
          {"id": "1000003288",   "name": "IDX80",       "scope": "idx"},
          {"id": "1000003576",   "name": "ESGQKEHATI",  "scope": "idx"},
          {"id": "1000000011",   "name": "IDXBUMN20",   "scope": "idx"},
          {"id": "1000003575",   "name": "ESGSKEHATI",  "scope": "idx"},
          {"id": "555",          "name": "KOMPAS100",   "scope": "idx"},
          {"id": "1837",         "name": "Investor33",  "scope": "idx"},
          {"id": "1000003830",   "name": "IDXSHAGROW",  "scope": "idx"},
          {"id": "1000000012",   "name": "JII70",       "scope": "idx"},
          {"id": "552",          "name": "MBX",         "scope": "idx"},
          {"id": "1000002393",   "name": "IDXG30",      "scope": "idx"},
          {"id": "1000003123",   "name": "IDXQ30",      "scope": "idx"},
          {"id": "1000000010",   "name": "IDXHIDIV20",  "scope": "idx"},
          {"id": "467",          "name": "IHSG",        "scope": "idx"},
          {"id": "1000004791",   "name": "NOTASI-KHUSUS","scope": "idx"},
          {"id": "1000005139",   "name": "TRADINGLIMIT","scope": "idx"},
          {"id": "1000004658",   "name": "DAYTRADE",    "scope": "idx"},
          {"id": "553",          "name": "DBX",         "scope": "idx"},
          {"id": "628",          "name": "Syariah",     "scope": "idx"},
          {"id": "1000004998",   "name": "IDXVESTA28",  "scope": "idx"},
          {"id": "1000003830",   "name": "IDXSHAGROW",  "scope": "idx"}
        ]
      }
    ]
  }
}
```

**Note:** This endpoint has the COMPLETE index list including IDs not documented elsewhere
(e.g. `NOTASI-KHUSUS` = 1000004791, `DAYTRADE` = 1000004658, `TRADINGLIMIT` = 1000005139).

---

### `/screener/metric` ⚠️ NOT IN `stockbit_api_data.md`
**Probe date:** 2026-06-15 | **Source:** `journals/stockbit-spy.json`  
**URL:** `GET /screener/metric`

Returns all available screener metrics with IDs. Useful for building screener queries programmatically.

```json
{
  "message": "Financial metrics for screener found",
  "data": [
    {
      "fitem_id": 18,
      "fitem_name": "Size",
      "show_chart_icon": 0,
      "child": [
        {"fitem_id": 2892,  "fitem_name": "Market Cap",                                    "show_chart_icon": 1, "child": []},
        {"fitem_id": 2895,  "fitem_name": "Enterprise Value",                              "show_chart_icon": 1, "child": []},
        {"fitem_id": 2899,  "fitem_name": "Current Share Outstanding",                     "show_chart_icon": 1, "child": []},
        {"fitem_id": 21535, "fitem_name": "Free Float",                                    "show_chart_icon": 1, "child": []},
        {"fitem_id": 21334, "fitem_name": "Number of Shareholders",                        "show_chart_icon": 1, "child": []},
        {"fitem_id": 21335, "fitem_name": "Number of Shareholders (# of changes 1M)",      "show_chart_icon": 1, "child": []},
        {"fitem_id": 21337, "fitem_name": "Number of Shareholders (% changes 1M)",         "show_chart_icon": 1, "child": []},
        {"fitem_id": 21543, "fitem_name": "Free Float Market Cap",                         "show_chart_icon": 1, "child": []}
      ]
    },
    {
      "fitem_id": 88,
      "fitem_name": "Valuation",
      "show_chart_icon": 0,
      "child": [
        {"fitem_id": 65, "fitem_name": "PE Standard Deviation Band", "show_chart_icon": 0,
         "child": [
           {"fitem_id": 12626, "fitem_name": "+2 PE Standard Deviation (1 Year)",  "show_chart_icon": 1, "child": []},
           {"fitem_id": 12623, "fitem_name": "+1 PE Standard Deviation (1 Year)",  "show_chart_icon": 1, "child": []}
         ]
        }
      ]
    }
  ]
}
```

**Key metric `fitem_id` values observed in screener results:**
| fitem_id | fitem_name |
|----------|-----------|
| 1461 | Return on Equity (TTM) |
| 13439 | Average (RoE 3 yr) |
| 13440 | Average (RoE 5 yr) |
| 3011 | Gross Profit (Growth: 3 Year) |
| 2290 | Gross Profit Margin (TTM)(%) |
| 3195 | Gross Profit Margin (Annual)(%) |
| 1561 | Gross Profit Margin (Quarter) |
| 13366 | Piotroski F-Score |

---

### `/screener/templates/{id}` ⚠️ NOT IN `stockbit_api_data.md`
**Probe date:** 2026-06-15 | **Source:** `journals/stockbit-spy.json`  
**URL:** `GET /screener/templates/{template_id}?type=TEMPLATE_TYPE_CUSTOM`

Returns screener results with per-company metric values.

```json
{
  "data": {
    "calcs": [
      {
        "company": {
          "country": "ID",
          "exchange": "IDX",
          "id": "294",
          "name": "Multi Bintang Indonesia Tbk.",
          "symbol": "MLBI",
          "symbol_2": "MLBI",
          "symbol_3": "MLBI",
          "type": "",
          "badges": {"is_new": false},
          "icon_url": "https://assets.stockbit.com/logos/companies/MLBI.png"
        },
        "results": [
          {"display": "76.75%", "id": 1461,  "item": "Return on Equity (TTM)",           "raw": "76.75"},
          {"display": "83.54",  "id": 13439, "item": "Average (RoE 3 yr)",               "raw": "83.54"},
          {"display": "79.48",  "id": 13440, "item": "Average (RoE 5 yr)",               "raw": "79.48"},
          {"display": "5.50%",  "id": 3011,  "item": "Gross Profit (Growth: 3 Year)",    "raw": "5.50"},
          {"display": "64.19%", "id": 2290,  "item": "Gross Profit Margin (TTM)(%)",     "raw": "64.19"},
          {"display": "63.76%", "id": 3195,  "item": "Gross Profit Margin (Annual)(%)",  "raw": "63.76"},
          {"display": "60.59%", "id": 1561,  "item": "Gross Profit Margin (Quarter)",    "raw": "60.59"},
          {"display": "9",      "id": 13366, "item": "Piotroski F-Score",                "raw": "9"}
        ]
      }
    ]
  }
}
```

**Note:** `results[].raw` is always a numeric string without `%`. `results[].display` has `%` appended.

---

## PROBED 2026-06-20 — BBCA ticker unless noted

All responses below captured via `probe_missing.py` on 2026-06-20 (market closed).
Token obtained from `.stockbit_profile/` persistent session.

---

### `/company-price-feed/v2/orderbook/companies/{ticker}`
**Probe date:** 2026-06-20 | **Source:** `journals/probe_orderbook.json`

```json
{
  "message": "...",
  "data": {
    "symbol": "BBCA",
    "name": "Bank Central Asia Tbk.",
    "status": "Active",
    "tradable": true,
    "company_type": "Saham",
    "country": "ID",
    "exchange": "IDX",
    "lastprice": 6300,
    "previous": 6075,
    "change": 225,
    "percentage_change": 3.7,
    "open": 6050,
    "high": 6300,
    "low": 6050,
    "close": 6300,
    "average": 6255,
    "volume": 366595500,
    "value": 2293015050000,
    "frequency": 38237,
    "up": "265",
    "down": "110",
    "unchanged": "1118",
    "fbuy": 1949692907500,
    "fsell": 1632500595000,
    "fnet": 317192312500,
    "foreign": "78.11",
    "domestic": "21.89",
    "has_foreign_bs": true,
    "uma": false,
    "ara": {"value": "7,550", "visible": true},
    "arb": {"value": "5,375", "visible": true},
    "next_ara": {"value": "7,550", "visible": true},
    "next_arb": {"value": "5,375", "visible": true},
    "autoreject_time_left_in_sec": 0,
    "auto_reject_estimation": "...",
    "corp_action": {"active": true, "icon": "...", "text": "..."},
    "notation": [],
    "icon_url": "https://assets.stockbit.com/logos/companies/BBCA.png",
    "orderbook_active_feature_mobile": "ORDER_BOOK_FEATURE_FOREIGN_BS",
    "bid": [
      {"price": "6225", "que_num": "119", "volume": "1397700", "change_percentage": ""},
      {"price": "6200", "que_num": "320", "volume": "1049800", "change_percentage": ""},
      {"price": "6175", "que_num": "306", "volume": "1477000", "change_percentage": ""}
    ],
    "offer": [
      {"price": "6300", "que_num": "...", "volume": "...", "change_percentage": ""}
    ],
    "total_bid_offer": {
      "bid":   {"freq": "12,968", "lot": "57,199,600"},
      "offer": {"freq": "8,805",  "lot": "51,709,600"}
    },
    "iepiev": {
      "symbol": "",
      "status": "STATUS_UNSPECIFIED",
      "iep": {"raw": 0, "formatted": ""},
      "iev": {"raw": 0, "formatted": ""},
      "time_left_seconds": 0,
      "best_bid_offer": {
        "bid": {
          "price":    {"raw": 6275, "formatted": "6,275"},
          "quantity": {"raw": 334,  "formatted": "334"},
          "change_percentage": "3.29%"
        },
        "offer": {
          "price":    {"raw": 6300,  "formatted": "6,300"},
          "quantity": {"raw": 30904, "formatted": "30,904"},
          "change_percentage": "3.70%"
        },
        "time_left_seconds": 42600
      },
      "iep_changes": {
        "price":      {"raw": 0, "formatted": ""},
        "percentage": {"raw": 0, "formatted": ""}
      }
    },
    "market_data": [
      {"label": "All Market", "frequency": {"raw": "38237", "formatted": "38.2 K"}, "volume": {"raw": "366595500", "formatted": "367 M"}, "value": {"raw": "2293015050000", "formatted": "2.29 T"}},
      {"label": "Regular",    "frequency": {"raw": "38237", "formatted": "38.2 K"}, "volume": {"raw": "366595500", "formatted": "367 M"}, "value": {"raw": "2293015050000", "formatted": "2.29 T"}},
      {"label": "Nego",       "frequency": {"raw": "0", "formatted": "0"},          "volume": {"raw": "0", "formatted": "0"},           "value": {"raw": "0", "formatted": "0"}},
      {"label": "Cash",       "frequency": {"raw": "0", "formatted": "0"},          "volume": {"raw": "0", "formatted": "0"},           "value": {"raw": "0", "formatted": "0"}}
    ]
  }
}
```

**Parser corrections / new fields vs existing doc:**
- `data.volume` is in **SHARES** (366,595,500 shares ≠ 3,665,955 lots) — the doc was wrong
- `data.total_bid_offer.bid.lot` is a comma-string (`"57,199,600"`) and in **SHARES**, not lots
- `data.total_bid_offer` also has `freq` (number of orders) — not just `lot`
- `data.iepiev.best_bid_offer.bid.change_percentage` → `"3.29%"` (new field)
- `data.iepiev.iep_changes` → price and % change of IEP (new, useful for pre-open trend)
- `data.iepiev.time_left_seconds` → seconds until session closes (non-zero during regular session)
- `data.ara` / `data.arb` → auto-reject upper/lower limits `{value: "7,550", visible: bool}`
- `data.foreign` / `data.domestic` → string % of total value (e.g. `"78.11"`)
- `data.up` / `data.down` / `data.unchanged` → advancing/declining/unchanged counts (strings)
- `data.market_data[]` → breakdown by market board (Regular, Nego, Cash) with `{label, frequency, volume, value}` each with `{raw, formatted}`
- `data.orderbook_active_feature_mobile` → feature flag string

---

### `/marketdetectors/{ticker}` (broker summary + bandar detector)
**Probe date:** 2026-06-20 | **Source:** `journals/probe_marketdetectors_latest.json`

```json
{
  "message": "Successfully retrieved market detector data",
  "data": {
    "from": "20260619",
    "to": "20260619",
    "broker_summary": {
      "brokers_buy": [
        {
          "blot": "534547",
          "blotv": "8.13085e+07",
          "bval": "3.3656082e+11",
          "bvalv": "5.1055367e+11",
          "netbs_broker_code": "YU",
          "netbs_buy_avg_price": "6279.216441085496",
          "netbs_date": "20260619",
          "netbs_stock_code": "BBCA",
          "type": "Asing",
          "freq": "5138"
        }
      ],
      "brokers_sell": [
        {
          "slot": "-1.051631e+06",
          "slotv": "1.469565e+08",
          "sval": "-6.62721285e+11",
          "svalv": "9.2479353e+11",
          "netbs_broker_code": "ZP",
          "netbs_sell_avg_price": "6292.974655765482",
          "netbs_date": "20260619",
          "netbs_stock_code": "BBCA",
          "type": "Asing",
          "freq": "1892"
        }
      ]
    },
    "bandar_detector": {
      "average": 6273.213,
      "broker_accdist": "Acc",
      "number_broker_buysell": -24,
      "total_buyer": 26,
      "total_seller": 50,
      "value": 1008870000000,
      "volume": 1608219,
      "avg": {
        "accdist": "Neutral",
        "amount": -48361996000,
        "percent": -4.7936797,
        "vol": -77092.87
      },
      "avg5": {
        "accdist": "Small Dist",
        "amount": -109973560000,
        "percent": -10.900667,
        "vol": -175306.6
      },
      "top1": {
        "accdist": "Big Dist",
        "amount": -324377800000,
        "percent": -32.152588,
        "vol": -517084
      },
      "top3": {
        "accdist": "Small Dist",
        "amount": -103025600000,
        "percent": -10.21198,
        "vol": -164231
      },
      "top5": {
        "accdist": "Small Acc",
        "amount": 67913175000,
        "percent": 6.731608,
        "vol": 108259
      },
      "top10": {
        "accdist": "Neutral",
        "amount": 34552230000,
        "percent": 3.4248445,
        "vol": 55079
      }
    }
  }
}
```

**Corrections / new fields vs existing doc:**
- Buy side: field names `blot`/`bval` (net) plus `blotv`/`bvalv` (gross volume/value) — both present
- Sell side: field names `slot`/`sval` (negative, net) plus `slotv`/`svalv` (gross, positive)
- Both sides have `freq` (trade frequency string) and `netbs_stock_code`
- `bandar_detector.top3`, `.top5`, `.top10` exist (not just `top1`) — each has `{accdist, amount, percent, vol}`
- `bandar_detector.number_broker_buysell` → int (negative = more sellers than buyers)
- `bandar_detector.average` → float (VWAP of the day)
- `bandar_detector.value` / `.volume` → total market value and lot volume for the day
- `broker_accdist` enum values seen: `"Acc"`, `"Dis"`, `"Neutral"`
- `accdist` label values seen: `"Big Dist"`, `"Small Dist"`, `"Neutral"`, `"Small Acc"`, `"Big Acc"`

---

### `/order-trade/running-trade`
**Probe date:** 2026-06-20 (post-market) | **Source:** `journals/probe_running_trade.json`

```json
{
  "message": "Successfully loaded running trade data",
  "data": {
    "is_open_market": false,
    "is_show_bs": true,
    "break_time_left_seconds": 0,
    "date": "...",
    "running_trade": [
      {
        "id": "4505278138",
        "time": "16:25:49",
        "action": "buy",
        "code": "BBCA",
        "price": "6,300",
        "change": "+3.70%",
        "lot": "0.63",
        "is_broker_exists": true,
        "buyer": "YU [F]",
        "seller": "YU [D]",
        "trade_number": "1750352",
        "buyer_type": "BROKER_TYPE_FOREIGN",
        "seller_type": "BROKER_TYPE_FOREIGN",
        "market_board": "NG",
        "buy_order_number": "4478740",
        "sell_order_number": "4478739",
        "group_order_number": "4478740",
        "value": {
          "raw": 396900,
          "formatted": "396.9K"
        }
      }
    ]
  }
}
```

**Corrections / new fields vs existing doc:**
- `data.is_open_market` → bool (false when market closed)
- `data.is_show_bs` → bool (whether buyer/seller column is shown)
- `data.break_time_left_seconds` → int (seconds until session resumes)
- `data.date` → current date string
- `running_trade[].id` → string trade ID
- `running_trade[].action` → `"buy"` | `"sell"` (direction label)
- `running_trade[].change` → price change % string (`"+3.70%"`)
- `running_trade[].trade_number` → string sequence number
- `running_trade[].buyer` → formatted: `"YU [F]"` (code + [F]oreign/[D]omestic suffix)
- `running_trade[].buyer_type` → enum: `"BROKER_TYPE_FOREIGN"` | `"BROKER_TYPE_LOCAL"` | `"BROKER_TYPE_UNSPECIFIED"`
- `running_trade[].buy_order_number` / `sell_order_number` / `group_order_number` → string order IDs
- `running_trade[].value.formatted` → human-readable `"396.9K"`, `"999.9M"`, etc.

---

### `/order-trade/running-trade/chart/{ticker}`
**Probe date:** 2026-06-20 | **Source:** `journals/probe_running_trade_chart.json`

```json
{
  "data": {
    "from": "2026-06-19",
    "to": "2026-06-19",
    "data_last_updated": "2026-06-19T00:00:00Z",
    "date_session_info": {},
    "price_chart_data": [
      {
        "date": "2026-06-19",
        "time": "09:00",
        "datetime_label": "09:00",
        "value": {"raw": "6175", "formatted": "6,175"},
        "open":  {"raw": "6075", "formatted": "6,075"},
        "high":  {"raw": "6175", "formatted": "6,175"},
        "low":   {"raw": "6050", "formatted": "6,050"}
      },
      {
        "date": "2026-06-19",
        "time": "09:01",
        "datetime_label": "09:01",
        "value": {"raw": "6200", "formatted": "6,200"},
        "open":  {"raw": "6175", "formatted": "6,175"},
        "high":  {"raw": "6200", "formatted": "6,200"},
        "low":   {"raw": "6150", "formatted": "6,150"}
      }
    ],
    "broker_chart_data": [
      {
        "type": "TYPE_CHART_VALUE",
        "brokers": ["XL", "YU", "BK", "ZP", "SQ"],
        "charts": [
          {
            "broker_code": "XL",
            "chart": [
              {
                "date": "2026-06-19",
                "time": "09:00",
                "datetime_label": "09:00",
                "value": {"raw": "4996225000", "formatted": "5B"},
                "open": null,
                "high": null,
                "low":  null
              }
            ]
          }
        ]
      }
    ]
  }
}
```

**Notes:**
- `price_chart_data[]` → minute-by-minute OHLC candlestick data (`value` = close price). All values are **strings** inside the `raw` field.
- `broker_chart_data[]` → top 5 brokers' cumulative net value per minute. `value.raw` is a string IDR amount (can be negative for net sellers). `open/high/low` are `null` for broker data.

---

### `/corpaction/{ticker}?limit=50`
**Probe date:** 2026-06-20 | **Source:** `journals/probe_corpaction.json`

```json
{
  "data": [
    {
      "action_type": "dividend",
      "action_info": {
        "dividend": {
          "company_id": "54",
          "company_symbol": "BBCA",
          "corp_action_active": true,
          "dividend_id": "117860",
          "dividend_created": "2026-06-05",
          "dividend_lastupdate": "2026-06-05",
          "dividend_cumdate": "2026-06-15",
          "dividend_exdate": "2026-06-17",
          "dividend_recdate": "2026-06-18",
          "dividend_paydate": "2026-06-26",
          "dividend_value": "20",
          "dividend_value_formatted": "Rp 20",
          "dividend_currency": "CURRENCY_IDR",
          "dividend_fiscal_year": 0,
          "dividend_value_adjusted": 0,
          "dividend_datahash": "2d563330e11432fc459742ba14bcbc98",
          "dividend_lock": 0,
          "dividend_iqp_id": "",
          "event_note": "",
          "lastprice": "",
          "lastprice_formatted": ""
        }
      }
    },
    {
      "action_type": "rups",
      "action_info": {
        "rups": {
          "company_id": "54",
          "company_symbol": "BBCA",
          "corp_action_active": false,
          "rups_id": "1460182",
          "rups_created": "2026-01-29",
          "rups_date": "2026-03-12",
          "rups_time": "14:00",
          "rups_venue": "Menara BCA, Grand Indonesia Jl. M.H. Thamrin No. 1 Jakarta 10310",
          "rups_datahash": "ef904f297719880d29916ed769f980d9",
          "rups_iqp_agenda": "",
          "rups_iqp_id": "",
          "rups_iqp_rec_dt": "",
          "rups_iqp_remark": "",
          "rups_iqp_result": "",
          "rups_iqp_revised_date": "",
          "rups_iqp_type": ""
        }
      }
    },
    {
      "action_type": "stocksplit",
      "action_info": {
        "stocksplit": {
          "company_id": "54",
          "company_symbol": "BBCA",
          "corp_action_active": false,
          "split_id": "...",
          "split_created": "YYYY-MM-DD",
          "split_exdate": "YYYY-MM-DD",
          "split_ratio": "1:2",
          "split_datahash": "..."
        }
      }
    }
  ]
}
```

**Corrections vs existing doc:**
- Action type key for stock split is `"stocksplit"` (not `"split"`) — payload key is also `stocksplit`
- Each action has `company_id`, `company_symbol`, `{type}_id`, `{type}_datahash`, `{type}_lastupdate` / `{type}_lock`
- Dividend has `dividend_value_formatted` (`"Rp 20"`), `dividend_currency`, `dividend_fiscal_year`, `dividend_value_adjusted`
- RUPS has many `rups_iqp_*` fields (IDX IQP reporting system fields, usually empty)
- `action_types seen in BBCA history:` `"dividend"`, `"rups"`, `"stocksplit"`

---

### `/insider/shareholding/composition/companies/{ticker}`
**Probe date:** 2026-06-20 | **Source:** `journals/probe_shareholding.json`

```json
{
  "message": "Successfully fetched composition by company symbol",
  "data": {
    "first_available_date": "...",
    "last_available_date": "2026-05-29",
    "periods": [
      {
        "report_date": "2026-05-29",
        "total_shares": {
          "raw": "123275050000",
          "formatted": "123.28B"
        },
        "compositions": [
          {
            "label": "DWIMURIA INVESTAMA ANDALAN",
            "shares": {
              "raw": "67729950000",
              "formatted": "67.73B"
            },
            "percentage": {
              "raw": 54.94213954891927,
              "formatted": "54.94%"
            },
            "colors": {
              "light": "#0BA16B",
              "dark": "#0BA16B"
            }
          },
          {
            "label": "Mutual Funds",
            "shares": {"raw": "18920621304", "formatted": "18.92B"},
            "percentage": {"raw": 15.348297408113, "formatted": "15.35%"},
            "colors": {"light": "#1FD795", "dark": "#1FD795"}
          },
          {
            "label": "Individual",
            "shares": {"raw": "10778610902", "formatted": "10.78B"},
            "percentage": {"raw": 8.74354616120618, "formatted": "8.74%"},
            "colors": {"light": "#35CBB1", "dark": "#35CBB1"}
          },
          {
            "label": "Pension Funds",
            "shares": {"raw": "5660775303", "formatted": "5.66B"},
            "percentage": {"raw": 4.59198783776604, "formatted": "4.59%"},
            "colors": {"light": "#8DEADA", "dark": "#8DEADA"}
          },
          {
            "label": "Exchange Traded Funds",
            "shares": {"raw": "2602956578", "formatted": "2.60B"},
            "percentage": {"raw": 2.11150316142642, "formatted": "2.11%"},
            "colors": {}
          },
          {
            "label": "Sovereign Wealth Fund",
            "shares": {"raw": "2025891794", "formatted": "2.03B"},
            "percentage": {"raw": 1.64339158167042, "formatted": "1.64%"},
            "colors": {}
          }
        ]
      }
    ]
  }
}
```

**New fields vs existing doc:**
- `data.first_available_date` / `data.last_available_date` → date range of available reports
- `periods[0].total_shares.{raw, formatted}` → total shares outstanding
- `compositions[].shares.{raw, formatted}` → absolute share count (not just %)
- `compositions[].colors.{light, dark}` → chart colors per category (hex string)

---

### `/insider/company/majorholder`
**Probe date:** 2026-06-20 | **Source:** `journals/probe_insider_majorholder.json`

```json
{
  "message": "Successfully majorholder data",
  "data": {
    "is_more": false,
    "movement": [
      {
        "id": "1000000439",
        "name": "HENDRA TANUMIHARDJA",
        "symbol": "BBCA",
        "date": "25 Mar 26",
        "nationality": "NATIONALITY_TYPE_LOCAL",
        "action_type": "ACTION_TYPE_BUY",
        "previous": {
          "value": "193,206",
          "percentage": "0.0002",
          "formatted_value": ""
        },
        "current": {
          "value": "341,139",
          "percentage": "0.0003",
          "formatted_value": ""
        },
        "changes": {
          "value": "+147,933",
          "percentage": "+0.0001",
          "formatted_value": "147,933"
        },
        "price_formatted": "6,982",
        "marker": "",
        "is_posted": false,
        "cmh_id": "0",
        "data_source": {
          "label": "Sumber: IDX",
          "type": "SOURCE_TYPE_IDX"
        },
        "broker_detail": {
          "code": "",
          "group": "BROKER_GROUP_UNSPECIFIED"
        },
        "badges": ["SHAREHOLDER_BADGE_DIREKTUR"]
      }
    ]
  }
}
```

**New fields vs existing doc:**
- `data.is_more` → bool (pagination — true if more pages)
- `movement[].id` → string record ID
- `movement[].nationality` → `"NATIONALITY_TYPE_LOCAL"` | `"NATIONALITY_TYPE_FOREIGN"`
- `movement[].previous.formatted_value` / `current.formatted_value` → usually `""`
- `movement[].changes.formatted_value` → absolute change without sign (`"147,933"`)
- `movement[].marker` → string (usually empty)
- `movement[].is_posted` → bool
- `movement[].cmh_id` → string
- `movement[].data_source.{label, type}` → `label: "Sumber: IDX"`, `type: "SOURCE_TYPE_IDX"` | `"SOURCE_TYPE_KSEI"`
- `movement[].broker_detail.{code, group}` → broker used for the transaction (often empty)

---

### `/analyst-ratings/{ticker}`
**Probe date:** 2026-06-20 | **Source:** `journals/probe_analyst_ratings.json`

```json
{
  "message": "Successfully retrieved analyst ratings data",
  "data": {
    "price_target": {
      "best_target": 8827,
      "best_low_target": 5500,
      "best_high_target": 10900,
      "current_price": 6300
    },
    "recommendation": "Buy",
    "total_buy": 35,
    "total_sell": 0,
    "total_hold": 2,
    "total_analyst": 37,
    "last_updated": "15 Jun 26"
  }
}
```

**New fields vs existing doc:**
- `data.price_target.best_low_target` → int (lowest analyst target, IDR)
- `data.price_target.best_high_target` → int (highest analyst target, IDR)

---

### `/analyst-ratings/{ticker}/consensus`
**Probe date:** 2026-06-20 | **Source:** `journals/probe_analyst_consensus.json`

This endpoint returns **forward estimates by metric**, not a consensus rating. It is a list not a dict.

```json
{
  "message": "Successfully retrieved analyst consensus data",
  "data": [
    {
      "name": "Revenue",
      "items": [
        {"year": 2025, "is_estimate": false, "value": "118,573 B", "raw_value": 0},
        {"year": 2026, "is_estimate": true,  "value": "118,236 B", "raw_value": 0},
        {"year": 2027, "is_estimate": true,  "value": "127,703 B", "raw_value": 0}
      ]
    },
    {
      "name": "Op. Profit",
      "items": [
        {"year": 2025, "is_estimate": false, "value": "71,261 B", "raw_value": 0},
        {"year": 2026, "is_estimate": true,  "value": "75,587 B", "raw_value": 0},
        {"year": 2027, "is_estimate": true,  "value": "82,485 B", "raw_value": 0}
      ]
    },
    {
      "name": "Net Income",
      "items": [
        {"year": 2025, "is_estimate": false, "value": "57,537 B", "raw_value": 0},
        {"year": 2026, "is_estimate": true,  "value": "60,629 B", "raw_value": 0},
        {"year": 2027, "is_estimate": true,  "value": "66,050 B", "raw_value": 0}
      ]
    },
    {
      "name": "EPS",
      "items": [
        {"year": 2025, "is_estimate": false, "value": "466.74", "raw_value": 0},
        {"year": 2026, "is_estimate": true,  "value": "490.46", "raw_value": 0},
        {"year": 2027, "is_estimate": true,  "value": "533.69", "raw_value": 0}
      ]
    }
  ]
}
```

**Note:** `data` is a **list**, not a dict. `raw_value` is always `0` — the actual value is in the formatted `value` string. This endpoint is completely different from `/analyst-ratings/{ticker}` — it contains multi-year forward estimates, not the rating count/recommendation.

---

### `/keystats/ratio/v1/{ticker}`
**Probe date:** 2026-06-20 | **Source:** `journals/probe_keystats.json`

```json
{
  "data": {
    "financial_report_currency": "IDR",
    "financial_year_parent": {
      "financial_year_groups": [
        {
          "financial_year_values": [
            {
              "year": "2026",
              "period_values": [
                {"period": "Q1", "quarter_value": "14,684 B", "year": "2026", "is_new_update": false}
              ],
              "annualised_value": "58,736 B",
              "ttm_value": "58,075 B",
              "is_new_update": false,
              "dividend": "301.00",
              "payout_ratio": "63.17%",
              "dividend_yield": "4.78%"
            }
          ]
        }
      ]
    },
    "closure_fin_items_results": [
      {
        "fin_name_results": [
          {
            "fitem": {
              "id": "12148",
              "name": "Current PE Ratio (Annualised)",
              "value": "13.22"
            },
            "hidden_graph_ico": false,
            "is_new_update": false
          },
          {
            "fitem": {
              "id": "2891",
              "name": "Current PE Ratio (TTM)",
              "value": "13.37"
            },
            "hidden_graph_ico": false,
            "is_new_update": false
          },
          {
            "fitem": {"id": "16577", "name": "Forward PE Ratio",           "value": "12.28"},
            "hidden_graph_ico": false, "is_new_update": false
          },
          {
            "fitem": {"id": "13427", "name": "IHSG PE Ratio TTM (Median)", "value": "7.57"},
            "hidden_graph_ico": false, "is_new_update": false
          },
          {
            "fitem": {"id": "2898",  "name": "Earnings Yield (TTM)",       "value": "7.48%"},
            "hidden_graph_ico": false, "is_new_update": false
          }
        ]
      }
    ],
    "stats": {
      "52_week_high": {"label": "52 Week High", "value": "10,400", "change_value": "-3,835", "change_percentage": "-36.88%"},
      "52_week_low":  {"label": "52 Week Low",  "value": "4,870",  "change_value": "+1,430", "change_percentage": "+29.36%"},
      "rank_near_52_week_high": {"label": "Rank (Near 52 Weeks High)", "value": "31.15%", "display_as": "progress_bar"}
    },
    "info": {
      "shares_outstanding": "123.28 B",
      "market_cap": {"formatted": "776.63 T", "raw": 776634150000000},
      "pbv": {"formatted": "3.00", "raw": 3.00}
    },
    "dividend_group": {
      "last_dividend_value": "Rp 20",
      "last_dividend_exdate": "17 Jun 26",
      "dividend_yield": "4.78%",
      "payout_ratio": "63.17%"
    }
  }
}
```

**New fields vs existing doc (major discoveries):**
- `data.stats` → pre-computed 52-week high/low with change vs current price, and rank
- `data.info.{shares_outstanding, market_cap.{formatted, raw}, pbv.{formatted, raw}}` → quick summary
- `data.dividend_group.{last_dividend_value, last_dividend_exdate, dividend_yield, payout_ratio}` → latest dividend summary
- `data.financial_report_currency` → `"IDR"` or `"USD"`
- `data.financial_year_parent` → multi-year net income with quarterly breakdown, dividend, payout ratio per year
- Each `fin_name_results[].fitem` has `id` (numeric string), `name`, `value` (string)
- `fin_name_results[].is_new_update` → bool flag for recently updated metrics

---

### `/company-price-feed/seasonality/{ticker}`
**Probe date:** 2026-06-20 | **Source:** `journals/probe_seasonality.json`

```json
{
  "message": "Success",
  "data": {
    "default_last_year": 5,
    "avg": {
      "columns": [
        {"name": "Jan", "value": "-1.10", "color": "#A70000"},
        {"name": "Feb", "value": "-0.34", "color": "#A70000"},
        {"name": "Jun", "value": "0.95",  "color": "#018601"},
        {"name": "Dec", "value": "1.35",  "color": "#018601"}
      ]
    },
    "prob": {
      "columns": [
        {"name": "Jan", "value": "40", "color": "#C20D0D"},
        {"name": "Feb", "value": "60", "color": "#018601"},
        {"name": "Jun", "value": "60", "color": "#018601"}
      ]
    },
    "up": {
      "columns": [
        {"name": "Jan", "value": "2", "color": "#C20D0D"},
        {"name": "Jun", "value": "3", "color": "#018601"}
      ]
    },
    "down": {
      "columns": [
        {"name": "Jan", "value": "3", "color": "#C20D0D"},
        {"name": "Jun", "value": "2", "color": "#A70000"}
      ]
    },
    "total_months": {
      "columns": [
        {"name": "Jan", "value": "5", "color": ""},
        {"name": "Jun", "value": "5", "color": ""}
      ]
    },
    "price_change": [
      {
        "row": 2026,
        "columns": [
          {"name": "Year", "value": "-21.98", "color": "#E70000"},
          {"name": "Jun",  "value": "10.53",  "color": "#009B00"},
          {"name": "May",  "value": "-2.56",  "color": "#A70000"}
        ]
      },
      {
        "row": 2025,
        "columns": [
          {"name": "Year", "value": "-16.32", "color": "#E70000"},
          {"name": "Dec",  "value": "-2.42",  "color": "#A70000"},
          {"name": "Jun",  "value": "-7.71",  "color": "#C20D0D"}
        ]
      }
    ]
  }
}
```

**New fields vs existing doc:**
- `data.down.columns[]` → number of negative years per month (mirror of `up`)
- `data.avg.columns[].color` → hex color string for the chart cell (green/red)
- `data.price_change[]` → **year-by-year price change per month**, `row` = year, `columns[].name` = month or `"Year"`. Enables full historical table display.

---

### `/company-price-feed/market-time`
**Probe date:** 2026-06-20 (market closed) | **Source:** `journals/probe_market_time.json`

```json
{
  "message": "Successfully get market time data",
  "data": {
    "market": {
      "status": "STATUS_CLOSE"
    },
    "iepiev_regular": {
      "status": "STATUS_CLOSE"
    },
    "iepiev_fca": {
      "status": "STATUS_CLOSE"
    }
  }
}
```

**This is the confirmed structure.** The field names are NOT `marketStatus` or `session` as previously guessed. The actual structure:
- `data.market.status` → market status string
- `data.iepiev_regular.status` → pre-open regular board call auction status
- `data.iepiev_fca` → FCA (Foreign Currency Auction?) call auction status
- Status enum values observed: `"STATUS_CLOSE"`. Expected live values: likely `"STATUS_OPEN"`, `"STATUS_PRE_OPEN"`, `"STATUS_PRE_CLOSING"` etc.

⚠️ **Probe was taken while market was closed.** Run again during pre-open (08:45–09:00 WIB, NCP locked 08:56–09:00) to capture all session status values.

---

### `/company-price-feed/historical/summary/{ticker}`
**Probe date:** 2026-06-20 | **Source:** `journals/probe_historical_summary.json`

```json
{
  "message": "Successfully get the historical summary",
  "data": {
    "result": [
      {
        "date": "2026-06-19",
        "open": 6050,
        "high": 6300,
        "low": 6050,
        "close": 6300,
        "change": 225,
        "change_percentage": 3.7,
        "average": 6255,
        "volume": 3665955,
        "value": 2293015050000,
        "frequency": 38237,
        "foreign_buy": 1949692907500,
        "foreign_sell": 1632500595000,
        "net_foreign": 317192312500
      }
    ],
    "paginate": {
      "totalrows": "...",
      "totalpages": "...",
      "page": 1,
      "limit": 10
    }
  }
}
```

**Notes:**
- `data.result[]` is the OHLCV list (not `data.list[]` as guessed in existing doc)
- `data.paginate` (not `data.pagination`) for pagination
- `volume` is in **LOTS** here (3,665,955 lots = 366,595,500 shares) — unlike the orderbook endpoint where volume is in shares
- `foreign_buy`, `foreign_sell`, `net_foreign` → IDR values per day (not lots)
- `change_percentage` is a float (e.g. `3.7`), not a string

---

### `/order-trade/broker/distribution`
**Probe date:** 2026-06-20 | **Source:** `journals/probe_broker_distribution.json`

```json
{
  "message": "Successfully loaded Broker Distribution data",
  "data": {
    "date_info": "2026-06-19",
    "start_date": "2026-06-19",
    "end_date": "2026-06-19",
    "by_value": {
      "top_broker_buy": [
        {
          "detail": {
            "code": "YU",
            "type": "Asing",
            "amount": 510553670000
          },
          "distribute_to": [
            {"code": "ZP",  "type": "Asing",     "amount": 163554732500},
            {"code": "AK",  "type": "Asing",     "amount": 138896915000},
            {"code": "YU",  "type": "Asing",     "amount": 88461090000},
            {"code": "SQ",  "type": "Lokal",     "amount": 27915345000},
            {"code": "CC",  "type": "Pemerintah","amount": 20560590000}
          ]
        }
      ],
      "top_broker_sell": [
        {
          "detail": {
            "code": "ZP",
            "type": "Asing",
            "amount": 662721285000
          },
          "distribute_to": [
            {"code": "YU", "type": "Asing", "amount": 176591092500},
            {"code": "AK", "type": "Asing", "amount": 169764202500}
          ]
        }
      ]
    },
    "by_volume": {
      "top_broker_buy":  [...],
      "top_broker_sell": [...]
    }
  }
}
```

**What this endpoint shows:** For each top broker (buyer or seller), it shows which brokers they traded AGAINST (cross-broker distribution). `distribute_to` = the counterparty brokers and amounts.

---

### `/findata-view/marketdetectors/brokers`
**Probe date:** 2026-06-20 | **Source:** `journals/probe_broker_list.json`

```json
{
  "message": "Successfully retrieved broker list",
  "data": [
    {
      "id": 96,
      "code": "AK",
      "name": "UBS Sekuritas Indonesia",
      "permission": "Penjamin Emisi Efek, Perantara Pedagang Efek",
      "group": "Asing",
      "color": "#c11214"
    },
    {
      "id": 33,
      "code": "AF",
      "name": "Harita Kencana Sekuritas",
      "permission": "Perantara Pedagang Efek",
      "group": "Lokal",
      "color": "#7924c3"
    }
  ]
}
```

**Field notes:**
- `id` → int (internal Stockbit broker ID)
- `group` → `"Asing"` (foreign) | `"Lokal"` (local) | `"Pemerintah"` (government-linked) — note Indonesian strings, not enum codes
- `permission` → comma-separated license types in Indonesian
- `color` → hex color for charting

---

### `/emitten/{ticker}/profile`
**Probe date:** 2026-06-20 | **Source:** `journals/probe_emitten_profile.json`

```json
{
  "data": {
    "address": [
      {
        "id": "54",
        "email": ["investor_relations@bca.co.id"],
        "fax": "021-23588300",
        "phone": "021-23588000",
        "npwp": "01.308.449.6-091.000",
        "website": "www.bca.co.id",
        "office": "Menara BCA, Grand Indonesia Jalan MH Thamrin No. 1 Jakarta 10310",
        "value": "<td ...> ... </td>",
        "lastupdate": "2021-12-28T14:00:18+07:00",
        "key": ""
      }
    ],
    "background": "PT Bank Central Asia Tbk. atau BBCA dalam bidang usaha bank umum...",
    "history": {
      "amount": "927 B",
      "board": "Papan Utama",
      "date": "31 May 2000",
      "price": "1,400",
      "registrar": "..."
    },
    "key_executive": [...],
    "secretary": [...],
    "shareholder": [...]
  }
}
```

**Field notes:**
- `data.address[].value` → raw HTML table fragment (parse carefully)
- `data.background` → plain text company description (Indonesian)
- `data.history.{amount, board, date, price, registrar}` → IPO details

---

### `/findata-view/company/financial`
**Probe date:** 2026-06-20 | **Source:** `journals/probe_financial_income.json`

```json
{
  "message": "Successfully retrieved company financial",
  "data": {
    "currency": ["IDR", "USD"],
    "default_currency": "IDR",
    "rounding_value": "In Million",
    "html_report": "<div class=\"preview-cont\">...</div>",
    "data_tables": {...}
  }
}
```

⚠️ **The financial data is returned as raw HTML in `html_report`**, not structured JSON. The `data_tables` field may contain structured data — inspect `data_tables` separately if needed. This endpoint is not suitable for direct JSON parsing without HTML extraction.

---

### `/earnings`
**Probe date:** 2026-06-20 | **Source:** `journals/probe_earnings.json`

```json
{
  "message": "Successfully retrieved earnings recap results",
  "data": {
    "keyword": "BBCA",
    "order": "desc",
    "page": "1",
    "sortcol": "4",
    "quarter": 1,
    "year": "2026",
    "totalrows": 1,
    "prev_earnings_period": {"quarter": "4", "year": "2025"},
    "next_earnings_period": {"quarter": "",  "year": ""},
    "company": [
      {
        "company_name": "BBCA",
        "analyst": {
          "consensus": {
            "actual": "119.12",
            "estimate": "-",
            "surprise": "-"
          },
          "prevyear": {
            "actual": "119.12",
            "change": "3.81",
            "previous": "114.75"
          }
        }
      }
    ]
  }
}
```

**Notes:**
- `data.company[]` — each item has `company_name` and `analyst.{consensus, prevyear}`
- `consensus.actual` → EPS actual (string), `consensus.estimate` → analyst EPS estimate (`"-"` if none)
- `prevyear.{actual, change, previous}` → YoY comparison
- `prev_earnings_period` / `next_earnings_period` → navigation between periods

---

### `/valuation/company/{ticker}/metrics`
**Probe date:** 2026-06-20 | **Source:** `journals/probe_valuation_metrics.json`

```json
{
  "message": "Metric value for company BBCA",
  "data": [
    {"id": 13200, "value": "471.10"},
    {"id": 0,     "value": "0.00"},
    {"id": 12635, "value": "20.96"}
  ]
}
```

**Notes:** Returns metric IDs with values but no labels. Cross-reference `fitem_id` values against `/screener/metric` to get labels. `id: 0` entries are placeholders.

---

## ENDPOINTS NOT YET PROBED

To capture a missing endpoint: run `saham fetch stockbit login`, open `saham fetch stockbit spy`, then navigate to the relevant Stockbit page.

| Endpoint | Priority | Notes |
|----------|----------|-------|
| `GET /valuation/company/{ticker}` | LOW | Returned 404/empty for BBCA — may require subscription |
| `GET /company-price-feed/market-time` | MEDIUM | Only captured post-market. Re-probe during pre-open (08:45–09:00 WIB, NCP locked 08:56–09:00) for live status values |

---

## NEWLY DISCOVERED ENDPOINTS (not in `stockbit_api_data.md`)

These were found in live traffic but are not documented in the main API reference yet:

| Endpoint | Description | Source |
|----------|-------------|--------|
| `GET /order-trade/broker/activity-chart` | Intraday cumulative net buy/sell value per broker per stock, minute-by-minute | `broker-scan-spy.json` |
| `GET /screener/universe` | Complete index/universe list with IDs for screener | `stockbit-spy.json` |
| `GET /screener/metric` | All screener-available financial metrics with fitem_id | `stockbit-spy.json` |
| `GET /screener/preset` | Pre-built screener template categories (Guru Screener etc.) | `stockbit-spy.json` |
| `GET /screener/favorites` | User's saved screener templates | `stockbit-spy.json` |
| `GET /screener/templates` | All available screener templates | `stockbit-spy.json` |
| `GET /screener/templates/{id}` | Run screener and get results with metric values | `stockbit-spy.json` |
| `GET /paywall/eligibility/check` | Check feature access (e.g. screener) | `stockbit-spy.json` |
