# Parked — Output Contract Ownership

Status: `PARKED` / `NON_BLOCKING`

Retired sources:

- `tasks/done/audit_signal_refactor_contract.md` → Task `OUTPUT-CONTRACT-OWNERSHIP`
- `tasks/done/signal_evidence_program.md` (non-blocking cleanup note)

Activation trigger: documentation hygiene pass after live-contract work; may
run anytime. Does **not** block `LIVE-CONTRACT-GATE` (already closed) or any
DQ/TUI gate.

## Task Metadata

- Task type: Spike / Research (documentation correction)
- Priority: Low
- Semantic classification: `NON_SEMANTIC`
- Chosen decision: make `docs/signal_engine_output_contract.md` describe what
  runtime actually emits and owns. Implement this option only.

## Problem Statement

Conceptual output guidance can drift from code: a dead
`regime_detection_method_at_signal` field looks like missing evidence; volatility
sizing already exists but is easy to “re-implement”; liquidity sizing and final
position-size composition are easy to invent from prose.

## Desired Outcome

- Active docs name exact current owners/locations for decision constraints,
  volatility diagnostics, and scoring authority.
- Dead regime-method field is documented as legacy/non-canonical.
- Liquidity and final composed sizing remain explicitly unimplemented.
- No duplicate authority map and no fingerprint migration in this task.

## Non-Goals

- No scoring formula changes.
- No new providers or market-context classifiers.
- No volatility/liquidity fields added to `DecisionConstraints`.
- No historical fingerprint rewrite (owned elsewhere when identity schema bumps).
- No final position-sizing implementation.

## Hard Invariants

- Current code/config/tests outrank conceptual docs.
- Producer provenance status is not scoring authority.
- `DecisionConstraints.effective_size_multiplier` currently means regime-policy
  multiplier only.
- Do not fabricate a constant to fill the dead regime-method field.

## Exact Work Boundary

Expected files:

- `docs/signal_engine_output_contract.md`
- possibly `docs/signal_refactor.md` index wording

Forbidden:

- `src/**` behavior changes
- Persistence/schema migrations
- Duplicate top-level `evidence_statuses` map

## Required Reading

- `docs/signal_engine_output_contract.md`
- `docs/signal_refactor.md`
- Current `DecisionConstraints`, volatility context, Alpha/Trigger contributions,
  observation metadata that writes null regime detection method

## Architecture Impact

```md
Layer plan:
- Domain: not touched
- Application: not touched
- Infrastructure: not touched
- Adapter: not touched
- Documentation: truthful ownership vs deferred concepts
```

## Exact Contract

Document current truths:

- `DecisionConstraints` owns regime/setup decision caps and regime size
  multiplier only.
- Volatility multiplier is separate diagnostic/persisted sizing input.
- Liquidity multiplier is not implemented.
- `alpha_trigger_score.group_contributions[].evidence_status` is the canonical
  scoring-authority representation.
- Producer-local provenance status is not scoring authority.
- Final position sizing is not owned by current SignalEngine output.

Dead field disposition:

- Document `regime_detection_method_at_signal` as legacy/never-produced and
  ineligible for canonical attribution.
- New-schema exclusion remains owned by artifact-identity work; physical cleanup
  of legacy rows remains quarantine/rebuild owned elsewhere.
- Do not migrate fingerprints in this task.

## Implementation Checklist

- [ ] Verify current emitters in code for each claimed field.
- [ ] Rewrite active output guide ownership sections.
- [ ] Mark dead regime-method field legacy/non-canonical.
- [ ] Explicitly defer liquidity and composed final sizing.
- [ ] `git diff --check`

## Acceptance Criteria

- [ ] Active output guide names exact current locations/owners for decision
      constraints, volatility, and evidence authority.
- [ ] Liquidity/final sizing remain explicitly unimplemented; no new
      `DecisionConstraints` or duplicate authority fields.
- [ ] `regime_detection_method_at_signal` documented as legacy/non-canonical.
- [ ] Existing volatility output and per-group authority remain unchanged in
      description and code.
- [ ] `git diff --check` clean.

## Do Not Interpret This As

- Do not implement fields because an archived shape listed them.
- Do not describe a permanently-null producer field as legitimate UNKNOWN
  evidence.
- Do not multiply regime and volatility sizing inside SignalEngine as a
  shortcut.
- Do not rename `effective_size_multiplier` behavior here.

## Completion Record

- Completed date:
- Documentation commit:
- Files changed:
- Verification result:
