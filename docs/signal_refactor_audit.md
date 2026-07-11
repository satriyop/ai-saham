# Signal Refactor Code Alignment Audit

Date: 2026-07-11

Scope: audit current codebase alignment with `docs/signal_refactor.md`, using code as source of truth. This document intentionally does not change implementation behavior.

Layer plan:
- Domain: not touched
- Application: not touched
- Infrastructure: not touched
- Adapter: not touched
- Documentation: this audit file only

Verification run during audit:
- `.venv/bin/python -m pytest -q` -> 2954 passed
- `git diff --check` -> passed
- Code was trusted over prior audit text for file:line references.

## Executive Summary

The codebase is broadly aligned with the signal refactor direction: deterministic-first, evidence-based scoring, setup phase state, Alpha/Trigger projection, decision policy, forward labels, PIT replay, volatility fingerprints, and promotion guardrails all exist.

The remaining issues are not "phase not implemented" issues. They are contract drift and semantic mismatches that can mislead tuning or future agents:

1. RS-vs-IHSG policy is documented as 20-day core evidence, but entry policy uses 5-day RS.
2. Decision policy coverage/conviction floors use setup-phase coverage/conviction when phase exists, not the final signal coverage/conviction shown in the docs.
3. Institutional accumulation evidence says DIAGNOSTIC-only, but its builder still honors YAML `evidence_status`.
4. The Alpha/Trigger `market_context` slot is populated from sector context, not MarketContext/regime evidence.
5. The output contract in the doc is more ambitious than the current output: regime detection method, volatility multiplier inside decision constraints, evidence status map, and some phase age fields are not fully emitted.
6. `signal_refactor_phases.md` is stale relative to the tracker and code.

No production-breaking issue was found in the current tested code. The risk is future tuning confusion, not immediate command failure.

## Findings

### HIGH-1: RS Policy Uses 5-Day RS While The Canonical Doc Describes 20-Day RS

Code evidence:
- `src/application/services/setup_phase_detector.py:679` reads `setup_evidence.rs_vs_ihsg_5d`.
- `src/application/services/accumulation_candidate_evidence_builder.py:362-363, 378` attaches `rs_vs_ihsg_5d` and `rs_vs_ihsg_20d` to the candidate and passes `rs_vs_ihsg_5d` to `SetupEvidenceBuilder`.
- `src/application/services/relative_strength_calculator.py:35-36` computes both 5d and 20d values.

Doc evidence:
- `docs/signal_refactor.md:495-499` defines `relative_strength_context.rs_vs_ihsg_20d`.
- `docs/signal_refactor.md:516-535` describes `rs_20d_lag_warning` / `rs_20d_hard_exclude`.
- `docs/signal_refactor.md:1981` lists `rs_vs_ihsg_20d_at_signal` in the core fingerprint fields.

Why it matters:
The current entry cap / hard exclude behavior is driven by 5-day relative strength, while the design rationale talks about 20-day market leadership/distribution. A 5-day lag can be noise; a 20-day lag is closer to the structural rotation signal described in the doc. This changes which candidates are capped to WATCH or AVOID.

Recommendation:
- Decide explicitly: is RS policy 5d tactical, 20d structural, or both?
- If the doc remains canonical, change `SetupPhaseDetector._rs_reasons()` to use `rs_vs_ihsg_20d` and make `SetupEvidence` carry that field.
- If 5d is intentional, update `docs/signal_refactor.md` to say policy uses 5d for entry timing while 20d remains attribution/context.
- Add tests proving the chosen window drives `rs_policy_warning` and `rs_policy_hard_exclude`.

### HIGH-2: Decision Floors Use Setup-Phase Coverage/Conviction, Not Final Signal Coverage/Conviction

Code evidence:
- `src/application/use_case/assess_signal_evidence_use_case.py:130-137` sets decision-policy coverage and conviction from `request.setup_phase.coverage_score` and `request.setup_phase.conviction_score` when setup phase exists.
- `src/application/services/setup_phase_detector.py:427-428` defines phase coverage/conviction as local phase evidence, not whole-signal evidence.
- `src/application/use_case/assess_signal_evidence_use_case.py:101-103` computes canonical group confidence separately from setup/flow evidence presence.

Doc evidence:
- `docs/signal_refactor.md:89-110` defines coverage as evidence availability and conviction as directional strength.
- `docs/signal_refactor.md:2017-2052` presents output-level `coverage_score` / `conviction_score` as part of final signal decision.
- `docs/signal_refactor.md:2152-2154` pseudocode checks `coverage_score < min_coverage` and `conviction_score < min_conviction` without saying these are setup-phase-only values.

Why it matters:
The user-facing signal coverage may say one thing while regime decision floors are applied to a different coverage/conviction source. A future tuner may think it is tuning final signal coverage floors, but the code is gating against setup-phase confidence when phase exists.

Recommendation:
- Clarify the contract before tuning:
  - Option A: decision floors are final signal floors. Use Alpha/Trigger or whole-signal coverage/conviction.
  - Option B: decision floors are setup-phase readiness floors. Rename config/docs to `phase_min_coverage` / `phase_min_conviction`.
- Do not leave one `min_coverage` name for two different concepts.
- Add a regression test where signal coverage and phase coverage differ, proving which one gates ENTER.

### MEDIUM-1: Institutional Accumulation Claims DIAGNOSTIC-Only But YAML Can Still Change Evidence Status

Code evidence:
- `src/application/services/institutional_accumulation_evidence_builder.py:6-15` says the evidence is DIAGNOSTIC-only and `evidence_status is always DIAGNOSTIC`.
- `src/application/services/institutional_flow_config.py:63-69` reads `evidence_status` from YAML via `from_mapping()`.
- `src/application/services/institutional_accumulation_evidence_builder.py:210`, `249`, `258`, `272`, `284` return `self._config.evidence_status` from the in-memory config.
- `config/institutional_accumulation.yaml:4` currently sets `evidence_status: DIAGNOSTIC`.

Why it matters:
Today the config value is DIAGNOSTIC, and this evidence does not directly grant production scoring authority. But the code contract and comments say config cannot promote it. That is not true: changing YAML to LOW_WEIGHT or PRODUCTION changes the persisted evidence status. This is exactly the kind of accidental promotion path the refactor is trying to prevent.

Recommendation:
- Make `InstitutionalAccumulationConfig.from_mapping()` ignore raw `evidence_status` and force `EvidenceStatus.DIAGNOSTIC`, matching company quality and sector context producers.
- Remove `evidence_status` from `config/institutional_accumulation.yaml` or keep it only as a commented non-authoritative note.
- Add a regression test: raw config with `evidence_status: PRODUCTION` still yields DIAGNOSTIC.

### MEDIUM-2: Alpha/Trigger `market_context` Slot Actually Means Sector Context

Code evidence:
- `config/signal_engine.yaml:152-156` defines Alpha/Trigger group weights including `market_context`.
- `src/application/use_case/assess_signal_evidence_use_case.py:180-190` populates `market_context` from `sector_context_evidence`.
- `src/application/use_case/assess_signal_evidence_use_case.py:265-280` scores that group from `SectorContextEvidence.sector_regime`, not `MarketContext.regime`.

Doc evidence:
- `docs/signal_refactor.md:1255` has a separate Sector Context section.
- `docs/signal_refactor.md:1294` has a separate Regime Detection Evidence section.
- `docs/signal_refactor.md:2053-2061` output contract separates `market_regime_context` and `sector_regime`.

Why it matters:
This is behaviorally safe because the group is DIAGNOSTIC by default, but the naming is misleading. A future agent may tune/promote `market_context` thinking it represents IHSG regime, while it actually represents sector context.

Recommendation:
- Rename Alpha/Trigger group `market_context` to `sector_context` in config and code, or update the docs to explicitly define `market_context` as sector-context evidence.
- If keeping the name for compatibility, add a hard comment in `config/signal_engine.yaml` and `AssessSignalEvidenceUseCase` saying it is sector context, not MarketContext/regime.

### MEDIUM-3: Output Contract Lists Fields That Current Code Does Not Fully Emit

Code evidence:
- `src/domain/value_objects/decision_constraints.py:17-26` contains `regime_size_multiplier` and `effective_size_multiplier`, but no `volatility_size_multiplier` or `liquidity_size_multiplier`.
- `src/application/services/volatility_context.py:14-19` computes volatility multiplier separately.
- `src/application/services/swing_analysis_serialization.py:40-53` and `src/application/services/accumulation_observation_fingerprint.py:416-428` emit volatility context, but decision constraints do not consume it.
- `src/application/services/accumulation_observation_fingerprint.py:129-131` explicitly writes `regime_detection_method_at_signal: None` because `MarketContext` exposes no method field.
- `src/domain/value_objects/market_context.py:58-71` has regime, confidence, stability, and days-in-regime, but no detection method or last-changed date.

Doc evidence:
- `docs/signal_refactor.md:2053-2059` includes `regime_detection_method`, `regime_last_changed`, and `days_in_current_regime`.
- `docs/signal_refactor.md:2063-2068` includes `volatility_size_multiplier` and `liquidity_size_multiplier` inside `decision_constraints`.
- `docs/signal_refactor.md:2073-2078` includes an `evidence_statuses` map.

Why it matters:
The doc’s example reads like an implementation contract, but the code emits a partial version. This is not necessarily wrong, but it will confuse implementers and reviewers.

Recommendation:
- Split the doc output contract into:
  - `implemented_current_contract`
  - `target_contract_after_future_execution-policy work`
- Or implement the missing fields explicitly:
  - add `regime_detection_method` to `MarketContext` / `RegimeDetectionEvidence`,
  - carry `volatility_size_multiplier` into `DecisionConstraints` or TradeSetup policy,
  - emit an explicit `evidence_statuses` map in signal output.

### MEDIUM-4: Signal Refactor Phase Docs Disagree With Tracker And Code

Doc evidence:
- `docs/signal_refactor_phases.md:92, 129` says A1 is partially implemented and A2 is planned.
- `docs/signal_refactor_tracker.md:71-85` says A1-H are done and I is in progress.

Code evidence:
- A1 exists in `DecisionPolicyService`.
- A2 exists through `MarketContext` quality metadata and regime observations.
- B-H objects/use cases exist in code and are covered by tests.

Why it matters:
Future agents reading `signal_refactor_phases.md` alone will think early phases are not started and may duplicate work or unwind already-implemented behavior.

Recommendation:
- Make `docs/signal_refactor_phases.md` status-neutral, or update statuses to match the tracker.
- Add a single line at the top: "Implementation status lives in `docs/signal_refactor_tracker.md`; this file is the phase contract only."

### MEDIUM-5: SignalEngine Self-Fetch API Still Looks More Authoritative Than It Is

Code evidence:
- `src/application/services/signal_engine.py:101-124` `evaluate()` self-fetches enrichment but has no setup/flow evidence.
- `src/application/services/signal_engine.py:111-113` says evidence groups are unavailable in self-fetch path and confidence will be 0.
- `src/application/services/signal_engine.py:136-172` `evaluate_with_context()` is the real pipeline path for setup/flow/phase/sector/company evidence.

Why it matters:
The comments are clear, but the public method name `evaluate()` still looks like the main signal endpoint. A future CLI or agent could call it and get a neutral-prior / flags-only result, then treat that as a full signal.

Recommendation:
- Keep behavior for now, but add an explicit warning/rationale to returned assessments when `evaluate()` is used without evidence groups.
- Consider a later rename to `evaluate_context_only()` or `evaluate_fallback()` after checking call sites.
- Add tests that `evaluate()` cannot produce high-confidence ENTER without evidence groups.

### LOW-2: `setup_scoring` Example Still Shows RS As 15% Weight Beside Text Saying It Is Not Merely A Weight

Doc evidence:
- `docs/signal_refactor.md:461-473` shows `relative_strength_vs_ihsg.weight: 0.15`.
- `docs/signal_refactor.md:486-490` says RS should not be treated as only a 15% score component for breakout/accumulation/foreign-bounce.

Why it matters:
The text resolves the contradiction, but the YAML-like snippet can still mislead implementers into making RS purely additive.

Recommendation:
- Rewrite the snippet so RS appears under `eligibility_caps` or `max_decision_policy`, not only under weighted scoring.
- If RS keeps an additive score contribution, show both layers explicitly: `rs_additive_weight` plus `rs_decision_cap_policy`.

## Alignment Confirmed

These parts are implemented and broadly aligned with `docs/signal_refactor.md`:

- Deterministic-first boundaries: core signal/refactor code lives in application/domain, not CLI policy.
- Risk remains separate from signal; `DecisionPolicyService` caps signal entry but does not replace RiskEngine.
- Canonical scoring path is staged evidence via `AssessSignalEvidenceUseCase`, not the old six-factor factor list.
- Missing setup/flow groups lower coverage; they are not neutral-filled.
- BB compression is setup/phase evidence, not flow evidence.
- Volume trigger requires dry-up plus expansion, not raw volume spike alone.
- Setup entry authority is explicit in `config/swing_setups.yaml` and enforced by decision policy.
- Forward labels and signal observation fingerprints exist.
- Observation fingerprints persist setup family, setup phase, strategy evidence, institutional accumulation, ticker profile, sector context, company quality, Alpha/Trigger, regime, and volatility fields.
- Evidence authority caps are enforced by `AlphaTriggerAggregator`.
- Promotion guardrails exist in config loading and tuning patch validation.
- Tuning patch validation rejects archived six-factor and diagnostic company-quality paths.
- Full test suite currently passes.

## Recommended Execution Order

1. Fix RS window semantics.
   - This affects real entry caps and should be resolved before tuning RS thresholds.

2. Fix coverage/conviction naming and gating source.
   - Either use final signal coverage/conviction for decision floors or rename the policy to phase coverage/conviction.

3. Force institutional accumulation producer status to DIAGNOSTIC.
   - This removes a misleading promotion path and aligns with the producer’s own comment.

4. Rename or clarify Alpha/Trigger `market_context`.
   - Prevents sector context from being mistaken as regime context.

5. Reconcile output contract.
   - Either implement missing fields or mark them explicitly as target/future.

6. Compress/update phase docs.
   - Make tracker the status source and phase docs the contract source.

7. Continue live observation and label accumulation.
   - No tuning patch or evidence promotion should happen until readiness is patch-eligible.

## Do Not Do Yet

- Do not promote `market_context`, `company_quality_context`, domestic bandar evidence, sector context, or event alpha based on implementation completeness alone.
- Do not tune RS thresholds until the 5d vs 20d contract is settled.
- Do not tune `regime_conditioning.*`; code and config correctly mark it legacy diagnostic.
- Do not use historical replay labels as production proof if the fingerprints are incomplete or generated before the current PIT enrichment/fingerprint contract.

## Resolved Since Prior Audit

### LOW-1: Setup Phase Test Fixture Is Now Correct (Was A Real Drift Point)

Current code:
- `tests/application/services/test_setup_phase_history.py:215-245` now creates 21 candles matching current dry-up + expansion semantics.
- Full test run passes.

Why it matters:
This was previously failing because the fixture described the old expansion-only behavior. It is now fixed, but it is worth recording because it proves the volume-trigger contract changed materially.

Recommendation:
- No code action now.
- Keep the 21-session fixture as the canonical example of `dry_up_reference_sessions + 1`.

### INFO-1: Corporate Action Calendar Synced But Not Wired To Scoring

New code (commit `d5d805b`, 2026-07-11):
- `src/domain/value_objects/corporate_action_calendar.py` — `CorporateActionCalendarEvent`, `CorporateActionCalendarDate` value objects.
- `src/domain/value_objects/corporate_action_event.py` — `CorporateActionEvent` value object.
- `src/adapters/cli/fetch_calendar_commands.py` — CLI command for sync.
- SQLite tables: `corp_action_cache`, `corporate_action_calendar_sync`, `corporate_action_event_dates`, `corporate_action_events` — populated with IDX corporate action data.

Current status:
- Data is populated into SQLite but not consumed by `SignalEngine`, `CompanyQualityContext`, or any scoring provider.
- No evidence builder or use case reads the calendar tables during signal evaluation.

Why it matters:
This is a correct first step (data availability before scoring), but future agents should not assume calendar-aware scoring is already live. Calendar events can materially affect outcome labels (e.g., a dividend record date coinciding with a foreign-buy streak).

Recommendation:
- Add `CorporateActionCalendarEvidence` producer (DIAGNOSTIC) that checks whether forward labels overlap corporate action windows.
- Add a promotion gate: do not promote calendar evidence until base rate is > 10k observations.

