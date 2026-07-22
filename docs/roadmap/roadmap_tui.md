# Roadmap: Read-Only TUI Research Workspace

Status: vetted roadmap / pre-implementation

Last verified: 2026-07-22

Scope: optional Textual-based terminal UI for local, deterministic research

## Decision

Build a narrow, read-only TUI as a sibling adapter to the CLI. Implement this
option only.

The first useful product journey is:

```text
Today -> accumulation candidates -> ticker research
```

Do not attempt to reproduce the full CLI command tree. The TUI earns further
scope only after this journey is useful, offline-capable, responsive, and
architecturally thin.

The CLI remains the primary supported automation interface. The TUI is an
optional interactive research workspace over the same application contracts:

```text
CLI adapter -----\
                  -> application use cases -> domain/ports -> infrastructure
TUI adapter -----/
```

The TUI may navigate, collect input, schedule application calls, preserve UI
state, and render canonical results. It must not become a second workflow or
policy system.

## Current Code Truth

This roadmap is based on source, tests, live CLI help, and accepted ADRs as of
2026-07-22. Reverify these facts before implementation.

| Concern | Current truth | Roadmap consequence |
|---|---|---|
| Public lifecycle | `today`, `fetch`, `audit`, `screen`, `learn`, `research`, `view`, `analyze`, `strategy`, `trade` | Design around user journeys and artifact authority, not one screen per command group |
| Daily orientation | `DailyBriefingUseCase` already returns readiness, authority, regime, opening observations, accumulation candidates, setup-lens results, and warnings | Use it as the first screen contract |
| Accumulation | `RunAccumulationScreenWorkflowUseCase` returns application-owned single/multi projections | Render its projection; do not reconstruct filtering, ranking, or canonical-window fields |
| Ticker research | `SwingAnalysisWorkflowUseCase` returns typed verdict, evidence, and diagnostics | Use a local-only request; do not scrape CLI output |
| Signal corpus | Explicit `saham research signal capture`/backfill owns canonical observation writes; ordinary screen/analyze paths are read-only | Do not revive old screen-recording behavior or use interactive frequency as the learning population |
| Readiness | `ReportSignalReadinessUseCase` is cohort-aware and exposes an exclusion ledger; its ephemeral 70/30 split is diagnostic and `promotion_eligible` remains false | Label the screen research corpus health, never promotion/calibration authority |
| Status | `GetSystemStatusUseCase` checks provider health as well as stored freshness | It is not a local-only Phase 1 contract |
| Runtime | Application workflows are synchronous and some are expensive | Never execute them directly on Textual's event loop |
| Dependencies | `pyproject.toml` has Typer/Rich but no Textual | Keep Textual optional and lazy-loaded |
| Architecture guard | The general layer scan covers domain/application/infrastructure, not adapter thinness | Add TUI-specific import and behavior guards |
| Composition | Concrete dependencies are manually wired in infrastructure composition roots or thin adapter factories | Use one TUI composition root; never make widgets dependency containers |

The earlier S1-style observation-identity precondition is retired from this
roadmap. The signal-evidence program now reports its lean canonical evidence
and baseline gates closed. Corpus population is optional product data, not a
prerequisite for starting the read-only TUI.

## Product Boundary

### V1 includes

- Optional `saham tui` launcher.
- Offline daily briefing.
- Accumulation candidate browsing.
- Local-only ticker research drilldown.
- Research corpus health after the main journey is stable.
- Help, keyboard navigation, loading, empty, unavailable, and error states.

### V1 excludes

- Provider refresh or fetch actions.
- Watchlist, observation, label, journal, or other persistence actions.
- Config editing, tuning review/application, or strategy authoring.
- Background schedulers or autonomous refresh loops.
- AI chat, conversational tools, or model challengers.
- Order placement or broker execution.
- A screen for every CLI command group.

Conversation/agent work belongs to
`docs/roadmap/roadmap_conversational_agent_architecture.md` and requires its own
approved implementation plan or ADR. It is not a later phase of this roadmap.
Write-capable TUI actions likewise require separate, action-specific tasks with
side-effect, idempotency, failure, and confirmation contracts.

## Architectural Contract

### Package and composition shape

Start with the smallest package that supports the first vertical slice:

```text
src/adapters/cli/
  tui_commands.py          # Typer command; no top-level Textual import

src/adapters/tui/
  __init__.py
  main.py                  # Textual application and run entrypoint
  composition.py           # only TUI module allowed to import infrastructure
  state.py                 # UI-only state and request-generation identifiers
  controllers/
  presenters/
  screens/
  widgets/
```

Do not pre-create speculative screens, widgets, presenters, repositories, or
agent modules. Add a file only when an implemented screen needs it.

`src/adapters/cli/tui_commands.py` must register a thin `saham tui` command and
import `src.adapters.tui.main` only inside the command function. If Textual is
not installed, it must exit non-zero with an actionable installation message,
not a traceback. Importing `src.adapters.cli.main`, running `saham --help`, and
using every non-TUI command must still work without the TUI extra.

`src/adapters/tui/composition.py` owns concrete repository, config-loader,
provider, and use-case construction. Prefer existing infrastructure
composition helpers where they match the required contract. Do not move
concrete construction into application factories or bootstrap modules.

### Import rules

Screens, widgets, presenters, state, and controllers may import:

```text
stdlib
textual / rich
src.application DTOs and use-case interfaces
src.domain value objects and enums needed for rendering
other src.adapters.tui modules
```

Only `src/adapters/tui/composition.py` may import `src.infrastructure.*`.

All TUI modules are forbidden from importing or invoking:

```text
src.adapters.cli display or command modules
sqlite3
provider clients outside composition.py
YAML/config loaders outside composition.py
subprocess or arbitrary shell execution
direct filesystem persistence
scoring, risk, setup, tuning, evidence-authority, or freshness policy
```

The TUI must never parse Rich/ANSI output or CLI JSON to recover application
state.

### Responsibility boundaries

| Component | Owns | Must not own |
|---|---|---|
| Application use case | Workflow, policy, filtering, canonical projection, business status, unavailable reasons | Textual concepts, colors, focus, navigation |
| TUI controller | One UI interaction, loading/cancellation state, invoking one injected application capability, mapping known failures to UI state | Cross-use-case business orchestration, retries, policy, persistence decisions |
| Presenter | DTO-to-view-model formatting, labels copied from canonical values, styles, column order | Thresholds, ranking, action wording, readiness or freshness calculation |
| Screen | Navigation, focus, binding interaction, choosing when an explicit action starts | Infrastructure construction, provider access, business decisions |
| Widget | Rendering and local visual state | Dependency wiring or application workflow |
| Composition root | Concrete dependency construction and injection | Business workflow or display policy |

Do not add `GetTui*UseCase` types. New application queries must be named for
their business meaning and must be independently useful to another adapter.
Add one only after the inventory proves an existing result cannot support the
screen without adapter-owned workflow or policy.

### Execution and concurrency

Existing application workflows are synchronous. Run them in Textual thread
workers, never directly in event handlers or reactive watchers.

Each screen action must have a monotonically increasing request-generation ID:

```text
user action
  -> mark generation N LOADING
  -> run injected application capability in worker
  -> post typed completion for generation N
  -> apply only if N is still the screen's active generation
```

Required rules:

- Superseding an action cancels or invalidates the older worker result.
- A late result must never overwrite newer screen state.
- Thread workers must not mutate widgets directly; return through Textual's
  thread-safe message/callback mechanism.
- No automatic retry. A retry is an explicit user action unless an application
  use case already owns a deterministic retry policy.
- Cursor movement, focus, and row highlighting never trigger provider calls,
  persistence, or expensive recomputation.
- App exit must close cleanly without applying late worker results.

### Screen-state contract

Every data-bearing screen uses these adapter states:

```text
IDLE
LOADING
READY
EMPTY
UNAVAILABLE
ERROR
```

- `EMPTY`: the application call succeeded and returned a valid empty result.
- `UNAVAILABLE`: the application result explicitly reports missing/stale data
  or another expected unavailable condition.
- `ERROR`: validation, configuration, infrastructure, or other execution failed.
- Contract/invariant/programmer errors must not be converted into ordinary
  missing data. They reach the central error boundary and remain visibly failed.

Implementation tasks must name the exact exception types mapped to expected
`UNAVAILABLE` or `ERROR` states. Broad `except Exception` handlers may protect
the terminal session only at the outer screen/app boundary; they must retain
the error class and must not fabricate a valid business result.

### Meaning of read-only

V1 is product-read-only: it performs no intentional fetch, corpus, label,
watchlist, journal, config, tuning, or other business mutation.

Some current SQLite repository constructors initialize schemas. Therefore do
not claim byte-for-byte storage immutability unless a later task introduces and
tests a genuinely read-only persistence composition. Phase 0 must record any
constructor/startup side effects. The UI must never present schema
initialization as a user-requested data update.

## Contract Inventory

### Daily workspace

```text
Owner: DailyBriefingUseCase
Input: DailyBriefingRequest
Output: DailyBriefingResponse
```

Render existing fields for overall authority, dataset readiness, clocks,
regime, opening observations, accumulation summary/candidates, setup-lens
impact, and warnings. Do not make `GetSystemStatusUseCase` part of this screen;
its provider-health probe violates the offline-only launch contract.

If a separate stored-data inventory later proves necessary, add a business-
named application query such as `GetLocalDataInventoryUseCase`. Its contract
must read local metadata only and must not silently reuse provider health
checks.

### Accumulation browser

```text
Owner: RunAccumulationScreenWorkflowUseCase
Input: RunAccumulationScreenWorkflowRequest
Output: RunAccumulationScreenWorkflowResult
Canonical rows: ScreenAccumSingleProjection or ScreenAccumMultiProjection
```

The projection is the one source of truth for candidate inclusion, canonical
window, filters, ranks/order, risk status, setup phase, data state, and next
action. Transport the returned projection to the presenter. Do not re-query or
reconstruct an equivalent candidate list.

V1 preserves canonical order. Interactive column sorting is deferred. If later
added, it must be labeled as presentation order and preserve the canonical rank
as a separate visible field.

### Ticker research

```text
Owner: SwingAnalysisWorkflowUseCase
Input: SwingAnalysisWorkflowRequest
Output: SwingAnalysisWorkflowResponse
```

The V1 request must be local-only:

```text
auto_refresh = false
force_refresh = false
include_sentiment = false
```

Other optional detail flags may expose already-local evidence. The screen must
render `SwingVerdict`, `SwingEvidence`, and `SwingDiagnostics` without merging
canonical and preview results. `TradeSetup` remains the sole final swing-action
wording. Missing signal evidence remains unavailable; it must not become
neutral, WATCH, or a presenter-authored fallback.

### Research corpus health

```text
Owner: ReportSignalReadinessUseCase
Input: ReportSignalReadinessRequest(target, semantic_compatibility_id)
Output: SignalReadinessReport
```

The UI must require or explicitly resolve a target and cohort exactly as the
use case does. Show:

- target components and diagnostic-target status;
- selected and available semantic compatibility IDs;
- observation and label counts;
- unique ticker/session counts;
- exclusion ledger;
- split mode, IS/OOS counts, diagnostic readiness, and blockers;
- `patch_eligible` only with its existing meaning;
- `promotion_eligible = false` and the diagnostic-only limitation.

Do not call label generation, capture, repair, tuning, or promotion workflows
from this screen. An empty corpus is a valid `EMPTY`/not-ready product state and
does not block shipment of the daily workspace.

## Delivery Roadmap

### Phase 0 — Inventory and executable task contract

Goal: prove the first journey can be built without importing CLI behavior or
inventing application policy.

Tasks:

- Record the screen-to-use-case mappings above in the implementation task.
- Inspect each production composition root and list its concrete dependencies.
- Record constructor/startup side effects, network-capable callables, optional
  evidence, and local-only request values.
- Define exact loading, empty, unavailable, error, and cancellation behavior.
- Verify which application DTO fields each first-slice widget consumes.
- Decide and lock the optional dependency range. At this validation date the
  candidate is `tui = ["textual>=8.2,<9"]`; recheck before editing the lockfile.
- Define the lazy-import failure message and exit behavior.

Acceptance:

- One implementation task covers only the optional shell and daily screen.
- Every transported value has one named owner and producer-to-presenter path.
- Network and mutation-capable dependencies are identified and excluded.
- Missing and failure states are explicit; no `as needed` contracts remain.
- No product-layer code is changed in this phase.

### Phase 1 — Optional shell and execution foundation

Goal: launch and exit a responsive optional TUI without weakening the base CLI.

Scope:

- Add the `tui` optional dependency and locked version.
- Add lazy `saham tui` registration.
- Add the minimal TUI package and one composition root.
- Add Help/About and an empty daily screen shell.
- Implement the worker, request-generation, and common screen-state machinery.

Acceptance:

- Base installation without Textual imports and runs `saham --help`.
- Without Textual, `saham tui` exits non-zero with the documented install hint.
- With the extra, `saham tui` starts and exits cleanly offline.
- No use case runs merely from focus/cursor changes.
- A superseded worker result cannot update current state.
- TUI-specific import guards reject infrastructure outside `composition.py`,
  CLI display imports, SQLite, YAML loaders, subprocess, and provider clients.
- Headless tests cover launch, Help navigation, and exit at 80x24.

### Phase 2 — Offline daily workspace

Goal: make `saham tui` useful for daily orientation from cached data.

Scope:

- Execute `DailyBriefingUseCase` in a worker.
- Render authority/readiness before candidate tables.
- Render regime, opening observations, accumulation shortlist, setup-lens
  impact, warnings, and data clocks.
- Provide explicit Reload for local recomputation only.

Acceptance:

- Startup and Reload perform no provider request or intentional business write.
- `READY`, `PARTIAL`, `NOT_READY`, empty, and execution-failure fixtures render
  distinguishable states.
- Candidate/actions/status text comes from the application response.
- A NOT_READY response does not show suppressed rankings as usable candidates.
- Presenter tests assert exact authority, warning, and unavailable mappings.
- Headless tests cover load, reload, late-result rejection, and error recovery.

### Phase 3 — Candidate browser and ticker drilldown

Goal: complete the first validated journey.

Scope:

- Open the application-owned accumulation projection from the daily screen.
- Navigate candidates without recomputation.
- Run an explicit local-only ticker research request on Enter.
- Render canonical verdict, signal coverage, risk gates, TradeSetup, supporting
  evidence, corporate-action risk, freshness, warnings, and diagnostics.

Acceptance:

- The candidate browser receives the exact workflow projection; no second read
  or reconstructed list determines inclusion/order.
- Candidate order matches the canonical projection.
- Navigation alone performs no application call.
- Ticker request records `auto_refresh=false`, `force_refresh=false`, and
  `include_sentiment=false` in controller tests.
- Canonical and preview verdicts are visually and structurally separate.
- Missing evidence is `UNAVAILABLE`, never neutral or adapter-authored advice.
- Tests prove no TUI module creates ENTER/WATCH/AVOID/BLOCKED wording.

### Phase 4 — Research corpus health

Goal: expose honest corpus status without implying evidence authority.

Scope:

- Add target and semantic-cohort selection.
- Render readiness counts, exclusions, split identity, metrics, and blockers.
- Support a valid empty-corpus state.

Acceptance:

- Multiple cohorts require explicit selection exactly as the application
  contract requires; the adapter never pools them.
- The ephemeral split and diagnostic-only meaning are always visible.
- `promotion_eligible` is not inferred from `diagnostic_ready` or
  `patch_eligible`.
- No capture, label, repair, patch, tuning, or promotion use case is wired.

### Phase 5 — Hardening and release decision

Goal: decide whether the narrow TUI deserves continued product investment.

Tasks:

- Test at 80x24, 120x40, and a representative large terminal.
- Test keyboard-only navigation, repeated reload, worker cancellation, app exit
  during work, error recovery, and empty databases.
- Verify base install, TUI-extra install, and offline execution in CI.
- Run architecture boundary and TUI adapter-thinness tests.
- Document installation, controls, local-only behavior, and limitations.
- Review actual user value before proposing any new screen or write action.

Exit decision:

- Keep Textual optional unless measured adoption justifies changing ADR-011's
  CLI-primary posture.
- Further read-only screens require their own user journey and contract map.
- Any write action or conversational agent requires a separate approved plan.

## Testing Strategy

| Test | Required proof |
|---|---|
| Packaging/import | Base CLI works without Textual; missing-extra failure is actionable |
| Architecture | TUI non-composition modules cannot import infrastructure, CLI display, SQLite, YAML, subprocess, or providers |
| Application | Existing/new business queries return typed results from fakes without Textual imports |
| Controller | Exact request values, one application call, generation handling, no automatic retry |
| Presenter | DTO-to-view-model formatting only; no thresholds, ranking, status, or action invention |
| Headless TUI | Navigation, bindings, loading/empty/unavailable/error states, terminal sizes |
| Concurrency | Superseded/late results cannot overwrite current state; exit during work is safe |
| Offline | No network/provider call in shell, daily, candidate navigation, ticker local-only, or readiness screens |
| Negative authority | Missing evidence never becomes neutral; preview never becomes canonical; readiness never implies promotion |

Prefer controller and presenter tests outside Textual. Use Textual's headless
`App.run_test()`/Pilot boundary for representative navigation and lifecycle
behavior rather than trying to prove business policy through widget snapshots.

## Do Not Interpret This As

- Do not wrap or execute CLI commands from the TUI.
- Do not scrape Rich tables, ANSI output, or CLI JSON.
- Do not create one screen per top-level CLI group.
- Do not add speculative `GetTui*` application use cases.
- Do not put workflow orchestration into controllers, screens, or presenters.
- Do not make `GetSystemStatusUseCase` an offline-only contract; it probes
  providers in its current composition.
- Do not trigger fetch, persistence, or expensive recomputation from mount,
  focus, cursor movement, or reactive field changes.
- Do not let user-driven presentation order replace canonical rank.
- Do not treat corpus availability, diagnostic readiness, or patch eligibility
  as promotion evidence.
- Do not make AI, provider credentials, network access, or model dependencies
  required for the TUI.
- Do not add generic write capability, arbitrary tools, direct SQL, shell
  access, config editing, tuning apply, or order execution.
- Do not claim storage is byte-for-byte read-only while current repository
  construction can initialize schemas.

## Implementation Close Criteria

Each phase task must state its own exact files, request/response contracts,
production composition roots, missing/failure mappings, negative tests, and
focused verification before editing.

A phase is done only when:

- the exact scoped journey works, not merely an empty screen shape;
- adapters remain thin and application/domain authority is unchanged;
- offline and no-intentional-mutation invariants have executable tests;
- optional dependency behavior is tested both installed and absent;
- cancellation and late-result behavior are tested;
- forbidden imports and authority fallbacks have negative tests;
- focused tests, architecture tests, and `git diff --check` pass;
- no unrelated worktree changes are modified.

## Immediate Next Task

Create a strict Phase 0/1 implementation task for only:

```text
optional lazy launcher
+ worker/screen-state foundation
+ offline DailyBriefingUseCase screen
```

Do not include candidate drilldown, readiness, writes, or agent work in that
task. Require pre-edit confirmation of the lazy import path, dependency bundle,
worker result transport, known exception mapping, and the exact
`DailyBriefingResponse` fields rendered.
