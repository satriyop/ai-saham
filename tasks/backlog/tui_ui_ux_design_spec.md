# TUI UI/UX Design Contract And Shell Alignment

Status: `DONE`

Roadmap: `docs/roadmap/roadmap_tui.md`

Prerequisite: TUI Phase 1 is `DONE`

Blocks: TUI Phases 3–5

## Task Metadata

- Task type: Design / UX specification with adapter-only alignment
- Priority: High
- Semantic classification: `NON_SEMANTIC`
- Chosen decision: adopt the screen, navigation, responsive, and visual
  contracts in this document. Implement this option only.

## Problem Statement

The TUI backlog defines architecture, data ownership, and screen behavior, but
does not fully constrain visual hierarchy, navigation, responsive layout,
keyboard interaction, or semantic styling. Phase 1 was completed before this
contract existed, and Phase 2 was implemented against the earlier behavioral
task. Without a binding UX design, later agents could create incompatible
layouts or hide authority and warning information.

## Desired Outcome

- Existing Phase 1 shell choices are audited without rewriting its completion
  history.
- The V1 information architecture, global keymap, screen hierarchy, responsive
  behavior, visual roles, state presentation, and accessibility behavior are
  fixed here.
- Phase 3 and Phase 4 implement their screens from these wireframes.
- Phase 5 verifies the resulting experience at all required sizes.
- Any shell alignment that can be completed without inventing future screens is
  implemented and tested in this task.

## Non-Goals

- No new business capability, screen data, provider, write action, AI, or
  background refresh.
- No redesign of application DTOs or use cases.
- No mouse-only interaction.
- No dashboard filled with one card per CLI command.
- No graphical charting or decorative animation.
- No change to canonical ordering, action wording, risk, readiness, or evidence
  authority.

## Current Implemented Baseline

Verified before this task was authored:

- `SahamTuiApp` uses Textual `Header` and `Footer`.
- Daily is pushed on mount; Help is a pushed screen.
- Global `q` quits.
- Daily binds `r`, `?`, and hidden alias `h`.
- Help binds `Esc` and hidden alias `d`.
- Daily uses one vertical scroll region with stacked sections.
- Phase 1 has a passing 80x24 Help navigation test.
- Generation-safe workers and offline behavior already exist and are not UX
  redesign targets.

Phase 1 remains `DONE`. This task may align its presentation but must not
invalidate or rewrite its architecture, packaging, worker, or completion record.

## Design Principles

1. Verdict first: authority, blockers, and canonical action precede supporting
   detail.
2. Progressive disclosure: overview first; evidence and diagnostics are opened
   deliberately.
3. Keyboard first: every action is visible in the Footer or Help.
4. Honest latency: LOADING, stale-result suppression, and retry are explicit.
5. No hidden mutation: Reload means local recomputation; navigation never runs
   a workflow.
6. Text before color: every semantic color has a visible text label.
7. Preserve terminal width: V1 has no persistent sidebar.
8. Canonical and preview outputs are never visually interchangeable.

## Information Architecture

V1 routes:

```text
Today
  -> Candidates
       -> Ticker Research
Research Health
Help (overlay/pushed screen from any route)
```

The main route labels are exactly:

- `Today`
- `Candidates`
- `Research`

Ticker Research is contextual detail, not a top-level route. Help is temporary
and returns to the previous screen.

## Global Shell Contract

V1 uses a full-width Header, content area, and contextual Footer. Do not add a
persistent navigation rail; it consumes too much of an 80-column terminal.

```text
┌ AI Saham · Today ───────────── OFFLINE · LQ45 · EOD 2026-07-21 ┐
│                                                                │
│                         active screen                          │
│                                                                │
├────────────────────────────────────────────────────────────────┤
│ 1 Today  2 Candidates  3 Research  r Reload  ? Help  q Quit   │
└────────────────────────────────────────────────────────────────┘
```

Header requirements:

- application name and active route/breadcrumb;
- `OFFLINE` always visible in V1;
- universe and effective/as-of date when known;
- detail breadcrumb uses `Candidates / BBRI`, not a new top-level label.

Footer requirements:

- show only actions valid on the current screen;
- use the same key label everywhere;
- critical navigation must not exist only in Help;
- hidden aliases may remain for compatibility but are not displayed.

## Binding Keymap

| Key | Action | Availability |
|---|---|---|
| `1` | Today | Global once route exists |
| `2` | Candidates | Global after Phase 3 |
| `3` | Research | Global after Phase 4 |
| `Up`/`Down`, `j`/`k` | Move selection or scroll | Lists/tables |
| `Enter` | Open selected item / submit focused form | Contextual |
| `Esc` | Back or close Help | Contextual |
| `Tab`/`Shift+Tab` | Move focus | Forms and focusable controls |
| `r` | Explicit local reload | Data screens only |
| `?` | Help | Global |
| `q` | Quit | Global |

Existing `h` for Help and `d` for Daily may remain hidden aliases. Do not assign
new behavior to them.

No action may be triggered by focus, hover, cursor movement, or selection
change alone.

## Responsive Contract

Supported minimum: 80x24.

| Width | Mode | Contract |
|---|---|---|
| 80–99 | Compact | Single column; only essential table columns; detail opens full-screen |
| 100–119 | Standard | Single-column sections with full core columns |
| 120+ | Wide | Two-pane/grid layout where specified |

Height rules:

- Header and Footer remain visible.
- Content scrolls vertically.
- Authority/blocker region is the first content region.
- Critical warnings must be reachable without horizontal scrolling.
- Never truncate ticker, canonical action, authority, risk, or data-state text.
- Secondary evidence may collapse or move to detail at compact width.

If terminal width is below 80, show an explicit minimum-size warning; do not
silently hide canonical or warning content.

## Visual Language

Use Textual theme variables and semantic CSS classes, not hard-coded RGB values.

| Role | Preferred semantic color | Required text |
|---|---|---|
| Ready / Open / Enter | success/green | `READY`, `OPEN`, `ENTER` |
| Partial / Watch | warning/amber | `PARTIAL`, `WATCH` |
| Not ready / Blocked / Error | error/red | `NOT_READY`, `BLOCKED`, `ERROR` |
| Unavailable / Missing | muted/gray | `UNAVAILABLE` or `MISSING` |
| Information / navigation | accent/cyan | descriptive label |
| Non-canonical preview | secondary/magenta | `NON-CANONICAL PREVIEW` |

Rules:

- Color never replaces text.
- No blinking.
- Animation is limited to a loading indicator.
- Section headings are concise uppercase labels.
- Warnings wrap; they are never ellipsized into invisibility.
- Numeric values align consistently; missing values render `—`, not zero.
- Use borders and whitespace to show hierarchy, not decorative boxes everywhere.

## Screen 1 — Today

### Content priority

1. Authority banner and blocking warnings.
2. Clocks and data readiness.
3. Market regime.
4. Accumulation summary and candidates.
5. Opening observations.
6. Setup-lens impact.
7. Detailed freshness and remaining warnings.

`NOT_READY` remains a valid loaded screen but replaces usable candidate rows
with the application's suppression/blocker explanation.

### Compact/standard wireframe

```text
┌ DATA AUTHORITY: PARTIAL ────────────────────────────────────────┐
│ 4/45 tickers stale · rankings have limited authority           │
└─────────────────────────────────────────────────────────────────┘

CLOCKS
Live session ...  Completed EOD ...  Opening snapshot ...

READINESS
Candles       PARTIAL 41/45
Broker flow   READY   45/45

REGIME
RISK_ON · conviction 0.72

ACCUMULATION
#  Ticker  Action  Signal/Cov  Risk     Data
1  BBRI    WATCH   68 / 82%    OPEN     CURRENT

OPENING
...

SETUP LENS
...

DETAILS / WARNINGS
...
```

### Wide wireframe

```text
┌ Authority and blockers — full width ────────────────────────────┐
├ Clocks ───────────────────────┬ Readiness ──────────────────────┤
├ Regime ───────────────────────┼ Freshness summary ──────────────┤
├ Accumulation candidates — full width ───────────────────────────┤
├ Opening ──────────────────────┬ Setup lens ─────────────────────┤
├ Detailed warnings — full width ─────────────────────────────────┤
```

The current Phase 2 stacked layout is an acceptable baseline. Before release,
its section order must follow this priority even if the wide grid is deferred.

## Screen 2 — Candidate Browser

Canonical projection order is preserved.

Compact columns:

```text
#  Ticker  Action  Signal/Cov  Risk  Data
```

Standard adds:

```text
Phase  Window
```

Wide layout:

```text
┌ Candidates (2/3 width) ───────┬ Selected preview (1/3 width) ──┐
│ canonical ordered table       │ ticker                         │
│                               │ canonical window               │
│                               │ phase / flow / warnings        │
└───────────────────────────────┴────────────────────────────────┘
```

Rules:

- Selected-row preview never causes another read.
- `Enter` opens Ticker Research.
- No interactive sorting in V1.
- Applied filters, counts, canonical window, and warnings remain accessible.
- Selection uses one clear highlight that remains legible without color.

## Screen 3 — Ticker Research

Canonical verdict is always first and remains visible before tabs/detail:

```text
BBRI · CANONICAL VERDICT
Action WATCH   Signal 68/100   Coverage 82%
Risk OPEN      Data CURRENT    Setup accumulation

[Overview] [Evidence] [Risk Gates] [Diagnostics] [Preview]
```

Exact detail sections:

- `Overview`: canonical verdict, freshness, setup, primary warnings.
- `Evidence`: application-provided setup, flow, sector, company, profile, and
  corporate-action evidence.
- `Risk Gates`: canonical OPEN/BLOCKED gates and reasons.
- `Diagnostics`: unavailable inputs, data freshness, broker/flow diagnostics,
  and informational refresh actions that cannot execute.
- `Preview`: visually distinct and headed `NON-CANONICAL PREVIEW`.

Compact mode uses a full-screen tab/section at a time. Wide mode may show
canonical overview beside the selected detail. Preview may never occupy the
canonical verdict region.

## Screen 4 — Research Corpus Health

```text
┌ DIAGNOSTIC ONLY — NOT PROMOTION EVIDENCE ───────────────────────┐
│ Target [......................................................] │
│ Cohort [......................................................] │
└─────────────────────────────────────────────────────────────────┘

Observations 120  Labels 74  IS 52  OOS 22
Diagnostic ready YES
Patch eligible    NO
Promotion eligible NO

BLOCKERS
...

EXCLUSIONS
Schema 4  Wrong cohort 18  Unavailable 9  Duplicate 3
```

The diagnostic banner and promotion status remain visible with metrics.
Unresolved multiple cohorts show a blocking selector state, never pooled data.

## Help

Help is a pushed screen/overlay and returns to the prior route with `Esc`.

It must contain:

- global navigation keys;
- current-screen keys;
- `Reload reads local cached inputs and never fetches provider data`;
- canonical versus preview meaning;
- research health diagnostic/non-promotion meaning once that route exists.

Help text grows with shipped routes; do not advertise unavailable screens.

## Screen-State UX

| State | Presentation |
|---|---|
| IDLE | Neutral instruction only when a screen requires input |
| LOADING | Keep shell visible; show operation and local-only scope |
| READY | Render canonical result and business authority separately |
| EMPTY | Explain successful empty result; never use success-looking fake rows |
| UNAVAILABLE | Name missing component/reason and preserve other valid content |
| ERROR | Inline alert with exact error class/message and explicit retry action |

Errors are inline, not modal, unless continuing would risk a consequential
action (outside V1). Reload does not clear the last good result until the new
generation succeeds; show it as stale/refreshing if retained.

## Content And Copy Rules

- Copy canonical actions, statuses, labels, reasons, dates, and warnings exactly.
- Presenter-written text may describe UI state only.
- Do not generate CLI commands, trading advice, next actions, or fallback verdicts.
- Use `—` for missing display values and `UNAVAILABLE` for meaningful absence.
- Show dates with their meaning, never an unlabeled date.
- Use `sessions`, not `days`, where the application contract uses sessions.

## Architecture And Data Constraints

- UI hierarchy does not change data ownership.
- Presenter maps one canonical response/projection to display models.
- Responsive hiding never causes a second query.
- Hidden compact columns remain available through detail, not recomputation.
- UI filters, if added later, cannot replace canonical ordering/rank.
- No component may import CLI displays or infrastructure outside composition.

## Phase 1 Post-Completion Alignment

Phase 1 remains complete. Audit it against this contract:

| Existing decision | Result |
|---|---|
| Header/Footer shell | Compatible; preserve |
| No sidebar | Compatible; preserve |
| `q`, `?`, hidden `h`, Help stack | Compatible |
| `Esc` and hidden `d` in Help | Compatible |
| 80x24 Help test | Compatible foundation |
| Route breadcrumb/offline context | Gap; align before Phase 5 |
| Global numeric navigation | Deferred until routes exist |
| Shared semantic CSS roles | Gap; add before Phase 3 styling |
| Help content for later routes | Deferred to owning phases |

Do not uncheck Phase 1 acceptance items. Record UX alignment as a dated
addendum in the Phase 1 task and implement remaining gaps through this task or
the named owning phase.

## Exact File Boundary For Alignment Work

Permitted:

- existing `src/adapters/tui/main.py`, shell CSS/state presentation, and Help;
- TUI-only semantic style helpers if justified;
- TUI headless/layout/accessibility tests;
- TUI task/roadmap documentation.

Forbidden:

- domain, application, infrastructure, repositories, config, or canonical DTOs;
- new data workflows or screens;
- changes to Phase 1 packaging/worker semantics unless a regression is proven.

## Implementation Checklist

- [x] Confirm Phase 1 remains `DONE`; do not rewrite its completion history.
- [x] Capture current shell behavior and sizes in the completion record.
- [x] Add the Phase 1 dated UX alignment addendum.
- [x] Align route title/breadcrumb and persistent OFFLINE context.
- [x] Define reusable semantic CSS roles without business calculations.
- [x] Update Help for only currently shipped routes.
- [x] Add headless assertions for 80x24 and 120x40 shell hierarchy.
- [x] Add text-without-color assertions for semantic states.
- [x] Update Phase 3–5 agents to treat this document as binding.

## Acceptance Criteria

- [x] Phase 1 completion status and evidence remain intact.
- [x] Shell uses Header/content/Footer with no sidebar.
- [x] Active route and OFFLINE context are visible.
- [x] Footer exposes only valid current actions.
- [x] 80x24 retains authority/warnings and usable navigation.
- [x] 120x40 supports the specified standard hierarchy.
- [x] Semantic meaning remains understandable without color.
- [x] Help advertises only shipped routes.
- [x] No UI interaction adds provider/write calls.
- [x] No canonical content or ordering is recalculated.
- [x] Phase 3, Phase 4, and Phase 5 tasks reference this contract.
- [x] Focused TUI tests, architecture tests, and `git diff --check` pass.
- [x] Status becomes `DONE`; completion record is filled.

## Required Negative Tests

- Header cannot omit OFFLINE in V1.
- Compact layout cannot hide authority, action, risk, data state, or warnings.
- Footer cannot advertise an unimplemented route.
- Color-stripped content retains READY/PARTIAL/NOT_READY and preview meaning.
- Focus/selection changes do not invoke a use case.
- Preview styling cannot use the canonical verdict container/class.
- Forbidden adapter imports remain rejected.

## Do Not Interpret This As

- Do not reopen or mark Phase 1 incomplete.
- Do not retrofit a sidebar.
- Do not implement Phase 3/4 data flows in this task.
- Do not prioritize visual polish over authority and warnings.
- Do not use color as the only distinction.
- Do not hide critical content to satisfy 80 columns.
- Do not invent business copy, ranking, or advice.
- Do not overwrite active Phase 2 work in the shared worktree.

## Architecture Impact

- Domain/Application/Infrastructure: not touched
- Adapter: shell presentation and Help alignment only
- Documentation/governance: binding UX contract and phase references
- New dependency: no
- Determinism/persistence/config/CLI behavior: unchanged
- AI usage: none

Layer plan:

```md
Layer plan:
- Domain: not touched
- Application: not touched
- Infrastructure: not touched
- Adapter: shell presentation/Help alignment only when implemented
```

## Verification

Run focused TUI headless tests at 80x24 and 120x40, TUI architecture tests,
color-independent text assertions, full tests when feasible, and
`git diff --check`.

## Agent Execution Protocol

Before editing source, restate the chosen shell, keymap, responsive modes,
semantic roles, exact files, and how Phase 1 evidence is preserved. Stop if
alignment requires business logic or an active Phase 2 file conflict. Check
items only from executed evidence.

## Completion Record

- Completed date: 2026-07-22
- Implementation commit: this UX alignment completion commit
- Phase 1 audit revision: `eef3838`; status and original completion evidence unchanged
- Existing decisions preserved: Header/Footer, no sidebar, Daily startup, pushed Help, local Reload, generation-safe workers, and hidden `h`/`d` aliases
- Alignment files changed: TUI app shell, Daily screen, Help, headless tests, and this completion record
- 80x24 result: Header/content/Footer, authority, warnings, and current navigation remain reachable
- 120x40 result: standard stacked hierarchy renders with active route and offline context
- Color-independent result: canonical READY/PARTIAL/NOT_READY and ERROR text remains explicit; preview has a separate reusable class and required text contract
- Focused tests: `34 passed` including TUI, boundary, and layer-boundary tests
- Architecture tests: `62 passed` for all architecture plus TUI tests
- `git diff --check`: passed
- Deferred route-owned items: Candidate/Ticker numeric route and preview surface belong to Phase 3; Research route belongs to Phase 4
