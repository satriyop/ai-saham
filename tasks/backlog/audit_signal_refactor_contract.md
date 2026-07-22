# Detailed Signal Contract Task Specifications

**Source audit:** `tasks/thought/signal_refactor_audit.md` (verified 2026-07-14)

> [!IMPORTANT]
> This is the detailed contract appendix, not the execution entry point.
> Start with [`signal_evidence_program.md`](signal_evidence_program.md), then
> use [`deterministic_signal_engine.md`](deterministic_signal_engine.md) or
> [`evidence_validation_and_promotion.md`](evidence_validation_and_promotion.md)
> to select one task before opening its specification here.

---

Before starting a task, read `AGENT_QUICKSTART.md`, follow the selected lane,
verify the task state against code and tests, and state the layer plan. Do not
promote diagnostic evidence or tune thresholds while relevant contract or data
prerequisites remain unresolved.

---

## How To Use This Appendix

- Task identity is semantic; priority remains separate metadata.
- `Done` records a final verification commit.
- `Active` requires at least one committed task-owned slice.
- `Ready` means prerequisites pass but implementation has not started.
- `Blocked` means an explicit prerequisite remains open.
- `Deferred` means the task is intentionally outside the active lane.
- Dependencies and active ordering live in the lane documents, not here.
- Exact contracts, forbidden interpretations, and close criteria live here.

### Current-Code Audit — refreshed 2026-07-22

- `DQ-BASELINE-GATE` is closed in [`audit_data_quality.md`](audit_data_quality.md)
  §17. Prefer that file + current code/tests over older pessimistic notes.
- Lean identity is integrated on the capture path (`observation_contract` +
  `semantic_compatibility_id`). Full three-part `ARTIFACT-IDENTITY` remains
  Foundation Done / apparatus parked — not “unintegrated lean identity.”
- `CONTROL-POPULATION` for `accumulation-discovery` is **lean-closed with
  stamped limitations** (below). Do not treat unchecked full-control / PIT
  universe criteria as open P0 baseline work.
- Deferred promotion / walk-forward / ML sections remain future specs.
- Unchecked criteria under Deferred or parked scopes describe future task
  completion; incidental adjacent code is not counted as task-owned completion
  unless a lean close note says so.

---

## Task BENCHMARK-EXCESS-RETURN — Repair Benchmark Excess-Return Evidence and Authority

**State:** Done

**Completed:** `5b9f3f0 tasks:update, adr:update`

---

## Task CANONICAL-EVIDENCE-BOUNDARY — Bind Evidence To Provenance And Availability

**State:** Done

**Completed:** `2526608 Fix Finding 6: replace fake screen/swing parity test with real boundary test`

---

## Task AUTHORITY-COVERAGE-READINESS — Fix Coverage/Conviction Gating Source and Naming

**State:** Done

**Completed:** `8c4dee1 Close remaining HIGH-2 Findings and Reconcile Acceptance State`

---

## Task CENTRAL-EVIDENCE-AUTHORITY — Remove Producer-Config Authority From Institutional Accumulation

**State:** Done — `c93363a Remove producer-config authority from
institutional accumulation evidence (CENTRAL-EVIDENCE-AUTHORITY)`.

### Metadata

- **Type:** Authority-boundary bugfix + persisted-provenance guardrail
- **Priority:** P2
- **Proportionality:** Keep. This is a bounded fail-closed config/builder fix;
  it does not require promotion infrastructure.
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
explicitly named central evidence registration. Promotion then requires the
deferred `evidence_validation_and_promotion.md` contract; the current
YAML-declared metric validator is not sufficient proof. Do not reintroduce an
authority field into the producer's calculation YAML.

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

- [x] `InstitutionalAccumulationConfig` has no `evidence_status` field
- [x] `config/institutional_accumulation.yaml` has no authority key
- [x] Wrapped and unwrapped mappings containing `evidence_status` fail with the
      explicit ownership error
- [x] Default and custom calculation configs produce DIAGNOSTIC top-level evidence
- [x] Foreign, domestic, and counterparty nested evidence is always DIAGNOSTIC
- [x] Partial-data and whole-build exception fallbacks are always DIAGNOSTIC
- [x] No producer-local config path can create LOW_WEIGHT or PRODUCTION output
- [x] Persisted institutional-accumulation fingerprints remain DIAGNOSTIC for new observations
- [x] Negative test proves a serialized/fabricated producer status cannot grant Alpha/Trigger scoring authority
- [x] Existing canonical `FlowConfirmationEvidence` and Alpha/Trigger `institutional_flow: PRODUCTION` behavior is unchanged
- [x] Future-promotion documentation points exclusively to the validated central authority registry
- [x] Focused config, builder, nested-output, fingerprint, and authority-boundary tests pass
- [x] Full test suite passes (5486 passed)
- [x] `git diff --check` clean

---

## Task SECTOR-CONTEXT-IDENTITY — Remove Alpha/Trigger `market_context`, adopt `sector_context`

**State:** Done — clean break implemented, reviewed, all criteria met.

### Implementation Note (Clean Break)

At implementation time the active `candidate_observations` and
`signal_forward_labels` tables were empty; all older artifacts had already been
moved to `candidate_observations_quarantine` / `signal_forward_labels_quarantine`.
A **clean break** was therefore selected instead of an active compatibility
mapping:

- `market_context` is **removed** from the Alpha/Trigger evidence namespace; it
  survives only as a rejection tombstone (`REMOVED_MARKET_CONTEXT_EVIDENCE_NAME`)
  used to produce explicit failures.
- There is **no** active compatibility alias, translation, normalization, or
  historical interpretation of `market_context` as a valid evidence identity.
- Quarantine tables are **raw audit storage only** — not executable, canonical,
  attributable, labelable, or promotable — and their JSON is left untouched.
- Current typed config, YAML config, live projection, schema-4 observations
  (build/write/read), label generation, and canonical attribution all **reject**
  `market_context`.
- The genuine market-wide `MarketContext` / `MarketContextEngine` subsystem is
  unchanged.

The historical "5,760 legacy labels" figure below described the pre-quarantine
state and is retained only as background; those rows are now quarantined and out
of the current canonical contract.

### Metadata

- **Type:** Evidence-identity rename + persisted-schema compatibility
- **Priority:** P2
- **Proportionality:** Keep. This is a machine-readable identity correction,
  not a cosmetic rename; it must precede new canonical attribution rows.
- **Risk:** The misleading name can corrupt future tuning/promotion decisions;
  an incomplete rename can split historical attribution or accidentally alter
  the real market-wide `MarketContext` system
- **Decision:** Remove the misleading `market_context` Alpha/Trigger identity;
  the group populated by `SectorContextEvidence` is `sector_context`. Reject the
  removed key in typed and YAML config; bump the persisted observation schema to
  4; reject `market_context` at every current canonical boundary. No active
  compatibility mapping — old rows are quarantined raw audit storage only.
  Implement this option only.

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
Alpha/Trigger group 'market_context' was removed; use 'sector_context' because
its producer is SectorContextEvidence
```

The typed `AlphaTriggerConfig.__post_init__` enforces the same rejection so
direct manual-DI construction cannot bypass the YAML resolver.

Do not reject legitimate market-wide `market_context_engine`, decision-policy,
risk-gate, repository, or CLI configuration.

#### Persisted contract (clean break)

New observations use `CANDIDATE_OBSERVATION_SCHEMA_VERSION = 4` and persist only
`sector_context` in `alpha_trigger_route_metadata[].group`.

There is no active compatibility mapping. `validate_current_alpha_trigger_identity`
only interprets the current schema (4): a schema-4 payload containing
`market_context` fails on build, write, and read. Older schema (1–3) rows are
outside the current canonical contract — they are neither validated nor
reinterpreted, and are never mapped to `sector_context`.

Existing raw JSON is never rewritten. Old artifacts are held in the quarantine
tables as raw audit storage only; they are not executable, canonical,
attributable, labelable, or promotable.

#### Promotion identity

Any future sector-context promotion record must use:

```text
evidence_name: sector_context
```

A new promotion record using `market_context` must fail. This rename does not
promote sector context; it remains DIAGNOSTIC until separately validated.

### Desired Outcome

- Machine-readable identity matches the actual sector-context producer.
- New config cannot retain or create the removed Alpha/Trigger group.
- No active compatibility mapping exists; old rows are quarantined raw audit
  storage only and are never mapped to `sector_context`.
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
- Do not preserve `market_context` as an active alias, and do not map it to
  `sector_context` during parsing, attribution, or readback.
- Do not let resolver merging create both `market_context` and `sector_context`.
- Do not rewrite, migrate, or reinterpret quarantined fingerprint JSON.
- Do not aggregate old and new identities together.
- Do not alter weights, route fractions, score mapping, presence logic, authority,
  decision policy, or risk behavior.
- Do not combine the adjacent question of whether categorical sector scoring is
  empirically adequate with this identity repair.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: remove the market_context Alpha/Trigger identity; guard contribution/registration/promotion, the current-schema route-metadata validator, and current-schema forward-label construction; no market-wide context changes
- Application: adopt sector_context defaults, projection, resolver rejection, reasons; reject the removed identity at the label-generation and attribution boundaries (current artifacts only; no historical interpretation or mapping)
- Infrastructure: bump observation schema to 4; validate observation and current-label write/read; leave quarantined raw JSON untouched
- Adapter: emit `sector_context` in Alpha/Trigger output only; surface the current-contract violation error; do not rename market-context workflows
- Documentation/Config: adopt the scoped Alpha/Trigger keys and document the clean break (current artifacts reject the removed identity; historical artifacts remain quarantine-only)
```

### Acceptance Criteria

- [x] All live Alpha/Trigger sector evidence uses the canonical `sector_context` identity
- [x] No Alpha/Trigger default, YAML route, weight, registration, contribution, or reason uses `market_context`
- [x] Removed keys are rejected in group weights, every horizon route, and evidence registrations (typed config and YAML resolver)
- [x] Resolver cannot produce simultaneous old and new group identities
- [x] Genuine market-wide `MarketContext` code/config/output remains unchanged
- [x] New fingerprints use schema 4 and persist only `sector_context`
- [x] Quarantined raw fingerprints remain unchanged and unmigrated
- [x] No active compatibility mapping exists; old rows are audit-only quarantine
- [x] Schema-4 fingerprints containing `market_context` fail on build, write, and read
- [x] Current forward labels containing `market_context` fail on construction, repository write, and read
- [x] Canonical attribution rejects a current label containing `market_context`
- [x] Promotion records using the removed identity fail; no promotion is added
- [x] Regression test proves scores, weights, route fractions, effective authority, and decisions are numerically unchanged
- [x] Negative test proves real market regime inputs are not routed into the renamed sector slot
- [x] Focused config, resolver, projection, aggregation, persistence, attribution, and output tests pass
- [x] Full test suite passes (5451 passed)
- [x] `git diff --check` clean

---

## Task OUTPUT-CONTRACT-OWNERSHIP — Make Output Ownership Truthful

**State:** Deferred, non-blocking — perform after `SECTOR-CONTEXT-IDENTITY`;
this documentation cleanup does not block `LIVE-CONTRACT-GATE`.

### Metadata

- **Type:** Output-contract documentation correction
- **Priority:** P2
- **Proportionality:** Simplify. Keep only truthful ownership and dead-field
  guidance; do not turn this into a new output or sizing implementation.
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
serialization, or historical JSON in OUTPUT-CONTRACT-OWNERSHIP.

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
- [ ] Liquidity/final sizing remains explicitly unimplemented and no new
      `DecisionConstraints` or duplicate authority fields are introduced
- [ ] `regime_detection_method_at_signal` is documented as legacy/non-canonical;
      new-schema exclusion remains owned by ARTIFACT-IDENTITY and cleanup by DQ-010
- [ ] Existing volatility output and per-group Alpha/Trigger authority remain
      unchanged and producer provenance is not described as scoring authority
- [ ] Current code/config/output pointers are verified directly
- [ ] `git diff --check` clean

---

## Task EVIDENCE-BACKED-ASSESSMENT — Remove Flags-Only SignalEngine Assessment Paths

**State:** Done — `4262ae3 Remove flags-only SignalEngine assessment paths
(EVIDENCE-BACKED-ASSESSMENT)`.

### Metadata

- **Type:** Public application-contract cleanup + fail-closed guardrail
- **Priority:** P1
- **Proportionality:** Keep. This removes a real signal-shaped pseudo-result
  that can be mistaken for canonical evidence-backed assessment.
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
coverage is handled by the canonical coverage/readiness contract from AUTHORITY-COVERAGE-READINESS.

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

- [x] `SignalEngine.evaluate()` and `evaluate_request()` no longer exist
- [x] No compatibility wrapper returns `AssessSignalResponse` without production evidence
- [x] Canonical assessment raises an explicit typed error when both production groups are absent
- [x] Setup-only and flow-only assessment remain supported
- [x] Both-group assessment remains supported
- [x] Valid assessment scores, classifications, constraints, and output are numerically unchanged
- [x] No-candidate swing workflow reports typed UNAVAILABLE/no-production-evidence state
- [x] No-candidate workflow does not pass a fabricated assessment into TradeSetup or preview composition
- [x] Unexpected no-evidence canonical calls are not swallowed as generic success/warning behavior
- [x] `build_context()` remains available for deterministic enrichment and flag audits
- [x] Negative test proves enrichment flags alone cannot produce any `AssessSignalResponse`
- [x] Negative test proves missing evidence is not represented as WATCH or AVOID
- [x] CLI displays application-owned status without inferring policy
- [x] Focused SignalEngine, swing workflow, TradeSetup composition, DTO, and CLI tests pass
- [x] Full test suite passes
- [x] `git diff --check` clean

---

## Task RETIRE-LEGACY-SIX-FACTOR-BASELINE — Remove The Executable Legacy Signal Scorer

### Metadata

- **State:** Done — `59bd03b` (Slice 1: removed the dead legacy-weight
  transport from the canonical `SignalEngine` construction path) and
  `b0e77d9` (Slice 2 + findings fix: deleted the executable
  `AssessSignalUseCase`/`AuditSignalUseCase` path and `saham analyze
  signal-audit`; removed the non-operational
  `signal_engine.scoring.seasonality/analyst/forward_pe` YAML surface;
  repaired the factory fail-closed tests; corrected impossible comments; and
  replaced obsolete `Phase N` labels in `config/signal_engine.yaml` with
  canonical task/contract terminology).
- **Type:** Public application-contract cleanup
- **Priority:** P1; required for `LIVE-CONTRACT-GATE`
- **Required before:** DQ-007 and CLI-002
- **Decision:** Remove the executable six-factor `AssessSignalUseCase` path and
  its public audit command. Preserve shared pure diagnostic scorers, historical
  decoding contracts, legacy stored artifacts, fixtures, and git history.
  Canonical inspection is implemented and verified later by DQ-007. Implement
  this option only.

### Problem

The production `SignalEngine` delegates canonical assessment to
`AssessSignalEvidenceUseCase`, but active source still contains
`AssessSignalUseCase`, a retired flat six-factor scorer. It returns the same
general `AssessSignalResponse` shape and remains reachable through
`AuditSignalUseCase` and `saham analyze signal-audit`. Its `factors.*` weights
and neutral-fill settings remain in `config/signal_engine.yaml`.

The path does not currently control screen, swing, `TradeSetup`, persistence,
tuning, or promotion. The defect is authority ambiguity: a public executable
use case can produce a score, classification, and entry quality without the
canonical evidence, provenance, availability, authority-coverage, and readiness
contract. CLI-002 would otherwise rename this legacy audit to `signal inspect`,
making the obsolete calculation look like the explanation of current behavior.

Running the old formula against current data/config is also not reliable
historical reproduction. True reproduction requires the original code/config,
source cutoff, and artifact schema identity. Current git history and immutable
legacy artifacts are more truthful than an active compatibility scorer.

### Exact Contract

#### Remove the executable legacy assessment path

Remove from executable/public application paths:

- `src/application/use_case/assess_signal_use_case.py`;
- `AssessSignalRequest` and any request/response aliases used only by that path;
- `src/application/use_case/audit_signal_use_case.py`;
- legacy six-factor weight resolution used only by that audit;
- `signal_engine.factors.*` and archived neutral-fill config after proving no
  canonical or retained diagnostic consumer reads them;
- tests and comments that execute or describe the retired scorer as production.

No compatibility wrapper, deprecated alias, factory, test helper, or CLI path
may return `AssessSignalResponse` from the retired formula.

#### Preserve genuinely shared current components

Do not delete or duplicate:

- `SignalContext` fields still consumed by canonical enrichment/flag policy;
- pure company-quality scoring helpers used by current diagnostic evidence;
- their required typed config, relocated to an accurately named diagnostic
  boundary if it currently lives under legacy factor config;
- canonical `SignalEngine`, `AssessSignalEvidenceUseCase`, evidence DTOs,
  authority coverage, readiness, constraints, and response serialization;
- historical persisted rows and their schema/code/config identities;
- `SignalEvidence`, `FactorEvidence`, and any reader required to decode or
  identify historical payloads; their later removal is a separate non-blocking
  cleanup requiring proof that no persisted artifact depends on them;
- minimal golden legacy fixtures or archived documentation needed to identify
  old artifacts.

Do not rewrite historical artifacts or recalculate them with the current engine.

#### Leave canonical inspection to DQ-007

This task removes the misleading executable score; it does not build its
replacement. DQ-007 owns the read-only canonical inspection use case, its
point-in-time verification, and its output contract. CLI-002 later exposes that
verified use case as `saham analyze signal inspect`.

It is acceptable for `saham analyze signal-audit` to be absent between this
task and CLI-002. Do not keep the legacy command alive as a compatibility bridge.

### Do Not Interpret This As

- Do not delete `SignalContext` merely because its old six-factor interpretation
  is retired.
- Do not delete shared company-quality math/config still used by current
  diagnostic evidence.
- Do not retain the old scorer under a `legacy`, `compatibility`, `audit`, or
  hidden name.
- Do not preserve a legacy score in canonical inspection for comparison.
- Do not delete historical decoders merely to remove the executable scorer;
  retain schema/version documentation, golden fixtures where needed, and git
  history.
- Do not change canonical scores, weights, thresholds, classifications,
  authority coverage, readiness, or `TradeSetup` behavior.
- Do not build canonical inspection or implement CLI hierarchy restructuring
  here; those are owned by DQ-007 and CLI-002 respectively.

### Negative Tests

- No importable public application path can instantiate or call
  `AssessSignalUseCase` or produce its six-factor score.
- Changing or supplying removed `factors.*` configuration fails clearly rather
  than silently tuning canonical production or a hidden compatibility scorer.
- Diagnostic company-quality evidence remains numerically unchanged where its
  shared scorers/config are intentionally retained.
- Historical legacy payloads remain readable/classifiable without executing the
  retired scorer or rewriting stored JSON.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: preserve canonical and historical decoding contracts; remove only request/response types proven exclusive to the retired executable path
- Application: delete the retired scorer/audit path; do not build a replacement inspector
- Infrastructure: remove legacy factor-weight loading used only by the retired audit; preserve historical readers
- Adapter: unregister and remove the old signal-audit calculation/handler; CLI hierarchy routing remains owned by CLI-002
- Documentation/config: remove active six-factor tuning surfaces and describe legacy artifacts by version/history
```

### Acceptance Criteria

- [x] `AssessSignalUseCase`, `AssessSignalRequest`, and the executable six-factor audit path no longer exist
- [x] No compatibility/deprecated/hidden path can return a legacy signal-shaped assessment
- [x] `signal_engine.factors.*` and legacy-only neutral-fill/weight resolution are removed or fail explicitly
- [x] Shared diagnostic scorers/config are retained under truthful ownership with unchanged intended values
- [x] Current screen, swing, canonical observation inputs, scores, decisions, and `TradeSetup` outputs are unchanged
- [x] Historical persisted artifacts remain unchanged and identifiable by their original semantic/schema provenance
- [x] Historical payload decoders remain available unless a separate dependency audit proves they are unused
- [x] DQ-007 owns construction and verification of canonical inspection
- [x] CLI-002 no longer instructs agents to rename/reuse the legacy audit handler
- [x] Focused canonical signal, diagnostic company-quality, historical decoding, and negative tests pass
- [x] Architecture tests and full suite pass (5407 passed)
- [x] `git diff --check` clean

---

## Task PROMOTION-ARTIFACT-INTEGRITY — Evidence-Bound Promotion Artifacts

**State:** Deferred — activation requires `ARTIFACT-IDENTITY`, canonical
evaluation data, and `DQ-BASELINE-GATE`.

### Decision and dependency

- **Priority:** P0
- **Depends on:** `DQ-CONTRACT-GATE`, BENCHMARK-EXCESS-RETURN, AUTHORITY-COVERAGE-READINESS, and `ARTIFACT-IDENTITY`;
  no artifact may approve promotion until `DQ-BASELINE-GATE` also passes
- **Decision:** YAML may request promotion but may not declare its own proof.
  Promotion must reference an immutable evaluation artifact that the application
  loads and verifies independently. Implement this option only.

### Exact contract

Persist an `EvidenceEvaluationArtifact` with at least:

```text
evaluation_id, artifact_hash, created_at, target, evidence_name, setup_family,
horizon, authority_segment when declared, evaluation_period, dataset_snapshot_id,
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
exemption is handled only by `BASELINE-AUTHORITY-RECERTIFICATION`.

### Do Not Interpret This As

- Do not trust metric numbers copied into YAML.
- Do not accept a filesystem path or prose `attribution_ref` as proof.
- Do not let tuning write approval state or evidence authority.
- Do not validate only schema shape; verify stored evidence and identity.

### Close criteria

- [ ] Forged qualifying YAML metrics cannot promote evidence
- [ ] Mutated/missing/hash-mismatched artifacts fail closed
- [ ] Target, evidence, horizon, setup, schema, code, config, and any declared
      authority-segment identities must match
- [ ] Local-ML evidence promotion additionally matches immutable model, feature, training-data, and inference identities
- [ ] Full-decision ML/API challenger artifacts are rejected as evidence-promotion proof
- [ ] Repository and validator negative tests pass
- [ ] Full suite and `git diff --check` pass

---

## Task EVIDENCE-AUTHORITY-SCOPE — Setup/Horizon-Scoped Evidence Authority

**State:** Deferred — activation requires `ARTIFACT-IDENTITY`, canonical
evaluation data, and `DQ-BASELINE-GATE`.

### Decision and dependency

- **Priority:** P0 before any non-baseline promotion
- **Depends on:** AUTHORITY-COVERAGE-READINESS and `ARTIFACT-IDENTITY`
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

## Task BASELINE-AUTHORITY-RECERTIFICATION — Legacy Baseline Authority Recertification

**State:** Deferred — activation requires valid evaluation and promotion
governance.

### Decision and dependency

- **Priority:** P0 governance; staged operational migration
- **Depends on:** BENCHMARK-EXCESS-RETURN, AUTHORITY-COVERAGE-READINESS, `PROMOTION-ARTIFACT-INTEGRITY`, and `EVIDENCE-AUTHORITY-SCOPE`
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

**State:** Lean-closed for `accumulation-discovery` (2026-07-22) — delivered via
DQ-003 lean slices with stamped limitations. Full screen-rejected controls,
PIT historical universe membership, and `swing-setup` population capture remain
**parked** behind named triggers (not open baseline P0).

### Decision and dependency

- **Priority:** P0 data-science correctness (lean slice closed; remainder parked)
- **Depends on:** `DQ-CONTRACT-GATE` session/PIT contracts and lean
  `ARTIFACT-IDENTITY` subset used by DQ-003. Full apparatus stays parked.
- **Delivered (lean):** dedicated capture/backfill use cases; idempotent
  `accumulation-discovery` observations with lean identity; ordinary
  `screen`/`analyze` remain non-writers; candidate-only datasets cannot claim
  recall/filter-value authority (`contains_control_population=false` stamped).
- **Parked (not bugs to reopen under DQ):** genuine screen-rejected control rows
  (production reject gates disabled on capture path), PIT index membership
  reconstruction (current-universe / survivorship disclosure instead),
  `NAMED-SWING-SETUP-CAPTURE`, CLI-003 `learn signal capture` router.
- **Decision (original full scope, still valid when triggered):** Persist both
  selected candidates and the contemporaneous eligible universe so learning can
  measure false negatives and selection bias.

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
policy, or promote evidence. DQ-003 verifies this application contract without
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

For proportional delivery, implement and validate one named observation
contract at a time. The first contract does not need to wait for the second,
but it cannot answer the other contract's evaluation question or reuse its
population.

### Close criteria

- [ ] Persisted selected/rejected controls contain the identity and outcome-linkage fields required for later precision, recall/opportunity-cost, and missed-winner evaluation; metric calculation belongs after DQ-004 labels
      *Lean (2026-07-22):* selected `accumulation-discovery` rows + lean identity Done via DQ-003. Genuine screen-rejected control rows **parked** (reject gates disabled on capture path; stamped limitation).
- [ ] Tightening a filter cannot hide rejected outcomes
      *Parked* with genuine rejected-control capture.
- [ ] Universe membership is point-in-time and survivorship-safe
      *Lean:* current-universe membership + survivorship disclosure stamped; full PIT reconstruction parked.
- [x] Candidate-only datasets cannot authorize screening-policy promotion
      *Lean:* `contains_control_population=false` / recall ineligible stamped on backfill response and readiness consumers.
- [x] Explicit capture is idempotent for the same semantic observation identity
- [x] Repeated interactive screen/analyze calls create no canonical samples
- [x] Capture and later label generation are separate operations
- [x] The capture application use case is adapter-independent and ready for CLI-003 wiring
      *Lean:* `RecordAccumulationObservationsUseCase` + backfill path exist; Typer `learn signal capture` router remains CLI-003.
- [x] Discovery and swing-setup observations cannot overwrite or substitute for one another
      *Lean:* non-`accumulation-discovery` contract rejected at write; swing producer parked.
- [ ] Swing-setup capture requires a named setup and evaluates a population, not a user-picked ticker
      *Parked:* `NAMED-SWING-SETUP-CAPTURE`.
- [x] Single-ticker inspection is read-only and excluded from canonical learning/readiness
- [x] Holidays or unresolved completed sessions cannot fabricate observations

---

## Task ARTIFACT-IDENTITY — Reproducible Signal Artifact Identity

**State:** Foundation Done — identity value objects, resolution, persistence
support, and the typed semantic-contract registry are committed. **Lean capture
integration is Done via DQ-003** (`observation_contract` +
`semantic_compatibility_id` on `accumulation-discovery` writes). Full
three-part apparatus (`artifact_id`, material-config registry, complete
provenance, universe warehouse) remains **parked** until a named trigger.
Readiness cohort isolation is Done via DQ-006. Those parked scopes do not
block CLI restructure after `DQ-BASELINE-GATE`.

**Committed progress:**

| Slice | Commit |
|---|---|
| Domain identity and canonical serialization | `c8a04cd ARTIFACT-IDENTITY Slice 1 — domain contracts + canonical serialization` |
| Pure identity resolver | `5c367a3 Add pure signal artifact identity resolver` |
| Candidate-observation persistence support | `68b2004 Persist optional signal artifact identity on observations` |
| Forward-label persistence and strict identity audit | `2c828c7 Slice 4: forward-label identity persistence + codec-triplet audit` |
| Typed semantic-contract registry | `2b0bff1 Fix Slice 5 Identity Collision: Preserve institutional window duplicate multiplicity and normalize commodity weights to float` |

Component persistence does not satisfy an end-to-end close criterion by itself.

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

### Semantic-change guardrail

Every change to signal, setup, regime, risk, execution, evidence, observation,
or label behavior must be classified before implementation as one or more of:
`CONFIG_MATERIAL`, `SEMANTIC_ENGINE`, `EVIDENCE_CONTRACT`,
`OBSERVATION_SCHEMA`, `LABEL_POLICY`, `LABEL_SCHEMA`, or `NON_SEMANTIC`.
`NON_SEMANTIC` requires an explicit explanation that deterministic behavior and
canonical outputs are unchanged.

Production integration must use one typed semantic-contract registry as the
source of evidence-contract, semantic-engine, execution/label-policy, material
config-path, and authority-registration identities. Canonical artifact creation
must fail closed when a required version, material config value, authority
registration, universe identity, or source identity cannot be resolved.

Executable contract tests must prove that every declared material config path
changes compatibility identity, display-only config does not, semantic and
label-policy versions affect the correct identities, identity-free artifacts do
not enter canonical readiness, and mixed compatibility identities are never
pooled. Full repository revision remains provenance only; automatically hashing
all source files into compatibility identity is forbidden because non-semantic
refactors must not fragment cohorts.

### Close criteria

These were originally end-to-end program criteria for the **full** three-part
apparatus. After DQ-003 / DQ-006 lean delivery, read each line as:

- **Lean satisfied** → checked below (current code)
- **Full apparatus still parked** → remains unchecked with a note

Foundation slices still supply the typed contracts; lean capture uses
`observation_contract` + config-content-hash `semantic_compatibility_id`
without wiring full `artifact_id` / material-config registry / universe warehouse.

- [x] Semantically different engines cannot share one `semantic_compatibility_id`
      *Lean:* whole-config-content hash + schema/engine/evidence versions forks
      the id (DQ-003). Full per-path material-config registry remains parked.
- [ ] Exact reruns reproduce `artifact_id`, `semantic_compatibility_id`, and material outputs
      *Lean partial:* same config → same `semantic_compatibility_id` + idempotent
      observation upsert (DQ-003). Full `artifact_id` reproduction parked.
- [x] Readiness groups by `semantic_compatibility_id`, reports provenance diversity separately, and quarantines incompatible mixtures
      *Lean:* DQ-006 cohort isolation + exclusion ledger; mixed cohorts fail closed
      / require `--cohort`. Full provenance-diversity product reporting may still grow.
- [x] Session, ticker, universe snapshot, source cutoff, and full code revision do not fragment otherwise compatible readiness cohorts
      *Lean:* readiness keys on lean `semantic_compatibility_id`; universe is out of
      the lean compatibility key by design (DQ-003 amendment). Full
      `universe_snapshot_id` warehouse remains parked.
- [x] Material scoring/policy changes require a new semantic contract version or resolved config identity
      *Lean:* any change to resolved scoring config content forks
      `semantic_compatibility_id`. Explicit semantic-engine version bumps remain
      the contract for engine-code changes (classify before editing).
- [x] New canonical fingerprints omit `regime_detection_method_at_signal`; historical raw JSON is not rewritten
      *Lean:* schema-4 / current fingerprint path + DQ-010 quarantine (no rewrite).
- [x] Invocation time/command cannot create a distinct canonical observation
      *Lean:* ordinary screen/analyze do not write; capture identity excludes
      invocation/command frequency (DQ-003).
- [x] Same semantic capture is a no-op/already-existing result, not a new sample
      *Lean:* idempotent upsert on canonical observation identity (DQ-003).
- [x] Different observation contracts or setup families cannot share an identity
      *Lean:* writer rejects non-`accumulation-discovery`; named-setup contract
      reserved / parked (`NAMED-SWING-SETUP-CAPTURE`).

### Foundation Checkpoint (Slice 1, as shipped)

- After Slice 1, no IDs were computed yet — `ArtifactId`,
  `SemanticCompatibilityId`, and `SignalArtifactIdentity` existed as immutable
  wrappers but no hashing or identity resolution was implemented.
- No schema or persistence changed — `CandidateObservation`,
  `CandidateObservationsRepository`, `SignalForwardLabel`, and all SQLite
  tables/indexes remain untouched.
- No readiness cohort behavior changed — grouping by
  `semantic_compatibility_id` is not wired anywhere.
- Slice 2 was designated to implement the pure application identity resolver: hash
  `SemanticCompatibilityDimensions` → `SemanticCompatibilityId`, hash
  `ArtifactIdentityDimensions` + `SemanticCompatibilityId` →
  `ArtifactId`, and produce a complete `SignalArtifactIdentity`.

### Slice 2 Checkpoint — Pure Identity Resolver

- `SignalArtifactIdentityResolver` implements canonical semantic and artifact
  SHA-256 hashing from `SemanticCompatibilityDimensions.to_canonical_json()` and
  `ArtifactIdentityDimensions.to_canonical_json()` respectively.
- Provenance is excluded from both hashes.
- Semantic-ID binding is validated: `artifact_dimensions.semantic_compatibility_id`
  must match the resolved semantic ID or `ValueError` is raised.
- Universe-snapshot binding is validated: artifact and provenance
  `universe_snapshot_id` must match or `ValueError` is raised.
- Wrong argument types raise `TypeError` with explicit messages.
- Known SHA-256 vectors are verified: semantic ID
  `sha256:38fa9b[…]`, artifact ID `sha256:96ea7e[…]`.
- The resolver imports only `hashlib` and domain identity types; no
  persistence, schema, CLI, readiness, producer, or migration integration
  exists yet.
- No close criterion for the overall ARTIFACT-IDENTITY task is checked.

### Slice 3 Checkpoint — Candidate Observation Persistence Support

- `CandidateObservation` gains an optional `artifact_identity:
  SignalArtifactIdentity | None` field after existing optional provenance
  fields. Existing constructors without the keyword default to `None`.
- A strict SQLite codec (`sqlite_signal_artifact_identity_codec.py`)
  round-trips `SignalArtifactIdentity | None` to/from three `TEXT NOT NULL
  DEFAULT ''` columns (`artifact_id`, `semantic_compatibility_id`,
  `artifact_provenance_json`). Encoding is delegated to
  `ArtifactProvenance.to_canonical_json()`; the codec never re-serializes or
  re-hashes.
- Three new migrations (versions 14, 15, 16) add the columns to the existing
  `candidate_observations` table. No unique index on `artifact_id` is created.
- `save_many()` calls the codec for each observation and persists the three
  values. It does not invoke `SignalArtifactIdentityResolver` or hash anything.
- `_row_to_observation()` calls the codec on every read. Malformed identity
  data raises `ValueError` — never silently coerced to `None`.
- Empty/legacy identity columns decode to `None`. Partial non-empty columns
  raise `ValueError` (fail-closed on corruption).
- Config-hash canonical identity, UPSERT conflict target, and
  schema-version validation are unchanged.
- Quarantine schema (`candidate_observations_quarantine`) preserves all three
  identity columns. `ensure_quarantine_table()` upgrades existing quarantine
  tables that lack them using bounded `ALTER TABLE` statements.
- `SOURCE_COLUMNS` in the repairer includes the three columns.
- Source-field contract catalog adds three entries: `artifact_id` and
  `semantic_compatibility_id` (identity text), `artifact_provenance_json`
  (non-scalar JSON), all with:
  - `null_policy="fail"` — actual NULL is corruption and must fail.
  - `invalid_values=frozenset({""})` — transitional empty string produces
    `INVALID_FIELD_VALUE` at WARN severity (via `invalid_value_policy="warn"`),
    so empty identity is visible in the audit without blocking.
- Producers, labels, readiness, and artifact-ID uniqueness are still not
  integrated. No close criterion for the overall ARTIFACT-IDENTITY task is
  checked.

### Slice 4 Checkpoint — Forward Label Persistence Support

- `SignalForwardLabel` gains an optional `artifact_identity:
  SignalArtifactIdentity | None` field after `schema_version`. Existing
  constructors without the keyword default to `None`.
- The existing strict SQLite codec (`sqlite_signal_artifact_identity_codec.py`)
  is reused — `encode_signal_artifact_identity()` and
  `decode_signal_artifact_identity()` — without duplication of parsing,
  canonicalization, hashing, or validation.
- Three new migrations (versions 9, 10, 11) add the columns to the existing
  `signal_forward_labels` table (`artifact_id TEXT NOT NULL DEFAULT ''`,
  `semantic_compatibility_id TEXT NOT NULL DEFAULT ''`,
  `artifact_provenance_json TEXT NOT NULL DEFAULT ''`). No unique index on
  `artifact_id`.
- `save_many()` calls `encode_signal_artifact_identity()` for each label and
  persists all three values. The UPSERT conflict target
  `(ticker, signal_date, horizon, observation_captured_at)` and ON CONFLICT
  DO UPDATE SET include all three identity columns.
- `_row_to_label()` calls `decode_signal_artifact_identity()` on every read.
  Empty all-three decode as `None`; partial non-empty columns raise
  `ValueError` (fail-closed on corruption). NULL values raise `ValueError`
  (the codec requires strings, matching the NOT NULL column contract).
- Quarantine schema (`signal_forward_labels_quarantine`) preserves all three
  identity columns. `ensure_quarantine_table()` upgrades existing quarantine
  tables that lack them using bounded `ALTER TABLE` statements.
- `SOURCE_COLUMNS` in the repairer includes the three columns.
- Source-field contract catalog adds three entries matching the
  candidate-observation pattern: `artifact_id` and `semantic_compatibility_id`
  (identity text), `artifact_provenance_json` (non-scalar JSON), all with
  `null_policy="fail"` and `invalid_values=frozenset({""})` /
  `invalid_value_policy="warn"`.
- The source-contract audit validates complete observation and label identity
  triplets through the strict codec. Partial or malformed triplets produce the
  blocking `INVALID_ARTIFACT_IDENTITY` finding; all-empty transitional triplets
  remain visible as field-level warnings.
- `SignalForwardLabel.to_dict()` and `from_dict()` are unchanged — identity is
  repository metadata, matching the candidate-observation persistence pattern.
- Producers, readiness, and artifact-ID uniqueness are still not integrated.
  No close criterion for the overall ARTIFACT-IDENTITY task is checked.

### Slice 5 Checkpoint — Typed Semantic Contract Registry

- One typed application registry now resolves observation and label semantic-
  compatibility dimensions from the declared contract, material runtime config,
  and authority registrations.
- Material config identity is setup-family and horizon aware. Runtime-equivalent
  unordered inputs are normalized without erasing meaningful multiplicity.
- Resolution fails closed for missing or invalid material inputs, authority-
  registration mismatches, and unsupported strategy-enabled artifacts.
- This slice does not write artifacts or change scoring, persistence, readiness,
  or capture behavior.
- Producer, readiness-cohort, and canonical-capture integration remain absent;
  no overall close criterion is checked by this slice alone.

### Integration Ownership

- `CONTROL-POPULATION`/DQ-003 must use this identity foundation when it creates
  the universe-driven canonical observation producer.
- DQ-004 must preserve compatible observation identity when producing labels.
- DQ-006 must group readiness by semantic compatibility and reject incompatible
  mixtures.
- The legacy accumulation recorder is not the canonical capture boundary and
  must not be upgraded into one as part of this task.

---

## Task PURGED-WALKFORWARD-VALIDATION — Purged Walk-Forward Evaluation

**State:** Deferred — activation requires canonical observations, executable
labels, and `DQ-BASELINE-GATE`.

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

## Task INCREMENTAL-EVIDENCE-EDGE — Paired Baseline/Evidence-Challenger Attribution

**State:** Deferred — activation requires canonical evaluation artifacts and
`PURGED-WALKFORWARD-VALIDATION`.

### Decision

- **Priority:** P1
- **Depends on:** `PURGED-WALKFORWARD-VALIDATION`
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

**State:** Parked — DQ-004 raw_market lane is Done and sufficient for
`DQ-BASELINE-GATE`. Net-executable labeling is a named product trigger, not an
open baseline P0. Do not start from “Blocked after CONTROL-POPULATION.”

### Decision

- **Priority:** P1 before threshold calibration / promotion that needs net returns
- **Depends on:** `DQ-CONTRACT-GATE` and point-in-time market data; promotion
  use requires `DQ-BASELINE-GATE` (already closed for the raw lane)
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

## Task STAGED-EVIDENCE-PROMOTION — Evidence Challenger, Monitoring, and Rollback

**State:** Deferred — activation requires validated incremental edge and
promotion governance.

### Decision

- **Priority:** P1 after evidence-bound evaluation
- **Depends on:** `PROMOTION-ARTIFACT-INTEGRITY`, `EVIDENCE-AUTHORITY-SCOPE`, and `INCREMENTAL-EVIDENCE-EDGE`
- **Decision:** Promotion is staged and reversible:

```text
DIAGNOSTIC -> SHADOW_CHALLENGER -> LOW_WEIGHT -> PRODUCTION
                                      |              |
                                      -> SUSPENDED <-
```

Shadow mode persists hypothetical contribution/decision without changing the
canonical decision. Every authority-increasing transition requires a minimum
live PIT period, explicit human action, and an immutable transition record.
Advancement from `LOW_WEIGHT` to `PRODUCTION` requires evidence gathered after
low-weight deployment. Define monitoring windows and rollback triggers for drawdown, precision,
coverage/missingness, data-semantic drift, and subgroup failure. Preserve the
last approved registration for deterministic rollback.

This lifecycle applies to deterministic evidence, eligible narrow local-ML
evidence, and deterministic policy candidates. For local ML, monitoring also
covers feature drift, calibration drift, model availability, and model/runtime
identity. Full-decision ML/API challengers remain shadow-only and cannot advance
to `LOW_WEIGHT` or `PRODUCTION` through this task.

### Close criteria

- [ ] Shadow evidence cannot alter live score/decision
- [ ] Every authority-increasing transition uses the same validated transition
  mechanism and an explicit human-approved record
- [ ] PRODUCTION approval uses evidence gathered after LOW_WEIGHT deployment
- [ ] Triggered rollback deterministically restores prior authority
- [ ] Tuning cannot advance lifecycle state
- [ ] Retrained or identity-mismatched local models resolve to DIAGNOSTIC
- [ ] Full-decision ML/API challengers cannot enter the evidence-authority lifecycle

---

## Guards: What NOT To Do While These Tasks Are Open

> [!WARNING]
> These restrictions apply until the contract ambiguities above are resolved.

- **Do not** promote `market_context`, `company_quality_context`, domestic bandar evidence, sector context, or event alpha based on implementation completeness alone.
- **Do not** tune RS thresholds until BENCHMARK-EXCESS-RETURN (5d vs 20d) is settled.
- **Do not** tune `regime_conditioning.*` — code and config correctly mark it legacy diagnostic.
- **Do not** use historical replay labels as production proof if fingerprints were generated before the current PIT enrichment/fingerprint contract.
- **Do not** use `min_coverage` / `min_conviction` in tuning until AUTHORITY-COVERAGE-READINESS names are resolved.
- **Do not** promote from YAML-declared metrics; require `PROMOTION-ARTIFACT-INTEGRITY`.
- **Do not** grant global group authority from setup/horizon-specific proof.
- **Do not** call baseline authority OOS-validated until `BASELINE-AUTHORITY-RECERTIFICATION` passes.
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
