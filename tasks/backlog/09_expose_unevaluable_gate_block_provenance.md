# Bind And Consume Persisted Unevaluable-Gate Provenance

Status: `IMPLEMENTED` — redesigned from the stale draft on 2026-08-08; shipped
2026-08-08 (snapshot binding + ml-saham adapter v2).
Sequence: **must land before task 04's purge and rebuild** — see
`tasks/backlog/00_SEQUENCE_accum_baseline_and_learning_loop.md`.

## 1. Vetted Verdict

The original task's central claim is false in current code.

Canonical accumulation observations already persist the exact evidence needed
to distinguish an unevaluable aggregate-policy block from a gate that genuinely
triggered. `AccumulationCandidateObservationPersister._build_engine_pack()`
adds a `risk` object after `build_candidate_observation_payload()` returns, via
`build_risk_assessment_capture_dict()`. The stored per-window paths include:

- `features_by_window.7.risk.unevaluable_gates`
- `features_by_window.7.risk.gate_evaluations`
- `features_by_window.7.risk.gate_triggered`

The previous grep stopped at the partial payload builder and therefore missed
the authoritative persister enrichment. Adding another observation field or
bumping schema 15 would duplicate an existing contract.

The real defect is downstream binding and interpretation:

1. ai-saham's `risk.accum.unevaluable_policy` snapshot says it has no
   `observation_result_fields`, although the fields exist in every persisted
   window whose risk assessment ran.
2. ai-saham's `risk.accum.hard_gates` snapshot declares only coarse
   `trade_setup.blocking_gates` and `candidate.risk_status`, not the exact
   per-gate audit outcomes.
3. ml-saham's hard-gate panel reads only `trade_setup.blocking_gates`. It ignores
   `risk.gate_evaluations` and therefore maps both an aggregate-policy block and
   a genuine gate trigger to the same component value.
4. ml-saham also invents a block for the first enabled gate when an action is
   blocked but no gate name maps. That fallback is not evidence-backed.

This is a data-contract and consumer-correctness fix, not a new persistence
shape.

## 2. Executable Evidence

Current evaluator results for the same `FundamentalGate` name are distinct:

| Case | `risk.gate_triggered` | `risk.unevaluable_gates` | Fundamental evaluation |
|---|---|---|---|
| Aggregate `UnevaluableGatePolicy=block`; F-score missing | `FundamentalGate` | `["FundamentalGate"]` | `outcome="skipped"`, `triggered=false` |
| F-score present and genuinely below threshold | `FundamentalGate` | `[]` | `outcome="triggered"`, `triggered=true` |

Passing both current shapes to ml-saham's
`extract_gate_components()` produces the same result:
`fundamental_gate=1.0`. The corpus can distinguish the cases; the consumer does
not.

A read-only inspection of `data/db/data.db` found the `risk` object and all
three audit keys in current stored rows. The inspected schema-9, schema-12, and
schema-13 cohorts contained no non-empty `unevaluable_gates`, consistent with
the shipped aggregate policy being `surface` and the configurations exercised
by those captures. No database write was performed.

Focused baseline checks before redesign:

- ai-saham: 57 passed across unevaluable policy, snapshot payload, and cohort
  identity tests.
- ml-saham: 18 passed across hard-gate and production-snapshot tests.

Those green tests encode the current incomplete binding; they do not disprove
the counterexample.

## 3. Required Fix Contract

### ai-saham

1. Keep `CANDIDATE_OBSERVATION_SCHEMA_VERSION == 15`. The required fields are
   already part of the canonical schema-15 payload. Do not create schema 16 for
   this task.
2. Change `build_unevaluable_gate_policy_payload()` to declare the existing
   result paths:
   - `features_by_window.7.risk.unevaluable_gates`
   - `features_by_window.7.risk.gate_evaluations`
3. Change `build_risk_hard_gates_payload()` so the exact authoritative result
   binding includes `features_by_window.7.risk.gate_evaluations`.
   `trade_setup.blocking_gates` and `candidate.risk_status` may remain as coarse
   action/presentation companions, but must not be the sole source for per-gate
   attribution.
4. Remove the stale builder docstring/note and the test asserting that the
   unevaluable policy has no observation fields.
5. Exercise the real canonical persister in the vertical regression. A test
   that stops at `build_candidate_observation_payload()` is not sufficient,
   because the persister owns the `risk` enrichment.
6. Keep the closed ADR-059 contract at `production_policy_snapshot.v4` with the
   same nine policy IDs. This changes row payload content, not the closed set or
   snapshot contract version.
7. Keep policy version/formula IDs at v1 unless implementation uncovers an
   actual decision-rule change. This task corrects field binding; it must not
   change gate evaluation, ordering, thresholds, or aggregate policy behavior.

Changing either canonical policy payload changes the ADR-059 snapshot-set
digest. ADR-068 folds that digest into the accumulation `compatibility_id`, so
this fix is identity-moving even though observation schema remains 15. It must
land before task 04's one purge and rebuild.

### ml-saham

1. Strengthen the v4 snapshot verifier to require the exact declared risk audit
   paths for `risk.accum.unevaluable_policy` and `risk.accum.hard_gates`.
2. For current schema-15 observations, extract hard-gate components from
   `features_by_window.7.risk.gate_evaluations`:
   - `triggered` -> blocked component (`1.0`)
   - `blocked_on_missing` -> blocked component (`1.0`), because the individual
     gate's own missing-data policy blocked
   - `pass`, `skipped`, `not_evaluated` -> not blocked (`0.0`)
3. Treat absent or malformed current risk audit data as unextractable/fail
   closed. Never turn missing evidence into all-clear or assign a blocked action
   arbitrarily to the first gate.
4. Remove the top-level legacy fallback from the production current-schema path
   or isolate it behind an explicitly historical reader. Do not broaden
   compatibility debt.
5. Bump the hard-gate adapter and conformance identity from v1 to v2, update the
   live-shaped golden fixture, and update the ML data-contract documentation.
   The panel schema can stay structurally the same, but its source semantics and
   extraction path change.
6. Keep `risk.accum.unevaluable_policy` identity-only. Do not invent a standalone
   challenger or scorer for an aggregate missing-data policy.

## 4. Semantics And Scope

Classification:

- ai-saham engine behavior: `NON_SEMANTIC`
- ai-saham policy snapshot material: `CONFIG_MATERIAL`
- accumulation cohort identity: moves through the snapshot-set digest
- observation schema: unchanged at 15
- ml-saham: `DATA_CONTRACT` + hard-gate adapter/conformance change

The authoritative distinction is the typed audit outcome, not a string
comparison between `gate_triggered` and `unevaluable_gates`.

`RiskAssessment.gate_triggered` remains semantically awkward for aggregate
policy blocks: it contains the first unevaluable gate name even though that
gate's audit row says `triggered=false`. Renaming or restructuring this domain
field would change broader action transport and is explicitly out of scope.
The exact persisted audit already supports correct corpus and challenge
behavior.

If a candidate exits before risk evaluation and therefore has no `risk` object,
that means `risk_not_evaluated`/not applicable. It is not an all-clear result and
must not be included as an evaluated hard-gate row.

`TradeSetup` remains a coarse action/presentation transport. It is not the
authority for ML per-gate attribution.

## 5. Non-Goals

- No gate decision, ordering, threshold, confidence, or short-circuit change.
- No change to the shipped `unevaluable_policy: surface` default.
- No new domain marker solely to duplicate `gate_evaluations`.
- No observation schema bump, SQL migration, historical reinterpretation, dual
  reader, or retroactive patching of old cohorts.
- No task-04 corpus purge or rebuild in this task.
- No standalone ML challenger for `risk.accum.unevaluable_policy`.

## 6. Layer Plan

```md
Layer plan:
- Domain: not touched
- Application: correct policy snapshot result-field declarations and vertical tests
- Infrastructure: not touched
- Adapter: no ai-saham adapter changes
- Cross-repo ml-saham: strict snapshot verification and hard-gate adapter v2 extraction
- Documentation/governance: ADR-059/data-contract wording and sequence contract
```

Adapters remain thin: the ML extractor translates persisted typed audit records
into panel components; no workflow or policy decision moves into an adapter.
AI is not involved.

## 7. Acceptance Criteria

- [x] A vertical ai-saham test runs a genuine trigger and an aggregate-policy
      block through the canonical observation persister and proves their stored
      risk audit differs.
- [x] Every declared `observation_result_fields` path resolves against a
      live-shaped schema-15 observation.
- [x] Mutating either corrected policy payload moves the snapshot-set digest and
      `compatibility_id`; changing the declarations does not move the behavioral
      probe digest or schema version.
- [x] ml-saham maps `triggered` and `blocked_on_missing` to `1.0`, and maps
      `pass`, `skipped`, and `not_evaluated` to `0.0`.
- [x] The aggregate-policy block counterexample no longer appears as a genuine
      FundamentalGate trigger in the hard-gate panel.
- [x] Missing/malformed schema-15 `risk.gate_evaluations` is rejected or skipped
      with an explicit diagnostic; no first-enabled-gate fallback remains.
- [x] Current-schema production extraction has no implicit top-level legacy
      fallback.
- [x] ml-saham hard-gate adapter/conformance v2 golden passes.
- [x] `production_policy_snapshot.v4`, its nine-row closed set, and observation
      schema 15 remain unchanged.
- [x] Relevant focused suites pass in both repositories.
- [x] ai-saham whole-repo `ruff check src/ tests/` and
      `ruff format --check src/ tests/` pass before close.

## 8. Required Order

Implement and commit the ai-saham and ml-saham halves contextually, verify the
cross-repo contract, and only then re-vet task 04 against the resulting identity.
Task 04 must not purge or rebuild a cohort whose policy snapshot binding is
known to be wrong.
