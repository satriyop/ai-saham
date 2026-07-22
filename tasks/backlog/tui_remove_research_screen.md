# TUI Removal — Research Corpus Health Screen

Status: `DONE`

Roadmap: `docs/roadmap/roadmap_tui.md`

Product/UX authority: `docs/roadmap/roadmap_tui.md`; the former
`tasks/backlog/tui_ui_ux_design_spec.md` is historical only

Supersedes: completed Phase 4 TUI Research Corpus Health and the subsequent
Research Scope Selector UX correction

Blocks: Milestone A Personal Command Center

## Task Metadata

- Task type: Product-scope correction / code removal
- Priority: High
- Semantic classification: `NON_SEMANTIC`
- Chosen decision: remove signal corpus/readiness diagnostics from the TUI and
  preserve them as application-owned CLI engineering tools. Implement this
  option only.

## Product Decision

The TUI exists for the investor-facing journey:

```text
Today -> accumulation candidates -> ticker research
```

The Research Corpus Health screen answers a different, specialist question:
whether persisted signal observations and labels form a sufficiently clean,
same-cohort diagnostic sample for calibration analysis. It does not research a
ticker, find candidates, improve a trading decision, or provide promotion
authority.

Putting that diagnostic in the primary TUI navigation created a misleading
product surface. Replacing raw identifiers with guided selectors improves
interaction mechanics but does not create user value. The screen and its
TUI-only discovery machinery must therefore be removed, not polished further.

This decision rejects the TUI surface, not the underlying readiness contract.

## Desired Outcome

The TUI has exactly these product routes:

```text
Today
  -> Candidates
       -> Ticker Research
Help (temporary overlay/pushed screen)
```

There is no Research/Research Health top-level route, key binding, Help entry,
screen, TUI composition dependency, or TUI-only scope catalog.

The following existing engineering interface remains available:

```text
saham research signal readiness --target TARGET [--cohort COHORT]
```

It continues to call `ReportSignalReadinessUseCase` with unchanged readiness,
cohort-isolation, exclusion-ledger, and diagnostic-only semantics.

## Scope Boundary

### Remove completely

- `src/adapters/tui/screens/research_health_screen.py`
- `src/adapters/tui/controllers/research_health_controller.py`
- `src/adapters/tui/presenters/research_health_presenter.py`
- `src/adapters/tui/widgets/research_health.py`
- `src/adapters/tui/readiness/`
- `tests/adapters/tui/readiness_fixtures.py`
- `tests/adapters/tui/test_readiness_composition.py`
- `tests/adapters/tui/test_research_health_contracts.py`
- `src/application/dto/signal_research_scope.py`
- `src/application/use_case/list_signal_research_scopes_use_case.py`
- `tests/application/use_case/test_list_signal_research_scopes_use_case.py`

### Edit to remove Research Health integration only

- `src/adapters/tui/main.py`
  - remove route binding, action, imports, constructor dependencies, screen
    creation, cancellation branches, and Research Health CSS selectors;
- `src/adapters/tui/composition.py`
  - remove readiness/scope imports, loader parameters, factories, controllers,
    presenters, and returned constructor arguments;
- `src/adapters/tui/screens/help.py`
  - remove Research route/key/copy without changing ticker-research help;
- `tests/adapters/tui/test_tui_app.py`
  - remove Research Health fixtures, fakes, construction arguments, and route
    scenarios while preserving Today/Candidates/Ticker coverage;
- `tests/adapters/tui/test_tui_release_gates.py`
  - remove Research Health release scenarios and add absence assertions;
- user documentation that advertises the TUI Research route.

### Preserve exactly

- `src/application/use_case/report_signal_readiness_use_case.py`
- `tests/application/use_case/test_report_signal_readiness_use_case.py`
- `src/adapters/cli/analyze_signal_readiness_commands.py`
- `tests/adapters/cli/test_signal_readiness_command.py`
- `saham research signal readiness` command registration
- signal capture, labels, replay, backfill, cohort identity, and persistence
- ticker research files, including:
  - `src/adapters/tui/screens/ticker_research_screen.py`
  - `src/adapters/tui/controllers/ticker_research_controller.py`
  - `src/adapters/tui/presenters/ticker_research_presenter.py`
  - `src/adapters/tui/research_capabilities.py`
  - `src/adapters/tui/widgets/research.py`

If a named preserve file must change to compile, stop and explain the exact
dependency before editing it. Do not broaden this task into readiness redesign.

## End-to-End Invariants

After removal:

```text
TUI startup
  -> compose Today/Candidates/Ticker dependencies only
  -> no readiness repositories or use cases constructed
  -> no Research route reachable by key, action, Help, or internal navigation

CLI readiness command
  -> ReportSignalReadinessUseCase
  -> exact SignalReadinessReport
  -> unchanged CLI table/JSON rendering
```

The TUI must not keep a dormant route, hidden key, lazy factory, compatibility
alias, or dead selector catalog. Removal is clean and complete.

## Architecture Impact

- Domain: no change
- Application: delete only the TUI-created scope-catalog DTO/use case; preserve
  readiness behavior
- Infrastructure: no repository/schema change
- Adapter: remove the Research Health TUI vertical slice and composition
- Persistence/config: unchanged
- CLI: readiness command remains supported and unchanged
- Determinism: unchanged
- AI usage: none

Layer plan:

```md
Layer plan:
- Domain: not touched
- Application: remove TUI-only scope discovery; preserve readiness use case
- Infrastructure: not touched
- Adapter: remove Research Health route and vertical slice
```

## Implementation Checklist

- [x] Confirm every remove/preserve path against current source before editing.
- [x] Record current focused TUI and CLI readiness baselines.
- [x] Remove the Research route, binding, action, CSS, and construction inputs.
- [x] Remove Research Health from Help and user-facing TUI documentation.
- [x] Delete the Research Health controller/presenter/screen/widgets/composition.
- [x] Delete TUI-only scope-catalog application code and tests.
- [x] Remove Research-specific fixtures and TUI tests.
- [x] Add negative route/composition/import assertions.
- [x] Prove Today, Candidates, and Ticker Research remain functional.
- [x] Prove CLI signal readiness remains functional and unchanged.
- [x] Run focused tests, architecture tests, full suite when feasible, and
  `git diff --check`.
- [x] Set this task to `DONE` and fill the completion record from executed
  evidence.

## Acceptance Criteria

- [x] The TUI exposes no route or visible label named `Research` or
  `Research Health`.
- [x] Key `3` does not navigate to a removed or hidden screen.
- [x] Help advertises only supported TUI routes and actions.
- [x] TUI construction accepts no readiness/scope loader, controller,
  presenter, repository, or use case.
- [x] Importing and starting the TUI imports no Research Health module.
- [x] All files in **Remove completely** are absent.
- [x] No `ResearchHealth*`, `ResearchScopes*`, `show_research`,
  `research-health`, or `ListSignalResearchScopes*` production reference
  remains.
- [x] Today -> Candidates -> Ticker Research still works keyboard-only.
- [x] Ticker Research terminology and implementation remain intact.
- [x] `ReportSignalReadinessUseCase` and its application tests are unchanged.
- [x] CLI readiness table and JSON tests pass.
- [x] No observation, label, schema, configuration, or database behavior
  changes.
- [x] Focused TUI and architecture tests plus `git diff --check` pass; the full
  suite was run and its three unrelated baseline failures are recorded below.
- [x] Completion record lists deleted files and verification evidence.

## Required Negative Tests

- Pressing `3` cannot open Research Health.
- No hidden `show_research` action exists on the TUI app.
- TUI composition cannot construct readiness repositories or use cases.
- TUI Help and footer contain no Research route.
- Import scan finds no TUI dependency on `ReportSignalReadinessUseCase` or
  `ListSignalResearchScopesUseCase`.
- Removing Research Health does not remove or rename Ticker Research.
- CLI `research signal readiness` still handles valid, invalid, empty, and
  multi-cohort requests according to its existing tests.

## Do Not Interpret This As

- Do not hide the screen while retaining its code and composition.
- Do not move it to an Advanced menu.
- Do not keep key `3` as a hidden compatibility alias.
- Do not retain the selector catalog for hypothetical future use.
- Do not delete or weaken the application readiness report or CLI command.
- Do not rename Ticker Research merely to avoid the word “research.”
- Do not modify signal calculations, eligibility thresholds, cohort rules,
  observation/label schemas, or persistence.
- Do not erase Phase 4's historical completion record; append the later product
  rejection instead.
- Do not claim the removed screen provided investor value.

## Verification Commands

Use repository-standard test invocation discovered at implementation time. At
minimum, verify:

```text
focused TUI app/navigation/help tests
TUI and general architecture tests
application readiness tests
CLI signal-readiness tests
full test suite when feasible
git diff --check
```

Also run a repository search proving that removed production symbols and route
labels are absent. A search hit in historical task documentation is allowed;
production and active UX/roadmap contracts are not.

## Agent Execution Protocol

Before editing, restate the exact removal set, preservation set, construction
changes, negative proofs, and exception boundary. Protect unrelated worktree
changes. If removal requires changing readiness semantics, CLI behavior,
persistence, or ticker research, stop and report the dependency rather than
expanding scope.

## Completion Record

- Completed date: 2026-07-22
- Implementation commit: this completion commit
- Files deleted: Research Health TUI screen, controller, presenter, widget,
  readiness composition package, fixtures, and focused tests; uncommitted
  selector DTO, use case, and application test
- Integration files changed: TUI app/composition/Help, TUI app/composition/
  release-gate tests, TUI boundary test, README, CLI README, Phase 4 historical
  record, and UX contract
- Route-absence proof: headless release journey verifies key `3` stays on
  Today, `action_show_research` is absent, binding `3` is absent, and Help has
  no Research entry
- Composition/import-absence proof: constructor-signature and architecture
  tests reject readiness/scope inputs and imports; production source search is
  empty for all removed symbols
- Today/Candidates/Ticker proof: keyboard-only release journey passed at
  80x24, 120x40, and 160x50; Ticker Research files are unchanged
- CLI readiness proof: existing valid, invalid, empty, and multi-cohort command
  tests passed unchanged
- Application readiness proof: existing `ReportSignalReadinessUseCase` tests
  passed unchanged
- Architecture tests: TUI and general layer-boundary tests passed
- Full suite: all tests outside three pre-existing unrelated failures passed;
  two stale `_FakeScreenerConfig` failures remain in
  `test_analyze_accum_workflow_factory.py`, plus the existing canonical-window
  generated-label-count failure in
  `test_backfill_signal_observations_use_case.py`
- `git diff --check`: passed
- Deferred items: the three unrelated full-suite baseline failures
