# Backlog: `saham today` Daily Briefing Improvements

**Source thought doc:** `tasks/thought/saham_today_improvement.md` (initial code verification: 2026-07-14)
**Current validation:** 2026-07-16 — rechecked after T11 cleanup (commit `5973749`).
**Code-verified against:** `src/adapters/cli/today_commands.py`, `src/application/use_case/daily_briefing_use_case.py`, `src/adapters/cli/view_market_context_display.py`, `tests/adapters/cli/test_today_commands.py`

---

> [!IMPORTANT]
> Before starting any task: read `AGENT_QUICKSTART.md`, confirm `AGENTS.md` / `GEMINI.md` compliance, and state the layer plan.
> These tasks involve the user-facing daily briefing. Adapters must stay thin. All workflow, policy, and readiness decisions belong in application use cases.

---

## Status at Current Validation Date (2026-07-16)

| Finding | Status |
|---------|--------|
| CLI startup broken (`src.application.domain` import) | ✅ RESOLVED |
| CLI smoke tests (`saham --help`, `saham today --help`) | ✅ `b3c6de1` — `test_cli_help_exits_zero`, `test_today_help_exits_zero` added |
| Three-clock date separation | ✅ RESOLVED |
| Fail-closed per-dataset readiness | ✅ RESOLVED — derived from shared freshness status and suppressed accumulation when NOT_READY |
| Universe scope enforcement in pre-open | ❌ Open |
| Verdict-first pre-open section title | ❌ Open — section is still "Top Pre-Open Candidates" |
| Canonical accumulation funnel with Signal/Risk/TradeSetup | ❌ Open — `Score` is still `foreign_flow_score` |
| Bounded setup-lens impact for accumulation candidates | ✅ Resolved |
| Honest market context (`RISK_ON` not aliased to `BULLISH`) | ✅ RESOLVED — `_market_regime_text` renders canonical values directly |
| Primary verdict header (DATA STATUS / POSTURE / ACTION) |  SKIP IT |
| Session-aware next action | ✅ Resolved — stale static `saham analyze swing TICKER` footer removed. Concrete setup-lens next commands come from T8; fallback footer now uses existing response fields only. |
| Warning severity (BLOCKER / WARNING / INFO) | ❌ Open — 5-row plain list |
| Rich `[local_clock]` markup bug | ✅ `b3c6de1` — fixed; uses `rich.text.Text` instead of f-string markup |
| Historical mode date separation | ✅ RESOLVED |

---

## Current Verification Notes (2026-07-16)

- T1 ✅ (`b3c6de1`): `src/adapters/cli/today_commands.py` now uses `rich.text.Text` to render the source tag as plain text.
- T2 ✅ (`b3c6de1`): `tests/adapters/cli/test_today_commands.py` has `test_cli_help_exits_zero`, `test_today_help_exits_zero`, and `test_today_shows_market_source_tag`.
- T3 ✅: Implemented clean-break date separation (live_session_date, latest_completed_eod_date, opening_snapshot_date, is_historical), decoupled from as_of_date, and suppressed market status in historical mode.
- T4 ✅: Fail-closed per-dataset readiness derived from shared freshness status, suppressed accumulation candidates when NOT_READY, warning message on PARTIAL/NOT_READY, and rendered readiness table.
- T13 ✅: Historical mode conditional rendering suppresses live market status and displays historical mode label.
- `src/application/use_case/daily_briefing_use_case.py` has three clocks (`live_session_date`, `latest_completed_eod_date`, `opening_snapshot_date`) and `is_historical` flag.
- Screen backlog S3 already introduced `src/domain/value_objects/data_freshness_status.py` and `src/application/services/data_freshness_service.py`; today work reuses these.
- `src/application/use_case/daily_briefing_use_case.py` still reads opening snapshot candidates without universe filtering, so T5 remains valid.
- T11 ✅ (`5973749`): Stale `saham analyze swing TICKER` footer removed. `_setup_lens_impact_elements` returns `SetupLensImpactRender` dataclass; `_fallback_next_command` helper provides 3-tier fallback. Old stale footer logic deleted.
- `src/adapters/cli/today_commands.py` still renders plain capped warnings, so T10/T12 remain valid. T6/T7/T8/T9/T11 are resolved (see their sections for as-built notes).

---

## Execution Order

| # | Task ID | Priority | Type | Description | Status |
|--:|---------|----------|------|-------------|--------|
| 1 | `T1` | P0 | Bugfix | Fix Rich `[source]` markup rendering bug | ✅ `b3c6de1` |
| 2 | `T2` | P0 | Bugfix | Add remaining CLI smoke tests | ✅ `b3c6de1` |
| 3 | `T3` | P0 | Refactor | Separate three date clocks in briefing use case | ✅ RESOLVED |
| 4 | `T4` | P0 | Feature | Fail-closed per-dataset readiness + ranking suppression | ✅ RESOLVED |
| 5 | `T5` | P0 | Bugfix | Enforce universe scope in pre-open opening candidates | ✅ RESOLVED |
| 6 | `T6` | P0 | Refactor | Rename to verdict-first pre-open presentation | ✅ RESOLVED |
| 7 | `T7` | P0 | Feature | Canonical accumulation funnel (Signal + Risk + TradeSetup) | ✅ Done |
| 8 | `T8` | P0 | Feature | Bounded setup-lens impact for accumulation candidates | ✅ Done |
| 9 | `T9` | P1 | Refactor | Expose honest market context (stop aliasing RISK_ON→BULLISH) | ✅ Done |
| 10 | `T10` | P1 | Feature | Primary verdict header before tables | ❌ Open |
| 11 | `T11` | P1 | Feature | Session-aware IDX lifecycle next action | ✅ Resolved — reduced to cleanup: stale static `saham analyze swing TICKER` footer removed. Concrete setup-lens next commands come from T8; fallback footer now uses existing response fields only. |
| 12 | `T12` | P1 | Refactor | Warning severity (BLOCKER / WARNING / INFO) | ❌ Open |
| 13 | `T13` | P2 | Bugfix | Historical mode: separate or omit live market status | ✅ RESOLVED |

> **Note:** T8 must not introduce a local ranking/scoring policy. It must reuse
> canonical swing/setup/trade-setup logic and remain bounded to the existing
> accumulation candidates shown by `saham today`.

---

## Task T1 — Fix Rich `[source]` Markup Rendering Bug

### Metadata

- **Type:** Bugfix
- **Priority:** P0 (display correctness)
- **Effort:** Small — single-line fix

### Problem

`today_commands.py:127` builds the market status string using f-string interpolation:

```python
market_text = (
    f"[{market_style}]{market_status.session_name}[/{market_style}]  "
    f"[{market_status.source}]"
)
```

`market_status.source` is `"local_clock"` or `"stockbit"`. When passed to Rich as part of a markup string, `[local_clock]` is interpreted as a Rich style tag and silently discarded because `local_clock` is not a valid style name. The source attribution disappears from terminal output.

Key file: `src/adapters/cli/today_commands.py:127`

### Desired Outcome

Source attribution is rendered as visible plain text in the output.
Use `rich.markup.escape(market_status.source)` or a `rich.text.Text` object to render the source without markup interpretation.

Example correct output:
```
Market    Regular / open  [local_clock]  ⚠ open
```

### Non-Goals

- No change to `MarketStatus` value object.
- No change to market time logic.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: not touched
- Application: not touched
- Infrastructure: not touched
- Adapter: today_commands.py (market_text construction only)
```

### Acceptance Criteria

- [x] Source tag is visible in terminal output
- [x] No Rich markup exception
- [x] Existing `test_today_commands.py` still passes
- [x] `git diff --check` clean

---

## Task T2 — Add Remaining CLI Smoke Tests

### Metadata

- **Type:** Test / Bugfix
- **Priority:** P0
- **Effort:** Small

### Problem

The CLI import blocker is resolved, but no test asserts:
- `saham --help` exits 0
- `saham today --help` exits 0

`test_today_commands.py` currently only tests the full `today` subcommand output.
A regression in CLI registration (e.g., a broken `analyze_commands.py` import) would go undetected until runtime.

Key file: `tests/adapters/cli/test_today_commands.py` — needs additions.

### Desired Outcome

- `test_cli_help_exits_zero()`: invokes `saham --help` via `CliRunner` and asserts `exit_code == 0`.
- `test_today_help_exits_zero()`: invokes `saham today --help` and asserts `exit_code == 0`.

### Non-Goals

- No production code changes.
- No lazy registration refactor in this task.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: not touched
- Application: not touched
- Infrastructure: not touched
- Adapter: tests/adapters/cli/test_today_commands.py (additions only)
```

### Acceptance Criteria

- [x] `test_cli_help_exits_zero` passes
- [x] `test_today_help_exits_zero` passes
- [x] All existing tests pass
- [x] `git diff --check` clean

---

## Task T3 — Separate Three Date Clocks in the Briefing Use Case

### Metadata

- **Type:** Refactor
- **Priority:** P0 — affects whether users understand if current-session vs completed-EOD data is being shown

### Problem

`DailyBriefingUseCase` and `DailyBriefingResponse` use a single `as_of_date` for all datasets:

- `daily_briefing_use_case.py:83` — `as_of = request.as_of_date or date.today()`
- `daily_briefing_use_case.py:86` — weekend rollback using only Saturday/Sunday, not IDX calendar
- `daily_briefing_use_case.py:101` — staleness check compares candle date against `as_of`

The briefing does not distinguish:
- `live_session_date` — what day it is today (for opening snapshot, live market status)
- `latest_completed_eod_date` — last fully completed IDX trading session (for candle/broker/MCE analysis)
- `opening_snapshot_date` — date of the loaded opening snapshot file

During a regular trading day, completed candles are from the prior session. Reporting 4/45 as "stale" against today's date is misleading.

Key files:
- `src/application/use_case/daily_briefing_use_case.py:83-107` — date derivation and staleness check
- `src/application/use_case/daily_briefing_use_case.py:54-63` — `DailyBriefingResponse` DTO

### Constraint From Screen Freshness Work

Screen backlog S3 already created:
- `src/domain/value_objects/data_freshness_status.py`
- `src/application/services/data_freshness_service.py`

Do not create a second freshness/status model for `today`. Reuse `compute_data_freshness()` / `DataFreshnessStatus` for source freshness and add only the minimum `today`-specific response fields needed for briefing clocks and authority.

### Calendar Decision

Use the existing local/weekend behavior unless a separate IDX calendar task is explicitly approved. Do not introduce network calendar lookup. If IDX holiday handling is added later, it must be local and injected; it must not be hidden inside the adapter.

### Desired Outcome

`DailyBriefingResponse` carries three separate date fields plus historical mode:

```python
live_session_date: date          # today's date (or request date)
latest_completed_eod_date: date  # last IDX session with complete candle data
opening_snapshot_date: date | None  # from snapshot file captured_at, or None
is_historical: bool
```

The staleness check for EOD-dependent features (candle coverage, broker flow, MCE) uses `latest_completed_eod_date`, not `live_session_date`, and should call the shared freshness service rather than reimplementing freshness loops locally.

Historical `--date` mode sets `live_session_date = request.as_of_date` and marks the briefing as `HISTORICAL` mode in the response so the adapter can suppress live market status display.

### Non-Goals

- No change to what data is fetched or how candles are stored.
- No network calls.
- No change to opening snapshot file format.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: reuse DataFreshnessStatus; do not add a duplicate freshness value object
- Application: daily_briefing_use_case.py — DailyBriefingResponse DTO, execute() date derivation, staleness check via data_freshness_service
- Infrastructure: not touched for this task unless an explicitly approved local calendar provider already exists
- Adapter: today_commands.py — render three dates and HISTORICAL mode label
```

### Acceptance Criteria

- [x] `DailyBriefingResponse` has `live_session_date`, `latest_completed_eod_date`, `opening_snapshot_date`
- [x] `DailyBriefingResponse` has `is_historical: bool`
- [x] Staleness check for candles uses `latest_completed_eod_date`
- [x] Freshness calculation reuses `compute_data_freshness()` / `DataFreshnessStatus`; no duplicate freshness service/value object is introduced
- [x] Historical mode sets `is_historical: bool = True` in response
- [x] Adapter renders three dates and suppresses live market status in historical mode
- [x] Regression test: weekend today → correct `latest_completed_eod_date`
- [x] Test: historical `--date` mode sets `is_historical = True`
- [x] Full test suite passes
- [x] `git diff --check` clean

---

## Task T4 — Fail-Closed Per-Dataset Readiness with Ranking Suppression

### Metadata

- **Type:** Feature
- **Priority:** P0 — currently shows accumulation rankings when only 4/45 tickers have current candles

### Problem

`daily_briefing_use_case.py:101`:
```python
stale_count = sum(1 for item in freshness if item.latest_date != as_of)
```

This is a single binary check (date matches or not) against a single `as_of` date.
The briefing continues to display rankings even when coverage is 4/45.
A warning row below a colored ranking table does not fail closed.

The design requires separate readiness per dataset:
- Completed candles (for accumulation/signal)
- Broker/foreign flow
- Market context (regime)
- Opening snapshot
- Point-in-time enrichment

### Desired Outcome

A `DataReadiness` value object or dataclass in the application layer that is derived from the shared freshness status and carries:
```python
dataset: str
required_as_of: date
coverage_count: int
total_count: int
status: Literal["READY", "PARTIAL", "NOT_READY", "UNAVAILABLE"]
reason: str | None
```

`DailyBriefingResponse` carries:
- `readiness_items: list[DataReadiness]`
- `overall_authority: Literal["READY", "PARTIAL", "NOT_READY"]`

If `overall_authority` is `NOT_READY`, the accumulation and swing sections are suppressed.
If `PARTIAL`, sections are shown with explicit quarantine labeling.

The adapter renders a readiness table before any ranking sections.

`DataReadiness` is the briefing authority projection, not a replacement for `DataFreshnessStatus`. Keep the raw freshness semantics in the shared service and derive suppression/quarantine policy in the briefing use case.

### Non-Goals

- No new data fetches.
- No new data providers.
- No changes to how broker or candle data is stored.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: reuse DataFreshnessStatus; do not add another source freshness enum
- Application: daily_briefing_use_case.py — DataReadiness projection, readiness calculation, suppression policy, response DTO
- Infrastructure: not touched
- Adapter: today_commands.py — render readiness table; suppress/quarantine affected sections
```

### Acceptance Criteria

- [x] `DailyBriefingResponse.overall_authority` is `NOT_READY` when candle coverage < policy minimum
- [x] Readiness is derived from shared freshness status; no duplicate freshness calculation loop is introduced
- [x] Accumulation table is suppressed (not just warned) when `NOT_READY`
- [x] Readiness table is shown before accumulation/swing sections
- [x] Test: candle coverage 4/45 → `NOT_READY` → accumulation suppressed
- [x] Full test suite passes
- [x] `git diff --check` clean

---

## Task T5 — Enforce Universe Scope in Pre-Open Opening Candidates

### Metadata

- **Type:** Bugfix
- **Priority:** P0 — LQ45 briefing currently shows non-LQ45 names without labeling them

### Problem

`daily_briefing_use_case.py:192-204` reads all candidates from `snapshot.json` without filtering against `universe_tickers`. RBMS and BNBR appeared in an LQ45 briefing because the opening snapshot is market-wide.

### Decision

Use **Option B**.

The opening snapshot is market-wide by nature. Do not discard outside-universe auction context, but never show it inside the universe-scoped pre-open list. Split the response into two explicitly labeled scopes:

- `opening_candidates` — only tickers inside the requested universe
- `market_wide_opening_observations` — outside-universe names from the same snapshot, clearly labeled as market-wide context

### Desired Outcome

No non-universe ticker appears under the universe-scoped pre-open section. Outside-universe names may still appear, but only under a separately labeled market-wide observations scope.

### Non-Goals

- No change to snapshot file format.
- No additional data fetches.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: not touched
- Application: daily_briefing_use_case.py — split opening candidates into two lists in response DTO
- Infrastructure: not touched
- Adapter: today_commands.py — render two pre-open scopes with clear labels
```

### Acceptance Criteria

- [x] Non-universe tickers do not appear under the universe-scoped pre-open section
- [x] Outside-universe tickers appear only under a clearly labeled market-wide observations section
- [x] Test: universe = [A, B], snapshot has [A, C] → A appears in universe section and C appears in market-wide section
- [x] Full test suite passes
- [x] `git diff --check` clean

---

## Task T6 — Verdict-First Pre-Open Presentation

### Metadata

- **Type:** Refactor
- **Priority:** P0 — SKIP/GAP_OUT names appear under "Top Pre-Open Candidates"

### Problem

`today_commands.py:207`: `Text("Top Pre-Open Candidates", style="bold cyan")`

SKIP and GAP_OUT candidates appear under this title, implying endorsement.
The section should be renamed and lead with an actionable verdict before showing observations.

Key files:
- `src/adapters/cli/today_commands.py:207` — section title
- `tests/adapters/cli/test_today_commands.py:29` — asserts old title (must be updated)

### Desired Outcome

Section renamed to `PRE-OPEN ASSESSMENT`.
If no universe-scoped candidate has an actionable setup, show `NO ACTIONABLE [UNIVERSE] SETUPS` first.
SKIP/AVOID observations are still shown but clearly labeled as observations, not as top candidates.

```text
PRE-OPEN ASSESSMENT
NO ACTIONABLE LQ45 SETUPS

Observed market-wide:
RBMS  SKIP  GAP_OUT
BNBR  SKIP  GAP_OUT
```

### Non-Goals

- No change to opening snapshot logic.
- No new data.
- No change to what `PRIME`/`WATCH`/`SKIP` means.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: not touched
- Application: not touched (verdict logic is display-side for section label only)
- Infrastructure: not touched
- Adapter: today_commands.py — section title, verdict-first display logic
- Tests: test_today_commands.py — update assertion for old title
```

### Acceptance Criteria

- [x] Section is titled `PRE-OPEN ASSESSMENT` not `Top Pre-Open Candidates`
- [x] If no PRIME/WATCH setups, `NO ACTIONABLE [UNIVERSE] SETUPS` is shown first
- [x] SKIP/AVOID names appear as labeled observations, not as "candidates"
- [x] `test_today_commands.py` updated to assert new title
- [x] Full test suite passes
- [x] `git diff --check` clean

---

## Task T7 — Canonical Accumulation Funnel (Signal + Risk + TradeSetup)

### Metadata

- **Type:** Feature
- **Priority:** P0 — largest task; requires architecture discussion before implementation
- **Effort:** Large — touches application use case composition and response DTOs

### Problem

The current `Score` column is `foreign_flow_score` from `AccumulationCandidate`. It is not:
- canonical `SignalEngine` score
- `RiskEngine` status
- `TradeSetup` action
- evidence coverage

A ticker with score 77.3 may have an AVOID verdict from canonical engines.

Current section title: `Top Accumulation Candidates` — implies canonical authority it does not have.

Key files:
- `src/adapters/cli/today_commands.py:175-202` — accumulation display
- `src/application/use_case/daily_briefing_use_case.py:117-129` — accumulation screen call
- `src/application/dto/accumulation_screen.py` — `AccumulationCandidate` DTO (check what fields it has)

### Desired Outcome

The accumulation section shows a funnel summary, then a table with canonical fields:

```text
ACCUMULATION SCREEN
45 checked | 41 data-ready | 6 flow candidates | 2 WATCH | 0 ENTER | 3 blocked

Ticker  Flow  Phase         Signal  Coverage  Risk   Action
INDF    60.6  ACCUMULATION  72      82%       OPEN   WATCH
BBTN    56.9  COMPRESSION   68      76%       OPEN   WATCH
GOTO    77.3  EXHAUSTION    61      64%       BLOCK  AVOID
```

Section renamed to `ACCUMULATION SCREEN`. `Score` column renamed to `Flow`.
No setup-impact matrix is created by T7; that responsibility belongs to T8.

### Non-Goals

- No network fetches.
- Raw foreign-flow score must not be labeled or colored as canonical score.
- Do not select or rank setup-lens candidates in T7.

### Architecture Notes

T7 should only project canonical fields already produced by
`AccumulationScreenUseCase`. Any setup-lens impact belongs to T8 and must use
canonical setup/swing/trade-setup logic.

The adapter only renders the response. T7 must not add ranking policy.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: not touched
- Application: DailyBriefingUseCase projection only; no setup-impact use case
- Infrastructure: not touched (reuses existing signal/risk engine)
- Adapter: today_commands.py — render funnel summary table and rename columns
```

### Acceptance Criteria

- [x] Section is titled `ACCUMULATION SCREEN`
- [x] Funnel summary shows: checked, data-ready, flow candidates, WATCH, ENTER, blocked counts
- [x] Table shows: Ticker, Flow, Phase, Signal, Coverage, Risk, Action columns
- [x] `Score` column is gone; `Flow` column shows foreign flow score
- [x] No new network calls; local only
- [x] Full test suite passes
- [x] `git diff --check` clean
- [~] Ranking follows canonical policy (TradeSetup action outranks flow score) — **superseded, see As-Built Note**
- [~] Test: ticker with high flow score but AVOID TradeSetup does not rank above a lower-flow WATCH — **superseded, see As-Built Note**

### As-Built Note (2026-07-15)

Implemented as a pure **projection**, not a new ranking/decision engine, per an
explicit corrected principle from the task requester: `today` must not invent
decision policy — it must project canonical `AccumulationScreenUseCase`
output as-is.

Deviations from the original design above:
- No setup-impact use case was created. A new
  `DailyAccumulationProjector` (`src/application/use_case/daily_accumulation_projection.py`)
  maps each `AccumulationCandidate` already returned by
  `AccumulationScreenUseCase` into a `DailyAccumulationCandidate` DTO
  (flow score, setup phase, signal score/coverage, risk status, TradeSetup
  action) and a `DailyAccumulationSummary` (checked/data-ready/flow
  candidates/ENTER/WATCH/blocked/unclassified counts).
- **No local ranking/sorting is introduced.** `today` preserves the exact
  order returned by `AccumulationScreenUseCase` — the "TradeSetup outranks
  flow score" acceptance criterion above is not applicable because `today`
  does not rank at all; ranking policy remains solely inside
  `AccumulationScreenUseCase`.
- Candidates with no `trade_setup` are shown as **unclassified** (`action =
  None`, counted in `unclassified_count`, with a warning), not assigned a
  pseudo-action like `REVIEW`.
- `today_commands.py` now wires a risk-enabled `AccumulationScreenUseCase`
  via `create_accumulation_assess_risk_use_case` (adapter wiring only, no
  policy) so `risk_assessment`/`trade_setup` are actually populated.

Tests: `tests/application/use_case/test_daily_accumulation_projection.py`
(new), `tests/application/use_case/test_daily_briefing.py`,
`tests/adapters/cli/test_today_commands.py`.

T8 was explicitly **not** implemented in the T7 change. The old "SWING
SHORTLIST" framing was rejected because `AccumulationScreenUseCase` output is
not semantically equivalent to `saham analyze swing TICKER --setup SETUP`.
T8 is now scoped as a bounded canonical setup-lens impact matrix for the
already-rendered accumulation candidates.

---

## Task T8 — Bounded Setup-Lens Impact For Accumulation Candidates

### Metadata

- **Type:** Feature
- **Priority:** P0 — users can see accumulation candidates, but cannot see which canonical swing setup lens would matter before running multiple manual commands
- **Pre-condition:** T7 must be completed and `DailyBriefingResponse.daily_accumulation_candidates` must be populated from canonical `TradeSetup`
- **Effort:** Medium/high — runs canonical setup-aware swing assessment in bounded local mode

### Problem

`saham today` already lists accumulation candidates with canonical signal/risk
projection, but it does not answer the next practical question:

> For the accumulation names already shown, what would the canonical swing path
> say under each available setup lens?

The answer must not be invented locally in `today`. A setup impact cell must be
derived from the same canonical application logic used by `saham analyze swing
TICKER --setup SETUP`, with local cached data only.

### Desired Outcome

A `SETUP LENS IMPACT` section appears after `ACCUMULATION SCREEN`.

Scope:
- Source tickers only from the accumulation candidates already selected for the
  daily briefing.
- Bound evaluation by the existing `--top` value.
- Evaluate every setup in `AVAILABLE_SWING_SETUPS`:
  - `foreign-bounce`
  - `coiled-spring`
  - `smart-money-confirmed`
  - `pullback-continuation`
- Use canonical application workflow/services, not CLI helper parsing or a
  `today`-specific scoring formula.
- Run in local cached/read-only mode: no fetch, no browser/API provider calls,
  no writes, no tuning, no journal append.

Each ticker/setup cell should show the compact canonical impact:
- resulting `TradeSetup.action`
- resulting signal score
- setup match status (`MATCH`, `PARTIAL`, `NO_MATCH`)
- entry-authority or phase cap when it changes/limits the action

Example shape:

```text
SETUP LENS IMPACT
Ticker  Base   foreign-bounce       coiled-spring        smart-money-confirmed  pullback-continuation
INDF    WATCH  WATCH 72 MATCH       WATCH 68 PARTIAL     WATCH 70 MATCH(no-entry)  AVOID 54 NO_MATCH
BBTN    WATCH  WATCH 69 PARTIAL     AVOID 58 NO_MATCH    WATCH 66 PARTIAL          WATCH 64 PARTIAL

Next:
  saham analyze swing INDF --setup foreign-bounce
  saham analyze swing BBTN --setup pullback-continuation
```

If no accumulation candidates are available, show:

```text
SETUP LENS IMPACT
No accumulation candidates to evaluate.
```

### Non-Goals

- No local setup bonus/penalty formula.
- No arbitrary ranking policy inside `today`.
- No new action vocabulary; final action must remain `TradeSetup.action`.
- No setup match inferred from setup name, strategy name, or display text.
- No additional data fetches, browser calls, provider refreshes, writes, tuning,
  or journal persistence.
- No change to `saham analyze swing` command.
- No replacement of the existing `ACCUMULATION SCREEN` section.
- No claim that accumulation score equals swing setup score.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: not touched
- Application: new bounded setup-impact use case/service composed by DailyBriefingUseCase; reuse canonical swing/setup/trade-setup services
- Infrastructure: not touched except existing adapter-side wiring of repositories/config loaders, if required
- Adapter: today_commands.py renders the returned DTO only; no setup scoring, no workflow branching
```

### Canonical Sources And Guardrails

- Available setup names come from
  `src.application.use_case.evaluate_swing_setup_use_case.AVAILABLE_SWING_SETUPS`.
- Setup fit/match comes from `EvaluateSwingSetupUseCase` or an existing
  canonical swing workflow component that delegates to it.
- Final action comes from `AssessTradeSetupUseCase` / canonical swing workflow
  response, not from setup match alone.
- `PrimarySetupFamilyResolver` remains diagnostic; it must not grant entry
  authority.
- Confirmation-only and phase-gated setups must obey existing decision-policy
  rules. Do not infer `entry_authority` from setup name.
- If the full swing workflow cannot be reused without fetch/write side effects,
  extract a local read-only application collaborator first. Do not call the CLI.

### Acceptance Criteria

- [x] `SETUP LENS IMPACT` section appears after `ACCUMULATION SCREEN`
- [x] The section evaluates only the accumulation candidates already included in the briefing, capped by `--top`
- [x] Every setup in `AVAILABLE_SWING_SETUPS` is represented for each evaluated ticker
- [x] Each setup cell is backed by canonical setup/swing/trade-setup logic and includes action, signal score, setup match, and any entry-authority/phase cap
- [x] No local rank/score/bonus/penalty policy is introduced in `today`
- [x] No fetch/write/tune/journal side effects occur while rendering `saham today`
- [x] Next commands contain resolved ticker and setup name, e.g. `saham analyze swing INDF --setup foreign-bounce`
- [x] If no accumulation candidates exist, the section says `No accumulation candidates to evaluate.`
- [x] Application use-case tests cover match/partial/no-match, confirmation-only no-entry, phase-gated cap, no-candidate behavior, and read-only/no-fetch behavior
- [x] Adapter tests cover rendering and resolved next-command text
- [x] Full test suite passes (pre-existing unrelated failure isolated below)
- [x] `git diff --check` clean

### As-Built Note (2026-07-15)

Implemented per the design above, with the full canonical
`SwingAnalysisWorkflowUseCase` reused directly (not a narrower collaborator):
`today_commands.py` wires four setup-bound workflow instances (one per
`AVAILABLE_SWING_SETUPS` entry, sharing one `StockAnalysisWorkflowDependencies`
bundle) via the existing `create_swing_analysis_workflow` factory, each run
with `auto_refresh=False`, `force_refresh=False`, `strategy_name=None`,
`include_sentiment=False` so no fetch/write/journal/AI side effects occur.

New application use case:
`src/application/use_case/daily_setup_lens_impact_use_case.py`
(`DailySetupLensImpactUseCase`). `DailyBriefingUseCase` composes it — invoked
only when injected, `overall_authority != "NOT_READY"`, and
`daily_accumulation_candidates` is non-empty; a per-call exception is
downgraded to a warning rather than failing the briefing.

Per-cell fields are read verbatim from canonical sources, never invented:
`action`/`signal_score` from `TradeSetup`, `setup_match`/`entry_authority`
from `SetupEvaluation`, and `capped_reason` from
`SignalAssessment.decision_constraints.constraint_reasons` (the same
`DecisionPolicyService` output that caps confirmation-only and phase-gated
setups to WATCH). A per-cell exception (e.g. missing broker detail for
`smart-money-confirmed`) is caught and surfaced as `warning` on that cell only
— it does not abort the row or the command.

Tests: `tests/application/use_case/test_daily_setup_lens_impact_use_case.py`
(new), `tests/application/use_case/test_daily_briefing.py`,
`tests/adapters/cli/test_today_commands.py`.

Full suite: 4114 passed. Seven pre-existing failures in
`tests/adapters/cli/test_stock_analysis_workflow_dependencies_config_paths.py`
are unrelated test-order pollution — reproduced identically on a clean `main`
checkout with `pytest tests/adapters/cli -q` (verified before and after this
change), not a regression introduced by T8.

#### Addendum (2026-07-15) — two residual fixes

Two follow-up bugs were fixed on top of the original T8 landing. First, the
historical `--date` path now threads `request.today` all the way into the
accumulation-candidate build: `SwingAnalysisInputCollector` passes
`as_of_date=request.today` and `create_accumulation_candidate_builder`'s
`_build_accumulation_candidate(ticker, window, as_of_date)` forwards it into
`AccumulationScreenRequest`, so setup-lens cells no longer mix historical
broker-detail context with current-day accumulation gates. Second,
`capped_reason` is now filtered to only setup entry-authority/phase-gate reasons
(markers `has no standalone entry authority`, `requires setup phase for ENTER`,
`requires phase`) via `_entry_authority_constraint_reasons`, so a generic
score/coverage/regime floor no longer mislabels a cell `(no-entry)`. New tests:
`tests/application/services/test_swing_analysis_input_collector.py` (proves the
date threads through) plus two filter tests in the T8 use-case test file.

---

## Task T9 — Expose Honest Market Context (Stop Aliasing RISK_ON to BULLISH)

### Metadata

- **Type:** Refactor
- **Priority:** P1 — misleads users about regime certainty

### Problem

`view_market_context_display.py:23`:
```python
REGIME_DISPLAY_LABEL: dict[str, str] = {
    "RISK_ON":  "BULLISH",
    "NEUTRAL":  "SIDEWAYS",
    ...
}
```

`today_commands.py:138-141` uses this map:
```python
label = REGIME_DISPLAY_LABEL.get(ctx.regime.value, ctx.regime.value)
regime_text = f"[{style}]{label} ({score}/7)[/{style}]"
```

This hides:
- the canonical regime name (`RISK_ON` not `BULLISH`)
- conviction score (0.69 shown as 5/7 which overstates certainty)
- regime confidence (0.2986 is low; the display hides it)
- local/global disagreement

### Desired Outcome

The `today` briefing does NOT use `REGIME_DISPLAY_LABEL`. It renders:
- canonical regime name: `RISK_ON`
- confidence qualifier: `low confidence` when `context.regime_confidence < 0.5`
- the two strongest tailwinds and headwinds when available

Example:
```
MARKET POSTURE
RISK_ON — low confidence
Conviction: 0.69 | Breadth: NEUTRAL 46.2% | Local trend: STRESSED | Global: FAVORABLE
```

> [!NOTE]
> `view_market_context_display.py` `REGIME_DISPLAY_LABEL` may be used by other commands (`saham view market-context`). Do not change that map for other commands — only the `today_commands.py` rendering should change.

### Non-Goals

- No change to `REGIME_DISPLAY_LABEL` for other commands.
- No change to `MarketContextEngine` output.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: not touched
- Application: not touched
- Infrastructure: not touched
- Adapter: today_commands.py — render regime directly without REGIME_DISPLAY_LABEL; add confidence qualifier
```

### Acceptance Criteria

- [x] `today` output shows `RISK_ON` not `BULLISH`
- [x] No other command's output is changed
- [x] `test_today_commands.py` updated with new assertions
- [x] Full test suite passes
- [x] `git diff --check` clean

### As-Built Note (2026-07-15)

Implemented per the task instructions (commit `fd51cef`), which differed from the
original design in the following ways:

- The task explicitly forbade confidence labels (`LOW`, `HIGH`, `MEDIUM` buckets)
  and thresholds, so no `low confidence` qualifier was added.
- The task required a strict output shape — canonical values joined by ` | ` with
  no invented display labels:
  ```
  Market regime  RISK_ON | conviction 0.69 | confidence 0.30 | stability TRANSITIONING
  ```
- Removed `REGIME_DISPLAY_LABEL` and `context_conviction_score` imports from
  `today_commands.py`. Added a private `_market_regime_text(ctx)` renderer.
- Preserved `context_regime_style` (color by conviction level) and
  `context_factor_value` (breadth display).
- `view_market_context_display.py` was not changed. Other commands that import
  `REGIME_DISPLAY_LABEL` / `context_conviction_score` are unaffected.
- New tests: `test_market_regime_text_renders_all_fields`,
  `test_market_regime_text_omits_optional_metadata`,
  `test_market_regime_text_appends_transition_warning`,
  `test_today_market_regime_renders_plain_values` (asserts `BULLISH` and
  `(5/7)` are absent from output).

---

## Task T10 — Primary Verdict Header Before Tables

### Metadata

- **Type:** Feature
- **Priority:** P1

### Problem

Currently there is no top-line summary block. Users must interpret colored tables to understand the day's status. A user should be able to read one block and understand: is data ready, what is the posture, what should they do now.

### Desired Outcome

A top-of-output verdict block before any tables:
```text
DATA STATUS:    PARTIAL (41/45 candles current)
MARKET POSTURE: RISK_ON, low confidence
ACTION NOW:     Review setup lens impact
NEXT COMMAND:   saham analyze swing INDF --setup foreign-bounce
```

Depends on T3 (three clocks) and T4 (readiness) for correct data.

### Non-Goals

- No new data fetches.
- Only renders existing response fields in a new top-level block.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: not touched
- Application: DailyBriefingResponse (add verdict_summary field or compute in adapter)
- Infrastructure: not touched
- Adapter: today_commands.py — render verdict block before all other sections
```

### Acceptance Criteria

- [ ] Verdict block appears before all tables
- [ ] `DATA STATUS` reflects `overall_authority` from T4
- [ ] `NEXT COMMAND` contains a resolved ticker, not a placeholder
- [ ] Full test suite passes
- [ ] `git diff --check` clean

---

## Task T11 — Session-Aware IDX Lifecycle Next Action

### Metadata

- **Type:** Feature
- **Priority:** P1

### Problem

`today_commands.py:220-232` — static next-action text with unresolved `TICKER` placeholder:
```python
"Next: saham screen accum --universe {response.universe} | saham analyze swing TICKER"
```

The action does not reflect:
- what IDX session phase it is (pre-open, NCP, opening, regular, after-close)
- what the briefing already discovered (e.g., INDF is the best candidate — show that, not `TICKER`)

### Desired Outcome

The application use case (or a small session-phase helper) derives the current IDX session phase and returns one primary next command. The adapter renders it.

Session-phase mapping:
- before pre-open: `saham fetch market --universe [universe]`
- NCP window: `saham screen pre-open`
- opening window: review pre-open confirmed setups
- regular session: `saham analyze swing [best_ticker]`
- after close: `saham fetch market --universe [universe]`
- historical mode: show replay/review actions only

### Non-Goals

- No network calls for session phase — use local clock and IDX schedule.
- No change to how IDX session times are derived (use existing `stockbit_market_time.py`).

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: not touched
- Application: daily_briefing_use_case.py — add next_action field to response; derive from session phase and top candidate
- Infrastructure: not touched (reuse existing market time service)
- Adapter: today_commands.py — render single next action, remove static TICKER template
```

### Acceptance Criteria

- [ ] Next action contains a real ticker name when one is available, not `TICKER`
- [ ] Next action is session-aware (different during pre-open vs regular vs after-close)
- [ ] Historical mode shows historical action only
- [ ] `test_today_commands.py` updated (old assertion for `TICKER` placeholder must be removed)
- [ ] Full test suite passes
- [ ] `git diff --check` clean

---

## Task T12 — Warning Severity (BLOCKER / WARNING / INFO)

### Metadata

- **Type:** Refactor
- **Priority:** P1

### Problem

`today_commands.py:213-218` — warnings are a plain list capped at 5 rows. Critical warnings (data below threshold, accumulation suppressed) can be hidden by non-critical info messages.

### Desired Outcome

Warnings are rendered with severity tiers:
- `BLOCKER` — must be shown first regardless of count cap; affects whether sections are shown
- `WARNING` — shown after blockers; affects interpretation
- `INFO` — shown last, can be capped

The application use case returns `list[BriefingWarning]` where each item has a `severity` field.
The adapter renders them grouped by severity with visual distinction.

### Non-Goals

- No change to what triggers warnings (that belongs in T4).
- No new warning sources beyond what already exists.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: not touched
- Application: daily_briefing_use_case.py — BriefingWarning dataclass with severity; replace plain list[str]
- Infrastructure: not touched
- Adapter: today_commands.py — group and render warnings by severity
```

### Acceptance Criteria

- [ ] `BriefingWarning` has `message: str` and `severity: Literal["BLOCKER", "WARNING", "INFO"]`
- [ ] BLOCKER warnings always visible regardless of count cap
- [ ] Tests for severity grouping
- [ ] Full test suite passes
- [ ] `git diff --check` clean

---

## Task T13 — Historical Mode: Separate or Omit Live Market Status

### Metadata

- **Type:** Bugfix
- **Priority:** P2

### Problem

When `--date 2026-06-19` is passed, the briefing still shows today's live market status (`Regular / open`) as though it belongs to the historical date. The user cannot tell what was true on 2026-06-19 vs what is true right now.

Depends on T3 (`is_historical` flag in response).

### Desired Outcome

- Historical mode shows `HISTORICAL MODE — [date]` label in the status section.
- Live market status (`Regular / open`, source tag) is either omitted or clearly separated from the historical analysis block.

### Non-Goals

- No change to how historical dates are resolved.
- No new data fetches.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: not touched
- Application: daily_briefing_use_case.py — is_historical flag (added in T3)
- Infrastructure: not touched
- Adapter: today_commands.py — conditional rendering of live market status based on is_historical
```

### Acceptance Criteria

- [x] `saham today --date 2026-06-19` does not show "Regular / open" as the current status
- [x] Historical mode label is visible in output
- [x] `test_today_commands.py` covers the historical rendering path
- [x] Full test suite passes
- [x] `git diff --check` clean

---

## Architecture Boundary Reminder

> [!IMPORTANT]
> `saham today` must not invoke other CLI commands or parse their rendered output.

```text
DailyBriefingUseCase
  ├── MarketDataReadinessService    (T4)
  ├── MarketContextEngine           (existing)
  ├── OpeningSnapshotReader         (existing)
  ├── AccumulationScreenUseCase     (existing)
  └── SetupLensImpactUseCase        (T8 — bounded, read-only, canonical)
```

The adapter (`today_commands.py`) only:
- parses flags
- wires dependencies
- calls the briefing use case
- renders the response
- maps errors

Workflow policy, ranking policy, readiness thresholds, and session-phase derivation all belong in application use cases.

---

## Already Confirmed Working (Do Not Re-implement)

- CLI startup: `risk_engine_helper.py` imports are valid. `src.application.domain` error is gone.
- `DailyBriefingUseCase` uses application use case pattern (not CLI-invoking CLI).
- Weekend rollback exists (`daily_briefing_use_case.py:86`) — extend to IDX holidays in T3.
- Opening snapshot date validation exists (`_opening_candidates()` checks `captured_at`).
- Individual sections degrade gracefully with `try/except` and warning messages.
- Score coloring thresholds exist (`today_commands.py:187-193`) — these will be re-labeled in T7.
