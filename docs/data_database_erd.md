# Database ERD — data.db

```mermaid
erDiagram
    candles {
        ticker TEXT PK  "Stock code"
        date TEXT PK    "Trading date"
        open TEXT      "Opening price"
        high TEXT      "High price"
        low TEXT       "Low price"
        close TEXT     "Closing price"
        volume INT     "Volume in shares"
    }

    broker_summaries {
        ticker TEXT PK          "Stock code"
        date TEXT PK            "Trading date"
        source TEXT PK          "'idx' | 'stockbit'"
        foreign_buy_value TEXT  "Foreign buy IDR"
        foreign_sell_value TEXT "Foreign sell IDR"
        foreign_buy_lot INT     "Foreign buy lots"
        foreign_sell_lot INT    "Foreign sell lots"
        total_value TEXT        "Total trade value"
        total_lot INT           "Total lots"
        top_buyers_json TEXT    "Top 10 buyers JSON"
        top_sellers_json TEXT   "Top 10 sellers JSON"
    }

    broker_daily_flow {
        ticker TEXT PK       "Stock code"
        date TEXT PK         "Trading date"
        broker_code TEXT PK  "Broker ID"
        source TEXT PK       "'stockbit'"
        broker_name TEXT     "Broker name"
        buy_lot INT          "Buy lots"
        sell_lot INT         "Sell lots"
        net_lot INT          "Net lots"
        buy_value TEXT       "Buy value IDR"
        sell_value TEXT      "Sell value IDR"
        net_value TEXT       "Net value IDR"
        avg_price TEXT       "Average price"
        buy_pct REAL         "% of total buy"
        sell_pct REAL        "% of total sell"
    }

    foreign_flow_points {
        ticker TEXT PK    "Stock code"
        date TEXT PK      "Trading date"
        source TEXT PK    "Data source"
        net_val TEXT      "Net foreign value IDR"
        net_lot INT       "Net foreign lots"
        avg_price TEXT    "VWAP of foreign buys"
    }

    foreign_flow_snapshots {
        ticker TEXT PK          "Stock code"
        snapshot_date TEXT PK   "Snapshot date"
        period_days INT PK     "Lookback window"
        source TEXT PK          "Data source"
        net_val TEXT            "Net value in period"
        net_lot INT             "Net lots in period"
    }

    iev_snapshots {
        date TEXT PK    "Date"
        ticker TEXT PK  "Stock code"
        iev INT         "Indicative equilibrium volume"
        rank INT        "IEV rank for the day"
        iep INT         "Indicative equilibrium price"
    }

    sentiment_logs {
        id INT PK         "Auto-increment"
        date TEXT         "Date"
        ticker TEXT       "Stock code"
        sentiment TEXT    "Label: BULLISH | NEUTRAL | BEARISH"
        catalyst TEXT     "Catalyst type"
        score REAL        "Confidence score 0-1"
    }

    sentiment_audits {
        log_id INT PK     "FK → sentiment_logs.id"
        days_after INT PK "Days since log"
        price_delta_pct REAL "Price change %"
        audited_at TEXT   "Audit timestamp"
    }

    candles ||--o{ broker_summaries : "(ticker, date)"
    candles ||--o{ broker_daily_flow : "(ticker, date)"
    candles ||--o{ foreign_flow_points : "(ticker, date)"
    candles ||--o{ foreign_flow_snapshots : "(ticker, date)"
    candles ||--o{ iev_snapshots : "(ticker, date)"
    sentiment_logs ||--o{ sentiment_audits : "id → log_id"
```

## Table Relationships

| # | Table | Purpose | Key | Rows Are |
|---|-------|---------|-----|----------|
| 1 | **candles** | Daily OHLCV prices | `(ticker, date)` | One row per stock per trading day |
| 2 | **broker_summaries** | Aggregate foreign buy/sell per stock per day | `(ticker, date, source)` | One row per stock per day per source (idx + stockbit) |
| 3 | **broker_daily_flow** | Per-broker breakdown (granular) | `(ticker, date, broker_code, source)` | One row per broker per stock per day |
| 4 | **foreign_flow_points** | Time-series net foreign flow | `(ticker, date, source)` | One row per stock per day, used by VWAP / accum |
| 5 | **foreign_flow_snapshots** | Pre-computed period aggregates | `(ticker, snapshot_date, period_days, source)` | Cached result of N-day lookback |
| 6 | **iev_snapshots** | Pre-open IEV rankings | `(date, ticker)` | One row per stock per pre-open session |
| 7 | **sentiment_logs** | AI sentiment classifications | `id` | One row per classification event |
| 8 | **sentiment_audits** | Price outcome after sentiment | `(log_id, days_after)` | One row per audit point per log |

## Entity Groupings

```
MARKET DATA                          BROKER/FLOW DATA
┌──────────┐                         ┌───────────────────┐
│ candles  │────(ticker,date)───────▶│ broker_summaries  │
│ OHLCV    │                         │ aggregate foreign  │
└──────────┘                         └───────────────────┘
     │                                      │
     │(ticker,date)                    (ticker,date)
     ▼                                      ▼
┌──────────┐                         ┌───────────────────────┐
│ iev_     │                         │ broker_daily_flow     │
│ snapshots│                         │ per-broker (granular) │
└──────────┘                         └───────────────────────┘
                                              │
                                         (ticker,date)
                                              ▼
                                     ┌───────────────────────┐
                                     │ foreign_flow_points   │
                                     │ net flow time-series  │
                                     └───────────────────────┘
                                              │
                                         (ticker,date)
                                              ▼
                                     ┌──────────────────────────┐
                                     │ foreign_flow_snapshots    │
                                     │ pre-computed aggregates   │
                                     └──────────────────────────┘

SENTIMENT
┌────────────────┐
│ sentiment_logs │───(id)───▶│ sentiment_audits │
└────────────────┘           └──────────────────┘
```

## Notes

- No formal FK constraints exist (SQLite, app-enforced referential integrity).
- `(ticker, date)` is the universal join key across all market data tables.
- `broker_daily_flow` stores per-broker data from Stockbit; `broker_summaries` stores aggregate foreign flow from both IDX and Stockbit.
- `foreign_flow_points` is the canonical time-series for net foreign flow, computed from `broker_summaries`.
- `foreign_flow_snapshots` is a cache layer — pre-computed aggregates for faster swing screening queries.
