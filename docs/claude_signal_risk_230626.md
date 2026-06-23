# Signal Engine & Risk Engine — Architecture Decision and Refactor Plan

_Date: 2026-06-23_
_Status: Concluded — ready for implementation_
_ADR target: ADR-018 in `ARCHITECTURE_DECISIONS.md`_

---

## 1. Context and Motivation

This document records the discussion and recommendation that emerged from implementing the AGY risk methodology improvements (Phases A–E, commit `4c827ce`). After wiring gates into CLI adapters and running the commands end-to-end, two structural problems became clear:

**Problem 1 — Fragmented wiring.** Every CLI adapter that needs risk assessment must manually:
- Instantiate `FundamentalGate`, `LiquidityGate`, `BandarGate`
- Create `AssessRiskUseCase` with those gates
- Build `GateContext` from whatever data happens to be available

This produced three separate wiring points in three files, two commands (`analyze risk`, `analyze compare`) that got no gates at all, and a bug where `screen accum` displayed a Risk column that was always `—` because the adapter forgot to pass `risk_use_case`.

**Problem 2 — Signal and risk are conflated.** The accumulation score (0–120), broker quality, bandar intensity, and seasonality all live inside `AccumulationScreenUseCase` as inline computation. The technical risk rules (RSI, EMA/SMA) and domain gates live inside `AssessRiskUseCase`. But there is no clear architectural boundary — both concepts exist as implementation details of two use cases rather than as first-class concerns.

---

## 2. The Core Distinction

These two questions are orthogonal:

| Engine | Question | Changes at | Output |
|--------|----------|------------|--------|
| **Signal Engine** | What is the market telling us about this stock right now? | Per session | Signal strength, entry quality |
| **Risk Engine** | How risky is this stock as a holding? | Per week / quarter | Risk level, gate rationale, confidence |

A strong signal does not imply low risk. Low risk does not imply a good entry signal. Both must be evaluated independently. Commands compose the two outputs to produce a recommendation.

---

## 3. What Belongs Where

### Signal Engine

Aggregates quantitative evidence for entry timing:

| Signal | Source | Currently in |
|--------|--------|--------------|
| Accumulation score (0–120) | Broker flow consistency, streak, VWAP discount, RSI headroom, BB squeeze, flow% | `AccumulationScreenUseCase` (inline) |
| Broker quality | Smart money vs noise ratio, weighted net flow | `compute_broker_quality_batch` service |
| Bandar accumulation intensity | `five_day_accdist` as positive signal | `AccumulationScreenUseCase` (display only) |
| Seasonality edge | ±% seasonal return, win rate | `AccumulationScreenUseCase` (display only) |
| Preset gate evaluation | `foreign-bounce` rules: score≥70, fvwap≥3%, trend==SIDE | `_evaluate_foreign_bounce` (inline) |
| Technical indicators as signal inputs | RSI headroom, EMA/SMA direction for scoring | `AccumulationScreenUseCase` |

### Risk Engine

Assesses structural and execution risk independently of entry timing:

| Risk Factor | Source | Currently in |
|-------------|--------|--------------|
| Technical risk signal | RSI overbought/oversold + EMA/SMA trend | `balanced.py`, `conservative.py`, `aggressive.py` |
| Fundamental gate | Piotroski F-score ≤ threshold → HIGH_RISK | `FundamentalGate` (domain) |
| Liquidity gate | Market cap < 1T IDR or 20d median tx < 5B IDR → HIGH_RISK | `LiquidityGate` (domain) |
| Distribution gate | 5d Big/Small Dist while technical LOW_RISK → MODERATE | `BandarGate` (domain) |
| Shareholding gate | individual_pct > 70% (Rec 7, deferred) | not yet implemented |

### Shared Inputs (same data, different lens)

| Data | Signal lens | Risk lens |
|------|-------------|-----------|
| RSI | Headroom for entry (lower = more room) | Overbought → HIGH_RISK |
| Bandar `five_day_accdist` | Accumulation intensity (positive signal) | Distribution as risk override |
| Candles | BB squeeze, trend direction for score | 20d median liquidity check |

Both engines receive these independently via their own injected providers. They do not share state.

### Stays Outside Both Engines

| Concern | Reason |
|---------|--------|
| Market regime (IHSG BULLISH/SIDEWAYS) | Macro-level, not stock-level; provided as context to the caller |
| Position sizing | Downstream of risk + signal; not an assessment |
| Sentiment (AI) | Optional layer, stays in `ExplainRiskUseCase` |
| Backtest simulation | Historical replay, not live assessment |

---

## 4. Target Architecture

```
┌─────────────────────────────────┐    ┌─────────────────────────────────┐
│          SIGNAL ENGINE          │    │           RISK ENGINE           │
│  Application Service            │    │  Application Service            │
│                                 │    │                                 │
│  Providers (injected):          │    │  Providers (injected):          │
│    market_repo                  │    │    market_repo                  │
│    broker_repo                  │    │    fundamentals_provider        │
│    bandar_provider              │    │    bandar_provider              │
│    seasonality_provider         │    │    shareholding_provider (opt)  │
│                                 │    │                                 │
│  evaluate(                      │    │  assess(                        │
│    ticker,                      │    │    ticker,                      │
│    window,                      │    │    profile,                     │
│    as_of_date=None              │    │    as_of_date=None              │
│  ) → SignalAssessment           │    │  ) → RiskAssessment             │
│                                 │    │                                 │
│  SignalAssessment:              │    │  RiskAssessment:                │
│    score: float                 │    │    risk_level: LOW/MOD/HIGH     │
│    strength: STRONG/MOD/WEAK    │    │    confidence: int (0–100)      │
│    entry_quality: ENTER/WATCH/  │    │    gate_triggered: str | None   │
│                  AVOID          │    │    rationale: tuple[str, ...]   │
│    signals: dict[str, Any]      │    │    signal_details: dict         │
│      score_breakdown            │    │      technical: LO@50           │
│      broker_quality             │    │      bandar: distributing       │
│      bandar_intensity           │    │      fundamentals: F=4          │
│      seasonality_edge           │    │                                 │
└─────────────────────────────────┘    └─────────────────────────────────┘
                │                                      │
                └──────────────┬───────────────────────┘
                               ↓
                        Command layer
               (screen accum / analyze swing / analyze risk)
                               ↓
                    Unified decision output:
                    Signal: STRONG (87)  Risk: MODERATE (BandarGate)
                    → WATCH / ENTER / AVOID
```

### Factory Pattern (bootstrap.py)

```python
def create_signal_engine(db_path) -> SignalEngine:
    return SignalEngine(
        market_repo=SQLiteMarketRepository(db_path),
        broker_repo=SQLiteBrokerRepository(db_path),
        bandar_provider=StockbitBandarDetectorProvider(...),
        seasonality_provider=StockbitSeasonalityProvider(...),
    )

def create_risk_engine(db_path) -> RiskEngine:
    sb = _make_stockbit_providers(db_path)
    return RiskEngine(
        market_repo=SQLiteMarketRepository(db_path),
        fundamentals_provider=sb.fundamentals_prov,
        bandar_provider=sb.bandar_prov,
        structural_gates=[FundamentalGate(), LiquidityGate()],
        execution_gates=[BandarGate()],
    )
```

No adapter ever touches `GateContext`, individual gates, or provider construction again.

---

## 5. Confidence Model (Redefined)

Currently `confidence` is a byproduct of how many technical indicators agree. It conflates two independent things: technical signal certainty and gate override certainty. Under the new model:

| Level | Meaning | When |
|-------|---------|------|
| 100 | All active tiers agree | Both RSI + trend confirm; no gate conflicts |
| 75 | One strong tier confirms | Single indicator active; no gate fired |
| 50 | Gate fired with uncertainty | Gate overrides but the technical signal was borderline |
| 25 | Conflicting signals | Gate fired but technical was already MODERATE/HIGH |
| 0 | No active signals | Both indicators neutral; no gate data |

This scale is **Risk Engine specific**. Signal Engine uses `strength` (STRONG / MODERATE / WEAK) as its own confidence expression — not a number.

---

## 6. Display Unification

Two shared display modules replace the current ad-hoc per-command rendering:

### `risk_display.py`
```python
summary_cell(assessment)      # "MID" in yellow for table Risk column
summary_label(assessment)     # "MODERATE via BandarGate" for summary lines
detail_panel(assessment)      # full rich panel:
                              #   1. Gate verdict (if fired) — FIRST, bold
                              #   2. Gate reason
                              #   3. Technical indicators: SMA/EMA/RSI
                              #   4. Technical rationale bullets
                              #   5. Confidence explanation
```

The current bug — panel shows "MODERATE" verdict but only "Net signal indicates LOW_RISK" bullets — is fixed by rule: gate reason always precedes technical rationale in both the `RiskAssessment.rationale` tuple and the display.

### `signal_display.py`
```python
score_cell(assessment)        # "87" in green for table Score column
strength_label(assessment)    # "STRONG" for summary lines
breakdown_panel(assessment)   # per-signal breakdown:
                              #   flow%, streak, VWAP discount, RSI headroom,
                              #   BB squeeze, broker quality, bandar intensity,
                              #   seasonality edge
```

---

## 7. Concrete Refactor Plan

### Phase R1 — Define the engines (domain + application layer)

**Scope:** New files only. No existing code touched. All tests still pass.

| Step | Action | Files |
|------|--------|-------|
| R1-1 | Create `SignalAssessment` value object | `src/domain/signal/value_objects/signal_assessment.py` |
| R1-2 | Create `SignalEngine` application service | `src/application/services/signal_engine.py` |
| R1-3 | Add provider injection + `assess()` self-fetch to `AssessRiskUseCase` → rename to `RiskEngine` | `src/application/services/risk_engine.py` |
| R1-4 | Add `create_signal_engine()` and `create_risk_engine()` to bootstrap | `src/application/services/bootstrap.py` |
| R1-5 | Unit tests for `SignalEngine` and `RiskEngine` in isolation | `tests/application/services/` |

At the end of R1: both engines exist and are tested. Nothing else has changed.

### Phase R2 — Migrate use cases to use the engines

**Scope:** Use cases delegate to engines. Adapter wiring removed.

| Step | Action | Files |
|------|--------|-------|
| R2-1 | `AccumulationScreenUseCase` calls `signal_engine.evaluate()` per candidate instead of inline scoring | `accumulation_screen_use_case.py` |
| R2-2 | `_run_risk_funnel()` calls `risk_engine.assess_with_context()` (pipeline path, no re-fetch) | `accumulation_screen_use_case.py` |
| R2-3 | `SwingAnalysisWorkflowUseCase` accepts `risk_engine` directly; remove manual gate wiring | `swing_analysis_workflow_use_case.py` |
| R2-4 | `analyze_commands.py` uses `create_risk_engine()` — gates now fire for `analyze risk` and `analyze compare` automatically | `analyze_commands.py` |
| R2-5 | Remove `FundamentalGate / LiquidityGate / BandarGate` instantiation from all CLI adapters | `screen_accum_commands.py`, `analyze_swing_commands.py` |

At the end of R2: no adapter ever wires gates. All commands get full gate evaluation automatically.

### Phase R3 — Unified display

**Scope:** Display modules extracted. Per-command rendering replaced.

| Step | Action | Files |
|------|--------|-------|
| R3-1 | Create `risk_display.py` with `summary_cell`, `summary_label`, `detail_panel` | `src/adapters/cli/risk_display.py` |
| R3-2 | Create `signal_display.py` with `score_cell`, `strength_label`, `breakdown_panel` | `src/adapters/cli/signal_display.py` |
| R3-3 | Fix rationale order in `RiskEngine`: gate reason prepended, not appended | `src/application/services/risk_engine.py` |
| R3-4 | Redefine confidence scale (table in Section 5) | `RiskEngine` + gate `GateResult` values |
| R3-5 | Replace ad-hoc Risk column in `screen_accum_display.py` with `risk_display.summary_cell()` | `screen_accum_display.py` |
| R3-6 | Replace Risk panel in `analyze_swing_display.py` with `risk_display.detail_panel()` | `analyze_swing_display.py` |

At the end of R3: MODERATE always shows gate reason first. Risk looks identical in every command.

### Phase R4 — ADR + cleanup

| Step | Action |
|------|--------|
| R4-1 | Write ADR-018 in `ARCHITECTURE_DECISIONS.md` |
| R4-2 | Update all tests that construct `AssessRiskUseCase` directly to use `RiskEngine` or test factory |
| R4-3 | Update `agy_risk_tracker.md` to reflect architectural refactor |
| R4-4 | Delete `assess_risk_use_case.py` if fully superseded; keep if `ExplainRiskUseCase` still depends on it |

---

## 8. Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| **N+1 queries in screening** — if `_run_risk_funnel` uses `assess()` and the engine re-fetches fundamentals + bandar per ticker | High | Keep `assess_with_context(ticker, profile, gate_context)` pipeline path. Screener passes pre-loaded context. Engine never re-fetches data the screener already loaded. |
| **`AccumulationScreenUseCase` scoring is deeply interleaved** — not a clean extraction | Medium | Phase R2-1: extract to `signal_engine.score_candidate(pre_loaded_data)` first (data provided by caller), then later make it self-fetching. Two sub-steps, not one. |
| **`ExplainRiskUseCase` coupling** — takes `RiskAssessment`; if the VO changes, AI layer breaks | Low | `RiskAssessment` schema is additive only. `signal_details` is a new optional field. No breaking change. |
| **Test surface area** — ~50 tests construct `AssessRiskUseCase` directly | Low | Introduce `create_test_risk_engine()` factory in `tests/conftest.py`. One-line change per test. |
| **Scope creep into Rec 1, 3, 7, 8, 9** — "unified engine" can expand indefinitely | Medium | Hard boundary: this refactor implements no new gates or signals. Rec 7 (shareholding gate) slots in as a single gate addition after R4. Rec 8 (Z-scoring) is a separate ADR. |

---

## 9. Non-Goals (Explicitly Deferred)

These are NOT part of this refactor:

- **New gate logic** — no new gates in R1–R4. Rec 7 (shareholding) is post-refactor.
- **Z-score normalization (Rec 8)** — full domain rewrite; needs its own ADR.
- **Factor decorrelation (Rec 9)** — premature; revisit at 5+ signals.
- **Macro signals / DXY (Rec 3)** — requires offline data provider.
- **Adaptive regime tuning (Rec 1)** — requires win/loss attribution pipeline.
- **Sentiment into Risk Engine** — stays in `ExplainRiskUseCase`.
- **Web/bot interface** — CLI only for now.

---

## 10. ADR-018 Content (to be written into ARCHITECTURE_DECISIONS.md)

```
## ADR-018: Signal Engine and Risk Engine as First-Class Application Services

**Decision**
Signal assessment and risk assessment are separated into two independent,
self-sufficient application services: SignalEngine and RiskEngine.

**Principles**

1. Orthogonality — strong signal ≠ low risk. Both are evaluated independently.
   A command composes the two outputs; it does not merge them.

2. Self-sufficient — each engine fetches its own data through injected ports.
   Callers provide a ticker and profile. Callers never build GateContext,
   instantiate gates, or manage provider calls for risk/signal evaluation.

3. Single factory — each engine is created once per command via
   create_signal_engine(db_path) and create_risk_engine(db_path) in bootstrap.
   Gate configuration lives in the factory, nowhere else.

4. Pipeline path — when a screener or workflow has already loaded data for a
   ticker, it may call assess_with_context() to avoid re-fetching.
   This is an optimization, not an architectural exception.

5. Display separation — RiskDisplay and SignalDisplay are the only places
   that render risk and signal output. Commands call display modules;
   they do not format risk/signal strings inline.

**Boundaries**

Signal Engine owns: accumulation score, broker quality, bandar accumulation
intensity, seasonality edge, preset gate evaluation, technical indicators as
signal inputs (RSI headroom, EMA/SMA direction).

Risk Engine owns: technical risk rules (RSI overbought, EMA/SMA risk trend),
structural gates (FundamentalGate, LiquidityGate), execution gates (BandarGate),
shareholding gate (future).

Neither engine owns: market regime, position sizing, sentiment, backtest.

**Rationale**
Prevents wiring fragmentation where each adapter independently instantiates
gates and builds context. Ensures every command — including analyze risk and
analyze compare — automatically benefits from all configured gates without
adapter-level awareness of gate internals.
```

---

## 11. Estimated Effort

| Phase | Sessions | Key risk |
|-------|----------|----------|
| R1 — Define engines | 1 | Clean slate; low risk |
| R2 — Migrate use cases | 1–2 | Scoring extraction complexity |
| R3 — Unified display | 1 | Rationale order + confidence scale redefinition |
| R4 — ADR + cleanup | 0.5 | Test updates are mechanical |
| **Total** | **3.5–4.5** | |

Recommended sequence: R1 → R4 (write ADR-018 early, guides R2+R3) → R2 → R3.

---

_This document is the conclusion of the Signal Engine / Risk Engine architecture discussion on 2026-06-23. Implementation begins with Phase R1._
