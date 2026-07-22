# Parked — Evidence Promotion Lane

Status: `PARKED` / `DEFERRED`

Retired sources:

- `tasks/done/audit_signal_refactor_contract.md` → promotion tasks
- `tasks/done/signal_evidence_program.md` (phase 4)
- `tasks/done/evidence_validation_and_promotion.md` (retired lane index)

Activation trigger (all required):

1. `DQ-BASELINE-GATE` has passed (closed).
2. Canonical observations and labels exist for the candidate cohort.
3. A named evidence or policy candidate is ready for evaluation.
4. Setup family, horizon, and optional authority segment are predeclared.

Do not build speculative promotion machinery without a named candidate.
Net-executable outcomes, when required, come from
`parked_idx_execution_labels.md`.

## Task Metadata

- Task type: Feature (governance + evaluation infrastructure)
- Priority: High when activated for a named candidate; otherwise deferred
- Semantic classification: typically `EVIDENCE_CONTRACT` plus evaluation/
  persistence schema bumps as designed per sub-task
- Chosen decision: technology-neutral staged promotion with immutable evaluation
  artifacts. Implement the ordered sub-tasks below for one named candidate only.

## Problem Statement

Without evidence-bound evaluation, scoped authority, purged validation, and
reversible staging, diagnostic completeness or YAML metrics can be mistaken for
production authority.

## Desired Outcome

For one named candidate:

- Immutable independently verified evaluation artifacts.
- Authority scoped to evidence + setup_family + horizon (+ optional segment).
- Purged walk-forward with untouched holdout discipline.
- Paired incremental edge vs identical baseline population.
- Staged lifecycle with monitoring and deterministic rollback.
- Baseline provisional authority explicitly recertified or demoted.

## Non-Goals

- No speculative platform for every future evidence type.
- No full-decision ML/API challenger authority through this lane.
- No tuning that writes approval state or authority.
- No global authority from one setup/horizon proof.

## Hard Invariants

- Deterministic rule/config engine remains the champion.
- YAML may request promotion but may not declare its own proof.
- Unknown scopes resolve to `DIAGNOSTIC`.
- Clean break: no alias/fallback dual-path for retired authority keys.
- Full-decision ML/API outputs remain separate non-authoritative challengers.

## Sub-Task Order

| Order | ID | Purpose |
|---:|---|---|
| 1 | `PROMOTION-ARTIFACT-INTEGRITY` | Immutable evaluation artifact + verified hash/gates |
| 2 | `EVIDENCE-AUTHORITY-SCOPE` | Exact-match scoped authority keys |
| 3 | `PURGED-WALKFORWARD-VALIDATION` | Purged folds + untouched holdout |
| 4 | `INCREMENTAL-EVIDENCE-EDGE` | Paired baseline vs baseline+evidence |
| 5 | `STAGED-EVIDENCE-PROMOTION` | Shadow → low-weight → production + rollback |
| 6 | `BASELINE-AUTHORITY-RECERTIFICATION` | Provisional baseline → validated or demoted |

Detailed contracts below. Start only the first incomplete sub-task whose
dependencies are met for the named candidate.

## Required Reading

- `docs/signal_evidence_authority.md`
- `AGENT_QUICKSTART.md` clean-break + semantic classification
- `tasks/done/audit_signal_refactor_contract.md` (archived full prose)
- `tasks/done/evidence_validation_and_promotion.md` (archived lane notes)
- Named candidate design notes (must exist before activation)

## Architecture Impact

```md
Layer plan:
- Domain: authority keys / evaluation identities as needed
- Application: evaluation, verification, transition, monitoring orchestration
- Infrastructure: artifact persistence and hash verification ports
- Adapter: thin approval/CLI surfaces only; no proof ownership
```

## Exact Contracts

### 1. PROMOTION-ARTIFACT-INTEGRITY

Persist an evaluation artifact with at least:

```text
evaluation_id, artifact_hash, created_at, target, evidence_name, setup_family,
horizon, authority_segment when declared, evaluation_period, dataset_snapshot_id,
observation_schema_version, label_schema_version, code_version, config_hash,
IS/OOS metrics, fold metrics, costs, blockers, approval_state
```

Local-ML evidence additionally binds model/feature/training/inference identities,
calibration/uncertainty, drift policy, and rollback target. Full-decision
ML/API challenger artifacts cannot satisfy evidence promotion.

Bootstrap validation loads the artifact through an application port, verifies
hash/gates/identity, and fails closed on missing/mutable/stale/mismatched data.

Close criteria:

- [ ] Forged YAML metrics cannot promote evidence
- [ ] Mutated/missing/hash-mismatched artifacts fail closed
- [ ] Target/evidence/horizon/setup/schema/code/config/segment identities match
- [ ] Local-ML extra identity gates enforced
- [ ] Full-decision ML/API artifacts rejected as evidence-promotion proof

### 2. EVIDENCE-AUTHORITY-SCOPE

Base key:

```text
EvidenceAuthorityKey(evidence_name, setup_family, horizon, authority_segment?)
```

Exact match only; unknown → `DIAGNOSTIC`. Add `authority_segment` only when
predeclared and separately proven. Persist resolved key and registration
version on observations.

Close criteria:

- [ ] Proof for one scope has zero authority elsewhere
- [ ] Unknown scope fails closed to DIAGNOSTIC
- [ ] Retrained/incompatible local-ML cannot inherit older authority
- [ ] Promotion artifacts expose exact scope

### 3. PURGED-WALKFORWARD-VALIDATION

Replace chronological 70/30 as promotion proof with purged folds and an
untouched final holdout. Embargo at least the label horizon; prevent overlapping
outcomes and silent holdout reuse. Report folds, median/worst, concentration,
uncertainty, and hypotheses attempted.

Close criteria:

- [ ] Leakage fixtures fail under naive split and pass under purged folds
- [ ] One exceptional fold cannot hide unstable folds
- [ ] Final holdout usage is recorded and cannot be silently reused

### 4. INCREMENTAL-EVIDENCE-EDGE

On identical observations compare deterministic baseline vs
baseline-plus-evidence (deterministic or eligible narrow local-ML). Report
decision/rank deltas, ENTER precision, missed-winner change, coverage loss,
turnover, net return, MAE/MFE, drawdown, and declared slices. Persist both
decisions and the ablation definition.

Close criteria:

- [ ] Correlated-but-redundant evidence fails
- [ ] Promotion artifact includes paired deltas and subgroup regressions
- [ ] No changed observation population between arms
- [ ] Full-decision ML/API assessments cannot satisfy this task

### 5. STAGED-EVIDENCE-PROMOTION

Lifecycle:

```text
DIAGNOSTIC -> SHADOW_CHALLENGER -> LOW_WEIGHT -> PRODUCTION
                                      |              |
                                      -> SUSPENDED <-
```

Shadow must not change canonical decisions. Authority-increasing transitions
require human action, immutable records, and post-low-weight evidence for
PRODUCTION. Define monitoring and deterministic rollback. Full-decision ML/API
challengers cannot advance to LOW_WEIGHT/PRODUCTION through this task.

Close criteria:

- [ ] Shadow cannot alter live score/decision
- [ ] Same transition mechanism + human-approved record for authority increases
- [ ] PRODUCTION uses post-LOW_WEIGHT evidence
- [ ] Triggered rollback restores prior authority
- [ ] Tuning cannot advance lifecycle state

### 6. BASELINE-AUTHORITY-RECERTIFICATION

Represent authority basis:

```text
LEGACY_BASELINE_PROVISIONAL | OOS_VALIDATED
```

Provisional baseline cannot expand scope/weight without an artifact. Each live
baseline scope is recertified or explicitly demoted; remove silent grandfathering.

Close criteria:

- [ ] Output/persistence distinguish provisional vs validated production
- [ ] Baseline scope cannot expand without an artifact
- [ ] Each live baseline scope is recertified or demoted

## Implementation Checklist

- [ ] Name the candidate, setup family, horizon, and optional segment.
- [ ] Confirm label basis (raw vs net) with the candidate’s claim type.
- [ ] Implement sub-tasks in order; do not skip proof steps.
- [ ] Negative tests for YAML forgery, scope leakage, and challenger misuse.
- [ ] Record completion in this file's Completion Record (no separate lane index).

## Acceptance Criteria

- [ ] All six sub-task close criteria for the named candidate are met, or
      remaining sub-tasks are explicitly still parked with owner/trigger.
- [ ] No full-decision ML/API path gained evidence authority.
- [ ] Focused tests + `git diff --check` pass.

## Do Not Interpret This As

- Do not require this lane for ordinary deterministic bug fixes.
- Do not grant global authority from one setup/horizon.
- Do not treat implementation completeness or aggregate profit factor as proof.
- Do not build separate approval services per lifecycle state.
- Do not start without a named candidate.

## Completion Record

- Completed date:
- Named candidate:
- Sub-tasks delivered:
- Implementation commits:
- Files changed:
- Commands run:
- Verification result:
- Remaining deferred items:
