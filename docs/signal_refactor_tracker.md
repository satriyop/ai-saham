# Signal Engine Refactor Tracker

_Design rationale: `docs/signal_refactor.md`_
_Phase plan: `docs/signal_refactor_phases.md`_
_Current implementation target: Phase A2_
_Updated: 2026-07-05_

This tracker records the current implementation state and concrete checklist for
the SignalEngine refactor. It is intentionally A2-focused: A1 is preserved as
Done, A2 is the active implementation target, and later phases remain out of
scope until their phase is explicitly opened.

---

## Authority

- `docs/signal_refactor.md` remains the design rationale.
- `docs/signal_refactor_phases.md` remains the execution plan.
- This tracker records current state and the concrete implementation checklist.
- If this tracker conflicts with the design rationale or phase plan, pause and
  update the tracker before implementation continues.

---

## Non-Negotiable Boundaries

- RiskEngine remains the only hard trade-risk gate authority.
- SignalEngine emits evidence, coverage/conviction, setup phase, context, and
  decision constraints.
- DecisionPolicy combines SignalEngine output with regime constraints.
- TradeSetup owns final stop, target, and position size.
- Regime evidence must not mutate the raw stock score.
- `enter_allowed=false` remains the authoritative ENTER block.
- Setup-specific policy may tighten regime policy, not loosen it.
- CLI adapters render results only; no scoring, cache, persistence, or workflow
  policy belongs in adapters.
- A2 may add regime persistence.
- A2 must not start Phase B ticker-level signal forward labels.
- IDX foreign-flow transition inputs stay diagnostic / low-authority until
  market-level labels prove lead-time value.

---

## Phase Overview

| Phase | Name | Status | Notes |
|---|---|---|---|
| Legacy 0-8 | Staged Evidence Foundation | Done | Historical foundation. |
| A1 | Regime Eligibility Policy Quick Win | Done | Implemented and verified; decision constraints are explicit. |
| A2 | Full RegimeDetectionEvidence And Replay | In Progress | Active implementation target. |
| B | Minimal Forward Labels And Observation Fingerprints | Not Started | Out of scope for A2; do not add ticker-level signal forward labels. |
| C | SetupPhaseState And Continuous Setup/Trigger Scoring | Not Started | Retain phase scope from `docs/signal_refactor_phases.md`. |
| D | Strategy Evidence Harness | Not Started | Retain phase scope from `docs/signal_refactor_phases.md`. |
| E | Institutional Accumulation Evidence | Not Started | Retain phase scope from `docs/signal_refactor_phases.md`. |
| F | Minimal Ticker Profile Diagnostics | Not Started | Retain phase scope from `docs/signal_refactor_phases.md`. |
| G | Simplified Alpha/Trigger Split | Not Started | Retain phase scope from `docs/signal_refactor_phases.md`. |
| H | Sector Context | Not Started | Retain phase scope from `docs/signal_refactor_phases.md`. |
| I | Full Walk-Forward Calibration And Expanded Tunables | Not Started | Retain phase scope from `docs/signal_refactor_phases.md`. |

---

## Phase A1 Tracker

**Status:** Done

**Goal:** reduce false positives immediately with explicit regime eligibility
policy.

Phase A1 is complete. Its implementation target was the quick regime eligibility
policy win, not replayable regime evidence or persistence.

### Implemented Scope

- Config-driven regime thresholds.
- `enter_allowed`.
- `max_decision`.
- `regime_size_multiplier`.
- WATCH / diagnostic coverage-conviction floors.
- Setup-specific regime compatibility policy.
- Setup family source priority where needed.
- Decision constraints emitted in application output.

### Verified A1 Guarantees

- RISK_ON, NEUTRAL, RISK_OFF, and VOLATILE decisions are deterministic.
- RISK_OFF / VOLATILE cannot emit ENTER when `enter_allowed=false`.
- `enter_allowed=false` blocks ENTER regardless of coverage/conviction floors.
- Setup-specific policy cannot re-enable ENTER under RISK_OFF/VOLATILE.
- Decision constraints are visible in signal/swing workflow output.
- CLI adapters display constraints only; policy remains outside adapters.

### A1 Output Contract

Application-layer signal/swing workflow results expose:

- `decision_constraints.max_decision`
- `decision_constraints.regime`
- `decision_constraints.regime_enter_allowed`
- `decision_constraints.regime_size_multiplier`
- `decision_constraints.setup_family`
- `decision_constraints.setup_regime_action`
- `decision_constraints.effective_size_multiplier`
- `decision_constraints.constraint_reasons`

---

## Phase A2 Tracker

**Status:** In Progress

**Goal:** build full replayable market-regime evidence after A1 policy is
explicit.

A2 should extend existing MarketContext infrastructure where possible while
making regime detection deterministic, replayable, and empirically validatable
at the market level.

### In Scope

- Deterministic `RegimeDetectionEvidence`.
- Replayable `regime_observations`.
- Regime confidence.
- Regime stability.
- Days in regime.
- Detection input fingerprints.
- IDX foreign-flow 5d/20d inputs.
- IHSG-weighted foreign buy/sell streaks.
- Regime forward labels.
- Market-level validation.

### Out Of Scope

- SignalEngine Alpha/Trigger rewrite.
- `SetupPhaseState`.
- Ticker-level signal forward labels from Phase B.
- Changing raw stock scores by regime.
- TradeSetup sizing math.
- Making IDX foreign-flow high-authority before labels prove value.

### Implementation Checklist

- [ ] Inspect current `MarketContext`, `MarketContextEngine`,
      `BuildMarketContextUseCase`, and SQLite market-context repository.
- [ ] Define `RegimeDetectionEvidence` as deterministic evidence/fingerprint
      output.
- [ ] Define persistence contract for `regime_observations`.
- [ ] Persist detection inputs listed in `docs/signal_refactor_phases.md`.
- [ ] Persist `ihsg_20d_return`.
- [ ] Persist `ihsg_trend_structure`.
- [ ] Persist `ihsg_breadth_pct_above_ma`.
- [ ] Persist `ihsg_volume_trend`.
- [ ] Persist `ihsg_atr_pct`.
- [ ] Persist `idx_foreign_flow_5d`.
- [ ] Persist `idx_foreign_flow_20d`.
- [ ] Persist `foreign_sell_streak_ihsg_weighted`.
- [ ] Persist `foreign_buy_streak_ihsg_weighted`.
- [ ] Persist `banking_sector_vs_ihsg`.
- [ ] Persist `sector_breadth`.
- [ ] Persist `regime_score`.
- [ ] Persist `regime`.
- [ ] Persist `regime_confidence`.
- [ ] Persist `regime_stability`.
- [ ] Persist `days_in_regime`.
- [ ] Persist `transition_warning`.
- [ ] Persist market forward labels for `forward_ihsg_return_5d`,
      `forward_ihsg_return_10d`, and `forward_ihsg_return_20d`.
- [ ] Persist realized volatility / adverse market movement where available.
- [ ] Keep IDX foreign-flow transition inputs diagnostic / low-authority until
      validated.
- [ ] Emit regime confidence/stability in signal/swing workflow output.
- [ ] Add deterministic replay tests.
- [ ] Add market-level label validation tests.

### Verification Checklist

- [ ] Regime observations are deterministic for the same local data and config.
- [ ] Regime observations can be replayed without network access.
- [ ] Detection input fingerprints are persisted with the observation.
- [ ] Regime confidence/stability are visible in signal output.
- [ ] Regime confidence/stability are visible in swing workflow output.
- [ ] Market-level forward labels validate regime improvements.
- [ ] Ticker-level signal forward labels are not introduced in A2.
- [ ] CLI adapters only render persisted/application output.
- [ ] RiskEngine hard-gate authority remains unchanged.

---

## Current Assumptions

- A2 should extend existing `MarketContext` infrastructure where possible.
- A2 may add schema-versioned local SQLite persistence.
- A2 should not introduce network-dependent tests.
- A2 should not alter A1 `decision_constraints` precedence.
- Existing dirty worktree changes are from A1; do not revert unrelated files.
- `SWING_10D` remains the first calibrated ticker-signal horizon, but A2 is
  market-regime infrastructure and should not implement Phase B ticker labels.

---

## A2 Layer Plan For Implementation

- Domain: add immutable regime evidence/value objects if required by the chosen
  A2 implementation.
- Application: own deterministic regime detection, workflow orchestration,
  evidence fingerprinting, forward-label generation, and validation policy.
- Infrastructure: implement schema-versioned local SQLite persistence for
  `regime_observations` if persistence is added.
- Adapter: render regime confidence/stability only; do not compute policy or
  persistence behavior.
