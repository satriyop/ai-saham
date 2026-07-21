# Backlog: ruthless data-quality and accuracy audit

## 1. Task metadata

**Task title:** Prove and repair point-in-time correctness for signal observations, labels, replay, readiness, accumulation evaluation, and sentiment outcomes  
**Task type:** Spike / Research followed by Bugfix and Refactor gates  
**Overall priority:** Critical / P0  
**Status:** Active — the executable DQ contract gate currently reports `PASS`,
but authoritative null/zero semantics and canonical artifact provenance remain
unresolved. Canonical observation/label work remains blocked, and sentiment
validation is independently deferred.
**Decision:** Audit the producer-to-consumer chain in the order defined here. Implement this option only.  
**Compatibility policy:** Clean break is allowed. Do not preserve incorrect data, schemas, outputs, or tests merely for backward compatibility.

### Cross-backlog ownership and gates

The authoritative cross-backlog execution sequence lives in
`tasks/backlog/signal_evidence_program.md`.

- This document owns source truth, point-in-time/session correctness, artifact
  data integrity, quarantine/rebuild, and baseline freezing.
- `tasks/backlog/deterministic_signal_engine.md` owns active SignalEngine
  semantic and deterministic-contract work.
- `tasks/backlog/evidence_validation_and_promotion.md` owns deferred empirical
  validation and authority promotion.
- `tasks/backlog/audit_signal_refactor_contract.md` is the detailed task-contract
  appendix shared by those two lanes.
- Data-quality and deterministic-contract completion do not independently
  authorize evidence promotion. The evidence-governance lane requires its own
  evaluation and transition contracts after their prerequisites pass.

This backlog has three gates; do not treat all checklist items in DQ-000..DQ-011
as a prerequisite for repairing signal semantics:

```text
DQ-CONTRACT-GATE = authoritative live-source/time subset of DQ-000 through DQ-002
DQ-BASELINE-GATE = DQ-003 through DQ-008, then DQ-010 and DQ-011
DQ-SENTIMENT-GATE = DQ-009 plus any sentiment-specific DQ-010 cleanup
```

`DQ-CONTRACT-GATE` blocks `LIVE-CONTRACT-GATE` only for defects that can change authoritative
live scoring. Diagnostic-only source defects, repair-command hardening, and
historical leakage proof remain required but instead block canonical capture,
empirical evaluation, tuning, and promotion. BENCHMARK-EXCESS-RETURN, AUTHORITY-COVERAGE-READINESS, artifact identity,
and related live-contract corrections define the schema that DQ-003 onward must
audit and rebuild. `DQ-BASELINE-GATE` unblocks CLI restructuring and empirical
evaluation for the canonical signal and accumulation lifecycle; it does not
authorize threshold tuning or production promotion. `DQ-SENTIMENT-GATE`
independently blocks sentiment calibration and the sentiment CLI migration, not
unrelated signal capture, evaluation, or CLI work.

**Executable `DQ-CONTRACT-GATE` severity semantics** (`saham audit data
contract-gate`, `BuildDQContractGateUseCase`):

- FAIL findings block: the gate reports `status=FAIL` and the CLI exits non-zero.
- WARN findings remain fully visible in the `warnings` array but do not block;
  a WARN-only result is `status=PASS` and exits 0.
- An invalid sub-audit status, or a sub-audit reporting FAIL without a FAIL
  finding, fails closed via a synthetic FAIL blocker.
- The gate never downgrades, hides, or re-classifies a source finding; severity
  ownership stays in the underlying source-contract and reconciliation audits.

Task states use one meaning throughout this file:

- `Done`: every task-owned close criterion is verified by current code/tests or
  an executable clean-data artifact.
- `Active`: implementation is in progress now.
- `Ready`: dependencies pass and the task can start.
- `Blocked`: a named prerequisite is not complete.
- `Deferred`: intentionally outside the active canonical-signal lane.

Do not use `Partial`. Committed preparatory slices are evidence in the task body,
not completion state.

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

Signal and accumulation tasks in `tasks/backlog/improvement_cli_restructure.md`
are blocked until `DQ-BASELINE-GATE` passes. Its sentiment task additionally
requires `DQ-SENTIMENT-GATE`.

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

**State:** Done — read-only audit protection is complete; mutating repair
commands now reject `--apply` without an explicit `--db`, failing before any
configuration load, repository construction, or mutation.

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
- [x] Repair commands default to dry-run, execute transactionally, and require
      explicit `--db` together with `--apply` before mutating data.
- [x] The validation panel and dates are committed as deterministic fixtures or manifests.
- [x] A failed audit cannot partially mutate canonical tables.

### DQ-001 — Establish authoritative source and field contracts

**Priority:** P0  
**Depends on:** DQ-000  
**Outcome:** Each field currently used by the production `setup_quality` or
`institutional_flow` evidence groups has a proven source meaning and
availability contract. Diagnostic/optional fields remain visible without
pretending to be authoritative.

**State:** Done — authoritative source and field contracts are established; missing-vs-zero flow semantics resolved.

**Current production scope:** candles, broker summaries, and tracked-broker
daily flow consumed by `setup_quality` or `institutional_flow`. The remaining
source families below are audited for explicit diagnostic/unavailable status;
they do not block this task unless current production authority consumes them.

**Audit source families:**

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

- [x] Each input currently used by production `setup_quality` or
      `institutional_flow` has a field-level contract and executable invariants
      where its source permits them.
- [x] Semantically equivalent overlaps among current production sources are
      reconciled on sampled and aggregate data; a source without a valid
      counterpart has a provider fixture and an explicit limitation instead.
- [x] Historical fields consumed by the current assessment/replay path that
      cannot be verified point-in-time are diagnostic, unavailable, or excluded
      from authority.
- [x] Missing and real zero values remain distinct throughout current production
      evidence construction, scoring, authority, and persisted fingerprints.
- [x] Canonical persisted fields and public outputs state units and aggregation
      meaning where the current production concept would otherwise be ambiguous.
      Internal legacy table names may rely on an explicit field contract when
      renaming them provides no behavioral safety benefit.
- [x] The live contract gate has no authority-impacting blocker for the current
      production evidence groups.

### DQ-002 — Implement one IDX market-session and effective-time contract

**Priority:** P0  
**Depends on:** DQ-001  
**Outcome:** Current screen, swing, canonical capture, and label-generation
workflows agree on what production evidence was available at a given decision
timestamp.

**State:** Completed — DQ-002 criteria fully satisfied (Criteria 1 satisfied in `fa7413f`, Criteria 3 satisfied in `07bc21c`).

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
- Prove that a T observation excludes future rows from the current production
  evidence sources. A diagnostic source must remain non-authoritative when its
  point-in-time availability is unproven.
- Apply explicit calendar/session semantics to a corporate event only when that
  event is consumed by the current production assessment or label contract.

**Accurate pointers:**

- Session resolver: `src/application/services/effective_market_session_resolver.py`
- Source availability: `src/application/use_case/assess_source_availability_use_case.py`
- Trading-session calendar contracts/providers under `src/domain/ports/` and `src/infrastructure/persistence/`
- Observation contract: `src/domain/ports/candidate_observations_repository.py`
- Candidate persistence: `src/infrastructure/persistence/sqlite_candidate_observations_repository.py`

**Clean-break rule:**

Artifacts without a defensible effective timestamp or data cutoff are invalid for learning and historical evaluation. Do not infer missing temporal provenance from `captured_at` alone.

**Acceptance criteria:**

- [x] One application-layer effective-session contract governs current screen,
      swing, and canonical capture workflows. Label generation inherits and
      validates the originating observation's contract instead of independently
      resolving another session (satisfied in `fa7413f`).
- [x] Weekend, holiday, pre-open, intraday, post-close, and late-provider tests pass.
- [x] Current-schema canonical candidate observations and forward labels require
      execution time, effective market session, and data-cutoff provenance;
      artifacts missing them are excluded from canonical reads (satisfied in `07bc21c`).
- [x] Temporal leakage tests intentionally plant future rows across the current
      authoritative source families and prove they are excluded or
      non-authoritative.

### DQ-003 — Audit and repair historical candidate-observation backfill

**State:** Active — amended 2026-07-21 to a **lean identity contract**: capture
persists an explicit `observation_contract` plus a `semantic_compatibility_id`
derived from a whole-config content hash, and defers the full three-part
`ARTIFACT-IDENTITY` apparatus (auto-detecting material-config registry,
`artifact_id` split, complete provenance, universe-membership platform) behind
named triggers. See "Lean identity amendment (2026-07-21)" below. Slice A of
`tasks/backlog/dq_003_lean_implementation_plan.md` is implemented in commit
`e00b4aa` (criteria 6 and 9 satisfied); Slices B–E remain.

**Priority:** P0  
**Depends on:** DQ-001, DQ-002  
**Outcome:** The first `accumulation-discovery` capture and backfill contract is
an idempotent point-in-time reproduction of what its live universe workflow
could have known. Named `swing-setup` capture is owned by
`NAMED-SWING-SETUP-CAPTURE` in `deterministic_signal_engine.md`.

**Program prerequisite:** `LIVE-CONTRACT-GATE`, including
`ARTIFACT-IDENTITY`. Ordinary `screen` and `analyze` invocations remain
assessment-only and are not observation-capture triggers.

`NAMED-SWING-SETUP-CAPTURE` starts after this task. It must complete before
named-setup labels, readiness metrics, attribution, or tuning claims are
allowed, but it does not block accumulation-discovery labels or this task's
close criteria.

**Accurate pointers:**

- CLI: `src/adapters/cli/analyze_signal_backfill_commands.py`
- Use case: `src/application/use_case/backfill_signal_observations_use_case.py`
- Candidate construction: `src/adapters/cli/screen_accum_workflow_factory.py` and its application dependencies
- Repository: `src/infrastructure/persistence/sqlite_candidate_observations_repository.py`
- Fingerprint services: `src/application/services/accumulation_observation_fingerprint.py` and related modules

**Audit requirements:**

- Compare backfilled T observations with one compact deterministic database
  fixture physically truncated at T. Cover at least one selected ticker, one
  rejected control, one missing/unavailable input, and one planted future row.
- Prove all indicator warm-up windows end at T.
- Prove broker windows contain broker sessions, not calendar approximations.
- Verify current-only enrichment is excluded or explicitly unavailable.
- Verify historical universe membership or record that the run used a current universe and is survivorship-biased.
- Reconcile candidate inclusion/exclusion counts and reasons per date.
- Test idempotence and uniqueness across ticker, effective session, workflow, window, setup/horizon where relevant, config hash, and data cutoff.
- Verify reruns after config changes do not overwrite semantically different observations.
- Validate `captured_at`, `snapshot_date`, `data_as_of_date`, workflow, window, config hash, and payload schema.
- Enforce the **lean identity contract** (amended 2026-07-21): persist an
  explicit `observation_contract` and a `semantic_compatibility_id` computed as
  a SHA-256 of the resolved config-file content plus the schema/engine/evidence
  contract versions. Reuse the existing `semantic_compatibility_id` column and
  codec. Do NOT enumerate a per-path material-config registry, do NOT populate
  `artifact_id` or the full `ArtifactProvenance`, and do NOT put
  `universe_snapshot_id` into any idempotency key. The full three-part
  `ARTIFACT-IDENTITY` apparatus stays parked (built, tested, unwired) until a
  named trigger in "Lean identity amendment (2026-07-21)" fires. Rationale: a
  whole-config hash cannot silently fail to fork on an unregistered path, and
  keeping universe out of the key preserves rerun idempotence.
- Persist the contemporaneous eligible-universe control population as well as
  selected candidates, including inclusion/exclusion state, rejection
  stage/reasons, pre-filter measurements, missing-data state, and rank.
- Implement canonical observation creation through one dedicated application
  capture use case. Reserve the future `saham learn signal capture` adapter
  routes for CLI-003; they are not part of this task's close criteria.
- Implement `accumulation-discovery` first as the selected/rejected/ranked
  eligible-universe observation. Persist its `observation_contract`. Reserve a
  distinct identity for `NAMED-SWING-SETUP-CAPTURE`, but do not implement that
  producer in DQ-003. The two contracts must never overwrite or masquerade as
  one another once both exist.
- Do not admit manually selected single-ticker inspection into the canonical
  population. A future `saham analyze signal inspect TICKER --contract ...`
  path is read-only diagnostic reconstruction and creates no
  observation/readiness row.
- Keep interactive screen/analyze assessment, explicit current-session capture,
  historical backfill, and forward-label generation as separate operations.
  Neither user attention nor invocation frequency may select or weight the
  learning population.
- Report inserted, already-existing, unavailable, rejected, and failed capture
  counts with machine-readable reasons at the ticker/date capture boundary.
  Internal diagnostic warnings do not require a new reason taxonomy. Rerunning
  the same semantic capture must not increase sample size.
- Preserve suspended, delisted, stale, and unavailable names as explicit states;
  do not erase them from evaluation denominators.

**Clean-break rule:**

If canonical identity omits a meaning-changing dimension, replace it and rebuild. Do not retain an upsert key that silently overwrites a different experiment. Purge or quarantine observations produced with leakage, current-only enrichment, unknown config, or invalid date alignment.

**Acceptance criteria:**

- [x] One compact truncated-database fixture matches the canonical semantic
      projection of `accumulation-discovery` backfill output; volatile audit
      metadata is validated separately. (Satisfied by Slice C:
      `tests/application/use_case/test_dq_003_truncated_backfill.py`. A planted
      T+1 row on the selected ticker leaves the captured semantic projection
      byte-identical whether or not it exists — proving the real composed
      capture path bounds reads at T — and `captured_at` is excluded from the
      projection and validated separately.)
- [x] Repeating the same run creates no duplicates or drift. (Satisfied by
      Slice C: a second capture against the same seeded DB adds no canonical
      rows and yields an identical semantic projection.)
- [x] Repeating interactive screen/analyze commands creates no canonical observations.
- [x] Explicit capture is idempotent and separate from forward-label
      generation. (Satisfied by Slice D:
      `test_dq_003_slice_d_fail_closed_separation.py` runs the REAL production
      capture composition with the REAL `GenerateSignalForwardLabelsUseCase`
      always wired — a `generate_labels=False` run writes observations and zero
      labels; a later `generate_labels=True` run over the same dates generates a
      label and leaves the canonical observation count unchanged; and repeating
      a capture-only run adds no canonical rows.)
- [ ] The capture application use case is adapter-independent and ready for CLI-003 wiring.
- [x] `accumulation-discovery` rows carry an explicit `observation_contract`
      and a config-content-hash `semantic_compatibility_id`. The writer rejects
      any non-`accumulation-discovery` contract, reserving a distinct contract
      for `NAMED-SWING-SETUP-CAPTURE` and preventing that later population from
      overwriting or substituting for discovery rows. Implementing the later
      producer, `artifact_id`, and full provenance is explicitly out of scope
      here (see deferral triggers). A config change that alters the resolved
      config content forks the `semantic_compatibility_id`; the same run reruns
      to the same id. (Satisfied by Slice A in commit `e00b4aa`:
      `lean_observation_identity.py`, persister contract-rejection + fail-closed
      write, repository migration 17 column + canonical-read predicate.)
- [x] Single-ticker inspection cannot write or count as canonical learning
      evidence. (Satisfied by Slice D: a behavioral test runs the read-only
      `AccumulationScreenUseCase.execute` for a single ticker against a
      repo-backed DB and asserts `candidate_observations` stays empty — only the
      explicit record/persist use case writes. A wiring guard asserts the
      read-only `create_accumulation_screen_workflow` composition constructs no
      recorder while only `create_accumulation_screen_workflow_bundle` — whose
      sole caller is the backfill capture command — does. No inspection writer
      exists today; the guard keeps it that way.)
- [x] Holiday/retry/failure fixtures prove fail-closed session handling and
      visible errors. **Session handling** (Slice D): a holiday/stale-cache
      decision date resolves to an explicitly *marked* fallback
      (`ihsg_cache_stale_or_holiday`, `is_eod_pending=False`, with a note), and
      that marker propagates end-to-end onto the persisted observation's
      provenance columns; a date with no source candles is skipped with the
      machine-readable `missing_source_candles_for_universe` reason.
      **Write-path failure** (DQ-003 follow-up): the persister no longer
      swallows failures — a `save_many` error (locked DB, `IntegrityError`,
      schema mismatch, malformed canonical object, or any programmer error)
      propagates through the record use case and the backfill loop, so the
      capture aborts visibly (non-zero) instead of reporting a silent 0-count. A
      run can no longer show `evaluated_count > saved_observation_count` from a
      lost write. Proven by
      `test_dq_003_slice_d_fail_closed_separation.py::
      test_backfill_fails_closed_on_save_failure`; the empty-input "nothing to
      do" path still returns 0 without raising. See "Slice D finding
      (2026-07-21)" below — now RESOLVED.
- [x] Changing a semantic identity dimension creates a distinct artifact or
      explicit version replacement. (Satisfied by Slice A in commit `e00b4aa`:
      any resolved-config change forks the `semantic_compatibility_id` cohort
      tag, so a rerun under
      changed config replaces the row and re-stamps its cohort; incompatible
      cohorts stay distinguishable and un-poolable downstream. Forking is via
      the cohort tag, not the upsert key, per the lean amendment.)
- [x] Candidate and control rows share one PIT cutoff but cannot overwrite one
      another. (Satisfied by Slice C: two distinct data-bearing tickers produce
      two distinct canonical identities that both persist under one shared
      `decision_at`/`analysis_as_of` cutoff, and neither collapses/overwrites
      the other. See the Slice C finding below on why the "control" is a second
      evaluated `pass` ticker rather than a `rejected_*` row.)
- [x] Candidate-only datasets are ineligible for screener recall/filter-value
      claims. (Satisfied by Slice E: `BackfillSignalObservationsResponse` carries
      a typed `contains_control_population: bool` — True only if at least one
      observation persisted this run has `screen_result != "pass"` — and a
      machine-readable `recall_eligibility` string, both surfaced in `to_dict()`.
      They are derived from Slice B's existing `rejected_count` aggregation (no
      new read, no persistence/identity change). Under the current production
      capture path every reject gate is disabled (Slice C finding), so
      `rejected_count == 0`, `contains_control_population is False`, and
      `recall_eligibility == "ineligible_candidate_only_no_screen_rejected_control"`
      — eligibility is enforced via the marker and is False (ineligible) under
      the universe-wide-`pass` capture. A downstream recall/precision consumer
      (DQ-006, which owns recall) MUST check `contains_control_population` and is
      blocked while it is False, pending the open design question in the Slice C
      finding. Building the recall consumer is out of scope here.)
- [x] Every ticker/date exclusion or failure at the canonical capture boundary
      has a machine-readable reason; internal diagnostic warnings are out of
      scope. (Satisfied by Slice B: `BackfillSignalObservationsResponse.
      ticker_exclusions` reports, per processed date, each universe ticker that
      produced no observation with the machine-readable reason
      `source_unavailable_not_evaluated`. Per the Slice C finding the production
      path disables every reject gate, so the only real ticker-boundary split is
      evaluated vs unavailable — the taxonomy covers the unavailable side only;
      finer internal diagnostic causes stay out of scope. Existing per-date
      `BackfillSkippedDate` reasons remain machine-readable.)
- [x] Capture reports universe size, evaluated count, selected count, rejected
      count, unavailable count, and universe-membership source identity. When
      historical membership is unavailable, the current-universe survivorship
      limitation is explicit; building a new historical-membership platform is
      out of scope. (Satisfied by Slice B: the response carries `universe_size`,
      `evaluated_count`, `selected_count`, `rejected_count`, `unavailable_count`,
      `universe_membership_source`, and `survivorship_limitation`, aggregated
      from screen results already in hand — no re-query, no persistence change.
      `rejected_count = 0` by construction per the Slice C finding (all reject
      gates disabled), so `selected_count == evaluated_count`; `evaluated_count`
      reconciles with `saved_observation_count`. The adapter passes
      `universe_membership_source = "<universe>@current"`; the use case owns the
      survivorship policy, emitting the current-universe survivorship limitation
      whenever the source ends in `@current`. Building a historical-membership
      platform stays parked per the deferral triggers.)

#### Slice C finding (2026-07-21) — the real capture path never emits `rejected_*`

The golden-fixture proof surfaced a production-behavior fact worth recording so
it is not mistaken for a test compromise. The production backfill composition
(`analyze_signal_backfill_commands.py`) builds its screen request with
`disable_score_filters=True`, and the structural market-cap / Piotroski floors
resolve to `0` (config `min_market_cap_idr = 0`; builder `min_piotroski`
default `0`). All four gates that can emit `screen_result != "pass"`
(structural market-cap, structural Piotroski, foreign-flow score, signal score)
are therefore **off**. The canonical capture path can only ever persist
`screen_result = "pass"`: it captures the entire evaluated universe as
negative-inclusive samples, not a screen-rejected subset.

Consequence: a `rejected_*` canonical observation is not producible via the
real path, so criterion 10's "candidate/control" pair is proven with two
distinct evaluated `pass` tickers (the honest, non-stubbed invariant is
distinct-identity non-overwrite under one PIT cutoff — see the Slice C test).
Faking a `rejected_*` row would require stubbing the engine or enabling a
non-production filter and was deliberately not done.

**Deferral:** if a future consumer (e.g. DQ-006 readiness / screener recall
claims) needs a genuine screen-rejected control population captured as
canonical rows, that requires a product decision — either the backfill must
stop disabling reject gates, or a separate capture mode must be defined. Do not
retrofit it by loosening the golden fixture. Tracked here as an open design
question, not a Slice C blocker.

#### Slice D finding (2026-07-21) — the persister swallows ALL save failures

**Status:** RESOLVED (DQ-003 follow-up, 2026-07-21). The blanket
`except Exception: return 0` was removed; the persister now fails closed. See the
disposition at the end of this subsection. **Original finding (CONFIRMED
fail-soft) retained below for the record.**

`AccumulationCandidateObservationPersister.persist(...)`
(`src/application/services/accumulation_candidate_observation_persister.py`)
wraps `save_many` — and all the preceding evidence-building — in a broad
`except Exception: logger.warning(...); return 0`. A genuine
contract/infrastructure error on the write path (a locked DB, a schema mismatch,
an `IntegrityError`, a malformed canonical object) is therefore converted into
an ordinary 0-count "success". The backfill response then shows
`evaluated_count > saved_observation_count` but carries **no machine-readable
failure marker** — the write loss is silent unless someone diffs the two counts.

This contradicts `AGENT_QUICKSTART.md` §14 ("Define the exception boundary"):
expected provider/data **absence** may degrade to a typed missing/0 result, but
contract, invariant, and programmer errors must propagate and fail closed. The
contract-rejection and `None`-compatibility-id checks already sit *outside* the
try and correctly raise; the `save_many` failure path does not.

Current behavior is pinned by
`tests/application/use_case/test_dq_003_slice_d_fail_closed_separation.py::
test_persistence_failure_is_currently_swallowed_to_zero_count`, so any future
narrowing is a deliberate, tested contract change.

**Disposition (RESOLVED 2026-07-21):** the blanket `except Exception:
logger.warning(...); return 0` wrapping the evidence-assembly + `save_many`
block was **removed entirely** — no allowlist was needed. Investigation
confirmed there is no legitimately-expected exception on this write path: the
evidence builders already degrade missing data to `None` rather than raising,
and the persister only runs on already-enriched candidates. So every exception
here is a contract/infrastructure/programmer error and now propagates and fails
closed. **Capture-failure contract change:** on such an error the capture run
now raises (non-zero exit) instead of returning a silent 0-count; a lost write
aborts the run visibly. The two pre-`try` guards (contract rejection, `None`
compatibility-id) are unchanged, and the genuine "nothing to do" early return
(no repository / no evaluated candidates) still returns 0 without raising. No
score/identity/schema/persisted-shape change, so no version bump. Aborting the
whole run on failure is the accepted behavior; resilient per-`(date, window)`
failure reporting that continues sibling dates is a separate future follow-up,
explicitly out of scope. Behavior pinned by
`test_dq_003_slice_d_fail_closed_separation.py::test_backfill_fails_closed_on_save_failure`
and `test_persister_empty_input_returns_zero_without_raising`; the reversed
best-effort contract is re-pinned by
`test_accumulation_screen_observations.py::test_persistence_failure_propagates_out_of_record_use_case`.

#### Lean identity amendment (2026-07-21)

**Decision:** Implement DQ-003 with a lean identity contract. Implement this
option only.

**What is required now:**

- Persist `observation_contract = "accumulation-discovery"` on every canonical
  row; the capture writer rejects any other contract value.
- Compute `semantic_compatibility_id` as
  `sha256(canonical(resolved_config_content) + schema_version +
  semantic_engine_version + evidence_contract_version)` and store it in the
  existing `semantic_compatibility_id` column via the existing codec.
- Keep the canonical upsert key exactly as today
  (`ticker, snapshot_date, workflow, window_sessions, data_as_of_date,
  config_hash`). `semantic_compatibility_id` is a cohort tag, not part of the
  upsert key, and `universe_snapshot_id` never enters any idempotency key.

**Do Not Interpret This As:**

- Do not enumerate or maintain a per-config-path material registry. Hash the
  whole resolved config content instead.
- Do not populate `artifact_id`, `ArtifactProvenance`, or `universe_snapshot_id`
  in the capture path. Leave those columns empty and the resolver/registry
  parked (marked `# PARKED — not wired; see DQ-003`).
- Do not delete the parked artifact-identity machinery; it is tested and
  trigger-gated for reuse.
- Do not treat over-forking (a cosmetic config edit forking the cohort) as a
  bug. Over-forking is safe; silent under-forking is the failure mode this
  amendment removes.

**Deferral triggers — graduate a parked piece only when its trigger fires:**

| Trigger | Wake this parked piece |
|---|---|
| ML challenger over-forks and wastes training data because immaterial config edits split compatible cohorts | The per-path material-config registry (`signal_semantic_contract.py`) |
| A second producer (`NAMED-SWING-SETUP-CAPTURE`) exists so one compatibility cohort spans multiple captured artifacts | The `artifact_id` vs `semantic_compatibility_id` split + resolver wiring |
| An ML evidence producer is promoted and needs drift monitoring or rollback | Consuming the full `ArtifactProvenance` fields |
| Survivorship must be corrected, not merely disclosed | The historical universe-membership platform |

Until a trigger fires, the corresponding acceptance-criterion obligation is
satisfied by the lean contract above, not by the full apparatus.

### DQ-004 — Audit and repair forward-label generation

**State:** Ready (raw-label slice) — amended 2026-07-22 to a **lean raw-label
contract**: build honest, point-in-time raw market-outcome labels now, and park
net-executable labels (fees, taxes, slippage, price limits, fills, execution
status) behind the `IDX-EXECUTION-LABELS` trigger. Raw labels are sufficient for
`DQ-BASELINE-GATE` research/ML validation, which does not authorize promotion;
execution-net labels are a promotion-lane concern. See "Lean raw-label amendment
(2026-07-22)" below.

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
- [ ] Missing sessions, suspensions, corporate actions, and incomplete windows
      have explicit outcomes. Corporate-action detection uses the local
      `CorporateActionCalendarRepository` (real `STOCK_SPLIT`/`REVERSE_SPLIT`/
      `RIGHTS_ISSUE`/`BONUS` ex-dates in the window), not a jump heuristic; a
      window crossing one is invalidated to `UNAVAILABLE`, never adjusted.
- [ ] Fees, taxes, slippage, price limits, gaps, fills, and timing follow
      `IDX-EXECUTION-LABELS` or the label is explicitly a raw (non-executable)
      market-outcome label. Under the lean amendment, raw labels are canonical
      for research/ML validation and carry an explicit raw-outcome marker;
      net-executable labels are parked behind `IDX-EXECUTION-LABELS`.
- [ ] Label uniqueness cannot attach one outcome to the wrong observation version.
- [ ] Summary use case excludes invalid/unavailable labels by contract.

#### Lean raw-label amendment (2026-07-22)

**Decision:** Implement DQ-004 as an honest raw market-outcome label now.
Implement this option only.

**What is required now:**

- Keep the existing raw outcome computation (close/max-high/min-low returns,
  days-to-peak/trough, target/stop triggers, SUCCESS/FAILURE/NEUTRAL, complete
  future-IDX-session windows, `UNAVAILABLE` on incomplete windows).
- Add corporate-action fail-closed invalidation: if a `STOCK_SPLIT`,
  `REVERSE_SPLIT`, `RIGHTS_ISSUE`, or `BONUS` has an `EX_DATE` inside the label
  window (queried from `CorporateActionCalendarRepository`), the label is
  `UNAVAILABLE` with a machine-readable reason — never a computed distorted
  return.
- Add an explicit raw-outcome marker so no consumer mistakes a raw label for a
  net-of-cost tradeable result.
- Prove every label field against hand/SQL candle math in a golden fixture.

**Do Not Interpret This As:**

- Do not model fees, taxes, slippage, price limits, fills, or execution status
  (`FILLED`/`PARTIAL`/`UNFILLED`/`UNTRADEABLE`). That is parked.
- Do not adjust prices across a corporate action; invalidate the label instead.
- Do not use a price-jump heuristic when the corporate-action calendar has the
  real event.
- Do not claim tradeable/net edge from raw labels; they are research/ML inputs
  only.

**Deferral trigger:**

| Trigger | Wake this parked work |
|---|---|
| A promotion/evaluation task needs net-of-cost tradeable outcomes | `IDX-EXECUTION-LABELS`: fees, taxes, slippage, price limits, fills, execution status, entry-model/exit-model/cost-model versioning, as a distinct net-executable label contract/schema |

**Open design decision (defaulted):** ordinary `DIVIDEND` ex-dates also drop the
close by the dividend amount. Default: invalidate only the four mechanical types
above now; treat dividend-ex distortion as a documented limitation for a
follow-up rather than invalidating otherwise-good labels over typically-small
drops.

**Coverage caveat:** corporate-action invalidation is only as complete as the
local calendar sync. A period with no synced calendar coverage must surface an
explicit "corporate-action coverage unavailable before date D" limitation, not
silently pass unchecked labels as clean.

### DQ-005 — Audit signal replay for reproducibility, not retrieval

**State:** Blocked — waits for canonical observations and labels from DQ-003
and DQ-004.

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

**State:** Blocked — waits for DQ-003 through DQ-005 reconciliation.

**Priority:** P0  
**Depends on:** DQ-003, DQ-004, DQ-005  
**Outcome:** Readiness reflects valid, independent, point-in-time observations and labels—not raw row volume.

**Promotion boundary:** Correct counts are necessary but insufficient for
promotion. The current chronological 70/30 split is diagnostic only. Production
proof additionally requires a compatible `semantic_compatibility_id`, purged
`PURGED-WALKFORWARD-VALIDATION`, `INCREMENTAL-EVIDENCE-EDGE`, and a verified
`PROMOTION-ARTIFACT-INTEGRITY` artifact.

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
- [ ] Mixed semantic compatibility identities are reported separately and cannot be pooled; ordinary provenance diversity remains visible without fragmenting compatible cohorts.
- [ ] No readiness output claims production eligibility from the 70/30 split alone.

### DQ-007 — Audit current SignalEngine inspection accuracy

**State:** Blocked — waits for `LIVE-CONTRACT-GATE`; the gate includes
`RETIRE-LEGACY-SIX-FACTOR-BASELINE`.

**Priority:** P1  
**Depends on:** DQ-001, DQ-002  
**Outcome:** Signal inspection explains the exact canonical engine calculation for a defensible effective session.

**Accurate pointers:**

- CLI: canonical routing is owned by CLI-002 after this task passes
- Use case: new canonical read-only inspection use case owned by this task
- Engine factory: `src/infrastructure/composition/signal_engine_factory.py`
- Config loader: `src/infrastructure/config/signal_engine_config_loader.py`
- Coverage provider: `src/infrastructure/persistence/sqlite_signal_coverage_provider.py`

**Audit requirements:**

- Build one read-only inspection use case that consumes the same prepared
  canonical evidence input and invokes the same canonical scorer as screen and
  swing. It must not reconstruct a parallel composite.
- Independently verify the exact consumed source rows, evidence inputs,
  configured group weights, resolved authority, missing-data behavior, known
  calculation vectors, and final scorer output.
- Verify unavailable/missing evidence cannot inflate authority coverage,
  readiness, or directional conviction.
- Verify there is no executable/displayed legacy six-factor score.
- Prove `--date T` builds a point-in-time context rather than joining latest enrichment.
- Validate factor coverage counts against SQL and distinguish rows from usable rows and unique tickers.
- Display source date, value, unit, freshness, authority, and unavailable reason for every factor.
- Expose effective session, exact provenance, source availability,
  `signal_authority_coverage`, typed setup readiness, decision constraints,
  diagnostic groups, and final canonical assessment.
- Perform no observation, label, tuning, promotion, or config writes.

**Clean-break rule:**

The executable legacy scorer is removed before this audit starts. Do not
preserve or reconstruct a dual score for compatibility. Rename `signal-audit`
semantics to inspection only after canonical correctness is proven.

**Acceptance criteria:**

- [ ] Golden factor calculations match engine output within declared decimal tolerances.
- [ ] Historical dates cannot consume future/current-only values.
- [ ] Missing data cannot increase authority or readiness.
- [ ] Table, JSON, and DTO use identical score/coverage terminology.
- [ ] Inspection consumes the same canonical input/scorer as screen and swing and computes no parallel composite.
- [ ] Inspection is read-only and exposes provenance, availability, authority, readiness, constraints, diagnostics, and final assessment.
- [ ] No legacy six-factor score or active factor-weight surface remains in inspection output.

### DQ-008 — Audit accumulation historical evaluation

**State:** Blocked — waits for DQ-003, DQ-004, and DQ-007.

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
- Record chronological split and overlapping-horizon risks explicitly.
  Promotion-grade purged walk-forward and embargo policy is owned by
  `PURGED-WALKFORWARD-VALIDATION`.
- Mark descriptive, in-sample, validation, and OOS results explicitly.
  Baseline-versus-evidence-challenger edge proof is owned by
  `INCREMENTAL-EVIDENCE-EDGE`.
- Verify CSV and JSON preserve numeric units and exact record identities.

**Clean-break rule:**

Invalidate published metrics produced with leakage, survivorship bias presented as unbiased, mismatched live/backtest rules, or unrealistic execution assumptions. Rename the command to evaluation only after its artifact contract is accurate.

**Acceptance criteria:**

- [ ] Truncated-data live reconstruction matches historical signal generation.
- [ ] Every included/skipped candidate is accounted for.
- [ ] Costs and execution assumptions are explicit in every result artifact.
- [ ] OOS performance is separated from training/validation.
- [ ] Sample size and evaluation role (`DESCRIPTIVE`, `IS`, `VALIDATION`, or `OOS`) are reported without claiming promotion-grade edge.

### DQ-009 — Audit sentiment outcome data independently

**State:** Deferred — activate only when sentiment calibration or the
sentiment-specific CLI migration is requested. It does not block the canonical
signal baseline.

**Priority:** P1  
**Depends on:** DQ-001, DQ-002  
**Outcome:** Sentiment audits bind one time-valid prediction to correct future market outcomes without duplicate or misleading statistics.

**Gate boundary:** DQ-009 is an independent diagnostic pipeline. Until it
passes, sentiment outcomes cannot support calibration, promotion, or the
sentiment-specific CLI migration. It does not block the canonical signal
`DQ-BASELINE-GATE` or unrelated CLI tasks.

DQ-009 does not itself authorize sentiment as canonical evidence. Offline
keyword sentiment is deterministic but remains diagnostic until a separate
deterministic-evidence promotion task passes. AI-classified sentiment is model
output: it remains diagnostic or a separate decision/evidence experiment unless
a future task implements an ADR-042-compliant narrow local-ML evidence producer.
Remote AI/API sentiment output cannot enter the evidence-promotion lifecycle.

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
- [ ] Reports and artifacts distinguish deterministic keyword sentiment from local-model and remote-API classifications
- [ ] No AI/API sentiment result is treated as canonical evidence or promotion proof

### DQ-010 — Quarantine, migrate, rebuild, and prove the clean break

**State:** Blocked — waits for canonical signal findings from DQ-003 through
DQ-008 to close. Sentiment cleanup remains independently gated by DQ-009.

**Priority:** P0  
**Depends on:** DQ-003 through DQ-008 findings resolved; sentiment-specific cleanup may run independently after DQ-009

**Completed AUTHORITY-COVERAGE-READINESS artifact subset (2026-07-18):**
- 19,317 incompatible candidate observations were moved to
  `candidate_observations_quarantine`; the canonical table contains 0.
- 5,760 linked legacy forward labels were moved to
  `signal_forward_labels_quarantine`; the canonical table contains 0.
- Canonical observation, label, readiness, attribution, and tuning consumers
  reject incompatible schema versions rather than coercing them.
- No rebuild was performed because the quarantined artifacts lack the current
  canonical semantic contract.

This completes only the AUTHORITY-COVERAGE-READINESS historical-artifact
requirement. It does not close DQ-010's broader dry-run, rollback, rebuild, and
reconciliation criteria.

**Outcome:** Canonical tables contain only artifacts satisfying the corrected contracts.

**Implementation guideline:**

- Produce a dry-run impact report before modifying data.
- Classify every existing observation and label as valid, rebuildable, invalid,
  or unverifiable. Apply the same process to sentiment audits only in the
  independent sentiment cleanup path after DQ-009.
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

**State:** Blocked — waits for DQ-010 and the corrected canonical baseline
gate.

**Priority:** P0  
**Depends on:** DQ-000 through DQ-008 and the canonical-signal portion of DQ-010

**Outcome:** CLI routing can change without mixing in data/accuracy changes.

Passing DQ-011 unblocks CLI restructuring and empirical evaluation only. It
does not authorize evidence promotion, threshold tuning, or legacy baseline
recertification; those remain governed by
`evidence_validation_and_promotion.md` and `signal_evidence_program.md`.

**Required baseline:**

- canonical command inputs/defaults;
- DTO and JSON schemas;
- stdout/stderr and exit behavior;
- read/write behavior and exact affected artifacts;
- effective-session and provenance fields;
- database reconciliation fixtures;
- representative golden outputs;
- known limitations with quantified blast radius;
- zero unresolved authoritative-signal or accumulation DQ-P0/P1 findings unless
  the affected data is explicitly enforced as non-authoritative.

**Acceptance criteria:**

- [ ] Every authoritative signal or accumulation DQ-P0/P1 finding is fixed, quarantined, or explicitly enforced as non-authoritative; accepted diagnostic limitations remain visible.
- [ ] Every canonical signal and accumulation command family covered by the CLI restructuring map has an executable data contract and representative golden fixture.
- [ ] The DQ-011-scoped audit suite passes on a clean rebuilt database.
- [ ] `tasks/backlog/improvement_cli_restructure.md` CLI-001 may begin.
- [ ] Later CLI old/new equivalence compares against this corrected baseline only.

DQ-011 does not authorize the sentiment-specific CLI migration. That migration
also requires DQ-009 and any resulting sentiment cleanup to pass.

### Solo-project proportionality

- Keep DQ-000 through DQ-002 narrow: executable source/time contracts and
  fail-closed behavior are required; a generic data-governance platform is not.
- DQ-003 and DQ-004 are mandatory because biased populations or incorrect
  labels invalidate every later conclusion. Implement one observation contract
  and one label policy before generalizing.
- DQ-005 through DQ-008 require representative golden fixtures and independent
  reconciliation, not exhaustive reproduction of every historical ticker/date.
- DQ-009 is optional and independent until sentiment calibration is explicitly
  requested.
- DQ-010 repairs only artifacts proven incompatible by the preceding tasks. Do
  not build a generic migration registry.
- DQ-011 freezes only the canonical commands and schemas needed by the planned
  CLI work; it is not a release-management system.
- Property tests, manual SQL, and full-suite runs apply when their failure mode
  is relevant. They are not mandatory checkbox theater for every small change.

## 9. Cross-cutting database checks

Every audit must evaluate the following dimensions and include only those that
apply to the affected artifact or command:

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
- Do not begin signal or accumulation CLI restructuring before DQ-011 passes;
  sentiment CLI restructuring additionally requires DQ-009.

## 15. Testing requirements

Each implementation task must select verification proportional to its affected
layers and failure modes. The following are required where applicable, not as
mandatory ceremony for every task:

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

- Field-level source contract matrix for authoritative inputs.
- IDX effective-session specification.
- Per-command finding record for actual DQ-P0/P1 defects.
- Reproduction commands or SQL for each recorded defect.
- Representative golden point-in-time fixtures.
- Before/after blast-radius report when behavior or persisted data changes.
- Quarantine/rebuild manifest when rows are removed or rebuilt.
- Corrected schema and artifact-version documentation when identity changes.
- Verified canonical behavioral baseline consumed by the CLI restructure.
- Explicit list of limitations that remain non-authoritative.

## 17. Final completion gate

The canonical `DQ-BASELINE-GATE` is complete only when:

- [ ] Every field that can affect canonical signal authority has verified
      semantics and temporal availability.
- [ ] All canonical signal, capture, label, replay, readiness, inspection, and
      accumulation-evaluation workflows use one IDX effective-session contract.
- [ ] Observations are point-in-time, uniquely identified, reproducible, and idempotent.
- [ ] Labels use complete future session windows and exact observation identity.
- [ ] Replay accurately distinguishes retrieval, recomputation, and drift.
- [ ] Readiness excludes invalid, duplicate, diagnostic, and contaminated samples.
- [ ] Signal inspection reconciles every canonical factor and weight.
- [ ] Accumulation evaluation matches live logic and reports execution/bias assumptions.
- [ ] Invalid historical artifacts are quarantined or rebuilt and cannot affect canonical metrics.
- [ ] Zero DQ-P0 or DQ-P1 findings remain open.
- [ ] Corrected contracts and golden outputs are frozen for CLI restructuring.

The independent `DQ-SENTIMENT-GATE` is complete only when:

- [ ] Sentiment outcomes use correct session timing and prediction identity.
- [ ] Invalid sentiment artifacts cannot affect sentiment calibration metrics.
- [ ] DQ-009 and any sentiment-specific DQ-010 cleanup pass.
