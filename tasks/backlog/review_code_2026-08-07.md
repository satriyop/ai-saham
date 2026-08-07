# Refactor Code Review — Findings Requiring Further Vetting

Status: `NEEDS_VETTING` — this is a review record, not an implementation-ready
task and not authorization to apply any proposed fix.

Review date: 2026-08-07

## 1. Task Metadata

**Task Title**
Vet and resolve the contract defects found in the post-ADR-067/ADR-068
refactor.

**Task Type**
Spike / Research followed by separately approved bugfix tasks.

**Priority**
High. RC-01A and RC-03 are fixed and verified; RC-01B is now vetted into an
implementation-ready design. The remaining unvetted findings include unsafe
browser-profile lock cleanup and plan-owned Action authority.

**Reviewed range**

- Committed baseline: `origin/main` at `05af50dd`.
- Reviewed HEAD: `619b6a4c` (`17` commits ahead).
- Diff size: `117 files changed, 5031 insertions, 4500 deletions`.
- Current code is the source of truth. Documentation was used only to identify
  intended invariants and then checked against executable paths.

## 2. Review Conclusion

The review remains open. RC-01A and RC-03 are fixed and vertically verified;
RC-01B is confirmed and design-vetted. RC-02 and RC-04 remain for one-by-one
vetting:

| ID | Severity | Status | Finding / result |
|---|---|---|---|
| RC-01A | P1 | `FIXED / VERIFIED` | Active v4/nine binds the complete resolved `DecisionPolicyConfig`; the original Action-changing counterexample now forks `compatibility_id` |
| RC-01B | P1 challenge/corpus | `VETTED / READY_FOR_IMPLEMENTATION` | Purpose-specific schema-14 producer bindings and fail-closed consumer contract selected; code not implemented |
| RC-02 | P1 | `NEEDS_VETTING` | Stockbit stale-lock cleanup fails open when lock ownership is unparseable |
| RC-03 | P2 | `FIXED / VERIFIED` | Readiness output and validation now source the same active v4 descriptor |
| RC-04 | P2 | `NEEDS_VETTING` | Plan swing still creates a plan-owned `TradeSetup.action` when screen has no setup |

Passing tests do not invalidate RC-02 or RC-04. RC-01B characterization tests
also preserve its current auto-selection, fallback, and unbound-artifact gaps;
the vetted design is not yet implemented.

## 3. Verification Evidence

Executed against the reviewed worktree before this review record was written:

```text
.venv/bin/ruff check src/ tests/
All checks passed!

.venv/bin/ruff format --check src/ tests/
1769 files already formatted

.venv/bin/python -m pytest -q --basetemp=/tmp/ai-saham-refactor-vet
6628 passed, 41 skipped in 258.49s

git diff --check origin/main...HEAD
passed

git diff --check
passed
```

Read-only production-corpus inspection via
`saham research accum status --format table` found `2,633` ACCUM observations
across five cohorts. Every cohort was `BLOCKED_POLICY` or `LEGACY_RAW_ONLY`;
none was challenge-ready. The report header named
`production_policy_snapshot.v2`, while active cohort validation required v3
and its eight-row closed set. No database writes or repairs were performed.

Post-fix verification on 2026-08-07:

```text
ai-saham full pytest: 6636 passed, 41 skipped
ai-saham Ruff check/format: passed
ai-saham git diff --check: passed
ml-saham focused v4 verifier/promotion: 36 passed
ml-saham challenge contract gate: 39 passed
ml-saham compileall (external pycache): passed
ml-saham git diff --check: passed
cross-repository real SQLite v4/nine read-only proof: passed
```

The ml-saham broad suite completed with `404 passed, 8 failed`; all eight are
existing demo-path failures outside RC-01A (retired `run_demo` entry points, an
undefined `mom`, and unavailable optional Prophet). Whole-repository ml-saham
Ruff remains blocked by 71 pre-existing findings outside the changed files;
the changed verifier/test files pass focused Ruff and format checks.

The mandatory ai-saham data audits reported manifest `PASS`, source-contract
`WARN`, and reconciliation `WARN`. The warnings are existing optional-field,
partial-source, and duplicate market-context/regime-identity findings, not v4
snapshot failures. The live DB was byte-identical before and after all audits:
`6c93209b9a01ef4230df6b2b19e4c0598fa8dfa2d23c0bfc731e036e4e29001c`.

## 4. Findings And Proposed Fixes

### RC-01A — ADR-068 compatibility identity omits resolved decision policy

Vetting status: `FIXED / VERIFIED` on 2026-08-07. Exact implementation record:
`tasks/backlog/rc01a_bind_decision_policy_into_accum_identity.md`.

The coordinated ai-saham/ml-saham cutover now uses immutable
`production_policy_snapshot.v4` with exactly nine rows. The same resolved typed
decision-policy object reaches both the production signal path and the
snapshot payload builder. The original ENTER-to-WATCH counterexample forks the
identity; old, partial, mixed, extra, and invalid sets contribute zero active
authority. v1-v3 remain immutable historical contracts. The real producer ->
SQLite -> ml-saham `mode=ro` verifier proof passed without changing the test
database.

#### Problem statement

`build_all_accumulation_policy_payloads()` accepts the resolved
`SignalEngineConfig`, but serializes only accum weights, evidence groups,
flags, classification, hard gates, raw-score weights, hard filters, and the
unevaluable-gate policy
(`src/application/services/accumulation_policy_snapshot_payloads.py:516`). It
does not serialize `SignalEngineConfig.decision_policy`.

The behavioral-probe runner independently constructs
`SignalEngine(config=SignalEngineConfig())`
(`src/application/services/behavioral_probe_runner.py:568`) instead of using
the runtime-resolved signal configuration. This prevents the probe digest from
covering runtime decision-policy mutations. `DecisionPolicyService` is used by
the signal-assessment use case and can change ENTER/WATCH/AVOID constraints,
including `enter_allowed`, thresholds, and maximum decision.

Fresh vetting changed the resolved typed RISK_ON decision policy from
ENTER-permitting behavior to WATCH-only behavior. The canonical decision moved
from ENTER to WATCH, while both configurations resolved the same compatibility
identity and the same two digest axes:

```text
base compatibility_id     sha256:682a2dede218c9a396590c0099584b078e5147f9dd4a688ae56fdc2e31398de6
mutated compatibility_id  sha256:682a2dede218c9a396590c0099584b078e5147f9dd4a688ae56fdc2e31398de6
same_identity              True
same_snapshot_digest       True
same_probe_digest          True
base decision              ENTER
mutated decision           WATCH
```

#### Impact

- Two observations can share a compatibility cohort even though canonical
  Action semantics differ.
- Readiness, comparison, or promotion code can treat an internally mixed cohort
  as coherent.

#### Vetted fix decision

1. Introduce immutable `production_policy_snapshot.v4`, with an exact nine-row
   active closed set. Add `signal.accum.decision_policy` as a v1 policy row and
   serialize the complete resolved `DecisionPolicyConfig`.
2. Keep the behavioral probe as the code-behavior axis. Do **not** inject
   runtime-resolved configuration merely to solve this defect: ADR-068's
   snapshot digest owns resolved policy, while the probe digest owns executable
   code behavior.
3. Add core probes and mutation coverage for currently named decision-policy
   code holes, including regime confidence, without treating finite coverage as
   proof of equivalence.
4. Cut the active producer, readiness validator, and `ml-saham` verifier to v4
   together. v1-v3 remain immutable historical sets and receive no alias,
   fallback, dual-write, or fabricated backfill.
5. Do not purge current data: the live database contains no ADR-068/v3
   observations or v3 snapshot rows. Keep existing rows as historical truth.

#### Settled classification

- `CONFIG_MATERIAL`: yes. The missing resolved policy can change Action.
- `OBSERVATION_SCHEMA`: no. RC-01A changes snapshot binding/identity, not the
  observation payload shape.
- `SEMANTIC_ENGINE`: no production calculation changes; the task records policy
  already consumed by the current engine.
- `EVIDENCE_CONTRACT`: no evidence meaning or authority changes.

#### Required negative and vertical tests

- Mutate every decision-policy identity field independently; each material
  mutation must change the canonical identity and the real production path must
  exhibit the expected output change.
- Generate the snapshot through the real production resolver, persist and read
  it, and validate it at the real readiness/consumer boundary.
- Prove old, partial, mixed, extra, duplicate, and digest-invalid snapshot sets
  contribute zero readiness authority.
- Prove no raw YAML/repository hash, hand-maintained semantic-version fallback,
  compatibility alias, or historical reinterpretation survives.

### RC-01B — Diagnostic producer semantics lack their own identity

Vetting status: `VETTED / READY_FOR_IMPLEMENTATION` on 2026-08-07. Exact task:
`tasks/backlog/rc01b_design_diagnostic_producer_identity.md`.

#### Problem statement

ADR-068 deliberately excludes diagnostic-only enrichment from the canonical
Action projection (`behavioral_probe_runner.py:586-592`). That is correct for
the Action cohort, but observations persist Alpha/Trigger, sector, company
quality, ticker-profile, institutional, and other diagnostic fields without a
separate producer-semantic identity. `ml-saham` consumes those fields while
selecting rows only by the Action `compatibility_id`.

Fresh vetting disabled the resolved Alpha/Trigger diagnostic producer. Its
persisted output changed from present to absent, but neither ADR-068 digest axis
nor the compatibility ID moved:

```text
base alpha_trigger output      present
mutated alpha_trigger output   absent
same behavioral probe digest  True
same snapshot digest           True
same compatibility_id         True
```

#### Impact

- Diagnostic panels can pool rows produced under different feature semantics.
- A challenge result can appear cohort-coherent while its input feature
  producer changed.
- This does not change live Action, because these fields remain diagnostic and
  non-authoritative.

#### Vetted implementation contract

1. Do **not** add all diagnostic producers to the canonical Action
   `compatibility_id`; that would recreate configuration-driven over-forking and
   fragment unrelated canonical cohorts.
2. Add immutable ai-owned `diagnostic_producer_snapshot.v1` rows from the exact
   typed objects used by the producers, then bind a closed purpose-specific
   producer set in accumulation observation schema 14.
3. Use four independent bindings: `mce.screen_display`,
   `sector.peer_context`, `institutional.accumulation_bag`, and
   `company_quality.bag`. `ml-saham` must require an explicit Action ID and the
   relevant explicit diagnostic ID before pooling rows.
4. Missing, mixed, unknown, or invalid diagnostic bindings fail closed for that
   diagnostic challenge. They do not invalidate unrelated canonical Action
   observations.
5. Historical observations/artifacts remain raw/display-only. Product
   extraction uses exact schema-14 window-7 paths, observation-bound MCE, and
   canonical `sc_sector_breadth`; no synthesized binding or legacy fallback.
6. Diagnostic control scoring must use the verified active v4/nine production
   policy. The current packaged static fixture is not production authority.
7. Diagnostic artifact schema 4 binds both identities, producer snapshots,
   spec content digest, population, source revision, and observation schema;
   reopen independently verifies them read-only and can never promote.

#### Additional confirmed current-code defects

The completed vet found that direct diagnostic execution auto-selects the
largest cohort, diagnostic health drops its selected compatibility ID,
diagnostic control scoring uses a static fixture, hand-maintained spec hashes
do not cover extractor semantics, artifacts discard producer identity, and
sector breadth is stored as `sc_sector_breadth` but extracted through mismatched
legacy names. The implementation task makes each path fail closed.

Settled classification: ai-saham `OBSERVATION_SCHEMA` plus diagnostic
`EVIDENCE_CONTRACT`; ml-saham `DATA_CONTRACT`, `PANEL_SCHEMA`, and diagnostic
`ARTIFACT_SCHEMA`. None is Action `CONFIG_MATERIAL`.

### RC-02 — Stockbit profile-lock cleanup deletes on unproven ownership

#### Problem statement

`_clear_stale_chromium_profile_locks()` says an unparseable marker is a safe
no-op (`src/infrastructure/browser/stockbit_session_actions.py:109-114`). The
implementation does the opposite: a non-numeric marker or `OSError` leaves
`owner_pid` as `None`, then falls through and unlinks `SingletonLock`,
`SingletonCookie`, `SingletonSocket`, `RunningChromeVersion`, and
`Default/Lock` (`:118-156`). The function runs before interactive/headless
reauthentication.

Current tests cover numeric live and dead PIDs, but not malformed targets,
read failures, host disagreement, or permission-related ambiguity.

#### Impact

- A lock can be deleted without proof that the Chromium owner is dead.
- Concurrent Chromium or automation processes may corrupt or race on the same
  profile.
- The docstring's safety guarantee is false on the highest-ambiguity branch.

#### Proposed fix — requires further vetting

Fail closed. Automatic cleanup may occur only when all of the following are
proven:

1. The marker format is recognized and parsed completely.
2. The recorded hostname is proven local under Chromium's actual platform
   format; cross-host/NFS ownership is never treated as stale merely because a
   local PID is absent.
3. PID liveness checking returns `ProcessLookupError`, which is the positive
   proof used for dead ownership.
4. Every deletion target is the exact, expected lock-family path inside the
   resolved profile directory and has the expected file/symlink type.

Any parse, read, permission, hostname, type, or liveness ambiguity should leave
all locks untouched and surface an actionable recovery message. Further vet
whether automatic deletion should exist at all; a safer design may report the
stale-lock diagnosis and require an explicit operator recovery command.

#### Questions that must be answered before implementation

- What lock encodings does the installed Chromium/Playwright stack actually
  use on supported macOS and Linux environments?
- Is a hostname-qualified marker sufficient proof for local ownership, and how
  are renamed hosts or shared profiles handled?
- Should cleanup remain implicit in reauthentication or move behind an explicit
  command/confirmation?
- Which lock objects are safe to remove together after dead ownership is
  proven?

#### Required negative tests

- Malformed and empty marker; non-numeric PID; unexpected separator.
- `readlink()`/`read_text()` failure and permission denial.
- Local live PID, local dead PID, cross-host marker, and PID-reuse adversarial
  case.
- Unexpected regular-file/symlink/directory types for every target.
- On every ambiguous case, assert zero unlink calls across the entire lock
  family.

### RC-03 — Readiness report names v2 while validating v3

Vetting status: `FIXED / VERIFIED` on 2026-08-07 as part of RC-01A.

#### Problem statement

`GetAccumulationProducerReadinessUseCase` imports
`POLICY_SNAPSHOT_BINDING_CONTRACT_V2` and hardcodes it into the report
(`src/application/use_case/get_accumulation_producer_readiness_use_case.py:18-20,142-145`).
The projection it invokes defines
`ACTIVE_SNAPSHOT_BINDING_CONTRACT = POLICY_SNAPSHOT_BINDING_CONTRACT_V3` and
validates the active v3 eight-policy closed set
(`src/application/services/accumulation_producer_readiness.py:87-89`).

The contradiction is visible in real CLI output: the top-level/header value is
v2 while per-cohort requirements are v3. Existing tests cover the v3 projection
internals but do not assert the report's top-level contract.

#### Impact

- Operator output misidentifies the active production contract.
- Machine consumers can select or explain the wrong contract.
- Debugging is misleading because one report contains two incompatible claims.

#### Implemented result

`GetAccumulationProducerReadinessUseCase` no longer imports or hardcodes v2. It
uses the active readiness descriptor, now v4/nine, that the cohort validator
also enforces. Focused use-case tests assert the DTO and JSON value, and the
real v4 producer/persistence/readiness/consumer vertical passed. v1-v3 remain
historical and cannot satisfy active readiness.

### RC-04 — Plan swing retains a plan-owned Action fallback

#### Problem statement

`resolve_authoritative_trade_setup()` returns the screen setup when present,
but otherwise returns `plan_recomputed`
(`src/application/services/swing_judgment_authority.py:22-43`). The plan
composer first creates that plan-side setup from its own signal/risk state and
then passes it to the helper
(`src/application/services/plan_swing_decision_composer.py:117-144`).

The module states both “Plan never recomputes Action” and “only composes a
TradeSetup of its own when screen produced none.” Those statements cannot both
describe a single authority boundary. The fallback is operationally reachable,
for example when screen has a signal assessment but no `TradeSetup` because
risk was unavailable, while the later plan path obtains enough risk data to
compose a setup. Tests currently preserve the fallback.

#### Impact

- Plan can originate ENTER/WATCH/AVOID after the screen judgment path produced
  no Action.
- The same ticker/session can gain an authority-bearing verdict because a
  second workflow had different data availability.
- Operator copy and ADR claims overstate the clean break.

#### Proposed fix — requires further vetting

Lock the missing-screen-verdict contract before editing. Recommended direction:

1. When no screen-authored `TradeSetup` exists, plan returns a typed
   unavailable/blocked judgment state and no authority-bearing `TradeSetup`.
2. If plan still needs structure such as entry, stop, target, or sizing, move
   those fields into a structure DTO that cannot carry `Action`; do not use an
   authority-bearing `TradeSetup` as a convenience transport.
3. Direct the operator back to the canonical screen/judge workflow to obtain a
   verdict. Do not synthesize WATCH, ENTER, or any other replacement Action.
4. Preserve the exact screen `TradeSetup` object/provenance when present; plan
   must not reconstruct an equal-looking copy or make a second judgment read.

#### Questions that must be answered before implementation

- What exact typed state represents “screen did not produce a verdict” in
  workflow state, JSON, plan files, and CLI/TUI output?
- Which downstream consumers require structural risk fields, and which
  currently assume `TradeSetup.action` always exists?
- Does removing the fallback require a `SEMANTIC_ENGINE` compatibility fork or
  an authority-contract-only clean break? This must be resolved before coding.
- Must previously persisted plan artifacts be quarantined or merely treated as
  historical display-only records?

#### Required negative and vertical tests

- Candidate absent; candidate present with signal but no setup; risk unavailable
  at screen then available at plan; and malformed/conflicting provenance.
- In every missing-screen-verdict case, assert that no plan engine/composer call
  can create an Action and no authority-bearing `TradeSetup` is persisted.
- When screen setup exists, assert object/provenance preservation and absence of
  a second judgment call.
- Exercise real CLI/JSON/plan-file/trade-log consumers so the missing state is
  explicit rather than converted to a default Action.

## 5. Architecture Impact Assessment

This review file changes no product layer. The likely implementation blast
radius is provisional and must be replaced by a precise file/contract inventory
in each implementation task.

```md
Layer plan:
- Domain: RC-04 may require a non-authority structure/missing-verdict type
- Application: RC-01, RC-03, and RC-04 policy/workflow ownership
- Infrastructure: RC-02 browser-profile lock handling; RC-01 persistence only if identity transport changes
- Adapter: RC-03 and RC-04 output mapping only; no policy may move here
```

- New dependencies: none expected.
- Determinism: must remain deterministic and local-first.
- Persistence: RC-01 and RC-04 may require contract/schema treatment after
  vetting; RC-02 and RC-03 should not change stored learning data.
- Adapter policy: forbidden. Adapters remain thin format/wiring boundaries.
- AI usage: none.

## 6. Non-Goals / Do Not Interpret This As

- Do not implement any proposed fix directly from this review record. Split
  findings into Task-Template-complete work only after the open questions are
  resolved.
- Do not mutate the meaning of ADR-059 v3 snapshots in place.
- Do not hash raw YAML, the repository, source revision, or arbitrary config as
  a substitute for a typed semantic contract. Source revision remains
  provenance, not compatibility identity.
- Do not preserve retired identities through aliases, dual reads/writes,
  fallbacks, or historical reinterpretation.
- Do not pool diagnostic features merely because their canonical Action
  identity matches.
- Do not delete Chromium locks unless dead local ownership is positively
  proven.
- Do not let plan manufacture a synthetic Action for a missing screen verdict.
- Do not put readiness, identity, lock-cleanup, or judgment policy in CLI/TUI
  adapters.
- Do not modify, purge, migrate, or backfill the current corpus until the
  identity and rollout contract is approved.
- Do not change `ml-saham` from this repository without an explicitly scoped
  cross-repository task.

## 7. Recommended Vetting And Delivery Sequence

1. RC-01A coordinated v4 cutover: completed and verified. RC-03 re-vet:
   completed and classified fixed.
2. RC-01B design vet: completed. Implement only after explicit approval, then
   vertically re-vet the coordinated cross-repository cutover.
3. Vet and implement RC-02 independently; it is infrastructure safety and does
   not depend on corpus identity.
4. Vet RC-04 as a separate authority-contract task. Resolve missing-state and
   transport ownership before touching the composer.
5. After each approved implementation, rerun focused tests, relevant
   architecture/contract tests, the whole-repository Ruff gate, full pytest
   where required by impact, and `git diff --check` on the exact final state.

## 8. Acceptance Criteria For Closing This Review Record

This review record is not complete merely because code changes compile. It may
move to done only when:

- [ ] Each finding is independently re-vetted against then-current code and
      classified as confirmed, qualified, stale, fixed, or remaining.
- [ ] Every confirmed finding has its own Task-Template-complete implementation
      contract with exact missing/failure states, transport owner, composition
      roots, negative tests, and close gates.
- [x] RC-01A includes a completed authority matrix and real canonical producer
      -> persistence/deserialization -> read-only consumer proof; RC-03 is then
      re-vetted against that same source of truth.
- [x] RC-01B inventories every cross-repository diagnostic consumer before an
      identity transport is selected.
- [x] Semantic-change classifications and corpus blast radius are explicit for
      RC-01A, RC-01B, and RC-03; RC-02 and RC-04 remain unvetted.
- [ ] No proposed fix weakens deterministic-first behavior, risk/signal
      guardrails, clean-break rules, or adapter thinness.
- [ ] The final implementations pass all required focused/full tests, the
      whole-repo Ruff check and format gate, and `git diff --check` on their
      exact final state.

## 9. Shared Worktree Note

The following pre-existing changes were present during review and are not part
of this file. Future agents must preserve them and must not use destructive git
cleanup:

```text
M  docs/adr/ADR-067-retire-setup-quality-and-fix-judgment-authority-by-surface.md
M  docs/evidence_diagnostic_factor_accum.md
M  tasks/backlog/00_SEQUENCE_accum_baseline_and_learning_loop.md
RM tasks/backlog/02_implement_adr_067_retire_setup_quality.md -> tasks/done/02_implement_adr_067_retire_setup_quality.md
?? tasks/backlog/09_expose_unevaluable_gate_block_provenance.md
```
