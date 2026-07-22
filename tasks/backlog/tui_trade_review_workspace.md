# TUI Milestone E — Journal And Review Workspace

Status: `BACKLOG`

Roadmap: `docs/roadmap/roadmap_tui.md`

Depends on: TUI Milestone D

## Task Metadata

- Task type: Feature / feedback workflow
- Priority: Medium-High
- Semantic classification: `NON_SEMANTIC`
- Chosen decision: build Review from exact saved-screen and swing-candidate
  journal records, with read-only summaries separated from explicit forward-
  outcome enrichment. Implement this option only.

## Problem Statement

Discovery and analysis have little personal value if the user cannot revisit
what was selected and measure what followed. Existing CLI review logic is also
misleading as a UI boundary: `AccumulationJournalService.review()` both enriches
journal rows (a write) and computes summaries, while filtering is partly owned
by display code.

The TUI needs an honest feedback workspace that distinguishes:

- a saved candidate snapshot;
- a recorded swing candidate/plan;
- a derived 5/10/20-session forward market outcome;
- an actual executed trade outcome, which the current swing journal does not
  prove.

## Desired Outcome

Review provides:

- Saved Candidates history from Milestone B;
- Swing Journal entry list/detail;
- read-only summaries by setup match, pattern, score bucket, and regime where
  exact data exists;
- explicit `Update forward outcomes` to fill missing derived closes from local
  candles;
- clear evaluated/unevaluated counts and unavailable reasons;
- links to the originating ticker and available recorded evidence.

The UI says `forward outcome` or `candidate outcome`, never `trade P&L`, unless
an exact execution journal supplies actual entry and exit.

## Required Application Refactor

Split the current combined review behavior into explicit boundaries.

### Read exact entries

```text
ListSwingJournalEntriesRequest
  date_from: date | None
  date_to: date | None
  tickers: tuple[str, ...]
  setups: tuple[str, ...]
  setup_matches: tuple[str, ...]
  regimes: tuple[str, ...]
  min_foreign_flow_score: float | None

ListSwingJournalEntriesResponse
  entries: tuple[AccumulationJournalEntry, ...]
  total_before_filter: int
  warnings: tuple[str, ...]
```

Filtering and ordering are application-owned. Order is newest date first, then
ticker, with exact stable tie behavior documented and tested.

### Summarize without writing

```text
SummarizeSwingJournalRequest
  entries: tuple[AccumulationJournalEntry, ...]
  horizon: 5 | 10 | 20

SummarizeSwingJournalResponse
  total_entries: int
  evaluated_entries: int
  unevaluated_entries: int
  by_score_bucket
  by_setup_match
  by_pattern
  by_regime when provenance exists
  signal_deltas
  warnings
```

Reuse existing `AccumulationJournalReport` statistics where semantics match,
but make horizon names/fields exact. Do not label a 10-session metric with a
user-selected 5/20 horizon if the underlying service cannot compute it.

### Explicit forward-outcome enrichment

```text
EnrichSwingJournalOutcomesRequest
  entry_keys: tuple[exact journal key, ...]
  horizon_days: int
  as_of_date: date | None

EnrichSwingJournalOutcomesResponse
  requested: int
  updated: int
  already_complete: int
  unavailable: tuple[key + reason, ...]
```

This use case owns candle reads and journal updates. It preserves existing
idempotency and updates only the derived review fields of exact selected rows.
The TUI confirms the write scope before execution and refreshes the read-only
query only after completion.

If the current journal store cannot address exact row keys safely, stop and
define that contract before implementation. Do not update rows by ticker alone.

### Saved candidates

Reuse the Milestone B watchlist list/query result. Do not reread its repository
directly or invent a second saved-candidate model.

## UX Contract

### Saved Candidates

- snapshot list with name, universe, window, saved date, and count;
- exact snapshot entries and recorded scores/ranks;
- open ticker;
- optional compare action delegates to the Milestone B comparison workflow.

### Swing Journal

```text
REVIEW  Swing Journal   2026-04-01 -> 2026-07-21
Setup [All] Match [All] Regime [All] Score [Any]
Recorded 24   Evaluated 18   Awaiting data 6
[Update forward outcomes]
-----------------------------------------------------------------------
Date       Ticker Setup          Match    Entry   10s return  Max up/down
2026-07-01 BBRI   foreign-bounce MATCH    4,840   +4.2%       +7.1/-2.0
```

Entry detail shows all recorded fields, derived closes, forward returns,
failed gates, pattern, regime, plan, and missing provenance. It never claims a
planned price was filled.

### Summary tabs

- By setup match.
- By pattern.
- By score bucket.
- By regime only when enough exact rows carry regime.
- Signal deltas with group sizes.

Every metric shows sample count and horizon. Zero observations render
UNAVAILABLE, not 0% performance.

### Update forward outcomes

Confirmation shows selected row count, exact horizon, local-candle dependency,
and `This updates derived review fields in the swing journal`.

It does not fetch providers. Missing future candles remain unavailable with a
reason; they are not failures or neutral results.

## Non-Goals

- No claim that a logged candidate was executed.
- No synthetic entry/exit, trade P&L, or portfolio return.
- No automatic outcome enrichment on mount/navigation.
- No provider fetch from Review.
- No tuning recommendation, parameter optimization, or AI interpretation.
- No mutation of original decision/setup/plan fields.
- No intraday review or manual outcome UI unless separately scoped from its
  existing typed contracts.

## Architecture Impact

- Domain: reuse journal entry/store keys; add exact key value object if missing
- Application: split list, summarize, and enrichment use cases
- Infrastructure: exact-key journal update/read implementation
- Adapter: Review filters/tables/details/confirmation/presentation
- Persistence: explicit derived review-field updates only
- Determinism: summaries deterministic for exact entry set/horizon
- AI: none

Layer plan:

```md
Layer plan:
- Domain: exact journal identity only if currently absent
- Application: list, summarize, and enrich workflows
- Infrastructure: exact-key journal store behavior
- Adapter: Review interaction and presentation
```

## Expected File Boundary

- application journal review DTO/use-case modules and tests;
- domain/store contract only if exact identity is absent;
- infrastructure journal implementation tests;
- TUI Review controllers/presenters/screen/widgets/composition;
- saved-candidate integration from Milestone B;
- headless read/filter/enrich/error tests;
- CLI review wiring update to preserve behavior through the new boundaries;
- Help/docs and this completion record.

Do not import `trade_accum_display.py`, `trade_accum_commands.py`, or concrete
journal storage into TUI modules.

## Implementation Checklist

- [ ] Audit exact swing journal identity, dual-write behavior, and current
  derived-field mutation.
- [ ] Define read/write exception and unavailable-reason contracts.
- [ ] Split list, summarize, and enrichment application boundaries.
- [ ] Move minimum-score and other filtering out of display code.
- [ ] Preserve existing CLI review behavior using the new use cases.
- [ ] Implement Saved Candidates and Swing Journal tabs.
- [ ] Implement filters, detail, summary tabs, and exact counts.
- [ ] Implement explicit enrichment confirmation/progress/result.
- [ ] Add idempotency, exact-key, missing-candle, and no-provider tests.
- [ ] Add terminology/authority negative tests.
- [ ] Run focused, architecture, CLI, and full tests when feasible.
- [ ] Fill completion record from evidence.

## Acceptance Criteria

- [ ] Review can list/filter exact journal entries without writing.
- [ ] Summary can run repeatedly without any persistence call.
- [ ] Outcome enrichment runs only after explicit confirmation.
- [ ] Enrichment targets exact entry keys and changes only derived review fields.
- [ ] Repeating enrichment is idempotent.
- [ ] Missing future candles remain unevaluated with exact reason.
- [ ] Recorded, evaluated, and unevaluated counts reconcile to exact entries.
- [ ] Every metric shows horizon and sample count.
- [ ] Empty groups are UNAVAILABLE, never reported as 0% success.
- [ ] Planned entry/stop/target are never described as executed.
- [ ] Saved-candidate data reuses Milestone B contracts.
- [ ] CLI swing review retains its supported behavior through new boundaries.
- [ ] No provider, tuning, config, or unrelated journal write is introduced.
- [ ] Focused tests, architecture tests, full suite when feasible, and
  `git diff --check` pass.

## Required Negative Tests

- Opening Review cannot update journal rows.
- Filter/sort/tab changes cannot enrich outcomes.
- Summary cannot call journal update or market repository.
- Enrichment cannot update by ticker alone or touch original decision fields.
- Missing candles cannot create zero return or loss/win classification.
- Planned prices cannot become actual execution fields.
- Presenter cannot filter entries or calculate unprovided aggregate metrics.
- TUI cannot import CLI displays, filesystem paths, or concrete stores.
- Authorization to enrich cannot authorize logging a new candidate.

## Do Not Interpret This As

- Do not call the existing combined `.review()` directly from the screen.
- Do not hide its write behavior under Reload.
- Do not call forward returns actual trades.
- Do not add portfolio P&L from candidate observations.
- Do not infer missing regime/setup/provenance.
- Do not generate advice or tuning conclusions from small samples.
- Do not broaden into intraday or broker execution records.

## Verification

Run journal identity/store tests; list/summarize/enrich application tests;
existing CLI swing log/review tests; TUI controller/presenter/headless tests at
80x24 and 120x40; strict read-only query and no-provider tests; disposable
journal exact-write/idempotency tests; architecture guards; full suite when
feasible; and `git diff --check`.

## Completion Record

- Completed date:
- Implementation commit:
- Files changed:
- Journal identity proof:
- Read-only list/summary proof:
- Explicit enrichment/write proof:
- Count reconciliation proof:
- Terminology/authority proof:
- CLI preservation proof:
- Focused tests:
- Architecture tests:
- Full suite:
- `git diff --check`:
- Deferred items:
