# ADR-069: Purpose-specific diagnostic producer identity

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — implemented 2026-08-08 (RC-01B); active observation
binding moved cleanly from schema 14 to schema 15 when structural-filter
provenance was added. Schema 14 remains immutable historical material.

**Amends:** [ADR-056](ADR-056-accum-corpus-session-observation-and-accum-path-labels.md),
[ADR-057](ADR-057-evidence-diagnostic-evidence-corpus-vocabulary.md), and
[ADR-068](ADR-068-behavioral-engine-identity-for-accum-cohorts.md)

## Decision

Current accumulation observation schema 15 carries a root
`diagnostic_bindings` closed set for the four shipped challenge diagnostics.
Each purpose-specific compatibility ID binds only the immutable typed producer
snapshots that define that diagnostic. The Action `compatibility_id` remains
exactly ADR-068's behavioral identity and never absorbs diagnostic material.

ai-saham owns and atomically persists `diagnostic_producer_snapshot.v1` rows
before current-schema observations. Snapshot payloads come from the same resolved
typed objects used by live builders; adapters do not reconstruct configuration.
The six producer IDs and four dependency sets are closed in
`diagnostic_producer_identity.py`.

ml-saham must independently verify the selected Action v4/nine snapshot set,
the selected diagnostic binding, every producer snapshot ID and digest, and
the exact schema-15 binding on every counted row. Production diagnostic
commands require both IDs explicitly. Health requires a diagnostic-ID-to-ID
mapping. Missing, historical, mixed, extra, or invalid material yields
`BLOCKED_DIAGNOSTIC_BINDING` for that diagnostic only.

Product extraction is a clean break: exact `features_by_window.7`, exact named
Alpha/Trigger contributions, canonical `sc_sector_breadth`, and frozen
`shared.market_context`. Root aliases, first-present windows, current-table MCE,
and packaged production-control policy fallbacks have no authority.

Diagnostic artifacts use sealed schema 4, are explicitly non-promotable, bind
both identity axes plus spec/extractor content, population, ranges, and source
revisions, and re-resolve upstream authority read-only before current display or
reopen. Diagnostic artifact schema 3 and observation schema 14 or older stay
historical; they are never rewritten or interpreted as current.

## Consequences

- Diagnostic producer changes fork only dependent diagnostic panels.
- Diagnostic output remains report-only and cannot affect Signal, Risk,
  TradeSetup, Action, or promotion.
- New schema-15 rows accumulate prospectively; no historical backfill exists.
