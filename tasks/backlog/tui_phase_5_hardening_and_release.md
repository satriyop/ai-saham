# TUI Phase 5 — Hardening And Release Decision

Status: `BACKLOG`

Roadmap: `docs/roadmap/roadmap_tui.md`

UX contract: `tasks/backlog/tui_ui_ux_design_spec.md`

Depends on: TUI Phases 0–4 and the completed UX contract/alignment task

## Task Metadata

- Task type: Refactor / Verification
- Priority: High before declaring TUI v1 supported
- Semantic classification: `NON_SEMANTIC`
- Chosen decision: harden the completed read-only journey and record an
  evidence-based release decision without adding scope. Implement this option only.

## Problem Statement

Component tests do not prove optional installation, small-terminal usability,
offline behavior, safe worker shutdown, or authority preservation across the
full journey. There is no objective release record.

## Desired Outcome

Verify:

```text
launch -> Daily -> Candidate Browser -> Ticker Research
                  -> Research Corpus Health
```

under supported terminal sizes, absent/present dependency, empty/stale/error
fixtures, repeated reload, cancellation, and exit-during-work. Update user docs
and CI, then record `RELEASE` or `DO_NOT_RELEASE` with evidence.

## Non-Goals

- No new screen, feature, provider, write, AI, scheduler, or redesign.
- Do not make Textual mandatory.
- Do not relax tests/guards.
- No product semantic change.
- No optimization without a measured failing budget.

## Release Gates

### Packaging

- Base install works without Textual.
- TUI extra resolves from lockfile.
- Missing-extra contract remains exact.
- Wheel/sdist includes TUI sources/assets.

### Layout and accessibility

- 80x24: all routes navigable; critical authority/warnings reachable.
- 120x40: reference layout.
- Large terminal: stable expansion/focus order.
- Keyboard-only: Help, Reload, Select, Back, Quit.
- Color is not sole carrier of authority, preview, or diagnostic meaning.

### Lifecycle and concurrency

- Repeated Reload cannot apply stale results.
- Route switch and exit during work are safe.
- Errors allow explicit retry.
- No automatic retry/refresh loop.

### Offline and read-only

- Full journey passes with network fakes that fail if called.
- Write fakes fail if called.
- Constructor/schema effects are documented exactly; byte-for-byte read-only is
  claimed only if tested.

### Authority

- Canonical/preview separation survives every layout.
- Missing evidence never becomes neutral/action fallback.
- Corpus health stays diagnostic/cohort-isolated.
- Presenters/controllers contain no canonical thresholds/action vocabulary.

## Exact File Boundary

Expected changes:

- existing TUI files only for defects demonstrated by a release gate;
- TUI/launcher/packaging/architecture/end-to-end tests;
- CI jobs for base and TUI-extra installs;
- `README.md` and/or `CLI_README.md`;
- this Release Decision Record.

No product-layer semantic change is authorized. Such a defect becomes a
separate blocker task.

## Architecture Impact

- Domain/Application/Infrastructure: not touched
- Adapter: release-gate defect fixes only
- Documentation/CI: install and test matrix
- New dependency/determinism/persistence impact: no
- Adapter-owned policy: no

Layer plan:

```md
Layer plan:
- Domain: not touched
- Application: not touched
- Infrastructure: not touched
- Adapter: proven hardening fixes only
```

## AI And Authority Declaration

No AI involved. No score, risk, TradeSetup, setup, market context, evidence,
observation, label, tuning, or promotion behavior changes.

## Test Matrix

- [ ] Base environment without Textual: CLI import/help/non-TUI smoke.
- [ ] TUI-extra environment: install/import/headless launch.
- [ ] Wheel/sdist content.
- [ ] 80x24 full navigation.
- [ ] 120x40 full navigation.
- [ ] Large-terminal full navigation.
- [ ] Keyboard-only focus/actions.
- [ ] READY/PARTIAL/NOT_READY Daily fixtures.
- [ ] Empty DB/corpus.
- [ ] Application error/recovery.
- [ ] Repeated Reload with out-of-order completions.
- [ ] Route change and exit during worker.
- [ ] Strict no-network journey.
- [ ] Strict no-write journey.
- [ ] Canonical/preview negative authority.
- [ ] Multi-cohort isolation.
- [ ] Architecture guards.
- [ ] Full repository suite.
- [ ] `git diff --check`.

## Acceptance Criteria

- [ ] Every release gate passes.
- [ ] CI covers base and TUI-extra contracts.
- [ ] Docs state install, controls, offline/no-intentional-write scope,
  constructor caveat, and exclusions.
- [ ] No new capability was added.
- [ ] No failing test was weakened/deleted/allowlisted.
- [ ] Any performance budget is measured/recorded.
- [ ] Release Decision Record has evidence and no unchecked blocker.
- [ ] Status becomes `DONE_RELEASED` or `DONE_NOT_RELEASED`.

## Required Negative Tests

- Missing Textual cannot break base CLI.
- Critical warnings remain reachable at 80x24.
- Text assertions retain meaning without color.
- Late result after route change/exit cannot mutate UI.
- Provider/write fakes are never called.
- Preview cannot occupy canonical region.
- Multi-cohort report cannot show pooled metrics.
- Architecture guard rejects forbidden import.

## Do Not Interpret This As

- Do not add polish features while testing.
- Do not make Textual mandatory.
- Do not hide critical content for small terminals.
- Do not solve product-layer defects in adapter.
- Do not release with authority/offline/packaging/concurrency failure.
- Do not decide from manual inspection alone.

## Data, Persistence, And Documentation

- Test data uses controlled fixtures or disposable temporary databases.
- Do not mutate user databases or journals during verification.
- No schema/config behavior change is authorized.
- README/CLI documentation is required and must match tested packaging,
  controls, limitations, and read-only caveat.

## Agent Execution Protocol

Before editing, confirm all prerequisites, restate release gates and exact files,
and identify disposable test storage. Defect fixes must cite the failing gate;
scope additions are forbidden. Do not choose RELEASE until automated evidence
for every acceptance item is recorded.

## Release Decision Record

- Decision: `UNDECIDED`
- Date:
- Source revision:
- Supported Python versions:
- Textual range:
- Terminal sizes:
- Base-install CI job:
- TUI-extra CI job:
- Full-suite result:
- Known limitations:
- Constructor/storage effects:
- Blocking failures:
- Evidence:

Rules:

- Set `RELEASE` only when every acceptance criterion passes.
- Set `DO_NOT_RELEASE` if any authority, offline, packaging, concurrency, or
  navigation gate remains.
- `DO_NOT_RELEASE` completes verification but must list scoped follow-up tasks.

## Completion Record

- Completed date:
- Implementation commit:
- Files changed:
- Focused/end-to-end tests:
- Architecture tests:
- Full suite:
- `git diff --check`:
- Final status:
- Follow-up tasks:
