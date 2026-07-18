# Signal Evidence Program

## Purpose

This is the concise execution index. It defines lane boundaries and dependency
order; it does not duplicate task contracts or maintain independent completion
claims.

## Choose The Correct Lane

| Question | Lane | Document |
|---|---|---|
| What must be fixed in the existing deterministic engine? | Active deterministic work | [`deterministic_signal_engine.md`](deterministic_signal_engine.md) |
| Is source data, PIT behavior, replay, or artifact integrity wrong? | Active data correctness | [`audit_data_quality.md`](audit_data_quality.md) |
| Is new evidence seeking authority in the deterministic engine? | Deferred evidence governance | [`evidence_validation_and_promotion.md`](evidence_validation_and_promotion.md) |
| Are we proposing a local model or remote AI/API challenger? | Future optional roadmap | [`ml_ai_challengers.md`](../../docs/roadmap/ml_ai_challengers.md) |
| Do I need the exact implementation contract for an existing signal task? | Detailed contract appendix | [`audit_signal_refactor_contract.md`](audit_signal_refactor_contract.md) |

## Program Sequence

```text
1. DATA AND TIME TRUTH
   DQ-000 -> DQ-001 -> DQ-002
   Exit: DQ-CONTRACT-GATE

2. DETERMINISTIC LIVE CONTRACT
   BENCHMARK-EXCESS-RETURN
   -> CANONICAL-EVIDENCE-BOUNDARY
   -> AUTHORITY-COVERAGE-READINESS
   -> ARTIFACT-IDENTITY
   -> EVIDENCE-BACKED-ASSESSMENT
   -> CENTRAL-EVIDENCE-AUTHORITY
   -> RETIRE-LEGACY-SIX-FACTOR-BASELINE
   -> SECTOR-CONTEXT-IDENTITY
   Exit: LIVE-CONTRACT-GATE

   Non-blocking documentation cleanup after the live contract:
   OUTPUT-CONTRACT-OWNERSHIP

3. CANONICAL OBSERVATIONS AND LABELS
   CONTROL-POPULATION + DQ-003
   -> IDX-EXECUTION-LABELS + DQ-004
   -> DQ-005 through DQ-011
   Exit: CANONICAL-EVIDENCE-GATE, then DQ-BASELINE-GATE

4. EVIDENCE VALIDATION AND PROMOTION
   Start only for a named candidate after canonical data is ready.
   See evidence_validation_and_promotion.md.

5. OPTIONAL ML/API ROADMAP
   Not active and never a blocker for deterministic completion.
```

## Non-Negotiable Invariants

- The deterministic rule/config engine is the canonical champion.
- Every task in this program is a clean break. Removed contracts are rejected;
  they are never retained as aliases, fallbacks, translations, dual paths, or
  active historical compatibility layers.
- Historical payloads may remain unchanged only in quarantine or raw audit
  storage. Quarantined data cannot participate in execution, labeling,
  attribution, readiness, tuning, promotion, or canonical reads.
- New schemas create new canonical cohorts. Rebuild through the new producer;
  never rewrite old payloads to impersonate the new contract.
- No historical artifact is canonical without PIT provenance and compatible
  semantic identity.
- Interactive command frequency must not determine the learning population.
- Ordinary `screen` and `analyze` commands remain read-only assessment paths.
- Readiness counts do not prove edge.
- Diagnostic evidence cannot gain authority through YAML or naming shortcuts.
- Full-decision ML/API challengers remain separate and non-authoritative.
- No tuning or promotion while relevant DQ-P0/P1 findings remain unresolved.

## Gate Meaning

| Gate | Proves | Does not prove |
|---|---|---|
| `DQ-CONTRACT-GATE` | Authoritative source/time inputs fail closed | Historical learning readiness |
| `LIVE-CONTRACT-GATE` | Existing deterministic assessment semantics are coherent | Edge or promotion eligibility |
| `CANONICAL-EVIDENCE-GATE` | Observations and labels are compatible and reproducible | Positive predictive value |
| `DQ-BASELINE-GATE` | Corrected deterministic baseline is frozen | Any challenger deserves authority |

Promotion-specific validation is intentionally deferred to the evidence
governance lane. ML/API implementation is intentionally deferred to the roadmap.

## Agent Rules

1. Start here and choose exactly one lane.
2. Read only that lane and the exact owning task contract.
3. Verify task state against current code and tests.
4. Do not implement roadmap work to satisfy deterministic close criteria.
5. Do not copy mutable task status into this index.
6. Stop if a task crosses lane boundaries without an explicit dependency.
7. Apply the program-wide clean-break policy even when an older task appendix
   mentions compatibility, mapping, aliases, or active legacy interpretation;
   that older language is superseded.
8. Do not globally remove a genuine active concept merely because a retired
   scoped identity used the same word. Prove the namespace boundary with a
   negative regression test.

Stop rather than weakening a contract when a prerequisite gate lacks
reproducible evidence, artifacts have incompatible identities, historical PIT
provenance cannot be established, a final holdout has already been inspected,
or an evaluation artifact cannot be independently verified.
