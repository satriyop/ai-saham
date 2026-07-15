# Task: Split `swing_tuning_review_journal.py` (Audit Finding 4)

Source: `docs/code-convention-audit.md`, Finding 4 ("Medium: `src/application/services/swing_tuning_review_journal.py`
mixes store, DTOs, comparison, and measurement", status `OPEN`).

This document is the complete, binding execution spec for that finding. It exists so the
implementing agent does not have to re-derive the split boundaries, the delegation contract, or
the import migration list. **Do not deviate from the module/function boundaries below.** If you
find a reason to deviate, stop and ask instead of improvising — that is how findings drift.

---

## 1. Task Metadata

**Task Title:** Split `swing_tuning_review_journal.py` into DTO module + 3 focused services + thin facade
**Task Type:** Refactor
**Priority:** Medium

---

## 2. Problem Statement

`src/application/services/swing_tuning_review_journal.py` (476 lines) currently owns four
unrelated concerns in one file: report/DTO definitions with `to_dict()` serialization, JSONL
append/read persistence orchestration, latest-review comparison policy, and post-apply
measurement/attribution. A future agent asking "where is metric delta computed?" or "where is the
comparison status decided?" must read the whole file. Two test files also reach into this module's
private helper `_summarize_record`, which only works because everything lives in one file.

## 3. Desired Outcome

- `SwingTuningReviewJournal` becomes a thin persistence-facing facade: `append_review`, `review`,
  `compare_latest`, `measure_latest_apply` — each delegating to an extracted pure function or DTO
  constructor. It keeps `SwingTuningReviewStore` as its only persistence port dependency.
- All DTOs (`SwingTuningReviewSaveResult`, `SwingTuningReviewSummary`, `SwingTuningReviewReport`,
  `SwingTuningMetricDelta`, `SwingTuningReviewComparison`, `SwingTuningAppliedPatchSummary`,
  `SwingTuningPostApplyMeasurement`) live in `src/application/dto/swing_tuning_review.py`.
- Raw-record summarization lives in `src/application/services/swing_tuning_review_summary.py`.
- Latest-review comparison policy lives in `src/application/services/swing_tuning_review_comparison.py`.
- Post-apply measurement/attribution lives in `src/application/services/swing_tuning_post_apply_measurement.py`.
- Every call site that currently imports from `swing_tuning_review_journal` is updated to import
  from the new, correct module. No behavior, JSON key, status string, note string, or sort order
  changes.

## 4. Non-Goals (Explicitly Out of Scope)

- No change to `SwingTuningReviewStore` or `SwingTuningReviewJsonlWriter`.
- No change to JSON field names, status strings (`INSUFFICIENT_HISTORY`, `READY`, `NO_APPLY_LOG`,
  `APPLY_LOG_INVALID`, `INSUFFICIENT_REVIEW_HISTORY`), note text, or metric names.
- No change to sort semantics (`compare_latest` sorts descending by `recorded_at`;
  `measure_latest_apply` sorts ascending).
- No change to CLI command names, options, or output wording.
- No compatibility re-export shim left behind in `swing_tuning_review_journal.py` for symbols that
  moved — every consumer's import is updated to the real new location instead.

## 5. Architecture Impact Assessment

```md
Layer plan:
- Domain: not touched
- Application: touched — services/DTO reorganization only, no policy/behavior change
- Infrastructure: not touched
- Adapter: touched — import paths only (`src/adapters/cli/*`), no adapter logic changes
```

- New dependency: No.
- Affects determinism: No.
- Requires persistence changes: No.
- Requires warm-up data: No.
- Places orchestration/policy inside an adapter: No.

## 6. AI Usage Declaration

No AI involved. This is a mechanical, behavior-preserving extraction with a fully specified target
shape — implement it directly, do not use AI-generated design choices for the split boundaries.

## 7. Risk, Signal, And Evidence Authority Considerations

Not affected. This file has no relationship to `SignalEngine`, `RiskEngine`, `TradeSetup`, market
context, setup policy, or evidence promotion — it only journals/reports swing tuning review runs.

## 8. Data & Persistence

- Reads: JSONL records via `SwingTuningReviewStore.read_all()` (unchanged).
- Writes: JSONL records via `SwingTuningReviewStore.append()` (unchanged).
- No schema change.

---

## 9. Exact Target Module Map

All line numbers below refer to the **current** file
`src/application/services/swing_tuning_review_journal.py` before this refactor.

### 9.1 New file: `src/application/dto/swing_tuning_review.py`

Move verbatim (preserve field order, defaults, comments, and `to_dict()` bodies exactly):

| Symbol | Current lines |
|---|---|
| `SwingTuningReviewSaveResult` | 19–30 |
| `SwingTuningReviewSummary` | 33–74 (keep the `is_ratio` and `walk_forward_enforced` inline comments) |
| `SwingTuningReviewReport` | 77–86 |
| `SwingTuningMetricDelta` | 89–102 |
| `SwingTuningReviewComparison` | 105–124 |
| `SwingTuningAppliedPatchSummary` | 127–140 |
| `SwingTuningPostApplyMeasurement` | 143–162 |

File header: `"""Data transfer objects for swing tuning review artifacts.\n\nLayer: Application DTO\n"""`
(match the docstring convention already used in `src/application/dto/swing_backtest.py`).
Imports needed: `from __future__ import annotations`, `from dataclasses import dataclass`. No
other imports — these dataclasses have no dependency on the store port or on each other's parent
module.

### 9.2 New file: `src/application/services/swing_tuning_review_summary.py`

Purpose: turn a raw JSONL record dict into a `SwingTuningReviewSummary`, plus the shared metric-delta
helper used by both comparison and post-apply measurement (they must not each re-implement it).

| Symbol | Current lines | Change |
|---|---|---|
| `_summarize_record` | 306–338 | **Rename to `summarize_review_record`** (public — it is now a genuine cross-module API, two test files and two sibling service modules import it) |
| `_dict` | 341–342 | move as-is (keep leading underscore — internal parsing helper) |
| `_str` | 345–346 | move as-is |
| `_int` | 349–355 | move as-is |
| `_float` | 358–364 | move as-is |
| `_list` | 474–476 | move here (it is a generic dict/list coercion helper, same family as `_dict`/`_str`) |
| `_metric_deltas` | 367–395 | move as-is, keep leading underscore |
| `_delta` | 398–404 | move as-is, keep leading underscore |

Imports needed: `SwingTuningMetricDelta`, `SwingTuningReviewSummary` from
`src.application.dto.swing_tuning_review`.

`swing_tuning_review_comparison.py` and `swing_tuning_post_apply_measurement.py` import
`summarize_review_record`, `_metric_deltas`, and whichever of `_dict`/`_str`/`_list` they need,
directly from this module. Do not duplicate any of these functions.

### 9.3 New file: `src/application/services/swing_tuning_review_comparison.py`

| Symbol | Current lines | Change |
|---|---|---|
| `compare_latest_review(sorted_records)` | 198–243 (body of `compare_latest`, minus the store read/sort) | New pure function. Signature: `compare_latest_review(sorted_records: list[dict[str, Any]]) -> SwingTuningReviewComparison`. `sorted_records` is expected **already sorted descending by `recorded_at`** — the caller (facade) does the read+sort, this function does not touch the store. |
| `_proposed_target_paths` | 407–416 | move as-is |

Imports needed: `SwingTuningReviewComparison`, `SwingTuningReviewSummary` from the dto module;
`summarize_review_record`, `_metric_deltas` from `swing_tuning_review_summary`.

### 9.4 New file: `src/application/services/swing_tuning_post_apply_measurement.py`

| Symbol | Current lines | Change |
|---|---|---|
| `measure_post_apply(apply_records, review_records)` | 245–303 (body of `measure_latest_apply`, minus the store read/sort) | New pure function. Signature: `measure_post_apply(apply_records: list[dict], review_records: list[dict[str, Any]]) -> SwingTuningPostApplyMeasurement`. `review_records` is expected **already sorted ascending by `recorded_at`** — same read/sort split as 9.3. |
| `_latest_apply_record` | 419–430 | move as-is |
| `_summarize_apply_record` | 433–447 | move as-is |
| `_latest_review_before` | 450–459 | move as-is |
| `_latest_review_after` | 462–471 | move as-is |

Imports needed: `SwingTuningPostApplyMeasurement`, `SwingTuningAppliedPatchSummary`,
`SwingTuningReviewSummary` from the dto module; `summarize_review_record`, `_metric_deltas`,
`_dict`, `_str`, `_list` from `swing_tuning_review_summary`.

### 9.5 Rewritten file: `src/application/services/swing_tuning_review_journal.py`

Keep **only** the `SwingTuningReviewJournal` class. New body, behavior-identical to today:

```python
class SwingTuningReviewJournal:
    def __init__(self, store: SwingTuningReviewStore) -> None:
        self._store = store

    def append_review(self, review: dict) -> SwingTuningReviewSaveResult:
        # unchanged body (lines 169-180 today)
        ...

    def review(self, limit: int = 10) -> SwingTuningReviewReport:
        records = self._store.read_all()
        sorted_records = sorted(
            records,
            key=lambda record: str(record.get("recorded_at") or ""),
            reverse=True,
        )
        summaries = tuple(
            summarize_review_record(record)
            for record in sorted_records[:max(limit, 0)]
        )
        return SwingTuningReviewReport(total_records=len(records), records=summaries)

    def compare_latest(self) -> SwingTuningReviewComparison:
        sorted_records = sorted(
            self._store.read_all(),
            key=lambda record: str(record.get("recorded_at") or ""),
            reverse=True,
        )
        return compare_latest_review(sorted_records)

    def measure_latest_apply(self, apply_records: list[dict]) -> SwingTuningPostApplyMeasurement:
        review_records = sorted(
            self._store.read_all(),
            key=lambda record: str(record.get("recorded_at") or ""),
        )
        return measure_post_apply(apply_records, review_records)
```

Note `compare_latest`'s early-return for `len(records) < 2` (today's lines 204–213) moves into
`compare_latest_review` itself (it is comparison policy, not facade plumbing) — `compare_latest_review`
must handle 0, 1, and 2+ records exactly as today's `compare_latest` does.

Imports this file needs after the split: `SwingTuningReviewSaveResult`, `SwingTuningReviewReport`,
`SwingTuningReviewComparison`, `SwingTuningPostApplyMeasurement` from the dto module;
`summarize_review_record` from `swing_tuning_review_summary`; `compare_latest_review` from
`swing_tuning_review_comparison`; `measure_post_apply` from `swing_tuning_post_apply_measurement`;
`SwingTuningReviewStore` from `src.domain.ports.swing_tuning_review_store` (unchanged).

---

## 10. Exact Import Migration (every call site — update, do not skip any)

Production code:

| File | Current import | New import |
|---|---|---|
| `src/adapters/cli/trade_swing_tuning_measurement_display.py:10-11` | `from src.application.services.swing_tuning_review_journal import (SwingTuningPostApplyMeasurement, ...)` | `from src.application.dto.swing_tuning_review import (SwingTuningPostApplyMeasurement, ...)` |
| `src/adapters/cli/trade_swing_tuning_review_display.py:20-22` | `from src.application.services.swing_tuning_review_journal import (SwingTuningReviewComparison, SwingTuningReviewReport, ...)` | `from src.application.dto.swing_tuning_review import (SwingTuningReviewComparison, SwingTuningReviewReport, ...)` |
| `src/adapters/cli/trade_swing_tuning_workflow_factory.py:22` | `from src.application.services.swing_tuning_review_journal import SwingTuningReviewJournal` | unchanged — class stays in this module |
| `src/adapters/cli/trade_tuning_status_commands.py:26-27` | `from src.application.services.swing_tuning_review_journal import (SwingTuningReviewJournal, ...)` | unchanged — class stays in this module |
| `src/application/services/swing_tuning_loop_status.py:23-27` | `from src.application.services.swing_tuning_review_journal import (SwingTuningAppliedPatchSummary, SwingTuningPostApplyMeasurement, SwingTuningReviewJournal, SwingTuningReviewSummary)` | split into two imports: `SwingTuningReviewJournal` from `swing_tuning_review_journal`; `SwingTuningAppliedPatchSummary, SwingTuningPostApplyMeasurement, SwingTuningReviewSummary` from `src.application.dto.swing_tuning_review` |
| `src/application/use_case/run_swing_tuning_review_use_case.py:26-27` | `from src.application.services.swing_tuning_review_journal import (SwingTuningReviewJournal,)` | unchanged — class stays in this module |

Test code:

| File | Current import | New import |
|---|---|---|
| `tests/adapters/cli/test_trade_swing_tuning_workflow_factory.py:6` | `SwingTuningReviewJournal` from `swing_tuning_review_journal` | unchanged |
| `tests/application/services/test_swing_tuning_performance.py:22-24` | `from src.application.services.swing_tuning_review_journal import (_summarize_record,)` | `from src.application.services.swing_tuning_review_summary import (summarize_review_record,)`; rename both call sites at lines 53 and 60 from `_summarize_record(...)` to `summarize_review_record(...)` |
| `tests/application/services/test_swing_tuning_review_journal.py` | `SwingTuningReviewJournal` from `swing_tuning_review_journal` | unchanged — this file keeps testing the facade end-to-end through the store, do not gut it |
| `tests/application/services/test_swing_tuning_walk_forward_guards.py:11-14` | `from src.application.services.swing_tuning_review_journal import (SwingTuningReviewJournal, _summarize_record,)` | split: `SwingTuningReviewJournal` from `swing_tuning_review_journal`; `summarize_review_record` from `swing_tuning_review_summary`; rename call sites at lines 25, 31, 37 |
| `tests/application/use_case/test_run_swing_tuning_review_use_case.py:20-22` | `SwingTuningReviewSaveResult` from `swing_tuning_review_journal` | from `src.application.dto.swing_tuning_review` |

Do a final repo-wide grep after editing to confirm nothing was missed:

```bash
grep -rn "from src\.application\.services\.swing_tuning_review_journal import" src tests
```

The only remaining matches after this task should import `SwingTuningReviewJournal` (and nothing
else) from that module.

---

## 11. Acceptance Criteria

- [ ] `src/application/services/swing_tuning_review_journal.py` contains only the
      `SwingTuningReviewJournal` class (plus its imports) — no dataclasses, no module-level `_`
      helper functions.
- [ ] `src/application/dto/swing_tuning_review.py`, `src/application/services/swing_tuning_review_summary.py`,
      `src/application/services/swing_tuning_review_comparison.py`,
      `src/application/services/swing_tuning_post_apply_measurement.py` exist with the exact symbol
      placement from Section 9.
- [ ] No file left behind imports a moved symbol from its old location (grep in Section 10 is clean).
- [ ] No compatibility re-export added anywhere for a moved symbol.
- [ ] All JSON keys, status strings (`INSUFFICIENT_HISTORY`, `READY`, `NO_APPLY_LOG`,
      `APPLY_LOG_INVALID`, `INSUFFICIENT_REVIEW_HISTORY`), note strings, and metric names are
      byte-for-byte unchanged.
- [ ] Sort order unchanged: `compare_latest` descending by `recorded_at`; `measure_latest_apply`
      ascending by `recorded_at`.
- [ ] Works without AI enabled (this code has no AI dependency — confirm none was introduced).
- [ ] Deterministic for same inputs (pure functions, no new randomness/IO).

## 12. Testing Expectations

Required, in this order:

1. Update the 6 test-file imports/renames in Section 10 — do this before writing anything new, or
   the existing regression coverage will silently stop running against the real code paths.
2. Add `tests/application/services/test_swing_tuning_review_comparison.py` exercising
   `compare_latest_review` directly and covering: 0 records, 1 record (`INSUFFICIENT_HISTORY`), 2+
   records (`READY`), the walk-forward-not-enforced note, and newly-proposed/disappeared target
   path diffing. Base cases on the existing `compare_latest` assertions already covered indirectly
   in `tests/application/services/test_swing_tuning_review_journal.py` — do not remove those
   facade-level assertions, add sibling direct-function coverage.
3. Add `tests/application/services/test_swing_tuning_post_apply_measurement.py` exercising
   `measure_post_apply` directly and covering: no apply log (`NO_APPLY_LOG`), apply log missing
   `applied_at` (`APPLY_LOG_INVALID`), missing before/after review (`INSUFFICIENT_REVIEW_HISTORY`),
   and the `READY` case with metric deltas.
4. Add `tests/application/services/test_swing_tuning_review_summary.py` exercising
   `summarize_review_record` directly for a fully-populated record and a sparse/missing-field
   record (tolerant parsing must return `None` fields, not raise).
5. Do not add a new `tests/application/dto/` test file for the DTOs — this repo's other
   `src/application/dto/*.py` modules have no dedicated DTO test files; `to_dict()` behavior stays
   covered indirectly through the summary/comparison/post-apply-measurement tests, consistent with
   existing convention.
6. All tests must run offline with no network or filesystem dependency beyond `tmp_path` (matches
   existing test style in this file's current test suite).

Run and confirm green before declaring done:

```bash
python -m pytest tests/application/services/test_swing_tuning_review_journal.py \
  tests/application/services/test_swing_tuning_review_summary.py \
  tests/application/services/test_swing_tuning_review_comparison.py \
  tests/application/services/test_swing_tuning_post_apply_measurement.py \
  tests/application/services/test_swing_tuning_performance.py \
  tests/application/services/test_swing_tuning_walk_forward_guards.py \
  tests/application/use_case/test_run_swing_tuning_review_use_case.py \
  tests/adapters/cli/test_trade_swing_tuning_workflow_factory.py \
  -q

python -m pytest tests/architecture -q
python -m pytest tests/integration/test_command_smoke_matrix.py -q
python -m pytest -q   # full suite, must stay green
ruff check src/application/dto/swing_tuning_review.py \
  src/application/services/swing_tuning_review_journal.py \
  src/application/services/swing_tuning_review_summary.py \
  src/application/services/swing_tuning_review_comparison.py \
  src/application/services/swing_tuning_post_apply_measurement.py
```

## 13. Documentation Impact

- README.md update required? No.
- New config options to document? No.
- Limitations to state? No.
- Update `docs/code-convention-audit.md` Finding 4 status from `OPEN` to `RESOLVED` following the
  exact style of Findings 1–3 (status line + resolution bullets + what was verified), once all
  acceptance criteria and tests above are green.

## 14. Agent Execution Instructions

Before implementation:

- Confirm you have read this document fully — the module map in Section 9 and import table in
  Section 10 are exhaustive; do not invent additional target files or leave symbols in
  unspecified locations.
- Confirm compliance with `AGENT_QUICKSTART.md` and `CLAUDE.md` in this repo.
- State the layer plan from Section 5 verbatim before editing.
- If any current file content differs from what Section 9's line numbers describe (i.e. the file
  changed since this doc was written), stop and re-read the live file rather than trusting the
  stale line numbers — but the symbol-to-module mapping and function boundaries stay authoritative
  regardless of line drift.

## Final Gate

If you cannot answer "yes" to all of Section 11's acceptance criteria after implementation, the
task is not done — do not mark Finding 4 as resolved in the audit doc.
