# Refactor: Restore Adapter Thinness In Formula Lifecycle Commands

> **DONE (2026-07-26)** — commit `c7bd245`. Implemented 4 application use cases
> (List/Show/Delete/PersistGenerated), relocated `StoredFormula` to
> `application/dto`, added the `FormulaStore` port, and isolated infra wiring in
> `indicator_formula_factory`. CLI behavior verified byte-for-byte against a
> captured baseline; 17 new offline unit tests + 59 affected tests pass; ruff clean.
> The verb-set gaps (`strategy show/delete`, `indicator validate`) remain
> deferred per the non-goals.

## 1. Task Metadata

- **Task Type:** Refactor (architecture compliance)
- **Priority:** Medium
- **Size:** Medium refactor (one adapter module + new application use cases; no domain/infra changes)
- **Created:** 2026-07-26
- **Related:** `tasks/done/audit_adapter-thinness-hidden-state-audit-2026-07-14.md`
  (that sweep fixed `strategy_lifecycle_commands.py` finding #2 but did **not**
  cover `indicator_formula_commands.py` — this task closes that straggler).

---

## 2. Problem Statement

`src/adapters/cli/indicator_formula_commands.py` owns workflow, policy, and
persistence decisions that CLAUDE.md reserves for the application layer. The
module reaches directly into infrastructure (`FormulaStorage`,
`create_indicator_registry`) and makes business decisions inline, so the adapter
is not thin. This is the same class of violation the 2026-07-14 audit fixed for
strategy commands; the formula lifecycle module slipped through that sweep.

Concrete deviations (current `indicator_formula_commands.py`):

| Location | What the adapter does today | Rule violated |
|---|---|---|
| `delete` L180 (`BUILTIN_NAMES`) | Decides **what is deletable** (business policy) | adapters must not own business status calculation / policy |
| `delete` L187–207 | exists-check → delete → interpret `deleted` bool | adapters must not own persistence decisions |
| `show` L148–156 | instantiate `FormulaStorage`, `get`, not-found fallback | persistence read + business logic in adapter |
| `list_indicators` L134–137 | instantiate `FormulaStorage`, `load_all()` | persistence read in adapter |
| `create` L79–86 | auto-generate `CUSTOM_…` **name policy** | business logic in adapter |
| `create` L88–102 | register-in-memory **and** persist; treat register-fail as warn, save-fail as warn | persistence/workflow orchestration in adapter |

Note: `create` already calls `CreateIndicatorFromIntentUseCase` for the AI step,
then re-acquires business decisions (naming, register+persist orchestration) on
the way to disk. That post-use-case leakage is the core smell.

---

## 3. Desired Outcome

- `indicator_formula_commands.py` becomes thin: parse args → call use case →
  format output → map errors. `typer.confirm()` (UI) may remain in the adapter.
- Formula lifecycle policy and persistence orchestration live in
  `application/use_case`.
- Observable CLI behavior is **unchanged** for `saham indicator create / list /
  show / delete` (same output, same exit codes, same confirmation UX).

---

## 4. Non-Goals (Out Of Scope)

- No new CLI commands (the `strategy show`, `strategy delete`, `indicator
  validate` verb-set gaps are deferred — "close the gap later").
- No new data providers, no AI model changes, no schema change.
- No change to `FormulaStorage` on-disk format or `config/formulas.yaml`.
- No change to `saham indicator compute` / `snapshot` (execution verbs).
- No risk/signal/evidence-authority changes.

---

## 5. Architecture Impact Assessment

- Layers touched: **Application (new use cases)**, **Adapter (refactor to thin)**.
- New dependency? **No.**
- Affects determinism? **No** (same deterministic paths; AI only in `create`,
  already bypassable via `--no-save` / mock provider).
- Persistence changes? **No schema change**; persistence *decisions* move from
  adapter into application (delete rule, register/persist orchestration).
- Warm-up data? **No.**
- Places orchestration/policy inside an adapter? **No — this task removes it.**

```md
Layer plan:
- Domain: not touched. (Name-generation policy could later move to domain; keep
  in application for this task to limit blast radius.)
- Application: NEW — ListFormulasUseCase, ShowFormulaUseCase, DeleteFormulaUseCase;
  extend the create path to own name-generation + register/persist orchestration.
  DeleteFormulaUseCase owns the BUILTIN_NAMES protection rule and returns a
  result enum {DELETED, NOT_FOUND, BUILTIN_PROTECTED}; expose a preview(name)
  read so the adapter can render before typer.confirm().
- Infrastructure: not touched structurally. FormulaStorage reused, but injected
  via a composition factory instead of being instantiated in the adapter.
- Adapter: refactor create/list/show/delete to thin — parse, call use case,
  format, map errors. Keep typer.confirm() only.
```

---

## 6. AI Usage Declaration

- **AI-assisted (non-authoritative)**, unchanged. Only `create` uses AI to
  translate intent → formula, exactly as today. With AI disabled the module
  still lists/shows/deletes/validates stored formulas; `create` degrades the
  same way it does now (mock provider / error path). This refactor does not add
  or remove AI involvement.

---

## 7. Risk, Signal, And Evidence Authority Considerations

- Decision components affected: **none** (SignalEngine, RiskEngine, TradeSetup,
  market context, setup policy, evidence authority all untouched).
- Does not change what can produce ENTER/WATCH/AVOID.
- Does not promote diagnostic evidence or change tuning eligibility.

---

## 8. Data & Persistence

- Reads: stored formulas (`config/formulas.yaml` via `FormulaStorage`), builtin
  registry names.
- Writes: formula save/delete — same operations as today, same file, moved
  behind use cases.
- Storage location unchanged. **Schema change? No.**
- Source semantics unchanged (same `FormulaStorage` API), so old/new are
  semantically equivalent by construction.

---

## 9. Acceptance Criteria

- [ ] `create / list / show / delete` produce identical output + exit codes to
      current behavior (verify against captured before/after).
- [ ] `indicator_formula_commands.py` no longer instantiates `FormulaStorage` or
      `create_indicator_registry` directly; both arrive via composition/use case.
- [ ] `BUILTIN_NAMES` protection lives in `DeleteFormulaUseCase`, not the adapter.
- [ ] Name-generation + register/persist orchestration live in the create path
      use case, not the adapter.
- [ ] Works without AI enabled (list/show/delete unaffected; create degrades as
      today).
- [ ] Deterministic for same inputs.
- [ ] No non-goals violated; adapter thinness reviewed.
- [ ] Complies with DEFINITION_OF_DONE.md.

---

## 10. Testing Expectations

- Unit-test the new application use cases (offline, no network):
  - `DeleteFormulaUseCase`: BUILTIN_PROTECTED path, NOT_FOUND path, DELETED path.
  - `ShowFormulaUseCase`: found vs not-found (returns available names).
  - `ListFormulasUseCase`: builtin + custom composition.
  - Create-path persist orchestration: name auto-generation, register-fail is
    non-fatal, save-fail is non-fatal, `--no-save` skips persistence.
- Mocks: fake `FormulaStorage` / registry stubs; mock AI translator for create.
- Adapter tests may stay light (thin wiring); do not let CLI tests substitute
  for the use-case workflow tests.

---

## 11. Documentation Impact

- README update: **No** (behavior unchanged).
- New config options: **No.**
- Limitations to state: **No.**

---

## 12. Agent Execution Instructions

Before implementation the agent must:
- Re-read `AGENT_QUICKSTART.md` + the refactor checklist in `AI_AGENT_CHECKLIST.md`.
- Capture current CLI output for create/list/show/delete as the behavior baseline.
- Confirm the layer plan above; state any ambiguity (e.g. whether name-generation
  policy should land in domain vs application) before coding.
- Follow the deterministic-first path; keep AI confined to the create translator.

## Suggested Build Order (severity-first)

1. `DeleteFormulaUseCase` — highest severity (only one leaking a *business rule*).
2. `ShowFormulaUseCase` + `ListFormulasUseCase` — persistence-read cleanup.
3. Create-path: lift name-generation + register/persist orchestration into the
   use case.
4. Composition factory wiring + adapter thinning + tests green.

## Final Gate

DoD compliance: behavior is unchanged and reproducible; the change *removes*
adapter policy/persistence ownership rather than adding capability; no risk /
signal / evidence surface is touched; new application logic is unit-tested offline.
