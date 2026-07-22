# TUI Phase 5 — Hardening And Release Decision

Status: `SUPERSEDED` — verification evidence retained; this is not an active
roadmap milestone

Product reset: `docs/roadmap/roadmap_tui.md`

Historical record only. Do not execute, reopen, or use this task as a gate for
the value-first TUI roadmap. Its completed verification evidence may still be
consulted by milestone-specific tests.

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

- [ ] Base environment without Textual: job and simulated contract added; first hosted CI run pending.
- [x] TUI-extra environment: install/import/headless launch.
- [x] Wheel/sdist content.
- [x] 80x24 full navigation.
- [x] 120x40 full navigation.
- [x] Large-terminal full navigation at 160x50.
- [x] Keyboard-only focus/actions.
- [x] READY/PARTIAL/NOT_READY Daily fixtures.
- [x] Empty DB/corpus.
- [x] Application error/recovery.
- [x] Repeated Reload with out-of-order completions.
- [x] Route change and exit during worker.
- [x] Strict no-network journey.
- [x] Strict no-write journey.
- [x] Canonical/preview negative authority.
- [x] Multi-cohort isolation.
- [x] Architecture guards.
- [x] Full repository suite executed; three blockers remain.
- [x] `git diff --check`.

## Acceptance Criteria

- [ ] Every release gate passes; full-suite and lint blockers remain.
- [x] CI covers base and TUI-extra contracts on Python 3.11 and 3.14.
- [x] Docs state install, controls, offline/no-intentional-write scope,
  constructor caveat, and exclusions.
- [x] No new capability was added.
- [x] No failing test was weakened/deleted/allowlisted.
- [x] No optimization was attempted; no measured failing performance budget exists.
- [x] Release Decision Record has evidence and every blocker has a scoped follow-up.
- [x] Status becomes `DONE_RELEASED` or `DONE_NOT_RELEASED`.

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

- Decision: `DO_NOT_RELEASE`
- Date: 2026-07-22
- Source revision: this Phase 5 completion commit, based on `01f5ae1`
- Supported Python versions: package metadata `>=3.11`; new install-contract matrix covers 3.11 and 3.14, pending its first hosted CI run
- Textual range: `>=8.2,<9`; locked resolution remains optional under the `tui` extra
- Terminal sizes: 80x24 minimum, 120x40 reference, 160x50 representative large terminal
- Base-install CI job: `Base install · Python 3.11/3.14`; verifies Textual absence, base CLI help/import, and exact missing-extra behavior; configured but not yet run remotely
- TUI-extra CI job: `TUI extra · Python 3.11/3.14`; locked install, focused/headless tests, and artifact inspection; local equivalent gates pass
- Full-suite result: `5754 passed, 3 failed` in 125.18s
- Known limitations: CLI remains the primary automation surface; Research form inputs temporarily own printable numeric/`r` keys while focused; readiness is diagnostic only
- Constructor/storage effects: no intentional business write; composed SQLite observation/label repository constructors may initialize or migrate schema tables, indexes, columns, and migration rows
- Blocking failures: two stale accumulation-audit factory fixtures omit `foreign_flow_score_policy`; multi-window forward-label generation returns zero instead of three; repository Ruff baseline has 727 violations; first hosted base/TUI matrix run remains pending
- Evidence: 72 focused TUI/launcher/packaging/architecture tests passed; 37 architecture tests passed; `uv lock --check` resolved 72 packages; disposable wheel/sdist build and content/metadata inspection passed; route-switch regression proves a cancelled late Daily result cannot update hidden UI

Rules:

- Set `RELEASE` only when every acceptance criterion passes.
- Set `DO_NOT_RELEASE` if any authority, offline, packaging, concurrency, or
  navigation gate remains.
- `DO_NOT_RELEASE` completes verification but must list scoped follow-up tasks.

## Completion Record

- Completed date: 2026-07-22
- Implementation commit: this Phase 5 completion commit
- Files changed: TUI state/controllers/screens/app lifecycle, shared worker dispatcher, release-gate and packaging tests, lockfile, CI matrix, README/CLI guide, release record, and blocker tasks
- Focused/end-to-end tests: `72 passed`
- Architecture tests: `37 passed`
- Full suite: `5754 passed, 3 failed`; failures are the three independently scoped blockers above
- `git diff --check`: passed
- Final status: `DONE_NOT_RELEASED`
- Follow-up tasks: `fix_accumulation_audit_factory_test_contract.md`, `fix_multi_window_forward_label_generation.md`, and `restore_repository_ruff_baseline.md`
