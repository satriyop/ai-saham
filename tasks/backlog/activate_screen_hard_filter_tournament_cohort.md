# Activate A Snapshot-Bound Cohort For The Screen Hard-Filter Tournament

Status: `READY`

Priority: **High** — required before `ml-saham` can run a verified
`baseline=production` screen hard-filter tournament.

Source: code-first follow-up to the completed
[`parked_screen_filter_replay_contract.md`](parked_screen_filter_replay_contract.md),
ADR-056, and ADR-059 on 2026-07-31.

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
  lean accumulation compatibility hash. Do not bump the observation payload to
  v3 merely to force a cohort fork.

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
  policy used to construct the canonical live `screen accum` request. It is not
  reconstructed from raw YAML in an adapter.
- The hard-filter payload records the exact four filter values, enabled states,
  first-match order, and missing-data behavior.
- The snapshot-binding contract ID is an explicit input to the accumulation
  compatibility hash, yielding a new cohort even when resolved YAML and engine
  semantic versions are otherwise unchanged.
- New observation IDs include the new compatibility ID through the existing
  `LearningObservation` identity formula. Old observation rows remain unchanged.
- Capture/backfill atomically ensures all seven v2 snapshots before writing the
  first observation in the new cohort.
- A fresh accumulation backfill creates a genuinely new, snapshot-bound cohort
  with reconciled observations and 3/10/20-session labels.
- `ml-saham` receives sufficient immutable identities to implement its existing
  snapshot-consumer clean break and later hard-filter tournament.
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

filters.piotroski.enabled
filters.piotroski.floor
filters.piotroski.missing_action

filters.accum_score.enabled
filters.accum_score.floor
filters.accum_score.missing_action

filters.signal_score.enabled
filters.signal_score.floor
filters.signal_score.missing_action

explicitly_excluded = [min_net_buy_days]
```

The implementation must verify the exact missing actions against:

- `AccumulationCandidateStructuralFilter` for market cap and Piotroski;
- `AccumulationCandidateSignalAssessor` for accumulation and signal scores.

Do not copy the above shape while guessing the values. Derive values and
enabled states from one typed default hard-filter policy object shared with the
canonical default screen request construction.

CLI overrides such as `--min-piotroski`, `--min-foreign-flow-score`, and
`--min-signal-score` are not the frozen default production baseline. A run with
an override must not be mislabeled as the snapshot's default policy. This task
does not add per-invocation snapshot rows.

### 5.3 One typed authority path

Introduce or extract one immutable application-owned type equivalent to:

```text
AccumulationScreenHardFilterPolicy
  min_market_cap_idr
  min_piotroski
  min_accum_score
  min_accum_score_enabled
  min_signal_score
  min_signal_score_enabled
```

The exact type name may change during ADR review, but the ownership path may
not:

```text
resolved typed configs + canonical default request policy
  -> one AccumulationScreenHardFilterPolicy
      -> BuildSignalObservationScreenRequest/default live screen construction
      -> production-policy snapshot payload assembly
```

The capture path may still neutralize score filters for corpus inclusion, but
that neutralized request is not the production policy snapshot. Snapshot
assembly must receive the pre-neutralization canonical default policy object.

Adapters may wire the object. They must not interpret YAML, calculate enabled
states, choose missing actions, or assemble snapshot payloads.

### 5.4 Non-circular clean cohort fork

Add the exact snapshot-binding contract ID to the lean accumulation
compatibility identity input:

```text
resolved_config_canonical
CANDIDATE_OBSERVATION_SCHEMA_VERSION
SEMANTIC_ENGINE_VERSION
EVIDENCE_CONTRACT_VERSION
policy_snapshot_binding_contract = production_policy_snapshot.v2
```

Requirements:

- use unambiguous canonical framing rather than raw delimiter-free string
  concatenation when changing the identity formula;
- the same inputs remain deterministic;
- changing only the binding contract from v1 to v2 forks the compatibility ID;
- snapshot payload digests remain projections and are **not** folded into the
  compatibility ID;
- the observation payload and learning observation contract remain
  `learning_observation.accumulation_discovery.v2` /
  `accumulation-discovery.v2`;
- every snapshot row and observation written in the new path uses the exact
  same newly resolved compatibility ID;
- existing v1 compatibility IDs and observations remain byte-for-byte
  unchanged and cannot be selected as verified snapshot-v2 cohorts.

This is a deliberate compatibility clean break. Do not add a reader alias,
fallback, translation, auto-upgrade, or `latest/largest cohort` selection.

### 5.5 Atomic write order

For capture and backfill:

1. Resolve canonical config, engine semantic versions, and the snapshot-v2
   binding contract.
2. Resolve the new compatibility ID once.
3. Resolve one typed production policy bundle including the default screen hard
   filters.
4. Build and validate all seven snapshot rows.
5. Atomically insert/reuse all seven rows for that compatibility ID.
6. Only after success, write observations carrying that same compatibility ID.

Missing, malformed, incomplete, mismatched, or conflicting snapshot rows must
fail before any observation write. A partial six-of-seven set is an invariant
failure, not a warning.

## 6. Architecture Impact Assessment

- New external dependency: No.
- Affects deterministic live decisions: No; current predicates and defaults
  remain unchanged.
- Persistence change: Yes; a new versioned snapshot artifact set and a new
  compatibility cohort are written to existing learning tables. A migration is
  required only if current schema constraints cannot store both artifact
  contract versions; do not add a table without proving that need.
- Warm-up data: No new provider warm-up. A fresh historical corpus backfill and
  label generation are required operationally.
- Orchestration or policy in adapter: No.

```md
Layer plan:
- Domain: versioned learning/snapshot contract constants and immutable hard-filter policy value; no I/O.
- Application: construct one typed default hard-filter policy, include the binding contract in compatibility resolution, assemble/validate seven snapshots, and enforce snapshot-before-observation workflow.
- Infrastructure: persist/read both immutable snapshot artifact versions in SQLite; preserve atomic closed-set semantics and old rows.
- Adapter: thin composition only; inject the shared typed policy and render existing failures without interpreting policy.
```

Sibling `ml-saham` boundary:

```md
- Data: read and validate snapshot v2 for an explicitly selected compatibility ID.
- Challenge: bind the verified hard-filter snapshot to a separate replay adapter.
- Protocol/tournament: own thresholds, folds, labels/outcomes, metrics, and artifacts.
- SQLite: read-only; no repair, migration, or inferred snapshots.
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
   and the non-circular compatibility fork.
2. Implement ai-saham producer/domain/application/infrastructure changes.
3. Run focused/full verification and data-audit gates on temporary databases.
4. Run one live operational backfill under the new compatibility ID.
5. Generate/reconcile 3/10/20-session labels for the new observation IDs.
6. Amend and implement
   `~/dev/ml-saham/tasks/backlog/consume_verified_ai_saham_policy_snapshots.md`
   for snapshot v2 and the exact seven-row set.
7. Re-run the existing screen-filter extract audit against the new explicit
   cohort; it must remain `SUFFICIENT_FOR_REPLAY`.
8. Only then approve the separate tournament decision checkpoint: exact
   filters/combinations, threshold grid, primary H=10 excess-vs-IHSG outcome,
   denominator, missingness, folds, embargo, minimum N, and INCONCLUSIVE rules.
9. Implement/run the tournament in ml-saham only.

Do not combine steps 1-7 with threshold selection or outcome inspection. Grid
design must not be opportunistically chosen after looking at full-panel H=10
results.

## 11. Acceptance Criteria

- [ ] ADR-059 explicitly defines `production_policy_snapshot.v2` before runtime
      implementation begins.
- [ ] Snapshot v1 remains immutable and validated as exactly six rows.
- [ ] Snapshot v2 validates exactly seven rows including
      `screener.accum.hard_filters`.
- [ ] The new hard-filter row uses `decision_type=gate`, policy version `v1`,
      and semantic contract `screen.accum.hard_filters.v1`.
- [ ] Its payload records all four filters, enabled states, floors, first-match
      order, and verified missing actions.
- [ ] `min_net_buy_days` and all non-goal filters are explicitly absent from the
      executable policy components.
- [ ] One typed default hard-filter policy object feeds both production default
      screen construction and snapshot assembly.
- [ ] Capture neutralization cannot alter the policy snapshot.
- [ ] Snapshot-v2 binding deterministically forks the compatibility ID without
      folding snapshot digests into it.
- [ ] Observation payload remains canonical ADR-056 v2; no unnecessary v3 or
      dual reader/writer is introduced.
- [ ] Existing observations/snapshots remain unchanged and ineligible for the
      new verified-policy cohort.
- [ ] All seven snapshots are atomically ensured before the first observation
      write on both capture and backfill paths.
- [ ] Same binding/content is idempotent; partial sets, conflicting content,
      wrong contracts, or wrong compatibility IDs fail closed.
- [ ] A fresh explicit compatibility cohort is captured/backfilled and is not
      the historical 1,890-row compatibility ID.
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
- [ ] Whole-repo tests and Ruff gates pass in every repository whose Python is
      changed.
- [ ] `git diff --check` passes and completion records contain both repository
      commits plus the new compatibility ID.

## 12. Testing Expectations

### ai-saham contract tests

- frozen canonical JSON/digest/ID vector for snapshot v2;
- exact seven-row set and decision-type map;
- v1 remains exact six and cannot accept the seventh row;
- hard-filter payload equals the shared typed live-default policy object;
- market-cap/Piotroski/accum/signal first-match behavior matches application
  services for pass, reject, threshold equality, and missing values;
- `min_net_buy_days` absent from executable hard-filter components;
- capture-neutralized request still produces the non-neutralized default policy
  snapshot;
- CLI override does not mutate/relabel the frozen default snapshot;
- compatibility hash differs when only snapshot binding changes v1 -> v2;
- deterministic hash for identical inputs and an unambiguous framing collision
  counterexample;
- new compatibility ID yields different observation IDs for the same
  ticker/session while old rows remain unchanged;
- snapshot ensure happens once and before any observation repository write;
- partial batch, bad metadata, wrong binding, digest conflict, and repository
  failure produce zero observation writes;
- capture and backfill production composition roots both carry the same typed
  policy object and compatibility ID.

### Integration/data tests

- temporary SQLite supports immutable v1 and v2 snapshot cohorts side by side;
- read APIs require explicit artifact contract + compatibility ID and never
  auto-select largest/latest;
- fresh-cohort observation/label generation and reconciliation;
- architecture tests prove adapters do not assemble policy payloads or parse
  hard-filter semantics;
- source/data audits report no new FAIL findings.

### Required close commands

```text
pytest <focused snapshot/identity/capture/repository suites>
pytest
ruff check src/ tests/
ruff format --check src/ tests/
git diff --check
```

If the full suite or data audit has an unrelated pre-existing failure, record
the exact command/failure and prove the focused contract gates are green; do
not weaken tests or lint configuration.

## 13. Documentation Impact

- ADR-059 amendment: Required.
- ADR-056 amendment: Required only to state that the v2 observation payload is
  retained while snapshot binding forks compatibility; do not redefine the
  ticker/session payload.
- `BOUNDARY.md`: Required; replace the closed six-row/current-v1-only wording
  with immutable v1 history plus current v2 seven-row ownership.
- Source-field/data-contract catalog: update if it validates closed contract
  enums or snapshot fields.
- Operator docs: record the explicit new cohort ID and backfill/label commands.
- `ml-saham` ADR-002, boundary, data contract, and consumer task: downstream
  update required before consumer implementation.

## 14. Agent Execution Instructions

Before implementation, the agent must:

1. Read `AGENT_QUICKSTART.md`, `AGENTS.md`, `TASK_TEMPLATE.md`,
   `ARCHITECTURE_DECISIONS.md`, `BOUNDARY.md`, ADR-056, ADR-059, and the
   implementation files named below.
2. Inspect and protect both dirty worktrees; stage only task-owned files.
3. Reverify the exact live-default request path, capture-neutralized path,
   structural/signal first-match predicates, and current compatibility formula.
4. State the hard invariants, forbidden interpretations, exact file boundary,
   exact output contracts, negative tests, and layer plan before editing.
5. List every production composition root for `screen accum`, TUI default
   accumulation, capture, and backfill. Stop if a path would receive an
   independently reconstructed policy.
6. Establish a foundation checkpoint: ADR/constants/type/hash vectors and
   negative contract tests must pass before persistence/workflow integration.
7. Stop if implementation would require rewriting existing observations,
   preserving a fallback/alias, importing sibling Python, putting policy in an
   adapter, or adding tournament evaluation to ai-saham.

Current implementation entry points to reverify:

- `src/adapters/composition/screen_accum_request.py`
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

## 15. Tournament Decision Checkpoint — Still Separate

This task makes a verified tournament possible. It does not authorize one.

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
8. explicit decision that these production knobs are candidates for retuning.

Current defaults being off or zero does not make replay useless, but it means
the tournament is a policy-design experiment rather than validation of an
already selective production baseline. Report that distinction explicitly.

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

## 17. Completion Record

- ADR amendment commit:
- ai-saham implementation commit:
- Fresh snapshot-v2 compatibility ID:
- Historical compatibility ID retained:
  `sha256:005363021f7f792071e43d12506aeefe474abf4fbd7d0a45f823b417e95e84c1`
- Snapshot v2 row count/digests:
- Fresh observation count:
- H3/H10/H20 label available/unavailable counts:
- Extract-audit verdict:
- SQLite before/after measurements:
- ml-saham consumer commit:
- Focused/full tests:
- Ruff check/format:
- Tournament checkpoint status: `BLOCKED` until section 15 is approved
