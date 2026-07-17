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
- The deterministic rule/config baseline remains independently executable.
  Narrow local-ML outputs may become typed evidence producers only after the
  model-specific PIT, OOS, incremental-edge, identity, monitoring, rollback,
  and approval requirements in ADR-042 pass.
- Full-decision ML models and remote AI/API agents may only run as optional,
  parallel, non-authoritative decision challengers against the same immutable
  point-in-time input. Their failure or absence cannot affect the deterministic
  result.
- Deterministic evidence, eligible narrow local-ML evidence, and deterministic
  policy candidates may follow the evidence-authority lifecycle. Full ML/API
  decision challengers do not enter that lifecycle and cannot be promoted to
  LOW_WEIGHT or PRODUCTION under ADR-042.

### Challenger terminology

In this program, `evidence challenger` means a deterministic evidence producer,
an eligible narrow local-ML evidence producer, or a deterministic rule,
configuration, or policy candidate evaluated against the deterministic
baseline.

`Decision challenger` means a separate full ML or API-produced action/assessment.
Decision challengers require their own future application contract and paired
evaluation artifacts. They are not implemented by this program and must not be
introduced as evidence-group producers.

## Phase 1 — Establish source and time truth

**Run:** DQ-000, DQ-001, DQ-002.

**Exit gate: `DQ-CONTRACT-GATE`**

- audit database/fixtures are protected and reproducible;
- source field semantics, units, grain, and availability are explicit;
- one IDX completed-session/effective-time contract exists;
- authoritative live-signal inputs fail closed on future or unavailable rows.

This is a live-authority gate, not a requirement to close every checklist item
in DQ-000 through DQ-002. Diagnostic-only data defects, repair-command safety
hardening, and historical-artifact leakage proof remain open in their owning
tasks but do not block shadow-only Phase 2 semantic repairs. They continue to
block canonical capture, empirical evaluation, tuning, and promotion.

Do not audit/rebuild historical signal artifacts against known-ambiguous signal
semantics before this gate passes.

## Phase 2 — Repair the live signal contract

**Run in order:**

1. HIGH-1 — correct benchmark excess-return semantics and demote unvalidated authority;
2. CANONICAL-EVIDENCE-BOUNDARY — bind evidence, exact consumed-row provenance,
   and source availability in one shared screen/swing in-memory input contract,
   shadow-only and without canonical observation writes;
3. HIGH-2 — replace ambiguous coverage/conviction with authority coverage and typed readiness;
4. ARTIFACT-IDENTITY — separate artifact identity, compatibility cohorts, and provenance;
5. HIGH-3 — remove flags-only pseudo-assessments;
6. MEDIUM-1 — remove producer-local institutional authority;
7. MEDIUM-2 — repair the sector-context identity;
8. MEDIUM-3 — correct output-ownership documentation; canonical dead-field
   exclusion belongs to ARTIFACT-IDENTITY and physical cleanup to DQ-010.

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
7. DQ-009 sentiment audit (independent after Phase 1; not part of the canonical
   signal baseline gate).

The data-quality backlog owns implementation verification for artifact identity,
control populations, and executable labels. The signal backlog owns their
semantic contracts and promotion consequences.

Canonical observation capture semantics begin here, not in Phase 2. Implement
them as a dedicated application use case with two different observation
contracts. `CLI-003` later exposes the lifecycle-correct command routes:

```text
saham learn signal capture --contract accumulation-discovery --session YYYY-MM-DD
saham learn signal capture --contract swing-setup --setup NAME --session YYYY-MM-DD
```

`accumulation-discovery` captures the contemporaneous eligible universe with
selected/rejected state, rejection stage, ranking, and screen evidence.
`swing-setup` evaluates one named setup over its contemporaneous eligible
population and captures typed readiness plus the deeper setup evidence. Both
reuse the canonical signal-evidence input, but their observations and identities
are not interchangeable. Phase 3 verifies the application contract directly;
scheduled production capture starts only after CLI-003 exposes that same use
case without duplicating policy.

Interactive `screen` and `analyze` commands remain assessment consumers and do
not become implicit capture triggers. A manually selected single ticker is
diagnostic inspection, not a canonical learning population; if exposed, use a
separate read-only interface equivalent to `saham analyze signal inspect`.

### Capture scheduling boundary

`install_cron.sh` currently invokes `saham screen accum --universe lq45
--multi --format json` at 19:15 WIB, but screening is read-only. That job is not
observation capture and its successful exit must never count as collection
readiness. Disabling or relabelling it is operational cleanup, not a Phase 2
signal-contract blocker.

The explicit `saham learn signal capture` routes and their cron migration belong
to `CLI-003` in `improvement_cli_restructure.md`, after DQ-011 authorizes the CLI
change. Until then, no legacy screen cron row is canonical or provisional
learning evidence. The eventual cutover must prevent dual writes and migrate
label scheduling to the lifecycle-correct `learn signal labels` route.

**Exit gate: `CANONICAL-EVIDENCE-GATE`**

- selected and rejected eligible-universe rows are PIT and survivorship-safe;
- observations bind compatible code/config/schema/authority/source identities;
- labels bind exact observations and execution-policy versions;
- raw market and net executable outcomes are distinct;
- replay, readiness, and historical evaluation reconcile independently.

## Phase 4 — Clean break and freeze

**Run:** canonical-signal DQ-010 cleanup, then DQ-011. Sentiment-specific
cleanup follows DQ-009 independently.

**Exit gate: `DQ-BASELINE-GATE`**

- invalid/unverifiable artifacts are quarantined or rebuilt;
- canonical consumers reject incompatible versions;
- zero unresolved authoritative signal or accumulation DQ-P0/P1 findings remain
  unless the affected data is explicitly enforced as non-authoritative;
- corrected command/data contracts and golden fixtures are frozen.

This gate unblocks signal and accumulation tasks in
`improvement_cli_restructure.md` plus empirical evidence-challenger evaluation. The
sentiment CLI task additionally requires DQ-009. This gate does not authorize
tuning or promotion.

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
- evidence challenger improves predeclared metrics versus the identical baseline population;
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

This lifecycle applies to deterministic evidence, eligible narrow local-ML
evidence, and deterministic policy candidates. It does not authorize full ML or
API decision assessments to become weighted or production inputs to the
deterministic champion.

**Exit gate: `VALIDATED-PRODUCTION-GATE`**

- live PIT shadow period meets its artifact-defined minimum;
- LOW_WEIGHT and PRODUCTION receive separate manual approvals;
- monitoring and rollback triggers are active and tested;
- every legacy baseline scope is explicitly OOS-validated or demoted;
- no permanent baseline exemption remains.

## Parallelism allowed

- DQ-009 sentiment audit may run after Phase 1 without waiting for signal schema
  repair. It blocks sentiment calibration and CLI-004, not the canonical signal
  baseline or unrelated CLI tasks.
- PROMO-INTEGRITY/AUTH-SCOPE infrastructure may start after ARTIFACT-IDENTITY,
  but cannot approve evidence before Phase 4 and Phase 6 gates.
- CLI design discussion may continue. Signal and accumulation CLI implementation
  remains blocked by DQ-011; the sentiment migration additionally requires DQ-009.
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
