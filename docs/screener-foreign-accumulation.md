# Foreign Accumulation Screener

## What Is This?

Every day on IDX, foreign investors (banks, hedge funds, institutional brokers) buy and sell stocks. IDX publicly discloses how much foreigners bought and sold for each stock every trading day. This screener reads that data and answers one question:

> **Which stocks are foreigners quietly buying — day after day — while the price is still low?**

This pattern is called **accumulation**: large players building a position before a price move. Performance evidence is not yet independently validated in this repository. Treat the screener as a deterministic evidence-ranking workflow until a versioned local audit reports universe, date range, sample count, horizon, costs, and config hash.

This is a **swing trade watchlist**, not an intraday tool. Signals here are for 5–20 day holding periods.

---

## Quick Start

```bash
# Step 1: Download fresh data (run once per day, takes ~30 seconds after first run)
saham fetch market --universe lq45

# Step 2: Screen all 45 LQ45 stocks for accumulation
saham screen accum --universe lq45

# Step 3: See all 3 time windows at once (recommended daily view)
saham screen accum --universe lq45 --multi
```

---

## Step 1 — Update Data

The screener reads from a local database (`data.db`). You need to populate it first.

```bash
saham fetch market --universe lq45             # LQ45 — 45 most liquid IDX stocks
saham fetch market --universe idx80            # IDX80 — 80 stocks
saham fetch market BBCA BBRI BMRI              # Specific tickers only

saham fetch market --universe lq45 --days 30  # Only fetch last 30 days (default: 90)
saham fetch market --universe lq45 --refresh  # Force full re-download, ignore cache
saham fetch market --universe lq45 --broker-only   # Only broker flow, skip price data
saham fetch market --universe lq45 --candles-only  # Only price data, skip broker flow
```

**Incremental updates.** After the first run (which downloads 90 days of history), subsequent runs only download new data since your last update. Running it twice in a row is near-instant — already-current tickers show `fresh`.

**Status codes in the update output:**

| Status | What it means |
|---|---|
| `fresh` | Already up to date — no download needed |
| `+5d` | Downloaded 5 new days of data since last run |
| `skip` | Skipped intentionally (e.g. `--broker-only` skips price data) |
| `ERR:...` | Download failed — just re-run, usually rate limiting |

**Which broker data source is used?**
- If you have a Stockbit login session → Stockbit (shows which specific broker bought/sold)
- Otherwise → IDX public API (shows total aggregate foreign flow only, no auth needed)

---

## Step 2 — Screen for Accumulation

### Single Window

```bash
# Default: last 7 days, show top 20
saham screen accum --universe lq45

# Change the lookback window
saham screen accum --universe lq45 --window 30    # last 30 days
saham screen accum --universe lq45 --window 90    # last 90 days

# Filter results
saham screen accum --universe lq45 --min-foreign-flow-score 50  # only strong foreign-flow evidence
saham screen accum --universe lq45 --min-streak 3     # only 3+ consecutive buy days
saham screen accum --universe lq45 --vwap-only        # only where foreigners are underwater
saham screen accum --universe lq45 --squeeze-only     # only BB squeeze setups
saham screen accum --universe lq45 --top 10           # show top 10 only

# More detail
saham screen accum --universe lq45 --guide            # explain columns and scoring components
saham screen accum --universe lq45 --top-broker       # show top broker-code detail when available
saham screen accum --universe lq45 --detail           # append run context and scoring definitions
saham screen accum --universe lq45 --format json      # machine-readable output
```

### Multi-Window (Recommended)

```bash
# See 7d / 30d / 90d scores side by side — one command
saham screen accum --universe lq45 --multi

# Sort by a specific window
saham screen accum --universe lq45 --multi --sort-by 30d

# Combine with filters
saham screen accum --universe lq45 --multi --squeeze-only
saham screen accum --universe lq45 --multi --top 15
```

---

## Reading the Output

### Single-Window Table

```
=============================================================================================
FOREIGN ACCUMULATION — LQ45 | 7d window | 2026-06-11
=============================================================================================
  # TICKER   SCORE  STREAK  NET_DAYS    NET_VALUE  FLOW%  VWAP_DISC    RSI  BB%ILE TREND
-------------------------------------------------------------------------------------------
  1 GGRM      60.3      4d       4/4       +19.4B  +24.8      -1.9%   42.5    —    DOWN
  2 GOTO      59.6      4d       4/4       +59.3B  +83.1      +0.0%   37.6    —    SIDE
  3 EXCL      59.0      4d       4/4       +22.4B  +24.1      -0.7%   36.6    —    DOWN
  4 BDMN      44.2      0d       3/4       +23.2B  +14.3      +3.2%   42.0   68%   DOWN
```

### Multi-Window Table (`--multi`)

```
=============================================================================================
FOREIGN ACCUMULATION — LQ45 | MULTI-WINDOW | 2026-06-11
=============================================================================================
  # TICKER     7d    30d    90d  PATTERN            TREND
-------------------------------------------------------------------------------------------
  1 GGRM      60.3    65.0    58.2  sustained           DOWN
  2 GOTO      59.6    68.7    53.1  sustained           SIDE
  3 EXCL      59.0    49.8    45.8  fresh rotation      DOWN
  4 BDMN      44.2    48.7    36.6  weak                DOWN
```

---

## Column-by-Column Explanation

### FOREIGN FLOW SCORE (0-100)

The deterministic foreign-flow evidence strength. Combines all indicators below into one number. Higher = stronger foreign-flow accumulation evidence.

| Range | Meaning | What to do |
|---|---|---|
| 58–100 | **Strong signal** | Worth researching further |
| 33–57 | **Moderate signal** | Watch, wait for confirmation |
| < 33 | **Weak signal** | Likely noise, skip |

Use `--min-foreign-flow-score 50` to filter out weak foreign-flow evidence. The foreign-flow score has a soft cap at 100 — component weights rarely all saturate at once.

---

### STREAK — Consecutive Buy Days

How many trading days **in a row** foreigners ended up as net buyers (bought more than they sold), counting back from today.

**Why it matters:** Anyone can buy on one good day. A streak of 4–7 days means a systematic, deliberate pattern — not a one-off trade. Institutions building a position don't do it in a single day; they spread purchases to avoid moving the price against themselves.

| Streak | Signal |
|---|---|
| 1–2d | Inconclusive |
| 3–4d | Noteworthy — watch this ticker |
| 5–7d | Strong — likely intentional accumulation |
| 8d+ | Very strong — institution is committed |

**Scoring:** Uses an exponential curve (not a hard cap). A 7-day streak earns ~63% of max streak points; 14 days earns ~86%. Longer streaks always score higher than shorter ones.

---

### NET_DAYS — Consistency Ratio

Format: `4/7` means foreigners were net buyers on 4 out of the last 7 trading days.

**Why it matters:** Streak measures the *current* run. NET_DAYS measures *overall consistency* across the full window. A stock with `4/4` (100% of days) is more convincing than `5/30` (only 17% of days) even if the streak number looks similar.

This is the **highest-weighted signal** (33.3 points out of 100) because sustained consistency is the clearest sign of institutional intent.

| Ratio | Meaning |
|---|---|
| 100% (4/4, 7/7) | Every day was a buy — strong conviction |
| 70–99% | Most days positive — healthy trend |
| 50–69% | Mixed — watch for deterioration |
| < 50% | More sell days than buy days — not accumulation |

---

### NET_VALUE — Total Net Foreign Flow

The total IDR value of (foreign buys − foreign sells) over the window period.

- `+19.4B` = foreigners net bought Rp 19.4 billion worth
- `-5.2B` = foreigners net sold Rp 5.2 billion worth

**Why it matters:** Confirms that the accumulation has real money behind it — not just marginally more buy trades than sell trades. A stock showing `4/4` NET_DAYS with `+10M` net value is a small retail-level move. The same consistency with `+500B` is institutional.

**Suffixes:** T = trillion, B = billion, M = million (IDR)

---

### FLOW% — Foreign Dominance of Daily Volume

The average percentage of total daily trading turnover that was net foreign buying/selling.

Example: `FLOW% = +24.8` means that on average, 24.8% of the total daily volume traded in that stock was net foreign buying.

**Why this is significant:** IDX has many domestic retail traders. When foreigners represent 20–30%+ of a day's total volume as net buyers, they are *dominating* that stock's price action. They're not just participating — they're in control.

| FLOW% | Interpretation |
|---|---|
| 0–5% | Minor participation |
| 5–15% | Meaningful foreign interest |
| 15–30% | Foreigners are a major force in this stock |
| 30%+ | Foreigners dominating — very strong signal |

`GOTO` showing `+83.1%` means foreigners represented 83% of net daily volume — essentially the entire order flow was foreign buying. That is exceptional.

**Scoring:** Contributes up to 10 points. Saturates at 20% (anything above 20% gets full points).

---

### VWAP_DISC — Foreigners' Profit/Loss on Position

VWAP (Volume Weighted Average Price) is the average price at which foreigners have been buying over the window. VWAP_DISC compares that to today's price.

- **Positive VWAP_DISC** (e.g. `+8.4%`) = foreigners bought at a higher average price than today. They are **underwater** (in a paper loss).
- **Negative VWAP_DISC** (e.g. `-1.9%`) = foreigners are in profit. Today's price is above their average buy.

**Why positive VWAP_DISC matters:** When foreigners are underwater and *still buying more*, it's a powerful signal. They are defending their position — adding to a losing trade because they believe in the recovery. This creates a price floor: a large institutional buyer will actively absorb selling pressure to protect their existing position.

Think of it this way: if you bought a stock at 10,000 and it's now at 9,000, you wouldn't keep buying unless you were very confident it would recover. That confidence is the signal.

| VWAP_DISC | Meaning |
|---|---|
| `> +5%` | Foreigners meaningfully underwater — strong defense motive |
| `+1% to +5%` | Slightly underwater — moderate signal |
| `0%` | Break even |
| `< 0%` | Foreigners in profit — less urgency to defend |

**Scoring:** Contributes up to 20 points. Linear — `+10%` underwater earns the full 20 points; `+5%` earns 10 points. Not binary anymore (old version gave all 20 or nothing).

**Note:** When VWAP_DISC shows `—`, it means not enough foreign buy data was available to compute it (common for low-activity days on the IDX public API).

---

### RSI — Room Left to Run

RSI (Relative Strength Index) measures recent price momentum on a 0–100 scale.

- **RSI > 70**: Overbought — stock has already run up, risky to enter now
- **RSI 55–70**: Momentum is building, but getting stretched
- **RSI 40–55**: Healthy range — stock is moving but not overextended
- **RSI 25–40**: Weak/recovering — ideal entry zone if combined with accumulation
- **RSI < 25**: Severe panic/capitulation — possible but high-risk entry

**Why it matters for accumulation:** The best accumulation setups are stocks where foreigners are buying consistently *while the price is still depressed*. An RSI of 35–45 with a 5-day buy streak means smart money is re-entering during weakness. By the time RSI hits 70, most of the move is already done.

**Scoring:** Tent function peaking at RSI=40 (maximum 8.3 points). Both extremes (< 25 and > 75) score zero — panic and overbought conditions are equally unfavorable.

| RSI | Score | What it means |
|---|---|---|
| 40 | 8.3 pts (max) | Perfect entry zone |
| 30 or 50 | ~5.8 pts | Good zone |
| 25 or 65 | ~0–2.5 pts | Getting extreme |
| < 25 or > 75 | 0 pts | Panic or overbought |

---

### BB%ILE — Bollinger Band Squeeze (Volatility Compression)

BB%ILE is the **percentile rank of today's Bollinger Band width** compared to the last 60 trading days.

First, what is Bollinger Band width? It measures how "wide" the price channel is. Wide bands = high volatility (big daily moves). Narrow bands = compressed volatility (stock is trading in a tight range).

BB%ILE tells you where today's volatility sits relative to the last 60 days:
- `BB%ILE = 5%` = Today's bands are among the **tightest 5%** of the last 60 days → extreme squeeze
- `BB%ILE = 50%` = Average volatility
- `BB%ILE = 90%` = Bands are very wide → volatility already expanded

**Why the squeeze matters:** When volatility compresses *while foreigners are quietly accumulating*, the stock is like a coiled spring. The accumulation adds buying pressure without moving the price (because volatility is low and the stock is trading flat). This typically precedes a sharp breakout — the compression releases suddenly when a catalyst hits.

The combination of **accumulation + squeeze** is considered a higher-priority candidate setup in IHSG.

| BB%ILE | Color | Meaning |
|---|---|---|
| ≤ 20% | 🟢 Green | **Squeeze** — coiled spring, watch closely |
| 21–40% | 🟡 Yellow | Moderately tight — building |
| > 40% | White | Normal/expanding volatility |
| `—` | — | Not enough price history (< 60 days of data) |

**Scoring:** Up to 8.3 points when enabled (disabled by default — see ADR-039: BB compression is a setup-phase diagnostic, not scored flow evidence). Bottom 20% would earn 4.2–8.3 pts; bottom 40% would earn 0–4.2 pts; above 40% earns 0.

---

### TREND — Price Direction vs SMA20

Whether the stock's current price is above or below its 20-day Simple Moving Average:

- `UP` = price is more than 2% above SMA20 — uptrend
- `DOWN` = price is more than 2% below SMA20 — downtrend
- `SIDE` = price is within ±2% of SMA20 — ranging

**Counterintuitive insight:** For accumulation setups, `DOWN` or `SIDE` is often better than `UP`. You want to enter *before* the trend turns up — when foreigners are buying into weakness, not chasing a stock that's already rising.

---

### PATTERN (Multi-Window Only)

The pattern label summarizes what the multi-window comparison reveals about the *nature* of the accumulation:

| Pattern | Meaning | Trade implication |
|---|---|---|
| **sustained** | Score ≥ 50 across all 3 windows | Foreigners have been accumulating for months — highest conviction, strongest signal |
| **building** | Strong 7d and 30d, weaker 90d | Accumulation is intensifying — recent acceleration of interest |
| **fresh rotation** | Strong 7d only, weak 30d/90d | Very recent buying — may be early or a one-week rotation, needs more time to confirm |
| **long-term only** | Strong 90d, weak recent windows | Foreigners were buying months ago but have slowed — position may be complete, watch for distribution |
| **coiled spring** | Any window: squeeze + score ≥ 50 | Accumulation AND volatility compression — higher-priority short-term breakout candidate |
| **weak** | No window scores ≥ 50 | Not a meaningful accumulation pattern currently |

**How to use PATTERN in your workflow:**
- `sustained` stocks are the safest bets — they've been building for a long time
- `coiled spring` stocks may move faster — the compressed volatility means the breakout (when it comes) is often sharp
- `fresh rotation` stocks need confirmation — check again in 5–7 days to see if the pattern holds
- `long-term only` stocks deserve caution — the smart money may already be exiting

---

## Scoring Definitions (`--detail` / `--guide`)

Add `--detail` after a screen run to show run context and scoring definitions.
Use `--guide` when you only want the column reference without running a screen.

This shows GGRM earned:
- `cons=33.3` — perfect consistency (4/4 days = 100%)
- `streak=10.9` — 4-day streak (exponential: not at max yet)
- `vwap=0.0` — foreigners are actually in profit (negative VWAP_DISC = 0 pts)
- `rsi=7.8` — RSI near 42, close to the ideal 40 sweet spot
- `flow=8.3` — 24.8% flow ratio earns full 8.3 pts (saturates at 20%)
- `bb=0.0` — no squeeze data (< 60 days of candle history)
- `inst=0.0` — no institutional brokers detected (IDX data, no Stockbit)

**Diagnostic use:** If a stock you expected to score high is ranked lower than expected, the scoring definitions show which component is likely missing. Common patterns:
- `vwap=0` — foreigners are in profit, no defense motive. Wait for a pullback.
- `streak=0` — high consistency but the run broke. A single sell day reset it.
- `bb=0` — not enough data for squeeze detection. Run `saham fetch market` with more days.

---

## Complete Scoring Formula

| Signal | Max pts | Formula |
|---|---|---|
| Consistency | 33.3 | `net_buy_ratio × 33.3` (linear: 100% days = 33.3 pts) |
| Streak | 25 | `25 × (1 − e^(−streak/7))` — 7d≈63%, 14d≈86%, never caps |
| VWAP discount | 16.7 | Linear: 0% = 0 pts, 10%+ underwater = 16.7 pts |
| RSI headroom | 8.3 | Tent peak at RSI=40, zero at RSI≤25 or ≥75 |
| Foreign flow ratio | 8.3 | Linear: 0% = 0 pts, 20%+ of turnover = 8.3 pts |
| BB squeeze | 8.3 | Disabled by default (setup-phase diagnostic, see ADR-039); bottom 20th pctile would earn 4.2–8.3 pts; bottom 40th 0–4.2 pts |
| Institutional brokers | 4.2 | Bonus if known institutional broker in top buyers (Stockbit only) |
| **Total (soft cap)** | **100** | |

Rescaled from a 0-120 scale to 0-100 (proportional ÷1.2) — see ADR-039 in `ARCHITECTURE_DECISIONS.md`.

---

## Recommended Daily Workflow

### Morning Routine (5 minutes)

```bash
# 1. Update data — fast after first run
saham fetch market --universe lq45

# 2. Multi-window overview — the most informative single view
saham screen accum --universe lq45 --multi

# 3. Focus on high-conviction setups
saham screen accum --universe lq45 --multi --squeeze-only   # coiled spring candidates
saham screen accum --universe lq45 --vwap-only --min-foreign-flow-score 50  # underwater + strong foreign-flow evidence
```

### Deep-Dive on a Candidate

Once you find a ticker worth researching (e.g. BBRI):

```bash
# How does the current score break down?
saham screen accum BBRI --window 7 --detail
saham screen accum BBRI --window 30 --detail

# What does the daily flow look like?
saham view ticker flow BBRI --days 30

# Swing decision and risk/signal context
saham plan swing BBRI
saham plan swing BBRI --with-sentiment   # add news context
```

### What Makes a Strong Candidate?

The ideal setup (from highest to lowest priority):

1. **PATTERN = `sustained` or `coiled spring`** — multi-window confirms the trend
2. **STREAK ≥ 5 days** — consecutive buying is systematic, not opportunistic
3. **VWAP_DISC > 0%** — foreigners are defending an underwater position
4. **BB%ILE ≤ 20% (green)** — volatility is compressed, breakout potential
5. **RSI between 30–50** — room to run, not overbought
6. **FLOW% > 15%** — foreigners are a meaningful force in this stock's volume
7. **NET_DAYS ≥ 70%** — consistent buying, not just a streak on low-activity days

No single signal is definitive. The score aggregates them all — but a stock with 5 of the 7 above is a much stronger candidate than one that barely passes a score threshold.

---

## Universe Management

```bash
saham fetch universe list
```

Output:
```
Configured universes:
  NAME            TICKERS  LAST UPDATED
  ----------------------------------------
  lq45                 45  2026-02-01
  idx80                68  2026-02-01
```

Universe lists are stored in `config/universes.yaml`. IDX rebalances indices every **February and August** — edit the YAML after each rebalancing.

Use `cached` to screen all tickers you've ever downloaded, regardless of which universe they belong to:

```bash
saham fetch market --universe cached
saham screen accum --universe cached --multi
```

---

## Broker Data: IDX vs Stockbit

| | IDX public API | Stockbit |
|---|---|---|
| Auth required | No | Browser session |
| Foreign buy/sell totals | ✓ | ✓ |
| Per-broker detail | ✗ | ✓ |
| Which institution bought | ✗ | ✓ |
| `--top-broker` flag | Not useful | Shows top broker-code detail |
| `inst` score component | Always 0 | Active |

**Why per-broker data matters:** Not all "foreign" buying is the same. A hedge fund (e.g. broker code `AK` = UBS, `BK` = JP Morgan, `ZP` = Morgan Stanley) buying 5 consecutive days is a fundamentally different signal than retail foreign accounts buying. With Stockbit data and `--top-broker`, you can see which institutions are moving.

To configure Stockbit:
```bash
# Login via browser (opens a Chromium window to authenticate with your Stockbit account)
saham fetch stockbit login

# Now screener can show top broker-code detail when available
saham screen accum --universe lq45 --top-broker
```

---

## Common Questions

**Q: A stock shows high score but is in a downtrend. Should I avoid it?**

Not necessarily. Foreign accumulation *during* a downtrend is often the setup — they're buying at lower prices before a reversal. A `DOWN` trend with a strong STREAK and positive VWAP_DISC means foreigners are absorbing the selling. The trend is likely to turn `UP` once their buying outweighs the sellers.

**Q: The same stock keeps showing up. When is it "too late" to enter?**

Watch STREAK and VWAP_DISC. If STREAK is now 0 (a sell day broke the run) or VWAP_DISC has turned negative (foreigners are now in profit and less motivated to defend), the setup has weakened. The optimal entry is typically 3–5 days into a streak, not after 15+ days.

**Q: Why does VWAP_DISC show `—` for some stocks?**

The IDX public API only provides aggregate foreign buy value and lot counts. For some stocks with low foreign activity, the per-day data is zero or missing. VWAP can't be computed without buy lots. This is normal — it doesn't mean no foreigners traded, just that the data granularity is insufficient. Stockbit data resolves this.

**Q: How is `FLOW%` different from `NET_VALUE`?**

`NET_VALUE` is an absolute number (total IDR). A large-cap stock like BBCA will naturally have higher NET_VALUE than a mid-cap. `FLOW%` is relative — it measures what *fraction* of that stock's total daily trading was foreign buying. A mid-cap stock with `FLOW% = 35%` is actually a stronger signal than a large-cap with `FLOW% = 3%` even if the absolute IDR values are reversed.

**Q: What does `--squeeze-only` filter for exactly?**

It keeps only stocks where `BB%ILE ≤ 20%` — meaning today's Bollinger Band width is in the bottom 20th percentile of the last 60 days. The band has narrowed significantly compared to its recent history. This is a quantitative definition of "the stock is coiling." Note: this filter requires at least 60 days of price data in your local database.

---

> **DISCLAIMER:** This tool is for research and analysis only. It does not constitute financial advice, investment recommendations, or trading signals. Always do your own research. Past patterns do not guarantee future results.
