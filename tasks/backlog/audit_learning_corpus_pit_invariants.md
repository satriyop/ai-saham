# Audit — Learning Corpus PIT Invariants In `reconcile-sources`

Status: `READY`

Source: look-ahead audit 2026-07-31. Companion to
`tasks/backlog/fix_risk_pit_cutoff_lookahead.md` — that task fixes the engine;
this one closes the hole that let the defect stay invisible.

## Task Metadata

- Task type: Feature (audit coverage)
- Priority: Medium. Must not block the engine fix.
- Semantic classification: `NON_SEMANTIC` — read-only audit findings only. No
  scoring, risk, evidence, observation, or label behavior changes; no persisted
  artifact changes; no contract-version bumps.
- Chosen decision: add **one** evaluator covering point-in-time coherence of
  persisted accumulation observations to the existing
  `saham audit data reconcile-sources` command. **Implement this option only.**

## Problem Statement

`AI_AGENT_CHECKLIST.md` (Data Contract Audit Gate) requires agents to run
`manifest`, `source-contracts`, and `reconcile-sources` before claiming that
affected data is point-in-time or replay safe. None of those three can observe a
PIT defect inside `learning_observations`:

| Command | Coverage of `learning_observations` |
|---|---|
| `manifest` | row counts, `cutoff_at` min/max, duplicate `(observation_id, artifact_digest)` |
| `source-contracts` | minimal field set only (`observation_id`, `artifact_digest`, `schema_version`, `captured_at`, FK refs) |
| `reconcile-sources` | **table absent entirely** — 16 hardcoded evaluators, none for `learning_observations` |

The 2026-07-31 audit found 1,755 of 1,890 accumulation observations whose 7-day
`risk.snapshot_date` was later than the observation session, undetected for the
corpus's entire life and found only by manual inspection. An agent could have
run the full mandated gate, received a clean result, and truthfully reported
"PIT-safe". That is a gate that cannot see the defect class it exists to catch.

Note the older `candidate_observations` table *did* have an identity evaluator
(`evaluate_candidate_observations_identity`). Coverage was lost, not never
built, when the corpus moved to `learning_observations` under ADR-056.

## Desired Outcome

- `saham audit data reconcile-sources` reports a finding when any accumulation
  observation carries a risk snapshot dated after its own session.
- The finding names the affected count and a bounded sample of
  `(ticker, session_date, risk_snapshot_date)` so an operator can act.
- A clean corpus produces no new findings and no change in exit status.
- Running the mandated Data Contract Audit Gate is once again sufficient to
  support a point-in-time claim about the accumulation corpus.

## Non-Goals

- No generic look-ahead detection framework, rule DSL, or pluggable check
  registry. One evaluator, following the existing pattern.
- No static or runtime analysis of engine code paths. This inspects **persisted
  rows only**.
- No new CLI command, no new command group, no new flags.
- No mutation, repair, quarantine, or purge. `reconcile-sources` is read-only
  and stays read-only.
- No checks for pre-open or swing observations. Accumulation only.
- No coverage of ownership `fetched_at`; that was audited and is correct
  (`COALESCE(report_date, fetched_date) <= as_of`) — flagging it would produce
  854 false positives.
- No change to `AI_AGENT_CHECKLIST.md` required commands (the three already
  listed stay the same; this task only makes the third one see more).

## Hard Invariants

1. Read-only. No writes, no schema changes, no migrations.
2. Additive to `reconcile-sources` output. Existing checks, codes, severities,
   and exit behavior are unchanged.
3. Absent or malformed data is reported, never guessed. Missing risk block,
   missing dates, or unparseable payload must not raise and must not be silently
   counted as passing.
4. The check reads persisted rows only. It must not import or invoke risk,
   signal, or screen engines.
5. A clean corpus yields zero new findings.

## Architecture Impact

- New dependency: No
- Affects determinism: No
- Persistence schema change: No
- Orchestration/policy in an adapter: No

```md
Layer plan:
- Domain: not touched
- Application: one new evaluator function in the source-reconciliation
  evaluator family, registered in AuditSourceReconciliationUseCase
- Infrastructure: one reader method returning the raw counts/samples from
  learning_observations
- Adapter: not touched (no new command, no new flags)
```

## Exact Contract

### Reader (infrastructure)

Extend the existing source-reconciliation reader used by
`AuditSourceReconciliationUseCase` with a method that returns, for
`purpose = 'ACCUMULATION_DISCOVERY'`:

- total observation count
- count where the canonical-window risk snapshot date is later than the session
- count where the risk block is present but the date is missing or unparseable
- count where `risk.gate_context.snapshot_date` disagrees with the session
- a bounded sample (cap at 10) of `(ticker, session_date, risk_snapshot_date)`

Payload shape, verified 2026-07-31:

- session date: top-level `session_date`; the ticker is top-level `ticker`
- canonical window: top-level `canonical_window` (currently `7`); the risk block
  lives at `features_by_window["<canonical_window>"]["risk"]`
- risk dates: `risk["snapshot_date"]` and
  `risk["gate_context"]["snapshot_date"]`

Resolve the window via `canonical_window` and fall back to `"7"` only if that
key is absent. Do not hardcode `"7"` as the primary lookup.

### Evaluator (application)

One function in the artifact evaluator family, mirroring the shape of
`evaluate_candidate_observations_identity` in
`src/application/services/source_reconciliation_artifact_evaluator.py`.

| Condition | Severity | Code |
|---|---|---|
| risk snapshot date later than session | `FAIL` | `LEARNING_OBSERVATIONS_RISK_SNAPSHOT_AFTER_SESSION` |
| `gate_context.snapshot_date` disagrees with session | `WARN` | `LEARNING_OBSERVATIONS_GATE_CONTEXT_SESSION_MISMATCH` |
| risk block present but dates missing/unparseable | `WARN` | `LEARNING_OBSERVATIONS_RISK_SNAPSHOT_UNREADABLE` |

`FAIL` is correct for the first condition: it is exactly the state that makes a
point-in-time claim false, and the Data Contract Audit Gate is defined to block
PIT/replay/readiness/tuning claims on FAIL.

Register it in the hardcoded evaluator tuple in
`AuditSourceReconciliationUseCase` (currently 16 entries). Keep the existing
ordering; append.

## Sequencing

Land after `fix_risk_pit_cutoff_lookahead.md` has been merged, purged, and
re-captured. Running this check against today's database would report a FAIL on
1,755 rows that are already scheduled for deletion, which is noise rather than
signal.

If it does land first, do not soften the severity or add an allowlist to keep
the gate green — record the known-failing state in the task and proceed.

## Required Reading

- `AGENT_QUICKSTART.md`, `AGENTS.md` / `CLAUDE.md`, `TASK_TEMPLATE.md`
- `AI_AGENT_CHECKLIST.md` → Data Contract Audit Gate
- `src/application/use_case/audit_source_reconciliation_use_case.py`
- `src/application/services/source_reconciliation_artifact_evaluator.py`
  (copy the `evaluate_candidate_observations_identity` shape)
- `docs/adr/ADR-056-accum-corpus-session-observation-and-accum-path-labels.md`
  for the payload contract
- `tasks/backlog/fix_risk_pit_cutoff_lookahead.md` for the measured defect

## Implementation Checklist

- [ ] Add the reader method; no writes.
- [ ] Add the evaluator with the three codes above.
- [ ] Register it in the evaluator tuple.
- [ ] Tests below.
- [ ] `saham audit data reconcile-sources --format json --db data/db/data.db`
      against the clean corpus; expect no new findings.
- [ ] Lint Gate: `ruff check src/ tests/` and `ruff format --check src/ tests/`.
- [ ] `git diff --check`.

## Testing Expectations

Positive:

- Clean fixture (every risk snapshot at or before its session) yields zero
  findings and leaves overall status unchanged.
- Contaminated fixture reproducing the real shape (session `2026-06-02`, risk
  snapshot `2026-07-28`) yields exactly one `FAIL` with the right code and the
  right count.
- Sample list is capped at 10 on a large contaminated fixture.

Negative:

- Observation with no risk block: no crash, no FAIL, no false WARN.
- Malformed / unparseable `decision_payload_json`: reported as
  `..._UNREADABLE`, never raised and never silently passed.
- Missing `canonical_window`: falls back to `"7"`; missing both means unreadable,
  not pass.
- Risk snapshot *earlier* than the session is not flagged (legitimate — the
  cache can lag the session).
- Pre-open and swing observations are ignored entirely by this evaluator.

All tests run offline against a temp SQLite file.

## Acceptance Criteria

- [ ] `reconcile-sources` detects the 2026-07-31 defect shape and reports FAIL.
- [ ] Clean corpus produces zero new findings and unchanged exit status.
- [ ] No mutation, no new command, no new flags.
- [ ] Every negative case above is covered by a test.
- [ ] Focused tests and full suite pass; Lint Gate passes whole-repo.

## Do Not Interpret This As

- Do not build a generic look-ahead framework or a check-registry abstraction.
  One evaluator, existing pattern.
- Do not add a new `saham audit data` subcommand.
- Do not make this command mutate, repair, quarantine, or purge anything. The
  corpus purge is a one-shot script owned by the engine fix task.
- Do not flag ownership `fetched_at` later than the session; it is verified
  correct and would emit 854 false positives.
- Do not weaken the FAIL severity or add an allowlist to keep the gate green
  against a genuinely contaminated corpus.
- Do not extend coverage to pre-open or swing in this task.
- Do not treat this task as a prerequisite for the engine fix.

## Completion Record

- Completed date:
- Implementation commit:
- Files changed:
- Commands run:
- Findings on the clean corpus:
- Test result:
- Lint result:
