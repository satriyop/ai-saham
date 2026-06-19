# Swing Trading with ai-saham

## What Is Swing Trading?

Swing trading is holding a stock for **5 to 20 trading days** to capture a single directional price move. You are not a day trader (holding hours) and not a long-term investor (holding months or years). You are looking for a setup that is about to move, entering close to the base, and exiting near the peak of that swing.

In IHSG specifically, swing trading works well because:

1. **IDX discloses broker-level transaction data daily.** Almost no other market in the world shows you exactly which institutions are buying or selling every stock every day. This is an information edge you cannot get in US or European markets.
2. **Foreign institutions telegraph their intent.** When a foreign broker accumulates consistently over 5–10 days, a price move almost always follows. The data exists — most retail traders just don't read it.
3. **IHSG has pronounced institutional cycles.** Large funds rotate sector by sector. When a sector is in favor, every major stock in it gets accumulated before moving. The accumulation screen catches this early.
4. **Volatility is manageable.** IHSG stocks typically trend for 10–20 days before reversing, giving enough time to position and exit without needing tick-by-tick precision.

---

## The Daily Workflow

```
DAILY ROUTINE (10 minutes)
──────────────────────────────────────────────────────────────────
Step 1 → Update data        saham fetch market --universe lq45
Step 2 → Check market       saham analyze regime
Step 3 → Find candidates    saham screen accum --universe lq45 --multi
Step 4 → Deep-dive          saham analyze swing BBRI --preset foreign-bounce --capital N
Step 5 → Confirm chart      saham analyze chart price BBRI --sma 20 --days 90
Step 6 → Size the trade     saham trade size BBRI --capital N    (if not using preset)
Step 7 → Log the decision   saham trade log swing --ticker BBRI --from-analysis --with-regime
──────────────────────────────────────────────────────────────────
After 10–20 trading days: review what the setup actually delivered
Step 8 → Review outcomes    saham trade review swing
```

Steps 3–6 collapse what previously required 6+ separate commands into one primary command (`saham analyze swing`) for each candidate, plus chart confirmation before logging or entry.

---

## Step 1 — Update Your Data

```bash
saham fetch market --universe lq45
# or for a broader universe:
saham fetch market --universe idx80
```

The screener, risk assessment, and indicators all read from a local SQLite database (`data.db`). If you skip the update, you are making decisions on yesterday's data. Foreign accumulation can reverse in a single day.

After the first full download (~90 seconds for LQ45), daily incremental updates take 5–10 seconds.

---

## Step 2 — Check the Market Regime

```bash
saham analyze regime
saham analyze regime --universe lq45
```

Before looking at individual stocks, check whether IHSG itself supports swing entries. The regime command evaluates seven deterministic signals — benchmark trend vs SMA20/50, benchmark returns, universe breadth, and foreign flow breadth — and classifies the market into one of four labels based on a **0–7 composite score**:

| Regime | Score | Meaning | Action |
|---|---|---|---|
| `BULLISH` | 6–7 | Strong benchmark & breadth confirmation | Lean into setups |
| `SIDEWAYS` | 4–5 | Normal conditions, no dominant trend | Trade selectively, tighter stops |
| `WEAK` | 2–3 | Increasing selling pressure, IHSG < SMAs | Reduce size, require higher score |
| `RISK_OFF` | 0–1 | Mass selling (Panic/Crash) | Pause new entries |

```
saham analyze regime --universe idx80
```

**Reading the output:**
- **Breadth above SMA20**: % of universe stocks trading above their 20-day moving average. Below 40% = weak breadth.
- **Breadth 5d change**: Whether breadth is improving or deteriorating. A negative change with a SIDEWAYS label is a warning.
- **Foreign flow breadth**: % of universe stocks with positive net foreign flow. Falling sharply = institutions are selling, not buying.

Add `--with-regime` to `saham analyze swing` to include regime context inline with your per-stock analysis. `--with-regime` is an analysis option, not a `saham analyze regime` option.

---

## Step 3 — Find Candidates

```bash
# Multi-window overview — your daily starting point
saham screen accum --universe lq45 --multi

# Narrow to highest conviction
saham screen accum --universe lq45 --multi --min-score 50

# Only coiled springs (BB squeeze setups)
saham screen accum --universe lq45 --squeeze-only

# Only where foreigners are defending (underwater positions)
saham screen accum --universe lq45 --vwap-only --min-score 50
```

**Why multi-window is the right starting view:**

A stock that scores 75 on 7 sessions, 72 on 30 sessions, and 68 on 90 sessions is a fundamentally different trade from one that scores 75 on 7 sessions and 15 on 90 sessions.

| Pattern | Meaning | Trade quality |
|---|---|---|
| `sustained` | Institutions building for months | Highest conviction |
| `building` | Acceleration in recent weeks | Good — momentum increasing |
| `fresh rotation` | Only this week | Needs confirmation |
| `coiled spring` | Accumulation + BB squeeze | Urgency — compressed, ready to break |
| `long-term only` | Was accumulating months ago, not now | Skip — may already be exiting |
| `weak` | No window scores ≥ 60 | Skip |

`BRK` appears in multi-window output when named Stockbit top-broker rows are cached:

| BRK | Meaning |
|---|---|
| `smart+` | Smart-money tier is net buying in recent named-broker rows |
| `noise+` | Noise/retail-heavy tier is net buying; treat fresh rotations cautiously |
| `smart-` | Smart-money tier is net selling; do not upgrade the setup |
| `noise-` | Noise/retail-heavy tier is net selling |
| `mixed` | Named flow exists but is not led clearly by smart/noise tiers |
| `n/a` | No named Stockbit broker detail in cache |

**What you are looking for at this stage:** a shortlist of 3–5 tickers that score ≥ 60 on at least two windows. This feeds Step 4.

**Window semantics:** `--window 7`, `--window 30`, and `--window 90` use the latest 7/30/90 broker sessions available as of the analysis date. Use `NET_DAYS` / `STREAK` to see how much of that session window was net foreign buying.

---

## Step 4 — Deep-Dive with `saham analyze swing`

`saham analyze swing` is the cornerstone command. It replaces: `swing screen`, `risk`, `compute ATR`, `backtest`, and `sentiment` — all in one run, all for a single stock.

### Basic usage

```bash
saham analyze swing BBRI
saham analyze swing BBRI --no-sentiment                          # skip news fetch
saham analyze swing BBRI --no-refresh --no-backtest --no-sentiment # fastest, cached-only
saham analyze swing BBRI --force-refresh                         # force provider refresh
saham analyze swing BBRI --sentiment-verbose                     # debug news provider issues
```

By default, `saham analyze swing` checks and refreshes only the requested ticker's candles and broker flow if local data is behind today. The `DATA` section shows whether refresh used current cache, fetched new rows, checked the provider but found no newer trading rows, failed, or was disabled.

Sentiment is optional context. Provider/RSS errors are suppressed into a concise `SENTIMENT` warning by default so deterministic gates stay readable. Use `--sentiment-verbose` only when debugging the news provider, or `--no-sentiment` for a fully offline deterministic run.

### With the `foreign-bounce` preset

The `foreign-bounce` preset applies a structured gate checklist to determine whether this specific setup meets entry criteria. When capital is provided, it also computes the exact lot size using regime-adaptive TP/SL from `config/swing_screener.yaml`.

```bash
saham analyze swing BBRI --preset foreign-bounce
saham analyze swing BBRI --preset foreign-bounce --capital 10000000
saham analyze swing BBRI --preset foreign-bounce --capital 50000000 --risk-pct 2
```

**Preset gates for `foreign-bounce`:**

| Gate | Requirement | Rationale |
|---|---|---|
| score | ≥ 70 | Minimum conviction threshold |
| vwap_disc_pct | ≥ +3% | Foreigners are underwater and motivated to defend |
| trend | SIDE | Entering a ranging stock, not chasing a breakout |
| flow_pct | ≥ +5% | Foreigners are meaningfully dominant in volume |
| rsi_present | YES | RSI indicator must be available for validation |
| RSI | ≤ 60 | Room to run — not entering an overbought stock |

**Classification output:**

- `ENTER` — all 6 gates pass; setup is aligned
- `WATCH` — close but not fully confirmed; wait for failed gates to improve
- `AVOID` — too many gates failed; not a valid setup today

**Regime-adaptive TP/SL:** The system loads TP/SL targets based on entry regime from `config/swing_screener.yaml`. When `--with-regime` is active, targets adjust automatically:

| Regime | TP | SL | R:R |
|--------|----|----|-----|
| BULLISH | +8% | -4% | 2:1 |
| SIDEWAYS | +5% | -5% | 1:1 |
| WEAK | +3% | -3% | 1:1 |
| RISK_OFF | +3% | -3% | 1:1 |
| Default | +5% | -5% | 1:1 |

Without `--with-regime`, the default SIDEWAYS targets (5%/5%) are used.

**Why 1:1 R:R in SIDEWAYS?**

The 5%/5% parameters match exactly what the backtest validates. The win rate and profit factor you see in the HISTORY section were produced with these exits — if you size to a 2:1 target but the backtest was run at 1:1, you're executing a strategy that was never validated at those parameters.

A 1:1 R:R requires a win rate above 50% just to break even. That's the implicit claim this preset makes: the accumulation signal is strong enough to be right more than half the time on a 5% bounce.

To explore a different R:R, change the backtest first:
```bash
saham trade backtest-swing --universe lq45 --start 2025-01-01 --take-profit 10 --stop-loss 5
```
If the win rate at 10% TP is still above 33% (the 2:1 break-even), the higher target is viable.

Note: `--rr` and `--atr-mult` flags are only active when no preset is used. When a preset is active, sizing is driven entirely by the preset's fixed percentages, not ATR.

### With market regime context

```bash
saham analyze swing BBRI --preset foreign-bounce --with-regime
saham analyze swing BBRI --preset foreign-bounce --with-regime --regime-universe lq45
```

Adding `--with-regime` appends a MARKET REGIME section to the output showing IHSG breadth and benchmark context at the moment of your analysis.

### With ATR-based sizing (no preset)

If you are using your own entry/exit logic rather than the preset, omit `--preset` and provide sizing parameters manually:

```bash
saham analyze swing BBRI --capital 10000000 --risk-pct 1 --atr-mult 1.5 --rr 2.0
saham analyze swing BBRI --capital 10000000 --entry 4825 --rr 2.5
```

This uses ATR(14) to calculate the stop distance (`stop = entry − 1.5 × ATR`) and positions size from fixed-fractional risk.

### Output sections

```
══════════════════════════════════════════════════════════════════════════════
SWING VIEW — BBRI · 2026-06-12 · profile=balanced
══════════════════════════════════════════════════════════════════════════════

DATA
  Analysis date  2026-06-12   Candles through  2026-06-12   Broker flow through  2026-06-12
  Regime as of   2026-06-12
  Refresh        candles=cached-current; broker(idx)=cached-current

ACCUMULATION (7 sessions)                          signal: building
  Score  74.1   STREAK  6s   NET_DAYS  5/7   FLOW%  +18.4%
  VWAP   +4.2%    BB%ILE  15%    TREND  SIDE
  [cons=28.6 streak=20.1 vwap=8.4 rsi=6.2 flow=9.2 bb=8.5]

ENRICHMENT (stockbit, cached by `saham fetch market`)
  📊 ANALYST: 35B 2H | target Rp8,827 (+40.7%)
  🏦 HOLDING: DWIMURIA 54.9% | Inst 31.9% | Individual 8.7%
  🔍 BANDAR: Score +5 (Acc, top1 47%)
  📈 FUNDAM: P/E 18.3, ROE 21.2%, F-Score 7, quality=True
  ⭐ INSIDER BUY — John Doe (Comm) BUY 500,000 @ 1,200
  ⚠ DIVIDEND RISK
  SEASONAL +0.9% (60%wr, 5y)

FLOW DETAIL (30 sessions)                          through: 2026-06-12 · institutional desk
  Range  2026-05-04 → 2026-06-12   Sessions  30/30
  Net    +71.81B IDR   BUY/SELL  19/11   STREAK  6s
  Avg FLOW%  +18.40%   Latest  +8.20B (+24.80%)

BROKER DETAIL (5/5 sessions)            through: 2026-06-12 · stockbit
  Top buyers       AK +18.20B (4s), CC +12.40B (3s), YP +8.10B (2s)
  Top sellers      KZ -9.40B (2s), DB -6.70B (1s)
  Smart flow       +14.10B IDR   Noise flow  +8.10B IDR
  Weighted net     +20.45B IDR   Smart share  58.4%
  Concentration    top buyer 38.0%; top seller 41.6%
  Quality          broad accumulation; smart support

PRESET — foreign-bounce                            final: ENTER
  PASS            score           actual=74.1       required=>= 70
  PASS            vwap_disc_pct   actual=+4.2%      required=>= +3%
  PASS            trend           actual=SIDE        required=SIDE
  PASS            flow_pct        actual=+18.4%      required=>= +5%
  PASS            RSI present     actual=44.5        required=present
  PASS            RSI             actual=44.5        required=<= 60
  Tested plan: TP +5%, SL -5%, max hold 10 trading days.

MARKET REGIME                                     SIDEWAYS
  Breadth SMA20  52.3%   5d change  -2.1%
  Benchmark 20d  -1.2%   Foreign flow breadth  38.1%

RISK CONFIRMATION                                 verdict: LOW_RISK  conf: 71/100
  SMA20     4,810   EMA20     4,825   RSI14   44.5
  · RSI below 50 — room to run

PRESET SIZING
  Entry    4,840   Stop  4,598  (-5.00%)   Target   5,082  (+5.00%)
  Position  4 lots = 400 shares   Cost  1,936,000 IDR  (19.4% of capital)
  Risk       96,800 IDR   Max hold  10 trading days
  (5% stop = 1.20× ATR14)

HISTORY  (foreign-accumulation)  28 trades
  Win rate  58.3%   Profit factor  1.84   Max DD  -12.4%

SENTIMENT (3d)                                     call: POSITIVE
  12 headlines   (+7 / =3 / -2)   confidence  58%

══════════════════════════════════════════════════════════════════════════════
SUMMARY: Score 74.1 · LOW_RISK · 58% WR · positive news
PLAN:  ENTER setup passed. Consider 4 lots at 4,840; TP 5,082; SL 4,598; max hold 10 trading days.
══════════════════════════════════════════════════════════════════════════════
```

`BROKER DETAIL` appears only when the cached broker summaries contain named per-broker transactions, typically from Stockbit. This is a named top-broker view, not the same as the aggregate foreign-flow time series in `FLOW DETAIL`. Use it as confirmation context:

- `broad accumulation` supports the aggregate flow signal.
- `concentrated accumulation` means one broker dominates the flow; downgrade confidence unless the chart is constructive.
- `recent distribution` means the latest named-broker session is net foreign selling; do not upgrade a setup based only on older 30-session accumulation.
- `Smart flow` / `Noise flow` classifies all named top-broker rows available in the Stockbit summary, including local brokers when Stockbit returns them.
- The deterministic tier map is `AK`, `BK`, `KZ`, `ZP`, `RX`, `MS`, `DB`, `ML`, `YU` = higher weight; `YP`, `PD`, `XL`, `XC` = lower/noise weight.
- Absence of a broker code means it was not present in the cached top-broker rows, not that the broker had zero activity.
- `Weighted net` is a measurement layer only. It does not change `ENTER/WATCH/AVOID` gates yet.
- `Broker quality` notes under the preset block are confirmation/warning context only. `smart+` can support an `ENTER` or prioritize a `WATCH`, while `noise+` or `smart-` warns you to demand stronger chart confirmation or avoid upgrading the setup.

### Enrichment signals explanation

The `ENRICHMENT` section shows live Stockbit enrichment signals (cached by `saham fetch market`). These are read-only — no API calls from analysis commands.

| Signal | Color rule | What it tells you |
|--------|-----------|-------------------|
| 📊 ANALYST | Green if bullish + ≥10% upside target | Analyst consensus direction and price target |
| 🏦 HOLDING | Cyan if institutional ≥30% | Who owns the stock — institutional vs retail domination |
| 🔍 BANDAR | Green if score ≥4, Yellow if Acc, Red if Dis | Stockbit's proprietary institutional operator signal (-9 to +9) |
| 📈 FUNDAM | Green if quality (ROE≥15% + F-Score≥5 + profit) | Fundamental health check: P/E, ROE, Piotroski F-Score |
| ⭐ INSIDER BUY | Cyan | Director/commissioner buying in last 90 days |
| ⚠ DIVIDEND RISK | Yellow | Upcoming ex-dividend date — price may gap down |
| SEASONAL | Green if positive return | Historical monthly return % and win rate (5 years) |

All signals are pre-warmed by `saham fetch market --universe lq45` and served from SQLite cache during analysis.

### All options

| Option | Default | Description |
|---|---|---|
| `--profile` | `balanced` | Risk profile: balanced / conservative / aggressive |
| `--preset` | none | Swing preset: `foreign-bounce` |
| `--window` | `7` | Accumulation analysis window in broker sessions |
| `--flow-window` | `30` | Broker-flow detail window in broker sessions |
| `--capital` | none | Capital in IDR — enables sizing block |
| `--risk-pct` | `1.0` | % of capital risked per trade |
| `--entry` | latest close | Entry price override |
| `--atr-mult` | `1.5` | ATR multiplier for stop (ATR-mode only) |
| `--rr` | `2.0` | Reward:risk ratio for target (ATR-mode only) |
| `--with-regime` | off | Add market regime section |
| `--regime-universe` | `idx80` | Universe for breadth context |
| `--benchmark` | `^JKSE` | Benchmark ticker for regime |
| `--no-sentiment` | off | Skip news sentiment (offline mode) |
| `--sentiment-verbose` | off | Show optional sentiment provider errors/noise |
| `--no-backtest` | off | Skip historical backtest |
| `--no-refresh` | off | Disable automatic single-ticker candle/broker refresh |
| `--force-refresh` | off | Force provider refresh even when cached data is fresh |
| `--format` | `table` | Output format: `table` or `json` |

---

## Step 5 — Confirm Chart Structure

Before sizing or logging a paper entry, confirm that price structure agrees with the numeric gates. This uses existing chart commands and does not change the deterministic signal.

```bash
saham analyze chart price BBRI --sma 20 --days 90
saham analyze chart rsi BBRI --days 90
saham analyze chart volume BBRI --days 30
```

| Check | Prefer | Avoid |
|---|---|---|
| Price structure | Sideways base, higher low, or tight range near SMA20/support | Lower-high breakdown, wide red candles, price far below support |
| RSI | Recovering from 30-50 with room before 60 | RSI pinned below 30 while price keeps making lower lows |
| Volume | Accumulation days supported by visible participation | Thin volume, or volume spikes mostly on down days |

Decision rule:

- `ENTER` from `saham analyze swing` plus constructive chart = eligible for sizing/logging.
- `ENTER` plus breakdown chart = downgrade to `WATCH`; wait for structure to repair.
- `WATCH` plus constructive chart = keep on shortlist and rerun tomorrow.
- `AVOID` stays `AVOID`; charts are not used to override failed deterministic gates.

## Step 6 — Size the Trade

When you need position sizing independently (without the full swing view), use `saham trade size`. It uses ATR-based fixed-fractional sizing.

```bash
saham trade size BBRI --capital 10000000
saham trade size BBRI --capital 50000000 --risk-pct 2 --entry 4825
saham trade size BBRI --capital 10000000 --atr-mult 2.0 --rr 3.0
```

**Output:**

```
══════════════════════════════════════════════════════════════════
POSITION SIZE — BBRI · 2026-06-12
══════════════════════════════════════════════════════════════════

INPUTS
  Capital                   10,000,000 IDR
  Risk per trade                 1.00 %  =     100,000 IDR
  Entry (latest close)           4,840
  ATR(14)                       112.45
  ATR multiplier                   1.5×
  Reward : Risk                    2.0

STOP
  Stop price                    4,671
  Stop distance                   169  per share
  Stop %                       -3.49 %

TARGET
  Target price                  5,178
  Target %                     +6.98 %

POSITION
  Raw shares                      591
  Round lots                        5  lots = 500 shares
  Position cost            2,420,000  IDR  (24.2% of capital)
  Actual risk                 84,500  IDR  (vs target 100,000)
  Actual reward              169,000  IDR

══════════════════════════════════════════════════════════════════
ACTION: Buy 5 lots at 4,840.  Stop 4,671.  Target 5,178.
══════════════════════════════════════════════════════════════════
```

**Why ATR-based stops, not a fixed percentage:**
Setting a stop at "5% below entry" ignores the stock's actual volatility. A stock with ATR = Rp 300 will hit a 5% stop on any random day just from normal fluctuation. ATR × 1.5 sets the stop outside one standard day's move — you only get stopped if the stock breaks down genuinely, not from noise.

**All options:**

| Option | Default | Description |
|---|---|---|
| `--capital` | required | Total capital in IDR |
| `--risk-pct` | `1.0` | % of capital at risk per trade |
| `--entry` | latest close | Entry price override |
| `--atr-mult` | `1.5` | ATR multiplier for stop distance |
| `--rr` | `2.0` | Reward:risk ratio for target |
| `--atr-period` | `14` | ATR period |
| `--format` | `table` | Output format: `table` or `json` |

---

## Step 7 — Log to the Trade Journal

After identifying a candidate, log the actual decision and plan to the accumulation journal. This creates a record that can be reviewed after 10–20 trading days to answer: *did ENTER setups outperform WATCH setups, and did failed gates matter?*

```bash
saham trade log swing --ticker BBRI --window 7 --from-analysis --with-regime
saham trade log swing --ticker BBCA --window 7 --entry-price 9450 --from-analysis --with-regime
```

The command:
1. Runs the accumulation screen for that ticker on the specified window
2. Computes the multi-window pattern (7/30/90 broker sessions) automatically
3. Re-evaluates the `foreign-bounce` preset gates when `--from-analysis` is used
4. Stores preset name, decision (`ENTER/WATCH/AVOID`), failed gates, regime, entry, stop, target, and max hold
5. Appends one row to `journals/accumulation.csv`
6. Is idempotent — re-running the same (date, ticker, window) never duplicates

Use `--entry-price` when your planned entry differs from the latest close. Without `--from-analysis`, the command still works as the old lightweight candidate log, but it will not preserve the trade decision or plan.

---

## Step 8 — Review Outcomes

After 10+ trading days, check whether the accumulation signals actually predicted returns.

```bash
saham trade review swing
saham trade review swing --horizon 10 --min-score 70
```

The review fetches actual forward closes from your local database and computes four tables:

**Performance by score bucket** — answers: does score ≥ 70 actually outperform score 40–69?
```
PERFORMANCE BY SCORE BUCKET
  BUCKET       N    AVG_5D    AVG_10D   WIN_RATE_10D
  --------------------------------------------------
  Score ≥ 70   12    +3.2%     +5.1%           67%
  Score 40–69   8    +1.1%     +1.8%           50%
  Score 0–39    5    -0.8%     -2.1%           40%
```

**Performance by preset decision** — answers: do true `ENTER` rows outperform watchlist rows?
```
PERFORMANCE BY PRESET DECISION
  DECISION       N   AVG_10D   WIN_RATE  AVG_MAX_UP   AVG_MAX_DD
  --------------------------------------------------------------
  ENTER          8    +5.4%       62%       +8.9%       -3.8%
  WATCH          6    +1.7%       50%       +5.2%       -5.9%
  AVOID          3    -2.4%       33%       +2.1%       -7.4%
```

**Performance by pattern** — answers: does `sustained` outperform `building`?
```
PERFORMANCE BY PATTERN
  PATTERN              N   AVG_10D   WIN_RATE  AVG_MAX_UP   AVG_MAX_DD
  ----------------------------------------------------------------------
  sustained            7    +6.2%       71%      +10.1%       -3.2%
  building             5    +4.8%       60%       +8.3%       -4.1%
  fresh rotation       3    +0.4%       33%       +5.0%       -6.7%
```

**Signal delta** — answers: which individual signal correlates strongest with 10d returns?
```
SIGNAL DELTA (correlation with 10d return)
  SIGNAL         GROUP A                 N_A  AVG_A  GROUP B                 N_B  AVG_B
  ----------------------------------------------------------------------------------
  streak         ≥5d                      12  +5.8%  <5d                      8  +0.9%
  vwap_disc      >0 (underwater)          15  +4.2%  ≤0 (in profit)          5  -1.8%
  bb_pctile      ≤20% (squeeze)            6  +7.1%  >40%                   14  +2.1%
  flow_pct       ≥15%                      9  +6.0%  <15%                   11  +1.3%
```

After 20+ entries the statistics become meaningful. This is the only way to know whether your read of the IDX accumulation signal is actually calibrated.

---

## Validating the Preset — Portfolio Backtests

### `saham trade backtest-swing` — Walk-forward portfolio simulation

This validates the `foreign-bounce` preset at the portfolio level. Unlike `saham strategy backtest` (which tests a rules-file strategy on one stock), `swing backtest` replays the full daily workflow across a universe: scan → apply preset gates → rank by score → open within cash limits → exit by TP/SL/max-hold.

```bash
saham trade backtest-swing --universe lq45 --start 2025-01-01
saham trade backtest-swing --universe lq45 --start 2025-01-01 --with-regime
saham trade backtest-swing --universe lq45 --start 2025-01-01 --allow-regimes SIDEWAYS,BULLISH
saham trade backtest-swing --universe lq45 --start 2025-01-01 --show-trades 20
saham trade backtest-swing --universe lq45 --start 2025-01-01 --cost-bps 0  # gross/no-cost comparison
```

Default simulations include `20` bps one-way transaction cost, applied on both entry and exit. This approximates common Indonesian retail fee schedules around 0.15% buy / 0.25% sell as an average per side. Use `--cost-bps 0` only when you intentionally want a gross, no-cost comparison.

**Key parameters:**

| Option | Default | Description |
|---|---|---|
| `--preset` | `foreign-bounce` | Swing preset to validate |
| `--start` | `2026-01-01` | Backtest start date |
| `--end` | today | Backtest end date |
| `--capital` | `100,000,000` | Initial capital in IDR |
| `--risk-pct` | `1.0` | % of capital risked per trade |
| `--max-positions` | `5` | Maximum concurrent open positions |
| `--take-profit` | `5.0` | Take-profit % |
| `--stop-loss` | `5.0` | Stop-loss % |
| `--max-hold` | `10` | Maximum hold in trading days |
| `--cost-bps` | `20.0` | One-way transaction cost in basis points; use `0` for gross/no-cost comparison |
| `--with-regime` | off | Group results by entry-date market regime |
| `--allow-regimes` | all | Only enter trades when regime is in this list |
| `--show-trades` | `20` | Print N most recent individual trades |

**Reading the output:**

```
══════════════════════════════════════════════════════════════════════════════
WALK-FORWARD SWING BACKTEST
══════════════════════════════════════════════════════════════════════════════
Preset: foreign-bounce | Period: 2025-01-01 to 2026-06-12
Cost: 20 bps one-way, applied on entry and exit
Read as: the workflow scans each replay date, opens eligible signals within
portfolio limits, then exits by TP/SL/max-hold.

METRIC                             VALUE
──────────────────────────────────────────────
Initial capital               100,000,000
Final equity                  118,400,000
Total return                       +18.40%
Max drawdown                        -8.20%
Trades                                  47
Win rate                             57.4%
Avg trade return                     +1.84%
Profit factor                          1.72
Exposure days                        38.5%

Skipped: no_cash=0, duplicate=0, no_forward_data=5, regime=8
```

**If `--with-regime` is included:**

```
PERFORMANCE BY ENTRY REGIME
──────────────────────────────────────────────────────────────────────────────
REGIME        TRADES    AVG_RET       WIN       TOTAL_PNL
BULLISH           18     +3.1%       67%      12,400,000
SIDEWAYS          22     +1.4%       55%       7,300,000
WEAK               7     -0.8%       43%      -1,200,000
```

This tells you which market conditions the preset works best in. If WEAK regime consistently underperforms, restrict entries with `--allow-regimes SIDEWAYS,BULLISH`.

### `saham analyze accum-audit` — Validate Signal Buckets

Use audit before turning a confirmation signal into a hard rule:

```bash
saham analyze accum-audit --universe lq45 --preset foreign-bounce --start 2026-01-01
```

The grouped output includes `broker_quality` buckets (`smart+`, `noise+`, `smart-`, `noise-`, `mixed`, `no_detail`) with forward returns and win rate. Treat these rows as evidence for whether broker quality should stay a warning, become a downgrade, or become a future preset gate.

### `saham analyze swing-compare` — Regime filter variants side-by-side

Instead of running `swing backtest` three times with different `--allow-regimes`, `swing compare` runs all variants in one pass:

```bash
saham analyze swing-compare --universe lq45 --start 2025-01-01
saham analyze swing-compare --universe lq45 --start 2025-01-01 --variants baseline,sideways_only
```

**Built-in variants:**

| Variant | Allowed regimes | Intent |
|---|---|---|
| `baseline` | all | No regime filter — maximum trades |
| `sideways_only` | SIDEWAYS, BULLISH | Skip WEAK and RISK_OFF |
| `weak_plus` | WEAK, SIDEWAYS, BULLISH | Skip only RISK_OFF |

**Output:**

```
══════════════════════════════════════════════════════════════════════════════
SWING BACKTEST COMPARISON
══════════════════════════════════════════════════════════════════════════════
Universe: lq45 | Period: 2025-01-01 to 2026-06-12 | Cost: 20 bps one-way

VARIANT          REGIMES                   TRADES    RETURN    MAX_DD       WIN       PF   SKIP_REG   EXPOSURE
────────────────────────────────────────────────────────────────────────────────────────────────────────────────
baseline         all                           47   +18.4%    -8.2%     57.4%     1.72          0     38.5%
sideways_only    SIDEWAYS,BULLISH              39   +21.2%    -5.8%     61.5%     1.94          8     32.1%
weak_plus        WEAK,SIDEWAYS,BULLISH         44   +19.8%    -7.1%     58.0%     1.81          3     36.4%
```

If `sideways_only` shows better risk-adjusted returns (higher PF, lower drawdown) than `baseline`, it is worth restricting your live entries to those regimes.

---

## Complete Example: One Morning Workflow

```bash
# 1. Update data
saham fetch market --universe lq45

# 2. Check market regime
saham analyze regime

# 3. Scan for candidates
saham screen accum --universe lq45 --multi --min-score 50
# → Shortlist: BBRI (sustained, 7s=74.1), TLKM (building, 7s=61.3)

# 4. Deep-dive on top candidate
saham analyze swing BBRI --preset foreign-bounce --capital 10000000 --with-regime
# → PLAN: ENTER setup passed. Consider 4 lots at 4,840; TP 5,082; SL 4,598

# 5. Confirm chart structure before paper entry
saham analyze chart price BBRI --sma 20 --days 90
saham analyze chart rsi BBRI --days 90
saham analyze chart volume BBRI --days 30
# → Confirm sideways base / support, RSI room, and volume participation

# 6. Check second candidate
saham analyze swing TLKM --preset foreign-bounce --capital 10000000
# → PLAN: WATCH only. vwap_disc: 1.2% (required >= 3%)

# 7. Log BBRI decision and plan to journal
saham trade log swing --ticker BBRI --window 7 --from-analysis --with-regime
# → Logged BBRI | 2026-06-12 | window=7 sessions | score=74.1 | pattern: sustained | preset=foreign-bounce | decision=ENTER | regime=SIDEWAYS | plan entry=4,840 stop=4,598 target=5,082 hold=10d

# --- 10 trading days later ---

# 7. Review outcomes
saham trade review swing --horizon 10
```

---

## Exit Signals

The application identifies entries. Monitor these signals on open positions by re-running `saham analyze swing` daily on positions you hold:

| Signal | Action |
|---|---|
| Preset changes from `ENTER` to `WATCH` | Tighten stop or reduce size |
| Preset changes from `WATCH` to `AVOID` | Exit — institutional support is weakening |
| STREAK drops to 0 (a sell day breaks the run) | Warning — watch closely |
| VWAP_DISC turns negative (foreigners now in profit) | Motivation to defend is gone — consider tightening stop |
| RSI > 70 (overbought) | Take partial profit or trail stop |
| Score drops below 40 from a high level | Thesis has changed — exit |
| Price hits 3× ATR above entry | Swing likely complete |
| Market regime turns `RISK_OFF` | Close all positions |

The discipline is: run `saham analyze swing TICKER --preset foreign-bounce` on every open position every morning. If the preset that justified your entry now says `AVOID`, the trade is over regardless of your P&L.

---

## Command Quick Reference

| Command | Purpose |
|---|---|
| `saham fetch market --universe lq45` | Fetch today's candle + broker data |
| `saham analyze regime` | IHSG market regime: BULLISH / SIDEWAYS / WEAK / RISK_OFF |
| `saham screen accum --universe lq45 --multi` | Multi-window accumulation screener |
| `saham analyze swing TICKER` | Composite view: accumulation + risk + sizing + backtest + sentiment |
| `saham analyze swing TICKER --preset foreign-bounce` | Gate-checked entry decision with structured plan |
| `saham analyze swing TICKER --preset foreign-bounce --capital N` | Full plan + lot sizing |
| `saham analyze swing TICKER --with-regime` | Adds IHSG breadth context to swing output |
| `saham trade size TICKER --capital N` | Standalone ATR-based position sizing |
| `saham trade backtest-swing --universe lq45` | Walk-forward portfolio backtest of the preset |
| `saham analyze swing-compare --universe lq45` | Compare baseline vs regime-filtered variants |
| `saham trade log swing --ticker BBRI --from-analysis --with-regime` | Log candidate, preset decision, failed gates, regime, and plan |
| `saham trade review swing` | Review journal: did ENTER beat WATCH and did high-score setups deliver? |

For a reference of accumulation screener columns (`STREAK`, `VWAP_DISC`, `FLOW%`, `BB%ILE`, `PATTERN`), run:

```bash
saham screen accum --guide
```
