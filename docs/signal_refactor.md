# Signal Engine Refactor Recommendation

Date: 2026-07-03

This note answers: if we restarted the signal engine today, what would be different in terms of factors, using the current repository and local data as evidence.

No runtime behavior is changed by this document.

## Executive Recommendation

Do not rewrite the app from scratch. The repo already has most of the right building blocks:

- `SignalEngine` is deterministic and pure once given a `SignalContext`.
- `RiskEngine` already separates hard gates from signal scoring.
- `MarketContextEngine` already computes a regime and applies signal/risk tightening.
- `ScoreForeignFlowUseCase` already produces a structured evidence breakdown.
- `EvaluateSwingSetupUseCase` already evaluates setup fit using trend, RSI, volatility compression, VWAP discount, and smart-flow checks.
- `SwingBacktestAttributionSummary` already defines allowlisted tuning targets for signal factors, risk gates, setup gates, and regime behavior.

The main problem is composition: `SignalEngine` currently flattens mixed evidence into one weighted average too early. If I started over, I would make the signal engine staged and evidence-first:

1. Eligibility gates decide whether the ticker is tradable enough.
2. Market regime conditions the rest of the decision.
3. Setup quality becomes the core directional timing signal.
4. Flow confirmation confirms or rejects the setup.
5. Fundamental/valuation context adjusts conviction, not timing.
6. Weak priors such as seasonality stay capped and low-impact.
7. Every factor returns evidence with direction, strength, confidence, freshness, and horizon.

## Current System Findings

### Current SignalEngine Shape

The current engine lives mainly in:

- `src/application/services/signal_engine.py`
- `src/application/use_case/assess_signal_use_case.py`
- `src/domain/value_objects/signal_assessment.py`
- `config/signal_engine.yaml`

`AssessSignalUseCase` computes six component scores:

| Factor | Current weight | Current role |
|---|---:|---|
| `bandar_intensity` | 0.20 | Operator accumulation/distribution snapshot |
| `foreign_flow_quality` | 0.20 | Compressed foreign-flow score from accumulation workflow |
| `insider_activity` | 0.20 | Insider buy/sell ratio |
| `seasonality_edge` | 0.15 | Monthly historical return/win-rate prior |
| `analyst_consensus` | 0.15 | Buy ratio plus price target upside |
| `forward_valuation` | 0.10 | Forward P/E score |

This is simple and testable, but it mixes different categories:

- Some factors are timing signals: foreign flow, bandar, technical setup.
- Some are context: analyst consensus, valuation.
- Some are weak priors: seasonality.
- Some are rare/low-frequency events: insider activity.
- Some are already composite scores before entering SignalEngine: foreign flow.

That makes the final score easy to compute but harder to trust.

### Local Data Inventory

From `data/db/data.db` on 2026-07-03:

| Dataset | Rows | Tickers | Date range |
|---|---:|---:|---|
| `candles` | 72,283 | 298 | 2024-04-22 to 2026-07-02 |
| `broker_summaries` | 80,007 | 293 | 2023-01-02 to 2026-07-02 |
| `foreign_flow_points` | 75,827 | 293 | 2025-06-12 to 2026-07-02 |
| `seasonality_cache` | 569 | 296 | 2026-06 to 2026-07 fetched months |
| `analyst_cache` | 296 | 296 | 2026-06-20 to 2026-07-02 fetched dates |
| `forward_estimates_cache` | 87 | 87 | 2026-06-28 to 2026-07-02 fetched dates |
| `bandar_detector` | 1,606 | 295 | 2026-06-18 to 2026-07-02 |
| `company_fundamentals` | 294 | 294 | 2026-06-18 to 2026-07-01 fetched dates |
| `insider_cache` | 2,803 | 296 | 2026-06-20 to 2026-07-02 fetched dates |
| `corp_action_cache` | 3,498 | 296 | 2026-06-20 to 2026-07-02 fetched dates |
| `market_context_snapshots` | 4 | n/a | 2026-06-25 to 2026-07-01 |
| `screen_snapshots` | 0 | 0 | empty |

Important data caveats:

- `IHSG` candles are Stockbit-backed locally: 241 rows from 2025-07-01 to 2026-07-02.
- No `^JKSE` rows are present in the inspected database.
- Equity candles are mostly Yahoo or `yahoo_inferred`: 49,385 Yahoo rows and 21,177 inferred Yahoo rows, versus 1,721 Stockbit rows.
- Because of the prior Yahoo volume issue, any future volume-sensitive score should prefer Stockbit candles where possible, especially for benchmark/index data.
- `screen_snapshots` is empty, so candidate-level learning is not yet accumulating through that table despite attribution code being ready for candidate observations.

### Current State Analysis

**Current factor coverage must be measured before changing weights.**

`insider_activity` carries 0.20 in `signal_engine.yaml`. It is not universally absent: `create_signal_engine(..., with_enrichment=True)` injects `StockbitInsiderActivityProvider`, `AccumulationScreenUseCase` computes `insider_net_buy_ratio`, and `signal_context_builder.py` passes that value into `SignalContext`. The remaining problem is not wiring absence; it is attribution. Before reducing or demoting insider activity, we need to measure how often the factor is present, fresh, directional, and useful in historical candidate outcomes.

The same caution applies to the other enrichment factors. The YAML weights show intended influence, but missing or unavailable factors can still behave like neutral evidence. The migration plan should therefore start with a current-factor audit that reports configured weight, active normalized weight, present/missing status, freshness, and realized contribution per factor.

**Setup data is already computed, just not threaded into SignalContext.**

`AccumulationCandidate` already carries `trend`, `rsi`, `bb_width_pctile`, `vwap_discount_pct`, and `vwap_pct`. `signal_context_builder.py` does not pass any of them to `SignalContext`. Phase 2 of the migration (Promote Setup Evidence) is therefore smaller than it sounds: extend `SignalContext` with these fields and update `build_signal_context_from_candidate()`. No new computation is needed; the data already runs in the screener.

**Bollinger compression has a current double-count and future triple-count risk.**

`ScoreForeignFlowUseCase` scores `bb_squeeze` at 10 pts inside `foreign_flow_quality`. `CoiledSpringSetupConfig` gates on `bb_width_pctile <= 0.20`. If setup quality is naively promoted as a third scored factor, Bollinger compression will cast three independent votes. The de-duplication recommendation in section 7 below should explicitly name BB compression as a sub-signal that must not appear in both `foreign_flow_quality` and the setup group.

**`analyst_consensus` has broad cache coverage but limited usable coverage.**

The inspected DB has 296 `analyst_cache` rows for 296 tickers, but only 87 rows have nonzero analyst counts; 209 rows are zero-analyst placeholders. Among usable rows, IDX sell-side consensus is structurally bullish-skewed. Before keeping this factor at material weight, its score variance and outcome attribution should be checked. Low variance means the factor ranks almost nothing differently and contributes mostly a constant offset, not signal.

## What I Would Change

### 1. Replace Flat Factor Scores With Evidence Objects

Today, `SignalContext` passes plain values and `SignalAssessment.breakdown` returns only `(factor_name, score)`.

I would introduce a richer evidence contract before aggregation:

```text
FactorEvidence
- name
- group: eligibility | regime | setup | flow | fundamental | prior
- direction: bullish | bearish | neutral
- strength: 0.0 to 1.0
- confidence: 0.0 to 1.0
- freshness: fresh | stale | missing
- horizon: intraday | swing | monthly | structural
- source: stockbit | yahoo | idx | derived | cache
- rationale
- raw_fields
```

The final score should be computed from evidence, not raw factor values. This makes it clear when a high score is strong because the evidence is strong versus merely because missing data defaulted to neutral.

Layer placement:

- Domain: immutable `FactorEvidence` / `SignalEvidence` value objects.
- Application: evidence builders and aggregation policy.
- Infrastructure: unchanged providers/repositories.
- Adapter: display the evidence; no scoring policy.

### 2. Promote Setup Quality To A First-Class Signal Group

The current `SignalEngine` does not directly score setup quality. It only receives `foreign_flow_quality`, while setup checks live in `EvaluateSwingSetupUseCase` and accumulation candidate fields.

But for swing trading, setup quality should be the center of the signal:

- trend state: `UP`, `SIDE`, `DOWN`
- pullback quality
- RSI headroom
- Bollinger compression
- support/resistance proximity
- VWAP discount/premium
- price relative to moving averages
- breakout/pullback setup match

Much of this already exists in the accumulation and swing setup path:

- `AccumulationCandidate.trend`
- `AccumulationCandidate.rsi`
- `AccumulationCandidate.bb_width_pctile`
- `AccumulationCandidate.vwap_discount_pct`
- `EvaluateSwingSetupUseCase`
- `config/swing_setups.yaml`

Two additional setup sub-signals worth naming explicitly, both computable from existing candle data with no new provider:

**Price relative strength vs. IHSG** — 5-day stock return minus 5-day IHSG return. Positive RS means the stock is outperforming the index during the accumulation observation window, which directly confirms that someone is buying into weakness rather than riding a broad market lift. IHSG candles are already in the local DB (241 Stockbit-backed rows). This is one of the few setup signals that is purely deterministic, has no provider dependency, and is immediately computable.

**Volume trend confirmation** — 5-day average volume vs. 20-day average volume. Accumulation on rising relative volume is structurally stronger evidence than the same flow pattern on declining volume. The existing `candles` table has the raw data. The caveat is that 70,562 of 72,283 candle rows are Yahoo or yahoo_inferred, which have unreliable volume. Until Stockbit candle coverage expands, this sub-signal should either use Stockbit candles only or carry a `source: yahoo` confidence penalty rather than being scored at face value.

`EvaluateSwingSetupUseCase` returns a binary `SetupMatch` (MATCH / PARTIAL / NO_MATCH), not a continuous score. To use setup evaluation as a signal factor, a translation is needed: MATCH → 100, PARTIAL → 60, NO_MATCH → 20, or alternatively the fraction of gates passed. This translation belongs in the application-layer evidence builder, not in the use case itself.

Important de-duplication constraint: Bollinger compression (`bb_width_pctile`) already appears in `ScoreForeignFlowUseCase` as a `bb_squeeze` sub-component (10 pts) and in `CoiledSpringSetupConfig` as `gate_max_bb_width_pctile`. If setup quality is promoted as a third scored group in SignalEngine, BB compression will cast three independent votes. It must appear in at most one scored group.

Recommendation: do not duplicate setup logic inside adapters. Move setup evidence into an application-level evidence builder consumed by the replacement SignalEngine. When promoting setup quality, explicitly exclude BB compression from the flow group to avoid triple-counting.

### 3. Treat Risk Gates As Gates, Not Score Factors

The repo already does this correctly. Keep it.

Risk factors such as liquidity, market cap floor, free float, fundamental gate, and dangerous bandar distribution should remain in `RiskEngine`. They should not be blended into a bullish score.

The right final composition is:

```text
Signal evidence says: is there opportunity?
Risk gates say: is it allowed?
TradeSetup says: ENTER / WATCH / AVOID after combining both.
```

This is already close to current architecture. The refactor should preserve that boundary.

### 4. Make Market Regime A Stage, Not Just A Post-Score Multiplier

Current market context behavior:

- `MarketContextEngine` computes regime from VIX, EIDO, USD/IDR, IHSG trend, breadth, and aggregate foreign flow.
- `SignalEngine` applies `signal_multiplier`.
- `RiskEngine` can apply gate tightening.

This is good, but still late in the pipeline. In the replacement SignalEngine, regime should affect factor interpretation:

- In `RISK_ON`, breakout and continuation setups can receive normal confidence.
- In `NEUTRAL`, require stronger flow confirmation.
- In `RISK_OFF`, downgrade weak setup evidence before final scoring, not only after scoring.
- In `VOLATILE`, treat mean-reversion and tight stops differently from trend-following setups.

Keep the deterministic `MarketContextEngine`; just feed its regime into the evidence aggregation policy earlier.

### 5. Reduce Or Cap Weak Priors

Seasonality should stay, but it should be small.

The recent seasonality fix corrected the headwind logic, but the conceptual issue remains: monthly seasonality is a weak prior for swing entries. It should not carry 15% of a signal unless backtests prove it.

Recommendation:

- Cap seasonality contribution at 3% to 5% in the replacement aggregator unless backtests justify more.
- Use it as a confidence nudge, not a primary factor.
- Require sufficient `total_years` and valid Stockbit payload. Specifically: a minimum of 5 years of data for the calendar month being scored. Many IDX stocks listed after 2020 have only 3–4 Januaries in their history; a 2-1 win record gives 66% win rate but is statistically meaningless. Below 5 years the factor should return `None` (unavailable), not a fabricated directional score.
- Keep missing seasonality as unavailable evidence, not bullish or bearish.

### 6. Lower Insider Activity Weight Until Proven

Insider activity currently has 20% weight, equal to foreign flow and bandar.

That is probably too high for IDX swing timing:

- Insider transactions are sparse.
- They are not necessarily near-term timing signals.
- Large shareholder selling can be administrative or portfolio-driven.
- Buying is useful, but usually as confirmation/context.

Recommendation:

- Move insider activity into fundamental/context evidence.
- Initial replacement cap: 5% to 8%.
- Consider asymmetric treatment: insider buying is positive context; insider selling is a warning only when large, recent, and repeated.

### 7. De-Duplicate Smart-Money Evidence

Current score can double-count institutional flow:

- `foreign_flow_quality` already includes consistency, streak, VWAP discount, flow ratio, Bollinger squeeze, and BCI.
- `bandar_intensity` separately measures operator accumulation/distribution.
- `smart-money-confirmed` setup also checks broker quality.

These are related signals, not independent evidence.

Recommendation:

- Group them under `flow_confirmation`.
- Keep sub-evidence visible: foreign consistency, foreign streak, BCI, bandar broad score, smart/noise share.
- Exclude Bollinger compression from the scored `flow_confirmation` group. BB compression belongs to setup quality because it describes price structure, not flow itself.
- Aggregate the group once, with internal caps, instead of giving each overlapping input full independent weight.

### 8. Keep Fundamental Context Attribution-Gated

`forward_valuation` currently uses absolute Forward P/E tiers:

- `<= 10`: very cheap
- `10-15`: cheap
- `15-20`: fair
- `20-30`: expensive
- `> 30`: decays

This is deterministic, but it ignores sector norms and growth. A bank, tower company, coal miner, and tech-like growth stock should not share one P/E curve. However, sector-relative valuation only makes sense if Phase 0 attribution shows valuation has timing value for the swing horizon. If forward valuation remains only a stretched-valuation flag, sector-relative P/E scoring is unnecessary.

Recommendation:

- Default clean-break behavior: use valuation as context/flag, not a primary timing score.
- Keep an absolute `VALUATION_STRETCHED` flag as the first deterministic rule.
- Add sector-relative valuation only if attribution proves valuation improves swing timing or confidence.
- If added later, keep sector-relative valuation as a modifier with clear caps; do not let it dominate short-term timing.

### 9. Add Confidence And Coverage To Final Classification

Today missing factors default to neutral `50.0`, and a coverage warning appears after too many missing factors.

That is better than failure, but it can still create false precision. A score of 62 with four missing factors should not be treated like a score of 62 with complete fresh evidence.

Recommendation:

- Keep `score` for ranking.
- Add `confidence` or `coverage_score`.
- Classification should consider both:

```text
ENTER requires score >= threshold and confidence >= threshold.
WATCH can allow lower confidence.
AVOID remains possible from strong negative evidence or risk gates.
```

This preserves deterministic behavior while making missing data visible in the contract.

### 10. Temporal Decay Functions for Evidence Freshness

Different signal categories degrade at different speeds. A binary fresh/stale flag is insufficient for dynamic swing setups.

Recommendation:

- Implement explicit temporal decay curves for factor groups in the aggregation layer:
  - **High-Frequency Flow (BCI, foreign net flow, bandar broad score):** Fast decay. Linear degradation over 3 to 5 market days, for example `final_confidence = base_confidence * (1 - age_days / 5)`, clamped at zero.
  - **Medium-Frequency Sentiment (Analyst consensus revisions):** Moderate decay. Degrades over 15 to 30 days.
  - **Low-Frequency Alignment (Insider transactions, company fundamentals):** Slow decay. Linear degradation over 90 days.
- Ensure that final factor confidence dynamically scales with age: `final_confidence = base_confidence * decay(age)`.

### 11. Serialization Contract for Complete Auditability

To prevent black-box decisions, the system must support exact state replay.

Recommendation:

- Define a JSON schema serialization contract for `SignalEvidence` (and all sub-evidence).
- Automatically persist this serialized evidence payload in a dedicated evidence table such as `candidate_observations` or `signal_evidence` on every screen run. Do not overload `screen_snapshots`; that table is a thin watchlist snapshot and is not suitable for structured evidence replay.
- Allow the CLI (`saham view ticker --replay`) to load this historical serialized snapshot directly to debug or review why a setup was classified as ENTER, WATCH, or AVOID at that specific date in the past, without needing to re-fetch live or historical data.

### 12. Overfitting Guardrails for Walk-Forward Calibration

Multi-factor models with customizable weights are highly vulnerable to curve-fitting (over-optimizing weights to historical noise, resulting in poor out-of-sample performance).

In this repository, "T2 Tuner" means the existing deterministic tuning workflow where `SwingBacktestAttributionSummary` produces allowlisted attribution targets, `SwingTuningDiffPolicy` and `SwingTuningPatchValidator` validate proposed YAML diffs, and `SwingTuningReviewJournal` records review history. AI, if used, only proposes diffs; the validator and human approval remain authoritative.

Recommendation:

- Establish hard constraints on the T2 Tuner (AI parameter optimization):
  - **Quantized Weight Steps:** Weights may only be adjusted in discrete steps of 5% (e.g., 0.05, 0.10, 0.15) to prevent hyper-optimization.
  - **Data Partitioning:** Enforce a strict minimum 70% In-Sample (training) and 30% Out-of-Sample (validation) historical window for any walk-forward run.
  - **Parameter Shift Limits:** Limit the maximum weight deviation to plus or minus 10% from baseline defaults per tuning cycle.

### 13. Test Fundamental Factors As Context Flags

The current engine uses `forward_valuation` (10%), `analyst_consensus` (15%), and `insider_activity` (20%) as weighted score contributors. These are fundamentals-oriented and operate on 3–12 month horizons. The use case is a 5–20 day swing accumulation screener.

For a 5–20 day horizon, fundamental factors are more plausibly context than timing. They tell you whether a company is worth owning, not necessarily whether now is the right 5-day window to enter. Their current combined stated weight is 45%, which is high enough to dominate a timing tool unless attribution proves otherwise.

A cleaner replacement hypothesis is to treat most of them as context flags that can warn, disqualify, or lightly modify confidence rather than boost timing by default:

- `forward_valuation`: if forward P/E > 50, add a `VALUATION_STRETCHED` flag. Do not score it as a positive signal for P/E ≤ 30. Extreme cheapness (P/E ≤ 8) may justify a small positive modifier.
- `analyst_consensus`: if buy_ratio < 0.20 (majority sell/hold), flag as `ANALYST_BEARISH`. Otherwise neutral. Do not reward majority buy consensus — in IDX it is near-constant.
- `insider_activity`: if net selling is large, recent, and repeated in the 90-day window, add `INSIDER_SELLING` warning. Buying remains positive context at low weight (5%).

This preserves the information value of fundamental data without letting it dominate a timing score. It also reduces the impact of the forward estimates coverage gap (only 87/296 tickers today): missing context should lower evidence completeness rather than fabricate bullish or bearish timing.

## Proposed Replacement SignalEngine Factor Groups

Initial deterministic grouping:

| Group | Purpose | Candidate data today | Suggested role |
|---|---|---|---|
| Eligibility | Tradability and hard exclusions | RiskEngine, candles, fundamentals, shareholding | Gate, not score |
| Regime | Market backdrop | MarketContextEngine | Condition/scaling |
| Setup quality | Timing and structure | candidate trend, RSI, BB, VWAP, setup gates, RS vs IHSG, volume trend | Primary score |
| Flow confirmation | Foreign/bandar/smart money (BB excluded to avoid triple-count) | broker summaries, foreign points, bandar cache | Primary confirmation |
| Fundamental context | Valuation extremes, insider selling | forward estimates, insider cache | Binary gate/flag, not weighted score |
| Analyst context | Sell-side consensus | analyst cache | Flag only when majority bearish; near-constant in IDX |
| Event/catalyst risk | Corporate action/news/earnings | corp actions, sentiment, earnings cache | Warning/gate/modifier |
| Priors | Seasonality (min 5 years sample) | seasonality cache | Small nudge |

Suggested initial influence, before backtest calibration:

| Group | Initial role |
|---|---|
| Setup quality | Primary scored timing group, initial 60% of scored opportunity evidence |
| Flow confirmation | Primary scored confirmation group, initial 40% of scored opportunity evidence |
| Market regime | Condition/threshold policy, not raw weight |
| Fundamental context | Flag/modifier; no default positive timing score |
| Analyst context | Bearish flag only unless attribution proves otherwise |
| Insider context | Warning/context modifier; low positive context only when recent/repeated |
| Seasonality prior | Capped weak prior, initially 3% to 5% if sample size is sufficient |
| Data confidence | Classification constraint, not raw weight |

This should be treated as a starting hypothesis only. Final weights should come from walk-forward attribution.

## Migration Plan

The controlling implementation plan is `docs/signal_refactor_phases.md`. Use
that file for phase order, acceptance criteria, and verification details. This
recommendation document is design rationale only.

## Recommended Near-Term Config Bias

Before the replacement aggregator exists, any low-code adjustment should be tested in backtests and attribution only, not applied blindly to production:

- Reduce `seasonality_edge` from `0.15` toward `0.03-0.05`.
- Reduce `insider_activity` from `0.20` toward `0.05-0.08`.
- Preserve or slightly increase true setup/flow influence, but avoid double-counting `foreign_flow_quality` and `bandar_intensity`.
- Do not change production thresholds without walk-forward comparison.

This should be tested, not applied blindly.

## Data Work Needed Before Relying On The Replacement Engine

1. Prefer Stockbit candles/volume where volume-sensitive features matter.
2. Keep IHSG canonical as `IHSG`, not `^JKSE`, for Stockbit-backed benchmark logic.
3. Populate a dedicated candidate-observation/evidence table for rejected candidate learning; do not overload `screen_snapshots`.
4. Improve valuation coverage: only 87 tickers have forward estimates in the inspected DB.
5. Decide whether `earnings_cache` should be populated; it is currently empty locally.
6. Keep cache freshness explicit per factor, especially analyst, forward estimates, and insider data.

## DoD And Architecture Compliance

- Deterministic-first: all recommended scoring remains rule-based and reproducible.
- AI optional: AI may only suggest YAML tuning diffs after deterministic attribution; it must not produce live decisions.
- Domain purity: value objects can describe evidence, but provider fetching and workflow stay outside domain.
- Application ownership: aggregation, setup evidence building, regime conditioning, and confidence policy belong in application services/use cases.
- Infrastructure thinness: providers and repositories should only fetch/cache/parse data.
- Adapter thinness: CLI should only request analysis and format evidence.
- Persistence: candidate observations and evidence snapshots should be local-first, likely SQLite, and schema-versioned.

## Bottom Line

The right refactor is not "add more factors." It is to stop treating every factor as an independent 0-100 vote.

Use the current repo's stronger parts:

- RiskEngine for gates.
- MarketContextEngine for regime.
- EvaluateSwingSetupUseCase for setup fit.
- ScoreForeignFlowUseCase for flow evidence.
- SwingBacktestAttributionSummary for tuning evidence.

Then rebuild SignalEngine around staged, confidence-aware evidence aggregation.
