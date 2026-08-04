# Superseded — Screen-Rejected Controls And PIT Universe

Status: `SUPERSEDED` (2026-07-31)

This combined task is retained only as a historical pointer. Do not implement
it.

It mixed two independent product questions and relied on assumptions that no
longer describe the current corpus accurately:

- `screen_result="pass"` does not mean the corpus contains only positive
  outcomes or live-screen winners. Capture neutralizes score/structural gates
  and records the PIT-tradable, **broker-observable** population. It is
  negative-inclusive by forward outcome, but it is not a census of every
  tradable ticker because a ticker without a usable broker-summary row is not
  evaluated.
- A control population is not defined by the presence of any
  `screen_result != "pass"` row. Recall/filter-value authority requires a
  complete, explicit denominator and compatible policy/input identities.
- Point-in-time tradable membership landed in commit `380afd87`. The remaining
  universe gap is narrower: authoritative historical index/eligible membership,
  including names absent from today's named universe or predating local
  ingestion.
- ADR-056 observations already carry full per-window engine packs and serialize
  cached PIT fundamentals when available. Filter replay must audit those inputs
  and their explicit missing states before proposing another capture mode.

## Replacement Tasks

- [`parked_screen_filter_replay_contract.md`](parked_screen_filter_replay_contract.md) (same `tasks/done/`; COMPLETED)
  — READY audit of corpus sufficiency for deterministic hard-filter replay.
  Accum policy evaluation remains owned by `ml-saham`; its threshold grid is a
  separate decision checkpoint.
- [`parked_historical_eligible_universe_membership.md`](parked_historical_eligible_universe_membership.md)
  — consumer-gated historical index/eligible-membership source and denominator
  contract.

## Binding Boundaries

- Ordinary `screen` and `analyze` commands remain read-only.
- Canonical capture remains a dedicated application use case.
- Do not add a second filtered capture mode until a named consumer, policy, and
  missing PIT input prove it is necessary.
- Do not treat candle-presence `@pit` membership as historical index/eligible
  membership.
- Any meaning-changing corpus revision is a clean break under
  `AGENT_QUICKSTART.md`.

## Supersession Record

- Superseded date: 2026-07-31
- PIT tradable-universe implementation: `380afd87`
- Replacement tasks:
  - `tasks/done/parked_screen_filter_replay_contract.md`
  - `tasks/backlog/parked_historical_eligible_universe_membership.md`
