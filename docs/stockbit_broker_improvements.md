# Broker Data Accuracy: Findings & Improvements

_Last updated: 2026-06-14 · Research conducted on data.db with 78 tickers_

## Overview

The system stores three tiers of broker data:

| Table | Rows | Source(s) | Granularity |
|---|---|---|---|
| `broker_summaries` | 35,829 (35,595 idx + 234 stockbit) | IDX public API + Stockbit | 1 row per ticker/date |
| `foreign_flow_points` | 7,878 | Stockbit only | 1 row per ticker/date |
| `broker_daily_flow` | 43,816+ | Stockbit only | 1 row per ticker/date/broker_code |

---

## Research Findings

### Finding 1 — broker_summaries source preference was inverted (BUG — fixed Phase 1)

`get_broker_summaries()` with `source=None` was using `MAX(source)` to pick a preferred row
when both IDX and Stockbit data existed for the same ticker/date:

```sql
SELECT ticker, date, MAX(source) AS best_src  -- 'stockbit' > 'idx' alphabetically
```

**Effect**: Stockbit-sourced rows were always preferred over IDX-sourced rows.

**Why this was wrong**: Stockbit broker_summaries are built client-side by summing only the
top-10 net buyers and top-10 net sellers returned by the `/marketdetectors/{ticker}` API.
The `total_value` field is a synthetic sum of those rows — NOT total market turnover.

**Measured gap for BBCA on 2026-06-12**:
- Stockbit `total_value`: ~1.78T IDR (sum of net-buyer buys + net-seller sells)
- True IDX `total_value`: ~2.46T IDR (from IDX `Value` field)
- **Coverage: ~72% — FLOW% denominator was 28% too small**

**All 10 display/analysis call sites** were affected (none pass `source=` argument):
- `accumulation_screen.py:248` — FLOW%, net days, avg_flow_ratio
- `swing_commands.py:604` — FlowDetail (FLOW DETAIL section)
- `swing_commands.py:841` — broker detail fallback
- `accumulation_commands.py:168` — screen broker quality
- `market_regime.py:243` — foreign flow breadth
- `pre_open_screen.py:417` — pre-open scoring
- `intraday_backtest.py:275` — backtest context
- `accumulation_audit.py:504` — audit classification
- `broker_commands.py:379` — `saham view broker`
- `fetch_broker_data.py:174` — `GetBrokerDataUseCase`

**Fix applied**: Changed `MAX(source)` → `MIN(source)` in `sqlite_broker_repository.py`.
`'idx' < 'stockbit'` alphabetically — IDX now wins. IDX `total_value` is true market turnover.

---

### Finding 2 — Stockbit broker_summaries were being written on every update (BUG — fixed Phase 2)

`_fetch_broker()` in `update_commands.py` ran `FetchBrokerDataUseCase(broker_provider, repo)`.
When the configured provider was Stockbit, broker_summaries were persisted with `source='stockbit'`.
This created 234 bad rows in the DB and would create more on every future Stockbit update.

**IDX broker_summaries are always accurate**:
- `total_value` = IDX `Value` field (true daily turnover) ✅
- `foreign_net_value` = true all-foreign aggregate (IDX `ForeignBuy`/`ForeignSell` exact share counts) ✅
- Values are `shares × close_price` — ±2–3% off from intraday VWAP (acceptable)

**Fix applied**: `_fetch_broker()` now always runs `FetchBrokerDataUseCase` against
`IdxBrokerDataProvider()` regardless of which broker provider is configured for the session.
Stockbit is only used for `broker_daily_flow` and `foreign_flow_points`.

---

### Finding 3 — foreign_flow_points.net_val is institutional desk proxy, not all-foreign (fixed Phase 3)

`foreign_flow_points` is populated via `broker_provider.fetch_foreign_flow_history()` which queries
Stockbit's historical endpoint using `_INSTITUTIONAL_PROXY_CODES` (formerly `_FOREIGN_BROKER_CODES`),
10 specific broker codes:

```
AK, ZP, YP, BK, YU, CP, KZ, HD, RX, DR
```

YP (Indo Premier / Mirae Asset) is a domestic broker that mirrors institutional foreign-style
orders — not a foreign entity.

**Consequence**: `net_val` represents the 10-code institutional desk aggregate, not all IDX
foreign investors. For true all-foreign aggregate, use `broker_summaries.foreign_net_value`
(IDX-sourced).

**Cross-validation vs IDX all-foreign (BBCA)**:

| Date | institutional net_val (10 codes) | Direction match vs IDX all-foreign |
|---|---:|---|
| 2026-06-12 | +247B | ✅ |
| 2026-06-11 | +379B | ✅ |
| 2026-06-09 | -829B | ✅ |
| 2026-06-10 | +54B | ⚠️ near-zero day: 10-code can diverge from true aggregate |

Directional signal is reliable 90%+ of the time. Magnitude undercounts on days when small
foreign brokers are active.

**Where `avg_price` IS accurate**: Within ±3% of close (confirmed on BBCA over 10 sessions),
no systematic bias. Used for VWAP% calculation — appropriate and kept as-is.

**Fix applied**: Renamed `_FOREIGN_BROKER_CODES` → `_INSTITUTIONAL_PROXY_CODES` in
`playwright_stockbit.py`. Updated FLOW DETAIL label in `swing_commands.py` to "institutional
desk" to distinguish from the true all-foreign signal in the ACCUMULATION section.

---

## Data Source Summary (after all fixes)

| Signal | Source | Accuracy |
|---|---|---|
| `FLOW%` (foreign vs total market) | `broker_summaries.foreign_net_value / total_value` (IDX) | ✅ True turnover |
| Net foreign days (2/7) | `broker_summaries.is_foreign_accumulating` (IDX) | ✅ True all-foreign |
| VWAP% discount | `foreign_flow_points.avg_price` (Stockbit) | ✅ ±3% of close |
| FLOW DETAIL net_val | `foreign_flow_points.net_val` (Stockbit, 10 codes) | ⚠️ Institutional desk proxy |
| Named broker sessions | `broker_daily_flow` (Stockbit, per-day per-broker) | ✅ Real daily data |
| Institutional flag | `broker_daily_flow` (Stockbit, per-day per-broker) | ✅ Real daily data |

---

## Current Data State (post-fix, 2026-06-14)

```
broker_summaries:    IDX rows only (234 bad Stockbit rows cleaned up in migration)
foreign_flow_points: 7,878 Stockbit rows (institutional desk proxy — avg_price accurate)
broker_daily_flow:   43,816+ rows, 78 tickers, 12 codes, 2026-03-16 → 2026-06-12
```
