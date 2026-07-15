# Backlog: Signal Refactor Contract Fixes

**Source audit:** `tasks/thought/signal_refactor_audit.md` (verified 2026-07-14)
**Audit verification run:** 2954 tests passed, `git diff --check` clean
**Status:** Ready for agent execution — read each task before picking one up

---

> [!IMPORTANT]
> All tasks in this backlog touch live scoring/policy code.
> Before starting ANY task: read `AGENT_QUICKSTART.md`, confirm `AGENTS.md` / `GEMINI.md` compliance, and **state the layer plan**.
> Do not promote diagnostic evidence or tune thresholds while these contract ambiguities remain unresolved.

---

## Execution Order

Execute tasks in this order. Later tasks depend on the naming clarity established by earlier ones.

| # | Task ID | Priority | Description |
|---|---------|----------|-------------|
| 1 | `HIGH-1` | HIGH | Fix RS window policy (5d vs 20d) |
| 2 | `HIGH-2` | HIGH | Fix coverage/conviction gating source and naming |
| 3 | `MEDIUM-1` | MEDIUM | Force institutional accumulation status to DIAGNOSTIC |
| 4 | `MEDIUM-2` | MEDIUM | Rename Alpha/Trigger `market_context` to `sector_context` |
| 5 | `MEDIUM-3` | MEDIUM | Reconcile output contract (missing fields) |
| 6 | `MEDIUM-4` | MEDIUM | Update phase docs to match tracker and code |
| 7 | `MEDIUM-5` | MEDIUM | Guard `SignalEngine.evaluate()` against misleading use |
| 8 | `LOW-2` | LOW | Fix RS weight example in `signal_refactor.md` |

---

## Task HIGH-1 — Fix RS Window Policy (5d vs 20d)

### Metadata

- **Type:** Refactor
- **Priority:** HIGH
- **Affects entry caps:** YES — real candidates may be capped/excluded differently depending on resolution

### Problem

`setup_phase_rs_policy.py` enforces the RS policy against `rs_vs_ihsg_5d`.
`docs/signal_refactor.md` documents the RS policy using `rs_vs_ihsg_20d` (structural rotation signal).
The two windows produce different candidates being capped to WATCH or AVOID.

Key files:

- `src/application/services/setup_phase_rs_policy.py:26` — reads `rs_vs_ihsg_5d`
- `src/application/services/setup_phase_detector.py:92-98` — calls `setup_phase_rs_policy_reasons()`
- `src/application/services/relative_strength_calculator.py` — computes both; only 5d consumed by policy
- `docs/signal_refactor.md:495-499, 516-535, 1981` — canonical doc says 20d

### Decision Required (Human Must Decide First)

**Option A — Doc is canonical, code is wrong:**
Change policy to use `rs_vs_ihsg_20d`. Update `SetupEvidence` to carry 20d field into policy.

**Option B — 5d is intentional:**
Update `docs/signal_refactor.md` to explicitly say "entry timing uses 5d; 20d remains attribution/context."

> [!CAUTION]
> Do NOT resolve this by guessing. An explicit owner decision must precede implementation.
> Changing the window changes live entry caps and exclusions immediately.

### Desired Outcome

- A single, clearly documented RS window drives `rs_policy_warning` and `rs_policy_hard_exclude`.
- Code and doc agree.
- Regression tests prove the chosen window drives warnings and hard excludes.

### Non-Goals

- No change to RS score weighting formula.
- No new data providers.
- No risk engine changes.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: not touched (unless SetupEvidence value object needs a field added)
- Application: setup_phase_rs_policy.py, possibly setup_phase_rs_policy_reasons()
- Infrastructure: not touched
- Adapter: not touched
- Documentation: docs/signal_refactor.md — update whichever option is chosen
```

### Acceptance Criteria

- [ ] One RS window is authoritative in both code and docs
- [ ] `rs_policy_warning` and `rs_policy_hard_exclude` tests cover the chosen window explicitly
- [ ] No other scoring behavior changed
- [ ] Full test suite passes
- [ ] `git diff --check` clean

---

## Task HIGH-2 — Fix Coverage/Conviction Gating Source and Naming

### Metadata

- **Type:** Refactor
- **Priority:** HIGH
- **Affects entry gating:** YES — decision floors apply to wrong source when setup phase exists

### Problem

`assess_signal_evidence_use_case.py:70-79` sets `policy_coverage` and `policy_conviction` from
`setup_phase.coverage_score` / `setup_phase.conviction_score` when a phase exists.
These are **setup-phase-only** scores, not the final signal coverage/conviction the user sees in output.
The doc pseudocode (`docs/signal_refactor.md:2152-2154`) implies the floor checks final signal coverage.

A tuner correcting "coverage floors" will unknowingly be tuning setup-phase readiness, not signal coverage.

Key files:

- `src/application/use_case/assess_signal_evidence_use_case.py:70-79` — gating logic
- `src/application/services/setup_phase_detector.py:281-311` — builds phase `coverage_score`
- `src/application/services/signal_evidence_group_scorer.py:112-139` — `renormalize()`, computes final `confidence`

### Decision Required (Human Must Decide First)

**Option A — Decision floors should use final signal coverage/conviction:**
Use Alpha/Trigger or whole-signal coverage/conviction for floors.

**Option B — Decision floors are setup-phase readiness floors (intended behavior):**
Rename config/docs: `min_coverage` to `phase_min_coverage`, `min_conviction` to `phase_min_conviction`.

> [!CAUTION]
> Do not leave one `min_coverage` name mapping to two different concepts.

### Desired Outcome

- Decision floor config names unambiguously match what they gate.
- A regression test exists where signal coverage != phase coverage, proving which one gates ENTER.
- Docs updated to match chosen option.

### Non-Goals

- No change to scoring weights.
- No new evidence builders.
- No risk engine changes.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: possibly value object field rename if coverage_score lives there
- Application: assess_signal_evidence_use_case.py gating logic; config naming
- Infrastructure: not touched
- Adapter: not touched
- Documentation: docs/signal_refactor.md pseudocode section (2152-2154)
```

### Acceptance Criteria

- [ ] One unambiguous coverage/conviction concept drives decision floors
- [ ] Config key names match what they gate
- [ ] Regression test: signal coverage != phase coverage yields correct source gating ENTER
- [ ] Full test suite passes
- [ ] `git diff --check` clean

---

## Task MEDIUM-1 — Force Institutional Accumulation Status to DIAGNOSTIC

### Metadata

- **Type:** Bugfix / Guardrail
- **Priority:** MEDIUM
- **Risk:** Accidental evidence promotion via YAML config is currently possible

### Problem

`institutional_accumulation_evidence_builder.py` module docstring says `evidence_status is always DIAGNOSTIC`.
But `institutional_flow_config.py:78-83` reads `evidence_status` directly from YAML and accepts any value.
Changing `config/institutional_accumulation.yaml` to `evidence_status: PRODUCTION` would promote this evidence
without going through promotion guardrails.

Today's config sets DIAGNOSTIC, so no live impact — but the gap is a single YAML edit away.

Key files:

- `src/application/services/institutional_flow_config.py:78-83` — reads evidence_status from YAML
- `src/application/services/institutional_accumulation_evidence_builder.py:1-19, 200, 239, 248, 262, 274` — passes config status through
- `config/institutional_accumulation.yaml:4` — current value is DIAGNOSTIC

### Desired Outcome

- `InstitutionalAccumulationConfig.from_mapping()` ignores YAML `evidence_status` and always forces `EvidenceStatus.DIAGNOSTIC`.
- `config/institutional_accumulation.yaml`: remove `evidence_status` key, or keep it as a commented note only.
- Regression test: raw config with `evidence_status: PRODUCTION` still yields DIAGNOSTIC output.

### Non-Goals

- No change to scoring weights or formula.
- No change to other producers (company quality, sector context).
- No new features.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: not touched
- Application: institutional_flow_config.py (from_mapping), institutional_accumulation_evidence_builder.py (status passthrough)
- Infrastructure: not touched
- Adapter: not touched
- Documentation/Config: comment in config/institutional_accumulation.yaml
```

### Acceptance Criteria

- [ ] YAML `evidence_status: PRODUCTION` cannot promote institutional accumulation evidence
- [ ] `from_mapping()` always sets `EvidenceStatus.DIAGNOSTIC` regardless of YAML value
- [ ] Regression test present and passing
- [ ] Full test suite passes
- [ ] `git diff --check` clean

---

## Task MEDIUM-2 — Rename Alpha/Trigger `market_context` to `sector_context`

### Metadata

- **Type:** Refactor (naming / doc clarity)
- **Priority:** MEDIUM
- **Risk:** Low behavioral impact (group is DIAGNOSTIC); high future tuning confusion risk

### Problem

`config/signal_engine.yaml:155` defines Alpha/Trigger group weight as `market_context: 0.25`.
`signal_alpha_trigger_projection.py:60-70` populates the `"market_context"` group slot with **sector context evidence**,
not `MarketContext` or regime evidence.
A future agent tuning `market_context` will think they are tuning IHSG regime influence — they are not.

Key files:

- `config/signal_engine.yaml:155, 165, 170, 175, 182` — `market_context` weight key
- `src/application/services/signal_alpha_trigger_projection.py:60-70` — population logic
- `src/application/services/signal_alpha_trigger_projection.py:91-99` — `_score_sector_market_context()`

### Desired Outcome

**Option A (preferred):** Rename `market_context` to `sector_context` in config and code everywhere it refers to sector context evidence.

**Option B (if rename is too risky for compatibility):** Add a hard comment in `config/signal_engine.yaml` and `AssessSignalEvidenceUseCase` stating the slot contains sector context, not MarketContext/regime.

### Non-Goals

- No change to actual score values or group weights.
- No new evidence builders.
- No behavioral change to signal output (only naming).

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: not touched
- Application: signal_alpha_trigger_projection.py (rename or comment), assess_signal_evidence_use_case.py (if it references the slot name)
- Infrastructure: not touched
- Adapter: not touched
- Documentation/Config: config/signal_engine.yaml (rename key or add comment)
```

### Acceptance Criteria

- [ ] No code or config uses `market_context` to mean sector context without an explicit clarifying comment
- [ ] Alpha/Trigger projection tests pass with updated slot name
- [ ] Full test suite passes
- [ ] `git diff --check` clean

---

## Task MEDIUM-3 — Reconcile Output Contract (Missing Fields)

### Metadata

- **Type:** Documentation / Partial Implementation
- **Priority:** MEDIUM
- **Risk:** Confusion for implementers; no production runtime impact today

### Problem

`docs/signal_refactor.md:2053-2078` describes an output contract including fields the code does not emit:

- `regime_detection_method` — always `None` at build time; `MarketContext` has no detection method field
- `volatility_size_multiplier` and `liquidity_size_multiplier` inside `decision_constraints` — computed separately, not carried into constraints
- `evidence_statuses` map — not emitted in signal output

Key files:

- `src/domain/value_objects/decision_constraints.py` — missing `volatility_size_multiplier`
- `src/application/services/volatility_context.py` — computes multiplier but does not carry it into constraints
- `src/application/services/accumulation_observation_metadata.py:26` — writes `regime_detection_method: None`
- `src/domain/value_objects/market_context.py` — no detection method or last-changed date field
- `src/domain/value_objects/signal_observation_fingerprint.py:63` — field exists, always None

### Decision Required (Human Must Decide First)

**Option A — Split the doc contract (lower risk):**
Rewrite `docs/signal_refactor.md:2053-2078` into two blocks:

- `current_contract` — what code actually emits today
- `target_contract` — planned after future execution-policy work

**Option B — Implement the missing fields:**

- Add `regime_detection_method` to `MarketContext` / `RegimeDetectionEvidence`
- Carry `volatility_size_multiplier` into `DecisionConstraints` or `TradeSetup` policy
- Emit explicit `evidence_statuses` map in signal output

> [!NOTE]
> Option A preserves doc-as-intent semantics and is lower risk. Only take Option B if all HIGH tasks are resolved first.

### Non-Goals

- No change to scoring formula.
- No new data providers.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan (Option A — doc split):
- Domain: not touched
- Application: not touched
- Infrastructure: not touched
- Adapter: not touched
- Documentation: docs/signal_refactor.md — split output contract section

Layer plan (Option B — implementation):
- Domain: MarketContext (add detection_method field), DecisionConstraints (add volatility_size_multiplier)
- Application: volatility_context.py (carry multiplier), accumulation_observation_metadata.py (populate field)
- Infrastructure: not touched
- Adapter: not touched
- Documentation: docs/signal_refactor.md — mark fields as implemented
```

### Acceptance Criteria

- [ ] Output contract doc matches what code actually emits (no phantom fields)
- [ ] If Option B: new fields are populated at build time and covered by tests
- [ ] Full test suite passes
- [ ] `git diff --check` clean

---

## Task MEDIUM-4 — Update Phase Docs to Match Tracker and Code

### Metadata

- **Type:** Documentation
- **Priority:** MEDIUM
- **Risk:** Future agents may duplicate already-implemented work

### Problem

`docs/signal_refactor_phases.md:92, 129` says phase A1 is partially implemented and A2 is planned.
`docs/signal_refactor_tracker.md:71-85` says A1-H are done and I is in progress.
The code confirms A1-H objects/use cases exist and tests pass.

An agent reading only `signal_refactor_phases.md` will treat done work as unstarted.

### Desired Outcome

- `docs/signal_refactor_phases.md` is no longer the implementation-status source.
- A single line at the top reads: "Implementation status lives in `docs/signal_refactor_tracker.md`; this file is the phase contract only."
- Phase statuses in `signal_refactor_phases.md` are either updated to match the tracker or removed.

### Non-Goals

- No code changes.
- No changes to tracker format.
- No new features.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: not touched
- Application: not touched
- Infrastructure: not touched
- Adapter: not touched
- Documentation: docs/signal_refactor_phases.md only
```

### Acceptance Criteria

- [ ] `signal_refactor_phases.md` header redirects to tracker for implementation status
- [ ] No phase status in the phases doc contradicts the tracker for A1-H
- [ ] `git diff --check` clean

---

## Task MEDIUM-5 — Guard `SignalEngine.evaluate()` Against Misleading Use

### Metadata

- **Type:** Refactor / Documentation
- **Priority:** MEDIUM
- **Risk:** Agents and CLI callers may treat `evaluate()` results as full-evidence signals

### Problem

`signal_engine.py:101-124` `evaluate()` self-fetches enrichment but passes no setup/flow evidence
to `AssessSignalEvidenceRequest`. The docstring says confidence will be 0 and evidence groups are absent —
but the returned `AssessSignalResponse` carries no equivalent machine-readable warning.
A caller treating the result as a full signal will get flags-only output with misleading authority.

Key files:

- `src/application/services/signal_engine.py:101-124` — `evaluate()` self-fetch path
- `src/application/services/signal_engine.py:112-113` — inline docstring warning
- `src/application/services/signal_engine.py:134-170` — `evaluate_with_context()` (full pipeline)

### Desired Outcome

- `evaluate()` returns an `AssessSignalResponse` with an explicit machine-readable field or flag indicating no evidence groups were provided.
- A test exists: `evaluate()` cannot produce high-confidence ENTER without evidence groups.
- Consider a future rename: `evaluate_context_only()` or `evaluate_fallback()` — mark as TODO if deferred.

### Non-Goals

- No change to scoring formula or output values.
- No change to `evaluate_with_context()` behavior.
- No renaming in this task (unless trivial); deferred rename is acceptable.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: not touched
- Application: signal_engine.py (add explicit warning field/flag to evaluate() response)
- Infrastructure: not touched
- Adapter: not touched
- Documentation: inline docstring (signal_engine.py)
```

### Acceptance Criteria

- [ ] `evaluate()` response carries a machine-readable indicator of missing evidence groups
- [ ] Test: `evaluate()` cannot return high-confidence ENTER
- [ ] `evaluate_with_context()` behavior unchanged
- [ ] Full test suite passes
- [ ] `git diff --check` clean

---

## Task LOW-2 — Fix RS Weight Example in `signal_refactor.md`

### Metadata

- **Type:** Documentation
- **Priority:** LOW
- **Pre-condition:** Resolve HIGH-1 first; RS window must be settled before rewriting RS examples

### Problem

`docs/signal_refactor.md:461-473` shows a YAML snippet with `relative_strength_vs_ihsg.weight: 0.15`.
`docs/signal_refactor.md:486-490` immediately says RS should not be treated as merely a 15% additive component
for breakout/accumulation/foreign-bounce setups.

The code example contradicts the explanatory text adjacent to it, potentially misleading implementers.

### Desired Outcome

- The snippet is rewritten so RS appears under `eligibility_caps` or `max_decision_policy`, not only under weighted scoring.
- If RS has both an additive score contribution and a policy cap, both layers are shown explicitly:
  e.g., `rs_additive_weight` alongside `rs_decision_cap_policy`.

### Non-Goals

- No code changes.
- No change to actual RS weights in config.

### Layer Plan (Agent Must State Before Coding)

```md
Layer plan:
- Domain: not touched
- Application: not touched
- Infrastructure: not touched
- Adapter: not touched
- Documentation: docs/signal_refactor.md:461-490 only
```

### Acceptance Criteria

- [ ] Doc snippet no longer implies RS is purely additive
- [ ] Both score contribution and cap policy are shown if both exist
- [ ] `git diff --check` clean

---

## Guards: What NOT To Do While These Tasks Are Open

> [!WARNING]
> These restrictions apply until the contract ambiguities above are resolved.

- **Do not** promote `market_context`, `company_quality_context`, domestic bandar evidence, sector context, or event alpha based on implementation completeness alone.
- **Do not** tune RS thresholds until HIGH-1 (5d vs 20d) is settled.
- **Do not** tune `regime_conditioning.*` — code and config correctly mark it legacy diagnostic.
- **Do not** use historical replay labels as production proof if fingerprints were generated before the current PIT enrichment/fingerprint contract.
- **Do not** use `min_coverage` / `min_conviction` in tuning until HIGH-2 names are resolved.

---

## Already Confirmed Aligned (Do Not Re-implement)

The following are working and tested. Do not revisit unless a specific regression surfaces:

- Deterministic-first boundaries: signal/refactor code lives in application/domain, not CLI policy
- Risk remains separate from signal; `DecisionPolicyService` caps signal entry but does not replace `RiskEngine`
- Canonical scoring path is staged evidence via `AssessSignalEvidenceUseCase`
- Missing setup/flow groups lower coverage; not neutral-filled
- BB compression is setup/phase evidence, not flow evidence
- Volume trigger requires dry-up plus expansion, not raw volume spike
- Setup entry authority enforced by `config/swing_setups.yaml` and decision policy
- Forward labels and signal observation fingerprints exist
- Evidence authority caps enforced by `AlphaTriggerAggregator`
- Promotion guardrails exist in config loading and tuning patch validation
- Full test suite (2954 tests) currently passes
