# ADR-059: Production policy snapshots for ML challenges

## Status

Accepted — 2026-07-31

## Context

`ml-saham` ADR-002 requires a frozen description of production policy for
challenge baselines (`baseline=production`). The current `ml-saham` packaged
JSON mirrors store hand-entered hashes, are not bound to
`learning_observations.compatibility_id`, and mix production identity with
ML-only panel/alias/protocol concerns.

Without a producer-owned, cohort-bound artifact, WIN/LOSE challenge outcomes
cannot safely inform human production-policy decisions.

## Decision

1. **`ai-saham` is the sole writer** of `production_policy_snapshot.v1` rows in
   the shared SQLite learning DB. `ml-saham` reads and digest-checks only.
2. Snapshots are **content-addressed projections** of the same resolved typed
   engine policies used by live accumulation engines — not a second YAML parse
   in an adapter, not packaged ML mirrors.
3. v1 export set is **closed and exact** (six rows per accumulation cohort):

   | `policy_id` | `decision_type` |
   |-------------|-----------------|
   | `screener.accum.score_weights` | `score` |
   | `signal.accum.evidence_group_weights` | `score` |
   | `signal.accum.flags` | `score` |
   | `signal.accum.classification` | `score` |
   | `risk.accum.hard_gates` | `gate` |
   | `signal.accum.raw_score` | `score` (identity-only) |

4. Binding constants for this slice:

   - `purpose = ACCUMULATION_DISCOVERY`
   - `learning_observation_contract_id =
     learning_observation.accumulation_discovery.v2`
   - `producer_observation_contract = accumulation-discovery.v2`
   - `policy_version = v1`

5. **Identity algorithms** (immutable):

   - `snapshot_id = stable_learning_id(PRODUCTION_POLICY_SNAPSHOT, {
       purpose, learning_observation_contract_id,
       producer_observation_contract, compatibility_id, policy_id })`
   - `material_config_hash = "sha256:" +
     sha256(resolved_config_canonical UTF-8).hexdigest()`
   - `payload_digest = sha256(canonical_payload_json UTF-8).hexdigest()`
     (lowercase hex, no prefix)
   - Canonical JSON reuses `learning_artifacts.canonical_json`
   - `created_at` and `source_revision` are provenance only

6. **Cohort consistency** (non-circular):

   - Snapshot digests are **not** folded into `compatibility_id`.
   - `compatibility_id` remains the lean whole-config hash
     (`resolve_lean_semantic_compatibility_id`).
   - Producer recomputes the lean ID from the same
     `resolved_config_canonical` bytes and requires equality before any
     snapshot or observation write.
   - Same `(purpose, compatibility_id, policy_id)` + same digest is idempotent;
     same key + different digest fails closed before observation writes.

7. **Producer trigger:** shared
   `run_signal_observation_corpus_write` path
   (`research accum capture` and `research accum backfill`) ensures all six
   snapshots before any observation write. No separate export command.

8. **Sector breadth** is out of scope for v1 (applied after signal assessment in
   production). Not encoded in `screener.accum.score_weights`. ML adapters must
   not retain the hand-mirror `+10 when present` production claim; sector-breadth
   counterfactuals are `BLOCKED_POLICY`.

9. **Historical cohorts** without snapshots remain raw corpus but are ineligible
   for verified production-policy challenges. No backfill of fabricated
   snapshots onto old rows.

10. **ML consumer** (sibling task): verified snapshot + separate
    `ChallengePolicyAdapter`; `BLOCKED_POLICY` on mismatch; no static-production
    fallback after cutover; golden conformance before counterfactual ablation.

## Consequences

- Fresh accumulation capture/backfill always materializes verified policy rows
  for the active lean compatibility cohort.
- `ml-saham` can stop treating packaged policy JSON as production authority once
  a fresh cohort exists and the consumer task lands.
- Live Signal/Risk/TradeSetup Actions are unchanged (`NON_SEMANTIC` for engine
  behavior).
- Adding a seventh production policy or another purpose requires a new task and
  contract amendment.

## Related

- ADR-042 deterministic champion and optional model challengers
- ADR-049 database-owned learning pipeline clean break
- ADR-056 accum corpus session observation
- ADR-057 evidence / diagnostic / corpus vocabulary
- `BOUNDARY.md` policy-snapshot ownership
- Sibling `ml-saham` ADR-002 ideal challenge system
