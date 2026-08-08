# Compact-By-Default Accum Output With Explicit Drill-Down

Status: `VETTED / READY FOR IMPLEMENTATION` — code-first re-vet **2026-08-08**.
Sequence: **7 of 8** — independent of the accumulation config freeze (adapter
presentation only). See `tasks/backlog/00_SEQUENCE_accum_baseline_and_learning_loop.md`.

## 1. Task Metadata

**Task Title**
Make `screen accum` render a compact decision table by default and move the
panel wall behind explicit drill-down flags.

**Task Type**
Refactor (adapter presentation only)

**Priority**
Medium — highest-frequency daily CLI friction; zero engine risk; safe during
accum freeze.

---

## 2. Re-Vet Verdict (2026-08-08)

### 2.1 Core premise still true for the single-window path

`display_results` in `src/adapters/cli/screen_accum_single_display.py` still
builds a **nested panel wall on every default run**. Current order (≈808 lines):

| # | Panel title (approx.) | Gated by flag today? |
|---|------------------------|----------------------|
| 1 | Judgment (single-ticker only, ADR-054) | No |
| 2 | Candidate Actions | No |
| 3 | Setup pattern match (diagnostic) | No |
| 4 | Decision · Action Why | No |
| 5 | Accum score components | No |
| 6 | Signal summary | No |
| 7 | Signal · FlowGrp components | No |
| 8 | Risk Status (+ gate detail lines) | No |
| 9 | Data Coverage | No |
| 10 | Market context (if present) | No |
| 11 | Sector macro (single-ticker if present) | No |
| 12 | Enrichment Details (if rows) | No |
| — | Diagnostic evidence bags | `--setup` / `--with-flow-detail` / `--with-sentiment` / `--full` only |
| — | Run Context + scoring definitions | **`--detail` only** |

Critical finding: **`--full` and `--detail` do not gate the main panel wall.**

- `--detail` → `include_detail=True` → only appends **Run Context** (and scoring
  definitions) after the wall (`display_results` ~L720–807).
- `--full` → diagnostic evidence request (`include_full`) for judgment-desk
  bags — **additional** panels, not a compact mode.

So the draft’s “move panels behind `--full`” must be read as **reusing the flag
vocabulary**, not as “already implemented.” Implementation must either:

1. invert meaning carefully (breaking change — document), or
2. add an explicit compact/default contract (e.g. default compact; `--detail` or
   a progressive set expands sections; keep `--full` for diagnostic bags).

Prefer (2) if operators already treat `--full` as diagnostic evidence.

### 2.2 Multi-window path is already compact-by-default

`display_multi` (`screen_accum_multi_display.py`, ~218 lines) already renders
**one side-by-side table** by default; extra context is behind `include_detail`
(`--detail`). Universe multi boards are **not** the main defect.

Scope of the compact default work:

| Path | Default today | Task 07 action |
|------|---------------|----------------|
| `display_multi` / `--multi` | Compact table | Keep; optional polish only |
| `display_results` (explicit ticker or single-window board) | Panel wall | **Primary target** |
| TUI board / judge | Hierarchical | **Out of scope** (non-goal) |

### 2.3 Shared presentation stack (post-refactor) — still the right boundary

Measured LOC (2026-08-08):

| Module | LOC | Role |
|--------|----:|------|
| `screen_accum_single_display.py` | 807 | Single-window panel wall |
| `screen_accum_commands.py` | 584 | 28 `typer.Option`s |
| `screen_accum_enrichment_display.py` | 455 | Enrichment / factor dump |
| `shared/decision_display.py` | 415 | Why / readiness / breakdown (CLI+TUI) |
| `screen_accum_formatters.py` | 276 | Cells / labels |
| `screen_accum_multi_display.py` | 218 | Multi-window board |
| `screen_accum_diagnostic_evidence_display.py` | 208 | ADR-054 diagnostic bags |
| `screen_accum_display.py` | 29 | Facade re-exports |

Also shared (must not fork):

- `src/adapters/shared/screen_accum_board_fields.py` — board cells
- `src/adapters/shared/score_display_labels.py` — Signal/Accum vocabulary
- `src/adapters/shared/multi_surface_inventory.py` — dual-surface inventory

Facade: `screen_accum_display.py` re-exports `display_results` / `display_multi`.

### 2.4 Why-line identifier leak — partially fixed; residual risk remains

`format_setup_readiness` in `decision_display.py` **already documents and
rejects** the old operator string:

```text
(missing: setup_evidence)   # retired — wrong twice (defect tone + identifier)
```

Current UNAVAILABLE path (~L94–105):

- Does **not** invent `missing:` labels for by-design flow-only readiness.
- If `missing_required_inputs` is non-empty, it still joins VO strings into
  `setup readiness UNAVAILABLE […] (detail)` — any **code-shaped** tokens in
  that tuple still leak.

Re-vet action for slice 4:

1. Audit `missing_required_inputs` / `failed_requirements` producers for
   snake_case identifiers.
2. Map to operator phrases in **shared** `decision_display` (or map at VO
   boundary if already human).
3. Keep existing tests in `tests/adapters/shared/test_decision_display.py` and
   add an identifier-leak guard.

Do **not** treat slice 4 as “blocked on ADR-067”; setup_quality is already
retired — residual is residual identifiers, not setup_quality return.

### 2.5 Flag surface still ~28 options

`screen_accum_commands.py` still has **28** `typer.Option` calls (filters,
windows, diagnostics, refresh, save, format, …). Grouping in `--help` remains
valuable; progressive disclosure should not invent a second parallel flag
forest.

### 2.6 Tests already present — golden baseline still needed

`tests/adapters/cli/test_screen_accum_display.py` exercises render smoke and
shared Why parity, but there is **no golden “default is compact” contract**.
Slice 1 remains useful: snapshot current default line/panel structure so the
restructure proves content is still reachable via drill-down.

### 2.7 Obsolete draft claims

| Draft | Update |
|-------|--------|
| “Slice 4 cheaper after task 1” | Task 1 (ADR-068) is **done**; not a gate |
| `decision_display.py:385` / single_display:804 | LOC drifted (~415 / ~807) |
| Why always prints `setup_evidence` | Softened; residual identifier audit remains |
| Multi path equally broken | Multi already compact |

---

## 3. Desired Outcome

- Default **single-window** `screen accum` output is one compact decision table
  (one row per ticker) plus a short next-command hint — **no nested panel wall**.
- Every section currently shown by default remains reachable through an
  explicit, discoverable flag (or progressive flag set). Nothing deleted.
- Default multi-window stays one table (already true).
- Operator-facing Why/readiness strings contain no code identifiers.
- CLI and TUI keep sharing `decision_display` / board field extractors — no
  CLI-only fork of Why.

---

## 4. Non-Goals

- **No engine, scoring, gate, action, or identity changes.** Presentation only.
- No change to what is **computed** — only what is **printed by default**.
- No removal of panels; move behind flags.
- No TUI cockpit restructure (TUI already hierarchical).
- No new dependency; no persistence; no config freeze conflict.
- Do not invent `READY` (ADR-054).

---

## 5. Architecture Impact Assessment

```md
Layer plan:
- Domain: not touched
- Application: not touched
- Infrastructure: not touched
- Adapter: restructure screen_accum_* display defaults + shared Why copy polish
```

Display-mode selection from user flags is **adapter parsing**, not policy.

---

## 6. AI Usage Declaration

**No AI involved.**

---

## 7. Risk, Signal, And Evidence Authority

No decision component. **Does this change ENTER/WATCH/AVOID? No.**

Binding parity rule (`AGENT_QUICKSTART.md`): Why / setup readiness / Accum
breakdown / decision stack stay in `src/adapters/shared/decision_display.py`.

---

## 8. Data & Persistence

None.

---

## 9. Acceptance Criteria

- [ ] Default multi-ticker **single-window** output is one table (no nested
      Candidate Actions / Why / Accum / Signal / Risk / Data panel stack).
- [ ] Default single-ticker output fits a standard terminal without scrolling
      (judgment strip optional; full case file behind flags).
- [ ] Every previously-default section reachable via documented flag(s).
- [ ] Output names the next command for detail (e.g. `--detail`, explicit
      diagnostic flags, or `plan swing TICKER` where already correct).
- [ ] No operator-facing string in the accum path contains code identifiers
      (`setup_evidence`, `flow_ev`, snake_case module tokens) — enforced by test.
- [ ] `--full` semantics documented: diagnostic bags vs progressive case-file
      expansion (no silent ambiguity).
- [ ] TUI board/judge behavior unchanged unless improved via shared Why copy.
- [ ] `tests/adapters/shared/test_multi_surface_inventory.py` green.
- [ ] Focused CLI display tests + Lint Gate green.

---

## 10. Slices (each = one commit)

**Slice 1 — Snapshot current default structure.**
Golden/smoke tests documenting panels printed by default for single- and
multi-ticker single-window paths (and multi-window control).
Commit: `test(cli): snapshot screen accum default panel structure`

**Slice 2 — Compact default for multi-ticker single-window board.**
`display_results` with `len(candidates) > 1`: one board table using shared
`extract_screen_accum_board_fields`; case-file panels behind progressive flags.
Commit: `refactor(cli): compact default multi-ticker single-window accum board`

**Slice 3 — Compact default for single-ticker judgment.**
Judgment strip + compact summary + next-command hint; full ADR-054 case file
behind `--detail` and/or explicit section flags; keep diagnostic bags on
`--full` / existing diagnostic flags.
Commit: `refactor(cli): compact default single-ticker accum judgment`

**Slice 4 — Operator language residual audit.**
Shared `decision_display` only; map any remaining identifier tokens; leak test.
Commit: `fix(display): remove residual code identifiers from Why copy`

**Slice 5 — Flag-surface / help grouping.**
Group the 28 options in `--help` (filters / board / diagnostics / refresh /
output); document progressive disclosure path in CLI guide if present.
Commit: `docs(cli): group screen accum flags and progressive disclosure`

---

## 11. Testing Expectations

- Structure/golden tests for default vs drill-down (slice 1→3).
- Content-completeness: union of drill-down output covers old default sections.
- Identifier-leak test over operator-facing accum display strings.
- Multi-surface inventory + existing `test_screen_accum_display` / decision_display.
- Inner loop: `pytest -m "not tui"` on adapter display modules; run `tui` marker
  only if shared Why changes affect TUI copy tests.
- Lint Gate for any Python under `src/` / `tests/`.

---

## 12. Documentation Impact

- CLI guide/reference: progressive disclosure path.
- README: only if it shows sample `screen accum` output.
- No config options.

---

## 13. Required Reading

- `AGENT_QUICKSTART.md` — multi-surface parity
- `src/adapters/cli/screen_accum_single_display.py` (`display_results`)
- `src/adapters/cli/screen_accum_multi_display.py` (`display_multi`)
- `src/adapters/cli/screen_accum_commands.py` (flag wiring)
- `src/adapters/shared/decision_display.py`
- `src/adapters/shared/screen_accum_board_fields.py`
- `tests/adapters/cli/test_screen_accum_display.py`
- `tests/adapters/shared/test_decision_display.py`
- `docs/design/tui-cockpit-opencode.md` (forbidden density patterns — context)

---

## 14. Do Not Interpret This As

- Permission to change computed scores, gates, or actions.
- Permission to delete a panel (move behind flags only).
- Permission to fork CLI-only Why formatters.
- Permission to invent READY.
- Permission to touch accum corpus / identity / freeze.

---

## 15. Completion Record

- Completed date:
- Slice commits:
- Default output panel count before → after (single-window multi + single-ticker):
- Progressive flag map (flag → sections):
- Residual identifier tokens removed:
- Test / Lint result:
