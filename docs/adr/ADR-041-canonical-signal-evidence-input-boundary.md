# ADR-041: Canonical Signal Evidence Input Boundary

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)
**Status:** Accepted — implementation pending
**Date:** 2026-07-17
**Current implementation:** Not yet canonical production architecture. DQ-002J provides a prototype/assessment path; rollout must follow the shadow-to-enforcement lifecycle in this ADR.

### Context

The accumulation screener and `saham analyze swing` both reach the canonical
`AssessSignalEvidenceUseCase`, but assemble evidence through different workflow
paths. DQ-002J proved that source availability can be computed and exposed for
`analyze swing`; it deliberately attaches shadow diagnostics after scoring and
is not the target architecture.

Evidence, exact consumed-row provenance, and source availability must not travel
as unrelated facts. Otherwise availability can describe a different repository
read from the one that produced the scored evidence, and separate screen/swing
integrations can drift. This becomes decision-critical when HIGH-2 introduces
production-authority coverage and typed setup readiness.

### Decision

Every signal-evidence group that can carry production authority must cross one
canonical application boundary that binds:

1. the immutable evidence value;
2. exact provenance of the source rows actually consumed; and
3. resolved source-availability assessments for those contributors.

Conceptually:

```text
source rows
    -> evidence builder
         -> evidence + exact consumed-row provenance
    -> source availability assessment
    -> canonical signal-evidence input
    -> AssessSignalEvidenceUseCase
    -> score, authority coverage, readiness, and diagnostics
```

The exact class names may evolve, but the relationship is binding: evidence and
the provenance/availability that authorize it are one typed input contract.
Both the candidate-producing accumulation screen and single-ticker swing
analysis must use that same boundary. Workflow-specific post-score attachment is
permitted only as temporary shadow instrumentation.

### Ownership And Invariants

- Infrastructure readers return rows and stored temporal facts; they do not
  decide freshness or scoring authority.
- Application evidence builders record the sources and exact rows/dates or
  timestamps actually consumed.
- The application availability service classifies that provenance as
  `CURRENT`, `LATE`, `STALE`, `PARTIAL`, `UNKNOWN`, `INVALID`, or
  `DIAGNOSTIC_ONLY`.
- `AssessSignalEvidenceUseCase` consumes typed evidence inputs and owns signal
  scoring/authority policy; it never queries repositories.
- Adapters construct concrete dependencies and render returned facts; they do
  not calculate availability or authority.
- Missing provenance fails closed. An unavailable required production source is
  not silently neutral-filled or removed from an authority denominator.
- Diagnostic evidence cannot improve production-authority coverage.
- Any consumed but unassessed contributor prevents a complete-authority claim.
- One resolved effective market session and compatible calendar snapshot are
  reused for one workflow execution.
- Screen and swing must not maintain different definitions of the same evidence
  group, provenance, availability, or authority.

### Shadow-To-Enforcement Lifecycle

`SHADOW` availability is observable but cannot affect score, coverage,
classification, candidate selection, persistence eligibility, or TradeSetup.
Moving to enforced authority is a HIGH-2 policy change, not an operator toggle:
it requires both canonical workflows to use this boundary, decision-parity and
negative tests, and explicit review of missing/unassessed-source behavior.

### Historical Artifact Consequence

Future canonical observations must bind the evidence-contract version,
availability/authority-registry version, effective session, source-data cutoff,
resolved config/code identity, and universe identity. The
`ARTIFACT-IDENTITY` task owns that persisted schema. DQ-002J does not make
existing observations canonical.

### Non-Goals

This ADR does not define scoring weights, HIGH-2 readiness predicates, an IDX
holiday calendar, predictive validation, evidence promotion, or ML training.
It does not require every registered or diagnostic data source to become a
production-authority input.

### Consequences

- HIGH-1 establishes corrected evidence meaning before the shared boundary is
  implemented.
- `CANONICAL-EVIDENCE-BOUNDARY` then migrates screen and swing in shadow mode
  without changing decisions.
- HIGH-2 may enforce authority coverage/readiness only after that migration is
  verified.
- New evidence producers must expose consumed-row provenance rather than asking
  downstream code to reconstruct or infer it.
