# Signal Refactor Phase Plan

Date: 2026-07-05

Purpose: provide the implementation phase plan for the finalized SignalEngine
refactor direction in `docs/signal_refactor.md`.

This document is a planning artifact only. It does not change runtime behavior.
`docs/signal_refactor.md` remains the design rationale; this file is the phase
execution plan.

## Rollout Principle

```text
Canonical architecture, pattern-specific rollout.
```

The architecture remains general and composable:

- shared evidence contracts
- `SetupPhaseState`
- `RegimeDetectionEvidence`
- forward labels
- evidence status registry
- Alpha/Trigger aggregation
- DecisionPolicy constraints
- TradeSetup execution boundary

Production calibration is pattern-specific to avoid exploding the tuning
surface. Do not calibrate foreign institutional accumulation, domestic bandar
accumulation, mean reversion, breakout, multiple profiles, and multiple horizons
all at once.

Initial production calibration target:

```text
foreign_institutional_accumulation_large_cap_SWING_10D
```

Initial target scope:

- universe: LQ45 / IDX80 / liquid large caps
- profile: `foreign_institutional`
- horizon: `SWING_10D`
- setup family: accumulation / foreign-bounce
- primary flow track: `foreign_institutional_track`
- required phase sequence: `ACCUMULATION -> COMPRESSION -> BREAKOUT_CONFIRMATION`
- primary trigger: compression breakout with price/volume confirmation
- regime: `RISK_ON` plus explicitly validated setup-specific exceptions
- profile weights: disabled initially
- validation: forward-label / OOS attribution gates required

Second rollout track:

```text
domestic_bandar_accumulation_midcap_TACTICAL_3D_or_SWING_10D
```

Second-track scope:

- universe: liquid mid/small caps with usable broker detail
- profile: `domestic_bandar`
- primary flow track: `domestic_bandar_track`
- trigger: volume dry-up reversal + broker net-buy flip + price confirmation
- calibration: separate from foreign institutional accumulation
- threshold reuse: do not reuse foreign-track thresholds without OOS attribution

## Cross-Phase Rules

- RiskEngine remains the only hard trade-risk gate authority.
- SignalEngine emits evidence, phase state, coverage/conviction, context, and
  decision constraints.
- TradeSetup / sizing / backtest policy owns final stop, target, and position
  size.
- Regime is not a hidden multiplier inside raw stock score.
- Missing evidence lowers `coverage_score`; weak or mixed evidence lowers
  `conviction_score`.
- `enter_allowed=false` is the authoritative ENTER block. Coverage/conviction
  floors become WATCH / diagnostic-quality floors only when ENTER is disabled.
- Evidence status is enforced by config: `DIAGNOSTIC`, `LOW_WEIGHT`,
  `PRODUCTION`.
- No automatic promotion from tuning output. Promotion is a manual config change
  after validator-approved OOS evidence.
- Every new tunable config path must be registered in validator bounds in the
  same phase it becomes tunable.
- Component weight groups must sum to `1.00`; validation must reject ambiguous
  or invalid sums.
- Saved observations must persist raw sub-signal fingerprints at signal time.

## Phase A1: Regime Eligibility Policy Quick Win

Status: planned

Goal: reduce false positives immediately before changing signal math or adding
new regime persistence infrastructure.

Work:

- Add config-driven regime thresholds.
- Add `enter_allowed`.
- Add `max_decision`.
- Add `regime_size_multiplier`.
- Add coverage/conviction floors for WATCH / diagnostic quality.
- Add setup-specific regime compatibility policy.
- Define `setup_family` source priority if needed for setup-specific policy.
- Emit decision constraints.
- Preserve raw score comparability across regimes.
- Do not create a new regime persistence table in A1.

Required policy:

```text
Regime-level enter_allowed=false always overrides setup-specific max_decision=ENTER.
No setup-specific policy may re-enable ENTER while regime-level ENTER is disabled.
Setup-specific policy may tighten regime policy, not loosen it, unless a future ADR allows exceptions.
```

Verify:

- RISK_ON, NEUTRAL, RISK_OFF, and VOLATILE decisions are deterministic.
- RISK_OFF / VOLATILE cannot emit ENTER when `enter_allowed=false`.
- Decision constraints are visible in output.
- CLI adapters only display policy results; no scoring policy lives in adapters.

Why first: A1 gives immediate false-positive reduction.

## Phase A2: Full RegimeDetectionEvidence And Replay

Status: planned

Goal: build replayable market-regime infrastructure after quick eligibility
policy is explicit.

Work:

- Add deterministic `RegimeModel` / `RegimeDetectionEvidence`.
- Persist replayable `regime_observations`.
- Persist regime detection inputs:
  - `ihsg_20d_return`
  - `ihsg_trend_structure`
  - `ihsg_breadth_pct_above_ma`
  - `ihsg_volume_trend`
  - `ihsg_atr_pct`
  - `idx_foreign_flow_5d`
  - `idx_foreign_flow_20d`
  - `foreign_sell_streak_ihsg_weighted`
  - `foreign_buy_streak_ihsg_weighted`
  - `banking_sector_vs_ihsg`
  - `sector_breadth`
- Persist `regime_score`, `regime`, `regime_confidence`,
  `regime_stability`, `days_in_regime`, and `transition_warning`.
- Persist regime forward labels:
  - `forward_ihsg_return_5d`
  - `forward_ihsg_return_10d`
  - `forward_ihsg_return_20d`
  - realized volatility / adverse market movement where available
- Keep IDX foreign-flow transition inputs diagnostic / low-authority until
  market-level labels prove lead-time value.

Verify:

- Regime observations are deterministic and replayable.
- Regime confidence/stability are visible in signal output.
- Regime improvements are validated with market-level forward labels, not only
  ticker trade outcomes.

Why next: A2 builds replayable regime infrastructure without blocking A1.

## Phase B: Minimal Forward Labels And Observation Fingerprints

Status: planned

Goal: create replayable outcome labels before deeper architecture and tuning.

Work:

- Persist deterministic `signal_forward_labels`.
- Start calibration with `SWING_10D` as the first calibrated horizon.
- Keep `TACTICAL_3D` and `ACCUM_20D` diagnostic or temporarily sharing
  `SWING_10D` defaults until SWING is patch-eligible.
- Implement `SUCCESS`, `FAILURE`, `NEUTRAL`, and `UNAVAILABLE`.
- Store continuous outcomes:
  - close return
  - max forward return
  - max adverse excursion
  - days to peak/trough
  - stop/target triggers
- Mark incomplete candle windows as `UNAVAILABLE` with reason.
- Persist sub-signal fingerprints at observation time:
  - setup family
  - setup phase
  - RSI
  - BB width percentile
  - VWAP position
  - RS vs IHSG
  - volume ratio
  - CNFB
  - foreign participation/concentration
  - domestic broker accumulation
  - market regime metadata
  - coverage/conviction

Verify:

- Labels are local-first and independent of AI.
- Attribution does not require recomputing historical evidence.
- Missing forward windows are explicit, not silently ignored.

Why second: without labels, improvements are judged by intuition.

## Phase C: SetupPhaseState And Continuous Setup/Trigger Scoring

Status: planned

Goal: detect temporal setup phase first, then replace coarse setup labels with
continuous price/volume pivot evidence.

Work:

- Add `SetupPhaseState`:
  - `NONE`
  - `ACCUMULATION`
  - `COMPRESSION`
  - `BREAKOUT_CONFIRMATION`
  - `EXHAUSTION`
  - `DISTRIBUTION`
  - `FAILED`
- Persist phase state, phase history, phase sequence validity, phase age, and
  phase strength.
- Enforce setup-family phase requirements:
  - accumulation / foreign-bounce require
    `ACCUMULATION -> COMPRESSION -> BREAKOUT_CONFIRMATION`
  - breakout requires `COMPRESSION -> BREAKOUT_CONFIRMATION`
  - pullback requires trend/context support plus support reclaim or pivot
    confirmation
  - mean reversion requires support/reversal evidence and explicit risk controls
- Emit `coverage_score` and `conviction_score`.
- Promote RS vs IHSG to setup eligibility / max-decision evidence for swing,
  breakout, accumulation, and foreign-bounce.
- Add setup-family configurable RS policy:
  - lag warning
  - hard exclude
  - warning action
  - mean-reversion exception requirements
- Add BB compression as `COMPRESSION` readiness, not bullish evidence.
- Add `volume_dry_up_then_expansion` as the primary `SWING_10D` trigger pattern
  for accumulation, foreign-bounce, and breakout.
- Route volume expansion, positive close, VWAP reclaim, support reclaim, and
  squeeze release to `BREAKOUT_CONFIRMATION` / Trigger.
- Treat price confirmation thresholds as placeholders until setup/horizon
  calibration.
- Ensure `vwap_reclaim.close_above_vwap_pct: 0.30` cannot independently unlock
  flow Trigger contribution in production.

Verify:

- Distribution, failed, and exhaustion phases are evaluated before generic
  non-breakout WATCH handling.
- Negative RS cannot be silently overwhelmed by other bullish setup components.
- Volume trigger eligibility is data-quality based: stock tickers may use valid
  local IDX/OHLCV volume regardless of vendor label, benchmark/IHSG source
  handling is separate, and enough valid 20d sessions are required.
- Suspended days, missing candles, synthetic/missing volume, and excessive
  zero-volume distortion make volume trigger unavailable and lower coverage.

## Phase D: Strategy Evidence Harness

Status: planned

Goal: reuse deterministic strategy packages as setup-family evidence and
empirical validation tools without creating a parallel decision engine.

Work:

- Add `StrategyEvidenceBuilder` in the application layer.
- Evaluate validated strategy YAMLs through `IndicatorRegistry`.
- Map matched strategy rules to setup-family and setup-phase evidence with:
  - coverage/conviction metadata
  - freshness
  - route metadata
  - rationale
- Persist matched strategy name, matched rule, and outcome in replay
  observations.
- Forbid strategy matches from overriding canonical `SetupPhaseState`
  transition rules.
- Use strategy backtests for empirical readiness checks before assigning
  production weight.

Verify:

- Strategy outcomes cannot directly override canonical SignalEngine decisions.
- Strategy evidence remains diagnostic until explicitly consumed by aggregation.

## Phase E: Institutional Accumulation Evidence

Status: planned

Goal: make IDX flow empirical and two-track, while keeping it low-authority
until proven.

Work:

- Add `InstitutionalAccumulationEvidence.institutional_flow`.
- Add `foreign_institutional_track`:
  - foreign participation
  - foreign CR4/CR8 concentration
  - CNFB-vs-price divergence
  - foreign VWAP distance
- Add `domestic_bandar_track`:
  - top3/top5 domestic broker net-buy consistency
  - broker reversal signal
  - accumulation-session ratio
  - domestic buy VWAP distance
  - broker HHI divergence
  - bandar broad / accumulation score
- Add counterparty transfer metrics when broker-side data supports it.
- Use asymmetric windows:
  - 20d/30d for bullish accumulation / Alpha
  - 3d/5d/7d for bearish distribution / risk
- Enforce valid-session coverage before CNFB/VWAP metrics are available.
- Persist raw flow metrics in replay observations.
- Enforce EvidenceRegistration:
  - `DIAGNOSTIC` report-only
  - `LOW_WEIGHT` status-capped
  - `PRODUCTION` normal configured weight

Verify:

- Missing foreign flow does not mean missing institutional flow when domestic
  broker evidence exists.
- Domestic broker accumulation supports ACCUMULATION / Alpha but cannot directly
  create ENTER.
- Broker codes are treated as evidence, not proof of actual owner identity.
- Foreign and domestic component weight groups sum to `1.00`.

## Phase F: Minimal Ticker Profile Diagnostics

Status: planned

Goal: classify ticker behavior without introducing tunable explosion.

Work:

- Add deterministic profile classifier as an application service.
- Use local data only:
  - liquidity
  - broker activity
  - foreign flow
  - volatility
  - index membership
- Output soft exposures and `profile_confidence`.
- Persist profile snapshots by epoch, monthly default cadence.
- Backtests read historical profile snapshots for the signal date.
- Define conservative fallback for sparse-history tickers.
- Use profiles for evidence interpretation, diagnostics, and max decision only.
- Do not add per-profile group weights yet.

Verify:

- Profile snapshots are deterministic and replayable.
- Sparse-history tickers receive conservative defaults.
- Profile-specific weights are not introduced before SWING_10D is patch-eligible.

## Phase G: Simplified Alpha/Trigger Split

Status: planned

Goal: separate structural attractiveness from entry timing without adding a
large tunable surface.

Work:

- Add Alpha and Trigger component scores.
- Derive Alpha and Trigger from the four canonical groups:
  - `setup_quality`
  - `institutional_flow`
  - `market_context`
  - `company_quality_context`
- Do not introduce a second independent factor tree.
- Store only `alpha_fraction`; derive `trigger_fraction = 1.0 - alpha_fraction`.
- Keep flow primarily Alpha/context.
- Permit flow Trigger contribution only when price/volume confirms.
- Apply EvidenceRegistration status caps during aggregation.
- Add volatility context emission if not already present:
  - ATR
  - ATR%
  - volatility bucket
  - ATR stop/target hints
  - volatility size multiplier
- Keep ATR stop/target hints as placeholders until TradeSetup/backtest
  calibration defines horizon-specific multiples.
- Decide score precision contract:
  - migrate score to float, or
  - add `raw_score` / `score_exact` while preserving display int behavior

Verify:

- Alpha/Trigger matrix is descriptive unless explicit gates are configured.
- Flow cannot dominate Trigger without price/volume confirmation.
- ATR hints do not compute final stop, target, or position size.

## Phase H: Sector Context

Status: planned

Goal: make IDX sector rotation part of signal interpretation without blocking on
a new external provider.

Work:

- Add sector-relative return and breadth metrics.
- Add ticker-vs-sector relative strength.
- Use local universe-derived sector metrics first.
- Fall back deterministically when sector mapping or peer coverage is
  insufficient.
- Feed sector context into `market_context` evidence and decision constraints.

Verify:

- Sector-derived context has local-universe fallback.
- Scoring code does not fetch network data to complete peer coverage.

## Phase I: Full Walk-Forward Calibration And Expanded Tunables

Status: planned

Goal: tune weights and thresholds only from replayable saved observations.

Work:

- Use persisted observations and forward labels.
- Do not introduce separate `TACTICAL_3D` or `ACCUM_20D` tuning surfaces until
  `SWING_10D` clears patch eligibility.
- Enforce in-sample/out-of-sample split.
- Quantize weight changes.
- Cap per-cycle shifts.
- Register all tunable config paths in validator bounds before use.
- Add validator support for diagnostic-ready vs patch-eligible states.
- Update `SwingTuningPatchValidator` where current behavior is weaker than the
  target acceptance gates.
- Reject hidden single-regime dependency unless setup is explicitly declared
  single-regime scoped before calibration.
- Reject threshold borrowing across patterns unless OOS attribution validates
  the transfer.

Patch-eligible target gates:

```yaml
tuning_readiness:
  diagnostic_ready:
    min_oos_trades: 10
    allowed_output: report_only
    may_change_config: false

  patch_eligible:
    min_is_trades: 60
    min_oos_trades: 30
    min_oos_profit_factor: 1.15
    min_oos_average_return: 0.0
    max_oos_drawdown_regression: 0.0
    require_regime_attribution: true
    require_coverage_conviction_bucket_attribution: true
    reject_single_regime_dependency:
      max_single_regime_oos_profit_share: 0.70
      min_positive_oos_regime_count: 2
      min_oos_trades_per_counted_regime: 5
```

Verify:

- Diagnostic-ready findings are report-only.
- Patch-eligible changes pass IS/OOS sample gates and attribution checks.
- No config patch can exceed EvidenceRegistration status caps.
- Regime improvements are validated with market-level forward labels, not only
  ticker trade outcomes.

## Layer Placement

Domain:

- immutable evidence value objects
- `RegimeDetectionEvidence`
- `SetupPhaseState` and phase-history value objects
- score/result value objects
- no providers, repositories, CLI, or AI

Application:

- evidence builders
- regime model / market-wide regime detection use case
- setup phase detector / transition policy
- strategy evidence builder
- indicator registry / formula evaluation orchestration
- profile classifier
- Alpha/Trigger aggregation
- regime threshold policy
- decision policy combining RegimeModel constraints with SignalEngine evidence
- replay labeling and calibration use cases

Infrastructure:

- repository implementations
- Stockbit/IDX/Yahoo provider adapters
- plugin loading
- local SQLite persistence
- schema-versioned observation storage

Adapter:

- CLI request parsing
- dependency wiring
- display formatting
- error mapping

## Definition Of Done For Each Phase

- Deterministic behavior under fixed local data and config.
- Unit or focused integration tests for changed policy.
- No scoring policy in CLI adapters.
- No AI-dependent scoring.
- New tunables registered in validator bounds.
- New persistence is schema-versioned where applicable.
- Existing RiskEngine hard-gate authority remains intact.
- Documentation updated when phase state changes.
