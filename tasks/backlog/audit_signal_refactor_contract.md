# Backlog: Signal Refactor Contract Fixes

**Source audit:** `tasks/thought/signal_refactor_audit.md` (verified 2026-07-14)
**Status:** Partial — HIGH-1 and CANONICAL-EVIDENCE-BOUNDARY are done; HIGH-2
is Partial (post-review Finding 1 fixed 2026-07-18: mandatory configured
SignalEngine wiring — see Task HIGH-2 below); ARTIFACT-IDENTITY is next.

---

> [!IMPORTANT]
> All tasks in this backlog touch live scoring/policy code.
> Before starting ANY task: read `AGENT_QUICKSTART.md`, confirm `AGENTS.md` / `GEMINI.md` compliance, and **state the layer plan**.
> Do not promote diagnostic evidence or tune thresholds while these contract ambiguities remain unresolved.
> Under ADR-042, narrow local-ML output may enter this backlog only as a typed
> evidence producer with immutable model/feature identity and model-specific
> validation. Full ML/API decisions remain separate non-authoritative
> challengers and are outside the evidence-promotion lifecycle.

---

## Execution Order

The authoritative cross-backlog phase order is
`tasks/backlog/signal_evidence_program.md`. This table is the signal-program task
inventory in approximate dependency order; do not interpret priority as license
to skip an unmet phase entry gate.

State labels are evidence claims: `Done` requires code/test verification,
`Partial` requires at least one verified task-owned implementation slice,
`Blocked` means a prerequisite prevents implementation, and `Not started` means
no task-owned implementation has been verified. Do not mark a task `Partial`
solely because adjacent infrastructure exists.

| # | Task ID | Priority | Description |
|---|---------|----------|-------------|
| 0 | `DQ-CONTRACT-GATE` | P0 | Resolve authoritative live-source/time blockers before semantic repairs |
| 1 | `HIGH-1` | P0 | Repair benchmark excess-return evidence and demote unvalidated RS gates |
| 2 | `CANONICAL-EVIDENCE-BOUNDARY` | P0 | Bind evidence, consumed-row provenance, and shadow availability across screen and swing |
| 3 | `HIGH-2` | P0 | Replace ambiguous coverage/conviction floors with explicit authority coverage and setup readiness |
| 4 | `ARTIFACT-IDENTITY` | P0 | Separate artifact uniqueness, semantic compatibility, and complete provenance |
| 5 | `CONTROL-POPULATION` | P0 | Capture eligible-universe controls, not only selected candidates |
| 6 | `PROMO-INTEGRITY` | P0 | Bind promotion to immutable, independently verified evaluation artifacts |
| 7 | `AUTH-SCOPE` | P0 | Scope authority by evidence, setup, horizon, and only proven segmentation dimensions |
| 8 | `HIGH-3` | P1 | Remove flags-only SignalEngine assessment paths and fail closed without production evidence |
| 9 | `IDX-EXECUTION-LABELS` | P1 | Label executable net outcomes under IDX market constraints |
| 10 | `WALKFORWARD-VALIDATION` | P1 | Replace one 70/30 split with purged, embargoed walk-forward evaluation |
| 11 | `INCREMENTAL-EDGE` | P1 | Require paired baseline-versus-evidence-challenger ablation |
| 12 | `SHADOW-PROMOTION` | P1 | Add evidence-challenger staged authority, monitoring, and rollback lifecycle |
| 13 | `BASELINE-RECERT` | P0 | Recertify or demote legacy baseline authority after the valid evaluation path exists |
| 14 | `MEDIUM-1` | MEDIUM | Remove producer-config authority from institutional accumulation evidence |
| 15 | `MEDIUM-2` | MEDIUM | Rename the persisted Alpha/Trigger sector evidence identity without changing real market context |
| 16 | `MEDIUM-3` | MEDIUM | Make output ownership truthful; defer dead-field migration to canonical artifact schema work |

---

## Task HIGH-1 — Repair Benchmark Excess-Return Evidence and Authority

**State:** Done

### Metadata

- **Type:** Data correctness + evidence-authority guardrail
- **Priority:** P0
- **Affects entry caps:** YES — the current unvalidated 5-session measurement can cap ENTER to WATCH or AVOID
- **Decision:** Temporarily make both measured horizons diagnostic-only. Repair the
  calculation and evidence contract, collect point-in-time labelled evidence,
  then promote only a validated setup-family-specific policy. Implement this
  option only.

### Problem

The current code calls the measurement `relative strength`, but the calculator
actually computes a benchmark excess return in percentage points:

```text
ticker return over N sessions - IHSG return over N sessions
```

`setup_phase_rs_policy.py` applies the 5-session value as production entry
authority. It emits `rs_policy_warning` or `rs_policy_hard_exclude`, and
`DecisionPolicyService` caps ENTER to WATCH or AVOID.

The archived design rationale proposes a 20-day field, but it is not an
executable specification:

- it is archived rather than a current authority document;
- it uses example thresholds such as `-0.03` and `-0.06`, implying different
  units from the calculator's percentage-point output;
- it provides no point-in-time out-of-sample evidence that either horizon or
  threshold should control entry.

The calculator also slices ticker and benchmark closes independently. It does
not align them by common IDX session date. Missing ticker candles, suspensions,
or provider gaps can therefore compare returns over different start/end dates.
That makes the current measurement unsafe as an authoritative gate.

Local database evidence confirms the horizon choice is material but does not
select a winner. Among 1,214 observations containing both measurements, applying
the current `-1/-4` percentage-point thresholds produces 688 different policy
buckets (56.7%). The mature `SWING_10D` labels currently match older
observations that do not contain these measurements, so the database cannot yet
justify 5 sessions, 20 sessions, or either threshold as a hard entry constraint.

The support-reclaim exception is also not a real exception. The code still
emits an `rs_policy_warning` marker, so `DecisionPolicyService` caps the result
to WATCH regardless of appended exception text. Its boolean condition appears
inverted, and no coherent mean-reversion family contract currently consumes it.

Key files:

- `src/application/services/relative_strength_calculator.py` — current formula
  and independently sliced candle series
- `src/domain/value_objects/setup_evidence.py` — formally carries only the
  5-session measurement
- `src/application/services/setup_evidence_builder.py` — hard-coded benchmark
  availability/freshness gate
- `src/application/services/candidate_setup_phase_evidence_assembler.py` —
  computes both values but passes only 5-session evidence into `SetupEvidence`
- `src/application/services/setup_phase_rs_policy.py` — creates authoritative
  warning/hard-exclude reason strings
- `src/application/services/decision_policy.py` — converts those strings into
  WATCH/AVOID caps
- `config/swing_setups.yaml` — current generic `-1/-4` thresholds shared across
  materially different setup families
- `docs/archive/signal_refactor_full_rationale.md` — historical design intent,
  not current executable authority

### Exact Measurement Contract

Do not introduce interpretive source fields such as `rs_tactical` or
`rs_structural`. The raw concept is benchmark excess return over an explicit
number of common sessions.

Preferred semantic names:

```text
excess_return_vs_ihsg_5_session_pct
excess_return_vs_ihsg_20_session_pct
```

Each computed window must expose a typed record equivalent to:

```text
BenchmarkExcessReturn
  benchmark
  window_sessions
  ticker_return_pct
  benchmark_return_pct
  excess_return_pct
  window_start
  window_end
  common_session_count
  status
  unavailable_reason
```

`window_sessions=5` means five close-to-close returns and therefore requires
six aligned closing prices. `window_start` and `window_end` must be identical
for ticker and benchmark.

### Desired Outcome

#### Stage 1 — Safe demotion and truthful naming

- Stop `rs_policy_warning` and `rs_policy_hard_exclude` from constraining the
  canonical decision.
- Continue computing and persisting both horizons as diagnostic measurements.
- Replace ambiguous `rs_vs_ihsg_*` naming in the corrected schema/contract with
  benchmark excess-return naming.
- Remove or disable the non-functional support-reclaim exception until a
  precise setup-family policy is validated.
- Mark the policy state explicitly as `DIAGNOSTIC_UNVALIDATED`.

#### Stage 2 — Calculation repair and evidence collection

- Align ticker and IHSG candles on common completed IDX sessions before
  calculating either return.
- Persist the component returns, exact common-session window, status, and
  unavailable reason.
- Backfill point-in-time observations only after common-session alignment is
  correct.
- Generate mature forward labels bound to the exact observation identity.
- Evaluate each horizon independently by setup family, regime, liquidity tier,
  and out-of-sample period.
- Compare each proposed gate against the same setup without the gate, after
  realistic costs.

#### Stage 3 — Explicit evidence promotion

- Promote a horizon to production authority only when point-in-time OOS results
  demonstrate incremental value for a named setup family.
- Give the policy role an explicit name in policy/config; do not encode an
  inferred role such as tactical or structural in the raw measurement.
- Calibrate horizon-specific, unit-explicit thresholds. Never reuse `-1/-4`
  automatically across horizons or setup families.
- Record the promotion decision through the repository's evidence-promotion
  guardrail/ADR process.

### Non-Goals

- No blind replacement of 5-session input with 20-session input.
- No threshold tuning before the point-in-time dataset is valid and labelled.
- No claim that either horizon represents tactical timing or structural
  leadership at the raw evidence layer.
- No preservation of ambiguous legacy field names in the new canonical schema
  merely for compatibility.
- No new data providers.
- No risk engine changes.

### Do Not Interpret This As

- Do not treat the archived rationale as canonical proof.
- Do not add `rs_vs_ihsg_20d` to `SetupEvidence` and declare the task complete.
- Do not calculate ticker and benchmark windows independently.
- Do not retain authoritative reason-string parsing while labelling the
  evidence diagnostic.
- Do not keep the support-reclaim flag as documentation-only behavior.
- Do not promote either horizon from in-sample results or row counts alone.
- Do not make missing excess-return evidence neutral or passed.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: add/rename a pure benchmark excess-return evidence value object and explicit availability status
- Application: common-session calculation, evidence assembly, temporary diagnostic authority, policy removal/guarding
- Infrastructure: no provider change; migration/version handling only if persisted canonical fields change
- Adapter: render exact measurement name, units, window dates, status, and diagnostic authority
- Documentation/config: remove unvalidated production thresholds and document the measurement/promotion contract
```

### Acceptance Criteria

- [x] Ticker and IHSG returns use the same common-session start and end dates
- [x] Five-session calculation requires six aligned closes; 20-session requires 21
- [x] Missing/suspended/gapped series return unavailable or use only explicitly aligned common sessions
- [x] Both horizons expose component returns, excess return, exact window, unit, status, and unavailable reason
- [x] Neither horizon can cap ENTER while status is `DIAGNOSTIC_UNVALIDATED`
- [x] `DecisionPolicyService` does not infer authority from diagnostic RS reason strings
- [x] The broken support-reclaim exception is removed
- [x] Full test suite passes
- [x] `git diff --check` is clean

---

## Task CANONICAL-EVIDENCE-BOUNDARY — Bind Evidence To Provenance And Availability

**State:** Done

### Metadata

- **Type:** Application-boundary architecture + shadow availability migration
- **Priority:** P0
- **Depends on:** HIGH-1
- **Required before:** HIGH-2 authority enforcement
- **Architecture:** ADR-041
- **Decision:** Replace workflow-specific evidence/availability plumbing with
  one typed signal-evidence input shared by the candidate-producing
  accumulation screen and `saham analyze swing`. Keep availability shadow-only
  and preserve every current score and decision. Implement this option only.

### Problem

Both workflows call `AssessSignalEvidenceUseCase`, but evidence is assembled
through different paths. DQ-002J adds useful `analyze swing` shadow diagnostics
after scoring; it is a prototype, not the final boundary. Extending that pattern
independently into the screener would allow evidence, consumed-row provenance,
and availability to drift and would leave HIGH-2 without one trustworthy input
on which to base authority coverage or setup readiness.

### Required Contract

Introduce typed application/domain contracts, following established naming,
that bind per evidence group:

```text
evidence value
exact consumed-row provenance
resolved EvidenceSourceAvailability
```

The candidate-producing path (`AccumulationScreenUseCase` /
`AccumulationCandidateSignalAssessor`) and deep-analysis path
(`SwingAnalysisWorkflowUseCase`) must both construct that same contract before
calling the canonical signal assessment. Evidence builders own provenance of
what they consumed; they must not ask downstream code to infer it from a
different query or a generic snapshot date.

The migration must remain `SHADOW`: availability is returned for diagnostics
but cannot affect scoring, coverage, classification, candidate selection,
TradeSetup, persistence eligibility, or tuning.

Here, "construct evidence" means build a typed in-memory assessment input. It
does not mean persist a canonical learning observation. `screen accum` and
`analyze swing` are consumers of the shared builder, not observation event
generators. Canonical capture belongs to `CONTROL-POPULATION` after
`ARTIFACT-IDENTITY`.

### End-To-End Invariants

- Evidence and its provenance/availability cannot be supplied independently.
- Every production-authority contributor is assessed or named as unassessed;
  unassessed contributors prevent complete-authority claims.
- Missing provenance resolves non-authoritatively; it is never inferred from
  execution time, database mtime, or a row not consumed.
- Both workflows use one effective session and one compatible calendar snapshot
  per execution, not per source or field.
- Diagnostic sources cannot raise production authority.
- Repeating either interactive command with the same effective session, source
  snapshot/cutoff, config, code, and evidence-contract identity cannot create a
  second learning sample or materially different canonical input.
- Invocation timestamp and command name are not canonical evidence inputs.
- Auto-refresh may change an assessment only through an explainable change in
  consumed source rows/snapshot identity.
- `AssessSignalEvidenceUseCase` remains repository-free.
- Adapters perform dependency wiring/rendering only.
- DQ-002J response diagnostics may be preserved for compatibility, but their
  values must originate from the canonical pre-score input, not a second
  workflow-specific assessment.

### Do Not Interpret This As

- Do not implement HIGH-2 authority coverage or setup readiness in this task.
- Do not activate availability as a decision gate.
- Do not integrate all registry sources without proving they feed a scored
  evidence group.
- Do not add a generic freshness/authority scalar or average statuses.
- Do not add repository reads to the signal scorer or policy to CLI adapters.
- Do not infer missing provenance or silently neutral-fill unavailable inputs.
- Do not persist a new canonical observation schema here; that belongs to
  `ARTIFACT-IDENTITY`.
- Do not make `screen accum` or `analyze swing` implicitly capture learning
  observations, even behind an idempotent upsert.
- Do not use CLI invocation frequency, invocation timestamp, or user-selected
  tickers to define the future learning population.
- Do not label the existing selected-candidate recorder
  `accumulation-discovery`; it lacks the required eligible-universe controls.
- Do not change weights, thresholds, recommendations, or tuning eligibility.

### Negative Tests

- A planted future row is excluded from both evidence and its provenance.
- Evidence cannot be constructed with availability from a different source
  read/cutoff.
- Missing and unassessed contributors cannot yield complete authority.
- Diagnostic evidence cannot increase authority.
- Screen and swing produce equivalent canonical evidence inputs for identical
  ticker/session/source fixtures.
- Repeated `screen accum` and `analyze swing` assessment does not add canonical
  observation rows.
- Identical semantic inputs produce equivalent canonical input regardless of
  command or invocation time; changed consumed source rows produce different,
  explainable provenance. Formal persisted identity belongs to
  `ARTIFACT-IDENTITY`.
- With shadow metadata removed from comparison, pre/post-migration signal,
  candidate inclusion/rank, TradeSetup, and serialized decision fields are
  unchanged.

### Close Criteria

- One typed canonical evidence input is used by both real
  `AssessSignalEvidenceUseCase` call paths.
- Provenance identifies the exact rows/dates/timestamps consumed by each scored
  evidence group.
- Source availability is resolved once and remains shadow-only.
- The shared builder is side-effect-free with respect to canonical learning
  persistence.
- DQ-002J no longer owns a separate post-score source-of-truth assessment.
- Focused screen/swing/signal/temporal-leakage tests and architecture tests
  pass; full suite passes when feasible; `git diff --check` is clean.
- HIGH-2 explicitly depends on this completed task before enforcing authority.

---

## Task HIGH-2 — Fix Coverage/Conviction Gating Source and Naming

**State:** Partial (2026-07-18) — signal_authority_coverage is the single
canonical authority-coverage metric (scoring, policy, output, persistence);
typed SetupPhaseReadiness replaces phase coverage/conviction gating; candidate
observations are schema 3 and forward labels schema 2; full test suite and
architecture tests pass; `git diff --check` clean. A post-review pass found
the scoring/policy contract above was correct but not universally enforced in
production: `AccumulationScreenUseCase` and its factories accepted an
optional `signal_engine` and silently fell back to a bare, unconfigured
`SignalEngine()` when a caller omitted it, and `signal_engine_config.py`'s
own Python defaults for RISK_ON/NEUTRAL `min_signal_authority_coverage` were
`0.0` instead of the canonical `0.70` in `config/signal_engine.yaml` — so an
unconfigured engine enforced no coverage floor at all. **Finding 1 fixed
(2026-07-18):** `signal_engine` is now a mandatory constructor/factory
parameter with no default and no `signal_engine or SignalEngine()` fallback
across `AccumulationScreenUseCase`, `AccumulationAuditUseCase`,
`SwingBacktestUseCase`, and both `accumulation_screen_factory.py` factories;
every production composition root (`screen accum`/`screen compare`,
`analyze swing` and its nested per-ticker screen, `analyze accum-audit`,
`trade log-accum`, `trade backtest-swing`, `analyze swing-compare`, and the
daily briefing) now injects one configured engine per invocation; the
RISK_ON/NEUTRAL code defaults now match the YAML (0.70). A follow-up review
of this fix found the YAML resolver itself
(`engine_bootstrap/signal_decision_policy_config_resolver.py`) still failed
open: `raw.get("min_signal_authority_coverage", 0.0)` meant any regime block
that omitted the key from `config/signal_engine.yaml` silently resolved to a
0.0 floor, recreating the original bypass despite the corrected dataclass
defaults. **Fixed (2026-07-18):** the resolver now raises `ValueError` when
`min_signal_authority_coverage` is missing from a regime's config block
instead of defaulting it, with a regression test covering a four-regime
config that omits the key from one regime. **Finding 2 fixed (2026-07-18):**
`GenerateSignalForwardLabelsUseCase` now excludes any candidate observation
whose schema is not exactly the canonical version (old, future, missing, or
malformed) from label generation entirely — no label, no fingerprint parse,
no candle read, and no repository write — instead of producing a fabricated
schema-2 UNAVAILABLE label from an incompatible schema-1/2 observation.
**Finding 3 fixed (2026-07-18):** readiness dates, latest-per-ticker counts,
raw counts, and target counts now use only schema-3 observations with
non-empty config_hash. Legacy diagnostic rows remain readable through
noncanonical repository methods. **Finding 4 fixed (2026-07-18):**
`SummarizeSignalForwardLabelsUseCase` now filters to exact schema-2 forward
labels before building any bucket, replaced the ambiguous
`coverage_bucket`/`conviction_bucket` groups with a canonical
`signal_authority_coverage_bucket`, and added typed
`setup_readiness_status`/`setup_readiness_current_phase`/missing-input/
failed-requirement attribution — with no fallback to the legacy fingerprint
fields. HIGH-2 stays Partial — other audit findings against this task are
not yet verified — do not mark Done until they are.

### Metadata

- **Type:** Decision-contract correctness + persisted-data semantic repair
- **Priority:** P0
- **Depends on:** CANONICAL-EVIDENCE-BOUNDARY
- **Affects entry gating:** YES — two differently defined coverage metrics and a
  non-directional phase-strength metric currently control ENTER
- **Decision:** Gate once on canonical production-authority coverage; represent
  setup-family readiness as typed requirements; keep phase strength and phase
  input completeness diagnostic; remove the generic derived conviction floor.
  Implement this option only.

### Problem

The current contract uses the words `coverage`, `confidence`, and `conviction`
for materially different calculations, then substitutes one calculation for
another depending on whether setup-phase evidence exists.

`SignalEvidenceGroupScorer.confidence` is not statistical confidence or trade
conviction. It is weighted evidence presence: setup contributes `0.60`, flow
contributes `0.40`, and the scorer already uses it to constrain classification.
The same value is exposed under aliases including `confidence_score`,
`coverage_score`, and `evidence_confidence`.

When setup phase exists, `AssessSignalEvidenceUseCase` does not pass that metric
to `DecisionPolicyService`. It substitutes:

- `setup_phase.coverage_score`: equal-weight presence of setup evidence, flow
  evidence, and a volume-valid flag;
- `setup_phase.conviction_score`: phase strength multiplied by that coverage.

Phase strength is a heuristic detector-strength value, not bullish trade
conviction. DISTRIBUTION and FAILED phases can legitimately receive high phase
strength. Calling this value `conviction` and imposing a generic minimum can
therefore make a strong bearish/failed classification look more entry-ready.
The phase coverage calculation also omits inputs such as benchmark evidence and
does not express setup-family-specific requirements.

When setup phase does not exist, both policy arguments fall back to the same
group-presence value. The policy then checks that one fact twice under different
names. This is not independent confirmation.

Alpha/Trigger does not provide a safe replacement scalar:

- its coverage includes configured diagnostic groups;
- its authority coverage is constrained by the current production/diagnostic
  weight split and has different semantics;
- its `conviction` is the normalized final score, so using both a score floor
  and conviction floor double-gates the same fact;
- the projection is currently built after decision policy resolution.

Persisted observations introduce a separate correctness defect. The candidate
fingerprint helper derives observation coverage from present flow fields divided
by two, rather than persisting the canonical signal metric. Those rows must not
be treated as compatible learning evidence merely because the column is named
`coverage_score`.

Local database inspection found 19,272 observations containing both signal and
phase metrics. Their signal and phase coverage values differed in every row;
the persisted signal coverage was `0.5` in all 19,272 rows, while phase coverage
was `1.0` in 19,269 rows. This is implementation-path evidence of semantic
incompatibility, not evidence that either threshold is calibrated correctly.

Key files:

- `src/application/use_case/assess_signal_evidence_use_case.py` — substitutes
  phase metrics into generic decision-policy arguments
- `src/application/services/signal_evidence_group_scorer.py` — weighted evidence
  presence currently named `confidence`
- `src/application/services/setup_phase_detector.py` — phase input coverage and
  detector strength currently combined as `conviction_score`
- `src/application/services/decision_policy.py` — generic regime-level
  `min_coverage` / `min_conviction` checks
- Alpha/Trigger projection and response mapping — additional conflicting names
  for coverage and normalized score
- candidate observation/fingerprint persistence path — persists flow presence
  divided by two as signal coverage
- decision-policy and observation regression tests — preserve current semantics
  and must be changed rather than worked around

### Exact Decision Contract

#### 1. Canonical signal authority coverage

Define one metric with one meaning:

```text
signal_authority_coverage =
  sum(configured weight for present PRODUCTION evidence groups)
  / sum(configured weight for required PRODUCTION evidence groups)
```

The denominator must be explicit for the evaluated signal contract. Diagnostic
groups cannot increase or decrease production-authority coverage. An unavailable
required production group remains missing; it is not silently renormalized away.

Rename `SignalEvidenceGroupScorer.confidence` and public aliases to
`signal_authority_coverage`. Apply any minimum authority-coverage gate exactly
once. If a regime-specific threshold is retained, name it
`min_signal_authority_coverage`; it must not silently change denominator or
meaning by regime.

#### 2. Directional signal score

`signal_score` is the scored directional evidence result. Do not derive a
second generic `conviction` scalar from that score and then gate on both. A
score threshold and `score / 100` conviction threshold are duplicate authority,
not independent evidence.

#### 3. Typed setup-family readiness

Replace generic phase coverage/conviction floors with a typed result equivalent
to:

```text
SetupPhaseReadiness
  setup_family
  status: READY | INCOMPLETE | INELIGIBLE | UNAVAILABLE
  missing_required_inputs
  failed_requirements
```

Each setup family owns explicit deterministic requirements. These may include
eligible phase state, required transition/sequence, volume confirmation, and
benchmark evidence only after that evidence has production authority. The
decision policy consumes the typed readiness result; it does not infer readiness
from a generic scalar.

`INCOMPLETE`, `INELIGIBLE`, and `UNAVAILABLE` are distinct. Missing data must not
be treated as a failed setup, and an ineligible phase must not be presented as
low confidence.

#### 4. Diagnostic phase metrics

If useful for observability, retain truthfully named metrics such as:

```text
phase_input_coverage
phase_detection_strength
```

They are diagnostic measurements. They are not trade conviction and cannot
independently authorize or veto ENTER.

#### 5. Persistence compatibility

Persist canonical `signal_authority_coverage` from the assessed signal contract,
not from a flow-only shortcut. Version the observation/fingerprint schema.
Readers must reject or exclude historical rows whose `coverage_score` came from
the flow-presence-divided-by-two path. HIGH-2 records their incompatible schema
and blast radius; physical quarantine or rebuild is owned by DQ-010. Do not
relabel those values in place.

### Desired Outcome

- One production-authority coverage definition is computed, exposed, persisted,
  and gated consistently.
- Setup eligibility/readiness is explicit per setup family and cannot be
  substituted by a detector-strength scalar.
- Directional score is not double-gated under the name `conviction`.
- Diagnostic phase completeness and strength remain observable without acquiring
  decision authority.
- Persisted observations have an explicit compatible schema/version and learning
  workflows exclude incompatible rows.

### Non-Goals

- No change to scoring weights.
- No new evidence builders.
- No risk engine changes.
- No threshold tuning or evidence promotion.
- No claim that authority coverage predicts outcome probability.
- No conversion of Alpha/Trigger diagnostic-group coverage into entry authority.

### Do Not Interpret This As

- Do not choose either current scalar wholesale and merely rename it.
- Do not rename `setup_phase.conviction_score` while preserving it as a generic
  entry floor.
- Do not use Alpha/Trigger `final_exact_score / 100` as independent conviction.
- Do not count diagnostic evidence toward production-authority coverage.
- Do not renormalize missing required production evidence out of the denominator.
- Do not preserve generic `min_coverage` or `min_conviction` compatibility aliases
  that retain ambiguous behavior.
- Do not encode setup-family readiness as another untyped float.
- Do not relabel historical `coverage_score` values as canonical without proving
  their producer and schema version.
- Do not update only output naming; all producers, consumers, persistence,
  tuning exclusions, tests, config, and docs must follow the same contract.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: add typed setup-family readiness/status; rename semantic assessment fields without IO or policy orchestration
- Application: compute canonical authority coverage, evaluate family readiness, remove duplicate conviction gating, and pass explicit facts to decision policy
- Infrastructure: version persisted observation/fingerprint semantics and reject incompatible coverage rows from canonical consumers; DQ-010 owns physical quarantine/rebuild
- Adapter: expose truthful authority-coverage, readiness, missing-input, and diagnostic phase fields; remove ambiguous aliases
- Documentation/config: replace generic floors and pseudocode with the exact contract; document schema compatibility
```

### Acceptance Criteria

- [ ] `signal_authority_coverage` has one formula across scoring, policy, output, persistence, and learning
- [x] Only present PRODUCTION evidence contributes to its numerator
- [x] Required PRODUCTION evidence remains in its denominator when unavailable
- [x] Diagnostic evidence cannot improve production-authority coverage
- [x] Any retained floor is named `min_signal_authority_coverage` and is applied once
- [x] Generic `min_coverage` and `min_conviction` decision floors are removed
- [x] No decision floor is derived from `signal_score / 100` or Alpha/Trigger normalized score
- [x] Each authoritative setup family returns typed READY, INCOMPLETE, INELIGIBLE, or UNAVAILABLE readiness
- [x] Readiness exposes missing inputs and failed requirements separately
- [x] Phase input coverage and detector strength, if retained, are diagnostic-only and truthfully named
- [x] Regression test: identical signal score and authority coverage with different diagnostic phase strength does not change authority by itself
- [x] Regression test: missing required production evidence lowers authority coverage and cannot be renormalized away
- [x] Regression test: diagnostic evidence presence cannot raise authority coverage
- [x] Negative test: high FAILED or DISTRIBUTION phase strength cannot satisfy bullish setup readiness
- [x] Observation/fingerprint persistence stores canonical coverage with an explicit schema/version
- [ ] Historical flow-derived coverage rows are identified as incompatible and excluded from canonical learning/tuning; their physical quarantine/rebuild is recorded for DQ-010
- [x] Existing tests that preserve phase scalars as generic decision floors are updated, not bypassed
- [ ] Config, public output, current docs, and archived rationale annotations use the same semantics
- [x] Focused decision-policy, readiness, persistence, and negative tests pass
- [x] Full test suite passes
- [x] `git diff --check` clean

---

## Task MEDIUM-1 — Remove Producer-Config Authority From Institutional Accumulation

**State:** Partial — scheduled after HIGH-3 in Phase 2.

### Metadata

- **Type:** Authority-boundary bugfix + persisted-provenance guardrail
- **Priority:** MEDIUM
- **Risk:** YAML or direct config construction can falsely label diagnostic
  evidence as production, contaminating display and persisted fingerprints and
  creating an unsafe future-consumer trap
- **Decision:** Remove `evidence_status` from the producer calculation config,
  reject the legacy key, and emit DIAGNOSTIC status at every builder path.
  Future scoring promotion belongs only to the validated central authority
  registry. Implement this option only.

### Problem

`InstitutionalAccumulationEvidenceBuilder` declares its output diagnostic-only,
persisted, and report-only. The implementation does not enforce that invariant.
`InstitutionalAccumulationConfig.from_mapping()` accepts `evidence_status` from
YAML, and the builder propagates it into the top-level evidence and nested
foreign, domestic, counterparty, and unavailable/error results.

This means changing `config/institutional_accumulation.yaml` to `PRODUCTION`, or
directly constructing `InstitutionalAccumulationConfig` with that enum value,
can create evidence and observation fingerprints falsely labelled production.

The current direct runtime impact must not be overstated: institutional
accumulation evidence is persisted and displayed but is not currently passed
into `AssessSignalEvidenceRequest` or the Alpha/Trigger projection. The existing
Alpha/Trigger registration `institutional_flow: PRODUCTION` refers to canonical
`FlowConfirmationEvidence`, not `InstitutionalAccumulationEvidence`. Therefore
the current defect does not by itself change canonical signal scoring or
`DecisionPolicy`.

It remains a real authority-boundary defect because:

- output and persisted provenance can make a false production claim;
- replay or learning consumers can misinterpret that claim;
- a future integration could trust the producer-local status and bypass the
  central promotion validator;
- comments currently promise an invariant that direct config construction can
  violate.

Key files:

- `src/application/services/institutional_flow_config.py` — producer calculation
  config currently owns an authority field
- `src/application/services/institutional_accumulation_evidence_builder.py` —
  propagates producer-config status through success and failure paths
- `src/application/services/institutional_flow_foreign_track.py` — nested status
  propagation
- `src/application/services/institutional_flow_domestic_track.py` — nested status
  propagation
- `src/application/services/institutional_flow_counterparty.py` — nested status
  propagation
- `src/application/services/accumulation_observation_institutional_fingerprint.py`
  — persists the producer status
- `config/institutional_accumulation.yaml` — exposes the unsafe authority key
- `src/application/services/engine_bootstrap/evidence_authority_validation.py` —
  validated central promotion mechanism; do not bypass or duplicate it
- `config/signal_engine.yaml` — canonical `institutional_flow` registration,
  which refers to a different evidence producer

### Exact Contract

#### Producer calculation config

`InstitutionalAccumulationConfig` owns calculation inputs only: windows, broker
classification, minimum sessions, component weights, and track weights. Remove
its `evidence_status` field.

Remove `institutional_accumulation.evidence_status` from YAML. Because this task
uses a clean break, `from_mapping()` must reject the key if present rather than
silently ignoring it:

```text
institutional_accumulation.evidence_status is not configurable; evidence
authority is owned by the validated central authority registry
```

The same rejection applies regardless of whether the mapping is wrapped in an
`institutional_accumulation` block or supplied as the block itself.

#### Producer output

While this producer remains diagnostic-only, every builder output must use
`EvidenceStatus.DIAGNOSTIC`, including:

- `InstitutionalAccumulationEvidence`;
- `ForeignInstitutionalTrack`;
- `DomesticBandarTrack`;
- `CounterpartyTransfer`;
- partial/unavailable results;
- whole-build exception fallback results.

No caller-supplied calculation config may alter that status.

#### Future promotion

If this producer later contributes to scoring, introduce or map it to an
explicitly named central evidence registration. Promotion requires the existing
manual OOS attribution record, validator, authority cap, and aggregation-path
enforcement. Do not reintroduce an authority field into the producer's
calculation YAML.

Keep the identities explicit:

```text
FlowConfirmationEvidence              -> current canonical institutional_flow slot
InstitutionalAccumulationEvidence     -> diagnostic producer in this task
```

This task must not demote or otherwise change the former.

### Desired Outcome

- Producer calculation config cannot express evidence authority.
- Legacy authority configuration fails explicitly rather than appearing to be
  accepted.
- Every institutional-accumulation result is truthfully diagnostic across
  success, partial-data, and exception paths.
- Persisted fingerprints cannot acquire production status through producer YAML.
- The central authority registry remains the sole future promotion boundary.

### Non-Goals

- No change to scoring weights or formula.
- No change to other producers (company quality, sector context).
- No new features.
- No change to current `FlowConfirmationEvidence` scoring authority.
- No change to the Alpha/Trigger `institutional_flow: PRODUCTION` registration.
- No promotion of institutional accumulation evidence.

### Do Not Interpret This As

- Do not silently ignore `evidence_status`; reject the stale key.
- Do not keep the dataclass field and merely force it in `from_mapping()`; direct
  construction would retain the bypass.
- Do not move authority selection to another producer-specific YAML key.
- Do not confuse institutional accumulation evidence with canonical flow
  confirmation evidence.
- Do not demote the existing Alpha/Trigger `institutional_flow` registration as
  part of this task.
- Do not rely only on the top-level status; nested and failure-path evidence must
  obey the same invariant.
- Do not rewrite historical persisted statuses in place without provenance and
  schema compatibility analysis.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: not touched
- Application: remove producer-config authority; enforce diagnostic status in top-level and nested builders across all result paths
- Infrastructure: not touched
- Adapter: not touched
- Documentation/Config: remove the legacy YAML key and document central-registry ownership
```

### Acceptance Criteria

- [ ] `InstitutionalAccumulationConfig` has no `evidence_status` field
- [ ] `config/institutional_accumulation.yaml` has no authority key
- [ ] Wrapped and unwrapped mappings containing `evidence_status` fail with the
      explicit ownership error
- [ ] Default and custom calculation configs produce DIAGNOSTIC top-level evidence
- [ ] Foreign, domestic, and counterparty nested evidence is always DIAGNOSTIC
- [ ] Partial-data and whole-build exception fallbacks are always DIAGNOSTIC
- [ ] No producer-local config path can create LOW_WEIGHT or PRODUCTION output
- [ ] Persisted institutional-accumulation fingerprints remain DIAGNOSTIC for new observations
- [ ] Negative test proves a serialized/fabricated producer status cannot grant Alpha/Trigger scoring authority
- [ ] Existing canonical `FlowConfirmationEvidence` and Alpha/Trigger `institutional_flow: PRODUCTION` behavior is unchanged
- [ ] Future-promotion documentation points exclusively to the validated central authority registry
- [ ] Focused config, builder, nested-output, fingerprint, and authority-boundary tests pass
- [ ] Full test suite passes
- [ ] `git diff --check` clean

---

## Task MEDIUM-2 — Rename Alpha/Trigger `market_context` to `sector_context`

**State:** Partial — scheduled after MEDIUM-1 in Phase 2.

### Metadata

- **Type:** Evidence-identity rename + persisted-schema compatibility
- **Priority:** MEDIUM
- **Risk:** The misleading name can corrupt future tuning/promotion decisions;
  an incomplete rename can split historical attribution or accidentally alter
  the real market-wide `MarketContext` system
- **Decision:** Cleanly rename only the Alpha/Trigger group populated by
  `SectorContextEvidence` to `sector_context`; reject the legacy key in new
  config; version persisted fingerprints; preserve old raw provenance through
  schema-aware historical interpretation. Implement this option only.

### Problem

The Alpha/Trigger group named `market_context` is populated exclusively from
`SectorContextEvidence`. Its current scorer reduces sector regime to
`BULLISH=75`, `NEUTRAL=50`, or `BEARISH=25`. It does not consume the real
market-wide `MarketContext`, IHSG regime, market breadth factors, volatility
state, global context, regime confidence, or regime stability.

The repository also has a genuine and operationally important `MarketContext`
concept backed by `MarketContextEngine`, `market_context_engine.yaml`, regime
gates, persistence, and CLI workflows. Reusing that name for a sector-only
Alpha/Trigger slot is objectively misleading. A future agent can reasonably
but incorrectly tune or promote the slot believing it represents IHSG regime.

This is not merely a cosmetic key rename. The group identity appears in:

- Alpha/Trigger default config and YAML;
- group weights and per-horizon route fractions;
- evidence registrations and future promotion records;
- group contributions and unavailable reasons;
- CLI/JSON output and tests;
- `alpha_trigger_route_metadata[].group` inside persisted observation
  fingerprints.

Local database inspection found 5,760 `signal_forward_labels` fingerprints
containing the legacy `market_context` identity. Renaming only live code would
split historical attribution between two group names.

The group is currently DIAGNOSTIC with zero effective scoring weight, so the
rename must not change canonical score or decision behavior. It also must not
transfer or invent a production promotion record.

Key files:

- `config/signal_engine.yaml` — weights, routes, and registration use the legacy
  group identity
- `src/application/services/signal_engine_config.py` — default group identity
- `src/application/services/engine_bootstrap/signal_alpha_trigger_config_resolver.py`
  — merges arbitrary keys and can otherwise retain both old and new identities
- `src/application/services/signal_alpha_trigger_projection.py` — maps
  `SectorContextEvidence` into the misnamed group
- `src/domain/value_objects/alpha_trigger_score.py` — contribution and promotion
  records persist evidence identity
- `src/application/services/accumulation_observation_signal_fingerprint.py` —
  serializes contribution group names into observation fingerprints
- current Alpha/Trigger output, config, aggregation, promotion, and persistence
  tests using `market_context`
- genuine market-wide context files under domain/application/infrastructure —
  explicitly outside the rename scope

### Exact Rename Contract

#### Canonical live identity

Use `sector_context` everywhere inside the Alpha/Trigger contract when the
producer is `SectorContextEvidence`:

- `AlphaTriggerConfig.group_weights`;
- all horizon `route_fractions`;
- `evidence_registrations` and `EvidenceRegistration.evidence_name`;
- `SignalAlphaTriggerProjection` group input;
- `AlphaTriggerGroupContribution.group`;
- unavailable/reason strings;
- public Alpha/Trigger output;
- current tests and documentation.

Rename `_score_sector_market_context()` to `_score_sector_context()` or an
equally explicit name. Do not change its calculation in this task.

#### Scoped legacy-key rejection

After the default is renamed, the resolver must not merge a supplied legacy
key and silently create both groups. Reject `market_context` specifically under:

```text
signal_engine.alpha_trigger.group_weights
signal_engine.alpha_trigger.route_fractions.<horizon>
signal_engine.alpha_trigger.evidence_registrations
```

Use an actionable error equivalent to:

```text
Alpha/Trigger group 'market_context' was renamed to 'sector_context' because
its producer is SectorContextEvidence
```

Do not reject legitimate market-wide `market_context_engine`, decision-policy,
risk-gate, repository, or CLI configuration.

#### Persisted compatibility

New observations must use a new fingerprint/schema version and persist only
`sector_context` in `alpha_trigger_route_metadata[].group`.

Do not rewrite existing fingerprint JSON in place. Historical analysis may map
`market_context` to the canonical analytical identity `sector_context` only
when the row's old schema version proves it predates this rename. Under the new
schema, `market_context` is invalid rather than a compatibility alias.

If the learning/attribution reader cannot perform version-aware normalization,
quarantine old rows from group-identity aggregation until rebuilt. Never merge
the strings without checking schema version.

#### Promotion identity

Any future sector-context promotion record must use:

```text
evidence_name: sector_context
```

A new promotion record using `market_context` must fail. This rename does not
promote sector context; it remains DIAGNOSTIC until separately validated.

### Desired Outcome

- Machine-readable identity matches the actual sector-context producer.
- New config cannot retain or create the misleading legacy Alpha/Trigger group.
- Historical attribution remains interpretable without mutating raw provenance.
- Genuine market-wide `MarketContext` concepts remain unchanged.
- Numerical Alpha/Trigger output is identical apart from identity strings and
  fingerprint schema version.

### Non-Goals

- No change to actual score values or group weights.
- No new evidence builders.
- No behavioral change to signal output (only naming).
- No global replacement of legitimate `market_context` concepts.
- No change to `MarketContextEngine`, regime policy, decision policy, or risk gates.
- No change to sector regime scoring or presence logic.
- No evidence promotion.

### Do Not Interpret This As

- Do not perform a repository-wide textual replacement of `market_context`.
- Do not rename `MarketContext`, `MarketContextEngine`, their config, persistence,
  CLI commands, risk gates, or regime inputs.
- Do not preserve `market_context` as an accepted new-config alias.
- Do not let resolver merging create both `market_context` and `sector_context`.
- Do not silently relabel historical fingerprint JSON in place.
- Do not normalize legacy identity without verifying the fingerprint schema version.
- Do not alter weights, route fractions, score mapping, presence logic, authority,
  decision policy, or risk behavior.
- Do not combine the adjacent question of whether categorical sector scoring is
  empirically adequate with this identity repair.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: rename Alpha/Trigger contribution/registration identity expectations; no market-wide context changes
- Application: rename defaults, projection, resolver validation, reasons, and schema-aware attribution interpretation
- Infrastructure: persist the new fingerprint schema/version; preserve historical raw JSON
- Adapter: emit `sector_context` in Alpha/Trigger output only; do not rename market-context workflows
- Documentation/Config: rename the scoped Alpha/Trigger keys and document legacy schema interpretation
```

### Acceptance Criteria

- [ ] All live Alpha/Trigger sector evidence uses the canonical `sector_context` identity
- [ ] No Alpha/Trigger default, YAML route, weight, registration, contribution, or reason uses `market_context`
- [ ] Legacy keys are rejected in group weights, every horizon route, and evidence registrations
- [ ] Resolver cannot produce simultaneous old and new group identities
- [ ] Genuine market-wide `MarketContext` code/config/output remains unchanged
- [ ] New fingerprints use a new schema/version and persist only `sector_context`
- [ ] Historical raw fingerprints remain unchanged
- [ ] Old-schema attribution maps the legacy identity explicitly, or old rows are quarantined until rebuilt
- [ ] New-schema fingerprints containing `market_context` fail validation
- [ ] Promotion records using the legacy identity fail; no promotion is added
- [ ] Regression test proves scores, weights, route fractions, effective authority, and decisions are numerically unchanged
- [ ] Negative test proves real market regime inputs are not routed into the renamed sector slot
- [ ] Focused config, resolver, projection, aggregation, persistence, attribution, and output tests pass
- [ ] Full test suite passes
- [ ] `git diff --check` clean

---

## Task MEDIUM-3 — Make Output Ownership Truthful

**State:** Partial — scheduled after MEDIUM-2 in Phase 2.

### Metadata

- **Type:** Output-contract documentation correction
- **Priority:** MEDIUM
- **Risk:** A permanently-null field creates meaningless attribution, while the
  conceptual output guide can make agents duplicate existing volatility and
  authority output or invent an unvalidated liquidity-sizing feature
- **Decision:** Document the current emitted contract and its ownership; mark the
  dead regime-detection-method field as legacy/non-canonical; do not perform a
  fingerprint migration in this task. `ARTIFACT-IDENTITY` defines the new
  canonical schema and DQ-010 owns physical cleanup. Do not add duplicate
  authority output or fold volatility/liquidity sizing into signal decision
  constraints. Implement this option only.

### Problem

The task's original source reference is stale. `docs/signal_refactor.md` is now
a short documentation index; the conceptual guidance lives in
`docs/signal_engine_output_contract.md`, which explicitly says current code,
schemas, config, and tests are authoritative.

The purported missing fields do not form one implementation feature:

1. `regime_detection_method_at_signal` is a dead persisted dimension.
   `MarketContext` has no such producer field, the observation builder always
   writes `None`, and attribution turns it into an `UNKNOWN` bucket. All 5,760
   local `signal_forward_labels` fingerprints contain a null value. This is not
   honest missing evidence; it is a concept that was never produced.
2. Volatility sizing already exists. `build_volatility_context()` deterministically
   computes it, swing JSON emits it under diagnostic volatility context, the
   observation fingerprint persists it, and attribution/tests consume it. It is
   intentionally not part of `DecisionConstraints`, whose current multiplier is
   the regime-policy multiplier.
3. `liquidity_size_multiplier` has no implementation or validated contract.
   Adding it would require a new measurement, freshness, thresholds, missing-data,
   calibration, composition, and ownership design. It is a new sizing feature,
   not output reconciliation.
4. Scoring authority is already exposed per Alpha/Trigger group through
   `group_contributions[].evidence_status`, alongside configured/effective weight,
   presence, routes, and reasons. A separate `evidence_statuses` map would
   duplicate authority and can drift. Producer provenance status is a different
   concept and must not be collapsed into the scoring-authority map.

`DecisionConstraints.effective_size_multiplier` is also easy to over-read: its
implementation currently equals `regime_size_multiplier`. It is not the final
position-size multiplier and does not compose volatility, liquidity, portfolio,
or RiskEngine constraints.

Key files:

- `docs/signal_refactor.md` — documentation index, not the old long-form output section
- `docs/signal_engine_output_contract.md` — conceptual output and persistence guidance
- `src/application/services/accumulation_observation_metadata.py` — always writes
  null regime detection method; already persists volatility context
- `src/domain/value_objects/signal_observation_fingerprint.py` and regime
  serialization helpers — retain the dead method field
- `src/application/use_case/summarize_signal_forward_labels_use_case.py` —
  creates meaningless `UNKNOWN` attribution for the dead field
- `src/application/services/volatility_context.py` — existing single source of
  truth for ATR volatility bucket and sizing hint
- `src/application/services/swing_analysis_serialization.py` — already emits
  diagnostic volatility multiplier
- `src/domain/value_objects/decision_constraints.py` and
  `src/application/services/decision_policy.py` — current regime/setup policy
  constraint output
- `src/domain/value_objects/alpha_trigger_score.py` — canonical per-group
  scoring-authority output

### Exact Contract

#### Current runtime output

Update `docs/signal_engine_output_contract.md` to distinguish explicitly:

- **Current emitted contract:** exact ownership and location of signal assessment,
  decision constraints, Alpha/Trigger authority contributions, volatility
  diagnostics, and observation fingerprints.
- **Conceptual/deferred contract:** ideas that require separate design and are
  not promised runtime fields.

Document these current truths:

- `DecisionConstraints` owns signal regime/setup decision caps and the regime
  size multiplier only.
- volatility multiplier is a separate diagnostic/persisted sizing input;
- liquidity multiplier is not implemented;
- `alpha_trigger_score.group_contributions[].evidence_status` is the canonical
  scoring-authority representation;
- producer-local provenance status, where present, is not scoring authority;
- final position sizing is not owned by the current SignalEngine output.

#### Dead fingerprint disposition

Document `regime_detection_method_at_signal` as a legacy, never-produced field
that is ineligible for canonical attribution. Do not modify persistence,
serialization, or historical JSON in MEDIUM-3.

`ARTIFACT-IDENTITY` must exclude the field from the new canonical fingerprint
schema. DQ-010 owns quarantine/rebuild of old rows and removal of the resulting
legacy `UNKNOWN` attribution. Do not replace the field with a fabricated
constant. If market-context reproducibility needs stronger provenance, create a
separate future contract for explicit `market_context_model_version`, config
fingerprint, enabled factor set, and threshold version.

#### Sizing ownership

Do not add volatility or liquidity fields to `DecisionConstraints` in this task.
A future unified position-sizing task must explicitly define an application-owned
composition equivalent to:

```text
regime multiplier
× volatility multiplier
× liquidity multiplier
× portfolio/RiskEngine constraints
= final position-size multiplier
```

That design must define missing-data behavior, caps/floors, prevention of double
application, point-in-time persistence, and which component has final authority.
It is not authorized by this task.

#### Misleading current name

Document that `DecisionConstraints.effective_size_multiplier` currently means
the effective multiplier within regime policy only. Renaming it to
`regime_size_multiplier` or introducing a true composed multiplier belongs to
the separate sizing contract; do not silently change public output here.

### Desired Outcome

- Current documentation describes what runtime actually emits and where each
  value is owned.
- The dead regime-method field has an explicit non-canonical disposition and
  cannot be mistaken for real evidence while canonical schema work is pending.
- Existing volatility and authority output is reused instead of duplicated.
- Liquidity and final position sizing remain explicitly deferred until their own
  validated contract exists.

### Non-Goals

- No change to scoring formula.
- No new data providers.
- No new market-context classification method or fabricated constant.
- No volatility or liquidity multiplier added to `DecisionConstraints`.
- No duplicate top-level `evidence_statuses` map.
- No change to existing volatility classification thresholds or multiplier values.
- No final position-sizing implementation.
- No historical fingerprint rewrite.

### Do Not Interpret This As

- Do not implement fields merely because an archived/conceptual shape listed them.
- Do not describe a permanently-null producer field as legitimate `UNKNOWN`
  evidence, and do not migrate it inside this documentation task.
- Do not add a constant `regime_detection_method` solely to populate the column.
- Do not remove existing volatility diagnostic or fingerprint output.
- Do not multiply regime and volatility sizing inside SignalEngine as a shortcut.
- Do not invent liquidity thresholds or use liquidity data without a separate
  point-in-time and calibration contract.
- Do not duplicate group authority into a map that can drift from contributions.
- Do not conflate producer provenance status with central scoring authority.
- Do not rename or change `effective_size_multiplier` behavior in this task.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: not touched
- Application: not touched
- Infrastructure: not touched
- Adapter: not touched
- Documentation: make docs/signal_engine_output_contract.md distinguish current runtime output from deferred concepts and record dead-field ownership by ARTIFACT-IDENTITY/DQ-010
```

### Acceptance Criteria

- [ ] The active output guide names exact current locations and owners for decision constraints, volatility, and evidence authority
- [ ] Liquidity and final composed position sizing are explicitly marked unimplemented/deferred
- [ ] The guide marks `regime_detection_method_at_signal` legacy/non-canonical and assigns new-schema exclusion to ARTIFACT-IDENTITY and physical cleanup to DQ-010
- [ ] No fabricated replacement method value is introduced
- [ ] Existing volatility context output, persistence, attribution, thresholds, and values are documented without being changed
- [ ] No volatility/liquidity field is added to `DecisionConstraints`
- [ ] No duplicate `evidence_statuses` map is added
- [ ] Per-group Alpha/Trigger scoring authority remains canonical
- [ ] Producer provenance is not described as scoring authority
- [ ] Current code/config/output pointers in the guide are verified directly
- [ ] `git diff --check` clean

---

## Task HIGH-3 — Remove Flags-Only SignalEngine Assessment Paths

**State:** Partial — waits for ARTIFACT-IDENTITY.

### Metadata

- **Type:** Public application-contract cleanup + fail-closed guardrail
- **Priority:** P1
- **Risk:** A signal-shaped response with zero production evidence can be
  mistaken for a real assessment and passed into TradeSetup composition
- **Decision:** Remove `evaluate()` and `evaluate_request()` as assessment entry
  points; retain `build_context()` for enrichment diagnostics; require the
  canonical assessment path to receive at least one production evidence group;
  represent absence of candidate evidence as unavailable rather than fabricating
  a flags-only assessment. Implement this option only.

### Problem

`SignalEngine.evaluate()` calls enrichment providers, builds `SignalContext`,
and invokes `AssessSignalEvidenceUseCase` without `SetupEvidence` or
`FlowConfirmationEvidence`. It therefore returns an `AssessSignalResponse` with
zero production evidence coverage. The response still has the same type and
shape as a canonical assessment, including score, classification, constraints,
and fields consumed by downstream workflow code.

`evaluate_request()` repeats the same flags-only behavior through a second
public entry point. Neither method name communicates that no scoring evidence
is available.

The risk is live rather than theoretical. `SwingAnalysisDecisionComposer` calls
`evaluate()` when no accumulation candidate exists, then can pass the returned
assessment into later TradeSetup and preview composition. A human-readable
docstring or new warning field does not make that object safe: downstream code
can continue consuming it as a normal assessment.

`evaluate_with_context()` is the canonical staged-evidence path, but its evidence
arguments are optional. Flow-only assessment is intentionally used by the batch
accumulation screener and is valid as incomplete coverage. The unsafe state is
not "both groups are not complete"; it is "no production evidence group was
provided at all."

Enrichment flags remain useful, but they are context diagnostics and score
penalties applied to an evidence-backed signal. They are not a standalone
positive or negative signal source.

Key files:

- `src/application/services/signal_engine.py` — misleading `evaluate()` and
  `evaluate_request()` entry points; canonical `evaluate_with_context()` path
- `src/application/services/swing_analysis_decision_composer.py` — uses
  `evaluate()` as a no-candidate fallback and composes downstream outputs
- `src/application/services/accumulation_candidate_signal_assessor.py` — valid
  flow-only canonical assessment path that must remain supported
- `src/application/dto/assess_signal.py` — response type does not distinguish a
  flags-only pseudo-assessment from an evidence-backed assessment
- `tests/application/services/test_signal_engine.py` — currently characterizes
  and legitimizes zero-evidence `evaluate()` output

### Exact Contract

#### Public SignalEngine API

Remove these public assessment methods:

```text
SignalEngine.evaluate()
SignalEngine.evaluate_request()
```

Do not retain compatibility wrappers, deprecation fallbacks, or aliases that
still return `AssessSignalResponse` without production evidence.

Retain:

```text
SignalEngine.build_context()
```

as the explicit enrichment/flag observability path. It returns `SignalContext`,
not a signal decision.

Keep one canonical assessment path (the current `evaluate_with_context()` may
retain its name in this task). It must fail explicitly before assessment when
both production evidence groups are absent:

```text
setup_evidence is None AND flow_confirmation_evidence is None
    -> NoProductionSignalEvidenceError
```

Use a typed application error or an equally explicit existing error contract.
Do not convert this state into WATCH, AVOID, zero score, or a warning-bearing
success response.

Flow-only and setup-only calls remain allowed. Their incomplete authority
coverage is handled by the canonical coverage/readiness contract from HIGH-2.

#### Workflow behavior

When swing analysis has no candidate/evidence, do not call SignalEngine for an
assessment. Set signal assessment to unavailable and add a machine-readable
workflow status/reason equivalent to:

```text
signal_assessment_status: UNAVAILABLE
signal_assessment_unavailable_reason: no_production_signal_evidence
```

If the existing workflow result has no typed availability contract, add it at
the application DTO boundary. CLI adapters only render that status; they must
not infer it from score, warnings, candidate absence, or exceptions.

The same error from an unexpected canonical caller must be mapped explicitly;
do not swallow it into a generic warning and continue with a stale assessment.

#### Flags and context

Provider-based enrichment and flag inspection must use `build_context()` or a
dedicated audit use case. Preserve deterministic flag construction and existing
provider failure behavior. Do not turn flags into an independent evidence group
or give them standalone entry/avoid authority.

### Desired Outcome

- No public SignalEngine method returns a signal assessment from enrichment
  flags alone.
- Canonical assessment fails closed when neither setup nor flow production
  evidence exists.
- Partial evidence remains valid and truthfully incomplete.
- No-candidate workflows expose typed unavailability and cannot feed a fabricated
  assessment into TradeSetup.
- Context/flag audit capability remains available through a non-assessment API.

### Non-Goals

- No change to scoring formula or output values.
- No change to numerical results for valid setup-only, flow-only, or both-group calls.
- No change to enrichment provider calculations.
- No new evidence group or evidence promotion.
- No requirement to rename `evaluate_with_context()` in this task.

### Do Not Interpret This As

- Do not add only a warning field while preserving flags-only success responses.
- Do not preserve `evaluate()` or `evaluate_request()` as hidden/deprecated aliases.
- Do not synthesize neutral evidence to satisfy the canonical guard.
- Do not treat missing production evidence as AVOID; unavailable is not bearish.
- Do not require both production groups; setup-only and flow-only remain valid.
- Do not give enrichment flags standalone scoring or decision authority.
- Do not let CLI adapters infer or decide assessment availability.
- Do not catch `NoProductionSignalEvidenceError` and continue composing a
  TradeSetup from an absent or stale signal assessment.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: define a typed assessment availability/status value only if the existing workflow DTO requires one; no scoring logic
- Application: remove flags-only entry points, guard canonical assessment, and map no-evidence workflow state explicitly
- Infrastructure: not touched
- Adapter: render typed unavailable status/reason only; no availability policy
- Documentation: update SignalEngine public API and workflow contract
```

### Acceptance Criteria

- [ ] `SignalEngine.evaluate()` and `evaluate_request()` no longer exist
- [ ] No compatibility wrapper returns `AssessSignalResponse` without production evidence
- [ ] Canonical assessment raises an explicit typed error when both production groups are absent
- [ ] Setup-only and flow-only assessment remain supported
- [ ] Both-group assessment remains supported
- [ ] Valid assessment scores, classifications, constraints, and output are numerically unchanged
- [ ] No-candidate swing workflow reports typed UNAVAILABLE/no-production-evidence state
- [ ] No-candidate workflow does not pass a fabricated assessment into TradeSetup or preview composition
- [ ] Unexpected no-evidence canonical calls are not swallowed as generic success/warning behavior
- [ ] `build_context()` remains available for deterministic enrichment and flag audits
- [ ] Negative test proves enrichment flags alone cannot produce any `AssessSignalResponse`
- [ ] Negative test proves missing evidence is not represented as WATCH or AVOID
- [ ] CLI displays application-owned status without inferring policy
- [ ] Focused SignalEngine, swing workflow, TradeSetup composition, DTO, and CLI tests pass
- [ ] Full test suite passes
- [ ] `git diff --check` clean

---

## Task PROMO-INTEGRITY — Evidence-Bound Promotion Artifacts

**State:** Partial — waits for ARTIFACT-IDENTITY and cannot authorize promotion before DQ-BASELINE-GATE.

### Decision and dependency

- **Priority:** P0
- **Depends on:** `DQ-CONTRACT-GATE`, HIGH-1, HIGH-2, and `ARTIFACT-IDENTITY`;
  no artifact may approve promotion until `DQ-BASELINE-GATE` also passes
- **Decision:** YAML may request promotion but may not declare its own proof.
  Promotion must reference an immutable evaluation artifact that the application
  loads and verifies independently. Implement this option only.

### Exact contract

Persist an `EvidenceEvaluationArtifact` with at least:

```text
evaluation_id, artifact_hash, created_at, target, evidence_name, setup_family,
horizon, market_tier, evaluation_period, dataset_snapshot_id,
observation_schema_version, label_schema_version, code_version, config_hash,
IS/OOS metrics, fold metrics, costs, blockers, approval_state
```

For a local-ML evidence producer, the artifact must additionally bind producer
kind, immutable model hash/version, feature-schema identity, training-data
identity, inference-runtime version, calibration/uncertainty results, drift
policy, and rollback target. A full-decision ML/API challenger artifact cannot
satisfy an evidence-promotion request.

The promotion record stores `evaluation_id`, expected hash, requested authority,
approver, and approval timestamp. Bootstrap validation must load the artifact
through an application port, recompute/verify its hash and gates, and prove that
identity/scope matches the registration. Missing, mutable, stale, mismatched, or
failed artifacts reject startup/config resolution. The existing baseline
exemption is handled only by `BASELINE-RECERT`.

### Do Not Interpret This As

- Do not trust metric numbers copied into YAML.
- Do not accept a filesystem path or prose `attribution_ref` as proof.
- Do not let tuning write approval state or evidence authority.
- Do not validate only schema shape; verify stored evidence and identity.

### Close criteria

- [ ] Forged qualifying YAML metrics cannot promote evidence
- [ ] Mutated/missing/hash-mismatched artifacts fail closed
- [ ] Target, evidence, horizon, setup, tier, schema, code, and config identities must match
- [ ] Local-ML evidence promotion additionally matches immutable model, feature, training-data, and inference identities
- [ ] Full-decision ML/API challenger artifacts are rejected as evidence-promotion proof
- [ ] Repository and validator negative tests pass
- [ ] Full suite and `git diff --check` pass

---

## Task AUTH-SCOPE — Setup/Horizon-Scoped Evidence Authority

**State:** Partial — waits for ARTIFACT-IDENTITY and cannot authorize promotion before DQ-BASELINE-GATE.

### Decision and dependency

- **Priority:** P0 before any non-baseline promotion
- **Depends on:** HIGH-2 and `ARTIFACT-IDENTITY`
- **Decision:** Replace global group authority with an explicit scoped key.

### Exact contract

Use a base key equivalent to:

```text
EvidenceAuthorityKey(evidence_name, setup_family, horizon, authority_segment?)
```

The resolved evidence registration also binds the producer kind and immutable
producer version. For local-ML evidence this includes the approved model and
feature-schema identities; a retrained or materially changed model resolves to
DIAGNOSTIC until separately evaluated and approved.

Resolution uses an exact match. Unregistered/unknown combinations resolve to
DIAGNOSTIC; no wildcard or nearest-match inheritance. The base key always uses
evidence, setup family, and horizon. Add a named `authority_segment` such as
`market_tier` only when the evidence contract predeclares that source meaning or
valid authority differs by that segment and the evaluation artifact proves the
segment separately. Do not multiply every evidence registration by market tier
by default. Regime, liquidity, and market tier remain mandatory evaluation
slices even when they are not authority-key dimensions. Persist the resolved
key, optional segment, and registration version in every observation.

### Close criteria

- [ ] Evidence proven for one setup/horizon or declared authority segment has zero authority elsewhere
- [ ] Unknown scope fails closed to DIAGNOSTIC
- [ ] Market tier is not an authority-key dimension unless the evidence contract and evaluation artifact explicitly require it
- [ ] Retrained or feature-incompatible local-ML evidence cannot inherit an older model's authority
- [ ] Promotion artifacts and output expose the exact scope
- [ ] Negative scope-leakage tests, full suite, and `git diff --check` pass

---

## Task BASELINE-RECERT — Legacy Baseline Authority Recertification

**State:** Partial — waits for valid evaluation and promotion-governance gates.

### Decision and dependency

- **Priority:** P0 governance; staged operational migration
- **Depends on:** HIGH-1, HIGH-2, `PROMO-INTEGRITY`, and `AUTH-SCOPE`
- **Decision:** Stop treating `setup_quality` and `institutional_flow` as
  empirically proven merely because they are baseline exemptions.

### Exact contract

Represent authority basis explicitly:

```text
LEGACY_BASELINE_PROVISIONAL | OOS_VALIDATED
```

Provisional baseline authority may remain temporarily to avoid disabling the
application, but cannot expand scope, gain weight, or justify new thresholds.
Give every baseline scope a recertification artifact, review owner, deadline,
and fallback/demotion policy. Remove `_BASELINE_EVIDENCE_AUTHORITY` exemption
only after equivalent evidence-bound registrations exist.

### Close criteria

- [ ] Output and persistence distinguish provisional from validated production
- [ ] Baseline scope cannot expand without an artifact
- [ ] Each live baseline scope is recertified or explicitly demoted
- [ ] No silent permanent grandfathering remains

---

## Task CONTROL-POPULATION — Point-in-Time Universe Controls

**State:** Partial — starts in Phase 3 with DQ-003 after the live contract gate.

### Decision and dependency

- **Priority:** P0 data-science correctness
- **Depends on:** `DQ-CONTRACT-GATE` session/PIT contracts and
  `ARTIFACT-IDENTITY`. Capture implementation and contract verification proceed
  in DQ-003; readiness, empirical claims, tuning, and promotion require
  `DQ-BASELINE-GATE`.
- **Decision:** Persist both selected candidates and the contemporaneous eligible
  universe so learning can measure false negatives and selection bias.

### Exact contract

For each observation session persist one universe snapshot and one row per
eligible ticker, including inclusion/exclusion status, rejection stage/reasons,
pre-filter measurements, missing-data state, and candidate rank. Delisted,
suspended, stale, and unavailable names remain represented truthfully. Candidate
and control rows share source cutoff/config identity but cannot overwrite one
another. Backfill must reconstruct the historical universe or mark it invalid.

Observation creation is owned by a dedicated application capture use case, not
ordinary analysis commands. CLI-003 later exposes that use case through these
reserved command targets:

```text
saham learn signal capture --contract accumulation-discovery --session YYYY-MM-DD
saham learn signal capture --contract swing-setup --setup NAME --session YYYY-MM-DD
```

The use case resolves one completed IDX session, freezes one eligible-universe
snapshot, builds selected and rejected/control observations from the same
cutoff, and persists them idempotently. It reports inserted, already-existing,
unavailable, rejected, and failed counts. Re-running the same semantic capture
must not increase sample size. Capture does not generate forward labels, tune
policy, or promote evidence. Phase 3 verifies this application contract without
requiring the later CLI router or cron migration.

The contracts answer different evaluation questions:

- `accumulation-discovery` captures every contemporaneously eligible ticker's
  selected/rejected state, rejection stage/reasons, rank, pre-filter values, and
  screen evidence. It measures discovery quality and missed opportunities.
- `swing-setup` requires `--setup NAME`, evaluates that named setup across its
  contemporaneously eligible population, and captures READY, INCOMPLETE,
  INELIGIBLE, and UNAVAILABLE states plus required deep setup evidence. It
  measures setup-specific executable edge.

Both consume the shared `CanonicalSignalEvidenceInput`; neither may reuse the
other observation type merely because ticker/session match. A single manually
selected ticker cannot become canonical capture because that reintroduces user
selection bias. If single-ticker reconstruction is needed, expose a separate
read-only diagnostic interface equivalent to:

```text
saham analyze signal inspect TICKER --contract swing-setup --setup NAME --session YYYY-MM-DD
```

Inspection must not write canonical observations or enter readiness, tuning, or
promotion populations.

`screen accum` and `analyze swing` remain read/assessment workflows with respect
to canonical learning persistence. User attention and command frequency must
not select or weight the training population.

### Close criteria

- [ ] Persisted selected/rejected controls contain the identity and outcome-linkage fields required for later precision, recall/opportunity-cost, and missed-winner evaluation; metric calculation belongs after DQ-004 labels
- [ ] Tightening a filter cannot hide rejected outcomes
- [ ] Universe membership is point-in-time and survivorship-safe
- [ ] Candidate-only datasets cannot authorize screening-policy promotion
- [ ] Explicit capture is idempotent for the same semantic observation identity
- [ ] Repeated interactive screen/analyze calls create no canonical samples
- [ ] Capture and later label generation are separate operations
- [ ] The capture application use case is adapter-independent and ready for CLI-003 wiring
- [ ] Discovery and swing-setup observations cannot overwrite or substitute for one another
- [ ] Swing-setup capture requires a named setup and evaluates a population, not a user-picked ticker
- [ ] Single-ticker inspection is read-only and excluded from canonical learning/readiness
- [ ] Holidays or unresolved completed sessions cannot fabricate observations

---

## Task ARTIFACT-IDENTITY — Reproducible Signal Artifact Identity

**State:** Partial — waits for HIGH-2.

### Decision

- **Priority:** P0 enabling contract; prerequisite for rebuilt canonical learning evidence
- **Decision:** Every observation/evaluation binds the semantic environment that
  produced it; names and dates alone are insufficient.

### Exact contract

Define three separate concepts. Do not use one oversized hash for all three:

```text
artifact_id               # uniqueness/idempotency for one captured artifact
semantic_compatibility_id # whether artifacts may be pooled for learning/readiness
provenance                # complete audit trail, not automatically a cohort key
```

`artifact_id` is derived from semantic capture inputs equivalent to:

```text
artifact_type
+ semantic_compatibility_id
+ effective_session
+ ticker
+ universe_snapshot_id
+ source snapshot/cutoff identity
```

`semantic_compatibility_id` contains only dimensions whose change can alter the
meaning or calculation of comparable evidence/outcomes:

```text
observation_contract
+ setup_family when applicable
+ evidence_contract_version
+ observation/label schema versions as applicable
+ semantic engine/scoring contract version
+ resolved material scoring/policy config hash
+ resolved authority registrations hash for the evaluated contract
+ execution/label-policy version when outcomes are compared
```

The new canonical observation/fingerprint schema must omit dead or never-
produced dimensions, including `regime_detection_method_at_signal`. Legacy raw
JSON remains immutable; DQ-010 owns quarantine/rebuild and legacy-attribution
cleanup.

Ticker, effective session, universe snapshot, source cutoff, invocation time,
and full repository commit are not compatibility dimensions. They vary across
otherwise comparable observations and must not fragment readiness cohorts.

`provenance` persists the full application revision, complete config and
authority-registry identities, source identities and cutoffs, universe snapshot,
IDX calendar/session-rule version, capture time, and other audit metadata. A
full git commit is provenance; a separately declared semantic engine/scoring
contract version is the compatibility dimension and must change whenever
material behavior changes. Unused display config or unrelated authority
registrations must not fragment a compatibility cohort.

Hash deterministic canonical serialization, not paths or volatile timestamps.
Readers reject unsupported semantic compatibility combinations and never pool
them silently. CLI command name, user identity, display flags, and invocation
count are excluded from both canonical identities. Identical semantic capture
inputs resolve to one `artifact_id`; changed provenance alone is visible but
does not imply semantic incompatibility.

### Close criteria

- [ ] Semantically different engines cannot share one `semantic_compatibility_id`
- [ ] Exact reruns reproduce `artifact_id`, `semantic_compatibility_id`, and material outputs
- [ ] Readiness groups by `semantic_compatibility_id`, reports provenance diversity separately, and quarantines incompatible mixtures
- [ ] Session, ticker, universe snapshot, source cutoff, and full code revision do not fragment otherwise compatible readiness cohorts
- [ ] Material scoring/policy changes require a new semantic contract version or resolved config identity
- [ ] New canonical fingerprints omit `regime_detection_method_at_signal`; historical raw JSON is not rewritten
- [ ] Invocation time/command cannot create a distinct canonical observation
- [ ] Same semantic capture is a no-op/already-existing result, not a new sample
- [ ] Different observation contracts or setup families cannot share an identity

---

## Task WALKFORWARD-VALIDATION — Purged Walk-Forward Evaluation

**State:** Partial — waits for canonical observations, labels, and the corrected baseline gate.

### Decision

- **Priority:** P1 before production promotion
- **Depends on:** canonical observations/labels and `ARTIFACT-IDENTITY`
- **Decision:** Replace the single chronological 70/30 split as promotion proof
  with repeated purged walk-forward folds and an untouched final holdout.

### Exact contract

Embargo at least the label horizon between training and test; prevent overlapping
outcome windows, ticker/date leakage, and repeated use of the final holdout.
Report every fold, median and worst fold, effective independent samples, ticker
and regime concentration, uncertainty interval, and hypotheses attempted.
Aggregate profit factor alone cannot pass promotion.

### Close criteria

- [ ] Leakage fixtures fail under naive split and pass under purged folds
- [ ] One exceptional fold cannot hide unstable folds
- [ ] Final holdout usage is recorded and cannot be silently reused

---

## Task INCREMENTAL-EDGE — Paired Baseline/Evidence-Challenger Attribution

**State:** Partial — waits for canonical evaluation artifacts and walk-forward validation.

### Decision

- **Priority:** P1
- **Depends on:** `WALKFORWARD-VALIDATION`
- **Decision:** Promotion requires incremental pipeline value, not standalone
  correlation or a favorable subgroup average.

### Exact contract

On identical observations compare the deterministic baseline versus
baseline-plus-evidence. The evidence challenger may be deterministic or an
eligible narrow local-ML evidence producer; it is not a full-decision model/API
challenger. Report
decision/rank deltas, ENTER precision, missed-winner change, coverage loss,
turnover, net return, MAE/MFE, drawdown, and setup/horizon/tier/regime slices.
Require predeclared primary metrics and non-regression gates. Persist both
decisions and the exact ablation definition.

### Close criteria

- [ ] An evidence factor correlated with returns but redundant to baseline fails
- [ ] Promotion artifact includes paired deltas and subgroup regressions
- [ ] No changed observation population between deterministic baseline and evidence challenger
- [ ] Local-ML evidence ablations bind immutable model and feature identities
- [ ] Full-decision ML/API assessments cannot satisfy this evidence-ablation task

---

## Task IDX-EXECUTION-LABELS — Executable Net Outcome Contract

**State:** Partial — starts in Phase 3 with DQ-004 after CONTROL-POPULATION.

### Decision

- **Priority:** P1 before threshold calibration
- **Depends on:** `DQ-CONTRACT-GATE` and point-in-time market data; promotion
  use requires `DQ-BASELINE-GATE`
- **Decision:** Label the declared executable entry/exit policy after realistic
  IDX costs; retain raw market outcomes separately.

### Exact contract

Define entry timestamp/model, fees/taxes, liquidity-tier slippage, price limits,
opening gaps, suspensions, missing sessions, corporate actions, partial/unfilled
states, and target/stop ordering ambiguity. Store gross and net outcomes plus
execution status. Untradeable is not zero return or failure. Each label binds to
the execution-policy version.

Raw market-movement labels may remain available for diagnostics when they are
explicitly typed as non-executable and excluded from tuning/promotion. The
executable model need not invent order-book precision the available data cannot
support: unsupported fill or partial-fill cases resolve to typed `UNAVAILABLE`
or `UNTRADEABLE` outcomes with reasons. Do not fabricate execution certainty.

### Close criteria

- [ ] Labels distinguish market movement from executable strategy result
- [ ] Raw diagnostic labels cannot enter tuning or promotion metrics
- [ ] Suspended/limit/unfilled/corporate-action fixtures are explicit
- [ ] Unsupported execution detail fails to typed unavailable/untradeable rather than using a speculative fill
- [ ] Promotion metrics use net executable outcomes and report unavailable rate

---

## Task SHADOW-PROMOTION — Evidence Challenger, Monitoring, and Rollback

**State:** Partial — waits for validated incremental edge and promotion governance.

### Decision

- **Priority:** P1 after evidence-bound evaluation
- **Depends on:** `PROMO-INTEGRITY`, `AUTH-SCOPE`, and `INCREMENTAL-EDGE`
- **Decision:** Promotion is staged and reversible:

```text
DIAGNOSTIC -> SHADOW_CHALLENGER -> LOW_WEIGHT -> PRODUCTION
                                      |              |
                                      -> SUSPENDED <-
```

Shadow mode persists hypothetical contribution/decision without changing the
canonical decision. Advancement requires a minimum live PIT period and manual
approval. Define monitoring windows and rollback triggers for drawdown, precision,
coverage/missingness, data-semantic drift, and subgroup failure. Preserve the
last approved registration for deterministic rollback.

This lifecycle applies to deterministic evidence, eligible narrow local-ML
evidence, and deterministic policy candidates. For local ML, monitoring also
covers feature drift, calibration drift, model availability, and model/runtime
identity. Full-decision ML/API challengers remain shadow-only and cannot advance
to `LOW_WEIGHT` or `PRODUCTION` through this task.

### Close criteria

- [ ] Shadow evidence cannot alter live score/decision
- [ ] LOW_WEIGHT and PRODUCTION require separate approvals/artifacts
- [ ] Triggered rollback deterministically restores prior authority
- [ ] Tuning cannot advance lifecycle state
- [ ] Retrained or identity-mismatched local models resolve to DIAGNOSTIC
- [ ] Full-decision ML/API challengers cannot enter the evidence-authority lifecycle

---

## Guards: What NOT To Do While These Tasks Are Open

> [!WARNING]
> These restrictions apply until the contract ambiguities above are resolved.

- **Do not** promote `market_context`, `company_quality_context`, domestic bandar evidence, sector context, or event alpha based on implementation completeness alone.
- **Do not** tune RS thresholds until HIGH-1 (5d vs 20d) is settled.
- **Do not** tune `regime_conditioning.*` — code and config correctly mark it legacy diagnostic.
- **Do not** use historical replay labels as production proof if fingerprints were generated before the current PIT enrichment/fingerprint contract.
- **Do not** use `min_coverage` / `min_conviction` in tuning until HIGH-2 names are resolved.
- **Do not** promote from YAML-declared metrics; require `PROMO-INTEGRITY`.
- **Do not** grant global group authority from setup/horizon-specific proof.
- **Do not** call baseline authority OOS-validated until `BASELINE-RECERT` passes.
- **Do not** use candidate-only observations to prove screener recall or filter value.
- **Do not** use the current 70/30 split as production promotion proof.
- **Do not** promote on gross close returns without the executable IDX label contract.

---

## Already Confirmed Aligned (Do Not Re-implement)

The following are working and tested. Do not revisit unless a specific regression surfaces:

- Deterministic-first boundaries: signal/refactor code lives in application/domain, not CLI policy
- Risk remains separate from signal; `DecisionPolicyService` caps signal entry but does not replace `RiskEngine`
- Canonical scoring path is staged evidence via `AssessSignalEvidenceUseCase`
- Missing setup/flow groups lower coverage; not neutral-filled
- BB compression is setup/phase evidence, not flow evidence
- Volume trigger requires dry-up plus expansion, not raw volume spike
- Setup entry authority enforced by `config/swing_setups.yaml` and decision policy
- Forward labels and signal observation fingerprints exist
- Evidence authority caps enforced by `AlphaTriggerAggregator`
- Promotion guardrails exist in config loading and tuning patch validation
