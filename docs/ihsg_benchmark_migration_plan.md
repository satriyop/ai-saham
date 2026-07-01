# IHSG Benchmark Migration Plan

Persistent tracker for migrating the app benchmark from Yahoo-specific `^JKSE`
to market-native `IHSG`, with Stockbit historical summary as the authoritative
source for IHSG daily OHLCV.

Last updated: 2026-07-01
Current phase: Phase 6 - Data quality audit warnings pending

## Objective

Use `IHSG` as the canonical internal benchmark ticker and treat `^JKSE` only as
a provider/user-input alias for Yahoo compatibility.

## Non-Goals

- Do not change domain candle semantics.
- Do not introduce AI-based analysis.
- Do not silently mix Yahoo `^JKSE` volume with Stockbit `IHSG` volume.
- Do not keep provider-specific ticker notation as canonical application state.

## Layer Plan

- Domain: not touched unless tests reveal hardcoded benchmark assumptions.
- Application: move benchmark defaults and fetch policy to canonical `IHSG`.
- Infrastructure: map canonical `IHSG` to provider-specific symbols.
- Adapter: expose compatibility aliases and display clear migration status only.

## Status Legend

- Not started: no implementation work done.
- In progress: code or data migration work active.
- Blocked: requires user decision or external session/auth access.
- Done: implemented and verified against acceptance checks.

## Phase 0 - Decision and Scope

Status: Done

Decision:
- Canonical benchmark ticker will be `IHSG`.
- Stockbit historical summary will be preferred for canonical `IHSG` daily OHLCV.
- Yahoo will remain available through provider alias `IHSG -> ^JKSE`.
- Backwards-compatible user input alias `^JKSE -> IHSG` should be supported.

Evidence:
- `emitten/{ticker}/info` provides current quote fields, not historical candles.
- `company-price-feed/historical/summary/IHSG` provides daily OHLCV, value,
  frequency, and foreign flow.
- Stockbit historical `volume` is lots; existing provider converts lots to shares.
- Yahoo `^JKSE` volume is unreliable for benchmark volume and returns 0 for some
  completed/current rows.

Acceptance checks:
- Decision recorded in this tracker.
- No code implementation started before phase plan is recorded.

## Phase 1 - Alias Contract and Tests

Status: Done

Goal:
- Define deterministic ticker alias behavior before changing fetch/persistence.

Planned changes:
- Add or reuse an infrastructure-level symbol mapper:
  - canonical `IHSG` + Stockbit historical -> API ticker `IHSG`
  - canonical `IHSG` + Yahoo -> API ticker `^JKSE`
  - input `^JKSE` -> canonical ticker `IHSG`
- Keep persisted candles under canonical ticker `IHSG`.

Tests:
- `IHSG` fetched via Stockbit calls Stockbit API as `IHSG`.
- `IHSG` fetched via Yahoo calls Yahoo API as `^JKSE`.
- User/request ticker `^JKSE` normalizes to persisted ticker `IHSG`.
- Ordinary stock tickers remain unchanged.

Acceptance checks:
- Alias behavior is deterministic and covered by offline unit tests.
- No adapter contains provider policy beyond wiring.

Implementation notes:
- Added `src/application/services/benchmark_symbol.py`.
- `^JKSE` is treated as a legacy/user-input alias for canonical `IHSG`.
- Yahoo provider maps canonical `IHSG` to Yahoo API symbol `^JKSE`.

## Phase 2 - Stockbit Historical Provider Canonicalization

Status: Done

Goal:
- Ensure Stockbit historical summary can return canonical `IHSG` candles.

Planned changes:
- Make `StockbitHistoricalProvider` accept canonical `IHSG`.
- Ensure returned `Candle.ticker` is canonical request ticker after normalization.
- Preserve `volume_unit="shares"` because Stockbit lots are converted by `* 100`.
- Preserve `price_adjustment_policy="raw"`.

Tests:
- Historical summary fixture for `IHSG` produces `Candle(ticker="IHSG")`.
- Volume lots are converted to shares.
- Returned candles are sorted ascending by date.

Acceptance checks:
- Stockbit historical provider works for `IHSG`.
- `^JKSE` does not get persisted from Stockbit fetch paths.

Implementation notes:
- `StockbitHistoricalProvider` canonicalizes input ticker before building the
  Stockbit historical summary URL.
- Returned candles use canonical ticker `IHSG`.
- Existing lots-to-shares conversion is preserved.

## Phase 3 - Benchmark Fetch Policy

Status: Done

Goal:
- Use Stockbit historical summary as primary source for benchmark candles when
  Stockbit auth is available.

Planned changes:
- Update fetch-market benchmark constant from `^JKSE` to `IHSG`.
- Route benchmark candle fetch to Stockbit historical first when broker provider
  is Stockbit/authenticated.
- Use Yahoo alias only as fallback when Stockbit is unavailable.
- Avoid Yahoo-first fallback for benchmark, because Yahoo returns rows even when
  benchmark volume is unreliable.

Tests:
- Fetch-market includes `IHSG` first.
- With Stockbit broker provider, benchmark candles use `stockbit_historical`.
- With no Stockbit auth, benchmark can fall back to Yahoo via `^JKSE`.
- Non-benchmark ticker routing is unchanged.

Acceptance checks:
- Benchmark source is visible in candle provenance.
- Adapter remains thin; non-trivial routing policy lives in application or
  infrastructure composition.

Implementation notes:
- `FetchMarketRefreshUseCase.BENCHMARK_TICKER` is now canonical `IHSG`.
- Fetch-market deduplicates legacy `^JKSE` input into `IHSG`.
- When a Stockbit broker provider is available, benchmark candles are fetched
  with `StockbitHistoricalProvider` instead of Yahoo-first fallback.
- Broker/meta/enrichment paths treat canonical `IHSG` as an index.

## Phase 4 - Config and Consumer Migration

Status: In progress

Goal:
- Move application defaults and consumers from `^JKSE` to `IHSG`.

Planned changes:
- Update configs:
  - `config/default.yaml`
  - `config/user.yaml.example`
  - `config/market_context_engine.yaml`
- Update tests and docs that assume `^JKSE`.
- Update market context and relative-strength defaults to canonical `IHSG`.
- Add compatibility handling for CLI/user input `^JKSE`.

Tests:
- Market context loads `IHSG` by default.
- Relative strength / benchmark-related tests use canonical ticker.
- CLI accepts `^JKSE` and normalizes to `IHSG` where appropriate.

Acceptance checks:
- No application config defaults use `^JKSE`.
- Existing user workflows still work with `^JKSE` as input alias.

Implementation notes:
- Updated shipped config defaults to `IHSG`.
- Updated market context factory, app config, indicator registry defaults,
  pre-open workflow, swing workflow alias forwarding, and trade CLI defaults.
- Updated swing backtest regime replay to honor canonicalized
  `benchmark_ticker`.
- Remaining work: update broader docs and any non-critical examples that mention
  `^JKSE`.

## Phase 5 - Data Repair / Migration

Status: Done

Goal:
- Remove inaccurate/stale `^JKSE` data and populate clean canonical `IHSG` rows.

Planned data operation:
- Back up `data/db/data.db` before destructive changes.
- Delete old benchmark rows:
  - `DELETE FROM candles WHERE ticker IN ('^JKSE', 'IHSG');`
- Re-fetch `IHSG` through Stockbit historical summary with `--refresh`.
- Recommended initial range: at least 800 days, or longer if backtests require it.

Verification queries:
- `SELECT ticker, source, volume_unit, MIN(date), MAX(date), COUNT(*) FROM candles WHERE ticker IN ('IHSG','^JKSE') GROUP BY ticker, source, volume_unit;`
- `SELECT date, close, volume, source FROM candles WHERE ticker='IHSG' ORDER BY date DESC LIMIT 10;`

Acceptance checks:
- No persisted `^JKSE` candle rows remain unless explicitly kept as legacy alias
  metadata outside `candles`.
- `IHSG` rows have `source='stockbit_historical'`.
- `IHSG` rows have `volume_unit='shares'`.
- Recent completed trading days have nonzero volume.
- Close values match Stockbit historical summary.

Implementation notes:
- Created backup: `data/db/data.db.pre-ihsg-migration-20260701.bak`.
- Initial 800-day request returned no Stockbit rows; live probe showed Stockbit
  historical summary returns rows for 365 days but not the 800-day range.
- Refreshed `IHSG` for 365 days through normal `saham fetch market` path.
- Deleted legacy `^JKSE` rows from `candles`.
- Final local state:
  - `IHSG`, `source='stockbit_historical'`, `volume_unit='shares'`,
    `price_adjustment_policy='raw'`
  - 240 rows from `2025-07-01` through `2026-07-01`
  - latest volume `17,211,509,900` shares on `2026-07-01`

## Phase 6 - Data Quality Audit

Status: In progress

Goal:
- Prevent this class of issue from recurring.

Planned changes:
- Add audit warnings for benchmark rows sourced from Yahoo `^JKSE`.
- Add audit warning for canonical benchmark missing or stale.
- Add audit warning for completed benchmark rows with zero volume.
- Optionally flag daily candles created during market hours if they are later
  treated as final EOD rows.

Tests:
- Audit flags Yahoo-sourced benchmark rows.
- Audit flags zero-volume completed `IHSG` rows.
- Audit passes clean Stockbit-sourced `IHSG` rows.

Acceptance checks:
- `saham fetch audit` reports benchmark provenance problems deterministically.
- Tests run offline with local fixtures.

Implementation notes:
- Audit expected trading day now prefers canonical `IHSG` and falls back to
  legacy `^JKSE` for unmigrated databases.
- Remaining work: add explicit warnings for Yahoo-sourced benchmark rows and
  zero-volume completed benchmark rows.

## Phase 7 - Documentation and Operator Notes

Status: Not started

Goal:
- Make the new source-of-truth clear to future agents and users.

Planned changes:
- Update `docs/data_sources.md`.
- Update README benchmark/candle provenance notes if needed.
- Document:
  - canonical ticker is `IHSG`
  - Yahoo alias is `^JKSE`
  - Stockbit historical summary is benchmark OHLCV source of truth
  - Stockbit `volume` lots are persisted as shares after conversion

Acceptance checks:
- Documentation explains provider aliasing and persisted ticker choice.
- Known limitation of Yahoo `^JKSE` volume is explicitly recorded.

## Phase 8 - Final Verification

Status: Not started

Goal:
- Prove the migration is complete and deterministic.

Commands to run:
- Targeted unit tests for providers, aliases, fetch-market, and audit.
- `saham fetch market IHSG --candles-only --refresh --days 800`
- `saham analyze regime`
- A representative command that previously consumed `^JKSE`.

Acceptance checks:
- Tests pass.
- `IHSG` candles are present and current.
- `^JKSE` user input remains compatible or fails with an explicit migration
  message.
- Market context works from `IHSG` candles.
- No new AI dependency or external mandatory provider is introduced beyond the
  already-authenticated Stockbit path; Yahoo fallback remains available.

Verification notes:
- Targeted regression suite passed: 108 tests.
- `saham analyze regime` succeeded using canonical `IHSG` rows.

## Current Next Step

Next recommended work:

1. Finish Phase 6 explicit data-quality warnings for benchmark provenance and
   zero-volume benchmark rows.
2. Finish Phase 7 broader documentation cleanup.
3. Optionally investigate Stockbit historical summary maximum lookback/chunking
   to extend `IHSG` beyond the currently refreshed 365-day range.
