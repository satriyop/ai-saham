# Parked — TUI Agent Phase 3 Ephemeral Sessions and Hardening

Status: `PARKED`

Activation trigger: Phases 1 and 2 are complete, their final contracts are
re-vetted against current code, and an ADR amendment locks session identity,
reference invalidation, context budgeting, and provider capability rules.

Source:

- ADR-060
- `docs/roadmap/roadmap_tui_ai_agent_implementation.md`, Phase 3

## 1. Task Metadata

- Task type: Feature / hardening
- Priority: Medium after Phase 2
- Semantic classification: `NON_SEMANTIC` — session state may influence only
  agent commentary/context retrieval, never deterministic analysis or persisted
  market/learning state.
- AI usage: optional multi-turn commentary over exact result references.
- Chosen decision: add bounded in-memory sessions only. Implement this option
  only.

## 2. Problem Statement

Independent one-turn requests cannot safely answer follow-up questions without
resending context. Naively retaining chat history risks binding old facts to a
new ticker, summarizing away authoritative fields, exceeding model context, or
painting a late answer into the wrong cockpit stage.

## 3. Desired Outcome

During one `saham tui` process, an operator may ask bounded follow-up questions.
The application session retains typed turn metadata and exact result references,
while old conversational prose may be summarized under deterministic budgets.

Session state disappears when the process exits. No transcript, preference,
tool result, or provider response is written to disk or SQLite.

## 4. Non-Goals

- No durable conversation or audit persistence.
- No cross-device/user synchronization.
- No autonomous preference inference or storage.
- No background/proactive agent, scheduler, notification, or wake-up behavior.
- No new read/write tools.
- No provider fallback or authority change.
- No model-authored summary replacing exact Action/freshness/provenance fields.

## 5. Hard Invariants

1. Session identity, turn ordering, budgets, invalidation, and stop rules are
   application policy, not Textual widget state.
2. Every referenced result retains subject, as-of, status, schema, provenance,
   and context digest. A ticker string alone is never sufficient identity.
3. Focus/result changes mark incompatible references stale before another turn.
4. Authoritative fields are stored/reintroduced exactly; they are never sourced
   from an LLM summary.
5. Older conversation may be summarized only as commentary. Pending failures,
   warnings, permissions, and exact result references are preserved structurally.
6. Cancellation/newer generation/navigation prevents late delivery even when
   ticker text matches.
7. Session eviction and context overflow fail visibly; no silent truncation.
8. AI-disabled deterministic operation has no session dependency.

## 6. Architecture Impact Assessment

```md
Layer plan:
- Domain: not touched
- Application: session DTOs/port, in-memory implementation contract, budgeting, invalidation, compression policy
- Infrastructure: provider capability metadata only; no persistence
- Adapter: session ID lifecycle, transcript navigation/rendering, cancellation signals
```

- New dependency: No by default.
- Persistence affected: No.
- CLI behavior affected: No.
- Deterministic authority affected: No.

## 7. Activation Checklist

- [ ] Phase 2 closed with exact tool/result-reference contracts.
- [ ] New/amending ADR defines session ID, turn ID, maximum turns, token/context
      budgets, eviction, stale-reference behavior, and compression boundary.
- [ ] Provider/model capability certification identity is locked to exact model,
      system-prompt version, tool-schema version, evaluation-suite version, and
      certification date/result.
- [ ] TUI designs cover follow-up, stale context, cancellation, overflow, and
      session reset at `80x24` and `120x40`.
- [ ] No persistent store is constructed anywhere in the session path.

## 8. Required Contracts Before Implementation

The activated task must specify immutable equivalents of:

- `AgentSessionId`, `AgentTurnId`, and monotonic turn sequence;
- `AgentSessionState` containing typed references and bounded commentary
  history, not unrestricted raw provider objects;
- compatibility predicate for current cockpit context vs prior references;
- exact P0–P4 context priorities and per-class budgets;
- summary input/output schema and fields forbidden from summarization;
- reset, cancel, evict, overflow, and unavailable statuses;
- capability certification record and behavior for uncertified models.

Recommended initial limits must be resolved in the activation ADR rather than
left to implementation judgment.

## 9. Negative Tests

- A response for an older generation cannot paint after focus/navigation/reset.
- Same ticker with a different context digest/as-of cannot reuse stale facts.
- Different ticker cannot inherit candidate facts or tool results.
- Summarization cannot change Action, scores, dates, warnings, freshness, or
  provenance.
- Overflow cannot silently drop P0/P1 facts.
- Uncertified model cannot gain tool capability.
- Process restart has no prior session rows/files/directories.
- Session state never feeds canonical workflows or persistence.

## 10. Acceptance Criteria

- [ ] Follow-ups work within one process using exact compatible references.
- [ ] Stale, cancelled, overflow, evicted, and reset states are explicit.
- [ ] Context compression preserves authority-bearing fields byte-for-byte in
      their typed representation.
- [ ] No persistent side effect occurs.
- [ ] Provider capability is identity-bound and does not grant authority.
- [ ] Offline/AI-disabled cockpit behavior is unchanged.
- [ ] Focused, interaction, adversarial, architecture, TUI, full-suite, Ruff,
      and `git diff --check` gates pass.

## 11. Do Not Interpret This As

- Do not add SQLite “just for convenience.”
- Do not treat an LLM-generated summary as session truth.
- Do not keep unlimited raw history in memory.
- Do not add proactive/background operation.
- Do not begin audit persistence from this task.

## 12. Completion Record

- Activation ADR:
- Completed date:
- Commit(s):
- Verification:

