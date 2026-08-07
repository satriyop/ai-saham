# ADR-059: Production policy snapshots for ML challenges

## Status

Accepted — 2026-07-31

Amended — 2026-07-31 (`production_policy_snapshot.v2`, hard filters, lean
compatibility.v2 binding)

Amended — 2026-08-06 (`production_policy_snapshot.v3`, aggregate
unevaluable-gate policy as the eighth row)

Amended — 2026-08-07 (`production_policy_snapshot.v4`, resolved canonical
signal decision policy as the ninth row)

## Context

`ml-saham` ADR-002 requires a frozen description of production policy for
challenge baselines (`baseline=production`). The current `ml-saham` packaged
JSON mirrors store hand-entered hashes, are not bound to
`learning_observations.compatibility_id`, and mix production identity with
ML-only panel/alias/protocol concerns.

Without a producer-owned, cohort-bound artifact, WIN/LOSE challenge outcomes
cannot safely inform human production-policy decisions.

v1 shipped six score/signal/risk rows. It did not record the four application
screen hard filters (market-cap floor, Piotroski floor, accumulation-score
floor, signal-score floor). The lean compatibility hash also omitted the
snapshot-binding contract, so later snapshot rows could attach to pre-snapshot
cohorts and appear retrospectively verified. That is forbidden.

## Decision

### Writer and projection rules

1. **`ai-saham` is the sole writer** of production policy snapshot rows in the
   shared SQLite learning DB. `ml-saham` reads and digest-checks only.
2. Snapshots are **content-addressed projections** of the same resolved typed
   engine / screen policies used by live accumulation paths — not a second YAML
   parse in an adapter, not packaged ML mirrors.
3. After the v4 cutover, the active producer writes **only**
   `production_policy_snapshot.v4` rows. No dual-write of v1-v3 under a new
   compatibility ID.

### Immutable v1 closed set (historical)

v1 export set is **closed and exact** (six rows). Do not mutate its meaning or
accept a seventh row under `production_policy_snapshot.v1`:

| `policy_id` | `decision_type` |
|-------------|-----------------|
| `screener.accum.score_weights` | `score` |
| `signal.accum.evidence_group_weights` | `score` |
| `signal.accum.flags` | `score` |
| `signal.accum.classification` | `score` |
| `risk.accum.hard_gates` | `gate` |
| `signal.accum.raw_score` | `score` (identity-only) |

Historical v1 rows remain readable and immutable. They are **ineligible** for
active verified hard-filter / current production challenges that require v2.

### Immutable v2 closed set (historical)

v2 export set is **closed and exact** (seven rows): the six v1 rows plus
`screener.accum.hard_filters` (`gate`). Do not mutate its meaning or accept an
eighth row under `production_policy_snapshot.v2`. Historical v2 rows remain
readable and immutable and are **ineligible** for current production challenges,
which require v3.

### Immutable v3 closed set (historical)

`production_policy_snapshot.v3` is **closed and exact** (eight rows). It is
readable immutable history and cannot satisfy current production eligibility.
Artifact contract version and each policy version are separate: unchanged
policies keep policy version `v1`.

| `policy_id` | `decision_type` | Policy version |
|-------------|-----------------|----------------|
| `screener.accum.score_weights` | `score` | existing `v1` |
| `signal.accum.evidence_group_weights` | `score` | existing `v1` |
| `signal.accum.flags` | `score` | existing `v1` |
| `signal.accum.classification` | `score` | existing `v1` |
| `risk.accum.hard_gates` | `gate` | existing `v1` |
| `signal.accum.raw_score` | `score` | existing `v1` |
| `screener.accum.hard_filters` | `gate` | existing `v1` |
| `risk.accum.unevaluable_policy` | `gate` | `v1` |

Unevaluable-gate semantic contract:

- `semantic_engine_contract_id = risk.unevaluable_gate.accum.v1`
- `formula_id = assess_risk_gate_evaluator.evaluate.unevaluable_aggregate.v1`

This row declares the **aggregate** posture for gates that ran without usable
input, which is orthogonal to each gate's own `missing_data_action` already
declared by `risk.accum.hard_gates`. Its payload records `action`
(`surface | block`), the derived `blocks` flag the evaluator reads,
`block_confidence`, and the closed `supported_actions` vocabulary, sourced from
`risk_engine.gates.unevaluable_policy` /
`risk_engine.gates.unevaluable_block_confidence`.

`surface` and `block` reject different candidates on missing gate data, so the
row is cohort identity, not documentation: before v3 two deployments with
opposite settings shared one `compatibility_id`.

The row declares **no** `observation_result_fields`. No stored observation field
carries this policy's own output — `RiskAssessment.to_dict()` has
`unevaluable_gates` but `AccumulationCandidate.to_dict()` never copies it, and
the persisted risk fields (`candidate.risk_status`, `candidate.risk_gate`,
`trade_setup.blocking_gates`) are already declared by `risk.accum.hard_gates`
and cannot distinguish an unevaluable-block from an ordinary gate trigger.

### Active v4 closed set

`production_policy_snapshot.v4` is **closed and exact**: the immutable eight-row
v3 set plus one ninth row:

| `policy_id` | `decision_type` | Policy version |
|-------------|-----------------|----------------|
| `signal.accum.decision_policy` | `gate` | `v1` |

Decision-policy contract:

- `semantic_engine_contract_id = signal.decision_policy.accum.v1`
- `formula_id = decision_policy_service.resolve.v1`
- `scope = canonical_accum_signal_entry_quality_and_constraints`

Its payload is the complete resolved `DecisionPolicyConfig`: all four regime
policies, every setup/regime route and action, regime-confidence and transition
caps, closed regime/decision vocabularies, missing-state semantics, and the
persisted `entry_quality` / `decision_constraints` paths. The same typed object
is passed to `DecisionPolicyService` and this pure payload builder; no adapter or
second YAML parse owns policy.

Hard-filter semantic contract:

- `semantic_engine_contract_id = screen.accum.hard_filters.v1`
- `formula_id = accumulation_screen.first_match_hard_filters.v1`

Hard-filter payload records floors, enabled states, first-match order
(market_cap → piotroski → accum_score → signal_score), missing actions,
provider-unavailable actions, provider-exception action, and
`explicitly_excluded = [min_net_buy_days]`.

Enabled rules:

- market_cap / piotroski: `enabled = floor > 0`
- accum_score / signal_score: configured enabled flags

Missing/action vocabulary (closed):

`pass_without_evaluation`, `rejected_flow`, `rejected_signal`,
`raise_contract_error`, `propagate_provider_error`.

### Binding constants

- `purpose = ACCUMULATION_DISCOVERY`
- `learning_observation_contract_id =
  learning_observation.accumulation_discovery.v2`
- `producer_observation_contract = accumulation-discovery.v2`
- Observation payload remains ADR-056 v2 (no observation schema bump solely
  for snapshot binding)

### Identity algorithms

Enum members:

- `PRODUCTION_POLICY_SNAPSHOT_V1 = production_policy_snapshot.v1`
- `PRODUCTION_POLICY_SNAPSHOT_V2 = production_policy_snapshot.v2`
- `PRODUCTION_POLICY_SNAPSHOT_V3 = production_policy_snapshot.v3`
- `PRODUCTION_POLICY_SNAPSHOT_V4 = production_policy_snapshot.v4`

`ProductionPolicySnapshot.create` requires an **explicit** `contract_id`
(no default). Snapshot identity:

```text
snapshot_id = stable_learning_id(contract_id, {
  purpose, learning_observation_contract_id,
  producer_observation_contract, compatibility_id, policy_id })
material_config_hash = "sha256:" + policy_snapshot_payload_digest
payload_digest = sha256(canonical_payload_json UTF-8)  # lowercase hex, no prefix
```

Canonical JSON reuses `learning_artifacts.canonical_json`. `created_at` and
`source_revision` are provenance only. Integrity validation recomputes using
`snapshot.contract_id`. Historical v1-v3 IDs remain unchanged.

`LEARNING_SCHEMA_VERSION` remains `1` (row shape unchanged).

### Behavioral compatibility framing

ADR-068 retired lean/config-byte identity. The snapshot-set payload digest is
one of exactly three orthogonal `compatibility_id` axes: behavioral probe
digest, policy snapshot payload digest, and observation payload schema version.
Runtime decision config remains on the snapshot axis; it is not injected into
the probe. `UNIQUE (purpose, compatibility_id, policy_id)` is unchanged. v1-v4
rows may coexist only under different compatibility IDs.

### Schema migration v3

Existing databases that created the table with a v1-only CHECK must rebuild
`learning_policy_snapshots` under learning migration version **3**:

- keep `schema_version CHECK (schema_version = 1)`
- widen `contract_id` CHECK to
  `production_policy_snapshot.v1 | production_policy_snapshot.v2`
- preserve columns and UNIQUE key
- copy with explicit column names; verify counts/contents
- rebuild cohort index; run `foreign_key_check`

Changing only `CREATE TABLE IF NOT EXISTS` is insufficient for existing DBs.

### Schema migration v4

The v3 contract needs the same treatment: databases stamped at migration 3 have
a v1/v2-only CHECK and reject every v3 row. Learning migration version **4**
rebuilds `learning_policy_snapshots` again with the same no-content-loss
procedure, widening `contract_id` CHECK to
`production_policy_snapshot.v1 | .v2 | .v3`. Historical rows are copied
byte-for-byte; the migration widens what may be written and never rewrites what
was.

### Schema migration v5

Learning migration version **5** rebuilds the table once more and widens only
the contract CHECK to `production_policy_snapshot.v1 | .v2 | .v3 | .v4`.
Ordered `(snapshot_id, payload_digest)` pairs and row count must match before
the old table is dropped; the cohort index and `foreign_key_check` are rebuilt.
Historical rows are copied verbatim.

### Producer trigger and bundle identity

Shared `run_signal_observation_corpus_write` (`research accum capture` and
`research accum backfill`) ensures all **nine** v4 snapshots before any
observation write. No separate export command. No dual-write of v1-v3. A
partial eight-of-nine set fails closed before observation writes.

Corpus write resolves one `AccumulationProductionPolicyBundle` that includes
`hard_filter_policy` and injects the same typed objects into engines (where
applicable) and snapshot ensure. Capture may neutralize score filters for
corpus inclusion; the snapshot always uses the **pre-neutralization** hard-filter
policy object.

Market-cap authority remains the live path:

```text
accumulation_screener.screener.min_market_cap_idr
  → SwingPolicyConfig.min_market_cap_idr
  → hard-filter policy / request
```

Do not add a second independently parsed market-cap field for this slice.

### Sector breadth and historical cohorts

The legacy conglomerate-group breadth bonus is retired from production policy
by [ADR-062](ADR-062-retire-accum-group-breadth-production-bonus.md). It remains
out of the closed score_weights snapshot; its dormant configuration and
isolated applier grant no authority. Historical cohorts without the required
active snapshot set remain raw corpus and ineligible for verified
production-policy challenges. No fabricated snapshot backfill onto old rows.

### ML consumer

Active production challenges accept snapshot **v4 / nine rows only**. No v1-v3
fallback for current production eligibility. Historical sets may be parsed only
as non-eligible. The unevaluable and decision-policy rows are identity-only for
challenge purposes; no fabricated scoring adapter is created for either.

## Consequences

- Fresh accumulation capture/backfill materializes nine verified v4 policy rows
  under a new compatibility cohort.
- The hard-filter production baseline is explicit (currently largely
  non-selective defaults) for policy-design tournaments.
- Live Signal/Risk/TradeSetup Actions are unchanged (`NON_SEMANTIC` for engine
  behavior).
- Further closed-set changes require a new task and contract amendment.

## Hardening (2026-07-31 review + v2 amendment)

1. **Exact object identity:** one `AccumulationProductionPolicyBundle` including
   `hard_filter_policy`; no second independent resolve for snapshots.
2. **Atomic closed set:** the whole active closed set (nine v4 rows) validated
   then written with `add_policy_snapshots_atomic` under one `BEGIN IMMEDIATE`
   transaction.
3. **Provenance:** `source_revision` required non-empty
   (`ai-saham@<version>[+git:<sha>]`).
4. **Integrity:** payload metadata keys must match row columns; integrity uses
   `snapshot.contract_id`.

## Related

- ADR-042 deterministic champion and optional model challengers
- ADR-049 database-owned learning pipeline clean break
- ADR-056 accum corpus session observation (payload remains v2; binding forks
  compatibility)
- ADR-057 evidence / diagnostic / corpus vocabulary
- `BOUNDARY.md` policy-snapshot ownership
- Task `activate_screen_hard_filter_tournament_cohort.md`
- Sibling `ml-saham` ADR-002 ideal challenge system
