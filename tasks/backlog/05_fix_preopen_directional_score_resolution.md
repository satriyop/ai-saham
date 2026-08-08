# Give Pre-Open `directional_score` Enough Resolution To Rank And Learn

Status: `IMPLEMENTED` — code-first re-vet and slices 1–5 landed **2026-08-08**.
Sequence: **5 of 8** — independent of the accumulation config freeze (PRE_OPEN
purpose isolation). See `tasks/backlog/00_SEQUENCE_accum_baseline_and_learning_loop.md`.

**Note:** PRE_OPEN corpus was clean-broken; live recapture must run in the NCP
lock window (`saham fetch iev` then `research pre-open capture`) to refill
rows under the new compatibility id.

## 1. Task Metadata

**Task Title**
Replace the discrete pre-open directional score lookup with a continuous ranking
score, fix confidence collapse from the intensity gate, and make NCP baseline
ops/coverage honest.

**Task Type**
Bugfix / scoring-material (PRE_OPEN purpose only)

**Priority**
High among remaining backlog — highest-value pre-open item; task 06 stays
blocked on accum depth.

---

## 2. Re-Vet Verdict (2026-08-08)

### 2.1 Still true: the ranking score is a six-value lookup

Canonical scorer: `src/application/services/pre_open_directional_baseline.py`
(`evaluate_pre_open_directional_baseline` → `_raw_score`).

Config surface: `config/signal_engine.yaml` → `pre_open_directional_baseline`
(typed as `PreOpenDirectionalBaselineConfig`).

```text
BULLISH × {HIGH: 80, MEDIUM: 70, LOW: 55}
NEUTRAL: 45 | CONFLICTED: 35 | BEARISH: 20 | UNKNOWN: 0
```

Continuous inputs are bucketed **before** scoring:

| Input | Where | Effect |
|-------|--------|--------|
| `bid_pressure` | `_book_pressure_state` @ 0.60 / 0.40 | BUY/SELL/BALANCED |
| `delta_iev_ratio` | `_confidence` / `_participation_state` @ 0.08 / −0.03 | HIGH/MEDIUM/LOW |
| `iev_intensity` | `_confidence` @ `min_normalized_iev_intensity=1.0` | if &lt; 1.0 → **force LOW** |

Discrete **direction** labels (BULLISH/BEARISH/…) stay correct product language.
Only the **ranking score** lacks resolution.

Domain VO: `PreOpenBaselineAssessment.raw_score: int` with contract
`pre_open_directional_baseline.v1`.

### 2.2 Stronger than the draft: confidence never leaves LOW on live corpus

Measured on `data/db/data.db` PRE_OPEN observations with a score (n=17 of 29):

| `raw_score` | direction | confidence | n |
|---:|---|---|---:|
| 35 | CONFLICTED | LOW | 10 |
| 55 | BULLISH | LOW | 4 |
| 20 | BEARISH | LOW | 2 |
| 45 | NEUTRAL | LOW | 1 |

- **Distinct scores:** 4 (not 6 — HIGH/MEDIUM never appear)
- **Modal share:** 35 ≈ **59%** of scored rows
- **`iev_intensity`:** n=17, max ≈ **0.086**, **100% &lt; 1.0**

So production confidence is collapsed by the intensity boolean, not merely by
the lookup table. A continuous score that still gates confidence on
`intensity >= 1.0` will keep mass ties among BULLISH names.

Re-vet implication: continuous scoring must **use intensity and
`delta_iev_ratio` as continuous terms** (with explicit missing handling). Do
not preserve a hard LOW clamp that real data never clears without first
proving the intensity formula scale is wrong and recalibrating.

### 2.3 NCP “620/2620” is stale; root cause is ops + top-N, not only a flag bug

Live IEV history (2026-08-08):

| | rows | dates | NCP-locked rows | NCP dates |
|--|---:|---:|---:|---:|
| `iev_snapshot_history` | **3170** | 28 | **720** (~23%) | **13** |
| `iev_snapshots` (canonical) | 1673 | 29 | 653 | 13 |

Recent NCP days almost always store **exactly 50** locked tickers — matching
`saham fetch iev --top-n` default **50** (`fetch_iev_commands.py`). Days with
`ncp_pct=0` are discovery-only / pre-NCP fetches (`is_ncp_locked` stays 0 when
collection start is before 08:56 WIB).

So the defect class is:

1. **Ops coverage:** many sessions never ran a lock-window fetch.
2. **Universe scope:** NCP baseline exists only for top-N movers, not full board.
3. **Sticky flag path** in `SQLiteIEVRepository` is already intentional and
   largely correct when a lock-window fetch runs.

Slice work should measure **per trading day**: “did we write an NCP batch?” and
“how many tickers?”, improve lock-window capture reliability / diagnostics, and
document top-N as an explicit population limit — not silently treat
history-wide NCP fraction as a single code bug.

### 2.4 Corpus size (updated)

| Metric | Draft (old) | Live 2026-08-08 |
|--------|-------------|-----------------|
| PRE_OPEN observations | 19 | **29** |
| Cohorts | — | **1** |
| Capture calendar days | 6 | **8** (captured_at) |
| PRE_OPEN labels | — | **22** |
| PRE_OPEN evaluations | history to n=17 | **8** eval rows |

Still far below `pre_open_session_v1` (`min_n_total=80`, 3 folds, embargo 1).
Continuous score is necessary for ranking; corpus growth remains necessary for
WIN/LOSE.

### 2.5 Why ml-saham shows `directional_score` n=0 (multi-cause)

`ml-saham` re-vet (same DB):

- `screener.pre_open.directional_score` health: **BLOCKED_POLICY**, n=0
- `screener.pre_open.iev_rank` health: **BLOCKED_POLICY**, n=**776** (panel builds)

Blockers are not only ties:

1. Production-facing PRE_OPEN challenges require **explicit**
   `--compatibility-id` (no largest-cohort auto-select).
2. `baseline=production` requires verified **production-policy snapshots** and
   adapters; pre-open specs are **static fixtures** → must pass
   `--baseline static_reference` (no silent remap).
3. Thin PRE_OPEN observation density and discrete scores still hurt
   directional ranking once the panel runs.

Acceptance must use explicit compatibility id + `static_reference` (or a later
ADR if pre-open joins production snapshots). Do not treat health n=0 alone as
proof the score table is empty.

### 2.6 Action thresholds that re-derive with the score

`AssessPreOpenDirectionalBaselineUseCase._classify` maps score → strength /
entry quality using **shared** `classification.strong_min_score=70` /
`moderate_min_score=45`:

| Old discrete score | Typical class |
|--------------------|---------------|
| 80 / 70 (bullish high/medium) | ENTER path (before auction_quality caps) |
| 55 (bullish low) | WATCH |
| ≤45 | AVOID |

`auction_quality` remains **cap-only** (CAUTION→max WATCH, UNRELIABLE→AVOID) —
preserve that (ADR-048).

Any continuous score **must** re-state ENTER/WATCH cutovers for pre-open.
Prefer **pre-open-local** thresholds on the new scale over silently reusing
accum classification numbers without justification.

### 2.7 Identity / clean break

PRE_OPEN still uses **config-hash compatibility**
(`compute_pre_open_semantic_compatibility_id` hashes
`PreOpenDirectionalBaselineConfig` + classification + iev_min/top_n). Changing
score formula or coefficients **forks** PRE_OPEN `compatibility_id`.

With only 29 PRE_OPEN rows, clean-break is cheap. **Accum corpus must stay
untouched** (post–task-04 freeze).

Contract: plan a bump of `pre_open_directional_baseline.v1` → **v2** when the
score semantics change (clean break, no dual-scale alias).

---

## 3. Desired Outcome

- Ranking score is continuous on a documented 0–100 (or documented) scale,
  monotonic in `delta_iev_ratio` and `bid_pressure` when other inputs are held
  fixed, and uses intensity as a continuous factor (or a recalibrated gate with
  proof that real NCP rows clear it).
- Discrete `PreOpenDirection` retained for display and action cascade inputs.
- `auction_quality` never adds points.
- NCP lock-window capture: per-day success/failure diagnostics; top-N limit
  explicit; failure reasons recorded.
- PRE_OPEN corpus clean-broken under new identity; accum rows unchanged.
- `ml-saham challenge run screener.pre_open.directional_score` with
  `--compatibility-id` and `--baseline static_reference` returns **n &gt; 0**
  extractable rows (protocol depth may still BLOCKED_DATA folds).

---

## 4. Non-Goals

- No accum path / accum corpus / accum identity changes.
- No change to BULLISH/BEARISH/CONFLICTED/NEUTRAL **classification rules**
  (direction from IEP × book only), unless a separate ADR says otherwise.
- No change to `iev_rank` challenge (already dense from IEV history).
- No new data provider.
- No lowering `pre_open_session_v1` protocol thresholds.
- No dual-scale compatibility for old 6-value scores.
- No giving `auction_quality` directional points.

---

## 5. Architecture Impact Assessment

```md
Layer plan:
- Domain: PreOpenBaselineAssessment score type/contract (v2); keep enums
- Application: continuous score in pre_open_directional_baseline;
  classification thresholds for pre-open; capture-time NCP diagnostics
- Infrastructure: IEV fetch/write diagnostics only if needed (flag path OK)
- Adapter: display continuous score + discrete direction; CLI/TUI labels
```

- Determinism: yes.
- Persistence: no SQL schema change expected; observation **identity** changes.
- Policy in adapter: no.

---

## 6. AI Usage Declaration

**No AI involved.**

---

## 7. Risk, Signal, And Evidence Authority

- Affects **pre-open SignalEngine** score and thus pre-open TradeSetup actions
  after classify + auction_quality caps.
- Pre-open risk remains annotate/non-blocking where already designed — do not
  promote RiskEngine to hard-block here.
- **Does this change what can produce ENTER/WATCH/AVOID?** **Yes, PRE_OPEN only.**

---

## 8. Data & Persistence

- **Read:** `iev_snapshots`, `iev_snapshot_history`, candles, PRE_OPEN
  observations.
- **Written:** IEV snapshots (existing path), fresh PRE_OPEN observations after
  clean break.
- **Schema change:** no table migration; contract/identity bump yes.
- **Old vs new score equivalent?** **No.**

---

## 9. Acceptance Criteria

- [ ] Continuous ranking score; live or fixture universe shows far lower exact-tie
      rate than the 6-value table (state target, e.g. unique scores ≥ 50% of n on
      a top-50 board fixture).
- [ ] Monotonicity tests: ↑ `delta_iev_ratio` and ↑ `bid_pressure` do not decrease
      score when direction-consistent and other inputs fixed.
- [ ] No hard confidence clamp that fails 100% of current corpus intensity values
      unless intensity formula is recalibrated with measured proof.
- [ ] Discrete direction label still rendered; auction_quality still cap-only.
- [ ] Every threshold on the old 6-value scale found and re-derived (at least
      `classification` cutovers used by
      `AssessPreOpenDirectionalBaselineUseCase`).
- [ ] Contract/id: `pre_open_directional_baseline.v2` (or accepted name) + new
      PRE_OPEN `compatibility_id`; no dual-scale reader.
- [ ] NCP: before/after per-day lock-window batch metrics; top-N documented.
- [ ] PRE_OPEN purge only; accum observation count and compatibility_id unchanged.
- [ ] ml-saham directional challenge with explicit `--compatibility-id` and
      `--baseline static_reference` extracts n &gt; 0.
- [ ] Offline tests + whole-repo Lint Gate.

---

## 10. Slices (each = one commit)

**Slice 1 — Measure and pin.**
Pin current six-value behavior + intensity-forced LOW with tests. Record tie
rate and intensity distribution on live PRE_OPEN payloads / synthetic board.
Commit: `test(pre-open): pin discrete directional score and intensity collapse`

**Slice 2 — NCP coverage honesty.**
Per-day lock-window metrics; improve diagnostics / cron guidance / optional
fetch fail-closed messaging when run outside 08:56–matching. Do not pretend
top-50 history is full-universe NCP.
Commit: `fix(pre-open): make NCP lock-window capture coverage observable`

**Slice 3 — Continuous score (contract v2).**
Replace `_raw_score` lookup with continuous formula; keep direction enums;
monotonicity tests; float or higher-resolution score as needed with VO update.
Commit: `fix(pre-open): continuous directional ranking score (baseline v2)`

**Slice 4 — Re-derive action cutovers.**
Pre-open ENTER/WATCH thresholds for the new scale; auction_quality caps
unchanged; no aliases.
Commit: `fix(pre-open): re-derive entry cutovers for continuous score`

**Slice 5 — PRE_OPEN corpus clean break + ml-saham.**
Backup; purge PRE_OPEN purpose only; recapture when market hours allow or
document deferred recapture; verify accum untouched; run ml-saham with
`--baseline static_reference` and record n.
Commit: `chore(corpus)!: clean-break pre-open corpus for directional v2`

---

## 11. Testing Expectations

- Existing `tests/application/services/test_pre_open_directional_baseline.py`
  updated for v2 (no dual expectation).
- Monotonicity + missing `delta_iev` → no fabricated confidence.
- `auction_quality` cannot increase score (negative test).
- Intensity path: either continuous contribution or recalibrated gate with
  fixtures drawn from **real intensity scale** (current max ≪ 1.0).
- Purge purpose isolation if slice 5 touches scripts.
- `pytest -m "not tui"` focused modules; full Lint Gate on Python changes.

---

## 12. Documentation Impact

- Config: continuous coefficients replace six score keys (or coexist only during
  PR then delete old keys in same clean break).
- Operator: NCP fetch must run in lock window; top-N is population limit.
- ml-saham docs: directional challenge needs static baseline + compatibility id.
- Limitations: protocol depth still short until PRE_OPEN corpus grows past ~80
  labeled rows.

---

## 13. Required Reading

- `AGENT_QUICKSTART.md`, `TASK_TEMPLATE.md`
- `docs/adr/ADR-048-pre-open-signal-evidence-and-observation-identity.md`
- `config/signal_engine.yaml` (`classification`, `pre_open_directional_baseline`)
- `config/pre_open_screener.yaml`
- `src/application/services/pre_open_directional_baseline.py`
- `src/application/use_case/assess_pre_open_directional_baseline_use_case.py`
- `src/infrastructure/persistence/sqlite_iev_repository.py`
- `src/adapters/cli/fetch_iev_commands.py`
- `~/dev/ml-saham/docs/challenge_pre_open_directional_score.md`
- `~/dev/ml-saham/src/ml_saham/challenge/protocols.py` (`pre_open_session_v1`)

---

## 14. Do Not Interpret This As

- Permission to touch the accum freeze cohort.
- Permission to keep dual-scale scores.
- Permission to lower ml-saham protocol floors.
- Permission to treat history-wide NCP fraction as the only success metric
  (per-day lock batch + top-N are the real ones).

---

## 15. Completion Record

- Completed date: **2026-08-08**
- Slice commits:
  - `8a80275e` pin discrete score + intensity collapse (superseded by v2 tests)
  - `144f963b` NCP lock-window coverage observability
  - `4cb540e8` continuous ranking score baseline v2 + entry cutovers
  - (this commit) PRE_OPEN purge isolation + closeout
- Tie rate before → after: 4 discrete scores / 59% modal → continuous board
  (unit: ≥5 distinct scores on 6 synthetic tickers; not six-value set)
- Intensity handling: continuous `log1p(i / 0.02)` term; HIGH confidence soft
  floor `intensity_high_soft=0.02` (live scale); no `intensity>=1.0` clamp
- NCP: `get_ncp_lock_window_coverage` + fetch iev messaging (top-N + lock batch YES/NO)
- Old → new entry cutover: shared 70/45 → pre-open `enter_min_score=62` /
  `watch_min_score=48`
- New PRE_OPEN `compatibility_id` (config after v2, iev_min=100000, top_n=5):
  `sha256:bc54ac667ed3be5f1787567d114577c4286917eed79f1fe25301e5724c9abacd`
- Accum observation count before/after purge: **1035 → 1035** (compat
  `sha256:355e5b59…` unchanged)
- PRE_OPEN purged: 29 obs, 22 labels, 8 evals (tracks for those ids)
- Recapture: deferred to NCP lock window (market hours)
- `ml-saham`: until recapture, no PRE_OPEN cohort; after capture use
  `--compatibility-id <new> --baseline static_reference`
- Test / Lint: pre-open suite green; whole-repo ruff green
