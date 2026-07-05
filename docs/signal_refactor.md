# Signal Engine Refactor Recommendation

Date: 2026-07-05

This document is the current recommendation for the next-generation SignalEngine
direction. It replaces the earlier restart analysis. It is a design and planning
document only; no runtime behavior is changed by this file.

The goal is an IDX-native signal engine that is more accurate, easier to tune,
and easier to audit without violating the deterministic-first, local-first,
hexagonal architecture rules of this repository.

## Executive Conclusion

Do not build one larger composite score. Build a profile-aware, evidence-based
engine that separates:

1. Setup quality: is the chart structure good?
2. Institutional flow: is there real accumulation/distribution?
3. Context: is the market, sector, and liquidity regime supportive?
4. Alpha: is the ticker structurally attractive enough for the intended horizon?
5. Trigger: is now a good entry timing window?
6. Decision policy: given the score, coverage, conviction, regime, and gates,
   what action is allowed?

The current empirical conclusion is:

```text
quiet accumulation -> volatility compression -> confirmed price/volume pivot
-> regime-sized entry
```

Flow is not the primary entry trigger. Institutional accumulation and
foreign/broker flow should primarily define Alpha, eligibility, context,
diagnostics, and risk warnings. Raw net-buy intensity must not directly create
`ENTER`. Trigger should be dominated by price/volume pivot confirmation:
positive close confirmation, squeeze release, volume spike or dry-up reversal,
VWAP reclaim, and support/reclaim behavior.

The strongest near-term improvement is therefore not more flow weighting. It is
regime-aware eligibility plus replayable forward labels, then temporal
setup-phase detection and continuous setup/trigger scoring that can prove
whether ordered accumulation -> compression -> breakout/pivot sequences separate
winners from losers out of sample.

## Architecture Principles

### Keep One Canonical Scoring Path

The production signal path should have one source of truth:

```text
Raw local data
 -> evidence builders
 -> ticker profile diagnostics
 -> Alpha and Trigger scoring
 -> market/setup-regime eligibility and sizing constraints
 -> decision policy
 -> persisted observation
 -> walk-forward tuning
```

Legacy flat scoring can remain temporarily as an archived reference for parity
checks, but runtime scoring and tuning should use only the evidence-based path.

### Preserve Score Meaning Across Regimes

Market regime should change classification thresholds, not distort raw evidence
scores.

Prefer:

```text
score = 74
RISK_OFF ENTER threshold = 80
decision = WATCH
```

Avoid:

```text
score = 74 * 0.50
```

The first approach keeps a score comparable across dates and regimes. The second
approach makes historical calibration harder because the same raw setup no
longer has the same score meaning.

### Separate Coverage From Conviction

Do not collapse evidence availability and evidence strength into one
`confidence` number. The engine should emit two distinct concepts:

```text
coverage_score:
  how much required evidence is available and fresh enough to use

conviction_score:
  how strongly the available evidence points in a directional conclusion
```

Rules:

```text
missing evidence     -> lowers coverage_score, not conviction_score
weak or mixed signal -> lowers conviction_score, not coverage_score
```

A high-conviction but low-coverage setup should usually be `WATCH` or
`INSUFFICIENT_DATA`, not `ENTER`. A high-coverage but low-conviction setup
should usually be weak `WATCH` or `AVOID`.

Example:

```text
setup_score = 76
flow_score = unavailable
coverage_score = 0.55
conviction_score = 0.78
decision = WATCH, not ENTER
```

### Deterministic First

All recommendations here are deterministic. AI may later summarize evidence or
propose config diffs, but AI must not become the scoring authority.

### Implementation Complete Is Not Empirically Ready

Evidence-first architecture is only useful if the evidence is empirically
discriminative.

An implemented evidence contract is not production-ready just because it is
typed, persisted, and displayed. It must prove that it separates profitable from
unprofitable outcomes across walk-forward out-of-sample samples.

Examples:

```text
evidence_quality fields exist   = implementation complete
evidence buckets separate high-quality OOS winners from losers
                               = empirical readiness

new flow evidence computes CR4  = implementation complete
CR4 buckets improve OOS payoff ratio or reduce drawdown
                               = empirical readiness
```

Until empirical readiness is proven, new evidence should be treated as
diagnostic, low-weight, or coverage/conviction-only. It should not become a
high-impact production factor merely because the implementation is finished.

### Evidence Status Registry

Evidence authority must be enforced by config/domain policy, not by comments.
Add a first-class evidence registration concept:

```text
EvidenceRegistration
- evidence_name
- status: DIAGNOSTIC | LOW_WEIGHT | PRODUCTION
- max_weight_by_status
- promotion_requires
- current_status
- promoted_by
- promoted_date
```

Rules:

```text
DIAGNOSTIC = report-only; cannot contribute to score
LOW_WEIGHT = may contribute only up to the configured status cap
PRODUCTION = may use normal configured weight
```

Promotion requires walk-forward OOS proof. The scoring engine must enforce the
registry on every aggregation path so a newly implemented evidence source cannot
accidentally become production authority.

Operational workflow:

```text
EvidenceRegistration is declared in YAML/config.
Application aggregation service loads and enforces it.
DIAGNOSTIC evidence is report-only.
LOW_WEIGHT evidence is capped by status.
PRODUCTION evidence uses configured weight.
Promotion is a manual config change after validator-approved OOS evidence.
No automatic promotion from tuning output.
Validator rejects patches that exceed status caps.
```

### Pattern-Specific Rollout Strategy

Principle:

```text
Canonical architecture, pattern-specific rollout.
```

The architecture remains general and composable: shared evidence contracts,
`SetupPhaseState`, `RegimeModel`, forward labels, decision policy, and the
TradeSetup execution boundary. Do not build a narrow one-off engine.

Empirical rollout is pattern-specific to avoid exploding the tuning surface. Do
not calibrate foreign institutional accumulation, domestic bandar accumulation,
mean reversion, breakout, multiple profiles, and multiple horizons all at once.

Initial production calibration target:

```text
foreign_institutional_accumulation_large_cap_SWING_10D
```

Scope:

```text
universe: LQ45 / IDX80 / liquid large caps
profile: foreign_institutional
horizon: SWING_10D
primary evidence: foreign_institutional_track
setup phase sequence: ACCUMULATION -> COMPRESSION -> BREAKOUT_CONFIRMATION
trigger: compression breakout with price/volume confirmation
regime: RISK_ON plus explicitly validated setup-specific exceptions
per-profile weights: disabled initially
validation: forward-label / OOS attribution gates required
```

Second rollout track:

```text
domestic_bandar_accumulation_midcap_TACTICAL_3D_or_SWING_10D
```

Scope:

```text
universe: liquid mid/small caps with usable broker detail
profile: domestic_bandar
primary evidence: domestic_bandar_track
trigger: volume dry-up reversal + broker net-buy flip + price confirmation
calibration: separate from foreign institutional accumulation
threshold reuse: do not reuse foreign-track thresholds blindly
```

Production-calibrated setup declarations must be explicit:

```text
target universe
profile
horizon
setup family
primary flow track
required phase sequence
regime scope
patch eligibility gates
```

A setup cannot borrow thresholds from another pattern unless OOS attribution
validates the transfer.

## Recommended Signal Model

### 1. Temporal Setup Phase State

The signal model must not be only a simultaneous factor composite. For IDX
accumulation and foreign-bounce setups, evidence order matters.

First-class state:

```text
SetupPhaseState:
- NONE
- ACCUMULATION
- COMPRESSION
- BREAKOUT_CONFIRMATION
- EXHAUSTION
- DISTRIBUTION
- FAILED
```

Core principle:

```text
state = where the ticker is in the setup lifecycle
score = strength of evidence inside the current or prior phase
```

For accumulation / foreign-bounce setups, the valid sequence is:

```text
Silent accumulation -> volatility compression -> breakout/pivot confirmation -> entry
```

Phase definitions:

```text
ACCUMULATION:
- CNFB rising over 15-30 sessions
- price flat or slightly declining
- volume stable or declining
- bandar/domestic broker net buy consistent
- no fast distribution warning

COMPRESSION:
- BB width percentile below configured threshold
- ATR declining or stable
- price holds support / range
- CNFB rising or plateauing, not dumping

BREAKOUT_CONFIRMATION:
- positive close above compression/range reference
- volume spike or valid volume confirmation
- VWAP reclaim / foreign VWAP reclaim / support reclaim
- optional broker/foreign acceleration confirms, but does not replace price confirmation

EXHAUSTION / DISTRIBUTION:
- fast 3d/5d/7d distribution
- bearish release from compression
- failed breakout
- volume spike on negative close
- caps max_decision or forces WATCH/AVOID depending severity
```

Decision rules for accumulation / foreign-bounce:

```text
ENTER is valid only in BREAKOUT_CONFIRMATION.
ENTER requires prior ACCUMULATION and COMPRESSION observed in sequence.
ACCUMULATION alone = WATCH / candidate tracking.
COMPRESSION alone = WATCH / trigger pending.
BREAKOUT_CONFIRMATION without prior accumulation/compression = different setup family,
not foreign-bounce ENTER.
DISTRIBUTION or FAILED caps decision or blocks entry.
```

Setup-family phase requirements are config-driven and must be persisted in
observations:

```yaml
setup_phase_requirements:
  accumulation:
    required_sequence: [ACCUMULATION, COMPRESSION, BREAKOUT_CONFIRMATION]

  foreign_bounce:
    required_sequence: [ACCUMULATION, COMPRESSION, BREAKOUT_CONFIRMATION]

  breakout:
    required_sequence: [COMPRESSION, BREAKOUT_CONFIRMATION]
    prior_accumulation: optional_unless_config_requires

  pullback:
    requires:
      trend_or_context_support: true
      support_reclaim_or_pivot_confirmation: true
    compression: optional

  mean_reversion:
    prior_accumulation_required: false
    requires:
      support_or_reversal_evidence: true
      explicit_risk_controls: true
```

This keeps strict sequencing for accumulation and foreign-bounce without
incorrectly forcing every setup family into the same lifecycle.

This phase state is evidence produced by SignalEngine, not a RiskEngine gate.
RiskEngine remains the only hard gate authority.

### 2. Primary Trigger Patterns

For `SWING_10D` accumulation-style setups, volume dry-up followed by directional
volume expansion is the anchor trigger pattern. It should not be treated as just
one of many equal trigger signals.

Initial policy shape:

```yaml
primary_trigger_patterns:
  swing_accumulation:
    setup_families:
      - accumulation
      - foreign_bounce
      - breakout
    volume_dry_up_then_expansion:
      dry_up:
        min_sessions_below_avg: 3
        volume_ratio_max: 0.50
        lookback_avg_sessions: 20
      expansion:
        volume_ratio_min: 1.50
        close_positive: true
        close_above_compression_range: true
```

Semantics:

```text
dry-up phase:
  supply exhaustion / quiet accumulation

expansion phase:
  demand returning with directional confirmation
```

For `SWING_10D` accumulation, foreign-bounce, and breakout setups, `ENTER`
should require expansion confirmation after dry-up/compression. Secondary
triggers may include VWAP reclaim, support reclaim, squeeze release, positive
close, and broker/foreign acceleration. Secondary triggers confirm or supplement
the primary pattern; they must not replace it unless setup config explicitly
allows that exception.

Scope:

```text
primary for:
- SWING_10D accumulation
- SWING_10D foreign_bounce
- SWING_10D breakout

not universal for:
- mean_reversion
- pre-open / NCP
- intraday
- catalyst setups
```

Data quality guardrails:

```text
volume trigger requires valid volume source
20d average requires enough valid trading sessions
suspended days / missing candles / zero-volume distortion = trigger unavailable
unavailable volume trigger lowers coverage_score
```

### 3. Continuous Setup And Trigger Scoring

Current setup classification can collapse useful information into coarse labels
such as `MATCH`, `PARTIAL`, and `NO_MATCH`. Those labels are still useful for
explanation, but they should not drive the numeric score by themselves.

Setup score should come from structural sub-signals directly, but setup
eligibility and max-decision caps can override the additive score. RS vs IHSG is
one of those cases: for non-mean-reversion IDX setups, negative RS is primarily
a setup-eligibility / max-decision signal, not merely a small additive weight.

```yaml
setup_scoring:
  trend_alignment:
    weight: 0.30
  rsi_quality:
    weight: 0.20
  bb_compression_readiness:
    weight: 0.20
  vwap_position:
    weight: 0.15
  relative_strength_vs_ihsg:
    weight: 0.15
```

Output example:

```text
setup_score = 73
setup_label = PARTIAL
failed_gates = ["rsi"]
```

The score remains continuous. The label and failed gates explain why it is not a
clean setup.

Relative strength vs IHSG is core `setup_quality` evidence for swing,
trend-following, breakout, accumulation, and foreign-bounce setups. It should
not remain merely diagnostic for swing/accumulation decisions, and it should not
be treated as only a 15% score component for breakout, accumulation, or
foreign-bounce setups.

Suggested evidence fields:

```text
relative_strength_context:
  rs_vs_ihsg_20d: float | null
  rs_bucket: LEADER | NEUTRAL | LAGGARD | UNKNOWN
  rs_confidence: float
  ihsg_window_complete: bool
```

Design rule:

```text
trend / breakout / accumulation / foreign_bounce:
  negative RS vs IHSG caps max_decision, heavily penalizes setup_quality,
  or marks the setup ineligible depending on severity

mean_reversion:
  weak RS may be allowed only when support/reversal evidence is strong
```

Setup-family configurable policy:

```yaml
relative_strength_policy:
  foreign_bounce:
    rs_20d_lag_warning: -0.03
    rs_20d_hard_exclude: -0.06
    warning_action:
      max_decision: WATCH
      setup_score_penalty: -25

  breakout:
    rs_20d_lag_warning: -0.03
    rs_20d_hard_exclude: -0.06
    warning_action:
      max_decision: WATCH
      setup_score_penalty: -25

  accumulation:
    rs_20d_lag_warning: -0.03
    rs_20d_hard_exclude: -0.06
    warning_action:
      max_decision: WATCH
      setup_score_penalty: -25

  mean_reversion:
    negative_rs_allowed: true
    requires:
      support_confirmed: true
      reversal_evidence_min: 70
```

Semantics:

```text
rs_20d_lag_warning:
  cap max_decision or apply a strong setup_score penalty

rs_20d_hard_exclude:
  setup_eligible = false and max_decision = AVOID for that setup family
```

This is SignalEngine setup eligibility, not `RiskEngine` `BLOCKED`. RiskEngine
remains the only hard trade-risk gate authority.

Negative RS while IHSG is rising should be treated as possible rotation-out or
distribution evidence for accumulation and breakout setups. Mean-reversion is
the exception, and it must explicitly require support/reversal evidence.

RS thresholds must be setup-family configurable and validator-bounded before
production use.

BB compression is `COMPRESSION` phase readiness, not simple bullish evidence.
Compression alone says price is coiled; it does not say direction. A setup
family may require compression before scoring, and compression quality may scale
trigger readiness, but trigger activation requires `BREAKOUT_CONFIRMATION`
through bullish release or positive price/volume confirmation.

```text
compression only                       = readiness, not bullish
compression + bullish close/reclaim    = trigger activation candidate
compression + bearish release          = risk/distribution evidence
```

Important de-duplication rule: Bollinger compression and volume confirmation
must not cast independent votes in multiple places. Bollinger compression
belongs to Setup Quality. Volume spike/dry-up confirmation belongs to Trigger
Timing. If a strategy package uses both, the `StrategyEvidenceBuilder` must map
each matched indicator to the owning route and cap any shared contribution.

Strict indicator ownership:

```text
Setup Quality owns relative geometry and readiness:
- Bollinger Band compression percentile
- RSI value / RSI quality
- SMA / trend alignment
- relative strength vs IHSG as core setup evidence
- daily VWAP position / proximity, not VWAP reclaim event

Trigger Timing owns immediate confirmation:
- daily volume spike or volume dry-up reversal
- positive close / pivot confirmation
- squeeze release direction
- VWAP reclaim
- support reclaim behavior
- pre-open NCP direction / imbalance
- intraday gap confirmation
- distance to foreign VWAP / tactical entry zone
```

Trigger may consume `setup_score`, but it must not independently rescore RSI,
BB width, or SMA alignment. This prevents technical momentum from being counted
once inside Setup Quality and again as separate Trigger inputs.

### 4. Reuse Indicators, Plugins, Formulas, And Strategies

The repository already has deterministic extension points that should be reused
instead of reimplemented inside SignalEngine:

```text
IndicatorRegistry:
- built-in indicators: SMA, EMA, RSI
- plugin indicators: ATR, MACD, RS_IHSG, VOLUME_RATIO, WILLIAMS_R, etc.
- formula indicators: parsed formula DSL such as SMA(RSI(14), 10)

Strategy packages:
- YAML rule sets with named indicators, deterministic conditions, outcomes, and
  backtest support
```

Recommended use:

```text
Indicator/plugin/formula output -> normalized evidence input
Strategy rule match             -> setup-family evidence / diagnostic signal
Strategy backtest result        -> empirical validation before production weight
```

Do not use strategy output as a direct SignalEngine decision override:

```text
Wrong:
strategy says LOW_RISK -> SignalEngine ENTER

Correct:
strategy says LOW_RISK -> evidence input -> canonical SignalEngine policy decides
```

Useful existing strategy packages for setup-family research:

| Strategy package | Candidate setup family | Suggested use |
|---|---|---|
| `foreign-accumulation` | `foreign_bounce` / accumulation | flow-confirmed setup evidence and regime attribution |
| `rs-momentum` | relative-strength momentum | RS vs IHSG setup evidence |
| `volume-spike` | volume trigger | trigger timing evidence |
| `williams-r-bounce` | mean reversion | bounce/oversold setup family |
| `bb-breakout` | breakout | breakout setup family |
| `bb-mean-reversion` | mean reversion | range/oversold setup family |

Future implementation should add a `StrategyEvidenceBuilder` in the application
layer. It should evaluate validated strategies through `IndicatorRegistry`,
emit evidence with route metadata, and persist matched rule names/rationales in
candidate observations. This keeps plugin/strategy extensibility useful without
creating a second production decision engine.

### 5. Institutional Accumulation Evidence

IDX flow should not be represented by raw net foreign buy alone. The flow layer
should test whether buying looks institutional, concentrated, persistent, and
price-absorbed.

Default authority:

```text
Flow defines Alpha/context/eligibility first.
Flow does not independently create ENTER.
Raw net-buy intensity is never an entry trigger by itself.
Flow may support Trigger only when it coincides with price confirmation.
Flow buckets start as diagnostic, binary, low-weight, or coverage/conviction
modifiers until walk-forward attribution proves bucket-level predictive value.
```

Recommended two-track evidence object:

```text
InstitutionalAccumulationEvidence
- institutional_flow
  - foreign_institutional_track
    - foreign_participation_score
    - foreign_concentration_cr4_score
    - foreign_concentration_cr8_score
    - cnfb_divergence_score
    - foreign_vwap_distance_score
    - coverage_score
    - conviction_score
  - domestic_bandar_track
    - top3_or_top5_domestic_broker_net_buy_consistency
    - broker_reversal_signal
    - accumulation_session_ratio
    - domestic_buy_vwap_distance
    - broker_hhi_divergence
    - bandar_broad_score
    - bandar_accumulation_score
    - coverage_score
    - conviction_score
  - counterparty_transfer_score
- coverage_score
- conviction_score
- reasons
```

Institutional flow is not foreign-only. Missing foreign flow must not imply
missing institutional flow if domestic broker accumulation evidence exists.
`foreign_institutional` profiles emphasize the foreign track, `domestic_bandar`
profiles emphasize the domestic track, and `retail_speculative` profiles keep
both tracks low-authority unless walk-forward attribution proves otherwise.
This is important for much of the non-LQ45/IDX80 universe, where foreign flow
can be sparse, absent, or irrelevant. Do not claim a fixed universe percentage
unless it is measured from local universe data.

Domestic broker accumulation does not directly create `ENTER`. It supports
ACCUMULATION / Alpha first, and still requires COMPRESSION plus price/volume
pivot confirmation before entry. Broker codes are evidence, not proof of actual
owner identity, so every broker-derived signal needs explicit coverage and
conviction metadata.

Recommended scoring weights:

```yaml
institutional_accumulation:
  authority: diagnostic_or_low_weight_until_proven
  track_weights:
    foreign_institutional_track: 0.45
    domestic_bandar_track: 0.40
    counterparty_transfer: 0.15
  foreign_institutional_track_components:
    foreign_participation: 0.25
    foreign_concentration_cr4_cr8: 0.20
    cnfb_price_divergence: 0.35
    foreign_vwap_distance: 0.20
  domestic_bandar_track_components:
    top3_or_top5_domestic_broker_net_buy_consistency: 0.25
    broker_reversal_signal: 0.15
    accumulation_session_ratio: 0.20
    domestic_buy_vwap_distance: 0.15
    broker_hhi_divergence: 0.15
    bandar_broad_or_accumulation_score: 0.10
```

All component weight groups must sum to `1.00`. Config validation must reject
component groups that are underweight, overweight, or ambiguous after disabled
components are removed.

These weights are an internal diagnostic composition, not automatic production
SignalEngine weights. Promotion from diagnostic to production scoring requires
Phase I walk-forward attribution.

#### Foreign Participation Ratio

Use traded value when available:

```text
foreign_participation =
  (foreign_buy_value + foreign_sell_value) / total_traded_value
```

Interpretation:

```text
< 10%   weak foreign relevance
10-30%  moderate foreign relevance
> 30%   meaningful foreign participation
```

These are initial defaults, not final truths. They must be walk-forward
calibrated.

#### Foreign Broker Concentration

Measure whether foreign buying is concentrated:

```text
foreign_buy_cr4 =
  top_4_foreign_broker_buy_value / total_foreign_buy_value

foreign_buy_cr8 =
  top_8_foreign_broker_buy_value / total_foreign_buy_value
```

High participation plus high CR4 is stronger evidence than high net foreign buy
spread across many brokers.

#### CNFB Price Divergence

Track cumulative net foreign buy against price:

```text
CNFB_20D = cumulative(foreign_buy_value - foreign_sell_value)
price_return_20D = close_today / close_20d_ago - 1
```

Strong silent accumulation evidence:

```text
CNFB_20D rising strongly
price_return_20D flat or slightly negative
volume stable or rising
drawdown controlled
```

Use asymmetric flow windows:

```text
bullish accumulation / Alpha:
- 20d and 30d windows by default
- optionally 60d for position/structural views
- purpose: detect quiet accumulation and cost basis

bearish distribution / risk:
- 3d, 5d, and 7d windows by default
- purpose: react faster to distribution and risk-off flow
```

Distribution evidence must react faster than accumulation evidence. Slow
accumulation can define Alpha; fast distribution can cap decision, reduce
coverage/conviction, or trigger risk warnings.

Do not rely only on Pearson correlation for short windows. Use CNFB slope, price
slope, CNFB percentile, and price range compression together.

Coverage requirement:

```text
CNFB_20D requires at least 15 valid trading sessions inside the last 20 expected
trading sessions. Below that, CNFB divergence is unavailable and coverage is
reduced.
```

Suspended days, missing broker summaries, and zero-trade days should not be
silently treated as normal observations.

#### Counterparty Transfer

Detect whether accumulation is concentrated on the buy side and fragmented on
the sell side:

```text
net_buy_hhi = sum((broker_net_buy_value / total_net_buy_value) ^ 2)
net_sell_hhi = sum((abs(broker_net_sell_value) / total_net_sell_value) ^ 2)
transfer_asymmetry = net_buy_hhi - net_sell_hhi
```

Availability rule:

```text
if total_net_buy_value <= 0 or total_net_sell_value <= 0:
    counterparty_transfer = unavailable
    coverage is reduced
```

Do not divide by zero or coerce the missing side to zero concentration. A day
with only net selling, only net buying, or unusable broker attribution is not a
valid counterparty-transfer observation.

Use volume/value-weighted concentration indices such as HHI rather than raw
broker counts. Raw `net_seller_count / net_buyer_count` is too noisy for IDX
because retail-heavy brokers can represent many small accounts and distort the
count. A positive transfer pattern is stronger when buy-side HHI is high and
sell-side HHI is lower or fragmented.

This should be evidence, not proof. Broker code does not perfectly identify
investor identity.

#### Foreign VWAP Distance

Estimate foreign cost basis:

```text
foreign_buy_vwap_20d =
  sum(foreign_buy_value) / sum(foreign_buy_volume)

distance_to_foreign_vwap =
  current_price / foreign_buy_vwap_20d - 1
```

Interpretation:

```text
-3% to +3%  near institutional cost basis
> +10%      late entry risk
below VWAP  possible opportunity or failed accumulation
```

Foreign VWAP distance is tactical context. It can support Trigger only when
price confirms through a reclaim/pivot. It must not independently dominate the
trigger score.

#### Domestic Bandar Flow

Domestic broker accumulation should be a parallel institutional-flow track, not
a fallback footnote under foreign flow.

Useful sub-signals:

```text
top3_or_top5_domestic_broker_net_buy_consistency
broker_reversal_signal
accumulation_session_ratio
domestic_buy_vwap_distance
broker_hhi_divergence
bandar_broad_score
bandar_accumulation_score
```

Definitions:

```text
top3_or_top5_domestic_broker_net_buy_consistency:
  same leading domestic brokers are net buyers over a configured 5d/10d/20d window

broker_reversal_signal:
  a broker or broker cluster that was consistently net selling flips to net buying

accumulation_session_ratio:
  sessions where top domestic brokers are net buyers / total valid sessions

domestic_buy_vwap_distance:
  current price vs estimated 20d domestic buy VWAP when value/volume data supports it

broker_hhi_divergence:
  buy-side HHI rises while sell-side HHI declines or remains fragmented

bandar_broad_score / bandar_accumulation_score:
  existing broad bandar accumulation evidence normalized into the domestic track
```

This track is especially important for `domestic_bandar` profiles where foreign
participation can be low or irrelevant. It starts under the same evidence status
registry rules as foreign flow: diagnostic or low-weight until OOS attribution
proves bucket-level predictive value.

Rules:

```text
foreign_institutional profile -> emphasize foreign_institutional_track
domestic_bandar profile       -> emphasize domestic_bandar_track
retail_speculative profile    -> keep both low-authority unless OOS proves value
missing foreign flow          -> does not mean institutional_flow is missing
```

Domestic broker accumulation supports ACCUMULATION state and Alpha. It can
support BREAKOUT_CONFIRMATION only when price/volume confirms. It must not
replace compression and price/pivot confirmation.

### 6. Ticker Profile Exposure

IDX tickers should not all use the same weights. BBCA, BBRI, TLKM, AMMN, BREN,
domestic second-liners, and illiquid third-liners have different driver
structures.

Use soft profile exposure, not a permanent hard bucket:

```json
{
  "profile": "FOREIGN_INSTITUTIONAL",
  "profile_confidence": 0.82,
  "exposures": {
    "foreign_institutional": 0.75,
    "domestic_bandar": 0.20,
    "retail_speculative": 0.05
  }
}
```

Inputs:

```text
median_turnover_20d
median_turnover_90d
market_cap
foreign_flow_share
foreign_net_buy_consistency
broker_concentration
top_broker_dominance
ATR / volatility
spread / liquidity
index membership
```

Initial profile policy:

```yaml
profiles:
  foreign_institutional:
    evidence_interpretation:
      foreign_flow_relevance: high
      broker_flow_relevance: confirmation_only
    max_decision: ENTER
    confidence_adjustment: neutral

  domestic_bandar:
    evidence_interpretation:
      foreign_flow_relevance: low
      broker_flow_relevance: high
    max_decision: ENTER
    confidence_adjustment: neutral

  retail_speculative:
    evidence_interpretation:
      foreign_flow_relevance: ignore_unless_participation_high
      broker_flow_relevance: medium_with_liquidity_cap
    max_decision: WATCH
    confidence_adjustment: cap_until_liquidity_confirmed
```

Operational confidence adjustments:

```yaml
confidence_adjustments:
  neutral:
    confidence_cap: 1.00

  cap_until_liquidity_confirmed:
    confidence_cap: 0.60
    release_when:
      median_turnover_20d_min: 5000000000
      valid_trading_days_20d_min: 15
      median_spread_pct_20d_max: 1.50
```

Do not introduce per-profile group weights initially. Profile should first
affect evidence interpretation, profile confidence, diagnostics, and max
decision. Only add profile-specific group weights after walk-forward data proves
enough sample volume per profile and enough OOS discriminative value.

Profile exposure should be epoch-based, not recalculated independently for every
signal date. The recommended default is monthly profile snapshots:

```text
ticker_profiles
- ticker
- profile_epoch_start
- profile_epoch_end
- primary_profile
- profile_confidence
- foreign_institutional_exposure
- domestic_bandar_exposure
- retail_speculative_exposure
- input_coverage
- schema_version
```

Daily signal calculations use the active profile snapshot for that date. The
classifier can be rerun monthly or quarterly, and backtests must read the stored
historical profile snapshot instead of recomputing with future data. This keeps
scores stable, auditable, and deterministic while still allowing profiles to
adapt over time.

Bootstrap rules for unclassified or sparse-history tickers:

```text
if median_turnover_20d and 20d broker/foreign data are available:
    classify from observed profile exposure
elif only liquidity data is available:
    default to domestic_bandar with low profile confidence
elif ticker is new, halted often, or has fewer than 15 valid trading days:
    profile = unclassified
    exposures = {domestic_bandar: 0.50, retail_speculative: 0.50}
    max_decision = WATCH until data coverage improves
```

The default should be conservative. A ticker with insufficient history must not
receive high-confidence foreign-institutional weights just because foreign data
is missing.

### 7. Alpha vs Trigger Split

The engine should separate structural attractiveness from entry timing.

Alpha answers:

```text
Is this ticker structurally attractive for the intended horizon?
```

Trigger answers:

```text
Is now a good entry window?
```

Recommended factor split:

```text
Alpha:
- sector-relative valuation
- earnings trend
- analyst revision
- insider / ownership quality
- sector tailwind
- durable institutional accumulation state for longer horizons

Trigger:
- `BREAKOUT_CONFIRMATION` setup phase state
- volume dry-up -> directional volume expansion for SWING_10D accumulation-style setups
- price pivot confirmation
- positive close confirmation
- squeeze release direction
- volume spike or dry-up reversal
- VWAP reclaim
- support/reclaim behavior
- foreign/broker flow acceleration only when price confirms
- foreign VWAP distance only as tactical context
- daily volume spike confirmation
- pre-open NCP direction / imbalance
```

Sub-signal routing must be explicit before Phase G implementation:

| Group | Alpha-routed evidence | Trigger-routed evidence |
|---|---|---|
| `setup_quality` | none by default; setup is timing/readiness evidence | continuous setup score, trend geometry, RSI quality, BB compression readiness, VWAP position, RS vs IHSG |
| `institutional_flow` | 20d/30d durable CNFB slope, domestic broker accumulation consistency, ACCUMULATION phase strength, accumulation persistence, buyer concentration stability, foreign participation regime | only price-confirmed 3d/5d flow acceleration during BREAKOUT_CONFIRMATION, broker streak acceleration with pivot confirmation, foreign/domestic VWAP reclaim context |
| `market_context` | sector regime, IHSG regime, liquidity regime, market-wide calendar overlays, sector-relative valuation context | NCP/pre-open confirmation, same-day gap direction, intraday liquidity/imbalance confirmation |
| `company_quality_context` | valuation percentile, earnings trend, analyst revision, insider/ownership quality, capped generic seasonality, configured ticker-specific event alpha | none by default; only event timing flags when explicitly configured |

`institutional_flow` and `market_context` may feed both Alpha and Trigger, but
no sub-signal may be routed to both unless the config explicitly marks it as
shared with a capped combined contribution. Evidence builders should emit route
metadata such as `route: alpha`, `route: trigger`, or `route: shared_capped`.

Trigger flow condition:

```yaml
price_confirmation:
  mode: any
  conditions:
    bullish_pivot_reclaim:
      close_above_prior_pivot_pct: 0.50
      daily_return_min_pct: 0.50
    positive_close_above_reference:
      reference: previous_close
      close_above_reference_pct: 0.50
    bullish_squeeze_release:
      bb_width_percentile_max_before_release: 0.20
      close_above_upper_band_or_range_high_pct: 0.30
      volume_ratio_min: 1.20
    vwap_reclaim:
      close_above_vwap_pct: 0.30
      intraday_or_daily_vwap_source_required: true
    support_reclaim_with_valid_volume:
      close_above_support_pct: 0.50
      volume_ratio_min: 1.20
      valid_volume_source: stockbit_or_idx
```

`price_confirmed = true` when the configured mode is satisfied using these
thresholds. Flow evidence cannot contribute to Trigger unless
`price_confirmed` is true for the same observation. Phase C may tune these
thresholds, but it must keep them explicit and validator-bounded.

These threshold values are initial placeholders, not final production constants.
Phase C must calibrate them by setup family and horizon, and every tunable price
confirmation threshold must be validator-bounded before production tuning.
In particular, `vwap_reclaim.close_above_vwap_pct: 0.30` is a placeholder only.
VWAP reclaim at 0.30% must not independently unlock flow Trigger contribution
in production. Production use likely needs confirmation with volume, pivot, or
support reclaim, calibrated by setup family/horizon and covered by validator
bounds.

Initial route fractions by horizon. Store only `alpha_fraction`; compute
`trigger_fraction = 1.0 - alpha_fraction` to avoid coupled-parameter validator
problems:

Naming clarification:

```text
alpha_fraction = per-group routing fraction into Alpha
alpha_weight   = final Alpha-vs-Trigger blend weight for the horizon
```

Do not use these interchangeably. `alpha_fraction` routes group contribution;
`alpha_weight` combines the already-computed Alpha and Trigger scores.

```yaml
route_fractions:
  TACTICAL_3D:
    setup_quality: {alpha_fraction: 0.00}
    institutional_flow: {alpha_fraction: 0.70}
    market_context: {alpha_fraction: 0.25}
    company_quality_context: {alpha_fraction: 1.00}

  SWING_10D:
    setup_quality: {alpha_fraction: 0.00}
    institutional_flow: {alpha_fraction: 0.80}
    market_context: {alpha_fraction: 0.60}
    company_quality_context: {alpha_fraction: 1.00}

  ACCUM_20D:
    setup_quality: {alpha_fraction: 0.10}
    institutional_flow: {alpha_fraction: 0.90}
    market_context: {alpha_fraction: 0.75}
    company_quality_context: {alpha_fraction: 1.00}
```

For each group, `trigger_fraction` is derived, not stored. Alpha and Trigger
scores are computed by routing weighted group contributions, then normalizing
each side by its routed total:

```text
alpha_score =
  sum(group_score * group_weight * alpha_fraction)
  / sum(group_weight * alpha_fraction)

trigger_score =
  sum(group_score * group_weight * (1 - alpha_fraction))
  / sum(group_weight * (1 - alpha_fraction))
```

This makes the Alpha/Trigger derivation computable while preserving the four
canonical group scores.

Flow's trigger-routed fraction is capped and conditional. It contributes only
when the same observation has price/volume confirmation such as pivot reclaim,
positive close, squeeze release, or VWAP reclaim. Without price confirmation,
flow remains Alpha/context evidence and cannot dominate Trigger.

Temporal routing rules:

```text
Alpha includes durable ACCUMULATION state.
Trigger requires BREAKOUT_CONFIRMATION state.
SWING_10D accumulation-style Trigger anchors on volume dry-up -> expansion.
Flow supports ACCUMULATION first.
Flow may support BREAKOUT_CONFIRMATION only when price/volume confirms.
BB compression is COMPRESSION/readiness state, not direct bullish trigger.
Price/volume pivot confirmation is BREAKOUT_CONFIRMATION.
```

Decision matrix:

```text
High Alpha + strong Trigger = ENTER
High Alpha + weak Trigger = WATCH
Low Alpha + strong Trigger = SPECULATIVE_ONLY or tactical WATCH
Low Alpha + weak Trigger = AVOID
```

This matrix is a conceptual explanation of the decision policy, not a second
mandatory gate. The mechanical decision is still driven by blended score,
coverage/conviction floors, hard gates, and regime/horizon thresholds. If a
future config adds explicit `min_alpha_score` or `min_trigger_score` gates,
those gates must be declared per horizon and tested so they do not conflict with
the blended-score threshold.

A 3-day tactical trade should not require the same Alpha quality as a 20-day
accumulation trade.

### 8. Sector Context

Sector context should be first-class for IDX.

Minimum useful evidence:

```text
sector_20d_return
sector_vs_ihsg_20d
sector_breadth
ticker_vs_sector_relative_strength
```

Sector regime alignment:

```text
bullish: sector outperforms IHSG and ticker outperforms sector
neutral: sector flat and breadth mixed
bearish: sector underperforms and breadth weak
```

This should feed Context and influence thresholds. It should not be hidden in a
generic post-score multiplier.

Initial data source should be computed from the local ticker universe rather
than blocked on a new sector-index provider:

```text
v1 sector return = equal-weight or liquidity-weighted return of local tickers
with the same sector classification
v1 sector breadth = percentage of same-sector tickers above selected moving
average / positive 20d return
fallback = unavailable if sector mapping or enough same-sector tickers are
missing
```

Official IDX sector indices can replace this later behind an infrastructure
provider, but Phase H should not depend on a new external data source.

### 9. Regime Detection Evidence

For IDX swing decisions, regime quality is upstream of stock scoring. A
mediocre setup in `RISK_ON` may outperform a strong setup in `RISK_OFF`, so
market regime must be a deterministic, replayable evidence model, not a hidden
context label or raw-score multiplier.

Recommended evidence object:

```text
RegimeDetectionEvidence
- ihsg_20d_return
- ihsg_trend_structure
- ihsg_breadth_pct_above_ma
- ihsg_volume_trend
- ihsg_atr_pct
- idx_foreign_flow_5d
- idx_foreign_flow_20d
- foreign_sell_streak_ihsg_weighted
- foreign_buy_streak_ihsg_weighted
- banking_sector_vs_ihsg
- sector_breadth
- regime_score
- regime: RISK_ON | NEUTRAL | RISK_OFF | VOLATILE | UNKNOWN
- regime_confidence
- regime_stability: STABLE | TRANSITIONING | UNKNOWN
- days_in_regime
- transition_warning
```

IDX-specific candidate hypothesis:

```text
market-wide foreign flow, especially consistent net selling/buying in
IHSG-heavy stocks, may lead regime transitions before IHSG price confirms
```

Candidate inputs:

```text
idx_foreign_flow_5d
idx_foreign_flow_20d
foreign_sell_streak_ihsg_weighted
foreign_buy_streak_ihsg_weighted
```

This hypothesis is diagnostic / low-authority until local walk-forward
attribution proves lead-time value. Do not state that foreign-flow streaks are
the best regime indicator until validated against local market-level labels.

Design boundary:

```text
RegimeModel computes market-wide regime evidence.
SignalEngine computes ticker/setup evidence.
DecisionPolicy combines SignalEngine output + RegimeModel constraints.
Regime must not be a hidden multiplier inside raw stock score.
```

Persistence:

```text
regime_observations:
- observation_date
- regime_score
- regime_label
- regime_confidence
- regime_stability
- regime_detection_inputs
- forward_ihsg_return_5d
- forward_ihsg_return_10d
- forward_ihsg_return_20d
- schema_version
```

Regime observations may also be embedded inside the signal observation
fingerprint, but the market-wide model should be replayable independently of
individual ticker trades.

### 10. Regime Threshold Policy

Market regime is an upstream evidence input and needs quality metadata because
it affects every ticker scored on the same date.

Recommended regime context:

```text
market_regime_context:
  regime: RISK_ON | NEUTRAL | RISK_OFF | VOLATILE | UNKNOWN
  regime_confidence: float
  regime_detection_method: string
  regime_last_changed: date | null
  days_in_current_regime: int | null
  regime_stability: STABLE | TRANSITIONING | UNKNOWN
```

Rules:

```text
TRANSITIONING regime -> cap max_decision or lower coverage_score
low regime_confidence -> cap max_decision or lower coverage_score
UNKNOWN regime -> no regime boost; conservative eligibility
```

Regime detection must be observable in saved observations and CLI output. It
should not be an invisible global modifier.

Use regime-conditioned thresholds:

```yaml
classification_thresholds:
  RISK_ON:
    enter: 68
    watch: 48
    confidence_cap: 1.00
    max_decision: ENTER
    regime_size_multiplier: 1.00

  NEUTRAL:
    enter: 72
    watch: 52
    confidence_cap: 0.90
    max_decision: ENTER
    regime_size_multiplier: 0.50

  RISK_OFF:
    enter_allowed: false
    watch: 60
    confidence_cap: 0.70
    max_decision: WATCH
    regime_size_multiplier: 0.25

  VOLATILE:
    enter_allowed: false
    watch: 65
    confidence_cap: 0.60
    max_decision: WATCH
    regime_size_multiplier: 0.00
```

Decision floors are separate from the regime confidence cap. The cap limits how
much regime quality can support eligibility; `min_coverage` and
`min_conviction` define the minimum evidence availability and directional
strength required for `ENTER`.

Initial decision-floor policy:

```yaml
decision_floors:
  TACTICAL_3D:
    RISK_ON: {min_coverage: 0.60, min_conviction: 0.62}
    NEUTRAL: {min_coverage: 0.65, min_conviction: 0.65}
    RISK_OFF: {min_coverage: 0.75, min_conviction: 0.75}
    VOLATILE: {min_coverage: 1.00, min_conviction: 1.00}  # ENTER disabled by regime

  SWING_10D:
    RISK_ON: {min_coverage: 0.65, min_conviction: 0.68}
    NEUTRAL: {min_coverage: 0.70, min_conviction: 0.70}
    RISK_OFF: {min_coverage: 0.80, min_conviction: 0.78}
    VOLATILE: {min_coverage: 1.00, min_conviction: 1.00}

  ACCUM_20D:
    RISK_ON: {min_coverage: 0.70, min_conviction: 0.68}
    NEUTRAL: {min_coverage: 0.75, min_conviction: 0.72}
    RISK_OFF: {min_coverage: 0.82, min_conviction: 0.78}
    VOLATILE: {min_coverage: 1.00, min_conviction: 1.00}
```

When `enter_allowed=false`, `min_coverage` and `min_conviction` are not `ENTER`
floors. They govern `WATCH` eligibility and diagnostic quality only. `ENTER`
remains disabled by `enter_allowed=false` regardless of floor values. Do not
rely on impossible floor values such as `1.00` to disable `ENTER`; the
authoritative block is `enter_allowed=false`.

This expresses the business rule clearly: in hostile markets, be more selective.
`RISK_OFF` intentionally disables `ENTER` in the initial policy. Earlier drafts
also made `ENTER` impossible through cap/floor interaction; this is now explicit
so calibration cannot accidentally enable RISK_OFF entries by raising a cap
alone.

Regime controls eligibility and sizing constraints, not raw scores. SignalEngine
should emit `max_decision`, `regime_size_multiplier`, and rationale. Actual
position sizing belongs in `TradeSetup` / sizing policy, which consumes these
constraints alongside capital, stop distance, liquidity, and risk limits.

### 11. Volatility-Adjusted Execution Policy

Static take-profit and stop-loss percentages should not be the long-term default
across a mixed IDX universe. Execution policy should be ATR-aware because BBCA,
coal cyclicals, second-liners, and speculative names have materially different
normal volatility.

Boundary:

```text
SignalEngine must not compute final stop price, target price, or position size.
SignalEngine may emit volatility context and sizing/execution constraints.
TradeSetup / sizing / backtest policy owns final stop, target, and position size.
```

Suggested emitted context:

```text
volatility_context:
  atr_20: float | null
  atr_pct: float | null
  volatility_bucket: LOW | NORMAL | HIGH | EXTREME | UNKNOWN
  stop_model_hint: ATR_MULTIPLE
  suggested_stop_atr: 2.0
  suggested_target_atr: 3.0
  volatility_size_multiplier: float
```

The example ATR multiples above are placeholders. Final stop/target multiples
belong to TradeSetup / backtest calibration and should be horizon-specific:

```yaml
atr_execution_hints:
  TACTICAL_3D:
    suggested_stop_atr: configurable
    suggested_target_atr: configurable

  SWING_10D:
    suggested_stop_atr: 2.0
    suggested_target_atr: 3.0

  ACCUM_20D:
    suggested_stop_atr: configurable
    suggested_target_atr: configurable
```

Sizing constraints combine conservatively:

```text
effective_size_multiplier = min(
  regime_size_multiplier,
  volatility_size_multiplier,
  liquidity_size_multiplier if present
)
```

SignalEngine may emit the constraint inputs and rationale, but TradeSetup /
backtest / sizing policy owns the final position size.

ATR-scaled exits must be validated per horizon and setup family through
walk-forward tests. Any ATR multipliers, volatility buckets, or size multipliers
must be configurable and registered in validator bounds in the same phase they
become tunable.

### 12. Setup-Specific Regime Compatibility

Generic regime thresholds are not enough. Each setup family should declare how
it behaves under each market regime because breakout, pullback, foreign-bounce,
and mean-reversion setups can have different regime sensitivity.

Initial policy shape:

```yaml
setup_regime_policy:
  foreign_bounce:
    RISK_ON: allowed
    NEUTRAL: restricted_or_watch_only
    RISK_OFF: allowed_if_flow_confirmation_strong  # ignored while regime ENTER disabled
    VOLATILE: enter_disabled

  breakout:
    RISK_ON: allowed
    NEUTRAL: allowed_if_volume_confirmation_strong
    RISK_OFF: restricted_or_watch_only
    VOLATILE: enter_disabled

  pullback:
    RISK_ON: allowed
    NEUTRAL: allowed
    RISK_OFF: allowed_if_risk_tight_and_flow_confirmed
    VOLATILE: restricted_or_watch_only

  mean_reversion:
    RISK_ON: restricted_or_watch_only
    NEUTRAL: allowed_if_support_confirmed
    RISK_OFF: restricted_or_watch_only
    VOLATILE: enter_disabled
```

Operational meanings:

```yaml
setup_regime_actions:
  allowed:
    max_decision: ENTER

  restricted_or_watch_only:
    max_decision: WATCH

  enter_disabled:
    max_decision: WATCH

  allowed_if_flow_confirmation_strong:
    max_decision: ENTER
    requires:
      flow_score_min: 75
      flow_conviction_min: 0.75
      institutional_accumulation_available: true

  allowed_if_volume_confirmation_strong:
    max_decision: ENTER
    requires:
      trigger_volume_score_min: 75
      valid_volume_source: stockbit_or_idx

  allowed_if_risk_tight_and_flow_confirmed:
    max_decision: ENTER
    requires:
      flow_score_min: 70
      max_atr_pct_override: 6.0
      risk_gates_open: true

  allowed_if_support_confirmed:
    max_decision: ENTER
    requires:
      support_distance_pct_max: 3.0
      max_adverse_setup_risk_pct: 4.0
```

Setup-specific policy modifies decision eligibility after evidence scoring. It
should not mutate raw evidence scores. If a setup is `restricted_or_watch_only`,
the decision can still surface a high score but cannot exceed `WATCH`.

Precedence rule:

```text
Regime-level enter_allowed=false always overrides setup-specific max_decision=ENTER.
No setup-specific policy may re-enable ENTER while regime-level ENTER is disabled.
Setup-specific policies may only tighten regime policy, not loosen it, unless a
future ADR explicitly allows exceptions.
```

For example, `foreign_bounce.RISK_OFF = allowed_if_flow_confirmation_strong`
cannot produce `ENTER` while the regime-level `RISK_OFF.enter_allowed` is
`false`; it can only explain why the setup remains a higher-quality `WATCH`.

### 13. Sector-Relative Valuation

Fixed P/E tiers are too generic for IDX. A P/E of 15 can be cheap for one ticker
and expensive for another depending on sector, quality, and growth.

Preferred hierarchy:

```text
1. sector-relative valuation percentile
2. IDX-relative valuation percentile
3. static P/E fallback
```

Coverage rule:

```text
if same-sector valuation peer coverage >= 80%:
    use sector-relative percentile
elif IDX-wide valuation coverage is sufficient:
    use IDX-relative percentile
else:
    use static P/E fallback with lower coverage/conviction
```

Peer coverage is measured against the active local universe/sector mapping for
the analysis date. The engine should not trigger network fetches from scoring
code just to complete a percentile; incomplete local coverage lowers coverage or
selects a fallback.

Valuation should contribute to Alpha and risk context, not short-term Trigger.

### 14. NCP Pre-Open As Execution Overlay

NCP/pre-open confirmation should not rewrite the daily signal score. It should
act as a same-day execution overlay:

```text
daily signal = ENTER candidate
NCP confirms = allow entry
NCP contradicts = WAIT_FOR_OPEN_CONFIRMATION or reduce size
NCP unavailable = no intraday boost
```

This keeps daily evidence replayable while still using one of the highest-signal
IDX timing windows.

### 15. Seasonality And Event Context

Do not collapse generic monthly seasonality, market-wide IDX calendar effects,
and ticker-specific events into one factor. They have different authority,
different data requirements, and different lookahead risks.

#### Generic Seasonality / Weak Prior

Generic seasonality remains a weak prior:

```text
examples:
- generic monthly win rate
- average month return
- broad January effect
```

Rules:

```text
minimum 5 usable years
missing or insufficient sample = unavailable
low-weight / capped contribution
does not directly create ENTER
```

Generic seasonality belongs in `company_quality_context` or weak-prior evidence.
It is not a trigger and should not be confused with event alpha.

#### Market-Wide Calendar Regime Modifiers

Market-wide calendar effects affect `market_context`, liquidity, and execution.
They should not be treated as ticker Alpha by default.

Examples:

```text
LEBARAN_LIQUIDITY_DRAIN
YEAR_END_DECEMBER_WINDOW_DRESSING_REGIME
EARNINGS_SEASON_VOLATILITY_REGIME
```

Possible effects:

```text
regime confidence
max_decision
regime_size_multiplier / effective_size_multiplier
liquidity thresholds
slippage assumptions
```

Avoid declaring these events as automatic `RISK_OFF` without validation. Model
them as liquidity/regime overlays that may cap decision or reduce size when
coverage and attribution support that behavior.

#### Ticker-Specific Event Alpha / Event Context

Ticker-specific event evidence is not generic seasonality. It must define active
windows, affected tickers, data source, announcement date, effective date, and
no-lookahead behavior.

Examples:

```text
MSCI / FTSE inclusion or deletion
high-dividend pre-ex-date window
major corporate action windows
```

Suggested config shape:

```yaml
event_context:
  msci_inclusion:
    active_window:
      start: effective_date_minus_trading_days_5
      end: effective_date
    scope: ticker_specific
    authority: diagnostic_until_validated

  dividend_chase:
    active_window:
      start: ex_date_minus_trading_days_10
      end: ex_date_minus_trading_days_2
    requires:
      dividend_yield_min: configurable
      ticker_dividend_history_available: true

  lebaran_liquidity_drain:
    scope: market_wide
    effect:
      liquidity_threshold_multiplier: configurable
      size_multiplier_cap: configurable
      max_decision_cap: configurable
```

Rules:

```text
event effects must avoid lookahead bias in backtests
event data source and announcement/effective dates must be persisted
strong event authority requires walk-forward validation and enough occurrences
MSCI/FTSE inclusion can be high-impact only when event data is reliable
dividend chase can be setup-dependent and regime-dependent, not guaranteed alpha
generic seasonality remains capped separately
```

Routing:

```text
generic seasonality      -> company_quality_context / weak priors
market-wide calendar     -> market_context / liquidity / execution overlay
ticker-specific events   -> event_context / event_alpha, routed into
                            company_quality_context only when configured
```

## Recommended Group Model

Use four top-level evidence groups as the only numeric evidence layer. Alpha and
Trigger are derived component views from those group scores. The final score is
then a horizon-specific blend of Alpha and Trigger.

Composition:

```text
group_scores = setup_quality, institutional_flow, market_context, company_quality_context

alpha_score =
  normalized weighted blend of group contributions routed to Alpha

trigger_score =
  normalized weighted blend of group contributions routed to Trigger

final_score =
  horizon_alpha_weight * alpha_score
  + (1 - horizon_alpha_weight) * trigger_score
```

This means the four groups drive all numeric scoring. Alpha/Trigger do not add a
second independent factor tree; they are decision-facing projections of the same
evidence.

```yaml
groups:
  setup_quality:
    weight: 0.35

  institutional_flow:
    weight: 0.30

  market_context:
    weight: 0.25

  company_quality_context:
    weight: 0.10
```

RiskEngine boundary:

```text
RiskEngine remains the only hard gate authority.
SignalEngine company_quality_context may lower conviction, affect score, add
warnings, or cap max decision, but it must not emit BLOCKED or duplicate
RiskEngine gates.
```

`company_quality_context` represents company quality and contextual conviction
only: valuation stretch, earnings trend, analyst revision, insider activity,
ownership quality, capped generic seasonality, and configured ticker-specific
event alpha. Market-wide calendar overlays belong in `market_context`, not
ticker Alpha. It must not contain liquidity gate, free-float gate, Piotroski
blocking gate, bandar distribution block, or technical gate logic. Those remain
RiskEngine responsibilities.

For `SWING_10D`:

```yaml
SWING_10D:
  hard_gates:
    min_median_turnover_20d: 5000000000
    min_price: 50
    max_atr_pct: 7.5
    require_valid_volume: true

  alpha_trigger_blend:
    alpha_weight: 0.40

  groups:
    setup_quality:
      weight: 0.35
    institutional_flow:
      weight: 0.30
    market_context:
      weight: 0.25
    company_quality_context:
      weight: 0.10
```

For `ACCUM_20D`:

```yaml
ACCUM_20D:
  hard_gates:
    min_median_turnover_20d: 7500000000
    min_price: 50
    max_atr_pct: 8.0
    require_valid_volume: true

  alpha_trigger_blend:
    alpha_weight: 0.50

  groups:
    setup_quality:
      weight: 0.25
    institutional_flow:
      weight: 0.40
    market_context:
      weight: 0.20
    company_quality_context:
      weight: 0.15
```

For `TACTICAL_3D`:

```yaml
TACTICAL_3D:
  hard_gates:
    min_median_turnover_20d: 3000000000
    min_price: 50
    max_atr_pct: 10.0
    require_valid_volume: true

  alpha_trigger_blend:
    alpha_weight: 0.20

  groups:
    setup_quality:
      weight: 0.45
    institutional_flow:
      weight: 0.30
    market_context:
      weight: 0.20
    company_quality_context:
      weight: 0.05
```

Hard gates are horizon-specific. They should not be copied blindly between
profiles because a tactical trade, swing trade, and 20-day accumulation trade
have different liquidity and volatility tolerance.

## Setup Family Source Contract

`setup_family` must be known before setup-specific regime policy is applied.
Do not infer it silently from ticker identity.

Source priority:

```text
1. Workflow/request declares setup family when available
   Example: --setup foreign-bounce
2. Strategy matches may propose setup families.
3. If multiple setup families match, persist all matches and choose
   primary_setup_family by deterministic priority.
4. If no family is known, use UNKNOWN and apply conservative policy.
```

Suggested deterministic priority can be configured, but it must be explicit:

```yaml
setup_family_priority:
  - foreign_bounce
  - accumulation
  - breakout
  - pullback
  - mean_reversion
```

Every saved observation should persist `matched_setup_families` and
`setup_family` / `primary_setup_family` so later attribution can explain which
policy was applied.

## Persisted Sub-Signal Fingerprints

Every saved signal or candidate observation must store raw sub-signal values as
they were at signal time. Attribution should not depend on recomputing
historical evidence later because replay can drift, provider data can change,
and local history can be incomplete.

Suggested fingerprint fields:

```text
sub_signal_fingerprint:
  setup_family
  setup_phase_current
  setup_phase_previous
  phase_sequence_valid
  rsi_at_signal
  bb_width_pctile_at_signal
  vwap_position_at_signal
  rs_vs_ihsg_20d_at_signal
  volume_ratio_at_signal
  cnfb_20d_at_signal
  foreign_participation_at_signal
  foreign_concentration_at_signal
  domestic_broker_accumulation_at_signal
  market_regime_at_signal
  regime_confidence_at_signal
  regime_stability_at_signal
  coverage_score
  conviction_score
```

The fingerprint is not a display artifact. It is the calibration and audit
record used by forward labels, attribution views, and future tuning patches.

Phase state and phase history must also be persisted at observation time:

```text
phase_history:
- phase
- phase_started_at
- phase_ended_at | null
- phase_age_sessions
- phase_strength
- phase_reasons
- sequence_valid_after_transition
```

Tuning attribution must be able to slice outcomes by current phase, previous
phase, phase age, and `phase_sequence_valid`. A foreign-bounce patch should not
be accepted if the apparent edge comes from generic breakout confirmations that
never had prior accumulation/compression.

## Output Contract

The final signal output should make score, coverage, conviction, context, and
decision explicit:

```json
{
  "ticker": "BBCA",
  "profile": "FOREIGN_INSTITUTIONAL",
  "profile_confidence": 0.82,
  "horizon": "SWING_10D",
  "setup_family": "foreign_bounce",
  "matched_setup_families": [
    "foreign_bounce",
    "accumulation"
  ],
  "setup_phase": {
    "current_phase": "BREAKOUT_CONFIRMATION",
    "phase_started_at": "2026-07-03",
    "phase_age_sessions": 2,
    "previous_phase": "COMPRESSION",
    "phase_sequence_valid": true,
    "accumulation_strength": 0.78,
    "compression_strength": 0.81,
    "breakout_strength": 0.74,
    "distribution_risk": 0.18,
    "phase_confidence": 0.76,
    "phase_reasons": [
      "Prior accumulation observed over 20 sessions",
      "Compression held above support",
      "Positive close reclaimed range high with valid volume"
    ]
  },
  "alpha_score": 71,
  "trigger_score": 78,
  "score": 75.2,
  "coverage_score": 0.76,
  "conviction_score": 0.82,
  "market_regime_context": {
    "regime": "NEUTRAL",
    "regime_confidence": 0.78,
    "regime_detection_method": "ihsg_trend_volatility_v1",
    "regime_last_changed": "2026-06-24",
    "days_in_current_regime": 8,
    "regime_stability": "STABLE"
  },
  "sector_regime": "BULLISH",
  "decision": "ENTER",
  "decision_constraints": {
    "max_decision": "ENTER",
    "regime_size_multiplier": 0.50,
    "volatility_size_multiplier": 0.75,
    "liquidity_size_multiplier": null,
    "effective_size_multiplier": 0.50,
    "constraint_reasons": [
      "NEUTRAL regime"
    ]
  },
  "evidence_statuses": {
    "relative_strength_vs_ihsg": "PRODUCTION",
    "foreign_institutional_track": "LOW_WEIGHT",
    "domestic_bandar_track": "DIAGNOSTIC",
    "sector_context": "LOW_WEIGHT"
  },
  "volatility_context": {
    "atr_20": 82.5,
    "atr_pct": 2.4,
    "volatility_bucket": "NORMAL",
    "stop_model_hint": "ATR_MULTIPLE",
    "suggested_stop_atr": 2.0,
    "suggested_target_atr": 3.0,
    "volatility_size_multiplier": 0.75
  },
  "relative_strength_context": {
    "rs_vs_ihsg_20d": 0.042,
    "rs_bucket": "LEADER",
    "rs_confidence": 0.88,
    "ihsg_window_complete": true
  },
  "sub_signal_fingerprint": {
    "setup_family": "foreign_bounce",
    "setup_phase_current": "BREAKOUT_CONFIRMATION",
    "setup_phase_previous": "COMPRESSION",
    "phase_sequence_valid": true,
    "rsi_at_signal": 58.4,
    "bb_width_pctile_at_signal": 0.18,
    "vwap_position_at_signal": 0.012,
    "rs_vs_ihsg_20d_at_signal": 0.042,
    "volume_ratio_at_signal": 1.34,
    "cnfb_20d_at_signal": 125000000000,
    "foreign_participation_at_signal": 0.34,
    "foreign_concentration_at_signal": 0.62,
    "domestic_broker_accumulation_at_signal": 0.41,
    "market_regime_at_signal": "NEUTRAL",
    "regime_confidence_at_signal": 0.78,
    "regime_stability_at_signal": "STABLE",
    "coverage_score": 0.76,
    "conviction_score": 0.82
  },
  "main_reasons": [
    "Foreign participation meaningful",
    "CNFB rising while price remains compressed",
    "Trend structure confirmed",
    "Sector outperforming IHSG"
  ],
  "risk_reasons": [
    "Entry price 4.8% above 20d foreign VWAP"
  ]
}
```

For the example above, `SWING_10D` uses:

```text
score = alpha_weight * alpha_score + (1 - alpha_weight) * trigger_score
score = 0.40 * 71 + 0.60 * 78 = 75.2
```

The exact persisted value should be stored before display rounding.

Current runtime objects may still validate `SignalAssessment.score` as an
integer. Persisting the pre-rounding float is therefore a planned contract
change, not an incidental implementation detail. Phase G must either:

```text
Option A: change `SignalAssessment.score` to a float and update callers/tests
Option B: keep `score` as display int and add `raw_score` / `score_exact` float
```

The recommendation is Option B for migration safety unless a full score-type
audit is completed first.

Decision policy should remain explicit:

```text
if hard_gate_failed:
    AVOID
elif coverage_score < min_coverage:
    INSUFFICIENT_DATA or WATCH
elif conviction_score < min_conviction:
    WATCH or AVOID
elif setup_phase.current_phase in [DISTRIBUTION, FAILED, EXHAUSTION]:
    WATCH or AVOID depending severity
elif regime blocks ENTER:
    WATCH
elif setup_family in [accumulation, foreign_bounce]
     and setup_phase.current_phase != BREAKOUT_CONFIRMATION:
    WATCH
elif setup_family in [accumulation, foreign_bounce]
     and setup_phase.phase_sequence_valid is false:
    WATCH or route to a different setup family
elif score >= enter_threshold
     and coverage_score >= min_coverage
     and conviction_score >= min_conviction:
    ENTER
elif score >= watch_threshold:
    WATCH
else:
    AVOID
```

## Implementation Phases

### Phase A1: Regime Eligibility Policy Quick Win

Goal: reduce false positives immediately before changing signal math or adding
new regime persistence infrastructure.

Work:

- Add config-driven regime thresholds, coverage/conviction floors, max
  decisions, and size multipliers.
- Add `enter_allowed`.
- Add setup-specific regime compatibility policy.
- Define `setup_family` source priority and deterministic primary-family
  selection before applying setup-specific regime policy.
- Preserve raw score comparability across regimes.
- Ensure regime changes affect eligibility/sizing constraints, not raw evidence
  scores.
- Emit decision constraints.
- No new regime persistence table is required in A1.
- Add tests for RISK_ON, NEUTRAL, RISK_OFF, and VOLATILE decisions.

Why first: A1 gives immediate false-positive reduction.

### Phase A2: Full RegimeDetectionEvidence And Replay

Goal: build replayable market-regime infrastructure after the quick eligibility
policy is explicit.

Work:

- Add deterministic `RegimeModel` / `RegimeDetectionEvidence` as an upstream
  market-wide model.
- Persist replayable regime observations and detection inputs.
- Persist `regime_confidence`, `regime_stability`, and `days_in_regime`.
- Emit market regime context with confidence, detection method, last-change
  date, days in regime, and stability.
- Keep regime out of raw stock score; DecisionPolicy combines regime
  constraints with ticker/setup evidence.
- Persist `idx_foreign_flow_5d`.
- Persist `idx_foreign_flow_20d`.
- Persist foreign buy/sell streaks for IHSG-weighted names.
- Include IDX-level foreign-flow inputs in regime observation fingerprints.
- Persist regime forward labels.
- Validate IDX-level foreign-flow transition evidence with market-level forward
  labels before making it high-authority.

Why second: A2 builds replayable regime infrastructure without blocking the A1
false-positive reduction.

### Phase B: Minimal Forward Labels

Goal: create replayable outcome labels before deeper architecture work.

Work:

- Persist deterministic `signal_forward_labels` records.
- Persist deterministic market-level regime labels when validating regime
  quality, including forward IHSG return over 5d/10d/20d.
- Start calibration with `SWING_10D` as the first calibrated horizon.
- Keep `TACTICAL_3D` and `ACCUM_20D` diagnostic or temporarily sharing
  `SWING_10D` defaults until `SWING_10D` reaches patch-eligible empirical
  readiness.
- Implement `SUCCESS`, `FAILURE`, `NEUTRAL`, and `UNAVAILABLE` outcomes.
- Store continuous labels: close return, max forward return, max adverse
  excursion, days to peak/trough, stop/target triggers.
- Keep labels local-first and independent of AI.
- Mark incomplete candle windows as `UNAVAILABLE` with a reason.
- Persist sub-signal fingerprints at observation time so later attribution does
  not depend on recomputed historical evidence.

Why second: without labels, improvements are judged by intuition instead of
walk-forward evidence.

### Phase C: SetupPhaseState And Continuous Setup/Trigger Scoring

Goal: detect temporal setup phase first, then replace coarse setup labels with
continuous price/volume pivot evidence.

Work:

- Add `SetupPhaseState` detection for `NONE`, `ACCUMULATION`, `COMPRESSION`,
  `BREAKOUT_CONFIRMATION`, `EXHAUSTION`, `DISTRIBUTION`, and `FAILED`.
- For accumulation/foreign-bounce, enforce the sequence:
  ACCUMULATION -> COMPRESSION -> BREAKOUT_CONFIRMATION before `ENTER`.
- Persist phase state, phase history, phase sequence validity, and phase
  strength in observations.
- Add continuous setup sub-signal scoring.
- Emit separate `coverage_score` and `conviction_score`.
- Include RS vs IHSG as a core `setup_quality` input for swing, trend,
  breakout, accumulation, and foreign-bounce setups.
- Add setup-family configurable RS thresholds, including max-decision caps for
  negative RS and hard-exclude rules when applicable.
- Treat negative RS while IHSG is rising as possible rotation-out/distribution
  evidence for accumulation and breakout setup families.
- Keep existing labels and failed gates for explanation.
- Add BB compression as COMPRESSION/readiness state, not bullish evidence.
- Exclude volume confirmation from setup scoring; route volume spike/dry-up,
  positive close, VWAP reclaim, support reclaim, and squeeze release to
  BREAKOUT_CONFIRMATION / Trigger.
- Add `volume_dry_up_then_expansion` as the primary trigger pattern for
  `SWING_10D` accumulation, foreign-bounce, and breakout setup families.
- Enforce volume-trigger data quality: valid volume source, enough valid
  sessions for the 20d average, and no suspended/missing/zero-volume distortion.
- Add tests proving one failed gate does not equal all gates failed.

Why third: after labels exist, price/volume pivot evidence can be checked for
actual OOS discrimination.

### Phase D: Strategy Evidence Harness

Goal: reuse existing deterministic strategy packages as setup-family evidence
and empirical validation tools without creating a parallel decision engine.

Phase D evidence is diagnostic-only. It is persisted and reported, but it is not
wired into group scores until Phase G explicitly consumes it through
Alpha/Trigger aggregation.

Work:

- Add `StrategyEvidenceBuilder` in the application layer.
- Evaluate validated strategy YAMLs through `IndicatorRegistry`.
- Map matched strategy rules to setup-family and setup-phase evidence with
  coverage/conviction metadata, freshness, route metadata, and rationale.
- Persist matched strategy name, matched rule, and outcome in replay
  observations.
- Forbid strategy matches from overriding canonical `SetupPhaseState`
  transition rules.
- Use strategy backtests for empirical readiness checks before assigning
  production weight.
- Forbid strategy outcomes from directly overriding canonical SignalEngine
  decisions.

### Phase E: Institutional Accumulation Evidence

Goal: make IDX flow empirical, but keep it low-authority until proven.

Work:

- Add foreign participation ratio.
- Add foreign CR4/CR8 concentration.
- Add CNFB-vs-price divergence.
- Add counterparty transfer metrics if broker-side data supports it.
- Add foreign VWAP distance.
- Add domestic bandar flow as a parallel track: domestic broker accumulation,
  top3/top5 broker net-buy consistency, broker reversal, accumulation-session
  ratio, broker HHI divergence, bandar broad/accumulation score, and domestic
  VWAP/cost-basis proxy when available.
- Use asymmetric windows: 20d/30d for bullish accumulation Alpha and 3d/5d/7d
  for bearish distribution/risk.
- Enforce minimum valid trading-session coverage before CNFB/VWAP metrics are
  considered available.
- Persist all raw metrics in replay observations.
- Keep flow diagnostic, binary, low-weight, or coverage/conviction-only until
  Phase I attribution proves bucket-level predictive value.
- Enforce the evidence status registry so DIAGNOSTIC flow is report-only and
  LOW_WEIGHT flow cannot exceed its configured cap.

### Phase F: Minimal Ticker Profile Diagnostics

Goal: classify ticker behavior without introducing tunable explosion.

Work:

- Add deterministic profile classifier as an application service.
- Start with local liquidity, broker, foreign-flow, volatility, and index
  membership data only.
- Output soft exposures and profile confidence.
- Persist profile snapshots by epoch, with monthly default cadence.
- Backtests must read historical profile snapshots for the signal date and must
  not recompute profiles using future data.
- Define conservative fallback for sparse-history tickers.
- Use profiles for evidence interpretation, profile confidence, diagnostics,
  and max decision only. Do not add per-profile group weights yet.
- Treat profile as diagnostic/max-decision context first; do not add separate
  per-horizon or per-profile tunables before `SWING_10D` is
  patch-eligible.

### Phase G: Simplified Alpha/Trigger Split

Goal: separate structural attractiveness from entry timing without adding a
large new tunable surface.

Work:

- Add Alpha and Trigger component scores.
- Derive Alpha and Trigger from the four group scores; do not introduce a second
  independent factor tree.
- Keep flow primarily Alpha/context. Permit trigger contribution only when price
  confirms.
- Add volatility context emission if not already present: ATR, ATR%, volatility
  bucket, ATR stop/target hints, and size constraint multiplier. Final
  stop/target/position size remains owned by TradeSetup/sizing/backtest policy.
- Decide and implement the score precision contract: either migrate
  `SignalAssessment.score` to float or add a separate raw/exact score field while
  preserving display int behavior.
- Register every new tunable config path in validator bounds in the same phase.
- Apply `EvidenceRegistration` status caps during aggregation.

### Phase H: Sector Context

Goal: make IDX sector rotation part of signal interpretation.

Work:

- Add sector-relative return and breadth metrics.
- Add ticker-vs-sector relative strength.
- Use local universe-derived sector metrics first; official IDX sector-index
  providers are optional later infrastructure.
- Feed sector context into Context evidence and regime thresholds.

### Phase I: Full Walk-Forward Calibration And Expanded Tunables

Goal: tune weights and thresholds only from replayable saved observations.

Work:

- Use persisted observations and forward labels.
- Do not introduce separate `TACTICAL_3D` or `ACCUM_20D` tuning surfaces until
  `SWING_10D` clears patch-eligible empirical readiness.
- Enforce in-sample/out-of-sample split.
- Quantize weight changes.
- Cap per-cycle shifts.
- Register all tunable config paths in validator bounds before use.
- Include validator bounds for ATR multipliers, volatility buckets, size
  multipliers, and RS-vs-IHSG thresholds before those settings become
  production tunables.
- Update `SwingTuningPatchValidator` from diagnostic floors to target
  patch-eligible floors where current validator behavior is weaker.
- Add validator support for separate diagnostic-ready and patch-eligible states.
- Record before/after artifacts.
- Do not allow AI or CLI output to mutate config directly.

Diagnostic-ready vs patch-eligible:

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

A finding can be diagnostic-ready with a small OOS sample, but it is not
patch-eligible until the stricter sample and attribution gates pass. If current
validator behavior is less strict, the stricter gates above are target-state
requirements and must not be claimed as implemented.

Single-regime dependency is rejected when more than 70% of OOS profit comes from
one regime, or when fewer than two regimes have positive OOS contribution with
at least five trades each. This prevents a patch from passing because it only
worked in one hidden market condition.

Exception: a setup may be single-regime scoped only when that scope is declared
upfront in config. Otherwise, hidden single-regime dependency fails patch
eligibility.

```yaml
setup_scope:
  foreign_bounce:
    allowed_regimes: [RISK_ON, NEUTRAL]
    single_regime_scoped: false
```

A config change is not accepted just because in-sample performance improves. It
must clear OOS gates, preserve or improve drawdown behavior, and pass attribution
checks showing the improvement is not hidden inside one market regime, one setup
family, one liquidity bucket, or one coverage/conviction bucket.

Forward labels must be persisted as deterministic outcome records, not inferred
ad hoc during calibration.

Suggested label schema:

```text
signal_forward_labels
- ticker
- signal_date
- horizon
- entry_reference_price
- label_window_start
- label_window_end
- close_return
- max_forward_return
- max_adverse_excursion
- days_to_peak
- days_to_trough
- stop_would_trigger
- target_would_trigger
- outcome_label: SUCCESS | FAILURE | NEUTRAL | UNAVAILABLE
- unavailable_reason
- schema_version
```

Regime-quality labels are separate market-level records:

```text
regime_forward_labels
- observation_date
- regime_label
- regime_score
- regime_confidence
- regime_stability
- forward_ihsg_return_5d
- forward_ihsg_return_10d
- forward_ihsg_return_20d
- forward_ihsg_max_adverse_return_20d
- realized_volatility_20d
- schema_version
```

Use regime labels to validate whether regime transitions, confidence, and
stability predict market-level forward behavior. Do not judge regime changes
only from ticker trade outcomes.

Initial policy thresholds:

| Horizon | Success condition | Failure condition | Neutral condition |
|---|---|---|---|
| `TACTICAL_3D` | `max_forward_return_3d >= 2.0%` and `max_adverse_excursion_3d > -2.5%` | `max_adverse_excursion_3d <= -2.5%` before target, or `close_return_3d <= -1.0%` | neither success nor failure |
| `SWING_10D` | `max_forward_return_10d >= 4.0%` and `max_adverse_excursion_10d > -4.0%` | `max_adverse_excursion_10d <= -4.0%` before target, or `close_return_10d <= -2.0%` | neither success nor failure |
| `ACCUM_20D` | `close_return_20d >= 5.0%` and `max_adverse_excursion_20d > -6.0%` | `max_adverse_excursion_20d <= -6.0%`, or `close_return_20d <= -3.0%` | neither success nor failure |

If there are not enough valid candles to complete the label window, store
`outcome_label = UNAVAILABLE` with an explicit reason. Calibration should
optimize continuous outcomes first and use `SUCCESS` / `FAILURE` / `NEUTRAL`
labels as stratified summary views.

Required attribution views before accepting a tuning change:

```text
by setup family
by market regime
by coverage bucket
by conviction bucket
by liquidity bucket
by ticker profile
by sector
```

## Layer Plan For Future Implementation

This document does not implement code, but future work should follow this layer
placement.

```text
Domain:
- immutable evidence value objects
- `RegimeDetectionEvidence` value objects
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
```

## Acceptance Criteria For Future Work

Any implementation based on this recommendation should satisfy:

- One canonical production signal path.
- Architecture remains general and composable, but production calibration is
  pattern-specific to avoid exploding the tuning surface.
- Initial production calibration targets
  `foreign_institutional_accumulation_large_cap_SWING_10D`; domestic bandar
  accumulation is a separate rollout track with separate calibration.
- Any production-calibrated setup declares target universe, profile, horizon,
  setup family, primary flow track, required phase sequence, regime scope, and
  patch eligibility gates.
- A setup cannot borrow thresholds from another pattern unless validated by OOS
  attribution.
- Strategy packages, plugins, and formulas may produce evidence, but may not
  directly override canonical SignalEngine decisions.
- Works fully without AI.
- Deterministic for the same local data and config.
- SignalEngine emits `coverage_score` and `conviction_score`; missing evidence
  lowers coverage, while weak or mixed evidence lowers conviction.
- High-conviction / low-coverage setups cannot become `ENTER` by conviction
  alone; high-coverage / low-conviction setups remain weak `WATCH` or `AVOID`.
- SignalEngine emits `SetupPhaseState` and phase history for accumulation /
  foreign-bounce setups.
- For accumulation / foreign-bounce, `ENTER` is valid only in
  `BREAKOUT_CONFIRMATION` after prior `ACCUMULATION` and `COMPRESSION` were
  observed in sequence.
- Setup-family phase requirements are config-driven and persisted in
  observations. Breakout requires `COMPRESSION -> BREAKOUT_CONFIRMATION`,
  pullback requires trend/context support plus support reclaim or pivot
  confirmation, and mean reversion requires support/reversal evidence with
  explicit risk controls.
- For `SWING_10D` accumulation, foreign-bounce, and breakout setups, the primary
  trigger pattern is volume dry-up followed by directional volume expansion.
- Secondary triggers such as VWAP reclaim, support reclaim, squeeze release,
  positive close, and broker/foreign acceleration may confirm or supplement the
  primary trigger, but cannot replace it unless setup config explicitly allows.
- Volume-trigger evidence requires a valid volume source, enough valid sessions
  for the 20d average, and no suspended/missing/zero-volume distortion; otherwise
  the trigger is unavailable and coverage is lowered.
- `ACCUMULATION` alone is candidate tracking; `COMPRESSION` alone is trigger
  pending; `BREAKOUT_CONFIRMATION` without valid prior phases is a different
  setup family, not foreign-bounce `ENTER`.
- `DISTRIBUTION`, `EXHAUSTION`, or `FAILED` phases cap max decision or force
  `WATCH` / `AVOID` depending severity.
- Regime thresholds are config-driven.
- Regime detection is a deterministic, replayable `RegimeDetectionEvidence`
  model upstream of ticker/setup scoring.
- `RegimeModel` computes market-wide regime evidence; SignalEngine computes
  ticker/setup evidence; DecisionPolicy combines both into decision constraints.
- Regime is not a hidden multiplier inside raw stock score.
- Regime observations persist observation date, regime score/label/confidence,
  stability, detection inputs, and market-level forward labels when used for
  validation.
- `RISK_OFF` and `VOLATILE` initial policies explicitly disable `ENTER`; this
  cannot be inferred only from cap/floor math.
- When `enter_allowed=false`, coverage/conviction floors are only WATCH /
  diagnostic-quality floors and cannot permit `ENTER`.
- Regime-level `enter_allowed=false` overrides any setup-specific
  `max_decision=ENTER`; setup-specific policy can tighten regime policy, not
  loosen it, unless a future ADR explicitly allows exceptions.
- Market regime context includes regime confidence, detection method,
  last-change date, days in regime, and stability.
- TRANSITIONING or low-confidence regimes cap max decision or reduce coverage.
- Market-wide foreign-flow transition indicators are diagnostic/low-authority
  until local walk-forward attribution proves lead-time value.
- Regime improvements must be validated with market-level forward labels, not
  only ticker trade outcomes.
- SignalEngine output includes decision constraints (`max_decision`,
  `regime_size_multiplier`, `volatility_size_multiplier`, optional
  `liquidity_size_multiplier`, `effective_size_multiplier`, and reasons) for
  TradeSetup/sizing policy to consume.
- SignalEngine emits volatility context and ATR-based execution hints only;
  TradeSetup/sizing/backtest policy owns final stop price, target price, and
  position size.
- Setup-specific regime compatibility is explicit and affects eligibility, not
  raw evidence scores.
- `setup_family` source priority is explicit; matched setup families and the
  deterministic primary setup family are persisted.
- Default setup-family priority must not let mean reversion shadow true
  accumulation matches; accumulation is prioritized above mean reversion unless
  profile-specific config states otherwise.
- Setup-specific regime labels have operational numeric requirements.
- Coverage and conviction floors are defined per horizon and regime, separate
  from regime confidence metadata.
- Profile diagnostics are observable in replay payloads.
- Profile exposure is epoch-based and persisted; daily scoring does not
  recalculate profile weights ad hoc.
- Profile does not introduce per-profile group weights initially; it affects
  evidence interpretation, diagnostics, and max decision first.
- Profile confidence adjustments have numeric confidence caps and release
  conditions.
- Flow metrics are persisted with raw values, normalized scores, and authority
  labels. Flow starts diagnostic/binary/low-weight until OOS attribution proves
  bucket-level predictive value.
- Institutional flow has two first-class tracks: `foreign_institutional_track`
  and `domestic_bandar_track`. Missing foreign flow does not imply missing
  institutional flow when domestic broker evidence exists.
- Domestic broker accumulation evidence includes top3/top5 net-buy consistency,
  broker reversal, accumulation-session ratio, domestic buy VWAP distance,
  broker HHI divergence, and bandar broad/accumulation scores.
- Domestic broker accumulation supports ACCUMULATION / Alpha and may support
  BREAKOUT_CONFIRMATION only with price/volume confirmation; it must not
  directly create `ENTER`.
- Broker codes are evidence, not proof of actual owner identity; broker-derived
  signals require explicit coverage and conviction metadata.
- Evidence status registry is enforced by the scoring engine:
  `DIAGNOSTIC` is report-only, `LOW_WEIGHT` is capped, and `PRODUCTION` may use
  normal configured weight.
- `EvidenceRegistration` is declared in YAML/config, loaded by the application
  aggregation service, promoted only by manual config change after
  validator-approved OOS evidence, and never automatically promoted from tuning
  output.
- Validator rejects tuning patches that exceed evidence status caps.
- Component weight groups must sum to `1.00`; config validation rejects
  underweight or overweight component groups.
- Raw net-buy intensity never directly creates `ENTER`.
- Trigger is dominated by price/volume pivot confirmation; foreign/broker flow
  supports Trigger only when price confirms.
- Relative strength vs IHSG is core `setup_quality` evidence for trend,
  swing, breakout, accumulation, and foreign-bounce setups.
- Negative RS vs IHSG caps max decision or heavily penalizes setup quality for
  trend/accumulation/foreign-bounce setups unless setup-family config explicitly
  permits an exception.
- RS policy is setup-family configurable and validator-bounded, including
  `rs_20d_lag_warning`, `rs_20d_hard_exclude`, warning actions, and
  mean-reversion exception requirements.
- Negative RS cannot be silently overwhelmed by other bullish setup components
  for breakout, accumulation, or foreign-bounce setups.
- The RS lag-warning band for every non-mean-reversion setup has an explicit
  `warning_action`; no threshold band is left undefined.
- `rs_20d_hard_exclude` means `setup_eligible = false` and
  `max_decision = AVOID` for that SignalEngine setup family, not RiskEngine
  `BLOCKED`.
- Alpha and Trigger are derived from the canonical four group scores:
  `setup_quality`, `institutional_flow`, `market_context`, and
  `company_quality_context`.
- Alpha/Trigger route fractions are defined per horizon and each group stores
  only `alpha_fraction`; Trigger fraction is derived as
  `1.0 - alpha_fraction`.
- Trigger flow contribution requires explicit `price_confirmed` evidence.
- Price confirmation threshold examples are placeholders. Production thresholds
  must be calibrated by setup family and horizon and validator-bounded.
- Placeholder `vwap_reclaim.close_above_vwap_pct: 0.30` must not independently
  unlock flow Trigger contribution in production; it requires calibrated
  setup/horizon rules and likely volume, pivot, or support confirmation.
- Alpha/Trigger matrix is descriptive unless explicit per-horizon gates are
  configured and tested.
- Setup owns RSI/BB/trend geometry; Trigger owns immediate confirmation and must
  not rescore setup indicators.
- Setup/readiness scoring may include BB compression, but compression alone is
  not bullish; Trigger activation requires bullish release or price/volume
  confirmation. Setup scoring excludes volume confirmation.
- RS thresholds are setup-family configurable and validator-bounded.
- Indicator/plugin/formula computations are reused through `IndicatorRegistry`
  instead of duplicated inside SignalEngine.
- Strategy evidence is diagnostic-only until the Alpha/Trigger aggregation phase
  explicitly consumes it.
- Strategy evidence may map matches into setup-phase evidence, but must not
  override canonical `SetupPhaseState` transition rules.
- Saved signal/candidate observations persist sub-signal fingerprints at signal
  time, including setup family, RSI, BB width percentile, VWAP position,
  RS-vs-IHSG, volume ratio, CNFB, foreign participation/concentration, domestic
  broker accumulation, regime metadata, coverage, and conviction.
- Saved observations persist phase state, phase history/fingerprint, and
  sequence validity. Tuning attribution slices by current phase, previous phase,
  phase age, and phase sequence validity.
- Sparse-history tickers receive conservative profile defaults.
- CNFB/VWAP metrics declare valid-session coverage and become unavailable below
  minimum coverage.
- Counterparty transfer uses value-weighted concentration metrics such as HHI,
  not raw broker-count ratios.
- Counterparty transfer is unavailable when buy-side or sell-side denominator is
  zero; no divide-by-zero fallback is allowed.
- Sector-relative valuation requires sufficient peer coverage and otherwise
  falls back deterministically.
- Generic monthly seasonality is a capped weak prior with sufficient-sample
  requirements and cannot directly create `ENTER`.
- Market-wide IDX calendar effects such as Lebaran liquidity drain, December
  window dressing regime, and earnings-season volatility route to
  `market_context` / liquidity / execution overlays, not ticker Alpha by
  default.
- Ticker-specific events such as MSCI/FTSE changes, dividend windows, and
  corporate actions are modeled as `event_context` / event alpha with explicit
  active windows, affected tickers, data source, announcement/effective dates,
  and no-lookahead rules.
- Strong event authority requires walk-forward validation and enough
  occurrences; dividend chase and index inclusion are not assumed guaranteed
  alpha.
- RiskEngine remains the only hard gate authority. `company_quality_context`
  must not emit `BLOCKED` or duplicate liquidity, free-float, Piotroski, bandar
  distribution, or technical gate logic.
- Score precision migration is explicit before Phase G persists decimal scores.
- Forward labels are persisted outcome records with explicit success, failure,
  neutral, and unavailable states per horizon.
- `SWING_10D` is the first calibrated horizon. `TACTICAL_3D` and `ACCUM_20D`
  remain diagnostic or share SWING defaults until `SWING_10D` reaches
  patch-eligible empirical readiness.
- Evidence contracts are not production-ready until walk-forward attribution
  shows OOS discriminative value.
- Tuning/config changes require minimum IS/OOS sample counts, OOS performance
  floors, regime attribution, coverage/conviction-bucket attribution, and no
  hidden single-regime dependency.
- Single-regime dependency is allowed only when the setup is explicitly declared
  single-regime scoped in config before calibration.
- Diagnostic-ready findings are report-only; patch-eligible changes require the
  stricter OOS sample and attribution gates.
- Every new tunable config path is registered in validator bounds in the same
  implementation phase.
- ATR multipliers, volatility buckets, size multipliers, and RS thresholds are
  validator-bounded before production use.
- ATR stop/target hints are placeholders until TradeSetup/backtest calibration
  defines horizon-specific multiples.
- `SwingTuningPatchValidator` supports diagnostic-ready vs patch-eligible states
  before expanded tuning patches are accepted.
- `institutional_flow` / `market_context` sub-signals have explicit
  Alpha/Trigger routing metadata before Phase G aggregation.
- Alpha includes durable accumulation state; Trigger requires
  `BREAKOUT_CONFIRMATION`. Flow supports `ACCUMULATION` first and supports
  Trigger only when price/volume confirms.
- Sector-derived `market_context` has a local-universe fallback and does not
  require a new external provider.
- No scoring policy lives in CLI adapters.
- All tuning uses saved observations and forward labels.

## Final Recommendation

Start with regime/setup eligibility and minimal forward labels before adding new
provider complexity. Then build `SetupPhaseState`, continuous price/volume
setup-trigger scoring, and the strategy evidence harness so setup-family and
phase-sequence behavior can be validated early. Add Institutional Accumulation
Evidence after that, but keep it diagnostic or low-authority until walk-forward
attribution proves predictive flow buckets. Add ticker profiles initially as
diagnostics/profile-confidence/max decision constraints, not as per-profile
weights. Full calibration and expanded tunables come last.
