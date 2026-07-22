# TUI Phase 0 — Inventory And Binding Implementation Contract

Status: `BACKLOG`

Roadmap: `docs/roadmap/roadmap_tui.md`

Blocks: TUI Phases 1–5

## Task Metadata

- Task type: Spike / Research
- Priority: High
- Semantic classification: `NON_SEMANTIC`
- Chosen decision: produce the binding implementation inventory for the
  read-only TUI. Implement this option only.

## Problem Statement

The roadmap fixes the architecture, but implementation still depends on facts
that must be resolved from current code: exact composition dependencies,
constructor side effects, network-capable callables, request defaults, DTO
fields, and exception behavior. Letting later agents rediscover these facts
would invite inconsistent wiring and adapter-owned policy.

## Desired Outcome

This document contains a completed, source-cited resolution record identifying:

- one producer and transport path for every displayed result;
- every concrete dependency required by the four planned screens;
- exact local-only request values;
- startup or constructor writes;
- absence, validation, infrastructure, and invariant failure behavior;
- the dependency range and lazy-launch failure contract;
- the files each later phase may change.

This phase changes no product code.

## Non-Goals

- No TUI, dependency, CLI, product, test, config, or persistence implementation.
- No redesign of current use cases or composition roots.
- No new application DTO or policy proposal unless a proven blocker is first
  escalated for separate approval.
- No agent, write-capable UI, provider, or broader command-tree planning.

## Hard Invariants

- Current code and tests outrank roadmap prose.
- CLI display functions and JSON are never TUI data sources.
- Ordinary screen/analyze workflows remain read-only.
- Interactive use never determines the learning population.
- Missing evidence is not neutral evidence.
- `TradeSetup` remains the only final swing-action wording.
- Diagnostic readiness and patch eligibility do not imply promotion.
- Missing business orchestration is assigned to a business-named application
  use case before UI implementation proceeds.

## Exact Work Boundary

Expected files changed:

- this task document;
- dependent TUI phase task documents when a resolved fact replaces a placeholder.

Forbidden changes:

- `src/**`
- `tests/**`
- `config/**`
- `pyproject.toml`
- `uv.lock`

If inventory reveals a product decision not fixed by the roadmap, stop and ask
instead of selecting a broader architecture.

## Required Reading

- `AGENT_QUICKSTART.md`, `AGENTS.md`, and `TASK_TEMPLATE.md`
- `docs/roadmap/roadmap_tui.md`
- ADRs 003, 004, 011, 021, 033, and 040
- Current source and focused tests for:
  - `DailyBriefingUseCase`
  - `RunAccumulationScreenWorkflowUseCase`
  - `SwingAnalysisWorkflowUseCase`
  - `ReportSignalReadinessUseCase`
  - their production composition roots
  - SQLite repositories constructed by those roots

Do not inspect unrelated backlog-task formatting.

## Architecture Impact

- Domain: not touched
- Application: not touched
- Infrastructure: not touched
- Adapter: not touched
- Documentation/governance: this task and dependent TUI tasks
- New dependency: no
- Determinism impact: no
- Persistence/schema impact: no
- Adapter-owned policy: no

Layer plan:

```md
Layer plan:
- Domain: not touched
- Application: not touched
- Infrastructure: not touched
- Adapter: not touched
```

## AI And Authority Declaration

- AI usage: no AI involved.
- SignalEngine, RiskEngine, TradeSetup, market context, setup policy, evidence
  authority, tuning, observations, and labels are unchanged.

## Required Resolution Record

Complete every cell with a source path and symbol. Never write “same as CLI,”
“reuse existing,” or “wire as needed.”

### A. Producer and transport map

| Screen | Request owner | Result owner | Composition root | Presenter input | Second reads? |
|---|---|---|---|---|---|
| Daily | `DailyBriefingRequest` | `DailyBriefingResponse` | TODO | TODO exact fields | No |
| Accumulation | `RunAccumulationScreenWorkflowRequest` | `RunAccumulationScreenWorkflowResult` plus single/multi projection | TODO | TODO exact projection | No |
| Ticker | `SwingAnalysisWorkflowRequest` | `SwingAnalysisWorkflowResponse` | TODO | TODO verdict/evidence/diagnostics fields | No |
| Corpus health | `ReportSignalReadinessRequest` | `SignalReadinessReport` | TODO | TODO exact fields | No |

### B. Dependency and side-effect inventory

| Capability | Concrete dependencies | Network-capable dependency | Constructor/startup write | Exclusion/mitigation |
|---|---|---|---|---|
| Daily | TODO | TODO | TODO | TODO |
| Accumulation | TODO | TODO | TODO | TODO |
| Ticker | TODO | TODO | TODO | TODO |
| Corpus health | TODO | TODO | TODO | TODO |

Inspect SQLite schema initialization. Record whether V1 is only
product-read-only or can guarantee byte-for-byte database immutability.

### C. Exact request defaults

Record every required constructor field, its source, and value:

- accumulation: all required fields, canonical window, filters, `top`, save
  disabled, and strategy-overlay behavior;
- ticker: all required fields, including `auto_refresh=False`,
  `force_refresh=False`, and `include_sentiment=False`;
- readiness: target parsing, optional cohort, and multiple-cohort behavior.

### D. Failure matrix

| Capability | Valid empty | Typed unavailable | Expected ERROR exceptions | Invariant/programmer failure |
|---|---|---|---|---|
| Daily | TODO | TODO | TODO exact types | Propagate to outer boundary |
| Accumulation | TODO | TODO | TODO exact types | Propagate to outer boundary |
| Ticker | TODO | TODO | TODO exact types | Propagate to outer boundary |
| Corpus health | TODO | TODO | TODO exact types | Propagate to outer boundary |

Malformed canonical DTOs, incompatible identity/cohort state, and impossible
states must not become ordinary missing data.

### E. Packaging and launcher

Confirm or amend with evidence:

```text
extra name: tui
candidate requirement: textual>=8.2,<9
base CLI imports Textual: never
missing-extra exit code: 1
missing-extra message:
TUI support is not installed. Install this checkout with: pip install -e '.[tui]'
```

If Textual's supported major changed, update Phase 1 and cite package metadata.
Do not leave an open-ended lower bound.

## Implementation Checklist

- [ ] Protect unrelated worktree changes.
- [ ] Inventory all four use cases and DTOs.
- [ ] Trace production composition roots and narrow callables.
- [ ] Identify network-capable dependencies.
- [ ] Identify constructor/startup writes.
- [ ] Complete producer/transport map.
- [ ] Complete dependency/side-effect inventory.
- [ ] Complete exact request defaults.
- [ ] Complete failure matrix with exact types.
- [ ] Resolve dependency and lazy-launch contract.
- [ ] Copy resolutions into dependent phase tasks.
- [ ] Replace every `TODO`.

## Acceptance Criteria

- [ ] Resolution tables are complete and source-cited.
- [ ] Every later phase has exact request values and transport ownership.
- [ ] No second-read or reconstructed-result option remains.
- [ ] Absence, expected exceptions, and invariants are distinguished.
- [ ] Network/mutation-capable dependencies have explicit exclusions.
- [ ] Packaging and missing-extra behavior are exact.
- [ ] No product, test, config, dependency, or lock file changed.
- [ ] `git diff --check` passes.
- [ ] Status becomes `DONE`; completion record is filled.

## Do Not Interpret This As

- Do not implement the TUI or add Textual.
- Do not refactor CLI factories.
- Do not create `GetTui*UseCase` types.
- Do not use CLI rendering/JSON as an intermediate.
- Do not weaken authority, cohort, provenance, or failure behavior.
- Do not leave later agents a choice between transport paths.

## Data, Testing, And Documentation

- Data read: repository source, tests, dependency metadata, and ADRs only.
- Data written: this and dependent task documents only.
- Schema/config/CLI behavior change: none.
- Tests: product tests are not required because no product contract changes;
  every cited claim must be verified through source inspection.
- Documentation impact: resolution tables and dependent task contracts are the
  deliverable.

## Agent Execution Protocol

Before editing, restate hard invariants, exact file boundary, unresolved facts,
and layer plan. During work, update checklist items only after evidence exists.
Before marking done, show that every TODO is gone, run `git diff --check`, fill
the completion record, and change status to `DONE`.

## Completion Record

- Completed date:
- Implementation commit:
- Verified source revision:
- Files changed:
- Key resolved decisions:
- Commands run:
- Verification result:
- Deferred items and owner:
