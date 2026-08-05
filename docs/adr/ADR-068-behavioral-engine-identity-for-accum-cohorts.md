# ADR-068: Behavioral engine identity for accum cohorts

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted

**Date:** 2026-08-04

**Amends:** [ADR-059](ADR-059-production-policy-snapshot-for-ml-challenges.md)
(snapshot digest becomes identity-material), and the lean compatibility material
defined in `lean_observation_identity.py`

**Depends on:** [ADR-057](ADR-057-evidence-diagnostic-evidence-corpus-vocabulary.md),
[ADR-062](ADR-062-retire-accum-group-breadth-production-bonus.md) (golden-gate
precedent), [ADR-067](ADR-067-retire-setup-quality-and-fix-judgment-authority-by-surface.md)

**Does not change:** scoring rules, gate thresholds, evidence authority, the
`ml-saham` boundary rules, or what produces ENTER/WATCH/AVOID.

---

## Context

A cohort (`compatibility_id`) exists to answer one question:

> Would this engine give the same answer to the same input?

Only observations for which that answer is *yes* may be pooled. Pool two
behaviourally different engines and every downstream verdict is confidently
wrong.

Today that question is answered by three proxies, and all three are wrong.

### Proxy 1 — raw config bytes (over-fires)

`resolve_lean_semantic_compatibility_id` (`lean_observation_identity.py:77-108`)
folds `resolved_config_canonical`, built by
`research_accum_backfill_commands.py:109-115` as the **raw text** of twelve
config files:

```python
content = Path(rel_path).read_text(encoding="utf-8")
blocks.append(f"# path: {rel_path}\n{content}")
```

Editing a comment forks the cohort. Roughly half those files provably cannot
change an accum decision — `sector_context` and `company_quality_context` are
DIAGNOSTIC under ADR-057, `market_context_engine` is diagnostic on screen accum,
and `plan_swing` / `swing_setups` / `swing_targets` / `swing_risk_policy` are
plan-only under ADR-067 §3.

### Proxy 2 — hand-typed version constants (under-fires)

Code enters identity only via `SEMANTIC_ENGINE_VERSION` and
`EVIDENCE_CONTRACT_VERSION` (`signal_semantic_contract.py:25,31`), both string
literals a human must remember to change. Change scoring math without bumping
one, and observations from two engines join one cohort silently. Nothing fails.

The comment above those constants shows a human correctly reasoning about which
axis a change belongs on. The mechanism is not wrong — it is **unenforced**.

### Proxy 3 — `config_hash` (does nothing)

`compute_accumulation_config_hash` has one caller
(`accumulation_candidate_observation_persister.py:170`, a write) and one reader
(`audit_source_field_contracts_use_case.py:414`) guarded by
`table == "candidate_observations"` — a table dropped in the 2026-07-27 clean
break. The field is write-only.

### Measured: hashing code is not the fix

Import closure from `accumulation_screen_use_case.py`: **180 files** (107
application, 73 domain).

| Digest scope | files | commits / 60d | forks / week |
|---|---|---|---|
| Full closure | 180 | 229 | ~27 |
| Domain only | 73 | 136 | ~16 |
| Narrowest scoring core | 6 | 28 | ~3.3 |

Weekly totals over the full closure never fall below 9. The `accum_path_v1`
protocol needs 40+ consecutive sessions in one cohort; the longest quiet window
on even the 6-file scope is about 5 days. Source-content digests are unusable at
every granularity — and they cannot distinguish a rename from a threshold change
anyway.

### Provenance is recorded but useless for this

`producer_source_revision.py` yields `ai-saham@0.1.0+git:<sha>`, stored on
snapshots and population bindings — **not** on observations, and not part of
identity. Worse, the snapshot is written once and reused when its digest matches
(`_immutable_insert`, `sqlite_learning_artifact_repository.py:596-625`), so after
an unbumped code change it keeps reporting the *first* build's SHA. It would
report a clean cohort that is not clean.

---

## Decision

### 1. Identity is measured behaviour, not material

Replace the proxies with a direct measurement. Cohort identity for
`ACCUMULATION_DISCOVERY` is the digest of three orthogonal parts:

| Part | Job | Source |
|---|---|---|
| **Behavioral probe digest** | "does the engine answer the same?" | frozen probe set, run offline |
| **ADR-059 snapshot payload digest** | "is the declared policy the same?" | existing seven-row v2 projection |
| **Payload schema version** | "is the stored record the same shape?" | `ACCUMULATION_OBSERVATION_PAYLOAD_SCHEMA_VERSION` |

Nothing else. No config bytes, no hand-typed engine versions.

### 2. The behavioral probe digest

A frozen, fully deterministic set of synthetic candidates is run through the
production accum decision path. Each probe's canonical output projection —
ordering, inclusion/exclusion, Accum/Signal/Risk/Action/readiness — is hashed.
The digest over `{probe_id → output}` is the behavioral identity.

Consequences, all automatic and requiring no human judgement:

| Change | Probe outputs | Cohort |
|---|---|---|
| rename a variable, extract a helper | identical | continues |
| comment or whitespace in any config | identical | continues |
| doc, test, or adapter-only edit | identical | continues |
| change a threshold | move | **forks** |
| change scoring or gate logic | move | **forks** |

This is the same technique as `test_adr062_offline_golden.py`, promoted from a
one-off retirement fixture to the identity mechanism itself.

### 3. Core and extended probe sets

Identity is computed over a **frozen core set** only.

New probes land in an **extended set** used for branch coverage and mutation
testing. Adding an extended probe must not change identity — otherwise improving
coverage would orphan the corpus, and nobody would improve coverage.

Promoting a probe from extended to core is a deliberate cohort boundary,
recorded like any other fork.

### 4. Determinism is a hard precondition

Probes must execute with no clock, no network, no database, no filesystem, and
no iteration-order dependence. Any flap makes identity meaningless and is a
release blocker, not a flake to retry.

The architecture already requires domain purity and deterministic-first
behaviour, so this should hold — but it must be **proven** by repeated-run
equality in CI, not assumed.

### 5. Coverage is enforced, not hoped for

A probe set that misses a branch reintroduces under-forking. Two enforced
measures replace hope:

- **Branch coverage** of the accum decision path under the probe run, with a CI
  floor. New uncovered branches fail the build.
- **Mutation testing**: deliberately perturb scoring constants and comparisons
  and assert the behavioral digest moves. A surviving mutant is a named,
  fixable hole.

Neither exists today, because today's mechanism has nothing measurable in it.

### 6. Record the build on every observation

Add `producer_source_revision` to the observation payload as **provenance beside
identity, not inside it**. It must not participate in `observation_id` or
`artifact_digest`, so idempotent re-capture keeps working exactly as today.

Under this ADR a cohort containing several builds is **expected and reassuring**
— it means different builds were measured to behave identically. The audit
reports it as information, not as an alarm.

### 7. What is deleted

Clean break, no shims, no aliases, no dual-identity path:

- `SEMANTIC_ENGINE_VERSION`, `EVIDENCE_CONTRACT_VERSION` and their pinning tests
- `resolved_config_canonical` and `_SCORING_CONFIG_PATH_ATTRS`
  (`research_accum_backfill_commands.py:76-115`)
- `compute_accumulation_config_hash`, `_CONFIG_HASH_FIELDS`, and the write-only
  `config_hash` payload field
- the dead `candidate_observations` branch in
  `audit_source_field_contracts_use_case.py:414`

### 8. What survives

- **ADR-059 seven-row v2 snapshot** — now identity-material via its payload
  digest. It is a *curated projection of resolved typed policy*, not a YAML
  re-parse, so a comment cannot move it. This is the correct granularity for
  "declared policy changed" and it already exists.
- **`ACCUMULATION_OBSERVATION_PAYLOAD_SCHEMA_VERSION`** — record shape is
  orthogonal to behaviour. A new payload field can leave answers identical while
  breaking a consumer, so it stays in the material.
- **`POLICY_SNAPSHOT_BINDING_CONTRACT`**, population binding, label contracts,
  calendar authority — untouched.
- **`ml-saham` boundary rules** — fail-closed cohort checks are unchanged and
  gain a stronger guarantee. `BOUNDARY.md` must be updated on both sides.

### 9. Data clean break

The corpus is purged and rebuilt under behavioral identity.

This is free **only right now**: all four existing cohorts are already unusable
(1,890 obs with zero snapshots; 349, 304, and 45 obs from one session each,
returning `BLOCKED_POLICY` / `INCONCLUSIVE` / `BLOCKED_DATA`). Every session of
good corpus accumulated after this point makes the change strictly more
expensive. There will not be a cheaper moment.

---

## Do Not Interpret This As

- permission to change any scoring rule, threshold, or gate;
- permission to let a probe read a clock, database, network, or filesystem;
- permission to add core probes casually — core additions are cohort boundaries;
- permission to put `producer_source_revision` inside `observation_id` or
  `artifact_digest`;
- permission to keep a fallback to config-byte or version-constant identity
  "just in case" — one mechanism only;
- permission to lower the coverage floor or ignore a surviving mutant to land a
  change;
- a claim that probe coverage is a proof of behavioural equivalence. It is a
  measured floor over a finite input set, and must be described that way in
  operator and `ml-saham` documentation;
- permission to relabel, migrate, or reinterpret pre-ADR-068 observations.

---

## Consequences

**The human step disappears.** No version constant to forget. This matters most
for AI agents making scoped changes without knowing a bump convention exists —
the failure mode the current design is least protected against.

**Over-forking and under-forking are fixed by the same mechanism**, because both
were symptoms of measuring a proxy instead of the thing.

**Two planned efforts collapse into this one.** A drafted task to trim which
config files count as identity became unnecessary and was deleted — trimming the
file set is moot once files are not identity material. Its fork-warning slice
survives as slice 5 of this ADR's implementation task. A separate
golden/version-bump enforcement task is subsumed entirely.

**Refactoring becomes safe again.** Renames, extractions, and type hints stop
threatening the corpus, which removes the standing incentive against cleaning up
scoring code during an accumulation window.

**Config freeze discipline relaxes but does not vanish.** Config edits that
change declared policy still fork via the snapshot digest. Comment and
formatting edits no longer do.

**Probe construction is real work.** Covering the accum decision surface — four
regimes × setup phases × gate outcomes × entry qualities — is a genuine effort,
not an afternoon, and it is the main cost of this ADR.

**Coverage remains a floor, not a guarantee.** A change touching only branches no
core probe reaches will not fork. Mutation testing bounds that gap and names it;
it does not close it.

---

## Verification and implementation pointers

- `src/application/services/lean_observation_identity.py:77-108`
- `src/adapters/cli/research_accum_backfill_commands.py:76-115`
- `src/domain/value_objects/signal_semantic_contract.py:25,31`
- `src/application/services/accumulation_observation_fingerprint.py:67-101`
- `src/application/services/accumulation_policy_snapshot_payloads.py`
- `src/application/use_case/audit_source_field_contracts_use_case.py:414`
- `src/infrastructure/persistence/sqlite_learning_artifact_repository.py:596-625`
- `src/adapters/composition/producer_source_revision.py`
- `tests/application/services/test_adr062_offline_golden.py` and
  `tests/fixtures/adr062_offline_group_breadth_retirement.v1.json` — the pattern
  to generalise
- `BOUNDARY.md` (both repos)

Implementation task:
[`tasks/backlog/01_implement_adr_068_behavioral_engine_identity.md`](../../tasks/backlog/01_implement_adr_068_behavioral_engine_identity.md).
It lands **before** ADR-067 implementation (which then uses the probe set as its
gate and needs no version bump), and before the corpus accumulation window opens — see
[`tasks/backlog/00_SEQUENCE_accum_baseline_and_learning_loop.md`](../../tasks/backlog/00_SEQUENCE_accum_baseline_and_learning_loop.md).
