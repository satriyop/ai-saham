# ADR-049: Database-Owned Learning Pipeline Clean Break

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted
**Date:** 2026-07-27
**Supersedes:** [ADR-023](ADR-023-codebase-directory-and-use-case-file-naming-standards.md)
for learning-artifact persistence; amends ADR-027, ADR-033, ADR-041, ADR-042,
and ADR-048.

## Context

Learning observations, outcomes, pre-open tracks, swing reviews, proposed YAML
patches, and application history were split across SQLite, JSON, JSONL, and
Markdown artifacts. Their identities and immutability rules differed, and some
evaluation paths could reread source tracks or transport untyped dictionaries.
That fragmentation made cohort lineage, out-of-sample isolation, and policy
application auditing difficult to prove.

## Decision

SQLite is the sole owner of learning observations, track snapshots, labels,
evaluations, policy proposals, paired validations, and application audit
records. Production scoring policy remains source-controlled YAML. SQLite is
never a runtime configuration fallback.

This is a clean break:

- no migration, compatibility reader, alias, dual write, fallback, or
  historical reinterpretation;
- the former observation and label tables and quarantines are permanently
  removed;
- opening track files and swing tuning review/patch/application files are
  deleted without import;
- learning artifacts are append-only and linked with restrictive foreign keys;
- every repository connection enables SQLite foreign-key enforcement.

The seven canonical tables are:

1. `learning_observations`
2. `learning_track_snapshots`
3. `learning_outcome_labels`
4. `learning_evaluations`
5. `learning_policy_proposals`
6. `learning_policy_validations`
7. `learning_policy_applications`

## Contracts

All contracts use schema version `1`.

Purposes:

- `ACCUMULATION_DISCOVERY`
- `PRE_OPEN_AUCTION_DIRECTION`
- `SWING_TRADE_SETUP`

Evaluation methods:

- `FORWARD_OUTCOME_COHORT`
- `SESSION_OUTCOME_COHORT`
- `PORTFOLIO_WALK_FORWARD`

Outcome bases:

- `PRICE_PATH_ONLY`
- `SIMULATED_NET_EXECUTION`
- `REALIZED_TRADE` is reserved and has no active producer.

Readiness:

- `INELIGIBLE`
- `DESCRIPTIVE_READY`
- `OOS_DIAGNOSTIC_READY`
- `POLICY_REVIEW_ELIGIBLE`

Removed identities, including `SIGNAL_COHORT`, `raw_market`, and `executable`,
are invalid at every typed producer and consumer boundary.

Canonical contract IDs:

| Artifact | Contract ID |
|---|---|
| Accumulation observation | `learning_observation.accumulation_discovery.v1` |
| Pre-open observation | `learning_observation.pre_open_auction_direction.v1` |
| Tactical label | `price_path.tactical_3d.v1` |
| Swing label | `price_path.swing_10d.v1` |
| Accumulation label | `price_path.accum_20d.v1` |
| Pre-open label | `price_path.open_30m.v1` |
| Accumulation evaluation | `forward_outcome_cohort.v1` |
| Pre-open evaluation | `session_outcome_cohort.v1` |
| Swing evaluation | `portfolio_walk_forward.v1` |
| Swing proposal | `swing_policy_proposal.v1` |
| Swing validation | `paired_oos_swing_policy_validation.v1` |
| YAML application | `yaml_policy_application.v1` |

Stable SHA-256 identifiers are derived from canonical JSON identity payloads.
`captured_at` and other operational timestamps are metadata and never
relational identity. Immutable insertion has exactly two outcomes:

- matching identifier and digest is an idempotent no-op;
- matching identifier and different digest is a hard contract error.

No artifact is overwritten or silently updated.

## Workflow ownership

Domain owns pure contracts, identity, digest, and invariants. Application use
cases own capture, label generation, compatible-cohort evaluation, proposal
generation, paired validation, readiness, and guarded application workflow.
Infrastructure implements SQLite and YAML/filesystem ports. Adapters only parse,
wire, call, and render.

Accumulation persists every evaluated pass or rejection with the exact
point-in-time evidence, provenance, availability, signal, risk, `TradeSetup`,
and funnel result. Its forward labels are `PRICE_PATH_ONLY`; such evaluations
cannot create an applicable production-policy proposal.

Pre-open capture remains NCP locked. Tracks are stored as snapshots linked to
the observation. The open-30-minute label is generated once and persisted.
Cohort evaluation reads persisted labels only and never rereads tracks or
recomputes outcomes. A single session is descriptive. AI prompt and tuning
paths are retired.

Swing review is chronological and staged:

1. freeze a point-in-time dataset and current YAML hash;
2. split in-sample and untouched out-of-sample populations;
3. evaluate the baseline in-sample;
4. generate and freeze a proposal from in-sample attribution only;
5. evaluate baseline and proposal on the identical OOS population;
6. persist both evaluations and a paired deterministic validation;
7. grant `POLICY_REVIEW_ELIGIBLE` only when every guard passes;
8. require explicit human `--yes` application;
9. verify PASS, current config hash, clean target files, unused proposal, exact
   changes, and post-write reread before persisting the application audit.

## Public CLI

Learning workflows are contextual:

```text
saham research accumulation capture|backfill|labels|evaluate|replay|status
saham research pre-open capture|track|labels|evaluate|status
saham trade swing backtest|tune|review|validate|apply|status
```

`research signal`, pre-open `grade|prompt|tune`, flat swing tuning commands,
patch/journal/file arguments, `--no-persist`, `--export-patch`, and persisted
JSON/JSONL/Markdown learning outputs are retired. `--format json` is stdout
only.

## Invariants and consequences

- Live signal and risk arithmetic and `TradeSetup` composition do not change.
- Policy proposal generation cannot inspect OOS results.
- Baseline and proposed policy validations bind an identical OOS population.
- `PRICE_PATH_ONLY` readiness cannot exceed `OOS_DIAGNOSTIC_READY`.
- Validations compare net return, profit factor, average return, drawdown
  regression, trade count, regime stability, authority coverage, and setup
  readiness.
- YAML application is explicit, single-use, hash-bound, and reread verified.
- Active learning rows use `ON DELETE RESTRICT`; clean-break deletion applies
  only to the explicitly retired schema and files.

## Non-goals

- No change to canonical scoring, risk, setup, sizing, or execution arithmetic.
- No ML or AI authority, evidence promotion, or automatic configuration change.
- No import or reinterpretation of historical learning artifacts.
- No deletion of unrelated trade journals, market data, or source caches.

