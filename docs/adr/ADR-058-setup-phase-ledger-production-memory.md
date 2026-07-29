# ADR-058: Setup phase ledger as production sequence memory

## Status

Accepted — 2026-07-29

## Context

Setup-phase sequence validation (`previous_phases`) previously mined
`learning_observations` via full-table JSON load per ticker. As the corpus grew,
`screen accum` / TUI open became multi-minute operations. Observations are a
**research corpus** (ADR-057); they are the wrong hot path for live sequence
checks.

## Decision

1. Store closed-session phase facts in `setup_phase_ledger` (ticker, as_of_date,
   phase, setup_family, source_workflow).
2. **Read** sequence history only from the ledger (`as_of_date < snapshot`).
3. **Write** from the shared assess path (canonical window 7 only); last-wins
   for the same natural key; unresolved primary stored as empty family for
   generic-screen matching.
4. Learning observations may still embed phase in fingerprints; they are **not**
   sequence authority.
5. One-shot backfill: `saham research accum backfill-phase-ledger`.

## Consequences

- Screen/TUI history I/O scales with per-ticker ledger rows, not corpus size.
- Capture before cron remains valid (capture runs assess and can mint ledger).
- Family grain is primary (or generic empty); multi-family rows are out of scope.

## Related

- ADR-056 session observations
- ADR-057 evidence vs diagnostic vs corpus vocabulary
