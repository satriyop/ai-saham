# Implement ADR-067: Retire `setup_quality`, One Evidence Basis, Plan Does Not Judge

Status: `READY` — task 01 (ADR-068) completed 2026-08-05; see
`tasks/done/01_implement_adr_068_behavioral_engine_identity.md`.

> **Why 068 goes first (2026-08-04):** ADR-068 deletes
> `SEMANTIC_ENGINE_VERSION` and `EVIDENCE_CONTRACT_VERSION`, which this task's
> original slice 5 was going to bump — wasted work. It also builds the probe set
> that replaces this task's original slice 1 golden fixture.
>
> With 068 first, this task needs **no hand-bump at all**: deleting the
> `setup_quality` config block changes the ADR-059 snapshot payload, which forks
> the cohort automatically. And because the change is NON_SEMANTIC on screen, the
> probe digest should stay **identical** — which turns ADR-067 §8's central claim
> from an assertion into a measurement.

Replaces a deleted draft (`fix_accum_setup_quality_evidence_gap.md`) that was
written on the false premise that `setup=None` on the discovery path is a wiring
defect. It is not — it is intentional design (ADR-054; `--setup` is DIAGNOSTIC,
`screen_accum_commands.py:170-178`), so attaching the group would have been an
ADR-057 evidence promotion. That reasoning is preserved in ADR-067 §Context.
Sequence: **2 of 8** — see `tasks/backlog/00_SEQUENCE_accum_baseline_and_learning_loop.md`

## 1. Task Metadata

**Task Title**
Retire the `setup_quality` production evidence group and the two-name blending
code; stop `plan swing` from judging.

**Task Type**
Refactor + Bugfix (CONFIG_MATERIAL; forks cohort identity; live screen scoring
claimed NON_SEMANTIC and must be proven)

**Priority**
High — first task in the config-edit batch that must land before the corpus
accumulation window opens.

---

## 2. Problem Statement

See [ADR-067](../../docs/adr/ADR-067-retire-setup-quality-and-fix-judgment-authority-by-surface.md)
§Context for the full measured case. Summary:

- `setup_quality` (weight 0.60) is present in **0 of 7,764** accum
  window-observations. Its only live attachment is
  `plan_swing_decision_composer.py:352` — the surface ADR-054 says must not
  judge.
- No plan/swing observation purpose exists, so the group has never entered the
  corpus and is **untunable by construction**.
- The declared `0.60/0.40` split changes no value the screen produces. It is
  decorative config that actively misleads readers.
- The "evidence group" machinery is not general — it is hardcoded to two names
  (`signal_evidence_group_scorer.py:179`, `:264`).

---

## 3. Desired Outcome

- `flow_confirmation` is the sole production evidence group on the accum path.
  The signal score **is** the flow group score.
- No weight declaration, renormalization, absent-group handling, or hardcoded
  `setup_quality` reference survives in scoring code or config.
- `plan swing` carries forward screen's verdict and computes no verdict of its
  own.
- Screen-path scoring output is **byte-identical** before and after, proven by
  the ADR-068 core probe digest staying unchanged.
- No operator string reports quality-derived setup readiness on the screen path.

---

## 4. Non-Goals

- **No threshold changes.** `strong_min_score`, `moderate_min_score`, and every
  RiskEngine threshold stay exactly as they are. Recalibration is deferred by
  ADR-067 §Consequences and must be routed through a validated proposal path.
- No corpus purge, re-capture, backfill, or relabel.
- No promotion of `sector_context` / `company_quality_context` into the vacated
  slot.
- No retirement of setup **phase**, **family**, or phase-derived **readiness**.
- No removal of `--setup` as a diagnostic lens.
- No compatibility path, alias, or dual-profile mode for the retired group.
- No changes to pre-open paths or `ml-saham`.
- No identity-mechanism changes — that is ADR-068 and its task, which lands
  first.
- No hand-bumping of engine version constants; they no longer exist.

---

## 5. Architecture Impact Assessment

- **Domain:** `ACCUMULATION_OBSERVATION_PAYLOAD_SCHEMA_VERSION`
  (`signal_artifact_schema.py`) only if the payload shape changes.
  `signal_semantic_contract.py`'s engine version constants are already gone
  (ADR-068). `SetupEvidence` VO **survives** for the diagnostic `--setup`
  lens — do not delete it.
- **Application:** `signal_evidence_group_scorer.py` (delete the two-name
  blend), `plan_swing_decision_composer.py` (stop judging),
  `accumulation_policy_snapshot_payloads.py` (snapshot payload),
  `signal_engine_config.py` (group config).
- **Infrastructure:** none.
- **Adapter:** `decision_display.py` and plan display modules — remove the
  quality-derived readiness string; render the carried-forward verdict.

New dependency: **No.**
Determinism: **No** — deterministic before and after.
Persistence: **No schema migration.** Payload schema version bumps only if the
payload shape actually changes; existing rows are historical and untouched.
Warm-up: **No.**
Policy in adapter: **No.**

```md
Layer plan:
- Domain: bump ACCUMULATION_OBSERVATION_PAYLOAD_SCHEMA_VERSION only if the
  payload shape changes; keep SetupEvidence VO
- Application: delete two-name blending + absent-group renormalization; remove
  plan-side CanonicalSignalEvidenceInput construction; update snapshot payload
- Infrastructure: not touched
- Adapter: remove quality-derived readiness copy; plan displays carried verdict
```

---

## 6. AI Usage Declaration

**No AI involved.**

---

## 7. Risk, Signal, And Evidence Authority Considerations

Affected: **SignalEngine** (group set), **TradeSetup** on the plan path only.
RiskEngine unchanged.

**Does this change what can produce ENTER/WATCH/AVOID?**
- Screen: **No** — claimed NON_SEMANTIC, proven by the ADR-068 core probe
  digest staying unchanged across this task.
- Plan: **Yes** — plan stops producing its own action. This is the intended
  ADR-067 §3 change and must be stated in the commit message.

**Evidence authority:** this is a **retirement**, the reverse of promotion. It
must not be used as precedent for attaching any currently-DIAGNOSTIC group.

---

## 8. Data & Persistence

- **Read:** unchanged. **Written:** unchanged shape apart from the payload
  losing `setup_quality` entries in `group_contributions`.
- **Schema change:** payload version bumps only if the shape changes
  (`group_contributions` loses its `setup_quality` entry, so it likely does —
  verify). No SQL migration.
- **Semantic equivalence:** screen path — **yes, and it must be proven**. Plan
  path — **no**, deliberately.

### Operational constraint (do not skip)

`install_cron.sh` runs accum capture at 19:15 WIB, Mon–Fri. Slices 3 and 5 each
move cohort identity (via the ADR-068 snapshot-payload axis). **Disable the accum
capture cron before slice 3 and re-enable only after slice 5 is merged**, or the corpus will accumulate rows
under half-finished intermediate identities. Record disable/enable times in the
Completion Record.

---

## 9. Acceptance Criteria

- [ ] ADR-068 core probe digest is **unchanged** across this task, proving the
      screen NON_SEMANTIC claim by measurement.
- [ ] `grep -rn "setup_quality" src/` returns no hit in scoring or config
      resolution paths (diagnostic-lens and test-fixture hits are expected;
      enumerate them).
- [ ] `config/signal_engine.yaml` has no `setup_quality` weight, no
      `evidence_registrations` entry for it, no `weak_setup_threshold`, no
      `weak_setup_discount`.
- [ ] `plan_swing_decision_composer.py:352` construction removed; plan renders a
      carried-forward verdict.
- [ ] No operator string reports quality-derived setup readiness on screen.
- [ ] Phase-derived readiness and DecisionPolicy phase caps behave identically
      (test).
- [ ] `--setup` diagnostic lens still works, still `MATCH ≠ ENTER`.
- [ ] Cohort forked via the ADR-068 snapshot-payload axis, with no hand-bump.
- [ ] Payload schema version bumped **only** if the shape changed.
- [ ] `production_policy_snapshot.v2` still exactly seven rows;
      `signal.accum.evidence_group_weights` retained with a single-group payload.
- [ ] No non-goals violated — in particular no threshold moved.
- [ ] **Lint Gate:** `ruff check src/ tests/` and `ruff format --check src/ tests/`.

---

## 10. Slices (each slice = one commit)

**Slice 1 — REMOVED.** The golden fixture is now the ADR-068 core probe set,
built by `01_implement_adr_068_behavioral_engine_identity.md` slice 1. Use it as
this task's gate; do not build a second fixture.

**Slice 2 — Plan stops judging.**
Remove `plan_swing_decision_composer.py:352`; plan carries forward screen's
verdict. This is the only intentional behavior change; record plan output before
and after. Screen golden must stay green.
Commit: `refactor(plan)!: plan swing carries screen verdict instead of judging`

**Slice 3 — Delete the group and the blending code.**

Exact removal set, verified against the working tree 2026-08-04:

| Location | What |
|---|---|
| `config/signal_engine.yaml:95-98` | `setup_quality` evidence-group block — `weight`, `authority_registration: setup_quality`, **`required_for_authority: true`** |
| `config/signal_engine.yaml:141-142` | `alpha_trigger.evidence_registrations` entry |
| `config/signal_engine.yaml:182` | `decision_policy.weak_setup_threshold: 60.0` |
| `config/signal_engine.yaml:183` | `decision_policy.weak_setup_discount: 0.50` |
| `signal_evidence_group_scorer.py:179` | `total_weight = g.setup_quality.weight + g.flow_confirmation.weight` |
| `signal_evidence_group_scorer.py:181-193` | absent-group renormalization that only exists to serve two groups |
| `signal_evidence_group_scorer.py:~264` | hardcoded `name="setup_quality"` authority-fact entry |

**`required_for_authority: true` is the subtle one.** `flow_confirmation`
(`:99-102`) carries the same flag, so removing a required-for-authority group
changes what `_compute_signal_authority_coverage` treats as its required set.
On the screen path this should be inert — `ATTACHED_REQUIRED` scopes the
denominator to groups that are present (`signal_evidence_group_scorer.py:324`) —
but **confirm it via the golden gate, do not assume it.**

Screen golden must stay green. If it moves, **stop** and revisit ADR-067 §5
before proceeding; the no-purge decision depends on this staying green.
*Cohort identity forks here. Cron must already be disabled.*
Commit: `refactor(signal)!: retire setup_quality evidence group and two-name blend`

**Slice 4 — Readiness resolution and operator copy.**
Apply ADR-067 §4 Amendment 2026-08-04:
- Decide and record whether `SetupPhaseReadinessEvaluator` still receives
  `SetupEvidence`. Recommended answer **no** — otherwise setup evidence keeps a
  route to Action via readiness → DecisionPolicy caps, which is production
  authority through a side door and contradicts §1.
- Preserve evaluator rules 1–3 (family / DISTRIBUTION / FAILED / EXHAUSTION)
  bit-identically; they are evidence-free and feed the phase caps.
- Remove the `setup readiness UNAVAILABLE (missing: setup_evidence)` string from
  `decision_display.py` and plan display.
- Add the test that fails on code identifiers in operator strings.

Baseline to preserve (measured 2026-08-04, 7,764 window-observations): `None`
7,379 · INELIGIBLE 201 · UNAVAILABLE 184 · INCOMPLETE 0 · READY 0.
Commit: `fix(signal): resolve setup readiness inputs and operator copy for ADR-067`

**Slice 5 — Snapshot payload update.**
Update `accumulation_policy_snapshot_payloads.py` so
`signal.accum.evidence_group_weights` declares the single production evidence
basis. Verify the seven-row closed set still holds.

**No engine version bump** — `SEMANTIC_ENGINE_VERSION` and
`EVIDENCE_CONTRACT_VERSION` no longer exist after ADR-068. The cohort forks
automatically because the snapshot payload digest is identity-material under
ADR-068 §1. Confirm the fork happened; do not force it by hand.

Payload schema version bumps only if the payload shape actually changes (the
`group_contributions` array loses its `setup_quality` entry, so it likely does —
verify rather than assume).
Commit: `chore(identity): update accum snapshot payload for ADR-067 retirement`

**Slice 6 — Docs and closeout.**
`docs/evidence_diagnostic_factor_accum.md` §5.2, ADR-067 `Proposed` →
`Accepted`, index row updated, Completion Record filled, cron re-enabled.
Commit: `docs(adr): accept ADR-067 and align evidence inventory`

---

## 11. Testing Expectations

Positive:
- Golden equivalence across slices 2–5 (screen path).
- Signal score equals flow group score exactly — no renormalization remains.
- Plan output carries screen's verdict verbatim; no independent recomputation.
- Phase-derived readiness and DecisionPolicy phase caps unchanged.
- `--setup` diagnostic lens unchanged, `MATCH ≠ ENTER` preserved.

Negative (these prove the defect cannot return):
- A test that fails if any scoring-path module references `setup_quality`.
- A test that fails if `plan swing` constructs a `CanonicalSignalEvidenceInput`.
- A test that fails if config declares a weight for a group with no production
  registration — the general form of the decorative-config defect.
- A test that fails if any operator-facing string contains a code identifier.

Offline. `pytest -m "not tui"` for the inner loop; run the `tui` marker before
close (plan/judge desks are affected). Ruff before close.

---

## 12. Documentation Impact

- README: **No.**
- `docs/evidence_diagnostic_factor_accum.md` §5.2: **Yes.**
- New config options: **No** — options are removed, not added.
- Limitations: **Yes** — record that this does not change the ENTER rate and
  that `strong_min_score` remains uncalibrated and deferred.

---

## 13. Required Reading

- `AGENT_QUICKSTART.md`, `CLAUDE.md`, `TASK_TEMPLATE.md`, `DEFINITION_OF_DONE.md`
- **ADR-067** (this task implements it), ADR-054, ADR-057, ADR-058, ADR-059
- ADR-062 — the retirement precedent; mirror its golden-gate and identity-lock
  discipline
- `config/signal_engine.yaml`

---

## 14. Do Not Interpret This As

- permission to change any threshold to "fix" the 0.3% ENTER rate;
- permission to delete the `SetupEvidence` value object or the `--setup` lens;
- permission to keep a shim, alias, or dual-profile path for the retired group;
- permission to promote a DIAGNOSTIC group into the vacated slot;
- permission to run capture between slices 3 and 5;
- a claim that schema-12 and schema-13 observations share a cohort.

---

## 15. Completion Record

- Completed date:
- Slice commits:
- Golden result (screen NON_SEMANTIC confirmed?):
- Plan output before → after:
- New `compatibility_id`:
- Cron disabled / re-enabled at:
- Remaining `setup_quality` references (enumerated, with justification):
- Test / Lint result:
