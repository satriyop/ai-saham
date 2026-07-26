# ADR-042: Deterministic Champion, Governed ML Evidence, and Optional Decision Challengers

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — amended by [ADR-049](ADR-049-database-owned-learning-pipeline-clean-break.md)
**Date:** 2026-07-17
**Amends:** ADR-002 and ADR-014

ADR-049 retires AI pre-open prompt/tuning paths and requires deterministic,
database-owned proposal and validation artifacts. It does not promote ML or AI
authority.

## Context

The application is deterministic-first, rule-first, and local-first. Existing
AI integrations explain deterministic results, classify optional sentiment, or
author artifacts that deterministic validators inspect. The signal-evidence
program also uses the word `challenger` for candidate evidence and policy
changes that may eventually earn deterministic authority.

These concepts must not be conflated. A narrow machine-learning output may be a
useful evidence source after rigorous validation. A model or remote AI agent
that emits a full decision is a different concern and must not become a hidden
input, fallback, or override for the deterministic decision path.

## Decision

The deterministic decision path is the canonical **champion**:

```text
point-in-time input
    -> deterministic SignalEngine + RiskEngine
    -> AssessTradeSetupUseCase
    -> canonical verdict
```

The deterministic baseline must always be independently computable. A narrowly
scoped local ML model may additionally produce typed evidence:

```text
same immutable point-in-time input
    |-> deterministic evidence --------------------|
    `-> optional local ML evidence producer --------|-> evidence registry
                                                        -> SignalEngine
                                                        -> deterministic policy
```

Local ML evidence starts diagnostic and gains authority only through the same
evidence registry, immutable evaluation artifacts, explicit scope, and manual
promotion controls used for other evidence. It enters only through its named
evidence registration; it does not directly feed `RiskEngine`,
`AssessTradeSetupUseCase`, sizing, or execution. The deterministic aggregator
and risk/composition policy remain authoritative; the model does not emit or
own the final action.

Full-decision ML models and remote AI/API agents may later run as optional,
non-authoritative **decision challengers**:

```text
same immutable point-in-time input
    |-> deterministic champion -> canonical verdict
    |-> optional full-decision ML challenger -> shadow assessment
    `-> optional API challenger -> shadow assessment

canonical verdict + shadow assessments -> comparison/evaluation artifacts
```

Implement decision challengers as parallel composition, not feature injection.
A challenger assessment is a separate result. It is never a field consumed by
`SignalEngine`, `RiskEngine`, `AssessTradeSetupUseCase`, sizing, execution, or
canonical observation selection.

## Binding invariants

1. The deterministic baseline runs and remains fully usable when all model
   dependencies, model artifacts, credentials, network access, and challenger
   configuration are absent.
2. Local ML evidence must be a narrow typed evidence object, not a final
   ENTER/WATCH/AVOID or risk decision. It must declare direction/strength,
   coverage, conviction, horizon, availability, and immutable model/feature
   identities as applicable to its evidence contract.
3. Local ML evidence begins `DIAGNOSTIC`. Promotion requires leakage-safe PIT
   features, purged walk-forward evaluation, untouched OOS evidence,
   incremental net-of-cost value over the identical baseline population,
   calibration/uncertainty reporting, material subgroup stability, explicit
   human approval, drift monitoring, and deterministic rollback.
4. Missing or failed ML evidence is typed `MISSING`, `UNAVAILABLE`, or
   non-authoritative according to its contract. It must not be neutral-filled,
   reconstructed from future/current data, or replaced by a remote API call.
5. Promoted ML evidence is scoped to the validated model, feature schema,
   setup, horizon, authority segment, and compatible artifact identities.
   Retraining or materially changing features creates a new unpromoted version.
6. Full-decision challenger execution is opt-in. Challenger timeout, failure, malformed
   output, or unavailability cannot alter, delay, suppress, or replace the
   deterministic result.
7. Champion and decision challenger receive the same immutable point-in-time input and
   compatible source, schema, code, configuration, universe, setup, and horizon
   identities. Comparison across incompatible identities fails closed.
8. Champion and decision-challenger outputs are persisted and displayed separately.
   UI/JSON must label challenger output as non-authoritative and must not render
   it as the canonical action.
9. Decision-challenger evaluation uses paired outcomes over the identical eligible
   population. It must not use a challenger-selected population as the champion
   baseline.
10. No automatic override, fallback, action blending, or promotion from a
   full-decision challenger into the champion is permitted.
11. Changing invariant 10 requires a new explicit ADR. Passing shadow or
   out-of-sample evaluation alone does not authorize that architecture change.
12. ML libraries and remote API clients belong behind infrastructure adapters.
   Domain and deterministic application policy remain free of those concrete
   dependencies.
13. A remote API decision challenger must record provider, model,
   request/schema version, response identity, and failure state. A local ML
   evidence producer or decision challenger must record model artifact
   identity, feature schema, training-data identity, and inference version.

## Two distinct promotion concepts

The signal-evidence authority lifecycle applies to deterministic evidence,
eligible narrow local-ML evidence, and deterministic policy candidates:

```text
DIAGNOSTIC -> SHADOW_CHALLENGER -> LOW_WEIGHT -> PRODUCTION
```

Here, `SHADOW_CHALLENGER` means an evidence producer or deterministic policy
candidate under empirical evaluation. Eligible narrow local-ML evidence may
eventually contribute through the deterministic aggregator after model-specific
validation and the existing human-approval gates pass.

A **decision challenger** is different. Full-decision ML and API assessments
remain parallel, non-authoritative shadow outputs. They do not enter the
evidence-authority lifecycle and cannot become `LOW_WEIGHT` or `PRODUCTION`
inputs under this ADR.

## Required future application contract

When decision challengers are introduced, the application layer must own a
typed parallel orchestration contract. At minimum, a challenger assessment must
bind:

- challenger kind (`ML_LOCAL` or `AI_API`);
- model/provider and immutable version identity;
- compatible champion input/artifact identity;
- predicted action, score, and confidence where applicable;
- availability/failure state;
- rationale or output artifact identity;
- an explicit `authoritative = false` invariant.

When local ML evidence producers are introduced, their infrastructure adapter
must load a pinned model artifact and emit a typed domain/application evidence
contract. Training, feature extraction with IO, and inference implementation do
not belong in the domain. Online self-training in the decision path is
prohibited.

Names are not prescribed here. The behavior and separation are binding.

## Current implementation status

- The deterministic champion exists through `SignalEngine`, `RiskEngine`, and
  `AssessTradeSetupUseCase`.
- AI explanation and authoring paths are optional and non-authoritative.
- No governed local-ML evidence producer, general full-decision ML challenger,
  or remote API decision-challenger contract currently exists.
- The custom YAML risk path can consume `SENTIMENT_*` fields, including a
  snapshot produced by the optional AI sentiment classifier. That legacy path
  is not fully aligned with this ADR when AI-derived sentiment affects an
  authoritative custom-rule result. Before claiming full conformance, AI
  sentiment must be emitted as separate challenger/diagnostic output, be rebuilt
  as an ADR-042-compliant governed local-ML evidence producer, or custom
  authoritative rules must accept deterministic sentiment only.

## Non-goals

- Introducing an ML framework, model, training pipeline, or API challenger now.
- Changing current deterministic scoring, risk gates, setup composition, or
  evidence weights.
- Authorizing automated trading or automated model promotion.
- Preventing AI from explaining results or proposing artifacts for deterministic
  validation and explicit human application.

## Consequences

- Deterministic behavior remains reproducible and operationally independent.
- Future local-ML evidence can be evaluated and promoted without transferring
  final decision authority to the model.
- Evidence-producer promotion and full-decision model comparison require
  separate terminology, artifacts, and authority checks.
- Any future proposal to blend or substitute a model's full decision/action
  into canonical decisions must be reviewed as a deliberate architecture
  change rather than an ordinary evidence promotion.
