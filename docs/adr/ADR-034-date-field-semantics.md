# ADR-034: Date Field Semantics

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)
**Status:** Accepted
**Date:** 2026-06-29
**Current implementation:** Date fields retain their explicit event/as-of semantics; callers must not treat collection time, market date, and effective session as interchangeable.

### Context

The codebase intentionally carries several date names that look similar but
answer different questions. Renaming all of them to one generic field would hide
important anti-lookahead and data provenance rules.

### Decision

Date fields keep these meanings:

| Field | Meaning |
|-------|---------|
| `snapshot_date` | Date of the evaluated point-in-time snapshot or workflow assessment. |
| `session_date` | Exchange trading session date for session-bound market data. |
| `report_date` | Publisher or filing date for reported data, such as IDX shareholding composition. |
| `as_of_date` | Replay/query boundary: only use data available on or before this date. |
| `fetched_at` | Cache/ingestion timestamp, not a market or filing date. |

New domain and application contracts should choose the most specific name from
this table. Do not standardize these fields mechanically unless the data meaning
is actually the same.

### Consequences

Backtest and replay paths can continue to use `as_of_date` as an availability
guard, while source-specific value objects retain their own provenance dates.
This avoids confusing `report_date` with cache freshness and avoids treating
session data as if it were a generic workflow snapshot.
