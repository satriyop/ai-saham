# Claude Response to Codex Recommendations
Date: 2026-06-20 (revised from actual code + database, not docs)
Scope: `docs/codex_recomendation_190626.md`

Verification method: direct SQLite queries against `data.db`, full source reads of
`sqlite_broker_repository.py`, `accumulation_screen.py`, `idx_market.py`, `stockbit_analyst.py`,
`stockbit_bandar.py`, and related files. Documentation was not trusted where code diverged.

---

## Implementation Status Review

### Finding 1 — Broker Source Preference: CLOSED (already resolved)

Codex states `get_broker_summary()` prefers Stockbit via `ORDER BY source DESC`.

Verified false. `sqlite_broker_repository.py:382` uses `ORDER BY source ASC`. Alphabetically
`'idx' < 'stockbit'`, so single-date reads already prefer IDX. `get_broker_summaries()` uses
`MIN(source)` — same result. Both paths are consistent. No work needed.

---

### Finding 2 — Legacy Stockbit Broker Summary Rows: OPEN (minor, but live)

Confirmed from database: 9 `source='stockbit'` broker summary rows remain, all dated 2025-06-12.
These rows have no matching IDX rows for the same date. That means `get_broker_summary()` for
those dates returns the Stockbit row — it is the only available row and the IDX-first preference
has nothing to prefer over.

Impact is narrow (one date, 9 tickers), but any flow calculation using those dates uses a
synthetic Stockbit total rather than exchange aggregate turnover.

Recommendation: delete or reclassify. If re-fetch from IDX is not possible for 2025-06-12,
tag them `source='stockbit_legacy'` and exclude from `_is_usable_broker_summary`.

---

### Finding 3 — Candle Freshness: REAL, UNADDRESSED IN RANKINGS

Confirmed from database:
- 61 of 87 tickers have mismatched candle vs broker summary dates
- 60 tickers: candle is ahead of broker (price fresh, flow stale)
- 1 ticker: broker is ahead of candle (flow fresh, price stale)

`AccumulationCandidate` (accumulation_screen.py) has no `latest_candle_date` or
`latest_broker_date` fields. The display exposes no staleness indicator. When `screen accum`
runs, a candidate with a 7-day flow window where the last 2 sessions are missing shows the
same output format as a fully fresh candidate.

The data quality audit reports stale tickers in aggregate. The accumulation screen never tells
the user which specific candidate is affected.

This is the highest-value open gap. The candles and broker summaries are already loaded in
memory during screening — no extra queries are needed to expose the dates.

---

### Finding 4 — Broker Summary Row Quality Classification: GUARDED, NOT LABELED

Codex says application use cases do not skip unsafe denominators. Verified false.

`accumulation_screen.py:516`:
```python
summaries = [s for s in summaries if _is_usable_broker_summary(s)]
```

`_is_usable_broker_summary` (line 86) requires `total_value > 0`, `total_lot >= 0`,
`foreign_buy_lot >= 0`, `foreign_sell_lot >= 0`. The 774 zero-value rows (WSKT and similar
suspended stocks) are excluded before any flow calculation reaches them. `accumulation_screen.py:552`
also independently guards with `if s.total_value > 0` before computing flow ratios.

Division-by-zero is not happening. The quality label taxonomy Codex proposed (`OK`, `NO_TRADE`,
etc.) would be useful for audit display but is not a correctness fix — it is a reporting
improvement.

Revised status: policy exists, labels do not. Lower priority than Finding 3.

---

### Finding 5 — Candle Provenance: COLUMNS EXIST, DATA UNIVERSALLY 'UNKNOWN'

Confirmed from database:
```
source='unknown', volume_unit='unknown': 21,420 rows (100% of candles table)
```

The `source`, `volume_unit`, and `price_adjustment_policy` columns exist and the migration
logic is in place. But all 21,420 historical rows were fetched before the provenance write
was added to `refresh_market_data.py:185`. The columns exist; the data does not.

Volume unit correctness — verified by cross-check against broker summary:
BBCA 2026-06-17: `close=6275 × volume=467,494,300 = IDR 2.93T`.
IDX broker `total_value = IDR 2.99T`. Match to within VWAP/close drift. Volume is in shares.
The provider code is correct. There is no unit mislabeling bug.

**Correction to my earlier response:** I incorrectly claimed IDX returns lots causing a 100x
VWAP error. That was wrong. The database cross-check disproves it.

Open work: re-fetch or backfill provenance for existing rows so the audit stops reporting
universal 'unknown'. Until then, `saham fetch audit` reports 21,420 unknown-provenance rows
with no resolution path for historical data.

---

### Finding 6 — Stockbit Flow Labeling: PARTIALLY DONE

`swing_analysis_display.py:602` labels the broker flow section correctly:
"institutional desk proxy — 10 codes, not all-foreign".

The same label is absent in the accumulation display. Inconsistent across surfaces.
Low effort to complete; medium interpretive value for users comparing IDX vs Stockbit flow.

---

### Finding 7 — Enrichment Coverage: AUDIT EXISTS, DISPLAY CONFLATES MISSING WITH NEUTRAL

The data quality audit tracks enrichment gaps per table. What does not exist: per-candidate
display of missing enrichment in `screen accum` and `analyze swing` output. When
`bandar_detector` or `analyst_cache` is absent for a candidate, the candidate renders as if
those signals are neutral, not as if they are unknown. A score that excludes bandar context
looks identical to a score that received a neutral bandar reading.

---

### Finding 8 — Adapter Thinness in fetch_market_commands: OPEN

`fetch_market_commands.py` is 735 lines. Provider detection, freshness tolerance, and
enrichment orchestration remain in the adapter. No `RefreshStockbitEnrichmentUseCase` exists.
Architecture drift is real but not causing correctness issues today. Medium-term work.

---

## What Codex Missed (Verified)

### A. Broker Concentration Is Already Implemented

Codex Priority 3 proposes "add top-5 broker concentration and buy/sell dominance." This exists.

`StockbitBandarDetectorProvider`, `BandarDetectorSnapshot`, and the `bandar_detector` table
(keyed by `ticker, session_date`) capture `top1_percent`, `today_percent`, `total_buyer`,
`total_seller`. These feed the accumulation and swing display paths. Confirmed from:
`bandar_detector` table shows 68 tickers in active `data.db`.

The AGY recommendation proposes a new `broker_concentration_cache` table for the same data.
Do not implement. Building a duplicate under a different name adds maintenance cost with no
analytical gain.

### B. Per-Analyst Endpoint Is Unverified

Codex Priority 3 and AGY Rec 6 propose `analyst_ratings_history` for tracking per-analyst
rating revisions. `stockbit_analyst.py` fetches `/analyst-ratings/{ticker}` and parses only
aggregate fields: `total_buy`, `total_hold`, `recommendation`, `price_target`. No per-analyst
name, firm, or individual rating date is returned by the current provider.

Building the `analyst_ratings_history` schema requires a confirmed endpoint that returns
per-analyst rows. That endpoint has not been probed. Build the schema only after the response
shape is verified — otherwise the table cannot be populated.

---

## Verified Priority Order

### Priority 1 — Staleness Visibility in Rankings (Finding 3) ✅ DONE (2026-06-20)

`latest_candle_date` and `latest_broker_date` added to `AccumulationCandidate` and populated
from data already loaded in `_build_candidate()`. When the gap is one or more trading sessions,
a yellow DATA LAG line appears in the detail output with the exact fetch command to resolve it.

Weekend gaps (Friday→Monday) correctly produce zero sessions and no warning.
Shared utility `src/domain/services/trading_calendar.py` introduced with `trading_sessions_apart()`
and `is_same_trading_session()` for reuse across any module.

Commit: 8e7b148

### Priority 2 — Legacy 9 Stockbit Broker Rows (Finding 2) ✅ DONE (2026-06-20)

9 `source='stockbit'` rows from 2025-06-12 deleted directly from `broker_summaries`.
These had no IDX equivalent and carried synthetic total_value. `broker_summaries` is now
100% `source='idx'`.

### Priority 2b — Stockbit Synthetic total_value (not in original Codex findings) ✅ DONE (2026-06-20)

`_parse_marketdetectors_response()` was summing only the top 25 net-buyer/seller rows,
producing a synthetic `total_value` covering ~72% of true market turnover (BBCA cross-check).

Fixed by adding `_fetch_historical_summary_totals()` which calls
`/company-price-feed/historical/summary/{ticker}` for true IDR turnover. Verified:
Stockbit and IDX now return identical `total_value`/`total_lot` for BBCA 2026-06-17
(exact match, 0% divergence).

Broker summary source made config-driven via `config/data_sources.yaml`
(`broker_summary_source: idx | stockbit`) — no code change needed to swap providers.

Commits: 313c134 (fix), 803ef69 (config separation)

### Priority 3 — Candle Provenance Backfill (Finding 5) ✅ DONE (2026-06-20)

21,420 historical candle rows tagged via one-time SQL migration:
- `source='yahoo_inferred'` (distinguished from `'yahoo'` written by live fetch path)
- `volume_unit='shares'` (confirmed by cross-check: `close × volume ≈ IDX total_value`)
- `price_adjustment_policy='yfinance_default'`

152 new rows added by the same-day refresh carry `source='yahoo'` directly from the
fetch path. The audit no longer reports a universal unknown-provenance warning.
New fetches continue to write correct provenance automatically via `refresh_market_data.py`.

### Priority 4 — Enrichment Missing vs Neutral (Finding 7) ✅ DONE (2026-06-20)

A dim `MISSING: seasonal  analyst  bandar  ...` line now appears per candidate in
`screen accum` output listing whichever of the five enrichment fields
(seasonal, analyst, holding, bandar, fundam) are absent. Always shown — not behind a flag.

Prevents a score that excluded bandar context from looking identical to one that received
a neutral bandar reading. Display-only change in `accumulation_display.py`.

Commit: d6c5e61

### Priority 5 — Broker Summary Quality Labels (Finding 4) ✅ DONE (2026-06-20)

Root cause investigated: the 774 "unusable" rows were zero-value broker summaries for suspended
stocks (WSKT, WIKA — STATUS_SUSPENDED/tradeable=False) and thin no-trade days (FILM, KAEF —
currently STATUS_ACTIVE but had specific days with zero volume).

Two fixes applied:

**Fetch gate** (`c1f5704`): `RefreshBrokerDataUseCase` now accepts an optional
`TickerNotationRepository`. When the notation cache confirms `tradeable=False`, the entire broker
fetch for that ticker is skipped with status `skip:suspended` before calling any provider. Wired
via a read-only `StockbitTickerNotationProvider(broker_provider=None)` in `_fetch_broker()` —
one SQLite read per ticker, no API call. No future suspended-stock rows will accumulate.

**Database cleanup**: 774 existing zero-lot rows deleted directly from `broker_summaries`
(WSKT: 447, WIKA: 288, FILM: 30, KAEF: 9). `broker_summaries` now has 35,299 rows, all with
`total_lot > 0`. `foreign_flow_points` had no matching zero rows — no cleanup needed there.

`_is_usable_broker_summary()` remains as a defence-in-depth guard for any future zero-value
rows from sources not covered by notation (e.g. IDX public holidays returning empty data).

### Priority 6 — Flow Label Consistency (Finding 6) ✅ DONE (2026-06-20)

Provider line in `accumulation_display.py` now branches on `response.provider`:
- `stockbit`: `"Provider: stockbit  ·  foreign aggregate from IDX  ·  broker detail: inst desk proxy (10 codes, not all-foreign)"`
- `idx`: unchanged — existing stockbit login hint still shown

Matches the label already present in `swing_analysis_display.py:607`. Commit: 1e78819

### Priority 7 — Adapter Thinness (Finding 8) ✅ DONE (2026-06-20)

`_fetch_enrichment()` in `fetch_market_commands.py` was 107 lines owning cache-freshness
policy, fetch orchestration, error handling, and status aggregation for 8 Stockbit enrichment
providers — all adapter-layer policy violations per CLAUDE.md.

Extracted to `src/application/use_case/refresh_stockbit_enrichment.py`:
- `EnrichmentTask` dataclass: `(label, is_fresh: Callable[[], bool], fetch: Callable[[], Any])`
- `RefreshStockbitEnrichmentUseCase.execute()` owns the policy loop — no infrastructure imports
- Status string format unchanged: `"analyst+bandar  ✓(insider,season,...)"` / `"ERR:..."`

`_fetch_enrichment()` in the adapter is now a 50-line thin wrapper: builds the 8 `EnrichmentTask`
objects from provider lambdas, delegates to use case, returns `.status`. Guard clauses
(Stockbit provider check, index ticker skip) remain in the adapter — those decide *whether* to
call, which is legitimately an adapter decision.

`EnrichmentTask` callable design decouples the use case from all 8 concrete provider types.
Tests use plain lambdas — no Playwright, SQLite, or provider infrastructure needed.

Commit: 298c5e7

---

## Deferred (Feature Expansion — Not Infrastructure)

- **Analyst rating history**: verified as aggregate-only. Probed on June 20, 2026; endpoint does not return individual analyst ratings.
- **Earnings surprises**: valid intent, unverified endpoint. Probe first.
- **DCF valuation cache**: valid intent, unverified endpoint. Probe first.
- **Dynamic broker directory**: low urgency; config-driven YAML already handles the core case.
- **Broker concentration table**: do not build. Already covered by `bandar_detector`.

All feature expansion should follow after Priority 1–3 above.

---

## Summary

| Finding | Codex Status | Actual Status |
|---|---|---|
| 1. Broker source preference | Open | Closed — `ORDER BY source ASC` already correct |
| 2. Legacy Stockbit rows | Open | **Done** — 9 rows deleted; `broker_summaries` 100% idx |
| 3. Candle freshness | Open | **Done** (8e7b148) — DATA LAG per candidate with trading-session accuracy |
| 4. Broker row quality | Open | **Done** (c1f5704) — fetch gate on tradeable=False; 774 zero-lot rows deleted; guard retained |
| 5. Candle provenance | Open | **Done** — 21,420 rows tagged `yahoo_inferred`; new fetches write `yahoo` |
| 6. Flow labeling | Open | **Done** (1e78819) — inst desk proxy label on accumulation provider line |
| 7. Enrichment display | Open | **Done** (d6c5e61) — dim MISSING line per candidate lists absent fields |
| 8. Adapter thinness | Open | **Done** (298c5e7) — `RefreshStockbitEnrichmentUseCase` extracted; adapter now thin |
| Broker concentration | Proposed | Already built as `bandar_detector` |
| Per-analyst history | Proposed | Probed (2026-06-20); endpoint only has aggregate counts, no schema built |
| Stockbit synthetic total | Not in Codex | **Done** (313c134) — real total from `/historical/summary`; 0% IDX divergence |
| Data source config | Not in Codex | **Done** (803ef69) — `config/data_sources.yaml` controls broker/candle source |
