# Remove Plan-Owned Action And Preserve Screen Judgment Authority

Status: `FIXED / VERIFIED` — implemented and vertically verified on 2026-08-07.

Source finding: RC-04 in
`tasks/backlog/review_code_2026-08-07.md` (`FIXED / VERIFIED` 2026-08-07).

## 1. Task Metadata

**Task Title**
Make `saham plan swing` a structure-only consumer of the exact screen-authored
judgment, including an explicit unavailable state.

**Task Type**
Bugfix / authority-contract clean break.

**Priority**
High. Before this fix, the fallback could create an authority-bearing Action
after the canonical screen path produced none.

## 2. Problem Statement

The plan workflow invokes the real accumulation screen and normally receives
its `AccumulationCandidate.trade_setup`. When that field is absent, however,
`PlanSwingRiskTradeSetupComposer` performs a separate risk assessment and calls
`AssessTradeSetupUseCase`; `resolve_authoritative_trade_setup()` then accepts
that plan-created setup as a fallback.

This path is reachable when the screen candidate has a signal assessment but
its risk/TradeSetup phase was unavailable, while the later plan-specific risk
pass succeeds. The end-to-end characterization test currently asserts a
non-null plan `TradeSetup` in exactly that state. Passing tests therefore
preserve, rather than disprove, the defect.

The refactor also left dormant plan-judgment machinery behind after both public
adapters hard-coded market-context and technical-gate switches to false:

- plan request/state/response DTOs still carry those switches and three
  market-context preview fields;
- the plan composer can still create a `TradeSetup` and Action through
  `AssessTradeSetupUseCase`;
- composition still injects plan-owned RiskEngine/gates/MCE dependencies;
- `SwingTradePlan.action_source` is inferred from flags, not from the actual
  judgment object, and can falsely claim `plan_recomputed`;
- plan artifact completeness checks geometry only, so `trade accum --from-plan`
  has no typed proof that a canonical screen judgment was available.

## 3. Desired Outcome

For one plan execution, the embedded screen evaluation is the only possible
source of Signal/Risk/TradeSetup/Action:

1. If the evaluation contains a valid screen `TradeSetup`, plan preserves that
   exact object and exposes a typed `AVAILABLE` screen-judgment reference.
2. If the screen has no setup, plan may still calculate geometry, but exposes
   `UNAVAILABLE`, no `TradeSetup`, and no Action. It directs the operator to
   rerun the canonical screen/judgment path.
3. A ticker, analysis-date, or internally inconsistent screen judgment fails
   closed as an invariant error; plan must not repair, relabel, or replace it.
4. CLI, JSON, TUI, saved plan artifacts, and `trade accum --from-plan` express
   the same authority state.
5. No application module in the plan-swing boundary can call an Action producer.

## 4. Exact Contract Decisions

### 4.1 One typed screen-judgment reference

Introduce one closed typed value used by workflow state/response and mapped
without inference into the saved plan artifact:

```text
ScreenJudgmentStatus = AVAILABLE | UNAVAILABLE
ScreenJudgmentSource = screen_accum
ScreenJudgmentUnavailableReason =
  no_screen_candidate
  | no_screen_signal_assessment
  | no_screen_risk_assessment
  | no_screen_trade_setup

ScreenJudgmentReference:
  status
  source
  ticker
  snapshot_date
  trade_setup
  unavailable_reason
```

Invariants:

- `AVAILABLE` requires the exact screen `TradeSetup`, source `screen_accum`, and
  no unavailable reason.
- `UNAVAILABLE` requires `trade_setup=None`, source `screen_accum`, and exactly
  one reason.
- For `AVAILABLE`, candidate ticker and `TradeSetup.ticker` must equal the
  canonicalized request ticker, and `TradeSetup.snapshot_date` must equal
  `AccumulationCandidateEvaluationResult.analysis_date`.
- A present setup with missing screen signal or risk, any identity mismatch, or
  any unknown enum value is malformed authority and raises a dedicated typed
  application invariant error. It is not downgraded to unavailable.
- When the setup is absent, reason precedence is the list above: no candidate,
  then no signal, then no risk, then no setup. These codes report only observed
  boundary state and do not invent upstream causality.

Replace the current resolver with a pure screen-reference resolver. It accepts
the evaluation result plus expected ticker and returns only the typed reference;
it has no `plan_recomputed` parameter and no fallback input.

### 4.2 Remove the entire plan Action-production seam

- Delete `PlanSwingRiskTradeSetupComposer` and its plan-side risk,
  `AssessTradeSetupUseCase`, technical-gate, and market-context TradeSetup
  preview paths.
- Replace `PlanSwingDecisionComposer` with a judgment-reference collaborator
  that only resolves and carries the screen reference. It receives no
  SignalEngine, RiskEngine, risk gates, market-context evaluator, or registry.
- Remove `with_market_context`, `with_technical_gate`, `regime_universe`, and
  `benchmark` from `PlanSwingWorkflowRequest` and all CLI, TUI, daily-lens,
  factory, state, and test construction sites. The shipped adapters already
  expose no switches and pass false; this removes inaccessible application
  authority, not a public feature.
- Remove plan-owned `risk_response`, `market_regime`,
  `market_context_signal_preview`, `market_context_risk_preview`, and
  `market_context_trade_setup_preview` from plan judgment DTOs and displays.
- The embedded screen candidate's exact `signal_assessment`, `risk_assessment`,
  and `trade_setup` may be rendered as one referenced screen judgment. They must
  not be recomputed or mixed with plan-produced responses.
- Keep the screen candidate builder wired with its canonical Signal/Risk
  dependencies. The removal applies only to the second plan-owned path.

### 4.3 Plan JSON clean break

Bump `plan_swing` JSON from schema 1 to schema 2. Keep the top-level canonical
groups `verdict`, `evidence`, and `diagnostics`, but make `verdict` a serialized
screen-judgment reference:

```json
{
  "status": "AVAILABLE",
  "source": "screen_accum",
  "ticker": "BBCA",
  "snapshot_date": "2026-08-07",
  "action": "WATCH",
  "trade_setup": {},
  "unavailable_reason": null,
  "signal_assessment": {},
  "risk_assessment": {}
}
```

For `UNAVAILABLE`, `action`, `trade_setup`, and any missing screen component are
null and `unavailable_reason` is required. Remove plan-risk and MCE preview
fields rather than retaining null compatibility slots. Do not add schema-1
aliases or a compatibility serializer.

### 4.4 `SwingTradePlan` schema 2 and handoff

Replace free-form `action_source` and flag provenance with a closed judgment
reference containing `status`, fixed `source=screen_accum`, `ticker`,
`snapshot_date`, `action`, and `unavailable_reason`.

- The builder accepts the typed workflow reference. It never infers authority
  from feature flags or a nullable `TradeSetup`.
- Add separate `geometry_complete` and `handoff_ready` properties.
  `handoff_ready` requires complete geometry and an `AVAILABLE` valid screen
  judgment. `is_complete` must be removed so callers cannot confuse the two.
- `incomplete_reason` describes geometry only. Judgment unavailability remains
  in `judgment_ref`; adapters must not collapse the two states.
- CLI and TUI save the schema-2 artifact for every completed workflow, including
  unavailable judgment, so the latest file reflects the latest analysis and
  preserves its blocked reason. The immutable plan-ID copy remains.
- Footer/TUI output offers `--from-plan` only when `handoff_ready`; otherwise it
  says `Screen judgment unavailable; run saham screen accum TICKER, then rerun
  saham plan swing TICKER.` Geometry may still be displayed as structure-only.
- `trade accum --from-plan` accepts only schema 2 with `handoff_ready=True`.
  Schema 1, unknown schemas, unavailable judgment, identity mismatch, malformed
  enums, and incomplete geometry all fail closed with distinct messages.
- Existing schema-1 files remain untouched historical files. There is no
  migration, translation, alias, dual read, or reinterpretation. Rerunning
  screen then plan creates a new schema-2 artifact.

## 5. Non-Goals

- No change to accumulation screen scoring, RiskEngine, SignalEngine,
  `AssessTradeSetupUseCase`, or canonical Action policy.
- No synthetic WATCH/AVOID/BLOCKED value for unavailable screen judgment.
- No Action field in a new convenience structure DTO.
- No revival of MCE/technical-gate plan switches under another name.
- No SQLite, learning observation, compatibility-ID, corpus, YAML, provider, or
  ml-saham change.
- No order execution. The existing plan-to-journal handoff remains explicit.
- No adapter-owned availability or authority inference.

## 6. Architecture Impact Assessment

```md
Layer plan:
- Domain: version and harden SwingTradePlan judgment-reference and handoff invariants
- Application: own screen-reference resolution; delete all plan Action/risk/MCE production
- Infrastructure: not touched
- Adapter: map the typed state consistently in CLI/TUI and remove dead wiring only
```

- New dependency: No.
- Determinism affected: Yes, beneficially. One input screen evaluation maps to
  one closed reference; no second data-availability-dependent judgment exists.
- Persistence change: Yes, filesystem `swing_trade_plan` schema 1 -> 2 only.
- Warm-up data: No.
- Policy in adapter: No.

Composition roots to update include
`plan_swing_workflow_factory.py`, `plan_swing_commands.py`, TUI composition, and
the daily setup-lens use case. Adapters may format messages and save the typed
artifact; they may not decide its status/source/readiness.

## 7. AI Usage Declaration

No AI involved. All authority, structure, serialization, and failure behavior
remain deterministic and offline.

## 8. Risk, Signal, And Evidence Authority

- Signal/Risk/TradeSetup/Action calculation on screen: unchanged.
- What can produce ENTER/WATCH/AVOID: narrowed on the plan surface from screen
  or plan fallback to screen only.
- Market context and technical risk inside plan: removed, not promoted.
- Plan geometry: remains non-authoritative structure and may exist without a
  judgment, but cannot enter the journal handoff in that state.
- Diagnostic evidence and tuning eligibility: unchanged.

Classification:

- `SEMANTIC_ENGINE`: yes for the plan surface. A previously synthetic Action
  becomes typed unavailable. The canonical screen engine is unchanged.
- `ARTIFACT_SCHEMA`: yes, `plan_swing` JSON and `swing_trade_plan` move to v2.
- `CONFIG_MATERIAL`: no.
- `OBSERVATION_SCHEMA`: no.
- `EVIDENCE_CONTRACT`: no change to canonical screen evidence.

No compatibility-ID fork or corpus quarantine is required because plan output
is not a learning observation/cohort. The explicit artifact version clean break
prevents old plan judgment from acquiring current handoff authority.

## 9. Data & Persistence

Reads remain local candles, broker data, configuration, and the one embedded
screen evaluation. Writes remain filesystem plan JSON only. No database schema
or row changes are allowed.

Old and new plan artifacts are not semantically equivalent: schema 1 permitted
plan-owned/inferred Action provenance; schema 2 proves screen ownership or
records unavailability. The version and strict loader behavior make that
difference explicit.

## 10. Required Tests

- Unit reason matrix for absent evaluation, absent signal, absent risk, and
  absent setup, including exact precedence.
- Available path proves object identity (`is`, not merely equality) from screen
  candidate through workflow response.
- Candidate/setup ticker mismatch, setup/evaluation date mismatch, present setup
  with missing prerequisites, unknown status/source/reason, and conflicting
  status fields raise typed invariant errors and create no artifact.
- Vertical reproducer: screen signal exists, screen setup is absent, and the
  formerly successful plan-risk seam is available. Result must contain no
  Action/TradeSetup and no Action-producing collaborator may be called.
- Source/AST contract over all `plan_swing*` application modules forbids
  `AssessTradeSetupUseCase`, `AssessTradeSetupRequest`, `plan_recomputed`,
  `market_context_trade_setup_preview`, `evaluate_swing_trade_setup`, and
  `evaluate_accumulation_discovery`.
- Constructor/composition tests prove the removed switches and dependencies no
  longer exist at application, CLI, TUI, and daily-lens roots.
- Golden plan JSON schema-2 tests for available and each unavailable state;
  assert removed fields are absent.
- SwingTradePlan schema-2 invariant/hash/round-trip tests; schema-1, flat legacy,
  unknown schema, malformed reference, and cross-ticker/date inputs fail closed.
- `trade accum --from-plan` rejects unavailable judgment even with complete
  geometry and rejects complete judgment with incomplete geometry.
- CLI and TUI parity tests prove both save the same typed latest state, display
  geometry without inventing Action, and expose handoff only when ready.
- Daily setup-lens maps unavailable judgment to no Action without fallback.

Focused characterization already run during vetting:

```text
60 passed in 0.34s
```

Those tests cover judgment authority, plan composition/workflow, plan artifact,
and signal-availability contracts; implementation inverted or deleted the named
fallback assertions.

Implementation verification on the final RC-04 worktree:

```text
.venv/bin/python -m pytest tests -q -k 'plan_swing or swing_trade_plan'
212 passed, 6437 deselected in 8.04s

.venv/bin/python -m pytest -q --basetemp=/tmp/ai-saham-rc04-20260807-1
6624 passed, 41 skipped in 215.69s

.venv/bin/ruff check src/ tests/
All checks passed!

.venv/bin/ruff format --check src/ tests/
1763 files already formatted

git diff --check
passed
```

Implementation close gates:

```text
.venv/bin/python -m pytest <all affected focused suites>
.venv/bin/ruff check src/ tests/
.venv/bin/ruff format --check src/ tests/
.venv/bin/python -m pytest -q --basetemp=<bounded temp path>
git diff --check
```

All tests run offline. No test may write into the real journal/plans directory
or SQLite database.

## 11. Acceptance Criteria

- [x] The plan boundary has exactly one typed screen judgment reference.
- [x] Missing screen setup produces no Action-bearing object anywhere.
- [x] Available setup preserves exact object and ticker/date provenance.
- [x] No plan application module imports or calls any Action producer.
- [x] Dormant plan risk/MCE/technical switches, state, previews, dependencies,
      and display panels are removed.
- [x] JSON and saved plan schemas are v2 and fail closed as specified.
- [x] Geometry completeness and journal-handoff readiness cannot be confused.
- [x] CLI, TUI, daily lens, saved files, and `--from-plan` agree.
- [x] Historical v1 files are unchanged and cannot gain active authority.
- [x] Canonical screen output, SQLite, learning corpus, and ml-saham are unchanged.
- [x] Required focused, negative, parity, full pytest, Ruff check/format, and
      `git diff --check` gates pass.

## 12. Documentation Impact

- README update: only if it documents plan-file schema or `--from-plan`.
- Config options: remove any remaining plan MCE/technical-gate documentation;
  add no new option.
- Update current architecture/ADR wording only where it still describes
  plan-owned previews or fallback. Do not rewrite historical ADR decisions.
- Document schema-1 plans as historical/display-only and the rerun instruction.

## 13. Agent Execution Instructions

Before implementation, reread `AGENT_QUICKSTART.md`, `AGENTS.md`, the bugfix
checklist, Definition of Done, and current authority ADRs selected by the
reading matrix. Reconfirm the code paths because this task was vetted against
HEAD `3c3e3c0193feea77d0d600d6fcef15368ab46c68` with unrelated dirty worktree
changes present.

State risks, ambiguities, assumptions, and the layer plan before coding. Stage
only files owned by RC-04; do not absorb RC-02 or the user's pre-existing staged
rename. Any need to retain a plan-owned Action producer, legacy loader, or
adapter authority is an architectural conflict and requires clarification.
