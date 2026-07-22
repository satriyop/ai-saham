# Parked — Artifact Identity Apparatus

Status: `PARKED`

Retired sources:

- `tasks/done/audit_signal_refactor_contract.md` → Task `ARTIFACT-IDENTITY`
- `tasks/done/audit_data_quality.md` → DQ-003 lean identity amendment
- `tasks/done/signal_evidence_program.md` (parked list)

Foundation + lean capture integration are **Done**. This task owns only the
parked full three-part apparatus.

Already shipped (do not rebuild):

- Identity value objects, resolver, persistence support, semantic-contract
  registry (foundation slices through `2b0bff1`)
- Lean capture: `observation_contract` + config-content-hash
  `semantic_compatibility_id` on `accumulation-discovery` (DQ-003)
- Readiness cohort isolation (DQ-006)

## Task Metadata

- Task type: Feature / Refactor
- Priority: Low until a named trigger fires; then High for that slice only
- Semantic classification: `OBSERVATION_SCHEMA` and/or `EVIDENCE_CONTRACT`
  depending on the woken slice
- Chosen decision: graduate only the parked piece whose trigger fired.
  Implement that slice only.

## Activation Triggers

| Trigger | Wake this parked piece |
|---|---|
| ML challenger over-forks because immaterial config edits split cohorts | Per-path material-config registry (`signal_semantic_contract.py`) |
| A second producer exists so one compatibility cohort spans multiple artifacts | `artifact_id` vs `semantic_compatibility_id` split + resolver wiring |
| An ML evidence producer is promoted and needs drift monitoring / rollback | Full `ArtifactProvenance` field consumption |
| Survivorship must be corrected, not merely disclosed | Historical universe-membership platform (also see controls task) |

Until a trigger fires, lean close criteria remain satisfied. Do not wire parked
machinery “for completeness.”

## Problem Statement

Lean identity intentionally parks full apparatus to avoid silent under-forking
and premature uniqueness complexity. Named product needs (multi-producer
cohorts, material-config precision, provenance consumers, universe warehouse)
still require the parked pieces.

## Desired Outcome

For each woken slice only:

- Material registry: only material paths fork compatibility; display-only edits
  do not.
- `artifact_id`: uniqueness/idempotency separate from cohort pooling.
- Provenance: full audit trail available to monitored producers without becoming
  a silent cohort key.
- Universe warehouse: membership corrected, not only disclosed.

## Non-Goals

- No rewrite of lean DQ-003 acceptance as incomplete.
- No deleting parked but tested identity machinery before a trigger.
- No treating over-forking from whole-config hash as a bug to “fix” without
  a material-registry trigger.
- No promotion authority from identity completeness alone.

## Hard Invariants

- Clean break for any new schema/cohort.
- Three concepts stay distinct: `artifact_id`, `semantic_compatibility_id`,
  `provenance`.
- Dead field `regime_detection_method_at_signal` stays excluded from new
  canonical fingerprint schema.
- Readers reject unsupported semantic combinations; never pool silently.
- CLI name, user identity, display flags, and invocation count are never
  identity dimensions.

## Exact Work Boundary

Inspect and extend only the woken slice among:

- `src/application/services/` identity / semantic-contract modules
- Observation/label persistence and codecs
- Capture writers that currently leave parked columns empty
- Focused identity contract tests

Leave parked `# PARKED — not wired` markers until their trigger fires.

## Required Reading

- `AGENT_QUICKSTART.md` semantic-change classification
- `tasks/done/audit_signal_refactor_contract.md` → `ARTIFACT-IDENTITY`
- `tasks/done/audit_data_quality.md` → DQ-003 lean identity amendment
- Current lean capture identity path and foundation modules

## Architecture Impact

```md
Layer plan:
- Domain: identity value objects / serialization only as needed
- Application: resolver, registry, capture wiring for the woken slice
- Infrastructure: persistence columns / codecs if required
- Adapter: not touched unless a display must expose new identity fields
```

## Exact Contract (full apparatus — implement only woken slice)

```text
artifact_id               # uniqueness/idempotency for one captured artifact
semantic_compatibility_id # whether artifacts may be pooled
provenance                # complete audit trail, not automatically a cohort key
```

`artifact_id` inputs (when woken):

```text
artifact_type + semantic_compatibility_id + effective_session + ticker
+ universe_snapshot_id + source snapshot/cutoff identity
```

`semantic_compatibility_id` material dimensions (when registry woken):

```text
observation_contract + setup_family when applicable
+ evidence_contract_version + observation/label schema versions
+ semantic engine/scoring contract version
+ resolved material scoring/policy config hash
+ resolved authority registrations hash
+ execution/label-policy version when outcomes are compared
```

Hash deterministic canonical serialization. Fail closed when required identity
inputs cannot be resolved.

## Implementation Checklist

- [ ] Record which trigger fired and which slice is in scope.
- [ ] Classify semantic change before editing.
- [ ] Wire only that slice; leave other parked markers.
- [ ] Negative tests for silent pooling / under-forking / over-claiming.
- [ ] Update consumers that must reject incompatible identities.

## Acceptance Criteria

- [ ] Only the triggered slice is wired and tested.
- [ ] Untouched parked slices remain explicitly parked.
- [ ] Compatibility pooling rules match the contract for the woken slice.
- [ ] Focused tests + `git diff --check` pass.

## Do Not Interpret This As

- Do not implement the full apparatus because foundation code exists.
- Do not put `universe_snapshot_id` into upsert keys without the universe
  trigger and a deliberate idempotence redesign.
- Do not treat lean whole-config hashing as defective without an over-fork
  trigger.
- Do not grant promotion authority from identity wiring alone.

## Completion Record

- Completed date:
- Trigger that fired:
- Slice delivered:
- Implementation commit:
- Files changed:
- Commands run:
- Verification result:
- Remaining parked slices:
