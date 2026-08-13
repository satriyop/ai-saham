# ADR-049: Database-Owned Learning Pipeline Clean Break

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — amended 2026-07-27 (post-open assess; CLI family clean break)
**Date:** 2026-07-27
**Supersedes:** [ADR-023](ADR-023-codebase-directory-and-use-case-file-naming-standards.md)
for learning-artifact persistence; amends ADR-027, ADR-033, ADR-041, ADR-042,
and ADR-048. Public CLI tree ownership for adapters remains
[ADR-020](ADR-020-cli-adapter-file-naming-convention.md).

### Amendment (post-open assess)

- Post-open assessment of an NCP pre-open plan is **`saham assess pre-open`**
  (read-only over `learning_observations` + linked `learning_track_snapshots`).
- It is **not** a learning outcome label and does **not** write learning tables.
- Paper notebook: `saham trade pre-open log` with exact
  `--observation-id` and `--opening-snapshot-id` (same assess use case).
- Retired: `saham trade confirm`, confirmation sidecars as assess authority,
  and `--type intraday` for this strategy path.

### Amendment (CLI family clean break)

- `research` = corpus / ML feeder only (`pre-open`, `accum`).
- `trade` = human paper notebook only (`pre-open`, `accum`).
- `policy accum` = guarded setup-config lifecycle (was under `trade swing`).
- Clean break: no aliases for `trade log --type`, flat `trade outcome` /
  `trade review`, `trade size`, `trade backtest-intraday`,
  `trade migrate-journal`, or `research accumulation` (name).
- Adapter filenames follow ADR-020 for the new tree (`trade_pre_open_*`,
  `trade_accum_*`, `research_accum_*`, `policy_accum_*`).

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

Canonical contract IDs (ADR-049 clean-break baseline; **accum unit/labels
amended by [ADR-056](ADR-056-accum-corpus-session-observation-and-accum-path-labels.md)**):

| Artifact | Contract ID | Notes |
|---|---|---|
| Accumulation observation | `learning_observation.accumulation_discovery.v2` | **ADR-056** session unit (one obs / ticker / session). Historical `…v1` rows remain immutable. |
| Pre-open observation | `learning_observation.pre_open_auction_direction.v1` | Unchanged by ADR-056 |
| Tactical label | `price_path.tactical_3d.v1` | Non-accum |
| Swing label | `price_path.swing_10d.v1` | Non-accum |
| Accumulation label (primary) | `price_path.accum_10d.v1` | **ADR-056** primary hold path |
| Accumulation label (aux) | `price_path.accum_20d.v1` | **ADR-056** auxiliary only — not the sole accum label |
| Pre-open label | `price_path.open_30m.v1` | Unchanged |
| Accumulation evaluation | `forward_outcome_cohort.v1` | Product-dropped evaluate for accum still governed by later tasks; see live help |
| Pre-open evaluation | `session_outcome_cohort.v1` | Unchanged |
| Swing evaluation | `portfolio_walk_forward.v1` | Unchanged |
| Swing proposal | `swing_policy_proposal.v1` | Unchanged |
| Swing validation | `paired_oos_swing_policy_validation.v1` | Unchanged |
| YAML application | `yaml_policy_application.v1` | Unchanged |

Agents must not treat the pre-056 single-row `accumulation_discovery.v1` +
sole `accum_20d` pair as the current accum learning contract.

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
saham research accum capture|backfill|labels|evaluate|replay|status
saham research pre-open capture|track|labels|evaluate|status
saham policy accum backtest|tune|review|validate|apply|status
saham trade pre-open log|outcome|review
saham trade accum log|review
```

`research` is corpus / ML feeder only. `trade` is the human paper notebook only.
`policy accum` is the guarded setup-config lifecycle (not paper, not corpus).

Retired command paths (clean break, no aliases): `research signal`,
`research accumulation` (use `research accum`), pre-open `grade|prompt|tune`,
`trade log --type …`, flat `trade outcome` / `trade review`, `trade size`,
`trade swing …`, `trade backtest-intraday`, `trade migrate-journal`, legacy
flat swing tuning names under `trade`, patch/journal/file arguments,
`--no-persist`, `--export-patch`, and persisted JSON/JSONL/Markdown learning
outputs. `--format json` is stdout only.

Adapter file ownership for these commands: [ADR-020](ADR-020-cli-adapter-file-naming-convention.md).

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

