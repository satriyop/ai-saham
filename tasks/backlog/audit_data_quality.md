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
- DQ-001 acceptance criteria below are **not** marked complete — DQ-001A/C
  now give field contracts for 18 tables (5 core + 13 enrichment) and
  DQ-001B gives executable reconciliation for 4 of the core tables
  (`candles`, `broker_summaries`, `broker_daily_flow`, plus the
  `foreign_flow_points`/`foreign_flow_snapshots` cross-table check).
  `candidate_observations`/`signal_forward_labels` reconciliation, all
  enrichment reconciliation (DQ-001D), and market context/sentiment
  source families remain unaudited.

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

**Acceptance criteria:**

- [ ] One application-layer session service is used by all audited workflows.
- [ ] Weekend, holiday, pre-open, intraday, post-close, and late-provider tests pass.
- [ ] Every persisted artifact distinguishes execution time from effective market session.
- [ ] Temporal leakage tests intentionally plant future rows and prove they are excluded.

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
