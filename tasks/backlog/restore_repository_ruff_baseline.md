# Restore Repository Ruff Baseline

Status: `BACKLOG`

## Task Metadata

- Task type: Refactor
- Priority: High
- Semantic classification: `NON_SEMANTIC`

## Problem Statement

The configured CI lint command still fails on the whole tree. Snapshot
2026-07-27 (~667 findings), e.g. ~403 E501, ~133 I001, ~48 F401, ~24 E402,
~17 F821, plus smaller W/F classes. The lint job cannot be a reliable release
gate while this baseline remains red.

**Agent process note:** Path-scoped Ruff is already mandatory for agents on
touched `src/`/`tests/` files (`AGENT_QUICKSTART.md` Lint Gate,
`TASK_TEMPLATE.md`, `DEFINITION_OF_DONE.md` §7b). This task restores
**whole-repo** green so CI and agent close criteria converge on full
`src/` + `tests/` without path carve-outs.

## Desired Outcome

Restore the existing Ruff check and format jobs without narrowing their scope,
disabling rules, or adding an allowlist. Split the work into reviewable,
responsibility-based commits and prove each semantic area is unchanged.

After merge: remove the “until baseline is green” path-scoped carve-out language
from `AGENT_QUICKSTART.md` Lint Gate (whole-repo only).

## Architecture Impact

- Product layers: mechanical edits only unless a finding requires a separate bug task
- CI/config: do not weaken
- Semantic behavior: unchanged
- Agent docs: drop path-scoped exception after this lands

## Acceptance Criteria

- [ ] `ruff check src/ tests/` passes with the current rule set.
- [ ] `ruff format --check src/ tests/` passes.
- [ ] Undefined names (F821) and other behavior-risking findings receive focused tests where needed.
- [ ] Full tests and `git diff --check` pass, aside from separately recorded blockers.
- [ ] Agent docs state whole-repo Ruff as the only Lint Gate (no path-scoped interim).

## Do Not Interpret This As

- Do not add blanket ignores, per-file exemptions, or baseline allowlists.
- Do not run an unreviewed repository-wide rewrite in a dirty worktree.
- Do not mix semantic product changes into mechanical lint cleanup.
- Do not cancel path-scoped agent lint before this task is actually green.
