# ADR-062: Retire accumulation group-breadth production bonus

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted

**Date:** 2026-08-02

**Amended:** 2026-08-02 — identity, schema-12, targeted YAML rejection,
compatibility-fork, research/ml-saham companion scope, and golden gate locked.

**Amends:** [ADR-059](ADR-059-production-policy-snapshot-for-ml-challenges.md)

**Depends on:** [ADR-030](ADR-030-accumulation-screener-evidence-split.md),
[ADR-042](ADR-042-deterministic-champion-and-optional-model-challengers.md),
[ADR-056](ADR-056-accum-corpus-session-observation-and-accum-path-labels.md),
[ADR-057](ADR-057-evidence-diagnostic-evidence-corpus-vocabulary.md), and
[ADR-059](ADR-059-production-policy-snapshot-for-ml-challenges.md)

**Removal task:**
[`tasks/backlog/retire_accum_group_breadth_score_bonus.md`](../../tasks/backlog/retire_accum_group_breadth_score_bonus.md)

## Context

The accumulation screener carries configuration fields named
`sector_breadth`, and `AccumulationSectorBreadthApplier` can add points when a
threshold of related candidates has positive `net_buy_ratio`. Its mapping comes
from `config/idx_groups.yaml`, which describes conglomerate/business groups,
not an authoritative IDX sector taxonomy or point-in-time membership source.

Current production screen and corpus composition do not inject this mapping.
The use case therefore has an empty ticker-to-group map and skips the applier.
The configured `enabled: true` value, transport fields, isolated unit tests,
and dormant implementation do not establish production behavior or authority.

Silently wiring the mapping would change accumulation ranking after signal
assessment without recomputing that assessment. It could alter downstream
candidate selection while the active seven-row `production_policy_snapshot.v2`
correctly excludes the bonus. Treating the existing static mapping as corpus
evidence would also invent membership provenance and historical meaning.

## Decision

Retire the current conglomerate-group breadth **score bonus** from production
policy. Implement this option only.

1. Do not inject `idx_groups` into any accumulation screen, capture, backfill,
   cron, briefing, or alternate accumulation-scoring path.
2. The current applier, config keys, request/DTO fields, fingerprints, payload
   fields, and isolated tests are removal debt, not a latent feature flag.
3. `production_policy_snapshot.v2` remains the exact seven-row closed set.
   There is no breadth policy row, snapshot v3, lean compatibility v3, or
   historical snapshot backfill from this decision.
4. ml-saham must evaluate the production baseline without a breadth bonus. It
   must not reconstruct the dormant rule from payload/config remnants.
5. Existing observations remain immutable historical facts. Residual zero/null
   fields do not prove that breadth was evaluated, unavailable, or authoritative.

### Identity and schema lock (amendment)

Live Accum, Signal, Risk, Action, and ordering stay **semantically unchanged**
and must be proven by an offline golden fixture. The clean-break still **forks
compatibility identity** because material config-hash inputs and candidate
payload shape change.

| Surface | Classification |
|---|---|
| Live Accum, Signal, Risk, Action, and ordering | `NON_SEMANTIC`, proven by offline golden |
| Removed config paths and config-hash inputs | `CONFIG_MATERIAL` |
| Removed candidate payload fields | `OBSERVATION_SCHEMA` |
| Semantic engine version | Unchanged |
| SQLite learning schema | Unchanged |
| Snapshot contract | Remains `production_policy_snapshot.v2`, seven rows |
| Lean contract ID | Remains `lean_accumulation_compatibility.v2` |
| Compatibility value | Must fork |

Required version action:

- Bump `ACCUMULATION_OBSERVATION_PAYLOAD_SCHEMA_VERSION` from `11` to `12`.
- The alias `CANDIDATE_OBSERVATION_SCHEMA_VERSION` follows it.
- Existing schema-11 observations remain immutable historical corpus.
- New schema-12 capture starts a **new** `compatibility_id` cohort.
- No semantic-engine bump, snapshot v3, lean-v3 contract ID, or SQLite
  migration.

**“Lean v2 unchanged” means the contract ID remains
`lean_accumulation_compatibility.v2`, not that the compatibility hash remains
equal.** Removing the four material config fields and changing the payload shape
produces a new compatibility value even when live scoring is identical.

Snapshot exclusion prose remains an explicit closed-set exclusion, corrected to:

> Retired from production policy by ADR-062; never part of the production
> accumulation baseline.

Existing snapshot rows remain unchanged. New schema-12 cohorts receive seven
snapshot-v2 rows under their new compatibility ID.

### Targeted YAML rejection (option C)

Delete `accumulation_screener.sector_breadth` from the shipped YAML.

The accumulation/swing policy composition path must reject that **exact**
retired section. Direct typed construction with retired keyword arguments must
fail naturally.

Do not:

- make every unrelated YAML loader globally strict; or
- silently ignore private configurations that still contain the retired section.

### Scope of `idx_groups`

Removal is limited to accumulation breadth scoring.

**Keep**

- `config/idx_groups.yaml`
- `GroupMappingService`
- sentiment/group display consumers
- unrelated conglomerate-context behavior

**Remove**

- `AccumulationScreenUseCase.idx_groups`
- corresponding factory parameters
- ticker-to-group accumulation mapping
- `AccumulationSectorBreadthApplier`
- all accumulation request/config/fingerprint/payload transport for the bonus

End-state invariant:

> No `idx_groups` constructor/factory parameter, no ticker-to-group state, no
> breadth applier type, and no accumulation production composition reference.

Tests must assert **absence**, not that a default remains `None`.

### Research and ml-saham companions (mandatory)

Active research consumers are in scope for the removal program:

- delete or retire `research/scripts/factor_card_sector_breadth.py`;
- remove active README commands and feeder claims;
- remove `sector_breadth_pct` and `sector_breadth_bonus` from
  `research/lab/panel.py`;
- update active factor-inventory documentation;
- retain old generated artifacts only as clearly historical, non-executable
  records;
- protect the unrelated `sc_sector_breadth` sector-context diagnostic.

ml-saham executable consumers are **mandatory** companions, not optional
documentation follow-up:

- remove candidate-panel aliases for `sector_breadth_bonus` /
  `sector_breadth_pct` that model the retired Accum score bonus;
- remove static/reference policy remnants that model the `+10` bonus;
- bump any affected panel or adapter identity as required by ml-saham contracts;
- preserve historical artifacts without granting them production eligibility;
- protect unrelated diagnostic paths such as sector-context `peer_breadth` /
  `sc_sector_breadth` consumers that are not the retired Accum bonus.

### Golden equivalence gate

Use an offline deterministic synthetic fixture—not a live LQ45 run—as the
reproducibility gate for live scoring equivalence. Freeze ordered tickers,
inclusion/exclusion, Accum/Signal/Risk/Action/readiness projections, and final
serialized projection excluding nondeterministic timestamps. A real dated screen
may be supplementary evidence only.

### Diagnostic exploration is a different future contract

This decision does not reject researching whether group or sector participation
has predictive value. A future diagnostic must start as a new, accurately named
contract and must define:

- whether the concept is sector, conglomerate group, or another taxonomy;
- a named membership authority, revision identity, effective dates, and PIT
  lookup semantics;
- overlap, denominator, minimum support, missing, partial, and conflicting
  membership behavior;
- exact observation provenance and immutable payload identity;
- collection boundaries that cannot affect score, Signal, Risk, TradeSetup,
  Action, candidate inclusion, or ordering.

Only ai-saham may write that corpus diagnostic. ml-saham may challenge it
offline after the producer contract exists. Out-of-sample value does not
automatically promote it; production activation would require a new ADR,
semantic/config versioning, complete composition wiring, snapshot decision,
and human approval.

## Do Not Interpret This As

- permission to set `idx_groups` in any accumulation-scoring production path;
- permission to relabel the current conglomerate map as sector membership;
- permission to flip or reuse the dormant fields as diagnostic evidence;
- permission to create a snapshot-v3 placeholder or eighth policy row;
- permission to reinterpret old null/zero fields or rebuild historical rows;
- permission to claim schema-11 and schema-12 observations share one
  compatibility cohort;
- a claim that “lean v2 unchanged” means compatibility hashes stay equal;
- a claim that changing only `enabled` is harmless to compatibility identity.

## Consequences

- Current **live** production scoring remains unchanged and golden-proven.
- Snapshot contract ID/shape remain v2 / seven rows; snapshot exclusion prose
  is corrected, not expanded into a breadth baseline.
- Lean **contract ID** remains v2; **compatibility values fork** for schema-12
  capture.
- The active-looking configuration is corrected through a scoped clean-removal
  task rather than a value flip that creates misleading identity churn.
- A future diagnostic begins from explicit provenance instead of inheriting the
  retired score mutation.
- Until removal lands, production non-wiring tests are mandatory fail-closed
  guards, and post-removal tests must assert absence of the accumulation
  breadth seam.

## Verification and implementation pointers

- `config/accumulation_screener.yaml`
- `config/idx_groups.yaml` (kept; not an accumulation score input)
- `src/application/services/accumulation_sector_breadth.py`
- `src/application/use_case/accumulation_screen_use_case.py`
- `src/application/services/accumulation_policy_snapshot_payloads.py`
- `src/domain/value_objects/signal_artifact_schema.py` (schema 11 → 12)
- `src/domain/value_objects/signal_semantic_contract.py` (config-hash paths)
- `tests/adapters/composition/test_sector_breadth_not_in_production_wiring.py`
- `tasks/backlog/retire_accum_group_breadth_score_bonus.md`
- ml-saham: challenge panel aliases, static/reference policy remnants, and
  historical-artifact non-eligibility for the retired bonus
