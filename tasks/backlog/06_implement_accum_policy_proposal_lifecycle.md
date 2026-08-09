# Give ml-saham Verdicts A Place To Land: Accum Policy Proposal Lifecycle

Status: `BLOCKED` — the corpus-growth producer recovered to
`CHALLENGE_INPUT_READY` on 2026-08-09; this task now requires at least two valid
post-embargo ml-saham OOS folds from the exact frozen cohort. Task 4's rebuild
alone is insufficient. Before those folds may unblock this task, close
`vet_ml_accum_oos_protocol_before_policy_lifecycle.md`: the current v1 splitter
still has a row-based thin-calendar fallback, row-count rather than
session-count sufficiency gates, and no policy-grade confirmation holdout.
Sequence: **6 of 8** — see `tasks/backlog/00_SEQUENCE_accum_baseline_and_learning_loop.md`

## 1. Task Metadata

**Task Title**
Extend the existing swing policy proposal→validate→apply lifecycle to accum
scoring config, so a challenge verdict can become a reviewed config change.

**Task Type**
Feature

**Priority**
Medium-High — the payoff task; worthless before task 4, high-value after.

---

## 2. Problem Statement

There is no path — automated or semi-automated — from an `ml-saham` verdict to
an `ai-saham` config change.

- `ml-saham challenge promote-packet` emits `PROMOTE.md`, a human checklist.
  `grep -rln "promote-packet\|promote_packet\|PROMOTE.md\|ml_saham" src/ scripts/`
  in ai-saham returns **only documentation** — zero code paths, zero commands.
- `artifacts/challenge/promote/` does not exist on disk. It has never been run.
- The only promotion decision ever recorded is a memo:
  `~/dev/ml-saham/docs/decisions/accum_score_weights_2026-07-29.md`, verdict
  "KEEP production… Promotion to ai-saham: **NO**."
- Today the operator would hand-edit `config/accumulation_screener.yaml` with no
  record, no validation, and no drift check.

Meanwhile a **complete, rigorous lifecycle already exists for swing** and has
never been used:

- `swing_policy_learning_use_case.py:409-427` — `_validation_issues` requires no
  regression across OOS net return, profit factor, average return, drawdown,
  trade count, regime stability, authority coverage, and setup readiness.
- `ApplySwingPolicyUseCase.execute` (line 454) — requires `--yes`, validation
  `PASS`, proposal unused, config hash match (no drift), target YAML git-clean
  (`swing_policy_config_gateway.py:33`), and post-write reread verification.
- Tables `learning_policy_proposals` / `_validations` / `_applications` exist.
- All three hold **0 rows**. It is not in any cron entry in `install_cron.sh`.

Only one knob is wired: `swing_backtest.execution.take_profit_pct`.

**The machinery is the best-engineered code in the repo and is inert.** This
task points it at accum.

---

## 3. Desired Outcome

- `saham policy accum propose | review | validate | apply | status` exists,
  mirroring the swing lifecycle's guarantees exactly.
- A proposal can be sourced from an `ml-saham` challenge export in a schema both
  repos agree on.
- Applying a proposal writes to `learning_policy_applications`, so there is a
  permanent, queryable record of every production config change and its evidence.
- A config change made **outside** this path is detectable (config-hash drift).
- `BOUNDARY.md`'s hard rule is preserved: **no auto-promotion, ever.** Apply
  always requires explicit human confirmation.

---

## 4. Non-Goals

- **No auto-promotion.** `BOUNDARY.md:78` — "Auto-promote config into
  production | human policy path only | never." This task does not soften it.
- No Python imports across repos. The seam is a file/DB contract only.
- No ai-saham code that scrapes or executes `ml-saham`.
- No changes to `ml-saham` in this task (a follow-up may align its export schema).
- No new tuning algorithms — this is a lifecycle, not a learner.
- No re-weighting decisions. This task ships the mechanism; the first real
  proposal is separate work.

---

## 5. Architecture Impact Assessment

- **Domain:** proposal/validation value objects if not already generic.
- **Application:** primary — an accum analogue of
  `swing_policy_learning_use_case.py`, with an accum-appropriate validator
  (rank IC and action-distribution regression rather than backtest P&L).
- **Infrastructure:** config gateway for accum YAML targets (reuse the swing
  gateway's git-clean and reread-verify behavior); reader for the ml-saham
  export artifact.
- **Adapter:** `saham policy accum …` CLI. Thin — parse, wire, call, format.

New dependency: **No.**
Determinism: **No** effect on scoring.
Persistence: **Yes** — writes to the three existing lifecycle tables. Schema
change only if accum needs fields swing does not; prefer reuse.
Warm-up: **No.**
Policy in adapter: **No** — the entire lifecycle is an application use case.

```md
Layer plan:
- Domain: reuse/generalise proposal + validation VOs; no new business rules
- Application: AccumPolicyLearningUseCase (propose/validate/apply) with an
  accum-specific validator; ml-saham export ingestion as a typed port
- Infrastructure: accum config gateway (git-clean, drift check, reread-verify);
  filesystem reader for the challenge export
- Adapter: saham policy accum CLI subcommands; no policy
```

---

## 6. AI Usage Declaration

**No AI involved.** The proposal source is a deterministic challenge export.

---

## 7. Risk, Signal, And Evidence Authority Considerations

Affected: potentially **SignalEngine**, **RiskEngine**, and screener weights —
whatever a proposal targets. That is exactly why the validator matters.

**Does this change what can produce ENTER/WATCH/AVOID?** Not by itself. It
creates a *gated* path by which such a change can be made, recorded, and
reverted.

**Patch-eligibility must be explicit.** Enumerate which config keys are
proposal-eligible and which are locked. Recommended locked at minimum:
evidence-authority registrations (ADR-057 lifecycle owns those), risk hard-gate
thresholds, and anything the `AGENT_QUICKSTART.md` non-negotiables cover. A
proposal targeting a locked key must fail closed.

**Does this promote diagnostic evidence?** No, and it must not become a
backdoor for doing so. Evidence promotion stays on the ADR-057 path.

---

## 8. Data & Persistence

- **Read:** `learning_observations`, `learning_outcome_labels`,
  `learning_policy_snapshots`, ml-saham export artifact, target YAML.
- **Written:** `learning_policy_proposals`, `_validations`, `_applications`;
  target YAML on apply.
- **Schema change:** No, if the swing tables generalise. Verify first.
- **Semantic equivalence:** the ml-saham export schema (v3, with
  `population_identity_kind/id/detail` bound to an exact
  `observation_compatibility_id`) must be validated on ingestion. A proposal
  whose cohort does not match the live cohort **fails closed**.

---

## 9. Acceptance Criteria

- [ ] `saham policy accum propose|review|validate|apply|status` implemented.
- [ ] Apply requires: explicit confirmation, validation PASS, unused proposal,
      config-hash match, git-clean target, and post-write reread verification —
      no weaker than swing.
- [ ] Proposal-eligible key allowlist enforced; locked keys fail closed.
- [ ] Cohort mismatch between export and live cohort fails closed.
- [ ] An end-to-end run produces ≥ 1 row in each of the three lifecycle tables —
      **the first time the loop has ever closed.**
- [ ] Rollback path exercised and documented.
- [ ] `BOUNDARY.md` no-auto-promotion rule provably intact.
- [ ] **Lint Gate** passes.

---

## 10. Slices (each slice = one commit)

**Slice 1 — Generalise the lifecycle.**
Extract the swing proposal/validate/apply core into a reusable application
service. Swing behavior byte-identical; assert against current expectations.
Commit: `refactor(policy): extract reusable policy lifecycle from swing`

**Slice 2 — Accum validator.**
Accum-appropriate regression checks (rank IC, action distribution, coverage) as
a pure service with unit tests. No CLI yet.
Commit: `feat(policy): add accum policy validation service`

**Slice 3 — Eligibility allowlist.**
Enumerate proposal-eligible vs locked config keys; fail closed on locked.
Commit: `feat(policy): enforce accum config patch-eligibility allowlist`

**Slice 4 — ml-saham export ingestion.**
Typed port + schema validation + cohort binding check. Fails closed on mismatch.
Commit: `feat(policy): ingest ml-saham challenge export as accum proposal`

**Slice 5 — CLI + apply path.**
`saham policy accum …` with the full swing-equivalent apply gate.
Commit: `feat(cli): add saham policy accum lifecycle commands`

**Slice 6 — Close the loop once.**
Run it end to end against the task-4 cohort. Record the first non-zero rows.
Commit: `docs(policy): record first closed accum learning loop`

---

## 11. Testing Expectations

- Every apply precondition, each failing independently (6 negative tests).
- Locked-key proposal rejected.
- Cohort-mismatch export rejected.
- Validator rejects a regression on each checked metric independently.
- Applied YAML matches the proposal exactly on reread.
- Swing lifecycle output unchanged after slice 1.
- Regression guard: a test that fails if any apply path can run without explicit
  confirmation.

Offline. `pytest -m "not tui"`. Ruff before close.

---

## 12. Documentation Impact

- README: **Yes** — the promotion path is a headline capability.
- New config options: **Yes** — eligibility allowlist.
- Limitations: **Yes** — state that apply is always human-confirmed.
- `BOUNDARY.md`: **Yes** — document the new seam on both sides.

---

## 13. Required Reading

- `AGENT_QUICKSTART.md`, `TASK_TEMPLATE.md`, `BOUNDARY.md`
- `src/application/use_case/swing_policy_learning_use_case.py` — the model to follow
- `src/infrastructure/.../swing_policy_config_gateway.py`
- `docs/adr/ADR-057-*` (evidence lifecycle — not this path), `ADR-059-*`
- `~/dev/ml-saham/docs/challenge_health.md` §promote-packet
- `~/dev/ml-saham/docs/decisions/accum_score_weights_2026-07-29.md`

---

## 14. Do Not Interpret This As

- **Not** permission to auto-apply. Human confirmation is non-negotiable.
- **Not** a route to promote diagnostic evidence to production authority.
- **Not** permission to weaken any swing-equivalent apply precondition for accum.
- **Not** worth starting before task 4 — with no evaluable cohort there is
  nothing to propose.

---

## 15. Completion Record

- Completed date:
- Slice commits:
- Eligible vs locked keys:
- First proposal / validation / application row ids:
- Rollback exercised:
- Test / Lint result:
