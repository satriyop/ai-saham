# Codex Recommendations: Data Accuracy, Consistency, and Feature Improvements

Date: 2026-06-19  
Scope: Repository code, active local SQLite data (`data.db`), `docs/data_sources.md`, and Stockbit API documentation (`docs/stockbit_api_data.md`, `docs/stockbit_api_end_point.md`).

This document is a recommendation pass only. No implementation was performed.

## Operating Constraints

These recommendations follow the repository contract:

- Deterministic-first behavior remains the default.
- AI output must not become the source of truth.
- Local-first persistence remains the baseline.
- Domain logic must stay free of I/O, providers, repositories, CLI, UI, and AI.
- Non-trivial refresh, cache, source-preference, and data-quality policy should live in application use cases.
- Adapters should remain thin: parse input, wire dependencies, call use cases, format output.

Layer plan for future implementation:

- Domain: add only pure value objects or policy-neutral quality classifications if needed.
- Application: own source-selection policy, data-quality auditing, freshness decisions, and feature orchestration.
- Infrastructure: own provider normalization, SQLite migrations, persisted provenance, and adapter-specific parsing.
- Adapter: expose commands and format reports only.

## Current Data Observations


Observed active `data.db` state:

| Table / Area | Observed State |
|---|---|
| `candles` | 21,420 rows, 87 tickers, date range `2025-01-30` to `2026-06-18` |
| `broker_summaries` | 36,082 rows, 86 tickers, date range `2023-01-02` to `2026-06-18` |
| `broker_summaries.source='idx'` | 36,073 rows |
| `broker_summaries.source='stockbit'` | 9 remaining legacy/degraded rows, all on `2025-06-12` |
| `foreign_flow_points.source='idx'` | 478 rows, 75 tickers |
| `foreign_flow_points.source='stockbit'` | 8,224 rows, 80 tickers |
| `broker_daily_flow.source='stockbit'` | 50,381 rows, 80 tickers, 12 broker codes |
| `ticker_notation_cache` | Empty |
| `analyst_cache` | 72 tickers |
| `seasonality_cache` | 72 tickers |
| `corp_action_cache` | 72 tickers |
| `shareholding_composition` | 68 tickers |
| `bandar_detector` | 68 tickers |
| `company_fundamentals` | 68 tickers |



## Findings

### 1. Broker Source Preference Is Inconsistent

Range reads from `broker_summaries` correctly prefer IDX by using `MIN(source)`, because IDX has true market turnover while Stockbit `broker_summaries` can be synthetic.

Single-date reads still prefer Stockbit through `ORDER BY source DESC` in `SQLiteBrokerRepository.get_broker_summary()`.

Impact:

- `saham view broker top TICKER --date DATE` can select Stockbit over IDX for a single date.
- This conflicts with the documented source policy in `docs/data_sources.md`.
- It can surface synthetic Stockbit turnover when IDX aggregate turnover is the more accurate source.

Recommendation:

- Make `get_broker_summary()` follow the same IDX-first preference as `get_broker_summaries()`.
- If named Stockbit broker details are needed, expose that explicitly through `source='stockbit'` or a dedicated named-broker query.
- Add tests proving single-date and range reads use the same default source policy.

### 2. Legacy Stockbit Broker Summary Rows Still Exist

There are 9 `broker_summaries.source='stockbit'` rows in active `data.db`.

Current cleanup removes Stockbit rows only when a matching IDX row exists for the same ticker and date. Rows without matching IDX remain.

Impact:

- These rows may still feed views or analysis for dates where IDX data is missing.
- Because Stockbit summary totals are synthetic, any FLOW% denominator based on these rows is less reliable.

Recommendation:

- Add a deterministic data-audit report that identifies degraded source rows.
- Classify remaining Stockbit summary rows as `DEGRADED_SUMMARY_SOURCE` unless explicitly used for named-broker display.
- Consider moving Stockbit top-broker rows into a dedicated table or treating them as broker-attribution context rather than aggregate flow truth.

### 3. Candle Freshness Is Uneven

Some tickers have latest candles behind the active latest trading date. Examples observed include tickers stale at `2026-06-12`, `2026-06-15`, and `2026-06-17` while the latest cached date is `2026-06-18`.

Impact:

- Ranking commands can compare fresh and stale tickers as if they were equally current.
- Swing and accumulation signals can become misleading when price/indicator state lags broker-flow state.

Recommendation:

- Add freshness gates to ranking workflows.
- Default behavior should show stale tickers with a warning or exclude them from top-ranked output unless `--include-stale` is passed.
- Candidate output should include a compact freshness field for candles, IDX broker summaries, Stockbit broker daily flow, and enrichment caches.

### 4. Broker Summary Rows Need Quality Classification

A query found 774 `broker_summaries` rows with non-positive `total_value` or invalid total/lot values.

These may represent legitimate no-trade, suspended, or special cases. They should not be blindly deleted, but they should not silently participate in denominator-sensitive calculations.

Impact:

- FLOW% can be distorted if `total_value <= 0`.
- Net-flow streaks can count days that should be considered non-trading or invalid.
- Suspended or illiquid tickers can receive noisy scores.

Recommendation:

- Add deterministic row quality labels:
  - `OK`
  - `NO_TRADE`
  - `SUSPENDED_OR_EMPTY`
  - `MISSING_DENOMINATOR`
  - `PROVIDER_ANOMALY`
- Application use cases should skip or down-rank rows with unsafe denominators.
- Display the count of excluded rows in analysis output.

### 5. Candle Provider Units Are Not Persisted

`docs/data_sources.md` notes that IDX candle volume is stored in lots, while Yahoo volume is raw shares. The current `candles` table does not persist source, volume unit, or adjustment policy.

Impact:

- Volume-sensitive indicators can be inconsistent if Yahoo and IDX candles coexist or are overwritten without provenance.
- Reconciliation between adjusted Yahoo data and raw IDX data is difficult.

Recommendation:

- Add candle provenance fields:
  - `source`
  - `volume_unit`
  - `price_adjustment_policy`
  - `fetched_at`
  - `schema_version`
- Normalize volume before domain/application calculations.
- Add an audit that flags mixed provider history per ticker.

### 6. Stockbit Flow Data Needs Stronger Labeling

`foreign_flow_points.source='stockbit'` represents an institutional-desk proxy based on selected broker codes, not total IDX all-foreign flow.

This is documented, but feature output should make the distinction hard to miss.

Impact:

- Users may interpret Stockbit institutional proxy magnitude as exact total foreign flow.
- Direction may be useful, but magnitude can undercount or diverge on mixed-flow days.

Recommendation:

- Rename display labels to “institutional desk proxy” wherever Stockbit `foreign_flow_points` is shown.
- Use IDX `broker_summaries` for all-foreign aggregate truth.
- Use Stockbit `broker_daily_flow` and `foreign_flow_points.avg_price` for attribution and VWAP context.

### 7. Enrichment Coverage Is Uneven

Several enrichment tables have partial coverage, and `ticker_notation_cache` is empty.

Impact:

- Some candidates include analyst/fundamental/bandar/shareholding context while others do not.
- Missing enrichment can be mistaken for neutral evidence.

Recommendation:

- Add an enrichment completeness score per ticker.
- Display missing enrichment as `missing`, not neutral.
- Do not let missing enrichment silently reduce or improve the trade score unless the scoring policy explicitly says so.
- Make `ticker_notation_cache` population failure visible in the post-fetch database status.

### 8. Adapter Thinness Drift Exists In Fetch Market

`src/adapters/cli/fetch_market_commands.py` currently owns non-trivial provider detection, freshness tolerance, and enrichment cache orchestration.

Impact:

- Cache and refresh policy are harder to test outside the CLI.
- The adapter contains behavior that the repository contract says should live in application use cases.

Recommendation:

- Move provider resolution policy into an application service or use case.
- Move enrichment refresh orchestration into a `RefreshStockbitEnrichmentUseCase`.
- Keep the CLI responsible only for parsing options, wiring concrete providers/repositories, invoking use cases, and formatting output.

## Recommended Improvements By Priority

### Priority 1: Data Accuracy And Consistency

1. Unify broker source preference.
   - Fix single-date broker summary default to IDX-first.
   - Add explicit source selection for Stockbit named-broker context.

2. Add `DataQualityAuditUseCase`.
   - Audit candles, broker summaries, foreign flow points, broker daily flow, and enrichment caches.
   - Report stale data, bad denominators, source conflicts, missing provider coverage, and mixed candle units.
   - Keep it deterministic and offline.

3. Add row quality classification for broker summaries.
   - Prevent invalid total turnover rows from contaminating FLOW%.
   - Make excluded row counts visible in reports.

4. Persist candle provenance.
   - Track provider and units to prevent Yahoo/IDX volume confusion.
   - Normalize before analysis.

### Priority 2: Feature Quality

1. Add data-confidence scoring to `screen accum` and `analyze swing`.
   - Inputs:
     - candle freshness
     - broker summary freshness
     - Stockbit daily broker flow availability
     - enrichment completeness
     - invalid-row exclusions
   - Output should be visible but separate from the trade score.

2. Improve freshness-aware ranking.
   - Fresh candidates rank normally.
   - Stale candidates display warnings or require `--include-stale`.
   - Missing core data should exclude candidates from rankings.

3. Reconcile IDX and Stockbit signals.
   - Add a report comparing IDX all-foreign direction vs Stockbit institutional-desk proxy direction.
   - Track direction match rate and divergence days.
   - Use this to calibrate confidence, not to override deterministic rules.

4. Improve enrichment interpretation.
   - Treat analyst, seasonality, insider, fundamentals, shareholding, and bandar as context.
   - Avoid over-weighting proprietary or incomplete enrichment.
   - Add “missing context” display where a cache is absent.

### Priority 3: Stockbit Feature Expansion

These should remain optional Stockbit-backed enhancements, never mandatory foundations.

1. Running trade chart
   - Use for intraday volume profile and opening confirmation.
   - Improve post-open confirmation by comparing first trade, orderbook `lastprice`, and first intraday bucket.

2. Broker distribution
   - Add top-5 broker concentration and buy/sell dominance.
   - Use as context for accumulation quality.

3. Historical price summary
   - Use as a cross-check against Yahoo/IDX OHLCV.
   - Detect corporate-action adjustment drift.

4. Analyst rating detail
   - Track consensus changes over time, not only current consensus.
   - Highlight recent upgrades/downgrades as context.

5. Earnings and valuation endpoints
   - Add quarterly EPS recap, valuation metrics, and earnings change context.
   - Keep these as read-only contextual signals.

## Suggested Implementation Tasks

### Task A: Broker Summary Source Policy Cleanup

Task type: Bugfix  
Priority: High  
AI usage: No AI involved  
Risk profiles affected: All profiles that consume broker summaries

Layer plan:

- Domain: not touched.
- Application: not touched unless a source-policy helper is introduced.
- Infrastructure: update repository read preference and tests.
- Adapter: not touched.

Acceptance criteria:

- `get_broker_summary()` defaults to IDX-first when multiple sources exist.
- Stockbit can still be requested explicitly when named-broker context is needed.
- Tests cover IDX-only, Stockbit-only, and both-source cases.

### Task B: Data Quality Audit Command

Task type: Feature  
Priority: High  
AI usage: No AI involved  
Risk profiles affected: None directly; improves all analysis reliability

Layer plan:

- Domain: optional pure quality enum/value object.
- Application: new audit use case with deterministic checks.
- Infrastructure: SQLite readers for audit inputs.
- Adapter: CLI command to display audit report.

Acceptance criteria:

- Runs offline.
- Reports stale candles, stale broker data, source conflicts, bad denominators, missing enrichment, and mixed provider/unit risk.
- Does not fetch network data.

### Task C: Candle Provenance Migration

Task type: Data consistency improvement  
Priority: High  
AI usage: No AI involved  
Risk profiles affected: Any feature using volume-sensitive calculations

Layer plan:

- Domain: not touched unless candle metadata becomes a domain value.
- Application: normalize or validate units before analysis.
- Infrastructure: schema migration and provider write changes.
- Adapter: no policy; only display provenance if requested.

Acceptance criteria:

- Candle rows include provider/source and volume unit.
- Existing rows are migrated with conservative defaults.
- Mixed-source histories are auditable.

### Task D: Freshness-Aware Candidate Ranking

Task type: Feature refinement  
Priority: Medium  
AI usage: No AI involved  
Risk profiles affected: Conservative, Balanced, Aggressive

Layer plan:

- Domain: not touched.
- Application: add freshness/confidence calculation.
- Infrastructure: repository date range reads as needed.
- Adapter: display freshness/confidence.

Acceptance criteria:

- Stale core data is visible.
- Ranking behavior is deterministic.
- Conservative profile does not treat stale data as equally reliable.

## Final Recommendation

The most important next step is not adding more signals. It is making the existing signals auditable and consistently sourced.

Recommended order:

1. Fix broker summary source preference consistency.
2. Add deterministic data-quality audit.
3. Add candle provenance and unit normalization.
4. Add freshness/confidence display to ranking and analysis commands.
5. Expand Stockbit-derived feature context only after the above quality gates are in place.

