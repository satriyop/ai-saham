# Parked — TUI Agent Phase 4 Audit Persistence

Status: `PARKED` / requires a dedicated persistence ADR

Activation trigger: Phase 3 is complete and the user explicitly approves a new
ADR defining audit purpose, schema, retention, deletion, export, redaction,
read-only inspection, migration, and failure behavior.

Source:

- `docs/roadmap/roadmap_tui_ai_agent_implementation.md`, Phase 4

## 1. Task Metadata

- Task type: Feature / persistence
- Priority: Low until Phases 1–3 demonstrate operational need
- Semantic classification: `NON_SEMANTIC` only if audit storage remains fully
  separate from canonical analysis, learning artifacts, preferences, and
  evidence authority.
- AI usage: stores redacted audit metadata about optional agent turns; does not
  grant model authority.
- Chosen decision: no persistence implementation until a dedicated ADR closes
  every data lifecycle decision. Implement this option only after activation.

## 2. Problem Statement

Ephemeral sessions provide no durable trace for debugging provider behavior,
tool permissions, cost, latency, or disputed answers. Persisting raw chat and
tool payloads without a purpose and lifecycle contract would create unnecessary
sensitive data, unclear deletion obligations, schema drift, and a new path that
could be mistaken for learning or decision authority.

## 3. Desired Outcome

After explicit activation, a local audit store records the minimum normalized,
redacted metadata needed to reconstruct what the agent requested and what
deterministic results it referenced. It supports read-only inspection, bounded
retention, explicit deletion/export, and versioned migrations.

Audit rows never become conversation memory, training material, corpus,
production evidence, preferences, or a canonical decision input.

## 4. Non-Goals

- No raw secret, API key, authorization header, provider client, or unrestricted
  request/response payload storage.
- No automatic use of audit history as future prompt context.
- No model training, evaluation cohort, observation, label, tuning, or evidence
  promotion from audit rows.
- No cloud synchronization or telemetry export.
- No config, preference, journal, watchlist, or trade persistence.
- No write tool authorization; Phase 5 is separate.

## 5. Hard Invariants

1. Application owns the audit record and repository port; SQLite is an
   infrastructure implementation.
2. Audit writes occur only after the turn reaches a defined terminal state and
   never change the turn result.
3. Audit-write failure is visible diagnostically but cannot suppress or replace
   deterministic cockpit results.
4. Stored context uses references/digests and an approved redacted projection,
   never unrestricted candidate/tool/provider objects.
5. Retention and deletion are deterministic application workflows, not ad hoc
   SQL or UI cleanup.
6. Read-only inspection is transitively read-only: no schema ensure, migration,
   repair, directory creation, or persistent PRAGMA.
7. Audit schema/version is independent from learning schema and compatibility
   identity.
8. Missing database/table is a typed empty/unavailable audit state and does not
   create storage during inspection.

## 6. Architecture Impact Assessment

```md
Layer plan:
- Domain: not touched
- Application: audit DTO/repository port, write/inspect/delete/export/retention use cases
- Infrastructure: versioned SQLite audit repository and migrations
- Adapter: explicit audit status and management surfaces only
```

- New dependency: No by default.
- Persistence affected: Yes; exact file/table ownership requires the ADR.
- CLI/TUI behavior affected: new explicit audit inspection/management surfaces
  only after approval.
- Deterministic analysis affected: No.

## 7. Mandatory ADR Decisions Before Activation

The persistence ADR must lock, with no placeholders:

- audit purpose and data controller/owner;
- database/file ownership and whether it shares `data.db`;
- table names, columns, keys, schema version, migration order, and indexes;
- exact persisted fields and redaction transform;
- treatment of user question and model answer: omitted, hashed, redacted, or
  stored with explicit rationale;
- retention duration/count, pruning trigger, deletion and export contracts;
- write transaction and failure/partial behavior;
- read-only connection mode and missing-store semantics;
- concurrency, corruption, backup, and migration rollback behavior;
- operator copy and disclosure.

Until these decisions are accepted, this task remains parked.

## 8. Minimum Audit Record Categories

The ADR may reduce this set for privacy, but may not add unrestricted payloads:

- audit/turn/session identifiers and timestamps;
- provider/model/prompt/tool-schema identities;
- requested/approved/denied/executed tool names and normalized safe arguments;
- deterministic result references/digests, subject, as-of, and status;
- terminal turn status, normalized failure category, latency, and token usage;
- redaction/version metadata;
- explicit record of any absent/omitted sensitive field.

## 9. Negative and Data-Safety Tests

- Secrets and authorization values cannot survive serialization/redaction.
- Audit rows are never read by agent context, canonical engines, corpus, labels,
  tuning, or promotion.
- Read-only inspection of a nonexistent path creates nothing.
- Read-only inspection performs no migration/repair/write.
- Failed audit write leaves the completed turn and deterministic UI intact.
- Retention deletes only exact eligible audit rows.
- Deletion/export uses explicit scope and stable ordering.
- Corrupt/mismatched schema fails closed with no silent rebuild.
- Migration round trips preserve approved fields and reject unsupported versions.

## 10. Acceptance Criteria

- [ ] Dedicated persistence ADR accepted and reflected in this task.
- [ ] Exact schema, lifecycle, redaction, and read-only contracts implemented.
- [ ] No audit data gains analysis, memory, learning, or authority semantics.
- [ ] Transitive read-only and nonexistent-path behavior are proven.
- [ ] Privacy/adversarial/migration/failure tests pass.
- [ ] Focused tests, architecture tests, full suite, Ruff gates, data audits where
      applicable, and `git diff --check` pass.

## 11. Do Not Interpret This As

- Do not create a chat-history table before the ADR.
- Do not reuse learning-artifact repositories or schema.
- Do not persist raw prompts/responses “temporarily.”
- Do not make audit success a prerequisite for deterministic operation.
- Do not start Phase 5 write tools under an audit-storage task.

## 12. Completion Record

- Persistence ADR:
- Completed date:
- Commit(s):
- Schema/migration:
- Retention/redaction proof:
- Verification:

