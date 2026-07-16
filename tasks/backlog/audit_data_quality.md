# Backlog: ruthless data-quality and accuracy audit

## 1. Task metadata

**Task title:** Prove and repair point-in-time correctness for signal observations, labels, replay, readiness, accumulation evaluation, and sentiment outcomes  
**Task type:** Spike / Research followed by Bugfix and Refactor gates  
**Overall priority:** Critical / P0  
**Status:** Backlog — must complete before CLI restructuring  
**Decision:** Audit the producer-to-consumer chain in the order defined here. Implement this option only.  
**Compatibility policy:** Clean break is allowed. Do not preserve incorrect data, schemas, outputs, or tests merely for backward compatibility.

### Cross-backlog ownership and gates

The authoritative cross-backlog execution sequence lives in
`tasks/backlog/signal_evidence_program.md`.

- This document owns source truth, point-in-time/session correctness, artifact
  data integrity, quarantine/rebuild, and baseline freezing.
- `tasks/backlog/audit_signal_refactor_contract.md` owns SignalEngine semantics,
  scoring/authority contracts, empirical evaluation, and promotion lifecycle.
- Neither document independently authorizes evidence promotion.

This backlog has two gates; do not treat all of DQ-000..DQ-011 as a prerequisite
for repairing signal semantics:

```text
DQ-CONTRACT-GATE = DQ-000 + DQ-001 + DQ-002
DQ-BASELINE-GATE = DQ-003 through DQ-011 after signal-contract repairs
```

`DQ-CONTRACT-GATE` establishes source meaning and time/session rules. HIGH-1,
HIGH-2, artifact identity, and related live-contract corrections then define
the schema that DQ-003 onward must audit and rebuild. `DQ-BASELINE-GATE`
unblocks CLI restructuring and empirical evaluation; it does not authorize
threshold tuning or production promotion.

## 2. Why this comes before CLI restructuring

The CLI restructure should preserve a verified contract, not freeze current defects. The dependency is:

```text
Market and enrichment source truth
        ↓
Historical candidate observations
        ↓
Forward labels
        ↓
Replay and readiness
        ↓
Current signal inspection
        ↓
Historical accumulation evaluation
        ↓
Verified behavioral baseline
        ↓
CLI hierarchy restructure
```

Sentiment audit is an independent outcome pipeline and can be audited in parallel after the shared temporal/data rules are defined.

`tasks/backlog/improvement_cli_restructure.md` is blocked until
`DQ-BASELINE-GATE` passes.

## 3. Problem statement

Passing unit tests and internally consistent output do not prove data accuracy. A deterministic engine can reproducibly calculate the wrong answer when:

- a source field has been assigned the wrong semantic meaning;
- T data leaks into a T-1 observation;
- latest enrichment is joined to historical observations;
- calendar days are treated as IDX trading sessions;
- incomplete forward windows are labelled as complete;
- observation identity collapses distinct configurations or sources;
- replay returns stored payloads without proving they are reproducible;
- readiness counts rows that are duplicated, invalid, diagnostic-only, or in-sample;
- historical evaluation uses a different feature path from live analysis;
- corporate actions, suspensions, price limits, fees, or delistings distort outcomes;
- table labels hide missing data, low coverage, or unavailable evidence.

These failures contaminate learning, tuning, confidence claims, and user interpretation. They must be detected at the database and application-contract level before command names are reorganized.

## 4. Desired outcome

For every audited command family, the repository must be able to answer with evidence:

1. What exact source rows were used?
2. What did each field mean at that source?
3. What information was knowable at the effective market timestamp?
4. Which config/rules/code version produced the artifact?
5. Can the artifact be independently recomputed from its recorded inputs?
6. Is the result complete, partial, stale, invalid, or unavailable?
7. What was persisted, under what identity, and can reruns duplicate it?
8. Does table output communicate the same semantics as JSON and the DTO?

Completion produces:

- verified source and field contracts;
- an IDX-session-aware temporal contract;
- trustworthy observation and label identities;
- point-in-time replay/evaluation parity;
- explicit completeness and invalidity states;
- quarantined or rebuilt invalid historical artifacts;
- regression fixtures and database reconciliation queries;
- a frozen, corrected baseline for the later CLI restructure.

## 5. Non-goals

- No new predictive factor merely to improve scores.
- No threshold tuning during data-quality repair.
- No promotion of diagnostic evidence.
- No AI-generated ground truth.
- No CLI hierarchy changes until this backlog passes.
- No preservation of invalid historical artifacts for compatibility.
- No claim of predictive edge based only on correctness tests.
- No destructive modification of the user's production database without an explicit backup, dry run, and approval at implementation time.

## 6. Ruthless audit principles

1. **Fail closed.** Unknown, stale, partial, or temporally invalid data must not masquerade as zero, neutral, fresh, passed, or complete.
2. **Point-in-time or invalid.** If historical availability cannot be proven, the feature cannot be authoritative in historical replay.
3. **Source semantics over convenient names.** Similar-looking fields are not equivalent until cardinality, owner, unit, aggregation, and time meaning are reconciled.
4. **One effective session contract.** Every producer and consumer uses the same IDX calendar and completed-session cutoff.
5. **Raw data remains raw.** Repairs create new canonical artifacts; they do not silently rewrite evidence provenance.
6. **Identity includes semantics.** Artifact uniqueness must include every dimension that changes meaning.
7. **Reproducibility is tested.** Stored artifacts must match independent recomputation within explicit numeric tolerances.
8. **No survivorship shortcuts.** Historical universes and unavailable/delisted/suspended names must be represented honestly.
9. **Clean breaks beat compatibility lies.** Bump schemas, remove misleading fields, and rebuild rows when meanings change.
10. **Output clarity is data quality.** Ambiguous labels and silent fallbacks are correctness defects.

## 7. Severity and disposition policy

| Severity | Definition | Required disposition |
|---|---|---|
| DQ-P0 | Leakage, wrong source meaning, corrupt identity, incorrect label/outcome, or false readiness | Stop downstream use; fix and rebuild/quarantine affected artifacts |
| DQ-P1 | Missing/stale data can change action or materially bias evaluation | Cap authority/readiness; repair before CLI restructure |
| DQ-P2 | Ambiguous display/JSON, weak provenance, avoidable duplicate work | Fix before baseline freeze unless explicitly waived |
| DQ-P3 | Cosmetic or performance-only issue with no semantic effect | Track separately; does not block correctness gate |

Every finding must record:

```text
finding_id
severity
affected command/artifact
source tables/fields
date/ticker sample
expected vs observed
reproduction query/command
root cause
blast radius
disposition
regression test
rebuild/quarantine requirement
```

## 8. Ordered audit backlog

### DQ-000 — Protect the evidence and define the audit harness

**Priority:** P0  
**Depends on:** none  
**Outcome:** Audits are repeatable and cannot accidentally corrupt the working database.

**State:** Implemented (2026-07-16). Shipped as a read-only audit baseline
manifest generator only, per the decision to implement this option only —
no repair/rebuild/quarantine/label/tuning behavior was added.

- `saham audit data manifest --format json|table` emits an
  `audit_baseline_manifest` (schema_version 1) with database identity
  (path/exists/sha256/size), config identity (hashes for the tracked
  config set including the new validation panel), git code identity
  (commit/dirty/status), SQLite schema identity (user_version, migration
  count, table list), per-table summaries (row count, min/max date,
  ticker count, duplicate-key count, null summary) for candles,
  broker_summaries, broker_daily_flow, candidate_observations,
  signal_forward_labels, stock_meta, analyst_cache, insider_cache,
  company_fundamentals, shareholding_composition, seasonality_cache, and
  corporate_action_events, a validation scope, and explicit warnings.
- Existing `saham fetch audit` (default quality-audit) output is unchanged.
- Files added: `src/application/use_case/build_audit_baseline_manifest_use_case.py`,
  `src/infrastructure/persistence/sqlite_audit_manifest_reader.py`,
  `src/infrastructure/config/audit_config_identity_reader.py`,
  `src/infrastructure/config/audit_validation_panel_reader.py`,
  `src/infrastructure/config/git_code_identity_provider.py`,
  `config/audit_validation_panel.yaml`, plus focused tests under
  `tests/application/use_case/`, `tests/infrastructure/persistence/`, and
  `tests/adapters/cli/`.
- CLI surface clean-break (2026-07-16): the manifest and DQ-001A
  source-contract audits were relocated from `fetch audit --manifest` /
  `fetch audit --source-contracts` to top-level `saham audit data manifest`
  / `saham audit data source-contracts` in
  `src/adapters/cli/audit_commands.py`. `fetch_audit_commands.py` now only
  contains the original quality-audit command — no aliases or
  backward-compatible flags were kept under `fetch audit`.
- Read-only proven: SQLite opened via `file:...?mode=ro` (uri=True), a test
  asserts a write against that same connection raises `OperationalError`,
  and the manifest was run against the live 629 MB production DB with
  file size/mtime confirmed byte-identical before and after.
- Correction during review: the first pass used the task template's
  guessed enrichment table names (`insider_activity_cache`,
  `fundamentals_cache`, `shareholding_cache`, and a null date column for
  `seasonality_cache`), which do not match the live schema
  (`insider_cache`, `company_fundamentals`, `shareholding_composition`,
  `seasonality_cache.fetched_month`) even though the correct names had
  already been verified via source read. This was a real DQ-000-class
  defect — a baseline manifest reporting real PIT tables as missing.
  Fixed and covered by regression tests
  (`test_real_enrichment_table_names_are_recognized`,
  `test_seasonality_cache_reports_fetched_month_as_date`); re-verified
  live with zero warnings and all 12 tables resolving.
- Verification: focused suite (19 tests) passes; full suite passes
  (4168 passed) aside from 7 pre-existing unrelated flaky tests in
  `test_stock_analysis_workflow_dependencies_config_paths.py` confirmed
  present on a clean `main` before this change; `py_compile` and
  `git diff --check` pass.
- Not done in this slice (by design, deferred to later DQ-00x): dry-run
  repair-operation tooling (no repair commands exist yet — DQ-010 owns
  quarantine/rebuild).

**Implementation guideline:**

- Work on a timestamped database copy or transactionally isolated fixture.
- Record database hash, schema version, row counts, min/max dates, duplicate counts, null rates, and source coverage before any repair.
- Add a reusable audit runner that emits structured findings; it must not mutate by default.
- Separate discovery queries from repair commands.
- Capture current config/rule hashes and application revision.
- Select a fixed validation panel spanning large-cap banks, commodity names, illiquid names, suspended/notation names, and missing-data cases.
- Select dates covering normal sessions, Mondays, holidays, month ends, corporate actions, high volatility, and current/incomplete sessions.

**Accurate pointers:**

- Database configuration: `src/infrastructure/config/app_config.py`
- SQLite repositories: `src/infrastructure/persistence/`
- Schema migrations: `src/infrastructure/persistence/sqlite_migration_runner.py`
- Data-source documentation: `docs/data_sources.md`, `docs/data_database_erd.md`

**Acceptance criteria:**

- [x] Audit commands default to read-only.
- [x] Baseline manifest includes database/config/code identity.
- [ ] All repair operations require explicit target database and dry-run output.
      (N/A for this slice — no repair operations were implemented; DQ-010
      owns quarantine/rebuild/repair tooling.)
- [x] The validation panel and dates are committed as deterministic fixtures or manifests.
- [x] A failed audit cannot partially mutate canonical tables.
      (No write statements are ever issued; the reader connects read-only.)

### DQ-001 — Establish authoritative source and field contracts

**Priority:** P0  
**Depends on:** DQ-000  
**Outcome:** Every consumed field has a proven source meaning and availability contract.

**State:** Partially implemented via two read-only slices; DQ-001 as a whole
is not complete.

- **DQ-001A** (2026-07-16): `saham audit data source-contracts` — executable
  field-level contracts (semantics, unit, sign convention, aggregation,
  grain, temporal meaning, null semantics, PIT support) for `candles`,
  `broker_summaries`, `broker_daily_flow`, `candidate_observations`,
  `signal_forward_labels`. Fails closed on missing/null/unknown-value
  fields. `broker_summaries.foreign_net_value` modeled as derived
  (`foreign_buy_value - foreign_sell_value`), not a stored column.
- **DQ-001B** (2026-07-16): `saham audit data reconcile-sources` —
  executable reconciliation, read-only, no repair/quarantine:
  - `candles`: OHLC invariants (`high`/`low` bounds), non-negative volume,
    unknown/null provenance (`source`, `volume_unit`,
    `price_adjustment_policy`), plus distribution summaries.
  - `broker_summaries`: non-negative value/lot fields, `(ticker, date,
    source)` duplicate identity.
  - `broker_daily_flow`: non-negative buy/sell values, `net_value ==
    buy_value - sell_value` arithmetic, `(ticker, date, broker_code,
    source)` duplicate identity, always-present INFO finding that this is
    a tracked-broker subset, not full market composition. Deliberately
    does **not** compare `broker_daily_flow` totals to `broker_summaries`
    totals — different source semantics, not a defect.
  - Cross-table: `foreign_flow_points` (`source='idx'` rows only) reconciled
    against derived `broker_summaries.foreign_buy_value -
    foreign_sell_value` for matching `(ticker, date, source)`, tolerance
    1.0 IDR. `foreign_flow_points(source='stockbit')` rows are a distinct
    provider and are intentionally **not** compared against `broker_summaries`
    — verified live that `source='idx'` rows match broker_summaries exactly
    for the matched rows (0 mismatches) while stockbit rows use a different
    pipeline. `foreign_flow_snapshots` (7-day windowed) is reported INFO as
    aggregated/not-direct-daily, never force-reconciled.
  - Unmatched `foreign_flow_points` rows (different-source rows with no
    same-source `broker_summaries` counterpart) are counted explicitly and
    surfaced as `FOREIGN_FLOW_POINTS_PARTIAL_COVERAGE` (WARN) rather than
    silently excluded from the denominator — live run: 85,988 total rows,
    51,379 matched/reconciled (0 mismatches), 34,609 unmatched (mostly
    `stockbit`-source rows with no `idx`-source counterpart), so overall
    status is `WARN`, not a falsely optimistic `PASS`.
  - A table existing with missing required identity/value columns (partial
    schema/migration) produces a `BROKER_SUMMARY_SCHEMA_INSUFFICIENT` /
    `TRACKED_BROKER_SCHEMA_INSUFFICIENT` / `CANDLES_SCHEMA_INSUFFICIENT`
    FAIL finding instead of an `sqlite3.OperationalError` crash — covers
    `candles` missing identity (`ticker`, `date`), OHLC (`open`, `high`,
    `low`, `close`), or `volume` columns, in addition to the existing
    tolerance for `candles` provenance columns (`volume_unit`,
    `price_adjustment_policy`) added later via `ALTER TABLE`, and the
    equivalent identity/value column checks for `broker_summaries` and
    `broker_daily_flow`.
  - Files: `src/application/use_case/audit_source_reconciliation_use_case.py`,
    `src/infrastructure/persistence/sqlite_source_reconciliation_reader.py`,
    wired into `src/adapters/cli/audit_commands.py`.
  - Read-only proven the same way as DQ-000/DQ-001A: `mode=ro` connection,
    write-rejection test, and a live run against the 629 MB production DB
    with file size unchanged before/after.
  - Not covered by DQ-001B: `candidate_observations`, `signal_forward_labels`
    reconciliation queries; all enrichment tables (analyst, insider,
    fundamentals, shareholding, seasonality, corporate actions, notation,
    bandar detector); market context and sentiment source families. These
    remain open for later DQ-001 slices.
- **DQ-001C** (2026-07-16): extends `saham audit data source-contracts`
  (same command, no new command added) with field-level contracts for 13
  enrichment/source-context tables: `analyst_cache`, `insider_cache`,
  `company_fundamentals`, `shareholding_composition`, `seasonality_cache`,
  `ticker_notation_cache`, `bandar_detector`, `corporate_action_events`,
  `corporate_action_event_dates`, `forward_estimates_cache`,
  `company_profile_cache`, `earnings_cache`, `stock_meta`. Column lists
  verified 1:1 against the live schema before encoding (all 13 tables and
  every listed column confirmed present via `PRAGMA table_info` against
  `data/db/data.db`; no guessed names).
  - Contract policy: identity fields (`ticker`, and per-table natural-key
    components such as `insider_cache.name`/`action_type`,
    `seasonality_cache.year`/`month`/`fetched_month`/`fetched_at`,
    `earnings_cache.year`/`quarter`,
    `corporate_action_event_dates.date_role`) and provenance/date fields
    (`fetched_date`/`fetched_at`/`fetched_month`, `session_date`,
    `event_date`, `transaction_date`) fail closed on null/missing;
    optional enrichment metrics (price targets, fundamentals ratios,
    ownership percentages, EPS figures, accdist labels, etc.) warn on
    null rather than fail, per the "don't fail on legitimate source
    absence" rule. `source` fields fail on null/empty/`'unknown'`.
  - PIT wording extended beyond the original `HISTORICAL` used for
    DQ-001A's core tables: `POINT_IN_TIME` for cache tables with a usable
    fetched date (accumulate historical snapshots), `CURRENT_CACHE` for
    `ticker_notation_cache` (no DB-enforced historical uniqueness —
    rebuilt on refresh, describes current tradeable/notation state), and
    `HISTORICAL` retained for `bandar_detector` (true `PRIMARY KEY
    (ticker, session_date)` market/session data).
  - `SQLiteSourceFieldContractReader` and `AuditSourceFieldContractsUseCase`
    were **not** modified — the existing generic catalog-driven reader
    already supported the new tables without code changes, only catalog
    data was added (`StaticSourceFieldContractCatalog` in
    `source_field_contract_catalog.py`).
  - No reconciliation/invariant checks were added here — this is field
    contracts only. Executable enrichment reconciliation (cross-checking
    enrichment values, e.g. against `company_fundamentals` vs. computed
    ratios, or notation/suspension consistency) remains future **DQ-001D**.
  - Live run surfaced a real pre-existing finding (not a bug): 413/825
    `seasonality_cache` rows have null `source` and 47/825 have null
    `fetched_at`, correctly producing FAIL — consistent with DQ-000's
    manifest `null_summary` for the same table.
- **DQ-001D** (2026-07-16): extends `saham audit data reconcile-sources`
  (same command, no new command added) with 8 enrichment/source-context
  reconciliation checks: `seasonality_cache` (provenance consistency:
  invalid/null `source`, null `fetched_at`, `fetched_month` vs `fetched_at`
  YYYY-MM mismatch, all-metrics-null); `company_fundamentals`,
  `analyst_cache`, `forward_estimates_cache` (shared PIT-coverage shape:
  missing `(ticker, fetched_date)` identity fails, duplicate identity
  warns, all-metrics-null warns); `insider_cache` (missing 5-column
  natural-key identity fails, duplicate natural key warns);
  `corporate_action_events`/`corporate_action_event_dates` linkage
  (orphan date rows and null `event_date` fail, events without dates and
  null `date_role` warn); `ticker_notation_cache` (always-present INFO
  stating it is `CURRENT_CACHE` not historical PIT, missing
  `source`/`fetched_date` warns); `stock_meta` (missing
  `ticker`/`source`/`fetched_at` fails, duplicate `(ticker, fetched_at)`
  warns, both `sector`/`industry` null warns). Deliberately does not
  duplicate DQ-001C's per-field null reporting — these are table-level
  reconciliation/invariant findings only.
  - Extraction required first: `audit_source_reconciliation_use_case.py`
    was already at 708 LOC (AI_AGENT_CHECKLIST.md requires an extraction
    plan past 700 LOC before adding behavior). DTOs moved to
    `src/application/dto/source_reconciliation_dto.py`; DQ-001B's four
    core evaluators moved unchanged to
    `src/application/services/source_reconciliation_core_evaluator.py`;
    the new 8 enrichment evaluators live in
    `src/application/services/source_reconciliation_enrichment_evaluator.py`.
    The use case is now a ~180-line orchestrator. The use case module
    re-exports all DTOs so no external import site needed to change.
  - New sibling infra reader
    `src/infrastructure/persistence/sqlite_enrichment_reconciliation_reader.py`
    (existing `sqlite_source_reconciliation_reader.py` for core tables is
    untouched) — same read-only `mode=ro` pattern, verified via a
    write-rejection test and a live run against the production DB with
    file size unchanged before/after.
  - `AuditSourceReconciliationUseCase.__init__` now requires an
    `enrichment_reader` parameter; existing DQ-001B tests updated with a
    fake "empty but healthy" enrichment reader so their PASS/FAIL/WARN
    assertions for core tables are unaffected.
  - Live run: `seasonality_provenance_consistency` FAILs (460 mismatches
    across 825 rows — same null `source`/`fetched_at` rows DQ-000/DQ-001C
    already found), `foreign_flow_reconciliation`/`forward_estimates_pit_coverage`/
    `stock_meta_provenance` WARN, overall command status is FAIL — this is
    an accurate reflection of real local data, not a defect in the checks.
  - Note: the task instructions for this slice referenced files named
    `reconcile_data_sources_use_case.py` /
    `sqlite_data_source_reconciliation_reader.py`, which do not exist in
    this repo. Verified against actual repo state and implemented against
    the real DQ-001B files (`audit_source_reconciliation_use_case.py` /
    `sqlite_source_reconciliation_reader.py`) instead of guessing new
    file names to match the stale instructions.
- **DQ-001E** (2026-07-16): extends both existing commands (no new command)
  for `candidate_observations`, `signal_forward_labels`,
  `market_context_snapshots`, `regime_observations`:
  - `source-contracts`: `candidate_observations`'s existing DQ-001A
    contract already covered all required identity fields — only extended
    `payload_json`'s `null_semantics` to note JSON-content validation is
    reconciliation's job. `signal_forward_labels`'s DQ-001A contract was
    missing 6 live columns (`days_to_peak`, `days_to_trough`,
    `stop_would_trigger`, `target_would_trigger`, `created_at`,
    `updated_at`) — added, not duplicated. Two brand-new table contracts
    added for `market_context_snapshots` (13 fields) and
    `regime_observations` (14 fields), field counts verified 1:1 against
    live `PRAGMA table_info`.
  - `reconcile-sources`: 4 new checks in a new sibling reader
    (`sqlite_signal_artifact_reconciliation_reader.py`) and sibling
    evaluator (`source_reconciliation_artifact_evaluator.py`):
    `candidate_observations_identity` (canonical-row `config_hash != ''`
    identity validity, legacy-row WARN, duplicate canonical identity WARN,
    `payload_json` parseability via SQLite `json_valid()`, missing
    top-level `schema_version` marker WARN — verified live payloads do
    carry that key before enabling the check);
    `signal_forward_labels_identity_linkage` (identity nulls FAIL,
    duplicate identity FAIL since it directly inflates readiness counts,
    `fingerprint_json` parseability FAIL, and observation linkage proven
    via `(ticker, signal_date, observation_captured_at)` →
    `(ticker, snapshot_date, captured_at)` — confirmed by reading
    `generate_signal_forward_labels_use_case.py`, not guessed; WARN
    "not canonical-grade for replay/readiness linkage" only when
    `candidate_observations` lacks the columns to prove it);
    `market_context_snapshot_identity` and `regime_observations_identity`
    (both WARN-if-missing since neither is a hard requirement for core
    scoring; invalid/unknown `regime` FAILs; `factors_json`/
    `detection_inputs_json` parseability FAILs; duplicate-PK checks kept
    for defensiveness even though the DB enforces uniqueness).
  - Every new observer checks required columns via `PRAGMA table_info`
    before querying (same pattern as DQ-001D, applied correctly this
    time — including a JOIN-ambiguous-column bug caught and fixed during
    self-testing: the `signal_forward_labels`↔`candidate_observations`
    orphan-linkage query originally reused an unqualified WHERE clause
    that collided between both tables' `ticker` columns).
  - `AuditSourceReconciliationUseCase.__init__` now requires an
    `artifact_reader` parameter; existing DQ-001B/D tests updated with a
    fake "empty but healthy" artifact reader.
  - Live run: `candidate_observations_identity` WARNs (all 19,317 rows are
    legacy, 0 canonical — consistent with DQ-000/DQ-001B's existing
    findings for this table); `signal_forward_labels_identity_linkage`,
    `market_context_snapshot_identity`, `regime_observations_identity` all
    PASS (0 invalid regimes, 0 invalid JSON, full observation linkage
    proven for all 5,760 labels).
  - Note: this task's instructions also referenced the same nonexistent
    `reconcile_data_sources_use_case.py` file name as DQ-001D's
    instructions; implemented against the real files again.
- **DQ-001F** (2026-07-16): read-path authority guard for invalid
  `seasonality_cache` provenance (413 rows with null/invalid `source`, 47
  rows with null `fetched_at`, 413 rows with all metrics null — first
  surfaced by DQ-CONTRACT-GATE failing on the live DB). This is a guard, not
  a repair: `StockbitSeasonalityProvider._read_cache()`
  (`src/infrastructure/browser/stockbit_seasonality.py`) now returns `None`
  instead of a `SeasonalEdge` whenever the newest PIT-eligible row has null/
  empty/case-insensitive-`"unknown"` `source` (the old silent
  `source or "stockbit"` fallback is removed) or a null/empty/unparseable
  `fetched_at`; required-metric null checks already existed and are
  unchanged. Because the row is selected by `ORDER BY ... DESC LIMIT 1`
  before this check runs, an invalid newest row fails closed rather than
  silently falling back to an older valid row for the same ticker/year/month.
  No database mutation, no repair/quarantine command, no scoring/threshold/
  tuning change — only the provider's read path and its tests changed.
  **The live `saham audit data contract-gate` still fails**: the 413/47
  invalid rows still exist in the database and are still reported by
  `source-contracts`/`reconcile-sources` exactly as before; this task only
  stops those rows from being usable as evidence going forward; the gate
  will keep failing until the rows are actually repaired or quarantined (no
  such command exists yet) or the contract is deliberately relaxed.
  - Tests: 9 new cases in `test_stockbit_seasonality.py` (valid row still
    returns `SeasonalEdge`; null/empty/`"Unknown"` source → `None`; null/
    malformed `fetched_at` → `None`; null required metric → `None`; a newer
    invalid row does not fall back to an older valid row) — 14 total pass.
    `test_pit_schema_contracts.py`'s seasonality PIT fixture needed an
    explicit valid `source` value, since its rows previously depended on the
    now-removed null-source fallback.
  - Verification: focused seasonality tests (14) plus signal/company-quality/
    candidate-observation/PIT focused tests (40) pass; `pytest -k
    seasonality` — 36 passed; full suite — 4379 passed; `python -m
    py_compile` on changed files; `git diff --check` clean; live `saham
    audit data contract-gate --format json` confirmed exit code 1 and still
    lists the seasonality_cache WARN findings unsuppressed.
- **DQ-001G** (2026-07-16, implemented — dry-run only): new read-only report
  command `saham audit data seasonality-cleanup-plan --format json|table
  [--db PATH]` that scans `seasonality_cache` and lists exactly which rows
  are invalid and why, for a future repair task to act on. This is a
  **dry-run planning tool, not a repair/gate command**: it never mutates the
  database, has no delete/quarantine implementation, and does not change
  `DQ-CONTRACT-GATE` or the existing `source-contracts`/`reconcile-sources`
  commands. It always exits 0, even when `status` is `FAIL` — it is a report,
  not a gate.
  - `BuildSeasonalityCleanupPlanUseCase`
    (`src/application/use_case/build_seasonality_cleanup_plan_use_case.py`)
    owns the row-invalidity policy (kept out of the infrastructure reader,
    matching the DQ-001A/AuditSourceFieldContractsUseCase convention): a row
    is invalid if `source` is null/empty/case-insensitive `"unknown"`
    (`INVALID_SOURCE`), `fetched_at` is null/empty (`MISSING_FETCHED_AT`),
    `fetched_at` is set but not ISO-parseable (`MALFORMED_FETCHED_AT`), or
    every one of `avg_return_pct`/`win_rate_pct`/`positive_years`/
    `total_years`/`back_years` is null (`ALL_METRICS_NULL`) — a row with only
    *some* metrics null is deliberately left out of the plan (DQ-001F's
    runtime guard already handles that case independently). A row can carry
    multiple reason codes at once.
  - `SQLiteSeasonalityCleanupPlanReader`
    (`src/infrastructure/persistence/sqlite_seasonality_cleanup_plan_reader.py`)
    is a read-only URI (`mode=ro`) observer that returns every raw
    `seasonality_cache` row uninterpreted — no classification, no DDL/write
    statements.
  - Output contract: `artifact_type: "seasonality_cleanup_plan"`,
    `schema_version: 1`, `status: "PASS"|"FAIL"`, `source_available`,
    `invalid_row_count`, `invalid_reason_counts`, `dry_run: true`,
    `proposed_action: "DELETE_INVALID_SEASONALITY_ROW"` (documented, never
    executed), and `rows: [{ticker, year, month, fetched_month, fetched_at,
    source, reasons}]`.
  - Tests: reader tests (4) proving raw pass-through and no mutation; use
    case tests (17) covering all 4 row-level reason codes individually,
    multi-reason rows, reason-count tallying, the "one null metric ≠
    invalid" rule, source-unavailability (missing DB and missing table),
    and one end-to-end test against the real SQLite reader/schema; CLI
    tests (9) covering the JSON/table contract, exit-code-0-on-FAIL,
    exit-code-0-on-missing-DB, invalid `--format` rejection, and
    no-mutation. `test_command_contract.py` and the `audit data --help`
    command-listing test updated for the new command (intentional
    addition, not scope creep).
  - **Follow-up fix (2026-07-16, same day):** the initial cut returned
    `status: "PASS"` with `invalid_row_count: 0` when the database or the
    `seasonality_cache` table itself could not be found — indistinguishable
    from "checked and found nothing wrong," which would silently mask a
    wrong `--db` path. Fixed: the response gained a `source_available: bool`
    field; `status` is now `"PASS"` only when `source_available` is true
    **and** `invalid_row_count == 0`. A missing database/table sets
    `source_available: false`, `status: "FAIL"`, and one of two entries in
    `invalid_reason_counts` is set to 1 (both table-level reasons with no
    row identity, distinct from the four per-row reason codes). The
    table-format output prints an explicit "seasonality_cache is unavailable"
    warning naming the specific reason in this case. Still a report command —
    exit code stays 0 either way.
  - **Second follow-up (2026-07-16, same day):** the first follow-up
    collapsed "database missing" and "table missing" into one
    `SEASONALITY_CACHE_UNAVAILABLE` reason. Split into two distinct, stable
    reason codes so automation can tell them apart: `DATABASE_MISSING` (the
    SQLite file itself does not exist) and `SEASONALITY_CACHE_TABLE_MISSING`
    (the database exists but has no `seasonality_cache` table). The response
    also gained `source_unavailable_reason: str | None` — `None` when
    `source_available` is true, otherwise one of the two codes above — so
    callers don't need to scan `invalid_reason_counts` to find out which case
    occurred.
  - Verification: `pytest -k "seasonality or contract_gate or audit_data or
    command_contract"` — 106 passed; full suite — 4407 passed; `python -m
    py_compile` on changed files; `git diff --check` clean; live `saham
    audit data seasonality-cleanup-plan --format json` reports 433 invalid
    rows (413 `INVALID_SOURCE` + 413 `ALL_METRICS_NULL` overlapping, 47
    `MISSING_FETCHED_AT`, 0 `MALFORMED_FETCHED_AT`), `source_available:
    true`, `source_unavailable_reason: null`, and **exits 0**; pointing
    `--db` at a nonexistent path reports `source_unavailable_reason:
    "DATABASE_MISSING"`; pointing `--db` at an existing file with no
    `seasonality_cache` table reports `source_unavailable_reason:
    "SEASONALITY_CACHE_TABLE_MISSING"` — both still exit 0; live `saham
    audit data contract-gate --format json` still **exits 1** — confirming
    this task does not close the live gate.
- **DQ-001H** (2026-07-16): deterministic seasonality_cache quarantine repair
  command `saham audit data repair-seasonality-cache --db PATH [--dry-run|--apply]
  [--format json|table]` that transactionally quarantines + deletes invalid
  `seasonality_cache` rows identified by the same classification logic as
  DQ-001G (`INVALID_SOURCE`, `MISSING_FETCHED_AT`, `MALFORMED_FETCHED_AT`,
  `ALL_METRICS_NULL`). Default mode is dry-run (`--dry-run`); `--apply` mutates
  the database. `--dry-run` and `--apply` together fail CLI validation. Never
  deletes without quarantining first. Re-running `--apply` is idempotent
  (second run reports 0 invalid rows and does not duplicate quarantine entries).
  - `RepairSeasonalityCacheUseCase`
    (`src/application/use_case/repair_seasonality_cache_use_case.py`) reuses
    `_classify()` from DQ-001G's use case for identical row-invalidity policy.
    Defines `SeasonalityCacheRepairer(Protocol)` port and
    `RepairSeasonalityCacheResponse` DTO with the required output contract keys.
    Orchestrates: reader → classify → if source unavailable or no invalid rows →
     return early; if dry-run → report only; if apply → `repairer.ensure_quarantine_table()`
     then `repairer.quarantine_and_delete(rows, repair_run_id)` inside one
     transactionally-safe call. Successful apply sets `status: "PASS"` (not
     `"FAIL"`) to signal the operation completed; `invalid_row_count`
     /`quarantined_row_count`/`deleted_row_count` document what was repaired.
     Source-unavailable early-return preserves the caller's `dry_run` value
     rather than silently setting `dry_run: true`.
  - `SQLiteSeasonalityCacheRepairer`
    (`src/infrastructure/persistence/sqlite_seasonality_cache_repairer.py`)
    creates `seasonality_cache_quarantine` table via `CREATE TABLE IF NOT EXISTS`
    (idempotent DDL). `quarantine_and_delete()` opens a connection, begins a
    transaction (`BEGIN`), inserts each row into the quarantine table with full
    original columns plus `quarantine_reasons_json`, `quarantined_at`,
    `repair_run_id`, `original_table`, `schema_version`, then deletes the
     matching row from `seasonality_cache`. NULL-safe deletion uses dynamic
     WHERE-clause construction: each NULL column gets `col IS NULL` (no bound
     param), each non-NULL column gets `col = ?` with the value bound. After
     each DELETE, checks `cursor.rowcount == 1` — if 0 or >1, raises
     `RuntimeError` which triggers a full rollback (prevents quarantine+delete
     atomicity violation). On success: `commit()`. On any exception:
     `rollback()` and re-raise. Returns affected row count.
  - `repair_run_id`: `str(uuid.uuid4())` — unique per `--apply` invocation.
    Quarantine rows record this for traceability.
  - CLI: `src/adapters/cli/audit_commands.py` registers
    `repair-seasonality-cache` under `saham audit data`. Default `--format json`.
    Dry-run and apply are flags; mutual exclusion enforced via
    `typer.BadParameter`. Table format prints mode, status, invalid/quarantined/
    deleted counts, reason counts, per-row details, and a clear "no mutation
    performed" note on dry-run or "quarantined N row(s)" on apply.
  - Quarantine table `seasonality_cache_quarantine` columns:
    `ticker`, `year`, `month`, `fetched_month`, `fetched_at`, `source`,
    `avg_return_pct`, `win_rate_pct`, `positive_years`, `total_years`,
    `back_years`, `quarantine_reasons_json` (TEXT), `quarantined_at` (TEXT),
    `repair_run_id` (TEXT), `original_table` (TEXT DEFAULT 'seasonality_cache'),
    `schema_version` (INTEGER DEFAULT 1).
  - Tests: application-layer use case tests (13) covering dry-run (reports
    invalid rows, does not call repairer, default mode is dry-run, rows listed
    with reasons), apply (calls quarantine_and_delete, returns counts, reuses
    repair_run_id), missing source (DB missing, table missing → no mutation),
    no invalid rows (PASS, 0 affected), reason counts tally, and full response
    DTO shape. Infrastructure tests (14) covering dry-run does not change mtime,
    ensure_quarantine_table creates table/idempotent, apply creates table,
    moves rows into quarantine, deletes from source, preserves valid rows,
    returns count, rerun idempotency, NULL-safe deletion (null source, mixed
    nulls), transaction rollback, and quarantine table column schema. CLI tests
    (9) covering dry-run exits 0/no mutation, default is dry-run, `--dry-run`
    + `--apply` together fails, apply mutates/quarantines/removes rows, missing
    DB exits 0 with FAIL, table format shows counts, clean DB returns PASS,
    invalid format rejected. `test_command_contract.py` updated for the new
    command. `test_audit_data_commands.py`'s command-listing test updated.
  - Does **not** close `DQ-CONTRACT-GATE`: the 413/47 invalid rows are now
    repair-able but the gate still fails because invalid rows still exist in
    the canonical table until `--apply` is explicitly run against that database.
  - Verification: `pytest -k "repair_seasonality or seasonality or contract_gate
    or audit_data or command_contract"` passes.
- DQ-001 acceptance criteria below are **not** marked complete — DQ-001A/C/E
  now give field contracts for 20 tables (5 core + 13 enrichment + 2
  market-context) and DQ-001B/D/E give executable reconciliation for
  candles, broker_summaries, broker_daily_flow,
  foreign_flow_points/foreign_flow_snapshots, all 8 DQ-001D enrichment
  tables, plus candidate_observations, signal_forward_labels,
  market_context_snapshots, and regime_observations. Sentiment source
  families remain unaudited.

**Audit each source family:**

- candles: OHLCV, adjusted/unadjusted status, session date, duplicate bars, zero volume, impossible ranges;
- broker summaries and daily flow: aggregation grain, foreign net value, buy/sell values, broker code identity, missing brokers, session completeness;
- foreign-flow snapshots/points: relation to broker summaries and aggregation window;
- enrichment: analyst, holdings, insider, fundamentals, notation, bandar detector, corporate actions;
- market context: IHSG, breadth universe, EIDO, VIX, FX, aggregate foreign flow;
- sentiment logs: headline identity, publication/fetch time, snapshot date, classifier/provider version.

**Required evidence per field:**

| Check | Required proof |
|---|---|
| Cardinality | one row per documented key, or explicit many-row aggregation |
| Source owner | provider/table responsible for the value |
| Unit | IDR, shares, lots, percent, ratio, score, timestamp timezone |
| Sign convention | positive/negative meaning and buyer/seller perspective |
| Aggregation | daily, rolling, point snapshot, latest known, cumulative |
| Temporal availability | when the value became knowable, not just its business date |
| Adjustment | splits, reverse splits, dividends, rights, symbol changes |
| Null semantics | unavailable vs zero vs not applicable |
| Point-in-time support | historical versioned, current-only, or unverifiable |

**Clean-break rule:**

If two sources are not semantically equivalent, do not retain one generic field name. Introduce distinct concepts or remove the invalid consumer. Current-only enrichment must not be backfilled into historical evidence as if known then.

**Acceptance criteria:**

- [ ] Every authoritative input has a field-level contract and executable reconciliation query.
- [ ] Cross-table overlaps are reconciled on a sampled and aggregate basis.
- [ ] Unverifiable historical fields are marked diagnostic/unavailable or removed from replay authority.
- [ ] Null and zero are never conflated.
- [ ] Schema/display names include units and aggregation meaning where ambiguity exists.

### DQ-002 — Implement one IDX market-session and effective-time contract

**Priority:** P0  
**Depends on:** DQ-001  
**Outcome:** Every workflow agrees on what data was available at a given decision timestamp.

**Required contract:**

```text
run_at                    # timezone-aware execution timestamp
decision_at               # intended decision timestamp
latest_completed_session  # IDX session available at decision_at
analysis_as_of            # canonical market snapshot session
observed_through           # per source
available_at               # per row/source when known
freshness_status           # CURRENT | STALE | PARTIAL | UNKNOWN | INVALID
```

**Audit requirements:**

- Use the IDX trading calendar, not weekdays.
- Define pre-open, intraday, post-close, and provider-settlement cutoffs.
- Define how holidays, special sessions, suspensions, and missing provider rows behave.
- Prove that a T observation never reads candles, broker data, enrichment, labels, or market context that became available after `decision_at`.
- Ensure corporate-event offsets count appropriate calendar/session semantics explicitly.

**Accurate pointers:**

- Current weekday-only example: `src/application/services/swing_data_freshness.py`
- Market calendar repository/provider paths under `src/domain/ports/` and `src/infrastructure/persistence/`
- Observation dates: `src/domain/value_objects/candidate_observation.py`
- Candidate persistence: `src/infrastructure/persistence/sqlite_candidate_observations_repository.py`

**Clean-break rule:**

Artifacts without a defensible effective timestamp or data cutoff are invalid for learning and historical evaluation. Do not infer missing temporal provenance from `captured_at` alone.

**State:** DQ-002A/B/C/D/E implemented (2026-07-16). One canonical application-layer
session resolver exists and now backs every audited freshness-adjacent
service (`data_freshness_service.py`, `swing_data_freshness.py`,
`market_freshness_service.py`), and `candidate_observations`/
`signal_forward_labels` persist its provenance; DQ-002 as a whole is not complete (see
Deferred items below).

- **DQ-002A** (2026-07-16, revised same day after review): `EffectiveMarketSessionResolver`
  added at `src/application/services/effective_market_session_resolver.py`.
  Public method `resolve(*, run_at: datetime, decision_at: datetime | None =
  None) -> EffectiveMarketSession` with fields `run_at`, `decision_at`,
  `latest_completed_session`, `analysis_as_of`, `market_session_name`
  (`WEEKEND` | `BEFORE_OPEN` | `PRE_OPEN` | `REGULAR` | `PRE_CLOSING` |
  `AFTER_CLOSE`), `is_eod_pending`, `resolution_source`, `notes`.
  Pre-open/intraday/post-close IS modeled — the first pass had collapsed all
  weekday times before `MARKET_CLOSE` into one `LIVE_SESSION` label, which a
  review correctly flagged as violating this task's own pre-open/intraday
  requirement; fixed by classifying against `PRE_OPEN_START`,
  `REGULAR_OPEN`, and `PRE_CLOSE_START` from `idx_market.py`.
  `latest_completed_session`/`is_eod_pending` are identical across all four
  pre-close bands (prior cached session, pending) — only the label
  distinguishes them, since none of the audited call sites need band-level
  behavioral differences yet.
  - Preferred source: cached IHSG benchmark candle series via
    `MarketDataRepository.get_candles(..., end_date=...)`, always bounded by
    the decision date so a cache that already contains sessions after
    `decision_at` can never leak into a past-dated resolution (regression
    test: `test_bounded_ihsg_lookup_does_not_leak_future_cached_sessions`).
    Falls back to `last_weekday` weekday arithmetic only when no cached
    IHSG session bounds the decision date, with an explicit
    `resolution_source` (`weekday_fallback_*`) and a human-readable note.
  - Holidays are handled implicitly and correctly by the same bounded-cache
    lookup used for stale-cache detection: a weekday with no IHSG session
    that day (because it was a holiday) naturally resolves to the last
    cached prior session instead of being forced as "completed" — no
    separate holiday calendar was added (`resolution_source =
    "ihsg_cache_stale_or_holiday"` covers both cases identically, which is
    correct since both mean "no proven session on the decision date").
  - Naive datetimes are rejected (`ValueError`) for both `run_at` and
    `decision_at` — normalization was not chosen; tested explicitly.
  - Tests: `tests/application/services/test_effective_market_session_resolver.py`
    (14 tests) cover weekday before/after close, stale-cache-after-close,
    weekend-with-cache, holiday-like weekday, missing-cache fallback,
    `decision_at` overriding `run_at`, naive-datetime rejection (both
    params), future-cache-leakage exclusion, and the four weekday pre-close
    bands (`BEFORE_OPEN`, `PRE_OPEN`, `REGULAR`, `PRE_CLOSING`) each
    resolving to a distinct label.
  - Integration: `DailyBriefingUseCase` (`src/application/use_case/daily_briefing_use_case.py`)
    now takes an optional `session_resolver: EffectiveMarketSessionResolver
    | None` constructor param (defaults to building one from the injected
    `market_repository`, preserving existing call sites/DI wiring with zero
    changes). Its ad-hoc `while live_session_date.weekday() >= 5: -= 1 day`
    weekend-rollback loop was replaced by a resolver call; only the
    `WEEKEND` branch's result overrides `live_session_date` — normal weekday
    `live_session_date` (`date.today()` when not historical) is untouched.
    This is a real, intended behavior change versus the old code: on a
    weekend, `live_session_date` now reflects the cache-proven last IDX
    session (e.g. a Friday holiday correctly rolls back to Thursday)
    instead of blindly assuming Friday. Compatibility test
    `test_daily_briefing_normal_trading_day_date_unaffected_by_resolver_integration`
    proves live-weekday resolution is unchanged; a new test
    `test_daily_briefing_weekend_prefers_cached_ihsg_session_over_blind_friday`
    proves the corrected weekend behavior; the pre-existing
    `test_daily_briefing_rolls_back_weekends` (blind-Friday-on-empty-cache)
    still passes unchanged in outcome, with its mock updated to explicitly
    configure `get_candles` (empty) since the resolver now calls it.
  - Not touched, deferred to DQ-002B/C: `swing_data_freshness.py`,
    `data_freshness_service.py`, and `market_freshness_service.py` still
    have their own independent weekday/cache logic and were **not**
    replaced or wired to the new resolver — this slice only adds the
    canonical resolver and integrates one call site
    (`DailyBriefingUseCase`) as the required behavior-preserving proof
    point, per the task scope ("implement only the first safe slice").
  - No persistence schema change, no migration, no scoring/SignalEngine
    change, no observation identity change — none were needed or made.
  - Verification: `python -m py_compile` on all changed files; focused
    resolver tests (14) and daily-briefing tests (18, up from 16) pass;
    `git diff --check` clean; full suite run 4327 passed / 7 failed, all 7
    pre-existing/unrelated failures in
    `tests/adapters/cli/test_stock_analysis_workflow_dependencies_config_paths.py`
    (mock-not-used/FileNotFoundError assertions, present on a clean `main`
    before this change, consistent with the same pre-existing flake noted
    under DQ-000).

- **DQ-002B** (2026-07-16): screen/today data freshness now consumes
  `EffectiveMarketSession` instead of computing its own expected-EOD via
  weekday/wall-clock arithmetic.
  - `data_freshness_service.py`'s `compute_data_freshness()` signature
    changed from `screen_date`/`now` to a required `effective_session:
    EffectiveMarketSession` keyword. `_expected_latest_eod()` (the internal
    weekday/wall-clock derivation) was deleted — the module now owns no
    time arithmetic itself; `expected_latest_eod = effective_session.
    latest_completed_session` and `eod_pending = effective_session.
    is_eod_pending` directly. Source-state (`MISSING`/`UNKNOWN`/
    `PENDING_EOD`/`READY`/`STALE`) and alignment semantics are unchanged.
  - `DailyBriefingUseCase.execute()` resolves one `EffectiveMarketSession`
    per call and reuses it for every ticker's freshness plus
    `latest_completed_eod_date` (`= effective_session.
    latest_completed_session` directly — the old "first freshness item, or
    a synthetic `compute_data_freshness()` call with no real inputs just to
    get `expected_latest_eod`" fallback is gone). Non-historical runs
    resolve `run_at` from real WIB wall-clock time-of-day combined with
    `date.today()` (so pre-open/regular/pre-closing/after-close classify
    correctly, while the date itself stays consistent with this method's
    existing mockable time source). Historical runs (`as_of_date` given)
    build a deterministic decision timestamp: `MARKET_CLOSE` WIB on that
    date, documented as treating that date as a completed EOD decision, not
    an intraday one — `MARKET_CLOSE` itself already resolves to
    `AFTER_CLOSE` since the resolver's before-close check is strict `<`.
  - `screen_accum_result_projector.py`'s `project_single_screen_result()`
    and `project_multi_screen_result()` both gained a required
    `effective_session: EffectiveMarketSession` keyword and no longer
    accept/derive per-candidate `screen_date`. The projectors still do not
    construct or call the resolver themselves — callers pass an
    already-resolved session in, preserving "projectors stay pure." In
    `project_multi_screen_result()`, every window's candidates now share
    the one passed-in `effective_session` (the old per-window
    `screened_at_by_window` lookup was removed) — an intentional,
    instructed behavior change: freshness across 7/30/90-day windows now
    reflects one shared decision point instead of each window's own
    `screened_at`.
  - `RunAccumulationScreenWorkflowUseCase` resolves the effective session
    exactly once per `execute()` (`self._session_resolver.resolve(run_at=
    datetime.now(IDX_TIMEZONE))`, proven by
    `test_single_mode_resolves_effective_session_once` and
    `test_multi_mode_resolves_effective_session_once_not_per_window`) and
    passes the same instance into both `_execute_single`/`_execute_multi`
    and their projector calls — never resolved per ticker or per window.
    Gained an optional `session_resolver: EffectiveMarketSessionResolver |
    None` constructor param (defaults to building one from the injected
    `market_repository`, same pattern as `DailyBriefingUseCase`).
  - `screen_accum_workflow_factory.create_run_accumulation_screen_workflow_
    use_case()` now explicitly builds and injects
    `EffectiveMarketSessionResolver(deps.market_repository)` rather than
    relying on the use case's implicit default, per the instruction that
    resolver construction belongs in factory/wiring code.
  - Tests updated (no test asserts weekday arithmetic inside
    `compute_data_freshness` anymore — that behavior is owned and tested by
    `EffectiveMarketSessionResolver` alone):
    `test_data_freshness_service.py` (10, rewritten around a fixture
    `EffectiveMarketSession` builder — added
    `test_no_expected_latest_eod_produces_unknown_for_present_source_dates`);
    `test_daily_briefing.py` (20, up from 18 — added
    `test_daily_briefing_explicit_as_of_date_uses_deterministic_after_close_decision`
    and `test_daily_briefing_resolves_session_once_per_execute_not_per_ticker`;
    every `MagicMock()` market repository across the file now explicitly
    configures `get_candles.return_value` since the resolver is now always
    invoked, non-historical or historical);
    `test_screen_accum_result_projector.py` (24, all 19 existing
    `project_*_screen_result` calls updated with a shared
    `_EFFECTIVE_SESSION` fixture); `test_run_accumulation_screen_workflow_
    use_case.py` (22, up from 20 — added the two once-per-execute tests, plus
    a shared `_fake_session_resolver()` helper injected via `_make_uc`);
    `test_screen_accum_display.py` (8) and
    `test_screen_accum_command_json_and_save.py` (15) updated via the
    shared `screen_accum_test_fixtures.py` `_FAKE_EFFECTIVE_SESSION`/
    `_fake_workflow_result()` helper, which itself now passes
    `effective_session` into its internal projector calls.
  - `swing_data_freshness.py` and `market_freshness_service.py` are
    **not** touched — explicitly deferred to DQ-002C, per this task's hard
    boundary ("Do NOT wire swing analyze freshness yet").
  - No scoring/SignalEngine/persistence-schema/migration/label-generation
    change — none were needed or made.
  - Verification: `python -m py_compile` on all changed files; the full
    required focused-test list (113 tests across
    `test_data_freshness_service.py`, `test_effective_market_session_
    resolver.py`, `test_daily_briefing.py`, `test_screen_accum_result_
    projector.py`, `test_run_accumulation_screen_workflow_use_case.py`,
    `test_screen_accum_display.py`, `test_screen_accum_command_json_and_
    save.py`) passes; `git diff --check` clean.

- **DQ-002C** (2026-07-16): `saham analyze swing` freshness now consumes
  `EffectiveMarketSession` instead of the weekday-only helpers it owned
  before.
  - `swing_data_freshness.py`: `expected_weekday_data_date()` and
    `weekday_session_lag()` are **deleted** (no remaining callers anywhere
    in `src/` or `tests/` after this slice — verified by grep before and
    after). `build_swing_data_freshness()`'s signature changed from
    `as_of_date: date` to a required `effective_session:
    EffectiveMarketSession`; `expected_date =
    effective_session.latest_completed_session` drives the
    stale/not-stale decision directly (stale only when a source date is
    strictly earlier than `expected_date`; equal, newer, or
    `expected_date is None` never warn stale). The old
    "N trading session(s) before expected data date" wording (which
    depended on `weekday_session_lag()`'s count) is replaced by
    `"Latest {candle|broker flow} ({date}) is stale versus expected data
    date ({expected})."` — the session count is no longer computable
    without a full IDX calendar, so it was dropped rather than
    reintroduced via a new weekday approximation. A missing
    `latest_completed_session` produces one explicit "Expected data date
    is unknown because the effective market session could not resolve a
    latest completed session" warning (not a per-source duplicate, not a
    weekday fallback). `SwingDataFreshness.as_of_date` is now
    `effective_session.analysis_as_of or
    effective_session.latest_completed_session or
    effective_session.decision_at.date()` — the dataclass shape and
    `to_dict()` output keys are unchanged.
  - `SwingAnalysisInputCollector.collect()` (called once per workflow
    `execute()`, and `saham analyze swing` only ever analyzes one ticker
    per request, so this is inherently once-per-execution, not
    per-ticker) resolves one `EffectiveMarketSession` and passes it to
    `build_data_freshness`. `request.today` doubles as the analog of an
    explicit as-of date (tests/backtests pass a fixed historical date; the
    live CLI path always passes real `date.today()` since `analyze swing`
    has no separate `--date` flag). The collector distinguishes the two by
    comparing `request.today` against `date.today()`: equal → real WIB
    wall-clock time-of-day (so pre-open/regular/pre-closing/after-close
    classify correctly); different → deterministic `MARKET_CLOSE` WIB
    decision timestamp on `request.today`, same historical-decision
    convention as DQ-002B's `DailyBriefingUseCase`.
  - `SwingAnalysisWorkflowUseCase` and `SwingAnalysisInputCollector` both
    gained an optional `session_resolver: EffectiveMarketSessionResolver |
    None` constructor param (default: build one from the injected
    `market_repository`, same pattern as DQ-002B).
    `analyze_swing_workflow_factory.create_swing_analysis_workflow()` now
    explicitly injects `EffectiveMarketSessionResolver(deps.
    market_repository)` rather than relying on the implicit default, per
    the instruction that resolver construction belongs in factory/wiring
    code.
  - Only the swing-analysis freshness path changed — `screen accum` and
    `today` (handled in DQ-002B) were not touched again; no CLI flags were
    renamed; no scoring/SignalEngine/risk/setup-verdict/persistence-schema/
    migration/label-generation change.
  - Tests: `test_swing_data_freshness.py` fully rewritten (11 tests, all
    built around a fixture `EffectiveMarketSession` builder, no weekday
    arithmetic asserted anywhere) covering weekend/holiday-like
    (pre-resolved Thursday), before-close/`is_eod_pending`, after-close
    stale, unknown-session (no fallback), mismatch, refresh-ERR,
    missing-candle, newer-than-expected, and `as_of_date` derivation
    (both the `analysis_as_of` path and the `decision_at.date()`
    fallback). `test_swing_analysis_input_collector.py`'s existing
    `request.today`-threading test was updated to inject a fake
    `session_resolver` (its `market_repo` fake predates `get_candles`
    accepting `end_date`, so it can't serve the real resolver's IHSG
    lookup — this is exactly the "use a fake resolver where practical"
    case). All pre-existing swing-workflow test files (`test_swing_
    analysis_workflow_core.py`, `_refresh.py`, `_optional_evidence.py`,
    `_market_context.py`, `_corporate_calendar.py`, `_refactor.py`) needed
    no changes — their shared `FakeMarketRepository` fixture already
    implements `get_candles(ticker, start_date=None, end_date=None)`,
    which the default resolver's bounded IHSG lookup can call safely.
  - Verification: `python -m py_compile` on all changed files; full
    required focused-test list passes (11 + 14 + 23 workflow tests across
    6 files + 5 CLI tests); broader sweep `pytest -k swing` — 488 passed;
    `git diff --check` clean.

- **DQ-002D** (2026-07-16): `market_freshness_service.py` no longer owns
  benchmark cache lookup. `MarketFreshnessService` lost its
  `MarketDataRepository` constructor dependency, `last_known_trading_day()`,
  and its own `get_date_range()` call — it is now a pure policy service:
  `resolve_reference_trading_day(effective_session, today)` reads
  `effective_session.latest_completed_session` (falling back to
  `last_weekday(today)` only when unresolved), and `end_tolerance_days(...)`
  takes `effective_session` instead of `benchmark`/repository access.
  `BenchmarkTickerAliases` moved from `market_freshness_service.py` to
  `src/domain/value_objects/benchmark_symbol.py` (pure domain value object)
  to remove the circular-import risk now that `EffectiveMarketSessionResolver`
  no longer needs to import from the freshness service.
  `FetchMarketCommandWorkflowUseCase` gained a required `session_resolver:
  EffectiveMarketSessionResolver` constructor param and resolves one
  `EffectiveMarketSession` per `execute()` call (same real-WIB-wall-clock
  `datetime.combine(today, now_wib.time(), tzinfo=IDX_TIMEZONE)` convention as
  DQ-002B/C) before computing `expected_trading_day`.
  `fetch_market_workflow_factory.create_workflow_use_case()` now constructs
  `MarketFreshnessService()` (no repository) and injects
  `EffectiveMarketSessionResolver(SQLiteMarketRepository(db_path=db_path))` —
  factory wiring only, no freshness policy in the adapter.
  `fetch_market_candle_refresh.fetch_candles()` and
  `fetch_market_broker_refresh.fetch_broker()` each gained an
  `effective_session: EffectiveMarketSession | None = None` parameter and
  pass it straight to `end_tolerance_days`/`resolve_reference_trading_day`
  when the caller supplies one — see the "Review follow-up" entry below for
  who supplies it and why per-call local resolution was removed from the
  command-workflow path.
  **Explicit remaining exception, preserved exactly as before:** the
  benchmark ticker's own `end_tolerance_days(is_benchmark=True, ...)` still
  uses `last_weekday(today)` directly and ignores the resolved
  `effective_session` entirely — this breaks the circular dependency where
  benchmark candles would otherwise need their own (possibly stale) cache to
  decide whether the benchmark cache itself needs refreshing.
  - Tests: `test_market_freshness_service.py` fully rewritten (5 tests, a
    fake-repository fixture replaced by an `EffectiveMarketSession` builder)
    proving non-benchmark tolerance/reference-day both read
    `effective_session.latest_completed_session`, an unresolved session
    falls back to `last_weekday(today)`, the benchmark path ignores a stale/
    older session and always uses the weekday fallback, and tolerance is
    never negative. `test_fetch_market_command_workflow_use_case.py` gained
    a `mock_session_resolver` fixture and every `FetchMarketCommandWorkflowUseCase`
    construction now passes `session_resolver=mock_session_resolver`.
    `test_effective_market_session_resolver.py`'s `BenchmarkTickerAliases`
    import updated to the new domain location.
  - Verification: `python -m py_compile` on all changed files;
    `rg -n "MarketFreshnessService\(repository|last_known_trading_day|get_date_range\("
    src tests` shows no stale service usage outside unrelated repository
    implementations/callers; `rg -n "BenchmarkTickerAliases" src tests` shows
    every reference importing from `src.domain.value_objects.benchmark_symbol`;
    full required focused-test list (7 files) passes; `pytest -k "fetch_market
    or market_freshness or effective_market_session"` — 81 passed; full suite
    — 4346 passed; `git diff --check` clean.
  - **Review follow-up (2026-07-16):** initial DQ-002D cut still let each
    ticker's `fetch_candles()`/`fetch_broker()` resolve its own
    `EffectiveMarketSession` independently inside the per-ticker loop, so a
    long `saham fetch market -u lq45` run crossing market close could use a
    different `latest_completed_session` for early vs. late tickers, and
    repeated the IHSG cache lookup once per ticker. Fixed:
    `FetchMarketCommandWorkflowUseCase.execute()` now resolves one
    `EffectiveMarketSession` before building `FetchMarketRefreshRequest` (not
    after, as before) and reuses it for both the refresh request and the
    `expected_trading_day` computation — one resolve per command run, not two.
    `FetchMarketRefreshRequest` gained an `effective_session:
    EffectiveMarketSession | None = None` field;
    `FetchMarketRefreshUseCase.execute()` forwards it into every
    `fetch_candles`/`fetch_broker` call for every ticker. `fetch_candles()`
    and `fetch_broker()` both gained an `effective_session=None` parameter:
    when provided (the command-workflow path) they use it directly with no
    further resolution; when `None` (the only other direct caller,
    `swing_data_refresh.refresh_swing_data()`, which fetches a single ticker
    with no shared command-level session) they resolve one locally exactly
    as before, preserving prior behavior for that caller. The benchmark
    circular-dependency exception (`is_benchmark=True` still forces
    `last_weekday(today)`) is unchanged. New test
    `test_fetch_market_refresh_passes_same_effective_session_to_every_ticker`
    proves the identical session object reaches every ticker's candle/broker
    fetch; new test
    `test_same_resolved_session_is_reused_for_refresh_and_expected_trading_day`
    proves the command workflow resolves exactly once and reuses the same
    object for `expected_trading_day`. Full suite — 4348 passed;
    `git diff --check` clean.

- **DQ-002E** (2026-07-16): `candidate_observations` and `signal_forward_labels`
  now persist execution/effective-session provenance instead of forcing
  future readers to infer session state from `captured_at`/`snapshot_date`.
  `CandidateObservation` (`src/domain/ports/candidate_observations_repository.py`)
  and `SignalForwardLabel` (`src/domain/value_objects/signal_forward_label.py`)
  each gained 7 optional metadata fields —
  `decision_at`, `latest_completed_session`, `analysis_as_of`,
  `market_session_name`, `is_eod_pending`, `resolution_source`,
  `resolution_notes` — copied verbatim from an already-resolved
  `EffectiveMarketSession`, never recomputed by any repository or by label
  generation. **Identity is unchanged**: `candidate_observations` canonical
  identity remains `(ticker, snapshot_date, workflow, window_sessions,
  data_as_of_date, config_hash)`; `signal_forward_labels`' unique constraint
  remains `(ticker, signal_date, horizon, observation_captured_at)` — a
  provenance-only re-save updates the existing row in place, proven by test.
  SQLite schema: both tables gained the same 7 columns via additive
  migrations (`decision_at TEXT NOT NULL DEFAULT ''`,
  `latest_completed_session TEXT NOT NULL DEFAULT ''`,
  `analysis_as_of TEXT NOT NULL DEFAULT ''`,
  `market_session_name TEXT NOT NULL DEFAULT ''`, `is_eod_pending INTEGER`
  (nullable), `resolution_source TEXT NOT NULL DEFAULT ''`,
  `resolution_notes_json TEXT NOT NULL DEFAULT '[]'`) —
  `candidate_observations` migrations 7–13, `signal_forward_labels`
  migrations 2–8. Legacy rows read every new field back as `None`/`()`.
  `AccumulationScreenResponse` did **not** need a new `effective_session`
  field: `RecordAccumulationObservationsUseCase.execute()` gained an optional
  `effective_session: EffectiveMarketSession | None = None` parameter instead,
  threaded straight into `AccumulationCandidateObservationPersister.persist()`
  — lower blast radius than adding a field to a response DTO shared by the
  read-only diagnostic screen path (`RunAccumulationScreenWorkflowUseCase`),
  which never persists and was left untouched. `BackfillSignalObservationsUseCase`
  gained an optional `session_resolver: EffectiveMarketSessionResolver | None`
  constructor dependency (defaulting to one built from its existing
  `market_data_repository`, explicitly injected in
  `analyze_signal_backfill_commands.py` per the factory-wiring convention) and
  resolves exactly one deterministic after-close-WIB session per
  `trading_date` (`datetime.combine(trading_date, MARKET_CLOSE,
  tzinfo=IDX_TIMEZONE)`), reused across every `window` for that date — proven
  by a test asserting object identity across all window-loop iterations for
  one date. `GenerateSignalForwardLabelsUseCase` copies all 7 fields from the
  source `CandidateObservation` onto both available and UNAVAILABLE labels;
  it has no resolver dependency at all, so there is no fresh-session-lookup
  path to guard against.
  Source-field contract catalog: both tables' contracts gained the same 7
  fields (via a shared `_effective_session_provenance_fields()` helper),
  `required=False`, `null_policy="ignore"` — legacy/unresolved rows are
  expected to have empty provenance, not a contract violation.
  Tests: candidate-observations repo round-trip + legacy-read + identity-
  unaffected-by-provenance-only-change (3 new tests); label repo round-trip +
  legacy-read (2 new tests); persister/recorder provenance-passed-through +
  no-session-leaves-fields-empty (2 new tests); backfill one-session-per-
  date/shared-across-windows (1 new test); label generation available/
  unavailable-copies-provenance + no-fresh-resolve (3 new tests). Full suite
  — 4359 passed; `git diff --check` clean.

**Deferred (not started):**

- Provider-settlement cutoffs and any band-specific behavioral difference
  between `BEFORE_OPEN`/`PRE_OPEN`/`REGULAR`/`PRE_CLOSING` beyond the label
  (all four currently resolve `latest_completed_session`/`is_eod_pending`
  identically — no call site needs finer behavior yet).
- `observed_through` / `available_at` / `freshness_status` fields from the
  full DQ-002 required contract — `EffectiveMarketSession` only implements
  `run_at`, `decision_at`, `latest_completed_session`, `analysis_as_of`,
  plus resolver-specific provenance fields (`market_session_name`,
  `is_eod_pending`, `resolution_source`, `notes`). `freshness_status` is not
  derivable without new policy and remains deferred (DQ-002E did not add it).
- Temporal-leakage proof across candles/broker/enrichment/labels/market
  context beyond the resolver's own bounded-cache-lookup guarantee.
- Extending persisted provenance (DQ-002E's pattern) to any artifact tables
  beyond `candidate_observations`/`signal_forward_labels`.

**Acceptance criteria:**

- [ ] One application-layer session service is used by all audited workflows.
      (Resolver is used by `DailyBriefingUseCase`,
      `RunAccumulationScreenWorkflowUseCase`/screen-accum projectors,
      `SwingAnalysisWorkflowUseCase`/`swing_data_freshness.py`, and now
      `FetchMarketCommandWorkflowUseCase`/`market_freshness_service.py`
      (DQ-002D). `data_freshness_service.py`, `swing_data_freshness.py`, and
      `market_freshness_service.py` all now own no independent time
      arithmetic beyond the documented benchmark-circular-dependency
      exception, and are pure functions of an injected
      `EffectiveMarketSession`.)
- [ ] Weekend, holiday, pre-open, intraday, post-close, and late-provider tests pass.
      (Weekend/holiday/pre-open/intraday/post-close covered by the resolver
      and its tests, and now by swing freshness's own tests reusing the
      same fixture pattern; provider-settlement/late-provider cutoffs not
      yet modeled.)
- [x] Every persisted artifact distinguishes execution time from effective market session.
      (DQ-002E: `candidate_observations` and `signal_forward_labels` now
      persist `decision_at`/`latest_completed_session`/`analysis_as_of`
      distinct from `captured_at`/write-timestamp columns. Other artifact
      tables — market_context_snapshots, regime_observations, etc. — are not
      yet covered.)
- [ ] Temporal leakage tests intentionally plant future rows and prove they are excluded.
      (Proven for the resolver's own IHSG lookup only; not yet proven across
      candles/broker/enrichment/labels/market-context consumers.)

### DQ-003 — Audit and repair historical candidate-observation backfill

**Priority:** P0  
**Depends on:** DQ-001, DQ-002  
**Outcome:** Backfilled observations are point-in-time reproductions of what the live workflow could have known.

**Accurate pointers:**

- CLI: `src/adapters/cli/analyze_signal_backfill_commands.py`
- Use case: `src/application/use_case/backfill_signal_observations_use_case.py`
- Candidate construction: `src/adapters/cli/screen_accum_workflow_factory.py` and its application dependencies
- Repository: `src/infrastructure/persistence/sqlite_candidate_observations_repository.py`
- Fingerprint services: `src/application/services/accumulation_observation_fingerprint.py` and related modules

**Audit requirements:**

- Compare backfilled T observations with independently recomputed T snapshots using data physically truncated at T.
- Prove all indicator warm-up windows end at T.
- Prove broker windows contain broker sessions, not calendar approximations.
- Verify current-only enrichment is excluded or explicitly unavailable.
- Verify historical universe membership or record that the run used a current universe and is survivorship-biased.
- Reconcile candidate inclusion/exclusion counts and reasons per date.
- Test idempotence and uniqueness across ticker, effective session, workflow, window, setup/horizon where relevant, config hash, and data cutoff.
- Verify reruns after config changes do not overwrite semantically different observations.
- Validate `captured_at`, `snapshot_date`, `data_as_of_date`, workflow, window, config hash, and payload schema.
- Enforce `ARTIFACT-IDENTITY` from the signal-refactor backlog: code version,
  resolved-config hash, authority-registry version, evidence-contract version,
  observation schema, universe snapshot, IDX calendar/session version, and
  source-data cutoff.
- Persist the contemporaneous eligible-universe control population as well as
  selected candidates, including inclusion/exclusion state, rejection
  stage/reasons, pre-filter measurements, missing-data state, and rank.
- Preserve suspended, delisted, stale, and unavailable names as explicit states;
  do not erase them from evaluation denominators.

**Clean-break rule:**

If canonical identity omits a meaning-changing dimension, replace it and rebuild. Do not retain an upsert key that silently overwrites a different experiment. Purge or quarantine observations produced with leakage, current-only enrichment, unknown config, or invalid date alignment.

**Acceptance criteria:**

- [ ] Golden truncated-database fixtures match backfill output exactly.
- [ ] Repeating the same run creates no duplicates or drift.
- [ ] Changing a semantic identity dimension creates a distinct artifact or explicit version replacement.
- [ ] Candidate and control rows share one PIT cutoff but cannot overwrite one another.
- [ ] Candidate-only datasets are ineligible for screener recall/filter-value claims.
- [ ] Every skip has a machine-readable reason.
- [ ] Survivorship and coverage limitations are quantified, not buried in prose.

### DQ-004 — Audit and repair forward-label generation

**Priority:** P0  
**Depends on:** DQ-003  
**Outcome:** Every label is correctly bound to one observation and one complete future IDX-session window.

**Accurate pointers:**

- CLI: `src/adapters/cli/analyze_signal_label_commands.py`
- Generator: `src/application/use_case/generate_signal_forward_labels_use_case.py`
- Summary: `src/application/use_case/summarize_signal_forward_labels_use_case.py`
- Value object: `src/domain/value_objects/signal_forward_label.py`
- Repository: `src/infrastructure/persistence/sqlite_signal_forward_labels_repository.py`

**Audit requirements:**

- Verify the label binds to exact observation identity, including `observation_captured_at` or its replacement canonical ID.
- Bind executable labels to execution-policy, entry-model, exit-model,
  cost-model, and label-schema versions.
- Preserve raw market outcomes separately from net executable outcomes and from
  execution status (`FILLED`, `PARTIAL`, `UNFILLED`, `UNTRADEABLE`, or an
  explicit equivalent).
- Verify the entry/reference price and whether it represents close, next open, auction, or another executable assumption.
- Count future IDX sessions, not rows blindly; detect gaps and suspensions.
- Validate close return, maximum high return, minimum low return, days to peak/trough, target/stop trigger, and same-day target/stop ordering.
- Adjust or explicitly invalidate windows crossing splits, reverse splits, rights adjustments, symbol changes, delistings, or bad OHLC.
- Verify incomplete windows never contribute to performance aggregates or patch eligibility.
- Verify horizon policy/config is versioned with the label.
- Recompute a statistically meaningful sample directly from candle rows and reconcile exactly.

**Clean-break rule:**

Labels with ambiguous entry price, incomplete windows, orphaned observations, missing policy version, or corporate-action distortion must be invalidated and rebuilt. Do not retain them as “best effort.”

**Acceptance criteria:**

- [ ] Independent SQL/manual calculations match every label field in golden fixtures.
- [ ] Target/stop collision policy has explicit tests.
- [ ] Missing sessions, suspensions, corporate actions, and incomplete windows have explicit outcomes.
- [ ] Fees, taxes, slippage, price limits, gaps, fills, and timing follow
      `IDX-EXECUTION-LABELS` or the label is non-canonical.
- [ ] Label uniqueness cannot attach one outcome to the wrong observation version.
- [ ] Summary use case excludes invalid/unavailable labels by contract.

### DQ-005 — Audit signal replay for reproducibility, not retrieval

**Priority:** P0  
**Depends on:** DQ-003, DQ-004  
**Outcome:** Replay proves what was stored and whether it can be reproduced from recorded inputs.

**Accurate pointers:**

- CLI: `src/adapters/cli/analyze_signal_replay_commands.py`
- Use case: `src/application/use_case/replay_signal_observation_use_case.py`
- Observation repository: `src/infrastructure/persistence/sqlite_candidate_observations_repository.py`

**Audit requirements:**

- Distinguish `retrieve stored observation` from `recompute historical observation`.
- If the command only retrieves, rename its artifact/description and do not claim replay reproducibility.
- Add or audit recomputation using recorded config/rules/data cutoff.
- Compare stored and recomputed score, factor presence, coverage, constraints, setup phase, and fingerprint.
- Classify differences: code-version drift, config drift, missing source history, data correction, or corruption.
- Never silently select “latest” when multiple observation versions exist without displaying the selected identity.

**Clean-break rule:**

If reproducibility cannot be achieved because the required code/config/source version is absent, return `UNREPRODUCIBLE` with reasons. Do not call successful row retrieval a successful replay.

**Acceptance criteria:**

- [ ] Output names the exact observation identity selected.
- [ ] Stored-versus-recomputed comparison is explicit or the command is explicitly retrieval-only.
- [ ] Multiple-version ambiguity fails or requires explicit selection.
- [ ] Drift is machine-readable and never collapsed into a generic warning.

### DQ-006 — Audit signal readiness counts and patch eligibility

**Priority:** P0  
**Depends on:** DQ-003, DQ-004, DQ-005  
**Outcome:** Readiness reflects valid, independent, point-in-time observations and labels—not raw row volume.

**Promotion boundary:** Correct counts are necessary but insufficient for
promotion. The current chronological 70/30 split is diagnostic only. Production
proof additionally requires compatible `ARTIFACT-IDENTITY`, purged
`WALKFORWARD-VALIDATION`, `INCREMENTAL-EDGE`, and a verified
`PROMO-INTEGRITY` artifact.

**Accurate pointers:**

- CLI: `src/adapters/cli/analyze_signal_readiness_commands.py`
- Use case: `src/application/use_case/report_signal_readiness_use_case.py`
- Target definitions/config referenced by that use case
- Observation and label repositories listed above

**Audit requirements:**

- Reconcile raw rows, canonical observations, valid labels, target-filter matches, labeled targets, in-sample/OOS counts, and unique dates/tickers.
- Ensure duplicate captures do not inflate readiness.
- Ensure one ticker/date does not count as independent samples across accidental duplicates.
- Verify diagnostic targets are never patch-eligible.
- Verify OOS split is time-based, immutable, and established before outcome inspection.
- Require diversity/coverage metrics by ticker, sector, regime, liquidity tier, and time—not only total count.
- Ensure invalid/unreproducible observations and labels are excluded with visible counts.
- Verify every blocker and patch-eligible decision from an independent SQL reconciliation.

**Clean-break rule:**

Any readiness metric based on contaminated, duplicate, in-sample, or invalid data must be removed or renamed. Patch eligibility remains false until all P0 audit gates pass, regardless of row count.

**Acceptance criteria:**

- [ ] Independent reconciliation matches every displayed/JSON count.
- [ ] Invalid and excluded counts are visible by reason.
- [ ] OOS membership cannot change after labels are observed.
- [ ] Patch eligibility is impossible when any mandatory provenance/quality gate fails.
- [ ] Mixed artifact identities are reported separately and cannot be pooled.
- [ ] No readiness output claims production eligibility from the 70/30 split alone.

### DQ-007 — Audit current SignalEngine inspection accuracy

**Priority:** P1  
**Depends on:** DQ-001, DQ-002  
**Outcome:** Signal inspection explains the exact canonical engine calculation for a defensible effective session.

**Accurate pointers:**

- CLI: `src/adapters/cli/analyze_signal_audit_commands.py`
- Use case: `src/application/use_case/audit_signal_use_case.py`
- Engine factory: `src/infrastructure/composition/signal_engine_factory.py`
- Config loader: `src/infrastructure/config/signal_engine_config_loader.py`
- Bootstrap/weight resolution: `src/application/services/bootstrap.py`
- Coverage provider: `src/infrastructure/persistence/sqlite_signal_coverage_provider.py`

**Audit requirements:**

- Recompute every factor score and weighted contribution independently from raw source rows.
- Reconcile configured, active, effective, alpha, and trigger weights.
- Verify missing factors use the documented neutral/unavailable behavior and do not inflate conviction.
- Verify canonical score, legacy diagnostic score, coverage, authority coverage, and entry-quality mapping use distinct labels.
- Prove `--date T` builds a point-in-time context rather than joining latest enrichment.
- Validate factor coverage counts against SQL and distinguish rows from usable rows and unique tickers.
- Display source date, value, unit, freshness, authority, and unavailable reason for every factor.

**Clean-break rule:**

Remove the “legacy” score if it is routinely misread or cannot be justified. Do not preserve dual scores solely for compatibility. Rename `signal-audit` semantics to inspection after correctness is proven.

**Acceptance criteria:**

- [ ] Golden factor calculations match engine output within declared decimal tolerances.
- [ ] Historical dates cannot consume future/current-only values.
- [ ] Missing data cannot increase authority or readiness.
- [ ] Table, JSON, and DTO use identical score/coverage terminology.

### DQ-008 — Audit accumulation historical evaluation

**Priority:** P1  
**Depends on:** DQ-001 through DQ-004, DQ-007  
**Outcome:** Historical accumulation results measure the same point-in-time strategy semantics claimed by live screening.

**Accurate pointers:**

- CLI: `src/adapters/cli/analyze_accum_commands.py`
- Workflow factory: `src/adapters/cli/analyze_accum_workflow_factory.py`
- Workflow: `src/application/use_case/run_accumulation_audit_workflow_use_case.py`
- Core evaluator: `src/application/use_case/accumulation_audit_use_case.py`
- Config: accumulation audit configuration under `src/infrastructure/config/` and `config/`
- CSV/display: `src/adapters/cli/analyze_accum_csv_writer.py`, `src/adapters/cli/analyze_accum_display.py`

**Audit requirements:**

- Establish live-screen versus historical-evaluation parity for features, setup gates, session windows, source precedence, and missing-data policy.
- Require historical universe membership or quantify survivorship bias.
- Verify no forward candle participates in signal construction.
- Verify outcome horizons, exit simulation, entry timing, fees, slippage, lot size, liquidity, price limits, suspensions, and same-day TP/SL policy.
- Include delisted, suspended, and failed names where source history permits.
- Reconcile skipped signals by reason; never drop them silently.
- Separate absolute return from excess return versus IHSG and sector.
- Use purged walk-forward splits with embargo for overlapping label horizons.
- Compare against simple baselines; do not interpret in-sample optimization as edge.
- Verify CSV and JSON preserve numeric units and exact record identities.

**Clean-break rule:**

Invalidate published metrics produced with leakage, survivorship bias presented as unbiased, mismatched live/backtest rules, or unrealistic execution assumptions. Rename the command to evaluation only after its artifact contract is accurate.

**Acceptance criteria:**

- [ ] Truncated-data live reconstruction matches historical signal generation.
- [ ] Every included/skipped candidate is accounted for.
- [ ] Costs and execution assumptions are explicit in every result artifact.
- [ ] OOS performance is separated from training/validation.
- [ ] Baseline comparison and uncertainty/sample size are reported.

### DQ-009 — Audit sentiment outcome data independently

**Priority:** P1  
**Depends on:** DQ-001, DQ-002  
**Outcome:** Sentiment audits bind one time-valid prediction to correct future market outcomes without duplicate or misleading statistics.

**Accurate pointers:**

- CLI: `src/adapters/cli/analyze_sentiment_commands.py`
- Factory: `src/adapters/cli/analyze_sentiment_workflow_factory.py`
- Use case: `src/application/use_case/audit_sentiment_use_case.py`
- Persistence: `src/infrastructure/persistence/sentiment_repository.py`
- Display: `src/adapters/cli/analyze_sentiment_display.py`

**Audit requirements:**

- Verify prediction identity includes ticker, prediction timestamp, classifier/provider/model/rules version, and source-headline set or digest.
- Use publication time and market session cutoff, not fetch date alone.
- Define reference price and 1/3/5 “trading day” outcomes precisely.
- Handle predictions made pre-open, intraday, post-close, weekends, and holidays.
- Adjust or invalidate outcomes crossing corporate actions or bad candles.
- Verify `INSERT OR REPLACE` cannot overwrite a semantically different audit.
- Reconcile unaudited selection and saved outcomes independently.
- Report class balance, coverage, unavailable outcomes, confusion matrix, calibration, and uncertainty; raw accuracy alone is insufficient.
- Separate AI-provider results from offline keyword classifier results.

**Clean-break rule:**

Existing logs/audits without prediction-time provenance or classifier version are not calibration-grade. Quarantine them from reported accuracy rather than inventing metadata.

**Acceptance criteria:**

- [ ] Golden prediction/outcome fixtures match direct candle calculations.
- [ ] Session cutoff tests cover pre-open, intraday, close, weekend, and holiday cases.
- [ ] Duplicate audit writes are idempotent and identity-safe.
- [ ] Statistics exclude invalid/unavailable outcomes and show excluded counts.

### DQ-010 — Quarantine, migrate, rebuild, and prove the clean break

**Priority:** P0  
**Depends on:** DQ-003 through DQ-009 findings resolved  
**Outcome:** Canonical tables contain only artifacts satisfying the corrected contracts.

**Implementation guideline:**

- Produce a dry-run impact report before modifying data.
- Classify every existing observation, label, and sentiment audit as valid, rebuildable, invalid, or unverifiable.
- Prefer immutable quarantine/archive tables or an exported audit bundle over silent deletion.
- Version schemas and artifacts when field meaning or identity changes.
- Rebuild from raw point-in-time-capable sources only.
- Preserve old data solely as explicitly non-canonical historical evidence.
- Make consumers reject old schema versions rather than silently coercing them.
- Compare before/after counts, date coverage, score distributions, label distributions, and readiness.

**Do not interpret “clean break” as:**

- permission to destroy the only copy of raw/user data;
- permission to mutate the production database without backup and approval;
- permission to hide the blast radius;
- permission to fabricate missing provenance;
- permission to retain invalid rows in canonical aggregates.

**Acceptance criteria:**

- [ ] Dry-run report identifies every affected row and reason.
- [ ] Backup/export and rollback instructions are tested.
- [ ] Canonical consumers reject incompatible artifact versions.
- [ ] Rebuilt artifacts pass all golden and reconciliation tests.
- [ ] No invalid/quarantined row contributes to readiness, tuning, or performance metrics.

### DQ-011 — Freeze the corrected baseline and unblock CLI restructuring

**Priority:** P0  
**Depends on:** DQ-000 through DQ-010  
**Outcome:** CLI routing can change without mixing in data/accuracy changes.

Passing DQ-011 unblocks CLI restructuring and empirical evaluation only. It
does not authorize evidence promotion, threshold tuning, or legacy baseline
recertification; those remain governed by the signal-refactor backlog and
`signal_evidence_program.md`.

**Required baseline:**

- canonical command inputs/defaults;
- DTO and JSON schemas;
- stdout/stderr and exit behavior;
- read/write behavior and exact affected artifacts;
- effective-session and provenance fields;
- database reconciliation fixtures;
- representative golden outputs;
- known limitations with quantified blast radius;
- zero unresolved DQ-P0 or DQ-P1 findings.

**Acceptance criteria:**

- [ ] All DQ-P0 and DQ-P1 findings are closed, not merely documented.
- [ ] Every command family has a signed-off data contract and golden fixture.
- [ ] Full audit suite passes on a clean rebuilt database.
- [ ] `tasks/backlog/improvement_cli_restructure.md` CLI-001 may begin.
- [ ] Later CLI old/new equivalence compares against this corrected baseline only.

## 9. Cross-cutting database checks

Every audit must include, where applicable:

- primary/unique key correctness;
- duplicate semantic identities;
- orphaned foreign references;
- null, zero, empty string, NaN, and sentinel use;
- impossible OHLC/volume/value ranges;
- date gaps and duplicate sessions;
- timezone-naive timestamps;
- min/max dates and future-dated rows;
- conflicting source values;
- stale latest-only enrichment in historical artifacts;
- schema-version distribution;
- config/rules hash presence and validity;
- deterministic serialization/fingerprints;
- idempotent writes;
- transactionality on partial failure;
- table/JSON unit and naming consistency.

## 10. Required quality dimensions per command

| Command family | Source accuracy | Point-in-time | Identity | Completeness | Reproducibility | Persistence | Output clarity |
|---|---:|---:|---:|---:|---:|---:|---:|
| Signal backfill | Critical | Critical | Critical | Critical | Critical | Critical | High |
| Signal labels | Critical | Critical | Critical | Critical | Critical | Critical | High |
| Signal replay | High | Critical | Critical | High | Critical | Read-only | Critical |
| Signal readiness | High | Critical | Critical | Critical | High | Read-only | Critical |
| Signal inspection | Critical | Critical | High | Critical | Critical | Read-only | Critical |
| Accumulation evaluation | Critical | Critical | High | Critical | Critical | Explicit CSV only | Critical |
| Sentiment audit | Critical | Critical | Critical | Critical | High | Critical | Critical |

## 11. Architecture impact assessment

| Question | Answer |
|---|---|
| Domain touched during fixes? | Possibly: corrected value objects/identity semantics |
| Application touched? | Yes: session policy, validation, workflow status, label/evaluation rules |
| Infrastructure touched? | Yes: repositories, schema versions, migrations, reconciliation tooling |
| Adapter touched? | Yes: explicit quality/provenance/error output only |
| New external dependency required? | No by default; justify any calendar dependency separately |
| Determinism affected? | Strengthened; same snapshot/config must reproduce the same artifact |
| Persistence changes possible? | Yes; clean schema break/rebuild may be required |
| Adapter policy allowed? | No; status and eligibility remain application-owned |

Required layer plan before each implementation task:

```text
Domain: pure identities/value objects/invariants only
Application: point-in-time policy, validation, orchestration, status, eligibility
Infrastructure: source mapping, repositories, migrations, audit queries
Adapter: input parsing and transparent rendering only
```

## 12. AI usage declaration

No AI may establish ground truth, repair missing provenance, decide validity, or alter labels. AI may assist investigation or explanation only. All audit verdicts and repairs must be deterministic and independently testable offline.

## 13. Risk, signal, and evidence authority constraints

- Patch/tuning eligibility is forced false while any relevant DQ-P0/P1 finding is open.
- Diagnostic evidence cannot be promoted during this backlog.
- Correcting corrupted inputs may legitimately change scores/actions; this is a bug fix, not tuning.
- Any action change caused by a repair must be documented with before/after evidence and blast radius.
- Missing authoritative evidence must reduce readiness/coverage or return unavailable; it must not be silently neutral-filled unless the canonical policy explicitly requires and labels it.
- No corrected dataset may be used to claim edge until untouched OOS evaluation passes.

## 14. Global negative requirements

Do Not Interpret This As:

- Do not freeze current behavior before proving it correct.
- Do not validate only DTO arithmetic while trusting source rows blindly.
- Do not use the live database as the only audit fixture.
- Do not treat current/latest enrichment as historical point-in-time data.
- Do not count weekdays as IDX sessions.
- Do not let incomplete labels enter summaries/readiness.
- Do not let duplicate captures inflate sample size.
- Do not call stored-row retrieval reproducible replay.
- Do not preserve misleading fields, schemas, or tests for compatibility.
- Do not tune thresholds to make corrected results look better.
- Do not silently delete or rewrite user data.
- Do not begin CLI restructuring before DQ-011 passes.

## 15. Testing requirements

Each task must include:

1. Unit tests for pure temporal, identity, label, and validation rules.
2. Repository tests against SQLite with real constraints and migrations.
3. Golden point-in-time fixtures built from truncated source data.
4. Property/invariant tests for OHLC, returns, horizons, identity, and idempotence.
5. Negative tests with future rows, missing sessions, duplicates, stale enrichment, corporate actions, and partial failures.
6. Independent SQL/manual reconciliation tests.
7. Table/JSON/DTO semantic parity tests.
8. Architecture boundary tests.
9. Focused command tests including exit code and stdout/stderr.
10. Full test suite after schema/identity changes.
11. `git diff --check` for every implementation task.

## 16. Required audit deliverables

- Field-level source contract matrix.
- IDX effective-session specification.
- Per-command finding register.
- Reproduction commands and SQL queries.
- Golden point-in-time fixtures.
- Before/after blast-radius report.
- Quarantine/rebuild manifest.
- Corrected schema and artifact-version documentation.
- Verified behavioral baseline consumed by the CLI restructure.
- Explicit list of limitations that remain non-authoritative.

## 17. Final completion gate

This backlog is complete only when:

- [ ] Every authoritative field has verified semantics and temporal availability.
- [ ] All workflows use one IDX effective-session contract.
- [ ] Observations are point-in-time, uniquely identified, reproducible, and idempotent.
- [ ] Labels use complete future session windows and exact observation identity.
- [ ] Replay accurately distinguishes retrieval, recomputation, and drift.
- [ ] Readiness excludes invalid, duplicate, diagnostic, and contaminated samples.
- [ ] Signal inspection reconciles every canonical factor and weight.
- [ ] Accumulation evaluation matches live logic and reports execution/bias assumptions.
- [ ] Sentiment outcomes use correct session timing and prediction identity.
- [ ] Invalid historical artifacts are quarantined or rebuilt and cannot affect canonical metrics.
- [ ] Zero DQ-P0 or DQ-P1 findings remain open.
- [ ] Corrected contracts and golden outputs are frozen for CLI restructuring.
