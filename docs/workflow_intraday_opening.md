# Opening Session Learning Loop

A daily 5-step learning cycle for opening scalping on IDX.
Closes the feedback gap between pre-open predictions and actual market outcomes.

## Motivation

The `saham screen pre-open` screener produces deterministic predictions
(gap %, entry range, ATR stop) for stocks moving in the 08:45–09:00 WIB pre-open
window (NCP snapshots taken at ~08:57 within the [08:56, 09:00) lock window). But without measuring whether those predictions were correct, thresholds
drift and false negatives go undetected.

This workflow captures the feedback loop: predict → track → measure → tune.

## Data Flow

### Directory Structure

```
data/opening/
└── YYYYMMDD/
    ├── ops_session.json      # Same-run ops export from research pre-open capture
    ├── track_HHMM.json       # Orderbook snapshots (research pre-open track)
    ├── grade.json            # Session scorecard (research pre-open grade; DB decisions)
    ├── open_30m_labels.json  # Corpus outcomes (research pre-open labels)
    ├── prompt.md             # AI prompt (research pre-open prompt)
    ├── tune.json             # AI recommendations (research pre-open tune)
    └── tune.md
```

**Decision authority:** SQLite `candidate_observations` via
`saham research pre-open capture` only. Day files are packaging / outcomes /
scorecards — not a second scorer.

### Snapshot Format

```json
{
  "date": "2026-06-17",
  "captured_at": "2026-06-17T08:57:00+07:00",
  "collection_started_at": "2026-06-17T08:56:00+07:00",
  "decision_at": "2026-06-17T08:57:00+07:00",
  "capture_phase": "NCP_LOCKED",
  "capture_valid_for_opening_prediction": true,
  "capture_confidence": "HIGH",
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
      "opening_price": 6400,
      "opening_price_source": "order_book_lastprice",
      "opening_price_confidence": "MEDIUM",
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

Opening price resolution fields (`opening_price`, `opening_price_source`,
`opening_price_confidence`) are also always captured. Sources include:
- `order_book_lastprice` — last traded price from Stockbit order book (MEDIUM confidence)
- `top_of_book_midpoint` — midpoint of best bid/offer (LOW confidence)
- `manual_entry` — user-supplied via `--opening-json` (HIGH confidence)

`broker_signal` is present only when `--broker-confirm` is used during `track`.
It captures real-time institutional absorption from Stockbit's running trade API.

### Grade Format

```json
{
  "date": "2026-06-17",
  "capture_phase": "NCP_LOCKED",
  "capture_valid_for_opening_prediction": true,
  "capture_confidence": "HIGH",
  "regime": "SIDEWAYS",
  "data_quality": {
    "capture_phase": "NCP_LOCKED",
    "capture_valid_for_opening_prediction": true,
    "capture_confidence": "HIGH",
    "high_confidence_price_count": 3,
    "medium_confidence_price_count": 2,
    "low_confidence_price_count": 0,
    "invalid_snapshot": false
  },
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
      "opening_price_source": "order_book_lastprice",
      "opening_price_confidence": "MEDIUM",
      "capture_phase": "NCP_LOCKED",
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

### Step 1: Capture decisions (08:57 WIB)

Sole decision write for the opening learning loop:

```bash
saham research pre-open capture
```

**What happens:**
1. Runs the full pre-open workflow (screen + signal/risk/TradeSetup pipeline)
2. **Saves decisions** to SQLite `candidate_observations` (learning authority)
3. Writes same-run ops packaging: `data/opening/YYYYMMDD/ops_session.json`
4. Writes trade-confirm sidecar for `saham trade confirm`

Capture fails closed unless the direct live provider completes its entire
timezone-aware collection window inside the requested session's NCP interval.
Manual mover payloads and saved snapshots remain discovery data and cannot be
written as authoritative pre-open decisions.

### Step 2: Track (09:00–09:30 WIB)

Checks full-orderbook depth every 5 minutes after opening auction:

```bash
saham research pre-open track
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
saham research pre-open track --broker-confirm
```
Embeds institutional absorption ratio, dominant side, and net lot per ticker
from Stockbit's running trade API. Data appears as `broker_signal` in track JSON.

**Manual run with specific tickers:**
```bash
saham research pre-open track --force BBCA BBRI BMRI
```

### Step 3: Grade (09:30+ WIB)

Produces deterministic accuracy report from snapshot + track data:

```bash
saham research pre-open grade
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
saham research pre-open prompt

# Print to stdout (pipe to clipboard)
saham research pre-open prompt --print | pbcopy
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
saham research pre-open tune

# Explicit key
saham research pre-open tune --api-key sk-...
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
| `saham research pre-open capture` | ~08:58 | Sole decision write | DB observations + `ops_session.json` |
| `saham research pre-open track` | 09:00–09:30 | 5-min full-depth orderbook + foreign net + opt-in broker attribution | `track_HHMM.json` |
| `saham research pre-open grade` | 09:30+ | Accuracy report (incl. bid pressure momentum + institutional absorption) | `grade.json` |
| `saham research pre-open prompt` | anytime | AI prompt | `prompt.md` |
| `saham research pre-open tune` | anytime | Config recommendations | `tune.json` + `tune.md` |

| Flag | Applies to | Effect |
|------|-----------|--------|
| `--broker-confirm` | `track` | Fetch running trade ticks from Stockbit for institutional absorption analysis (~2s/ticker) |
| `--allow-invalid-snapshot` | `tune` | Allow AI tuning from low-confidence or out-of-window snapshot data |

Order book depth and foreign net are always captured — no flag required.

## Auto-Window

All commands auto-detect the current market phase:

| Current time (WIB) | Phase | Behavior |
|--------------------|-------|----------|
| Before 08:45 | OUT_OF_SESSION | "Market not open yet" |
| 08:45–08:56 | PRE_NCP | Capture available (MEDIUM confidence) |
| 08:56–09:00 | NCP_LOCKED | Capture with HIGH confidence |
| 09:00–09:30 | OPEN | Track ready |
| 09:30–10:00 | POST_OPEN | Grade + prompt available |
| After 10:00 | POST_OPEN | Full cycle complete → tune available |

Use `--force` to bypass auto-window for testing or historical runs.

Snapshot confidence drives behavior:
- `HIGH` (NCP_LOCKED) — normal operation, tuning allowed
- `MEDIUM` (PRE_NCP) — data valid but may shift before NCP locks
- `LOW` (OPEN/POST_OPEN) — snapshot not valid for opening prediction; `tune` requires `--allow-invalid-snapshot`

## Integration with Other Workflows

### Command-family consistency

| Family | Role |
|--------|------|
| `screen pre-open` | **Live** display — no observation corpus write |
| `research pre-open capture` | **Sole save-decisions write** + ops_session export |
| `research pre-open track` / `grade` / `prompt` / `tune` | **Same-day ritual** after capture |
| `research pre-open labels` | **Outcomes** (`open_30m`) from saved decisions + tracks |

Do not auto-write observations from live `screen`. There is no top-level `learn` group.

### → `saham trade`

Paths stay separate: `screen pre-open` for live display; `research pre-open capture`
for decisions (and confirm sidecar); track/grade under `research pre-open`.

### → `data/opening/` + Journals

Opening session data is stored standalone. For trade journal integration, use:

```bash
saham trade log intraday      # paper trade log from opening signals
saham trade outcome  # record actual outcome
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
