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
- Do not run destructive git cleanup in a shared dirty worktree. `git reset`, `git checkout --`, `git restore`, `git clean`, and broad stash/cleanup commands require explicit user approval and a stated file scope.

## Before Editing

1. Identify the task type.
2. Read the required docs from the matrix below.
3. State the layer plan.
4. State risks, ambiguities, and assumptions.
5. State persistence/config/CLI behavior impact if any.
6. Pick focused verification before changing files.
7. Check `git status --short` before edits or git operations, and treat unrelated dirty files as user/other-agent work.

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
