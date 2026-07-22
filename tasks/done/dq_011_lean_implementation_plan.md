# DQ-011 lean implementation plan

**Status:** Done — 2026-07-22 (thin baseline freeze; code/tests as truth).

Companion to `tasks/backlog/audit_data_quality.md` → DQ-011 and
`tasks/done/improvement_cli_restructure.md` → CLI-001 hard prerequisite.

## Guiding decision (final)

> Freeze the **corrected behavioral baseline** for the current signal +
> accumulation CLI surface, add thin adapter invoke contracts where missing,
> stamp known limitations, and close DQ-011 so CLI-001 may begin.
> Do **not** rebuild history, touch quarantine, rename commands, or start
> CLI-002 routing in this task.

## Freeze scope (current registered names)

| Family | Current CLI | Side effects | Adapter contract |
|--------|-------------|--------------|------------------|
| Inspect | `saham analyze signal-inspect` | Read-only | PASS — `test_signal_inspect_command.py` |
| Replay / verify | `saham analyze signal-replay` / `--verify` | Read-only | PASS — `test_signal_replay_command.py` |
| Readiness | `saham analyze signal-readiness` | Read-only | PASS — `test_signal_readiness_command.py` |
| Backfill | `saham analyze signal-backfill-observations` | Writes obs (+ optional labels) | PASS — extended backfill CLI tests |
| Labels | `saham analyze signal-labels` | Summary RO; `--generate*` writes | PASS — extended label CLI tests |
| Accum eval | `saham analyze accum-audit` | Offline; CSV via `--output` | PASS — claim_stamp + no DB write |

## Slice map (closed)

| Slice | Status |
|-------|--------|
| D11-1 | Done — `signal-inspect` in `EXPECTED_COMMANDS` + help test; restructure pointers |
| D11-2 | Done — golden index below |
| D11-3 | Done — inspect / replay / readiness CliRunner contracts |
| D11-4 | Done — summary RO + generate rejection no-write |
| D11-5 | Done — invalid date / range leave tables untouched |
| D11-6 | Done — schema_version 2 + claim_stamp DESCRIPTIVE/raw_market; no obs/label writes |
| D11-7 | Done — limitations section |
| D11-8 | Done — DQ-011 Done; CLI-001 unblocked |

## Golden fixture index (D11-2)

| Family | Existing golden / primary test |
|--------|--------------------------------|
| Backfill | `tests/application/use_case/test_dq_003_truncated_backfill.py` |
| Labels | `tests/application/use_case/test_dq_004_forward_label_golden_reconciliation.py` |
| Replay / verify | `test_retrieve_stored_signal_observation_use_case.py`, `test_verify_stored_signal_observation_use_case.py` |
| Readiness | `tests/application/use_case/test_report_signal_readiness_use_case.py` |
| Inspect | `tests/application/use_case/test_inspect_canonical_signal_use_case.py` |
| Accum-audit | `tests/adapters/cli/test_analyze_accum_commands.py` |

## Known limitations (frozen stamps — not “bugs” to fix in CLI-001)

- Labels / accum outcomes: `outcome_basis=raw_market` (net-executable parked: `IDX-EXECUTION-LABELS`)
- Readiness: `promotion_eligible=false`; OOS diagnostic-only
- Accum-audit: `evaluation_role=DESCRIPTIVE`, `costs_modeled=false`
- Capture: candidate-only / no control population → recall ineligible
- Replay default = retrieval-only; `--verify` exit 2 = UNREPRODUCIBLE (incl. not found)
- Inspect name provisional until CLI-002
- Empty canonical OK after DQ-010; quarantine is historical parking
- Ordinary screen/analyze must not write observations

## Explicit non-goals (unchanged)

- CLI routing rename — CLI-002+
- Sentiment / DQ-009 / CLI-004
- Quarantine UX, mandatory historical rebuild
- Net-executable labels, promotion, purged walk-forward
- Changing SignalEngine / label math

## Classification

`NON_SEMANTIC` — adapter contracts and doc freeze only; one stale accum JSON
assertion updated to match shipped schema_version 2 / claim_stamp.

```md
Layer plan:
- Domain: not touched
- Application: not touched
- Infrastructure: not touched (temp DB in tests only)
- Adapter: CliRunner contracts + command-tree sync (tests)
- Documentation/governance: this plan, backlog Done, CLI-001 unblock
```
