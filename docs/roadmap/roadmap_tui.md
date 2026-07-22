# Roadmap: TUI And Optional Agent Interface

Status: thought document / implementation roadmap  
Date: 2026-07-16  
Scope: Textual-based terminal UI for AI Saham, with optional later chat/agent mode

## Executive Summary

The best UI direction for the current codebase is a TUI first, not a full GUI.
The repository is already CLI-first, local-first, deterministic-first, and
workflow-heavy. A TUI can improve navigation, drilldown, and daily research
ergonomics while keeping the same ports-and-adapters architecture.

The TUI must be implemented as a new adapter:

```text
CLI adapter -> application use cases -> domain/ports -> infrastructure
TUI adapter -> application use cases -> domain/ports -> infrastructure
```

It must not become a second business-logic system. TUI screens and widgets may
render, navigate, collect input, and call application use cases. They must not
query SQLite directly, construct provider clients directly, recompute scores,
invent labels, or override SignalEngine, RiskEngine, TradeSetup, tuning, or
evidence-promotion rules.

Recommended path:

1. Stabilize data and view contracts.
2. Build a read-only Textual TUI adapter.
3. Add ticker drilldown and workflow navigation.
4. Add learning/readiness panels after canonical observation data and grading
   loops are populated enough to be trustworthy.
5. Add optional conversational agent mode only after the TUI has stable
   read-only context providers and approval guardrails.

## Current Codebase Vetting

### Strengths To Build On

| Area | Current Evidence | TUI Impact |
|---|---|---|
| Architecture | `README.md`, `ARCHITECTURE_DECISIONS.md`, `tests/architecture/test_layer_boundaries.py` | TUI can fit cleanly as `src/adapters/tui` |
| CLI adapter pattern | `src/adapters/cli/main.py` and many command modules | Existing command groups map naturally to TUI screens |
| Manual dependency injection | CLI workflow factories wire concrete repositories/providers | TUI should use equivalent thin composition factories |
| Application DTOs/use cases | `daily_briefing_use_case.py`, `run_accumulation_screen_workflow_use_case.py`, `swing_analysis_workflow_use_case.py`, readiness/label/audit use cases | TUI can render structured results without scraping CLI output |
| Rich display components | Existing CLI display modules use Rich tables/panels | Useful reference for information hierarchy, but not a direct widget layer |
| Projection discipline | `screen_accum_result_projector.py` centralizes screen projection | Good example: adapter should render canonical application projections |
| AI posture | `docs/ai_modes.md`, `src/infrastructure/ai/README.md` | Optional chat/agent can reuse AI as adapter, never authority |

### Current Gaps And Risks

| Gap | Why It Matters For TUI | Required Response |
|---|---|---|
| No TUI dependency | `pyproject.toml` has Typer/Rich, not Textual | Add Textual only when implementing Phase 1, likely as optional UI dependency |
| CLI modules mix wiring and rendering | Some CLI files are large composition/rendering surfaces | Do not copy CLI internals into TUI widgets; create TUI-specific presenters and application view use cases where needed |
| S1 observation identity was fixed in code, but local data may still be legacy | Learning/readiness panels can show empty or provisional results if the DB has no canonical observations yet | Gate learning/calibration panels on canonical observation availability and label coverage, not on the old S1 implementation bug |
| Some workflows are expensive or provider-backed | TUI navigation should not accidentally fetch or recompute on every cursor move | Default to local cached reads; make network refresh explicit |
| AI docs mention older/default provider details that may drift | Agent mode could over-trust stale provider assumptions | Use current AI factory/config at implementation time; keep chat optional and provider-swappable |
| Architecture guard scans domain/application/infrastructure, not adapters | A TUI adapter can still become fat without failing current boundary tests | Add TUI-specific adapter-thinness tests or review checklist in implementation phases |

## Architectural Decision

### Placement

Use this package shape:

```text
src/adapters/tui/
  __init__.py
  app.py
  main.py
  tui_factory.py
  routes.py
  bindings.py

  screens/
    dashboard_screen.py
    accumulation_screen.py
    ticker_detail_screen.py
    data_status_screen.py
    calendar_screen.py
    readiness_screen.py
    agent_screen.py

  widgets/
    candidate_table.py
    ticker_header.py
    signal_panel.py
    risk_panel.py
    broker_flow_panel.py
    calendar_events_panel.py
    data_freshness_badge.py
    readiness_summary_panel.py
    chat_transcript.py
    tool_approval_panel.py

  presenters/
    dashboard_presenter.py
    accumulation_presenter.py
    ticker_detail_presenter.py
    readiness_presenter.py
    agent_presenter.py
```

### Dependency Direction

Allowed imports in TUI screens/widgets/presenters:

```text
src.application.dto
src.application.use_case
src.application.services only for pure presentation-safe DTO helpers when already accepted
src.domain value objects/enums for rendering canonical values
textual
rich
stdlib
```

Allowed imports in `src/adapters/tui/tui_factory.py` only:

```text
src.infrastructure.persistence
src.infrastructure.config
src.infrastructure.browser/provider composition when explicitly needed
src.infrastructure.ai factory for optional agent mode
```

Forbidden in TUI screens/widgets:

```text
sqlite3
src.infrastructure.*
provider clients
YAML loaders
direct filesystem persistence
scoring formulas
risk/signal policy
adapter-local thresholds, buckets, labels, pseudo-actions, or rankings
```

### Runtime Shape

```text
saham tui
  -> adapters.cli or adapters.tui entrypoint parses launch options
  -> TUI factory wires repositories/providers/use cases
  -> Textual app owns navigation and screen lifecycle
  -> screens call application-facing controllers/use cases
  -> presenters map DTOs to view models
  -> widgets render only
```

Do not make Textual widgets dependency containers. They should receive already
constructed callables, controller objects, or DTOs.

## Application View Contracts Needed

The TUI should not scrape CLI table output. Where existing use cases return
good DTOs, reuse them. Where a screen would need to call many unrelated use
cases or perform workflow assembly, add application query/view use cases.

Recommended application use cases:

```text
GetTuiDashboardUseCase
GetAccumulationCandidatesViewUseCase
GetTickerResearchViewUseCase
GetDataStatusViewUseCase
GetCalendarRiskViewUseCase
GetLearningReadinessViewUseCase
```

These are not TUI-specific in behavior. They are read/query use cases returning
stable view DTOs that could also power CLI JSON or future web UI.

Example DTO boundary:

```text
Application DTO:
  ticker
  canonical action/status fields
  score fields already produced by engines/use cases
  freshness status
  calendar risk status
  unavailable reasons
  warnings

TUI presenter:
  display text
  color/style names
  column order
  collapsed/expanded state
```

## UX Scope

### TUI Should Do First

Read-only research terminal:

```text
Dashboard
Accumulation candidate browser
Ticker drilldown
Data/fetch status
Corporate calendar risk view
Readiness/label coverage view after S1
```

### TUI Should Not Do First

```text
Config editing
Tuning patch apply
Autonomous fetch loops
Background scheduling daemon
ML views
AI-authored decisions
Broker deep analytics beyond available application DTOs
```

Write actions can be added later, but every write action must have explicit
confirmation, application-owned workflow, and deterministic behavior when AI is
disabled.

## Phase Roadmap

### Phase 0: Preconditions And Contract Cleanup

Goal:

```text
Prepare the codebase so TUI renders canonical application outputs instead of
recreating CLI behavior.
```

Tasks:

- Confirm S1 remains fixed in code: screen execution is read-only, canonical
  recording is explicit, duplicate recording is idempotent, and labels use
  canonical observation rows.
- Check local data readiness before exposing learning/calibration screens:
  canonical observation count, label count, unavailable reasons, and IS/OOS
  split coverage.
- Identify which CLI commands already have reusable application DTOs.
- Identify which CLI output logic is adapter-only and should become
  application projection before TUI uses it.
- Decide dependency packaging:
  - preferred: `ui = ["textual>=..."]` optional extra
  - alternative: main dependency only if TUI becomes first-class default
- Decide command entrypoint:
  - `saham tui` as a Typer command
  - optional future script: `saham-tui`

Acceptance:

- No TUI code yet required.
- Written inventory of reusable use cases and missing view contracts.
- S1 status and canonical-data readiness are explicit in the TUI task plan.
- Textual dependency decision is recorded before dependency edit.

Layer plan:

```text
Domain: not touched
Application: maybe add/read view-contract tasks only, no UI
Infrastructure: not touched
Adapter: not touched or docs only
```

### Phase 1: Minimal Read-Only TUI Shell

Goal:

```text
Start a Textual app that shows local system/data status and navigates between
empty or simple read-only screens.
```

Scope:

- Add `src/adapters/tui`.
- Add `saham tui` launcher.
- Add Dashboard, Data Status, and Help/About screens.
- Use local cached status only.
- No provider/network fetch from screen lifecycle.
- No AI.

Recommended screens:

```text
DashboardScreen
DataStatusScreen
HelpScreen
```

Acceptance:

- `saham tui` starts and exits cleanly.
- TUI works offline.
- TUI imports no infrastructure outside `tui_factory.py`.
- Architecture test remains green.
- Basic smoke test covers app construction or presenter output.

Layer plan:

```text
Domain: not touched
Application: reuse existing status/read use cases or add read-only view use case
Infrastructure: not touched except factory wiring through existing implementations
Adapter: new Textual adapter, thin launcher, screens, widgets, presenters
```

### Phase 2: Accumulation Candidate Browser

Goal:

```text
Make the most common human workflow easier: browse accumulation candidates and
open a candidate detail placeholder.
```

Scope:

- Screen for accumulation candidates using application projection.
- Sort/filter using canonical application output only.
- Keyboard navigation:
  - up/down candidate
  - enter opens ticker detail
  - refresh runs explicit local recompute or documented use case
- Show warnings and freshness status clearly.

Dependencies:

- Reuse `RunAccumulationScreenWorkflowUseCase`.
- Reuse `screen_accum_result_projector.py` or a new application view use case.
- Do not persist diagnostic multi-window rows; S1 fixed this contract and TUI
  must not reintroduce the old side effect.

Acceptance:

- Candidate rows match CLI JSON/table projection for equivalent inputs.
- No adapter-local score/rank/bucket calculation.
- Network/provider refresh is explicit, not automatic on cursor movement.
- Multi-window mode does not worsen S1.

Layer plan:

```text
Domain: not touched
Application: add view DTO/use case only if existing response is not enough
Infrastructure: not touched
Adapter: TUI screen, presenter, candidate table widget
```

### Phase 3: Ticker Research Drilldown

Goal:

```text
Provide a single ticker view that combines existing deterministic evidence in
one navigable screen.
```

Scope:

- Header: ticker, latest candle/broker dates, freshness.
- Signal panel: canonical signal score, coverage, decision fields.
- Risk panel: canonical OPEN/BLOCKED status and gates.
- Trade setup panel: canonical TradeSetup action/status.
- Broker flow panel: existing broker summary/detail fields.
- Corporate calendar panel: existing event-risk context.
- Warnings/unavailable evidence panel.

Dependencies:

- Reuse `SwingAnalysisWorkflowUseCase` where practical.
- Consider `GetTickerResearchViewUseCase` to avoid screen-level orchestration.

Acceptance:

- TUI never creates ENTER/WATCH/AVOID text independently.
- Every displayed action/status comes from domain/application/config.
- Missing data appears as unavailable/unknown, not neutral.
- No direct SQLite/provider access in widgets/screens.

Layer plan:

```text
Domain: not touched
Application: likely add ticker research view DTO/use case
Infrastructure: factory wiring only
Adapter: TUI detail screen and presenters
```

### Phase 4: Readiness, Labels, And Calibration Panels

Goal:

```text
Expose learning health only after observation identity and label binding are
trustworthy.
```

Hard gate:

```text
Do not present learning/calibration data as authoritative unless canonical
observations and labels exist for the selected scope. If the DB only has legacy
candidate_observations rows, the screen must show "no canonical observations"
or "provisional / not calibration-grade" instead of silently using legacy rows.
```

Scope:

- Observation counts by date/universe/setup/horizon.
- Forward-label counts and unavailable reasons.
- IS/OOS counts with explicit split method.
- Patch eligibility and blockers from application readiness output.
- Accumulation screener grading loop status when available.

Dependencies:

- `ReportSignalReadinessUseCase`
- `GenerateSignalForwardLabelsUseCase`
- `SummarizeSignalForwardLabelsUseCase`
- future accumulation grading loop use case

Acceptance:

- IS/OOS split method is shown.
- Provisional or incomplete data is visible.
- No config patch apply from TUI.
- No AI-generated tuning authority.

Layer plan:

```text
Domain: not touched
Application: readiness/coverage view use cases as needed
Infrastructure: factory wiring only
Adapter: TUI readiness screens and presenters
```

### Phase 5: Controlled Write Actions

Goal:

```text
Allow selected deterministic actions from the TUI without turning it into a
policy layer.
```

Possible actions:

```text
Run fetch status
Run explicit fetch market/calendar command equivalent
Save watchlist
Generate labels
Run readiness report
Open/draft tuning review without apply
```

Rules:

- Every write action must call an application use case.
- Every write action must show a confirmation dialog with exact data impact.
- No background mutation on screen open.
- No autonomous config apply.
- No AI-triggered tool execution without explicit user approval.

Acceptance:

- Actions are deterministic for the same inputs and local data.
- Side effects are idempotent where applicable.
- Errors are visible and actionable.
- Tests cover action controller behavior outside Textual where possible.

Layer plan:

```text
Domain: not touched unless existing use case requires domain value objects
Application: owns all write workflows
Infrastructure: existing providers/repositories only
Adapter: confirmation UI and error mapping only
```

### Phase 6: Optional Conversation Agent Mode

Goal:

```text
Add a chat-style research copilot inside the TUI without giving AI authority
over scores, risk, trade setup, config, or persistence.
```

Recommended initial capability:

```text
Ask questions about currently loaded DTOs:
- Why is this ticker WATCH/AVOID/BLOCKED?
- What changed in accumulation candidates?
- Which rows have calendar risk?
- What are the readiness blockers?
```

Architecture:

```text
AgentScreen
  -> SendAgentMessageUseCase
  -> AgentContextProvider ports
  -> LlmProvider port
  -> infrastructure AI adapter
```

Application contracts to add:

```text
StartAgentConversationUseCase
SendAgentMessageUseCase
BuildAgentContextUseCase
ExecuteApprovedAgentToolUseCase
ConversationRepository port
LlmProvider or AgentModelProvider port
```

Agent tools must be application-owned capabilities, not arbitrary shell access:

```text
get_current_dashboard_context
get_ticker_research_context
get_accumulation_candidates_context
get_readiness_context
draft_research_note
```

Forbidden in initial agent mode:

```text
shell execution
arbitrary file editing
direct SQL
config patch apply
placing orders
changing risk/signal/tuning authority
claiming model output as trading advice
```

AI behavior rules:

- AI is optional and disabled by default unless explicitly enabled.
- The deterministic TUI must still work without API keys or network.
- AI answers must cite the local DTO/context fields they used.
- AI can summarize or explain; it cannot decide.
- Tool calls require explicit user approval if they have side effects.
- All prompts and model/provider choices must be versioned or logged.

Acceptance:

- Mock provider tests pass offline.
- Chat fails gracefully without API keys.
- Agent cannot access raw infrastructure from UI/widgets.
- Agent cannot mutate config or data in read-only mode.

Layer plan:

```text
Domain: optional ports/value objects only if needed for provider abstraction
Application: agent conversation and context use cases
Infrastructure: AI provider adapters and optional conversation persistence
Adapter: Textual chat UI, transcript, approval panel
```

## Testing Strategy

Use layered tests:

| Test Type | Scope |
|---|---|
| Architecture tests | TUI screens/widgets must not import infrastructure or forbidden libraries |
| Application tests | View use cases return stable DTOs from fake repositories/providers |
| Presenter tests | DTO to view-model formatting, no policy decisions |
| TUI smoke tests | App starts, screen routes exist, key bindings do not crash |
| Agent tests | Mock LLM, deterministic context, no network, side-effect approval rules |

Prefer testing application controllers and presenters outside Textual. Keep full
Textual integration tests small.

## Dependency Strategy

Recommended `pyproject.toml` shape when implementation starts:

```toml
[project.optional-dependencies]
ui = [
    "textual>=0.x",
]
```

Do not add a UI dependency until Phase 1 starts. Do not make AI provider
packages mandatory for TUI. Agent mode should use existing optional/provider
patterns and fail gracefully when provider dependencies or API keys are absent.

## Implementation Guardrails For Future Agents

Before implementing any TUI phase, the agent must:

- Read `README.md`, `PROMPT_CONTRACT.md`, `DEFINITION_OF_DONE.md`,
  `AI_AGENT_CHECKLIST.md`, `TASK_TEMPLATE.md`, and
  `ARCHITECTURE_DECISIONS.md`.
- Read this roadmap and the specific use cases/screens affected.
- State the layer plan.
- State whether the phase touches SignalEngine, RiskEngine, TradeSetup,
  market context, setup policy, evidence authority, persistence, or AI.
- Confirm that TUI remains an adapter.

Implementation rules:

- Do not scrape CLI output.
- Do not import infrastructure from TUI widgets/screens.
- Do not duplicate CLI rendering logic if it contains business semantics.
- Do not invent labels, thresholds, rankings, scores, buckets, or next-step
  recommendations in the adapter.
- Do not make AI mandatory.
- Do not let AI write config, apply patches, or override deterministic results.
- Do not expose learning/calibration panels as authoritative unless canonical
  observations and exact label binding are present for the selected scope.

## Recommended Immediate Next Task

Create a Phase 0 inventory document:

```text
docs/thought/tui_phase0_inventory.md
```

It should map:

```text
TUI screen -> existing CLI command -> existing application use case/DTO ->
missing application view contract -> S1/data-risk dependency -> test target
```

This keeps the first implementation small and prevents the TUI from inheriting
adapter-local CLI behavior.
