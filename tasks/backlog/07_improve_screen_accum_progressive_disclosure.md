# Compact-By-Default Accum Output With Explicit Drill-Down

Status: `READY` — independent; ships anytime. Slice 4 is cheaper after task 1.
Sequence: **7 of 8** — see `tasks/backlog/00_SEQUENCE_accum_baseline_and_learning_loop.md`

## 1. Task Metadata

**Task Title**
Make `screen accum` render a compact decision table by default and move the
panel wall behind explicit drill-down flags.

**Task Type**
Refactor (adapter presentation only)

**Priority**
Medium — highest-frequency friction in daily use; zero engine risk.

---

## 2. Problem Statement

A single-ticker `screen accum` run renders **ten stacked Rich panels**:
Judgment, Candidate Actions, Setup pattern match, Decision·Action Why, Accum
score components, Signal summary, Signal·FlowGrp components, Risk Status, Data
Coverage, SECTOR MACRO, Enrichment Details
(`src/adapters/cli/screen_accum_single_display.py:570-628`). Three tickers
produce a screenful of nested boxes with no visual hierarchy.

Presentation for this one command spans ~1,683 lines across
`screen_accum_single_display.py` (804), `decision_display.py` (385),
`screen_accum_multi_display.py` (218), `screen_accum_formatters.py` (276). The
command carries **28 flags**.

This is a known, self-identified defect. `tasks/thought/improvement_saham_screen.md:536`:

> "Three tickers generated a very long nested panel containing action, seven
> evidence rows per ticker, signal, risk rationale, data, and enrichment details.
> The default should be a compact decision table."

Ranked priority 8 for daily usability in that document (line 666-678) and still
unresolved. `docs/design/tui-cockpit-opencode.md` independently lists "flat CLI
dump as only ticker stage without hierarchy" and "judge multi-chip density wall"
in its forbidden-patterns catalogue.

Secondary defect, same surface: the Why line leaks an internal Python symbol to
every user, on every row —

```
Why  authority 100% · setup readiness UNAVAILABLE (missing: setup_evidence) · gate open
```

`setup_evidence` is an identifier, not operator language.

---

## 3. Desired Outcome

- Default `screen accum` output is a single compact decision table: one row per
  ticker, no nested panels.
- Every panel currently shown by default remains reachable through an explicit,
  discoverable flag. Nothing is deleted.
- The output states what to run next to see more.
- Operator-facing strings contain no code identifiers.
- CLI and TUI keep rendering from the same shared formatters — no divergence.

---

## 4. Non-Goals

- **No engine, scoring, gate, or action changes.** Presentation only. If a value
  looks wrong, that is a different task.
- No change to what data is computed — only what is printed by default.
- No removal of any existing panel; drill-down must reach all of them.
- No TUI restructure (the TUI already has hierarchy).
- No new flags beyond what drill-down requires; prefer reusing `--full`,
  `--detail`, and the existing flag vocabulary.

---

## 5. Architecture Impact Assessment

- **Domain / Application / Infrastructure:** **not touched.**
- **Adapter:** `screen_accum_single_display.py`,
  `screen_accum_multi_display.py`, `screen_accum_formatters.py`, and
  `src/adapters/shared/decision_display.py` for the Why copy.

New dependency: **No.**
Determinism: **No.**
Persistence: **No.**
Warm-up: **No.**
Policy in adapter: **No** — and this task must not add any. Display-mode
selection from an explicit user flag is parsing, not policy.

```md
Layer plan:
- Domain: not touched
- Application: not touched
- Infrastructure: not touched
- Adapter: restructure accum display into compact default + drill-down;
  reword Why copy in the shared decision_display module
```

---

## 6. AI Usage Declaration

**No AI involved.**

---

## 7. Risk, Signal, And Evidence Authority Considerations

No decision component is affected. **Does this change what can produce
ENTER/WATCH/AVOID? No.**

One constraint from the multi-surface parity rules in `AGENT_QUICKSTART.md`:
Why / setup readiness / Accum breakdown / decision stack must stay in
`src/adapters/shared/decision_display.py`. Do not fork a CLI-only copy to get a
shorter string — change the shared function and let the TUI benefit.

Do not invent `READY`. `decision_display.py:91` is explicit: surface it only
when the value object says so.

---

## 8. Data & Persistence

- **Read:** nothing new. **Written:** nothing. **Schema change:** No.

---

## 9. Acceptance Criteria

- [ ] Default multi-ticker output is one table, no nested panels.
- [ ] Default single-ticker output fits a standard terminal without scrolling.
- [ ] Every previously-default panel reachable via a documented flag.
- [ ] Output names the next command to run for detail.
- [ ] No operator-facing string contains a code identifier
      (`setup_evidence`, `flow_ev`, etc.) — enforced by test.
- [ ] TUI renders identically to before, or better; no shared-formatter fork.
- [ ] `tests/adapters/shared/test_multi_surface_inventory.py` still passes.
- [ ] **Lint Gate** passes.

---

## 10. Slices (each slice = one commit)

**Slice 1 — Snapshot current output.**
Golden-output tests for the current default rendering, so the restructure is
provably lossless in content.
Commit: `test(cli): golden-snapshot current screen accum output`

**Slice 2 — Compact default for multi-ticker.**
One-row-per-ticker table. Panels move behind `--full`.
Commit: `refactor(cli): compact default table for multi-ticker accum board`

**Slice 3 — Compact default for single-ticker.**
Judgment summary + next-command hint; the other nine panels behind flags.
Commit: `refactor(cli): compact default for single-ticker accum detail`

**Slice 4 — Operator language in the Why line.**
Reword shared `decision_display.py` strings; no code identifiers. Add the
enforcing test. Cheaper after task 1, since the `missing: setup_evidence` case
largely disappears — but do not block on it.
Commit: `fix(display): remove code identifiers from operator-facing Why copy`

**Slice 5 — Flag-surface audit.**
Group the 28 flags in `--help` by purpose; document the drill-down path.
Commit: `docs(cli): group and document screen accum flag surface`

---

## 11. Testing Expectations

- Golden output for default and each drill-down flag.
- Content-completeness test: the union of drill-down output contains everything
  the old default contained (proves nothing was lost).
- Identifier-leak test over all operator-facing strings in the accum path.
- Multi-surface inventory test still green.
- TUI accum board unchanged.

Adapters may be lightly tested per `CLAUDE.md`, but the golden tests are the
safety net for a large presentation refactor — do not skip them.
`pytest -m "not tui"` for the inner loop; run the `tui` marker before close.
Ruff before close.

---

## 12. Documentation Impact

- README: **Yes** if it shows example output.
- `CLI_GUIDE.md` / `CLI_REFERENCE.md`: **Yes** — document the drill-down path.
- New config options: **No.**
- Limitations: **No.**

---

## 13. Required Reading

- `AGENT_QUICKSTART.md` — multi-surface parity section (binding here)
- `tasks/thought/improvement_saham_screen.md` §"UI/UX review" (lines 515-596)
- `docs/design/tui-cockpit-opencode.md` — forbidden-patterns catalogue
- `src/adapters/shared/decision_display.py`, `score_display_labels.py`,
  `screen_accum_board_fields.py`

---

## 14. Do Not Interpret This As

- **Not** permission to change any computed value, threshold, or action.
- **Not** permission to delete a panel. Move it, don't drop it.
- **Not** permission to fork a CLI-only copy of a shared formatter.
- **Not** permission to invent a `READY` state (ADR-054).

---

## 15. Completion Record

- Completed date:
- Slice commits:
- Default output line count before → after:
- Drill-down flags and what each reveals:
- Test / Lint result:
