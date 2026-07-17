# ADR-028: IDX Market Microstructure Rules

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — implemented scope clarified
**Date:** 2026-06-24
**Current implementation:** The binding implemented scope is IDX tick-size rounding and the regular-market Rp50 price floor. Other microstructure ideas require separate evidence, implementation, tests, and an ADR amendment before becoming authoritative.

## Decision

IDX exchange constraints that affect validity of a price or order assumption
must be deterministic domain/application policy, never adapter heuristics.

Current binding rules:

1. Computed entry, stop, and target prices use IDX tick-size rules through
   `src/domain/value_objects/tick_size.py` and the consuming application service.
2. The Rp50 regular-market floor is enforced as defined by ADR-022.

## Non-authoritative proposals

Auto-rejection proximity, issuer-specific foreign ownership caps, numeric bandar
thresholds, and T+2-derived risk heuristics are not accepted current rules.
They must not be implemented merely because they appeared in an earlier version
of this ADR. Each needs a verified data source, precise effective-date semantics,
deterministic policy, replay-safe evidence, tests, and an explicit decision.

## Rationale

Exchange mechanics can change and some constraints vary by instrument or board.
Keeping only verified, implemented rules in the active ADR prevents plausible
but unsupported IDX heuristics from entering production logic.
