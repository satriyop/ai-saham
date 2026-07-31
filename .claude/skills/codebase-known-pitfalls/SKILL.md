---
name: codebase-known-pitfalls
description: >
  Repeatable bug patterns and their correct solutions, learned from real bugs
  found in ai-saham code reviews (commits 87c24bd, post-R1 2026-06-24, R3 2026-06-24,
  TradeSetup ADR-026 2026-06-25).
  Use this skill whenever you are about to: write or modify a fetch/cache use
  case, build or extend GateContext, add a new risk gate, thread as_of_date
  through a service, design a frozen dataclass value object, write profile-
  override logic in assess_all_profiles, add counts to a fetch response DTO,
  inject a service into a use case, build enrichment-result workflows, add a
  new field to RiskAssessment/SignalAssessment/TradeSetup, or post-process
  assessment results with replace().
  Also trigger for: "gate not firing in screener but fires in analyze risk",
  "backtest results look too good", "free_float_pct over 100", "active_codes
  lower than expected", "CLOSE always shows dash", "profile list out of sync",
  "signal computed twice for same ticker", "should I inject AssessSignalUseCase",
  "BLOCKED_STRUCTURAL shows as BLOCKED_EXECUTION", "regime gate not classifying
  correctly", "tests pass but production crashes in RISK_OFF regime".
---

# Codebase Known Pitfalls

Bugs confirmed in real code reviews. Read the relevant section **before** writing
or modifying the components listed. Each section names the anti-pattern, explains
why it fails silently, and shows the correct form.

---

## 1. Incremental Fetch / Cache Use Cases

### 1a. Filter before saving — handle refresh, boundary date inclusive

Affected file: `src/application/use_case/fetch_broker_daily_flows_use_case.py`

There are three distinct sub-bugs that have each appeared in this codebase.
They all live in the same 5-line block that decides which rows to save.

**Sub-bug i — save-all instead of filter:**
```python
# WRONG — saves every API row, wasted full-table scan to count diffs
flows = provider.fetch(...)       # always returns full history (e.g. 2591 rows)
repository.save(flows)            # upserts all rows every time
added = count_db_changes(...)     # always 0 — completely wasted
```

**Sub-bug ii — refresh=True still applies date filter:**
```python
# WRONG — corrupted existing rows can never be overwritten
if before_max_date is None:
    new_flows = flows or []
else:
    new_flows = [f for f in flows if f.date >= before_max_date]
# refresh flag is ignored — refresh=True is supposed to mean "overwrite everything"
```

**Sub-bug iii — strict > on boundary date drops new broker codes:**
```python
# WRONG — a new broker code appearing on the already-stored max date is silently dropped
new_flows = [f for f in flows if f.date > before_max_date]
#                                                         ^--- must be >=
```

**Correct pattern (all three fixed together):**
```python
before_max_date = repository.get_date_range(ticker, source=source)  # one cheap query

if request.refresh or before_max_date is None:
    # refresh=True: save everything so existing rows can be corrected (upsert)
    # no prior data: first fetch, save all
    new_flows = flows or []
else:
    # >= (not >) so new broker codes for the already-stored max date are included
    new_flows = [f for f in flows if f.date >= before_max_date] if flows else []

if new_flows:
    repository.save(new_flows)
    cached_range = repository.get_date_range(ticker, source=source)  # re-query after save
else:
    cached_range = before_range
```

**Why `>=` not `>`:** If max date is D3 and a new broker code "YP" appears in the
provider response for D3, strict `>` silently discards it. The `>=` filter lets
new rows for the boundary date pass through. Re-saving already-stored rows for D3
is safe because `save_broker_daily_flows` uses upsert semantics.

### 1b. Reuse the freshness-check result — never issue two identical DB queries

The freshness check and the "before state" capture are the same query. Run it once.

**Anti-pattern:**
```python
if not request.refresh:
    cached = repo.get_date_range(ticker)    # Query 1
    if cached and cached[1] >= expected:
        return cached_response
before_range = repo.get_date_range(ticker)  # Query 2 — identical, wasted
```

**Correct pattern:**
```python
before_range = repo.get_date_range(ticker)  # Query 1 only
if not request.refresh:
    if before_range and before_range[1] >= expected:
        return cached_response(before_range)
# before_range is already available for everything below
```

### 1c. Never use date-arithmetic heuristics to detect "history gaps"

**Anti-pattern (was in this codebase, now removed):**
```python
expected_start = expected_latest - timedelta(days=request.days)
has_history_gap = (
    before_min_date is None
    or before_min_date > expected_start + timedelta(days=7)
)
```

Why it fails: fires True when a ticker was first fetched with `days=30` and later
called with `days=365`. The stored history is contiguous but shorter — not a gap.
Result: all 2591 rows re-persisted every run even after a full fetch.

**Correct invariant:** the only time "save everything" is correct is `before_max_date is None`
or `request.refresh is True`. Historical backfill is a separate concern, handled by `--refresh`.

### 1d. Dead guards with dangerous fallback paths are correctness time-bombs

When you write `if x is not None` and `x` is provably non-None in that branch, the
fallback clause runs under conditions you believe impossible. If the fallback is
"save all rows", you've built a silent regression trigger.

Before writing a guard whose else-clause saves everything: prove the guard can
evaluate False, or delete it.

### 1e. Count aggregate metrics from the full provider response, not the filtered subset

**Anti-pattern:**
```python
new_flows = [f for f in flows if f.date >= before_max_date]  # only new rows
repository.save(new_flows)
# WRONG — active_codes only counts broker codes in the incremental slice
active_codes = len({f.broker_code for f in new_flows}) if new_flows else 0
```

Why it fails: on an incremental run that adds only D3, `new_flows` contains only D3
rows. If brokers AK and YP were active on D1 and D2, they're not in `new_flows` and
`active_codes` = 1 instead of 3.

**Correct pattern:**
```python
# Count from the full provider response — represents the whole fetched window
active_codes = len({f.broker_code for f in flows}) if flows else 0
```

---

## 2. IndicatorSnapshot.extras Is Path-Specific

Affected file: `src/adapters/cli/analyze_commands.py` → `compare()` function.

`CLOSE` is only injected into `IndicatorSnapshot.extras` inside
`_build_snapshot_for_rules()`, which runs only when `rules_file is not None`.

The `compare` command (and any command using the aggregate path) does not set
`rules_file`, so `snap.get('CLOSE')` silently raises `KeyError` on every call.
Wrapping it in `except KeyError` produces a silent always-`"—"` regression.

**Anti-pattern:**
```python
try:
    close = f"{float(snap.get('CLOSE')):,.0f}"
except KeyError:
    close = "—"    # silently always shows "—" on the aggregate path
```

**Correct pattern — use the typed, always-available source:**
```python
candles = repository.get_candles(ticker.upper())
close = f"{candles[-1].close:,.0f}" if candles else "—"
```

**General rule:** before calling `snap.get('X')`, trace all code paths that lead to
that call and verify `X` is inserted into extras on every one. When in doubt, use
the direct typed source (repository, domain entity field) instead of extras.

---

## 3. Risk Engine Gate Consistency

Affected files: `src/application/use_case/assess_risk_use_case.py`,
`src/adapters/cli/screen_accum_commands.py`, `src/adapters/cli/analyze_swing_commands.py`

### 3a. Gate loops must use first-gate-wins semantics in both entry points

`AssessRiskUseCase` has two execution paths:
- `execute()` — single profile, returns immediately on first triggered gate (**first-wins**)
- `execute_all_profiles()` — all profiles at once

If `execute_all_profiles()` lacks a `break`, the second gate evaluates against an
already-mutated `assessment.risk_level` and silently overwrites the first gate's
result. The same ticker gets different risk levels depending on which method is called.

**Anti-pattern (execute_all_profiles inner loop):**
```python
for gate in self._execution_gates:
    gate_result = gate.evaluate(gate_ctx, assessment.risk_level)
    if gate_result.triggered and gate_result.override_risk is not None:
        assessment = replace(assessment, ...)
        # no break — last gate wins, inconsistent with execute()
```

**Correct pattern:**
```python
for gate in self._execution_gates:
    gate_result = gate.evaluate(gate_ctx, assessment.risk_level)
    if gate_result.triggered and gate_result.override_risk is not None:
        assessment = replace(assessment, ...)
        break  # first-gate-wins: matches execute() semantics
```

Any time you add a gate or change gate evaluation order: check **both** `execute()`
and `execute_all_profiles()` and verify they still agree.

### 3b. `evaluate_all_profiles()` is the single source of truth for profile lists

The structural gate early-return path must not hardcode `[CONSERVATIVE, BALANCED, AGGRESSIVE]`.
If a 4th profile is ever added to `evaluate_all_profiles()`, the hardcoded list silently
diverges and returns only 3 assessments.

**Anti-pattern:**
```python
# WRONG — will silently diverge if a 4th profile is added
assessments = [
    replace(gate_assessment, profile=RiskProfile.CONSERVATIVE),
    gate_assessment,
    replace(gate_assessment, profile=RiskProfile.AGGRESSIVE),
]
```

**Correct pattern — delegate profile enumeration:**
```python
proto_assessments = self._rule_engine.evaluate_all_profiles(latest_snapshot)
assessments = [
    replace(
        a,
        risk_level=gate_result.override_risk,
        confidence=gate_result.confidence,
        rationale=(gate_result.reason, *a.rationale),  # PREPEND — see §3c
        gate_triggered=type(gate).__name__,
    )
    for a in proto_assessments
]
```

### 3c. Gate override must PREPEND the gate reason, not REPLACE all rationale

When a structural gate fires and overrides all profiles in `execute_all_profiles()`,
the gate result replaces `risk_level` and `confidence` — but must **prepend** to `rationale`,
not replace it. Replacing discards profile-specific technical signals (RSI values, EMA
divergence, which rules triggered), which are meaningful audit information.

**Anti-pattern:**
```python
# WRONG — all technical rationale is discarded
replace(a, rationale=(gate_result.reason,), ...)
```

**Correct pattern:**
```python
# CORRECT — gate reason first, then technical context preserved
replace(a, rationale=(gate_result.reason, *a.rationale), ...)
```

The execution gate block (BandarGate downgrade) already uses this prepend pattern:
`rationale=(gate_result.reason, *assessment.rationale)`. Structural gate early-returns
must use the same form.

---

## 4. Domain Value Objects Must Clamp Computed Properties

Affected file: `src/domain/value_objects/shareholding_composition.py`

Provider data contains occasional malformed values (e.g., `institution_pct=110`
from a data-entry error). A computed property with no bounds check silently
produces `free_float_pct > 100`, which causes downstream gates that only check
`< threshold` to pass silently.

**Anti-pattern:**
```python
@property
def free_float_pct(self) -> float:
    return round(self.individual_pct + self.institution_pct, 2)  # can exceed 100
```

**Correct pattern:**
```python
@property
def free_float_pct(self) -> float:
    """Estimated publicly tradable float. Clamped [0, 100]."""
    return round(min(max(self.individual_pct + self.institution_pct, 0.0), 100.0), 2)
```

General rule: any computed property on a domain value object whose inputs come from
an external provider should enforce valid-domain invariants via clamping or assertion.

---

## 5. Response DTO Field Naming — API Size vs Rows Saved

When a provider always returns a full history window (e.g., Stockbit
`RT_PERIOD_LAST_1_YEAR` = 2591 rows), `fetched_count` and `added_count` are
different numbers. Never conflate them.

- `fetched_count` → rows actually saved to the DB (what changed this run)
- `added_count` → same as fetched_count in this codebase (new rows only)
- If you also need the API response size, give it a distinct name like `api_response_count`

In `FetchBrokerDailyFlowsResponse`, `fetched_count` means **rows saved**. Do not
change it back to mean API response size — that's the regression this replaced.

---

## 6. Gate Wiring Parity Across All CLI Command Sites

**This is the most dangerous category — fails silently in production.**

Affected files: `src/adapters/cli/screen_accum_commands.py`,
`src/adapters/cli/analyze_swing_commands.py`, `src/adapters/cli/analyze_risk_commands.py` (or equivalent)

When a new gate is added to the system, it must be wired in **every** CLI command that
builds an `AssessRiskUseCase`. If it's only in one command site, stocks that would be
filtered by that gate pass as LOW_RISK in other command paths — a silent, dangerous inconsistency.

**The failure mode:** FreeFloatGate was wired in `analyze risk` but not in `screen accum`
or `analyze swing`. Thin-float stocks (individual% + institution% < 15%) passed through the
screener as LOW_RISK while `analyze risk` on the same ticker correctly flagged HIGH_RISK.
A user trusting the screener output would unknowingly trade a structurally risky stock.

**Pattern to follow when adding a new gate:**

```python
# 1. Define the gate in src/domain/rules/your_new_gate.py
# 2. Add it to ALL of these locations:
#    - src/adapters/cli/screen_accum_commands.py   structural_gates=[..., YourNewGate()]
#    - src/adapters/cli/analyze_swing_commands.py  structural_gates=[..., YourNewGate()]
#    - src/adapters/cli/analyze_risk_commands.py   (if separate from risk_engine factory)
#    - src/application/services/bootstrap.py       create_risk_engine() factory
#    - Any other command that builds AssessRiskUseCase directly

# 3. Grep for all locations that instantiate AssessRiskUseCase or structural_gates=
grep -r "structural_gates" src/adapters/
grep -r "AssessRiskUseCase" src/adapters/
```

**Test to add:** a test that verifies the gate fires in the screener path AND the analyze
path for the same ticker/context. If both paths use `create_risk_engine()` from bootstrap,
one factory test covers both — which is why using the factory is preferred over inline
`AssessRiskUseCase` construction in CLI adapters.

---

## 7. GateContext Field Must Be Populated, Not Just Listed

**Corollary to §6 — also silent in production.**

A gate in `structural_gates=[..., FreeFloatGate()]` will silently skip (not fire) if the
corresponding field in `GateContext` is `None`. The gate implementation typically has
a guard: `if ctx.free_float_pct is None: return GateResult(triggered=False)`.

This means: wiring the gate class is not enough — the data field must also be populated
from the right source before the gate runs.

**Anti-pattern (`swing_analysis_workflow_use_case.py` before fix):**
```python
# shareholding is available on accumulation_candidate but was never read
gate_ctx = GateContext(
    ticker=request.ticker,
    snapshot_date=request.today,
    piotroski_f_score=fund.piotroski_f_score if fund else None,
    market_cap_idr=fund.market_cap_idr if fund else None,
    five_day_accdist=bandar.five_day_accdist if bandar else None,
    bandar_is_distributing=bandar.is_distributing if bandar else False,
    # free_float_pct absent — FreeFloatGate always sees None → always skips
)
```

**Correct pattern:**
```python
shareholding = accumulation_candidate.shareholding  # or fetch from provider
gate_ctx = GateContext(
    ...
    free_float_pct=shareholding.free_float_pct if shareholding else None,
)
```

**Checklist when wiring a new gate:**
1. Gate class is in the `structural_gates` or `execution_gates` list ✓
2. The GateContext field the gate reads is populated from the correct data source ✓
3. The data source is fetched/available at the point where GateContext is built ✓

---

## 8. Thread `as_of_date` Through All Provider Calls in Backtest Mode

Affected file: `src/application/services/risk_engine.py`

When a service method accepts `as_of_date` for temporal integrity (backtest support),
**every** downstream provider call that supports historical queries must also receive
that date. Forgetting one call silently mixes live data into the historical context.

**Anti-pattern (before fix):**
```python
def assess(self, ticker: str, profile: str, as_of_date: date | None = None):
    gate_ctx = self._build_gate_context(ticker)  # ← as_of_date never forwarded

def _build_gate_context(self, ticker: str) -> GateContext:
    fund = self._fundamentals_provider.get_fundamentals(ticker)       # live data
    comp = self._shareholding_provider.get_composition(ticker)        # live data
    # as_of_date was available on the parent call but not passed here
```

Result: backtesting with `as_of_date=date(2025, 1, 1)` silently uses today's
fundamentals (Piotroski score, shareholding) while using historical candles.
The backtest looks clean but isn't — look-ahead bias in gate evaluation.

**Correct pattern:**
```python
def assess(self, ticker: str, profile: str, as_of_date: date | None = None):
    gate_ctx = self._build_gate_context(ticker, as_of_date)

def _build_gate_context(self, ticker: str, as_of_date: date | None = None) -> GateContext:
    fund = self._fundamentals_provider.get_fundamentals(ticker, as_of_date)
    comp = self._shareholding_provider.get_composition(ticker, as_of_date)
```

**Rule:** when adding `as_of_date` to a public method, grep for every provider call
inside that method AND its private helpers. All of them that accept `as_of_date` must
receive it. Missing even one creates silent look-ahead bias.

---

## 9. Always Pass `end_date=snapshot_date` When Fetching Candles for Gate Evaluation

Affected file: `src/application/use_case/assess_risk_use_case.py`

`repository.get_candles(ticker)` with no `end_date` always returns candles through
**today**, even when `snapshot_date` is a historical date. This causes look-ahead bias
in LiquidityGate: the 20-day median transaction volume is computed over future candles.

**Anti-pattern:**
```python
# In _inject_gate_context() or equivalent:
snapshot_date = gate_context.snapshot_date
candles = self._repository.get_candles(request.ticker.upper())   # returns through today!
ctx = replace(ctx, recent_candles=tuple(candles[-20:]))           # future candles included
```

**Correct pattern:**
```python
snapshot_date = gate_context.snapshot_date
candles = self._repository.get_candles(
    request.ticker.upper(),
    end_date=snapshot_date,    # temporal boundary — no future candles
)
ctx = replace(ctx, recent_candles=tuple(candles[-20:]))
```

**General rule:** any candle fetch whose result is used in a gate, indicator, or signal
computation during backtesting must be bounded by `end_date=snapshot_date` (or
`end_date=as_of_date`). Unbounded fetches are only safe for live ("today") evaluation.

---

## 10. Frozen Dataclass Cannot Have a Dict Field

Affected file: `src/domain/value_objects/signal_assessment.py`

`@dataclass(frozen=True)` generates `__hash__` from all fields. `dict` is unhashable,
so a frozen dataclass with a `dict` field raises `TypeError: unhashable type: 'dict'`
the first time the hash is computed (e.g., storing in a set or dict key).

**Anti-pattern:**
```python
@dataclass(frozen=True)
class SignalAssessment:
    breakdown: dict[str, float]   # TypeError when hashed
```

**Correct pattern — tuple of tuples + property for dict access:**
```python
@dataclass(frozen=True)
class SignalAssessment:
    breakdown: tuple[tuple[str, float], ...]   # hashable

    @property
    def breakdown_dict(self) -> dict[str, float]:
        return dict(self.breakdown)    # callers needing dict use this property
```

**General rule:** all fields on frozen dataclasses must be hashable types. Safe types:
`str`, `int`, `float`, `bool`, `date`, `Decimal`, `tuple`, `frozenset`, enums.
Unsafe: `list`, `dict`, `set`, any mutable container. If you need mutable-access
semantics, expose it via a `@property` that constructs the mutable type on demand.

### §10b. Use the domain-defined accessor, not a re-derived equivalent

When a domain object exposes a typed accessor (property or method), always use it
instead of re-deriving the same value at the call site. Using `dict(obj.breakdown)`
where the domain offers `obj.breakdown_dict` is both redundant and fragile: if the
property ever adds logic (caching, conversion, validation), call-site re-derivations
silently diverge.

**Anti-pattern:**
```python
"breakdown": dict(self.signal_assessment.assessment.breakdown),
```

**Correct pattern — use the property the domain explicitly defines:**
```python
"breakdown": self.signal_assessment.assessment.breakdown_dict,
```

The domain docstring (`breakdown uses tuple-of-tuples … Use breakdown_dict property
for dict access`) is the signal. When a docstring says "use X for Y access", use X.

---

## 11. Dead Constants Shadowed by Enum Dispatch Mislead Future Agents

Affected file: `src/application/use_case/assess_signal_use_case.py`

When classification dispatches on an enum (e.g., `SignalStrength.STRONG`), any
numeric threshold constants that are **not read** by the dispatch logic are dead code.
Leaving them named `_ENTER_THRESHOLD` or `_WATCH_THRESHOLD` misleads future agents
(and humans) into believing entry quality is score-based.

**Anti-pattern:**
```python
_STRONG_THRESHOLD = 70      # used ✓
_MODERATE_THRESHOLD = 45    # used ✓
_ENTER_THRESHOLD = 65       # never read — _classify_entry() dispatches on enum
_WATCH_THRESHOLD = 40       # never read

@staticmethod
def _classify_entry(strength: SignalStrength) -> EntryQuality:
    if strength == SignalStrength.STRONG:
        return EntryQuality.ENTER
    if strength == SignalStrength.MODERATE:
        return EntryQuality.WATCH
    return EntryQuality.AVOID
```

**Correct pattern:** delete constants that are not read anywhere. If entry thresholds
are ever needed, add them to the function that uses them, with a comment explaining
the relationship to strength thresholds.

**Test to catch this:** if you see a constant like `_X_THRESHOLD` that does not appear
in any function body (only in the module-level definition), it's dead. Grep before adding
or keeping such constants.

---

## 12. First-Class Service Injection Boundary (ADR-025)

**Context:** `SignalEngine` and `RiskEngine` are first-class application services.
`AssessSignalUseCase` and `AssessRiskUseCase` are their internal implementation details.

**The violation:** injecting `AssessSignalUseCase` directly into a peer use case
(e.g., `AccumulationScreenUseCase(signal_use_case=AssessSignalUseCase())`) creates a
coupling between two application-layer components at the wrong level. It bypasses the
first-class service boundary and makes future changes to `SignalEngine`'s internals
invisible to callers.

**Anti-pattern:**
```python
# WRONG — exposes internal implementation detail as a peer dependency
class AccumulationScreenUseCase:
    def __init__(self, signal_use_case: "AssessSignalUseCase | None" = None):
        self._signal_use_case = signal_use_case or AssessSignalUseCase()

    def _compute_signal(self, ctx):
        return self._signal_use_case.execute(AssessSignalRequest(..., signal_context=ctx))
```

**Correct pattern — inject the first-class service:**
```python
# CORRECT — SignalEngine is the public boundary; AssessSignalUseCase is hidden inside it
class AccumulationScreenUseCase:
    def __init__(self, signal_engine: "SignalEngine | None" = None):
        from src.application.services.signal_engine import SignalEngine as _SE
        self._signal_engine = signal_engine or _SE()   # lightweight: no providers needed
                                                        # when screener builds SignalContext itself

    def _compute_signal(self, ticker, ctx):
        return self._signal_engine.evaluate_with_context(ticker, ctx)
```

**Rule:** never inject `AssessSignalUseCase` or `AssessRiskUseCase` into any class outside
`signal_engine.py` / `risk_engine.py`. The first-class service is the contract; its internal
use case is an implementation detail. Callers hold `SignalEngine` / `RiskEngine` references.

**When `SignalEngine()` with no providers is correct:** the screener path calls
`evaluate_with_context(ticker, ctx)`, which passes `SignalContext` directly to the use case —
providers are bypassed entirely. Only `evaluate(ticker, date)` uses injected providers.
So a lightweight `SignalEngine()` is correct for callers that build their own `SignalContext`.

---

## 13. Fast-Path Reuse of Enrichment Results — Avoid Double Computation

**Context:** `SwingAnalysisWorkflowUseCase` delegates to `AccumulationScreenUseCase` to build
`accumulation_candidate`. The screener already computes `signal_assessment` on each candidate.

**The violation:** the workflow rebuilds `SignalContext` from the same candidate fields and
calls `evaluate_with_context()` again — identical inputs, identical output, wasted computation.

**Anti-pattern:**
```python
# WRONG — candidate.signal_assessment is already populated; this recomputes it
if accumulation_candidate is not None:
    bd = accumulation_candidate.bandar_detector
    ...  # 15-line SignalContext build
    signal_assessment = self._signal_engine.evaluate_with_context(request.ticker, signal_ctx)
```

**Correct pattern — 3-branch structure:**
```python
signal_assessment = None
if self._signal_engine is not None:
    try:
        if accumulation_candidate is not None and accumulation_candidate.signal_assessment is not None:
            # Fast path: screener already paid the cost — just reuse it
            signal_assessment = accumulation_candidate.signal_assessment
        elif accumulation_candidate is not None:
            # Fallback: candidate exists but screener ran without a signal_engine
            # (e.g. compare mode, test isolation). Recompute from candidate data.
            signal_ctx = _build_signal_ctx_from_candidate(accumulation_candidate, request)
            signal_assessment = self._signal_engine.evaluate_with_context(request.ticker, signal_ctx)
        else:
            # No candidate — use provider-based standalone evaluation
            signal_assessment = self._signal_engine.evaluate(request.ticker, request.today)
    except Exception as exc:
        warnings.append(f"Signal assessment unavailable: {exc}")
```

**Why the fallback branch matters:** some callers construct the screener without a
`signal_engine` (compare mode, lightweight tests). `candidate.signal_assessment` is then
`None`. The fallback branch handles this gracefully without breaking the fast path.

**General rule:** when a workflow passes an enriched object (candidate, response DTO) to a
downstream step, the downstream step should check whether the relevant computed field is
already populated before recomputing it from the same source data. This is structural
(single-computation invariant), not caching — no TTL, no invalidation needed.

---

## 14. MarketContextEngine — `universe=` Parameter Is Mandatory for Breadth and Flow Factors

**Context:** `MarketContextEngine.__init__` accepts `universe: list[str] = []`. Passing an empty
list (or omitting it) silently disables two of six scoring factors: `idx_breadth` and `foreign_flow`
both report UNAVAILABLE. No error is raised at construction time.

**The violation:** constructing `MarketContextEngine` without resolving the regime universe first.

```python
# WRONG — idx_breadth + foreign_flow always UNAVAILABLE; conviction is systematically deflated
engine = MarketContextEngine(market_repository=repo, config=cfg)
```

**Correct pattern — always resolve before constructing:**
```python
tickers = resolve_tickers(
    universe=APP_CFG.analysis.regime_universe,
    explicit=[],
    db_path=db_path,
)
engine = MarketContextEngine(
    market_repository=SQLiteMarketRepository(db_path=db_path),
    config=cfg,
    universe=tickers,
    broker_repository=SQLiteBrokerRepository(db_path=db_path),
    context_repository=SQLiteMarketContextRepository(db_path=db_path),
)
```

**Where this bites:** any CLI command that constructs `MarketContextEngine` inline — check
`today_commands.py`, `analyze_regime_commands.py`, and any new command that adds regime context.

**Related pitfall — benchmark override:** if the command accepts a `--benchmark` flag, use
`dataclasses.replace` twice (nested frozen dataclass) to propagate it to the config before
constructing the engine:
```python
if benchmark and benchmark != cfg.idx_trend.benchmark_ticker:
    cfg = dc_replace(cfg, idx_trend=dc_replace(cfg.idx_trend, benchmark_ticker=benchmark))
```
See §10 for frozen dataclass override patterns.

---

## 15. `assess_all_profiles()` Must Receive the Same Post-Processing as `assess()`

**Context:** `RiskEngine` exposes multiple public assessment entry points: `assess()`,
`assess_with_context()`, `assess_request()`, and `assess_all_profiles()`. Post-processing steps
(e.g., `_apply_regime_gate()`) are wired individually into each path — there is no shared
post-processing hook.

**The violation:** adding a post-processing step to `assess()` but forgetting `assess_all_profiles()`.
The multi-profile comparison view silently skips the gate, showing HIGH_RISK without the regime label.

**Detection heuristic:** any time you add or modify a post-processing step in one `assess_*` method,
grep for all other `assess_*` methods in `risk_engine.py` and apply the same step.

**Correct implementation for `assess_all_profiles()`** when the regime gate must apply:
```python
def assess_all_profiles(
    self,
    request: AssessRiskRequest,
    market_context: "MarketContext | None" = None,
) -> "AssessAllProfilesResponse":
    result = self._use_case.execute_all_profiles(self._inject_gate_context(request))
    if market_context is not None and market_context.gate_tightening:
        gate_label = f"regime:{market_context.regime.value}"
        gated = [
            replace(a, gate_triggered=gate_label)
            if a.risk_level == RiskLevel.HIGH_RISK and a.gate_triggered is None
            else a
            for a in result.assessments
        ]
        result = replace(result, assessments=gated)
    return result
```

Note: `_apply_regime_gate()` operates on a single `AssessRiskResponse`; `assess_all_profiles`
returns `AssessAllProfilesResponse` whose `.assessments` is a list of `RiskAssessment` objects.
The logic must be replicated inline using `replace()` on each item — it cannot call the helper
directly.

---

## 16. Vocabulary-Boundary Gate Failures — String-Matching Gates Fail Open After Vocab Migration

**The pattern:** any gate or filter that works by testing a vocabulary string silently fails open when
the vocabulary changes and not every comparison site is updated. This is the most insidious failure
mode in the codebase because: (a) there is no type error, (b) the gate continues to "work" for the
values it does recognize, and (c) the failing case is the high-risk regime you most need the gate to
catch.

**How the MCE migration triggered this simultaneously in three places:**

| Site | Old (failing) value | New (correct) value | Effect of mismatch |
|---|---|---|---|
| `tighten_in_regimes` config | `["WEAK", "RISK_OFF"]` | `["VOLATILE", "RISK_OFF"]` | VOLATILE market → gate never tightens |
| `_REGIME_TARGETS` dict | no RISK_ON / NEUTRAL / VOLATILE keys | added all MCE keys | all MCE regimes → 5%/5% default TP/SL |
| `SWING_COMPARE_VARIANTS` | `"sideways_only"` / `"weak_plus"` labels | MCE-vocab tuples | wrong regimes filtered in compare mode |

**Defense strategy — three rules:**

1. **Fail-closed for unrecognized values.** Any sidecar reader or gate that receives a string regime
   value should validate against a known set and coerce unknowns to `"RISK_OFF"`, not silently pass:
   ```python
   _KNOWN_REGIMES = {"RISK_ON", "NEUTRAL", "RISK_OFF", "VOLATILE", "BULLISH", "SIDEWAYS", "WEAK"}
   if raw is not None and raw.upper() not in _KNOWN_REGIMES:
       typer.echo(f"Warning: unrecognized regime '{raw}' ...", err=True)
       raw = "RISK_OFF"
   ```

2. **Keep backward-compat keys in lookup tables.** Old sidecar files still contain legacy labels.
   Lookup dicts (`_REGIME_TARGETS`, YAML `preset_targets`) should carry both old and new keys.

3. **When migrating a vocab, grep every comparison site.** Search for each old label string
   (BULLISH, SIDEWAYS, WEAK) across `src/`, `config/`, and `tests/` before closing the migration PR.

---

## 17. Business-Day Gap for Market Data Staleness

**Context:** `BuildMarketContextUseCase._staleness_warning()` checks how many days have passed since
the most recent candle. Using calendar days (`(as_of - candles[-1].date).days > 1`) fires a false
alarm every Monday: a 3-day weekend gap looks like stale data even though no trading occurred.

**Wrong:**
```python
if (as_of - candles[-1].date).days > 1:
    return StalenessWarning(...)
```

**Correct — count only weekdays (Mon–Fri):**
```python
def _business_day_gap(start: date, end: date) -> int:
    """Count trading-day gap: start exclusive, end inclusive."""
    days, current = 0, start + timedelta(days=1)
    while current <= end:
        if current.weekday() < 5:   # 0=Mon … 4=Fri
            days += 1
        current += timedelta(days=1)
    return days

if _business_day_gap(candles[-1].date, as_of) > 1:
    return StalenessWarning(...)
```

**Scope of the pattern:** apply this wherever `(date_a - date_b).days` is used as a "is this stale?"
or "how many sessions have passed?" test on market data. The correct threshold remains `> 1` because
a single skipped business day (public holiday, data provider gap) warrants a staleness flag.

---

## 18. Piecewise Scoring — Use Strict `<` at the Top of Each Tier Boundary

**Context:** `VixFactor._score()` (and any piecewise linear scorer) maps a continuous input value
onto a 0.0–1.0 score through ordered tier conditions. Using `<=` at the boundary between two tiers
causes a discontinuous score jump: a value exactly at the threshold takes the lower-tier score, while
the very next floating-point value takes the upper-tier score.

**Wrong (discontinuous at `cfg.high = 35.0`):**
```python
elif v <= cfg.high:           # v=35.0 → score=0.25
    score = 0.25 + (cfg.high - v) / (cfg.high - cfg.elevated) * 0.25
else:                         # v=35.001 → score=0.0   ← jump!
    score, label = 0.0, "STRESSED"
```

**Correct (boundary belongs to the more restrictive tier):**
```python
elif v < cfg.high:            # v=35.0 falls here: score=0.0 (the stricter tier)
    score = 0.25 + (cfg.high - v) / (cfg.high - cfg.elevated) * 0.25
else:                         # v >= cfg.high → VOLATILE override fires separately
    score, label = 0.0, "STRESSED"
```

**General rule:** in piecewise scoring, the tier boundary belongs to the *more restrictive* (higher
stress, lower score) tier. Use `< threshold` for the less-restrictive tier so that
`v == threshold` falls into the stricter tier. This maintains score monotonicity and prevents
discontinuous jumps.

**Applies to:** `VixFactor`, any future factor that uses a multi-tier `if/elif/else` scoring
pattern in `src/application/use_case/build_market_context_use_case.py` or similar.

---

## 19. `replace()` Fill-In Obligation for New Dataclass Fields

**Context:** `dataclasses.replace()` copies a dataclass instance with selected fields changed.
It silently leaves any field **not mentioned** at its current value (or default if the source
instance also had the default). A new field added to a dataclass does NOT force callers of
`replace()` to set it — unlike the constructor, which will raise `TypeError` if a required
kwarg is missing.

**The failure mode (TradeSetup ADR-026, commit 28087db):**
`gate_is_structural: bool | None` was added to `RiskAssessment`. The primary `execute()` path
used direct construction (`RiskAssessment(..., gate_is_structural=True)`), which was updated.
But four `replace()` call sites spread across two files were missed:

| Call site | Expected | Got | Result |
|---|---|---|---|
| `execute_all_profiles()` structural gate (assess_risk_use_case.py:479) | `True` | `None` | BLOCKED_STRUCTURAL → BLOCKED_EXECUTION |
| `execute_all_profiles()` execution gate (assess_risk_use_case.py:508) | `False` | `None` | correct by coincidence (None is falsy) |
| `_apply_regime_gate()` (risk_engine.py:238) | `True` | `None` | BLOCKED_STRUCTURAL → BLOCKED_EXECUTION |
| `assess_all_profiles()` regime replace (risk_engine.py:145) | `True` | `None` | BLOCKED_STRUCTURAL → BLOCKED_EXECUTION |

**Why it's silent:** `gate_is_structural: bool | None = None` has a default of `None`.
`replace(a, gate_triggered="FundamentalGate")` produces a valid object with `gate_is_structural=None`.
Downstream code checking `if risk.assessment.gate_is_structural:` gets `False` for `None`,
silently choosing the wrong branch.

**Rule — when you add a field to a dataclass:**

```python
# Step 1: find all replace() calls referencing this dataclass
grep -r "replace(" src/ | grep -v "^Binary"
# Then grep for type(gate).__name__ or whatever field you can identify
grep -rn "gate_triggered" src/

# Step 2: for every replace() call, explicitly set the new field
replace(a, gate_triggered=..., gate_is_structural=True)   # NOT: replace(a, gate_triggered=...)
```

**Step 3 — add a targeted test:**
```python
# Test that all four paths return the correct gate_is_structural value
def test_structural_gate_is_structural_in_all_profiles():
    result = use_case.execute_all_profiles(request_with_structural_gate)
    for a in result.assessments:
        assert a.gate_is_structural is True, f"profile {a.profile}: expected True got {a.gate_is_structural}"
```

**Primary vs secondary call sites:** constructor calls (primary `execute()` path) are usually the
first implementation and are updated. `replace()` calls in secondary paths
(`execute_all_profiles`, `assess_all_profiles`, helper functions) are the dangerous ones.
Grep specifically for `replace(` after adding any new dataclass field.

---

## 20. Early Return Hides Crash in Non-Happy-Path Code

**Context:** A function with an early return for the common case (e.g., "no adjustment needed,
return immediately") leaves the code below the early return effectively untested if tests
only exercise that common case.

**The failure mode (TradeSetup ADR-026, commit 28087db):**
`_apply_market_context()` in `signal_engine.py` has:
```python
if multiplier == 1.0 and not tighten:
    return response    # ← early return for RISK_ON/NEUTRAL regimes
```
All tests used RISK_ON or NEUTRAL market context (or no context at all), so they always hit
the early return. The code below contained a runtime crash:
```python
rationale=response.assessment.rationale + note,  # TypeError: tuple + str
```
1910 tests passed. Production would crash on the first RISK_OFF or VOLATILE regime evaluation.

**Pattern:**
```
early_return_condition → covers 90% of test cases
rest of function       → untested, contains crash
```

**Rule — for every early return in a non-trivial function:**
- Write at least one test that bypasses it
- The test should exercise the "expensive path" that the early return protects
- Name it clearly: `test_apply_market_context_risk_off_regime` not `test_apply_market_context`

**Functions in this codebase with early returns that need non-happy-path tests:**
- `_apply_market_context()` — bypass by using `multiplier < 1.0` or `gate_tightening=True`
- `_apply_regime_gate()` — bypass by setting `risk_level=HIGH_RISK` and `gate_tightening=True`
- `_staleness_warning()` — bypass by using stale candle dates

---

## 21. `TYPE_CHECKING` Guard Makes Symbols Invisible at Runtime

**Context:** `if TYPE_CHECKING:` is `False` at runtime. Imports inside this block are
available to type checkers (mypy, pyright) but do NOT exist in the running process.
Any runtime code that tries to use a symbol imported only under `TYPE_CHECKING` raises `NameError`.

**The failure mode (TradeSetup ADR-026):**
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.domain.value_objects.signal_assessment import EntryQuality  # invisible at runtime

def _resolve_action(self, sig, risk) -> SetupAction:
    eq = sig.assessment.entry_quality
    if eq == EntryQuality.ENTER:   # ← NameError: name 'EntryQuality' is not defined
        ...
```

The original fix was an inline import inside the method body:
```python
def _resolve_action(self, ...):
    from src.domain.value_objects.signal_assessment import EntryQuality  # re-imported every call
    ...
```
This works but re-executes the import on every call (Python caches `sys.modules`, so the cost
is a dict lookup, but it's still unnecessary overhead and misleading idiom).

**Correct pattern — real module-level import:**
```python
from src.domain.value_objects.signal_assessment import EntryQuality   # module-level, no guard

if TYPE_CHECKING:
    from src.application.use_case.assess_risk_use_case import AssessRiskResponse
    # ^ keep TYPE_CHECKING for things used ONLY in annotations, not runtime logic
```

**Rule:** `TYPE_CHECKING` is for type annotations in function signatures and class fields ONLY.
If a symbol is used in `if x == Symbol.MEMBER:` or any runtime comparison, it must be a real
module-level import. The inline-inside-method pattern is a workaround for circular imports —
if you don't have a circular import, just import at the top.

---

## 22. `tuple[str, ...] + str` TypeError — Append With `(item,)` Syntax

**Context:** Python's `+` operator on sequences requires both operands to be the same type.
`tuple + str` raises `TypeError: can only concatenate tuple (not "str") to tuple`.
This is non-obvious because `list + [item]` and `str + str` both work, leading agents to
assume `tuple + str` would silently coerce.

**The failure mode (TradeSetup ADR-026, signal_engine.py:290):**
```python
# SignalAssessment.rationale is tuple[str, ...]
# note is a plain str built by string concatenation
note = f" [regime:{regime} ×{multiplier:.2f} {base}→{adjusted}]"

new_assessment = replace(
    response.assessment,
    rationale=response.assessment.rationale + note,   # TypeError!
)
```

**Correct pattern — wrap the item in a single-element tuple:**
```python
rationale=response.assessment.rationale + (note,),   # tuple + tuple[str] ✓
```

**Variant patterns:**
```python
# Prepend (gate reason before technical rationale — see §3c):
rationale=(gate_result.reason, *a.rationale)          # unpack existing tuple ✓

# Append multiple items:
rationale=response.assessment.rationale + (item_a, item_b)   # ✓

# Append from a list:
rationale=response.assessment.rationale + tuple(new_items)    # ✓
```

**Why tests don't catch this:** the crash only fires when the `if multiplier == 1.0 and not tighten: return` early return is bypassed (see §20). RISK_ON/NEUTRAL regimes hit the early return. Add a test that uses `multiplier=0.8` (RISK_OFF) or `gate_tightening=True` to exercise this path.

---

## 23. CLI `runner.invoke(app, …)` Tests Leak Live Network — Stub Every I/O Seam, Not Just the Use Case

**Context:** `runner.invoke(app, [...])` runs the *entire* command, not just the
unit under test. The live-first CLI commands (`screen accum`, `today`,
`fetch market`) fetch/refresh as **side effects around** the core use case.
Mocking only the headline factory leaves *secondary* seams doing real
Stockbit/Yahoo HTTP — each `invoke` blocks ~10–14s on a TCP connect, and a
file of ~20–40 invokes exceeds the 120s cap and looks like a hang.

**The failure mode (fixed commits 30d017ed, cdd61e3d):**
```python
# Mocks the workflow factory — but screen accum ALSO auto-refreshes explicit
# tickers first (ADR-054 S1: _refresh_explicit_tickers_for_screen ->
# auto_refresh_swing_data -> live Stockbit candle fetch).
monkeypatch.setattr(
    "src.adapters.composition.screen_deps.create_run_accumulation_screen_workflow_use_case",
    fake_uc,
)
result = runner.invoke(app, ["screen", "accum", "INDF", "--format", "json"])  # ~12s: real fetch
```

**Diagnosing a "hang":** it is almost never a hang — it is cumulative network
latency. Confirm with `pytest FILE -o faulthandler_timeout=8`; the dumped stack
lands in `httpx`/`socket.create_connection`, and the frame above it names the
unstubbed seam.

**The seams per command (stub ALL that apply, at their call-site module):**
| Command | Extra live seams beyond the workflow factory |
|---|---|
| `screen accum TICKER` | `src.adapters.cli.plan_swing_optional_fetchers.auto_refresh_swing_data` |
| `fetch market` | `stockbit_market_time.fetch_and_cache_market_status` / `get_display_market_status`; `fetch_market_context_inputs.refresh_market_context_inputs` (^VIX/EIDO/IDR=X); macro calendar |
| `today` | uses `--offline` + patches `DailyBriefingUseCase` (correct model to copy) |

**Correct pattern — the default is zero network; the real path is opt-in and loud:**
```python
@pytest.fixture(autouse=True)
def _no_explicit_ticker_auto_refresh(request, monkeypatch):
    if request.node.get_closest_marker("uses_live_refresh"):  # explicit opt-out
        return
    monkeypatch.setattr(
        "src.adapters.cli.plan_swing_optional_fetchers.auto_refresh_swing_data",
        lambda **kwargs: [],
    )
```
Patch at the **call-site module** — these commands do local `from … import` inside
the function, so the name is bound there at call time. Give the stub a
**discoverable opt-out marker** (registered in `pyproject.toml`), never a silent
global autouse in a distant conftest — a future refresh test must fail loudly,
not mysteriously no-op.

**Architectural read:** needing to stub N seams for one command is the
`adapter-thinness` smell — the side-effect orchestration belongs in one
application use case the test can replace wholesale, not scattered `_refresh_*`
helpers in the adapter.

---

## Quick Reference — Component → Pitfall

| Component / scenario | Read section |
|---|---|
| Writing a new fetch/cache use case | §1 (all subsections) |
| Adding `refresh=True` to a fetch use case | §1a sub-bug ii |
| Boundary date in incremental save | §1a sub-bug iii (use `>=` not `>`) |
| Counting active broker codes / aggregate metrics | §1e |
| Reading `snap.get('X')` in analyze commands | §2 |
| Adding a new gate to `AssessRiskUseCase` | §3a, §6, §7 |
| Gating early-return in `execute_all_profiles` | §3b |
| Override rationale in profile gate early-return | §3c (prepend, don't replace) |
| Computed property on a value object from provider data | §4 |
| Adding counts to a fetch response DTO | §5 |
| Wiring a new gate in CLI adapters | §6 |
| Populating GateContext fields from the right source | §7 |
| Adding `as_of_date` to a service that calls providers | §8 |
| Fetching candles for gate/signal evaluation in backtest | §9 |
| Designing a frozen dataclass value object | §10 |
| Using a domain value object property for dict access | §10b |
| Naming threshold constants near enum dispatch logic | §11 |
| Injecting a dependency into a use case (service vs internal) | §12 |
| "Should I inject AssessSignalUseCase?" | §12 |
| Signal computed twice for the same ticker in workflow | §13 |
| Workflow receives enriched candidate — recompute or reuse? | §13 |
| Constructing MarketContextEngine in a new command | §14 |
| benchmark= override not reaching MCE config | §14 |
| assess_all_profiles() not applying regime gate | §15 |
| Gate that worked for old vocab silently disabled after migration | §16 |
| Sidecar reader receives unrecognized regime string | §16 |
| Monday staleness false alarm on market data freshness check | §17 |
| Piecewise scorer jumps at exact threshold value | §18 |
| Added new field to RiskAssessment/SignalAssessment/TradeSetup | §19 |
| `replace()` call not updated after new dataclass field added | §19 |
| BLOCKED_STRUCTURAL returned as BLOCKED_EXECUTION from all-profiles path | §19 |
| Tests pass (1910 green) but production crashes with certain inputs | §20 |
| Function has early return — non-happy path never tested | §20 |
| `NameError` on symbol imported under `TYPE_CHECKING` | §21 |
| Inline `from ... import X` inside method body (workaround for circular import) | §21 |
| `TypeError: can only concatenate tuple (not "str") to tuple` | §22 |
| Appending a string to `rationale: tuple[str, ...]` | §22 |
| CLI `runner.invoke(app, …)` test slow / "hangs" / times out | §23 |
| Writing a `screen accum` / `fetch market` / `today` CLI test | §23 |
| Mocked the use case but the invoke still does real Stockbit/Yahoo I/O | §23 |
