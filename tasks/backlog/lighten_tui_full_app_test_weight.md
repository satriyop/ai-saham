# Lighten TUI Full-App Test Weight

Status: `READY`

Source: full-suite timing investigation 2026-07-31. Stopgap already landed
(`tui` marker + `tests/adapters/tui/conftest.py` auto-tagging → `-m "not tui"`
for the fast loop). This task is the durable fix.

## 1. Task Metadata

- Task type: Refactor (test strategy)
- Priority: Low-Medium — developer-loop speed; not blocking correctness.
- Semantic classification: `NON_SEMANTIC` — test-only; no product behavior,
  scoring, risk, evidence, or persisted-artifact change.
- Chosen decision: push most TUI assertions down to widget / view-model unit
  level; keep a small set of full-app end-to-end journeys marked `tui`.

## 2. Problem Statement

`tests/adapters/tui/` is 201 tests across 40 files, and it is **~60% of the
full-suite wall time** (>120s of a 200s suite; the ~5,566 non-TUI tests run in
<80s). Each TUI test mounts and paints a real Textual `App` (~1.5-4.7s) and
simulates keypresses — even when the assertion is about a single widget, chord,
or rendered cell.

This is an inverted test pyramid: many Tier-3 full-app integration tests where
most of the intent is Tier-2 widget/state behavior. It is not a leak (no network;
the stopgap only hides the cost from the fast loop), it is structural.

## 3. Desired Outcome

- The majority of per-widget / per-chord / per-render assertions run against a
  widget (or its view-model) instantiated with fake data — no full `App` mount.
- A small, deliberate set of true cross-widget journeys remains as full-app e2e
  tests (kept under the `tui` marker).
- Full-suite wall time drops materially (target: TUI slice well under half its
  current cost) with no loss of behavioral coverage.

## 4. Non-Goals

- No deletion of coverage — behaviors keep a test, at a lower altitude.
- No change to TUI/app runtime behavior.
- No big-bang rewrite: convert opportunistically when a cockpit area is touched.
- No removal of the `tui` marker / conftest stopgap (it stays useful for the
  residual e2e set).

## 5. Approach (incremental)

1. Inventory TUI tests by what they actually assert: (a) widget renders X given
   data, (b) a chord/key dispatches to a view, (c) a genuine multi-widget
   journey.
2. For (a): test the widget in isolation (mount just the widget, or assert on the
   render-data/view-model it produces) instead of the whole app.
3. For (b): test the keymap/dispatch mapping directly where possible, not via a
   full app paint.
4. For (c): keep as full-app e2e, marked `tui` — but consolidate to a handful of
   representative journeys rather than one per interaction.
5. Convert file-by-file when that cockpit area is next edited; do not block other
   work on a sweep.

## 6. Architecture Impact

```md
Layer plan:
- Domain / Application / Infrastructure: not touched.
- Adapter (TUI): test-only refactor; may extract small view-model/pure-render
  helpers from widgets to make them unit-testable (no behavior change).
```

## 7. Acceptance Criteria

- [ ] Converted areas assert at widget/view-model level without a full `App`
      mount, preserving the original behavioral assertions.
- [ ] Residual full-app journeys remain marked `tui`.
- [ ] `pytest -m "not tui"` stays green; converted tests move OUT of the `tui`
      slice (net TUI-slice time drops).
- [ ] No product behavior change; deterministic.
- [ ] **Lint Gate**: `ruff check`/`format --check` clean for touched files.

## 8. Testing / Verification

- Before/after: record `tui`-slice wall time and count; show the slice shrank.
- Whole-repo Ruff on touched test files.

## 9. Notes

- Textual supports testing widgets without a full app run via `App.run_test()`
  pilots scoped to a single screen, and widgets can often be exercised by
  constructing them with fake data and asserting on their reactive state /
  render output. Prefer the smallest harness that still proves the behavior.

## Completion Record

- Completed date:
- Files converted:
- TUI-slice time before/after:
- Verification result:
