# Signal Engine Refactor Tracker

_Design rationale: `docs/signal_refactor.md`_
_Phase plan: `docs/signal_refactor_phases.md`_
_Started: 2026-07-03_

This file is the canonical phase-by-phase state for the SignalEngine staged-evidence refactor. Update it as each step completes. Survives context compaction — always check this file at the start of a new session before touching signal engine code.

---

## Phase Overview

| # | Phase | Status | Branch/Commit |
|---|-------|--------|---------------|
| 0 | Baseline & Evidence Audit | ✅ Done | see Phase 0 detail |
| 1 | Evidence Objects Beside Current Scores | ✅ Done | see Phase 1 detail |
| 2 | Setup Evidence Contract | ✅ Done | see Phase 2 detail |
| 3 | Flow Confirmation Group | ✅ Done | see Phase 3 detail |
| 4 | Replace Signal Aggregator | ✅ Done | 1788860, c0e47cd |
| 5 | Regime-Conditional Signal Interpretation | ✅ Done | f361b90, 01afcf0 |
| 6 | Confidence-Aware Classification | ✅ Done | e57e9fb |
| 7 | Persistence For Replayable Evidence | ✅ Done | pending commit |
| 8 | Walk-Forward Calibration Guardrails | 🔲 Not Started | — |

**Status legend:** 🔲 Not Started · 🔄 In Progress · ✅ Done · ⏸️ Deferred

---

## Invariants (never break these across any phase)

- No production scoring changes in Phase 0.
- No provider, repository, or CLI dependency may enter domain objects.
- `EvaluateSwingSetupUseCase` and `config/swing_setups.yaml` remain the only authoritative setup policy. No duplicate thresholds inside `SignalEngine`.
- `RiskEngine` remains the only gate authority. Risk factors must not be blended into bullish signal scores.
- No parallel legacy/v2 production paths. Phase 4 is a clean cut.
- No AI output may directly mutate config. `SwingTuningPatchValidator` + human approval are mandatory before any YAML apply.
- CLI additions must stay under existing command groups (`analyze`, `screen`, `trade`, etc.) unless the phase plan explicitly creates a new lifecycle group. Do not create top-level signal commands.
- Application use cases own persistence orchestration. Adapters only wire dependencies and format output. If a use case result must be persisted, the use case (or a thin workflow wrapper) calls the repository — not the adapter.

---

## Phase 0: Baseline And Evidence Audit

**Goal:** Make current signal behavior measurable before replacing it. No scoring changes.

**Status:** ✅ Done — 2157 tests pass, zero production scoring changes

### Sub-steps

- [x] 0.1 Add `SignalAuditReport` — per-factor: present/missing, raw value, score, configured weight, active normalized weight, data source, freshness
- [x] 0.2 Add `saham analyze signal-audit TICKER [--date DATE]` subcommand under existing `analyze` group
- [x] 0.3 Add DB coverage audit use case — usable row counts for insider, analyst, forward estimates, seasonality, bandar per factor
- [x] 0.4 Add fixture tests capturing current `AssessSignalUseCase` output for known representative cases (these are the comparison baseline for Phase 4, not frozen requirements)

### Files Created/Modified

| Action | File |
|--------|------|
| New | `src/domain/value_objects/signal_audit.py` |
| New | `src/application/use_case/audit_signal_use_case.py` |
| New | `src/application/services/signal_coverage_service.py` |
| New | `src/adapters/cli/analyze_signal_commands.py` |
| Modify | `src/application/services/signal_engine.py` — added `build_context()` public method |
| Modify | `src/application/services/bootstrap.py` — added `_resolve_signal_raw_weights`, `load_signal_weight_tables()` |
| Modify | `src/adapters/cli/analyze_commands.py` — registered `signal-audit` |
| New | `tests/application/use_case/test_audit_signal_use_case.py` (6 tests) |
| New | `tests/application/use_case/test_signal_baseline.py` (3 golden baseline cases) |
| Modify | `tests/adapters/cli/test_command_contract.py` — added `signal-audit` to expected analyze commands |

### Key Finding From Live Run (BBCA 2026-07-03)

`foreign_flow_quality` is the one missing factor. This is important: the screener path computes `foreign_flow_quality` from `foreign_flow_score` via `signal_context_builder.py`, but `SignalEngine.evaluate()` (self-fetch path) has no `ForeignFlowProvider` — so `foreign_flow_quality` is always None in the evaluate path. The Phase 0 audit makes this gap visible. Phase 0 preview shows renormalized score (excluding missing factor) = 70 vs composite = 66.

### Verify

- Existing signal tests pass unchanged.
- New audit tests use deterministic fixtures (no live provider calls).
- No production scoring changes.

---

## Phase 1: Evidence Objects Beside Current Scores

**Goal:** Introduce canonical evidence contracts. Thread `seasonality_total_years` into `SignalContext`. No scoring changes.

**Status:** ✅ Done — 2173 tests pass (16 new), zero scoring changes

### Sub-steps

- [x] 1.1 Add `FactorEvidence` frozen dataclass to domain — fields: `name`, `group`, `direction`, `strength`, `confidence`, `freshness`, `horizon`, `source`, `rationale`, `raw_fields`
- [x] 1.2 Add `SignalEvidence` frozen dataclass to domain — collection of `FactorEvidence` with aggregate confidence and coverage fields
- [x] 1.3 Extend `SignalContext` with `seasonality_total_years: int | None` — `SeasonalEdge` already carries it; it just needs to be threaded
- [x] 1.4 Update `signal_context_builder.py` — pass `se.total_years` as `seasonality_total_years` in `build_signal_context_from_candidate()`
- [x] 1.5 Add `SignalEvidenceBuilder` application service — builds `SignalEvidence` from `SignalContext` using current scores (no new scoring logic)
- [x] 1.6 Unit tests for evidence objects (complete, partial, missing data cases) and serialization determinism; `Freshness.STALE` enum exists but emission is deferred until timestamped evidence
- [x] 1.7 CLI display unchanged — no evidence surfaced in CLI output yet (deferred to later phase)

### Files Created/Modified

| Action | File |
|--------|------|
| New | `src/domain/value_objects/factor_evidence.py` — `Direction`/`Freshness`/`Horizon` str-Enums + `FactorEvidence` frozen dataclass |
| New | `src/domain/value_objects/signal_evidence.py` — `SignalEvidence` frozen dataclass |
| Modify | `src/domain/value_objects/signal_assessment.py` — added `seasonality_total_years: int | None = None` to `SignalContext` |
| Modify | `src/application/services/signal_context_builder.py` — added `seasonality_total_years=se.total_years if se else None` |
| New | `src/application/services/signal_evidence_builder.py` — `SignalEvidenceBuilder.build(context, breakdown)` |
| New | `tests/domain/value_objects/test_factor_evidence.py` (8 tests) |
| New | `tests/application/services/test_signal_evidence_builder.py` (8 tests) |

### Key Design Notes

- `SignalEvidenceBuilder` receives the already-computed `breakdown` tuple from `AssessSignalUseCase` — it annotates scores, never re-computes them.
- Presence detection is intentionally duplicated from `AuditSignalUseCase` (shared domain helper deferred).
- Direction rule: score ≥ 60 → BULLISH, ≤ 40 → BEARISH, MISSING always NEUTRAL (no fabricated direction from neutral fill).
- `seasonality_total_years` appears in `raw_fields` when set — Phase 6 sample guard reads it from `SignalContext`.

### Verify

- Evidence builder tests cover complete, partial, and missing data.
- `Freshness.STALE` is modeled but not emitted until a later phase carries
  cache/source timestamps into replayable evidence.
- Evidence serialization is deterministic under fixed inputs.
- No provider or CLI dependency enters domain objects.
- Existing signal and screener tests pass unchanged.

---

## Phase 2: Setup Evidence Contract

**Goal:** Make setup/timing structure visible to the signal layer without duplicating setup policy or changing scores.

**Status:** ✅ Done — 2186 tests pass (11 new), zero scoring changes

### Dependencies

- Phase 1 complete ✅

### Sub-steps

- [x] 2.1 Add `SetupEvidence` value object to domain — wraps: trend, rsi, bb_width_pctile, vwap_discount_pct, vwap_pct, setup_match, rs_vs_ihsg, volume_trend
- [x] 2.2 Add `SetupEvidenceBuilder` application service — consumes `AccumulationCandidate` + `SetupEvaluation`, emits `SetupEvidence`
- [x] 2.3 Add SetupMatch → evidence strength translation in builder only (MATCH → 100.0, PARTIAL → 60.0, NO_MATCH → 20.0). `EvaluateSwingSetupUseCase` untouched.
- [x] 2.4 RS vs IHSG date-gate: `_IHSG_AVAILABLE_FROM = 2025-07-01`; before that date or when rs_vs_ihsg_5d=None → freshness=MISSING, value=None
- [x] 2.5 Volume trend source-gate: candle_source="stockbit" → FRESH; "yahoo"/"yahoo_inferred" → MISSING, value=None
- [x] 2.6 `SwingEvidence.setup_evidence: SetupEvidence | None` added (default None); `SetupEvidenceBuilder` wired in swing workflow `execute()`, guarded on candidate+setup_eval presence, wrapped in try/except
- [x] 2.7 11 unit tests: match translation, RS date-gate (before/after cutoff), volume source-gating, technical field threading, bb_width_pctile bounds

### Files Created/Modified

| Action | File |
|--------|------|
| New | `src/domain/value_objects/setup_evidence.py` — `SetupEvidence` frozen dataclass with `__post_init__` validation |
| New | `src/application/services/setup_evidence_builder.py` — `SetupEvidenceBuilder.build()` with RS date-gate and volume source-gate |
| Modify | `src/application/use_case/swing_analysis_workflow_use_case.py` — `setup_evidence` field added to `SwingEvidence`; builder wired into `execute()` |
| New | `tests/application/services/test_setup_evidence_builder.py` (11 tests) |

### Key Design Notes

- RS vs IHSG: `_IHSG_AVAILABLE_FROM = date(2025, 7, 1)`. MISSING enforces `rs_vs_ihsg_5d = None` (no partial RS).
- Volume: only `candle_source == "stockbit"` → FRESH. Yahoo IDX volume is frequently 0 or synthetic.
- RS and volume sub-signals currently passed as None to builder (emit MISSING). Populated in a future follow-up when candle query infrastructure is available.
- `EvaluateSwingSetupUseCase` and `config/swing_setups.yaml` untouched.

### Key Design Notes

- RS vs IHSG is unavailable before 2025-07-01. Any backtesting or attribution over older data must handle `freshness: missing` for this sub-signal.
- `EvaluateSwingSetupUseCase` stays binary (MATCH / PARTIAL / NO_MATCH). The continuous translation lives only in `SetupEvidenceBuilder`.
- `SignalEngine` is untouched in this phase. Setup evidence flows into it only in Phase 4 via the replacement aggregator input.

### Verify

- `EvaluateSwingSetupUseCase` and `config/swing_setups.yaml` tests unchanged.
- Setup evidence absent when candidate fields are None.
- No scoring changes in production path.

---

## Phase 3: Flow Confirmation Group

**Goal:** Reduce double-counting across related smart-money signals. Resolve BB compression location permanently.

**Status:** ✅ Done — 2205 tests pass (17 new), BB disabled in flow score

### Dependencies

- Phase 1 complete ✅

### Sub-steps

- [x] 3.1 Add `FlowConfirmationEvidence` value object — sub-evidence: foreign consistency, foreign streak, foreign flow ratio, foreign VWAP discount, BCI, bandar broad score, smart/noise broker share
- [x] 3.2 Add `FlowConfirmationEvidenceBuilder` application service — groups sub-evidence, applies internal cap (default 0.80)
- [x] 3.3 **BB compression removal**: `bb_squeeze` default changed to `enabled=False` in `BollingerSqueezePolicy`. "bb" key still emitted at 0.0 in breakdown (re-enablable via explicit policy). Previous composite score 120 → 114 for max-squeeze inputs.
- [x] 3.4 Group cap applied: `capped_strength = min(uncapped_strength, group_cap)`. Uncapped = average of flow_strength + bandar_strength (when both present), else flow_strength alone.
- [x] 3.5 6 tests proving BB excluded from scored weight even at maximum squeeze. 11 builder tests covering sub-signal extraction, BB/RSI exclusion, bandar direction mapping, group cap, to_dict()

### Files Created/Modified

| Action | File |
|--------|------|
| New | `src/domain/value_objects/flow_confirmation_evidence.py` — `FlowSubSignal` + `FlowConfirmationEvidence` frozen dataclasses |
| New | `src/application/services/flow_confirmation_evidence_builder.py` — builder with BB/RSI exclusion and group cap |
| Modify | `src/application/use_case/score_foreign_flow_use_case.py` — `bb_squeeze` default `enabled=False` |
| Modify | `tests/application/use_case/test_score_foreign_flow.py` — expected "bb": 0.0, total: 114.0 |
| New | `tests/application/services/test_flow_confirmation_evidence_builder.py` (11 tests) |
| New | `tests/application/use_case/test_score_foreign_flow_bb_exclusion.py` (6 tests) |

### Key Design Notes

- BB belongs in `SetupEvidence` (price structure). RSI is price-action, not broker flow. Both excluded from `FlowConfirmationEvidence`.
- Flow sub-signal keys: cons, streak, vwap, flow, inst (5 of 7 breakdown keys).
- Group cap 0.80: prevents bandar + foreign flow from each contributing a full independent vote in Phase 4 aggregator.
- `FlowConfirmationEvidence` is diagnostic-only in Phase 3. Phase 4 uses `capped_strength` as scored group input.
- `bb_squeeze` re-enablable via explicit `BollingerSqueezePolicy(enabled=True)` for callers that need legacy behaviour.

---

## Phase 4: Replace Signal Aggregator

**Goal:** Make the evidence-first staged aggregator the canonical `SignalEngine`. Clean break — no parallel paths.

**Status:** ✅ Done — 2239 tests pass, AssessSignalEvidenceUseCase is canonical in SignalEngine and wired in all production paths with consistent trade_setup and MCE preview

### Dependencies

- Phases 1, 2, 3 complete
- Phase 0 fixture baseline captured

### Sub-steps

- [x] 4.1 Implement `AssessSignalEvidenceUseCase` — staged aggregation: setup quality → flow confirmation → fundamental flags → analyst flags → insider flags → confidence/freshness
- [x] 4.2 Implement `renormalize` missing-evidence policy: missing evidence excluded from weight denominator, always lowers confidence, no fabricated bullish/bearish direction
- [x] 4.3 Add YAML configuration for evidence groups, flag thresholds in `config/signal_engine.yaml`
- [x] 4.4 Add flag implementations: `VALUATION_STRETCHED` (P/E > 50, -10 pts), `ANALYST_BEARISH` (buy_ratio < 0.20, -8 pts), `INSIDER_SELLING` (net_buy_ratio < -0.30, -12 pts)
- [x] 4.5 Wired `AssessSignalEvidenceUseCase` as canonical path in `signal_engine.py`. `AssessSignalUseCase` retained as archived reference (not called by SignalEngine).
- [x] 4.6 Updated CLI displays: `screen_accum_display.py` and `analyze_swing_display.py` — replaced old 6-factor columns (Bandar/Foreign/Insider/Season/Analyst/Fwd) with new evidence columns (Setup/Flow/Conf%/Flags). Detailed breakdown now shows group names, evidence confidence, and flag penalties.
- [x] 4.6b Production wiring: `accumulation_screen_use_case.py` now builds `FlowConfirmationEvidence` per candidate (SetupEvidence intentionally absent — batch screener does not evaluate named setups; confidence=0.40). `swing_analysis_workflow_use_case.py` re-scores with both evidence objects after they are built, then recomposes `trade_setup` and MCE preview from the enriched signal so `SwingVerdict` is internally consistent. Backtest attribution tuning keys updated from `factors.*` to `evidence_groups.*` and `flags.*`. `config/signal_engine.yaml` header and inline comments rewritten to reflect Phase 4 reality — old `factors.*` and dead scoring sections marked ARCHIVED.
- [x] 4.7 Document before/after explanation for each Phase 0 fixture case where output changes
- [x] 4.8 Unit tests for all staged aggregation paths, renormalize policy, and each flag

### Files To Create/Modify

| Action | File |
|--------|------|
| New | `src/application/use_case/assess_signal_evidence_use_case.py` |
| Modify | `src/application/services/signal_engine.py` — replace flat aggregator path |
| Modify | `config/signal_engine.yaml` — add evidence groups, flag thresholds, missing-evidence policy |
| Modify | CLI signal display files |
| New | `tests/application/use_case/test_assess_signal_evidence_use_case.py` |

### Key Design Notes

- Initial scored weight split: Setup quality 60%, Flow confirmation 40% (starting hypothesis; Phase 8 calibrates).
- Insider activity initial cap: 5% to 8% positive context only.
- Seasonality initial cap: 3% to 5%.
- Fundamental context (forward valuation, analyst consensus, insider selling): flags/modifiers only; no default positive timing score.

### Phase 0 Fixture Before/After Commentary

Phase 0 golden fixtures in `tests/application/use_case/test_signal_baseline.py`
capture the archived six-factor `AssessSignalUseCase` behavior. They are not a
one-to-one production input for Phase 4 because the canonical path now consumes
`SetupEvidence` and/or `FlowConfirmationEvidence` evidence groups plus
negative-only flags from `SignalContext`.

Directly replaying Phase 0 `SignalContext` fixtures through
`AssessSignalEvidenceUseCase` therefore exercises the flag-only/no-evidence path:
no setup group, no flow group, confidence `0.0`, and neutral prior score `50`
unless a negative flag fires. This is intentional. Production paths must supply
evidence groups:

- `screen accum`: supplies `FlowConfirmationEvidence`; setup evidence is absent
  by design because batch screening does not evaluate a named setup. Expected
  confidence is `0.40` before a single-ticker swing workflow enriches it.
- `analyze swing`: supplies both `SetupEvidence` and `FlowConfirmationEvidence`
  when an accumulation candidate and named setup evaluation are available.

| Phase 0 case | Archived flat result | Direct Phase 4 flag-only replay | Explanation |
|--------------|----------------------|----------------------------------|-------------|
| `all_factors_present_strong` | `89 STRONG ENTER` | `50 MODERATE WATCH`, confidence `0.0` | Old positive bandar/foreign/insider/seasonality/analyst/valuation factors no longer create bullish score directly. Without setup/flow evidence groups, the new engine has no directional evidence and returns neutral prior. |
| `all_factors_missing_neutral` | `50 MODERATE WATCH` | `50 MODERATE WATCH`, confidence `0.0` | Same visible score, but semantics changed: old path neutral-filled six missing factors; new path reports no evidence groups and low confidence explicitly. |
| `bandar_and_flow_only` | `70 STRONG ENTER` | `50 MODERATE WATCH`, confidence `0.0` | Old path double-counted correlated bandar and foreign flow as two independent bullish factors while neutral-filling the rest. New production path requires `FlowConfirmationEvidence`; a raw `SignalContext` alone is insufficient directional evidence. |

This is the intended Phase 4 break point: bullish signal strength comes from
staged evidence groups, not from neutral-filled legacy factor averages.

### Verify

- Replacement output is deterministic under fixed inputs.
- Phase 0 fixtures have explicit before/after commentary for any changed cases.
- CLI output no longer relies on legacy flat breakdown semantics.
- All invariants hold (no risk gates in score, no duplicate setup thresholds).

---

## Phase 5: Regime-Conditional Signal Interpretation

**Goal:** Move `MarketContext` from late post-score multiplier to explicit evidence conditioning stage.

**Status:** ✅ Complete

**Commit:** f361b90; ADR/display/test compliance follow-up 01afcf0; compact CLI help/display follow-up pending commit

### Dependencies

- Phase 4 complete (replacement aggregator is canonical)

### Sub-steps

- [x] 5.1 Added `market_context: MarketContext | None = None` to `AssessSignalEvidenceRequest`; added `RegimeConditioningConfig` dataclasses to `assess_signal_use_case.py` and `SignalEngineConfig`
- [x] 5.2 Implemented `_condition_group_scores()` in `AssessSignalEvidenceUseCase`: RISK_ON=no-op; NEUTRAL=weak flow (<50) ×0.80; RISK_OFF=weak setup (<60) ×0.50; VOLATILE=setup ×0.70 + flow ×0.80. Applied BEFORE renormalization. `_apply_gate_tightening()` added for ENTER→WATCH cap.
- [x] 5.3 Regime notes appear in `rationale` tuple (visible in `--diagnostic`); `regime_conditioning=1.0` marker in breakdown when conditioning fires; `gate_tightening=1.0` when gate cap fires
- [x] 5.4 Retired `_apply_market_context()` module-level function and `apply_market_context()` public method from `signal_engine.py`. All three call sites now pass `market_context=market_regime` directly to `AssessSignalEvidenceRequest`. Workflow updated to pass regime to initial signal compute, re-score, and to set MCE signal preview to canonical signal.
- [x] 5.5 `tests/application/use_case/test_signal_regime_conditioning.py` — 18 tests covering all regime branches, gate tightening, idempotency, combined regime+flags. All pass.

### Files Modified

| Action | File |
|--------|------|
| Modify | `src/application/use_case/assess_signal_use_case.py` — added `NeutralRegimeConfig`, `RiskOffRegimeConfig`, `VolatileRegimeConfig`, `RegimeConditioningConfig`; extended `SignalEngineConfig` |
| Modify | `src/application/use_case/assess_signal_evidence_use_case.py` — added `market_context` field; `_condition_group_scores()`; `_apply_gate_tightening()`; updated `execute()` pipeline |
| Modify | `src/application/services/signal_engine.py` — removed `_apply_market_context()` and `apply_market_context()`; passes `market_context` to use case |
| Modify | `src/application/use_case/swing_analysis_workflow_use_case.py` — initial signal compute uses `market_context=market_regime`; MCE signal preview = canonical signal; evidence re-score passes `market_context=market_regime` |
| Modify | `src/application/services/bootstrap.py` — loads `regime_conditioning.*` config section |
| Modify | `config/signal_engine.yaml` — added `regime_conditioning:` section with per-regime thresholds/discounts |
| Modify | `tests/application/use_case/test_swing_analysis_workflow.py` — `FakeSignalEngine.apply_market_context` no longer imports retired function |
| New    | `tests/application/use_case/test_signal_regime_conditioning.py` — 18 regime conditioning tests |

### Verify

- All 58 tests in signal_regime_conditioning + swing_analysis_workflow + assess_signal_evidence pass.
- Full suite 2257 tests pass (commit f361b90).

### Follow-up: ADR-037 compliance fixes (post-review)

Code review identified four issues in Phase 5 commit (f361b90):
- [x] High: ADR-032 conflict → added ADR-037 to ARCHITECTURE_DECISIONS.md superseding preview-only constraint
- [x] Medium: workflow test `test_swing_workflow_canonical_trade_setup_unaffected_by_market_context` contradicted Phase 5 → renamed to `test_swing_workflow_mce_regime_forwarded_to_signal_engine`; now verifies market_context is forwarded when MCE enabled
- [x] Medium: MCE display "Signal impact" comparison showed "No signal score change (multiplier=1.0)" because preview==canonical → replaced with regime-aware "Signal: conditioning applied" message
- [x] Low/Medium: panel subtitle "evidence only — does not change final TradeSetup" → updated to "regime conditioning in canonical signal · risk preview via MCE"
- [x] Medium: CLI help text for `--with-market-context` no longer says MCE is what-if only; it now states the canonical signal/trade setup is conditioned with market regime
- [x] Low/Medium: compact Market Context panel now reads `regime_conditioning` / `gate_tightening` markers from signal breakdown and shows `conditioned` instead of comparing canonical signal with the identical preview object

---

## Phase 6: Confidence-Aware Classification

**Goal:** Stop treating incomplete evidence as equally reliable as complete evidence.

**Status:** ✅ Done — confidence-aware entry classification implemented; focused tests pass

### Dependencies

- Phase 4 complete
- Phase 1 complete (`seasonality_total_years` threaded through `SignalContext`)

### Sub-steps

- [x] 6.1 Add `confidence_score` (0.0–1.0) to `SignalAssessment` or replacement value object
- [x] 6.2 Implement seasonality 5-year sample guard using `seasonality_total_years` from `SignalContext` — fewer than 5 years → `freshness: missing`, not directional evidence
- [x] 6.3 Add config thresholds in `config/signal_engine.yaml`: `enter_min_confidence`, `watch_min_confidence`
- [x] 6.4 Update classification: ENTER requires score >= score threshold AND confidence >= enter_min_confidence; WATCH can tolerate lower confidence
- [x] 6.5 Unit tests for score-confidence disagreement cases (high score + low confidence → WATCH not ENTER)

### Files To Create/Modify

| Action | File |
|--------|------|
| Modify | `src/domain/value_objects/signal_assessment.py` — add confidence field |
| Modify | `src/application/use_case/assess_signal_evidence_use_case.py` — confidence-aware classification |
| Modify | `config/signal_engine.yaml` — confidence thresholds |
| Modify | CLI signal display — show confidence alongside score |
| New | `tests/application/use_case/test_confidence_aware_classification.py` |

### Key Behavior

- `SignalAssessment.confidence_score` is now part of the domain output and is
  serialized by `to_dict()`.
- `AssessSignalEvidenceUseCase` keeps score classification (`STRONG`,
  `MODERATE`, `WEAK`) score-based, but entry quality is confidence-aware:
  `ENTER` requires `confidence >= enter_min_confidence`; `WATCH` requires at
  least `watch_min_confidence`.
- Default thresholds: `enter_min_confidence: 0.70`,
  `watch_min_confidence: 0.40`.
- Flow-only high scores (`confidence=0.40`) become `WATCH`, not `ENTER`.
  Setup-only high scores (`confidence=0.60`) also become `WATCH` under default
  config.
- Seasonality with `seasonality_total_years < 5` is treated as unavailable:
  archived flat scoring returns neutral/no-data, and `SignalEvidenceBuilder`
  marks the seasonality factor `MISSING`.
- Unknown seasonality sample size (`seasonality_total_years is None`) is also
  unavailable. `SignalEngine.build_context()` now threads
  `SeasonalEdge.total_years` / `back_years`, and audit/evidence annotation share
  one application-layer presence rule.
- `Freshness.STALE` is still not emitted in Phase 6 because `SignalContext` does
  not carry source fetch timestamps. Stale-vs-fresh evidence remains Phase 7
  replay/persistence work; Phase 6 covers complete, partial, unknown-sample,
  short-sample, and missing evidence.

### Verify

- `python -m py_compile src/domain/value_objects/signal_assessment.py src/application/use_case/assess_signal_use_case.py src/application/use_case/assess_signal_evidence_use_case.py src/application/services/signal_evidence_builder.py src/application/services/bootstrap.py src/adapters/cli/analyze_swing_display.py`
- `./.venv/bin/pytest tests/application/use_case/test_confidence_aware_classification.py tests/application/use_case/test_assess_signal_evidence_use_case.py tests/application/use_case/test_assess_signal.py tests/application/services/test_signal_evidence_builder.py tests/application/use_case/test_signal_regime_conditioning.py tests/application/services/test_signal_engine.py`
- `./.venv/bin/pytest tests/adapters/cli/test_swing_commands.py`
- `./.venv/bin/pytest tests/application/use_case/test_swing_analysis_workflow.py tests/application/use_case/test_screen_risk_funnel.py tests/application/use_case/test_accumulation_screen.py`
- Post-review seasonality alignment: `./.venv/bin/pytest tests/application/services/test_signal_engine.py tests/application/services/test_signal_evidence_builder.py tests/application/use_case/test_audit_signal_use_case.py tests/application/use_case/test_assess_signal.py tests/application/use_case/test_signal_baseline.py tests/application/use_case/test_confidence_aware_classification.py tests/application/use_case/test_assess_signal_evidence_use_case.py`

---

## Phase 7: Persistence For Replayable Evidence

**Goal:** Make historical signal decisions replayable without live re-fetching.

**Status:** ✅ Done — candidate observations persisted locally and replayable via CLI

### Dependencies

- Phase 4 complete (`SignalEvidence` contract stable enough to serialize)

### Sub-steps

- [x] 7.1 Define candidate observation JSON schema + schema version field (starts at `schema_version: 1`)
- [x] 7.2 Create `candidate_observations` table — schema-versioned JSON blob column. **Does not reuse or extend `screen_snapshots`.** Table created/upgraded via `SqliteMigrationRunner` inside the repository. No separate `migrations/` directory.
- [x] 7.3 Add `CandidateObservationsRepository` port to domain
- [x] 7.4 Create `SQLiteCandidateObservationsRepository` — uses `SqliteMigrationRunner` for table init/upgrade
- [x] 7.5 Implement schema-evolution tolerance in reader: payload defaults `schema_version`, display uses optional-safe `.get()`, unsupported major schema versions are rejected with clear error
- [x] 7.6 Wire persistence into the accumulation screen use case — the use case calls the repository after screening completes. Adapter only injects the repository dependency.
- [x] 7.7 Add `saham analyze signal-replay TICKER DATE` subcommand under existing `analyze` group — loads stored payload, does not re-fetch live providers
- [x] 7.8 Unit tests for persistence, schema-version rejection, command contract, and replay read path

### Files To Create/Modify

| Action | File |
|--------|------|
| New | `src/domain/ports/candidate_observations_repository.py` |
| New | `src/infrastructure/persistence/sqlite_candidate_observations_repository.py` — table via `SqliteMigrationRunner` |
| Modify | Accumulation screen use case or workflow — call `CandidateObservationsRepository.save()` after screen run |
| Modify | Accumulation screen adapter — inject `CandidateObservationsRepository`; do not orchestrate persistence here |
| New or Modify | `src/adapters/cli/analyze_commands.py` or `analyze_signal_commands.py` — add `signal-replay` subcommand |
| New | `tests/infrastructure/persistence/test_sqlite_candidate_observations_repository.py` |
| New | `tests/application/use_case/test_replay_signal_observation_use_case.py` |
| Modify | `tests/adapters/cli/test_command_contract.py` — add `signal-replay` |

### Key Behavior

- `screen accum` persists schema-versioned candidate observations after screening
  completes. Persistence is local-first SQLite and best-effort; screen results are
  not blocked if observation persistence fails.
- Payload shape starts at `schema_version: 1` with root
  `artifact_type: candidate_observation`, request metadata, candidate snapshot,
  signal assessment, and optional trade setup.
- Replay reads the latest stored observation for `ticker + snapshot_date`; it
  does not instantiate market, broker, Stockbit, or signal providers.
- Unsupported schema versions greater than 1 fail with a clear error.

### Verify

- Local-first persistence only (SQLite, no remote calls).
- Schema version included in every persisted payload.
- Evidence replay reads stored payload; no live providers called.
- `screen_snapshots` schema unchanged.
- No new `migrations/` directory created; table management lives in the repository class.
- `python -m py_compile src/domain/ports/candidate_observations_repository.py src/infrastructure/persistence/sqlite_candidate_observations_repository.py src/application/use_case/replay_signal_observation_use_case.py src/application/use_case/accumulation_screen_use_case.py src/application/services/accumulation_screen_factory.py src/adapters/cli/screen_accum_workflow_factory.py src/adapters/cli/analyze_signal_commands.py src/adapters/cli/analyze_commands.py`
- `./.venv/bin/pytest tests/infrastructure/persistence/test_sqlite_candidate_observations_repository.py tests/application/use_case/test_replay_signal_observation_use_case.py tests/adapters/cli/test_command_contract.py tests/application/use_case/test_accumulation_screen.py`

---

## Phase 8: Walk-Forward Calibration Guardrails

**Goal:** Extend the existing tuning infrastructure to cover the new signal groups while preventing overfit.

**Status:** 🔲 Not Started

### Existing tuning infrastructure (extend, do not rewrite)

| Class | File | Role |
|-------|------|------|
| `SwingBacktestAttributionSummary` | `src/application/services/swing_backtest_attribution.py` | Allowlisted tuning targets |
| `SwingTuningDiffPolicy` | `src/application/services/swing_tuning_contracts.py` | Validates proposed YAML diff paths |
| `SwingTuningPatchValidator` | `src/application/services/swing_tuning_patch_validator.py` | Rejects out-of-range or unauthorized changes |
| `SwingTuningReviewJournal` | `src/application/services/swing_tuning_review_journal.py` | Records tuning history for audit |

### Sub-steps

- [ ] 8.1 Extend `SwingBacktestAttributionSummary` allowlisted targets — add signal group weights and evidence flag thresholds added in Phase 4
- [ ] 8.2 Extend `SwingTuningPatchValidator` — add YAML paths from Phase 4 `config/signal_engine.yaml` evidence group section
- [ ] 8.3 Add in-sample/out-of-sample split enforcement (minimum 70% IS, 30% OOS)
- [ ] 8.4 Add quantized weight step validator (weights must be multiples of 0.05)
- [ ] 8.5 Add max per-cycle parameter shift cap (maximum ±0.10 deviation from baseline per tuning cycle)
- [ ] 8.6 Profile calibration sweep on representative data; introduce NumPy or Polars only if pure-Python path cannot meet defined budget
- [ ] 8.7 Unit tests for new guardrail rules

### Files To Create/Modify

| Action | File |
|--------|------|
| Modify | `src/application/services/swing_backtest_attribution.py` |
| Modify | `src/application/services/swing_tuning_patch_validator.py` |
| Modify | `src/application/services/swing_tuning_contracts.py` (if DiffPolicy paths live here) |
| New | `tests/application/services/test_swing_tuning_guardrails.py` |

### Verify

- No AI output directly mutates config.
- Patch validation and dry-run remain mandatory before apply.
- Measurement compares saved before/after artifacts; does not claim causality.

---

## Notes / Decisions Log

_Append decisions, blockers, or scope changes here as they come up._

| Date | Note |
|------|------|
| 2026-07-03 | Design rationale and phase plan vetted across multiple rounds. Both docs finalized. Tracker created. |
| 2026-07-03 | Phase 0 complete. `saham analyze signal-audit BBCA --coverage` works end-to-end. 2157 tests pass. Key finding: `foreign_flow_quality` is always None in `SignalEngine.evaluate()` self-fetch path — no ForeignFlowProvider is injected. Screener path (signal_context_builder.py) is fine. Gap is now visible in audit output. |
| 2026-07-03 | Phase 1 complete. `FactorEvidence`/`SignalEvidence` domain objects + `SignalEvidenceBuilder` + `seasonality_total_years` threading. 2175 tests pass (after review fixes). No scoring changes, no CLI changes. Phase 2 and Phase 3 both unblocked. |
| 2026-07-03 | Phase 2 complete. `SetupEvidence` domain VO + `SetupEvidenceBuilder` + wired into `SwingEvidence`. 2188 tests pass (13 new, after review cleanup). RS sub-signal date-gated at 2025-07-01; volume sub-signal source-gated to stockbit. RS/volume currently MISSING (no candle query infra yet). |
| 2026-07-03 | Phase 3 complete. `FlowConfirmationEvidence` + builder. BB disabled by default in `ScoreForeignFlowUseCase` (key retained at 0.0). Group cap 0.80 applied to bandar+flow aggregate. 2205 tests pass (17 new). `FlowConfirmationEvidence` diagnostic-only; Phase 4 will use `capped_strength`. |
| 2026-07-03 | Phase 4 complete. `AssessSignalEvidenceUseCase` — staged aggregation with 2 evidence groups (setup 60%, flow 40%) + 3 flags (VALUATION_STRETCHED/ANALYST_BEARISH/INSIDER_SELLING). Missing evidence excluded from denominator (lowers confidence, not direction). `AssessSignalUseCase` retained as archived reference; no longer called by `SignalEngine`. 2239 tests pass (31 new). 4.6/4.7 complete after CLI display update and explicit Phase 0 before/after commentary. |
| 2026-07-03 | Phase 5 complete. `MarketContext` is canonical signal conditioning when `--with-market-context` is enabled. ADR-037 supersedes ADR-032 preview-only wording. Follow-up fixed stale CLI help and compact Market Context display so preview-vs-canonical equality no longer hides `regime_conditioning` / `gate_tightening`. Focused CLI tests pass. |
| 2026-07-03 | Phase 6 complete. `SignalAssessment.confidence_score` added; evidence confidence now caps entry quality. High score with low confidence becomes `WATCH`, not `ENTER`. Seasonality with unknown or fewer than 5 years is unavailable/missing, not directional evidence. Self-fetch, audit, and evidence annotation now share that rule. Focused signal, CLI, and workflow tests pass. |
| 2026-07-03 | Phase 7 complete. `candidate_observations` SQLite persistence added via `SqliteMigrationRunner`; `screen accum` persists schema-versioned candidate observations from the application use case; `saham analyze signal-replay TICKER DATE` replays stored payloads without live providers. Focused persistence, replay, command contract, and accumulation tests pass. |
