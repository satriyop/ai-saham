# Bind Resolved Decision Policy Into ACCUM Cohort Identity

Status: `IMPLEMENTED / VERIFIED` — coordinated v4/nine-row clean-break landed
in the current ai-saham and ml-saham worktrees on 2026-08-07.

Source finding: RC-01A in
`tasks/backlog/review_code_2026-08-07.md` (`CONFIRMED` 2026-08-07).

## 1. Task Metadata

**Task Title**
Make every resolved ACCUM `DecisionPolicyConfig` mutation fork the canonical
behavioral cohort before an observation can be written.

**Task Type**
Bugfix (`CONFIG_MATERIAL` in ai-saham; `POLICY_CONTRACT` in ml-saham).

**Priority**
High — block new `research accum capture|backfill` until this lands in both
repositories. The current database has no ADR-068/v3 observation cohort, so
this is the last cheap clean-break point.

## 2. Problem Statement

The production corpus path resolves one `SignalEngineConfig` and injects it
into the real `SignalEngine`. `AssessSignalEvidenceUseCase` passes
`config.decision_policy` to `DecisionPolicyService`, which can change canonical
ENTER/WATCH/AVOID output and the emitted decision constraints.

The ADR-059 v3 eight-row snapshot projection serializes evidence-group, flag,
classification, risk-gate, hard-filter, and unevaluable-gate policy, but omits
`SignalEngineConfig.decision_policy`. The ADR-068 probe intentionally runs the
in-code default engine to measure the code axis. Therefore neither current
identity axis sees a runtime-resolved decision-policy mutation.

Reproduced on HEAD `619b6a4c`:

```text
mutation: RISK_ON.enter_allowed true -> false
canonical decision: ENTER -> WATCH
compatibility_id: unchanged (sha256:682a2dede218c...)
policy snapshot payload digest: unchanged
behavioral probe digest: unchanged
```

This permits two behaviorally incompatible producers to write into one cohort.
`ml-saham` compounds the gap: its current production snapshot verifier still
accepts only v2/seven rows and therefore cannot verify either v3's
unevaluable-gate policy or the new decision-policy row.

## 3. Chosen Decision And Desired Outcome

**Implement this option only.**

Introduce immutable `production_policy_snapshot.v4` as the active ACCUM
snapshot-binding contract. Its closed set is exactly nine rows: the immutable
v3 eight-row set plus one new row:

| Field | Exact value |
|---|---|
| `policy_id` | `signal.accum.decision_policy` |
| `policy_version` | `v1` |
| `decision_type` | `gate` |
| `semantic_engine_contract_id` | `signal.decision_policy.accum.v1` |
| `formula_id` | `decision_policy_service.resolve.v1` |
| `scope` | `canonical_accum_signal_entry_quality_and_constraints` |

The active producer writes only v4. The v4 snapshot-set payload digest joins
the existing ADR-068 fold unchanged, so any material decision-policy mutation
automatically forks `compatibility_id`.

The same resolved `DecisionPolicyConfig` object must reach:

```text
config/signal_engine.yaml
  -> load_signal_engine_config_raw
  -> resolve_signal_engine_config
  -> AccumulationProductionPolicyBundle.signal_engine_config
  -> SignalEngine / AssessSignalEvidenceUseCase / DecisionPolicyService
  -> build_signal_decision_policy_payload
  -> v4 snapshot-set digest
  -> ADR-068 compatibility_id
  -> observation + nine atomic learning_policy_snapshots rows
  -> ai-saham readiness
  -> ml-saham read-only v4 verifier
```

No adapter may parse or serialize decision policy independently.

## 4. Exact v4 Contracts

### 4.1 Closed set

Add:

```text
LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V4
  = production_policy_snapshot.v4

PRODUCTION_POLICY_ID_SIGNAL_DECISION_POLICY
  = signal.accum.decision_policy

ACCUMULATION_PRODUCTION_POLICY_IDS_V4
  = (*ACCUMULATION_PRODUCTION_POLICY_IDS_V3,
     PRODUCTION_POLICY_ID_SIGNAL_DECISION_POLICY)

ACCUMULATION_PRODUCTION_POLICY_IDS
  = ACCUMULATION_PRODUCTION_POLICY_IDS_V4
```

`ACCUMULATION_PRODUCTION_POLICY_DESCRIPTORS_V4` is the single descriptor map
used by snapshot write and readiness validation. Its order must equal
`ACCUMULATION_PRODUCTION_POLICY_IDS_V4` exactly.

### 4.2 Decision-policy payload

Add the pure application function:

```python
build_signal_decision_policy_payload(
    policy: DecisionPolicyConfig,
) -> dict[str, Any]
```

It must serialize the complete resolved typed object, with deterministic key
ordering through canonical JSON:

- `regime_policy`, for exactly `RISK_ON`, `NEUTRAL`, `RISK_OFF`, `VOLATILE`:
  - `enter_allowed`
  - `max_decision`
  - `regime_size_multiplier`
  - `enter_threshold` (including explicit `null`)
  - `watch_threshold`
  - `min_signal_authority_coverage`
- `setup_regime_policy`: every resolved setup-family key, every regime key,
  and its exact action name.
- `setup_regime_actions`: every resolved action key and `max_decision`.
- `regime_confidence_min_enter`.
- `regime_transitioning_cap_enter`.
- Closed vocabularies:
  - regimes: `NEUTRAL`, `RISK_OFF`, `RISK_ON`, `VOLATILE`;
  - decisions: `AVOID`, `ENTER`, `WATCH`.
- Missing semantics: absent setup family means no setup-specific action; absent
  market context resolves to `RISK_ON`, matching `DecisionPolicyService`.
- Observation result fields:
  - `entry_quality` ->
    `features_by_window.7.signal.assessment.entry_quality`;
  - `decision_constraints` ->
    `features_by_window.7.signal.assessment.decision_constraints`.

The builder receives `signal_engine_config.decision_policy` from the already
resolved production bundle. It must not read YAML, construct defaults, inspect
private service state, or accept a second mapping.

### 4.3 Behavioral probe boundary

Keep `compute_behavioral_probe_digest()` independent of runtime config. It
continues to measure executable code behavior with frozen inputs and in-code
defaults. Do not change the ADR-068 three-part fold:

```text
behavioral_probe_digest
policy_snapshot_payload_digest
observation_payload_schema_version
```

Close the named `DecisionPolicyService` probe-input hole for
`regime_confidence_min_enter` by extending `BehavioralProbe`/`MarketContext`
input and promoting a deliberate core probe. Add code mutation coverage for
all decision-policy branch families. A core probe change is itself a cohort
boundary and must be recorded in the task result.

### 4.4 Persistence migration

Add learning migration version `5` and
`learning_policy_snapshots__v5`. Rebuild the table exactly as migrations 3/4
do, widening only the `contract_id` CHECK to include v4. Preserve all v1-v3
columns and rows byte-for-byte, verify row count plus ordered
`(snapshot_id, payload_digest)`, rebuild the cohort index, and run
`foreign_key_check` before recording migration 5.

`LEARNING_SCHEMA_VERSION` and production snapshot row `schema_version` remain
`1`; the SQL row shape does not change.

### 4.5 Producer and readiness behavior

- `EnsureAccumulationPolicySnapshotsUseCase` writes exactly nine atomic v4 rows
  before any observation write.
- Partial, mixed, extra, duplicate, malformed, digest-invalid, or non-v4 active
  sets fail closed before observation persistence.
- `AccumulationProducerReadiness` treats v1-v3 as historical/legacy only and v4
  as the sole active contract.
- `GetAccumulationProducerReadinessUseCase` must source its top-level
  `active_snapshot_binding_contract` from the same active descriptor used by
  cohort validation. Remove its hard-coded v2 import. JSON and table output
  must report v4 and nine required rows.

### 4.6 ml-saham consumer

Change the production verifier directly from active v2/seven to active
v4/nine. Do not temporarily make v3 active and do not accept multiple active
sets.

- `SNAPSHOT_CONTRACT = "production_policy_snapshot.v4"`.
- `REQUIRED_POLICIES` contains exactly the nine v4 rows, including:
  - `risk.accum.unevaluable_policy` / `risk.unevaluable_gate.accum.v1`;
  - `signal.accum.decision_policy` / `signal.decision_policy.accum.v1`.
- Independently recompute canonical payload digests and snapshot IDs using v4.
- Require one common material snapshot-set hash and exact cohort binding.
- v1-v3 may be recognized only as historical/non-eligible; none may satisfy a
  production baseline request.
- Do not invent challenge adapters for the two identity-only gate rows merely
  to satisfy adapter-count tests. Snapshot verification and challenge adapter
  availability are separate contracts. Unsupported tournaments remain
  `BLOCKED_POLICY`.

## 5. Non-Goals / Do Not Interpret This As

- No change to decision thresholds, setup routing, ENTER/WATCH/AVOID behavior,
  risk behavior, evidence authority, or diagnostic output.
- No runtime-config injection into the behavioral probe.
- No fourth ADR-068 identity axis.
- No raw YAML, repository, source-tree, or git-revision hashing. Source revision
  remains provenance only.
- No mutation of v1, v2, or v3 meanings; no v4 row under an older contract ID.
- No dual-write, compatibility alias, silent translation, fallback, or active
  historical normalization.
- No fabricated snapshot backfill onto existing cohorts.
- No observation payload/schema bump solely for this binding change.
- No corpus purge. Current live evidence found no ADR-068/v3 observations or
  v3 snapshot rows; historical rows remain immutable raw truth.
- No diagnostic producer identity work; that is RC-01B.
- No automatic policy promotion or ai-saham SQLite write from ml-saham.

## 6. Architecture Impact Assessment

- New dependency: No.
- Determinism affected: identity coverage improves; engine output is unchanged.
- Persistence change: Yes, migration 5 widens the snapshot contract CHECK and
  new captures write a nine-row v4 set.
- Warm-up data: No.
- Adapter-owned policy: No.

```md
Layer plan:
- Domain: add v4 contract/policy constants and exact closed-set identity
- Application: serialize decision policy; update descriptors, cohort identity inputs, snapshot ensure, and readiness
- Infrastructure: learning migration 5 widens the snapshot contract CHECK without rewriting rows
- Adapter: wiring/output assertions only; no config parsing or policy
```

Cross-repository boundary:

```md
- ai-saham: owns typed production policy, observation identity, snapshot writes, migration, and readiness
- ml-saham: read-only verification of v4 plus fail-closed challenge eligibility
```

## 7. AI Usage Declaration

No AI involved. This is a deterministic typed identity and validation contract.

## 8. Risk, Signal, Evidence, And Change Classification

- SignalEngine: existing decision policy becomes identity-visible; scoring is
  unchanged.
- RiskEngine/TradeSetup: unchanged.
- What produces ENTER/WATCH/AVOID: unchanged.
- Evidence authority/promotion: unchanged; identity verification is tightened.
- Diagnostic evidence: unchanged and excluded from this task.

ai-saham classification:

- `CONFIG_MATERIAL`: required; resolved material policy currently changes
  Action without moving identity.
- `SEMANTIC_ENGINE`: not applicable; no calculation change.
- `EVIDENCE_CONTRACT`: not applicable; no evidence meaning/authority change.
- `OBSERVATION_SCHEMA`: not applicable; observation payload shape is unchanged.

ml-saham classification: `POLICY_CONTRACT`. The active verified production
baseline moves from v2/seven directly to v4/nine.

## 9. Data & Persistence

- Reads: resolved typed production policies, existing immutable snapshot rows,
  observations for readiness, and ml-saham's read-only upstream SQLite view.
- Writes: ai-saham migration metadata and new v4 snapshot rows only. Observation
  writes continue only after the v4 set verifies.
- Storage: ai-saham `learning_policy_snapshots`; ml-saham writes no upstream
  data.
- Data-source swap: none.
- Existing v1-v3 sources are not semantically equivalent to v4 and remain
  explicitly historical.

## 10. Mandatory Readiness / Promotion Authority Matrix

| Artifact / boundary | Authority owner and source | Exact identity dimensions | Integrity proof | Semantic contract checks | Missing state | Invalid / conflicting state | May contribute to readiness / promotion when |
|---|---|---|---|---|---|---|---|
| ACCUM observation | ai-saham `run_signal_observation_corpus_write` -> canonical observation builder | observation ID, ACCUM purpose/contract, payload schema, v4-derived `compatibility_id`, population/window/session/cutoff | Existing observation ID/digest and column-vs-JSON reconciliation | Active observation contract/schema; no historical alias | No rows = collecting/insufficient data | Missing/malformed identity = `BLOCKED_POLICY` or current named corruption state; zero authority | Integrity passes and its exact cohort has a valid nine-row v4 set |
| Outcome label | ai-saham immutable label producer/repository | label ID, observation ID, exact 3d/10d/20d contract/horizon | Existing ID/digest/linkage checks | Exact label contract and availability; unchanged by this task | Insufficient horizon remains unavailable | Wrong/cross-observation/conflicting label fails closed | Label and linked v4 observation both validate |
| External/reference authority | Existing ai-saham calendar/population authorities; unchanged | Exact existing session, population, cutoff, and coverage identities | Existing PIT/calendar/population validation | Producer and readiness use existing same authority | Existing unavailable state | Existing fail-closed mismatch state | Existing checks pass; v4 grants no substitute authority |
| Policy/config snapshot | ai-saham typed resolver + `EnsureAccumulationPolicySnapshotsUseCase` | v4 contract, purpose, observation contracts, cohort, nine exact policy IDs, per-row descriptor, common material set hash | Recompute payload digest, snapshot ID, metadata, exact set, and common hash independently | v4 only; decision-policy payload contains every resolved field; v1-v3 historical | Zero/partial v4 = `BLOCKED_POLICY` | Mixed/extra/duplicate/malformed/digest-invalid/mismatched v4 = `BLOCKED_POLICY`, zero authority | Exactly nine coherent v4 rows verify against the observation cohort |
| Cohort/readiness projection | ai-saham `GetAccumulationProducerReadinessUseCase` + projection service | ACCUM purpose, population, explicit `compatibility_id`, active v4 descriptor | Consume only validated observations/snapshots; report v4/nine from one source | Existing precedence/minimum-data rules; legacy sets cannot become active | Collecting/insufficient depth remains typed | Any authority corruption uses existing named blocked state | Every authority row passes and minimum-data rule passes |
| Export/reopen/promotion artifact | ml-saham challenge writer/reopen verifier + authoritative ai-saham snapshot store | artifact, cohort, v4 snapshot ID/digest, adapter, protocol, baseline/challenger, population, source revision | Recompute artifact integrity and re-read exact v4 snapshot row read-only | `production` requires v4/nine plus supported adapter/protocol; historical/static never auto-upgrades | Missing DB/v4 authority = `BLOCKED_POLICY` | Unsupported schema, adapter, ID, digest, or cohort mismatch = `BLOCKED_POLICY` | Current authoritative v4 identities and all protocol/promotion gates pass |
| Repository/transport | ai-saham snapshot port/SQLite adapter; ml-saham read-only connection | Exact row keys and all serialized identity columns | Read-time column/JSON/digest/ID reconciliation; migration count/content checks | Deserialization is not verification; no adapter defaults | Missing table/columns = fail closed | Query/schema/serialization errors propagate or block | Exact authoritative rows arrive through permitted read-only path |

Field classification for the new payload:

- Every serialized `DecisionPolicyConfig` field: `SEMANTIC_CONTRACT` and
  identity-material through the snapshot digest.
- Snapshot IDs, contract IDs, policy ID, purpose, cohort, observation bindings:
  `IDENTITY`.
- Payload digest, snapshot ID recomputation, common material hash: `INTEGRITY`.
- `created_at`, `source_revision`: provenance/diagnostic only; never cohort
  identity.
- No decision-policy field may be classified `IRRELEVANT`.

## 11. Expected File Boundary

Before editing, verify current paths and report any necessary deviation.

ai-saham expected production files:

- `docs/adr/ADR-059-production-policy-snapshot-for-ml-challenges.md`
- `docs/adr/ADR-068-behavioral-engine-identity-for-accum-cohorts.md`
- `ARCHITECTURE_DECISIONS.md`
- `BOUNDARY.md`
- `src/domain/value_objects/learning_artifacts.py`
- `src/application/services/accumulation_policy_snapshot_payloads.py`
- `src/application/services/accumulation_production_policy_descriptors.py`
- `src/application/services/behavioral_cohort_identity.py`
- `src/application/services/behavioral_probe_set.py`
- `src/application/services/behavioral_probe_runner.py`
- `src/application/services/accumulation_producer_readiness.py`
- `src/application/use_case/ensure_accumulation_policy_snapshots_use_case.py`
- `src/application/use_case/get_accumulation_producer_readiness_use_case.py`
- `src/infrastructure/persistence/sqlite_learning_artifact_repository.py`
- relevant focused tests under `tests/application`, `tests/adapters/composition`,
  `tests/infrastructure/persistence`, and CLI readiness tests.

ml-saham expected files:

- `BOUNDARY.md`
- `data_contract.md`
- `src/ml_saham/challenge/production_policy_snapshots.py`
- `tests/test_production_policy_snapshots.py`
- challenge/reopen/health tests that assert active snapshot contract/count.

Do not start implementation unless both repositories are available and their
pre-existing dirty changes can be preserved. Stop rather than partially landing
the producer or consumer.

## 12. Negative, Mutation, And Vertical Tests

### ai-saham

- Mutate each regime field independently; each mutation moves snapshot digest
  and `compatibility_id`.
- Mutate each setup-family route, setup action, confidence threshold, and
  transition cap independently with the same expectation.
- Prove a no-op reconstruction produces byte-identical payload/digest/identity.
- Prove the fresh counterexample (`RISK_ON.enter_allowed`) changes ENTER to
  WATCH and now forks identity.
- Assert real production resolver -> bundle -> SignalEngine and payload builder
  receive the same decision-policy object by identity.
- Assert the decision-policy observation paths resolve on a real producer-built
  session observation.
- Assert eight-of-nine, mixed v3/v4, extra, duplicate, invalid metadata,
  malformed JSON, bad digest, bad snapshot ID, and common-hash disagreement all
  fail before observation write.
- Migration 5 tests: fresh DB, v1-only, v1/v2, v1/v2/v3; byte-for-byte
  historical preservation and FK/index verification.
- Readiness use-case plus JSON/table output report v4 and nine rows from the
  same active descriptor.
- Behavioral probe repeated-run equality, branch floor, and mutation suite pass;
  the regime-confidence mutant no longer survives as an input hole.

### ml-saham

- Real/canonical v4 fixture generated from the ai-saham contract passes
  read-only verification.
- v1, v2, v3, partial v4, mixed, extra, duplicate, malformed, bad digest/ID,
  wrong cohort, and inconsistent material hashes all produce `BLOCKED_POLICY`
  or raise the exact verifier error mapped to it.
- Omitted/explicit production baseline cannot fall back to static or historical
  sets.
- Static-reference behavior remains explicit and non-promotable.
- Unsupported adapter for a verified identity-only row remains blocked rather
  than receiving a fabricated adapter.
- Producer snapshot -> SQLite persistence -> ml-saham read-only deserialize ->
  verifier -> supported challenge/reopen boundary passes vertically.
- Read-only tripwire proves upstream DB hash/size/mtime, schema, and row counts
  unchanged.

All tests run offline; no provider/network access is permitted.

## 13. Acceptance Criteria

- [x] Active ai-saham contract is v4 with exactly nine rows.
- [x] Every `DecisionPolicyConfig` field is serialized and mutation-covered.
- [x] The reproduced ENTER->WATCH policy mutation forks `compatibility_id`.
- [x] The probe remains the code axis and runtime config remains the snapshot
      axis; the ADR-068 fold still has exactly three parts.
- [x] Capture/backfill cannot write an observation without the exact atomic v4
      set.
- [x] Readiness reports v4/nine from one source of truth.
- [x] ml-saham production verification accepts only coherent v4/nine.
- [x] Historical v1-v3 rows are unchanged and never active/promotion-eligible.
- [x] No observation schema bump or corpus purge occurred.
- [x] No raw config/source/revision hash or compatibility fallback exists.
- [x] Cross-repository vertical and adversarial tests pass.
- [x] Relevant architecture/boundary tests pass.
- [x] ai-saham full pytest passes.
- [x] ml-saham focused contract suite and `./scripts/check_challenge_contracts.sh`
      pass; run its full suite if the consumer change is broad under its gate.
- [x] ai-saham whole-repo `ruff check src/ tests/` and
      `ruff format --check src/ tests/` pass.
- [x] ml-saham `python -m compileall -q src tests` passes.
- [x] `git diff --check` passes in both repositories on the exact final state.
- [x] Data audit commands are reported; task-relevant failures block canonical,
      readiness-safe, or promotion-safe claims.

### Implementation and verification result — 2026-08-07

- Active identity: `production_policy_snapshot.v4`, exact nine-row closed set,
  default compatibility ID
  `sha256:d2138218537afd93996a1e552f81f109d81f3149b405c66012623c3fedcd5b7f`.
- The decision-policy payload is built from the same resolved typed object used
  by the production signal engine. Independent field mutations and the original
  ENTER-to-WATCH counterexample now fork the compatibility identity.
- The behavioral core has 20 probes. Its digest is
  `913ab690547eba19e95f509f281ce4d1afe15ffdaaae3d242795b18c2f5b4ad8`;
  the new regime-confidence boundary probe kills the previously surviving
  confidence-threshold mutant.
- Migration 5 accepts v4 while preserving v1-v3 as immutable historical rows.
- A real ai-saham bundle wrote nine rows to a temporary SQLite database;
  ml-saham reopened that database with `mode=ro`, independently verified the
  exact v4 set, and left database hash, size, and mtime unchanged.
- ai-saham: `6636 passed, 41 skipped`; whole-repository Ruff check/format and
  `git diff --check` passed.
- ml-saham: focused verifier/promotion slice `36 passed`; challenge contract
  gate `39 passed`; compileall with an external bytecode cache and
  `git diff --check` passed. Its broad suite reached `404 passed` with eight
  pre-existing demo-path failures outside this task; whole-repository Ruff also
  remains blocked by 71 pre-existing findings outside the changed files. The
  changed Python files pass focused Ruff and format checks.
- Live ai-saham DB audits: manifest `PASS`; source-contracts and reconciliation
  `WARN` only for existing optional-field coverage, partial-source coverage,
  and duplicate market-context/regime identities. The live database remained
  byte-identical before/after all audits:
  `6c93209b9a01ef4230df6b2b19e4c0598fa8dfa2d23c0bfc731e036e4e29001c`.

## 14. Documentation Impact

- README update: only if it names the active snapshot contract/count.
- Config documentation: no new option; existing decision-policy keys gain
  explicit identity binding.
- Required updates: ADR-059, ADR-068 clarification, both BOUNDARY mirrors,
  ai-saham readiness/operator contract, and ml-saham data/production-policy
  contract.

## 15. Agent Execution Instructions

Before implementation, the agent must:

1. Read both repositories' agent quickstarts/contracts, boundaries, ADR-059,
   ADR-068, challenge data/extract contracts, and current dirty status.
2. Restate the exact v4/nine-row contract, clean-break rules, authority matrix,
   file boundary, missing/failure states, and composition roots.
3. Confirm both repositories can be changed without overwriting unrelated work.
4. Implement in dependency order: contract/constants -> payload/descriptors ->
   identity -> migration/persistence -> readiness -> composition verification ->
   ml-saham read-only consumer -> outputs/docs -> vertical and close gates.
5. Stop if any path requires an alias, partial producer-only landing, diagnostic
   identity expansion, historical rewrite, or adapter-owned policy.

The task is not complete until the exact v4 producer artifact survives real
persistence and the real ml-saham read-only consumer accepts it while every
older/invalid counterexample contributes zero authority.
