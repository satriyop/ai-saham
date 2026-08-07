# Stop Recording Unevaluable-Gate Blocks Under The Gate's Own Name

Status: `READY` — independent; ships anytime.
Sequence: **9 of 9** — see `tasks/backlog/00_SEQUENCE_accum_baseline_and_learning_loop.md`

## 1. Task Metadata

**Task Title**
Give a `RiskAssessment` blocked by `UnevaluableGatePolicy` its own recorded
identity, instead of borrowing the name of the gate that could not be
evaluated.

**Task Type**
Bugfix (persisted-observation-shape; surfaced while verifying commit
`619b6a4c`, which threaded `unevaluable_gate_policy` into ADR-068 cohort
identity — that fix closed the identity gap, this task closes the separate
corpus-observability gap it left behind)

**Priority**
Medium — not blocking task 04's purge+rebuild, but every session observed
before this lands carries the same confound, so it is cheapest to fix before
the corpus grows further.

---

## 2. Problem Statement

`config/risk_engine.yaml` sets `unevaluable_policy: surface` (the
`UnevaluableGatePolicy` default), which never blocks. But the moment an
operator or ADR-059-driven experiment flips it to `block`
(`src/domain/rules/risk_gate.py:99-140`,
`UnevaluableGateAction.BLOCK`), the following happens at
`src/application/use_case/assess_risk_gate_evaluator.py:218-241`:

```python
if unevaluable_rows and self._unevaluable_gate_policy.blocks:
    first = unevaluable_rows[0]
    assessment = RiskAssessment(
        rationale=(_unevaluable_block_rationale(unevaluable_rows),),
        ...
        gate_triggered=first.gate,          # <-- the unevaluable gate's own name
        gate_confidence=self._unevaluable_gate_policy.block_confidence,
        unevaluable_gates=unevaluable,
    )
```

`gate_triggered` is set to the **name of the gate that had no usable input**,
not a synthetic "blocked by aggregate policy" marker. That value is exactly
what flows into the persisted corpus:

- `src/application/use_case/assess_trade_setup_use_case.py:107-108`
  (`_blocking_gates`) reads `risk.assessment.gate_triggered` verbatim.
- `src/domain/value_objects/trade_setup.py:156-157` writes it into
  `blocking_gates` / `gate_triggered` on `TradeSetup.to_dict()`.
- `src/application/services/accumulation_policy_snapshot_payloads.py:373-378`
  declares `risk.accum.hard_gates`'s `observation_result_fields` as exactly
  `trade_setup.blocking_gates` and `candidate.risk_status`
  (`src/application/dto/accumulation_screen.py:354`,
  `risk_status = risk_assessment.risk_level_name` — `"BLOCKED"` whenever
  `gate_triggered` is set, full stop).

So a session where `FundamentalGate` had no fundamentals data and got blocked
by policy, and a session where `FundamentalGate` genuinely evaluated and
tripped its threshold, both persist as `blocking_gates: ["FundamentalGate"]`,
`risk_status: "BLOCKED"`. `RiskAssessment.unevaluable_gates`
(`src/domain/value_objects/risk_assessment.py:42`) carries the disambiguating
information at assessment time, but nothing declared in
`observation_result_fields` ever copies it into a persisted field — confirmed
by grep: `unevaluable_gates` never appears in
`src/application/services/accumulation_observation_fingerprint.py`, which
builds every payload that reaches storage.

**Consequence:** with `unevaluable_policy: block`, a `blocking_gates`-based
label (or an ML challenger trained against the corpus, per ADR-059) cannot
tell "the gate ran and fired" from "the gate never ran and the aggregate
policy decided to treat that as a block anyway." These are different claims
about the ticker — one asserts something about `FundamentalGate`'s own
threshold, the other asserts nothing about it at all
(`risk_assessment.py:31-33`) — but they are byte-identical in storage.

**Why this was not caught earlier:** `surface` (never blocks) has been the
shipped default the whole time this corpus has been accumulating, so the
confound has never actually fired in stored data. It is a real hole in the
persisted schema, not a hole in today's numbers.

---

## 3. Desired Outcome

- A session observation must be able to distinguish, after the fact:
  1. A gate ran and its own threshold triggered.
  2. No gate ran to a verdict, and `UnevaluableGatePolicy` chose to block.
- The disambiguation must not require re-deriving it from config (i.e. "well,
  `unevaluable_policy` was `block` at the time, so..." is not sufficient —
  the record itself must say which case happened, per this project's
  reproducibility rule: "No hidden state. No silent decisions.").
- `unevaluable_gates` (or an equivalent explicit marker) becomes a declared,
  observation-backed field for `risk.accum.unevaluable_policy`
  (`PRODUCTION_POLICY_ID_UNEVALUABLE_GATE_POLICY`,
  `production_policy_snapshot.v3`), replacing its current
  `"Declares no observation_result_fields"` note
  (`accumulation_policy_snapshot_payloads.py:508-511`) with a real one.

## 4. Non-Goals (Explicitly Out of Scope)

- No change to gate evaluation logic, gate ordering, or short-circuit
  behavior.
- No change to `UnevaluableGatePolicy` semantics (`SURFACE`/`BLOCK`,
  `block_confidence`) — this task is about what gets *recorded*, not what
  gets *decided*.
- No change to `config/risk_engine.yaml`'s shipped default (`surface`
  stays).
- No retroactive repair of historical observations — this is a
  going-forward schema fix, not a backfill.
- No new cohort-identity fork by itself. If the chosen fix changes
  `CANDIDATE_OBSERVATION_SCHEMA_VERSION`
  (`src/domain/value_objects/signal_artifact_schema.py`), confirm during
  implementation whether that participates in `compatibility_id`
  (ADR-068) or is orthogonal to it, and say so explicitly in the PR —
  do not assume either way.

---

## 5. Architecture Impact Assessment

* Which layer(s) will be touched?
  * Domain: `RiskAssessment` already carries `unevaluable_gates`
    (`risk_assessment.py:42`) and `TradeSetup` already carries
    `blocking_gates` (`trade_setup.py:126`) — likely no new domain field,
    but confirm whether `TradeSetup` needs its own explicit
    "blocked_by_policy: bool" style marker or whether persisting
    `unevaluable_gates` at the observation layer is sufficient to
    disambiguate (`gate_triggered in unevaluable_gates` is enough context
    once both are present in the same record).
  * Application: `build_candidate_observation_payload` /
    `build_session_observation_payload`
    (`accumulation_observation_fingerprint.py:67`, `:161`) need to carry
    `unevaluable_gates` through to the persisted payload; the declared
    `observation_result_fields` path for
    `PRODUCTION_POLICY_ID_UNEVALUABLE_GATE_POLICY`
    (`accumulation_policy_snapshot_payloads.py:472-512`) needs updating to
    point at it.
  * Infrastructure: none expected — this is payload shape, not a new
    table/column (session observations are stored as a JSON blob per
    ADR-056/schema-10).
  * Adapter: none expected.
* Does this introduce a new dependency? No.
* Does this affect determinism? No — same inputs still produce the same
  recorded output, the output is just more complete.
* Does this require persistence changes? Yes — new key(s) inside the
  existing JSON observation payload. No schema/table migration expected,
  but confirm against `CANDIDATE_OBSERVATION_SCHEMA_VERSION` per the
  Non-Goals note above.
* Does this place orchestration or policy inside an adapter? No.

```md
Layer plan:
- Domain: not touched, unless the disambiguation is judged to need an
  explicit marker beyond re-exposing `unevaluable_gates`
- Application: payload builders + the ADR-059 payload's
  observation_result_fields declaration
- Infrastructure: not touched
- Adapter: not touched
```

---

## 6. AI Usage Declaration

No AI involved. This is a deterministic payload-shape fix.

---

## 7. Risk, Signal, And Evidence Authority Considerations

* Which decision components are affected? RiskEngine (recording only — no
  behavior change) and the persisted-evidence surface that ADR-059 treats as
  the ML consumer's ground truth.
* How does behavior differ? It does not. ENTER/WATCH/AVOID/BLOCKED
  outcomes are unchanged; only what gets written down about a BLOCKED
  outcome gets more precise.
* Does this change what can produce ENTER/WATCH/AVOID? No.
* Does this promote diagnostic evidence or change tuning eligibility? No —
  `unevaluable_gates` is already authoritative domain output
  (`RiskAssessment`), this task only stops dropping it before storage.

---

## 8. Data & Persistence

* What data is read? `RiskAssessment.unevaluable_gates` (already computed,
  already present on every `AssessRiskResponse`).
* What data is written? The candidate/session observation JSON payload
  gains a field carrying `unevaluable_gates` (or the chosen equivalent),
  reachable by the path declared in
  `PRODUCTION_POLICY_ID_UNEVALUABLE_GATE_POLICY`'s
  `observation_result_fields`.
* Where is it stored? Same JSON blob columns used today (no new table).
* Is schema change required? Likely a `CANDIDATE_OBSERVATION_SCHEMA_VERSION`
  bump (additive field) — confirm during implementation; not a SQL schema
  migration.
* Old/new source equivalence checklist: N/A — this adds a field, it does not
  replace or reinterpret an existing one. `blocking_gates` / `risk_status`
  keep their current meaning unchanged.

---

## 9. Acceptance Criteria

* [ ] A session observation captured with `unevaluable_policy: block` and at
      least one unevaluable gate can be mechanically distinguished from one
      where the same gate genuinely triggered — assert this with a real
      `assess_risk_gate_evaluator` run through to the persisted payload, not
      a unit test that stops at `RiskAssessment`.
* [ ] `PRODUCTION_POLICY_ID_UNEVALUABLE_GATE_POLICY`'s payload declares a
      real `observation_result_fields` entry; its
      `"Declares no observation_result_fields"` note is removed or corrected.
* [ ] `test_real_production_config_declared_observation_paths_resolve`
      (`tests/adapters/composition/test_accumulation_production_policy_bundle.py`)
      is extended to cover the new declared path, following the same
      `_assert_declared_paths_resolve` pattern already used for the other
      two rows.
* [ ] Works without AI enabled (N/A — no AI involved).
* [ ] Deterministic for same inputs.
* [ ] No non-goals violated (gate logic, config defaults, retroactive
      backfill untouched).
* [ ] Relevant ADRs considered: ADR-059 (declared policy / observation
      binding), ADR-056 (session observation shape), ADR-068 (confirm schema
      version interaction, per Non-Goals).
* [ ] Adapter thinness reviewed — no adapter changes expected.
* [ ] **Lint Gate**: whole-repo `ruff check src/ tests/` and
      `ruff format --check src/ tests/` pass.

---

## 10. Testing Expectations

* Unit-test the payload builder change directly: a candidate whose
  `risk_assessment.gate_triggered == risk_assessment.unevaluable_gates[0]`
  (the policy-block shape) must serialize the disambiguating field.
* Extend the existing real-config observation-path regression test (see
  Acceptance Criteria) rather than inventing a parallel one — that test
  exists specifically to catch declared paths that don't resolve against
  real producers.
* All tests run offline (no network, no live DB).
* Confirm whole-repo Ruff check/format before close.

---

## 11. Documentation Impact

* README.md update required? No.
* New config options to document? No — no config surface changes.
* Limitations to state? Yes — update ADR-059's
  `risk.accum.unevaluable_policy` row description
  (`docs/adr/ADR-059-production-policy-snapshot-for-ml-challenges.md`,
  the 2026-08-06 amendment section) to remove or correct the "declares no
  observation fields" language once this lands.

---

## 12. Agent Execution Instructions

Before implementation, the agent must:

* Confirm understanding of this task and re-verify the three code citations
  above against current `main` (line numbers drift).
* Confirm compliance with `AGENT_QUICKSTART.md`.
* Decide and state up front: does disambiguation live purely in the
  application-layer payload (re-exposing `unevaluable_gates` as-is), or does
  it need a small domain-level marker on `TradeSetup`/`RiskAssessment`
  (e.g. a `blocked_by_unevaluable_policy: bool` derived property)? Either is
  defensible; state the choice and why before writing code.
* State the layer plan (§5) before coding.

Only then may implementation begin.

## Final Gate

If the agent cannot confidently answer:

> "How does this task comply with the Definition of Done?"

The task must be revised before execution.
