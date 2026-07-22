# ADR-041: Canonical Signal Evidence Input Boundary

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)
**Status:** Accepted — amended 2026-07-22 (discovery ATTACHED_REQUIRED + settled bandar)
**Date:** 2026-07-17
**Current implementation:** Canonical boundary is live for screen and swing. See AUTHORITY-COVERAGE-READINESS and Discovery Authority amendments below.

### Context

The accumulation screener and `saham analyze swing` both reach the canonical
`AssessSignalEvidenceUseCase`, but assemble evidence through different workflow
paths. DQ-002J proved that source availability can be computed and exposed for
`analyze swing`; it deliberately attaches shadow diagnostics after scoring and
is not the target architecture.

Evidence, exact consumed-row provenance, and source availability must not travel
as unrelated facts. Otherwise availability can describe a different repository
read from the one that produced the scored evidence, and separate screen/swing
integrations can drift. This becomes decision-critical when AUTHORITY-COVERAGE-READINESS introduces
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
Moving to enforced authority is an AUTHORITY-COVERAGE-READINESS policy change, not an operator toggle:
it requires both canonical workflows to use this boundary, decision-parity and
negative tests, and explicit review of missing/unassessed-source behavior.

### Historical Artifact Consequence

Future canonical observations must bind the evidence-contract version,
availability/authority-registry version, effective session, source-data cutoff,
resolved config/code identity, and universe identity. The
`ARTIFACT-IDENTITY` task owns that persisted schema. DQ-002J does not make
existing observations canonical.

### Non-Goals

This ADR does not define scoring weights, AUTHORITY-COVERAGE-READINESS readiness predicates, an IDX
holiday calendar, predictive validation, evidence promotion, or ML training.
It does not require every registered or diagnostic data source to become a
production-authority input.

### Consequences

- BENCHMARK-EXCESS-RETURN establishes corrected evidence meaning before the shared boundary is
  implemented.
- `CANONICAL-EVIDENCE-BOUNDARY` then migrates screen and swing in shadow mode
  without changing decisions.
- AUTHORITY-COVERAGE-READINESS may enforce authority coverage/readiness only after that migration is
  verified.
- New evidence producers must expose consumed-row provenance rather than asking
  downstream code to reconstruct or infer it.

### AUTHORITY-COVERAGE-READINESS Amendment (2026-07-18)

`CANONICAL-EVIDENCE-BOUNDARY` and AUTHORITY-COVERAGE-READINESS are both implemented. This amendment
records the resulting behavior without rewriting the historical decision above.

- `AssessSignalEvidenceUseCase` now consumes the canonical evidence input's
  resolved availability to compute `signal_authority_coverage`
  (`SignalEvidenceGroupScorer`), and `DecisionPolicyService` is the sole
  consumer of that coverage plus typed `SetupPhaseReadiness`. Screen and swing
  both cross this same boundary before scoring — neither builds a second,
  independently-assembled availability check after the fact.
- `AvailabilityEnforcementMode.ENFORCED` (added alongside `SHADOW`) is what
  `AssessSignalEvidenceUseCase` now emits. Availability is no longer purely
  observational: an unavailable or non-authoritative required PRODUCTION
  source lowers `signal_authority_coverage`, which `DecisionPolicyService` can
  use to cap ENTER/WATCH.
- Directional score arithmetic is unaffected by this change. `base_score` is
  still computed only from attached evidence groups' scores, exactly as
  before AUTHORITY-COVERAGE-READINESS — availability changes authority coverage and downstream
  decision eligibility only, never the directional score itself.
- `SHADOW` remains a valid mode for any future evidence producer that has not
  yet been wired into authority-coverage enforcement; it is not removed by
  this amendment, only superseded for the setup/flow groups AUTHORITY-COVERAGE-READINESS covers
  today.

### Discovery Authority + Settled Bandar Amendment (2026-07-22)

Screen discovery remains intentionally flow-only (`setup=None` on
`CanonicalSignalEvidenceInput`). That is not a missing setup default and must
not fabricate `SetupEvidence`.

This amendment records two related authority-policy clarifications without
changing the shared evidence / provenance / availability *definitions*:

1. **Authority denominator scope** (`AuthorityDenominatorScope`):
   - `ALL_REQUIRED` (default; swing / full contract): every required
     PRODUCTION group in config stays in the
     `signal_authority_coverage` denominator even when absent.
   - `ATTACHED_REQUIRED` (screen discovery): only required PRODUCTION groups
     attached on this request enter the denominator. Intentionally unattached
     setup is out of scope for that assessment and does not permanently cap
     coverage at flow's weight share.
   Screen and swing still share one scorer, one availability contract, and one
   meaning of each evidence group; only the request declares whether an
   unattached required group is in-scope for this assessment's denominator.

2. **Settled vs complete authority for bandar**:
   - Unassessed contributors (e.g. `bandar_detector`) still force
     `all_authoritative=False` — no complete-authority claim while a real
     contributor went unassessed (invariant preserved).
   - Coverage math uses `settled_authority_fraction` over assessed source
     families, so CURRENT broker settlement can contribute without zeroing
     the whole flow group for unassessed bandar.

Observation schema / semantic / evidence-contract versions bump for this
cohort; older rows remain raw/non-canonical and are not reinterpreted.
