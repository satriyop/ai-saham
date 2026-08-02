# ADR-062: Retire accumulation group-breadth production bonus

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted

**Date:** 2026-08-02

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

1. Production screen, capture, backfill, cron, and alternate composition roots
   must not inject `idx_groups` into accumulation scoring.
2. The current applier, config keys, request/DTO fields, fingerprints, payload
   fields, and isolated tests are removal debt, not a latent feature flag.
3. `production_policy_snapshot.v2` remains the exact seven-row closed set.
   There is no breadth policy row, snapshot v3, lean compatibility v3, or
   historical snapshot backfill from this decision.
4. ml-saham must evaluate the production baseline without a breadth bonus. It
   must not reconstruct the dormant rule from payload/config remnants.
5. Existing observations remain immutable historical facts. Residual zero/null
   fields do not prove that breadth was evaluated, unavailable, or authoritative.

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

- permission to set `idx_groups` in an accumulation production factory;
- permission to relabel the current conglomerate map as sector membership;
- permission to flip or reuse the dormant fields as diagnostic evidence;
- permission to create a snapshot-v3 placeholder or eighth policy row;
- permission to reinterpret old null/zero fields or rebuild historical rows;
- a claim that changing only `enabled` is harmless to compatibility identity.

## Consequences

- Current production output remains unchanged.
- Snapshot v2 and current lean compatibility remain unchanged.
- The active-looking configuration is corrected through a scoped clean-removal
  task rather than a value flip that creates misleading identity churn.
- A future diagnostic begins from explicit provenance instead of inheriting the
  retired score mutation.
- Until removal lands, production non-wiring tests are mandatory fail-closed
  guards.

## Verification and implementation pointers

- `config/accumulation_screener.yaml`
- `config/idx_groups.yaml`
- `src/application/services/accumulation_sector_breadth.py`
- `src/application/use_case/accumulation_screen_use_case.py`
- `src/application/services/accumulation_policy_snapshot_payloads.py`
- `tests/adapters/composition/test_sector_breadth_not_in_production_wiring.py`
- `tasks/backlog/retire_accum_group_breadth_score_bonus.md`
