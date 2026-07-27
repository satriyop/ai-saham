# ADR-033: Workflow Composition Artifact Boundaries

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)
**Status:** Accepted — amended by [ADR-049](ADR-049-database-owned-learning-pipeline-clean-break.md)
**Date:** 2026-06-28
**Current implementation:** Workflows compose domain/application capabilities; reusable evidence and artifacts cross boundaries through typed values rather than CLI display parsing.

### Context

The CLI now exposes several deterministic workflows that reuse overlapping data:
broker flow, candles, enrichment, signal, risk, market context, setup gates, and
historical replay. Reuse is useful, but a generic workflow wrapper would blur
which output is an actionable verdict and which output is evidence, discovery, a
session confirmation, or a learning artifact.

### Decision

Public commands stay explicit. Shared behavior should be extracted only at
small contract boundaries, not by collapsing commands behind a generic mode.

Canonical artifact ownership:

| Command | Workflow family | Canonical artifact | Meaning |
|---------|-----------------|--------------------|---------|
| `saham analyze swing TICKER` | Single-ticker swing decision | `TradeSetup` | Authoritative swing action from `SignalEngine + RiskEngine` |
| `saham screen accum` | Candidate discovery | `AccumulationCandidate` with optional `TradeSetup` | Ranked candidates; final action exists only when both signal and risk are present |
| `saham screen pre-open` | Intraday pre-open planning | `PreOpenScreenResult` | Conditional pre-open candidate list and entry ranges |
| `saham analyze pre-open` | Post-open assessment of NCP pre-open plan | `AnalyzePreOpenResult` / `IntradayConfirmationResult` | Read-only ENTER/WAIT/SKIP after opening track snapshot; database-identified (replaces retired `trade confirm` sidecars) |
| `saham trade log --type pre-open` | Paper journal for pre-open strategy | journal row with observation_id + opening_snapshot_id | Explicit notebook write via same assess use case; not a learning label |
| `saham trade swing backtest` | Historical replay | typed learning evaluation | Walk-forward performance artifact, not a live verdict |
| `saham trade backtest-intraday` | Historical proxy simulation | `IntradayBacktestResponse` | Daily-OHLC proxy performance artifact, not exact intraday replay |
| `saham analyze accum-audit` | Learning/audit replay | `AccumulationAuditResponse` | Forward-return audit of foreign-flow score evidence |
| `saham trade log --type swing` | Journal continuation | `LogSwingCandidateResponse` | Persistence outcome for a logged candidate |

Composition rules:

* `TradeSetup` is the only final swing trade verdict wording.
* Any command that shows a complete swing action from signal and risk must call
  `AssessTradeSetupUseCase`.
* `SetupEvaluation`, strategy evidence, sentiment, broker detail, and market
  context preview are evidence modules. They must not independently overwrite
  `TradeSetup.action`.
* Pre-open and intraday confirmation use their own session artifacts. They must
  not reuse `TradeSetup` wording unless the full swing signal/risk contract is
  actually composed.
* Backtest and audit commands produce database-owned learning artifacts. They may replay the
  same deterministic rules, but their outputs are performance observations, not
  current recommendations.

JSON contract rules:

* JSON outputs and command sidecars should include `schema_version` and
  `artifact_type` at the root.
* New machine-facing fields should use explicit artifact names such as
  `foreign_flow_score`, `signal_score`, `risk_status`, `opening_broker_backing_score`, or
  `trade_setup.action`.
* Opening-session artifacts use `opening_setup` for PRIME/WATCH/SKIP labels;
  they must not use generic `verdict` unless they compose a `TradeSetup`.
* `saham analyze swing --format json` treats grouped `verdict`, `evidence`, and
  `diagnostics` as canonical. It does not emit top-level aliases such as
  `trade_setup`, `signal_assessment`, `accumulation`, `risk`, or `data`.

### Layering

Adapters may parse flags, construct infrastructure dependencies, call use cases,
format display, and write command sidecars. Workflow policy and composition
belong in application use cases. Infrastructure factories are preferred when a
command needs a configured engine, repository bundle, or provider bundle.

### Consequences

This keeps the user-facing command model explicit while still allowing shared
internals. Future refactors should add narrow services such as provider bundles,
config factories, display DTOs, or composition contract tests before introducing
larger workflow abstractions.
