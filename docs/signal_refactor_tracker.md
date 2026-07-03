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
| 4 | Replace Signal Aggregator | 🔲 Not Started | — |
| 5 | Regime-Conditional Signal Interpretation | 🔲 Not Started | — |
| 6 | Confidence-Aware Classification | 🔲 Not Started | — |
| 7 | Persistence For Replayable Evidence | 🔲 Not Started | — |
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
- [x] 1.6 Unit tests for evidence objects (complete, partial, stale, missing data cases) and serialization determinism
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

- Evidence builder tests cover complete, partial, stale, and missing data.
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

**Status:** 🔲 Not Started

### Dependencies

- Phases 1, 2, 3 complete
- Phase 0 fixture baseline captured

### Sub-steps

- [ ] 4.1 Implement `AssessSignalEvidenceUseCase` — staged aggregation: setup quality → flow confirmation → fundamental flags → analyst flags → insider flags → priors → confidence/freshness
- [ ] 4.2 Implement `renormalize` missing-evidence policy: missing evidence excluded from weight denominator, always lowers confidence, no fabricated bullish/bearish direction
- [ ] 4.3 Add YAML configuration for evidence groups, flag thresholds, and missing-evidence policy in `config/signal_engine.yaml`
- [ ] 4.4 Add flag implementations: `VALUATION_STRETCHED` (P/E > 50), `ANALYST_BEARISH` (buy_ratio < 0.20), `INSIDER_SELLING` (large + recent + repeated)
- [ ] 4.5 Wire `AssessSignalEvidenceUseCase` as canonical path in `src/application/services/signal_engine.py`. Remove old flat `AssessSignalUseCase` path.
- [ ] 4.6 Update CLI displays to render new canonical evidence and assessment. No dual-engine comparison mode.
- [ ] 4.7 Document before/after explanation for each Phase 0 fixture case where output changes
- [ ] 4.8 Unit tests for all staged aggregation paths, renormalize policy, and each flag

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

### Verify

- Replacement output is deterministic under fixed inputs.
- Phase 0 fixtures have explicit before/after commentary for any changed cases.
- CLI output no longer relies on legacy flat breakdown semantics.
- All invariants hold (no risk gates in score, no duplicate setup thresholds).

---

## Phase 5: Regime-Conditional Signal Interpretation

**Goal:** Move `MarketContext` from late post-score multiplier to explicit evidence conditioning stage.

**Status:** 🔲 Not Started

### Dependencies

- Phase 4 complete (replacement aggregator is canonical)

### Sub-steps

- [ ] 5.1 Add `MarketContext` as explicit input to `AssessSignalEvidenceUseCase`
- [ ] 5.2 Implement regime conditioning in aggregator — RISK_ON: normal confidence; NEUTRAL: require stronger flow confirmation; RISK_OFF: downgrade weak setup evidence before scoring; VOLATILE: treat mean-reversion differently from trend-following
- [ ] 5.3 Add diagnostics showing which regime policy affected the signal (visible in `--diagnostic` output)
- [ ] 5.4 Retire `_apply_market_context()` in `src/application/services/signal_engine.py` (currently called at lines 109, 126, 139, 151; defined at line 290) — once regime is owned by the replacement aggregator
- [ ] 5.5 Unit tests proving regime is applied exactly once

### Files To Create/Modify

| Action | File |
|--------|------|
| Modify | `src/application/use_case/assess_signal_evidence_use_case.py` — add MarketContext input |
| Modify | `src/application/services/signal_engine.py` — remove `_apply_market_context()` (lines 109/126/139/151/290) |
| New | `tests/application/use_case/test_signal_regime_conditioning.py` |

### Verify

- Existing `MarketContextEngine` tests pass unchanged.
- RISK_OFF and VOLATILE behavior is deterministic and visible in diagnostics.
- Tests prove regime applied once.

---

## Phase 6: Confidence-Aware Classification

**Goal:** Stop treating incomplete evidence as equally reliable as complete evidence.

**Status:** 🔲 Not Started

### Dependencies

- Phase 4 complete
- Phase 1 complete (`seasonality_total_years` threaded through `SignalContext`)

### Sub-steps

- [ ] 6.1 Add `confidence_score` (0.0–1.0) to `SignalAssessment` or replacement value object
- [ ] 6.2 Implement seasonality 5-year sample guard using `seasonality_total_years` from `SignalContext` — fewer than 5 years → `freshness: missing`, not directional evidence
- [ ] 6.3 Add config thresholds in `config/signal_engine.yaml`: `enter_min_confidence`, `watch_min_confidence`
- [ ] 6.4 Update classification: ENTER requires score >= score threshold AND confidence >= enter_min_confidence; WATCH can tolerate lower confidence
- [ ] 6.5 Unit tests for score-confidence disagreement cases (high score + low confidence → WATCH not ENTER)

### Files To Create/Modify

| Action | File |
|--------|------|
| Modify | `src/domain/value_objects/signal_assessment.py` — add confidence field |
| Modify | `src/application/use_case/assess_signal_evidence_use_case.py` — confidence-aware classification |
| Modify | `config/signal_engine.yaml` — confidence thresholds |
| Modify | CLI signal display — show confidence alongside score |
| New | `tests/application/use_case/test_confidence_aware_classification.py` |

### Verify

- Tests cover complete, partial, stale, and missing evidence cases.
- Score-confidence disagreement cases produce expected classification.
- Seasonality guard rejects < 5 years as unavailable, not directional.

---

## Phase 7: Persistence For Replayable Evidence

**Goal:** Make historical signal decisions replayable without live re-fetching.

**Status:** 🔲 Not Started

### Dependencies

- Phase 4 complete (`SignalEvidence` contract stable enough to serialize)

### Sub-steps

- [ ] 7.1 Define `SignalEvidence` JSON schema + schema version field (start at `schema_version: 1`)
- [ ] 7.2 Create `candidate_observations` or `signal_evidence` table — schema-versioned JSON blob column. **Do not reuse or extend `screen_snapshots`.** Table created/upgraded via `SqliteMigrationRunner` inside the repository (follow the pattern from `7613c93`). Do not introduce a separate `migrations/` directory.
- [ ] 7.3 Add `CandidateObservationsRepository` port to domain
- [ ] 7.4 Create `SQLiteCandidateObservationsRepository` — uses `SqliteMigrationRunner` for table init/upgrade
- [ ] 7.5 Implement schema-evolution tolerance in reader: tolerate missing optional fields, default new optional fields safely, reject unsupported major schema versions with clear error, avoid CLI crashes on older snapshots
- [ ] 7.6 Wire persistence into the accumulation screen use case or workflow — the use case calls the repository after screening completes. The adapter only injects the repository dependency and formats output.
- [ ] 7.7 Add `saham analyze signal-replay TICKER DATE` subcommand under existing `analyze` group — loads stored payload, does not re-fetch live providers
- [ ] 7.8 Unit tests for persistence, schema-evolution (v1 payload parsed by v1+ reader), and replay read path

### Files To Create/Modify

| Action | File |
|--------|------|
| New | `src/domain/ports/candidate_observations_repository.py` |
| New | `src/infrastructure/persistence/sqlite_candidate_observations_repository.py` — table via `SqliteMigrationRunner` |
| Modify | Accumulation screen use case or workflow — call `CandidateObservationsRepository.save()` after screen run |
| Modify | Accumulation screen adapter — inject `CandidateObservationsRepository`; do not orchestrate persistence here |
| New or Modify | `src/adapters/cli/analyze_commands.py` or `analyze_signal_commands.py` — add `signal-replay` subcommand |
| New | `tests/infrastructure/persistence/test_sqlite_candidate_observations.py` |

### Verify

- Local-first persistence only (SQLite, no remote calls).
- Schema version included in every persisted payload.
- Evidence replay reads stored payload; no live providers called.
- `screen_snapshots` schema unchanged.
- No new `migrations/` directory created; table management lives in the repository class.

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
