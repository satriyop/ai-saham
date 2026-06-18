# Opening Session Learning Loop

A daily 5-step learning cycle for opening scalping on IDX.
Closes the feedback gap between pre-open predictions and actual market outcomes.

## Motivation

The `saham trade intraday pre-open` screener produces deterministic predictions
(gap %, entry range, ATR stop) for stocks moving in the 08:45–08:57 WIB pre-open
window. But without measuring whether those predictions were correct, thresholds
drift and false negatives go undetected.

This workflow captures the feedback loop: predict → track → measure → tune.

## Data Flow

### Directory Structure

```
data/opening/
└── YYYYMMDD/
    ├── snapshot.json         # Step 1: predictions at 08:57
    ├── track_HHMM.json       # Step 2: orderbook snapshots
    ├── grade.json            # Step 3: accuracy report
    ├── prompt.md             # Step 4: AI prompt
    ├── tune.json             # Step 5: structured AI recommendations
    └── tune.md               # Step 5: human-readable AI recommendations
```

### Snapshot Format

```json
{
  "date": "2026-06-17",
  "timestamp": "2026-06-17T08:57:00+07:00",
  "regime": "SIDEWAYS",
  "candidates": [
    {
      "ticker": "BBCA",
      "iev": 591840000000,
      "iep": 6400,
      "prev_close": 6225,
      "gap_pct": 2.81,
      "trend": "NEUTRAL",
      "verdict": "SKIP",
      "entry_range": [6017, 6533],
      "stop_distance": 208,
      "reason_codes": ["GAP_TOO_HIGH", "TREND_NEUTRAL"]
    }
  ]
}
```

### Track Format

```json
{
  "timestamp": "2026-06-17T09:00:00+07:00",
  "tickers": [
    {
      "ticker": "BBCA",
      "bid_price": 6375,
      "bid_volume": 15000,
      "offer_price": 6400,
      "offer_volume": 20000,
      "gap_pct": 2.81,
      "in_range": true,
      "bid_pressure_ratio": 0.42,
      "depth_ratio_5": 1.15,
      "fnet_intraday": 12500000000,
      "fbuy_intraday": 87500000000,
      "fsell_intraday": 75000000000,
      "iep": 6400,
      "broker_signal": {
        "absorption_ratio": 0.67,
        "dominant_side": "buy",
        "institutional_net_lot": 1250,
        "top_brokers": [
          {"broker": "MANDIRI SEKURITAS", "side": "buy", "volume": 50000},
          {"broker": "BRI DANAREKSA", "side": "sell", "volume": 35000}
        ]
      }
    }
  ]
}
```

Order book depth fields (`bid_pressure_ratio`, `depth_ratio_5`, `fnet_intraday`,
`fbuy_intraday`, `fsell_intraday`, `iep`) are always captured — no flag needed.
They come from Stockbit's full-depth orderbook endpoint (20+ price levels).

`broker_signal` is present only when `--broker-confirm` is used during `track`.
It captures real-time institutional absorption from Stockbit's running trade API.

### Grade Format

```json
{
  "date": "2026-06-17",
  "regime": "SIDEWAYS",
  "entries": { "correct": 1, "total": 5 },
  "gap_band": { "correct": 3, "total": 5 },
  "trend": { "correct": 3, "total": 5 },
  "stop_distance": { "adequate": 5, "total": 5 },
  "overall_grade": "C",
  "per_ticker": [
    {
      "ticker": "BBCA",
      "verdict": "SKIP",
      "actual_open": 6400,
      "in_entry_range": true,
      "gap_band_correct": true,
      "trend_correct": false,
      "stop_adequate": true,
      "tags": ["FALSE_NEGATIVE"]
    }
  ]
}
```

## Step-by-Step

### Step 1: Snapshot (08:57 WIB)

Captures pre-open predictions after NCP locks:

```bash
saham trade opening snapshot
```

**What happens:**
1. Runs the pre-open screener with movers from IDX/Stockbit
2. Computes gap %, entry range, ATR-based stop for each candidate
3. Classifies trend (BULLISH/NEUTRAL/BEARISH)
4. Saves deterministic verdict with reason codes
5. Writes to `data/opening/YYYYMMDD/snapshot.json`

**Manual run with historical date:**
```bash
saham trade opening snapshot --force --date 2026-06-17
```

### Step 2: Track (09:00–09:30 WIB)

Checks full-orderbook depth every 5 minutes after opening auction:

```bash
saham trade opening track
```

**What happens:**
1. Fetches Stockbit full-depth orderbook (20+ levels): `bid_pressure_ratio`, `depth_ratio_5`
2. Captures live foreign net for the session: `fnet_intraday`, `fbuy_intraday`, `fsell_intraday`
3. Computes current gap % vs previous close
4. Checks if price is inside/outside predicted entry range
5. Optionally fetches real-time running trade ticks via `--broker-confirm`
6. Saves per-interval snapshot to `data/opening/YYYYMMDD/track_HHMM.json`

Order book depth and foreign net are always captured (no flag needed). The
`bid_pressure_ratio` measures total bid lots vs (bid + offer) across ALL levels,
not just top-of-book — institutional bids often sit 2–3 ticks below last price.

**With broker attribution (requires Stockbit login):**
```bash
saham trade opening track --broker-confirm
```
Embeds institutional absorption ratio, dominant side, and net lot per ticker
from Stockbit's running trade API. Data appears as `broker_signal` in track JSON.

**Manual run with specific tickers:**
```bash
saham trade opening track --force BBCA BBRI BMRI
```

### Step 3: Grade (09:30+ WIB)

Produces deterministic accuracy report from snapshot + track data:

```bash
saham trade opening grade
```

**Metrics computed:**

| Metric | What it measures | Grade scale |
|--------|-----------------|-------------|
| Entry range hit-rate | % of tickers opening inside predicted range | A (>80%) → F (<40%) |
| Gap band accuracy | Was the ATR band correctly calibrated? | A (>80%) → F (<40%) |
| Stop distance adequacy | Were stops wide enough to avoid false exits? | A (100%) → F (<80%) |
| Trend classification | BULLISH/NEUTRAL/BEARISH vs actual move | A (>80%) → F (<40%) |
| Overall | Weighted composite | A (≥90%) → F (<50%) |

If order book data was captured (always-on), grade additionally reports:
- `ob_bid_pressure_T0`: bid pressure ratio at first track interval
- `ob_bid_pressure_T5`: bid pressure ratio at last track interval  
- `ob_bid_momentum`: change in bid pressure over the tracking window
- `ob_fnet_T0`: foreign net at first track interval (IDR)
- `ob_fnet_latest`: foreign net at last track interval (IDR)

The per-ticker breakdown tags critical errors:
- `FALSE_NEGATIVE`: verdict was SKIP but stock opened in entry range
- `FALSE_POSITIVE`: verdict was ENTER/WAIT but stock opened outside range
- `TREND_MISCLASSIFIED`: trend direction was wrong
- `STOP_TOO_TIGHT`: price crossed stop within 5 minutes of open

### Step 4: Prompt

Generates an AI prompt from the session data:

```bash
# Save to file
saham trade opening prompt

# Print to stdout (pipe to clipboard)
saham trade opening prompt --print | pbcopy
```

The prompt includes:
- Today's date and market regime
- Per-ticker predictions (gap %, entry range, verdict)
- Actual opening prices and track data
- Grade metrics with per-ticker breakdown
- Current config file (`config/pre_open_screener.yaml`)
- Explicit request: "What thresholds should I change?"

### Step 5: Tune

Calls DeepSeek with the grade + config to get actionable tuning recommendations:

```bash
# Uses DEEPSEEK_API_KEY from environment
saham trade opening tune

# Explicit key
saham trade opening tune --api-key sk-...
```

**What you get back:**
- Recommended threshold changes with before/after values
- Per-ticker tuning if patterns emerge (e.g., "BBCA always gap 2-3%, raise BULLISH threshold")
- Updated config snippet ready to copy-paste
- Rationale for each recommendation

**Example output:**
```yaml
# Recommended changes to config/pre_open_screener.yaml
thresholds:
  bull_gap_min: 0.5          # was 1.0 — captured more entries
  neutral_gap_max: 3.0       # was 2.0 — BBCA no longer false negative
  trend:
    bull_min_score: 45       # was 50 — more balanced in SIDEWAYS regime
```

## Command Reference

| Command | Timing | Purpose | Output file |
|---------|--------|---------|-------------|
| `saham trade opening snapshot` | 08:57 | Pre-open predictions | `snapshot.json` |
| `saham trade opening track` | 09:00–09:30 | 5-min full-depth orderbook + foreign net + opt-in broker attribution | `track_HHMM.json` |
| `saham trade opening grade` | 09:30+ | Accuracy report (incl. bid pressure momentum + institutional absorption) | `grade.json` |
| `saham trade opening prompt` | anytime | AI prompt | `prompt.md` |
| `saham trade opening tune` | anytime | Config recommendations | `tune.json` + `tune.md` |

| Flag | Applies to | Effect |
|------|-----------|--------|
| `--broker-confirm` | `track` | Fetch running trade ticks from Stockbit for institutional absorption analysis (~2s/ticker) |

Order book depth and foreign net are always captured — no flag required.

## Auto-Window

All commands auto-detect the current market phase:

| Current time (WIB) | Behavior |
|--------------------|----------|
| Before 08:45 | "Market not open yet" |
| 08:45–08:57 | Pre-open in progress → run normally |
| 08:57–09:15 | Snapshot available → track ready |
| 09:15–09:30 | Track in progress → skip snapshot |
| 09:30–10:00 | Track complete → grade + prompt available |
| After 10:00 | Full cycle complete → tune available |

Use `--force` to bypass auto-window for testing or historical runs.

## Integration with Other Workflows

### → `saham trade intraday`

The opening snapshot uses the same screener under the hood. Results are
independent: `trade intraday` for manual decision-making, `trade opening` for
automated learning loop.

### → `data/opening/` + Journals

Opening session data is stored standalone. For trade journal integration, use:

```bash
saham trade intraday log      # paper trade log from opening signals
saham trade intraday outcome  # record actual outcome
```

### → `docs/deepseek_preopen_recommendation_170626.md`

The June 17 post-mortem documents the first full run of this workflow. See it for
a complete example of what the learning loop produces, including the BBCA false
negative case study.

## Tuning Guidelines

| Signal | If accuracy is low... | Try adjusting |
|--------|----------------------|---------------|
| False negatives (missed entries) | Lower BULLISH gap threshold, widen entry range multiplier | `bull_gap_min`, `range_atr_mult` |
| False positives (bad entries) | Raise BULLISH threshold, require higher trend score | `bull_gap_min`, `trend.bull_min_score` |
| Stops hit immediately | Increase ATR multiplier | `stop_atr_mult` |
| Trend wrong too often | Adjust regime-specific trend thresholds | `trend.*` per-regime values |

## Accuracy Tracking Over Time

The learning loop builds a history of grades that reveals systematic weaknesses:

```
data/opening/
├── 2026-06-17/
│   ├── grade.json           # C — BBCA false negative
│   └── tune.md
├── 2026-06-18/
│   ├── grade.json           # B — after tuning BULLISH threshold
│   └── tune.md
└── 2026-06-19/
    ├── grade.json           # B+ — continuing improvement
    └── tune.md
```

Over 20+ sessions, patterns emerge:
- "BBCA always gaps 2-3% → raise BULLISH threshold"
- "BUMI gaps >10% every time → SKIP is always correct"
- "BMRI opens flat → WATCH with trend score filter"
