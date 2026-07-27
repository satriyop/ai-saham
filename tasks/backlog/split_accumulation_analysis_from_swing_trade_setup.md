# Split Accumulation Evidence Analysis from Swing Trade Analysis

Status: `BACKLOG`

Governing decisions:

- [ADR-025](../../docs/adr/ADR-025-signalengine-architecture.md)
- [ADR-026](../../docs/adr/ADR-026-risk-plus-signal-pipeline-composition.md)
- [ADR-033](../../docs/adr/ADR-033-workflow-composition-artifact-boundaries.md)
- [ADR-041](../../docs/adr/ADR-041-canonical-signal-evidence-input-boundary.md)
- [ADR-049](../../docs/adr/ADR-049-database-owned-learning-pipeline-clean-break.md)

## 1. Task Metadata

- Task type: Refactor / product-boundary migration
- Priority: Medium
- Semantic classification: `NON_SEMANTIC` only when fixture parity proves the
  existing `saham analyze swing` signal, risk, `TradeSetup`, sizing, and plan
  outputs are unchanged. Escalate before editing if evidence authority,
  calculations, gates, configuration, or compatibility identity changes.
- Chosen decision: add `saham analyze accumulation TICKER` for accumulation
  evidence inspection and retain `saham analyze swing TICKER` as the final
  swing-trade assessment. Implement this option only.

## 2. Problem Statement

`saham analyze swing` currently bundles accumulation evidence inspection with
the final swing-trade decision. Its options and panels mix broker-flow detail,
accumulation pattern/phase, signal, risk, market context, named setup,
backtesting, sizing, entry, stop, target, and holding period.

This makes two different questions appear to be one:

1. “Is accumulation present, reliable, and ready?”
2. “Given all canonical evidence and risk, is there an actionable swing trade?”

The bundle obscures ownership, encourages accumulation-specific details to leak
into a supposedly strategy-level command, and leaves no focused read-only
analysis surface corresponding to `screen accumulation` and
`research accumulation`.

## 3. Desired Outcome

Provide two explicit read-only analysis commands.

### Accumulation evidence

```text
saham analyze accumulation TICKER
saham analyze accumulation TICKER --window N
saham analyze accumulation TICKER --with-flow-detail
saham analyze accumulation TICKER --as-of YYYY-MM-DD
saham analyze accumulation TICKER --format json
```

This command answers only:

> Is accumulation present, what evidence supports it, what is its provenance,
> availability, phase/readiness, and what is missing?

It displays the canonical accumulation assessment, flow components, pattern,
phase/readiness, data quality, provenance, and availability. It does not
compose a final `TradeSetup`, size a position, or emit a second
`ENTER` / `WATCH` / `AVOID` action.

### Swing trade assessment

```text
saham analyze swing TICKER
saham analyze swing TICKER --setup NAME
saham analyze swing TICKER --capital IDR --risk-pct PCT
saham analyze swing TICKER --as-of YYYY-MM-DD
saham analyze swing TICKER --format json
```

This command answers:

> Given canonical evidence—including the typed accumulation assessment when
> applicable—signal, risk, regime, and setup policy, is there an actionable
> swing trade and what is its plan?

It remains the sole command in this pair that projects final `TradeSetup`
action, entry, stop, target, size, and holding horizon.

## 4. Non-Goals

- No replacement or alias for `saham analyze swing`.
- No rename of swing to accumulation.
- No change to `screen accumulation` candidate discovery.
- No change to `research accumulation` capture, labels, evaluation, or replay.
- No new signal scorer, risk rule, setup policy, strategy, provider, or AI path.
- No promotion of accumulation evidence.
- No observation write from either interactive analysis command.
- No duplicated accumulation calculation maintained separately by each command.
- No change to production YAML values or `TradeSetup` arithmetic.

## 5. Do Not Interpret This As

- Do not make `analyze accumulation` a second source of
  `ENTER` / `WATCH` / `AVOID`.
- Do not make `analyze swing` a thin alias of `analyze accumulation`.
- Do not copy the current monolithic workflow into two divergent implementations.
- Do not query accumulation evidence twice inside one swing analysis.
- Do not reconstruct accumulation provenance from rendered dictionaries.
- Do not let CLI panels calculate phase, readiness, score, action, or policy.
- Do not persist interactive single-ticker analysis as canonical learning data.
- Do not treat user-selected ticker analysis as a population observation.
- Do not silently move options between commands without CLI negative tests and
  updated documentation.

## 6. Architecture Impact Assessment

- Domain: reuse current evidence, signal, risk, setup, and `TradeSetup` types.
  Add no duplicate accumulation or action vocabulary.
- Application: extract one typed `AnalyzeAccumulationUseCase` result and make
  swing orchestration consume that exact typed result where accumulation
  evidence is applicable.
- Infrastructure: reuse current repositories/providers through existing ports;
  composition roots may be split or deduplicated.
- Adapter: mount `analyze accumulation`, split options/displays, and keep both
  adapters thin.

- New dependency: No.
- Affects determinism: No.
- Persistence changes: No.
- Warm-up data: No new requirement; preserve existing window/data rules.
- Adapter policy/orchestration: No.

```md
Layer plan:
- Domain: reuse canonical evidence and action types; no new verdict language
- Application: typed accumulation analysis producer consumed by swing orchestration
- Infrastructure: reuse existing ports and provider/repository composition
- Adapter: separate accumulation evidence and swing TradeSetup commands/displays
```

## 7. AI Usage Declaration

No AI involved. Existing optional sentiment/AI-adjacent diagnostics must remain
optional, non-authoritative, and outside accumulation authority.

## 8. Risk, Signal, and Evidence Authority

- `analyze accumulation` exposes evidence and readiness; it cannot authorize a
  trade or bypass SignalEngine/RiskEngine.
- `analyze swing` remains the final canonical composition:

```text
canonical evidence → SignalEngine + RiskEngine → AssessTradeSetupUseCase
```

- Accumulation evidence reaches swing analysis through a typed application
  result, not display payloads or adapter-local dictionaries.
- Market context and named setup policy remain swing concerns unless an
  existing canonical accumulation result explicitly owns a field.
- No change to what can produce `ENTER` / `WATCH` / `AVOID`.
- No diagnostic evidence promotion or tuning eligibility change.

## 9. Exact Ownership and Transport

Define one owning application DTO, provisionally
`AnalyzeAccumulationResult`, containing:

- ticker and effective PIT session/cutoff;
- resolved accumulation window/config identity;
- exact evidence input/provenance and availability;
- accumulation score/components already owned by canonical application logic;
- pattern/phase/readiness types;
- warnings and typed missing states;
- consumed repository-row identities/fingerprint where currently available.

Producer-to-consumer chain:

```text
repositories/providers through ports
  → AnalyzeAccumulationUseCase (one call)
  → AnalyzeAccumulationResult
      ├─→ analyze accumulation display/JSON
      └─→ AnalyzeSwingUseCase
           → SignalEngine + RiskEngine + setup policy
           → TradeSetup + plan
           → analyze swing display/JSON
```

`AnalyzeSwingUseCase` must not re-query or rebuild accumulation evidence after
receiving the typed result. The result must not carry both a derived canonical
assessment and a separately mutable duplicate of its raw source.

Missing/failure behavior:

- expected unavailable accumulation evidence: typed unavailable/missing state;
- unsupported ticker/session: typed application error;
- malformed canonical evidence, cutoff mismatch, or provenance mismatch:
  propagate and fail closed;
- optional detail unavailable: typed warning without changing the canonical
  swing decision;
- provider refresh failure: preserve current explicit failure/fallback contract;
  do not invent a new adapter fallback.

## 10. CLI Option Ownership

Move or expose under `analyze accumulation`:

- accumulation `--window`;
- broker `--flow-window`;
- `--with-flow-detail`;
- accumulation evidence/detail output;
- common `--as-of`, `--db`, refresh controls, and `--format`.

Keep under `analyze swing`:

- `--setup`;
- `--capital`, `--risk-pct`, `--entry`, `--atr-mult`, `--rr`;
- signal/risk/market detail and explanation;
- market-context controls;
- strategy/backtest and sentiment options;
- final `TradeSetup` and trade-plan output.

If `analyze swing` retains accumulation detail flags for a transition, that is
not a compatibility alias: it must call the same typed producer and be
documented as an opt-in projection of subordinate evidence. Do not duplicate
calculation. Removed or moved flags must be proven absent where the final
chosen CLI contract says they no longer belong.

## 11. Acceptance Criteria

- [ ] `saham analyze accumulation TICKER` exists and is read-only.
- [ ] It presents accumulation evidence, provenance, availability, and
      readiness without final trade action, sizing, stop, or target.
- [ ] `saham analyze swing TICKER` remains the final swing `TradeSetup`
      assessment.
- [ ] Swing consumes the exact typed accumulation result once; no duplicate
      evidence query/reconstruction occurs within a run.
- [ ] Equivalent fixtures preserve current swing signal, risk, `TradeSetup`,
      sizing, plan, and JSON semantics.
- [ ] Both commands resolve the same PIT cutoff and accumulation identity for
      the same ticker/as-of/config.
- [ ] Interactive commands write no learning observations or labels.
- [ ] Adapter displays contain no local scoring, readiness, or action policy.
- [ ] Help text and documentation clearly distinguish evidence analysis from
      trade analysis.
- [ ] No alias, dual scorer, or hidden legacy workflow remains.

## 12. Testing Expectations

- Unit: `AnalyzeAccumulationUseCase` availability, PIT cutoff, provenance,
  pattern/phase/readiness, and failure states.
- Producer/consumer: recording fake proves swing receives the exact typed
  result emitted by the accumulation producer and invokes it once.
- Parity: golden fixtures compare pre-migration and post-migration swing
  canonical outputs, not merely rendered text.
- Negative: accumulation analysis cannot return final `TradeSetup` action or
  write observations; adapter cannot query repositories directly.
- CLI: option ownership, JSON contracts, removed aliases/flags, and help.
- Architecture: domain/application imports and manual-DI composition roots.
- Full offline suite and `git diff --check`.

## 13. Documentation Impact

- Update CLI overview, accumulation screener/research docs, swing trading guide,
  building blocks, architecture index, examples, and relevant ADR amendments.
- Add a concise vocabulary table:

```text
accumulation = evidence/discovery method
swing        = trade horizon and final TradeSetup
```

- Document that `WATCH` from final swing `TradeSetup` may be rerun on a later
  PIT session; this is a new assessment, not a forward label.

## 14. Delivery Sequence

1. Amend governing ADR/workflow ownership documentation.
2. Extract typed accumulation application result with focused contract tests.
3. Make current swing workflow consume that result once and prove canonical
   output parity.
4. Mount `saham analyze accumulation` and its evidence-only display/JSON.
5. Split CLI option ownership and remove forbidden duplicate/alias paths.
6. Update documentation and architecture tests.
7. Run focused/full suites and `git diff --check`; commit only task-owned files.

## 15. Agent Execution Instructions

Before implementation, read `AGENT_QUICKSTART.md`, `AGENTS.md`,
`TASK_TEMPLATE.md`, `DEFINITION_OF_DONE.md`, ADR-025, ADR-026, ADR-033,
ADR-041, ADR-049, and current executable screen/analyze/research composition
roots.

Before editing, state:

- exact DTO ownership and producer-to-consumer transport;
- CLI option ownership;
- semantic classification and parity strategy;
- current dirty-worktree scope.

If extraction requires changed scoring, evidence authority, setup policy, or
compatibility identity, stop and request an explicit contract decision.

## Final Gate

The task is complete only when accumulation evidence and swing trade analysis
are separate user concepts backed by one shared typed application producer,
current swing canonical output is unchanged, both commands remain read-only,
negative architecture/CLI tests pass, the full suite passes, and
`git diff --check` is clean.
