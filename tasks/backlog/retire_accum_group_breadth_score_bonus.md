# Retire Accum Group-Breadth Score Bonus

Status: `IN_PROGRESS` (implementation)

Authority: [ADR-062](../../docs/adr/ADR-062-retire-accum-group-breadth-production-bonus.md)

## 1. Task Metadata

- Task title: Remove the retired accumulation group-breadth score bonus
- Task type: Refactor / clean break
- Priority: High
- Primary owner: `ai-saham`
- Semantic classification (locked):

| Surface | Classification |
|---------|----------------|
| Live Accum / Signal / Risk / Action / order | `NON_SEMANTIC` — production never applied the bonus |
| Material config path set + request config-hash fields | `CONFIG_MATERIAL` — new observation identity only; historical rows unchanged |
| Candidate payload keys drop on new producers | no `OBSERVATION_SCHEMA` bump — optional residual keys; old rows immutable |
| Semantic engine version | unchanged |
| Snapshot / lean contract IDs | unchanged (`production_policy_snapshot.v2`, lean v2) |

## 2. Chosen Decision

Remove the dormant conglomerate-group breadth score mutation and all
active-looking production-policy surfaces. Implement this option only.

Production currently supplies no group mapping and skips the applier. The
implementation must preserve that exact output while making the contract
truthful. Do not activate, replace, or redesign breadth in this task.

## 3. Locked Compatibility Decisions (pre-edit)

1. **Reject vs ignore:** presence of `sector_breadth` in accumulation/swing
   policy YAML is a **hard load error** (not silent ignore).
2. **`idx_groups` scope:** remove only the accumulation-scoring seam
   (`AccumulationScreenUseCase` / factory params / applier). Keep
   `config/idx_groups.yaml`, `GroupMappingService`, and non-scoring consumers
   (e.g. sentiment display).
3. **Snapshot exclusion:** keep `sector_breadth` in `explicitly_excluded` with
   reason rewritten to ADR-062 retirement (seven-row v2 closed set unchanged).
4. **Research:** honesty updates in-repo; panel may still *read* residual
   historical keys. Factor card is offline-only and non-authoritative.
5. **ml-saham:** no PolicySpec / baseline reconstruction; companion copy only.

### Inventory (producers / consumers removed)

| Surface | Action |
|---------|--------|
| `AccumulationSectorBreadthApplier` | deleted |
| `AccumulationScreenUseCase` `idx_groups` / applier apply | removed |
| Factory `idx_groups` param | removed |
| `SwingPolicyConfig` four fields | removed |
| `AccumulationScreenRequest` four fields | removed |
| `AccumulationCandidate` pct/bonus + `to_dict` | removed |
| Observation request builder / log trade transport | removed |
| `_CONFIG_HASH_FIELDS` four knobs | removed |
| Material config four paths | removed |
| YAML `sector_breadth` block | removed; retired comment left |
| Composer/loader | hard-reject retired block |
| Snapshot exclusion prose | ADR-062 reason |
| Isolated applier tests | replaced by clean-break tests |

### Unrelated (must remain)

- Sector-context evidence `sector_breadth` / `sc_sector_breadth`
- Regime evidence `sector_breadth`
- `config/idx_groups.yaml` + group mapping service
- Research panel optional historical residual fields (read-only)

## 4. Required Dependency Order

1. Inventory every producer and consumer of the four `sector_breadth_*` policy
   fields and the two candidate payload fields. **Done (above).**
2. Prove production composition never supplies `idx_groups` and capture golden
   representative output before edits. **Done** — production skip is established;
   golden equivalence tests lock no score mutation surface.
3. Compatibility blast radius recorded (above). Historical rows unchanged.
4. Remove the score mutation and application wiring surface.
5. Remove typed config/request and observation-transport remnants.
6. Remove or replace misleading YAML/comments and isolated tests.
7. Re-run production-output equivalence, snapshot closed-set, observation
   round-trip, full test, and lint gates.

## 5. Scope

At minimum inspect:

- `config/accumulation_screener.yaml` and its loader/composer;
- `SwingPolicyConfig` and `AccumulationScreenRequest`;
- `SignalObservationRequestBuilder` and observation fingerprints;
- accumulation logging/capture/backfill request transport;
- `AccumulationScreenUseCase` constructor, mapping, and apply order;
- `AccumulationSectorBreadthApplier`;
- candidate serialization fields `sector_breadth_pct` and
  `sector_breadth_bonus`;
- every production composition root and relevant fixture;
- ADR-059 snapshot exclusion payload and closed-set tests;
- ml-saham readers of any removed serialized fields, read-only only.

## 6. Do Not Interpret This As

- Do not inject `idx_groups` into accumulation scoring.
- Do not replace conglomerate groups with sectors.
- Do not keep aliases, fallback fields, dual serialization, ignored config
  keys, or a no-op applier for compatibility.
- Do not create or reserve snapshot v3, lean compatibility v3, migration 4, or
  an eighth snapshot row.
- Do not rewrite historical observations, snapshots, or labels.
- Do not turn the removed score rule into diagnostic corpus evidence.
- Do not let ml-saham invent or mirror a policy absent from production.
- Do not delete `idx_groups.yaml` / group mapping used outside Accum scoring.

## 7. Layer Plan

```text
Layer plan:
- Domain: remove retired material-config path entries only
- Application: remove applier, policy/request fields, and workflow transport
- Infrastructure: remove YAML loading/persistence mapping remnants; hard-reject
- Adapter: preserve thin production composition (no new wiring)
```

No new dependency, provider, UI, CLI command, database write, or AI behavior.

## 8. End-to-End Invariants

- The same production inputs produce the same Accum, Signal, Risk, Action,
  candidate inclusion, and ordering before and after removal.
- Production composition has no `idx_groups` accumulation-scoring seam.
- Snapshot v2 remains exactly seven verified rows and excludes breadth.
- New canonical producers cannot emit or accept the retired config/request
  identity. Historical rows remain immutable raw facts and gain no authority.
- Unrelated sector-context evidence remains intact; it is a different concept.
- ml-saham continues to verify/challenge the real seven-policy baseline only.

## 9. Required Tests

- Negative production-composition test: no group map or breadth applier.
- Golden production-output equivalence (no score mutation surface).
- Typed config hard rejection of retired YAML keys.
- Observation serialization: new `to_dict` omits retired keys.
- Snapshot test: exact seven v2 IDs, no breadth ID, no v3 constants.
- Regression: sector-context evidence contract untouched.
- `git diff --check`, focused + full suite, whole-repo Ruff.

## 10. Close Criteria

- [x] Pre-edit inventory and compatibility decision are recorded in this task.
- [x] Every retired producer/consumer surface is removed in dependency order.
- [x] No forbidden alias, fallback, no-op transport, or production wiring remains.
- [x] Production-output equivalence is proven independently.
- [ ] Snapshot v2 and unrelated sector-context contracts remain green.
- [ ] Focused, architecture, full-suite, diff, and Ruff gates pass after final edits.
- [ ] ai-saham changes are committed with a scoped commit.
- [ ] ml-saham companion references are updated without adding a breadth baseline.
