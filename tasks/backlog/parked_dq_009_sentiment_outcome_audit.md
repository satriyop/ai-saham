# Parked — DQ-009 Sentiment Outcome Audit

Status: `PARKED`

Retired sources:

- `tasks/done/audit_data_quality.md` → DQ-009 / `DQ-SENTIMENT-GATE`
- `tasks/done/signal_evidence_program.md` (gate snapshot)

Activation trigger: sentiment calibration, sentiment promotion claims, or the
sentiment-specific CLI migration is explicitly requested.

Does **not** block canonical signal baseline, CLI signal/accum remount, or TUI.

## Task Metadata

- Task type: Spike / Research followed by Bugfix
- Priority: Medium (P1 when activated)
- Semantic classification: `EVIDENCE_CONTRACT` and possibly `LABEL_SCHEMA`
  when activated; confirm before editing
- Chosen decision: audit the sentiment prediction → outcome pipeline for
  point-in-time correctness and identity safety. Implement this option only.

## Problem Statement

Sentiment audits can bind predictions to wrong future outcomes, duplicate
statistics, or treat AI/API classifications as canonical evidence. Until this
gate passes, sentiment cannot support calibration, promotion, or its CLI
migration.

## Desired Outcome

- One time-valid prediction binds to correct future market outcomes.
- Invalid/unavailable outcomes are excluded with visible counts.
- Deterministic keyword, local-model, and remote-API results stay distinct.
- No AI/API sentiment result is treated as canonical evidence or promotion proof.

## Non-Goals

- No sentiment authority promotion into SignalEngine.
- No new predictive classifier merely to improve accuracy.
- No blocking of canonical signal/accum work.
- No destructive rewrite of user sentiment logs without backup/approval.

## Hard Invariants

- Fail closed on missing prediction-time provenance or classifier version.
- Publication time + market session cutoff beat fetch date alone.
- Offline keyword sentiment remains diagnostic until a separate promotion task.
- Remote AI/API sentiment cannot enter the evidence-promotion lifecycle.
- Clean break: quarantine invalid audits rather than inventing metadata.

## Exact Work Boundary

Expected files (when activated — revise before coding if inventory differs):

- `src/adapters/cli/analyze_sentiment_commands.py`
- `src/adapters/cli/analyze_sentiment_workflow_factory.py`
- `src/adapters/cli/analyze_sentiment_display.py`
- `src/application/use_case/audit_sentiment_use_case.py`
- `src/infrastructure/persistence/sentiment_repository.py`
- focused tests under `tests/` for the above

Forbidden until activation and task revision:

- SignalEngine scoring, readiness, capture, or promotion wiring
- Treating this task as a prerequisite for `DQ-BASELINE-GATE` (already closed)

## Required Reading

- `AGENT_QUICKSTART.md`, `AGENTS.md`, `TASK_TEMPLATE.md`
- `tasks/done/audit_data_quality.md` → DQ-009
- `docs/signal_evidence_authority.md`
- Current sentiment CLI / use case / repository source and tests

## Architecture Impact

```md
Layer plan:
- Domain: possibly pure prediction/outcome identities
- Application: session/cutoff policy, audit orchestration, eligibility
- Infrastructure: sentiment repository / identity constraints
- Adapter: transparent rendering only
```

## AI And Authority Declaration

- AI may assist investigation only; it must not establish ground truth.
- Offline keyword sentiment stays diagnostic until a separate promotion task.
- Local-ML sentiment requires ADR-042-compliant producer treatment if promoted.
- Remote AI/API sentiment remains non-authoritative challenger/diagnostic only.

## Exact Contract

Audit requirements:

- Prediction identity includes ticker, prediction timestamp,
  classifier/provider/model/rules version, and source-headline set or digest.
- Use publication time and market session cutoff, not fetch date alone.
- Define reference price and 1/3/5 trading-day outcomes precisely.
- Handle pre-open, intraday, post-close, weekend, and holiday predictions.
- Adjust or invalidate outcomes crossing corporate actions or bad candles.
- `INSERT OR REPLACE` cannot overwrite a semantically different audit.
- Reconcile unaudited selection and saved outcomes independently.
- Report class balance, coverage, unavailable outcomes, confusion matrix,
  calibration, and uncertainty; raw accuracy alone is insufficient.
- Separate AI-provider results from offline keyword classifier results.

## Implementation Checklist

- [ ] Confirm activation trigger with the user.
- [ ] Inventory current sentiment producer/consumer contracts.
- [ ] Golden prediction/outcome fixtures vs direct candle math.
- [ ] Session cutoff matrix (pre-open / intraday / close / weekend / holiday).
- [ ] Idempotent identity-safe writes.
- [ ] Statistics exclude invalid/unavailable with visible counts.
- [ ] Reports distinguish keyword / local-model / remote-API classifications.
- [ ] Prove no AI/API result is treated as canonical evidence.

## Acceptance Criteria

- [ ] Golden prediction/outcome fixtures match direct candle calculations.
- [ ] Session cutoff tests cover pre-open, intraday, close, weekend, holiday.
- [ ] Duplicate audit writes are idempotent and identity-safe.
- [ ] Statistics exclude invalid/unavailable outcomes and show excluded counts.
- [ ] Reports distinguish deterministic keyword from local-model and remote-API.
- [ ] No AI/API sentiment result is treated as canonical evidence or promotion proof.
- [ ] `DQ-SENTIMENT-GATE` checklist in the retired DQ doc can be marked closed
      via a completion record here.
- [ ] Focused tests + `git diff --check` pass.

## Do Not Interpret This As

- Do not block signal/accum CLI or TUI work on this task.
- Do not promote sentiment because the audit pipeline exists.
- Do not invent missing prediction provenance.
- Do not collapse keyword and AI classifications into one accuracy number.

## Completion Record

- Completed date:
- Implementation commit:
- Verified source revision:
- Files changed:
- Commands run:
- Verification result:
- Deferred items and owner:
