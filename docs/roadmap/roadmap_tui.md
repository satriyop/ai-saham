# Roadmap: Personal TUI Investing Workstation

Status: product reset / value-first roadmap

Last verified: 2026-07-22

Scope: a personal, local-first terminal workspace for daily IDX discovery,
decision support, validation, and review

## Product Decision

The TUI is not a visual catalog of CLI commands and not a place to expose
internal diagnostics. Its job is to remove friction from the repeated workflow
of one person using AI Saham to make and evaluate investing decisions.

The product loop is:

```text
update data
  -> understand the market
  -> discover and compare candidates
  -> inspect one ticker deeply
  -> validate the setup or strategy historically
  -> size and record a candidate/paper-trade plan
  -> review what worked
```

If a screen does not shorten or improve that loop, it does not belong in the
primary TUI.

The CLI remains the automation and advanced-operations interface. The TUI
reuses the same typed application contracts; it never shells out to CLI
commands or parses terminal output.

## Why The Previous Roadmap Was Wrong

The previous roadmap optimized for a narrow read-only implementation instead
of personal user value. It selected capabilities that were easy to wire while
excluding essential steps already present in the CLI:

- refreshing the data used for today's decisions;
- exploring a universe, not only a preselected shortlist;
- using the full accumulation filters and multi-window comparison;
- viewing price structure, RSI, volume, broker flow, and ticker context;
- testing a named swing setup across a universe;
- validating and backtesting a custom strategy;
- sizing, journaling, and reviewing paper-trade outcomes.

It also promoted Signal Corpus Health, an engineering/calibration diagnostic,
to a primary menu. That screen is rejected and governed by
`tasks/backlog/tui_remove_research_screen.md`.

Completed shell, worker-safety, Daily, candidate, and ticker code may be reused
where it supports this roadmap. Prior phase numbering is implementation history,
not the future product plan.

There is no generic hardening or release-decision phase. Every milestone must
be usable for a real personal workflow and carries its own quality checks.

## Evidence: Live CLI Capability Audit

The audit used live `saham --help` output, current CLI source, application use
cases, README workflows, and accepted ADRs. Command presence alone does not
earn TUI placement; the user job and interaction benefit must be clear.

| CLI capability | Actual user job | TUI value | Decision |
|---|---|---:|---|
| `fetch market`, `fetch status` | Make today's analysis current and understand missing data | Essential | First-class explicit Update workflow |
| `today` | Orient quickly: readiness, clocks, regime, candidates, warnings | High | Dashboard summary, not the whole product |
| `view universe` | Scan the market by flow, change, volume, or ticker | High | Market/Discovery table |
| `screen accum --multi` | Find institutional accumulation across 7/30/90 sessions | Essential | Core Discovery workspace |
| accumulation filters and sort | Narrow by score, streak, squeeze, VWAP, broker quality, setup | Essential | Visible filter bar and sortable table |
| `screen watchlist`, `screen compare` | Preserve a shortlist and see new/dropped/strengthening names | High | Saved screens and comparison view |
| `analyze swing` | Decide whether one ticker/setup is actionable and why | Essential | Core Ticker Workbench |
| `analyze chart price/rsi/volume` | Confirm price structure, momentum, and participation | High | Ticker tabs/panels |
| `view ticker flow/top-brokers/foreign-history/distribution` | Inspect institutional behavior behind a candidate | High | Ticker Flow tab |
| `view TICKER`, `analyze risk`, `analyze signal inspect` | Inspect cached context, risk gates, and canonical signal evidence | High | Progressive ticker evidence |
| `trade size` | Convert an entry idea into stop, target, capital risk, and lots | Essential | Position Plan panel |
| `trade backtest-swing`, `analyze swing-compare` | Test a named setup and compare variants/regimes | Essential | Setup Backtest |
| `strategy list/validate/backtest` | Select and test a personal rules package | Essential | Strategy Backtest |
| `trade log`, `trade review` | Record decisions and learn from forward outcomes | High | Journal/Review workspace |
| `screen pre-open`, `learn snapshot/track/grade` | Run the time-sensitive opening-session workflow | Conditional | Separate later workspace only for an active intraday user |
| signal corpus readiness/replay/capture | Maintain research evidence infrastructure | Low for daily investing | CLI engineering tools only |
| audit, provider diagnostics, migrations | Operate and repair the system | Low for normal decisions | CLI only; surface actionable status where needed |
| tuning apply, AI strategy creation, indicator authoring | Change policy/configuration | High risk and infrequent | CLI only until separately designed and guarded |

## User Outcomes

The roadmap is successful when the personal user can answer these questions
without leaving the TUI:

1. Is my data current enough to act on?
2. What is the current market regime and breadth?
3. Which stocks are accumulating across meaningful time windows?
4. What changed since my last shortlist?
5. Why is this ticker ENTER, WATCH, AVOID, or blocked?
6. Does the selected setup match, and which gates fail?
7. What do price, RSI, volume, and broker flow show?
8. How many lots fit my capital and risk limit?
9. Did this setup or strategy work over a chosen historical period?
10. What forward outcomes followed my recorded candidate decisions?

## Product Information Architecture

```text
Dashboard
  |- data freshness and explicit Update
  |- market regime and breadth
  `- today's shortlist and warnings

Discover
  |- Universe
  |- Accumulation
  `- Saved / Compare

Ticker Workbench  (opened from any ticker or global search)
  |- Overview
  |- Setup
  |- Chart
  |- Flow
  |- Signal & Risk
  `- Position Plan

Backtest
  |- Setup Backtest
  `- Strategy Backtest

Review
  |- Saved candidates
  |- Swing candidate journal
  `- Forward-outcome breakdowns

Help  (temporary overlay)
```

There is no top-level Research menu. “Ticker Workbench” means analysis of an
investment candidate. Signal-dataset research remains in the CLI.

## Shared Interaction Model

### Navigation

- Top-level destinations are always visible in a compact top bar or footer.
- `1` Dashboard, `2` Screen (CLI: saham screen), `3` Backtest, `4` Review.
- `/` opens ticker search from anywhere.
- `Enter` opens or executes the explicitly focused action.
- `Esc` returns to the previous context without losing the current result.
- `?` shows route-specific help; `q` quits.
- Ticker Workbench is contextual and keeps the originating candidate list,
  filters, selection, and scroll position when returning.

### Global context

Every relevant screen shows:

- active universe;
- effective/as-of trading date;
- cache freshness and last successful update;
- active capital and risk percentage when sizing/testing;
- current operation state: IDLE, RUNNING, READY, PARTIAL, EMPTY, or ERROR.

Raw configuration keys, target grammars, hashes, provider payloads, and CLI
flags are not normal form fields. Friendly controls retain exact typed values
internally. Advanced details may show exact identities read-only.

### Expensive and write-capable actions

- Selection, focus, sorting, and tab changes never start work.
- `Run`, `Update`, `Save`, and `Log` are explicit buttons/actions.
- Update shows its universe, provider plan, progress, partial failures, and
  stored dates. It must not masquerade as local Reload.
- Save and Log show the exact artifact to be written and report success/failure.
- No order execution is added.
- Tuning application, configuration editing, and AI-authored strategy changes
  remain outside this roadmap.

### Result design

- Verdict and blockers appear before supporting evidence.
- Candidate tables preserve canonical rank even when presentation sorting is
  changed.
- Missing evidence is visibly unavailable, never neutral-filled.
- Canonical live decisions, historical backtests, and optional previews use
  distinct labels and visual regions.
- Results remain visible while a user changes tabs; an explicit rerun replaces
  them only after a successful new result.
- Errors preserve the last valid result and identify which operation failed.

### Visual design language

The target is a calm, information-dense analytical workstation—inspired by professional terminal environments like Bloomberg Terminal, OpenBB, LazyGit, and K9s. It is not a neon gaming dashboard and not a plain dump of bordered widgets.

Milestone A owns the central design token system and shared `.tcss` component vocabulary. Route modules must consume these tokens and cannot introduce private palettes or raw color literals.

#### Design Tokens & Theme Palette (Nord-Inspired Slate Baseline)

| Category | Token Name | Value / Hex | Usage & Semantic Purpose |
|---|---|---|---|
| **Canvas** | `$canvas` | `#111318` | Base background; high contrast without harsh pure black |
| **Surface** | `$surface` | `#1a1d24` | Main panel / card backgrounds (tables, detail containers) |
| **Surface Raised** | `$surface-raised` | `#232732` | Modal dialogs, dropdowns, floating overlays |
| **Border Subtle** | `$border-subtle` | `#2e3440` | Subtle container outlines (`border: round $border-subtle;`) |
| **Border Active** | `$border-active` | `#88c0d0` / `#5e81ac` | High-visibility keyboard focus outline (`border: round $border-active;`) |
| **Text Primary** | `$text-primary` | `#e5e9f0` | Tickers, key metrics, active values (`bold`) |
| **Text Secondary** | `$text-secondary` | `#d8dee9` | Table cells, body labels |
| **Text Muted** | `$text-muted` | `#6c7a96` | Subtitles, column headers, inactive shortcuts |
| **Text Accent** | `$text-accent` | `#88c0d0` | Route headings, tab selection, action buttons |

#### Financial Signal & Status Tokens (Text + Symbol + Color)

Color reinforces status but never carries status alone. Every status display combines explicit text/symbols with semantic color to preserve 100% clarity on monochrome or colorblind terminals:

| Signal / Status | Semantic Color | Symbol & Text | Context & Example |
|---|---|---|---|
| **Bullish / Ready** | `$status-bullish` (`#a3be8c` Green) | `▲ ENTER` / `READY` / `MATCH` | Actionable setup, ready cache, matching gate |
| **Caution / Watch** | `$status-caution` (`#ebcb8b` Amber) | `◆ WATCH` / `PARTIAL` / `STALE` | Partial setup fit, stale data, warning gate |
| **Bearish / Blocked** | `$status-bearish` (`#bf616a` Crimson) | `▼ AVOID` / `BLOCKED` / `ERROR` | Failed risk gate, avoid verdict, system error |
| **Unavailable** | `$status-unavailable` (`#4c566a` Muted) | `— UNAVAILABLE` | Missing candle/flow input (never zero-filled) |
| **Preview** | `$status-preview` (`#b48ead` Purple) | `⚡ NON-CANONICAL PREVIEW` | Backtest or non-authoritative preview |

#### Interactive Component Specs

- **Selected Table Row**: Uses `$surface-raised` background + bold text + a left-edge indicator bar (`│ BBRI ...`).
- **Focus Ring**: Every active focusable widget (inputs, table, buttons, tabs) displays a prominent `$border-active` outline (`border: round $border-active;`).
- **Modal Confirmation Cards**: Center-aligned overlay cards (`width: 64`, `border: thick $text-accent`) with explicit action badges (`[ WRITE ACTION: Cache Update ]`).
- **Terminal Charting**: Sparklines and volume bars use unicode 8-level block characters (`  ▂ ▃ ▄ ▅ ▆ ▇ █`). Price/RSI series use smooth box-drawing lines (`─│┌┐└┘├┤┼`) with explicit horizontal threshold markers (`--- 70 OVERBOUGHT ---`).
- **Numeric Alignment**: Numeric columns are right-aligned with fixed precision; dates, tickers, and status labels remain left/center aligned to prevent visual jitter.

#### Vertical Line Budgeting for Minimum 80x24 Viewport

To ensure zero clipping on the supported **80x24 minimum terminal**, screens adhere to a strict 24-line vertical allocation:

```text
Line 01    : Application Header & Status Context (Fixed)
Line 02-04 : Decision / Verdict Strip (Fixed)
Line 05    : Workspace Tab Bar / Navigation (Fixed)
Line 06-22 : Scrollable Active Workspace Content (17 lines)
Line 23-24 : Action Bar & Footer Keyboard Hints (Fixed)
Total      : 24 lines (Zero vertical clipping)
```

Visual polish is part of implementation, not a later release phase. Each milestone must supply deterministic visual snapshots or equivalent rendered-screen evidence at `80x24` and `120x40`, including one non-happy state. Baselines are produced by the headless renderer from fixed fixtures and stored with tests; manually captured screenshots alone do not satisfy acceptance.

## Core Screen Designs

### Dashboard

```text
 AI Saham  Dashboard   LQ45   EOD 2026-07-21   DATA: STALE 1d   [Update]
 -----------------------------------------------------------------------
 MARKET        SIDEWAYS   breadth 56%   foreign breadth improving
 DATA          candles 45/45   broker 43/45   enrichment 38/45
 WARNINGS      2 tickers missing broker flow

 TODAY'S CANDIDATES
 #  Ticker  Pattern       7s   30s  90s  Setup     Risk     Data
 1  BBRI    building      74   68   61   MATCH     OPEN     READY
 2  BMRI    coiled spring 71   64   55   PARTIAL   OPEN     READY

 [Open Discover]   [Open selected ticker]
```

The dashboard is a launchpad. It does not dump every DailyBriefing field into
one scrolling page. Details open in the owning workspace.

### Screen (CLI: `saham screen`)

Maps 1:1 to the CLI screen family. Nav key `2` / route label: **Screen**.
Code: `ScreenWorkspaceScreen`, `ScreenController`, `ScreenPresenter`.

```text
 SCREEN  [Universe] [Accumulation] [Saved / Compare]
 Universe [LQ45]  Windows [7,30,90]  Min score [50]
 [ ] Squeeze  [ ] Foreign underwater  Sort [Canonical]       [Run]
 -----------------------------------------------------------------------
 #  Ticker  Pattern       7s   30s  90s  Flow%  VWAP  Signal Risk  Data
 1  BBRI    building      74   68   61    18%   +4%   STRONG OPEN  READY

 Selected: flow trend, broker-quality summary, failed gates, freshness
 [Open ticker] [Save shortlist] [Compare saved]
```

This screen exposes the useful `screen accum` controls instead of hard-coding
one request. A separate Universe tab supports flow/change/volume browsing even
when a ticker is not already shortlisted.

### Ticker Workbench

```text
 BBRI  4,840  +1.2%   DATA READY   Setup [foreign-bounce]   [Run analysis]
 VERDICT  ENTER   Signal STRONG 74   Risk OPEN   Setup MATCH
 BLOCKERS none
 -----------------------------------------------------------------------
 [Overview] [Setup] [Chart] [Flow] [Signal & Risk] [Position Plan]
```

- Overview: canonical `TradeSetup`, freshness, key evidence, warnings.
- Setup: selected setup, MATCH/PARTIAL/NO_MATCH, every passed/failed gate.
- Chart: price with SMA/EMA, RSI, and volume over selectable periods.
- Flow: daily foreign flow, VWAP context, top brokers, history/distribution.
- Signal & Risk: canonical components, coverage, unavailable inputs, gates.
- Position Plan: capital, risk %, entry, stop, target, lots, max hold, and
  invalidation; explicit candidate/plan Log action.

Global ticker search must open this workbench even when the ticker did not come
from the current candidate list.

### Backtest

```text
 BACKTEST  [Setup Backtest] [Strategy Backtest]

 Setup [foreign-bounce]  Universe [LQ45]  2025-01-01 -> 2026-07-21
 Capital [100,000,000] Risk [1%] TP [5%] SL [5%] Hold [20] Cost [20 bps]
 [ ] Regime attribution                                      [Run backtest]
 -----------------------------------------------------------------------
 Return 12.4%  Drawdown -6.1%  Trades 38  Win 55%  PF 1.31  Exposure 42%
 [Equity] [Trades] [Regimes] [Attribution] [Compare runs]
```

Setup Backtest uses `SwingBacktestUseCase`. Strategy Backtest uses
`BacktestUseCase` after selecting an existing validated strategy, ticker,
period, and capital. The UI must show which parameters are defaults and which
the user changed.

Backtest output is historical evidence, never a current ENTER/WATCH/AVOID
verdict. Comparisons retain the full request identity for each run so differing
dates, costs, universes, and parameters cannot be mistaken for like-for-like
results.

Strategy authoring and tuning are not required to gain value from Backtest. The
first useful version lists strategies, shows validation errors, runs tests, and
compares results. Editing YAML remains an external/CLI workflow.

### Review

```text
 REVIEW  [Saved Candidates] [Swing Journal]
 Period [Last 90 sessions]  Setup [All]  Regime [All]
 -----------------------------------------------------------------------
 Recorded 24  Forward-evaluated 18  Awaiting data 6
 Avg 10-session return +2.1%  Avg max drawdown -5.4%
 [By setup] [By score] [By regime] [Entry list]
```

Review closes the loop. It must use persisted watchlist/journal artifacts and
existing application workflows; it must not infer unrecorded trades or rewrite
outcomes.

## Application Contract Readiness

| Journey | Current reusable boundary | Readiness / required work |
|---|---|---|
| Dashboard | `DailyBriefingUseCase` | Reusable; redesign presentation hierarchy |
| Data Update | `FetchMarketCommandWorkflowUseCase` | Reusable core; add an application-owned update-and-recompute result if one action must refresh Dashboard |
| Universe | `build_universe_view` / universe summary types | Reusable but normalize function-style boundary if needed |
| Accumulation | `RunAccumulationScreenWorkflowUseCase` | Reusable single/multi projections and filters |
| Save shortlist | `SaveScreenWatchlistUseCase` | Reusable explicit write |
| List/compare shortlist | current CLI reads repository and orchestrates comparison inline | Extract business-named application query/workflow before TUI wiring |
| Ticker verdict | `SwingAnalysisWorkflowUseCase` | Reusable; expose user-selected setup/detail/refresh options |
| Risk comparison | `RunRiskCompareUseCase` | Reusable for comparison where valuable |
| Ticker dashboard | current `view TICKER` is adapter/display-oriented | Extract typed application response; never import its display module |
| Broker flow | `GetBrokerDataUseCase` plus repository-backed CLI views | Reuse typed boundary; extract typed queries for top/history/distribution where absent |
| Charts | current chart commands are adapter-oriented | Add a typed chart-series application query; do not parse ASCII output |
| Position sizing | `compute_position_size` service | Wrap in a business-named application use case for typed request/response and validation |
| Setup Backtest | `SwingBacktestUseCase` | Reusable; composition/config resolution must move behind a non-CLI boundary |
| Strategy Backtest | `BacktestUseCase`, `StrategyLoader` | Reusable; add typed list/validation query contracts where needed |
| Candidate/plan log | `LogAccumulationTradeWorkflowUseCase` / `LogSwingCandidateUseCase` | Reusable explicit write with confirmation/result; does not prove execution |
| Review | existing trade-review CLI paths | Audit and extract typed application queries before TUI wiring |

An existing Rich display or CLI helper is not an application contract. When a
row says extraction is required, that extraction is part of the milestone and
must be independently useful to another adapter.

## Value-Ordered Milestones

These are product milestones, not the previous numbered phases.

### Milestone A — Personal Command Center

User value: open one workspace, see whether data is usable, update it explicitly,
understand the market, and reach today's candidates.

Scope:

- redesign Dashboard around readiness, market pulse, warnings, and shortlist;
- select universe and effective date;
- add explicit market-data Update with progress and partial-failure reporting;
- recompute Dashboard from the resulting application-owned workflow result;
- establish the shared semantic theme, shell, reusable visual primitives, and
  responsive/minimum-size policy consumed by Milestones B–E;
- retain optional dependency, worker cancellation, and late-result safety.

Value acceptance:

- the user can go from stale cache to an updated actionable Dashboard without
  opening another terminal command;
- the screen makes stale, partial, and current data impossible to confuse;
- the shared shell is visually coherent, keyboard-first, readable in
  monochrome, and intentionally composed at both `80x24` and `120x40`;
- Update never runs on mount, focus, or local Reload;
- provider/write behavior is explicit and tested with disposable storage.

Backlog file: removed 2026-07-27 (re-spec from this roadmap when implementing).

### Milestone B — Candidate Discovery Workbench

User value: scan the market, run the full accumulation workflow, narrow the
list, preserve a shortlist, and see what changed.

Scope:

- Universe and Accumulation tabs;
- universe/window/filter/sort controls matching useful live CLI capabilities;
- canonical-rank preservation and visible presentation sorting;
- candidate preview with pattern, flow, setup/risk, and freshness;
- save shortlist and compare against a new run;
- restore list/filter/selection state after ticker drilldown.

Value acceptance:

- the user can reproduce the useful `screen accum --multi` workflow without
  typing opaque flags;
- all filters are application-owned and execute only on explicit Run;
- saved comparison clearly separates new, dropped, strengthening, weakening,
  and unchanged tickers;
- opening a ticker requires no second candidate computation.

Backlog file: removed 2026-07-27 (re-spec from this roadmap when implementing).

### Milestone C — Ticker Decision Workbench

User value: understand one candidate completely and turn it into a risk-sized
paper-trade plan.

Scope:

- global ticker search;
- selectable setup and analysis options;
- Overview, Setup, Chart, Flow, Signal & Risk, and Position Plan tabs;
- explicit cached analysis versus provider refresh choice;
- typed chart and ticker-dashboard application queries where missing;
- explicit candidate/plan Log action.

Value acceptance:

- the user can complete discovery -> analysis -> chart/flow confirmation ->
  sizing without leaving the TUI;
- canonical verdict, setup fit, historical evidence, and optional preview are
  visually and semantically separate;
- changing a tab or input does not silently rerun analysis;
- logged data is shown before confirmation and exact success/failure is visible.

Backlog file: removed 2026-07-27 (re-spec from this roadmap when implementing).

### Milestone D — Backtest Workspace

User value: test whether a setup or personal strategy has historical support
before relying on it.

Scope:

- Setup Backtest over ticker(s)/universe with date, cost, capital, risk,
  TP/SL, hold, positions, and regime controls;
- Strategy list and validation status;
- Strategy Backtest for ticker, period, and capital;
- summary metrics, equity curve, trade list, regime/attribution views;
- compare pinned runs with full parameter identity.

Value acceptance:

- setup and strategy testing are distinct and named correctly;
- invalid strategy/setup/input combinations fail before expensive work;
- every result shows universe/ticker, period, costs, parameters, and warnings;
- comparisons never hide differing inputs;
- no backtest result is presented as a live trade verdict.

Backlog file: removed 2026-07-27 (re-spec from this roadmap when implementing).

### Milestone E — Journal And Review

User value: close the learning loop using personal recorded candidates and
their derived forward outcomes.

Scope:

- saved-candidate history;
- swing candidate-journal list and detail;
- explicit derived forward-outcome enrichment, clearly disclosed as a journal
  write;
- breakdown by setup, score/pattern, regime, and horizon;
- links back to ticker and originating evidence when provenance exists.

Value acceptance:

- all metrics reconcile to exact journal records;
- evaluated, awaiting-data, and unavailable outcomes remain distinct;
- the TUI never treats planned prices as executed entries/exits or fabricates
  missing provenance;
- review identifies repeatable strengths and failures without AI authority.

Backlog file: removed 2026-07-27 (re-spec from this roadmap when implementing).

## Deferred Until Personally Needed

### Opening Session Workspace

`screen pre-open` plus `learn snapshot/track/grade` is a real workflow, but it
is time-sensitive and operationally different from swing analysis. Add it only
if the personal user actively trades the opening session. Its UI must follow the
NCP clock and preserve snapshot/confirmation artifact identities.

### Authoring And Tuning

Strategy creation, indicator formula editing, tuning proposals, config diffs,
and patch application remain CLI/file workflows. They are infrequent,
write-sensitive, and need a separate design if personal usage proves the TUI
would materially improve them.

## Explicitly Excluded

- Signal corpus health, capture, labeling, replay, and readiness screens.
- Data-quality audits, migration controls, raw database browsing, and provider
  debugging consoles.
- A generic command launcher that merely mirrors the CLI tree.
- Shell command execution or parsing CLI/Rich output.
- Automated order placement or broker execution.
- AI chat as a navigation layer or source of canonical decisions.
- Automatic tuning/config application.
- Background actions triggered by focus, selection, or navigation.

## Architecture And Safety Contract

```text
CLI adapter ----\
                 -> application use cases -> domain/ports -> infrastructure
TUI adapter ----/
```

- Screens own navigation, focus, input collection, and explicit action timing.
- Controllers invoke one injected application capability and manage UI request
  generations/cancellation.
- Presenters format typed results; they do not calculate scores, filters,
  verdicts, readiness, backtest metrics, or journal outcomes.
- Application use cases own cross-step workflow, validation, persistence policy,
  and typed results.
- Only TUI composition may construct infrastructure dependencies.
- No TUI module imports CLI commands/displays, `sqlite3`, provider clients,
  config loaders, subprocess, or direct filesystem persistence.
- Same typed input and persisted state must produce the same deterministic
  result regardless of CLI or TUI adapter.
- AI and network failures cannot replace deterministic results with invented
  fallbacks.

Write-capable tasks must name the data written, confirmation rule, idempotency
key, partial-failure behavior, and disposable test storage. Fetch cache writes,
watchlist saves, and journal logs are separate explicit actions; authorization
for one does not authorize the others.

## Quality Is Part Of Every Milestone

There is no separate quality-only milestone. Every backlog task must include:

- keyboard-only behavior at 80x24 and 120x40;
- conformance to the shared theme/components with no route-private palette;
- deterministic rendered-screen evidence at both supported sizes, including a
  non-happy state and monochrome/status-text verification;
- exact loading, partial, empty, unavailable, validation, and error states;
- generation-safe workers and late-result rejection;
- thin-adapter and forbidden-import tests;
- no work on focus/selection/navigation;
- authority separation between live verdicts, setup fit, previews, and
  historical backtests;
- focused application/controller/presenter/headless tests;
- preservation of unrelated shared-worktree changes;
- `git diff --check` and full-suite evidence when feasible.

Packaging and CI remain normal Definition-of-Done concerns. They do not decide
whether a low-value feature deserves to exist.

## Backlog Reset

- Completed TUI Phase 0–5 / research-screen docs live under `tasks/done/`
  (implementation history only).
- Active TUI design token / shell contract retained as
  `tasks/backlog/tui_ui_ux_design_spec.md` (route scope still subordinate to this
  roadmap).
- Milestone A–E task files under `tasks/backlog/tui_*.md` were **removed
  2026-07-27** as stale product contracts; re-author from this roadmap before
  implementation (do not resurrect deleted files without re-vetting current code).

## Immediate Order Of Work

1. Treat remaining Research Health cleanup as historical if already done; do not
   revive rejected TUI research-health scope.
2. When resuming TUI product work: re-spec Milestone A (Personal Command Center)
   from this roadmap + design-spec tokens, then implement.
3. Draft Milestone B only after the Command Center workflow is usable.
4. Build the Ticker Workbench before adding low-frequency diagnostics.
5. Build Backtest around actual setup/strategy backtests, not generic forms.
6. Add Review only from exact existing journal/watchlist provenance.

At every step, ask one product question first:

> Which real decision becomes faster, clearer, or safer for the personal user?

If the answer is unclear, do not add the screen.
