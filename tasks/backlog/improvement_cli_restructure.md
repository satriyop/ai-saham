# Backlog: CLI command hierarchy restructure

## 1. Task metadata

**Task title:** Restructure signal and audit CLI commands by lifecycle, subject, and operation  
**Task type:** Refactor  
**Overall priority:** High  
**Status:** Backlog — approved direction, not implemented  
**Decision:** Implement the hierarchy in this document only.

**Hard prerequisite:** Complete `tasks/backlog/audit_data_quality.md` through
DQ-011 with zero open DQ-P0/DQ-P1 findings. Freeze only the corrected behavioral
baseline; do not preserve known data-quality defects during CLI migration.

## 2. Problem statement

The `saham analyze` command surface currently exposes implementation-oriented flat names:

```text
signal-audit
signal-backfill-observations
signal-labels
signal-readiness
signal-replay
accum-audit
audit
swing-compare
compare
```

This creates four problems:

1. Related SignalEngine operations are difficult to discover because they are sorted as unrelated leaf commands.
2. Read-only analysis and persistence-producing learning workflows are mixed under `analyze`.
3. Bare names such as `audit` and `compare` do not identify their subject.
4. Agents can reasonably misinterpret command authority and side effects from the command path.

The current `analyze audit` is specifically a sentiment-outcome audit and persists audit results. `analyze accum-audit` is an offline historical evaluation. `analyze signal-audit` inspects current factor inputs rather than auditing historical outcomes. They do not share one artifact or one side-effect contract.

## 3. Chosen command model

Use this naming grammar:

```text
saham {lifecycle} {subject} {operation}
```

Canonical target commands:

```text
saham analyze signal inspect TICKER
saham analyze signal replay TICKER SNAPSHOT_DATE
saham analyze signal readiness --target TARGET

saham learn signal backfill-observations --universe ... --start ... --end ...
saham learn signal capture --contract accumulation-discovery --session ...
saham learn signal capture --contract swing-setup --setup ... --session ...
saham learn signal labels [SNAPSHOT_DATE] [options]

saham learn sentiment audit
saham analyze accumulation evaluate [TICKERS...] [options]
```

Use subcommands, not operation-selecting flags. Do not introduce forms such as:

```text
saham signal --audit
saham analyze signal --replay
saham analyze audit --type accumulation
```

Flags modify one operation. They must not select workflows with different arguments, artifacts, or persistence behavior.

## 4. Current-to-target mapping

| Current command | Canonical replacement | Lifecycle | Side effects |
|---|---|---|---|
| `saham analyze signal-audit TICKER` | `saham analyze signal inspect TICKER` | Analysis | Read-only |
| `saham analyze signal-replay TICKER DATE` | `saham analyze signal replay TICKER DATE` | Analysis | Read-only |
| `saham analyze signal-readiness --target TARGET` | `saham analyze signal readiness --target TARGET` | Analysis | Read-only |
| `saham analyze signal-backfill-observations ...` | `saham learn signal backfill-observations ...` | Learning | Writes observations; may generate labels when requested |
| New explicit canonical capture workflow | `saham learn signal capture --contract ...` | Learning | Idempotently writes universe-driven canonical observations |
| `saham analyze signal-labels ...` | `saham learn signal labels ...` | Learning | Read-only summary unless a generation flag is used; generation persists labels |
| `saham analyze audit` | `saham learn sentiment audit` | Learning | Persists sentiment audit outcomes |
| `saham analyze accum-audit ...` | `saham analyze accumulation evaluate ...` | Analysis | Offline evaluation; CSV write remains explicit through `--output` |

Old paths become hidden transitional aliases. They must call the same command handler/use case as the canonical path and must not fork behavior.

## 5. Key principles

1. **Lifecycle before subject.** The root command communicates operational intent and likely side effects.
2. **One canonical workflow.** Aliases share the same request mapping, use case, DTO, renderer, exit code, and artifact schema.
3. **Names describe artifacts.** `inspect` means current factor inspection; `replay` means stored-observation replay; `evaluate` means historical outcome measurement.
4. **No hidden writes under analysis.** Commands that generate or persist learning artifacts belong under `learn`.
5. **Adapters stay thin.** Routers register commands; handlers parse/map/render; application use cases retain workflow and persistence policy.
6. **Deterministic behavior is unchanged.** This refactor changes discoverability and routing, not SignalEngine, RiskEngine, TradeSetup, evidence authority, or scoring.
7. **Migration is observable.** Deprecated aliases warn on stderr and never contaminate JSON stdout.
8. **Agent discoverability is a contract.** Help text must state artifact, side effects, data source, and whether a command is read-only.

## 6. Ordered implementation backlog

### CLI-001 — Freeze corrected behavioral contracts before routing changes

**Priority:** P0  
**Depends on:** `tasks/backlog/audit_data_quality.md` DQ-011  
**Outcome:** Corrected and verified command behavior is captured so routing changes cannot silently alter semantics.

**Accurate pointers:**

- Router: `src/adapters/cli/analyze_commands.py`
- Root routers: `src/adapters/cli/main.py`, `src/adapters/cli/learn_commands.py`
- Signal compatibility exports: `src/adapters/cli/analyze_signal_commands.py`
- Focused handlers:
  - `src/adapters/cli/analyze_signal_audit_commands.py`
  - `src/adapters/cli/analyze_signal_replay_commands.py`
  - `src/adapters/cli/analyze_signal_readiness_commands.py`
  - `src/adapters/cli/analyze_signal_backfill_commands.py`
  - `src/adapters/cli/analyze_signal_label_commands.py`
- Sentiment handler: `src/adapters/cli/analyze_sentiment_commands.py`
- Accumulation evaluation: `src/adapters/cli/analyze_accum_commands.py`

**Implementation guideline:**

- Import the corrected contracts and golden fixtures produced by DQ-011.
- Add command-contract tests for arguments, defaults, exit codes, stdout/stderr, JSON roots, and database writes.
- Record which paths are read-only and which write observations, labels, sentiment audits, or explicit CSV output.
- Snapshot representative `--help` output semantically; avoid brittle full-terminal snapshots.
- Test invalid dates, missing required arguments, unsupported formats, absent data, and persistence failures.

**Acceptance criteria:**

- [ ] Every command in the mapping table has a focused contract test.
- [ ] Tests distinguish stdout from stderr.
- [ ] Tests assert read-only commands do not change relevant row counts.
- [ ] Tests assert generation/audit commands write only their documented artifacts.
- [ ] Existing JSON `schema_version`, `artifact_type`, and canonical fields are captured where supported.

### CLI-002 — Introduce the read-only `analyze signal` group

**Priority:** P0  
**Depends on:** CLI-001  
**Outcome:** Signal inspection commands are discoverable under one read-only analysis group.

**Canonical contract:**

```text
saham analyze signal inspect TICKER [--date DATE] [--coverage] [--db PATH]
saham analyze signal replay TICKER SNAPSHOT_DATE [--db PATH]
saham analyze signal readiness --target TARGET [--format table|json] [--db PATH]
```

**Implementation guideline:**

- Create a focused Typer router, suggested file: `src/adapters/cli/analyze_signal_router.py`.
- Register it with `analyze_app.add_typer(signal_app, name="signal")`.
- Reuse existing focused handlers; do not copy their logic.
- Rename the internal audit handler to `inspect_signal` when compatibility permits. The public artifact is a factor inspection report, not a historical audit.
- Update module docstrings and examples to canonical paths.
- Help text must say `Read-only SignalEngine diagnostics from local data.`

**Do not interpret this as:**

- Do not move backfill or label generation into `analyze signal`.
- Do not change factor weights, neutral-fill behavior, scoring, coverage policy, or evidence authority.
- Do not make repositories/services public merely to share handlers.
- Do not create a second SignalEngine construction path.

**Acceptance criteria:**

- [ ] `saham analyze signal --help` lists only `inspect`, `replay`, and `readiness`.
- [ ] Canonical commands match old output/artifacts for identical inputs.
- [ ] The canonical commands are read-only.
- [ ] Help and error examples use canonical paths.
- [ ] Negative tests prove write-producing signal operations are absent from this group.

### CLI-003 — Introduce the persistence-aware `learn signal` group

**Priority:** P0  
**Depends on:** CLI-001  
**Outcome:** Observation and label generation are visibly classified as learning workflows.

**Canonical contract:**

```text
saham learn signal capture \
  --contract accumulation-discovery --session DATE \
  [--format table|json] [--db PATH]

saham learn signal capture \
  --contract swing-setup --setup NAME --session DATE \
  [--format table|json] [--db PATH]

saham learn signal backfill-observations \
  --universe UNIVERSE --start DATE --end DATE \
  [--horizon HORIZON] [--generate-labels] [--format table|json] [--db PATH]

saham learn signal labels [SNAPSHOT_DATE] \
  [--ticker TICKER] [--horizon HORIZON] \
  [--generate | --generate-all] [--eligible-dates] \
  [--captured-at TIMESTAMP] [--format table|json] [--db PATH]
```

**Implementation guideline:**

- Create a focused router, suggested file: `src/adapters/cli/learn_signal_router.py`.
- Register it under the existing `learn_app`.
- Reuse current application use cases and persistence repositories.
- Route both capture contracts through the one application capture use case
  defined by `CONTROL-POPULATION`; the CLI must not implement universe,
  selection, setup-readiness, identity, or idempotency policy.
- State side effects in the first help paragraph.
- Keep label summary behavior available, but clearly distinguish `SUMMARY ONLY` from `GENERATE AND PERSIST` in output.
- Preserve local-only/deterministic backfill behavior.

**Do not interpret this as:**

- Do not merge observation backfill and label generation into one flag-driven command.
- Do not put capture under a top-level `evidence` namespace; `evidence` is an
  artifact, while `learn` is the persistence-producing lifecycle.
- Do not make ordinary `analyze signal` commands persist observations or labels.
- Do not allow single-ticker capture into the canonical learning population;
  per-ticker reconstruction belongs to read-only `analyze signal inspect`.
- Do not alter observation identity, deduplication, eligibility, horizons, or label definitions.
- Do not automatically generate labels unless the existing explicit option requests it.

**Acceptance criteria:**

- [ ] `saham learn signal --help` lists `capture`, `backfill-observations`, and `labels`.
- [ ] `capture` requires an explicit supported observation contract; swing setup capture also requires `--setup`.
- [ ] Discovery and swing-setup capture are universe-driven and idempotent.
- [ ] Help explicitly identifies written tables/artifacts at a user-meaningful level.
- [ ] Identical requests produce the same DTOs and persistence effects as old paths.
- [ ] Summary-only label invocation remains read-only.
- [ ] Negative tests prove no implicit generation occurs.

### CLI-004 — Replace ambiguous sentiment `analyze audit`

**Priority:** P1  
**Depends on:** CLI-001  
**Outcome:** The command path identifies both its subject and its persistence lifecycle.

**Canonical contract:**

```text
saham learn sentiment audit [--db PATH]
```

**Rationale:**

`saham analyze audit` calls `AuditSentimentUseCase`, retrieves unaudited sentiment logs, evaluates forward outcomes, and saves audit records. The bare word `audit` hides both the sentiment subject and the write behavior.

**Accurate pointers:**

- Registration: `src/adapters/cli/analyze_commands.py`
- Handler/factory: `src/adapters/cli/analyze_sentiment_commands.py`, `src/adapters/cli/analyze_sentiment_workflow_factory.py`
- Use case: `src/application/use_case/audit_sentiment_use_case.py`
- Display: `src/adapters/cli/analyze_sentiment_display.py`

**Implementation guideline:**

- Add or reuse a `learn sentiment` router and register `audit` there.
- Keep `AuditSentimentUseCase` as the sole workflow owner.
- Rename adapter symbols/docstrings from generic `sentiment_audit` only if doing so improves local clarity without touching application semantics.
- Help must say that eligible audit outcomes are persisted.

**Acceptance criteria:**

- [ ] The canonical path identifies `sentiment` and `audit`.
- [ ] Persistence behavior and displayed metrics are unchanged.
- [ ] Running with no eligible logs remains a successful, clear no-op result.
- [ ] A persistence failure exits non-zero and does not claim completion.

### CLI-005 — Rename accumulation audit to evaluation

**Priority:** P1  
**Depends on:** CLI-001  
**Outcome:** Historical accumulation replay is named after its produced evaluation artifact.

**Canonical contract:**

```text
saham analyze accumulation evaluate [TICKERS...] [existing options]
```

**Rationale:**

The workflow deterministically replays accumulation signals, measures forward returns, optionally simulates exits, and optionally exports raw records. It is not the same concern as sentiment audit or current signal inspection.

**Accurate pointers:**

- Registration: `src/adapters/cli/analyze_commands.py`
- Handler: `src/adapters/cli/analyze_accum_commands.py`
- Workflow factory: `src/adapters/cli/analyze_accum_workflow_factory.py`
- Application workflow: `src/application/use_case/run_accumulation_audit_workflow_use_case.py`
- Core evaluation: `src/application/use_case/accumulation_audit_use_case.py`
- Display/export: `src/adapters/cli/analyze_accum_display.py`, `src/adapters/cli/analyze_accum_csv_writer.py`

**Implementation guideline:**

- Add an `analyze accumulation` router with `evaluate`.
- Reuse the existing request/response and application workflow during migration.
- Do not rename application types in the same task unless a separate repository-wide symbol-migration task is approved.
- Preserve explicit `--output` CSV behavior and offline/local-data guarantees.

**Acceptance criteria:**

- [ ] Canonical and legacy paths return equivalent summaries and JSON for identical inputs.
- [ ] No CSV is written without `--output`.
- [ ] Setup/filter/exit-grid semantics remain unchanged.
- [ ] Help clearly calls the output historical evaluation, not a current trade verdict.

### CLI-006 — Add hidden deprecated aliases without duplicate workflows

**Priority:** P1  
**Depends on:** CLI-002, CLI-003, CLI-004, CLI-005  
**Outcome:** Existing scripts receive a controlled migration window.

**Legacy aliases:**

```text
analyze signal-audit
analyze signal-replay
analyze signal-readiness
analyze signal-backfill-observations
analyze signal-labels
analyze audit
analyze accum-audit
```

**Implementation guideline:**

- Keep aliases hidden from normal group help.
- Emit one deprecation message to stderr containing the exact canonical replacement.
- Forward parsed arguments to the same handler/request factory; do not shell out and do not invoke Typer recursively.
- Keep JSON stdout byte-equivalent where timestamps/runtime metadata do not prevent it.
- Define the removal version/date in release notes before shipping.

**Do not interpret this as:**

- Do not preserve old commands indefinitely.
- Do not create separate compatibility use cases.
- Do not write warnings to stdout.
- Do not silently redirect an old read-only command to a write-producing command.

**Acceptance criteria:**

- [ ] Legacy aliases are absent from normal help.
- [ ] Every alias warns on stderr with its exact replacement.
- [ ] Alias and canonical exit codes/artifacts match.
- [ ] JSON stdout remains parseable without warning text.
- [ ] Tests assert the alias removal metadata exists.

### CLI-007 — Reconcile documentation and agent discovery surfaces

**Priority:** P1  
**Depends on:** CLI-002 through CLI-006  
**Outcome:** Humans and agents find one canonical command vocabulary.

**Accurate pointers:**

- `README.md`
- `CLI_README.md`
- `docs/how_to_general.md`
- Signal learning/tuning documentation under `docs/`
- `AGENT_QUICKSTART.md` only if it contains affected command examples
- Router/module docstrings and Typer help examples
- Shell completion output and command contract tests

**Implementation guideline:**

- Search the repository for every legacy command string.
- Replace user-facing examples with canonical paths.
- Document deprecated aliases in one migration section rather than alongside canonical examples.
- For each canonical command, state: purpose, artifact, read/write behavior, local/network behavior, and authoritative versus diagnostic meaning.
- Make command tables sort by lifecycle → subject → operation.

**Acceptance criteria:**

- [ ] Repository search finds legacy paths only in alias registration, migration tests, release notes, and historical records.
- [ ] Help and docs agree on side effects.
- [ ] No doc calls `signal inspect` a historical audit.
- [ ] No doc places observation/label generation under analysis.

### CLI-008 — Remove deprecated aliases in a declared breaking release

**Priority:** P2  
**Depends on:** CLI-006, CLI-007, elapsed migration window  
**Outcome:** The public command surface contains only canonical names.

**Implementation guideline:**

- Remove alias registrations, compatibility-only imports, warning helpers, and alias tests.
- Retain migration documentation for the supported release window.
- Confirm no internal automation or documentation still calls old paths.

**Acceptance criteria:**

- [ ] Old paths fail with Typer's unknown-command error and non-zero exit.
- [ ] Canonical paths remain unchanged.
- [ ] Compatibility-only modules are removed only when no imports remain.
- [ ] Full CLI contract suite and repository command-string audit pass.

## 7. Architecture impact assessment

| Question | Answer |
|---|---|
| Domain touched? | No |
| Application behavior changed? | No; existing use cases remain canonical |
| Adapter touched? | Yes; router registration, command names, help, and compatibility aliases |
| Infrastructure touched? | No, except import wiring if composition roots require path updates |
| New runtime dependency? | No |
| Determinism affected? | No |
| Persistence schema changed? | No |
| Existing write behavior moved to a clearer lifecycle path? | Yes |
| Risk/signal/evidence authority changed? | No |

Layer plan for implementation:

```text
Domain: not touched
Application: retain existing use cases and DTO contracts; symbol rename only in separately approved task
Infrastructure: not touched except unavoidable import path updates
Adapter: add grouped routers, canonical registrations, aliases, warnings, and help
Documentation: update command references and migration guide
```

## 8. AI usage declaration

No AI is involved in runtime behavior. The restructure must work fully offline wherever the existing command does. Existing optional AI behavior in unrelated sentiment analysis is unchanged.

## 9. Risk, signal, and evidence authority

This refactor must not change:

- SignalEngine factor values, weights, coverage, or score;
- RiskEngine gates or TradeSetup composition;
- setup evaluation or market-context authority;
- observation/label definitions or learning eligibility;
- diagnostic versus production evidence status;
- what can produce ENTER, WATCH, AVOID, or BLOCKED.

The only semantic clarification is operational: persistence-producing learning workflows are exposed under `learn`, and read-only inspection remains under `analyze`.

## 10. Data and persistence invariants

- `analyze signal inspect`, `replay`, and `readiness` remain read-only.
- `learn signal backfill-observations` preserves current observation writes and deduplication.
- `learn signal labels` writes only when an explicit generation option requests it.
- `learn sentiment audit` preserves current audit-record writes.
- `analyze accumulation evaluate` writes no database state; CSV output occurs only with `--output`.
- No schema migration is part of this backlog.
- Canonical and deprecated paths must address the same configured database.

## 11. Global negative requirements

Do Not Interpret This As:

- Do not introduce a top-level `saham signal` group in this restructure.
- Do not use flags to select distinct operations.
- Do not combine sentiment audit, accumulation evaluation, and signal inspection into a generic audit use case.
- Do not duplicate application workflows for aliases.
- Do not change output schemas, scoring, persistence identity, or decision authority as cleanup.
- Do not move application policy into Typer routers or display modules.
- Do not make deprecated aliases visible as canonical help entries.
- Do not restructure `risk/compare` or `swing/swing-compare` in this scope; track them separately after this migration proves the grouping pattern.

## 12. Verification requirements

Each implementation task must run:

1. Focused command contract tests for canonical and legacy paths.
2. Focused application use-case tests for every reused workflow.
3. Negative tests for forbidden writes and invalid command placement.
4. JSON stdout/stderr separation tests.
5. CLI help/discovery tests.
6. Architecture boundary tests.
7. Full test suite before removing aliases.
8. `git diff --check` for every task.

Representative smoke matrix:

| Command | Success | Invalid input | No data | JSON | Write assertion |
|---|---:|---:|---:|---:|---:|
| `analyze signal inspect` | ✓ | ✓ | ✓ | if supported | no writes |
| `analyze signal replay` | ✓ | ✓ | ✓ | if supported | no writes |
| `analyze signal readiness` | ✓ | ✓ | ✓ | ✓ | no writes |
| `learn signal backfill-observations` | ✓ | ✓ | ✓ | ✓ | exact observation writes |
| `learn signal labels` summary | ✓ | ✓ | ✓ | ✓ | no writes |
| `learn signal labels --generate*` | ✓ | ✓ | ✓ | ✓ | exact label writes |
| `learn sentiment audit` | ✓ | n/a | no eligible logs | current contract | exact audit writes |
| `analyze accumulation evaluate` | ✓ | ✓ | ✓ | ✓ | no DB writes; CSV only if requested |

## 13. Global completion gate

The restructure is complete only when:

- [ ] All canonical paths exist and have accurate help.
- [ ] Read-only and write-producing commands are separated by lifecycle.
- [ ] Old aliases call the same handlers/use cases and warn only on stderr.
- [ ] No engine, scoring, risk, evidence, or persistence semantics changed.
- [ ] Documentation uses canonical paths consistently.
- [ ] Side effects are stated and tested.
- [ ] Alias removal is scheduled and later completed in a breaking release.
- [ ] Focused tests, architecture tests, full suite at final migration, and `git diff --check` pass.
