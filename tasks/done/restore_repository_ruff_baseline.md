# Restore Repository Ruff Baseline

> [!NOTE]
> **Done 2026-07-27.** Whole-repo `ruff check src/ tests/` and
> `ruff format --check src/ tests/` pass. Path-scoped agent carve-out removed
> from `AGENT_QUICKSTART.md` / DoD / task template.

Status: `DONE`

## Task Metadata

- Task type: Refactor
- Priority: High
- Semantic classification: `NON_SEMANTIC`

## Problem Statement (historical)

CI lint reported hundreds of Ruff findings (~630+ before autofix; was ~727
earlier). The lint job could not act as a reliable release gate while red.

## Shipped

- `ruff check --fix` + `ruff format` across `src/` and `tests/`
- Manual fixes: F821 (imports / dead audit helpers), E402, E721, E741, F841, E501
- Removed dead candidate-observation audit helpers that referenced deleted use cases
- Restored re-export of `format_disc_pct_plain` incorrectly dropped as unused
- Agent docs now require whole-repo Ruff (same as CI)

## Acceptance Criteria

- [x] `ruff check src/ tests/` passes with the current rule set.
- [x] `ruff format --check src/ tests/` passes.
- [x] Behavior-risking F821s addressed (imports or dead code removal).
- [x] Agent docs state whole-repo Ruff as the Lint Gate (no path-scoped interim).
