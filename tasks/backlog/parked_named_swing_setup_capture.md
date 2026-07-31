# Parked — Named Swing Setup Capture

Status: `PARKED`

Retired sources:

- `tasks/done/signal_evidence_program.md` (named-setup extension)
- `tasks/done/audit_data_quality.md` → DQ-003 reservation for swing-setup
- `tasks/done/deterministic_signal_engine.md` → Named Swing Setup Capture
- `tasks/done/audit_signal_refactor_contract.md` → `CONTROL-POPULATION` swing half

Activation trigger: product explicitly requests labels, readiness, attribution,
or tuning claims for a named swing setup (breakout, pullback, mean reversion,
etc.).

Does **not** block `accumulation-discovery` labels or the closed DQ baseline.

## Task Metadata

- Task type: Feature
- Priority: Medium when activated
- Semantic classification: `OBSERVATION_SCHEMA` and `EVIDENCE_CONTRACT`
- Chosen decision: capture population-based evaluations for one explicit named
  swing setup under a distinct observation contract. Implement this option only.

## Problem Statement

`accumulation-discovery` answers discovery/rank questions. Named setup edge
requires a different population contract: evaluate one setup family across its
contemporaneous eligible universe, never a user-picked ticker. Without that
producer, setup-specific readiness and tuning claims are unsafe.

## Desired Outcome

- One explicit setup-family identity per capture.
- Distinct `observation_contract` from `accumulation-discovery`.
- Population evaluation of READY / INCOMPLETE / INELIGIBLE / UNAVAILABLE plus
  required deep setup evidence.
- Idempotent PIT capture reusable by later labels/readiness.
- Interactive screen/analyze remain non-writers.

## Non-Goals

- No compatibility alias or dual write with discovery rows.
- No single-ticker inspection that writes canonical observations.
- No label generation, tuning, or promotion inside this capture task.
- No CLI-003 router as a close criterion (application capture first).

## Hard Invariants

- Discovery and swing-setup observations cannot overwrite or masquerade as each
  other.
- Capture is universe-driven and adapter-independent.
- Clean break for the new contract/cohort.
- Reuse DQ-003 PIT / idempotence / provenance discipline.
- User attention and command frequency must not select the learning population.

## Exact Work Boundary

Expected ownership when activated:

- New capture application use case (or explicit mode on the existing recorder)
  with `observation_contract` reserved for named swing setups
- Setup-family identity binding to `config/swing_setups.yaml` (or successor)
- Persistence rejection of cross-contract overwrite
- Focused population fixtures (not single-ticker happy paths)

Reserved future CLI (not close criteria):

```text
saham learn signal capture --contract swing-setup --setup NAME --session YYYY-MM-DD
```

Read-only diagnostic (must not write):

```text
saham analyze signal inspect TICKER --contract swing-setup --setup NAME --session YYYY-MM-DD
```

## Required Reading

- `AGENT_QUICKSTART.md`, `AGENTS.md`, `TASK_TEMPLATE.md`
- `tasks/done/deterministic_signal_engine.md` (archived named-setup notes)
- `tasks/done/audit_data_quality.md` → DQ-003 contract reservation
- `parked_screen_filter_replay_contract.md` if recall/filter replay is needed
- `parked_historical_eligible_universe_membership.md` if historical membership
  is required
- Current `RecordAccumulationObservationsUseCase` and contract rejection tests

## Architecture Impact

```md
Layer plan:
- Domain: setup-family / observation-contract identities
- Application: named-setup capture orchestration and fail-closed writes
- Infrastructure: persistence predicates for the new contract
- Adapter: thin future CLI wiring only after application contract exists
```

## Exact Contract

- Require `--setup NAME` (or equivalent request field); reject missing setup.
- Evaluate the named setup across its contemporaneous eligible population.
- Capture READY, INCOMPLETE, INELIGIBLE, and UNAVAILABLE states plus required
  deep setup evidence.
- Consume shared `CanonicalSignalEvidenceInput`; do not reuse discovery rows
  merely because ticker/session match.
- Persist lean identity at minimum (`observation_contract` +
  `semantic_compatibility_id`); full apparatus stays in
  `parked_artifact_identity_apparatus.md`.
- Keep label generation separate and blocked until this capture contract lands.

## Implementation Checklist

- [ ] Confirm named setup family and activation consumer.
- [ ] Implement application capture with distinct observation_contract.
- [ ] Prove discovery rows cannot be overwritten/substituted.
- [ ] Population fixtures for READY/INCOMPLETE/INELIGIBLE/UNAVAILABLE.
- [ ] Prove single-ticker inspection remains read-only.
- [ ] Document label/readiness follow-ons as separate tasks.

## Acceptance Criteria

- [ ] Swing-setup capture requires a named setup and evaluates a population.
- [ ] Distinct contract/identity from `accumulation-discovery`.
- [ ] Idempotent PIT capture; interactive commands write nothing.
- [ ] Capture does not generate labels, tune, or promote.
- [ ] Focused tests + `git diff --check` pass.

## Do Not Interpret This As

- Do not treat discovery observations as setup-edge evidence.
- Do not admit manually selected tickers into the canonical setup population.
- Do not implement CLI-003 as a substitute for the application contract.
- Do not claim setup promotion from capture completeness alone.

## Completion Record

- Completed date:
- Setup families delivered:
- Implementation commit:
- Files changed:
- Commands run:
- Verification result:
- Deferred label/readiness owners:
