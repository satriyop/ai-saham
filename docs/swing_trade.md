# Swing Trading with ai-saham

## What Is Swing Trading?

Swing trading is holding a stock for **5 to 20 trading days** to capture a single directional price move — a "swing." You are not a day trader (holding hours) and not a long-term investor (holding months or years). You are looking for a setup that is about to move, entering close to the base, and exiting near the peak of that swing.

In IHSG specifically, swing trading works well because:

1. **IDX discloses broker-level transaction data daily.** Almost no other market in the world shows you exactly which institutions are buying or selling every stock every day. This is an information edge you cannot get in US or European markets.
2. **Foreign institutions telegraph their intent.** When a foreign broker accumulates consistently over 5–10 days, a price move almost always follows. The data exists — most retail traders just don't read it.
3. **IHSG has pronounced institutional cycles.** Large funds rotate sector by sector. When a sector is in favor, every major stock in it gets accumulated before moving. The accumulation screen catches this early.
4. **Volatility is manageable.** IHSG stocks typically trend for 10–20 days before reversing, giving enough time to position and exit without needing tick-by-tick precision.

The workflow below uses every relevant feature in this application, in the order you should use them.

---

## The Full Swing Trade Workflow

```
DAILY ROUTINE
─────────────
Phase 1 → Update data         saham update
Phase 2 → Find candidates     saham screen accumulation --multi
Phase 3 → Confirm setup       saham risk + saham indicators + saham compute ATR
Phase 4 → Check sentiment     saham sentiment
Phase 5 → Time the entry      saham screen pre-open
Phase 6 → Validate thesis     saham backtest
─────────────────────────────────────────────────────────────────────
Repeat daily until exit signal appears
```

---

## Phase 1 — Update Your Data

```bash
saham update --universe lq45
# or for a broader universe:
saham update --universe idxcomp100
```

**Why this must come first, every day:**
The screener, risk assessment, and indicators all read from a local SQLite database (`data.db`). If you skip the update, you are making decisions on yesterday's data — or worse, data from last week. Foreign accumulation can reverse in a single day. An institution that bought 7 days in a row can switch to selling on day 8. You need today's data.

After the first full download (~90 seconds for LQ45), subsequent daily updates take ~5–10 seconds because the system only fetches new data since your last run (incremental updates).

**Update output to watch:**
```
  [  1/45] BBCA   candles=fresh  broker=fresh    ← already current
  [  2/45] BBRI   candles=+1d    broker=+1d      ← fetched today's data
  [  3/45] BMRI   candles=ERR:   broker=+1d      ← candle fetch failed, re-run
```

If you see `ERR:` for several tickers, re-run the update. This is usually a rate-limit from Yahoo Finance and resolves on the second run.

---

## Phase 2 — Find Candidates

```bash
# Step 2a: Multi-window overview — your daily starting point
saham screen accumulation --universe lq45 --multi

# Step 2b: Narrow to highest conviction
saham screen accumulation --universe lq45 --multi --min-score 50

# Step 2c: Surface coiled spring setups
saham screen accumulation --universe lq45 --squeeze-only

# Step 2d: Only where foreigners are defending (underwater positions)
saham screen accumulation --universe lq45 --vwap-only --min-score 50
```

**Why multi-window is the right starting view:**

A single 7-day window tells you what happened this week. But a stock that scores 75 on 7d, 72 on 30d, and 68 on 90d is a fundamentally different trade from one that scores 75 on 7d and 15 on 90d.

| Pattern | Meaning | Trade quality |
|---|---|---|
| `sustained` | Institutions have been building for months | Highest conviction — the position is large |
| `building` | Acceleration in recent weeks | Good — momentum is increasing |
| `fresh rotation` | Only this week | Needs confirmation — may be noise |
| `coiled spring` | Accumulation + BB squeeze | Urgency — compressed, ready to break |
| `long-term only` | Was accumulating months ago, not now | Skip — they may already be exiting |

**What you are looking for at this stage:**
A shortlist of 3–5 tickers that score ≥ 60 on at least two windows, ideally `sustained` or `coiled spring`. Do not act yet. This is your candidate list for Phase 3.

**Reading the key columns:**

- **STREAK**: 5+ consecutive buy days is the minimum for high-conviction swing. Under 3 days needs more time.
- **VWAP_DISC positive**: Foreigners are underwater and motivated to defend. This creates a price floor. A positive VWAP_DISC means there is a large buyer who will absorb selling pressure beneath their average buy price.
- **FLOW% > 15%**: Foreigners are dominating volume. A stock where foreigners are 25% of daily turnover as net buyers is one they control. Price goes where they take it.
- **BB%ILE ≤ 20% (green)**: The price channel has compressed. Energy is building. When this releases, moves are sharp and fast. The lower the percentile, the more compressed.

---

## Phase 3 — Confirm the Setup

For each candidate from Phase 2, run the risk assessment and key indicators.

### 3a. Full Technical Risk Assessment

```bash
saham risk BBRI --profile balanced
saham risk BBRI --all                        # see all three profiles side by side
saham risk BBRI --profile balanced --trend   # include trend direction analysis
```

**Why risk assessment before entry:**
The accumulation screen tells you foreigners are buying. The risk assessment tells you *what the chart looks like*. You want both signals aligned:
- Foreigners buying (Phase 2) + chart technically sound (Phase 3) = high-probability setup
- Foreigners buying + chart technically broken = proceed with caution

What the risk command evaluates:
- **RSI** — are you entering at a sensible level or chasing an overbought stock?
- **SMA20/SMA50** — is the stock above or below key moving averages?
- **MACD** — is momentum turning positive? A bullish MACD crossover during foreign accumulation is a very strong signal.
- **Bollinger Bands** — is the stock near the lower band (good entry) or upper band (overextended)?
- **Overall verdict** — the profile (conservative/balanced/aggressive) gives a structured risk rating

**Reading the profiles:**
- `conservative` — requires more confirmations, smaller position sizing implied
- `balanced` — standard assessment, good for most swing trades
- `aggressive` — fewer requirements, higher risk/reward

Start with `--profile balanced`. If it flags caution, investigate why before entering.

### 3b. Volatility — Size Your Stop with ATR

```bash
saham compute ATR BBRI --period 14
```

**Why ATR is critical for swing trading:**
ATR (Average True Range) measures how many rupiah a stock typically moves in a single day. This is the only correct basis for setting a stop loss.

If ATR = Rp 150 per share and you set a stop 50 below your entry, you will get stopped out by normal daily noise before the move happens. If ATR = Rp 150, your stop should be at least 1.5–2× ATR below entry (Rp 225–300).

**Stop loss formula for swing trades:**
```
Stop loss distance = 1.5 × ATR14
Stop loss price    = entry price − stop loss distance
Position size      = (capital × risk %) / stop loss distance
```

Example: Stock at Rp 5,000, ATR = Rp 150, you risk 2% of Rp 100M capital:
```
Stop distance = 1.5 × 150 = Rp 225
Stop price    = 5,000 − 225 = Rp 4,775
Capital risk  = 100,000,000 × 2% = Rp 2,000,000
Position size = 2,000,000 / 225 = 8,888 shares ≈ 88 lots
```

This is the only principled way to size a position. Never use a fixed percentage like "I'll cut if it drops 5%" — 5% on a volatile stock is just noise, while 5% on a stable stock is a genuine breakdown.

### 3c. Momentum Indicators

```bash
saham indicators BBRI --sma 20 --ema 20 --rsi 14
saham compute FOREIGN_FLOW BBRI               # rolling 3-day net foreign flow
```

**SMA20**: The most watched moving average on IDX. Price reclaiming SMA20 from below, during active foreign accumulation, is a textbook swing entry signal. The average buy gets a boost from both technical and flow confirmation.

**EMA20**: Reacts faster than SMA. Use it to spot momentum shifts earlier. If EMA20 > SMA20 and both are rising, momentum is building.

**FOREIGN_FLOW (rolling 3-day)**: Shows the short-term acceleration of foreign buying. Useful for confirming that the multi-week trend (from Phase 2) is still active today. If the 3-day flow is turning negative while the 30-day is still positive, the trade is weakening.

---

## Phase 4 — Add Context with Sentiment

```bash
saham sentiment BBRI --days 7
saham sentiment BBRI --days 7 --max 30
saham sentiment BBRI --ai-classify --provider claude    # AI classification if enabled
```

**Why sentiment matters for swing trades:**
Foreign institutions do not accumulate randomly. They have thesis. Before a stock moves, there is often a catalyst — an earnings beat, a sector tailwind, a regulatory change, a commodity price move (important for miners, plantations, energy stocks).

Sentiment analysis reads recent news headlines and classifies them as positive, negative, or neutral. What you are looking for:

- **Positive sentiment + accumulation** = thesis confirmed. Both smart money and news are aligned.
- **Neutral sentiment + accumulation** = quiet accumulation. Often the strongest setup — they are building before the news breaks.
- **Negative sentiment + accumulation** = contrarian buy. Institutions are buying the fear. High risk but high reward if they are right.
- **Negative sentiment + no accumulation** = avoid. Smart money agrees the news is bad.

**The most dangerous scenario for a swing trade:** entering on positive news (sentiment is great, stock already spiked) with no foreign accumulation. This is retail FOMO, not institutional positioning. The stock often reverses as institutions sell into retail enthusiasm.

---

## Phase 5 — Time the Intraday Entry

```bash
# Before market opens: get your action plan
saham screen pre-open

# After extracting data from Stockbit (if your candidate appears in morning movers):
saham screen pre-open \
  --movers-json '[{"ticker":"BBRI","iev":180000}]' \
  --order-books-json '{"BBRI":{"price":4800,"volume":300000}}'
```

**Why the pre-open screen is the last step, not the first:**
The pre-open screener looks at morning movers (stocks with high IEV — Intraday Expected Volume) and order book depth. It answers: "given that I already want to own BBRI as a swing trade, what is the best entry price this morning?"

Using it without Phase 2 (accumulation screening) first means you are chasing whatever happened to move overnight — not necessarily your pre-identified swing candidate.

**The entry decision from pre-open:**
1. Does your candidate appear in the morning movers? Good — there is fresh activity.
2. Where is the largest bid in the order book? Enter one tick above the largest bid — this is where real buying support sits. The large bid absorbs selling and acts as a floor.
3. Place your stop at 1.5× ATR below your entry (from Phase 3b), not below the bid level.

**If your candidate does NOT appear in the morning movers:**
This is fine. It means the stock is quiet. You can enter via a limit order at or slightly below the previous close. Quiet accumulation days often produce better entry prices than noisy gap-up days.

---

## Phase 6 — Validate Your Thesis Historically

```bash
saham backtest BBRI --strategy foreign-accumulation --capital 100000000
saham backtest BBRI --strategy rsi-momentum --capital 100000000
saham backtest BBRI --strategy rsi-momentum --start 2023-01-01 --end 2024-01-01 --verbose
```

**Why backtest before committing capital:**
Before entering a trade, check whether this strategy has historically worked on *this specific stock*. Not all IHSG stocks behave the same way under the same strategy. A mining stock (ADRO, HRUM) behaves differently than a bank (BBCA, BBRI) under the same accumulation pattern.

What to look for in backtest results:
- **Win rate > 55%**: The strategy has a positive edge on this stock.
- **Average win / average loss > 1.5**: You make more on winners than you lose on losers.
- **Maximum drawdown**: The worst single losing streak. If this exceeds your emotional tolerance, reduce position size.

If the backtest shows this stock has historically *not* responded to the accumulation signal (low win rate), treat the current signal with extra caution — require more confirmations from Phase 3.

---

## Putting It All Together — Example Daily Workflow

```bash
# Morning routine (~10 minutes before market opens)

# 1. Update data
saham update --universe lq45

# 2. Find today's candidates
saham screen accumulation --universe lq45 --multi --min-score 50

# Suppose BBRI shows: 7d=74.1 | 30d=68.3 | 90d=52.0 | sustained | DOWN

# 3. Confirm the setup
saham risk BBRI --profile balanced --trend
saham compute ATR BBRI --period 14               # e.g. ATR = Rp 75

# 4. Context check
saham sentiment BBRI --days 7

# 5. Check for morning catalyst
saham screen pre-open
# If BBRI appears → extract order book, find largest bid

# 6. Entry decision
# Entry: Rp 4,825 (one tick above largest bid at 4,800)
# Stop:  Rp 4,713 (entry − 1.5 × ATR = 4,825 − 112)
# Target: Rp 5,050 (entry + 3 × ATR = swing target for risk/reward > 2:1)
# Size: (capital × 2%) / 112 lots

# 7. Optional: validate the thesis
saham backtest BBRI --strategy foreign-accumulation --capital 100000000
```

---

## Exit Signals

The current application identifies entries. Watch for these manual exit signals during the hold:

| Signal | Action |
|---|---|
| STREAK drops to 0 (a sell day breaks the run) | Warning — watch closely, may be reversal |
| VWAP_DISC turns negative (foreigners now in profit) | Weaken in motivation — consider tightening stop |
| RSI > 70 (overbought) | Take partial profit or trail stop |
| Price > SMA20 and RSI > 65 | Target zone — consider full exit |
| Price hits 3× ATR above entry | Close position — swing is likely complete |
| Accumulation score drops below 40 (run `screen accumulation` daily) | Exit — the thesis has changed |

The discipline is to check `saham screen accumulation` on your open positions every day, not just at entry. If a stock was `sustained` yesterday and drops to `weak` today (streak broke, FLOW% dropped), the institutional support is weakening. Do not hold without that support.

---

## Top 3 Recommendations to Enrich Swing Trading in This Application

These are the highest-impact additions that would close the gap between what the app does today and a complete swing trade system.

---

### Recommendation #1 — Position Sizing Calculator (`saham size`)

**The gap:** Every swing trade requires three numbers: entry price, stop price, and position size. The app currently gives you ATR (to calculate stop distance) but no command to produce the final position size from your capital and risk %.

**Why it matters:** Under-sizing means you leave money on the table. Over-sizing means one bad trade blows up your capital. The only correct sizing comes from: `(capital × risk%) / (stop distance × 100)` using ATR as the stop input. This needs to be automated — doing it in your head under time pressure leads to errors.

**What it would look like:**
```bash
saham size BBRI --capital 100000000 --risk-pct 2 --entry 4825
# Output:
# ATR (14d):     Rp 75
# Stop distance: Rp 112  (1.5 × ATR)
# Stop price:    Rp 4,713
# Target (2:1):  Rp 5,049  (entry + 2 × stop distance)
# Position:      89 lots  (Rp 21.5M)
# Risk:          Rp 1.99M (1.99% of capital)
```

This closes the loop from signal (Phase 2) → sizing (Phase 3) → entry (Phase 5) in a single command.

---

### Recommendation #2 — Watchlist with Daily Change Tracking (`saham watch`)

**The gap:** There is no way to track your shortlist day over day. A stock identified as a `sustained` candidate on Monday may show `streak broke` by Wednesday. Without daily comparison, you have to manually re-run the full screen and remember previous states.

**Why it matters:** The best swing setups evolve over days. A stock in early accumulation (score 45, streak 2d) might grow into a strong setup (score 72, streak 6d) 5 days later. Conversely, a position you are holding might be signalling deterioration that you miss because you are not tracking it. The watchlist makes the signal *temporal* — you see trends, not just snapshots.

**What it would look like:**
```bash
saham watch add BBRI TLKM GOTO        # add to personal watchlist
saham watch                           # show daily snapshot with change vs yesterday

# Output:
# TICKER   SCORE  Δ     STREAK  Δ    VWAP_DISC  BB%ILE  STATUS
# BBRI      74.1  +3.2    5d   +1d    +8.4%      18%    ↑ building
# TLKM      68.3  -1.1    3d    0d    +2.1%      44%    → stable
# GOTO      55.0  -8.4    0d   -4d    -0.3%       —     ↓ streak broke

saham watch remove GOTO               # GOTO's streak broke — remove from list
```

The `↓ streak broke` alert on GOTO is the kind of signal that prevents you from holding a position that has lost its institutional support.

---

### Recommendation #3 — Exit Signal Monitor (`saham screen exit`)

**The gap:** The application is entirely focused on finding entries. There is no systematic way to know when a swing trade is over. Currently, an investor manually checks RSI, VWAP_DISC, and streak every day for each open position.

**Why it matters:** Exits are harder than entries. Most swing trade losses come from not exiting when the thesis changes — holding too long because the stock "might recover." A systematic exit signal based on the same signals used for entry removes emotion from this decision.

**Exit conditions to flag:**
1. Streak drops to 0 (sell day appeared — institutional support wavered)
2. VWAP_DISC crosses negative (foreigners are now in profit, motive to defend is gone)
3. RSI > 70 (target zone, consider taking profit)
4. Score drops below 40 from a high level (thesis deteriorated)
5. FLOW% drops below 5% (institutions stepped back from volume dominance)

**What it would look like:**
```bash
saham screen exit --watchlist         # check all watched positions for exit signals

# Output:
# TICKER   ENTRY    ENTRY_SCORE  TODAY_SCORE  SIGNAL
# BBRI     4825     74.1         71.3         ✓ hold — still accumulating
# TLKM     3100     68.3         38.1         ⚠ EXIT — score collapsed (was 68, now 38)
# GOTO     8200     72.0         45.5         ⚠ EXIT — streak broke + VWAP turned negative
```

When `EXIT` appears, the system explains which condition triggered it. This makes the exit decision systematic rather than emotional, consistent with the same data-driven approach used at entry.

---

> These three additions — position sizing, watchlist tracking, and exit signals — complete the swing trade loop. The entry side (Phases 1–6) is already strong. The missing pieces are all on the trade management side: how much to buy, how to track it, and when to sell.
