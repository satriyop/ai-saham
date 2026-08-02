# Decide Accum Group-Breadth Production Authority

Status: `DECISION_ACCEPTED`

Companion consumer program:

- `~/dev/ml-saham/tasks/backlog/close_accum_challenge_decision_coverage_gaps.md`

Related producer program:

- `tasks/backlog/grow_snapshot_bound_accum_challenge_corpus.md`

## 1. Task Metadata

- Task title: Decide whether accumulation group breadth is production policy or
  retired configuration
- Task type: Spike / Research + architecture decision
- Priority: High
- Primary owner: `ai-saham`
- Current semantic classification: documentation-only and `NON_SEMANTIC`
- A later activation would be at least `CONFIG_MATERIAL` + `SEMANTIC_ENGINE` and
  requires a separate implementation task after this decision is accepted.
- AI usage: AI-assisted, non-authoritative. The accepted ADR and human product
  decision are authoritative.

## 2. Problem Statement

Accumulation policy exposes settings named `sector_breadth`, and a pure applier
can add score points from `config/idx_groups.yaml`. Current production
composition roots do not pass `idx_groups` into `AccumulationScreenUseCase`, so
`_ticker_to_group` remains empty and the executable path skips the applier.

The configured mapping describes conglomerate/group membership rather than an
authoritative sector-universe index. Activating it without first defining its
concept, PIT membership, overlap behavior, scoring order, and Action interaction
would convert configuration intent and isolated unit tests into false production
authority. Leaving it indefinitely configured but unreachable also creates
product and maintenance ambiguity.

## 3. Desired Outcome

Produce one accepted, evidence-backed architecture decision. The selected
outcome is **RETIRE**; activation is rejected:

1. **RETIRE (selected)** — declare the configured group-breadth rule non-product and create
   a separate clean-removal task for dead configuration, DTO fields, pure
   applier wiring surfaces, snapshots' exclusion prose, and tests; or
2. **ACTIVATE (rejected)** — define the exact production policy contract and create a
   separate implementation task that wires every authorized production
   composition root, proves deterministic conformance, versions material
   identities, and only then enables producer snapshot/export work.

The decision record must use one truthful product name. It must not call
conglomerate membership "sector breadth" unless the chosen authority actually
uses a sector classification and sector membership source.

Observable outputs:

- accepted ADR or equivalent architecture decision record;
- complete current composition-root and consumer inventory;
- explicit RETIRE or ACTIVATE choice with rationale and rejected alternative;
- if ACTIVATE, a completed authority contract and version/blast-radius plan;
- one separate actionable implementation/removal backlog task;
- updates to the linked producer and ml-saham consumer tasks.

## 4. Non-Goals

- No runtime wiring of `idx_groups`.
- No change to Accum score, Signal, Risk, TradeSetup, Action, or live candidate
  ordering.
- No `production_policy_snapshot.v3`, eight-row closed set,
  `lean_accumulation_compatibility.v3`, migration 4, or dual write.
- No reinterpretation, mutation, or rebinding of historical observations or
  snapshots.
- No claim that `config/idx_groups.yaml` is a PIT sector-membership authority.
- No ml-saham adapter, tournament, challenger grid, or verdict implementation.
- No provider, scraper, network, AI model, UI, or database change.

## 5. Architecture Impact Assessment

This decision task is documentation/governance only.

```text
Layer plan:
- Domain: not touched
- Application: not touched
- Infrastructure: not touched
- Adapter: not touched
- Documentation/governance: architecture decision, inventories, and follow-up task
```

- New dependency: No
- Determinism affected: No in this task
- Persistence change: No
- Warm-up data: No in this task
- Adapter-owned orchestration/policy: No

An ACTIVATE follow-up must place policy and orchestration in domain/application
services and keep adapters thin. A RETIRE follow-up must be a scoped clean break,
not a compatibility alias or silently ignored duplicate field.

## 6. AI Usage Declaration

AI-assisted, non-authoritative. AI may inventory code paths and compare contract
options. It may not choose product semantics, establish external membership
authority, or approve activation. The accepted human-reviewed ADR is the gate.

## 7. Risk, Signal, And Evidence Authority Considerations

Potentially affected by a future ACTIVATE decision:

- Accum score and candidate ordering;
- downstream Signal assessment inputs and output;
- Risk/TradeSetup population because post-breadth ranking may change survivors;
- Action distribution and captured learning observations;
- lean compatibility identity and production snapshot closed set;
- ml-saham challenge adapter/protocol eligibility.

This task changes none of them. Diagnostic configuration and isolated applier
tests do not grant evidence or production authority.

## 8. Decision Contract To Lock

An ACTIVATE decision is incomplete unless every row below has an exact answer:

| Dimension | Required lock |
|---|---|
| Product concept and policy ID | Conglomerate-group breadth or sector breadth; final user-facing name; final stable policy ID |
| Membership authority | Named owner/source, exact group/sector key, revision, coverage, PIT availability, and missing state |
| Population | Which candidate set forms the denominator; when membership is resolved; treatment of filtered/non-observable names |
| Overlap | Whether a ticker may belong to multiple groups and the deterministic conflict/aggregation rule |
| Formula and units | Input field and unit; positivity rule; denominator; threshold comparison; bonus amount; rounding |
| Minimum support | Exact group-size threshold and behavior below it |
| Missing/provider error | Closed typed outcomes; no implicit empty group, zero breadth, or pass |
| Scoring order | Exact position relative to structural filters, signal assessment, candidate sort/truncation, Risk, and Action |
| Action interaction | Whether the bonus can change eligibility/Action indirectly and how that is captured in observations |
| Composition roots | Every CLI, scheduled, briefing, backtest, research capture/backfill, and alternate factory that must wire the same authority—or an explicit reason it is outside the policy |
| Identity/versioning | Config/semantic engine versions, observation compatibility material, snapshot version/closed set, adapter/conformance implications, and clean-break stance |
| Observability | Frozen payload fields, provenance, status/diagnostic surface, and exact distinction between unavailable and inactive |
| Verification | Pure tests, production-factory tests, mutation tests, replay goldens, producer-to-read-only-consumer round trip, and no-mutation proof |

For RETIRE, the ADR must instead inventory every field/config/test/doc/export
that carries the dead concept and define a clean-removal follow-up with no
silent alias or dual meaning.

## 9. Data And Persistence

This task reads code, YAML, ADRs, tests, and existing read-only corpus evidence.
It writes documentation only. No database or schema change is permitted.

An ACTIVATE follow-up may not be marked ready until it names the authoritative
membership source and proves its PIT meaning. Current YAML is configuration,
not historical membership authority.

## 10. Required Inventory

At minimum inspect and record:

- `AccumulationScreenUseCase` construction and apply order;
- `create_accumulation_screen_use_case` and every caller;
- direct `AccumulationScreenUseCase(...)` construction roots;
- `AccumulationSectorBreadthApplier` and DTO/config loaders;
- `config/idx_groups.yaml` ownership and semantic meaning;
- production policy snapshot payload exclusions and ADR-059;
- observation fingerprint/payload fields and compatibility construction;
- capture/backfill, cron, daily briefing, manual screen, backtest, and test-only
  compositions;
- all ai-saham and ml-saham consumers of the current fields or exclusion.

Do not infer coverage from one factory accepting an optional `idx_groups`
parameter. Verify which production callers actually supply it.

## 11. Acceptance Criteria

- [x] Current executable behavior is proven: production composition skips the
      applier when no group mapping is injected.
- [x] The mapping's current concept is identified objectively; conglomerate
      grouping and sector classification are not conflated.
- [ ] Every production and research composition root is inventoried.
- [x] RETIRE or ACTIVATE is explicitly selected and accepted by the product
      owner/maintainer.
- [x] The selected option has an accepted ADR with alternatives and trade-offs.
- [ ] ACTIVATE, if selected, completes every row in section 8 before
      implementation is authorized.
- [x] RETIRE, if selected, inventories every removal surface and historical
      artifact consequence.
- [x] A separate implementation/removal task is created; this decision task
      does not smuggle runtime work.
- [x] Linked ai-saham/ml-saham tasks are updated with the decision and task path.
- [x] No v3 snapshot, migration, production behavior change, DB write, identity
      inference, or historical reinterpretation occurs in this task.
- [x] `git diff --check` passes and every referenced local path exists.

## 12. Testing Expectations

No runtime code is changed. Validate references, inventory executable
composition roots, and run `git diff --check`. Focused runtime tests are evidence
for the decision but not required merely to create this task. Any later Python
implementation must satisfy the full Ruff and verification gates in
`AGENT_QUICKSTART.md`.

## 13. Documentation Impact

- New ADR or accepted architecture decision: required.
- Linked producer and ml-saham tasks: required.
- Snapshot/compatibility docs: update only after ACTIVATE is chosen and its
  implementation contract is approved.
- README/config/operator docs: handled by the later implementation/removal task.

## 14. Agent Execution Instructions

Before research, read `AGENT_QUICKSTART.md`, `AGENTS.md`, this task, ADR-059,
the accumulation composition/factory code, policy snapshot payloads, observation
compatibility contracts, focused tests, and both linked cross-repo tasks.

Stop if the selected option lacks a named authority owner, PIT semantics,
complete composition-root inventory, version/blast-radius decision, or accepted
product meaning. Do not treat a non-empty mapping or a passing unit test as
production authority.

## 15. Completion Record

```text
Decision date: 2026-08-02
Decision: RETIRE production score bonus; future diagnostic requires a new contract
ADR/decision record: docs/adr/ADR-062-retire-accum-group-breadth-production-bonus.md
Composition roots inventoried: screen/capture/backfill production non-wiring is guarded; removal task requires the final exhaustive inventory
Membership authority and PIT contract (ACTIVATE only): not applicable; no authority exists and activation is rejected
Identity/version blast radius: snapshot v2 and lean v2 unchanged by this decision; removal task must lock observation/config clean-break impact before code
Follow-up implementation/removal task: tasks/backlog/retire_accum_group_breadth_score_bonus.md
Linked task updates: ai-saham corpus task and ml-saham C3/roadmap/operator docs updated; seven-policy baseline retained with no breadth reconstruction
Commands and outcomes: focused non-wiring/snapshot guard 6 passed; cross-repo diff checks passed
Known limitations: runtime remnants intentionally remain until the separate clean-removal task passes its compatibility preflight
```
