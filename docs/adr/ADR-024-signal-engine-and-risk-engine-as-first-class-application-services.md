# ADR-024: Signal Engine and Risk Engine as First-Class Application Services

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted
**Date:** 2026-06-24
**Current implementation:** SignalEngine and RiskEngine are separate, injectable, deterministic application services. Current schemas and policies live in their implementation, factories, and dedicated config files.

## Decision

- SignalEngine answers whether entry evidence is sufficiently strong and
  aligned. It owns canonical signal scoring and classification.
- RiskEngine answers whether structural or execution conditions block acting.
  It owns deterministic risk gates.
- Neither engine is adapter logic, and neither reads the other's assessment.
- Complete trade actions compose both assessments only through
  `AssessTradeSetupUseCase` as defined by ADR-026.
- Workflow-specific screening/setup policy stays outside the engines.

## Configuration contract

- Signal policy belongs in `config/signal_engine.yaml`.
- Risk policy belongs in `config/risk_engine.yaml`.
- Config is parsed and validated by infrastructure and injected as typed policy;
  engines do not load YAML.
- Supported component enablement, thresholds, weights, and missing-evidence
  behavior must be explicit and validated. Invalid config must fail clearly;
  it must not silently fall back.
- A disabled component cannot contribute to scoring or blocking. Any weight
  redistribution must be deterministic and defined by the current scorer.

## Current implementation pointers

- `src/application/services/signal_engine.py`
- `src/application/use_case/assess_signal_evidence_use_case.py`
- `src/application/services/risk_engine.py`
- `src/application/services/engine_bootstrap/`
- `config/signal_engine.yaml`
- `config/risk_engine.yaml`

The retired six-factor schema, old bootstrap paths, and earlier class-level
interfaces are preserved in git history, not as active implementation guidance.

## Consequences

- Adapters and workflows cannot invent substitute composite signal or risk
  scores.
- Signal and risk remain independently testable and explainable.
- Policy changes remain reviewable configuration changes without moving
  workflow ownership into adapters.
