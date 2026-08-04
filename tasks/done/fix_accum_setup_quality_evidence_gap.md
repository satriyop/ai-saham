# Attach `setup_quality` Evidence On The Accum Discovery Path

Status: `SUPERSEDED` by
[ADR-067](../../docs/adr/ADR-067-retire-setup-quality-and-fix-judgment-authority-by-surface.md)
— **do not implement this task.**

> **Why superseded (2026-08-04):** this task was drafted on the premise that
> `setup=None` on the discovery path is a wiring defect and that attaching
> `setup_quality` is "a wiring fix, not an evidence promotion." Both claims are
> false. `--setup` is documented DIAGNOSTIC (`MATCH ≠ ENTER`,
> `screen_accum_commands.py:170-178`), ADR-054 makes the board the cheap
> discovery surface, and `docs/evidence_diagnostic_factor_accum.md:124` records
> non-attachment as design. Attaching the group would have been an ADR-057
> evidence promotion — the exact act this file's own §14 forbids.
>
> The real defect is that `setup_quality` has 0/7,764 corpus presence and no
> capture purpose, so it is untunable by construction. ADR-067 retires it
> instead. A replacement implementation task will be written against that ADR.
>
> Retained as a record of the reasoning, not as work.

Sequence: ~~1 of 8~~ — see `tasks/backlog/SEQUENCE_accum_baseline_and_learning_loop.md`

## 1. Task Metadata

**Task Title**
Attach `setup_quality` evidence on the accumulation discovery screen so signal
scoring uses its designed evidence base.

**Task Type**
Bugfix (scoring-material — forks cohort identity)

**Priority**
High — highest-value item in the 2026-08-04 vet.

---

## 2. Problem Statement

`screen accum` computes its signal score from **one of four** evidence groups.

`src/application/services/accumulation_candidate_signal_assessor.py:244`
hardcodes `setup=None` when building `CanonicalSignalEvidenceInput`. The
`setup_quality` group is therefore never attached on the discovery path.

`SignalEvidenceGroupScorer._blend` (`signal_evidence_group_scorer.py:178-193`)
renormalizes over present groups only — correct in isolation. But
`config/signal_engine.yaml` weights `setup_quality: 0.60` /
`flow_confirmation: 0.40`, and `classification.strong_min_score: 70` (→ ENTER)
was calibrated against the blended score. The board only ever produces the 0.40
sleeve, renormalized to 100%.

### Measured evidence (2026-08-04, `data/db/data.db`)

Across all **7,764** accum window-observations in `learning_observations`:

| Evidence group | present | configured weight |
|---|---|---|
| `setup_quality` | **0 / 7,764** | 0.60 |
| `institutional_flow` | 7,764 / 7,764 | 0.40 |
| `sector_context` | 0 / 7,764 | diagnostic |
| `company_quality_context` | 0 / 7,764 | diagnostic |

Resulting action distribution:

| Action | n | % |
|---|---|---|
| AVOID | 2,541 | 32.7% |
| BLOCKED_STRUCTURAL | 1,854 | 23.9% |
| WATCH | 1,801 | 23.2% |
| BLOCKED_EXECUTION | 1,545 | 19.9% |
| **ENTER** | **23** | **0.3%** |

Signal score distribution is centred on 30–50; only **206 / 7,764 (2.7%)** ever
reach the ENTER threshold of 70.

### Why the coverage floor did not catch this

`accumulation_candidate_signal_assessor.py:259` passes
`AuthorityDenominatorScope.ATTACHED_REQUIRED`. That scopes the coverage
denominator to groups that are *present*
(`signal_evidence_group_scorer.py:324`), so `signal_authority_coverage` reads
**1.0** even with three of four groups absent. The regime floors in
`decision_policy.py:98` (`min_signal_authority_coverage` 0.70–1.00) are
therefore **inert on this path** — they cannot fail. Operator-facing copy
compounds it: every row renders `authority 100% · setup readiness UNAVAILABLE
(missing: setup_evidence)`.

**Who is affected:** every user of `screen accum` and the TUI accum board, plus
every consumer of the learning corpus — 2,588 observations were captured from
this degenerate policy.

---

## 3. Desired Outcome

- The accum discovery path attaches a real `setup_quality` group input, or
  states an explicit, typed, and *visible* reason why it is absent for a given
  candidate.
- `signal_authority_coverage` on the accum path becomes capable of being < 1.0
  and therefore capable of failing the configured regime floors.
- ENTER becomes reachable for candidates that genuinely satisfy both sleeves.
- Operator copy never claims `authority 100%` while production-registered
  groups are missing.

Explicitly **not** in scope: whether the resulting ENTER rate is "good". That is
a tuning question, answerable only after task 4 rebuilds the corpus.

---

## 4. Non-Goals (Explicitly Out Of Scope)

- No new data providers.
- No change to `config/accumulation_screener.yaml` sleeve weights (the accum
  score is a separate concern — see the deferred re-weighting note in
  `SEQUENCE_*.md`).
- No change to `strong_min_score` / `moderate_min_score` in this task. Land the
  evidence fix first, measure, then propose thresholds through task 6.
- No promotion of `sector_context` or `company_quality_context` from DIAGNOSTIC
  to PRODUCTION (ADR-057 lifecycle required; separate task).
- No corpus purge or re-capture here — that is task 4's single clean break.
- No UI restructure (tasks 7/8).

---

## 5. Architecture Impact Assessment

- **Domain:** likely untouched. `SetupEvidence`
  (`src/domain/value_objects/setup_evidence.py`) already exists; confirm it
  needs no new field.
- **Application:** primary. `accumulation_candidate_signal_assessor.py`
  (build + attach setup group input), possibly
  `screen_assessment_pipeline.py`, and the composition of whatever produces
  setup quality on the plan path (`evaluate_swing_setup_use_case`).
- **Infrastructure:** possibly a repository read if setup evidence needs
  indicator history not currently loaded on the screen path. Prefer reusing the
  existing aggregate rather than adding a provider call per ticker.
- **Adapter:** untouched except copy (deferred to task 7).

New dependency: **No.**
Affects determinism: **No** (same inputs → same output; the *output values*
change, which is the point).
Persistence changes: **No schema change.** Cohort identity forks — handled in
task 4.
Warm-up data: **Yes** if setup quality needs indicator history; state the
warm-up requirement explicitly and fail closed when unavailable.
Policy inside an adapter: **No.**

```md
Layer plan:
- Domain: not touched (verify SetupEvidence sufficiency first; if a new field
  is required, it is a pure value-object change)
- Application: attach setup group input in
  accumulation_candidate_signal_assessor; reuse the plan-path setup builder via
  a shared application service rather than duplicating logic
- Infrastructure: not touched unless setup evidence requires history the screen
  path does not already load; if so, extend an existing repository read, no new
  provider
- Adapter: not touched (composition root wiring only, if the builder is a new
  injected dependency)
```

---

## 6. AI Usage Declaration

**No AI involved.** Deterministic scoring path only.

---

## 7. Risk, Signal, And Evidence Authority Considerations

Affected components: **SignalEngine** (directly), **TradeSetup** (via signal
score), **DecisionPolicy** (coverage floor becomes live).
RiskEngine unchanged by this task — see task 2.

**Does this change what can produce ENTER/WATCH/AVOID? Yes — materially.**
This is the point of the task and must be stated in the commit message.

**Does this promote diagnostic evidence?** No. `setup_quality` is already
registered `PRODUCTION` in `config/signal_engine.yaml:141-149`
(`alpha_trigger.evidence_registrations`). This task makes an
already-production-registered group actually present. It is a **wiring fix, not
an evidence promotion**, and must not be used as precedent for attaching
`sector_context` / `company_quality_context`.

**Coverage floors become live.** Once `setup_quality` can be absent-and-counted,
`ATTACHED_REQUIRED` vs `ALL_REQUIRED` on the accum path must be a deliberate,
documented decision. Recommendation: switch the accum path to `ALL_REQUIRED` so
the floor means what operators think it means. If that is judged too strict for
discovery, keep `ATTACHED_REQUIRED` but **change the operator copy** so
`authority` is not reported as 100% while a production group is missing. Pick
one and record the reasoning in the task's completion record.

---

## 8. Data & Persistence

- **Read:** existing candle / indicator / broker aggregates already loaded on
  the screen path, plus whatever the setup-quality builder requires.
- **Written:** nothing new. Existing observation capture will record the new
  values.
- **Schema change:** No.
- **Old vs new source semantically equivalent?** N/A — no source is being
  swapped. A previously-absent input becomes present.

Cohort impact: `compute_accumulation_config_hash` is unchanged by this task, but
`SEMANTIC_ENGINE_VERSION` / evidence contract versioning must be bumped so the
new engine cannot be confused with the old one in the corpus. **All 2,588
existing accum observations become historical-engine artifacts** and are purged
in task 4. Do not attempt to reconcile old and new observations.

---

## 9. Acceptance Criteria

- [ ] `setup=None` is gone from `accumulation_candidate_signal_assessor.py`; the
      setup group is either attached or absent for a typed, asserted reason.
- [ ] A screen run over LQ45 produces `setup_quality present = true` for a
      non-trivial fraction of candidates; the exact fraction is recorded.
- [ ] `signal_authority_coverage` is observed < 1.0 for at least one candidate
      (proves the metric is no longer self-fulfilling).
- [ ] The `ATTACHED_REQUIRED` vs `ALL_REQUIRED` decision is made, documented,
      and covered by a test.
- [ ] No operator-facing string reports `authority 100%` while a
      production-registered group is absent.
- [ ] Behavior matches Desired Outcome; deterministic for same inputs.
- [ ] Works without AI enabled.
- [ ] No non-goals violated.
- [ ] ADR-041 (authority denominator), ADR-057 (evidence vocabulary) considered.
- [ ] Adapter thinness reviewed; all workflow in application.
- [ ] **Lint Gate:** `ruff check src/ tests/` and `ruff format --check src/ tests/`.

---

## 10. Slices (each slice = one commit)

**Slice 1 — Prove and pin the gap.**
Characterisation tests asserting current behavior: on the accum path,
`setup_present is False` and `signal_authority_coverage == 1.0`. These tests are
*inverted* in slice 3; they exist so the change is provably the cause.
Commit: `test(signal): pin accum setup_quality absence and inert coverage floor`

**Slice 2 — Extract a reusable setup-quality builder.**
Lift setup-quality evidence construction out of the plan/swing path into a
shared application service with no plan-specific assumptions. Plan path switched
to the extracted service; behavior identical (assert plan output unchanged).
No screen behavior change yet.
Commit: `refactor(signal): extract shared setup-quality evidence builder`

**Slice 3 — Attach on the discovery path.**
Replace `setup=None`. Handle missing prerequisites with a typed absent-reason,
never a fabricated neutral value. Invert slice 1's tests.
Commit: `fix(signal): attach setup_quality evidence on accum discovery path`

**Slice 4 — Resolve the coverage-denominator semantics.**
Apply the `ATTACHED_REQUIRED` / `ALL_REQUIRED` decision from section 7, with
tests proving the regime floor can now reject. Update
`src/adapters/shared/decision_display.py` so the Why line cannot claim full
authority under partial evidence.
Commit: `fix(signal): make accum authority coverage non-self-fulfilling`

**Slice 5 — Version bump + measurement record.**
Bump `SEMANTIC_ENGINE_VERSION`; update version-pinning tests. Run LQ45 and
record the new action distribution in the Completion Record for comparison
against the 0.3% ENTER baseline.
Commit: `chore(signal): bump semantic engine version for setup_quality attach`

---

## 11. Testing Expectations

Unit-tested (application):
- Setup group attaches when prerequisites are met; score blends 0.60/0.40.
- Setup group absent → typed reason recorded, **never** neutral-filled
  (regression guard on `_blend`'s "missing groups excluded from denominator"
  contract).
- Coverage < 1.0 is reachable and trips the configured regime floor.
- Plan-path output is byte-identical after slice 2's extraction — assert against
  currently-expected values, not re-derived ones.

Negative tests (prove the bug cannot return):
- A test that fails if any production-registered group is hardcoded to `None`
  in a signal assessor.
- A test that fails if `authority_coverage == 1.0` while a
  production-registered group has `present is False`.

All tests run offline. Use `pytest -m "not tui"` for the inner loop.
Confirm whole-repo Ruff before close.

---

## 12. Documentation Impact

- README.md update: **No.**
- New config options: **No.**
- Limitations to state: **Yes** — record in the Completion Record that all
  pre-fix accum observations reflect a flow-only engine and are not comparable
  to post-fix ones.

---

## 13. Required Reading

- `AGENT_QUICKSTART.md`, `CLAUDE.md`, `TASK_TEMPLATE.md`, `DEFINITION_OF_DONE.md`
- `docs/adr/ADR-041-*` (authority denominator scope)
- `docs/adr/ADR-057-*` (evidence vocabulary — evidence vs diagnostic vs corpus)
- `docs/evidence_diagnostic_factor_accum.md` §5.1
- `config/signal_engine.yaml` — confirm weights and registrations before editing

---

## 14. Do Not Interpret This As

- **Not** permission to attach `sector_context` or `company_quality_context`.
  Those are DIAGNOSTIC and require the ADR-057 promotion lifecycle.
- **Not** permission to lower `strong_min_score` to manufacture ENTERs. If the
  ENTER rate is still near zero after the fix, that is a finding to route
  through task 6, not a threshold to hand-edit.
- **Not** a corpus task. Do not purge, re-capture, or backfill here.

---

## 15. Completion Record

- Completed date:
- Slice commits:
- `ATTACHED_REQUIRED` vs `ALL_REQUIRED` decision + reasoning:
- Setup-group attach rate on LQ45:
- New action distribution (vs baseline ENTER 23/7,764 = 0.3%):
- Observed minimum `signal_authority_coverage`:
- Test result:
- Lint result:
