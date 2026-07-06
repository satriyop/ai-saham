# Signal Engine Refactor Tracker

_Design rationale: `docs/signal_refactor.md`_
_Phase plan: `docs/signal_refactor_phases.md`_
_Current implementation target: Phase D planning_
_Updated: 2026-07-06_

This tracker records the current implementation state and concrete checklist for
the SignalEngine refactor. A1, A2, Phase B, and Phase C are preserved as Done.
Phase D is now planned as the next implementation target.

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
- Closed Phase C added `SetupPhaseState`, phase-history persistence, and
  continuous setup/trigger evidence without rewriting the Phase G Alpha/Trigger
  aggregate architecture.
- Closed Phase C keeps price confirmation thresholds as placeholders until
  setup/horizon calibration proves them.
- Closed Phase C did not change TradeSetup sizing math.
- Closed Phase C did not promote flow or trigger evidence into production
  authority without saved-label attribution proof.
- Closed Phase C does not require AI or network-dependent tests.
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
| C | SetupPhaseState And Continuous Setup/Trigger Scoring | Done | Closed 2026-07-06; diagnostic setup phase, replay history, and data-quality volume trigger implemented. |
| D | Strategy Evidence Harness | Planned | Diagnostic-only strategy evidence tracker created 2026-07-06. |
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

**Status:** Done (2026-07-06)

**Goal:** detect temporal setup phase first, then replace coarse setup labels
with continuous price/volume pivot evidence.

Phase C made setup state explicit and replayable before Alpha/Trigger
aggregation is rewritten in Phase G. Phase B labels remain the attribution
source for validating whether setup phases and pivot triggers separate outcomes.
Phase C did not start Phase I tuning or config patching.

### In Scope

- `SetupPhaseState` values: `NONE`, `ACCUMULATION`, `COMPRESSION`,
  `BREAKOUT_CONFIRMATION`, `EXHAUSTION`, `DISTRIBUTION`, and `FAILED`.
- Phase state, phase history, sequence validity, phase age, and phase strength.
- Setup-family phase requirements for accumulation, foreign-bounce, and
  breakout, with pullback and mean-reversion specifics deferred.
- Continuous setup/trigger evidence for price and volume pivot behavior.
- `coverage_score` and `conviction_score` emission.
- RS vs IHSG promoted to setup eligibility / max-decision evidence.
- Setup-family configurable RS policy.
- BB compression as `COMPRESSION` readiness, not bullish evidence.
- `volume_dry_up_then_expansion` as primary `SWING_10D` trigger pattern for
  accumulation, foreign-bounce, and breakout.
- Trigger routing for volume expansion, positive close, and VWAP reclaim, with
  support reclaim and squeeze release deferred.
- Volume-trigger data quality checks for ticker type, valid 20d sessions,
  missing candles, suspended days, synthetic/missing volume, and zero-volume
  distortion.
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

- [x] Inspect current `SetupEvidence`, `SetupEvidenceBuilder`,
      `EvaluateSwingSetupUseCase`, swing workflow, accumulation screen
      observation payloads, and Phase B label attribution use cases.
- [x] Define immutable `SetupPhaseState` / phase-history domain value objects.
- [x] Define deterministic phase transition policy for `NONE`,
      `ACCUMULATION`, `COMPRESSION`, `BREAKOUT_CONFIRMATION`, `EXHAUSTION`,
      `DISTRIBUTION`, and `FAILED`.
- [x] Persist current phase, previous phase, phase history, phase age sessions,
      phase strength, phase reasons, and `phase_sequence_valid`.
- [x] Enforce accumulation / foreign-bounce sequence:
      `ACCUMULATION -> COMPRESSION -> BREAKOUT_CONFIRMATION`.
- [x] Enforce breakout sequence:
      `COMPRESSION -> BREAKOUT_CONFIRMATION`.
- [x] Evaluate distribution, failed, and exhaustion phases before generic
      non-breakout WATCH handling.
- [x] Emit `coverage_score` and `conviction_score` separately in setup/phase
      output.
- [x] Promote RS vs IHSG to setup eligibility / max-decision evidence for
      swing, breakout, accumulation, and foreign-bounce.
- [x] Add setup-family configurable RS policy: lag warning, hard exclude,
      warning action, and mean-reversion exception requirements.
- [x] Treat negative RS as unable to be silently overwhelmed by other bullish
      setup components.
- [x] Add BB compression as `COMPRESSION` readiness, not bullish evidence.
- [x] Add `volume_dry_up_then_expansion` trigger for accumulation,
      foreign-bounce, and breakout.
- [x] Route volume expansion, positive close, and VWAP reclaim to
      `BREAKOUT_CONFIRMATION` / Trigger.
- [x] Keep price confirmation thresholds documented as placeholders until
      setup/horizon calibration.
- [x] Ensure `vwap_reclaim.close_above_vwap_pct: 0.30` cannot independently
      unlock flow Trigger contribution in production.
- [x] Enforce volume data quality and enough valid 20d sessions for volume
      trigger availability.
- [x] Treat suspended days, missing candles, and zero-volume distortion as
      unavailable trigger evidence that lowers coverage.
- [x] Persist phase state/history into signal/candidate observations at
      observation time.
- [x] Add deterministic tests for phase transitions and sequence validity.
- [x] Add tests proving one failed gate does not mean all gates failed.
- [x] Add tests proving distribution, failed, and exhaustion are evaluated
      before generic WATCH.
- [x] Add tests proving negative RS cannot be overwhelmed by bullish components.
- [x] Add tests for volume-trigger source/session coverage and unavailable
      handling.
- [x] Keep CLI adapters render-only for phase/evidence output.

### Deferred Follow-Up Items

These are not Phase C closure blockers and remain available for later phase
work or calibration:

- [ ] Enforce pullback requirements: trend/context support plus support reclaim
      or pivot confirmation.
- [ ] Enforce mean-reversion requirements: support/reversal evidence and
      explicit risk controls.
- [ ] Add dedicated support reclaim and squeeze release trigger routing beyond
      the current positive close / VWAP reclaim / volume expansion path.
- [ ] Add explicit CLI adapter rendering regression tests for phase/evidence
      output.

### Verification Checklist

- [x] Phase state is deterministic for fixed local candles, config, and saved
      evidence.
- [x] Phase history is persisted at observation time and replayable.
- [x] Phase sequence validity is available for Phase B label attribution.
- [x] Setup output exposes distinct coverage and conviction.
- [x] BB compression is readiness evidence, not bullish evidence.
- [x] Trigger evidence requires valid price/volume confirmation.
- [x] Flow evidence cannot directly create ENTER through Phase C trigger logic.
- [x] No Alpha/Trigger aggregate rewrite is introduced in Phase C.
- [x] No TradeSetup sizing math changes are introduced.
- [x] Tests run offline and do not require network access.

---

## Phase D Tracker: Strategy Evidence Harness

**Status:** In progress - core diagnostic harness implemented

**Goal:** reuse deterministic strategy packages as setup-family evidence and
empirical validation tools without creating a parallel decision engine.

Phase D evidence is diagnostic-only. It is persisted and reported, but it must
not affect SignalEngine group scores, canonical `SetupPhaseState`, TradeSetup
sizing, or final ENTER/WATCH/AVOID decisions until Phase G explicitly consumes
it through the Alpha/Trigger aggregation plan.

### Non-Goals

- [x] Do not allow a strategy match to override `SetupPhaseState`.
- [x] Do not allow a strategy result to override SignalEngine decisions.
- [x] Do not add Phase G Alpha/Trigger aggregation.
- [x] Do not add Phase I calibration/tuning or production weights.
- [x] Do not introduce AI, network calls, or provider fetches.
- [x] Do not move strategy evaluation or policy into CLI adapters.
- [x] Do not change TradeSetup stop, target, or position sizing.

### Layer Plan

- Domain: add immutable strategy evidence value object(s) only if existing
  value objects cannot represent matched strategy evidence cleanly.
- Application: add `StrategyEvidenceBuilder`, strategy-to-setup mapping policy,
  deterministic strategy evaluation orchestration, replay fingerprint fields,
  and empirical readiness checks.
- Infrastructure: reuse existing local strategy YAML loading and persistence;
  extend local observation payloads only, unless separate SQLite persistence is
  required for replay queries.
- Adapter: render strategy evidence returned by application results only; no
  strategy evaluation, scoring, or persistence policy in CLI.

### Input Contract

- [x] Strategy YAML must already pass existing strategy validation.
- [x] Strategy evaluation must run through existing deterministic rule /
      indicator infrastructure and `IndicatorRegistry`.
- [x] Evaluation must use local candles and local config only.
- [x] Indicator warm-up handling must remain in application use cases.
- [x] Strategy evidence must be reproducible for fixed candles, config,
      strategy YAML, and as-of date.

### Evidence Model Checklist

- [x] Add `StrategyEvidence` or equivalent immutable diagnostic value object.
- [x] Capture matched strategy package name.
- [x] Capture matched rule identifier / rule label.
- [x] Capture route metadata: setup family, setup phase, and evidence route
      such as setup, trigger, filter, or exit-context.
- [x] Capture match outcome: matched, not matched, unavailable, or invalid.
- [x] Capture coverage metadata: required inputs present / total inputs.
- [x] Capture conviction metadata: deterministic match strength or rule
      confidence without implying production authority.
- [x] Capture freshness metadata for candles and derived indicator inputs.
- [x] Capture rationale explaining which deterministic rule(s) matched.
- [x] Capture unavailable reasons for missing candles, warm-up, invalid config,
      missing indicators, or insufficient data.
- [x] Ensure strategy evidence serializes to stable dict/JSON.

### Strategy Mapping Policy

- [ ] Define config-driven mapping from strategy packages/rules to setup
      family and setup phase evidence.
- [x] Treat mapped strategy output as evidence about a setup route, not as the
      setup route itself.
- [ ] Allow multiple strategy matches to coexist without overwriting each other.
- [x] Preserve canonical setup phase sequence policy from Phase C.
- [x] Keep BB/compression, volume trigger, RS, and flow authority in their
      existing Phase C evidence paths.
- [x] Add explicit behavior for unmapped strategies: diagnostic only,
      `setup_family=None`, no decision constraints.
- [ ] Add conflict behavior: contradictory strategy matches are reported as
      mixed evidence, not collapsed into a single bullish/bearish decision.

### Application Wiring

- [x] Add `StrategyEvidenceBuilder` in `src/application/services`.
- [x] Reuse existing strategy loader/validator instead of parsing YAML ad hoc.
- [x] Evaluate strategy rules through `IndicatorRegistry`.
- [x] Add strategy evidence to swing workflow evidence output when strategy
      evidence is requested or a strategy package is already part of the request.
- [x] Add strategy evidence to replay/candidate observation fingerprints.
- [x] Ensure evidence-enriched signal re-score ignores strategy evidence in
      Phase D.
- [x] Ensure DecisionPolicy ignores strategy evidence in Phase D except for
      reporting already-computed diagnostic constraints if present.
- [x] Keep CLI adapters thin: no direct strategy evidence computation.

### Persistence And Replay Checklist

- [x] Persist matched strategy name in candidate/signal observation payloads.
- [x] Persist matched rule identifier.
- [x] Persist strategy match outcome.
- [x] Persist route metadata and mapped setup family/phase.
- [x] Persist coverage, conviction, freshness, rationale, and unavailable
      reasons.
- [x] Extend `SignalObservationFingerprint.from_dict()` to parse strategy
      evidence fields when present.
- [x] Extend Phase B label attribution summaries with strategy evidence buckets:
      strategy name, matched rule, route, and outcome.
- [x] Ensure old observations without strategy evidence still parse.
- [x] Do not recompute strategy evidence when generating forward labels; labels
      must use saved observation-time evidence.

### Empirical Readiness Checklist

- [ ] Add a deterministic readiness summary from existing strategy backtests.
- [ ] Readiness must be diagnostic-only in Phase D.
- [ ] Require minimum sample count before reporting a strategy route as
      empirically ready.
- [ ] Report insufficient sample size explicitly.
- [ ] Do not assign production weights or unlock scoring based on readiness
      until Phase G/I.
- [ ] Preserve setup-family and horizon grouping, starting with `SWING_10D`.

### Tests

- [x] Domain/value-object serialization tests for strategy evidence.
- [x] Application tests for strategy evidence builder with local fake candles
      and fake strategy/rule results.
- [x] Tests for matched, not matched, unavailable, and invalid strategy states.
- [x] Tests that strategy matches cannot override `SetupPhaseState`.
- [x] Tests that strategy matches cannot override SignalEngine decisions.
- [x] Tests that strategy evidence is ignored by evidence-enriched re-score in
      Phase D.
- [x] Persistence tests proving observation payloads include strategy evidence.
- [x] Forward-label tests proving strategy attribution uses saved fingerprints
      and does not recompute strategies.
- [ ] CLI tests proving adapters render strategy evidence only.
- [x] Offline-only tests; no network or AI dependencies.

### Documentation Checklist

- [x] Document Phase D evidence as diagnostic-only.
- [x] Document initial mapping policy from strategy package/rule to setup family/phase.
- [x] Document persistence fields and replay attribution buckets.
- [ ] Document empirical readiness limits and sample-size requirements.
- [ ] Document that Phase G is the first phase allowed to consume strategy
      evidence in Alpha/Trigger aggregation.

### Phase D Verification Checklist

- [x] Strategy evidence is deterministic for fixed local inputs.
- [x] Strategy evidence is persisted at observation time.
- [x] Strategy evidence is replayable through Phase B labels.
- [x] Strategy evidence remains diagnostic-only in SignalEngine and
      DecisionPolicy.
- [x] Canonical `SetupPhaseState` is never overwritten by strategy output.
- [x] TradeSetup sizing math is unchanged.
- [x] Adapters remain thin.
- [x] Tests pass offline.

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

- Phase D is the next implementation target.
- Phase D must preserve the diagnostic-only strategy evidence contract until
  Phase G explicitly consumes strategy evidence in Alpha/Trigger aggregation.
- Phase B labels remain the source for replay attribution.
- Phase I tuning/config patching remains out of scope until Phase I is opened.
- Network-dependent tests remain out of scope for refactor phases.
- Existing dirty worktree changes are intentional; do not revert unrelated
  files.
- `SWING_10D` remains the first calibrated ticker-signal horizon.

---

## Closed Phase C Layer Summary

- Domain: added immutable setup phase state and phase history value objects.
- Application: owns deterministic phase detection, setup-family sequence policy,
  RS policy, volume-trigger availability, coverage/conviction calculation, and
  observation persistence orchestration.
- Infrastructure: extended local persistence/replay paths through existing
  observation payloads and local repositories.
- Adapter: remains render-only for setup phase/evidence output; no workflow,
  scoring, persistence policy, or phase transitions are computed in adapters.
