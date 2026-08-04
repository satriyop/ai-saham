# Activate A Snapshot-Bound Cohort For The Screen Hard-Filter Tournament

Status: `DONE`

Priority: **High** — required before `ml-saham` can run a verified
`baseline=production` screen hard-filter tournament.

Source: code-first follow-up to the completed
[`parked_screen_filter_replay_contract.md`](parked_screen_filter_replay_contract.md)
(archived COMPLETED in `tasks/done/`),
ADR-056, and ADR-059 on 2026-07-31. Locked clarifications incorporated 2026-07-31
after pre-implementation vet.

Primary owner: **`ai-saham`** — production hard-filter policy identity,
compatibility-cohort authority, observation capture, and policy-snapshot writer.

Downstream owner: **`ml-saham`** — read-only snapshot verification, offline
counterfactual replay, folds/metrics, and tournament verdicts.

## 1. Task Metadata

- Task type: Feature / architecture-contract amendment / clean-break cohort
- Priority: High
- Semantic classification: `NON_SEMANTIC` for live behavior because no
  predicate, configured value, score, gate result, or Action changes. The task
  introduces a new production-policy artifact contract and deliberately forks
  corpus compatibility identity. `OBSERVATION_SCHEMA` is **not required by the
  chosen design** because the ADR-056 ticker/session payload meaning and shape
  remain v2.
- New snapshot artifact contract: `production_policy_snapshot.v2`.
- New policy ID: `screener.accum.hard_filters`.
- Compatibility decision: fold the exact snapshot-binding contract ID into the
  lean accumulation compatibility hash via a versioned canonical-JSON framing.
  Do not bump the observation payload to v3 merely to force a cohort fork.
- Completion model: **two checkpoints** (producer merge vs operational DONE).

## 2. Problem Statement

The hard-filter replay extractor is complete and returned
`SUFFICIENT_FOR_REPLAY`, but a verified tournament remains blocked by two
production-identity gaps.

First, ADR-059's immutable `production_policy_snapshot.v1` set contains six
score/signal/risk rows but no policy row for the four application screen
filters being challenged:

1. market-cap floor;
2. Piotroski floor;
3. accumulation-score floor;
4. signal-score floor.

Consequently, `ml-saham` can replay hypothetical floors but cannot honestly
identify a hard-filter baseline as verified production policy.

Second, the current lean compatibility ID does not include the policy-snapshot
binding contract. Running capture/backfill after the v1 exporter landed can
insert snapshot rows under the same compatibility ID already used by the
1,890-row historical v2 cohort. Because snapshot lookup is cohort-wide, that
would make rows produced before the snapshot-bound composition path appear
retrospectively verified. This contradicts ADR-059's rule that historical
cohorts without snapshots remain ineligible and that snapshots must not be
fabricated or inferred for old observations.

This is an activation-contract defect, not a missing rejected/control-population
bug. Adding capture-time rejected rows is not the remedy.

## 3. Desired Outcome

- ADR-059 is amended with `production_policy_snapshot.v2`.
- Snapshot v1 remains immutable: exactly six rows with its existing bindings.
- Snapshot v2 contains exactly seven rows: the six existing policies plus
  `screener.accum.hard_filters`.
- The seventh row is assembled from the same resolved typed default screen
  hard-filter policy used to construct the canonical live `screen accum`
  request. It is not reconstructed from raw YAML in an adapter.
- The hard-filter payload records the exact four filter values, enabled states,
  first-match order, missing-data behavior, and provider-unavailable branches.
- The lean compatibility identity uses a versioned canonical-JSON framing that
  includes the snapshot-binding contract, yielding a new cohort even when
  resolved YAML and engine semantic versions are otherwise unchanged.
- New observation IDs include the new compatibility ID through the existing
  `LearningObservation` identity formula. Old observation rows remain unchanged.
- Capture/backfill atomically ensures all seven v2 snapshots before writing the
  first observation in the new cohort. Producer writes **v2 only** after cutover
  (no dual-write v1).
- Producer code/ADR is mergeable after temporary-DB tests, full suite, Ruff,
  data audits, and migration tests. The backlog task stays `IN_PROGRESS` until
  live operational activation completes (section 11.2).
- `ml-saham` consumer task is amended now to v2/seven (implementation separate);
  active production challenges accept snapshot v2 only.
- No live floor is retuned and no tournament WIN/LOSE result is produced here.

## 4. Non-Goals

- No screen-rejected/control capture mode.
- No change to the negative-inclusive forward-outcome corpus policy.
- No observation payload v3 while the ADR-056 ticker/session payload meaning
  and shape remain unchanged.
- No rewrite, deletion, migration, relabeling, or reinterpretation of existing
  v2 observations or v1 policy snapshots.
- No threshold-grid selection, folds, embargo, minimum N, winner metric, or
  tournament artifact implementation in `ai-saham`.
- No persistence of one row per threshold, fold, filter combination, or
  tournament run in the shared SQLite database.
- No production configuration change and no automatic application of an
  `ml-saham` result.
- No inclusion of `min_net_buy_days`; it remains the broker-observability
  precondition and is not one of the four challenged hard filters.
- No inclusion of risk gates, setup gates, display-only thresholds, sorting,
  ranking, sector breadth, `min_streak`, `vwap_only`, or `squeeze_only` in the
  new hard-filter policy row.
- No relocation of market-cap ownership off the live path in this task (see
  §5.3).
- No dual-write of v1 snapshots under the new compatibility ID.
- No sibling Python imports in either direction.
- No AI, model, provider, or network dependency.

## 5. Hard Contract Decisions

### 5.1 Immutable v1 and exact v2 set

Do not mutate the meaning or closed-set validation of
`production_policy_snapshot.v1`.

Add `production_policy_snapshot.v2` with exactly these seven IDs:

| `policy_id` | `decision_type` | Policy version |
|---|---|---|
| `screener.accum.score_weights` | `score` | existing `v1` |
| `signal.accum.evidence_group_weights` | `score` | existing `v1` |
| `signal.accum.flags` | `score` | existing `v1` |
| `signal.accum.classification` | `score` | existing `v1` |
| `risk.accum.hard_gates` | `gate` | existing `v1` |
| `signal.accum.raw_score` | `score` | existing `v1` |
| `screener.accum.hard_filters` | `gate` | `v1` |

The artifact contract version and each individual policy version are separate
identities. Do not rename unchanged policies to policy version v2 merely because
the closed snapshot set gains a seventh row.

The new hard-filter semantic contract ID is exactly:

```text
screen.accum.hard_filters.v1
```

### 5.2 Exact hard-filter payload

The canonical payload for `screener.accum.hard_filters` must include at least
these machine fields with no prose-only substitute:

```text
policy_id = screener.accum.hard_filters
policy_version = v1
decision_type = gate
semantic_engine_contract_id = screen.accum.hard_filters.v1
formula_id = accumulation_screen.first_match_hard_filters.v1
scope = canonical_default_screen_accum

first_match_order =
  1. market_cap
  2. piotroski
  3. accum_score
  4. signal_score

filters.market_cap.enabled
filters.market_cap.floor_idr
filters.market_cap.missing_action
filters.market_cap.provider_unavailable_action
filters.market_cap.provider_exception_action

filters.piotroski.enabled
filters.piotroski.floor
filters.piotroski.missing_action
filters.piotroski.provider_unavailable_action
filters.piotroski.provider_exception_action

filters.accum_score.enabled
filters.accum_score.floor
filters.accum_score.missing_action

filters.signal_score.enabled
filters.signal_score.floor
filters.signal_score.missing_action

explicitly_excluded = [min_net_buy_days]
```

#### Enabled rules (locked)

```text
market_cap.enabled = floor_idr > 0
piotroski.enabled  = floor > 0
accum_score.enabled = configured enabled flag
signal_score.enabled = configured enabled flag
```

Default production values (current live defaults; largely non-selective):

```text
market_cap    floor_idr=0     enabled=false
piotroski     floor=0         enabled=false
accum_score   floor=0.0       enabled=true
signal_score  floor=45.0      enabled=false
```

Piotroski `0` comes from the canonical CLI/TUI default request contract
(`DEFAULT_MIN_PIOTROSKI`). CLI overrides (`--min-piotroski`,
`--min-foreign-flow-score`, `--min-signal-score`) are invocation-specific and
must not mutate the frozen default snapshot. This task does not add
per-invocation snapshot rows.

#### Closed missing/action vocabulary (locked)

```text
pass_without_evaluation
rejected_flow
rejected_signal
raise_contract_error
propagate_provider_error
```

| Filter | Disabled | Missing value | Provider unavailable |
|---|---|---|---|
| Market cap | `pass_without_evaluation` | `rejected_flow` | `pass_without_evaluation` |
| Piotroski | `pass_without_evaluation` | `rejected_flow` | `pass_without_evaluation` |
| Accum score | `pass_without_evaluation` | `raise_contract_error` | N/A |
| Signal score | `pass_without_evaluation` | `rejected_signal` | N/A |

Also record:

- fundamentals-provider **exception** → `propagate_provider_error` (not ordinary
  missingness);
- structural filters are **skipped entirely** when the fundamentals provider
  object is absent (`AccumulationCandidateStructuralFilter`); missing
  fundamentals reject only when the provider exists and returns no usable value;
- `accum_score` is a required typed float in production. Offline payload
  missingness for tournament extract remains `unextractable_contract`, not a
  production rejection classification.

Implementation must verify these behaviors against:

- `AccumulationCandidateStructuralFilter` for market cap and Piotroski;
- `AccumulationCandidateSignalAssessor` for accumulation and signal scores.

Do not copy the payload shape while guessing values. Derive floors and enabled
states from one typed default hard-filter policy object shared with canonical
default screen request construction.

### 5.3 One typed authority path (market-cap ownership preserved)

There is **one configured authority** for market cap, not two:

```text
YAML: accumulation_screener.screener.min_market_cap_idr
  → load_swing_policy_config() → SwingPolicyConfig.min_market_cap_idr
  → BuildSignalObservationScreenRequest / AccumulationScreenHardFilterPolicy
```

Therefore:

- snapshot market-cap floor from `swing_policy.min_market_cap_idr` (live path);
- identify material source as `accumulation_screener.screener.min_market_cap_idr`;
- do **not** add a second independently parsed value on
  `AccumulationScreenerConfig`;
- construct the typed hard-filter policy once from existing typed inputs.

Moving ownership off this path is a later clean refactor and is **out of scope**.

Introduce or extract one immutable application-owned type:

```text
AccumulationScreenHardFilterPolicy
  min_market_cap_idr
  min_piotroski
  min_accum_score
  min_accum_score_enabled
  min_signal_score
  min_signal_score_enabled
```

Include it **inside** `AccumulationProductionPolicyBundle`:

```text
hard_filter_policy: AccumulationScreenHardFilterPolicy
```

Ownership path (may not fork):

```text
resolved typed configs + canonical default request policy
  -> one AccumulationScreenHardFilterPolicy
      -> AccumulationProductionPolicyBundle.hard_filter_policy
          -> snapshot payload assembly (pre-neutralization)
          -> BuildSignalObservationScreenRequest / default live screen
              -> capture may derive neutralized copy for corpus inclusion
```

Corpus invocation:

```text
production bundle
  ├─ hard_filter_policy → snapshot payload
  └─ hard_filter_policy → request builder
                              └─ capture derives neutralized copy
```

The snapshot always consumes the pre-neutralization object. Do not inject an
independently built hard-filter policy in parallel.

Adapters may wire the object. They must not interpret YAML, calculate enabled
states, choose missing actions, or assemble snapshot payloads.

### 5.4 Non-circular clean cohort fork (canonical JSON framing)

Replace delimiter-free string concatenation for lean accumulation compatibility
with this exact algorithm (contract
`lean_accumulation_compatibility.v2`):

```python
material = canonical_json(
    {
        "contract_id": "lean_accumulation_compatibility.v2",
        "resolved_config_canonical": resolved_config_canonical,
        "candidate_observation_schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION,
        "semantic_engine_version": SEMANTIC_ENGINE_VERSION,
        "evidence_contract_version": EVIDENCE_CONTRACT_VERSION,
        "policy_snapshot_binding_contract": "production_policy_snapshot.v2",
    }
)
compatibility_id = "sha256:" + sha256(material.encode("utf-8")).hexdigest()
```

`canonical_json` means the existing learning-artifacts helper:

```text
ensure_ascii=true
allow_nan=false
sort_keys=true
separators=(",", ":")
UTF-8 bytes
```

Frozen golden vector (current engine versions as of task lock):

```text
resolved_config_canonical = "x: 1\n"
candidate_observation_schema_version = 9
semantic_engine_version = "1.5"
evidence_contract_version = "1.5"
policy_snapshot_binding_contract = "production_policy_snapshot.v2"
```

Exact canonical bytes:

```json
{"candidate_observation_schema_version":9,"contract_id":"lean_accumulation_compatibility.v2","evidence_contract_version":"1.5","policy_snapshot_binding_contract":"production_policy_snapshot.v2","resolved_config_canonical":"x: 1\n","semantic_engine_version":"1.5"}
```

Expected result:

```text
sha256:5b2849a0e60d2cfe880fc8e65d6f1ab10f9668ed2676a1379fc7d2e8255837f2
```

Requirements:

- do **not** preserve the delimiter-free v1 hash algorithm as an alias,
  fallback, or dual-path reader;
- the same inputs remain deterministic;
- changing only the binding contract from v1→v2 forks the compatibility ID;
- snapshot payload digests remain projections and are **not** folded into the
  compatibility ID;
- the observation payload and learning observation contract remain
  `learning_observation.accumulation_discovery.v2` /
  `accumulation-discovery.v2`;
- every snapshot row and observation written in the new path uses the exact
  same newly resolved compatibility ID;
- existing compatibility IDs and observations remain byte-for-byte unchanged
  and cannot be selected as verified snapshot-v2 cohorts.

This is a deliberate compatibility clean break. Do not add a reader alias,
fallback, translation, auto-upgrade, or `latest/largest cohort` selection.

### 5.5 Snapshot contract identity (enum + create)

Add explicit enum members:

```text
PRODUCTION_POLICY_SNAPSHOT_V1 = production_policy_snapshot.v1
PRODUCTION_POLICY_SNAPSHOT_V2 = production_policy_snapshot.v2
```

(Replace the current single `PRODUCTION_POLICY_SNAPSHOT` name with the v1
member; keep the string value identical so historical IDs recompute.)

Make `ProductionPolicySnapshot.create()` receive the contract **explicitly** —
no hardcoded/default v1.

For v2 rows:

```python
stable_learning_id(
    LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V2,
    identity,
)
```

Integrity validation must recompute using `snapshot.contract_id`. Historical v1
rows and IDs remain unchanged. `LEARNING_SCHEMA_VERSION` remains `1`; the row
shape has not changed.

### 5.6 Schema migration v3 (explicitly required)

Existing DBs have:

```sql
contract_id TEXT NOT NULL CHECK (contract_id = 'production_policy_snapshot.v1')
```

Changing only `CREATE TABLE IF NOT EXISTS` is insufficient.

Implement migration version **3** under the learning migration namespace as one
transaction:

1. rebuild `learning_policy_snapshots`;
2. keep `schema_version CHECK (schema_version = 1)`;
3. widen only `contract_id` to:

```sql
CHECK (
  contract_id IN (
    'production_policy_snapshot.v1',
    'production_policy_snapshot.v2'
  )
)
```

4. preserve existing columns and
   `UNIQUE (purpose, compatibility_id, policy_id)`;
5. copy rows using explicit column names;
6. verify before/after row counts and contents;
7. drop/rename/recreate the cohort index atomically;
8. run `foreign_key_check`.

Coexistence of v1 and v2 rows relies on the compatibility-ID fork (same
`(purpose, compatibility_id, policy_id)` cannot hold two contracts). Do not
change the unique key to include `contract_id`.

### 5.7 Producer cutover and atomic write order

After cutover, capture/backfill writes **exactly seven**
`production_policy_snapshot.v2` rows under the new compatibility ID.

- No dual-write v1.
- No v1 rows under the new compatibility ID.
- V1 remains readable only as immutable historical data.
- A partial six-of-seven v2 set fails before observation writes.

Write order:

1. Resolve canonical config, engine semantic versions, and the snapshot-v2
   binding contract.
2. Resolve the new compatibility ID once (canonical-JSON framing).
3. Resolve one typed production policy bundle including
   `hard_filter_policy`.
4. Build and validate all seven snapshot rows under
   `production_policy_snapshot.v2`.
5. Atomically insert/reuse all seven rows for that compatibility ID.
6. Only after success, write observations carrying that same compatibility ID.

Missing, malformed, incomplete, mismatched, or conflicting snapshot rows must
fail before any observation write.

## 6. Architecture Impact Assessment

- New external dependency: No.
- Affects deterministic live decisions: No; current predicates and defaults
  remain unchanged.
- Persistence change: Yes; migration v3 widens snapshot `contract_id` CHECK;
  new versioned snapshot artifact set and new compatibility cohort are written
  to existing learning tables. Do not add a table.
- Warm-up data: No new provider warm-up. A fresh historical corpus backfill and
  label generation are required operationally for task DONE (not for producer
  code merge).
- Orchestration or policy in adapter: No.

```md
Layer plan:
- Domain: versioned learning/snapshot contract constants (V1/V2 enums),
  ProductionPolicySnapshot.create(contract explicit), immutable hard-filter
  policy value object if placed in domain; no I/O.
- Application: AccumulationScreenHardFilterPolicy + bundle field; one pure
  resolver; lean compatibility.v2 framing; assemble/validate seven v2
  snapshots; snapshot-before-observation workflow.
- Infrastructure: migration v3; persist/read both immutable snapshot artifact
  versions; preserve atomic closed-set semantics and old rows.
- Adapter: thin composition only; inject the shared typed policy and render
  existing failures without interpreting policy.
```

Sibling `ml-saham` boundary:

```md
- Data: read and validate snapshot v2 for an explicitly selected compatibility ID.
- Challenge: bind the verified hard-filter snapshot to a separate replay adapter.
- Protocol/tournament: own thresholds, folds, labels/outcomes, metrics, and artifacts.
- SQLite: read-only; no repair, migration, or inferred snapshots.
- Active production eligibility: snapshot v2 / seven rows only; no v1 fallback.
- Historical v1 parse/display: only if explicitly non-eligible for production baseline.
```

## 7. AI Usage Declaration

No AI involved. Identity, serialization, filtering, capture, labels, and
downstream replay are deterministic and offline.

## 8. Risk, Signal, And Evidence Authority Considerations

- SignalEngine: no score or classification change.
- RiskEngine: no gate change.
- TradeSetup and Action: unchanged.
- Market context and setup policy: unchanged.
- Evidence authority: unchanged. This is corpus/policy identity, not production
  evidence promotion.
- Tuning eligibility: becomes stricter. Only the new snapshot-v2-bound cohort
  may support a verified hard-filter `baseline=production` claim.
- ENTER/WATCH/AVOID: unchanged.
- An eventual `ml-saham` WIN remains human decision support and cannot edit
  production configuration automatically.

## 9. Data And Persistence

Reads:

- canonical resolved configuration already used by production composition;
- typed swing/screener policies and default request policy;
- existing SQLite snapshot/observation/label tables for reconciliation;
- local market/broker/fundamental data already required by accumulation
  backfill.

Writes:

- exactly seven `production_policy_snapshot.v2` rows for one new compatibility
  ID;
- one fresh v2 observation per ticker/session under the new ID;
- normal 3/10/20-session outcome labels referencing those new observation IDs.

Storage constraints:

- do not write tournament panels, classifications, threshold combinations,
  folds, or metrics to the ai-saham database;
- snapshot storage is seven rows per cohort and negligible;
- corpus storage is approximately one additional clean cohort, not a multiplier
  per tournament candidate;
- before operational backfill, record DB size/page count/freelist and current
  observation/label counts;
- after backfill/labels, report deltas. Do not promise zero file growth because
  SQLite may either reuse free pages or allocate new ones.

Source equivalence:

- The new policy artifact and the runtime screen request must be semantically
  equivalent because they consume the same typed object.
- The capture-neutralized request is intentionally not equivalent to the live
  default policy and must never be serialized as though it were.
- Existing observations are not equivalent to the new binding cohort for
  verified-policy eligibility, even when their feature payloads look identical.

Point-in-time behavior:

- observations retain ADR-056 PIT session/cutoff behavior;
- fundamental values remain the PIT values already persisted in the feature
  pack;
- the snapshot records the cohort's production policy, not today's policy
  applied retroactively to older compatibility IDs.

## 10. Cross-Repository Sequencing

1. Accept an ADR-059 amendment defining snapshot v2, the exact seven-row set,
   the non-circular compatibility fork, and migration/enum identity rules.
2. **Amend** (do not implement yet)
   `~/dev/ml-saham/tasks/backlog/consume_verified_ai_saham_policy_snapshots.md`
   to require snapshot v2 / seven rows; forbid committing a v1-only consumer.
3. Implement ai-saham producer/domain/application/infrastructure changes
   including migration v3.
4. Run focused/full verification and data-audit gates on temporary databases
   → **producer merge checkpoint** (section 11.1).
5. Run one live operational backfill under the new compatibility ID.
6. Generate/reconcile 3/10/20-session labels for the new observation IDs.
7. Record DB size/page/freelist + observation/label/snapshot deltas; extract
   audit must return `SUFFICIENT_FOR_REPLAY` for the new explicit cohort
   → **operational DONE checkpoint** (section 11.2).
8. Only then implement the amended ml-saham consumer (active challenges accept
   v2/seven only; no v1 fallback for production eligibility).
9. Only then approve the separate tournament decision checkpoint: exact
   filters/combinations, threshold grid, primary H=10 excess-vs-IHSG outcome,
   denominator, missingness, folds, embargo, minimum N, and INCONCLUSIVE rules.
10. Implement/run the tournament in ml-saham only.

Do not combine steps 1–7 with threshold selection or outcome inspection. Grid
design must not be opportunistically chosen after looking at full-panel H=10
results.

## 11. Acceptance Criteria

### 11.1 Producer merge checkpoint (code/ADR)

- [ ] ADR-059 explicitly defines `production_policy_snapshot.v2` before runtime
      implementation begins.
- [ ] Snapshot v1 remains immutable and validated as exactly six rows.
- [ ] Snapshot v2 validates exactly seven rows including
      `screener.accum.hard_filters`.
- [ ] The new hard-filter row uses `decision_type=gate`, policy version `v1`,
      and semantic contract `screen.accum.hard_filters.v1`.
- [ ] Its payload records all four filters, enabled states, floors, first-match
      order, missing actions, provider-unavailable, and exception actions.
- [ ] Default production floors/enabled match the locked defaults in §5.2.
- [ ] `min_net_buy_days` and all non-goal filters are explicitly absent from the
      executable policy components.
- [ ] `AccumulationProductionPolicyBundle` includes `hard_filter_policy`.
- [ ] One typed default hard-filter policy feeds both production default screen
      construction and snapshot assembly; capture neutralization cannot alter
      the policy snapshot.
- [ ] Market-cap continues to flow from
      `accumulation_screener.screener.min_market_cap_idr` →
      `SwingPolicyConfig.min_market_cap_idr` (no second parse).
- [ ] Lean compatibility uses `lean_accumulation_compatibility.v2` framing;
      frozen golden vector matches §5.4.
- [ ] Delimiter-free v1 hash algorithm is not retained as an alias.
- [ ] `LearningContractId` has explicit V1/V2 members;
      `ProductionPolicySnapshot.create(contract=...)` is explicit;
      integrity uses `snapshot.contract_id`.
- [ ] Migration v3 rebuilds the table, widens `contract_id` CHECK only, preserves
      unique key and `schema_version = 1`, verifies counts/contents, rebuilds
      index, runs `foreign_key_check`.
- [ ] After cutover, producer writes **only** seven v2 rows for the new
      compatibility ID (no dual-write v1).
- [ ] All seven snapshots are atomically ensured before the first observation
      write on both capture and backfill paths.
- [ ] Same binding/content is idempotent; partial sets, conflicting content,
      wrong contracts, or wrong compatibility IDs fail closed.
- [ ] Observation payload remains canonical ADR-056 v2.
- [ ] Existing observations/snapshots remain unchanged in temporary-DB
      migration/identity tests.
- [ ] Temporary-DB tests, full suite, Ruff, and data audits pass.
- [ ] `git diff --check` passes.
- [ ] ml-saham consumer **task** amended to v2/seven (implementation not
      required for this checkpoint).
- [ ] Completion note: **producer implemented; operational activation pending**.

### 11.2 Operational DONE checkpoint (live)

- [ ] A fresh explicit compatibility cohort is captured/backfilled and is not
      the historical 1,890-row compatibility ID
      (`sha256:005363021f7f792071e43d12506aeefe474abf4fbd7d0a45f823b417e95e84c1`).
- [ ] New observation and 3/10/20 label counts reconcile with no duplicate
      ticker/session units inside the cohort.
- [ ] The hard-filter extractor returns `SUFFICIENT_FOR_REPLAY` for the new
      explicit cohort.
- [ ] Production SQLite before/after size, page, freelist, observation, label,
      and snapshot deltas are recorded.
- [ ] `ml-saham` remains read-only and no tournament artifact is written into
      ai-saham SQLite.
- [ ] No live screen, SignalEngine, RiskEngine, TradeSetup, or Action behavior
      changes.
- [ ] Completion record filled with new compatibility ID and measurements.

Until 11.2 is complete, task status remains `IN_PROGRESS` (not `DONE`) even if
producer code is merged.

## 12. Testing Expectations

### ai-saham contract tests

- frozen golden vector for lean compatibility.v2 (§5.4 exact digest);
- frozen canonical JSON/digest/ID vector for snapshot v2;
- exact seven-row set and decision-type map;
- v1 remains exact six and cannot accept the seventh row;
- hard-filter payload equals the shared typed live-default policy object;
- enabled rules: `floor > 0` for market_cap/piotroski; config flags for scores;
- default floors/enabled match locked production defaults;
- missing/provider/exception action vocabulary matches §5.2 table;
- market-cap/Piotroski/accum/signal first-match behavior matches application
  services for pass, reject, threshold equality, and missing values;
- structural skip when fundamentals provider is absent;
- `min_net_buy_days` absent from executable hard-filter components;
- capture-neutralized request still produces the non-neutralized default policy
  snapshot from bundle.hard_filter_policy;
- CLI override does not mutate/relabel the frozen default snapshot;
- compatibility hash differs when only snapshot binding changes;
- delimiter-free old algorithm is not accepted as alias;
- new compatibility ID yields different observation IDs for the same
  ticker/session while old rows remain unchanged;
- snapshot ensure happens once and before any observation repository write;
- partial batch, bad metadata, wrong binding, digest conflict, and repository
  failure produce zero observation writes;
- capture and backfill production composition roots both carry the same typed
  policy object and compatibility ID;
- `ProductionPolicySnapshot.create` rejects implicit/default contract;
- v1 historical snapshot_id recomputes unchanged after enum rename.

### Integration/data tests

- temporary SQLite supports immutable v1 and v2 snapshot cohorts side by side
  (different compatibility IDs);
- migration v3 on a pre-v3 fixture DB: row count/content preserve, CHECK accepts
  v2, foreign_key_check clean;
- read APIs require explicit artifact contract + compatibility ID and never
  auto-select largest/latest;
- fresh-cohort observation/label generation and reconciliation (temp DB);
- architecture tests prove adapters do not assemble policy payloads or parse
  hard-filter semantics;
- source/data audits report no new FAIL findings.

### Required close commands (producer merge)

```text
pytest <focused snapshot/identity/capture/repository/migration suites>
pytest
ruff check src/ tests/
ruff format --check src/ tests/
git diff --check
```

If the full suite or data audit has an unrelated pre-existing failure, record
the exact command/failure and prove the focused contract gates are green; do
not weaken tests or lint configuration.

## 13. Documentation Impact

- ADR-059 amendment: Required (v2 set, enum, framing, migration, cutover,
  hard-filter payload contract).
- ADR-056 amendment: Required only to state that the v2 observation payload is
  retained while snapshot binding forks compatibility; do not redefine the
  ticker/session payload.
- `BOUNDARY.md`: Required; replace the closed six-row/current-v1-only wording
  with immutable v1 history plus current v2 seven-row ownership.
- Source-field/data-contract catalog: update if it validates closed contract
  enums or snapshot fields.
- Operator docs: record the explicit new cohort ID and backfill/label commands
  after operational activation.
- `ml-saham` consumer task amend: **required now** (before consumer
  implementation); ADR-002/boundary/data contract update with that consumer
  work.

## 14. Agent Execution Instructions

Before implementation, the agent must:

1. Read `AGENT_QUICKSTART.md`, `AGENTS.md`, `TASK_TEMPLATE.md`,
   `ARCHITECTURE_DECISIONS.md`, `BOUNDARY.md`, ADR-056, ADR-059, and the
   implementation files named below.
2. Inspect and protect both dirty worktrees; stage only task-owned files.
3. Reverify the exact live-default request path, capture-neutralized path,
   structural/signal first-match predicates, market-cap load path
   (`swing_policy_config_loader` ← `accumulation_screener.screener.min_market_cap_idr`),
   and current compatibility formula.
4. State the hard invariants, forbidden interpretations, exact file boundary,
   exact output contracts, negative tests, and layer plan before editing.
5. List every production composition root for `screen accum`, TUI default
   accumulation, capture, and backfill. Stop if a path would receive an
   independently reconstructed policy.
6. Establish a foundation checkpoint: ADR/constants/type/hash vectors and
   negative contract tests must pass before persistence/workflow integration.
7. Stop if implementation would require rewriting existing observations,
   preserving a fallback/alias, importing sibling Python, putting policy in an
   adapter, relocating market-cap ownership, dual-writing v1, or adding
   tournament evaluation to ai-saham.

Current implementation entry points to reverify:

- `src/adapters/composition/screen_accum_request.py`
- `src/infrastructure/config/swing_policy_config_loader.py`
- `src/application/services/signal_observation_request_builder.py`
- `src/application/services/accumulation_candidate_structural_filter.py`
- `src/application/services/accumulation_candidate_signal_assessor.py`
- `src/application/services/lean_observation_identity.py`
- `src/application/services/accumulation_production_policy_bundle.py`
- `src/application/services/accumulation_policy_snapshot_payloads.py`
- `src/application/use_case/ensure_accumulation_policy_snapshots_use_case.py`
- `src/adapters/cli/research_accum_backfill_commands.py`
- `src/domain/value_objects/learning_artifacts.py`
- `src/infrastructure/persistence/sqlite_learning_artifact_repository.py`
- `src/infrastructure/persistence/sqlite_migration_runner.py`

## 15. Tournament Decision Checkpoint — Still Separate

This task makes a verified tournament possible. It does not authorize one.

**Baseline intent (locked):** `baseline=production` means the exact current,
largely non-selective default:

```text
market cap: off
Piotroski: off
accum score: enabled at 0
signal score: off
```

The tournament question is:

> Does adding a named hard-filter policy improve the predeclared H=10
> outcome/utility metrics versus today’s effectively unfiltered production
> default?

It is a **policy-design/retuning experiment**, not validation of an already
selective production screen.

A future `WIN` means only “candidate for human retuning.” It does **not**
establish:

- full-universe recall;
- value against broker-unobservable names;
- production readiness during fundamentals-provider outages;
- permission to change configuration automatically.

Before changing the ml-saham roadmap from SKIPPED or implementing WIN/LOSE
metrics, a human-approved task must name:

1. exact enabled filter combination(s);
2. exact thresholds/grid and ex-ante rationale;
3. selected snapshot-v2 ID/digests and compatibility ID;
4. primary H=10 binary winner definition and secondary metrics;
5. denominator, missing, source-unavailable, and horizon-unavailable rules;
6. folds, embargo, minimum N, multiplicity control, and
   provisional/INCONCLUSIVE rules;
7. baseline/challenger/adapter/protocol artifact identities;
8. explicit decision that these production knobs are candidates for retuning;
9. provider-unavailable deployment policy for any candidate production retune.

## 16. Do Not Interpret This As

- Do not add rejected rows to manufacture classical screener recall.
- Do not call the current 1,890-row cohort snapshot-v2 verified.
- Do not insert v2 snapshot rows under the old compatibility ID.
- Do not mutate ADR-059 v1 from six rows to seven in place.
- Do not bump the observation payload contract when only the compatibility
  binding changes.
- Do not snapshot the capture-neutralized all-pass request as production.
- Do not treat CLI override values as the frozen canonical default policy.
- Do not include `min_net_buy_days` in the hard-filter tournament.
- Do not store threshold grids or replay outputs in shared SQLite.
- Do not let ml-saham infer, repair, or write policy snapshots.
- Do not auto-promote a tournament result into production configuration.
- Do not dual-write v1 under the new compatibility ID.
- Do not keep delimiter-free lean hash as an alias.
- Do not relocate market-cap ownership off `SwingPolicyConfig` in this task.
- Do not merge a v1-only ml-saham consumer and immediately supersede it.
- Do not mark this backlog task `DONE` after producer merge alone.

## 17. Completion Record

### 17.1 Producer merge

- ADR amendment commit: `46c35f86`
- ai-saham implementation commit: `46c35f86`
- Migration v3 verified (temp + note if live pending): yes — temp-DB rebuild
  preserves v1 rows and accepts v2; live DB not yet activated
- Lean compatibility golden vector:
  `sha256:5b2849a0e60d2cfe880fc8e65d6f1ab10f9668ed2676a1379fc7d2e8255837f2`
- Historical compatibility ID retained:
  `sha256:005363021f7f792071e43d12506aeefe474abf4fbd7d0a45f823b417e95e84c1`
- Focused/full tests: focused contract suites green; domain/application/
  infrastructure.persistence/composition **3712 passed**; full-repo suite run
  via `.venv` (see session notes)
- Ruff check/format: green (`ruff check src/ tests/`, `ruff format --check`)
- ml-saham consumer task amended (path/commit or date):
  `~/dev/ml-saham/tasks/backlog/consume_verified_ai_saham_policy_snapshots.md`
  retargeted to v2/seven on 2026-07-31
- Status note: `producer implemented; operational activation complete`

### 17.2 Operational activation

- Fresh snapshot-v2 compatibility ID:
  `sha256:8ba8fc1e53868bb267c3ef4efeb6ba8780479f4b83fb500573df7826b4040beb`
- Snapshot v2 row count/digests: exactly 7; `risk.accum.hard_gates`
  `86fd1442…`, `screener.accum.hard_filters` `575f6366…`,
  `screener.accum.score_weights` `cd5cd1b9…`,
  `signal.accum.classification` `45311f95…`,
  `signal.accum.evidence_group_weights` `7fe32f83…`,
  `signal.accum.flags` `6c42f888…`, `signal.accum.raw_score` `455c9148…`.
- Fresh observation count: 304 unique ticker/session rows for 2026-06-30;
  zero duplicate ticker/session units.
- H3/H10/H20 label available/unavailable counts: 304/0, 302/2, 300/4.
- Extract-audit verdict: `SUFFICIENT_FOR_REPLAY`; 304 selected, 304
  extracted, 0 unextractable, H10 reconciliation 302 + 2 = 304.
- SQLite before/after measurements: file bytes 1,341,685,760 →
  1,341,685,760; page count 327,560 → 327,560; freelist 160,422 →
  148,421; observations 2,251 → 2,555 (+304); labels 4,330 → 5,242
  (+912); snapshots 6 → 13 (+7).
- ml-saham consumer implementation commit (if any): pending downstream v2
  consumer commit.
- Tournament checkpoint status: `BLOCKED` until section 15 is approved
