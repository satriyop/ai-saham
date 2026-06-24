# Re-Architecture Recommendation: Risk Engine & Signal Engine as First-Class Citizens

**Date:** 2026-06-24  
**Author:** Claude (claude-sonnet-4-6) — architectural analysis pass  
**Branch:** main @ 87c24bd  
**Scope:** Full codebase review — ADRs, feature alignment, engine design, IDX market fit

**ADR Status:** ✅ All ADR changes in this document have been applied to `ARCHITECTURE_DECISIONS.md` (2026-06-24). Section 5 below reflects what was done, not what is proposed.

**R1 Status:** ✅ SignalEngine first-class service complete (2026-06-24). 50 unit tests, full suite 1913/1913 green. Section 2.2 updated to reflect the new state.

**R2 Status:** ✅ Use-case migration complete (2026-06-24, commit 3d79500). `AccumulationScreenUseCase._composite_score()` deleted; `SwingAnalysisWorkflowUseCase` gains `signal_assessment` field. `CompositeSignalScore` VO removed. 1914 tests green.

**R3 (Code Review) Status:** ✅ All 4 post-R2 code review findings fixed (2026-06-24, commit 3d79500). ADR compliance: `AccumulationScreenUseCase` now injects `SignalEngine` directly. Double computation eliminated (fast-path reuse). `breakdown_dict` consistency fix. `coverage_warning` surfaced in swing display.

**Code Review Status:** ✅ All 10 confirmed findings fixed (2026-06-24). See Section 5b for the fix record.

---

## 1. Executive Summary

The codebase now has two production-ready first-class engines: **RiskEngine** (ADR-024, Phases A–F complete, 102 tests) and **SignalEngine** (ADR-025, R1 complete 2026-06-24, 50 tests). The stated vision of "two first-class engines that all features center on" is architecturally realized — both engines exist, are injectable, and are independently testable. Ten code review findings covering gate wiring parity, backtest look-ahead bias, and broker flow data correctness were also fixed in the same session (Section 5b).

The remaining work to fully center all features on the two engines:

1. Six major features still bypass both engines (pre-open screener, sentiment, regime, charts, intraday, strategy backtest)
2. No learning loop exists for swing-domain risk/signal tuning
3. AI role is still passive (read-only explainer; no tuning or parameter-suggestion capacity)
4. Risk profile thresholds are hardcoded Python, not YAML-configurable
5. Backtest results are disconnected from gate parameter optimization
6. ADR-014 (Full-AI Mode) is an orphaned empty stub that should be formally closed

Six IDX-specific market microstructure items are also missing from the professional-grade bar: auto-rejection band awareness, T+2 settlement risk, foreign ownership cap saturation, regime-driven gate tightening, BandarGate score granularity, and tick-size compliance in PositionSizer.

**ADR layer is complete.** ADRs 002, 010, 014, 024 have been revised; ADRs 025–028 have been added to `ARCHITECTURE_DECISIONS.md` (2026-06-24). The binding contracts for all planned work are in place.

**R1 is complete.** `SignalEngine`, `SignalAssessment`, `SignalContext`, `AssessSignalUseCase`, and `create_signal_engine()` factory are all implemented and tested (2026-06-24). The remaining use-case migration work (R2: delegate `AccumulationScreenUseCase._composite_score()` and `SwingAnalysisWorkflowUseCase` inline assembly to `SignalEngine`) is the immediate next priority.

**R2 complete (2026-06-24):** `AccumulationScreenUseCase._composite_score()` deleted; both use cases delegate to `SignalEngine`. `CompositeSignalScore` removed. R3 code review fixes also applied (ADR compliance, double computation, `breakdown_dict`, `coverage_warning` display).

**Recommended next action:** Phase 2 — Risk+Signal Pipeline Composition (`CombinedAssessment`, `ActionRecommendation`, ADR-026). See Section 5 Phase 2.

---

## 2. Current State Assessment

### 2.1 Risk Engine — What We Have

**Status: Production-ready ✅** (Phases A–F complete, 2026-06-24)

The Risk Engine is a well-designed 3-tier gate pipeline:

```
Tier 1+2: Structural Gates (run BEFORE technical rules)
  ├── FundamentalGate   — Piotroski F-score ≤ 3 → HIGH_RISK
  ├── LiquidityGate     — MarketCap < 1T IDR OR 20d median tx < 5B IDR → HIGH_RISK
  └── FreeFloatGate     — individual% + institution% < 15% → HIGH_RISK

  ↓ (structural gates pass)

Tier 2: Technical Rules (profile-specific RSI + EMA/SMA thresholds)
  ├── ConservativeRuleSet  — RSI > 75 / < 25; EMA/SMA ≥ 1%; BOTH must agree
  ├── BalancedRuleSet      — RSI > 70 / < 30; any divergence; majority rules
  └── AggressiveRuleSet    — RSI > 60 / < 40; EMA/SMA ≥ 0.1%; either can signal

  ↓ (technical rules complete)

Tier 3: Execution Gates (run AFTER technical rules)
  └── BandarGate  — 5-day distribution while LOW_RISK → downgrade to MODERATE
```

**Key files:**
- `src/domain/rules/` — gate implementations (4 gates), rule sets (3 profiles), `RuleEngine`
- `src/domain/value_objects/risk_assessment.py` — immutable output
- `src/application/use_case/assess_risk_use_case.py` — orchestration
- `src/application/services/risk_engine.py` — first-class service (ADR-024)
- `src/application/services/bootstrap.py` — `create_risk_engine()` factory

**Remaining gaps in the Risk Engine (even as-built):**
- Gate thresholds are hardcoded in Python — not exposed to `config/default.yaml` or profile YAML
- No per-profile gate weight or confidence weighting; all gates are binary triggers
- BandarGate treats the -9 to +9 Stockbit score as binary (`< 0` = distributing), ignoring magnitude
- No regime-awareness: JKSE RISK_OFF doesn't tighten F-score threshold or liquidity floor
- No `as_of_date` passed through in `assess()` self-fetch path (only `assess_with_context()` path has temporal integrity)

---

### 2.2 Signal Engine — R1 Complete ✅ (2026-06-24)

**Status: Production-ready ✅** (R1 complete, 50 tests, 1913/1913 suite green)

The Signal Engine is now a first-class application service parallel to RiskEngine. It implements 6-factor composite scoring with graceful degradation when enrichment data is missing.

**New files created in R1:**

| File | Role |
|------|------|
| `src/domain/value_objects/signal_assessment.py` | `SignalStrength` enum, `EntryQuality` enum, `SignalContext` frozen dataclass (10 fields), `SignalAssessment` frozen dataclass |
| `src/application/use_case/assess_signal_use_case.py` | Pure computation — 6-factor weighted scoring, no IO, no providers |
| `src/application/services/signal_engine.py` | First-class service, mirrors `risk_engine.py`; 5 optional enrichment providers |
| `src/application/services/bootstrap.py` | `create_signal_engine(db_path, with_enrichment=False)` factory added |

**Signal factor weights (configurable in YAML — Phase 3):**

| Factor | Weight | Data source |
|--------|--------|-------------|
| Bandar accumulation intensity | 0.20 | `StockbitBandarDetectorProvider` (dynamic range `(3+n)*2`) |
| Foreign flow quality | 0.20 | `StockbitForeignFlowProvider` (0.0–1.0 pre-normalized) |
| Piotroski F-score | 0.20 | `StockbitFundamentalsProvider` (0–9 → 0–100) |
| Seasonality edge | 0.15 | `StockbitSeasonalityProvider` (tailwind/headwind/neutral) |
| Analyst consensus | 0.15 | `StockbitAnalystConsensusProvider` (buy% × 60 + upside/30 × 40) |
| Forward P/E valuation | 0.10 | `StockbitForwardEstimatesProvider` (smooth interpolation 5 bands) |

**Output:** `SignalAssessment(score: int, strength: SignalStrength, entry_quality: EntryQuality, breakdown: tuple[tuple[str, float], ...], rationale: tuple[str, ...])`

**Key design decisions:**
- `breakdown` is `tuple[tuple[str, float], ...]` not `dict` — keeps frozen dataclass hashable without `__hash__` override
- Coverage warning fires at ≥3/6 factors missing (neutral 50 applied)
- `bandar_max_range` is dynamic: `(3 + num_optional) * 2` where num_optional counts non-None `top3/5/10_accdist` fields

**R2 complete — all migration targets resolved (2026-06-24, commit 3d79500):**
- ✅ `AccumulationScreenUseCase._composite_score()` deleted; `signal_engine.evaluate_with_context()` is the call site
- ✅ `SwingAnalysisWorkflowUseCase` injects `SignalEngine`; response carries `signal_assessment` field
- ✅ `CompositeSignalScore` VO deleted; single scoring system via `SignalAssessment`
- ✅ ADR compliance fix (R3): `AccumulationScreenUseCase` injects `SignalEngine` (not `AssessSignalUseCase`)
- ✅ Double computation eliminated (R3): workflow fast-path reuses `candidate.signal_assessment`

---

### 2.3 Feature Alignment Map

The table below maps every major CLI command group to whether it routes through the two engines:

| Feature / Command | Routes through SignalEngine | Routes through RiskEngine | Verdict |
|-------------------|--------------------------|--------------------------|---------|
| `analyze risk` | ✗ | ✅ (via `create_risk_engine()`) | Partial — Phase 2 |
| `analyze swing` | ✅ (R2 done, 2026-06-24) | ✅ (all 3 gates, fixed 2026-06-24) | ✅ Both aligned |
| `screen accum` | ✅ (R2 done, 2026-06-24) | ✅ (post-screen funnel, all 3 gates) | ✅ Both aligned |
| `screen pre-open` | ✗ (own scoring system) | ✗ | ❌ Not aligned |
| `analyze regime` | ✗ (standalone) | ✗ | ❌ Not aligned |
| `analyze sentiment` | ✗ (standalone) | ✗ | ❌ Not aligned |
| `analyze chart` | ✗ | ✗ | ❌ Not aligned |
| `learn snapshot/track/grade/tune` | ✗ (intraday-only loop) | ✗ | ❌ Not aligned |
| `trade swing-backtest` | ✗ (preset rule replay) | ✗ (no gate integration) | ❌ Not aligned |
| `trade intraday-backtest` | ✗ | ✗ | ❌ Not aligned |
| `indicator compute/snapshot` | ✗ (raw math only) | ✗ | Deliberate (fine) |
| `strategy backtest` | ✗ | ✗ (no gate integration) | Partial gap |
| `view ticker` | ✗ | ✗ (cached data view) | Deliberate (fine) |
| `analyze compare` | ✗ | ✅ (via `create_risk_engine()`) | Partial — Phase 2 |

**Interpretation:** "Phase 2" means the engine is wired but the use case has not yet been migrated to compose both engine outputs via `CombinedAssessment` (ADR-026). "Not aligned" means the feature has its own parallel logic with no delegation path. "`analyze swing`" and "`screen accum`" are now fully aligned (R2+R3, 2026-06-24).

---

## 3. Vision Alignment Gaps (Findings)

### Gap 1: Signal Engine Did Not Exist — ✅ RESOLVED (2026-06-24)

**Severity: Was Critical — now resolved**

`SignalEngine` is now a self-sufficient, injectable, testable application service parallel to `RiskEngine`. Both engines follow the same pattern: context object pre-loading, optional provider injection, factory in `bootstrap.py`, frozen immutable output value object.

**Resolved by R1 (2026-06-24):**
- `src/domain/value_objects/signal_assessment.py` — `SignalAssessment`, `SignalContext`, `SignalStrength`, `EntryQuality`
- `src/application/use_case/assess_signal_use_case.py` — pure scoring logic (no IO)
- `src/application/services/signal_engine.py` — first-class service with 5 optional enrichment providers
- `src/application/services/bootstrap.py` — `create_signal_engine()` factory
- `tests/application/use_case/test_assess_signal.py` — 50 unit tests

**R2+R3 complete (2026-06-24, commit 3d79500):**
- ✅ `AccumulationScreenUseCase._composite_score()` deleted; delegates to `SignalEngine.evaluate_with_context()`
- ✅ `SwingAnalysisWorkflowUseCase` injects `SignalEngine`; fast-path reuses `candidate.signal_assessment`
- ✅ Single scoring system: `CompositeSignalScore` removed, `SignalAssessment` is the single source of truth
- ✅ ADR compliance: both use cases inject `SignalEngine` (not `AssessSignalUseCase`)

---

### Gap 2: Six Features Bypass Both Engines Entirely

**Severity: High — architectural drift accumulates as features grow**

Six command groups implement their own parallel logic without connecting to the emerging engine layer:

**a) Pre-open screener (`screen pre-open`, `src/application/use_case/pre_open_screen_use_case.py`)**
Has its own scoring and ranking logic (order book pressure, IEV, spread) that is structurally similar to what a SignalEngine should compute for the intraday domain. There is no risk engine integration at all for intraday candidates — a high-conviction pre-open pick could have a Piotroski F-score of 2 and no gate would fire.

**b) `analyze regime` (`src/application/use_case/market_regime_use_case.py`)**
Computes JKSE regime (BULLISH/SIDEWAYS/WEAK/RISK_OFF) as a standalone result. This regime output is the most important context modifier for both engines — an aggressive setup in a RISK_OFF regime should have tightened gate thresholds — but it is never fed into either engine. The regime is computed but then thrown away by the CLI adapter.

**c) `analyze sentiment` (`src/application/use_case/fetch_sentiment_use_case.py`)**
News sentiment (BULLISH/NEUTRAL/BEARISH) is a legitimate signal factor for the signal engine, especially for event-driven accumulation. Currently it is a standalone CLI command. Feeding it into `SignalEngine` as an optional context modifier (parallel to `GateContext` for `RiskEngine`) would align it with the vision.

**d) `analyze chart` commands**
Chart commands are pure visualization. They could overlay signal engine output (entry zone, strength) on price charts, but currently there is no integration point. This is lower priority but represents a UX alignment gap.

**e) `learn snapshot/track/grade/tune` (opening learning loop)**
The `learn` command group implements a sophisticated learning loop — but only for the intraday pre-open domain. It snapshots order book predictions at 08:57, tracks through 09:30, grades accuracy, and prompts AI config suggestions. This exact pattern — snapshot → track → grade → tune — is what the swing signal/risk engines need but don't have.

**f) `strategy backtest` and `trade swing-backtest`**
Backtesting runs strategy YAML rules against historical candles and reports win rate, Sharpe, max drawdown. But gate evaluation (FundamentalGate, LiquidityGate, etc.) is not applied in the backtest run — meaning a strategy's historical performance is overstated if it would have hit gates in real evaluation. The backtest and the engine are measuring different things.

**Recommendation:** Once Signal Engine exists, feed regime into both engines as `MarketRegimeContext` parameter. Feed sentiment into Signal Engine as optional `SentimentContext`. Integrate gate evaluation into backtest runs so historical performance reflects real engine behavior.

---

### Gap 3: No Learning Loop for Swing Risk/Signal Engines

**Severity: High — the system cannot self-improve on its primary use case**

The pre-open learning loop (`learn` commands) is the best piece of adaptive infrastructure in the codebase. It proves the concept. But the swing domain — where the risk and signal engines live — has no equivalent.

**What is missing:**
- A `SwingSignalJournal` that records: ticker, date, signal score, risk level, gate triggered, entry price
- A grading mechanism: after N trading days, compare forward return vs. journal entry
- Attribution: which gate fired on losing trades? which signal component led on winning trades?
- A tuning prompt: AI-assisted suggestion of gate threshold adjustments based on attribution
- An apply mechanism: write suggested thresholds back to a profile config YAML

**Professional-grade analogy:** Bloomberg PORT's alpha/risk attribution model does exactly this — tracks every factor contribution to realized P&L and suggests factor exposure adjustments. QuantConnect's Lean engine records every signal with its indicators and lets you backtest parameter sweeps on historical signal accuracy.

**Current state:** `journals/accumulation.csv` exists as a signal journal, and `journals/trades.jsonl` tracks entries/exits. But there is no mechanism to connect journal outcomes back to engine parameters.

**Recommendation:** Design `SwingLearningLoop` as an application service with four phases (parallel to `learn` commands): `grade_signal_history()`, `attribute_to_gates()`, `prompt_adjustment()`, `apply_tuning()`. This is ADR-027 territory.

---

### Gap 4: AI Role Is Too Passive

**Severity: Medium — long-term capability constraint**

The current AI role in the system:
- `ExplainRiskUseCase` — reads pre-computed `RiskAssessment`, generates narrative explanation (read-only)
- `CreateStrategyFromIntentUseCase` — generates YAML from natural language
- `CreateIndicatorFromIntentUseCase` — generates formula from description
- `OpeningPromptUseCase` — suggests intraday config changes from grading data (closest to tuning)
- `FetchSentimentUseCase` — classifies news headlines

ADR-002 says: "AI may assist explanation, exploration, or augmentation." It does not address AI as a **parameter tuner** — taking historical performance data (gate attribution, signal accuracy, forward return distribution) and proposing concrete threshold updates to `config/swing_screener.yaml` or gate Python classes.

**What is missing:**
- An `AI Tuner` role (between explainer and decision-maker): AI reads historical attribution data + current thresholds → proposes revised thresholds → human approves → system applies
- This is different from AI-as-decision-maker (which is correctly rejected by the architecture)
- The tuner produces *proposed config*, not *live decisions*. The human gate remains.

**Three-tier AI model for these engines:**

| Tier | Role | Current | Gap |
|------|------|---------|-----|
| T1: Explainer | Narrates pre-computed results | ✅ `ExplainRiskUseCase` | None |
| T2: Tuner | Proposes parameter changes from historical data | Partial (`OpeningPromptUseCase` for intraday only) | Swing domain missing |
| T3: Proposer | Generates new gate logic or signal factors from research | ✅ `CreateStrategyFromIntentUseCase` | Not wired to engines |

**Recommendation:** Extend T2 to swing domain. Add `SwingSignalTunerUseCase` that takes gate attribution summary → calls `AIExplainer` with structured tuning prompt → returns proposed `config/swing_screener.yaml` diff → user applies with `learn tune` equivalent. This keeps human in the loop; AI never applies changes autonomously.

---

### Gap 5: Risk Profiles Use Hardcoded Python Thresholds

**Severity: Medium — prevents easy calibration**

Current profile thresholds are hardcoded in Python:

```python
# src/domain/rules/conservative.py
_RSI_HIGH_RISK = 75
_RSI_LOW_RISK = 25
_EMA_SMA_MIN_DIVERGENCE_PCT = Decimal("1")  # 1%

# src/domain/rules/balanced.py
_RSI_HIGH_RISK = 70
_RSI_LOW_RISK = 30
_EMA_SMA_MIN_DIVERGENCE_PCT = Decimal("0")

# src/domain/rules/aggressive.py
_RSI_HIGH_RISK = 60
_RSI_LOW_RISK = 40
_EMA_SMA_MIN_DIVERGENCE_PCT = Decimal("0.1")
```

Gate trigger thresholds (`Piotroski ≤ 3`, `MarketCap < 1T`, `20d median tx < 5B IDR`, `free_float_pct < 15%`) are hardcoded in gate classes. The `BandarGate` threshold (`bandar_is_distributing`) is a hardcoded boolean derived from `five_day_accdist < 0`.

**To support the learning loop and backtesting feedback loop, thresholds must be configurable at runtime.** A calibrated IDX profile might need RSI HIGH_RISK at 72 (not 70) after discovering that IDX stocks in accumulation can sustain RSI above 70 for weeks due to thin float + institutional support.

**Recommendation:** Read gate thresholds from `config/swing_screener.yaml` (already partially used for smart money brokers and preset gates). ADR-010 should be revised to mandate config-driven thresholds with code defaults as fallback.

---

### Gap 6: Backtest Results Are Disconnected from Gate Evaluation

**Severity: Medium — performance measurement is inaccurate**

`trade swing-backtest` (`SwingBacktestUseCase`) runs presets against historical candles and applies strategy rules. But gate evaluation (FundamentalGate, LiquidityGate, BandarGate, FreeFloatGate) is NOT applied during the backtest run.

**Consequence:** A strategy's backtested win rate is measured on ALL candidates that pass the screening rules, including candidates that would have been filtered by a HIGH_RISK gate in live evaluation. The backtested performance is optimistic compared to live.

**Professional-grade practice:** QuantConnect's Lean Engine and WorldQuant's platform both apply risk model filters during backtesting to ensure the simulated performance reflects the live signal-and-risk pipeline. The rule is: if the gate would fire in live, it must fire in backtest.

**Recommendation:** Pass `RiskEngine` into `SwingBacktestUseCase` and apply gate evaluation on each candidate during the walk-forward loop. Add a `--no-gates` flag for raw signal performance comparison. This also creates a natural gate attribution data source: track which candidates survived vs. were gated, and what their forward returns were.

---

### Gap 7: ADR-014 (Full-AI Mode) Is Orphaned

**Severity: Low — confusion risk, no runtime impact**

ADR-014 was added as a forward-looking decision: "the system may support a future Full-AI Mode where AI-generated analysis can bypass rule-based logic." Current status:
- `config/full_ai.yaml` exists but contains only a single-line stub (filename, nothing else)
- Zero code references to full_ai.yaml anywhere in the codebase
- No implementation started
- The concept ("bypass rule-based logic") contradicts the project's core mission statement

The project's stated philosophy is: "AI → YAML → Validator → Registry → Runtime. A compiler where AI writes source code." Full-AI Mode (bypass mode) is the opposite of this. The canonical position, repeated in CLAUDE.md and DEFINITION_OF_DONE.md, is that AI is advisor, not decision-maker.

**Recommendation:** Formally close ADR-014 as REJECTED. Replace it with ADR-027 (Learning Loop) which captures the legitimate version of "AI-enhanced mode" — AI proposes config changes from historical performance data, human approves.

---

## 4. IDX Market Professional-Grade Gaps

This section covers Indonesia-specific market structure rules that professional-grade IDX tools enforce but the current codebase does not.

### 4.1 Auto-Rejection Band Proximity

**IDX rule:** Automatic rejection of orders outside ±35% of previous close (for stocks priced ≥ Rp 200) or ±25% (for stocks priced < Rp 200). This is the hard ceiling for single-day moves.

**Current gap:** Neither the Risk Engine nor any gate flags when a stock is within N% of its auto-rejection ceiling. This matters for momentum plays and gap-open intraday setups where you could be holding a position that can't exit without hitting the limit.

**Recommended addition:** A new `AutoRejectionGate` or a flag in `GateContext.price_vs_rejection_band_pct`. Add to `LiquidityGate` as a secondary check or as a separate advisory flag (non-blocking; just adds to rationale).

### 4.2 T+2 Settlement Risk in Thin Float Stocks

**IDX rule:** Indonesia uses T+2 settlement (trade date + 2 business days). For stocks with free float < 20%, short-term settlement pressure can create forced selling at T+2 if a large player exits.

**Current gap:** `FreeFloatGate` triggers on free_float_pct < 15% but doesn't distinguish between settlement risk scenarios. A 14% free float in a stock with high foreign ownership near its cap is categorically different from 14% in a stock where the promoter holds everything.

**Recommended addition:** Extend `GateContext` to include `foreign_ownership_pct` (from `StockbitShareholdingProvider`). `FreeFloatGate` should check: if `foreign_ownership_pct > 40%` AND `free_float_pct < 20%` → settlement risk flag in rationale.

### 4.3 Foreign Ownership Cap Saturation

**IDX rule:** Most IDX stocks have a 49% foreign ownership cap. Banking, media, and strategic sectors have lower caps (33% or sector-specific). Near-cap saturation means future foreign buying is constrained, which is bearish for stocks that depend on foreign flows as a signal.

**Current gap:** `FreeFloatGate` checks float structure but doesn't check foreign ownership cap proximity. An accumulation signal driven by foreign buying loses conviction if foreign ownership is at 47% of a 49% cap — there are almost no more foreign buyers who can enter.

**Recommended addition:** A `ForeignCapGate` or cap proximity flag. Requires adding `foreign_ownership_cap_pct` to `GateContext` (hardcoded by sector or fetched from IDX sector data). Gate fires when `foreign_ownership_pct / foreign_ownership_cap_pct > 0.92` (within 8% of cap) and primary signal driver is foreign flow.

### 4.4 JKSE Regime → Gate Threshold Tightening

**Professional practice:** In bear markets and crisis periods, structural risk thresholds tighten. Bloomberg PORT uses a regime-conditional risk model: factor volatility estimates expand in HIGH_VOL regimes, causing more positions to breach risk limits.

**Current gap:** The `market_regime_use_case.py` computes JKSE regime (BULLISH/SIDEWAYS/WEAK/RISK_OFF) but this output is never passed to `RiskEngine` or `SignalEngine`. A LOW_RISK assessment in RISK_OFF regime is inappropriate — during RISK_OFF, even "safe" stocks drop 20%+ with IHSG.

**Recommended addition:** `AssessRiskRequest` accepts optional `market_regime: str | None`. `RuleEngine` adjusts thresholds based on regime:
- RISK_OFF: F-score threshold tightens (≤ 3 → ≤ 4), RSI HIGH_RISK threshold drops (e.g., Aggressive: 60 → 55)
- BULLISH: thresholds relax slightly toward Balanced behavior
- Regime is advisory, not a gate; modifies thresholds, doesn't add a new tier

### 4.5 BandarGate Score Granularity

**Current gap:** `BandarGate` uses `bandar_is_distributing: bool` which is `True` when `five_day_accdist < 0`. The Stockbit bandar score ranges from -9 (heavy distribution) to +9 (heavy accumulation). A score of -1 (slight distribution) and -9 (heavy distribution) both trigger the gate identically.

**IDX-specific context:** In Indonesia, "bandar" (large operators, market makers, or block traders) behavior is more concentrated than in developed markets due to thin float and low institutional diversity. A -9 bandar score is a genuine "exit trap" signal, while -1 might be normal day-to-day noise.

**Recommended revision:** Change `GateContext.bandar_is_distributing: bool` to `GateContext.bandar_five_day_score: int | None` (-9 to +9). `BandarGate` configures a threshold (`bandar_distribution_threshold: int = -2`, configurable in profile YAML). Only scores ≤ threshold trigger the downgrade. -1 becomes noise; -5 is a genuine gate trigger.

### 4.6 Tick Size Compliance in PositionSizer

**IDX tick sizes (effective):**
| Price Range | Tick Size |
|-------------|-----------|
| < Rp 200 | Rp 1 |
| Rp 200 – Rp 499 | Rp 2 |
| Rp 500 – Rp 1,999 | Rp 5 |
| Rp 2,000 – Rp 4,999 | Rp 10 |
| ≥ Rp 5,000 | Rp 25 |

**Current gap:** `src/application/services/position_sizer.py` computes entry price, stop loss, and target levels. These levels are not rounded to the nearest IDX tick. A computed stop loss of Rp 1,432 is invalid on IDX — the nearest valid tick is Rp 1,430 (rounding down to valid Rp 5 tick). Submitting an Rp 1,432 order would be auto-adjusted by the exchange, changing the risk/reward ratio.

**Recommended addition:** A `round_to_tick(price: Decimal) -> Decimal` pure function in `src/domain/value_objects/` (analogous to `price_floor.py`). Used in `PositionSizer` for all computed price levels. This is a pure domain function with no external dependencies.

---

## 5. ADR Changes (Applied 2026-06-24)

All ADR changes below have been committed to `ARCHITECTURE_DECISIONS.md`. This section records what changed and why.

### 5.1 ADRs Revised

#### ADR-002: Rule-First, AI-Optional Design — REVISED ✅

**What changed:** Added the three-tier AI model (T1 Explainer / T2 Tuner / T3 Proposer) with explicit constraints for each tier. The previous text ("AI may assist explanation, exploration, or augmentation") left the T2 Tuner role undefined — AI proposing config parameter changes from historical attribution data was neither permitted nor prohibited. The revision formally permits T2 with a clear human-in-the-loop constraint: AI proposes, human approves, AI never applies autonomously.

**Key addition:** "T2 Tuner: AI reads historical attribution summaries and proposes a YAML config diff. Proposed changes require explicit human approval. AI never applies changes autonomously."

---

#### ADR-010: Risk Profiles as Policy Layer — REVISED ✅

**What changed:** Expanded from 3 bullet points to a full specification. Added:
- Threshold table for all three built-in profiles (RSI high/low, EMA/SMA divergence, decision logic)
- Mandate that thresholds are read from `config/swing_screener.yaml` at startup; Python constants are defaults only
- Mandate that gate trigger levels (F-score cutoff, market cap floor, liquidity floor, free float minimum, bandar distribution threshold) are configurable per profile in YAML
- YAML schema validation at startup (invalid config aborts, no silent fallback)
- Regime-conditional threshold tightening reference (ADR-026)

---

#### ADR-014: Full-AI Mode (Explicit Bypass Mode) — REJECTED ✅

**What changed:** Status changed from DEFERRED to REJECTED. `config/full_ai.yaml` should be deleted (empty 1-line stub, zero code references).

**Why rejected:** "Bypass rule-based logic" contradicts the project's core philosophy. The legitimate use case (AI-enhanced analysis) is fully covered by ADR-002 T2 Tuner and ADR-027 Learning Loop. An indefinitely deferred ADR with an empty config stub creates confusion for future agents about what is permitted.

---

#### ADR-024: Signal Engine and Risk Engine as First-Class Application Services — REVISED ✅

**What changed:** Expanded from RiskEngine-only documentation to symmetric coverage of both engines. Added:
- Full `SignalEngine` interface definition (entry points, factory, context object)
- `SignalAssessment` output specification
- Signal factor weights and configurability mandate
- Orthogonality rule explicitly stated (neither engine reads the other's output)
- Removed the note "accumulation score logic stays in `AccumulationScreenUseCase` until a future `SignalEngine` is formalised" — that holdover is now a migration target, not an accepted design

---

### 5.2 New ADRs Added ✅

| ADR | Title | Status |
|-----|-------|--------|
| ADR-025 | SignalEngine Architecture | Added ✅ |
| ADR-026 | Risk+Signal Pipeline Composition | Added ✅ |
| ADR-027 | Risk/Signal Learning Loop | Added ✅ |
| ADR-028 | IDX Market Microstructure Rules | Added ✅ |

**ADR-025** defines `SignalEngine` as a first-class service: interface, value objects (`SignalAssessment`, `SignalContext`, `SignalStrength`, `EntryQuality`), default factor weights, factory pattern, and migration targets in `AccumulationScreenUseCase`.

**ADR-026** defines how both engine outputs compose into a `CombinedAssessment` with `ActionRecommendation` (ENTER/WATCH/AVOID/BLOCKED). The composition rule is deterministic domain logic. BLOCKED (HIGH_RISK) always overrides any signal strength. Regime (RISK_OFF/WEAK) downgrades ENTER to WATCH.

**ADR-027** defines the swing learning loop — four phases (record/grade/attribute/tune), journal schema, attribution minimum sample size (30), AI Tuner constraints, and persistence paths. Parallel to the existing pre-open learning loop.

**ADR-028** defines six IDX microstructure rules: tick size compliance (`round_to_tick()` pure domain function), auto-rejection band proximity in `GateContext`, foreign ownership cap saturation in `SignalContext`, BandarGate score granularity (`bandar_five_day_score: int` replacing `bandar_is_distributing: bool`), and T+2 settlement risk advisory in `FreeFloatGate`.

---

## 5b. Code Review Fixes (Applied 2026-06-24)

All 10 findings from the post-R1 code review were confirmed and fixed in the same session. Listed by severity.

### Critical — Gate Wiring Parity (Findings #1, #2, #3)

`FreeFloatGate` was wired in `analyze risk` but missing from two other command sites, causing thin-float stocks to be assessed as LOW_RISK by the screener and the swing workflow while `analyze risk` would correctly flag them HIGH_RISK.

| Finding | File | Fix |
|---------|------|-----|
| #1 | `src/adapters/cli/screen_accum_commands.py:359` | Added `FreeFloatGate()` to `structural_gates` list |
| #2 | `src/adapters/cli/analyze_swing_commands.py:709` | Added `FreeFloatGate()` to `structural_gates` list |
| #3 | `src/application/use_case/swing_analysis_workflow_use_case.py:187` | Added `free_float_pct=shareholding.free_float_pct if shareholding else None` to `GateContext` constructor (gate was in the list but always saw `None`) |

### High — Backtest Look-Ahead Bias (Findings #4, #5)

| Finding | File | Fix |
|---------|------|-----|
| #4 | `src/application/services/risk_engine.py` | `_build_gate_context(ticker, as_of_date=None)` now passes `as_of_date` to `get_fundamentals()` and `get_composition()` provider calls; `assess()` forwards its `as_of_date` argument through |
| #5 | `src/application/use_case/assess_risk_use_case.py:316` | `get_candles()` now called with `end_date=snapshot_date` to prevent future candles leaking into LiquidityGate input during backtest |

### Medium — Broker Flow Data Correctness (Findings #6, #7, #8, #9)

| Finding | File | Fix |
|---------|------|-----|
| #6 | `src/application/use_case/fetch_broker_daily_flows_use_case.py` | `refresh=True` now bypasses date filter entirely (`if request.refresh or before_max_date is None: new_flows = flows`) — corrupted rows can now be overwritten |
| #7 | Same file | Changed `f.date > before_max_date` to `f.date >= before_max_date` — new broker codes on the already-stored max date are no longer silently dropped |
| #8 | `src/application/use_case/assess_risk_use_case.py` (execute_all_profiles) | Structural gate override changed from `rationale=(gate_result.reason,)` to `rationale=(gate_result.reason, *a.rationale)` — profile-specific technical signals are preserved, not discarded |
| #9 | `fetch_broker_daily_flows_use_case.py` | `active_codes` now counts from full provider response (`flows`) not just newly-added rows (`new_flows`) — incremental runs no longer undercount active broker codes |

### Low — Dead Code (Finding #10)

| Finding | File | Fix |
|---------|------|-----|
| #10 | `src/application/use_case/assess_signal_use_case.py` | Removed `_ENTER_THRESHOLD = 65` and `_WATCH_THRESHOLD = 40` — never read; `_classify_entry()` dispatches on `SignalStrength` enum |

**Tests added:**
- `tests/application/use_case/test_assess_risk_gates.py` — added `test_structural_gate_preserves_technical_rationale_in_all_profiles` (Fix #8)
- `tests/application/use_case/test_fetch_broker_daily_flows.py` — 10 new tests covering all three broker flow fixes (#6, #7, #9)
- Full suite: 1913/1913 green after all fixes applied

---

## 6. Recommended Architecture

### 6.1 Signal+Risk Pipeline (Both Engines Composing)

```
                    ┌─────────────────────────────┐
                    │         CLI Command          │
                    │  (screen accum / analyze      │
                    │   swing / analyze risk / etc.)│
                    └────────────┬────────────────┘
                                 │ builds request
                    ┌────────────▼────────────────┐
                    │      Application Layer       │
                    │  (use case orchestration)    │
                    │                              │
                    │  ┌──────────────────────┐   │
                    │  │ Pre-loaded context:  │   │
                    │  │ enrichment data from │   │
                    │  │ providers (once)     │   │
                    │  └──────┬───────────────┘   │
                    │         │                    │
                    │  ┌──────▼──────┐  ┌────────▼──────┐  │
                    │  │SignalEngine │  │  RiskEngine   │  │
                    │  │evaluate()  │  │  assess()     │  │
                    │  └──────┬─────┘  └───────┬───────┘  │
                    │         │                │           │
                    │  ┌──────▼────────────────▼───────┐  │
                    │  │      CombinedAssessment        │  │
                    │  │  decide() → ActionRecommend.   │  │
                    │  └───────────────────────────────┘  │
                    └────────────────────────────────────┘
                                 │
                    ┌────────────▼──────────────┐
                    │   Display Layer (CLI)      │
                    │ signal_display.py          │
                    │ risk_display.py            │
                    └───────────────────────────┘
```

**Key principle:** Both engines receive the same pre-loaded context (enrichment data fetched once). Neither engine fetches its own data in the screener/workflow path — they accept `*Context` objects. Self-fetch (`assess()` without context) is available for single-ticker commands.

### 6.2 Engine Configurability (YAML-Driven)

```yaml
# config/swing_screener.yaml — extended

risk_engine:
  profiles:
    conservative:
      rsi_high_risk: 75
      rsi_low_risk: 25
      ema_sma_min_divergence_pct: 1.0
      fundamental_gate:
        f_score_threshold: 3          # ≤ threshold → HIGH_RISK
      liquidity_gate:
        market_cap_floor_idr: 1_000_000_000_000   # 1T IDR
        median_tx_floor_idr: 5_000_000_000        # 5B IDR
      free_float_gate:
        min_free_float_pct: 15.0
      bandar_gate:
        distribution_threshold: -2    # score ≤ this → gate fires
    balanced:
      rsi_high_risk: 70
      ...

signal_engine:
  weights:
    bandar_intensity: 0.20
    foreign_flow_quality: 0.20
    piotroski_score: 0.20
    seasonality_edge: 0.15
    analyst_consensus: 0.15
    forward_eps_valuation: 0.10
  thresholds:
    strong: 70         # score ≥ 70 → STRONG
    moderate: 45       # score ≥ 45 → MODERATE
    enter: 65          # entry_quality ENTER threshold
    watch: 40          # entry_quality WATCH threshold
```

Both engines read from this config at startup via `yaml_loader.py`. Python constants become defaults only. The learning loop proposes diffs to this file.

### 6.3 AI Integration Tiers (Layered, All Optional)

```
T1: Explainer (today — exists)
    Input:  RiskAssessment + IndicatorSnapshot
    Output: Natural language narrative
    File:   src/application/use_case/explain_risk_use_case.py ✅

T2: Tuner (build next — swing domain)
    Input:  SwingSignalAttributionSummary (gate hit rates, win/loss correlation)
    Output: Proposed config YAML diff (threshold changes, weight adjustments)
    File:   src/application/use_case/swing_signal_tuner_use_case.py (new)
    Note:   AI proposes; human approves via `swing learn tune --apply`

T3: Proposer (exists for strategy/formula — extend to engine components)
    Input:  Natural language description of desired signal behavior
    Output: New gate class skeleton or new signal factor definition
    File:   src/application/use_case/create_strategy_from_intent_use_case.py ✅
    Note:   Extension to signal factor generation
```

All three tiers must fail gracefully — no AI call may block engine evaluation.

### 6.4 Learning Loop Design (Swing Domain)

```
Day 0 (trade entry):
  swing learn record --ticker BBCA --entry 9100
  → Records: SignalAssessment + RiskAssessment + entry price + date
  → Persists to journals/swing_signal_outcomes.jsonl

Day 5+ (after holding period):
  swing learn grade --days 5
  → Reads journals/swing_signal_outcomes.jsonl
  → Fetches forward returns for each recorded entry
  → Computes: outcome (WIN/LOSS/NEUTRAL), return_pct, max_favorable, max_adverse

  swing learn attribute
  → Correlates outcomes with:
    - Gates triggered on losing trades
    - Signal components on winning trades  
    - Entry quality vs. actual outcome
  → Outputs: attribution summary table

  swing learn tune
  → Calls AI Tuner with attribution summary
  → AI proposes: "Consider tightening bandar_distribution_threshold from -2 to -3
     (43% of gated-then-won trades had score -2; -3 would have let them through)"
  → Requires --apply flag + confirmation to write to config

  swing learn history
  → Shows historical accuracy of signal/risk combined assessments
```

**Persistence schema for `journals/swing_signal_outcomes.jsonl`:**
```json
{
  "ticker": "BBCA",
  "entry_date": "2026-06-24",
  "entry_price": 9100,
  "signal_score": 72,
  "signal_strength": "STRONG",
  "risk_level": "LOW_RISK",
  "risk_confidence": 100,
  "gates_triggered": null,
  "action": "ENTER",
  "outcome_date": null,
  "exit_price": null,
  "return_pct": null,
  "outcome": null
}
```

### 6.5 Backtesting Integration

The `SwingBacktestUseCase` must apply gate evaluation during walk-forward simulation:

```python
# Current (wrong — missing gates)
for candidate in candidates:
    if strategy.evaluate(candles_as_of(date)):
        enter_trade(candidate)

# Recommended (gate-aware)
for candidate in candidates:
    if strategy.evaluate(candles_as_of(date)):
        risk = risk_engine.assess_with_context(candidate.ticker, ..., as_of_date=date)
        if risk.risk_level == RiskLevel.HIGH_RISK:
            log_gated(candidate, risk)  # for attribution
            continue
        enter_trade(candidate)
```

Add to `BacktestResult`:
- `gated_count: int` — candidates blocked by gates
- `gated_tickers: list[str]` — which tickers were blocked
- `gate_attribution: dict[str, int]` — how many times each gate fired

This makes the backtested performance reflect the live pipeline, and produces gate attribution data for the learning loop.

---

## 7. Implementation Roadmap

Ordered by dependency and impact.

### Phase 0 — ADR Layer — DONE ✅ (2026-06-24)

ADRs 002, 010, 014, 024 revised; ADRs 025–028 added. Binding contracts for all implementation phases are in place.

Also: delete `config/full_ai.yaml` (1-line empty stub, formally rejected by ADR-014).

---

### Phase 1 — Signal Engine (R1) — DONE ✅ (2026-06-24)

**Reference:** `docs/claude_signal_risk_230626.md` (R1–R3 complete)

| Step | Task | Status |
|------|------|--------|
| R1-1 | Create `SignalAssessment` value object | ✅ `src/domain/value_objects/signal_assessment.py` |
| R1-2 | Create `SignalEngine` application service | ✅ `src/application/services/signal_engine.py` |
| R1-3 | Add `create_signal_engine()` factory | ✅ `src/application/services/bootstrap.py` |
| R1-4 | Write `AssessSignalUseCase` (pure scoring) | ✅ `src/application/use_case/assess_signal_use_case.py` |
| R1-5 | 50 unit tests, full suite green | ✅ `tests/application/use_case/test_assess_signal.py` |
| R2-1 | Migrate `AccumulationScreenUseCase._composite_score()` to delegate | ✅ commit 3d79500 |
| R2-2 | Migrate `SwingAnalysisWorkflowUseCase` signal assembly to delegate | ✅ commit 3d79500 |
| R3-1 | ADR compliance: inject `SignalEngine` (not `AssessSignalUseCase`) | ✅ commit 3d79500 |
| R3-2 | Eliminate double computation (fast-path reuse pattern) | ✅ commit 3d79500 |
| R3-3 | `breakdown_dict` consistency + `coverage_warning` display | ✅ commit 3d79500 |

**Next:** Phase 2 — Risk+Signal Pipeline Composition (`CombinedAssessment`, ADR-026)

### Phase 2 — Risk+Signal Pipeline Composition — IMMEDIATE NEXT

| Step | Task | File |
|------|------|------|
| C-1 | Create `CombinedAssessment` value object | `src/domain/value_objects/combined_assessment.py` |
| C-2 | Create `ActionRecommendation` enum (ENTER/WATCH/AVOID/BLOCKED) | `src/domain/value_objects/action_recommendation.py` |
| C-3 | Wire pipeline into `SwingAnalysisWorkflowUseCase` | existing file |
| C-4 | Wire pipeline into `AccumulationScreenUseCase` | existing file |
| C-5 | Write ADR-026 | `ARCHITECTURE_DECISIONS.md` |

**Estimated effort:** 1.5–2 sessions

### Phase 3 — Config-Driven Gate Thresholds

| Step | Task | File |
|------|------|------|
| D-1 | Extend `config/swing_screener.yaml` schema | `config/swing_screener.yaml` |
| D-2 | Load gate thresholds from YAML in `create_risk_engine()` | `src/application/services/bootstrap.py` |
| D-3 | Load signal weights from YAML in `create_signal_engine()` | `src/application/services/bootstrap.py` |
| D-4 | Change `BandarGate` to use `bandar_five_day_score` | `src/domain/rules/bandar_gate.py` |
| D-5 | Update `GateContext` with `bandar_five_day_score: int | None` | `src/domain/rules/risk_gate.py` |
| D-6 | Revise ADR-010 | `ARCHITECTURE_DECISIONS.md` |

**Estimated effort:** 2 sessions

### Phase 4 — IDX Microstructure Rules

| Step | Task | File |
|------|------|------|
| I-1 | Add `round_to_tick()` pure domain function | `src/domain/value_objects/tick_size.py` |
| I-2 | Apply tick rounding in `PositionSizer` | `src/application/services/position_sizer.py` |
| I-3 | Add `foreign_ownership_pct` to `GateContext` | `src/domain/rules/risk_gate.py` |
| I-4 | Extend `FreeFloatGate` with foreign cap saturation check | `src/domain/rules/free_float_gate.py` |
| I-5 | Add auto-rejection band proximity to `GateContext` | `src/domain/rules/risk_gate.py` |
| I-6 | Write ADR-028 | `ARCHITECTURE_DECISIONS.md` |

**Estimated effort:** 2 sessions

### Phase 5 — Regime Integration

| Step | Task | File |
|------|------|------|
| G-1 | Add `market_regime: str | None` to `AssessRiskRequest` | existing file |
| G-2 | `RuleEngine` adjusts thresholds by regime at evaluation time | `src/domain/rules/rule_engine.py` |
| G-3 | `SwingAnalysisWorkflowUseCase` fetches regime and passes to both engines | existing file |
| G-4 | Revise ADR-002 | `ARCHITECTURE_DECISIONS.md` |

**Estimated effort:** 1.5 sessions

### Phase 6 — Backtest Gate Integration

| Step | Task | File |
|------|------|------|
| B-1 | Inject `RiskEngine` into `SwingBacktestUseCase` | existing file |
| B-2 | Apply gate evaluation in walk-forward loop | existing file |
| B-3 | Add gate attribution to `BacktestResult` | `src/domain/value_objects/backtest_result.py` |

**Estimated effort:** 2 sessions

### Phase 7 — Swing Learning Loop

| Step | Task | File |
|------|------|------|
| L-1 | Create `SwingSignalJournal` service | `src/application/services/swing_signal_journal.py` |
| L-2 | Create `swing learn record` CLI command | new command module |
| L-3 | Create `swing learn grade` CLI command | new command module |
| L-4 | Create `swing learn attribute` with attribution summary | new command module |
| L-5 | Create `SwingSignalTunerUseCase` (AI Tuner T2) | `src/application/use_case/swing_signal_tuner_use_case.py` |
| L-6 | Create `swing learn tune` CLI command | new command module |
| L-7 | Write ADR-027 | `ARCHITECTURE_DECISIONS.md` |

**Estimated effort:** 3–4 sessions

---

## 8. Non-Goals

These items were considered but are explicitly out of scope:

- **Automated trading execution** — the system is an analysis engine, not an algo trader. This remains a hard non-goal from CLAUDE.md.
- **Real-time streaming data** — offline-first mandate (ADR-005) holds. Streaming providers are a future adapter, not an architecture change.
- **Multiple simultaneous strategies in backtest** — portfolio-level simulation is a separate capability; single-strategy backtesting is sufficient for current scope.
- **Z-score normalization of signal factors** (AGY Rec 8) — deferred by design. Requires full domain rewrite. Revisit after signal engine is stable.
- **Factor decorrelation** (AGY Rec 9) — premature at current factor count (6 factors). Revisit at 10+.
- **Macro signals DXY/USD-IDR** (AGY Rec 3) — offline-first mandate means no real-time macro feed. Manual regime proxy via IHSG is sufficient.
- **Web/bot adapters** — stubs exist; priority is engine quality, not adapter proliferation.

---

## Appendix: File Reference Index

| Role | Path | Status |
|------|------|--------|
| **Signal Engine (R1 — NEW)** | | |
| SignalEngine service | `src/application/services/signal_engine.py` | ✅ R1 done |
| SignalAssessment + SignalContext value objects | `src/domain/value_objects/signal_assessment.py` | ✅ R1 done |
| AssessSignalUseCase (pure scoring) | `src/application/use_case/assess_signal_use_case.py` | ✅ R1 done |
| Signal engine tests | `tests/application/use_case/test_assess_signal.py` | ✅ 50 tests |
| **Risk Engine** | | |
| Risk Engine service | `src/application/services/risk_engine.py` | ✅ production-ready |
| Risk use case | `src/application/use_case/assess_risk_use_case.py` | ✅ |
| Gate base + GateContext | `src/domain/rules/risk_gate.py` | ✅ |
| FundamentalGate | `src/domain/rules/fundamental_gate.py` | ✅ |
| LiquidityGate | `src/domain/rules/liquidity_gate.py` | ✅ |
| BandarGate | `src/domain/rules/bandar_gate.py` | ✅ |
| FreeFloatGate | `src/domain/rules/free_float_gate.py` | ✅ wired in all 3 sites (2026-06-24) |
| Conservative / Balanced / Aggressive rules | `src/domain/rules/{conservative,balanced,aggressive}.py` | ✅ |
| RuleEngine | `src/domain/rules/rule_engine.py` | ✅ |
| RiskAssessment value object | `src/domain/value_objects/risk_assessment.py` | ✅ |
| **Migration targets (R2)** | | |
| Inline signal scoring | `src/application/use_case/accumulation_screen_use_case.py:358` | 🔜 R2 |
| Preset gate evaluation | `src/application/use_case/accumulation_screen_use_case.py:1106` | 🔜 R2 |
| CompositeSignalScore (to supersede) | `src/domain/value_objects/composite_signal_score.py` | 🔜 R2 |
| Swing analysis workflow | `src/application/use_case/swing_analysis_workflow_use_case.py` | 🔜 R2 |
| **Shared** | | |
| Bootstrap factory | `src/application/services/bootstrap.py` | ✅ both engines |
| PositionSizer | `src/application/services/position_sizer.py` | |
| Backtest use case | `src/application/use_case/backtest_use_case.py` | |
| Swing backtest use case | `src/application/use_case/swing_backtest_use_case.py` | 🔜 Phase 6 |
| Market regime use case | `src/application/use_case/market_regime_use_case.py` | 🔜 Phase 5 |
| Sentiment use case | `src/application/use_case/fetch_sentiment_use_case.py` | |
| Pre-open screener use case | `src/application/use_case/pre_open_screen_use_case.py` | |
| ExplainRisk use case | `src/application/use_case/explain_risk_use_case.py` | ✅ |
| ADRs | `ARCHITECTURE_DECISIONS.md` | ✅ ADR-025/026/027/028 added |
| Signal/Risk refactor plan | `docs/claude_signal_risk_230626.md` | R1 done; R2–R4 remain |
| AGY risk tracker | `docs/agy_risk_tracker.md` | |
| Improvement roadmap | `docs/improvement_roadmap_tracker.md` | |
| Swing screener config | `config/swing_screener.yaml` | |
| Default config | `config/default.yaml` | |
| Full AI stub (to delete) | `config/full_ai.yaml` | ADR-014 REJECTED |
