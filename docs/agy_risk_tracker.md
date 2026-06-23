# AGY Risk Improvements Tracker
_Source doc: `docs/agy_risk_improvements_210626.md`_
_Source plan: `.claude/plans/vet-docs-agy-risk-improvements-210626-md-sunny-prism.md`_
_Started: 2026-06-23_

This file is the canonical state tracker for the AGY risk methodology improvements. Update it as each item completes. Survives context compaction — always check this file at the start of a new session when continuing this work.

---

## Phase Overview

| Phase | Items | Status | Notes |
|-------|-------|--------|-------|
| A | Rec 13, 15 | ✅ Done | Rec 13 done; Rec 15 deferred to Phase C/E |
| B | Rec 4, 5, 2, 6 | ✅ Done | 49 new tests; 1804 total pass |
| C | Rec 11 | ✅ Done | gate_triggered moved to RiskAssessment; 6 new tests; 1810 total pass |
| D | Rec 16, 12 | ✅ Done | as_of_date on both ports + infra guards; 18 new tests; 1828 total pass |
| E | Rec 14 | ✅ Done | risk funnel on survivors; Risk col in display; 9 new tests; 1835 total pass |
| — | Rec 1, 3, 7, 8, 9, 10 | ⏸️ Deferred | See deferred reasons below |

**Status legend:** 🔲 Not Started · 🔄 In Progress · ✅ Done · ⏸️ Deferred

---

## Recommendation Status

| # | Recommendation | Status | Branch/Commit |
|---|----------------|--------|---------------|
| 1 | Adaptive Regime Tuning (regime_overrides.yaml) | ⏸️ Deferred | needs win/loss attribution pipeline |
| 2 | Liquidity Filter (20-day median IDR 5B floor) | ✅ Done | LiquidityGate |
| 3 | Macro Signals (DXY / USD-IDR) | ⏸️ Deferred | needs offline data provider (local-first mandate) |
| 4 | Piotroski F-Score Safeguard | ✅ Done | FundamentalGate |
| 5 | Bandarmology Divergence Filter | ✅ Done | BandarGate |
| 6 | Dynamic Liquidity & Size Gates (market cap tiering) | ✅ Done | LiquidityGate (market cap check) |
| 7 | Ownership Stability Filter (individual_pct > 70%) | ⏸️ Deferred | verify shareholding_composition data quality first |
| 8 | Z-Score Normalization | ⏸️ Deferred | full domain rewrite — needs ADR; v2 feature |
| 9 | Factor Decorrelation | ⏸️ Deferred | premature — only 2 indicators; revisit at 5+ |
| 10 | Alpha vs. Risk Model Separation | ⏸️ Deferred | low payoff; existing separation is adequate |
| 11 | Hierarchical 3-Gate Pipeline | ✅ Done | gate_triggered on RiskAssessment; response.gate_triggered is now a property |
| 12 | Backtesting Temporal Integrity | ✅ Done | as_of_date threaded through AccumulationScreenUseCase to both providers |
| 13 | Early Market Cap Floor Pruning | ✅ Done | — |
| 14 | Post-Screening Risk Gating Funnel | ✅ Done | _run_risk_funnel() on survivors; Risk column in display; gate detail line |
| 15 | Share Data Snapshots (no duplicate queries) | ✅ Done | Delivered in Phase E: _run_risk_funnel() builds GateContext from pre-loaded candidate data |
| 16 | Date-Bound Queries on Persistence Ports | ✅ Done | as_of_date on FundamentalsProvider + ShareholdingProvider; infra guards fetched_date/report_date |

---

## Phase A — Quick Wins

**Goal:** Zero-risk refactors and dependency injection. No new domain logic.

### Rec 13: Early Market Cap Floor Pruning

**Layer plan:**
- Domain: not touched
- Application: `accumulation_screen_use_case.py` — fetch fundamentals first when `min_market_cap_idr > 0` or `min_piotroski > 0`; apply both gates immediately; skip all other enrichment for rejected tickers
- Infrastructure: not touched
- Adapter: not touched

**Status:** ✅ Done

**Files changed:**
- `src/application/use_case/accumulation_screen_use_case.py` — added logger; early fundamentals fetch + dual gate block before enrichment loop; removed duplicate market_cap and piotroski checks from tail of loop
- `tests/application/use_case/test_accumulation_screen.py` — 5 new tests: market_cap floor exclude/include, enrichment-skip assertions for both gates, no-gate baseline

**Side-effect note:** Piotroski failures now increment `tickers_skipped` (consistent with market_cap behavior). Old code silently skipped without counting.

### Rec 15: Share Data Snapshots

**Status:** ⏸️ Deferred — `AssessRiskUseCase` is not called from the screener yet. Deferring to Phase C/E when the risk use case gets wired into the screening pipeline. At that point, pass pre-loaded fundamentals/bandar snapshots instead of re-querying.

---

## Phase B — DB-Contextual Risk Enrichment

**Goal:** Wire existing DB data (fundamentals, bandar, candles) into risk assessment as domain-level gates.

### Rec 4: Piotroski F-Score Gate

**Status:** ✅ Done (covers Recs 4, 5, 2, 6)

**Files created:**
- `src/domain/rules/risk_gate.py` — `RiskGate` ABC, `GateResult`, `GateContext`
- `src/domain/rules/fundamental_gate.py` — F-score ≤ 3 → HIGH_RISK (Rec 4)
- `src/domain/rules/bandar_gate.py` — 5d distribution + LOW_RISK → MODERATE (Rec 5)
- `src/domain/rules/liquidity_gate.py` — market cap < 1T OR median 20d tx < 5B → HIGH_RISK (Rec 2 + 6)
- `tests/domain/test_fundamental_gate.py` — 13 tests
- `tests/domain/test_bandar_gate.py` — 11 tests
- `tests/domain/test_liquidity_gate.py` — 17 tests
- `tests/application/use_case/test_assess_risk_gates.py` — 8 integration tests

**Files modified:**
- `src/application/use_case/assess_risk_use_case.py` — `gate_context` on request, `gate_triggered` on response, `structural_gates`/`execution_gates` on use case, `_build_gate_context()` helper

**Design notes:** Gates are opt-in (no gates = behaviour unchanged). `GateContext` is pure data. Structural gates run before rule engine; execution gates after. Callers unchanged.

---

## Phase C — Hierarchical Pipeline Restructure

**Goal:** Chain gates (Structural → Liquidity → Execution) in `AssessRiskUseCase`. Add `gate_triggered` field to `RiskAssessment`.

### Rec 11: 3-Tier Gate Pipeline

**Layer plan:**
- Domain: `src/domain/rules/` — `RiskGate` ABC with `evaluate(snapshot) → Optional[RiskLevel]`; gates: `FundamentalGate` (Tier 1), `LiquidityGate` (Tier 2), `ExecutionGate` wrapping existing RSI+trend rules + `BandarGate` (Tier 3)
- Application: `AssessRiskUseCase` — chains gates in order; stops at first `HIGH_RISK` override; populates `gate_triggered: str` on `RiskAssessment`
- Infrastructure: not touched
- Adapter: not touched — `RiskAssessment` output contract extended (not broken)

**Status:** ✅ Done

**Files changed:**
- `src/domain/value_objects/risk_assessment.py` — added `gate_triggered: str | None = None` (optional, backward-compat)
- `src/application/use_case/assess_risk_use_case.py` — structural and execution gate branches now set `gate_triggered` on `RiskAssessment` directly; `AssessRiskResponse.gate_triggered` demoted to a property that delegates to `assessment.gate_triggered`
- `tests/domain/test_risk_assessment_gate_triggered.py` — 6 new tests: default None, field value, frozen immutability, property delegation, gate-fired and gate-passed integration cases

**Design notes:** `RiskAssessment` is now the single source of truth for `gate_triggered`. `ExplainRiskUseCase` callers automatically get richer `assessment.gate_triggered` in the domain value object passed to the AI layer — no changes to `ExplainRiskUseCase` needed. Tier 1/2 (structural) and Tier 3 (execution) comments added to `execute()` for readability.

---

## Phase D — Backtesting Integrity

**Goal:** Prevent look-ahead bias by scoping fundamentals/shareholding queries to historical dates.

### Rec 16: Date-Bound Persistence Ports

**Layer plan:**
- Domain: `src/domain/ports/` — add `as_of_date: Optional[date]` to `FundamentalsProvider.get()` and `ShareholdingProvider.get()`
- Application: not touched (ports gain optional param)
- Infrastructure: SQLite repo implementations — add `WHERE period_end <= as_of_date` filter when `as_of_date` provided
- Adapter: not touched

**Status:** ✅ Done

**Files changed:**
- `src/domain/ports/fundamentals_provider.py` — `as_of_date: date | None = None` on abstract method
- `src/domain/ports/shareholding_provider.py` — same
- `src/infrastructure/browser/stockbit_fundamentals.py` — date-bound filter: `fetched_date <= as_of_date`; TTL bypassed in backtest mode; live fetch blocked when `as_of_date` set; mem_cache bypassed in backtest mode
- `src/infrastructure/browser/stockbit_shareholding.py` — same with `report_date` as primary boundary, `fetched_date` as fallback
- `tests/infrastructure/test_fundamentals_as_of_date.py` — 9 new tests
- `tests/infrastructure/test_shareholding_as_of_date.py` — 9 new tests

### Rec 12: Temporal Integrity in Backtests

**Layer plan:**
- Domain: not touched
- Application: `SwingBacktestUseCase` already passes `as_of_date=signal_date` to `AccumulationScreenRequest`. Missing link was propagation into provider calls inside `AccumulationScreenUseCase`.
- Infrastructure: not touched (covered by Rec 16)
- Adapter: not touched

**Status:** ✅ Done

**Files changed:**
- `src/application/use_case/accumulation_screen_use_case.py` — all three provider calls (lines 537, 634, 647) now pass `as_of_date=request.as_of_date`

---

## Phase E — Screener Integration

**Goal:** Run the full risk engine only on screener survivors, not all 800+ tickers.

### Rec 14: Post-Screening Risk Gating Funnel

**Layer plan:**
- Domain: not touched
- Application: `accumulation_screen.py` — after primary technical/flow filter isolates top N candidates, run `AssessRiskUseCase` on survivors; flag `HIGH_RISK` before final display sort
- Infrastructure: not touched
- Adapter: `accumulation_commands.py` — pass risk gate result to display layer (new column or warning indicator)

**Status:** ✅ Done

**Files changed:**
- `src/application/use_case/accumulation_screen_use_case.py` — `risk_profile` on request; `risk_assessment: RiskAssessment | None` on candidate; `risk_use_case` param on use case; `_run_risk_funnel()` helper; call in `execute()` after sort/breadth; `to_dict()` includes `risk_level`, `risk_confidence`, `risk_gate`
- `src/adapters/cli/screen_accum_display.py` — "Risk" column (HI/MID/LO colored); gate detail line when `gate_triggered` is set
- `tests/application/use_case/test_screen_risk_funnel.py` — 9 new tests

**Design notes:**
- Funnel is opt-in (`risk_use_case=None` → no change to existing callers)
- `_run_risk_funnel()` builds `GateContext` from already-loaded candidate data (Rec 15 data sharing: zero extra provider queries)
- Errors are caught per-candidate and logged at DEBUG — funnel failures never abort the screen
- `risk_profile` on `AccumulationScreenRequest` controls which rule profile the risk engine uses (default "balanced")

---

## Deferred Items

| Rec | Why Deferred |
|-----|-------------|
| 1 | Adaptive Regime Tuning needs a win/loss attribution pipeline to generate meaningful `regime_overrides.yaml` — that's a separate data science project |
| 3 | DXY/USD-IDR macro signals require an offline-capable external data provider; violates local-first mandate until one exists |
| 7 | Ownership stability filter — verify `shareholding_composition` data completeness for the IDX universe before building logic on it |
| 8 | Z-scoring replaces the entire `domain/rules/` thresholding model — full domain rewrite; needs ADR and v2 feature flag |
| 9 | Factor decorrelation is premature with only 2 indicators (RSI + EMA/SMA divergence); revisit when 5+ signals are wired in |
| 10 | Alpha vs. Risk model separation — existing `AssessRiskUseCase` + `ExplainRiskUseCase` split is adequate; low payoff refactor |

---

## Architecture Guardrails (do not violate)

- **Domain gates must be pure functions** — receive plain Python values, never a DB connection or repository
- **Application layer owns data fetching** — `AssessRiskUseCase` fetches from infrastructure and passes values into gates
- **Adapters stay thin** — display layer changes only when `RiskAssessment` output contract changes
- **Rec 3 (DXY) must not bypass local-first** — any macro provider must be offline-capable (SQLite-cached or bundled data)
- **Rec 8 (Z-scoring) requires an ADR** before any code is written — it replaces the existing rule model, not extends it

---

## Notes / Decisions Log

_Append decisions, blockers, or scope changes here as they come up._

- 2026-06-23: Phase sequence approved. Tracker created. Implementation begins with Phase A.
- 2026-06-23: Rec 13 done (1755 tests pass). Rec 15 deferred — AssessRiskUseCase not yet wired into screener. Phase A complete. Next: Phase B.
- 2026-06-23: Phase B done (1804 tests pass). RiskGate ABC + FundamentalGate + BandarGate + LiquidityGate. Gates opt-in via constructor; all existing callers unchanged. Next: Phase C.

