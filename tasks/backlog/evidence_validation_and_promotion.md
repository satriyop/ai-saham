# Evidence Validation And Promotion

## Scope

This is the technology-neutral governance lane for evidence or deterministic
policy changes seeking new or expanded authority inside the deterministic
engine.

For plain-language **current** PRODUCTION / DIAGNOSTIC meanings (not task
status), see [`docs/signal_evidence_authority.md`](../../docs/signal_evidence_authority.md).

It applies to:

- new deterministic evidence;
- changed deterministic setup or policy candidates;
- eligible narrow local-ML outputs represented as typed evidence.

It does not apply to ordinary bug fixes, output renames, or full-decision
ML/API challengers.

## Activation Trigger

This lane is deferred. Start it only when all of the following are true:

1. `DQ-BASELINE-GATE` has passed.
2. Canonical observations and executable labels exist.
3. A named evidence or policy candidate is ready for evaluation.
4. Its proposed setup family, horizon, and optional authority segment are
   predeclared.

Infrastructure may be prepared earlier only when an active deterministic task
requires the same contract. Do not build speculative promotion machinery merely
because this roadmap exists.

## Task Order

| Order | Task | State | Purpose |
|---:|---|---|---|
| 1 | `PROMOTION-ARTIFACT-INTEGRITY` | Deferred | Bind every authority request to immutable independently verified evidence |
| 2 | `EVIDENCE-AUTHORITY-SCOPE` | Deferred | Prevent authority from leaking outside validated setup/horizon scope |
| 3 | `PURGED-WALKFORWARD-VALIDATION` | Deferred | Replace one chronological split with purged folds and untouched holdout |
| 4 | `INCREMENTAL-EVIDENCE-EDGE` | Deferred | Compare baseline and baseline-plus-evidence on the identical population |
| 5 | `STAGED-EVIDENCE-PROMOTION` | Deferred | Shadow, cap exposure, monitor, suspend, and roll back |
| 6 | `BASELINE-AUTHORITY-RECERTIFICATION` | Deferred | Validate or demote provisional legacy baseline authority |

Detailed contracts remain in
[`audit_signal_refactor_contract.md`](audit_signal_refactor_contract.md).
`Deferred` means the task is intentionally inactive until the activation
trigger passes; unchecked criteria do not imply partial implementation.

## Authority Scope

The base authority key is:

```text
evidence + setup_family + horizon
```

Add an `authority_segment`, such as market tier, only when the evidence
contract predeclares it and evaluation proves the segment separately. Do not
prepopulate a Cartesian matrix of evidence, setup, horizon, tier, regime, and
liquidity buckets.

Unknown scopes resolve to `DIAGNOSTIC`.

Existing baseline `PRODUCTION` authority remains provisional until recertified;
it is not retroactive out-of-sample proof and cannot justify scope or weight
expansion.

## Lifecycle

```text
DIAGNOSTIC -> SHADOW_CHALLENGER -> LOW_WEIGHT -> PRODUCTION
                                      |              |
                                      -> SUSPENDED <-
```

`LOW_WEIGHT` is a technical exposure cap, not a separate organizational role.
Use one promotion-transition mechanism for all authority changes. Every
authority-increasing transition requires explicit human action and an immutable
record. Advancement from `LOW_WEIGHT` to `PRODUCTION` must use evidence gathered
after low-weight deployment; two approvals against the same unchanged evidence
are not sufficient.

## Non-Negotiable Proof

- point-in-time and leakage-safe inputs;
- immutable semantic and provenance identity;
- purged/embargoed walk-forward evaluation;
- untouched holdout discipline;
- net-of-cost executable outcomes;
- paired incremental value over the identical baseline population;
- material subgroup and worst-fold reporting;
- monitoring, suspension, and deterministic rollback;
- YAML cannot declare its own proof;
- tuning cannot change authority or approval state.

## Solo-Project Proportionality

- Build this lane only for a named candidate, never as speculative platform
  infrastructure.
- Use one evaluation-artifact shape and one transition mechanism; do not build
  separate approval services for each lifecycle state.
- Scope authority by evidence, setup, and horizon. Add a segment only after
  observed data proves it is materially necessary.
- Begin with the minimum purged walk-forward and paired-ablation metrics needed
  for the candidate. Add subgroup dimensions only when sample size supports
  them.
- Local-ML identity and drift fields are conditional requirements only when the
  candidate is a local-ML evidence producer.
- Full-decision ML/API challenger orchestration remains in the future roadmap
  and is never required by this lane.

## Do Not Interpret This As

- Do not require this lane for deterministic bug fixes.
- Do not grant global authority from one setup or horizon.
- Do not treat implementation completeness, correlation, or aggregate profit
  factor as promotion proof.
- Do not route full-decision ML/API outputs through this lifecycle.
- Do not build a separate approval subsystem for every lifecycle state.
