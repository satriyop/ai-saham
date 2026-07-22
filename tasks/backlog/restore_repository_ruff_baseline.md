# Restore Repository Ruff Baseline

Status: `BACKLOG`

## Task Metadata

- Task type: Refactor
- Priority: High
- Semantic classification: `NON_SEMANTIC`

## Problem Statement

The configured CI lint command currently reports 727 violations across the
repository: 506 E501, 114 I001, 48 F401, 21 E402, 13 F841, 13 W293, four F821,
three E741, three F541, one E721, and one W292. The lint job cannot be a release
gate while this baseline remains red.

## Desired Outcome

Restore the existing Ruff check and format jobs without narrowing their scope,
disabling rules, or adding an allowlist. Split the work into reviewable,
responsibility-based commits and prove each semantic area is unchanged.

## Architecture Impact

- Product layers: mechanical edits only unless a finding requires a separate bug task
- CI/config: do not weaken
- Semantic behavior: unchanged

## Acceptance Criteria

- [ ] `ruff check src/ tests/` passes with the current rule set.
- [ ] `ruff format --check src/ tests/` passes.
- [ ] Undefined names and other behavior-risking findings receive focused tests.
- [ ] Full tests and `git diff --check` pass, aside from separately recorded blockers.

## Do Not Interpret This As

- Do not add blanket ignores, per-file exemptions, or baseline allowlists.
- Do not run an unreviewed repository-wide rewrite in a dirty worktree.
- Do not mix semantic product changes into mechanical lint cleanup.
