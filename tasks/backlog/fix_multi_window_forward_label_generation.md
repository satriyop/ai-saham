# Fix Multi-Window Forward Label Generation

Status: `BACKLOG`

## Task Metadata

- Task type: Bugfix
- Priority: High
- Semantic classification: `LABEL_POLICY` pending root-cause confirmation;
  fail closed and apply the required compatibility/version review before editing

## Problem Statement

`BackfillSignalObservationsUseCase` records three canonical observations for
windows 7/30/90, but the real label-generation path reports zero generated
labels where the existing contract expects one attempt per canonical window.
This keeps the full suite red and may indicate identity or label-policy drift.

## Desired Outcome

Diagnose the exact skip reasons and restore the explicitly governed
observation-to-label behavior without collapsing windows, fabricating identity,
or admitting non-canonical observations.

## Architecture Impact

- Domain/Application/persistence impact: determine from root cause before implementation
- Adapter: not touched
- Data Contract Audit Gate: required

## Acceptance Criteria

- [ ] Record the exact current skip reason for each canonical window.
- [ ] Confirm observation identity, semantic cohort, cutoff, and label-policy provenance.
- [ ] Generate or explicitly reject each window under one documented canonical rule.
- [ ] Preserve fail-closed behavior for malformed or non-canonical observations.
- [ ] Add adversarial multi-window and identity tests.
- [ ] Run focused data-contract, architecture, and full suites plus `git diff --check`.

## Do Not Interpret This As

- Do not weaken canonical identity validation to make the count pass.
- Do not collapse multiple windows to latest-per-ticker.
- Do not rewrite historical observations or silently bridge retired contracts.
- Do not classify the fix `NON_SEMANTIC` without proving label behavior is unchanged.
