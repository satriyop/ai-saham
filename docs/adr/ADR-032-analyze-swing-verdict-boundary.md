# ADR-032: `plan swing` Verdict Boundary

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — amended by ADR-037 (MCE); product role of `plan` amended by
[ADR-054](ADR-054-screen-judge-plan-structure-contract.md) and
[ADR-067](ADR-067-retire-setup-quality-and-fix-judgment-authority-by-surface.md)
**Date:** 2026-06-26
**Current implementation:** `TradeSetup.action` remains the only action type when
shown. **Judgment desk** for accumulation is `screen accum` (universe + ticker).
`plan swing` is **trade-structure** design and **carries forward** screen judgment
rather than re-judging (ADR-054/067). MCE on these desks is **display-only Policy A**
(ADR-054/057); risk-side regime adjustment remains preview-only. Engine-level MCE
conditioning when explicitly wired is ADR-037 — not the screen/plan default.

## Decision

`saham plan swing` may display setup, strategy, sentiment, flow, signal,
risk, market-context, and backtest evidence, but those panels do not create
independent trade verdicts.

```text
# When plan shows or carries an action (shared composer / carry-forward):
canonical SignalAssessment + RiskAssessment
  -> AssessTradeSetupUseCase
  -> TradeSetup.action
# Plan must not invent a second Action story (ADR-054/067).
```

- When Action is present, `TradeSetup.action` is the only action vocabulary.
- After ADR-054/067, **deep judgment** for a chosen accum name is
  `screen accum TICKER`; plan designs structure and may **carry forward** that
  verdict instead of recomputing it.
- Setup evaluation answers setup fit and entry authority only (ADR-031).
- Strategy/backtest, sentiment, broker-flow, and detail panels are inspection
  evidence and cannot override `TradeSetup`.
- Market-context panels on plan/screen are **diagnostic under Policy A** unless a
  later task promotes B-MCE into DecisionPolicy (see ADR-037 surface amendment).
- Risk-side market-context adjustment remains preview-only unless a later ADR
  explicitly promotes it.
- CLI/workflow code must not introduce hidden score merging or decision branches.

## Current contract source

Use `saham plan swing --help`, `saham screen accum --help`, current workflow
source, and tests for the available flags and default display. Retired
preview-only signal rules, plan-as-sole-desk wording, and old flag inventories
remain in git history rather than this active ADR.
