# Fundamentals Point-in-Time Depth Limit

**Measured:** 2026-08-05 against `data/db/data.db`
**Owning task:** `tasks/backlog/03_fix_risk_gate_silent_skip_and_fundamentals_pit_hole.md`, slice 4
**Verdict:** an honest point-in-time backfill of `piotroski_f_score` and
`market_cap_idr` is **not achievable** with the existing Stockbit fundamentals
fetch path. No backfill was performed. This document records the achievable
depth and the constraint it places on the corpus rebuild.

---

## 1. What was asked

Close the coverage hole that makes `FundamentalGate` unevaluable on 55.4% of
accumulation window-observations, by backfilling historical
`piotroski_f_score` and `market_cap_idr` — but only with **honest** values: the
value as it actually was as of a past date. A value computed today and stamped
with a historical `fetched_date` embeds look-ahead and is forbidden.

## 2. Measured state of `company_fundamentals`

| | |
|---|---|
| Rows | 9,014 across 303 tickers |
| `piotroski_f_score` NULL | 8,541 (94.7%) |
| `market_cap_idr` NULL | 8,541 (94.7%) |
| `fetched_date` span | 2016-05-30 → 2026-08-03 |
| Earliest row carrying either field | **2026-07-08** |

The table has exactly one date column, `fetched_date`, with
`UNIQUE(ticker, fetched_date)`. There is no `period_end` / `report_date`
column, so a row means "this is what the source said as of `fetched_date`".
The `saham audit data source-contracts` contract agrees:
`temporal_meaning: as of fetched_date`, `point_in_time_support: POINT_IN_TIME`,
`null_semantics: unavailable if null (source absence is valid)`.

The two populations in the table are distinct and both already honestly dated:

- **8,541 historical quarterly rows** (41 distinct dates, 2016-05-30 onward)
  written by `StockbitFundamentalsCache.write_historical_rows`. They are dated
  `quarter_end + 60 days` — a conservative publication lag — and carry only
  `net_profit_margin` and `revenue_yoy_growth`. `piotroski_f_score` and
  `market_cap_idr` are set to `None` at the parser
  (`stockbit_fundamentals_parser._parse_historical_rows`), never guessed.
- **473 live snapshot rows** from 2026-07-08 onward, dated with the true fetch
  timestamp, carrying the full field set.

So the NULLs are not a bug and not a PIT-lookup defect. The PIT read
(`StockbitFundamentalsCache.read(..., as_of_date=...)`,
`WHERE date(fetched_date) <= date(?)`) is correctly bounded. There is simply no
historical source for these two fields.

## 3. Why an honest backfill is not achievable

`StockbitFundamentalsProvider` calls exactly one endpoint:
`/keystats/ratio/v1/{ticker}?year_limit=10`.

**`piotroski_f_score`** arrives as a single precomputed scalar in that
response's flat ratio list (`"Piotroski F-Score"`). It is not computed locally
— there is no F-score calculator anywhere in `src/`. The same response's
`financial_year_parent` block, which `year_limit=10` widens, carries only
**Net Income and Revenue** per quarter. The nine F-score components need
per-period ROA, operating cash flow, leverage, current ratio, share count,
gross margin and asset turnover — none of which are in that block.

Producing historical F-scores would require (a) a different endpoint
(`/findata-view/company/financial`) for full per-period statements, and (b) a
new local Piotroski calculator. That is a new fetch path plus new domain logic,
outside this task's "use existing Stockbit fundamentals fetch paths" bound.
Independently, it would still not be *provably* honest: Stockbit's statement
view is the current view, so restatements would silently leak backwards.

**`market_cap_idr`** arrives as a single current scalar
(`data.info.market_cap.raw`, with `data.stats.market_cap` as fallback). It is
not derived from shares outstanding. There is **no shares-outstanding field
anywhere in `src/`** — not fetched, not parsed, not stored. Reconstructing
historical market cap as `shares × historical close` would therefore mean
applying *today's* share count to a past date. IDX small and mid caps change
their share count often (rights issues, private placements), so that is exactly
the look-ahead contamination the task forbids.

Neither field has a stored historical antecedent, so there is nothing to
reconstruct from. The correct action under the task's hard constraint is to
record the true fetch date and let the PIT lookup skip — which the current code
already does.

## 4. Achievable depth (the hard limit)

**Fundamental risk evidence has honest point-in-time coverage from 2026-07-08
only**, per ticker from that ticker's first live snapshot fetch:

| Coverage start | Tickers |
|---|---|
| 2026-07-08 | 273 |
| 2026-07-09 | 30 |
| **Total with any coverage** | **303** |

Before 2026-07-08 there is no honest value for either field for any ticker, and
no way to create one from the existing provider.

### What this bounds

| Consumer | Field | Effect before 2026-07-08 |
|---|---|---|
| `FundamentalGate` | `piotroski_f_score` | `GateOutcome.UNEVALUABLE` — asserts nothing |
| `LiquidityGate` market-cap leg | `market_cap_idr` | 1T IDR floor not applied; the median-tx leg still evaluates |
| `AccumulationCandidateStructuralFilter` | both | `min_market_cap_idr` / `min_piotroski` reject everything if set above 0 |

Note the asymmetry: the structural filter **rejects** on a missing value while
the gates go **unevaluable**. Setting `min_market_cap_idr` or `min_piotroski`
above 0 for any pre-2026-07-08 session therefore empties the universe rather
than degrading it.

## 5. Constraint on the corpus rebuild (task 4)

> **A corpus cohort that spans sessions before 2026-07-08 carries a permanently
> degraded, non-recoverable fundamental risk assessment. That depth cannot be
> repaired later by re-fetching — the data does not exist to fetch.**

Options for task 4, in order of preference:

1. **Start the deep cohort at 2026-07-08 or later.** Every session then has
   honest `piotroski_f_score` and `market_cap_idr` for all 303 tickers, and
   `FundamentalGate` plus the LiquidityGate market-cap leg are genuinely live.
   Coverage depth grows one session per day from here with no extra work.
2. **Go deeper and accept the degradation explicitly.** Pre-2026-07-08 rows
   must be treated as a separate cohort — mixing them with post-cutoff rows
   pools observations where a gate was live with observations where it was
   structurally blind, which is not one population.
3. **Do not** set `min_market_cap_idr` or `min_piotroski` above 0 for any
   pre-cutoff session (see §4).

The current corpus spans 2026-06-02 → 2026-08-04, i.e. it straddles the cutoff.
That straddle is the reason `FundamentalGate` shows 4,299 unevaluable
window-observations (55.4%).

## 6. Gate skip rates

Measured with `scripts/report_risk_gate_skip_rates.py --window all`, over the
7,764 persisted accum window-observations. Unchanged before → after, because no
backfill landed and no persisted observation was rewritten:

```
gate             pass  triggered  skipped  not_evaluated  unknown%
BandarGate       2928       1545     1437           1854     18.5%
FreeFloatGate    3630        588     2280           1266     29.4%
FundamentalGate  3348        117     4299              0     55.4%
LiquidityGate    6498       1149        0            117      0.0%
```

The `FundamentalGate` 55.4% is now explained rather than fixed: it is the exact
consequence of the 2026-07-08 coverage start against a corpus that begins
2026-06-02. It will fall on its own as the corpus moves past the cutoff, and
task 4 can make it 0% by choosing option 1 above.

`LiquidityGate` reads 0.0% because it only reports unevaluable when *neither*
of its legs has input; with candles present it still evaluates the median-tx
leg. The market-cap leg being inapplicable is recorded separately, in the gate
reason and in `gate_context.missingness.market_cap_idr`.

## 7. Data Contract Audit Gate

| Command | Exit | Status |
|---|---|---|
| `saham audit data manifest` | 0 | — |
| `saham audit data source-contracts` | 0 | `WARN` |
| `saham audit data reconcile-sources` | 0 | `WARN` |

All 11 `company_fundamentals` findings are `WARN / NULLS_IN_OPTIONAL_FIELD`,
reporting the same 8,541 NULLs analysed above. They are **pre-existing
live-data coverage findings, not caused by this work** — no slice of this task
wrote to `company_fundamentals` or changed any persisted source semantics. No
`FAIL` findings. No schema change was made or required.

Per the gate: this document does **not** claim the pre-2026-07-08 fundamental
path is point-in-time complete. It claims the opposite, and bounds it.

## 8. Guard

`tests/infrastructure/browser/test_fundamentals_pit_cutoff_regression.py` pins
the invariant that makes "let the PIT lookup skip" a safe answer: a row dated
after a session — snapshot or backfilled — is invisible to that session, and
when nothing is visible on or before the cutoff the read returns `None` rather
than the nearest later row. This guards the `34fc4360` look-ahead class of bug
on the fundamentals side, and it is what makes a future honest backfill safe to
land without re-auditing the read path.
