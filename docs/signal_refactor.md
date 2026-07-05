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
6. Decision policy: given the score, confidence, regime, and gates, what action
   is allowed?

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
regime-aware eligibility plus replayable forward labels, then continuous
setup/trigger scoring that can prove whether price/volume pivots separate
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

### Missing Data Reduces Confidence

Missing evidence must not become neutral bullish/bearish evidence. It should
reduce confidence and be visible in the replay payload.

Example:

```text
setup_score = 76
flow_score = unavailable
confidence = capped at 0.55
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
evidence_confidence exists      = implementation complete
evidence_confidence separates high-quality OOS winners from losers
                               = empirical readiness

new flow evidence computes CR4  = implementation complete
CR4 buckets improve OOS payoff ratio or reduce drawdown
                               = empirical readiness
```

Until empirical readiness is proven, new evidence should be treated as
diagnostic, low-weight, or confidence-only. It should not become a high-impact
production factor merely because the implementation is finished.

## Recommended Signal Model

### 1. Continuous Setup And Trigger Scoring

Current setup classification can collapse useful information into coarse labels
such as `MATCH`, `PARTIAL`, and `NO_MATCH`. Those labels are still useful for
explanation, but they should not drive the numeric score by themselves.

Setup score should come from structural sub-signals directly:

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

BB compression is trigger readiness, not simple bullish evidence. Compression
alone says price is coiled; it does not say direction. A setup family may require
compression before scoring, and compression quality may scale trigger readiness,
but trigger activation requires a bullish release or positive price/volume
confirmation.

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
- relative strength vs IHSG

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

### 1.1 Reuse Indicators, Plugins, Formulas, And Strategies

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

### 2. Institutional Accumulation Evidence

IDX flow should not be represented by raw net foreign buy alone. The flow layer
should test whether buying looks institutional, concentrated, persistent, and
price-absorbed.

Default authority:

```text
Flow defines Alpha/context/eligibility first.
Flow does not independently create ENTER.
Raw net-buy intensity is never an entry trigger by itself.
Flow may support Trigger only when it coincides with price confirmation.
Flow buckets start as diagnostic, binary, low-weight, or confidence-only until
walk-forward attribution proves bucket-level predictive value.
```

Recommended evidence object:

```text
InstitutionalAccumulationEvidence
- foreign_participation_score
- foreign_concentration_score
- cnfb_divergence_score
- counterparty_transfer_score
- foreign_vwap_distance_score
- confidence
- reasons
```

Recommended scoring weights:

```yaml
institutional_accumulation:
  authority: diagnostic_or_low_weight_until_proven
  foreign_participation: 0.20
  foreign_concentration_cr4: 0.20
  cnfb_price_divergence: 0.30
  counterparty_transfer: 0.15
  foreign_vwap_distance: 0.15
```

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
confidence, or trigger risk warnings.

Do not rely only on Pearson correlation for short windows. Use CNFB slope, price
slope, CNFB percentile, and price range compression together.

Coverage requirement:

```text
CNFB_20D requires at least 15 valid trading sessions inside the last 20 expected
trading sessions. Below that, CNFB divergence is unavailable and confidence is
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
    confidence is reduced
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

### 3. Ticker Profile Exposure

IDX tickers should not all use the same weights. BBCA, BBRI, TLKM, AMMN, BREN,
domestic second-liners, and illiquid third-liners have different driver
structures.

Use soft profile exposure, not a permanent hard bucket:

```json
{
  "profile": "FOREIGN_INSTITUTIONAL",
  "confidence": 0.82,
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

Do not introduce per-profile group weights initially. Profile should first
affect evidence interpretation, confidence, diagnostics, and max decision. Only
add profile-specific group weights after walk-forward data proves enough sample
volume per profile and enough OOS discriminative value.

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

### 4. Alpha vs Trigger Split

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
- durable institutional accumulation for longer horizons

Trigger:
- setup quality
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
| `setup` | none by default; setup is timing/readiness evidence | continuous setup score, trend geometry, RSI quality, BB compression readiness, VWAP position, RS vs IHSG |
| `flow` | 20d/30d durable CNFB slope, accumulation persistence, buyer concentration stability, foreign participation regime | only price-confirmed 3d/5d flow acceleration, broker streak acceleration with pivot confirmation, foreign VWAP reclaim context |
| `context` | sector regime, IHSG regime, liquidity regime, sector-relative valuation context | NCP/pre-open confirmation, same-day gap direction, intraday liquidity/imbalance confirmation |
| `fundamental_risk` | valuation percentile, earnings trend, analyst revision, insider/ownership quality, event-tagged seasonality | none by default; only event timing flags when explicitly configured |

Flow and context may feed both Alpha and Trigger, but no sub-signal may be routed
to both unless the config explicitly marks it as shared with a capped combined
contribution. Evidence builders should emit route metadata such as
`route: alpha`, `route: trigger`, or `route: shared_capped`.

Initial route fractions by horizon:

```yaml
route_fractions:
  TACTICAL_3D:
    setup: {alpha: 0.00, trigger: 1.00}
    flow: {alpha: 0.70, trigger: 0.30}
    context: {alpha: 0.25, trigger: 0.75}
    fundamental_risk: {alpha: 1.00, trigger: 0.00}

  SWING_10D:
    setup: {alpha: 0.00, trigger: 1.00}
    flow: {alpha: 0.80, trigger: 0.20}
    context: {alpha: 0.60, trigger: 0.40}
    fundamental_risk: {alpha: 1.00, trigger: 0.00}

  ACCUM_20D:
    setup: {alpha: 0.10, trigger: 0.90}
    flow: {alpha: 0.90, trigger: 0.10}
    context: {alpha: 0.75, trigger: 0.25}
    fundamental_risk: {alpha: 1.00, trigger: 0.00}
```

For each group, `alpha + trigger` must equal `1.00`. Alpha and Trigger scores
are computed by routing weighted group contributions, then normalizing each
side by its routed total:

```text
alpha_score =
  sum(group_score * group_weight * alpha_route_fraction)
  / sum(group_weight * alpha_route_fraction)

trigger_score =
  sum(group_score * group_weight * trigger_route_fraction)
  / sum(group_weight * trigger_route_fraction)
```

This makes the Alpha/Trigger derivation computable while preserving the four
canonical group scores.

Flow's trigger-routed fraction is capped and conditional. It contributes only
when the same observation has price/volume confirmation such as pivot reclaim,
positive close, squeeze release, or VWAP reclaim. Without price confirmation,
flow remains Alpha/context evidence and cannot dominate Trigger.

Decision matrix:

```text
High Alpha + strong Trigger = ENTER
High Alpha + weak Trigger = WATCH
Low Alpha + strong Trigger = SPECULATIVE_ONLY or tactical WATCH
Low Alpha + weak Trigger = AVOID
```

This matrix is a conceptual explanation of the decision policy, not a second
mandatory gate. The mechanical decision is still driven by blended score,
confidence floor, hard gates, and regime/horizon thresholds. If a future config
adds explicit `min_alpha_score` or `min_trigger_score` gates, those gates must be
declared per horizon and tested so they do not conflict with the blended-score
threshold.

A 3-day tactical trade should not require the same Alpha quality as a 20-day
accumulation trade.

### 5. Sector Context

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

### 6. Regime Threshold Policy

Use regime-conditioned thresholds:

```yaml
classification_thresholds:
  RISK_ON:
    enter: 68
    watch: 48
    confidence_cap: 1.00
    max_decision: ENTER
    size_multiplier: 1.00

  NEUTRAL:
    enter: 72
    watch: 52
    confidence_cap: 0.90
    max_decision: ENTER
    size_multiplier: 0.50

  RISK_OFF:
    enter_allowed: false
    enter: 80
    watch: 60
    confidence_cap: 0.70
    max_decision: WATCH
    size_multiplier: 0.25

  VOLATILE:
    enter_allowed: false
    watch: 65
    confidence_cap: 0.60
    max_decision: WATCH
    size_multiplier: 0.00
```

Minimum confidence is separate from the regime confidence cap. The cap limits
how high confidence may be after regime/data-quality adjustments; the floor
defines the minimum confidence required for `ENTER`.

Initial minimum confidence policy:

```yaml
minimum_confidence:
  TACTICAL_3D:
    RISK_ON: 0.60
    NEUTRAL: 0.65
    RISK_OFF: 0.75
    VOLATILE: 1.00  # ENTER disabled by regime

  SWING_10D:
    RISK_ON: 0.65
    NEUTRAL: 0.70
    RISK_OFF: 0.80
    VOLATILE: 1.00

  ACCUM_20D:
    RISK_ON: 0.70
    NEUTRAL: 0.75
    RISK_OFF: 0.82
    VOLATILE: 1.00
```

This expresses the business rule clearly: in hostile markets, be more selective.
`RISK_OFF` intentionally disables `ENTER` in the initial policy. Earlier drafts
also made `ENTER` impossible through `confidence_cap < minimum_confidence`; this
is now explicit so calibration cannot accidentally enable RISK_OFF entries by
raising the confidence cap alone.

Regime controls eligibility and sizing constraints, not raw scores. SignalEngine
should emit `max_decision`, `size_multiplier`, and rationale. Actual position
sizing belongs in `TradeSetup` / sizing policy, which consumes these constraints
alongside capital, stop distance, liquidity, and risk limits.

### Setup-Specific Regime Compatibility

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
      flow_confidence_min: 0.75
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

### 7. Sector-Relative Valuation

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
    use static P/E fallback with lower confidence
```

Peer coverage is measured against the active local universe/sector mapping for
the analysis date. The engine should not trigger network fetches from scoring
code just to complete a percentile; incomplete local coverage lowers confidence
or selects a fallback.

Valuation should contribute to Alpha and risk context, not short-term Trigger.

### 8. NCP Pre-Open As Execution Overlay

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

### 9. Event-Tagged Seasonality

Generic monthly seasonality is a weak prior. It should remain capped unless
sample size and event context are strong.

Useful IDX event tags:

```text
WINDOW_DRESSING_DEC
JANUARY_EFFECT
LEBARAN_LIQUIDITY_DRAIN
DIVIDEND_SEASON
MSCI_REBALANCE
FTSE_REBALANCE
EARNINGS_SEASON
```

Rules:

```text
minimum 5 usable years
missing or insufficient sample = unavailable
small contribution unless attribution proves otherwise
```

## Recommended Group Model

Use four top-level evidence groups as the only numeric evidence layer. Alpha and
Trigger are derived component views from those group scores. The final score is
then a horizon-specific blend of Alpha and Trigger.

Composition:

```text
group_scores = setup, flow, context, fundamental_risk

alpha_score =
  normalized weighted blend of group contributions routed to Alpha

trigger_score =
  normalized weighted blend of group contributions routed to Trigger

final_score =
  horizon_alpha_weight * alpha_score
  + horizon_trigger_weight * trigger_score
```

This means the four groups drive all numeric scoring. Alpha/Trigger do not add a
second independent factor tree; they are decision-facing projections of the same
evidence.

```yaml
groups:
  setup:
    weight: 0.35

  flow:
    weight: 0.30

  context:
    weight: 0.25

  fundamental_risk:
    weight: 0.10
```

For `SWING_10D`:

```yaml
SWING_10D:
  hard_gates:
    min_median_turnover_20d: 5000000000
    min_price: 50
    max_atr_pct: 7.5
    require_valid_volume: true

  alpha_trigger_blend:
    alpha: 0.40
    trigger: 0.60

  groups:
    setup:
      weight: 0.35
    flow:
      weight: 0.30
    context:
      weight: 0.25
    fundamental_risk:
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
    alpha: 0.50
    trigger: 0.50

  groups:
    setup: 0.25
    flow: 0.40
    context: 0.20
    fundamental_risk: 0.15
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
    alpha: 0.20
    trigger: 0.80

  groups:
    setup: 0.45
    flow: 0.30
    context: 0.20
    fundamental_risk: 0.05
```

Hard gates are horizon-specific. They should not be copied blindly between
profiles because a tactical trade, swing trade, and 20-day accumulation trade
have different liquidity and volatility tolerance.

## Output Contract

The final signal output should make score, confidence, context, and decision
explicit:

```json
{
  "ticker": "BBCA",
  "profile": "FOREIGN_INSTITUTIONAL",
  "profile_confidence": 0.82,
  "horizon": "SWING_10D",
  "alpha_score": 71,
  "trigger_score": 78,
  "score": 75.2,
  "confidence": 0.82,
  "market_regime": "NEUTRAL",
  "sector_regime": "BULLISH",
  "decision": "ENTER",
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
score = 0.40 * alpha_score + 0.60 * trigger_score
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
elif confidence < min_confidence:
    INSUFFICIENT_DATA or WATCH
elif regime blocks ENTER:
    WATCH
elif score >= enter_threshold and confidence >= min_confidence:
    ENTER
elif score >= watch_threshold:
    WATCH
else:
    AVOID
```

## Implementation Phases

### Phase A: Regime And Setup Eligibility Policy

Goal: make regime constraints explicit before changing signal math.

Work:

- Add config-driven regime thresholds, confidence floors, max decisions, and
  size multipliers.
- Add setup-specific regime compatibility policy.
- Preserve raw score comparability across regimes.
- Ensure regime changes affect eligibility/sizing constraints, not raw evidence
  scores.
- Add tests for RISK_ON, NEUTRAL, RISK_OFF, and VOLATILE decisions.

Why first: this controls false positives immediately and prevents flow or setup
experiments from creating entries in hostile regimes.

### Phase B: Minimal Forward Labels

Goal: create replayable outcome labels before deeper architecture work.

Work:

- Persist deterministic `signal_forward_labels` records.
- Implement `SUCCESS`, `FAILURE`, `NEUTRAL`, and `UNAVAILABLE` outcomes.
- Store continuous labels: close return, max forward return, max adverse
  excursion, days to peak/trough, stop/target triggers.
- Keep labels local-first and independent of AI.
- Mark incomplete candle windows as `UNAVAILABLE` with a reason.

Why second: without labels, improvements are judged by intuition instead of
walk-forward evidence.

### Phase C: Continuous Setup/Trigger Scoring

Goal: replace coarse setup labels with continuous price/volume pivot evidence.

Work:

- Add continuous setup sub-signal scoring.
- Keep existing labels and failed gates for explanation.
- Add BB compression as trigger readiness, not bullish evidence.
- Exclude volume confirmation from setup scoring; route volume spike/dry-up,
  positive close, VWAP reclaim, support reclaim, and squeeze release to Trigger.
- Add tests proving one failed gate does not equal all gates failed.

Why third: after labels exist, price/volume pivot evidence can be checked for
actual OOS discrimination.

### Phase D: Strategy Evidence Harness

Goal: reuse existing deterministic strategy packages as setup-family evidence
and empirical validation tools without creating a parallel decision engine.

Work:

- Add `StrategyEvidenceBuilder` in the application layer.
- Evaluate validated strategy YAMLs through `IndicatorRegistry`.
- Map matched strategy rules to setup-family evidence with confidence,
  freshness, route metadata, and rationale.
- Persist matched strategy name, matched rule, and outcome in replay
  observations.
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
- Use asymmetric windows: 20d/30d for bullish accumulation Alpha and 3d/5d/7d
  for bearish distribution/risk.
- Enforce minimum valid trading-session coverage before CNFB/VWAP metrics are
  considered available.
- Persist all raw metrics in replay observations.
- Keep flow diagnostic, binary, low-weight, or confidence-only until Phase I
  attribution proves bucket-level predictive value.

### Phase F: Minimal Ticker Profile Diagnostics

Goal: classify ticker behavior without introducing tunable explosion.

Work:

- Add deterministic profile classifier as an application service.
- Start with local liquidity, broker, foreign-flow, volatility, and index
  membership data only.
- Output soft exposures and confidence.
- Persist profile snapshots by epoch, with monthly default cadence.
- Backtests must read historical profile snapshots for the signal date and must
  not recompute profiles using future data.
- Define conservative fallback for sparse-history tickers.
- Use profiles for evidence interpretation, confidence, diagnostics, and max
  decision only. Do not add per-profile group weights yet.

### Phase G: Simplified Alpha/Trigger Split

Goal: separate structural attractiveness from entry timing without adding a
large new tunable surface.

Work:

- Add Alpha and Trigger component scores.
- Derive Alpha and Trigger from the four group scores; do not introduce a second
  independent factor tree.
- Keep flow primarily Alpha/context. Permit trigger contribution only when price
  confirms.
- Decide and implement the score precision contract: either migrate
  `SignalAssessment.score` to float or add a separate raw/exact score field while
  preserving display int behavior.
- Register every new tunable config path in validator bounds in the same phase.

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
- Enforce in-sample/out-of-sample split.
- Quantize weight changes.
- Cap per-cycle shifts.
- Register all tunable config paths in validator bounds before use.
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
    require_confidence_bucket_attribution: true
    reject_single_regime_dependency: true
```

A finding can be diagnostic-ready with a small OOS sample, but it is not
patch-eligible until the stricter sample and attribution gates pass. If current
validator behavior is less strict, the stricter gates above are target-state
requirements and must not be claimed as implemented.

A config change is not accepted just because in-sample performance improves. It
must clear OOS gates, preserve or improve drawdown behavior, and pass attribution
checks showing the improvement is not hidden inside one market regime, one setup
family, one liquidity bucket, or one confidence bucket.

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
by confidence bucket
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
- score/result value objects
- no providers, repositories, CLI, or AI

Application:
- evidence builders
- strategy evidence builder
- indicator registry / formula evaluation orchestration
- profile classifier
- Alpha/Trigger aggregation
- regime threshold policy
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
- Strategy packages, plugins, and formulas may produce evidence, but may not
  directly override canonical SignalEngine decisions.
- Works fully without AI.
- Deterministic for the same local data and config.
- Missing evidence lowers confidence instead of becoming neutral signal.
- Regime thresholds are config-driven.
- `RISK_OFF` and `VOLATILE` initial policies explicitly disable `ENTER`; this
  cannot be inferred only from cap/floor math.
- Setup-specific regime compatibility is explicit and affects eligibility, not
  raw evidence scores.
- Setup-specific regime labels have operational numeric requirements.
- Minimum confidence floors are defined per horizon and regime, separate from
  confidence caps.
- Profile diagnostics are observable in replay payloads.
- Profile exposure is epoch-based and persisted; daily scoring does not
  recalculate profile weights ad hoc.
- Profile does not introduce per-profile group weights initially; it affects
  evidence interpretation, confidence, diagnostics, and max decision first.
- Flow metrics are persisted with raw values, normalized scores, and authority
  labels. Flow starts diagnostic/binary/low-weight until OOS attribution proves
  bucket-level predictive value.
- Raw net-buy intensity never directly creates `ENTER`.
- Trigger is dominated by price/volume pivot confirmation; foreign/broker flow
  supports Trigger only when price confirms.
- Alpha and Trigger are derived from the canonical four group scores.
- Alpha/Trigger route fractions are defined per horizon and each group route
  sums to `1.00`.
- Alpha/Trigger matrix is descriptive unless explicit per-horizon gates are
  configured and tested.
- Setup owns RSI/BB/trend geometry; Trigger owns immediate confirmation and must
  not rescore setup indicators.
- Setup/readiness scoring may include BB compression, but compression alone is
  not bullish; Trigger activation requires bullish release or price/volume
  confirmation. Setup scoring excludes volume confirmation.
- Indicator/plugin/formula computations are reused through `IndicatorRegistry`
  instead of duplicated inside SignalEngine.
- Sparse-history tickers receive conservative profile defaults.
- CNFB/VWAP metrics declare valid-session coverage and become unavailable below
  minimum coverage.
- Counterparty transfer uses value-weighted concentration metrics such as HHI,
  not raw broker-count ratios.
- Counterparty transfer is unavailable when buy-side or sell-side denominator is
  zero; no divide-by-zero fallback is allowed.
- Sector-relative valuation requires sufficient peer coverage and otherwise
  falls back deterministically.
- Score precision migration is explicit before Phase G persists decimal scores.
- Forward labels are persisted outcome records with explicit success, failure,
  neutral, and unavailable states per horizon.
- Evidence contracts are not production-ready until walk-forward attribution
  shows OOS discriminative value.
- Tuning/config changes require minimum IS/OOS sample counts, OOS performance
  floors, regime attribution, confidence-bucket attribution, and no hidden
  single-regime dependency.
- Diagnostic-ready findings are report-only; patch-eligible changes require the
  stricter OOS sample and attribution gates.
- Every new tunable config path is registered in validator bounds in the same
  implementation phase.
- Flow/context sub-signals have explicit Alpha/Trigger routing metadata before
  Phase G aggregation.
- Sector context has a local-universe fallback and does not require a new
  external provider.
- No scoring policy lives in CLI adapters.
- All tuning uses saved observations and forward labels.

## Final Recommendation

Start with regime/setup eligibility and minimal forward labels before adding new
provider complexity. Then build continuous price/volume setup-trigger scoring
and the strategy evidence harness so setup-family behavior can be validated
early. Add Institutional Accumulation Evidence after that, but keep it
diagnostic or low-authority until walk-forward attribution proves predictive
flow buckets. Add ticker profiles initially as diagnostics/confidence/max
decision constraints, not as per-profile weights. Full calibration and expanded
tunables come last.
