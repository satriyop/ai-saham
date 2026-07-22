# Fix Accumulation Audit Factory Test Contract

Status: `BACKLOG`

## Task Metadata

- Task type: Bugfix
- Priority: High
- Semantic classification: `NON_SEMANTIC`

## Problem Statement

Two accumulation-audit factory tests construct a stale `_FakeScreenerConfig`
without `foreign_flow_score_policy`. Production wiring now requires that typed
policy, so the full suite fails before testing the intended dependency graph.

## Desired Outcome

Update the strict test fixture to provide the current typed screener contract
and assert that the exact policy is passed into
`create_accumulation_screen_use_case`. Do not weaken or bypass production
factory wiring.

## Architecture Impact

- Domain/Application/Infrastructure/Adapter: not touched
- Tests: current config-contract fixture and assertions only
- Persistence/config semantics: unchanged

## Acceptance Criteria

- [ ] Both failing factory tests pass against the real current signature.
- [ ] The fake exposes a real typed `foreign_flow_score_policy`, not `None` or a loose mock.
- [ ] The exact policy identity is asserted at the screen-use-case factory boundary.
- [ ] Focused and full tests plus `git diff --check` pass, aside from independently recorded blockers.

## Do Not Interpret This As

- Do not remove `foreign_flow_score_policy` from production wiring.
- Do not use `getattr`, defaults, or a compatibility fallback.
- Do not alter scoring/config semantics.
