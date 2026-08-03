# Fix Seasonality Negative-Cache Rows With Null Provenance

Status: `COMPLETED`

Source: DQ investigation 2026-07-31. Reactive repair
(`saham audit data repair-seasonality-cache`) was applied — 3 live rows
quarantined, 0 null-source rows remain — but the write path recreates them, so
this task removes the root cause.

## 1. Task Metadata

- Task type: Bugfix
- Priority: Medium — chronic audit churn (464 quarantined rows across 4 repair
  runs), low decision blast radius (rows are all-null, unusable on read).
- Semantic classification: `NON_SEMANTIC` — data-hygiene only. No scoring, risk,
  evidence, signal, or label behavior change; no persisted-feature semantics
  change; no contract-version bump.
- Chosen decision: stop persisting negative-cache rows (Option A) and enforce a
  never-null-provenance invariant at the write boundary. Option B (audit-legal
  negative cache) documented as the alternative if re-fetch cost is proven.

## 2. Problem Statement

`StockbitSeasonalityCache._write_cache`
(`src/infrastructure/browser/stockbit_seasonality.py:278`) is called
unconditionally from `get_seasonal_edge` (`:339-340`) with the result of
`_fetch`. `_fetch` returns `None` on empty body, parse failure, or exception
(`:353-362`). When `edge is None`, the row is written with **every metric AND
`source` set to `None`** (`:303-308`, `edge.source if edge else None`).

Consequences:

- The data-quality audit classifies these as `INVALID_SOURCE` + `ALL_METRICS_NULL`
  (`build_seasonality_cleanup_plan_use_case.py:227`), and
  `repair-seasonality-cache` quarantines+deletes them — a self-inflicted loop
  (464 rows / 4 runs).
- They never serve their cache purpose: `_read_cache` already rejects null-metric
  rows (`stockbit_seasonality.py:244`).
- They never dedupe: the `UNIQUE(ticker, year, month, fetched_month, fetched_at)`
  key includes `fetched_at = datetime.now()`, so each negative write inserts a
  fresh row rather than updating — they accumulate without bound between sweeps.

Root architectural mismatch: the write layer treats null-everything as a "no
data, remembered" marker; the audit layer treats null-everything as corruption.
The two contracts contradict, producing the worst of both worlds — written,
ignored on read, deleted on sweep.

## 3. Desired Outcome

- No new negative-cache rows are ever persisted: a no-data / failed fetch writes
  nothing.
- A row that IS persisted always has a non-null `source` (provenance invariant).
- After the fix, repeated enrichment over a universe containing no-seasonality
  tickers leaves `repair-seasonality-cache` dry-run at `status=PASS`,
  `invalid_row_count=0` on every subsequent run.
- Valid seasonality behavior is unchanged (same rows, same values, same source).

## 4. Non-Goals

- No `NO_DATA` status column / audit-rule exemption — that is Option B, out of
  scope unless re-fetch cost is proven material.
- No change to the audit classification or the repair/quarantine workflow (they
  stay strict; after this fix they should simply find nothing).
- No change to the seasonality read path or `SeasonalEdge` semantics.
- No risk/signal/evidence/label or scoring change.
- No new data provider.

## 5. Hard Invariants

- A persisted `seasonality_cache` row has a non-null `source` and at least one
  non-null metric. (Enforced at the write boundary.)
- A no-data fetch is a no-op for persistence, not a null-row write.
- Valid rows continue to upsert as before (idempotent on real data).

## 6. Architecture Impact

```md
Layer plan:
- Domain: not touched.
- Application: not touched (audit/repair unchanged; they become no-ops in
  steady state).
- Infrastructure: StockbitSeasonalityCache write path — skip persistence when
  edge is None; guard source non-null. Optional: NOT NULL source DB constraint
  (see decision note below).
- Adapter: not touched.
```

- New dependency: No.
- Affects determinism: No (removes non-deterministic null-row accumulation).
- Persistence change: schema change only IF the optional `NOT NULL source`
  constraint is adopted (see §8). The primary code-level guard needs none.
- Places policy in an adapter: No (infrastructure write policy, already there).

Decision note (primary vs hardening):
- Primary (low-risk, no migration): code-level guard — `get_seasonal_edge` does
  not call `_write_cache` when `result is None`; `_write_cache` refuses a
  null/empty `source` defensively.
- Optional hardening: `NOT NULL` on `source` at the DB level. SQLite cannot add
  NOT NULL to an existing column in place; it needs a table rebuild/migration.
  Adopt only if the code guard is judged insufficient. Live data already has 0
  null-source rows, so the migration is clean if chosen.

## 7. AI Usage Declaration

- No AI involved.

## 8. Data & Persistence

- Reads: unchanged.
- Writes: FEWER rows — no-data fetches persist nothing. Valid rows unchanged.
- Schema change: No for the code guard; Yes (table rebuild) only if the optional
  NOT NULL constraint is adopted.
- Old vs new semantically equivalent? For valid rows, Yes (identical). The only
  behavioral difference is that no-data outcomes stop being persisted — which is
  the intended correctness fix, not a source swap.

## 9. Acceptance Criteria

- [ ] `get_seasonal_edge` with a no-data/failed fetch persists no row.
- [ ] `_write_cache` cannot persist a row with null/empty `source`.
- [ ] Valid seasonality still upserts with `source="stockbit"` and metrics.
- [ ] `repair-seasonality-cache` dry-run reports `invalid_row_count=0` after an
      enrichment pass over a no-seasonality ticker (regression proof).
- [ ] Deterministic; works without AI; no non-goals violated.
- [ ] Adapter thinness N/A (infra-only); no policy moved into an adapter.
- [ ] **Lint Gate**: `ruff check src/ tests/` and `ruff format --check
      src/ tests/` pass; no rule weakening / blanket noqa / new per-file ignores.

## 10. Testing Expectations

- Unit-test `get_seasonal_edge`/`_write_cache` with a mock api client:
  - `_fetch` → None (empty body) ⇒ no row written.
  - valid body ⇒ row written with source + metrics.
  - defensive: `_write_cache` called with `edge=None` (or null source) writes
    nothing.
- Offline (mock client; no Playwright/network).
- Whole-repo Ruff check/format before close.

## 11. Documentation Impact

- README/CLI: No (internal cache behavior).
- New config: No.
- Limitations to state: dropping negative caching means no-data tickers are
  re-fetched each enrichment run. Confirm this is acceptable; if a "checked, no
  data" freshness marker is later needed, that is Option B, tracked separately.

## 12. Agent Execution Instructions

Before implementation: confirm the re-fetch-cost decision (§11 limitation).
Default is Option A (accept re-fetch). Only escalate to Option B if a measured
cost justifies a schema change. State the layer plan and proceed.

## Do Not Interpret This As

- Do not weaken the audit `INVALID_SOURCE`/`ALL_METRICS_NULL` rules to make the
  null rows "valid" — fix the writer, not the detector.
- Do not add a `NO_DATA` column as the default path (that is Option B).
- Do not persist a placeholder source (e.g. "unknown"/"stockbit") on no-data
  rows to dodge the audit — that reintroduces unprovenanced/empty rows.

## Completion Record

- Completed date: 2026-07-31
- Chosen option (A / A+NOT NULL / B): A — code-level guard in `_write_cache`
  (no schema migration). NOT NULL constraint deferred (code guard is sufficient).
- Implementation commit: (see branch merge)
- Files changed:
  - `src/infrastructure/browser/stockbit_seasonality.py` — `_write_cache` now
    returns early when `edge is None` or `source` is blank (provenance invariant).
  - `tests/infrastructure/browser/test_stockbit_seasonality.py` — 4 tests:
    none-edge no-op, blank-source no-op, valid-edge persists, `get_seasonal_edge`
    no-data fetch persists nothing.
- Commands run: `pytest tests/infrastructure/browser/test_stockbit_seasonality.py`
  (18 passed); `ruff check` + `ruff format --check` (clean).
- Verification result: live data already repaired (3 rows quarantined, 0
  null-source remaining); the no-data `get_seasonal_edge` path now writes no row,
  so the audit will find no new INVALID_SOURCE/ALL_METRICS_NULL rows to churn.
