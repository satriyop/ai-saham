---
name: codebase-known-pitfalls
description: >
  Repeatable bug patterns and their correct solutions, learned from real bugs
  found in ai-saham code reviews (commits 87c24bd, post-R1 2026-06-24, R3 2026-06-24).
  Use this skill whenever you are about to: write or modify a fetch/cache use
  case, build or extend GateContext, add a new risk gate, thread as_of_date
  through a service, design a frozen dataclass value object, write profile-
  override logic in assess_all_profiles, add counts to a fetch response DTO,
  inject a service into a use case, or build enrichment-result workflows.
  Also trigger for: "gate not firing in screener but fires in analyze risk",
  "backtest results look too good", "free_float_pct over 100", "active_codes
  lower than expected", "CLOSE always shows dash", "profile list out of sync",
  "signal computed twice for same ticker", "should I inject AssessSignalUseCase".
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
