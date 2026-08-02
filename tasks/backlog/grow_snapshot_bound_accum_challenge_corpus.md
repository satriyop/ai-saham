# Grow The Snapshot-Bound Accum Challenge Corpus

Status: `IN_PROGRESS_CONTRACT_HARDENING`

## Locked design decision (2026-08-02) — lookback / compatibility identity

**Option A — Producer attestation (selected for this task).**

- `pit_tradable_lookback_sessions` is persisted on each observation’s typed
  `population_binding`, validated with exact integer types (no coercion), and
  required to be **identical across every current-authority observation in a
  compatibility cohort**, along with other cohort-invariant population fields
  (contract, name, named-universe identity/tickers, tradability contract,
  benchmark, binding schema version).
- Session-dependent fields (PIT membership digest/session/tickers) may differ.
- Document explicitly: `compatibility_id` is an **opaque producer-fork stamp**.
  This task does **not** cryptographically reverse or prove lookback from that
  hash. Authority is typed producer attestation + cohort consistency, not
  identity-material reversibility.
- Do not hardcode lookback `10`, consult live YAML as historical authority, or
  introduce an immutable cohort-identity artifact (Option B) in this task.

## Locked design decision (2026-08-02) — ACCUM label integrity discovery (v1)

**Bounded-anchor model for ACCUM readiness label authority (selected for this
task; not an implementation-only exception).**

ACCUM readiness detects label corruption when **at least one** authoritative
scope anchor survives:

1. **Requested parent identity** — dual-key on column and `artifact_json`
   `observation_id` for the ACCUM observations under evaluation;
2. **Expected label identity** — deterministic `label_id` recomputed from each
   parent × allowed label contracts;
3. **ACCUM label contract** — dual-key on column and `artifact_json`
   `contract_id` for exactly:
   - `price_path.accum_3d.v1`
   - `price_path.accum_10d.v1`
   - `price_path.accum_20d.v1`

Every candidate found through **any** of those anchors is fully validated
(recon, digest, `label_id` identity) before filtering. Invalid ACCUM labels
fail closed.

**Purpose isolation (normative):** PRE_OPEN / other purposes must not abort
ACCUM readiness. `price_path.open_30m.v1` is **outside** the ACCUM readiness
candidate union. Unrelated PRE_OPEN corpus health is not ACCUM authority.

**Explicit out-of-scope for readiness (v1):** simultaneous corruption of **all**
scope anchors (parent ID, label ID, **and** ACCUM label contract) is outside
ACCUM readiness detection. That class of failure belongs to a **separate
corpus-wide integrity/audit mechanism**, or a future schema-level purpose
binding / external immutable inventory. This task **must not** close by
pretending readiness can detect all-anchor mutation under pure bounded SQL
discovery.

**Forbidden without a new task/ADR:** whole-table label scans on the ACCUM
status hot path that break purpose isolation; inventing a silent inventory;
claiming all-anchor detection without inventory/purpose-binding design.

## Locked Decisions (2026-08-02/03) — market-session authority for path labels

Authoritative market-session source for ACCUM path labels and readiness:

| Dimension | Lock |
|---|---|
| Contract | `stockbit.trading_sessions.ihsg_history.v1` |
| Meaning | A **successfully completed, strict Stockbit IHSG historical query** defines observed market-session dates for its requested range. **Not** official IDX calendar authority. Stockbit is the source. |
| Artifact | Immutable `TradingSessionCalendarSnapshot` (snapshot_id, contract, source, benchmark, coverage, ordered_sessions, source_revision, captured_at, payload_digest) persisted in `trading_session_calendar_snapshots`. |
| Writer | Strict Stockbit probe → write repository only on fully validated responses. Status never writes and never contacts Stockbit. |
| Read-only repository | `SQLiteTradingSessionCalendarSnapshotReadRepository` (`mode=ro`, no schema ensure). Load **by snapshot_id bound on each label**, never “latest”. |
| Completeness | Every pagination page must succeed. Partial results after errors are forbidden. Empty complete range is allowed. Unexplained local IHSG cache holes prove nothing without a snapshot. |
| Label metrics schema v3 | `calendar_snapshot_id`, `calendar_contract_id`, `calendar_source_revision`, `label_window_sessions`, `label_window_digest` = digest({snapshot_id, label_contract, signal_date, sessions}). **Do not** hash growing full-cache coverage. |
| Producer/validator | Same snapshot identity. Producer binds labels to one snapshot; readiness reloads that exact snapshot and rechecks first-N + digests + revision. |
| Observation payload versions | Accum **11** / binding **2**; pre-open **10**. |

Cron/application order: strict Stockbit calendar sync → persist snapshot → generate labels → read-only readiness status.

Source: code-first cross-repo product-gap audit on 2026-07-31.

Companion consumer task:

- `~/dev/ml-saham/tasks/backlog/close_accum_challenge_decision_coverage_gaps.md`

## 1. Task Metadata

- Task type: producer operations + bounded contract extension
- Priority: Critical
- Primary owner: `ai-saham`
- Semantic classifications by checkpoint:
  - P0 corpus readiness/status reporting: `NON_SEMANTIC`
  - P1 prospective capture/label operations: `NON_SEMANTIC` unless current
    executable capture meaning must change
  - P2 sector-breadth decision: documentation audit only in this task. A future
    activation is at least `CONFIG_MATERIAL` + `SEMANTIC_ENGINE`; its snapshot
    follow-up requires a separate explicit architecture/task contract.
  - P3 Action/readiness coverage: `OBSERVATION_SCHEMA` only if the current typed
    payload cannot represent the required states; no bump merely to improve
    prospective coverage
- This task-file creation is documentation-only and `NON_SEMANTIC`.
- Chosen decision: keep the single existing
  `run_signal_observation_corpus_write` producer used by `research accum
  capture|backfill`, grow one LQ45 snapshot-bound cohort, and extend `research
  accum status` for producer readiness. Diagnose Action/readiness transport but
  never alter live policy to manufacture density. Do not implement a sector-
  breadth snapshot until a separate architecture task first establishes an
  actual production policy. Implement this option only.

Sequencing guard: the corpus PIT, tradable-universe, risk-cutoff, and v2
snapshot prerequisites are complete. Treat them as foundations, not work to
repeat. Current unrelated TUI/shared-adapter worktree changes are out of scope;
stage and commit only files owned by this task.

## Locked Decisions (2026-08-01)

1. **P2 does not authorize v3.** Current production composition roots do not
   pass `idx_groups` into `AccumulationScreenUseCase`; therefore
   `_ticker_to_group` is empty and the breadth applier is skipped. The rule is
   configured and unit-tested in isolation, but is not established as active
   production behavior. No `production_policy_snapshot.v3`,
   `lean_accumulation_compatibility.v3`, eight-row set, or learning migration 4
   may be implemented from this task.
2. **P0 readiness is a producer handoff gate, not fold authority.** The exact
   status rules and the intentionally non-identical ml-saham mapping are locked
   below.
3. **PIT backfill is allowed.** It must execute the current canonical producer
   for previously unwritten past sessions using PIT inputs and the active
   binding. It must create new immutable rows; it may not copy, rebind, mutate,
   or attach snapshots to legacy observations.
4. **Operational universe is LQ45 only.** Use `--universe lq45` and preserve the
   recorded PIT membership source. Universe expansion is a separate population
   contract and is not part of this task.
4b. **Population authority for ACCUM challenge inputs (locked 2026-08-01).**
   Choose **Option A: typed persisted binding on the observation. Implement this
   option only.** There is no authoritative historical LQ45 constituency store
   to support B, and C would make readiness depend on that nonexistent store.
   The honest population is today's configured LQ45 roster intersected with
   candle-active PIT tradability for the observation session; it is **not** a
   claim that the system reconstructs historical LQ45 index membership.
   - Typed contract: `population.accum.lq45_current_roster_pit_tradable.v1`.
   - Pure type: `AccumPopulationBinding`; final writer:
     `AccumulationCandidateObservationPersister`; orchestration owner:
     `BackfillSignalObservationsUseCase`; storage owner: the existing
     `LearningObservationRepository` inside `decision_payload.population_binding`.
     Do not add a population warehouse or a second repository in this task.
   - Exact binding fields: `schema_version=2`, the contract ID above,
     `population_name=lq45`, `membership_session` equal to the observation
     session, `membership_digest` equal to outer `universe_id`, positive
     `membership_count`, attested sorted `membership_tickers` and
     `named_universe_tickers` with membership ⊆ named roster,
     `named_universe_digest` over the sorted configured LQ45 roster used by the
     run, `tradable_membership_contract=pit_tradable.candle_presence.v1`, material
     `pit_tradable_lookback_sessions`, `benchmark_symbol=IHSG`, and non-empty
     `producer_source_revision`.
   - `universe_id` remains
     `artifact_digest({"tickers": sorted(resolved_membership)})`. Readiness
     revalidates the typed binding, equality/linkage to the observation, and
     exact contract fields. This is producer-attested authority protected by
     the immutable observation digest; it is not an independent reconstruction
     or cryptographic proof of external origin.
   - Classification: `OBSERVATION_SCHEMA`, not `NON_SEMANTIC`. Current
     accumulation payload schema is
     `ACCUMULATION_OBSERVATION_PAYLOAD_SCHEMA_VERSION=11` (attested ticker sets;
     incomplete schema-10 is non-current). Pre-open remains on
     `PRE_OPEN_OBSERVATION_PAYLOAD_SCHEMA_VERSION=10` and must not silently
     inherit accumulation-only population bumps. Lean compatibility folds the
     accumulation payload version only. Keep
     `learning_observation.accumulation_discovery.v2`,
     `accumulation-discovery.v2`, and `production_policy_snapshot.v2`; no SQLite
     migration, snapshot v3, dual write, or compatibility alias is authorized.
   - Existing schema-9 observations without `population_binding` remain
     immutable historical corpus and project as `LEGACY_RAW_ONLY`, including
     their old compatibility cohorts. Incomplete schema-10 (pre-attested tickers)
     is also non-current / `LEGACY_RAW_ONLY`. A schema-11/current-cohort row with a
     missing or invalid binding is `BLOCKED_POLICY`. Never rewrite schema-9 rows
     or attach a binding after the fact.
5. **P3 is diagnose plus bounded repair.** Produce a root-cause report and fix
   transport only if an already-computed typed value is lost. Data density grows
   through P1 operations. Any change to live Action/readiness policy or inputs
   that changes production behavior requires a separate task.
6. **Code-complete and operations-complete are separate states.** After P0/P1/
   P3 code and documentation merge, set this task to
   `CODE_COMPLETE_AWAITING_DATA`. Move it to `tasks/done/` only after the
   explicit LQ45 cohort produces the companion ml-saham report with at least
   two valid post-embargo OOS folds.
7. **Parallel order is allowed.** P0 and P1 implementation may proceed together;
   P3 diagnosis may run against the current v2 cohort in parallel. P0 types and
   fail-closed tests must land before the new cron wrapper is activated. P2 is
   outside that execution path and does not block P0/P1/P3 code work.

## 2. Problem Statement

`ai-saham` now writes a coherent v2 accumulation cohort with seven verified
production snapshots before observations. The current live data still cannot
support broad production challenge verdicts:

- the largest historical cohort has 1,890 observations across 42 sessions but
  zero v2 snapshots and must remain ineligible;
- the active v2 cohort has 304 observations from only one session, so the
  sibling protocol yields one valid OOS fold and stays `INCONCLUSIVE`;
- current v2 observations contain zero ENTER and only 11/304 non-null setup
  readiness values;
- the observation payload already has production Action/trade setup and typed
  setup-readiness fields, so inventing a parallel readiness schema would create
  a second source of truth;
- sector breadth is configured and the pure applier can mutate Accum score, but
  current production factories do not supply `idx_groups`; the executable path
  therefore skips the applier. ADR-059's exclusion is currently honest, and a
  production counterfactual would be false authority until the live-policy
  decision is made separately.

The missing snapshots on the historical cohort are not repairable metadata.
They are absent because the cohort predates the active producer contract.
Attaching today's policy to those rows would fabricate point-in-time authority.

## 3. Desired Outcome And Ordered Checkpoints

### P0 - truthful producer readiness status

Extend the existing `saham research accum status` application result and thin
CLI rendering. For every explicit compatibility cohort, report in table and
JSON:

- exact compatibility ID, observation contract, observation count, distinct
  session count, and economic-date range;
- snapshot binding contract, verified snapshot count, required count, and exact
  missing/extra/invalid policy IDs;
- H3/H10/H20 label counts by AVAILABLE/insufficient-horizon/conflict state;
- Action distribution from the frozen observation payload;
- setup-readiness present/missing counts and typed state distribution;
- explicit operator classification: `LEGACY_RAW_ONLY`,
  `BLOCKED_POLICY`, `COLLECTING`, or `CHALLENGE_INPUT_READY`.

`CHALLENGE_INPUT_READY` means producer contracts and minimum operational inputs
are present; it is not an ML verdict. `ml-saham` alone determines valid folds
and challenge readiness under its protocol.

Apply status precedence and exact rules as follows:

| Producer status | Exact rule |
|---|---|
| `LEGACY_RAW_ONLY` | Observations exist, but their binding is absent, unknown, or historical/non-active and no snapshot corruption is present. Zero snapshots on the 1,890-row legacy cohort is this state. |
| `BLOCKED_POLICY` | The cohort claims the active binding but its closed snapshot set is partial, mixed, malformed, digest-invalid, semantically unsupported, or bound to a different purpose/observation contract/compatibility ID. Any conflicting snapshot rows also produce this state. |
| `COLLECTING` | The exact active snapshot set verifies, but the cohort has fewer than two distinct economic sessions or zero AVAILABLE primary H10 labels. |
| `CHALLENGE_INPUT_READY` | The exact active snapshot set verifies, there is at least one observation across at least two distinct economic sessions, and at least one primary `price_path.accum_10d.v1` label is AVAILABLE. |

H3 and H20 counts are reported but do not gate producer readiness. Action and
setup-readiness distributions are reported but do not gate P0; the ml-saham C4
task owns their protocol-specific support threshold.

Producer and consumer vocabularies intentionally differ:

| ai-saham producer status | ml-saham interpretation |
|---|---|
| `LEGACY_RAW_ONLY` | `BLOCKED_POLICY` for active production-baseline challenges |
| `BLOCKED_POLICY` | `BLOCKED_POLICY` |
| `COLLECTING` | `BLOCKED_DATA` or `INCONCLUSIVE_DEPTH`, selected by the ml protocol reason |
| `CHALLENGE_INPUT_READY` | eligible for ml `READY_FOR_PROTOCOL`; ml may still return `INCONCLUSIVE_DEPTH` or another fail-closed verdict |

### P1 - snapshot-bound capture, PIT backfill, and labels

Use only the shared `run_signal_observation_corpus_write` path for scheduled and
manual capture/backfill. The end-to-end producer chain remains:

```text
resolved typed production policies
  -> one AccumulationProductionPolicyBundle
  -> EnsureAccumulationPolicySnapshotsUseCase (atomic closed set)
  -> BackfillSignalObservationsUseCase / RecordAccumulationObservationsUseCase
  -> immutable learning_observations
  -> research accum labels --all-label-contracts
  -> immutable learning_outcome_labels
```

Required operating behavior:

- capture the active compatibility cohort across independent market sessions
  and regimes using LQ45 PIT membership/cutoffs;
- allow bounded historical backfill only by re-running the current canonical
  producer for previously unwritten sessions with reconstructable PIT inputs;
- preserve original `session_date`, `captured_at`, provenance, and immutable
  observation identity so backfill cannot masquerade as an old live capture;
- ensure the complete current snapshot set before each observation write;
- label every compatibility cohort independently for H3/H10/H20 as horizons
  mature;
- surface partial/failed scheduled runs; do not report success from a subset;
- keep capture idempotent and preserve exact original rows on rerun;
- document the cron/runbook that invokes capture and labels, including expected
  status output and recovery from an interrupted run.

Replace the two independent accumulation cron success surfaces with one exact
operator wrapper, `scripts/cron_accum_challenge_corpus.sh`, invoked by one
`install_cron.sh` entry after EOD data refresh. It must use
`set -euo pipefail` and run, in order:

```text
research accum capture --universe lq45 --session <economic-session> --format json
research accum labels --all-label-contracts --format json
research accum status --format json
```

The wrapper exits non-zero on any command failure and emits its final completion
marker only after all three commands succeed. No external alerting integration
is required in this task; the cron exit status, one log, and final status JSON
are the operator surface. `COLLECTING` is a successful run state, not a command
failure.

Producer merge and operational sufficiency are separate checkpoints. Do not
mark P1 operationally complete merely because code/tests pass. Record live
session/label growth until the companion ml task reports at least two valid
post-embargo OOS folds for the explicit cohort.

### P2 - decided: retire production bonus; no snapshot implementation here

The current executable production contract is:

- `sector_breadth_enabled` defaults/configures true, but production composition
  does not provide `idx_groups`, so the applier is skipped;
- isolated applier semantics use conglomerate/group membership from
  `config/idx_groups.yaml`, not the sector-universe index;
- a ticker maps to one group and later YAML iteration wins on overlap;
- breadth is the fraction `[0,1]` of surviving group members whose
  `net_buy_ratio > 0` for the screen window;
- groups below `sector_breadth_min_tickers` receive a computed
  `sector_breadth_pct` but zero bonus; unmapped/disabled execution leaves
  `sector_breadth_pct = None` and bonus `0.0`;
- the applier runs after signal assessment and before risk/sort, so even if
  wired its current mutation would alter displayed/ranking Accum score without
  recomputing the already-produced signal assessment.

These facts made P2 a semantic-design question, not a missing snapshot row.
ADR-062 resolves it by retiring the current conglomerate-group breadth bonus
from production policy. The seven-row v2 snapshot stays exact, and this corpus
task must not add, infer, or backfill a breadth policy row.

Any future group/sector breadth diagnostic is a new contract, not activation of
the retired bonus. It must first lock the actual concept, membership source and
PIT identity, overlap rule, population, unavailable behavior, and corpus
provenance. It remains diagnostic-only until separate out-of-sample evidence
and an explicit promotion decision exist. Do not reserve or implement v3
strings speculatively.

Architecture decision task:

- `tasks/backlog/decide_accum_group_breadth_production_authority.md`

### P3 - diagnose Action/readiness coverage and repair transport only

First prove why readiness is absent on current rows using the production call
path. Do not solve sparse data by synthesizing READY, coercing `None`, or adding
an adapter-only duplicate.

The current owning path remains the assessed signal/trade setup serialized into
the one observation payload. Preserve one source of truth:

- Action comes from the frozen production candidate/trade-setup result;
- readiness comes from typed `SetupPhaseReadiness` on the assessed signal;
- missing readiness remains explicit absence with recorded reason where the
  domain contract provides one;
- downstream status reads the stored payload and never recomputes today's
  Action/readiness.

If a traced production path fails to transport an already-computed typed value,
fix that end-to-end transport and add lineage/call-count tests. If readiness is
legitimately unavailable because its PIT inputs are absent, improve the
producer-owned PIT input/capture operation only through a separately classified
task; do not invent values or broaden this implementation.

P3 code completion requires a checked-in root-cause note with measured
denominators for each absence cause, plus transport tests and a fix only when
lineage is broken. It has no numeric ENTER/readiness density target. P1
operations grow sessions/regimes, while the companion ml-saham C4 protocol
decides when class support is sufficient.

Do not activate the parked named-swing-setup capture merely to increase counts.
That is a distinct population/observation contract. P3 concerns the existing
ACCUMULATION_DISCOVERY payload only.

## 4. Non-Goals

- No policy tournament, rank IC, fold engine, WIN/LOSE, or factor verdict in
  `ai-saham`.
- No `research accum evaluate` revival; it remains dropped for this product.
- No fabricated snapshot backfill for legacy observations.
- No observation rewrite, compatibility alias, dual write, current-policy
  fallback, or historical reinterpretation.
- No imports from `ml-saham` and no writes by `ml-saham` to the shared DB.
- No automatic production config change or ML-driven promotion.
- No change to live Signal, Risk, TradeSetup, Action, group mapping, or sector-
  breadth behavior inside this task.
- No user-selected ticker population or interactive command writing canonical
  observations.

## 5. Architecture Impact Assessment

```md
Layer plan:
- Domain: producer-readiness DTO/status contract in P0; preserve existing typed
  Action/readiness authority. No sector-breadth identity in this task.
- Application: cohort readiness projection, existing capture/label orchestration,
  atomic snapshot ensure, and exact typed-value transport.
- Infrastructure: bounded read projections for status; no schema migration or
  new snapshot contract in this task.
- Adapter: extend `research accum status`; existing capture/backfill/labels
  commands remain thin composition roots.
```

Foundation checkpoint: P0 status types and fail-closed tests must land before
the new cron wrapper is activated. P0/P1 may otherwise develop together and P3
diagnosis may proceed in parallel. P2 has no runtime implementation here.

## 6. Authority And Data Contracts

- `ai-saham` is the sole writer/owner of observations, labels, policy snapshots,
  market inputs, and the shared SQLite schema.
- `ml-saham` is the read-only challenge consumer and owns panels/protocols/
  verdicts/artifacts.
- Grain remains one observation per ticker/session with windows 7/30/90 as
  features and H10 as the primary path horizon.
- Cohorts never mix. Every snapshot/observation/label query binds purpose and
  compatibility ID.
- Economic date and available-at cutoff are the observation session and its
  recorded PIT execution context.
- Missing, unavailable, insufficient horizon, malformed contract, and conflict
  are different states. None may be converted to numeric zero or success.
- The status path is bounded/read-only and must not repair or materialize data.

### 6.1 Mandatory Readiness Authority Matrix

This matrix is normative for P0 readiness. An implementer must reconcile every
cell against the current DTO, production writer, repository reader, and negative
tests before editing. A valid digest proves immutable content consistency; it
does not by itself prove identity, producer origin, PIT meaning, or semantic
eligibility.

#### 6.1.1 ACCUM label readiness discovery (v1 authority lock)

This cell is **task authority**, not an implementation footnote. It binds the
repository reader used by `GetAccumulationProducerReadinessUseCase` / `research
accum status`.

| Dimension | Lock |
|---|---|
| Scope | ACCUM readiness label candidate discovery only (not corpus-wide audit) |
| Surviving-anchor rule | Corruption is in-scope for readiness when **at least one** of these anchors survives: (1) requested parent `observation_id` (column **or** JSON), (2) expected `label_id` for parent × allowed contracts, (3) ACCUM label `contract_id` dual-key for exactly `price_path.accum_3d.v1` / `accum_10d.v1` / `accum_20d.v1` |
| Validation | Every candidate found through any surviving anchor is fully validated (column↔artifact recon, digest, `label_id` identity) before parent filtering |
| Fail-closed ACCUM | Invalid ACCUM-family candidates → integrity error / `BLOCKED_POLICY`; never silent skip as immature horizon |
| Purpose isolation | PRE_OPEN family `price_path.open_30m.v1` is **outside** the ACCUM candidate union; PRE_OPEN corpus health must not abort ACCUM status |
| Out of scope (v1) | Simultaneous corruption of **all** scope anchors (parent ID, label ID, **and** ACCUM contract) is **not** readiness-detectable under bounded SQL; belongs to a separate corpus-wide integrity/audit mechanism or a future inventory/purpose-binding design |
| Forbidden without new task/ADR | Whole-table label scans on ACCUM status hot path; inventing an inventory to “close” all-anchor detection silently; claiming all-anchor detection under pure bounded discovery |

Implementer note: code comments in
`sqlite_learning_artifact_repository._list_labels_with_identity_discovery` must
remain consistent with this table. Do not widen or narrow discovery without an
authority update here.

| Artifact / boundary | Authority owner and source | Exact identity dimensions | Integrity proof | Semantic contract checks | Missing state | Invalid / conflicting state | May contribute to readiness when |
|---|---|---|---|---|---|---|---|
| Accumulation observation | `AccumulationCandidateObservationPersister` using `build_session_observation_payload`; stored by the ai-saham learning observation repository | `stable_learning_id(learning_observation.accumulation_discovery.v2, {purpose=ACCUMULATION_DISCOVERY, policy_contract=accumulation_discovery.policy.v1, horizon_contract=accum_10d, compatibility_id, cutoff_at, universe_id, window_id})`; `window_id={UPPER_TICKER}:{YYYY-MM-DD}`; outer `schema_version=LEARNING_SCHEMA_VERSION`; payload `schema_version=CANDIDATE_OBSERVATION_SCHEMA_VERSION` | Independently recompute `observation_id` and `artifact_digest`; stored outer columns must agree with the serialized identity and payload | Exact `artifact_type=accumulation_session_observation`, `workflow=research_accum_capture`, `canonical_window=7`, `horizon_primary=accum_10d`, and exact feature keys `7,30,90`; payload ticker/date must equal `window_id`; parsed `shared.provenance.decision_at` must equal outer `cutoff_at`; `latest_completed_session` and `analysis_as_of` must equal the payload/window economic session; payload `captured_at` must equal outer `captured_at`; all datetimes must be timezone-aware and canonical | No observation is `COLLECTING`; a missing required field on an existing active row is not ordinary absence | Any ID, digest, schema, contract, ticker/session/cutoff, capture timestamp, provenance, or envelope mismatch is `BLOCKED_POLICY`; the row contributes zero sessions, counts, Actions, readiness values, or label eligibility | Every identity, integrity, schema, semantic, provenance, and PIT check passes |
| Population / universe binding | `BackfillSignalObservationsUseCase` constructs `AccumPopulationBinding` from the configured `lq45` roster, `resolve_pit_tradable_membership`, material lookback, session, and producer revision; `AccumulationCandidateObservationPersister` writes it into the observation payload; existing observation repository owns storage | Exact `population.accum.lq45_current_roster_pit_tradable.v1`, binding schema **2**, attested sorted `membership_tickers`/`named_universe_tickers` with membership ⊆ named, `population_name=lq45`, membership session, membership/count/digest, configured-roster digest, tradable algorithm contract, lookback, IHSG benchmark, and producer revision; outer `universe_id=membership_digest=artifact_digest({"tickers": sorted(resolved_membership)})` | Observation digest covers the complete typed binding; readiness validates every exact field, subset, and cross-field equality. The binding is a producer attestation, not an external historical-constituency lookup. A 64-hex shape alone is never sufficient | Population meaning is exactly current configured LQ45 roster intersected with candle-active membership over the material N-session window ending at the observation session. Do not call it reconstructed historical LQ45 membership. Different resolved membership digests are allowed across sessions under this one contract | Schema-9 and incomplete schema-10 observations are immutable non-current rows (`LEGACY_RAW_ONLY`); missing/invalid binding on a schema-11/current-cohort row is `population_authority_unbound` and `BLOCKED_POLICY` | Free-form labels, membership outside named roster, arbitrary hash-shaped values without the complete binding, wrong contract/name/session/algorithm/lookback/benchmark, digest/count mismatch, or missing revision fail closed and contribute zero authority | The complete schema-2 binding passes, agrees with the schema-11 observation and its session/universe identity, and the cohort uses the exact population contract |
| Accumulation path label | `GenerateAccumulationPricePathLabelsUseCase`; immutable ai-saham label repository | `stable_learning_id(exact_label_contract, {observation_id, contract_id})`; outer `schema_version=LEARNING_SCHEMA_VERSION`; allowed family is exactly `price_path.accum_3d.v1`, `price_path.accum_10d.v1`, or `price_path.accum_20d.v1`; H10 is primary | Independently recompute `label_id` and `artifact_digest`; recompute producer fingerprint as `artifact_digest({observation_id, decision_digest=observation.artifact_digest, label_contract})`; verify linkage to a fully validated observation and uniqueness of `(observation_id, contract_id)` | `outcome_basis=PRICE_PATH_ONLY`; `AVAILABLE` outcome is exactly `SUCCESS|FAILURE|NEUTRAL` and carries the production metric schema/units; `UNAVAILABLE` has `outcome=None` and a supported `unavailable_reason`; label window begins after the authoritative observation session and contains exactly the contract's 3/10/20 market sessions; entry reference equals frozen `shared.current_price` | Immature horizon or missing inputs creates no terminal row and is reported as insufficient horizon; a supported terminal `UNAVAILABLE` remains distinct from missing | Wrong schema/family/basis/outcome/fingerprint/metrics/window/linkage, cross-observation labels, and any duplicate/conflicting row at any path horizon are `BLOCKED_POLICY`; none may be counted | The label passes every check, belongs to a fully validated observation, and its horizon/state is permitted by the readiness rule; only an AVAILABLE H10 label grants the minimum-label gate |
| Production policy snapshot set | `EnsureAccumulationPolicySnapshotsUseCase` from the same resolved `AccumulationProductionPolicyBundle` used by capture; ai-saham snapshot repository is sole writer | Exact `production_policy_snapshot.v2` seven-policy closed set from ADR-059; `schema_version=LEARNING_SCHEMA_VERSION`; snapshot ID formula from ADR-059 over purpose, observation contracts, compatibility ID, and policy ID | Recompute snapshot ID and canonical-payload digest; verify payload metadata against columns; verify atomic unique closed set, one common `material_config_hash`, and the exact compatibility ID supplied by the observation cohort | Exact purpose, observation bindings, policy IDs/versions, decision types, semantic engine contracts, descriptors, and supported v2 contract; source revision non-empty; v1 remains historical-only | No set or a historical v1-only set is `LEGACY_RAW_ONLY`; partial active v2 is not missing-data collection | Unsupported schema, mixed v1/v2, extra/missing/duplicate row, split material hash, bad digest/ID, descriptor mismatch, or wrong cohort binding is `BLOCKED_POLICY` | All seven v2 rows form one coherent active production identity and every row passes schema, identity, integrity, and descriptor checks |
| Cohort readiness projection | `GetAccumulationProducerReadinessUseCase` plus pure `project_cohort_readiness`; never an adapter or ml-saham | Explicit `purpose=ACCUMULATION_DISCOVERY` and one exact `compatibility_id`; population identity is the validated population binding above; no implicit latest-cohort selection or cross-cohort pooling | Consume only rows validated by the preceding matrix rows; repository/deserialization success is not validation; invalid rows may appear only in diagnostics and contribute zero authority | Precedence is `BLOCKED_POLICY` before `LEGACY_RAW_ONLY` before `COLLECTING` before `CHALLENGE_INPUT_READY`; diagnostics such as Action/readiness distributions never grant status | Verified active set with fewer than two authoritative economic sessions or zero AVAILABLE valid H10 labels is `COLLECTING` | Any authority-bearing corruption in any observation, population binding, label, or active snapshot row is `BLOCKED_POLICY` | Exact active snapshot set passes, all consumed artifacts pass, there are at least two authoritative economic sessions, and at least one valid AVAILABLE primary H10 label exists |
| Repository / status transport | `LearningObservationRepository`, `LearningOutcomeLabelRepository`, `LearningPolicySnapshotRepository`; concrete status path is `SQLiteLearningArtifactReadRepository`; CLI is formatting only | Exact persisted primary keys and all serialized identity/contract/schema/provenance fields above | Validation occurs in the application readiness boundary after typed deserialization; status path must be opened read-only and tests must prove no schema ensure, migration, repair, insert, update, or fallback read | Deserialization is not authority verification; repositories and adapters may not synthesize defaults, translate retired aliases, select a replacement cohort, or suppress malformed rows | Missing table/file/row is surfaced through the task's exact legacy/collecting/error contract; it is never repaired by status | Query, schema, serialization, duplicate, or contract errors propagate or become the exact fail-closed status specified above | The application receives the exact requested rows through the permitted bounded read path and all upstream matrix checks pass |
| ml-saham export / reopen / promotion | ml-saham artifact writer plus authoritative read-only lookup of ai-saham `learning_policy_snapshots`; ml-saham owns protocol artifacts, never production rows | Exact supported artifact schema; explicit cohort/population identity; production policy/snapshot ID and digest; adapter/protocol/baseline/challenger/source revision identities | Format checks are diagnostic only; `validate_verified_production_identity(..., conn=<required read-only DB>)` must re-resolve the snapshot ID/digest from ai-saham's authoritative store | Historical/static/diagnostic artifacts cannot acquire current production eligibility; `baseline=production` requires verified v2 authority; no v1 fallback and no auto-promotion | Missing DB authority or historical artifacts remain display-only/ineligible | Unsupported schema, missing DB authority, wrong population/cohort, or snapshot mismatch blocks reopen/promotion | Current production identity verifies against the authoritative DB and every ml-saham protocol/promotion gate independently passes |

### 6.2 DTO Field Classification And Implementer Stop Rule

The implementer must expand this inventory if a DTO gains fields. No field may
silently disappear from review.

| DTO / artifact | `IDENTITY` | `INTEGRITY` | `SEMANTIC_CONTRACT` | `DIAGNOSTIC` / operational | `IRRELEVANT` |
|---|---|---|---|---|---|
| `LearningObservation` | `observation_id`, `contract_id`, `purpose`, `policy_contract`, `horizon_contract`, `compatibility_id`, `cutoff_at`, `universe_id`, `window_id` | `artifact_digest` | `schema_version`, `decision_payload` including ticker/session/schema/workflow/horizon/windows/price/provenance/captured timestamp | outer `captured_at` is operational timing but must equal payload capture provenance | none |
| `LearningOutcomeLabel` | `label_id`, `contract_id`, `observation_id` | `artifact_digest`, `fingerprint` | `schema_version`, `outcome_basis`, `availability`, `outcome`, `metrics` | `labeled_at` is operational and intentionally digest-excluded | none |
| `ProductionPolicySnapshot` | `snapshot_id`, `contract_id`, `purpose`, both observation contract IDs, `compatibility_id`, `policy_id` | `payload_digest`, `material_config_hash`, `canonical_payload` | `schema_version`, `policy_version`, `decision_type`, `semantic_engine_contract_id` | `source_revision`, `created_at` are provenance and intentionally identity-excluded, but remain required and well-formed | none |
| `CohortProducerReadiness` | `compatibility_id`, `observation_contract` | nested validation reports and verified snapshot set | `producer_status`, authoritative session/label minimums | date ranges, distributions, presence/missing counts | none |
| `TradingSessionCalendarSnapshot` | `snapshot_id`, `contract_id`, `source`, `benchmark`, coverage bounds, `ordered_sessions`, `source_revision` | `payload_digest`, recomputed snapshot ID, normalized-column equality vs `artifact_json` | exact Stockbit contract/source/IHSG benchmark; complete strict acquisition | `captured_at` (required, timezone-aware; excluded from content digest) | none |

**Mandatory implementation rule:** the population decision is Option A exactly
as locked above. Do not substitute B/C, a new warehouse, shape-only hash
validation, historical-LQ45 wording, or an adapter-built dictionary. Implement
the typed application/domain transport and schema-11 / binding-schema-2 clean
break (incomplete schema-10 remains non-current). Add mutation tests for every
matrix dimension and prove each invalid artifact contributes zero sessions,
labels, or readiness.

### 6.3 Clarifications For Completion And Further Work

1. Further fail-closed readiness hardening, operations, documentation, and tests
   are allowed. New authority claims must implement the matrix exactly. The task
   remains `IN_PROGRESS_CONTRACT_HARDENING` and must not claim `CODE_COMPLETE`
   until all matrix rows—including the Option-A population binding—pass.
2. Every check in the matrix is a hard P0 blocker, not a deferred follow-up.
   This explicitly includes label fingerprint recomputation, provenance
   `decision_at == cutoff_at`, payload/outer `captured_at` equality, exact path
   horizon/session semantics, and entry reference equality with frozen
   `shared.current_price`.
3. Any multi-row path-label group for H3, H10, **or H20** is cohort-level
   `BLOCKED_POLICY`, even when a clean H10 label exists elsewhere. Auxiliary
   horizons do not grant readiness, but a conflict in them proves corpus
   integrity failure and is not diagnostic-only.
4. Merge and operations remain separate gates:
   - code may become `CODE_COMPLETE_AWAITING_DATA` only after the fully resolved
     matrix is implemented, all mutation tests and required gates pass, and the
     scoped changes are committed/merged;
   - operational DONE still requires multi-session corpus growth and an
     ml-saham report with at least two valid post-embargo OOS folds.

## 7. Failure And Exception Contract

- Config generation changes while policy objects resolve: fail before any
  snapshot or observation write.
- Partial/mismatched/unsupported snapshot set: rollback/fail before observation
  writes; no warning-and-continue.
- Observation identity conflict: fail explicitly and preserve the existing row.
- Label digest conflict: report conflict/non-zero failure; never overwrite.
- Missing mature horizon: typed insufficient/unavailable state, not FAILURE.
- Expected missing PIT provider data may become the owning typed unavailable
  result only where the current domain contract declares it.
- Malformed canonical payload, impossible identity/provenance, repository
  corruption, and programmer errors propagate and fail closed; broad exception
  handling must not convert them to ordinary missing data.
- Status formatting failure must not mutate data.

## 8. Production Composition Roots

Implementation must inspect and test every current root, including:

- `research accum capture` -> `run_signal_observation_corpus_write`;
- `research accum backfill` -> the same shared function;
- scheduled/cron capture and all-label generation scripts;
- `research accum labels --all-label-contracts`;
- `research accum status`;
- `create_accumulation_screen_workflow_bundle` and
  `AccumulationScreenUseCase` sector-breadth wiring;
- `EnsureAccumulationPolicySnapshotsUseCase` and the atomic repository method;
- schema installation/migration and clean-break/audit manifests.

Tests must prove object/row lineage and call counts, not only equal values. A
second config read that validates byte identity is allowed; a second independent
policy resolve or mutable copy is not.

## 9. Testing Expectations

Require independent tests for:

- status happy path plus legacy zero-snapshot and partial-snapshot cohorts;
- exact observation/session/date/snapshot/label/Action/readiness counts;
- no status writes and no implicit cohort pooling;
- idempotent capture and labels across multiple independent sessions/cohorts;
- partial snapshot atomic rollback and config-generation drift;
- immutable legacy rows and rejection of invalid active bindings;
- a composition-root regression test proving current production does not claim
  sector-breadth authority without an explicit future activation task;
- Action/readiness transport lineage and forbidden recomputation/synthesis;
- scheduled composition-root wiring and surfaced partial failure.

For Python changes, close with:

```bash
pytest <focused paths> -q
pytest -m "not tui"
pytest -m tui                 # if any TUI/shared surface is touched
ruff check src/ tests/
ruff format --check src/ tests/
git diff --check
```

Run the Data Contract Audit Gate and relevant `saham audit data ...` checks.
For broad persistence/config work, run the full suite before completion unless
an exact blocker is recorded.

## 10. Acceptance Criteria

- [x] Task-author decisions in the mandatory readiness authority matrix are
      resolved, including Option-A population semantics and historical-row state.
- [ ] Implementation is reconciled against every matrix cell and consumed DTO
      field; all required mutation tests prove invalid rows contribute zero authority.
- [x] `research accum status` exposes explicit per-cohort snapshot/session/
      label/Action/readiness readiness without computing ML verdicts.
- [x] Snapshot-bound capture/backfill and labels grow one active compatible LQ45 cohort
      across independent sessions without rewriting legacy data.
      (code path + cron includes sync-session-calendar; live multi-session growth is ops)
- [ ] Operational completion records a companion ml report with at least two
      valid post-embargo OOS folds; code merge alone is not operational DONE.
- [x] P2 records the configured-but-unwired breadth finding and creates no v3,
      eight-row set, lean-v3 identity, or migration 4.
- [x] Existing typed Action/readiness is transported and measured without a
      duplicate schema, synthesis, or current-time recomputation.
- [x] No accum evaluate revival, sibling import, auto-promotion, or ML verdict.
- [x] Focused, architecture/data, full relevant, Ruff, and diff gates pass
      (3 pre-existing non-tui failures unrelated to this task recorded).
- [x] BOUNDARY, operator/cron, status/CLI, and companion task docs are
      updated with real completion evidence.
- [x] Unrelated shared-worktree changes are preserved.

## 11. Do Not Interpret This As

- Do not attach today's snapshots to the 1,890-row historical cohort.
- Do not make missing policy a warning or select a different/latest cohort.
- Do not mutate v2 to add sector breadth or keep old/new dual writes.
- Do not create `production_policy_snapshot.v3`,
  `lean_accumulation_compatibility.v3`, or migration 4 from this task.
- Do not parse sector-breadth YAML independently in an adapter.
- Do not treat more rows from one session as more independent folds.
- Do not synthesize ENTER/readiness or reinterpret `None` as a class.
- Do not activate named-setup capture as an ACCUM discovery shortcut.
- Do not implement challenge scoring or production changes here.

## 12. Agent Execution Instructions

Before editing, read the repository harness, BOUNDARY, ADR-056, ADR-059,
current capture/label/status/snapshot code and tests, cron/install paths, the
companion ml task, and inspect both worktrees. Restate hard invariants, forbidden
interpretations, exact files/composition roots, semantic classifications, and
the foundation checkpoint.

Stop if current code contradicts the locked producer chain. Do not implement P2
live scoring or snapshot changes; both require a separate architecture/task
contract after product-owner approval.

## 13. Completion Record

```text
Completed date (code gate): REOPENED 2026-08-02 (still open)
Task status: IN_PROGRESS_CONTRACT_HARDENING

Authority locks recorded this cycle (required before any CODE_COMPLETE claim):
  - § Locked design decision — lookback Option A (producer attestation)
  - § Locked design decision — ACCUM label integrity discovery (v1 bounded anchors)
  - § 6.1.1 ACCUM label readiness discovery (v1 authority lock table)
  These are task authority, not implementation-only comments.

CODE_COMPLETE_AWAITING_DATA eligibility rule for this reopen:
  - May be claimed only after independent review accepts the locked bounded-anchor
    exception (above) as intentional task authority AND remaining code gates pass.
  - Must NOT be claimed solely because the implementation already matches the rule.
  - Operational multi-session growth + ml-saham ≥2 OOS folds remain separate
    (operational DONE / move to tasks/done/).

Open before CODE_COMPLETE_AWAITING_DATA:
  - Independent review acceptance of §6.1.1 bounded-anchor ACCUM label discovery
  - Operational AWAITING_DATA (live multi-session cohort + companion OOS folds)

Closed under the bounded-anchor model (implementation + tests; authority now explicit):
  - ACCUM/PRE_OPEN label purpose isolation (e1fae445)
  - Global observation/snapshot integrity before classify
  - Combined ACCUM label parent/ID mutation fails closed
  - Invalid PRE_OPEN label does not abort ACCUM status
  - Invalid ACCUM label still fails closed
  - ml-saham pack seal, concurrent publication, exact identities, v4 promote evidence

P2 configured-but-unwired finding recorded: YES (no v3)

CODE_COMPLETE_AWAITING_DATA: NOT claimed until §6.1.1 authority is accepted by review
Operational DONE: still requires live multi-session growth + ml-saham OOS folds
```
