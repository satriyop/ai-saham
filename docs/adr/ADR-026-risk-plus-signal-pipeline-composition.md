# ADR-026: Risk+Signal Pipeline Composition

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — implementation evolved
**Date:** Not recorded (legacy decision)
**Current implementation:** Implemented through TradeSetup and AssessTradeSetupUseCase; BLOCKED is split into structural and execution actions.
_Date: 2026-06-24 · Updated: 2026-06-25 · Context: Defines how SignalEngine and RiskEngine outputs combine into an action verdict_

**Decision**
Features presenting a complete trade recommendation MUST compose both engine outputs through a `TradeSetup` domain value object, produced by `AssessTradeSetupUseCase`. The composition rule is deterministic and lives in the application layer (use case), not the domain value object itself.

> **Implementation note:** The original plan named `CombinedAssessment` / `ActionRecommendation`. During implementation the design evolved: (1) composition logic belongs in an application use case, not a static domain method; (2) `BLOCKED` was split into two distinct states to separate structural disqualifiers (permanent, skip entirely) from execution-quality gates (re-check if market conditions change).

**Value Object: `TradeSetup`** (`src/domain/value_objects/trade_setup.py`)

```python
@dataclass(frozen=True)
class TradeSetup:
    ticker: str
    snapshot_date: date
    action: SetupAction
    signal_score: int                    # final 0-100 score from SignalAssessment
    signal_score_raw: int                # pre-regime score, when available
    signal_strength: SignalStrength      # from SignalAssessment
    risk_level: RiskLevel                # from RiskAssessment
    blocking_gates: tuple[str, ...]      # gate labels; empty when not BLOCKED_*
    regime: MarketRegime | None          # None when MCE not used
    signal_multiplier: float             # 1.0 = no MCE impact; <1.0 = headwind
    gate_tightening: bool                # True when regime tightened gates
    rationale: str
```

**Enum: `SetupAction`** (`src/domain/value_objects/trade_setup.py`)

```python
class SetupAction(Enum):
    ENTER             = "ENTER"              # STRONG signal + LOW_RISK [+ favorable regime]
    WATCH             = "WATCH"              # MODERATE signal OR MODERATE risk
    AVOID             = "AVOID"              # WEAK signal
    BLOCKED_EXECUTION = "BLOCKED_EXECUTION"  # execution-quality gate fired (re-check later)
    BLOCKED_STRUCTURAL= "BLOCKED_STRUCTURAL" # structural gate fired (skip entirely)
```

**BLOCKED split rationale**

`gate_is_structural: bool | None` on `RiskAssessment` carries the gate type:
- `True` → structural gate (e.g. FundamentalGate, LiquidityGate, FreeFloatGate, or MCE regime gate when applied by RiskEngine) → `BLOCKED_STRUCTURAL`: the instrument is fundamentally unsuitable right now.
- `False` → execution gate (e.g. BandarGate) → `BLOCKED_EXECUTION`: the current execution/flow environment is poor; conditions may change.
- `None` → no gate triggered (normal path).

**Composition Rule** (`AssessTradeSetupUseCase`, deterministic, no I/O):

```
if any gate triggered and gate_is_structural == True:
    → BLOCKED_STRUCTURAL
elif any gate triggered and gate_is_structural == False:
    → BLOCKED_EXECUTION
elif signal.entry_quality == ENTER:
    → ENTER
elif signal.entry_quality == WATCH:
    → WATCH
elif signal.strength == WEAK:
    → AVOID
else:
    → WATCH
```

**MCE Regime Modifier**
`MarketContextEngine` output is optional. Current code records `regime`, `signal_multiplier`, and `gate_tightening` in `TradeSetup` when the caller supplies `market_context`.

Engine-level adjustment is owned by the engines, not by `AssessTradeSetupUseCase`:
- `SignalEngine.evaluate_with_context(..., market_context=...)` applies `score × signal_multiplier` and caps ENTER to WATCH when `gate_tightening=True`. This evaluation consumes the enriched context built via `build_context()`.
- `RiskEngine.assess(..., market_context=...)` marks HIGH_RISK assessments with a `regime:{REGIME}` structural gate when `gate_tightening=True`.

Callers that compute signal/risk before market context is available may still pass market context to `AssessTradeSetupUseCase`; in that case the regime is recorded in the verdict rationale, but signal/risk scores are not retroactively recomputed.

**Implications**

* `AssessTradeSetupUseCase` (`src/application/use_case/assess_trade_setup_use_case.py`) is the single composition point. It is stateless — instantiated inline as `AssessTradeSetupUseCase().execute(request)`.
* `SwingAnalysisWorkflowUseCase` computes `trade_setup` after signal, risk, and `market_regime` are all resolved. Current implementation passes `market_context=market_regime` to the composer for verdict context; engine-level MCE adjustment requires passing the same context into `SignalEngine`/`RiskEngine` before composition.
* `AccumulationScreenUseCase` computes `trade_setup` per candidate inside `_run_risk_funnel()` — the only scope where `AssessRiskResponse` (not just `RiskAssessment`) is still in scope. No `market_context` (screener doesn't use MCE).
* `SwingAnalysisWorkflowResponse.trade_setup` and `AccumulationCandidate.trade_setup` are both `TradeSetup | None` (None when signal or risk are absent).
* CLI display: color-coded action cell (bold green=ENTER, yellow=WATCH, red=AVOID, bold red=BLOCKED_*) in both `screen accum` table and `analyze swing` Panel 1 Signal Snapshot.
* `TradeSetup.to_dict()` is the canonical serialization for JSON output and the ADR-027 learning journal.

**Rationale**
Without a formal composition rule, every CLI command that shows both signal and risk invents its own merging logic — creating divergent action columns in `screen accum`, `analyze swing`, and future commands. `AssessTradeSetupUseCase` ensures the same ENTER/WATCH/AVOID/BLOCKED logic everywhere. The BLOCKED split enables the learning loop (ADR-027) to attribute outcomes separately: structural blocks have no actionable signal, execution blocks may yield profitable retries.

---

## Amendment: Evidence-Backed Signal Assessment (July 2026)

* **Context & Rules:**
  * `build_context()` returns enrichment/flag context only and never returns a signal assessment.
  * `evaluate_with_context()` is the only canonical `SignalEngine` assessment API.
  * It requires at least one setup or flow production evidence group.
  * Zero production evidence raises `NoProductionSignalEvidenceError`.
  * Flags cannot independently produce an assessment.
