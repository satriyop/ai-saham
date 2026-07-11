# Agent Quickstart

Read this before every task. This is the mandatory entry point for agents. The longer governance docs remain binding when their task type applies.

## Non-Negotiables

- This is analysis software, not an automated trading bot.
- Deterministic-first and local-first behavior must be preserved.
- Domain code stays pure: no IO, providers, repositories, CLI, UI, browser, database, or AI calls.
- Application use cases own workflow, policy, orchestration, cache/fetch decisions, and business status calculation.
- Infrastructure implements ports for databases, providers, browser/API clients, filesystem, and AI integrations.
- Adapters stay thin: parse input, wire dependencies, call use cases, format output, and map errors.
- AI may assist authoring and explanations, but must not become the source of truth for scoring, risk, strategy, or persistence decisions.
- Do not bypass risk, signal, tuning, evidence-promotion, or architecture guardrails unless the user explicitly asks for an ADR/design change first.
- Do not promote diagnostic evidence or tune patch-eligible config without out-of-sample proof and validator support.
- Trust current code during audits. Treat docs as intent, then verify against implementation.
- Do not revert unrelated user or agent changes.

## Before Editing

1. Identify the task type.
2. Read the required docs from the matrix below.
3. State the layer plan.
4. State risks, ambiguities, and assumptions.
5. State persistence/config/CLI behavior impact if any.
6. Pick focused verification before changing files.

Layer plan format:

```md
Layer plan:
- Domain:
- Application:
- Infrastructure:
- Adapter:
```

If a layer is not touched, say `not touched`.

## Required Reading Matrix

Always read:

- `AGENT_QUICKSTART.md`
- Your agent-specific contract if present, such as `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, or `CURSOR.md`

For code changes, also read:

- `DEFINITION_OF_DONE.md`
- Relevant sections of `PROMPT_CONTRACT.md`
- Relevant sections of `AI_AGENT_CHECKLIST.md`

For architecture, layer boundary, persistence, scoring, signal, risk, tuning, strategy, market context, or evidence-promotion work, also read:

- `ARCHITECTURE_DECISIONS.md`
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

If verification is skipped or impossible, say exactly why.
