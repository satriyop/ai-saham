# Accum Action / Setup-Readiness Absence — Root Cause (P3)

**Date:** 2026-08-01  
**Scope:** ACCUMULATION_DISCOVERY session observations on maintainer DB  
**Task:** `tasks/backlog/grow_snapshot_bound_accum_challenge_corpus.md` P3  
**Method:** code-path trace (assessor → fingerprint payload → SQLite payload) + measured
counts from frozen `decision_payload_json` (no recompute of today’s Action/readiness).

## Measured denominators (maintainer DB, 2026-08-01)

| Cohort (prefix) | n | Snapshots | Action ENTER | Action other | Readiness present | Readiness null |
|-----------------|---|-----------|--------------|--------------|-------------------|----------------|
| `sha256:005363…` (legacy) | 1890 | 0 | 8 | 1882 | 86 | 1804 |
| `sha256:58988d…` (partial v1-era) | 349 | 6 | 0 | 349 | 26 | 323 |
| `sha256:8ba8fc…` (active v2) | 304 | 7 | 0 | 304 | 11 | 293 |

### Active v2 cohort (`sha256:8ba8fc…`, n=304) — absence causes

| Cause | Count | % of n |
|-------|------:|-------:|
| `signal.setup_readiness` JSON null **and** `setup_family_result.primary_setup_family is None` | 293 | 96.4% |
| Typed readiness present (`INELIGIBLE` 6 + `UNAVAILABLE` 5) | 11 | 3.6% |
| Missing canonical window pack / signal object | 0 | 0% |
| Fingerprint has status while signal readiness null (transport split) | 0 | 0% |
| Action null | 0 | 0% |

Present readiness breakdown (11):

- `INELIGIBLE` with family breakout/pullback and failed phase requirements: 6  
- `UNAVAILABLE` with `missing_required_inputs=["setup_evidence"]`: 5  

Action distribution (304): BLOCKED_STRUCTURAL 204, BLOCKED_EXECUTION 38, AVOID 32, WATCH 30, ENTER 0.

## Production call path (authority)

1. `AccumulationCandidateSignalAssessor` resolves `setup_family_result` once, detects
   `setup_phase`, builds optional `canonical_evidence` (setup always `None` on this
   screen path — setup evidence is not fabricated).
2. `ScreenAssessmentPipeline.evaluate_signal` → SignalEngine →
   `AssessSignalEvidenceUseCase` → `SetupPhaseReadinessEvaluator.evaluate(...)`.
3. Evaluator rule 1 (locked): **missing/blank `setup_family` → `None`** (flow-only
   assessment; not an error).
4. `build_candidate_observation_payload` serializes
   `signal.setup_readiness.to_dict()` when non-null, else explicit JSON `null`.
5. Session payload stores that pack under `features_by_window["7"]` (canonical window).
6. Status / research readers must read the frozen payload only (P0 extractor).

## Conclusion

| Question | Answer |
|----------|--------|
| Is an already-computed typed readiness **lost in transport**? | **No.** When the evaluator returns a `SetupPhaseReadiness`, payload + fingerprint both retain it (11/304). When family is absent, evaluator returns `None` and transport stores `null` faithfully. |
| Why is readiness sparse? | **Domain contract:** `primary_setup_family is None` on nearly all LQ45 screen rows → readiness intentionally `None`. Not a serializer bug. |
| Why zero ENTER on active v2? | **Legitimate production Action stack** (structural/execution blocks, WATCH/AVOID). Action is always present on the frozen trade_setup; density is policy/population, not transport. |
| Transport fix in this task? | **None.** No lineage repair required. |
| Forbidden “fixes” | Synthesize READY, coerce `None`→class, duplicate adapter schema, activate named-setup capture for density, change live Action policy. |

## Follow-ups (out of this task)

- Separate task if product wants denser family assignment or setup evidence on the
  ACCUM discovery path (would be semantic/config, not observation schema polish).
- ml-saham C4 remains blocked until class support and folds exist under protocol.

## Verification hooks

- `tests/application/services/test_accumulation_action_readiness_transport.py`  
  — lineage: computed readiness survives payload; missing family stays null;  
  status extractors never recompute Action/readiness.
