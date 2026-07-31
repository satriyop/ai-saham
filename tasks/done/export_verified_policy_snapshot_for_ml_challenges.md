# Export Verified Production Policy Snapshots For ML Challenges

Status: `DONE` (`ai-saham` producer). Companion `ml-saham` consumer remains
activation-blocked until a fresh cohort is captured and the sibling task lands.

Source: code-first re-vet of `ml-saham` ADR-002 section 3.1 on 2026-07-31.

Primary owner: **`ai-saham`** — production-policy and corpus authority.

Consumer owner: **`ml-saham`** — read-only challenge adapter and policy-tournament
authority. The sibling implementation must be tracked in that repository, but
it must consume the contract produced here rather than invent production truth.

Companion consumer task (present, deliberately activation-blocked):
`~/dev/ml-saham/tasks/backlog/consume_verified_ai_saham_policy_snapshots.md`.

## 1. Task Metadata

- Task type: Feature / cross-repository contract
- Priority: High — until this lands, `ml-saham`'s `baseline=production` is a
  manually mirrored approximation, not a verified production identity.
- Expected semantic classification: `NON_SEMANTIC` for live engine behavior.
  This adds a versioned learning artifact and does not change SignalEngine,
  RiskEngine, TradeSetup, scoring, gates, or Actions. If implementation changes
  an existing observation payload instead of using the dedicated artifact
  below, stop and reclassify it as `OBSERVATION_SCHEMA` with a clean-break
  cohort.
- New artifact contract: `production_policy_snapshot.v1`.
- Chosen decision: `ai-saham` writes exactly six canonical, content-addressed
  policy rows per accumulation cohort (the closed v1 set in section 10), one per
  `(purpose, compatibility_id, policy_id)`, into SQLite. `ml-saham` reads and
  verifies them. Implement this option only.

## 2. Problem Statement

`ml-saham` ADR-002 correctly requires a frozen description of "what production
does / would do", but the current implementation loads hand-maintained JSON
mirrors from `ml-saham/src/ml_saham/challenge/policies/`.

Those files currently:

- contain manually entered `hash` strings that the loader trusts without
  recomputing;
- are not bound to the selected `learning_observations.compatibility_id`;
- can drift independently from resolved `ai-saham` configuration and typed
  engine policy;
- mix production identity with ML-only concerns such as panel kind, extraction
  aliases, protocol selection, and scorer dispatch;
- do not fully express decision type, semantic scorer contract, material
  parameters, or production missing-data/availability rules.

Consequently, a challenge artifact can say `baseline=production` while actually
testing an unverified `ml-saham` mirror. This makes WIN/LOSE evidence unsafe for
human production-policy decisions even when folds and metrics are correct.

The accumulation corpus already supplies the correct join authority:
`learning_observations.compatibility_id`. It also records per-observation
production outputs, but it does not expose a normalized, independently
verifiable definition of the material production policy for counterfactual
reweighting/ablation.

## 3. Desired Outcome

- `ai-saham` deterministically materializes the exact production-policy identity
  used by an accumulation compatibility cohort.
- The snapshot is built from the same resolved typed configuration and semantic
  contracts used to construct the live engines, not from a second raw-YAML
  interpretation and not from constants copied into an adapter.
- Each snapshot has canonical JSON and a recomputable SHA-256 digest.
- A snapshot is bound to exactly one `purpose`, observation contract,
  `compatibility_id`, and `policy_id`.
- Reusing the same binding with different canonical content fails closed. A
  material policy change must produce a new compatibility cohort.
- `ml-saham` may call a baseline `production` only after selecting one
  compatibility cohort and verifying the required snapshot digest and contract.
- Missing, malformed, unsupported, or mismatched snapshots produce
  `BLOCKED_POLICY`; there is no fallback to packaged mirrored production values.
- Observed production scores/actions remain the preferred baseline when the
  research question does not require counterfactual recomputation.
- Counterfactual ablation/reweighting uses the verified snapshot plus a
  separately versioned `ml-saham` challenge adapter whose conformance is tested
  against `ai-saham` golden vectors.

## 4. Non-Goals

- No automatic application of ML winners to `ai-saham` configuration.
- No import of either repository's Python package by the other repository.
- No ML model, remote AI, network service, or new data provider.
- No change to live scoring, RiskEngine gates, TradeSetup, setup policy, MCE
  authority, or final Action.
- No serialization of Python source code or whole-repository hash as policy
  identity.
- No claim that arbitrary counterfactual scorers are production code.
- No inclusion of diagnostic-only bags as production policies. MCE, sector,
  institutional, and company-quality diagnostics remain outside this artifact
  unless they are separately promoted into DecisionPolicy under the governed
  evidence lifecycle.
- No pre-open or swing expansion in this slice. Prove the contract end-to-end
  for `ACCUMULATION_DISCOVERY`; add other purposes through separate tasks after
  the contract is stable.
- No rewriting old observations or pretending old cohorts emitted a snapshot.
- No compatibility reader for missing snapshots and no silent fallback to
  `ml-saham` packaged JSON.

## 5. Hard Invariants

1. `ai-saham` is the sole writer and semantic authority for production policy
   snapshots.
2. `ml-saham` opens the shared database read-only and never repairs, invents, or
   backfills snapshots.
3. Canonical content digest is computed, never supplied as an unchecked label.
4. Full source revision belongs in provenance; only explicit semantic contract
   IDs and resolved material parameters belong in compatibility identity.
5. One selected observation cohort maps to snapshots from that same
   `compatibility_id`; cross-cohort policy reuse is forbidden.
6. Same `(purpose, compatibility_id, policy_id)` plus same digest is idempotent.
   Same key plus different digest is an under-forked compatibility error and
   fails closed.
7. The producer must use the same typed policy/config objects injected into the
   engine path. Adapters must not reconstruct policy from YAML.
8. The snapshot describes production policy only. ML payload paths, aliases,
   panel construction, fold policy, challenger definitions, and metrics remain
   `ml-saham` concerns.
9. Production missing-data and evidence-availability behavior belongs in the
   snapshot. Evaluation PIT/folds/universe/min-N remain in the ML `Protocol`.
10. No snapshot or ML result can directly modify production configuration.
11. Snapshot digests are **not** folded back into `compatibility_id`. The cohort
    identity remains the existing hash of canonical resolved-config bytes plus
    observation-schema, semantic-engine, and evidence-contract versions.
    Snapshots are deterministic projections bound to that identity; making
    their digests input to the same identity would be circular.
12. The application producer receives both the exact
    `resolved_config_canonical` string and the already resolved
    `LeanObservationIdentity`, recomputes the compatibility ID with
    `resolve_lean_semantic_compatibility_id`, and requires equality before any
    snapshot or observation write.

## 6. Architecture Impact Assessment

- New dependency: No.
- Affects determinism: No change to decisions; deterministic artifact output is
  added.
- Persistence change: Yes — one new SQLite learning-artifact table and
  migration, owned only by `ai-saham`.
- Warm-up data: No.
- Orchestration or policy in adapter: No.

```md
Layer plan:
- Domain: typed immutable ProductionPolicySnapshot value object and repository
  port; canonical contract enums/identifiers only, no I/O.
- Application: assemble snapshots from already-resolved typed engine policies;
  validate cohort binding and idempotent/fail-closed write semantics.
- Infrastructure: SQLite migration/repository plus canonical JSON SHA-256
  implementation; only ai-saham writes.
- Adapter: thin research/corpus composition wiring and an inspect/status JSON
  surface if needed; no config interpretation or policy assembly.
```

Sibling `ml-saham` layer boundary:

```md
- Data/infrastructure: read and digest-check the ai-saham snapshot table.
- Challenge application: bind selected cohort to required policy snapshots and
  return BLOCKED_POLICY on any mismatch.
- Challenge adapters: retain payload aliases/panel/scorer dispatch, but stop
  presenting static packaged mirrors as verified production authority.
```

## 7. AI Usage Declaration

No AI involved. Snapshot assembly, hashing, validation, persistence, and
challenge gating are deterministic and offline.

## 8. Risk, Signal, And Evidence Authority Considerations

- SignalEngine: behavior unchanged; active material signal policy is described.
- RiskEngine: behavior unchanged; active gate policy is described.
- TradeSetup: behavior unchanged; its observed Action/gates remain frozen in the
  corpus.
- Market context: diagnostic context is not promoted by this task.
- Evidence authority: unchanged. The snapshot records existing authority and
  missing-data rules; it does not promote evidence.
- ENTER/WATCH/AVOID: unchanged.
- Tuning eligibility: becomes stricter downstream because challenges without a
  verified cohort-bound production snapshot must be blocked.

## 9. Exact Artifact Contract

Create a dedicated table (final naming may follow existing migration naming,
but semantics are fixed) equivalent to:

```text
learning_policy_snapshots
  snapshot_id                 TEXT PRIMARY KEY
  schema_version              INTEGER = 1
  contract_id                 TEXT = production_policy_snapshot.v1
  purpose                     TEXT = ACCUMULATION_DISCOVERY
  learning_observation_contract_id
                              TEXT = learning_observation.accumulation_discovery.v2
  producer_observation_contract
                              TEXT = accumulation-discovery.v2
  compatibility_id            TEXT
  policy_id                   TEXT
  policy_version              TEXT
  decision_type               TEXT  # rank|score|gate|size|label
  semantic_engine_contract_id TEXT
  material_config_hash        TEXT
  canonical_payload_json      TEXT
  payload_digest              TEXT  # sha256(canonical_payload_json bytes)
  source_revision             TEXT  # provenance only
  created_at                  TEXT

  UNIQUE(purpose, compatibility_id, policy_id)
```

There is no foreign key in v1: no normalized cohort-parent table currently
exists. Remove any FK expectation from implementation/tests. Cohort integrity
is enforced by the application recomputation rule and the unique binding above.

### Exact identity and digest algorithms

- Add `LearningContractId.PRODUCTION_POLICY_SNAPSHOT` with exact value
  `production_policy_snapshot.v1`.
- `snapshot_id = stable_learning_id(PRODUCTION_POLICY_SNAPSHOT, identity)` where
  `identity` is exactly:

  ```text
  purpose
  learning_observation_contract_id
  producer_observation_contract
  compatibility_id
  policy_id
  ```

- Payload digest is **not** an ID input. This preserves the existing learning
  artifact rule: same relational identity plus changed content produces a
  digest conflict instead of a second row.
- `material_config_hash = "sha256:" +
  sha256(resolved_config_canonical UTF-8 bytes).hexdigest()`.
- `payload_digest =
  sha256(canonical_payload_json UTF-8 bytes).hexdigest()` (lowercase 64 hex,
  no prefix, matching current learning artifact digest convention).
- `created_at` and `source_revision` are excluded from the canonical payload,
  payload digest, snapshot ID, material config hash, and semantic compatibility.

### Exact canonical JSON contract

Reuse `src.domain.value_objects.learning_artifacts.canonical_json`; do not add a
second canonicalizer. The frozen byte contract is:

- recursively convert enums to `.value` and aware datetimes to ISO-8601;
- stringify mapping keys;
- retain explicit nulls (no null omission);
- `ensure_ascii=True`;
- `allow_nan=False` (NaN and infinity rejected);
- `sort_keys=True`;
- `separators=(",", ":")` (no insignificant whitespace);
- hash the resulting UTF-8 bytes.

`ml-saham` must parse and re-encode with the identical rules and require the
re-encoded string to equal the stored `canonical_payload_json` before checking
the digest. Add one frozen non-ASCII/null/bool/float byte-layout fixture shared
by contract tests in both repositories.

The canonical payload must contain, where applicable:

- policy ID/version and explicit decision type;
- semantic scorer/gate contract identifier;
- enabled/disabled components;
- exact resolved material weights, thresholds, caps, saturation values,
  normalization/renormalization mode, and ordering where behavior depends on
  it;
- missing-data, unavailable-evidence, and gate short-circuit behavior;
- formula identifiers for code-owned calculations;
- output scale and action/classification thresholds;
- links to the observation fields that contain the frozen production result,
  expressed as producer contract field names, not ML extraction aliases.

Do not put these ML concerns in the production snapshot:

- `panel_kind`, ML scorer dispatch, extraction fallback aliases;
- protocol horizons, fold counts, embargo, min N, metrics;
- challenger IDs or learned weights;
- diagnostic feature bags that have no production authority.

## 10. Accumulation Policy Scope

The v1 export set is **closed and exact**. Export exactly these six IDs; adding
TradeSetup, sizing, soft gates, diagnostics, or any seventh policy requires a
new task/contract amendment.

| Exact `policy_id` | `decision_type` | v1 role |
|---|---|---|
| `screener.accum.score_weights` | `score` | Material canonical `AccumScorePolicy`/BCI component policy only |
| `signal.accum.evidence_group_weights` | `score` | Material setup/flow group weights and missing-group renormalization |
| `signal.accum.flags` | `score` | Material do-no-harm flags, thresholds and penalties |
| `signal.accum.classification` | `score` | Material strong/moderate score thresholds; this is not an outcome label |
| `risk.accum.hard_gates` | `gate` | Material enabled gates, thresholds, missing-data and short-circuit rules |
| `signal.accum.raw_score` | `score` | Identity-only row pointing to the frozen observed signal field; no reconstructed raw-score formula |

Exact slice binding:

- `purpose = "ACCUMULATION_DISCOVERY"`;
- `policy_version = "v1"` for all six rows;
- `learning_observation_contract_id =
  "learning_observation.accumulation_discovery.v2"`;
- `producer_observation_contract = "accumulation-discovery.v2"`.

`signal.accum.raw_score` gets a real sixth table row so challenge preparation
has one uniform verified-policy lookup. Its payload identifies the producer
semantic contract and canonical observation field
`features_by_window.<canonical_window>.signal.raw_exact_score`. The rounded
classification/display companion is
`features_by_window.<canonical_window>.signal.assessment.score`; it is not the
raw-score baseline. The row contains no ML aliases or counterfactual formula.

**Sector breadth decision for v1: option C — out of scope.** It is not part of
the `screener.accum.score_weights` snapshot because current production applies
the bonus after signal assessment. Remove/disable it as a production component
in the corresponding ML adapter during cutover. Any challenger or factor query
that names sector breadth returns `BLOCKED_POLICY` with a pointer to the engine
ordering follow-up. Do not encode it as an ordered step in v1 and do not retain
the current `+10 when present` mirror behavior.

## 11. Producer Workflow

Create one application-owned `EnsureAccumulationPolicySnapshotsUseCase` (exact
class/file naming may follow repository convention). The one shared
`run_signal_observation_corpus_write` composition path calls it automatically
for **both** `research accum capture` and `research accum backfill`.

1. Composition reads `resolved_config_canonical` once and uses those same bytes
   to resolve `LeanObservationIdentity`.
2. Composition resolves typed engine policies/configuration once.
3. It invokes the ensure use case once per command invocation, before the
   backfill/capture use case can write any observation.
4. The ensure use case recomputes compatibility ID from the supplied canonical
   bytes and requires equality with the supplied lean identity.
5. It builds exactly the six required rows from the supplied typed policy
   objects and producer field contract.
6. Repository insert/verify is idempotent. An existing key with a different
   payload digest aborts the entire command before observation writes.
7. The observation writer then proceeds using the same lean identity.

This check runs on every capture/backfill invocation; repository idempotence
makes it an insert only for a new cohort. There is no required separate export
command and no operator sequencing gap. A read-only inspect/status command
remains optional.

## 12. `ml-saham` Consumer Contract

The companion implementation must:

1. Select exactly one accumulation compatibility cohort.
2. Load every snapshot required by the selected PolicySpec from the same
   cohort.
3. Recompute and validate `payload_digest` and validate supported contract and
   semantic-engine IDs.
4. Separate the verified production snapshot from the ML-owned
   `ChallengePolicyAdapter` (`panel_kind`, extraction aliases, scorer dispatch).
5. Use frozen observed production score/action when that answers the baseline
   question.
6. Use counterfactual reproduction only when an adapter has conformance proof
   for that snapshot's semantic contract.
7. Return `BLOCKED_POLICY` for missing, mismatched, malformed, unsupported, or
   unverifiable snapshots.
8. Remove static packaged policy JSON as production authority. Packaged files
   may remain only as explicitly named test fixtures or challenger definitions;
   no fallback is allowed.
9. Include snapshot ID/digest, compatibility ID, and adapter version in every
   challenge artifact.

## 13. Data & Persistence

- Reads: resolved typed production policies/config; selected accumulation
  compatibility identity.
- Writes: `learning_policy_snapshots` in the existing `ai-saham` SQLite DB.
- Schema change: Yes, additive table/migration.
- Old and new sources semantically equivalent: No. Handwritten `ml-saham` JSON
  is an unverified mirror; the new artifact is producer-owned and cohort-bound.
- Point-in-time behavior: snapshot is immutable for its compatibility cohort.
  Challenges over historical observations must resolve the matching historical
  cohort snapshot, never today's live config.
- Existing observations without snapshots remain historical raw corpus but are
  ineligible for a verified production-policy challenge. Do not fabricate or
  infer snapshots for them.

## 14. Sequencing

1. `ai-saham`: accept the ADR/artifact contract **before runtime code is
   written**. ADR and implementation may share one PR/branch, but the contract
   commit/section must land first and code review must treat it as binding.
2. `ai-saham`: implement the typed value object, port, application producer,
   SQLite migration/repository, and accumulation wiring.
3. `ai-saham`: capture a fresh clean compatibility cohort with verified
   snapshots; do not rewrite old observations.
4. `ml-saham`: implement reader, digest/contract validation, cohort binding,
   `BLOCKED_POLICY`, and production-vs-adapter separation.
5. `ml-saham`: add cross-repository golden conformance fixtures for every
   supported semantic scorer/gate contract.
6. `ml-saham`: retire packaged mirrored JSON as production authority.
7. Only then treat new challenge artifacts as verified
   `baseline=production`.

Do not land the `ml-saham` fallback removal before a fresh `ai-saham` cohort and
snapshots are available, but do not keep a compatibility fallback afterward.

## 15. Testing Expectations

### `ai-saham`

- Canonical serialization produces byte-identical JSON and digest for identical
  typed policy input.
- Changing any material parameter changes the snapshot digest; because the
  parameter originates in the canonical resolved-config input, it also changes
  the existing compatibility identity. A test must prove both changes from the
  same input mutation.
- Changing `created_at` or source revision does not change semantic digest.
- Same cohort/key + same digest is idempotent.
- Same cohort/key + different digest fails before observation persistence.
- Snapshot payload matches resolved accumulation, signal, and risk typed policy
  objects in focused contract tests.
- Missing required snapshot prevents corpus observation writes.
- SQLite uniqueness, digest-conflict behavior, and read/write round trip are
  covered. No FK is expected in v1.
- Frozen canonical byte layout, material-config hash, payload digest, and exact
  `stable_learning_id` formula are covered.
- Both capture and backfill prove the automatic ensure step runs before the
  first observation write.
- Tests run offline against a temporary SQLite database.

### `ml-saham`

- Valid matching snapshot permits a challenge.
- Missing snapshot, bad digest, wrong cohort, unsupported contract, and
  unsupported semantic scorer each return `BLOCKED_POLICY`.
- No test fixture can pass merely because a packaged mirror exists.
- Golden vectors prove each ML counterfactual adapter reproduces the declared
  `ai-saham` semantic contract before ablation/reweighting is enabled.
- Challenge artifact contains cohort ID, snapshot ID/digest, and adapter version.
- Tests run offline.

Both repositories must pass focused tests, full relevant suites, `git
diff --check`, and their whole-repository Ruff gates when Python is changed.

## 16. Acceptance Criteria

- [x] `production_policy_snapshot.v1` is documented in an accepted `ai-saham`
      ADR or amendment before runtime implementation begins.
- [x] `ai-saham` is the only snapshot writer and builds snapshots from the same
      resolved typed policies used by production engines.
- [x] Canonical JSON digest is recomputed and validated; no handwritten hash is
      trusted.
- [x] Required snapshots are bound to purpose, observation contract, and exact
      compatibility cohort.
- [x] The export set is exactly the six IDs in section 10 with the locked
      decision-type map; no seventh row is emitted.
- [x] Purpose and both observation-contract strings match the exact constants
      in section 10.
- [x] Cohort consistency uses the recomputation rule in section 5; snapshot
      digests are not folded circularly into compatibility identity.
- [x] Canonical JSON, digest, material hash, and snapshot ID use the exact
      algorithms in section 9.
- [x] Sector breadth is absent from v1 policy snapshots (blocked as counterfactual
      remains `ml-saham` companion cutover work).
- [x] Capture and backfill automatically ensure snapshots through their shared
      composition path; no separate export command is required.
- [x] Under-forked same-cohort policy divergence fails closed.
- [ ] Fresh accumulation corpus cohort contains all required policy snapshots
      (operator: run capture/backfill after deploy).
- [ ] `ml-saham` separates production snapshot identity from ML extraction and
      scorer adapter concerns.
- [ ] `ml-saham` blocks missing/mismatched/unverifiable snapshots with
      `BLOCKED_POLICY` and has no static-production fallback.
- [ ] Observed outputs are used for ordinary production baselines;
      counterfactual reproduction requires golden conformance proof.
- [ ] Challenge artifacts carry snapshot/cohort/adapter identities.
- [x] No live decision behavior, evidence authority, or automatic promotion is
      changed.
- [x] Adapter thinness and repository boundary tests pass.
- [x] Focused/full relevant tests, data audits, and whole-repo Ruff gates pass
      (`ai-saham`).

## 17. Documentation Impact

- `ai-saham` ADR/amendment required: Yes.
- Root `BOUNDARY.md` update required: Yes — add policy-snapshot ownership/read
  contract.
- `ml-saham` ADR-002 amendment required: Yes — distinguish verified
  `ProductionPolicySnapshot` from `ChallengePolicyAdapter` and remove "names
  only" as sufficient production definition.
- New config option: No.
- Limitations to state: historical cohorts without snapshots are not verified
  production-policy challenge cohorts.

## 18. Required Reading

- `AGENT_QUICKSTART.md`, `AGENTS.md`, `TASK_TEMPLATE.md`
- `BOUNDARY.md`
- `docs/adr/ADR-042-deterministic-champion-and-optional-model-challengers.md`
- `docs/adr/ADR-049-database-owned-learning-pipeline-clean-break.md`
- `docs/adr/ADR-056-accum-corpus-session-observation-and-accum-path-labels.md`
- `src/application/services/lean_observation_identity.py`
- `src/domain/value_objects/signal_semantic_contract.py`
- `src/application/services/engine_bootstrap/`
- sibling `ml-saham/docs/adr/ADR-002-ideal-challenge-system.md`
- sibling `ml-saham/src/ml_saham/challenge/types.py`
- sibling `ml-saham/src/ml_saham/challenge/policies/registry.py`
- sibling `ml-saham/src/ml_saham/challenge/scorers.py`

## 19. Agent Execution Instructions

Before implementation, the agent must:

- confirm the cross-repository ownership boundary and implement `ai-saham`
  producer work before `ml-saham` consumer cutover;
- inspect both worktrees and protect unrelated changes;
- state whether the chosen persistence shape requires any classification beyond
  the expected `NON_SEMANTIC` live-engine classification;
- state the exact typed production policy objects used as snapshot inputs;
- state the exact semantic contract IDs and material parameters exported;
- state the layer plan in both repositories;
- run the Data Contract Audit Gate after persistence/corpus changes;
- stop for clarification if implementation would import sibling Python,
  auto-apply ML output, reinterpret historical rows, or retain a fallback.

## Do Not Interpret This As

- Do not call a non-empty arbitrary string a verified policy hash.
- Do not copy more constants into `ml-saham` and label the copy an export.
- Do not read raw YAML independently in a CLI adapter to assemble the snapshot.
- Do not hash the entire repository into semantic compatibility.
- Do not bind today's policy to an older observation cohort.
- Do not treat `source_ref` prose as machine-verifiable provenance.
- Do not put ML protocol/fold/panel rules inside the production snapshot.
- Do not let `ml-saham` write the shared SQLite database.
- Do not preserve static mirrored production JSON as a fallback after cutover.
- Do not turn diagnostic evidence into production policy by including it in the
  snapshot.
- Do not auto-edit production configuration after a challenge WIN.

## Completion Record

- Completed date: 2026-07-31 (`ai-saham` producer)
- `ai-saham` implementation commit: uncommitted at implementation time (working tree)
- `ml-saham` implementation commit: not started (companion task activation-blocked)
- Fresh compatibility cohort: not yet captured; requires post-deploy
  `research accum capture|backfill` on a live DB
- Snapshot contract/digest verification: unit + SQLite repository tests green;
  source-contracts catalog includes `learning_policy_snapshots` (PASS on empty
  table smoke)
- Commands run:
  - `.venv/bin/python -m pytest tests/domain/value_objects/test_production_policy_snapshot.py tests/application/use_case/test_ensure_accumulation_policy_snapshots_use_case.py tests/application/services/test_accumulation_policy_snapshot_payloads.py tests/infrastructure/persistence/test_sqlite_learning_artifact_repository.py tests/infrastructure/persistence/test_learning_clean_break.py tests/domain/value_objects/test_learning_artifacts.py -q`
  - `ruff check src/ tests/` and `ruff format --check src/ tests/`
  - smoke `saham audit data source-contracts` against temp DB with new schema
- Test result: focused suites passed (39+ related)
- Data-audit result: `learning_policy_snapshots` registered; contract_status PASS
  on empty table; full-DB FAIL expected when other audited tables are missing
- Lint result: whole-repo Ruff check + format green
