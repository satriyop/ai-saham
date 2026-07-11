You are an AI development agent working on this repository.

Before every task:

1. Read and follow `AGENT_QUICKSTART.md`.
2. Read this `AGENTS.md`.
3. Use the reading matrix in `AGENT_QUICKSTART.md` to decide which longer docs are required for the task.

Do not default to reading every governance document for every small task. Escalate to the full docs when the task type requires it.

Always confirm explicitly:

- You understand the system architecture and layer boundaries.
- You will follow deterministic-first principles.
- You will not bypass guardrails unless explicitly instructed.
- You will ask for clarification if a task violates the Task Template or is architecturally unsafe.
- You will keep adapters thin and put workflow/policy in application use cases.
- You will protect shared worktree changes and will not run destructive git cleanup without explicit approval and file scope.

Before coding, state:

- Risks, ambiguities, or missing information you detect.
- Assumptions you must make, if unavoidable.
- The implementation layer plan:

  ```md
  Layer plan:
  - Domain:
  - Application:
  - Infrastructure:
  - Adapter:
  ```

For documentation-only tasks, the layer plan may state all product layers as `not touched` and add `Documentation/governance` separately.

Proceed with implementation only after the preflight is clear and the user has requested implementation or the task is explicitly actionable.
