# ADR-032: `plan swing` Verdict Boundary

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — amended by ADR-037
**Date:** 2026-06-26
**Current implementation:** `TradeSetup.action` is authoritative. Requested MCE context conditions the canonical signal before composition; risk-side regime adjustment remains preview-only.

## Decision

`saham plan swing` may display setup, strategy, sentiment, flow, signal,
risk, market-context, and backtest evidence, but those panels do not create
independent trade verdicts.

```text
canonical SignalAssessment + RiskAssessment
  -> AssessTradeSetupUseCase
  -> TradeSetup.action
```

- `TradeSetup.action` is the command's authoritative action.
- Setup evaluation answers setup fit and entry authority only (ADR-031).
- Strategy/backtest, sentiment, broker-flow, and detail panels are inspection
  evidence and cannot override `TradeSetup`.
- When market context is requested, it conditions SignalEngine before
  composition as defined by ADR-037.
- Risk-side market-context adjustment remains preview-only unless a later ADR
  explicitly promotes it.
- CLI/workflow code must not introduce hidden score merging or decision branches.

## Current contract source

Use `saham plan swing --help`, current workflow source, and tests for the
available flags and default display. Retired preview-only signal rules and old
flag inventories remain in git history rather than this active ADR.
