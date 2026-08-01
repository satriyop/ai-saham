# Parked Epic — TUI Agent Phase 5 Consequential Tools

Status: `PARKED EPIC` / no write authority granted

Activation trigger: Phases 1–4 are complete, the user explicitly selects one
consequential business capability, and a new ADR plus a dedicated Task Template
contract authorize that one tool's approval, idempotency, audit, recovery, and
failure semantics.

Source:

- `docs/roadmap/roadmap_tui_ai_agent_implementation.md`, Phase 5

## 1. Task Metadata

- Task type: Epic / future architecture
- Priority: Low; activate by demonstrated operator value, not roadmap order
- Semantic classification: must be decided per tool. A write is not automatically
  `NON_SEMANTIC` merely because AI only requested it.
- AI usage: the model may propose a consequential operation; deterministic
  policy and explicit user approval are the only authorization.
- Chosen decision: activate and implement one narrowly scoped tool at a time.
  Implement this option only.

## 2. Problem Statement

Read-only assistance cannot perform requested operational steps such as an
explicit cache refresh or paper-journal entry. Exposing broad writes would let
probabilistic output affect durable state, repeat uncertain operations, bypass
existing validators, or confuse a proposal with approval.

## 3. Desired Outcome

For one separately approved capability, the model may propose a typed operation.
The application validates it, displays an exact consequence/diff, obtains an
explicit scoped confirmation, executes the existing application use case with
an idempotency key, and records a terminal result. The model cannot approve,
expand, repeat, or conceal the operation.

Potential capability families, each requiring its own ADR/task:

| Family | Earliest permissible shape |
|---|---|
| Cache refresh | Exact providers/scope/writes preview, then explicit confirmation |
| Paper journal | Exact ticker/plan/outcome fields and idempotent local write |
| Watchlist | Exact named list and item diff |
| Durable presentation/workflow preference | Typed key/value/scope/expiry diff |
| Config/tuning proposal | Proposal artifact only through existing validators; application remains separately human-controlled |

Broker order placement, automated trading, guardrail bypass, arbitrary config
mutation, shell, SQL, filesystem, browser, and unrestricted network tools are
forbidden and are not activation candidates under this epic.

## 4. Non-Goals

- No blanket “operations mode” permission.
- No session-wide permanent write authority.
- No model self-approval or approval inferred from conversational tone.
- No generic write/command tool.
- No automatic retry after a timeout or unknown completion state.
- No direct repository/provider calls from TUI or model.
- No automated trading, order placement, sizing override, or Action override.
- No tuning/config/evidence promotion without existing deterministic validators
  and their separate explicit human-controlled application workflow.

## 5. Hard Invariants

1. Every tool is absent until its own ADR/task is accepted and registered in a
   closed application allowlist.
2. The model proposes; deterministic policy validates; the user approves; the
   existing application use case executes.
3. Approval binds exact normalized arguments, scope, side effects, expiry, and
   idempotency key. Any change invalidates approval.
4. `UNKNOWN_COMPLETION_STATE` fails closed and is never retried automatically.
5. Denial, cancellation, timeout, malformed output, or audit failure cannot be
   interpreted as approval.
6. Provider/model fallback cannot occur during an approval/execution sequence.
7. Tool output cannot modify canonical scoring, risk, TradeSetup, evidence
   authority, or promotion rules.
8. TUI confirmation is presentation only; approval and execution state machine
   live in application.

## 6. Architecture Impact Assessment

```md
Layer plan:
- Domain: only if the selected existing business capability already owns a pure domain contract
- Application: proposal validation, permission/approval state machine, idempotency, orchestration, terminal status
- Infrastructure: existing concrete write adapter plus approved audit/idempotency persistence
- Adapter: exact preview/confirm/deny/cancel/result presentation only
```

- New dependency: decide per tool.
- Persistence: Yes for any durable action, approval/audit, or idempotency record.
- Determinism: execution and authorization must be deterministic; AI remains
  non-authoritative.
- CLI impact: shared use case only; no CLI command execution.

## 7. Per-Tool Activation Contract

Before creating runtime code, the selected tool task must lock:

- exact business name, input/output DTOs, and existing use case;
- complete side-effect inventory: provider calls, tables/files, rows, config,
  cache invalidation, and external effects;
- preview source and exact user-visible diff;
- permission level, approval wording, scope, expiry, and cancellation;
- idempotency-key formula, uniqueness owner, transaction boundary, and replay;
- timeout-before-write, timeout-during-write, partial, rollback, and
  `UNKNOWN_COMPLETION_STATE` semantics;
- retry matrix and operations that are never retryable;
- audit record and recovery/inspection path;
- all production composition roots;
- negative tests proving model/adapter cannot self-authorize.

No unresolved field may be delegated to implementer judgment.

## 8. Required State Machine

Every activated tool must use an application-owned equivalent of:

```text
PROPOSED
  -> VALIDATED
  -> AWAITING_APPROVAL
  -> DENIED | CANCELLED | APPROVED
  -> EXECUTING
  -> SUCCEEDED | FAILED | PARTIAL | UNKNOWN_COMPLETION_STATE
```

Transitions are closed and independently tested. Provider prose cannot create a
transition. `APPROVED` binds the exact immutable proposal digest.

## 9. Negative Tests

- Model cannot approve its own proposal or alter an approved payload.
- Replayed/expired/cross-session approval is rejected.
- Duplicate execution with the same idempotency key cannot duplicate effects.
- Different payload with the same key is rejected.
- Unknown completion is not retried through the same or another provider.
- Adapter bypass of application approval state is impossible.
- Broad SQL/shell/filesystem/network arguments are schema-impossible.
- Failure cannot be presented as success or hidden by model commentary.
- Config/tuning proposal cannot apply itself or bypass validators.
- No tool can place an order or override canonical Action/sizing/risk.

## 10. Acceptance Criteria

- [ ] One exact tool ADR and implementation task are explicitly approved.
- [ ] Authority, side effects, approval, idempotency, audit, and recovery are
      fully specified before code.
- [ ] State transitions and negative authorization tests are exhaustive.
- [ ] Existing application use case remains the single workflow authority.
- [ ] Unknown/partial/failure behavior is visible and fail-closed.
- [ ] No forbidden generic or trading capability is introduced.
- [ ] Focused, persistence, adversarial, architecture, TUI, full-suite, Ruff,
      and `git diff --check` gates pass for each activated tool.

## 11. Do Not Interpret This As

- Do not implement all potential families as one task.
- Do not expose existing CLI commands as tools.
- Do not equate a user saying “yes” earlier in conversation with bound approval.
- Do not omit idempotency because a write is “local only.”
- Do not make audit persistence itself grant write permission.
- Do not treat this parked epic as authority to write runtime code.

## 12. Completion Record

- Activated tool ADR/tasks:
- Completed capability families:
- Explicitly rejected/deferred families:
- Verification:

