# Retire Accum Group-Breadth Score Bonus

Status: `READY_FOR_IMPLEMENTATION`

Authority: [ADR-062](../../docs/adr/ADR-062-retire-accum-group-breadth-production-bonus.md)

## 1. Task Metadata

- Task title: Remove the retired accumulation group-breadth score bonus
- Task type: Refactor / clean break
- Priority: High
- Primary owner: `ai-saham`
- Semantic classification: begin as `NON_SEMANTIC` only if production-output
  equivalence is proven before editing; compatibility identity and observation
  shape changes must be classified separately from engine behavior.

## 2. Chosen Decision

Remove the dormant conglomerate-group breadth score mutation and all
active-looking production-policy surfaces. Implement this option only.

Production currently supplies no group mapping and skips the applier. The
implementation must preserve that exact output while making the contract
truthful. Do not activate, replace, or redesign breadth in this task.

## 3. Required Dependency Order

1. Inventory every producer and consumer of the four `sector_breadth_*` policy
   fields and the two candidate payload fields.
2. Prove production composition never supplies `idx_groups` and capture golden
   representative output before edits.
3. Determine the exact compatibility blast radius of removing fields from
   material config/fingerprint inputs. Preserve historical rows unchanged; do
   not claim old and new identities are equivalent without proof.
4. Remove the score mutation and application wiring surface.
5. Remove typed config/request and observation-transport remnants in producer
   to consumer order.
6. Remove or replace misleading YAML/comments and isolated tests.
7. Re-run production-output equivalence, snapshot closed-set, observation
   round-trip, full test, and lint gates.

Stop before editing if removal would make an active observation schema invalid,
silently reinterpret stored fields, or require a compatibility alias. Revise
the task with the exact clean-break cohort/version contract first.

## 4. Scope

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

## 5. Do Not Interpret This As

- Do not inject `idx_groups` anywhere.
- Do not replace conglomerate groups with sectors.
- Do not keep aliases, fallback fields, dual serialization, ignored config
  keys, or a no-op applier for compatibility.
- Do not create or reserve snapshot v3, lean compatibility v3, migration 4, or
  an eighth snapshot row.
- Do not rewrite historical observations, snapshots, or labels.
- Do not turn the removed score rule into diagnostic corpus evidence.
- Do not let ml-saham invent or mirror a policy absent from production.

## 6. Layer Plan

```text
Layer plan:
- Domain: remove only retired serialized/domain-facing remnants if inventory proves ownership
- Application: remove applier, policy/request fields, and workflow transport
- Infrastructure: remove YAML loading/persistence mapping remnants; no new I/O
- Adapter: preserve thin production composition and remove obsolete transport only
```

No new dependency, provider, UI, CLI command, database write, or AI behavior.

## 7. End-to-End Invariants

- The same production inputs produce the same Accum, Signal, Risk, Action,
  candidate inclusion, and ordering before and after removal.
- Production composition has no `idx_groups` accumulation-scoring seam.
- Snapshot v2 remains exactly seven verified rows and excludes breadth.
- New canonical producers cannot emit or accept the retired config/request
  identity. Historical rows remain immutable raw facts and gain no authority.
- Unrelated sector-context evidence remains intact; it is a different concept.
- ml-saham continues to verify/challenge the real seven-policy baseline only.

## 8. Required Tests

- Negative production-composition test: no group map or breadth applier can be
  injected into screen, capture, backfill, cron, briefing, or alternate roots.
- Golden production-output equivalence test covering ranking and Action.
- Typed config rejection test for retired keys if strict config loading owns
  that boundary; silent ignore is forbidden.
- Observation serialization/read tests proving the chosen clean-break behavior
  without rewriting historical rows.
- Snapshot test: exact seven v2 IDs, no breadth ID, no v3 constants/artifacts.
- Regression test protecting the unrelated sector-context evidence contract.
- `git diff --check`.
- Focused tests, architecture-boundary tests, and full test suite.
- Whole-repository `ruff check src/ tests/` and
  `ruff format --check src/ tests/` after the final Python edit.

## 9. Close Criteria

- [ ] Pre-edit inventory and compatibility decision are recorded in this task.
- [ ] Every retired producer/consumer surface is removed in dependency order.
- [ ] No forbidden alias, fallback, no-op transport, or production wiring remains.
- [ ] Production-output equivalence is proven independently.
- [ ] Snapshot v2 and unrelated sector-context contracts remain green.
- [ ] Focused, architecture, full-suite, diff, and Ruff gates pass after final edits.
- [ ] ai-saham changes are committed with a scoped commit.
- [ ] ml-saham companion references are updated without adding a breadth baseline.
