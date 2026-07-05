# Signal Engine Refactor Tracker

_Design rationale: `docs/signal_refactor.md`_
_Phase plan: `docs/signal_refactor_phases.md`_
_Current implementation target: Phase C_
_Updated: 2026-07-05_

This tracker records the current implementation state and concrete checklist for
the SignalEngine refactor. It is intentionally Phase C-focused: A1, A2, and
Phase B are preserved as Done, Phase C is the active implementation target, and
later phases remain out of scope until their phase is explicitly opened.

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
- Phase C may add `SetupPhaseState` and phase-history persistence.
- Phase C may add continuous setup/trigger evidence, but must not rewrite the
  Phase G Alpha/Trigger aggregate architecture.
- Phase C must keep price confirmation thresholds as placeholders until
  setup/horizon calibration proves them.
- Phase C must not change TradeSetup sizing math.
- Phase C must not promote flow or trigger evidence into production authority
  without saved-label attribution proof.
- Phase C must not require AI or network-dependent tests.
- IDX foreign-flow transition inputs stay diagnostic / low-authority until
  market-level labels prove lead-time value.

---

## Phase Overview

| Phase | Name | Status | Notes |
|---|---|---|---|
| Legacy 0-8 | Staged Evidence Foundation | Done | Historical foundation. |
| A1 | Regime Eligibility Policy Quick Win | Done | Implemented and verified; decision constraints are explicit. |
| A2 | Full RegimeDetectionEvidence And Replay | Done | Implemented 2026-07-05; all checklist items complete, 2347 tests pass. |
| B | Minimal Forward Labels And Observation Fingerprints | Done | Implemented and verified; saved labels and fingerprint attribution are operational. |
| C | SetupPhaseState And Continuous Setup/Trigger Scoring | In Progress | Active implementation target. |
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

**Status:** Done (2026-07-05)

**Completed summary:**

- Added deterministic `RegimeDetectionEvidence`.
- Added replayable `regime_observations`.
- Persisted regime inputs, fingerprints, confidence, stability, days in regime,
  transition warning, and IHSG forward labels.
- Exposed regime confidence/stability in signal and swing workflow output.
- Added deterministic replay and market-label validation tests.

**Carry-forward notes:**

- Realized volatility / adverse market movement remains deferred to Phase I.
- Foreign buy/sell streaks are stored as equal-weight approximations.
- `banking_sector_vs_ihsg` is unavailable when no `banking_universe` is
  configured.
- `sector_breadth` remains unavailable until Phase H.
- IDX foreign-flow transition inputs remain diagnostic / low-authority until
  market-level labels prove value.

---

## Phase B Tracker

**Status:** Done (2026-07-05)

**Completed summary:**

- Added deterministic `signal_forward_labels` for ticker-level outcomes.
- Kept `SWING_10D` as the first calibrated horizon while `TACTICAL_3D` and
  `ACCUM_20D` remain diagnostic.
- Persisted signal-time `sub_signal_fingerprint` records for attribution.
- Added local-first label generation through `saham analyze signal-labels`.
- Added saved-label attribution summary that reads persisted labels and
  fingerprints without recomputing historical evidence.

**Carry-forward notes:**

- Phase B labels are now available for Phase C validation.
- Same-day target/stop collisions are conservatively labeled as `FAILURE`
  until intraday order is available.
- Coverage and conviction are stored separately in observation fingerprints.

---

## Phase C Tracker

**Status:** In Progress

**Goal:** detect temporal setup phase first, then replace coarse setup labels
with continuous price/volume pivot evidence.

Phase C must make setup state explicit and replayable before Alpha/Trigger
aggregation is rewritten in Phase G. It should use Phase B labels to validate
whether setup phases and pivot triggers separate outcomes, but it must not start
Phase I tuning or config patching.

### In Scope

- `SetupPhaseState` values: `NONE`, `ACCUMULATION`, `COMPRESSION`,
  `BREAKOUT_CONFIRMATION`, `EXHAUSTION`, `DISTRIBUTION`, and `FAILED`.
- Phase state, phase history, sequence validity, phase age, and phase strength.
- Setup-family phase requirements for accumulation, foreign-bounce, breakout,
  pullback, and mean reversion.
- Continuous setup/trigger evidence for price and volume pivot behavior.
- `coverage_score` and `conviction_score` emission.
- RS vs IHSG promoted to setup eligibility / max-decision evidence.
- Setup-family configurable RS policy.
- BB compression as `COMPRESSION` readiness, not bullish evidence.
- `volume_dry_up_then_expansion` as primary `SWING_10D` trigger pattern for
  accumulation, foreign-bounce, and breakout.
- Trigger routing for volume expansion, positive close, VWAP reclaim, support
  reclaim, and squeeze release.
- Volume-trigger data quality checks for source, valid 20d sessions, missing
  candles, suspended days, and zero-volume distortion.
- Observation persistence of phase state and phase history.

### Out Of Scope

- Phase D strategy evidence harness.
- Phase E institutional accumulation evidence expansion.
- Phase G Alpha/Trigger aggregation rewrite.
- Phase I walk-forward calibration and config patching.
- TradeSetup stop, target, or position-size math.
- Making price confirmation thresholds production-calibrated.
- Letting `vwap_reclaim.close_above_vwap_pct: 0.30` independently unlock flow
  Trigger contribution.
- Recomputing historical evidence for attribution instead of using saved
  observations and Phase B labels.

### Implementation Checklist

- [ ] Inspect current `SetupEvidence`, `SetupEvidenceBuilder`,
      `EvaluateSwingSetupUseCase`, swing workflow, accumulation screen
      observation payloads, and Phase B label attribution use cases.
- [ ] Define immutable `SetupPhaseState` / phase-history domain value objects.
- [ ] Define deterministic phase transition policy for `NONE`,
      `ACCUMULATION`, `COMPRESSION`, `BREAKOUT_CONFIRMATION`, `EXHAUSTION`,
      `DISTRIBUTION`, and `FAILED`.
- [ ] Persist current phase, previous phase, phase history, phase age sessions,
      phase strength, phase reasons, and `phase_sequence_valid`.
- [ ] Enforce accumulation / foreign-bounce sequence:
      `ACCUMULATION -> COMPRESSION -> BREAKOUT_CONFIRMATION`.
- [ ] Enforce breakout sequence:
      `COMPRESSION -> BREAKOUT_CONFIRMATION`.
- [ ] Enforce pullback requirements: trend/context support plus support reclaim
      or pivot confirmation.
- [ ] Enforce mean-reversion requirements: support/reversal evidence and
      explicit risk controls.
- [ ] Evaluate distribution, failed, and exhaustion phases before generic
      non-breakout WATCH handling.
- [ ] Emit `coverage_score` and `conviction_score` separately in setup/phase
      output.
- [ ] Promote RS vs IHSG to setup eligibility / max-decision evidence for
      swing, breakout, accumulation, and foreign-bounce.
- [ ] Add setup-family configurable RS policy: lag warning, hard exclude,
      warning action, and mean-reversion exception requirements.
- [ ] Treat negative RS as unable to be silently overwhelmed by other bullish
      setup components.
- [ ] Add BB compression as `COMPRESSION` readiness, not bullish evidence.
- [ ] Add `volume_dry_up_then_expansion` trigger for accumulation,
      foreign-bounce, and breakout.
- [ ] Route volume expansion, positive close, VWAP reclaim, support reclaim,
      and squeeze release to `BREAKOUT_CONFIRMATION` / Trigger.
- [ ] Keep price confirmation thresholds documented as placeholders until
      setup/horizon calibration.
- [ ] Ensure `vwap_reclaim.close_above_vwap_pct: 0.30` cannot independently
      unlock flow Trigger contribution in production.
- [ ] Enforce valid volume source and enough valid 20d sessions for volume
      trigger availability.
- [ ] Treat suspended days, missing candles, and zero-volume distortion as
      unavailable trigger evidence that lowers coverage.
- [ ] Persist phase state/history into signal/candidate observations at
      observation time.
- [ ] Add deterministic tests for phase transitions and sequence validity.
- [ ] Add tests proving one failed gate does not mean all gates failed.
- [ ] Add tests proving distribution, failed, and exhaustion are evaluated
      before generic WATCH.
- [ ] Add tests proving negative RS cannot be overwhelmed by bullish components.
- [ ] Add tests for volume-trigger source/session coverage and unavailable
      handling.
- [ ] Add tests proving CLI adapters only render phase/evidence output.

### Verification Checklist

- [ ] Phase state is deterministic for fixed local candles, config, and saved
      evidence.
- [ ] Phase history is persisted at observation time and replayable.
- [ ] Phase sequence validity is available for Phase B label attribution.
- [ ] Setup output exposes distinct coverage and conviction.
- [ ] BB compression is readiness evidence, not bullish evidence.
- [ ] Trigger evidence requires valid price/volume confirmation.
- [ ] Flow evidence cannot directly create ENTER through Phase C trigger logic.
- [ ] No Alpha/Trigger aggregate rewrite is introduced in Phase C.
- [ ] No TradeSetup sizing math changes are introduced.
- [ ] Tests run offline and do not require network access.

---

## Known Technical Debt (Explicitly Tracked)

### TD-1: Double Regime Effect — regime_conditioning + decision_policy both active

**Status:** Transitional — tracked, not a blocker for Phase C planning.

**Description:** `AssessSignalEvidenceUseCase._condition_group_scores()` (Phase 5 legacy) mutates
group scores before renormalization when regime is RISK_OFF/VOLATILE/NEUTRAL. A1/A2 then adds
explicit `decision_policy` constraints on top. This creates a compound effect: score is discounted
AND ENTER is blocked.

**Contract violation:** The A1/A2 contract states "regime controls constraints, not score."
`assessment.score` still reflects regime conditioning. `signal_score_raw` (added in A2) preserves
the regime-neutral score for comparability.

**Documented workaround:**
- `config/signal_engine.yaml` `regime_conditioning.*` block marked TRANSITIONAL — DO NOT TUNE.
- `_condition_group_scores()` docstring marks it as transitional Phase 5 legacy.
- `AssessSignalResponse.signal_score_raw` holds the regime-neutral score.

**Resolution path:** When walk-forward validation (Phase I) confirms `decision_policy` alone
provides equivalent or better regime gating, remove `_condition_group_scores()` from the canonical
path and promote `signal_score_raw` → `assessment.score`. Requires updating test expectations.

---

## Current Assumptions

- Phase C should extend existing setup evidence, swing workflow, and candidate
  observation infrastructure where possible.
- Phase C may add schema-versioned local SQLite persistence for setup phase
  observations or extend existing observation payloads.
- Phase C should use Phase B labels for validation and attribution, but should
  not start Phase I tuning/config patching.
- Phase C should not introduce network-dependent tests.
- Phase C should not alter A1 `decision_constraints` precedence.
- Phase C should not alter A2 regime observation contracts.
- Phase C should not alter Phase B `signal_forward_labels` contracts except to
  enrich saved fingerprints with phase fields.
- Existing dirty worktree changes are from A1; do not revert unrelated files.
- `SWING_10D` remains the first calibrated ticker-signal horizon.

---

## Phase C Layer Plan For Implementation

- Domain: add immutable setup phase state, phase history, and setup/trigger
  evidence value objects.
- Application: own deterministic phase detection, setup-family sequence policy,
  RS policy, volume-trigger availability, coverage/conviction calculation, and
  observation persistence orchestration.
- Infrastructure: implement schema-versioned local SQLite persistence for
  setup phase observations if separate persistence is added.
- Adapter: render setup phase/evidence output only; do not compute workflow,
  scoring, persistence policy, or phase transitions.
