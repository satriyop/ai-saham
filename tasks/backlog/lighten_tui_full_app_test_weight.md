# Lighten TUI Full-App Test Weight

Status: `READY`

Source: full-suite timing investigation 2026-07-31. Stopgap landed and then
sharpened (see Locked Decisions §D1): `tui` is now a **cost-based** marker
auto-applied to any `tests/adapters/tui` test that drives a Textual app via
`run_test`. Fast loop: `pytest -m "not tui"`.

## 1. Task Metadata

- Task type: Refactor (test strategy)
- Priority: Low-Medium — developer inner-loop speed. Raise if the local workflow
  routinely needs the *full* suite (CI runs everything regardless).
- Semantic classification: `NON_SEMANTIC` — test-only; no product behavior,
  scoring, risk, evidence, or persisted-artifact change.
- Chosen decision: push most TUI assertions down to pure model/paint units; keep
  a small, named set of full-app journeys as the residual `tui` slice.

## 2. Problem Statement

`tests/adapters/tui/` currently splits (post-stopgap) into **88 full-app tests**
(`run_test` mounts, ~1.5-4.7s each) and ~113 already-pure model/paint tests. The
88-test `tui` slice is ~60% of full-suite wall time (≈120s of a 200s suite); the
rest of the suite runs in <80s.

This is an inverted pyramid: many Tier-3 full-app integration tests where the
intent is Tier-2 widget/state behavior. Mixed files exist (e.g.
`test_cockpit_app.py` has 3 full-app + 10 pure tests), so the split is per-test,
not per-file. This is not a leak (no network); it is structural test weight.

## 3. Desired Outcome

- Most per-widget / per-render / per-chord assertions run against a widget model
  or `paint()` output built from fake data — **no `run_test` mount**.
- A small, named set of true cross-widget journeys remains full-app (§D3).
- The `tui` slice shrinks by ≥50% in count and wall time (§D4), no coverage lost.

## 4. Locked Decisions (answers to the implementer's clarifications)

### D1 — Marker strategy: cost-based auto-tag + explicit overrides (resolves A/B/C)
`tests/adapters/tui/conftest.py` tags `tui` per-test **iff the test's source uses
`run_test`** (the canonical Textual mount). Consequences:
- A converted test that stops calling `run_test` **auto-leaves** the `tui` slice
  and joins `-m "not tui"` — *in place*, no dir move, no manual re-tag. This is
  what makes AC "converted tests move OUT of the tui slice" well-defined (it was
  impossible under the earlier path-based tag).
- Pure model tests already in the dir are already excluded from the slice
  (verified: 113 of them run in ~1.8s under `-m "not tui"`).
- Escape hatches for the rare auto-detection miss: `@pytest.mark.tui`
  (force-include, e.g. a test that mounts via a module-level helper) and
  `@pytest.mark.tui_unit` (force-exclude). Both registered in pyproject.toml.
- Not chosen: path-based auto-tag (wrong for mixed files); split-dir (needs
  moving/splitting mixed files); opt-out-only (would leave pure tests wrongly
  tagged until each is touched).

### D2 — Preferred harness order (use the lowest tier that proves the behavior)
1. **Pure**: build the widget/view-model (`build_*_model(...)`) or call
   `widget.paint()` / render helper with fake data; assert on the model or the
   `Static`/renderable content. No app, no DOM.
2. **Thin host**: a minimal single-screen `run_test` host **only** when the
   behavior genuinely needs the DOM (focus, layout, reactive mount).
3. **Full `CockpitApp`**: journeys only (§D3).
Do not reach for tier 3 "to be safe" — that is the habit this task removes.

### D3 — Frozen residual full-app journey set (keep these as `tui`; everything else drops to a lower tier)
- Accum board → Enter → Judge → `d` toggle → `esc` trail
- Broker list → home → deep view (`m` matrix or `c` calendar)
- View ticker → detail
- Pre-open inspect (one representative)
- (Optional) Plan → paper
Target residual: ~4-6 journeys. Anything outside this list should not mount the
full app by default.

### D4 — Success metric (record in the Completion Record)
- **Primary (hard):** `pytest -m tui` **test count** ↓ ≥50% (baseline 88 → ≤44),
  trending toward the §D3 residual (~6-15).
- **Secondary (reported):** `pytest -m tui` wall time before/after (baseline
  ≈120s) and total-suite wall time before/after. Count is primary because it is
  machine-independent.

### D5 — Cadence: dedicated small-PR series by surface, not purely opportunistic
Convert in a bounded series so this does not stay forever-READY:
1. Broker-desk widgets (home/top/matrix/calendar/flow-history)
2. Judge desk + judge card grid + flag chips
3. Ticker view / desks journey
4. Chords / keymap (§D6)
Opportunistic conversion while editing a surface is also welcome, but the series
is what guarantees completion.

### D6 — Chords / keymap: extract a pure dispatch table if cheap, else one e2e
First check whether the cockpit key→action bindings can be read as a pure table
(binding map) and asserted without mounting. If yes, test that table purely and
delete the per-chord app mounts. If Textual's binding system genuinely requires a
running app, keep **one** representative chord e2e that proves dispatch wiring —
do **not** keep one full-app mount per chord.

### D7 — Visual-parity / interaction tests
For expand/toggle logic (flag chips, judge detail), prefer `FlagChip` /
`JudgeDesk` `paint()`/model isolation. Keep **one** full journey that proves the
chip↔stage wiring end-to-end; the rest move to pure.

## 5. Non-Goals

- No deletion of behavioral coverage — behaviors keep a test, at a lower tier.
- No change to TUI/app runtime behavior.
- No big-bang rewrite; follow the §D5 series.
- No removal of the `tui` / `tui_unit` markers or the conftest (they remain the
  mechanism for the residual e2e set).

## 6. Architecture Impact

```md
Layer plan:
- Domain / Application / Infrastructure: not touched.
- Adapter (TUI): test-only refactor; may extract small pure view-model / render
  helpers from widgets to make them unit-testable — a behavior-preserving
  extraction, not a redesign.
```

## 7. Acceptance Criteria

- [ ] Converted areas assert at model/paint level (no `run_test`), preserving the
      original behavioral assertions.
- [ ] Converted tests auto-leave the `tui` slice (they no longer reference
      `run_test`); the residual `tui` set matches §D3.
- [ ] `pytest -m tui` count ↓ ≥50% vs the 88 baseline (§D4 primary).
- [ ] `pytest -m "not tui"` and full `pytest` stay green.
- [ ] Marker strategy remains cost-based per §D1; any `@pytest.mark.tui` /
      `tui_unit` override is justified in a comment.
- [ ] No product behavior change; deterministic.
- [ ] **Lint Gate**: `ruff check`/`format --check` clean for touched files.

## 8. Testing / Verification

- Record baseline vs final: `-m tui` count and wall time, total-suite wall time.
- Whole-repo Ruff on touched test files.

## 9. Notes on Textual harnesses

- The genuinely *free* path is **pure**: construct the widget/model and assert on
  its reactive state or its rendered `Static`/renderable — no app.
- `App.run_test()` (a pilot) is **not** free: it boots and drives the whole app.
  Use it only for §D3 journeys or when a behavior truly needs the DOM (tier 2/3).
- Because the marker keys on `run_test`, "make it pure" and "leave the slice" are
  the same action — removing the `run_test` mount does both.

## Completion Record

- Completed date:
- Surfaces converted (per §D5):
- `-m tui` count before/after:
- `-m tui` wall time before/after:
- Total-suite wall time before/after:
- Verification result:
