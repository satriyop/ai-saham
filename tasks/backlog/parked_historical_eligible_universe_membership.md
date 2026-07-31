# Parked — Historical Eligible-Universe Membership

Status: `PARKED`

Source: supersedes the historical-universe half of
`parked_screen_rejected_controls_and_universe.md`.

## Task Metadata

- Task type: Spike / Research before Feature
- Priority: Low until a named consumer requires historical eligibility rather
  than PIT tradability
- Semantic classification: `NON_SEMANTIC` for source research. Reclassify the
  implementation after the exact persisted contract is chosen; a changed corpus
  population will require a clean-break cohort.
- Chosen decision: do not build a membership warehouse speculatively. First
  name the consumer, membership concept, authoritative source, and coverage.
  Implement only the proven concept and date range.

## Activation Trigger

Wake this task only when a named consumer requires one of these claims:

- historical index constituency as of each observation date;
- historical exchange-listed or strategy-eligible membership;
- representation of names removed from today's named universe;
- representation of delisted or long-suspended names outside candle-presence
  membership; or
- correction of survivorship before the local ingestion window.

PIT candle presence, generic research interest, or a desire to remove an honest
limitation note is not enough.

## Current Contract

Commit `380afd87` implemented per-date PIT **tradable** membership:

- `cached@pit` uses board-wide candle activity over the configured trading-session
  window and does not intersect today's cache.
- A named universe uses today's named membership intersected with PIT candle
  activity.
- The response explicitly says this is not historical index/eligible membership
  and that pre-ingestion delistings remain absent.

This corrects forward-going and locally observable tradability bias. It does not
prove historical index constituency, listing eligibility, or membership before
local data exists.

## Problem Statement

The repository has no authoritative source that answers which ticker belonged
to a specific historical index/eligible universe on a given session, including
effective additions/removals, suspensions, delistings, symbol changes, and
pre-ingestion history.

Candle presence cannot answer that question: trading activity and eligibility
are different concepts. A long suspension can remove candles while eligibility
continues; a traded name can be outside a named index.

## Desired Outcome

For one activated membership concept:

- Resolve membership as of each observation session from an authoritative,
  provenance-bound source.
- Preserve effective-from/effective-to semantics without look-ahead.
- Represent eligible-but-unavailable, suspended, delisted, renamed, and
  source-unknown states explicitly.
- Bind the membership source/version and cutoff to the corpus cohort.
- Reconcile every ticker/session denominator state independently from screen
  pass/reject classification.
- Mark unsupported dates or concepts invalid rather than silently falling back
  to current membership or candle presence.

## Source Contract Required Before Coding

The activation proposal must answer:

1. Membership concept: index constituent, exchange listed, or strategy eligible.
2. Source owner and acquisition authority.
3. Publication date versus effective membership date.
4. Point-in-time correction/revision behavior.
5. Coverage start/end and known gaps.
6. Symbol-change, merger, IPO, delisting, and relisting semantics.
7. Suspension semantics: eligible, tradable, or unavailable.
8. Stable source identity and provenance fields.
9. Local storage, idempotency, and audit/reconciliation plan.
10. Behavior when the source is absent or contradictory.

Do not begin an infrastructure implementation until these are resolved.

## Non-Goals

- No replacement of the existing PIT tradable resolver.
- No inference of index membership from candles, price history, today's YAML,
  or today's cache.
- No generic multi-index warehouse without a named consumer.
- No screen-filter replay or `screen_result` changes; see
  `parked_screen_filter_replay_contract.md`.
- No interactive `screen` / `analyze` writes.
- No AI-derived membership authority.

## Architecture Impact

```md
Layer plan:
- Domain: typed membership concept/state and source identity only after the source contract is approved
- Application: per-session membership orchestration, fail-closed validity, and denominator reconciliation
- Infrastructure: authoritative source adapter and local PIT repository for the activated concept only
- Adapter: thin import/backfill/audit command if required; no membership policy
- Documentation/governance: source limitations, supported claims, and corpus clean-break record
```

- New dependency: Likely yes; must be named before coding.
- Affects determinism: Yes; membership becomes authoritative source data but
  must remain reproducible for the same source snapshot and cutoff.
- Persistence change: Likely yes; exact schema is intentionally undecided until
  the source contract exists.
- AI usage: No AI involved.

## Acceptance Criteria

- [ ] A named consumer and exact membership claim fired the trigger.
- [ ] The source contract above is complete and independently auditable.
- [ ] Per-date fixtures cover addition, removal, IPO, delisting, suspension,
      symbol change, missing source, and planted future membership.
- [ ] Future-published membership cannot affect an earlier observation date.
- [ ] Eligible-but-unavailable names remain in the denominator with a typed state.
- [ ] Unsupported dates fail closed; no current-list or candle-presence fallback.
- [ ] Membership source/version/cutoff participates in corpus compatibility and
      provenance as required by the approved semantic classification.
- [ ] Re-running the same source snapshot is idempotent.
- [ ] Focused tests, data-contract audit, `git diff --check`, architecture tests,
      full suite where required, and the whole-repo Ruff gate pass for Python
      changes.

## Do Not Interpret This As

- Do not call `@pit` candle activity historical index membership.
- Do not treat absence of a candle as proof of index removal or delisting.
- Do not erase the current survivorship limitation until the activated claim and
  date range are actually supported.
- Do not build multiple membership concepts behind one vague `eligible` flag.
- Do not let an adapter choose membership or fallback policy.

## Required Reading When Activated

- `AGENT_QUICKSTART.md`, `AGENTS.md`, `TASK_TEMPLATE.md`
- `tasks/backlog/pit_tradable_universe_backfill.md`
- Current PIT tradable resolver, backfill use case, corpus identity resolver,
  and data-audit commands
- ADR-056 and the accepted learning/corpus boundary in `BOUNDARY.md`
