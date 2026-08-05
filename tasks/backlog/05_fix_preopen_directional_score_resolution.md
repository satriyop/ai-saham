# Give Pre-Open `directional_score` Enough Resolution To Rank And Learn

Status: `READY` — independent of tasks 1–4, can run in parallel.
Sequence: **5 of 8** — see `tasks/backlog/00_SEQUENCE_accum_baseline_and_learning_loop.md`

## 1. Task Metadata

**Task Title**
Replace the six-valued pre-open directional score lookup with a continuous
score, and fix NCP baseline capture coverage.

**Task Type**
Bugfix (scoring-material for the PRE_OPEN purpose)

**Priority**
Medium-High — highest-value pre-open item; blocks any pre-open learning.

---

## 2. Problem Statement

### 2.1 The score cannot rank

`config/signal_engine.yaml:53-61` maps direction × confidence to a **six-value
lookup**:

```
bullish  { HIGH: 80, MEDIUM: 70, LOW: 55 }
neutral  45
conflicted 35
bearish  20
unknown  0
```

`pre_open_directional_baseline.py:210-227` applies it as a cascade. Across a
universe of ~270 tickers, six distinct scores means the ranking is almost
entirely ties. Spearman rank IC — the metric `ml-saham` scores this policy on
(`ml_saham/eval/metrics.py:67-70`) — is close to meaningless under mass ties.

Observed consequence: `screener.pre_open.directional_score` returns **n=0** in
`ml-saham challenge health`, while `screener.pre_open.iev_rank` — a genuinely
continuous ranking over the same tickers — returns n=695.

The underlying inputs are already continuous and are being discarded:
- `delta_iev_ratio` → bucketed into HIGH/MEDIUM/LOW at `0.08` / `-0.03`
- `bid_pressure` → bucketed into BUY/SELL at `0.60` / `0.40`
- `iev_intensity` → used only as a `>= 1.0` boolean

### 2.2 The NCP baseline is mostly missing

`iev_snapshot_history` holds 2,620 rows over 26 distinct dates, of which only
**620 are NCP-locked**. The 08:56 NCP-locked reading is the highest-signal
observation of the session (IDX Kep-00003/BEI/04-2025 locks pre-open orders
08:56–09:00). Without a valid locked baseline, `delta_iev` is MISSING and scores
neutral — so the confidence axis silently collapses on most days.

### 2.3 The corpus is too small to judge either way

`learning_observations` holds **19** PRE_OPEN observations across 6 dates.
`learning_evaluations` shows the full history: n=2 → 5 → 10 → 17, latest
`average_return_pct` **+0.156%** with `{FAILURE: 6, NEUTRAL: 6, SUCCESS: 5}`.
Nothing can be concluded from n=17.

---

## 3. Desired Outcome

- `directional_score` is continuous over its plausible range, monotonic in each
  input, and produces few ties across a live universe.
- The discrete `PreOpenDirection` classification is **retained** for operator
  display and for the action cascade; only the *ranking score* becomes continuous.
- NCP-locked baseline capture succeeds on effectively every trading day, or the
  failure reason is recorded per day.
- Pre-open observation capture accumulates at a rate that can reach
  `pre_open_session_v1`'s minimum within a knowable number of sessions.

---

## 4. Non-Goals

- No change to `auction_quality` semantics — it stays an **action cap only** and
  must never contribute directional points.
- No change to the BULLISH/BEARISH/CONFLICTED/NEUTRAL classification rules.
- No change to `iev_rank` (it already works).
- No change to the accum path or accum corpus (purpose isolation).
- No new data provider.
- No lowering of `pre_open_session_v1` protocol thresholds.

---

## 5. Architecture Impact Assessment

- **Domain:** the score value object / scoring function if it lives in domain.
- **Application:** `pre_open_directional_baseline.py` — continuous scoring;
  `pre_open_screen_use_case.py` unchanged in structure.
- **Infrastructure:** IEV capture path — diagnose and fix NCP-locked write
  coverage.
- **Adapter:** display the continuous score; keep the discrete label visible.

New dependency: **No.**
Determinism: **No** — remains fully deterministic.
Persistence: **No schema change** expected; confirm `iev_snapshot_history`
already carries what the fix needs.
Warm-up: **Yes** — `iev_intensity` needs 20d average volume; already required.
Policy in adapter: **No.**

```md
Layer plan:
- Domain: continuous scoring function if the score VO is domain-resident
- Application: pre_open_directional_baseline continuous score; capture-time
  NCP baseline validation
- Infrastructure: IEV snapshot capture/write path fix for NCP-locked rows
- Adapter: render continuous score alongside the discrete direction label
```

---

## 6. AI Usage Declaration

**No AI involved.**

---

## 7. Risk, Signal, And Evidence Authority Considerations

Affected: **SignalEngine** (pre-open path only), pre-open `TradeSetup` action.
RiskEngine on pre-open stays **ANNOTATE**, not BLOCK (`screen_policy.py:42-53`) —
do not change that here.

**Does this change what can produce ENTER/WATCH/AVOID?** Yes, for pre-open. The
score becomes continuous, so any threshold expressed against it must be
re-derived, not carried over numerically. State the mapping explicitly.

**Cohort impact:** this forks the PRE_OPEN `compatibility_id`. With only 19
observations, a clean break is cheap — take it rather than carrying two
generations. Purge PRE_OPEN corpus rows only; accum rows are out of scope and
must be provably untouched.

---

## 8. Data & Persistence

- **Read:** `iev_snapshots`, `iev_snapshot_history`, `candles`.
- **Written:** IEV snapshots (existing path), fresh PRE_OPEN observations.
- **Schema change:** No (verify `is_ncp_locked` provenance is sufficient).
- **Old vs new semantically equivalent?** **No** — the score's range and
  distribution change. Any persisted or displayed threshold tied to the old
  6-value scale is invalid. Enumerate and update every one; do not leave an
  alias or a compatibility shim.

---

## 9. Acceptance Criteria

- [ ] `directional_score` is continuous; a live universe run produces a tie rate
      below a stated target.
- [ ] Score is monotonic in `delta_iev_ratio` and in `bid_pressure`, proven by test.
- [ ] Discrete direction label still rendered; `auction_quality` still cap-only.
- [ ] Every old-scale threshold identified and re-derived; none left dangling.
- [ ] NCP-locked capture rate measured before and after; failures logged per day.
- [ ] PRE_OPEN corpus clean-broken; accum rows provably untouched.
- [ ] `ml-saham challenge run screener.pre_open.directional_score` returns n > 0.
- [ ] Deterministic; offline tests; no non-goals violated.
- [ ] ADR-048 (NCP window) considered.
- [ ] **Lint Gate** passes.

---

## 10. Slices (each slice = one commit)

**Slice 1 — Measure.**
Report the tie rate of the current score on a live universe and the per-day
NCP-locked capture rate. Pin current scoring behavior with tests.
Commit: `test(pre-open): pin discrete directional score and measure tie rate`

**Slice 2 — Fix NCP baseline capture.**
Diagnose why only 620/2,620 history rows are NCP-locked. Fix capture or record
the structural reason. This lands first because a continuous confidence axis is
worthless without the baseline.
Commit: `fix(pre-open): restore NCP-locked baseline capture coverage`

**Slice 3 — Continuous score.**
Replace the lookup. Keep the discrete label. Monotonicity tests.
Commit: `fix(pre-open): make directional score continuous`

**Slice 4 — Re-derive thresholds.**
Update every threshold expressed against the old scale. No aliases, no dual-scale
support.
Commit: `fix(pre-open): re-derive action thresholds for continuous score`

**Slice 5 — PRE_OPEN corpus clean break.**
Backup, purge PRE_OPEN rows only, re-capture, verify accum untouched, run
`ml-saham` and record the verdict.
Commit: `chore(corpus)!: clean-break pre-open corpus for continuous score`

---

## 11. Testing Expectations

- Monotonicity in each continuous input, both directions.
- Boundary behavior at the old bucket edges (`0.08`, `-0.03`, `0.60`, `0.40`) —
  no discontinuity should remain.
- `auction_quality` cannot add points (negative test).
- Missing/MISSING `delta_iev` still resolves neutral and never fabricates confidence.
- Purge purpose isolation: accum row count unchanged.

Offline. `pytest -m "not tui"`. Ruff before close.

---

## 12. Documentation Impact

- README: **No.**
- New config options: **Yes** — the continuous score's coefficients replace the
  lookup table in `signal_engine.yaml`.
- Limitations: **Yes** — state that pre-open evaluation remains underpowered
  until the corpus grows well past n=17.

---

## 13. Required Reading

- `AGENT_QUICKSTART.md`, `TASK_TEMPLATE.md`
- `docs/adr/ADR-048-*` (NCP window / capture timing)
- `config/pre_open_screener.yaml`, `config/signal_engine.yaml:44-61`
- `~/dev/ml-saham/docs/challenge_pre_open_directional_score.md`
- IDX Kep-00003/BEI/04-2025 NCP rules (08:56–09:00 order lock)

---

## 14. Do Not Interpret This As

- **Not** permission to let `auction_quality` contribute directional points.
- **Not** permission to keep a dual-scale compatibility path. One scale.
- **Not** permission to touch the accum corpus.

---

## 15. Completion Record

- Completed date:
- Slice commits:
- Tie rate before → after:
- NCP-locked capture rate before → after:
- Old → new threshold mapping:
- `ml-saham` verdict + n:
- Test / Lint result:
