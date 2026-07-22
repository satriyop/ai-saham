# TUI Phase 1 — Optional Shell And Execution Foundation

Status: `DONE`

Roadmap: `docs/roadmap/roadmap_tui.md`

Depends on: `tasks/backlog/tui_phase_0_inventory_and_contract.md`

Blocks: TUI Phases 2–5

## Task Metadata

- Task type: Feature
- Priority: High
- Semantic classification: `NON_SEMANTIC`
- Chosen decision: add a lazy-loaded optional Textual shell with a shared,
  generation-safe worker foundation. Implement this option only.

## Problem Statement

There is no optional TUI entrypoint, and application workflows are synchronous.
Eager Textual imports would break base installs; direct event-loop execution
would freeze interaction and allow stale results to overwrite current state.

## Desired Outcome

- `saham tui` appears in help without importing Textual.
- A base install retains every non-TUI command.
- Missing Textual produces the Phase 0 message and exit code.
- With the extra, an offline shell opens, navigates Daily/Help, and exits.
- Future screens share typed state and request-generation behavior.

## Non-Goals

- No daily data load, candidate, ticker, readiness, fetch, write, config, AI,
  or provider construction.
- No generic workflow controller.
- No polish beyond a usable 80x24 shell.

## Hard Invariants

- `src.adapters.cli.main` imports without Textual.
- Only `src/adapters/tui/composition.py` may import infrastructure.
- Widgets are never dependency containers.
- Worker threads never mutate widgets directly.
- No automatic retry or calls from focus/cursor/route changes.

## Exact File Boundary

Expected production files:

- `pyproject.toml`, `uv.lock`
- `src/adapters/cli/main.py`, `src/adapters/cli/tui_commands.py`
- `src/adapters/tui/__init__.py`, `main.py`, `composition.py`, `state.py`
- only minimal Help/Daily-shell screen files

Expected tests:

- `tests/adapters/cli/test_tui_commands.py`
- `tests/adapters/tui/test_tui_app.py`
- `tests/adapters/tui/test_tui_state.py`
- `tests/architecture/test_tui_boundaries.py`

Any product-layer or unrelated CLI change requires task revision first.

## Exact Contracts

### Lazy CLI

`tui_commands.py` has no top-level import from `src.adapters.tui` or `textual`.
Its command function imports the runner internally. Catch only the exact missing
optional-dependency case; unrelated import/startup failures must propagate.

Phase 0 Resolution E (binding):

```text
extra: tui
requirement: textual>=8.2,<9
exit code: 1
message: TUI support is not installed. Install this checkout with: pip install -e '.[tui]'
```

Catch `ModuleNotFoundError` only when `exc.name == "textual"`, print the exact
message to stderr, and raise `typer.Exit(code=1)`. Any other missing transitive
module or startup/import failure propagates. Textual 8.2.8 was current when
Phase 0 verified the closed range on 2026-07-22; evidence is recorded in the
Phase 0 task and PyPI package metadata.

### Shared state

`src/adapters/tui/state.py` owns:

```text
ScreenStatus = IDLE | LOADING | READY | EMPTY | UNAVAILABLE | ERROR
ScreenState:
  generation: int
  status: ScreenStatus
  payload: object | None
  error_type: str | None
  error_message: str | None
```

Reject READY without payload, ERROR without both error fields, non-ERROR with
error fields, and negative generations.

The generation API must begin/increment, complete-current, fail-current, and
ignore-stale. Payload remains the source object, not a reconstructed copy.

### Thread boundary

Thread workers return through a Textual thread-safe message/callback, invoke at
most one injected application capability, and never access widgets.

## Architecture Impact

- Domain/Application: not touched
- Infrastructure: composition module exists but wires no provider
- Adapter: launcher, shell, state
- New dependency: yes, optional Textual extra
- Determinism/persistence impact: no
- Adapter-owned policy: UI lifecycle only, no business policy

Layer plan:

```md
Layer plan:
- Domain: not touched
- Application: not touched
- Infrastructure: no implementation changes
- Adapter: lazy launcher, shell, state, routes
```

## AI And Authority Declaration

No AI involved. Signal, risk, TradeSetup, market context, setup, evidence,
tuning, observations, and labels are unchanged.

## Implementation Checklist

- [x] Confirm Phase 0 is `DONE`; copy packaging contract.
- [x] State file boundary and worker transport before editing.
- [x] Add and lock optional dependency.
- [x] Add lazy CLI registration.
- [x] Add minimal TUI package/composition root.
- [x] Add state/generation implementation.
- [x] Add Daily shell and Help route.
- [x] Add architecture guard.
- [x] Add import, state, concurrency, and headless tests.

## Acceptance Criteria

- [x] Base CLI help works without importing Textual.
- [x] Missing-extra behavior is exact.
- [x] Unrelated import errors are not mislabeled.
- [x] Installed shell launches/exits offline.
- [x] Help navigation works at 80x24.
- [x] Focus/cursor/route changes run no use case.
- [x] Stale completion cannot replace newer state.
- [x] Invalid state combinations fail.
- [x] Architecture guard enforces roadmap prohibitions without allowlists.
- [x] No network or persistence occurs.
- [x] Focused, architecture, full tests when feasible, and `git diff --check` executed;
  the three unrelated full-suite baseline failures are recorded below.
- [x] Status becomes `DONE`; completion record is filled.

## Required Negative Tests

- Base CLI with `textual` unavailable.
- Exact missing-extra error.
- Unrelated `ModuleNotFoundError` propagates.
- Generation N finishes after N+1 and is ignored.
- Invalid ScreenState combinations fail.
- Fixture with forbidden TUI import is detected.

## Do Not Interpret This As

- Do not import Textual at CLI import time or catch all import errors.
- Do not add a DI container/service locator.
- Do not run placeholder business use cases.
- Do not add later-phase or agent files.
- Do not weaken architecture tests.

## Verification

Run focused launcher/state/headless tests, general and TUI architecture tests,
the full suite when feasible, and `git diff --check`.

## Data, Persistence, And Documentation

- Data read/write: none.
- Schema/config change: none.
- CLI change: adds optional `saham tui`; base commands remain unchanged.
- Documentation impact: no user guide required until Phase 5; exact
  missing-extra help text is tested here.
- All tests must run offline.

## Agent Execution Protocol

Before editing, confirm Phase 0 status, copy its resolved packaging contract,
restate hard invariants/forbidden interpretations/exact files, and describe the
worker result transport. Stop if the design needs product-layer changes. Update
checklists and the completion record only from executed verification evidence.

## Completion Record

- Completed date: 2026-07-22
- Implementation commit: not created; working-tree delivery
- Files changed: `pyproject.toml`, `uv.lock`, CLI registration/lazy launcher,
  minimal TUI app/composition/state/Daily/Help modules, Phase 1 CLI/state/app and
  architecture tests, existing exact command-tree test, this task, and the
  Phase 2 status
- Locked dependency: `textual==8.2.8`; added lock entries are
  `linkify-it-py==2.1.0`, `mdit-py-plugins==0.6.1`, and `uc-micro-py==2.0.0`
- Missing-extra verification: subprocess proves base CLI imports without
  `textual` or `src.adapters.tui.main`; exact simulated missing-Textual exit is
  code 1 with the Phase 0 message; unrelated `ModuleNotFoundError` identity
  propagates
- Focused tests: `17 passed`; exact CLI command contract: `13 passed`
- Architecture tests: TUI and general boundaries `7 passed`; no allowlist
- Full suite: `5702 passed, 3 failed` in 110.22s. These are the same unrelated
  accumulation-audit fixture and signal-label backfill failures recorded by
  the Phase 0 prerequisite; no new failure.
- `git diff --check`: passed; scoped Ruff passed
- Deferred items: repository-wide Ruff currently reports 727 existing
  out-of-scope violations; Daily data execution begins in Phase 2
