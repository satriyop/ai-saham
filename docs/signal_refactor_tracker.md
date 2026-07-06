# Signal Engine Refactor Tracker

_Design rationale: `docs/signal_refactor.md`_
_Phase plan: `docs/signal_refactor_phases.md`_
_Current implementation target: Phase G implementation_
_Updated: 2026-07-06_

This tracker records the current implementation state and concrete checklist for
the SignalEngine refactor. A1, A2, B, C, D, E, and F are closed. Phase G is in
implementation.

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
- Closed Phase D added `StrategyEvidenceBuilder`, diagnostic-only strategy rule
  evidence, and replay fingerprint fields without affecting SignalEngine group
  scoring or DecisionPolicy.
- Closed Phase E added `InstitutionalAccumulationEvidence` (two-track foreign +
  domestic flow evidence, counterparty HHI), 23 `ia_*` fingerprint fields, and
  the `InstitutionalAccumulationEvidenceBuilder` as DIAGNOSTIC-only without
  affecting `FlowConfirmationEvidence` group scoring, `DecisionPolicy`, or
  `AssessSignalEvidenceUseCase`.
- Closed Phase F added `TickerProfileSnapshot` (liquidity, broker concentration,
  foreign flow, ATR-style volatility, index membership dimensions, soft primary
  profile exposures, and separate market tier), replay fingerprint fields,
  `TickerProfileClassifier` (builds index reverse index from `universes.yaml`
  at construction; never fetches data), and wired into both use cases as
  DIAGNOSTIC-only without affecting SignalEngine group scoring,
  `DecisionPolicy`, or `AssessSignalEvidenceUseCase`.

---

## Phase Overview

| Phase | Name | Status | Notes |
|---|---|---|---|
| Legacy 0-8 | Staged Evidence Foundation | Done | Historical foundation. |
| A1 | Regime Eligibility Policy Quick Win | Done | Implemented and verified; decision constraints are explicit. |
| A2 | Full RegimeDetectionEvidence And Replay | Done | Implemented 2026-07-05; all checklist items complete, 2347 tests pass. |
| B | Minimal Forward Labels And Observation Fingerprints | Done | Implemented and verified; saved labels and fingerprint attribution are operational. |
| C | SetupPhaseState And Continuous Setup/Trigger Scoring | Done | Closed 2026-07-06; diagnostic setup phase, replay history, and data-quality volume trigger implemented. |
| D | Strategy Evidence Harness | Done (2026-07-06) | Diagnostic-only strategy evidence harness. 2424 tests pass. |
| E | Institutional Accumulation Evidence | Done (2026-07-06) | Two-track institutional flow evidence, diagnostic-only. 2457 tests pass. |
| F | Minimal Ticker Profile Diagnostics | Done (2026-07-06) | Deterministic ticker behavior classifier, diagnostic-only. 2489 tests pass. |
| G | Simplified Alpha/Trigger Split | Done (2026-07-06) | Four canonical Alpha/Trigger slots configured; market/company slots start DIAGNOSTIC/unavailable until producers feed them. |
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

### Completed

- Immutable `SetupPhaseState` with NONE / ACCUMULATION / COMPRESSION / BREAKOUT_CONFIRMATION / EXHAUSTION / DISTRIBUTION / FAILED transitions; sequence enforced per setup family.
- Phase history, phase age, phase strength, phase reasons, and `phase_sequence_valid` persisted at observation time.
- RS vs IHSG promoted to setup eligibility / max-decision evidence with per-family configurable RS policy; negative RS cannot be overwhelmed by bullish components.
- BB compression as `COMPRESSION` readiness only; `volume_dry_up_then_expansion` as primary SWING_10D trigger for accumulation / foreign-bounce / breakout.
- Volume data quality checks: valid 20d sessions, suspended days, missing candles, zero-volume distortion lower coverage.
- `coverage_score` and `conviction_score` emitted separately; phase state persisted into signal and candidate observation fingerprints.
- All checklist items verified; no Alpha/Trigger rewrite, no TradeSetup sizing changes.

## Closed Phase C Layer Summary

- Domain: added immutable setup phase state and phase history value objects.
- Application: owns deterministic phase detection, setup-family sequence policy,
  RS policy, volume-trigger availability, coverage/conviction calculation, and
  observation persistence orchestration.
- Infrastructure: extended local persistence/replay paths through existing
  observation payloads and local repositories.
- Adapter: remains render-only for setup phase/evidence output; no workflow,
  scoring, persistence policy, or phase transitions are computed in adapters.

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

---

## Phase D Tracker: Strategy Evidence Harness

**Status:** Done (2026-07-06)

**Completed:**

- Added frozen `StrategyEvidence` / `StrategyRuleEvidence` domain value objects with coverage, conviction, freshness, rationale, outcome (MATCHED/NOT_MATCHED/UNAVAILABLE/INVALID), and stable `to_dict`/`from_dict`.
- Added `StrategyEvidenceBuilder` in `src/application/services`; evaluates strategy YAMLs through existing `IndicatorRegistry`; never raises — degrades to UNAVAILABLE/INVALID.
- Strategy evidence wired into swing workflow and accumulation screen observation fingerprints; stored under `strategy_*` fields in `SignalObservationFingerprint`.
- Evidence-enriched re-score and `DecisionPolicy` ignore strategy evidence in Phase D (zero impact on group scores or ENTER/WATCH/AVOID decisions, verified by grep).
- Phase B label attribution extended with strategy evidence buckets; old observations without strategy fields still parse cleanly.
- 2424 tests pass offline.

**Carry-forward (open, not Phase D closure blockers):**

- [ ] Config-driven mapping from strategy package/rule to setup family + phase evidence (multi-match coexistence and conflict reporting).
- [ ] Empirical readiness summary from existing backtests (min sample size, SWING_10D grouping).
- [ ] CLI adapter rendering regression tests for strategy evidence display.
- [ ] Document Phase G as first phase allowed to consume strategy evidence in Alpha/Trigger aggregation.

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

- Phase G (Simplified Alpha/Trigger Split) is the active implementation target.
- Phase F profile snapshots remain DIAGNOSTIC-only; profiles do not feed into
  SignalEngine group scoring or DecisionPolicy in the current Phase G
  implementation.
- Phase E institutional accumulation evidence is DIAGNOSTIC-only; `FlowConfirmationEvidence`
  group scoring is unchanged in the current Phase G implementation.
- Phase D strategy evidence contract is preserved; strategy evidence remains
  diagnostic and cannot override canonical setup phase or SignalEngine decisions.
- Phase B labels remain the source for replay attribution; no recomputation of
  historical evidence.
- Phase I tuning/config patching remains out of scope until Phase I is opened.
- Network-dependent tests remain out of scope for refactor phases.
- `SWING_10D` remains the first calibrated ticker-signal horizon.

---

## Phase E Tracker: Institutional Accumulation Evidence

**Status:** Done (2026-07-06)

**Goal:** Make IDX institutional flow empirical with two parallel tracks
(`foreign_institutional_track` + `domestic_bandar_track`), add counterparty
transfer metrics, enforce asymmetric observation windows, and persist all raw
metrics in replay observations. Everything built in Phase E is DIAGNOSTIC /
LOW_WEIGHT status until Phase I OOS attribution proves bucket-level predictive
value.

Phase E does NOT change `AssessSignalEvidenceUseCase` group scoring,
`DecisionPolicy`, or `TradeSetup`. The existing `FlowConfirmationEvidence`
continues to drive the `flow_confirmation` group score unchanged.

### Completed

- Added `EvidenceStatus` enum (DIAGNOSTIC / LOW_WEIGHT / PRODUCTION) and four frozen dataclasses: `ForeignInstitutionalTrack`, `DomesticBandarTrack`, `CounterpartyTransferEvidence`, `InstitutionalAccumulationEvidence` — all with `__post_init__` bounds, `to_dict`/`from_dict`, backward-compat `data.get()`.
- Added `config/institutional_accumulation.yaml` with asymmetric windows, `min_valid_sessions`, and component weights; config validates all three weight groups sum to 1.00.
- Added `InstitutionalAccumulationEvidenceBuilder` with `from_yaml()` factory; implements all foreign (participation, CR4/CR8, CNFB 20d/30d bullish + 3d/5d/7d bearish, foreign VWAP) and domestic (broker consistency, reversal, accumulation session ratio, domestic VWAP, HHI divergence, bandar normalisation) metrics and counterparty HHI; never raises — degrades to UNAVAILABLE with reason. `BrokerDailyFlow` foreign classification via `DEFAULT_FOREIGN_BROKER_CODES` frozenset (overridable in tests).
- Added 23 `ia_*` fields to `SignalObservationFingerprint` (all `None`-defaulted; `data.get()` in `from_dict()`).
- Added `_ia_evidence_fingerprint()` helper and spread into `_sub_signal_fingerprint()` in `accumulation_screen_use_case.py`; added `_build_candidate_institutional_accumulation_evidence()` method.
- Added `institutional_accumulation_evidence` field and build block to `swing_analysis_workflow_use_case.py`; wired into `SwingEvidence` constructor and `to_dict()`.
- Verified zero references to `InstitutionalAccumulationEvidence` in `AssessSignalEvidenceUseCase`, `DecisionPolicy`, and all domain entity files.
- 2452 tests pass offline (28 new Phase E tests; 2424 existing all green).

### Post-Closure Fixes Applied (2026-07-06)

After external review, three issues were identified and resolved:

1. **CNFB metadata key mismatch (High):** `_ia_evidence_fingerprint()` was reading wrong flat keys (`cnfb_divergence_30d_score`, `cnfb_distribution_3d_score`). Fixed to read from `metadata["cnfb_bullish_scores"]["cnfb_20d/30d"]` and `metadata["cnfb_bearish_scores"]["cnfb_3d"]`. `ia_cnfb_divergence_20d` is now the raw 20d score, not the averaged track score. Tests added.

2. **Conviction renormalization (Medium):** Foreign and domestic track conviction was a non-renormalized weighted sum — missing components dragged conviction down, conflating it with coverage. Fixed: conviction now renormalizes over available-component weights so it reflects signal strength only. Coverage captures availability. Tests added.

3. **EvidenceStatus registry (Medium):** Explicitly deferred to Phase G/I. No runtime code path promotes `InstitutionalAccumulationEvidence` into scoring in Phase E. Documented in Deferred section.

2457 tests pass after fixes.

### Carry-Forward (open, not Phase E closure blockers)

- [ ] Extend `summarize_signal_forward_labels_use_case.py` to group by `ia_foreign_track_coverage` / `ia_domestic_track_coverage` buckets in attribution (currently reads `ia_*` fields but no dedicated bucket grouping).
- [ ] Persistence integration test: verify `ia_*` fields land in saved observation payload via `AccumulationScreenUseCase` with a broker-repo stub.
- [ ] CLI adapter regression tests for Phase E evidence rendering.

### Deferred to Later Phases

- Empirical readiness summary and OOS attribution (Phase I).
- Promoting any component from DIAGNOSTIC to LOW_WEIGHT or PRODUCTION (Phase I).
- Domestic bandar cost basis / VWAP reclaim as Trigger evidence (Phase G).
- Ticker profile driving evidence interpretation weights (Phase F → now active).
- BandarDetectorSnapshot historical caching (infrastructure improvement).
- **EvidenceStatus registry / cap enforcement** (`signal_refactor.md` §2329): Phase E has the enum and config-validated `evidence_status = DIAGNOSTIC` but no registry object that prevents runtime promotion above DIAGNOSTIC. Safe for Phase E because no Phase E path feeds `InstitutionalAccumulationEvidence` into scoring. Implement the registry as a Phase G/I gate when evidence promotion paths actually exist.

---

## Phase F Tracker: Minimal Ticker Profile Diagnostics

**Status:** Done (2026-07-06)

**Goal:** Classify ticker behavior deterministically without introducing tunable explosion.
Produce `TickerProfileSnapshot` for each ticker at signal time — dimension scores, soft
primary-profile exposures, separate market tier, and profile confidence. DIAGNOSTIC-only.
Does not feed into SignalEngine scoring or DecisionPolicy.

**Completed summary:** Phase F is closed as a diagnostic-only layer. Sparse/new
tickers are conservative (`primary_profile=unclassified`, FI=0.0 / DB=0.5 /
RS=0.5), configured exposure weights are validated, snapshots are persisted in
replay fingerprints, and no Phase F output changes scoring, decision policy, or
TradeSetup sizing.

**Completed:**

- Added deterministic `TickerProfileSnapshot` with dimension scores, market
  tier, soft profile exposures, profile confidence, evidence status, and
  backward-compatible serialization.
- Added `config/ticker_profile.yaml` and validation for index scores plus
  exposure weights.
- Added `TickerProfileClassifier` using local candles, broker flows/summaries,
  market cap, sector metadata, and a construction-time universe reverse index.
- Added conservative sparse-history fallback:
  `primary_profile=unclassified`, `market_tier=unknown`, confidence `0.30`,
  FI `0.0`, DB `0.5`, RS `0.5`.
- Persisted `tp_*` replay fingerprint fields and exposed
  `ticker_profile_snapshot` in swing evidence output.
- Wired profile snapshots into swing and accumulation workflows as
  DIAGNOSTIC-only evidence.
- Verified Phase F does not change `AssessSignalEvidenceUseCase`,
  `DecisionPolicy`, `SignalEngine` group scoring, `TradeSetup`, or sizing.
- Phase F tests passed offline with the then-existing unrelated fetch-market
  CLI failures noted.

**Carry-forward notes:**

- Phase F profile snapshots remain diagnostic until a later phase explicitly
  promotes or routes them.
- Sparse/new ticker fallback is intentionally conservative and should remain so
  until walk-forward evidence proves otherwise.
- Phase F did not introduce a `ticker_profiles` SQLite table; snapshots are
  replayed through saved observation fingerprints.

### Deferred to Later Phases

- Per-profile group weights.
- Profile-driven max-decision overrides.
- Evidence interpretation wiring.
- Epoch-keyed `ticker_profiles` SQLite table for backtest snapshot lookup (Phase I).
- Per-horizon profile tunables (Phase I).

---

## Phase G Tracker: Simplified Alpha/Trigger Split

**Status:** Done (2026-07-06)

**Goal:** Add a diagnostic-first Alpha/Trigger projection layer to the canonical
signal evidence path. Alpha and Trigger are derived from existing evidence
groups; they do not introduce a second factor tree. Existing integer
`SignalAssessment.score` remains stable while exact float diagnostics are
emitted for attribution and audit.

Current implementation note: Phase G now has four canonical configured
Alpha/Trigger group slots. Runtime producers currently populate
`setup_quality` and `institutional_flow`; `market_context` and
`company_quality_context` are real configured slots that start unavailable and
DIAGNOSTIC, so they lower evidence coverage but cannot affect score until later
phases provide producer evidence and promote authority.

### Non-Goals

- [x] No second factor tree.
- [x] No `TradeSetup` stop, target, or position-size authority change.
- [x] No RiskEngine hard-gate change.
- [x] No Phase I walk-forward tuning or promotion.
- [x] No CLI policy logic.
- [x] No strategy evidence override of canonical `SetupPhaseState`.

### Domain

- [x] Added `AlphaTriggerScore` with `alpha_score`, `trigger_score`,
      `final_exact_score`, `horizon`, `alpha_weight`, route contributions,
      coverage, authority coverage, conviction, flow-trigger gate state,
      reasons, and unavailable reasons.
- [x] Added `AlphaTriggerGroupContribution` serialization for per-group route
      metadata.
- [x] Added `EvidenceRegistration` and `EvidenceAuthorityStatus`
      (`DIAGNOSTIC`, `LOW_WEIGHT`, `PRODUCTION`) with deterministic status caps.
- [x] Kept `SignalAssessment.score` as `int`.
- [x] Added optional exact fields to `SignalAssessment`: `raw_exact_score` and
      `alpha_trigger_score`.
- [x] Added domain tests for value-object serialization, bounds, and evidence
      status caps.

### Config

- [x] Added `signal_engine.alpha_trigger.route_fractions` for `TACTICAL_3D`,
      `SWING_10D`, and `ACCUM_20D`.
- [x] Stored only `alpha_fraction`; Trigger fraction is derived as
      `1.0 - alpha_fraction`.
- [x] Added `signal_engine.alpha_trigger.horizon_alpha_weights`.
- [x] Added `signal_engine.alpha_trigger.group_weights` for all four canonical
      groups.
- [x] Added default evidence registrations for `setup_quality`,
      `institutional_flow`, `market_context`, and `company_quality_context`.
- [x] Preserved current runtime compatibility by mapping
      `setup_quality -> setup_quality` and
      `flow_confirmation -> institutional_flow`, while representing
      `market_context` and `company_quality_context` as real missing configured
      groups until producers feed them.
- [x] Registered new numeric tunable paths in `SwingTuningPatchValidator`
      bounds: route fractions, horizon alpha weights, and low-weight cap.
- [x] Added config loader tests for Alpha/Trigger config and invalid route
      fractions.

### Application

- [x] Added `AlphaTriggerAggregator` application service.
- [x] Aggregator consumes existing group scores after canonical group scoring.
- [x] Computes normalized Alpha and Trigger without neutral-filling missing
      groups into side denominators.
- [x] Computes Alpha/Trigger `coverage` as evidence availability over required
      configured runtime group weights, so missing setup/flow evidence lowers
      coverage instead of being hidden by present-only denominators.
- [x] Emits `authority_coverage` separately for status-cap-adjusted available
      weight, avoiding overload of the evidence coverage contract.
- [x] Represents not-yet-populated canonical groups (`market_context`,
      `company_quality_context`) as unavailable configured contributions, so
      they lower evidence coverage while DIAGNOSTIC status prevents scoring
      authority.
- [x] Applies `DIAGNOSTIC`, `LOW_WEIGHT`, and `PRODUCTION` authority caps.
- [x] Enforces flow Trigger contribution only when same-observation
      `SetupPhaseState.BREAKOUT_CONFIRMATION` and confirmed
      `FlowConfirmationEvidence` are present.
- [x] Keeps setup internals owned by setup/setup-phase evidence.
- [x] Keeps strategy evidence diagnostic; it is not passed into the aggregator
      and cannot override setup phase.
- [x] Added focused use-case tests for projection formulas, missing groups,
      coverage semantics, canonical unavailable groups, flow-trigger blocking,
      and breakout-confirmed unlocking.

### Wiring / Persistence

- [x] Wired Alpha/Trigger diagnostics into `AssessSignalEvidenceUseCase` and
      `AssessSignalResponse`.
- [x] Emitted Alpha/Trigger fields through `SignalAssessment.to_dict()`.
- [x] Emitted Alpha/Trigger fields through swing workflow verdict JSON.
- [x] Persisted Alpha/Trigger exact scores, horizon, route metadata, and gating
      reasons in accumulation candidate observation fingerprints.
- [x] Added Alpha/Trigger fields to `SignalObservationFingerprint` with
      backward-compatible defaults and `data.get()` parsing.
- [x] Added Phase B attribution buckets for saved alpha/trigger values without
      recomputing historical evidence.
- [x] Added diagnostic volatility context to swing workflow output: ATR, ATR%,
      volatility bucket, ATR stop/target hints, and size multiplier hint.
- [x] Did not change final stop, target, or position sizing authority.

### Tests Added / Updated

- [x] `tests/domain/value_objects/test_alpha_trigger_score.py`
- [x] `tests/application/use_case/test_assess_signal_evidence_use_case.py`
      Alpha/Trigger cases.
- [x] `tests/application/services/test_signal_engine_config.py`
      Alpha/Trigger config cases.
- [x] `tests/application/services/test_alpha_trigger_aggregator.py`
      four-group coverage and diagnostic authority-cap cases.
- [x] `tests/application/use_case/test_summarize_signal_forward_labels_use_case.py`
      Alpha/Trigger attribution bucket case.

### Verification

- [x] Run `python -m py_compile` for changed domain/application/config/bootstrap
      files.
- [x] Run focused pytest for Alpha/Trigger domain, aggregator/use-case, config
      validator/config loader, swing workflow serialization, persistence
      fingerprint parsing, and forward-label attribution.
- [x] Run `git diff --check`.
- [x] Review `git diff` for unintended adapter policy or TradeSetup/RiskEngine
      changes.
- [x] Full suite run: 2515 passed, 3 failed in
      `tests/adapters/cli/test_fetch_market_commands.py`; failures match the
      pre-existing fetch-market status/date expectation issues and are unrelated
      to Phase G.

### Deferred / Not Phase G Closure Blockers

- [ ] Phase D/E/F diagnostic evidence is not promoted into production scoring.
- [ ] `market_context` and `company_quality_context` producers remain deferred;
      their canonical slots exist, lower evidence coverage while missing, and
      remain DIAGNOSTIC until later phases feed and validate them.
- [x] Candidate observation persistence has Alpha/Trigger payload fields and
      existing repository/workflow-adjacent regression tests pass.
- [x] Swing workflow JSON emits Alpha/Trigger and volatility context; existing
      swing workflow regression tests pass.
- [ ] CLI display formatting for Alpha/Trigger diagnostics is not implemented;
      adapters remain render-only.
- [ ] ATR hint thresholds and size multipliers are placeholders and not
      Phase-I-calibrated production tunables.
- [ ] Phase I walk-forward calibration, promotion workflow, and empirical
      readiness gates remain out of scope.

### Layer Summary

- Domain: Alpha/Trigger score, route contribution, and evidence registration
  value objects; additive exact fields on `SignalAssessment`.
- Application: Alpha/Trigger aggregation service, evidence use-case wiring,
  response serialization, fingerprint attribution, and volatility diagnostics.
- Infrastructure: config YAML and bootstrap resolution; validator bounds for
  new numeric config paths.
- Adapter: not touched for policy; display-only follow-up remains optional.

---
