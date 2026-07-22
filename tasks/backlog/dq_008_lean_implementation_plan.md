# DQ-008 lean implementation plan (amended 2026-07-22)

**Status:** DONE (D8-1 + D8-2 implemented 2026-07-22). Parked items unchanged.

Companion to `tasks/backlog/audit_data_quality.md` → DQ-008 and its "Lean
accumulation-evaluation amendment (2026-07-22)". Prove historical accumulation
evaluation is an honest **DESCRIPTIVE** replay of the live accumulation-flow
screen path — not a promotion-grade backtester and not a silent-leakage report.

## Guiding decision

Implement this option only.

> Historical accumulation evaluation must (1) generate signals through the
> **same accumulation-flow screen scoring path** as live (session +
> `CanonicalSignalEvidenceInput` + `SignalEngine`), (2) account for every
> included/skipped candidate by reason, and (3) stamp every artifact with
> explicit raw-outcome / non-executable assumptions and
> `evaluation_role=DESCRIPTIVE`. Do **not** build a backtest platform, net-cost
> engine, purged walk-forward, historical-universe warehouse, or OOS promotion
> claim in this task.

**Why (codebase-grounded):**

- `AccumulationAuditUseCase` already replays `AccumulationScreenUseCase` per
  date with `as_of_date` and `EffectiveMarketSession` at market close — the
  spine exists.
- Composition is thinner than live screen: no Stockbit enricher providers,
  `source_availability_use_case=None`, no risk funnel, default foreign-flow
  policy — parity must be proven or gaps made visible, not assumed.
- Skip accounting today is only `skipped_no_forward_data`; audit filters and
  screen rejects can disappear silently.
- Outcomes are absolute close-to-close (+ optional TP/SL path sim) with no
  fees, no `outcome_basis`, no evaluation role — easy to overclaim as
  tradeable/OOS.
- Net-executable costs and purged walk-forward already have owning tasks
  (`IDX-EXECUTION-LABELS`, `PURGED-WALKFORWARD-VALIDATION`). DQ-004 lean set
  the precedent: raw honesty first.

---

## Vet findings → backlog revisions

| Current backlog ask | Verdict | Lean action |
|---|---|---|
| Live vs historical parity (features, gates, session, missing-data) | Keep — partial | D8-1: shared screen composition + truncated-data golden; document flow-only / filter-preset limits |
| Truncated-data live reconstruction matches historical signals | Keep | D8-1 golden |
| No forward candle in signal construction | Keep (already partially tested) | Keep + regression in D8-1 |
| Historical universe / survivorship | Keep honesty, not warehouse | Structured survivorship warning field; park full membership DB |
| Skip reconciliation by reason | Keep — **missing** | D8-2 skip ledger |
| Fees, slippage, lot, limits, fills, same-day TP/SL as tradeable | **Overscoped** | Park behind `IDX-EXECUTION-LABELS`; stamp `costs_modeled=false` / `outcome_basis=raw_market` |
| Absolute vs excess return (IHSG/sector) | Optional / park | Park unless a tiny existing calculator wires free; do not block lean close |
| Chronological split / overlapping-horizon risks | Keep note only | Explicit artifact notes; park purged WF |
| DESCRIPTIVE / IS / VALIDATION / OOS roles | Keep honesty | Always `DESCRIPTIVE` for lean; forbid OOS/promotion claim |
| CSV/JSON numeric units + record identity | Keep (lean) | D8-2: records identity or explicit summary-only contract |
| CLI rename to “evaluate” | Later | Park behind CLI restructure after contract accurate |

---

## What already exists (reuse)

| Piece | Location |
|---|---|
| CLI | `analyze_accum_commands.py` → `saham analyze accum-audit` |
| Workflow | `RunAccumulationAuditWorkflowUseCase` |
| Core replay | `AccumulationAuditUseCase` |
| Screen UC | `AccumulationScreenUseCase` (+ assessor `score_canonical_flow`) |
| Session | `EffectiveMarketSessionResolver` @ `MARKET_CLOSE` |
| Record / exit / stats | `accumulation_audit_record_builder.py`, `*_exit_simulator.py`, `*_statistics.py` |
| Config | `config/accumulation_audit.yaml`, `accumulation_audit_config.py` |
| Look-ahead test | `test_accumulation_audit_does_not_use_future_candle_as_signal_price` |
| Setup threshold parity test | `test_accumulation_audit_setup_thresholds_match_live_swing_setups` |
| Live screen factory | `screen_accum_workflow_factory.py` / `accumulation_screen_factory.py` |
| DQ-007 inspect | Shared-path proof for accumulation-flow (reuse as reference, not substitute) |

---

## Contract clarifications (implement this option only)

1. **Parity scope = accumulation-flow scoring path**
   - Same screen UC / assessor / `SignalEngine` path used for live screen and
     historical replay (prefer wiring audit through the same factory/bundle
     live uses, or golden-assert identical scores on truncated DB).
   - Audit YAML “setups” remain **filter presets** (threshold packs), not
     swing `SetupEvidence` / TradeSetup. Say so on the artifact.
   - Enrichment/risk funnel: either wire to match live, or fail closed /
     mark fields unavailable — do not silently diverge and claim full parity.

2. **Outcomes stay raw**
   - `outcome_basis=raw_market` (or equivalent) on every result artifact.
   - Entry model explicit: e.g. signal-day close reference; forward windows
     start next session.
   - Exit grid (if enabled) is **path simulation diagnostic**, not net
     executable fills.
   - `costs_modeled=false` / `execution_assumptions` text required.

3. **Evaluation role**
   - Lean artifacts always report `evaluation_role=DESCRIPTIVE`.
   - Do not invent IS/VALIDATION/OOS membership in DQ-008.
   - Notes must state overlapping-horizon / survivorship residual risk.

---

## Slice D8-1 — Signal-path parity + truncated-data golden

**Status:** DONE

**Goal:** Close “truncated-data live reconstruction matches historical signal
generation” and no-look-ahead for signal construction.

**Layer plan:**
```md
- Domain: not touched
- Application: AccumulationAuditUseCase wiring toward shared screen composition;
  optional thin parity helper — no new scorer
- Infrastructure: not touched (unless factory reuse needs config ports already present)
- Adapter: thin display of parity/session notes only if needed
```

**Contracts:**

1. Historical replay constructs / invokes the **same** accumulation screen
   scoring path as live (factory/bundle reuse preferred over a second bare
   ctor graph).
2. Golden: on a truncated SQLite (or recording fakes) for fixed
   `(ticker, signal_date)` vectors, historical audit signal score /
   `signal_authority_coverage` / setup_phase (if present) match a live-style
   single-date screen (or DQ-007 inspect) on the same truncated DB.
3. Negative: candles/enrichment after `signal_date` cannot change the
   signal-day score.
4. Document residual gaps (e.g. filter presets ≠ TradeSetup) in notes.

**Negative-first tests:**
- Truncated parity golden (score + coverage).
- Future candle does not affect signal price/score (keep/extend existing).
- If source-availability remains `None`, artifact notes say so — or wire it
  and assert availability parity.

**Semantic Change Classification:** Prefer `NON_SEMANTIC` for live screen
scores. If audit wiring changes live screen defaults, stop —
`SEMANTIC_ENGINE` / explicit decision required.

**Checkpoint:** stop for review after D8-1 before skip ledger / artifact work.

---

## Slice D8-2 — Skip ledger + raw/DESCRIPTIVE artifact honesty

**Status:** DONE

**Goal:** Close skip accounting, explicit cost/execution assumptions, and
evaluation-role honesty without building OOS infrastructure.

**Layer plan:**
```md
- Domain: not touched (or tiny report DTO fields in application)
- Application: skip ledger + artifact claim fields on audit response/workflow
- Infrastructure: not touched
- Adapter: CSV/JSON/table surface the new fields; thin formatting only
```

**Contracts:**

1. **Skip ledger** (at least):
   - `skipped_no_forward_data` (existing)
   - screen reject classes reused where available (`rejected_flow`,
     `rejected_signal`, structural, etc.)
   - audit filter exclusions by reason
   - Totals reconcile: evaluated + skipped_by_reason = considered universe
     attempts for the run (define “considered” explicitly in notes)

2. **Artifact stamps (every JSON/CSV summary):**
   - `evaluation_role=DESCRIPTIVE`
   - `outcome_basis=raw_market`
   - `costs_modeled=false`
   - entry/exit assumption strings
   - structured `survivorship_warning` (not only free text)
   - overlapping-horizon risk note

3. **Identity**
   - Either include record-level identities in JSON, or mark
     `records_in_json=false` and require CSV for row identity — no silent
     mismatch.

**Negative-first tests:**
- Filter-excluded tickers appear in ledger, not only vanish.
- Artifact JSON always carries DESCRIPTIVE + raw + costs_modeled=false.
- No artifact field claims promotion / OOS / net-executable.

**Close:** focused + related accum-audit tests green; `git diff --check`.

---

## Parked (explicit)

| Parked | Wake when |
|---|---|
| Fees, taxes, slippage, lot, price limits, fills, net returns | `IDX-EXECUTION-LABELS` |
| Purged walk-forward / embargo / holdout OOS | `PURGED-WALKFORWARD-VALIDATION` |
| Claiming IS/VALIDATION/OOS or promotion-grade edge | After immutable split + purged WF + edge task |
| Full historical universe membership warehouse | Product requires unbiased membership |
| Excess return vs IHSG/sector on audit outcomes | Optional follow-on if calculator wires free |
| CLI rename `accum-audit` → evaluate | CLI restructure after contract accurate |
| Treating exit-sim as tradeable | Only with executable label contract |
| Corporate-action-adjusted audit returns | Align with label CA policy in a named follow-on |

---

## After each slice — doc update

- Mark closed DQ-008 acceptance criteria `[x]` with satisfied-notes.
- Update this plan’s slice `Status`.
- Keep DQ-008 State = Done only when D8-1 + D8-2 close lean criteria.
- Do not mark parked criteria done.
- Do not claim `DQ-BASELINE-GATE` complete (still needs DQ-010/011 and any
  remaining gate checklist items).
