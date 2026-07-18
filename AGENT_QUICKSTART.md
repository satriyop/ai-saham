# Agent Quickstart

Read this before every task. This is the mandatory entry point for agents. The longer governance docs remain binding when their task type applies.

## Non-Negotiables

- This is analysis software, not an automated trading bot.
- Deterministic-first and local-first behavior must be preserved.
- Domain code stays pure: no IO, providers, repositories, CLI, UI, browser, database, or AI calls.
- Application use cases own workflow, policy, orchestration, cache/fetch decisions, and business status calculation.
- Infrastructure implements ports for databases, providers, browser/API clients, filesystem, and AI integrations.
- Adapters stay thin: parse input, wire dependencies, call use cases, format output, and map errors.
- Use manual dependency injection. Application services/use cases receive ports, typed config objects, pure services, or narrow callables; they do not construct concrete SQLite, Stockbit, browser, filesystem, or YAML loader implementations.
- The deterministic rule/config engine is the canonical champion and must run
  independently of ML libraries, model artifacts, AI credentials, and network
  access.
- A narrowly scoped local ML model may become a typed evidence producer only
  after point-in-time, incremental out-of-sample validation and explicit
  evidence-authority promotion. Its immutable model and feature identities,
  missing-data behavior, drift monitoring, and rollback must remain governed.
- Full-decision ML models and remote AI/API agents may only produce separate,
  optional, non-authoritative challenger assessments. They must never become
  fallbacks, overrides, or hidden inputs to canonical scoring, risk,
  `TradeSetup`, sizing, execution, or observation selection.
- AI may assist authoring and explanations, but must not become the source of truth for scoring, risk, strategy, or persistence decisions.
- Do not confuse evidence-producer promotion with decision-challenger
  authority. Deterministic evidence and eligible narrow local-ML evidence may
  pass the validator-gated evidence lifecycle. Full ML/API decision outputs
  remain parallel shadow results unless a newer explicit ADR changes that rule.
- Do not bypass risk, signal, tuning, evidence-promotion, or architecture guardrails unless the user explicitly asks for an ADR/design change first.
- Do not promote diagnostic evidence or tune patch-eligible config without out-of-sample proof and validator support.
- Trust current code during audits. Treat docs as intent, then verify against implementation.
- Do not revert unrelated user or agent changes.
- Do not run destructive git cleanup in a shared dirty worktree. `git reset`, `git checkout --`, `git restore`, `git clean`, and broad stash/cleanup commands require explicit user approval and a stated file scope.

## Before Editing

1. Identify the task type.
2. Read the required docs from the matrix below.
3. State the layer plan.
4. State risks, ambiguities, and assumptions.
5. State persistence/config/CLI behavior impact if any.
6. Pick focused verification before changing files.
7. Check `git status --short` before edits or git operations, and treat unrelated dirty files as user/other-agent work.

## Semantic Change Classification

Before changing signal, setup, regime, risk, execution, evidence, observation,
or label behavior, classify the change explicitly in preflight. Use exactly one
or more of these categories:

- `CONFIG_MATERIAL`: a scoring/policy/config value can change canonical output;
  include its resolved path/value in the material config identity.
- `SEMANTIC_ENGINE`: deterministic calculation or decision behavior changes;
  bump the semantic engine/scoring contract version.
- `EVIDENCE_CONTRACT`: evidence meaning, availability, authority, or derivation
  changes; bump the evidence contract version.
- `OBSERVATION_SCHEMA`: persisted observation meaning or shape changes; bump the
  observation schema version and preserve old rows unchanged.
- `LABEL_POLICY`: execution, costs, stop/target, sizing, or label interpretation
  changes; bump the execution/label-policy version.
- `LABEL_SCHEMA`: persisted label meaning or shape changes; bump the label schema
  version and preserve old rows unchanged.
- `NON_SEMANTIC`: behavior and canonical outputs are unchanged; state why no
  compatibility identity changes.

Do not classify a material change as `NON_SEMANTIC` merely because tests still
pass. Do not hash the whole repository into semantic compatibility: the full
revision belongs in provenance, while explicit contract versions and resolved
material config belong in compatibility identity. Until canonical artifact
identity production is fully wired, do not claim changed rules/config are
comparable with earlier observations or labels.

### Signal Evidence Program Clean-Break Policy

Every task owned by `tasks/backlog/signal_evidence_program.md` is a clean-break
task. This program-wide rule supersedes compatibility, alias, dual-path,
fallback, translation, or active historical-normalization language in older
task drafts.

- Removed contracts, names, schemas, commands, config keys, and execution paths
  must be rejected by every new canonical producer and consumer. Do not retain
  an active alias, compatibility property, silent translation, fallback, or
  parallel old/new path.
- A schema/version bump creates a new canonical cohort. Older rows may remain
  byte-for-byte unchanged only in quarantine or raw audit storage; raw
  retention does not grant execution, labeling, attribution, readiness,
  tuning, promotion, or canonical-read authority.
- Do not rewrite old payloads to look as though they were produced under the
  new contract. Quarantine or rebuild them through the new canonical producer.
- Reject removed identities at all applicable typed-config, domain, producer,
  persistence, label, attribution, and promotion boundaries. Repository-only
  rejection is insufficient when application code consumes a repository port.
- Scope removals to the retired contract. A genuine active concept that happens
  to share a word with a removed identity remains active and must be protected
  by explicit regression tests.
- If clean break would destroy non-quarantined user data or an owning task truly
  requires a compatibility bridge, stop before editing and request an explicit
  program-contract change. Do not infer an exception.

For this policy, "preserve old rows unchanged" means preserve raw historical
truth only. It never means preserve active compatibility.

Layer plan format:

```md
Layer plan:
- Domain:
- Application:
- Infrastructure:
- Adapter:
```

If a layer is not touched, say `not touched`.

## Shared Worktree Safety

Agents often work in the same local checkout. Protect other work first:

- Before editing, committing, or any git operation, inspect `git status --short`.
- Never use broad cleanup commands to get a clean tree.
- Never run `git reset`, `git checkout --`, `git restore`, `git clean`, or equivalent destructive cleanup unless the user explicitly approves the exact operation and file scope.
- Do not stash the whole worktree when unrelated files are dirty. If stashing is needed, stash only files you own and state the path list first.
- Stage and commit only files touched for the current task.
- If your uncommitted work matters, commit it before handing off or before another agent starts risky work.
- If unrelated changes block the task, stop and report the conflict instead of overwriting them.

## Drafting Instructions For Other Agents

When drafting instructions for another agent, use a strict implementation
harness. Multi-agent prompts must reduce interpretation space, not merely
describe intent.

Required structure:

1. State the chosen decision.
   - Do not present multiple implementation options unless the task is
     explicitly a design discussion.
   - If one option is chosen, write "Implement this option only."
2. State forbidden interpretations.
   - Add a `Do Not Interpret This As` section.
   - Explicitly list shortcuts, compatibility behavior, or alternative readings
     that are not allowed.
   - For Signal Evidence Program tasks, state that clean break is mandatory and
     enumerate every old alias, fallback, translation, and canonical historical
     interpretation that must not survive.
3. Define exact contracts.
   - Name methods, DTOs, repository methods, config keys, CLI flags, and
     ownership boundaries when they are known.
   - Avoid vague phrases like "wire appropriately", "reuse if possible", or
     "handle as needed."
4. Include end-to-end invariants.
   - Say which downstream consumers must change too.
   - Do not only describe the local file change.
5. Require negative tests.
   - Tests must prove forbidden behavior cannot happen.
   - Existing tests that preserve old behavior must be updated, not worked
     around.
6. Define close criteria.
   - State what must be true before the task is considered done.
   - Include focused tests, full tests when feasible, and `git diff --check`.
7. Require pre-edit design confirmation for structural changes.
   - The agent must state how it will implement the contract before editing.
   - If the design violates any forbidden interpretation, stop before coding.
8. Resolve transport and ownership decisions before delegation.
   - State which type owns intermediate data, which function creates it, and
     how it reaches each consumer. Do not leave the implementer to choose
     between public DTO fields, wrapper results, workflow state, or side
     channels.
   - Constrain both the required result and the permitted path used to produce
     it. A correct-looking result produced through a forbidden second read,
     reconstructed provenance, adapter policy, or compatibility fallback is
     not acceptable.
9. Split foundational contracts from broad integration.
   - For cross-workflow changes, require a checkpoint after domain contracts,
     typed intermediate results, and negative contract tests pass. Do not let
     screen, swing, persistence, and CLI wiring proceed on an unreviewed
     foundation.
10. Name every production composition root.
   - List all factories, commands, cron paths, backfills, and alternate modes
     that must receive the new dependency or contract. Component tests do not
     prove production wiring.
11. Require independent tests, not implementation mirrors.
   - Tests must assert the intended invariant with real application boundaries
     or strict recording fakes. A component invoked twice is not cross-workflow
     parity, and a test must not be named "unchanged" while asserting changed
     behavior.
   - Include adversarial counterexamples for identity, provenance, cutoff,
     missing-data, and forbidden fallback behavior where relevant.
12. Define missing and failure states exactly.
   - State whether absence is represented by `None`, an empty collection, a
     typed `UNKNOWN` result, an exception, or omission. Do not leave this choice
     to the implementer, especially when it can alter scoring or authority.
13. Enforce one source of truth for transported data.
   - Do not permit both a derived object and a second independently mutable copy
     of its source/result to travel through workflow state. Name the one owning
     DTO or result type and require downstream access through it.
   - If exact consumed rows, provenance, identity, or cutoff state matters,
     explicitly forbid re-querying, reconstructing, or substituting
     value-equivalent rows. State the complete producer-to-consumer chain.
14. Define the exception boundary, not only the missing-data behavior.
   - Distinguish expected provider/data absence from contract, invariant, and
     programmer errors. State exactly which exception types become typed
     unavailable results or warnings and which must propagate and fail closed.
   - Broad best-effort handling must not convert malformed canonical objects,
     mismatched provenance, or impossible state into ordinary missing evidence.
15. Test lineage and call behavior independently from computed values.
   - When a task requires exact inputs, tests must assert repository read count,
     transported row identity/keys, and absence of forbidden second reads. Two
     queries returning equal values do not prove shared provenance.
   - When a typed wrapper binds values together, tests must prove downstream
     code preserves the wrapper until the named boundary instead of extracting
     one field early and silently discarding the rest.

Use a `Do Not Interpret This As` section for high-risk work. Example:

```md
Do Not Interpret This As:
- Do not make ordinary diagnostic commands write canonical learning data.
- Do not expose private services through public properties to avoid wiring.
- Do not preserve old behavior tests when the task explicitly changes the contract.
- Do not update only the producer; update downstream consumers that rely on the contract.
```

## Delegated Task Implementation

When implementing a task from another agent's instruction, treat the
instruction as a contract, not a suggestion. Directionally correct is not done
if the explicit contract is incomplete.

Before coding, restate:

1. Hard invariants.
   - Behaviors that must be true after implementation.
   - Example: if projection is required to own all filtering, old workflow or
     adapter paths must not keep part of that filtering.
2. Forbidden interpretations.
   - Things that may seem acceptable but are not allowed.
   - Example: "fail explicitly" means a non-zero failure, not warning and
     continue.
3. Exact file boundary.
   - List files expected to change.
   - Any unrelated file change must be reported before continuing.
4. Exact output contract.
   - Name required JSON keys, CLI exit behavior, error messages, DTO fields,
     repository identity keys, or config paths.
   - If an output field is required, add a test asserting it exists.
5. Negative tests.
   - Prove invalid or unsupported paths fail.
   - Do not test only the happy path.
6. Existing behavior preservation.
   - When moving logic across layers, preserve the current predicate exactly
     unless the task explicitly changes it.
7. Stop condition.
   - If the instruction is ambiguous or conflicts with current code, stop and
     ask instead of implementing a weaker interpretation.

Before marking done:

- [ ] The exact requested behavior is implemented, not only the general shape.
- [ ] No unrelated files were touched.
- [ ] Required output fields and error paths are covered by tests.
- [ ] Unsupported combinations fail if the task says they must fail.
- [ ] No old code path still performs logic that was supposed to move layers.
- [ ] Grep confirms the old forbidden behavior is gone.
- [ ] Focused tests and `git diff --check` pass.

## Manual Dependency Injection

This repository uses explicit manual DI, not a DI framework:

- Domain objects are constructed normally, but never receive infrastructure dependencies.
- Application use cases/services receive dependencies through constructors or request objects.
- Stable cross-boundary dependencies should be ports/protocols or typed policy/config objects.
- Narrow callables are acceptable for small adapter-bound seams when a full port would be ceremony.
- Concrete provider/repository/config-loader construction belongs in infrastructure composition roots or thin CLI workflow factories.
- `src/application/*factory*.py` and `src/application/*bootstrap*.py` files are compatibility/pure assembly helpers only; they must not become concrete infrastructure composition roots.
- Adapters may instantiate infrastructure only as wiring. If an adapter decides freshness, retry, scoring, setup, risk, or persistence policy, move that logic into an application use case.

## Required Reading Matrix

Always read:

- `AGENT_QUICKSTART.md`
- Your agent-specific contract if present, such as `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, or `CURSOR.md`

For code changes, also read:

- `DEFINITION_OF_DONE.md`
- Relevant sections of `PROMPT_CONTRACT.md`
- Relevant sections of `AI_AGENT_CHECKLIST.md`

For architecture, layer boundary, persistence, scoring, signal, risk, tuning, strategy, market context, or evidence-promotion work, also read:

- `ARCHITECTURE_DECISIONS.md`, then only the individual ADRs selected by its
  task-to-ADR reading matrix
- Relevant design docs under `docs/`
- Relevant config files under `config/`

For user-facing CLI/output/workflow changes, also read:

- Relevant `README.md` sections
- Relevant CLI docs such as `CLI_README.md`, if touched

For task scoping, ambiguous requirements, or handoff tasks, also read:

- `TASK_TEMPLATE.md`

For documentation-only edits:

- Read the docs being edited.
- Read source docs they reference.
- Read implementation files only when the doc makes code claims.

## Verification Defaults

- Documentation-only: run `git diff --check`; run tests only if examples/contracts changed.
- Small localized code change: run focused tests for touched behavior and `git diff --check`.
- Shared scoring/risk/signal/tuning/persistence/config change: run focused tests, architecture boundary tests, and the full test suite unless explicitly deferred.
- CLI/output change: run command contract or display tests, and manually inspect representative output when practical.
- Data ingestion, persistence, source mapping, observations, labels, replay,
  readiness, tuning, market-context evidence, or data-safety claims: apply the
  Data Contract Audit Gate in `AI_AGENT_CHECKLIST.md` and report relevant
  `saham audit data ...` findings.

If verification is skipped or impossible, say exactly why.
