# Design Purpose-Specific Diagnostic Producer Identity

Status: `VETTED / READY_FOR_IMPLEMENTATION` — the design contract is complete;
runtime implementation still requires separate user approval and re-vetting of
the resulting code.

Source finding: RC-01B in
`tasks/backlog/review_code_2026-08-07.md` (`VETTED` 2026-08-07).

## 1. Task Metadata

**Task Title**
Define how ml-saham proves coherent producer semantics for each diagnostic
feature family without expanding ai-saham's canonical Action cohort identity.

**Task Type**
Spike / Research (cross-repository data and panel contract design).

**Priority**
High before accumulating or challenging new diagnostic-feature rows; independent
of live Action correctness.

## 2. Problem Statement

ADR-068 correctly excludes diagnostic-only enrichment from the canonical
behavioral projection: diagnostic changes must not fragment Action cohorts.
However, ai-saham persists diagnostic feature bags without a separate semantic
producer identity, while ml-saham selects and pools observations using only the
Action `compatibility_id`.

Confirmed counterexample on HEAD `619b6a4c`:

```text
Alpha/Trigger enabled -> disabled
persisted diagnostic output: present -> absent
behavioral probe digest: unchanged
snapshot payload digest: unchanged
compatibility_id: unchanged
```

Current persisted diagnostic families include Alpha/Trigger route metadata,
sector context, sector-macro context, company quality, ticker profile,
institutional accumulation, volatility, setup diagnostics, and frozen market
context. ml-saham production-facing diagnostic panels consume subsets of these
fields but carry no purpose-specific producer contract/digest.

## 3. Desired Outcome

Produce a reviewed, implementation-ready successor task that answers exactly:

1. Which persisted fields does each production-facing ml-saham diagnostic
   panel consume?
2. Which exact ai-saham producer, typed inputs/configuration, formula, source
   authority, and missing-state semantics define each field?
3. Which fields must share one producer identity, and which need independent
   purpose-specific identities?
4. Where is the one authoritative typed binding created, transported, stored,
   integrity-checked, and consumed?
5. How does ml-saham select one Action cohort plus one relevant diagnostic
   producer identity and fail closed on mixed/absent/invalid bindings?
6. What observation/panel/artifact versions and clean-break handling are
   required?

The deliverable must choose one exact schema and rollout. It must not leave the
implementation agent to choose between a root binding, per-window binding,
side table, reconstructed digest, or consumer inference.

## 4. Current Producer-To-Consumer Inventory To Reconcile

The vet must trace at least these shipped paths and add every omitted current
consumer it discovers:

| Diagnostic family | ai-saham producer/persistence starting points | ml-saham consumer starting points |
|---|---|---|
| Alpha/Trigger projection | `SignalAlphaTriggerProjection`, `AlphaTriggerAggregator`, `_alpha_trigger_fingerprint`, window `signal.alpha_trigger_score` and `sub_signal_fingerprint` | `panel_diagnostic._group_score_from_signal`, sector/company/institutional diagnostic specs |
| Sector peer context | `SectorContextEvidenceBuilder`, `_sc_fingerprint`, Alpha/Trigger `sector_context` contribution | `sector.peer_context`: `sector_context_score`, `peer_breadth` |
| Sector macro context | `SectorMacroContextEvidenceBuilder`, `_smc_fingerprint` | inventory every MCE/sector-macro diagnostic use; do not assume equivalence to sector peer context |
| Company quality | `CompanyQualityContextEvidenceBuilder`, `_cq_fingerprint`, Alpha/Trigger `company_quality_context` contribution | `company_quality.bag`: `company_quality_score`, `cq_valuation_score`, ticker-profile fallbacks |
| Ticker profile | `TickerProfileClassifier`/assembler, `_tp_fingerprint` | `tp_liquidity_score`, `tp_volatility_score`, and every chapter/product consumer; curriculum use must be classified separately |
| Institutional accumulation | institutional evidence builder, `_ia_evidence_fingerprint`, Alpha/Trigger `institutional_flow` contribution | `institutional.accumulation_bag`: group score and `ia_*` fields |
| Market context | frozen observation `shared.market_context`, `_market_context_fingerprint`, snapshot fallback | `mce.screen_display`; identify observation-bound authority versus current table fallback |
| Volatility/setup/strategy diagnostic bags | corresponding observation fingerprint builders | inventory all challenge consumers; do not promote curriculum-only reads into product scope |

For each consumed field, the design must record:

- exact persisted JSON path and sample unit/window;
- field type, unit, scale, sign, null/missing meaning, and PIT cutoff;
- canonical producer callable and owning layer;
- all typed configuration and reference-data inputs that can change meaning;
- formula/contract ID and deterministic digest material;
- upstream provenance and availability authority;
- whether it is `DIAGNOSTIC`, `IDENTITY`, `INTEGRITY`, or irrelevant to that
  named panel;
- current fallback/alias behavior in ml-saham and whether it must be deleted;
- mutation proving the feature or missingness changes.

## 5. Non-Goals / Do Not Interpret This As

- No code, config, SQLite, artifact, or corpus changes during this design vet.
- No expansion of ADR-068 canonical Action `compatibility_id` with diagnostic
  config, diagnostic code, raw files, or source revision.
- No promotion of diagnostic evidence into Signal, Risk, TradeSetup, or Action.
- No generic repository/source hash presented as semantic identity.
- No one global diagnostic hash unless the inventory proves every named panel
  has exactly the same material producer set and fork requirements.
- No consumer reconstruction of producer identity from observed values.
- No largest/latest producer-ID auto-selection for production-facing panels.
- No fallback that treats missing binding as the current producer.
- No retroactive synthesis, rewrite, or reinterpretation of historical rows.
- No curriculum reader may silently define challenge-product authority.
- No ml-saham write, migration, repair, PRAGMA mutation, or schema ownership over
  ai-saham SQLite.

## 6. Architecture Impact Assessment

This task itself is read-only design work.

```md
Layer plan:
- Domain: not touched
- Application: not touched; inventory proposed typed binding owner
- Infrastructure: not touched; inventory persistence/read-only transport options
- Adapter: not touched
- Documentation/governance: produce the completed design matrix and implementation task
```

- New dependency: No.
- Determinism: the selected design must use deterministic typed canonical
  material.
- Persistence change: none in this task; likely later observation-schema work,
  to be decided explicitly.
- Warm-up data: none for identity; individual producers retain their existing
  data requirements.
- Adapter policy: forbidden.

Cross-repository boundary remains:

- ai-saham owns producer semantics, observation writes, schemas, and binding
  creation.
- ml-saham reads upstream data read-only and independently verifies bindings
  before diagnostic panel pooling.

## 7. AI Usage Declaration

No AI involved in authority. The vet is deterministic code/data-contract
analysis; any assistant-written prose must be verified against current code.

## 8. Risk, Signal, And Evidence Authority

- Live Signal/Risk/TradeSetup/Action: unchanged and explicitly out of scope.
- Diagnostic evidence remains report-only and non-authoritative.
- The problem is challenge feature comparability, not production judgment.
- No diagnostic challenge result may auto-promote production configuration.

Provisional later classifications to resolve:

- ai-saham: likely `OBSERVATION_SCHEMA` for persisted bindings and
  `EVIDENCE_CONTRACT` only where a diagnostic evidence meaning/derivation
  contract is versioned; never `CONFIG_MATERIAL` for the canonical Action ID.
- ml-saham: likely `DATA_CONTRACT` + `PANEL_SCHEMA`, and possibly
  `ARTIFACT_SCHEMA` if results persist the diagnostic producer identity.

## 9. Data & Persistence Vet

Read only:

- current ai-saham observation builders and live-shaped redacted payloads;
- current SQLite schema/rows using explicit read-only mode;
- ml-saham panel extractors, diagnostic specs, protocols, artifacts, and reopen
  paths;
- current config/resolvers/composition roots for each producer.

Write only the eventual design/backlog documentation through a separately
approved documentation task. Do not edit either repository during evidence
collection.

The vet must compare live DB values only to prove path/presence/cardinality and
mixed-producer risk. It must not claim that equal observed values prove equal
producer semantics.

## 10. Required Design Authority Matrix

The successor implementation task must replace this routing matrix with one row
per exact diagnostic artifact/family and complete every cell:

| Artifact / boundary | Authority owner and source | Exact identity dimensions | Integrity proof | Semantic contract checks | Missing state | Invalid / conflicting state | May contribute to a diagnostic challenge when |
|---|---|---|---|---|---|---|---|
| Observation/Action cohort | ai-saham canonical producer | Existing ADR-068 triple, purpose, schema, population/window/session/cutoff | Existing ID/digest and snapshot verification | Action identity only; diagnostics explicitly excluded | Existing collecting/blocked state | Existing Action identity corruption blocks | Canonical observation authority passes independently |
| Diagnostic producer binding | Exact named ai-saham typed producer/builder | Purpose/family contract, formula/config digest, schema, window/cutoff, source-authority version | Recompute binding ID and canonical payload digest independently | Exact active producer contract; no raw hash or inferred-current default | Typed absent/unavailable, never current-by-default | Missing/mixed/unknown/malformed/digest-invalid binding blocks that diagnostic family | Exact relevant producer binding verifies for every counted row |
| Diagnostic feature payload | Exact observation builder/path | Field set/version, producer binding linkage, observation/window identity | Validate serialized field types/paths and binding linkage | Units, missingness, PIT, derivation, and diagnostic-only authority | Explicit unavailable feature; not zero | Wrong field family/path/unit/window or cross-binding linkage blocks | Feature and producer binding both validate |
| External/reference authority | Exact calendar/sector/profile/provider authority used by producer | Coverage interval/set, revision/completeness, consumed keys | Prove exact consumed set/interval and PIT availability | Producer and challenge interpret same source/axis | Unproven coverage distinct from authoritative empty | Stale/partial/future/mismatched reference authority blocks affected feature | Exact reference coverage is proven read-only and bound |
| Diagnostic panel/cohort | Named ml-saham panel builder | Explicit Action `compatibility_id` plus exact diagnostic producer identity and protocol/sample unit | Consume only validated rows; preserve exclusion diagnostics | No implicit pooling, fallback, largest/latest, or curriculum authority | Insufficient valid rows = typed blocked/inconclusive state | Any mixed producer set contributes zero rows/authority | Every counted row shares both selected identities and panel minimums pass |
| Diagnostic result/artifact/reopen | ml-saham writer/verifier | Artifact schema/ID, Action cohort, diagnostic producer ID, spec/protocol, population/range, source revision | Recompute artifact integrity and re-resolve upstream identities read-only | Historical/unbound result cannot become current/promotion eligible | Historical display-only | Missing upstream authority or identity mismatch blocks reopen/promotion | Current upstream identities and all protocol gates verify |
| Repository/transport | ai-saham write port/SQLite; ml-saham read-only boundary | Exact row keys and serialized binding fields | Read-time schema/JSON/ID/digest checks; read-only tripwire | Deserialization is not verification; no adapter invention | Missing table/field/binding typed explicitly | Schema/query/serialization errors propagate or block | Exact authoritative rows arrive through the permitted path |

The design must also classify every consumed DTO/JSON field as `IDENTITY`,
`INTEGRITY`, `SEMANTIC_CONTRACT`, `DIAGNOSTIC`, or `IRRELEVANT`, justifying any
`IRRELEVANT` field that could plausibly change feature meaning or grouping.

## 11. Required Evidence And Counterexamples

- Record both repository HEADs and dirty status; preserve unrelated changes.
- Enumerate diagnostic specs and distinguish product challenge from curriculum.
- Trace every extractor fallback and alias; test primary and fallback paths
  against live-shaped golden payloads.
- Query current observations read-only by Action cohort, payload schema, window,
  producer source revision, and presence of each diagnostic family.
- For each feature family, transiently mutate one typed config value and one
  producer formula seam; prove the persisted/extracted feature or missingness
  changes while Action `compatibility_id` does not.
- Prove whether producer semantics are common across 7/30/90 windows or require
  per-window bindings.
- Prove whether one family digest would over-fork unrelated panels using an
  explicit dependency matrix, not intuition.
- Inspect artifact/reopen paths to ensure a diagnostic result cannot discard the
  producer identity after panel construction.
- Run the ai-saham data audit gate and ml-saham focused diagnostic/contract
  suites read-only; distinguish unrelated live-data warnings.
- Verify upstream DB SHA/size/mtime and both worktrees are unchanged afterward.

## 12. Acceptance Criteria

- [x] Every production-facing diagnostic feature has an exact current
      producer-to-consumer lineage row.
- [x] Curriculum-only consumers are identified and excluded from authority.
- [x] Every fallback/alias is classified as retained exact contract or deleted;
      no open-ended legacy fallback remains.
- [x] One exact typed binding owner, transport path, persistence location, and
      verifier is selected.
- [x] The design explicitly decides global versus purpose-specific identities
      from a producer/consumer dependency matrix.
- [x] Action cohort identity remains unchanged and diagnostic evidence remains
      non-authoritative.
- [x] Missing, mixed, invalid, historical, and cross-window states are defined
      exactly.
- [x] Observation schema, panel schema, artifact schema, clean-break behavior,
      and rollout order are selected explicitly.
- [x] The successor implementation task contains the completed authority matrix,
      exact constants/types/paths, negative tests, composition roots, and close
      gates required by `AGENT_QUICKSTART.md`.
- [x] No code, SQLite, config, artifact, or unrelated worktree state changed
      during this vet.

## 13. Testing Expectations

This is a read-only vet, so tests characterize current behavior rather than
landing a fix:

- ai-saham focused observation, Alpha/Trigger, profile/sector/company-quality,
  behavioral identity, and persistence contract tests;
- ml-saham diagnostic extractor, cohort, artifact, and reopen tests with bounded
  temp paths and no cache writes into the shared checkout;
- ml-saham `./scripts/check_challenge_contracts.sh`;
- live-shaped extraction probes and read-only SQLite tripwire;
- `git diff --check` in both repositories.

The final design report must state test commands, exits, limitations, and why
any skipped gate was not applicable. Ruff/compile gates become mandatory in the
later Python implementation, not this read-only design task.

## 14. Documentation Impact

- README update: No during vetting.
- New config options: No.
- Limitations: Yes — explicitly state that current Action compatibility does
  not prove diagnostic feature-producer coherence.
- Expected design references: both BOUNDARY mirrors, ai-saham ADR-057/068 and
  observation contracts, ml-saham `data_contract.md`, challenge extract/product
  contracts, and relevant diagnostic specs.

## 15. Agent Execution Instructions

Before starting, the agent must:

1. Confirm read-only scope, both repository boundaries, deterministic-first
   behavior, diagnostic non-authority, and shared-worktree protection.
2. State stale-contract risks, the exact feature families to inventory, and the
   read-only command/test plan.
3. Complete code and live-data lineage before proposing schema. Do not begin
   from a preferred hash shape.
4. Present one chosen design in the successor task, plus a
   `Do Not Interpret This As` section and adversarial negative tests.
5. Stop if the design would require diagnostic promotion, canonical Action
   over-forking, consumer-inferred identity, upstream writes from ml-saham, or
   historical reinterpretation.

This task closes when the design is implementation-ready, not when it merely
lists possible identity schemes.

## 16. Vet Result And Current-Code Evidence

RC-01B is confirmed and the design below is implementation-ready. The vet used
current code at ai-saham `d3c7e669` and ml-saham `c639d1a3`; documentation was
only a routing aid. Four production-facing diagnostic specs are shipped:

1. `mce.screen_display`
2. `sector.peer_context`
3. `institutional.accumulation_bag`
4. `company_quality.bag`

Sector-macro, standalone ticker-profile, volatility, setup, and strategy bags
are persisted but have no current challenge-product diagnostic spec. Curriculum
and display readers do not acquire product authority from this task.

The original Alpha/Trigger mutation remains decisive: disabling the resolved
diagnostic producer removes persisted output while the v4 Action compatibility
ID, policy-snapshot digest, and behavioral-probe digest remain unchanged. This
is correct for Action identity and proves the need for a separate diagnostic
identity.

Current ml-saham behavior adds four confirmed defects to the original finding:

- direct diagnostic execution has no explicit compatibility option and
  `build_diagnostic_panel()` permits exploratory largest-cohort selection;
- `challenge health --with-diagnostics` does not forward its selected Action
  compatibility ID to diagnostic health;
- diagnostic control scores load the packaged
  `screener.accum.score_weights` fixture instead of the verified v4/nine
  production snapshot;
- `sector.peer_context.peer_breadth` looks for legacy aliases, but ai-saham
  persists canonical `sc_sector_breadth`, so the live feature is always absent.

The inspected corpus contained five ACCUM cohorts (1,890, 349, 304, 45, and 45
rows). Current exploratory selection chose the 1,890-row legacy cohort and
produced 1,665 H10 rows per diagnostic. Sector context was present in all 1,665
rows, while `peer_breadth` was present in zero despite `sc_sector_breadth` being
stored. The observation-bound market context was present in that cohort, but a
current-table fallback remains in code and is unsafe. No historical row proves
the new contract.

Focused characterization passed:

```text
ai-saham producer/serialization/config tests: 219 passed
ml-saham diagnostic/cohort tests: 18 passed
```

These tests characterize current behavior; they do not validate the missing
identity. Both worktrees' unrelated dirty state was preserved, and no product
code, SQLite row, configuration, or artifact was changed by this vet.

## 17. Chosen Identity And Persistence Contract

Use purpose-specific composite bindings owned and written by ai-saham. Do not
use one global diagnostic hash, extend Action compatibility, or infer identity
from feature values.

### 17.1 Immutable producer snapshots

Add ai-saham table `learning_diagnostic_producer_snapshots` with contract
`diagnostic_producer_snapshot.v1` and these logical columns:

```text
snapshot_id, schema_version, contract_id, purpose, producer_id,
producer_contract_id, formula_id, canonical_payload_json, payload_digest,
source_revision, created_at
```

`payload_digest` is SHA-256 over canonical JSON of the complete typed semantic
payload. `snapshot_id` is SHA-256 over canonical JSON containing
`contract_id`, `purpose`, `producer_id`, `producer_contract_id`, and
`payload_digest`. `source_revision` is provenance only. A semantic change
always creates a new immutable row; no compatibility ID participates in the
snapshot key.

The application use case
`EnsureAccumulationDiagnosticProducerSnapshotsUseCase` receives the exact same
resolved typed objects used by production builders, canonicalizes them, and
persists snapshots atomically before observation persistence. Adapters neither
parse configuration nor construct identity.

### 17.2 Observation binding

Bump the accumulation observation payload from schema 13 to schema 14. Add one
root `diagnostic_bindings` object keyed by the four exact diagnostic IDs. Each
entry has this closed shape:

```json
{
  "contract_id": "diagnostic_binding.accum.v1",
  "diagnostic_id": "sector.peer_context",
  "compatibility_id": "sha256:<digest>",
  "producers": {
    "diagnostic.alpha_trigger_projection": {
      "snapshot_id": "sha256:<digest>",
      "payload_digest": "sha256:<digest>"
    }
  }
}
```

The composite compatibility ID is canonical SHA-256 over the binding contract,
diagnostic ID, observation schema version, and an exact producer-ID-sorted list
of required snapshot IDs and payload digests. The window role is fixed by the
feature contract below; it is not inferred from an available window. Unrelated
producer changes therefore do not fork another diagnostic panel.

Required producer sets are closed:

| Diagnostic ID | Required producer IDs |
|---|---|
| `mce.screen_display` | `diagnostic.market_context.frozen` |
| `sector.peer_context` | `diagnostic.alpha_trigger_projection`, `diagnostic.sector_peer_context` |
| `institutional.accumulation_bag` | `diagnostic.alpha_trigger_projection`, `diagnostic.institutional_accumulation` |
| `company_quality.bag` | `diagnostic.alpha_trigger_projection`, `diagnostic.company_quality_context`, `diagnostic.ticker_profile` |

Unknown, duplicate, missing, or extra producers invalidate that binding. They
do not invalidate the Action observation or an unrelated diagnostic binding.

## 18. Exact Producer Semantic Payloads

| Producer ID | Producer contract / formula ID | Complete canonical material |
|---|---|---|
| `diagnostic.alpha_trigger_projection` | `diagnostic.alpha_trigger_projection.accum.v1` / `signal_alpha_trigger_projection.build_score.v1` | resolved enabled state, default horizon, route membership/fractions, and formula maps needed to determine contribution presence and score |
| `diagnostic.sector_peer_context` | `diagnostic.sector_peer_context.v1` / `sector_context_evidence_builder.build.v1` | complete `SectorContextConfig` plus the ordered sector-universe group/ticker list; ordering is preserved because first-match group selection is semantic |
| `diagnostic.institutional_accumulation` | `diagnostic.institutional_accumulation.v1` / `institutional_accumulation_evidence_builder.build.v1` | complete `InstitutionalAccumulationConfig`, normalized sorted foreign-broker codes, all windows, weights, and minimum-session rules |
| `diagnostic.company_quality_context` | `diagnostic.company_quality_context.v1` / `company_quality_context_evidence_builder.build.v1` | complete `CompanyQualityContextConfig`, the exact resolved `SignalScoringConfig`, and neutral score |
| `diagnostic.ticker_profile` | `diagnostic.ticker_profile.v1` / `ticker_profile_classifier.classify.v1` | complete `TickerProfileConfig` plus normalized universe-membership material consumed by the classifier |
| `diagnostic.market_context.frozen` | `diagnostic.market_context.frozen.v1` / `market_context_engine.evaluate.v1` | complete resolved `MarketContextConfig`, factor thresholds, benchmark/banking/general universes, availability rules, and frozen-context serialization formula |

Composition must correct one current seam: company-quality construction
currently permits a bare default `SignalScoringConfig()` while other paths use
resolved configuration. Resolve one exact typed object at the composition root
and pass that same object to both the builder and snapshot use case. No code may
inspect private builder fields to reconstruct material.

## 19. Product Feature Lineage And Missing Semantics

Every product extractor uses exactly `features_by_window.7`; there is no 30/90,
first-present, root, or legacy fallback.

| Diagnostic / feature | Exact schema-14 source | Type / unit and missing meaning | Canonical producer |
|---|---|---|---|
| MCE `regime_score` | `shared.market_context.regime` | ml mapping score; unknown/missing = unavailable, not zero | frozen MCE |
| MCE `vix` | `shared.market_context.factors[vix].value` | raw VIX level; absent = unavailable | frozen MCE |
| MCE `eido` | `shared.market_context.factors[eido].value` | divergence percent; absent = unavailable | frozen MCE |
| MCE `usd_idr` | `shared.market_context.factors[usd_idr].value` | change percent; absent = unavailable | frozen MCE |
| MCE `idx_trend` | `shared.market_context.factors[idx_trend].value` | trend percent; absent = unavailable | frozen MCE |
| MCE `idx_breadth` | `shared.market_context.factors[idx_breadth].value` | breadth percent; absent = unavailable | frozen MCE |
| MCE `foreign_flow` | `shared.market_context.factors[foreign_flow].value` | average IDR flow; absent = unavailable | frozen MCE |
| Sector `sector_context_score` | `features_by_window.7.signal.alpha_trigger_score.group_contributions[group=sector_context].score` | score 0-100; absent contribution = unavailable | Alpha projection + sector context |
| Sector `peer_breadth` | `features_by_window.7.sub_signal_fingerprint.sc_sector_breadth` | ratio 0-1; absent = unavailable | sector context |
| Institutional `institutional_flow_score` | `features_by_window.7.signal.alpha_trigger_score.group_contributions[group=institutional_flow].score` | canonical flow-group score 0-100; absent contribution = unavailable | Alpha projection + canonical Action flow inputs |
| Institutional `ia_foreign_participation` | `features_by_window.7.sub_signal_fingerprint.ia_foreign_participation` | ratio 0-1; absent = unavailable | institutional accumulation |
| Institutional `ia_domestic_buy_vwap_distance` | `features_by_window.7.sub_signal_fingerprint.ia_domestic_buy_vwap_distance` | signed ratio; absent = unavailable | institutional accumulation |
| CQ `company_quality_score` | `features_by_window.7.signal.alpha_trigger_score.group_contributions[group=company_quality_context].score` | score 0-100; absent contribution = unavailable | Alpha projection + company quality |
| CQ `cq_valuation_score` | `features_by_window.7.sub_signal_fingerprint.cq_valuation_score` | nullable score 0-100; absent = unavailable | company quality |
| CQ `tp_liquidity_score` | `features_by_window.7.sub_signal_fingerprint.tp_liquidity_score` | nullable ratio 0-1; absent = unavailable | ticker profile |

All values are diagnostic only. The relevant observation session/cutoff and
Action population identity provide PIT/sample authority; producer bindings
provide semantics. A missing value remains unavailable and never becomes zero.

## 20. Consumer Clean Break And Fail-Closed Rules

ml-saham must make these changes as one coordinated panel-contract cutover:

1. Direct diagnostic commands require explicit `--compatibility-id` and
   `--diagnostic-compatibility-id`. No largest, latest, or single-cohort
   production auto-selection remains.
2. Diagnostic health requires an exact repeatable mapping of diagnostic ID to
   diagnostic compatibility ID. A missing mapping blocks only that diagnostic.
3. First verify the Action cohort against active v4/nine authority, then require
   schema-14 observations and the exact root binding on every counted row.
4. Read `learning_diagnostic_producer_snapshots` in SQLite `mode=ro`; recompute
   canonical payload digest, snapshot ID, closed producer set, and composite ID.
5. Load diagnostic control scoring from the already verified active v4
   production-policy set. Remove the packaged static fixture from product
   diagnostic authority.
6. Compute the diagnostic spec content digest from canonical spec content,
   including feature definitions, regime mapping, and extractor-contract ID.
   A hand-maintained literal is not an integrity proof.

Delete these product fallbacks:

| Current behavior | Required behavior |
|---|---|
| `_pick_window_blob` chooses 7/30/90/first | exact `features_by_window.7` only |
| root-level signal/fingerprint/candidate views | schema-14 canonical paths only |
| group-score aliases and aggregate fallbacks | exact named Alpha/Trigger contribution only |
| root MCE and current `market_context_snapshots` fallback | exact observation-bound `shared.market_context` only |
| `peer_breadth`/`sector_breadth`/`breadth_at_signal` aliases | exact `sc_sector_breadth` only |

Schema 13 and older observations and schema-3 diagnostic artifacts are
historical raw/display-only. They receive no backfill, synthesized binding,
alias, compatibility mapping, or current-producer interpretation. Missing,
mixed, invalid, unknown, extra, cross-window, or unbound identity yields typed
`BLOCKED_DIAGNOSTIC_BINDING` for that diagnostic. No current Action cohort is
purged or invalidated; schema-14 diagnostic cohorts accumulate prospectively.

## 21. Result Artifact And Reopen Contract

Introduce diagnostic result artifact schema 4, explicitly mode-tagged and
non-promotable. Its manifest binds:

- Action compatibility ID and verified v4 policy snapshot set;
- diagnostic compatibility ID and exact producer snapshot IDs/digests;
- observation schema 14, diagnostic spec content digest, and protocol;
- population identity, date/session/cutoff range, exclusions, and sample unit;
- upstream database source revision/provenance.

Add a read verifier that re-resolves both Action and diagnostic identity before
comparison, display, or reopen. Deserialization alone is not verification.
There is no diagnostic promotion path. Historical schema-3 artifacts stay
display-only.

## 22. Completed Authority Matrix

| Boundary | Authority / identity | Integrity and semantics | Missing / invalid behavior |
|---|---|---|---|
| Action cohort | ai-saham v4/nine compatibility triple | existing snapshot and probe verification | existing blocked/legacy state; independent of diagnostics |
| Producer snapshot | ai-saham typed snapshot use case; producer contract + formula + typed payload | ml recomputes payload digest and snapshot ID read-only | missing/unknown/digest-invalid row blocks affected diagnostic |
| Observation binding | schema-14 root purpose binding | closed producer set and recomputed composite ID | absent/mixed/extra/cross-linked binding blocks affected diagnostic |
| Feature payload | exact window-7 paths in section 19 | types, units, null semantics, PIT and producer linkage | wrong path/window/unit or implicit zero is invalid |
| Panel | explicit Action ID + purpose-specific diagnostic ID | all counted rows share both verified identities | insufficient rows is blocked/inconclusive; no auto-selection |
| Artifact/reopen | ml diagnostic artifact v4 | recompute artifact, panel, producer, and upstream identities | historical/unbound/mismatch is display-only or blocked |
| Transport | ai writes SQLite; ml reads `mode=ro` | schema, canonical JSON, ID, digest, and closed-set checks | query/schema/serialization errors propagate as typed block |

Field classification is closed as follows: compatibility IDs and snapshot IDs
are `IDENTITY`; canonical payload/spec/artifact digests are `INTEGRITY`; formula
IDs, exact paths, units, windows, PIT and missing rules are
`SEMANTIC_CONTRACT`; feature values and results are `DIAGNOSTIC`; timestamps and
source revision are provenance. None may contribute to Signal, Risk,
TradeSetup, Action, or production promotion.

## 23. Implementation Plan, Negative Tests, And Close Gates

### Layer plan

- Domain: immutable producer/binding value types and typed invalid/missing
  states only; no workflow.
- Application: canonical payload builders, snapshot ensure use case, schema-14
  observation binding, and composition from the same typed producer objects.
- Infrastructure: ai-owned immutable table/repository and ml read-only verifier.
- Adapter: explicit CLI arguments and rendering of typed blocks only.
- Documentation/governance: both boundary mirrors and data/panel/artifact
  contracts updated after executable behavior is verified.

Required negative tests must prove:

- every independently material producer mutation forks only dependent
  diagnostic IDs while Action compatibility remains unchanged;
- semantic formula/spec/regime-map mutation changes its content identity;
- missing, mixed, duplicate, extra, unknown, malformed, digest-invalid, or
  cross-purpose snapshot references contribute zero rows;
- schema <=13, artifact schema 3, missing explicit IDs, and largest/latest
  selection cannot acquire product authority;
- 30/90/first-window, root aliases, current-MCE-table fallback, and static
  control-policy fallback are rejected;
- `sc_sector_breadth` extracts with its defined ratio while every legacy alias
  fails;
- absent MCE factors and optional CQ/TP/IA values remain unavailable, not zero;
- artifact reopen fails after any upstream Action, diagnostic, spec, population,
  source, or payload identity mismatch;
- SQLite is byte-identical across all ml-saham reads and failure paths.

The implementation closes only after focused vertical producer -> immutable
snapshot -> schema-14 observation -> SQLite -> ml read-only verifier -> panel ->
artifact/reopen proof, both repositories' contract suites, the mandatory
ai-saham data audits, full relevant pytest, whole-repository Ruff check and
format check, compile/package gates where applicable, and `git diff --check`.

### Do Not Interpret This As

- Do not place diagnostic producer material in Action compatibility.
- Do not create a repository/source hash or one global diagnostic hash.
- Do not infer current semantics from values, timestamps, or the only cohort.
- Do not repair or reinterpret historical observations or artifacts.
- Do not allow ml-saham to write ai-saham SQLite.
- Do not make diagnostic output promotable or authoritative.
- Do not move policy or binding construction into CLI/TUI adapters.
