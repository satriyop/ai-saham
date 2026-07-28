# SignalEngine Evidence Model

This document extracts the cohesive evidence model from the historical
[SignalEngine refactor rationale](archive/signal_refactor_full_rationale.md).
It describes design responsibility, not guaranteed runtime behavior. Current
config, code, tests, ADRs, and `AI_AGENT_CHECKLIST.md` are authoritative.

## Setup Phase State

Accumulation-oriented signals are temporal. Evidence order matters, so the
model distinguishes lifecycle state from evidence strength:

```text
SetupPhaseState:
- NONE
- ACCUMULATION
- COMPRESSION
- BREAKOUT_CONFIRMATION
- EXHAUSTION
- DISTRIBUTION
- FAILED

state = where the ticker is in the setup lifecycle
score = strength of evidence inside the current or prior phase
```

For accumulation and foreign-bounce setups, the intended sequence is:

```text
ACCUMULATION -> COMPRESSION -> BREAKOUT_CONFIRMATION
```

- `ACCUMULATION`: sustained institutional evidence without fast distribution.
- `COMPRESSION`: volatility contracts while support and accumulation remain
  intact; compression is readiness, not bullish direction.
- `BREAKOUT_CONFIRMATION`: positive price/volume pivot, directional release,
  reclaim, or equivalent configured confirmation.
- `EXHAUSTION`, `DISTRIBUTION`, and `FAILED`: cap the maximum decision or force
  `WATCH`/`AVOID` according to current policy.

`ENTER` for an accumulation-family setup requires the configured phase sequence
and an allowed entry phase. A breakout without prior accumulation may belong to
a different setup family. Phase requirements belong in validated setup config;
named setups map deterministically to their broad family.

Setup phase is SignalEngine evidence. It is not a RiskEngine hard gate.

## Primary Trigger Patterns

For `SWING_10D` accumulation-style setups, the anchor trigger is volume dry-up
followed by directional volume expansion:

```text
dry-up:
  supply exhaustion / quiet accumulation

expansion:
  demand returns with positive price and range confirmation
```

Secondary confirmation may include VWAP reclaim, support reclaim, squeeze
release, positive close, or broker/foreign acceleration. Secondary evidence
must not replace the primary trigger unless current setup config explicitly
allows and tests that exception.

Volume-trigger availability requires quality-valid stock OHLCV, enough valid
sessions for its lookback, and protection against suspended, missing, synthetic,
or zero-volume distortion. Unavailable evidence lowers coverage rather than
being interpreted as a weak signal.

The trigger is not universal. Mean-reversion, catalyst, NCP/pre-open, and
intraday setup families may use different configured trigger contracts.

## Continuous Setup and Trigger Scoring

Coarse labels such as `MATCH`, `PARTIAL`, and `NO_MATCH` are explanatory; they
must not be the sole numeric scoring inputs. Continuous setup quality is derived
from structural sub-signals such as trend alignment, RSI quality, BB compression
readiness, daily VWAP position, and relative strength versus IHSG.

Eligibility and max-decision constraints can override additive score. For
trend, breakout, accumulation, and foreign-bounce families, negative relative
strength versus IHSG is primarily an eligibility or max-decision concern. Mean
reversion is an explicit exception only when support/reversal evidence is
strong enough under current config.

Strict evidence ownership prevents double counting:

```text
Setup Quality owns:
- Bollinger compression percentile
- RSI value/quality
- SMA/trend alignment
- relative strength versus IHSG
- daily VWAP position, not the reclaim event

Trigger Timing owns:
- volume spike or dry-up reversal
- positive close/pivot confirmation
- directional squeeze release
- VWAP or support reclaim
- NCP/intraday confirmation where relevant
- tactical distance to foreign VWAP
```

Trigger may consume setup readiness but must not rescore the same RSI, BB, SMA,
or volume facts through multiple routes.

## Institutional Accumulation Evidence

Institutional evidence has two first-class tracks:

```text
foreign_institutional_track
domestic_bandar_track
```

Missing foreign flow does not mean all institutional evidence is missing when
domestic broker evidence is available. Broker codes remain evidence, not proof
of beneficial-owner identity.

### Foreign Institutional Track

Candidate fields include foreign participation ratio, foreign broker
concentration such as CR4/CR8, CNFB price divergence, counterparty transfer
using value-weighted HHI, foreign VWAP distance, and asymmetric slow
accumulation/fast distribution windows.

CNFB and VWAP-derived metrics declare session coverage and become unavailable
below configured minimums. Counterparty transfer is unavailable when either
denominator is zero; no divide-by-zero fallback is allowed.

### Domestic Bandar Track

Candidate fields include top-three/top-five net-buy consistency, broker
reversal, accumulation-session ratio, domestic buy VWAP distance, broker HHI
divergence, and bandar broad/accumulation scores.

Domestic accumulation supports `ACCUMULATION`/Alpha first. It may support
`BREAKOUT_CONFIRMATION` only with price/volume confirmation and must not create
`ENTER` directly.

All flow evidence persists raw values, normalized values, coverage, conviction,
and authority status. New flow buckets remain `DIAGNOSTIC` or `LOW_WEIGHT` until
walk-forward attribution demonstrates discriminative value.

## Ticker Profile Exposure

Ticker profiles describe how evidence should be interpreted; they are not a
shortcut to hidden per-ticker scoring policy. Typical diagnostics consider
liquidity/market-cap behavior, foreign participation, broker concentration,
domestic flow behavior, volatility, and index membership/context.

Sparse-history tickers receive conservative defaults. Profile exposure should
be epoch-based and persisted so replay uses the profile known at signal time.
Daily scoring must not recalculate profile weights ad hoc.

Initial profile usage is diagnostic, evidence interpretation, confidence caps,
or max-decision constraints. Per-profile group weights remain disabled until
out-of-sample evidence supports them. Confidence adjustments require explicit
caps and release conditions.

## Alpha Versus Trigger Split

Alpha represents durable structural attractiveness; Trigger represents entry
timing. Both are routed from the canonical group scores:

```text
setup_quality
institutional_flow
market_context
company_quality_context
```

Each group stores one `alpha_fraction` per horizon. Trigger fraction is derived
as `1.0 - alpha_fraction`. Horizon policy combines normalized Alpha and Trigger
scores using its configured Alpha weight.

Design constraints:

- accumulation state and durable flow belong primarily to Alpha;
- Trigger requires `BREAKOUT_CONFIRMATION` and immediate price/volume evidence;
- flow may support Trigger only when `price_confirmed` is explicit;
- descriptive matrices do not grant authority unless config and tests enforce
  corresponding gates;
- score precision migration must be explicit if exact decimal scores are
  persisted alongside display integers.

## Sector Context

Sector evidence supplies market context without requiring a new provider when
local-universe data is sufficient. Candidate evidence includes sector return
and breadth, ticker relative strength versus sector, sector relative strength
versus IHSG, sector regime, peer coverage, and data quality.

Sector-derived context must declare coverage and remain unavailable when peer
coverage is insufficient. Sector-relative valuation similarly requires enough
valid peers and otherwise falls back deterministically.

Sector context begins diagnostic or low-authority until replay attribution
supports promotion. It conditions eligibility/context; it does not silently
rewrite raw setup evidence.

### Sector Macro Context (ADR-053)

Sibling diagnostic evidence (L2b), not peer technicals: routes external macro
series (e.g. coal futures, USD/IDR) per `universes.yaml` group. v1 live map is
`energy` only; authority is DIAGNOSTIC; fingerprints use `smc_*` fields
(observation schema v9). Does not reweight Signal or Risk. Independent of MCE
global `commodity_composite` (which stays optional and off by default).

## Regime Detection Evidence

Market regime is deterministic, replayable evidence upstream of ticker scoring.

```text
RegimeModel:
  market-wide evidence, regime label, confidence, stability

SignalEngine:
  ticker/setup evidence and scores

DecisionPolicy:
  combines both into eligibility, max decision, and sizing constraints
```

Regime evidence may include IHSG trend, breadth, volume, volatility, and
market-wide foreign-flow diagnostics. Persist observation date, inputs, score,
label, confidence, stability, detection method, and market-level forward labels
when validating the model.

Regime is not a hidden multiplier in the raw ticker score. Low-confidence or
transitioning regimes cap decisions or reduce usable coverage through explicit
policy. A regime-level prohibition on `ENTER` overrides setup-specific policy;
setup policy may tighten but must not silently loosen that constraint.

Volatility context may emit ATR-based execution hints and size multipliers, but
TradeSetup/sizing/backtest policy owns final stop, target, and position size.

## Seasonality and Event Context

Generic monthly seasonality is a capped weak prior. It requires sufficient
sample size and cannot create `ENTER` directly.

Market-wide calendar effects route to `market_context`, liquidity, or execution
overlays rather than ticker Alpha by default.

Ticker-specific events such as index changes, dividend windows, and corporate
actions belong to explicit `event_context`/event-alpha evidence with active
windows, affected tickers, source, announcement/effective dates, and
no-lookahead availability rules.

Strong event authority requires adequate occurrences and walk-forward proof.
Dividend chase and index inclusion must not be assumed to provide guaranteed
alpha.

## Related Documents

- [Design Overview](signal_engine_design_overview.md)
- [Output Contract](signal_engine_output_contract.md)
- [Documentation Index](signal_refactor.md)
- [Archived Full Rationale](archive/signal_refactor_full_rationale.md)
