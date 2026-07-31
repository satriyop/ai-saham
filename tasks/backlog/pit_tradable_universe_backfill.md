# Point-In-Time Tradable Universe For Historical Backfill

Status: `READY`

Source: survivorship-bias investigation 2026-07-31 (pointer
`src/adapters/cli/research_accum_backfill_commands.py:169`). Companion to — **not
a duplicate of** — `tasks/backlog/parked_screen_rejected_controls_and_universe.md`.

Boundary vs the parked task:

| This task (READY) | Parked Slice B (still PARKED) |
|---|---|
| PIT **tradable** universe from candle presence | PIT **index/eligible** membership reconstruction |
| Uses data we already have (swept candles) | Needs an external membership source/warehouse |
| Corrects forward-going + in-window survivorship | Corrects pre-ingestion history too |
| Light: resolver `as_of_date` + repo query | Heavy: membership warehouse |

Deliver this slice first; it does **not** close the parked Slice B, which remains
the only path to true historical *index membership* and pre-2025 delistings.

## 1. Task Metadata

- Task type: Feature
- Priority: Medium — latent bias today (~1yr corpus); grows as depth accrues.
- Semantic classification: `OBSERVATION_SCHEMA` — changes the value of the
  persisted `universe_membership_source` (`@current` → `@pit`) and the derived
  `survivorship_limitation`. No scoring/risk/evidence behavior change.
- Chosen decision: thread `as_of_date` into universe resolution and derive
  backfill membership from point-in-time candle presence, replacing the
  static current-universe membership on the corpus-write paths only.

## 2. Problem Statement

Historical backfill applies **today's** universe membership to every historical
date:

- `resolve_tickers` (`src/application/services/universe_loader.py`) has no
  `as_of_date`; it returns current static membership (or `cached`).
- `run_signal_observation_corpus_write` stamps `f"{universe}@current"`
  (`research_accum_backfill_commands.py:172`); the use case derives the
  `survivorship_limitation` note from the `@current` suffix
  (`backfill_signal_observations_use_case.py:306`).

The corpus is therefore survivorship-biased and only **disclosed**, not
corrected — "judging an old competition using only companies still present
today." The accumulation capture/backfill path shares the same membership
identity limitation.

Precondition now satisfied (2026-07-31): a nightly board candle sweep
(`saham fetch market --universe cached --candles-only`, 18:35 cron in
`install_cron.sh`) forward-fills the whole tracked board daily, so **candle
presence now approximates true trading activity**. Absence of a bar on a swept
day means "did not trade," not "not requested" — the signal a PIT tradable
universe requires. This makes the light path viable; before the sweep it was a
no-op.

## 3. Desired Outcome

- A resolution path accepts `as_of_date` and, for backfill, returns membership =
  tickers with at least one candle within **N trading sessions** ending at
  `as_of_date` (N configurable; default sized to tolerate illiquid
  non-daily traders — the lumpiness analysis suggested ~5–10 sessions).
- Backfill corpus writes stamp `{universe}@pit` when PIT membership is used.
- `survivorship_limitation` becomes `None` for the broad current-universe claim
  and is replaced by a **narrower, still-honest** note: tradable-universe PIT
  only; index membership not reconstructed; delistings before the ingestion
  window (pre-2025-07) are physically absent.
- Applies to both `run_signal_observation_corpus_write` and the accumulation
  backfill/capture membership identity.

## 4. Non-Goals

- No historical **index/eligible-universe** membership reconstruction — that is
  parked Slice B in `parked_screen_rejected_controls_and_universe.md`.
- No attempt to recover pre-ingestion-window delistings (data absent).
- No new data provider; no Yahoo/IDX/Stockbit changes.
- No risk/signal/evidence-authority or setup-policy changes.
- No change to interactive `screen`/`analyze` (they stay read-only, non-writers).
- No change to the nightly sweep itself (already landed).

## 5. Hard Invariants

- Membership is a pure function of `as_of_date` + swept candles; same inputs →
  same membership (determinism).
- The corpus-write paths are the only callers switched to PIT membership;
  live/interactive resolution keeps current behavior unless a caller opts in.
- `survivorship_limitation` must never silently become `None` — it downgrades to
  the narrower disclosure, it does not vanish.
- Re-running the same semantic backfill must not change membership for a past
  `as_of_date` given the same candle coverage.

## 6. Architecture Impact

```md
Layer plan:
- Domain: not touched (membership derivation is application policy).
- Application: universe_loader gains as_of_date + PIT-membership derivation;
  backfill use case membership-source policy (@current vs @pit) and the
  narrowed survivorship_limitation wording.
- Infrastructure: new MarketDataRepository port method to list tickers active in
  a date window (SELECT DISTINCT ticker FROM candles WHERE date BETWEEN ? AND ?),
  implemented on SQLiteMarketRepository.
- Adapter: research_accum_backfill_commands.py stays thin — passes as_of_date /
  membership identity only; owns no policy.
```

- New dependency: No.
- Affects determinism: Yes (intended — membership becomes date-dependent and
  reproducible).
- Persistence change: No schema change; the persisted
  `universe_membership_source` **value** changes (`@current` → `@pit`).
- Orchestration/policy in adapter: No.

## 7. AI Usage Declaration

- No AI involved. Deterministic membership derivation only.

## 8. Risk, Signal, And Evidence Authority Considerations

- No decision-component behavior change (SignalEngine/RiskEngine/TradeSetup
  untouched).
- Second-order note: PIT membership changes **which tickers enter the learning
  corpus per date**, so downstream tuning cohorts can shift. This is a
  correctness improvement, but flag it — do not compare pre/post corpora as if
  the population were unchanged. See `[[tuning_regime_finding]]`.

## 9. Data & Persistence

- Reads: `candles` (ticker, date) via the new repo port method.
- Writes: unchanged rows; only the `universe_membership_source` value differs.
- Schema change: No.
- Old vs new source semantically equivalent? **No** — `@current` (static, today)
  vs `@pit` (date-windowed, candle-derived). The `@pit` suffix + narrowed
  `survivorship_limitation` make the difference explicit in the output contract.
- Point-in-time behavior: this task's entire purpose.

## 10. Acceptance Criteria

- [ ] `resolve_tickers` (or a sibling resolver) returns date-dependent
      membership for a given `as_of_date` and window N.
- [ ] A ticker with candles up to date D and none after is **included** for
      `as_of_date ≤ D` and **excluded** for `as_of_date > D + window`.
- [ ] `@pit` runs stamp `{universe}@pit` and emit the narrowed limitation; the
      broad survivorship note no longer appears for those runs.
- [ ] Both signal-corpus and accumulation backfill paths use PIT membership.
- [ ] Works without AI; deterministic for same inputs; no non-goals violated.
- [ ] Adapter thinness reviewed; policy lives in application.
- [ ] **Lint Gate**: `ruff check src/ tests/` and `ruff format --check
      src/ tests/` pass; no rule weakening / blanket noqa / new per-file ignores.

## 11. Testing Expectations

- Unit-test the PIT resolver against a fixture DB where one ticker "delists"
  mid-window (candles then absent): assert inclusion before, exclusion after the
  window.
- Unit-test the backfill use case membership-source policy: `@pit` → narrowed
  limitation, `@current` → existing broad limitation (regression guard).
- All tests offline (fixture candles, no network).
- Whole-repo Ruff check/format before close.

## 12. Documentation Impact

- README/CLI docs: note that backfill can produce a PIT tradable universe and
  what the `@pit` marker means. (Yes)
- New config option (window N): document. (Yes)
- Limitations to state: tradable-universe PIT only; index membership not
  reconstructed; pre-ingestion delistings absent. (Yes)

## Required Reading

- `AGENT_QUICKSTART.md`, `TASK_TEMPLATE.md`, relevant `AI_AGENT_CHECKLIST.md`
- `tasks/backlog/parked_screen_rejected_controls_and_universe.md` (Slice B boundary)
- `tasks/backlog/audit_learning_corpus_pit_invariants.md` (PIT audit coverage —
  ensure a new PIT membership claim is auditable there too)

## Do Not Interpret This As

- Do not treat `@pit` as index-membership-correct — it is tradable-universe only.
- Do not delete the `survivorship_limitation` field; downgrade its wording.
- Do not switch interactive `screen`/`analyze` resolution to PIT membership.
- Do not claim pre-2025 survivorship is corrected — that data does not exist.

## Completion Record

- Completed date:
- Implementation commit:
- Files changed:
- Commands run:
- Verification result:
- Remaining parked slices (index membership): still in
  `parked_screen_rejected_controls_and_universe.md`
