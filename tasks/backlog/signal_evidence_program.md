# Signal Evidence Program — Phase Execution Map

## Purpose and authority

This document is the authoritative execution order across:

- `tasks/backlog/audit_data_quality.md` — source truth, PIT/session correctness,
  artifact integrity, quarantine/rebuild, and corrected baseline;
- `tasks/backlog/audit_signal_refactor_contract.md` — signal semantics,
  authority, empirical validation, promotion, monitoring, and recertification;
- `tasks/backlog/improvement_cli_restructure.md` — later command hierarchy only.

It is an orchestration index, not a third task specification or status tracker.
Task contracts and acceptance criteria remain in their owning backlog. Verify
actual completion from code, tests, artifacts, and task disposition; never add
mutable “done” claims here.

Priority describes risk. Phase order describes dependency. A late P0 task is
still critical but cannot execute safely before its prerequisites exist.

## Non-negotiable program invariants

- No tuning or evidence promotion while relevant DQ-P0/P1 findings remain open.
- No historical artifact is canonical without point-in-time provenance and a
  compatible semantic identity.
- Interactive command frequency must not determine the learning population.
  `screen` and `analyze` may construct the same canonical evidence input in
  memory, but ordinary invocations must not create additional canonical
  observations merely because a user ran them.
- Canonical observation capture is a separate, explicit, point-in-time,
  idempotent, universe-driven workflow. Selected candidates and rejected
  controls originate from the same contemporaneous universe snapshot.
- DQ-011 unblocks CLI restructuring and empirical evaluation, not promotion.
- Readiness counts do not prove edge.
- Promotion proof is executable, net-of-cost, incremental, scoped, immutable,
  independently verified, human-approved, monitored, and reversible.
- Legacy baseline PRODUCTION means provisional operational authority until
  recertified; it is not retroactive OOS proof.

## Phase 1 — Establish source and time truth

**Run:** DQ-000, DQ-001, DQ-002.

**Exit gate: `DQ-CONTRACT-GATE`**

- audit database/fixtures are protected and reproducible;
- source field semantics, units, grain, and availability are explicit;
- one IDX completed-session/effective-time contract exists;
- future-row and cutoff tests fail closed.

Do not audit/rebuild historical signal artifacts against known-ambiguous signal
semantics before this gate passes.

## Phase 2 — Repair the live signal contract

**Run in order:**

1. HIGH-1 — correct benchmark excess-return semantics and demote unvalidated authority;
2. CANONICAL-EVIDENCE-BOUNDARY — bind evidence, exact consumed-row provenance,
   and source availability in one shared screen/swing in-memory input contract,
   shadow-only and without canonical observation writes;
3. HIGH-2 — replace ambiguous coverage/conviction with authority coverage and typed readiness;
4. ARTIFACT-IDENTITY — define reproducible semantic identity;
5. HIGH-3 — remove flags-only pseudo-assessments;
6. MEDIUM-1 — remove producer-local institutional authority;
7. MEDIUM-2 — repair the sector-context identity;
8. MEDIUM-3 — remove dead/misleading output and fingerprint semantics.

**Exit gate: `LIVE-CONTRACT-GATE`**

- one canonical evidence-backed assessment path exists;
- screen and swing bind evidence to the same consumed-row provenance and
  shadow availability contract before HIGH-2 enforcement;
- repeated interactive assessment against the same semantic inputs is
  side-effect-free and cannot multiply the learning sample;
- diagnostic evidence cannot gain authority through naming/config shortcuts;
- new observation/label schemas can bind corrected semantics;
- valid partial evidence is distinct from no evidence and unavailable data.

## Phase 3 — Build trustworthy observations and labels

**Run:**

1. CONTROL-POPULATION together with DQ-003;
2. IDX-EXECUTION-LABELS together with DQ-004;
3. DQ-005 replay reproducibility;
4. DQ-006 readiness reconciliation;
5. DQ-007 current signal inspection parity;
6. DQ-008 accumulation historical evaluation;
7. DQ-009 sentiment audit (may run independently after Phase 1).

The data-quality backlog owns implementation verification for artifact identity,
control populations, and executable labels. The signal backlog owns their
semantic contracts and promotion consequences.

Canonical observation capture begins here, not in Phase 2. Implement it as a
dedicated application use case with a thin explicit CLI entry point equivalent
to `saham evidence capture --type signal --session YYYY-MM-DD`. The same use
case may later be invoked by a scheduler or agent. Interactive `screen` and
`analyze` commands remain assessment consumers and do not become implicit
capture triggers.

**Exit gate: `CANONICAL-EVIDENCE-GATE`**

- selected and rejected eligible-universe rows are PIT and survivorship-safe;
- observations bind compatible code/config/schema/authority/source identities;
- labels bind exact observations and execution-policy versions;
- raw market and net executable outcomes are distinct;
- replay, readiness, and historical evaluation reconcile independently.

## Phase 4 — Clean break and freeze

**Run:** DQ-010, then DQ-011.

**Exit gate: `DQ-BASELINE-GATE`**

- invalid/unverifiable artifacts are quarantined or rebuilt;
- canonical consumers reject incompatible versions;
- zero unresolved DQ-P0/P1 findings remain;
- corrected command/data contracts and golden fixtures are frozen.

This gate unblocks `improvement_cli_restructure.md` and empirical challenger
evaluation. It does not authorize tuning or promotion.

## Phase 5 — Install promotion governance

**Run:** PROMO-INTEGRITY and AUTH-SCOPE.

These mechanisms may be implemented after ARTIFACT-IDENTITY, but no artifact may
approve promotion until `DQ-BASELINE-GATE` passes.

**Exit gate: `PROMOTION-GOVERNANCE-GATE`**

- YAML cannot self-declare proof;
- promotion loads and verifies an immutable evaluation artifact;
- authority is exact-scoped by evidence/setup/horizon/market tier;
- unknown scopes resolve to DIAGNOSTIC;
- tuning cannot alter authority or approval state.

## Phase 6 — Prove incremental executable edge

**Run:** WALKFORWARD-VALIDATION, then INCREMENTAL-EDGE.

**Exit gate: `EMPIRICAL-EDGE-GATE`**

- purged/embargoed walk-forward folds and untouched holdout pass;
- executable net outcomes include IDX costs and constraints;
- challenger improves predeclared metrics versus the identical baseline population;
- worst-fold and material subgroup non-regression gates pass;
- uncertainty, concentration, unavailable rate, and hypotheses tried are visible.

Standalone correlation, aggregate profit factor, implementation completeness,
or a favorable diagnostic subgroup cannot pass this gate.

## Phase 7 — Deploy and recertify safely

**Run:** SHADOW-PROMOTION, then BASELINE-RECERT.

Lifecycle:

```text
DIAGNOSTIC -> SHADOW_CHALLENGER -> LOW_WEIGHT -> PRODUCTION
                                      |              |
                                      -> SUSPENDED <-
```

**Exit gate: `VALIDATED-PRODUCTION-GATE`**

- live PIT shadow period meets its artifact-defined minimum;
- LOW_WEIGHT and PRODUCTION receive separate manual approvals;
- monitoring and rollback triggers are active and tested;
- every legacy baseline scope is explicitly OOS-validated or demoted;
- no permanent baseline exemption remains.

## Parallelism allowed

- DQ-009 sentiment audit may run after Phase 1 without waiting for signal schema repair.
- PROMO-INTEGRITY/AUTH-SCOPE infrastructure may start after ARTIFACT-IDENTITY,
  but cannot approve evidence before Phase 4 and Phase 6 gates.
- CLI design discussion may continue, but CLI implementation remains blocked by DQ-011.
- Documentation-only MEDIUM tasks may proceed when they do not freeze or
  preserve semantics that HIGH/DQ tasks are changing.

## Stop conditions for future agents

Stop and report instead of weakening the contract when:

- a prerequisite gate has no reproducible evidence;
- historical universe/source provenance cannot be reconstructed;
- a task requires mixing incompatible artifact versions;
- an evaluation needs an already-inspected final holdout;
- a promotion artifact cannot be independently recomputed;
- a requested compatibility path would restore ambiguous or unsafe authority.
