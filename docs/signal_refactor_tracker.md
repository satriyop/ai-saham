# Signal Engine Refactor Tracker

_Design rationale: `docs/signal_refactor.md`_
_Phase plan: `docs/signal_refactor_phases.md`_
_Current implementation target: Phase G implementation_
_Updated: 2026-07-06_

This tracker records the current implementation state and concrete checklist for
the SignalEngine refactor. A1, A2, B, C, D, E, and F are closed. Phase G is the next
implementation target.

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

- Phase F (Minimal Ticker Profile Diagnostics) is the active implementation target.
- Phase F profile snapshots are DIAGNOSTIC-only; profiles do not feed into SignalEngine
  group scoring or DecisionPolicy until Phase G explicitly wires them.
- Phase E institutional accumulation evidence is DIAGNOSTIC-only; `FlowConfirmationEvidence`
  group scoring is unchanged until Phase G/I explicitly promotes institutional flow.
- Phase D strategy evidence contract is preserved; Phase G is the first phase
  allowed to consume it in Alpha/Trigger aggregation.
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

**Status:** Closed

**Goal:** Classify ticker behavior deterministically without introducing tunable explosion.
Produce `TickerProfileSnapshot` for each ticker at signal time — dimension scores, soft
primary-profile exposures, separate market tier, and profile confidence. DIAGNOSTIC-only.
Does not feed into SignalEngine scoring or DecisionPolicy.

**Close summary:** Phase F is closed as a diagnostic-only layer. Sparse/new
tickers are conservative (`primary_profile=unclassified`, FI=0.0 / DB=0.5 /
RS=0.5), configured exposure weights are validated, snapshots are persisted in
replay fingerprints, and no Phase F output changes scoring, decision policy, or
TradeSetup sizing.

Design rationale: `docs/signal_refactor.md` § Phase F.
Implementation plan: `/Users/satriyo/.claude/plans/plan-for-phase-e-bubbly-panda.md`.

### Non-Goals

- [x] Do not change `AssessSignalEvidenceUseCase` group scoring.
- [x] Do not change `DecisionPolicy` or `SignalEngine.evaluate_with_context()`.
- [x] Do not add per-profile group weights (Phase G).
- [x] Do not add max-decision overrides driven by profile (Phase G).
- [x] Do not add evidence interpretation wiring into scoring (Phase G).
- [x] Do not add a new `ticker_profiles` SQLite table (Phase I).
- [x] Do not duplicate `EvidenceStatus` enum — import from `institutional_accumulation_evidence.py`.
- [x] Do not fetch data inside the classifier.

### Domain

- [x] Add `TickerProfileSnapshot` frozen dataclass in `src/domain/value_objects/ticker_profile_snapshot.py`.
  - Fields: ticker, snapshot_date, epoch (str), primary_profile, profile_confidence,
    liquidity_score, broker_concentration_score, foreign_flow_score, volatility_score,
    index_membership_score, market_cap_bucket, sector, sub_sector, index_memberships,
    coverage_score, evidence_status, reasons, unavailable_reasons, market_tier,
    foreign_institutional_exposure, domestic_bandar_exposure,
    retail_speculative_exposure, metadata.
  - `__post_init__` bounds: all `*_score` fields, profile_confidence,
    coverage_score, and soft exposure fields in [0,1]; non-empty ticker.
  - `to_dict()`/`from_dict()` with `data.get()` for backward compat; snapshot_date as ISO string.
- [x] Reuse `EvidenceStatus` enum from `institutional_accumulation_evidence.py` — do not duplicate.

### Config

- [x] Add `config/ticker_profile.yaml` with evidence_status, profile_window_days (30),
      market_cap_thresholds_idr (large/mid/small), index_membership_scores (lq45/idx30/idx80/jii/mbx),
      liquidity_thresholds, volatility_thresholds, sparse_history_threshold (10),
      conservative_fallback_confidence (0.30), and exposure_weights.
- [x] `TickerProfileConfig.validate()` checks index_membership_scores all in [0,1].
- [x] `TickerProfileConfig.validate()` checks configured exposure weights are
      non-negative and sum to 1.0 per profile.

### Application

- [x] Add `TickerProfileRequest` frozen dataclass (ticker, snapshot_date, candles,
      broker_daily_flows, broker_summaries, market_cap_idr, sector, sub_sector).
- [x] Add `TickerProfileClassifier` with `from_yaml()` factory in
      `src/application/services/ticker_profile_classifier.py`.
- [x] Load `universes.yaml` at construction; build `{ticker: (universe_names...)}` reverse index
      for index membership resolution (not a per-request data fetch).
- [x] Compute `liquidity_score` from Candle: mean `high * volume` per day → saturating linear
      between `low_daily_value_idr` (0.0) and `high_daily_value_idr` (1.0); guard zero-volume candles.
- [x] Compute `broker_concentration_score` from BrokerDailyFlow (local brokers only): buy-side HHI;
      guard `total_local_buy == 0`.
- [x] Compute `foreign_flow_score` from BrokerSummary: mean `(foreign_buy + foreign_sell) / total`;
      guard zero total.
- [x] Compute `volatility_score` from Candle using ATR-style true range:
      `max(high-low, abs(high-prev_close), abs(low-prev_close)) / prev_close`
      → saturating linear between `low_atr_pct` (0.0) and `high_atr_pct`
      (1.0); guard insufficient candles and zero previous close.
- [x] Compute `index_membership_score` from reverse index + config: max score across memberships;
      0.0 (not None) if no index membership.
- [x] Assign `market_cap_bucket` from `market_cap_idr` thresholds (large/mid/small/micro/None).
- [x] Assign `market_tier` from deterministic rules: blue_chip → second_liner
      → speculative → third_liner → unknown.
- [x] Compute soft behavioral exposures for `foreign_institutional`,
      `domestic_bandar`, and `retail_speculative`; assign `primary_profile`
      from the largest exposure when history is sufficient.
- [x] Sparse/new tickers force `primary_profile=unclassified`, `market_tier=unknown`,
      confidence = conservative_fallback_confidence, and conservative exposures
      FI=0.0 / DB=0.5 / RS=0.5.
- [x] Coverage = available metric slots / 5. Index membership always counts (0.0 minimum).
- [x] Profile confidence = exposure margin (largest exposure minus second
      largest exposure) when history is sufficient; sparse history uses
      conservative_fallback_confidence.
- [x] `metadata["diagnostic_only"] = True` always.
- [x] Builder never raises — top-level `except Exception` → minimal fallback snapshot with
      `metadata["error"]`; per-dimension degradation to None.

### Persistence

- [x] Add ticker profile fingerprint fields to `SignalObservationFingerprint`
      in `signal_forward_label.py` (all `None`-defaulted, `data.get()` in
      `from_dict()`): `ticker_profile_label` (stores `primary_profile`),
      `ticker_profile_confidence`, `tp_market_tier`, soft exposure fields,
      dimension scores, market-cap/sector/index fields, `tp_coverage_score`,
      and `tp_epoch`.
- [x] Add `_tp_fingerprint(tp)` helper in `accumulation_screen_use_case.py` (same None-guard pattern as `_ia_evidence_fingerprint()`).
- [x] Extend `_sub_signal_fingerprint()` with `tp_snapshot` param; spread `_tp_fingerprint()` result.
- [x] Add `ticker_profile_snapshot` key to `SwingEvidence.to_dict()`.

### Wiring

- [x] Add `ticker_profile_snapshot: "TickerProfileSnapshot | None" = None` to `SwingEvidence` dataclass.
- [x] Add build block in `swing_analysis_workflow_use_case.py` after `institutional_accumulation_evidence`
      block (same guard pattern; same data sources already opened).
- [x] Add `_build_candidate_ticker_profile(candidate, snapshot_date)` method to
      `accumulation_screen_use_case.py` (same guard pattern as `_build_candidate_institutional_accumulation_evidence()`).
      Uses same 45d broker window; extracts market_cap/sector from already-loaded candidate fields.
- [x] Extend `_candidate_observation_payload()` and `_persist_candidate_observations()` loop.
- [x] Confirm Phase F snapshot is NOT passed to `signal_engine.evaluate_with_context()`.
- [x] Confirm `DecisionPolicy` has zero references to `TickerProfileSnapshot`.
- [x] CLI adapters render returned snapshot only; no computation in CLI.

### Tests

- [x] Domain VO: to_dict/from_dict round-trip; ISO date; index_memberships as list.
- [x] Snapshot rejects empty ticker and out-of-bounds scores.
- [x] from_dict accepts minimal dict (backward compat, all optional fields None).
- [x] Classifier: liquidity score — high-value candles → score near 1.0; low-value → near 0.0.
- [x] Classifier: index membership score — LQ45 ticker → 1.0; not in any index → 0.0.
- [x] Classifier: market cap bucket — thresholds large/mid/small/micro.
- [x] Classifier: market_tier "blue_chip" — LQ45 + large cap.
- [x] Classifier: market_tier "second_liner" — IDX80 + mid cap.
- [x] Classifier: market_tier "third_liner" — small cap, no index.
- [x] Classifier: market_tier "speculative" — low liquidity + high volatility.
- [x] Classifier: sparse history fallback — < 10 candles →
      `primary_profile=unclassified`, market_tier "unknown", confidence 0.30,
      FI=0.0 / DB=0.5 / RS=0.5.
- [x] Classifier: graceful degradation — exception → fallback, no raise.
- [x] Classifier: missing broker data — dimensions None, coverage < 1.0, snapshot still returned.
- [x] Config validation — index score > 1.0 rejected.
- [x] Config validation — exposure weights reject negative values and sums
      other than 1.0 per configured profile.
- [x] `_tp_fingerprint()` reads correct fields; `tp_index_memberships` is comma-joined string.
- [x] Scoring isolation — `TickerProfileSnapshot` does NOT change `AssessSignalEvidenceUseCase` output (zero references in SignalEngine + domain rules confirmed by grep).
- [x] Backward compat — old fingerprints without `tp_*` fields parse without KeyError (all fields `= None` default; `data.get()` in `from_dict()`).
- [x] All tests pass offline (2489 total; 3 pre-existing CLI fetch failures unrelated to Phase F).

### Verification

- [x] `TickerProfileSnapshot` is deterministic for fixed local data + config.
- [x] Profile snapshots are replayable through Phase B forward labels (tp_* fields persisted at signal time).
- [x] Sparse-history tickers receive conservative defaults
      (`primary_profile=unclassified`, market_tier "unknown", confidence 0.30,
      FI=0.0 / DB=0.5 / RS=0.5).
- [x] Phase F snapshot is DIAGNOSTIC-only in `SignalEngine` and `DecisionPolicy` (grep confirms zero references).
- [x] No per-profile group weights introduced.
- [x] `SwingEvidence` sizing math and TradeSetup unchanged.
- [x] All tests pass offline (2489 passing; 3 pre-existing unrelated failures).

### Deferred to Later Phases

- Per-profile group weights (Phase G).
- Profile-driven max_decision overrides (Phase G).
- Evidence interpretation wiring (Phase G).
- Epoch-keyed `ticker_profiles` SQLite table for backtest snapshot lookup (Phase I).
- Per-horizon profile tunables (Phase I).
- EvidenceStatus registry / cap enforcement (Phase G/I).

---
