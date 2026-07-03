# Signal Refactor Phase Plan

Date: 2026-07-03

Purpose: provide an implementation-ready phase plan for improving SignalEngine
composition and tuning. This plan is the controlling implementation plan;
`docs/signal_refactor.md` is the design rationale.

No runtime behavior is changed by this document.

## Source Corrections Applied To `docs/signal_refactor.md`

These corrections keep the design rationale aligned with current code:

- Insider activity is not assumed absent. It is wired when enrichment providers
  are used, passed through `signal_context_builder.py`, and must be measured
  through attribution before changing weight.
- Analyst coverage is described as broad cache coverage but limited usable
  analyst-count coverage: 296 cached rows, 87 usable rows, and 209
  zero-analyst placeholders in the inspected DB.
- Bollinger compression is documented as a current double-count / future
  triple-count risk, not as unconditional current triple-counting.
- Fundamental/analyst/insider demotion is documented in signal_refactor.md
  Section 13 as a replacement-design direction. It must be implemented through
  the canonical replacement aggregator, not through a parallel legacy/v2 split.

## Phase 0: Baseline And Evidence Audit

Goal: make current signal behavior measurable before replacing it.

Tasks:
- Add a deterministic audit report for current SignalEngine inputs:
  - factor value present/missing
  - factor score
  - configured weight
  - active normalized weight
  - data source/freshness when available
- Add fixture tests that capture representative current outputs for known cases.
  These fixtures are comparison evidence for the replacement, not a requirement
  to preserve old behavior byte-for-byte.
- Add a small local DB audit command or service for factor coverage:
  - insider usable coverage
  - analyst usable coverage
  - forward estimates coverage
  - seasonality coverage
  - bandar coverage
- Measure score variance and realized contribution before reducing or demoting
  any factor.

Outcomes:
- We know the actual current factor coverage and contribution.
- Future phases have a measured baseline and explainable break points.

Verify:
- Existing signal tests pass.
- New audit tests use deterministic fixtures.
- No production scoring changes happen in Phase 0.

## Phase 1: Evidence Objects Beside Current Scores

Goal: introduce the canonical evidence contracts used by the replacement
SignalEngine.

Tasks:
- Add immutable value objects:
  - `FactorEvidence`
  - `SignalEvidence`
- Minimum fields:
  - `name`
  - `group`
  - `direction`
  - `strength`
  - `confidence`
  - `freshness`
  - `horizon`
  - `source`
  - `rationale`
  - `raw_fields`
- Evidence raw fields must preserve enough source data for later policy:
  - seasonality `total_years` / `back_years`
  - candle source for volume-sensitive features
  - cache/fetch date for freshness and decay
- `SignalContext` must be extended with `seasonality_total_years: int | None`
  in this phase. `SeasonalEdge` already carries `total_years` and `back_years`,
  but `signal_context_builder.py` currently only passes `win_rate_pct` and
  `avg_monthly_return_pct`. The Phase 6 sample guard (reject fewer than 5 years)
  cannot be applied without this field being threaded through first.
- Extend the application scoring path toward evidence-first output.
- Until Phase 4 replaces the aggregator, keep CLI display behavior stable:
  render the existing breakdown/assessment by default, and expose early evidence
  only through explicit diagnostic/detail output. Do not put scoring policy in
  adapters.

Outcomes:
- Richer evidence is available for debugging and future tuning.
- The replacement engine has explicit inputs instead of scattered raw fields.

Verify:
- Evidence builder tests cover complete, partial, and missing data. `Freshness.STALE`
  is modeled in the enum but not emitted until a later phase carries cache/source
  timestamps into replayable evidence.
- Evidence serialization is deterministic.
- No provider or CLI dependency enters domain objects.

## Phase 2: Setup Evidence Contract

Goal: make setup/timing structure visible to the signal layer without
duplicating setup policy.

Tasks:
- Build `SetupEvidence` from existing data:
  - `AccumulationCandidate.trend`
  - `rsi`
  - `bb_width_pctile`
  - `vwap_discount_pct`
  - `vwap_pct`
  - `SetupEvaluation`
- Add deterministic setup sub-evidence where data quality allows:
  - 5-session price relative strength vs canonical `IHSG`
  - 5-session vs 20-session volume trend
- Volume trend must be source/confidence-gated. Stockbit candles can be treated
  as higher-confidence; Yahoo or `yahoo_inferred` volume must carry lower
  confidence or remain unavailable for scoring.
- IHSG candle coverage constraint: local DB has IHSG rows from 2025-07-01
  onward (Stockbit-backed). Equity candles go back to 2024-04-22. RS vs IHSG
  is unavailable for any backtest or analysis before 2025-07-01. Evidence
  builders must emit `freshness: missing` rather than computing a partial RS
  when the IHSG window is incomplete.
- Translate `SetupMatch` into evidence strength in the application evidence
  builder only. Do not change `EvaluateSwingSetupUseCase` into a scoring engine.
- Keep `EvaluateSwingSetupUseCase` and `config/swing_setups.yaml` as the
  authoritative setup policy.
- Do not add duplicate setup thresholds inside `SignalEngine`.
- Emit setup evidence alongside current signal output as diagnostic data. It
  becomes an input to the replacement aggregator in Phase 4.

Outcomes:
- Setup evidence is visible in signal diagnostics.
- Setup/timing structure is available to the replacement aggregator without
  duplicating setup policy.

Verify:
- Setup gate tests remain authoritative.
- Setup evidence appears only when source data is present.

## Phase 3: Flow Confirmation Group

Goal: reduce double-counting across related smart-money signals.

Tasks:
- Create one `flow_confirmation` evidence group.
- Include sub-evidence:
  - foreign consistency/streak
  - foreign flow ratio
  - foreign VWAP discount
  - BCI
  - bandar broad score
  - smart/noise broker share when available
- Keep sub-breakdown visible.
- Cap group influence so correlated broker/flow inputs cannot each vote as
  independent full-strength signals.
- BB compression policy decision (resolved here, not deferred):
  BB compression (`bb_width_pctile`) is a timing/structure signal — it indicates
  whether price is in a tight range before a potential move. It belongs in the
  setup quality group. Remove `bb_squeeze` from the scored contribution inside
  `ScoreForeignFlowUseCase`.
  BB evidence may remain visible in the flow breakdown for diagnostics but must
  not add scored weight there. Setup quality becomes the single scoring home for
  this signal.

Outcomes:
- Smart-money evidence is grouped and explainable.
- Future tuning can adjust the group rather than scattered overlapping factors.

Verify:
- Foreign-flow score breakdown remains visible.
- Bandar evidence remains visible as sub-evidence.
- Tests prove BB compression is counted in only one configured group at a time.

## Phase 4: Replace Signal Aggregator

Goal: make the evidence-first staged aggregator the canonical SignalEngine.

Tasks:
- Implement staged aggregation in application layer:
  - eligibility is not score; RiskEngine remains gate authority
  - setup quality
  - flow confirmation
  - fundamental/context flags
  - analyst context flags
  - insider context flags
  - priors
  - confidence/freshness
- Treat forward valuation, analyst consensus, and insider activity as a
  hypothesis for flags/modifiers unless attribution supports direct timing
  score weight.
- Keep candidate thresholds such as valuation stretched, analyst bearish, and
  insider selling configurable in YAML before enabling them.
- Implement the canonical missing-evidence policy:
  - missing evidence is excluded from score weight (`renormalize`)
  - missing evidence always lowers confidence
  - no unavailable factor may fabricate bullish or bearish direction
- The missing-evidence policy must be configured in YAML for auditability,
  emitted in diagnostics, and covered by tests. The shipped clean-break default
  is `renormalize`.
- Replace the old flat weighted average as the canonical SignalEngine path.
- Update CLI displays to render the new canonical evidence and assessment
  wording without a dual-engine comparison mode.

Outcomes:
- SignalEngine is staged, evidence-first, and confidence-aware at the contract
  level.
- Behavior changes are intentional, documented, and verified against the Phase 0
  baseline rather than hidden behind a compatibility flag.

Verify:
- Replacement output is deterministic under fixed inputs.
- Phase 0 fixtures have an explicit before/after explanation for changed cases.
- CLI output no longer relies on legacy flat breakdown semantics.

## Phase 5: Regime-Conditional Signal Interpretation

Goal: move MarketContext from late multiplier toward explicit evidence
conditioning.

Tasks:
- Feed `MarketContext` into the replacement aggregator.
- Let regime adjust confidence/threshold interpretation before final score.
- Add diagnostics showing which regime policy affected the signal.
- Remove any duplicate post-score regime adjustment once regime is part of the
  replacement aggregation policy. Specifically retire `_apply_market_context()`
  in `src/application/services/signal_engine.py` as the post-score multiplier
  path once regime conditioning is owned by the replacement aggregator.

Outcomes:
- RISK_OFF/VOLATILE downgrades are explainable.
- Market regime becomes a policy stage, not hidden score math.

Verify:
- Existing MarketContext tests pass.
- RISK_OFF and VOLATILE behavior is deterministic and visible.
- Tests prove regime is applied once.

## Phase 6: Confidence-Aware Classification

Goal: stop treating incomplete evidence as equally reliable.

Tasks:
- Add `coverage_score` or `confidence_score` to signal output.
- Missing data can still map to neutral raw score, but lowers confidence.
- Requires `seasonality_total_years` threaded through `SignalContext` from the
  Phase 1 task.
- Seasonality with fewer than 5 years for the scored calendar month should be
  unavailable or low-confidence evidence, not directional timing evidence.
- Define config thresholds for confidence-aware classification.
- ENTER requires both score and confidence thresholds.
- WATCH can tolerate lower confidence.

Outcomes:
- A high raw score with poor evidence coverage does not look as strong as a
  complete-evidence score.
- Coverage warning becomes part of the decision contract, not just text.

Verify:
- Tests cover complete, partial, unknown-sample, short-sample, and missing
  evidence cases. Stale evidence requires cache/source timestamps and is deferred
  to the persistence/replay phase.
- Classification tests cover score-confidence disagreement cases.

## Phase 7: Persistence For Replayable Evidence

Goal: make historical decisions replayable without live re-fetching.

Tasks:
- Define schema-versioned JSON payload for `SignalEvidence`.
- Persist evidence snapshots locally for screened candidates.
- Do not reuse `screen_snapshots` for evidence storage. The existing
  `screen_snapshots` table (`sqlite_watchlist_repository.py`) stores a thin
  watchlist snapshot: `flow_score`, `composite_score`, `consecutive_streak`,
  `net_buy_ratio`, `bci_label`. Its schema cannot hold structured `SignalEvidence`
  without breaking the watchlist/comparison use case. Create a separate
  `candidate_observations` or `signal_evidence` table with a schema-versioned
  JSON blob column.
- Parse persisted evidence with schema-evolution tolerance:
  - tolerate missing optional fields
  - default newly added optional fields safely
  - reject unsupported major schema versions with a clear error
  - avoid CLI crashes when rendering older snapshots
- Add read path for debugging historical signal decisions.

Outcomes:
- Rejected candidates become learnable.
- Future tuning can evaluate candidate-level evidence, not only completed
  trades.

Verify:
- Local-first persistence only.
- Schema version included.
- Evidence replay reads stored payload, not live providers.

## Phase 8: Walk-Forward Calibration Guardrails

Goal: extend the existing tuning loop to handle canonical evidence groups while
preventing overfit.

The tuning infrastructure already exists:
- `SwingBacktestAttributionSummary` — defines allowlisted tuning targets
- `SwingTuningDiffPolicy` — validates proposed YAML diffs against allowed paths
- `SwingTuningPatchValidator` — rejects out-of-range or unauthorized parameter changes
- `SwingTuningReviewJournal` — records tuning history for audit

Tasks:
- Extend `SwingBacktestAttributionSummary` allowlisted targets to include
  signal group weights and evidence thresholds.
- Extend `SwingTuningPatchValidator` rules to cover new YAML paths added in
  Phase 4.
- Add guardrails not yet present:
  - in-sample/out-of-sample split enforcement
  - quantized weight steps (5% increments)
  - max per-cycle parameter shift cap
- Define a local performance budget for calibration runs before adding
  numerical dependencies.
- Profile the tuning sweep; introduce NumPy or Polars only if profiling shows
  the pure-Python path cannot meet budget.
- Keep AI strictly in T2 tuner role: AI proposes YAML diffs,
  `SwingTuningPatchValidator` approves/rejects, human confirms before apply.

Outcomes:
- Tuning remains deterministic-first.
- Proposed changes are auditable and reversible.

Verify:
- No AI output directly mutates config.
- Patch validation and dry-run remain mandatory before apply.
- Measurement compares saved before/after artifacts and does not claim
  causality.

## Recommended Execution Order

1. Phase 0: add current-factor audit/coverage report.
2. Phase 1: add evidence objects beside current scores.
3. Phase 2: expose setup evidence, no scoring change.
4. Phase 3: group flow evidence and prevent double-counting.
5. Phase 4: replace the flat SignalEngine aggregator.
6. Phase 5: regime-conditional canonical policy.
7. Phase 6: confidence-aware classification.
8. Phase 7: evidence persistence/replay.
9. Phase 8: calibrated tuning guardrails.

## Non-Goals

- No rewrite from scratch.
- No AI-driven live decision path.
- No adapter-owned scoring policy.
- No duplicate setup thresholds inside SignalEngine.
- No risk gates blended into bullish signal score.
- No parallel legacy/v2 production paths.
- No compatibility alias unless a concrete persisted-data reader requires it.
