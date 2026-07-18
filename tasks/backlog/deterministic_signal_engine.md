# Deterministic Signal Engine Work

## Scope

This is the active implementation lane for correcting and completing the
existing deterministic signal engine. None of these tasks requires an ML model,
an AI API, or a decision challenger.

Use this document to answer:

> What must be fixed in the application that exists today?

Detailed implementation contracts remain in
[`audit_signal_refactor_contract.md`](audit_signal_refactor_contract.md). Data
truth and PIT prerequisites remain in
[`audit_data_quality.md`](audit_data_quality.md).

## Agent Entry Point

1. Find the first task below whose state is not `Done` and whose dependency is
   satisfied.
2. Open only that task's detailed contract.
3. Verify its state against current code and tests before editing.
4. Do not start evidence promotion or ML roadmap work from this file.

## Active Order

| Order | Task | State | Evidence / blocker |
|---:|---|---|---|
| 1 | `BENCHMARK-EXCESS-RETURN` | Done | `5b9f3f0 tasks:update, adr:update` |
| 2 | `CANONICAL-EVIDENCE-BOUNDARY` | Done | `2526608 Fix Finding 6: replace fake screen/swing parity test with real boundary test` |
| 3 | `AUTHORITY-COVERAGE-READINESS` | Done | `8c4dee1 Close remaining HIGH-2 Findings and Reconcile Acceptance State` |
| 4 | `ARTIFACT-IDENTITY` | Done (foundation) | `2b0bff1`; canonical capture/readiness integration is owned by DQ-003/DQ-006 |
| 5 | `EVIDENCE-BACKED-ASSESSMENT` | Ready | Current flags-only public paths still exist; no artifact dependency |
| 6 | `CENTRAL-EVIDENCE-AUTHORITY` | Ready | Current producer YAML/dataclass still controls its own status |
| 7 | `SECTOR-CONTEXT-IDENTITY` | Blocked | Requires the active artifact/schema identity contract |

`OUTPUT-CONTRACT-OWNERSHIP` is a deferred, non-blocking documentation cleanup
after `SECTOR-CONTEXT-IDENTITY`. It does not block `LIVE-CONTRACT-GATE`.

The exact task contracts and acceptance criteria are the corresponding
`## Task ...` sections in
[`audit_signal_refactor_contract.md`](audit_signal_refactor_contract.md).
Priority is metadata inside each task; it is not part of task identity.

## Canonical Data Work After Live Contract Repair

These remain deterministic application/data tasks. They do not belong to the
ML roadmap.

| Task | State | Purpose | Owning dependency |
|---|---|---|---|
| `CONTROL-POPULATION` | Blocked | Capture selected and rejected eligible-universe controls | DQ-003 + `ARTIFACT-IDENTITY` |
| `IDX-EXECUTION-LABELS` | Blocked | Produce executable net outcome labels | DQ-004 + `CONTROL-POPULATION` |
| DQ-005 through DQ-011 | See DQ backlog | Replay, readiness, inspection, cleanup, and baseline freeze | [`audit_data_quality.md`](audit_data_quality.md) |

### Capture Boundary

- Interactive `screen` and `analyze` commands are read-only assessment paths.
- Canonical capture is a separate idempotent, universe-driven application use
  case that records selected and rejected controls from one PIT snapshot.
- The current `screen accum --multi` cron invocation is not canonical capture
  and cannot contribute readiness rows.
- CLI and cron migration remain owned by `CLI-003` after DQ-011; no temporary
  screen-side write path is allowed.

## Phase 2 Close Criteria

Phase 2 closes only when:

- one canonical evidence-backed assessment path exists;
- screen and swing preserve the same evidence/provenance contract;
- no flags-only path can return a canonical signal assessment;
- diagnostic evidence cannot gain authority from producer config;
- canonical artifacts bind compatible identity dimensions;
- partial evidence, unavailable evidence, and no evidence remain distinct;
- sector evidence uses a truthful canonical identity.

Phase 2 does **not** require:

- an ML framework or model;
- local-ML evidence;
- a full-decision ML challenger;
- a remote AI/API challenger;
- model training, drift monitoring, or model promotion.

## Do Not Interpret This As

- Do not tune weights or thresholds while repairing contracts.
- Do not promote diagnostic evidence because its implementation is complete.
- Do not implement deferred promotion infrastructure without a concrete
  evidence candidate and canonical evaluation data.
- Do not add ML or API challenger code to close Phase 2.
- Do not duplicate detailed task acceptance criteria in this scan document.

## Solo-Project Proportionality

| Task | Assessment |
|---|---|
| `ARTIFACT-IDENTITY` | Keep the current minimal IDs and provenance. Do not add a generic artifact registry or extra uniqueness infrastructure before canonical capture needs it. |
| `EVIDENCE-BACKED-ASSESSMENT` | Keep. It removes a real misleading public API, not governance ceremony. |
| `CENTRAL-EVIDENCE-AUTHORITY` | Keep. It is a small fail-closed config cleanup that prevents false persisted authority. |
| `SECTOR-CONTEXT-IDENTITY` | Keep. Wrong machine-readable identity contaminates future attribution and promotion. |
| `OUTPUT-CONTRACT-OWNERSHIP` | Simplify and keep non-blocking. It is documentation hygiene, not a Phase 2 runtime gate. |
| `CONTROL-POPULATION` | Keep, but implement one observation contract at a time. Controls are required to measure false negatives without selection bias. |
| `IDX-EXECUTION-LABELS` | Keep a conservative executable model. Unsupported fills remain unavailable; do not build order-book simulation. |
