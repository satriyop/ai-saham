# DQ-004 lean implementation plan (amended 2026-07-22)

Companion to `tasks/backlog/audit_data_quality.md` → DQ-004 and its "Lean
raw-label amendment (2026-07-22)". Build honest raw market-outcome labels;
park net-executable (cost-modeled) labels behind `IDX-EXECUTION-LABELS`.

## Guiding decision

Raw labels are sufficient for `DQ-BASELINE-GATE` research/ML validation (which
does not authorize promotion). Costs shift return *magnitude*, not *direction* or
*ranking*, so an ML challenger learns the same signal from raw returns. Build the
raw contract honestly now; defer execution realism to the promotion lane.

## What already exists (do not rebuild)

`generate_signal_forward_labels_use_case.py` already computes close/max-high/
min-low returns, days-to-peak/trough, target/stop triggers, SUCCESS/FAILURE/
NEUTRAL, complete future-IDX-session windows, and `UNAVAILABLE` on incomplete
windows. It binds labels to canonical observations and skips non-canonical ones.
The label repo enforces `UNIQUE(ticker, signal_date, horizon, observation_captured_at)`.
The summary use case counts `unavailable_count` separately.

## What is missing / partial (this plan)

- Corporate-action awareness: **none** in the label path — the real gap.
- Explicit raw-vs-executable marker on the label: absent.
- Golden reconciliation fixture (hand/SQL vs code): absent.
- Explicit tests for collision policy, summary exclusion, and observation binding.

## Available data (confirmed 2026-07-22)

`CorporateActionCalendarRepository.get_events_for_ticker(ticker, from_date,
to_date, event_types, as_of_fetched_at)` returns typed events
(`STOCK_SPLIT`/`REVERSE_SPLIT`/`RIGHTS_ISSUE`/`BONUS`/`DIVIDEND`/...) with
`EX_DATE` roles and `ratio_old`/`ratio_new`. Real detection is possible — no
jump heuristic needed.

---

## Slice D4-1 — Corporate-action fail-closed + raw-outcome marker

**Goal:** a label whose window crosses a real mechanical corporate action is
`UNAVAILABLE`, never a distorted number; every raw label is explicitly marked
non-executable. Closes criterion 3 (corporate-action half) and the
"raw/non-canonical" half of criterion 4.

**Layer plan:**
```md
- Domain: add raw-outcome marker + reason to SignalForwardLabel (value object)
- Application: inject CorporateActionCalendarRepository into the generator;
  window-crossing check → UNAVAILABLE
- Infrastructure: none new (reuse the existing calendar repo/port)
- Adapter: pass the calendar repo through the label + backfill composition roots
```

**Contracts:**
- Inject `CorporateActionCalendarRepository` into
  `GenerateSignalForwardLabelsUseCase` (new constructor port; manual DI).
- In `_build_label`, after resolving the window `[window[0].date,
  window[-1].date]`, query
  `get_events_for_ticker(ticker, window_start, window_end,
  event_types=(STOCK_SPLIT, REVERSE_SPLIT, RIGHTS_ISSUE, BONUS))` filtered to
  `EX_DATE` roles inside the window. If any exist → return an `UNAVAILABLE`
  label with reason `corporate_action_in_window:<type>@<ex_date>`.
- Query WITHOUT `as_of_fetched_at` (labels are computed after the fact; knowing a
  split *did* happen is correct — invalidation is conservative, never leakage).
- Add an explicit raw-outcome marker to `SignalForwardLabel`, e.g.
  `outcome_basis: str = "raw_market"` (future net labels will be
  `"net_executable"`). Serialize it in `to_dict`/`from_dict`.
- **Coverage gate (RESOLVED 2026-07-22 — coarse global-sync gate, Option 1):**
  per-window historical coverage is not provable from the schema (sync markers
  are run-date keyed, calendar is forward-looking). So evaluate ONCE per run
  (not per label) a new port method `has_any_sync_marker() -> bool` — SQLite:
  `SELECT 1 FROM corporate_action_calendar_sync WHERE status='success' LIMIT 1`
  (do NOT reuse `has_synced_for_date`; its exact event-type sync_key
  false-negatives). If **no** successful marker → every label `UNAVAILABLE`
  with `reason="corporate_action_coverage_unavailable"`. If a marker exists →
  run per-event detection; "no events" is a clean raw label. **Precedence:**
  detection beats the gate — an open gate never waves through a window with a
  detected mechanical action. Residual limitation (synced-but-sparse gap passing
  as clean) is accepted and documented; do NOT claim completeness. Per-window
  coverage provenance is parked.

**Do Not Interpret This As:**
- Do not adjust prices across a corporate action; invalidate.
- Do not model fees/slippage/fills/execution status.
- Do not invalidate on `DIVIDEND` (deferred per amendment's open decision).
- Do not use a price-jump heuristic.

**Semantic Change Classification (state in preflight):** adding `outcome_basis`
is an additive label field; prefer NON-bumping (all existing/new labels are
uniformly `"raw_market"`, no existing data changes meaning) — confirm, and if a
`SIGNAL_FORWARD_LABEL_SCHEMA_VERSION` bump is truly required, STOP and ask.

**Composition roots to wire (both):**
- `src/adapters/cli/analyze_signal_label_commands.py`
- the backfill label wiring in
  `src/adapters/cli/analyze_signal_backfill_commands.py`
  (`GenerateSignalForwardLabelsUseCase(...)` construction)

**Negative-first tests:**
- Window crossing a planted `STOCK_SPLIT` ex-date → `UNAVAILABLE` with reason;
  the raw return is NOT computed.
- Same window with the split ex-date OUTSIDE (day after window end) → normal
  raw label.
- No successful sync marker → every label `UNAVAILABLE` /
  `corporate_action_coverage_unavailable`; returns not computed.
- Sync marker present + no events in window → normal raw label (gate opens;
  "no events" ≠ "unavailable").
- Sync marker present + planted split ex-date in window → `UNAVAILABLE` /
  `corporate_action_in_window:...` (detection wins over the open gate).
- `has_any_sync_marker()` evaluated once per run, not per observation (recording fake).
- `DIVIDEND` ex-date in window → still a normal label (documents the deferral).
- Every persisted raw label carries `outcome_basis == "raw_market"`.

**Close:** focused generator + value-object tests, architecture boundary test
(generator owns the check, adapter only wires), `git diff --check`.

**Checkpoint:** stop for review after the value-object marker + generator
contract + negative tests pass, before the golden fixture builds on them.

---

## Slice D4-2 — Golden reconciliation fixture + verification tests

**Goal:** *prove* every raw label field against independent candle math, and
lock the existing collision / summary / binding behavior. Closes criteria 1, 2,
5, 6.

**Layer plan:** test-only (`NON_SEMANTIC`); no `src/` change expected. If a test
cannot pass without a source change, STOP and report a finding.

**Contracts / tests:**
- Golden fixture: a small deterministic candle set; hand-compute close_return,
  max_forward_return, max_adverse_excursion, days_to_peak, days_to_trough,
  stop/target triggers, and outcome for ≥1 SUCCESS, 1 FAILURE, 1 NEUTRAL, and
  1 `UNAVAILABLE` (incomplete window). Assert exact field-by-field match.
- Collision policy: a window where target and stop could both trigger on the
  same day → assert conservative `FAILURE` (criterion 2).
- Summary exclusion: `UNAVAILABLE` labels are excluded from success/failure/
  neutral rates and counted only in `unavailable_count` (criterion 6).
- Observation binding: a label attaches to the exact observation version and a
  second observation capture cannot silently steal/overwrite its outcome
  (criterion 5) — assert against the repo `UNIQUE` key behavior.

**Close:** fixture + verification tests pass on a clean DB; full suite passes;
`git diff --check`.

---

## Parked (behind `IDX-EXECUTION-LABELS`, fires at promotion)

Net-executable labels: fees, taxes, slippage, price limits, gaps, fills,
execution status (`FILLED`/`PARTIAL`/`UNFILLED`/`UNTRADEABLE`), entry-model/
exit-model/cost-model versioning, next-open/auction entry assumptions — as a
distinct net-executable label contract/schema, separate from the raw label.

## After each slice — doc update

Mark the closed DQ-004 criteria `[x]` in `audit_data_quality.md` with
satisfied-notes; update this plan's slice `Status`. Do not mark criterion 4's
execution half done — it stays parked behind the trigger.
