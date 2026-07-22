# ML And AI Challenger Roadmap

## Status

**Future and optional.** Nothing in this document blocks deterministic signal
engine completion, canonical observation capture, or ordinary application use.

ADR-042 is the binding architecture decision. This roadmap does not authorize
implementation or production authority by itself.

## Deterministic Champion

The canonical path remains independently executable:

```text
point-in-time input
    -> deterministic SignalEngine + RiskEngine
    -> AssessTradeSetupUseCase
    -> canonical verdict
```

Model libraries, model artifacts, credentials, network access, and challenger
availability must not be required by this path.

## Roadmap A: Narrow Local-ML Evidence

A local model may later emit one narrow typed evidence object. It does not own
ENTER/WATCH/AVOID, risk, sizing, execution, or observation selection.

Before implementation, define:

- evidence meaning and horizon;
- point-in-time feature contract;
- immutable model, feature-schema, training-data, and inference identities;
- missing/unavailable behavior;
- calibration and uncertainty output;
- drift and rollback policy.

Before gaining authority, it must pass
[`parked_evidence_promotion_lane.md`](../../tasks/backlog/parked_evidence_promotion_lane.md).

## Roadmap B: Full-Decision Challengers

A local full-decision model or remote AI/API agent may later produce a separate
non-authoritative assessment against the same immutable input as the champion.

Binding boundary:

- opt-in and parallel;
- persisted and displayed separately;
- explicitly `authoritative = false`;
- failure or timeout cannot alter or delay the champion;
- no fallback, override, blending, or hidden feature injection;
- never consumed by SignalEngine, RiskEngine, TradeSetup, sizing, execution, or
  canonical observation selection;
- never promoted through the evidence-authority lifecycle.

## Activation Conditions

Do not create implementation tasks until a concrete use case identifies:

1. the challenger type and decision being compared;
2. the immutable shared input contract;
3. expected user-facing value beyond deterministic output;
4. local/runtime or provider constraints;
5. paired evaluation and failure semantics;
6. maintenance cost acceptable for the project.

At activation time, write a task-specific application contract. Do not
prebuild generic orchestration, provider, model-registry, or UI abstractions.

## Not In Current Scope

- ML framework selection;
- training pipelines;
- model registry implementation;
- remote API challenger integration;
- online learning;
- automatic evidence or decision promotion;
- automated trading.
