# CLI_README.md - Learning Stock Analysis with AI Saham

> **Progressive guide**: This documentation teaches stock analysis concepts alongside commands. Start from the top if you're new to technical analysis.

---

## 1. Welcome: What Is This Tool?

AI Saham is a **composable stock analysis engine** for the Indonesia Stock Exchange (IDX). It's designed for developers, traders, and fintech teams who want to analyze stocks using technical indicators.

### Core Philosophy

```
"Deterministic analysis first, AI explains second"
```

This tool provides:
- **Rule-based analysis** - Every result is reproducible and explainable
- **Local-first design** - Works offline after initial data fetch
- **Composable indicators** - Combine SMA, EMA, RSI in custom rules
- **Strategy packages** - First-class, versionable, portable strategy artifacts
- **Optional AI** - Get explanations, but never depend on them

### What This Tool Is NOT

- **Not a trading bot** - It analyzes, it doesn't execute trades
- **Not financial advice** - Use as one input in your research
- **Not a black box** - Every decision is traceable and auditable

---

## 2. Quick Start (5 Minutes to First Analysis)

Verify installation and run your first analysis:

```bash
# Step 1: Check installation
saham version

# Step 2: Download stock data
saham data update BBCA --days 365

# Step 3: See risk assessment across all profiles
saham analyze risk BBCA --all

# Step 4: Create and test a strategy
saham strategy init momentum
saham strategy backtest BBCA --strategy momentum

# Step 5: Or create a strategy from natural language!
saham strategy create "RSI oversold strategy" --name my_rsi --provider mock
saham strategy backtest BBCA --strategy my_rsi
```

**What just happened?**
1. `version` - Confirmed the CLI is installed
2. `data update` - Downloaded 1 year of daily price data for Bank Central Asia (BBCA)
3. `analyze risk --all` - Analyzed the stock using 3 different risk tolerance profiles
4. `strategy init` - Created a reusable strategy package
5. `strategy backtest --strategy` - Tested the strategy on historical data
6. `strategy create` - Used AI to generate a complete strategy from natural language

You now have a local copy of BBCA's data and can analyze it offline anytime.

---

## 3. Understanding Stock Data

Before analyzing, you need data. The `data update` command downloads **OHLCV data** (Open, High, Low, Close, Volume) and **broker flow data** (foreign buy/sell) in one pass. See section 21 for the full `data update` reference.

### What is OHLCV?

Each trading day produces these 5 values:

| Field | Meaning | Why It Matters |
|-------|---------|----------------|
| **Open** | First trade price | Shows where market opened |
| **High** | Highest price | Shows buyer strength |
| **Low** | Lowest price | Shows seller pressure |
| **Close** | Last trade price | Most important - where it ended |
| **Volume** | Shares traded | Shows conviction behind moves |

### Batch Update

```bash
# Fetch 1 year of data + broker flow for an entire universe (recommended)
saham data update --universe lq45 --days 365

# Single ticker
saham data update BBCA --days 365

# Use IDX public API directly (no Yahoo)
saham data update BBCA --days 365 --provider idx
```

### Output Explained

```
Fetching BBCA...

Ticker: BBCA
Source: yahoo_finance
Records: 252
Date range: 2024-01-02 to 2025-01-24

Database: /path/to/project/data.db

Latest (2025-01-24):
  Open:        10,575
  High:        10,625
  Low:         10,475
  Close:       10,500
  Volume:      45,234,100
```

- **Records: 252** - About 1 year of trading days (IDX has ~250 trading days/year)
- **Database path** - Where data is cached for offline use

---

## 4. Technical Indicators (Building Understanding)

Technical indicators transform raw price data into actionable signals. AI Saham supports three foundational indicators that form the basis of most trading strategies.

### 4.1 SMA - Simple Moving Average

**What it does:** Smooths out price noise by averaging the last N closing prices.

**Why it matters:**
- Price above SMA → Bullish tendency
- Price below SMA → Bearish tendency
- SMA itself shows trend direction

```bash
# Default: 20-day SMA (approximately 1 month)
saham indicator compute SMA BBCA

# 50-day SMA (medium-term trend)
saham indicator compute SMA BBCA --period 50

# 200-day SMA (long-term trend)
saham indicator compute SMA BBCA --period 200

# SMA on a different price field
saham indicator compute SMA BBCA --field high
```

**Period Guide:**

| Period | Timeframe | Use Case |
|--------|-----------|----------|
| 10 | 2 weeks | Short-term trading |
| 20 | 1 month | Default, general analysis |
| 50 | ~2.5 months | Medium-term trend |
| 200 | ~10 months | Long-term trend, institutional benchmark |

**Reading the Output:**

```
Summary:
  Latest:      10,234.50      # Current SMA value
  Highest:     10,890.00      # Peak during period
  Lowest:       9,456.00      # Trough during period
  Average:     10,123.45      # Average of all SMA values
```

### 4.2 EMA - Exponential Moving Average

**What it does:** Like SMA, but gives more weight to recent prices.

**Why it matters:**
- Reacts faster to price changes than SMA
- Better for active trading (catches reversals sooner)
- **Matches TradingView calculations** - Compare directly with charts

```bash
# Default: 20-day EMA
saham indicator compute EMA BBCA

# Faster EMA for active trading
saham indicator compute EMA BBCA --period 9

# Compare with SMA of same period
saham indicator compute SMA BBCA --period 20
saham indicator compute EMA BBCA --period 20
```

**SMA vs EMA - When to Use Which:**

| Scenario | Better Choice | Why |
|----------|---------------|-----|
| Swing trading | EMA | Faster reaction to reversals |
| Long-term investing | SMA | Less whipsaw on noise |
| Crossover strategies | Both | EMA crosses SMA = signal |

### 4.3 RSI - Relative Strength Index

**What it does:** Measures momentum on a scale of 0-100.

**Why it matters:**
- **> 70:** Overbought - buyers may be exhausted, pullback possible
- **< 30:** Oversold - sellers may be exhausted, bounce possible
- **30-70:** Neutral territory

```bash
# Default: 14-day RSI (industry standard)
saham indicator compute RSI BBCA

# Shorter period = more sensitive
saham indicator compute RSI BBCA --period 7

# Longer period = smoother
saham indicator compute RSI BBCA --period 21
```

**Psychology Behind RSI:**

When RSI > 70:
- Many traders have already bought
- Few buyers left to push price higher
- Often precedes a pullback (but not always!)

When RSI < 30:
- Heavy selling has occurred
- Sellers may be running out of shares to sell
- Often precedes a bounce (but not always!)

**Output Interpretation:**

```
Summary:
  Latest:        65.42         # Current momentum reading
  Highest:       78.90         # Was overbought at some point
  Lowest:        28.45         # Was oversold at some point
  Average:       52.34         # Overall tendency

  Status: NEUTRAL (30 <= RSI <= 70)
```

### 4.4 The `indicator compute` Command - Universal Indicator Computation

Compute **any** indicator - built-in, plugin, or custom formula - for any stock.

```bash
# Compute built-in indicators
saham indicator compute RSI BBCA
saham indicator compute SMA BBCA --period 50

# Compute plugin indicators
saham indicator compute ATR BBCA --period 14

# Compute custom formulas (created via saham indicator create)
saham indicator compute SMOOTH_RSI BBCA --tail 10

# Control output
saham indicator compute EMA BBRI --period 20 --days 180 --tail 50
```

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--period` | `-p` | 14 | Period for the indicator (ignored for formulas) |
| `--days` | `-d` | 365 | Days of data to use |
| `--tail` | `-t` | 30 | Show last N values |
| `--db` | | ./data.db | Database path |

**Output Example:**

```
Computing SMOOTH_RSI for BBCA...

Ticker: BBCA
Indicator: SMOOTH_RSI
Values: 245 (showing last 10)

Date         SMOOTH_RSI
---------------------------
2026-01-15         45.23
2026-01-16         47.89
2026-01-17         42.15
...
2026-01-27         38.72

Summary:
  Latest:        38.72
  Highest:       52.30
  Lowest:        28.45
```

**Use Cases:**
- Debug formula outputs before using in rules
- Verify indicator calculations match TradingView
- Quick analysis without writing rules files
- Explore plugin indicator behavior

### 4.5 Combining Indicators - The `indicator snapshot` Command

**Why combine?** Single indicators can give false signals. When multiple indicators agree, signals are stronger.

```bash
# See all three indicators aligned by date
saham indicator snapshot BBCA

# Custom periods for your strategy
saham indicator snapshot BBRI --sma 50 --ema 50 --rsi 7

# JSON output for programmatic use
saham indicator snapshot BBCA --format json
```

**Reading Combined Output:**

```
Date         SMA            EMA            RSI
-------------------------------------------------
2025-01-24   10,234.50      10,198.75      65.42
2025-01-23   10,221.00      10,189.50      62.18
...
```

**Agreement = Stronger Signal:**

| SMA Trend | EMA Trend | RSI | Interpretation |
|-----------|-----------|-----|----------------|
| Price > SMA | Price > EMA | > 50 | Strong bullish alignment |
| Price < SMA | Price < EMA | < 50 | Strong bearish alignment |
| Mixed | Mixed | ~50 | No clear signal, wait |

---

## 5. Risk Assessment - The `analyze risk` Command

The `analyze risk` command converts indicator values into actionable assessments using rule-based evaluation.

### Three Built-in Profiles

| Profile | RSI Overbought | RSI Oversold | Decision Logic |
|---------|---------------|--------------|----------------|
| **conservative** | > 75 | < 25 | All indicators must agree |
| **balanced** | > 70 | < 30 | Majority rules |
| **aggressive** | > 65 | < 35 | Single indicator can signal |

### Basic Usage

```bash
# Balanced profile (default)
saham analyze risk BBCA

# Conservative for retirement accounts
saham analyze risk BBCA --profile conservative

# Compare all three profiles
saham analyze risk BBCA --all
```

### Choosing the Right Profile

| Your Situation | Recommended Profile | Why |
|----------------|---------------------|-----|
| Long-term investing | conservative | Fewer signals, higher conviction |
| General analysis | balanced | Good starting point |
| Active trading | aggressive | More signals, earlier entries |
| Learning | balanced then --all | See how profiles differ |

### Understanding Risk Levels

The assessment returns one of three levels:

| Level | Meaning | Consider |
|-------|---------|----------|
| **HIGH_RISK** | Indicators suggest elevated risk | Review positions, consider taking profits |
| **MODERATE** | Neutral conditions | Monitor, no urgent action |
| **LOW_RISK** | Favorable conditions | Potential entry point |

**Important:** These are technical signals, not predictions. A "LOW_RISK" stock can still go down!

### Full Output Example

```bash
saham analyze risk BBCA
```

```
Assessing risk for BBCA...

Ticker: BBCA
Profile: balanced
Data Date: 2025-01-24

Indicators:
  SMA(20):      10,234.50
  EMA(20):      10,198.75
  RSI(14):         65.42

---------------------------------------
RISK ASSESSMENT
---------------------------------------

Risk Level:  MODERATE
Confidence:  72/100

Rationale:
  - RSI in neutral range (30-70)
  - Price near moving averages
  - No strong directional signals

---------------------------------------

DISCLAIMER: Analysis only, not trading advice.
```

### Comparing All Profiles

```bash
saham analyze risk BBCA --all
```

```
Profile        Risk Level   Confidence
--------------------------------------
conservative   MODERATE     68/100
balanced       MODERATE     72/100
aggressive     LOW_RISK     65/100
```

**Interpretation:**
- Conservative and balanced agree on MODERATE
- Aggressive sees LOW_RISK (more permissive thresholds)
- When all three agree, signal is stronger

---

## 6. News Sentiment - The `analyze sentiment` Command

Sentiment analysis adds context to price movements by analyzing news headlines.

**Critical Understanding:** Sentiment does NOT affect risk assessment. It's supplementary information only.

### Basic Usage

```bash
# Analyze last 3 days of news (default)
saham analyze sentiment BBCA

# Look back further
saham analyze sentiment BBCA --days 7

# Use AI for classification (more nuanced)
saham analyze sentiment BBCA --ai-classify

# Choose news source
saham analyze sentiment BBCA --news-provider google

# Offline keyword classification
saham analyze sentiment BBCA --no-ai
```

### Options Explained

| Option | Purpose | When to Use |
|--------|---------|-------------|
| `--days 7` | Fetch 7 days of news | Need more context |
| `--max 30` | Limit to 30 headlines | Faster analysis |
| `--ai-classify` | Use AI instead of keywords | Need nuance (e.g., sarcasm) |
| `--news-provider` | News source (composite, google, kontan, cnbc, mock) | Choose source |
| `--no-ai` | Offline keyword classification | No API key, faster |
| `--provider ollama` | Use local Ollama | Privacy, no API key |

### Output Interpretation

```
---------------------------------------
SENTIMENT SNAPSHOT
---------------------------------------

Overall: NEUTRAL
Confidence: 12/20 headlines (60%)

Breakdown:
  Positive:  5 (25%)
  Neutral:   12 (60%)
  Negative:  3 (15%)

Recent Headlines:
  [+] BBCA Reports Strong Q4 Earnings...
  [=] Bank Indonesia Holds Interest Rates...
  [-] Regional Banks Face Margin Pressure...

[Provider: google_news | Classifier: keyword]
```

**Sentiment Symbols:**
- `[+]` Positive - Good news for the stock
- `[=]` Neutral - No clear impact
- `[-]` Negative - Bad news for the stock

### Risk Trend Over Time

Track how risk levels have been evolving:

```bash
# Show risk history for last 20 days
saham analyze risk BBCA --trend 20
```

Output shows the risk level and confidence for each day plus a trend direction (↑ IMPROVING, ↓ DETERIORATING, → STABLE).

### Adding Sentiment to Risk Assessment

```bash
saham analyze risk BBCA --with-sentiment
```

This adds a sentiment section to the risk output, but remember: sentiment is contextual information only and does NOT change the risk level.

### JSON Output

```bash
saham analyze risk BBCA --format json
```

Useful for programmatic consumption or piping to other tools.

### Additional Risk Options

| Option | Purpose |
|--------|---------|
| `--trend N` | Show risk trend over last N days |
| `--format table/json` | Output format |
| `--news-provider` | News source: composite, google, kontan, cnbc |
| `--no-ai` | Disable AI classification for sentiment |

### Sentiment Accuracy Audit

Audit past sentiment predictions against actual price moves:

```bash
saham analyze audit
```

Uses logged sentiment data (stored automatically in SQLite) and checks whether POSITIVE/NEUTRAL/NEGATIVE classifications were correct after 1, 3, and 5 trading days.

---

## 7. Broker Data & Foreign Flow - The `data broker` Command

Foreign investor flow is one of the most watched metrics in the Indonesian market. The `data broker` command suite lets you fetch, cache, and analyze broker summary data.

### Data Providers

Two providers are available for fetching broker/foreign flow data:

| Provider | Auth Required | Data | Best For |
|----------|--------------|------|----------|
| **`idx`** (default) | None | Foreign flow (lots + estimated values), OHLCV, total volume | Quick setup, no auth hassle |
| **`stockbit`** | JWT token (~24h expiry) | Foreign flow (exact values) + top broker breakdown | Per-broker analysis |

The **IDX provider** uses the public idx.co.id API — no registration or token needed. It provides per-stock foreign buy/sell data in lots (values are estimated from volume × closing price).

The **Stockbit provider** provides exact foreign flow values and per-broker breakdowns (top buyers/sellers), but requires a JWT token that expires every ~24 hours.

### Why Foreign Flow Matters in IDX

| Metric | What It Tells You |
|--------|-------------------|
| **Foreign Net Buy** | Foreigners accumulating → often bullish signal |
| **Foreign Net Sell** | Foreigners distributing → potential weakness |
| **Consecutive Buy Days** | Sustained accumulation pattern |
| **Top Brokers** | Which brokers are driving the flow (Stockbit only) |

### Fetching Broker Data

```bash
# Fetch using IDX provider (default - no auth required)
saham data broker fetch BBCA

# Explicitly specify provider
saham data broker fetch BBCA --provider idx
saham data broker fetch BBCA --provider stockbit-session

# Fetch 90 days of history
saham data broker fetch BBRI --days 90

# Specific date range
saham data broker fetch TLKM --start 2024-01-01 --end 2024-06-30

# Force refresh (ignore cache)
saham data broker fetch BBCA --refresh
```

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--days` | `-d` | 30 | Number of days to fetch |
| `--start` | `-s` | — | Start date (YYYY-MM-DD) |
| `--end` | `-e` | — | End date (YYYY-MM-DD) |
| `--refresh` | `-r` | false | Force refresh from provider |
| `--provider` | `-P` | idx | Data provider (idx, stockbit-session) |
| `--db` | | ./data.db | Database path |

### Setting Up Stockbit (Optional)

Only needed if you want per-broker breakdown data (top buyers/sellers). Stockbit now uses **browser session cookies** (Playwright-based) instead of JWT tokens:

```bash
# Install browser automation dependencies
pip install -e ".[browser]"
playwright install chromium

# Step 1: Login via browser (opens a Chromium window)
saham data stockbit login

# The browser stays open until you log in to stockbit.com.
# Once logged in, cookies are saved automatically.
# Use --timeout 300 if you have 2FA.

# Step 2: Check session health
saham data stockbit status

# Step 3: Smoke test the adapter
saham data stockbit test
```

**Note:** Browser sessions may expire. Run `saham data stockbit status` to check, and `saham data stockbit login` to refresh.

### Viewing Foreign Flow

```bash
# Show foreign flow summary
saham data broker flow BBCA

# Last 20 trading days
saham data broker flow BBRI --days 20
```

**Output Example:**

```
Foreign Flow for BBCA (last 10 trading days)
============================================================
Total net flow: 125.50B
Buy days: 7 | Sell days: 3
Consecutive buy days: 4
------------------------------------------------------------
Date         Net Flow       Ratio  Top Buyer  Top Seller
------------------------------------------------------------
2025-01-27       15.20B      3.2%         YP          CC
2025-01-24       22.45B      4.8%         MS          RX
2025-01-23       -8.30B     -1.9%         CC          YP
...
```

**Reading the Output:**
- **Net Flow**: Positive = foreign buying, Negative = foreign selling
- **Ratio**: Foreign flow as % of total trading value
- **Consecutive buy days**: How many days in a row foreigners have been buying

### Viewing Top Brokers

```bash
# Top brokers for latest date
saham data broker top BBCA

# Top brokers for specific date
saham data broker top BBRI --date 2025-01-15
```

**Output Example:**

```
Broker Summary for BBCA on 2025-01-27
======================================================================
Foreign Net Flow: 15.20B (3.2%)
Total Value: 475.00B
----------------------------------------------------------------------

Top Buyers:
Code   Name                 Type     Net Value       Net Lot
YP     Mirae Asset          Foreign       8.50B      850,000
MS     Morgan Stanley       Foreign       4.20B      420,000
CC     Mandiri Sekuritas    Local         2.50B      250,000
...

Top Sellers:
Code   Name                 Type     Net Value       Net Lot
RX     RHB Sekuritas        Foreign      -5.30B     -530,000
DB     Deutsche Bank        Foreign      -3.80B     -380,000
...
```

### Checking Provider Status

```bash
saham data broker status
```

**Output:**
```
IDX provider: Available (public API, no auth required)
Stockbit provider: Configured
  Validating Stockbit token...
  Status: Connected and working

Default provider: idx
```

### Importing Broker Data from CSV

Don't have Stockbit access? Import broker data from any CSV source (RTI exports, manual downloads, spreadsheets):

```bash
# Auto-detect format and import
saham data broker import data.csv

# Preview without importing
saham data broker import data.csv --preview

# Use custom column mapping
saham data broker import data.csv --mapping my_format

# Control error handling
saham data broker import data.csv --on-error skip    # Skip invalid rows (default)
saham data broker import data.csv --on-error fail    # Stop on first error
saham data broker import data.csv --on-error report  # Import valid rows, report all errors
```

**Supported CSV Formats:**

| Format | Description | Required Columns |
|--------|-------------|------------------|
| **Simple** | Aggregate foreign flow | date, ticker, foreign_buy_value, foreign_sell_value |
| **Detailed** | Individual broker transactions | date, ticker, broker_code, broker_type, buy_value, sell_value |

**Simple Format Example:**
```csv
date,ticker,foreign_buy_value,foreign_sell_value,foreign_buy_lot,foreign_sell_lot,total_value,total_lot
2024-01-15,BBCA,50000000000,30000000000,5000,3000,200000000000,20000
```

**Detailed Format Example:**
```csv
date,ticker,broker_code,broker_name,broker_type,buy_lot,sell_lot,buy_value,sell_value
2024-01-15,BBCA,YP,Mirae Asset,FOREIGN,10000,5000,50000000000,25000000000
```

**Custom Column Mappings:**

For non-standard CSV formats, create a YAML mapping file:

```yaml
# ~/.ai-saham/csv_mappings/my_format.yaml
version: 1
name: "my_format"
format: simple

columns:
  date: "Trade Date"           # Your column name
  ticker: "Stock Code"
  foreign_buy_value: "FB Val"
  foreign_sell_value: "FS Val"

transforms:
  date:
    format: "%d/%m/%Y"         # Date format
  foreign_buy_value:
    multiplier: 1000000        # Values in millions
```

**Listing Available Mappings:**

```bash
saham data broker mappings
```

**Output:**
```
Available CSV Mappings:
----------------------------------------
  default (built-in auto-detection)
  rti_export
  stockbit_manual

Use with: saham data broker import data.csv --mapping <name>
```

### Using Foreign Flow in Strategies

Once you've fetched broker data, you can use foreign flow indicators in your strategies:

```yaml
# strategies/foreign-accumulation/strategy.yaml
version: 1
name: "Foreign Accumulation"
description: "Enter when foreigners are consistently buying"

indicators:
  foreign_flow_3d:
    type: FOREIGN_FLOW
    period: 3

  consecutive_buy:
    type: CONSECUTIVE_FOREIGN_BUY
    period: 1

default_outcome: MODERATE

signal_mapping:
  LOW_RISK: ENTER_LONG
  MODERATE: HOLD
  HIGH_RISK: EXIT_LONG

rules:
  - name: strong_accumulation
    priority: 10
    when:
      all:
        - left:
            indicator: foreign_flow_3d
          operator: ">"
          right:
            value: 50000000000  # 50B IDR
        - left:
            indicator: consecutive_buy
          operator: ">="
          right:
            value: 3
    outcome: LOW_RISK
    rationale: "Strong foreign accumulation pattern"

  - name: heavy_distribution
    priority: 10
    when:
      left:
        indicator: foreign_flow_3d
      operator: "<"
      right:
        value: -30000000000  # -30B IDR
    outcome: HIGH_RISK
    rationale: "Heavy foreign selling"
```

**Available Foreign Flow Indicators:**

| Indicator | Description | Example Usage |
|-----------|-------------|---------------|
| `FOREIGN_FLOW` | Rolling sum of foreign net value | `> 50B` over 3 days |
| `FOREIGN_FLOW_RATIO` | Foreign flow as % of total value | `> 5%` average |
| `CONSECUTIVE_FOREIGN_BUY` | Count of consecutive buy days | `>= 3` days |

### Complete Workflow

```bash
# 1. Set up Stockbit browser session when broker-level detail is needed
saham data stockbit login

# 2. Fetch broker data
saham data broker fetch BBCA --days 90

# 3. View the flow
saham data broker flow BBCA

# 4. Use in backtest (requires broker data pre-loaded)
saham strategy backtest BBCA --strategy foreign-accumulation
```

---

## 8. Backtesting - The `strategy backtest` Command

Backtesting lets you test a strategy on historical data before risking real capital.

### How Backtesting Works

1. Replay historical candles chronologically
2. Apply your rules to each candle
3. Generate buy/sell signals
4. Calculate hypothetical returns

### Signal Mapping (Risk Level → Trade Action)

| Risk Level | Trade Action | Meaning |
|------------|--------------|---------|
| LOW_RISK | ENTER_LONG | Buy signal |
| MODERATE | HOLD | Keep current position |
| HIGH_RISK | EXIT_LONG | Sell signal |

### Basic Usage

```bash
# Recommended: Use strategy packages
saham strategy backtest BBCA --strategy momentum
saham strategy backtest BBRI -S momentum --start 2024-01-01 --end 2024-12-31

# Or use explicit path
saham strategy backtest TLKM -S ./strategies/my_strat/strategy.yaml --verbose

# Backward compatible: Use rules file directly
saham strategy backtest BBCA --rules-file config/custom_rules.yaml.example
saham strategy backtest ASII -r rules.yaml --capital 50000000
```

### Key Options

| Option | Purpose | Example |
|--------|---------|---------|
| `--strategy` / `-S` | Strategy name or path (recommended) | `-S momentum` |
| `--rules-file` / `-r` | Rules file (alias for --strategy) | `-r rules.yaml` |
| `--start` | Start date | `--start 2024-01-01` |
| `--end` | End date | `--end 2024-12-31` |
| `--capital` | Initial capital (IDR) | `--capital 50000000` |
| `--verbose` | Show each trade | Debug your strategy |
| `--format` | Output format | `--format json` |

### Strategy Resolution

When using `--strategy NAME`, the system searches in order:
1. `./NAME/strategy.yaml` (current directory)
2. `./strategies/NAME/strategy.yaml` (local strategies folder)
3. `~/.ai-saham/strategies/NAME/strategy.yaml` (user strategies)

If you provide a path with `/` or ending in `.yaml`, it's used directly.

### Understanding Backtest Metrics

```
==================================================
BACKTEST RESULTS
==================================================

Ticker:         BBCA
Strategy:       my_custom_rules
Period:         2024-01-01 to 2024-12-31

--------------------------------------------------
PERFORMANCE
--------------------------------------------------

Initial Capital:           100,000,000 IDR
Final Capital:             118,500,000 IDR
Total Return:                    18.50%
Max Drawdown:                    -8.23%

--------------------------------------------------
TRADE STATISTICS
--------------------------------------------------

Total Trades:                        12
Winning Trades:                       8
Losing Trades:                        4
Win Rate:                        66.67%
Profit Factor:                     2.15
Avg Win:                    3,125,000 IDR
Avg Loss:                   1,500,000 IDR
```

**Metric Guide:**

| Metric | What It Tells You | Good Value |
|--------|-------------------|------------|
| Total Return | Overall performance | Positive, beats benchmark |
| Max Drawdown | Worst peak-to-trough drop | Lower is better (-10% to -20% typical) |
| Win Rate | % of profitable trades | > 50% (but not everything) |
| Profit Factor | Gross profit / gross loss | > 1.5 is good, > 2 is excellent |

**Warning Signs:**
- Max Drawdown > -30%: Strategy may be too risky
- Win Rate high but Profit Factor low: Small wins, big losses
- Total Trades < 10: Not enough data to be statistically significant

---

## 9. Custom Rules DSL

The Custom Rules DSL lets you encode YOUR investment philosophy into YAML.

### Why Custom Rules?

- Codify your strategy for consistency
- Remove emotional decision-making
- Test strategies via backtesting
- Share and version control your approach

### Basic Structure

```yaml
version: 1
name: "my_strategy"
description: "My personal trading approach"

# What to return when no rules match
default_outcome: MODERATE

# Define custom indicators (optional)
indicators:
  fast_rsi:
    type: RSI
    period: 7

  slow_ema:
    type: EMA
    period: 50

# Your rules (evaluated in priority order)
rules:
  - name: oversold_entry
    priority: 10          # Lower = evaluated first
    when:
      indicator: fast_rsi # Use custom indicator
      operator: "<"
      value: 25
    outcome: LOW_RISK
    rationale: "RSI(7) below 25 suggests oversold"
```

### Built-in and Registered Indicators

These are always available without definition in your rules file:

| Name | Default Period | Type | Access As |
|------|---------------|------|-----------|
| RSI | 14 | Built-in | `indicator: RSI` |
| SMA | 20 | Built-in | `indicator: SMA` |
| EMA | 20 | Built-in | `indicator: EMA` |
| ATR | 14 | Plugin | `indicator: ATR` |
| *Your formulas* | — | Formula | `indicator: YOUR_NAME` |

**Using Registered Formulas in Rules:**

Any formula created via `saham indicator create` and saved to `config/formulas.yaml` can be used directly in rules without re-defining them:

```yaml
# First, create your formula once:
# saham indicator create "smoothed RSI" --name SMOOTH_RSI

# Then use it in rules.yaml - no definition needed!
version: 1
name: "smooth_rsi_strategy"
default_outcome: MODERATE

rules:
  - name: oversold
    when:
      indicator: SMOOTH_RSI   # Uses formula from config/formulas.yaml
      operator: "<"
      value: 30
    outcome: LOW_RISK
```

This keeps rules files clean and promotes formula reuse across strategies.

### Formula-Based Indicators (Advanced)

Instead of just type+period, you can define indicators using **mathematical expressions**:

```yaml
indicators:
  # Smoothed RSI - apply 10-day SMA to RSI(14)
  smooth_rsi:
    formula: "SMA(RSI(14), 10)"

  # MACD line - difference of two EMAs
  macd_line:
    formula: "EMA(CLOSE, 12) - EMA(CLOSE, 26)"

  # Price distance from moving average (percentage)
  sma_distance:
    formula: "(CLOSE - SMA(CLOSE, 20)) / SMA(CLOSE, 20) * 100"
```

**Formula Syntax:**
- **Series:** `OPEN`, `HIGH`, `LOW`, `CLOSE`, `VOLUME`
- **Functions:** `SMA(series, period)`, `EMA(series, period)`, `RSI(period)`, `ATR(period)`
- **Math:** `+`, `-`, `*`, `/`
- **Grouping:** `( )`

**Why use formulas?**
- Create indicators that don't exist as built-ins
- Combine multiple indicators into one
- Express complex trading concepts concisely

### Condition Types

**1. Indicator vs Value:**
```yaml
when:
  indicator: RSI      # Built-in or custom
  operator: "<"       # <, <=, >, >=, ==, !=
  value: 30
```

**2. Indicator vs Indicator (Crossovers):**
```yaml
when:
  left:
    indicator: fast_ema
  operator: ">"
  right:
    indicator: slow_ema
```

**3. Indicator vs Literal Value (Left/Right Form):**
```yaml
when:
  left:
    indicator: foreign_flow_3d
  operator: ">"
  right:
    value: 50000000000  # 50B IDR threshold
```

The right-hand side can be either an `indicator:` reference or a literal `value:`.

**4. Compound Conditions (`all:` — Logical AND):**
```yaml
when:
  all:
    - indicator: rsi
      operator: "<"
      value: 30
    - left:
        indicator: CLOSE
      operator: ">"
      right:
        indicator: sma_50
```

All sub-conditions must be true for the rule to match. Each sub-condition can be any of the above types (indicator vs value, indicator vs indicator, or nested `all:`).

**5. Price Field References:**

You can reference raw candle price fields directly in conditions:

| Field | Description |
|-------|-------------|
| `OPEN` | Opening price |
| `HIGH` | Highest price |
| `LOW` | Lowest price |
| `CLOSE` | Closing price |
| `VOLUME` | Trading volume |

```yaml
# Compare closing price to a moving average
when:
  left:
    indicator: CLOSE
  operator: ">"
  right:
    indicator: sma_50
```

### Example: EMA Crossover Strategy

```yaml
version: 1
name: "ema_crossover"
default_outcome: MODERATE

indicators:
  fast_ema:
    type: EMA
    period: 9
  slow_ema:
    type: EMA
    period: 21

rules:
  - name: bullish_crossover
    priority: 10
    when:
      left:
        indicator: fast_ema
      operator: ">"
      right:
        indicator: slow_ema
    outcome: LOW_RISK
    rationale: "EMA(9) above EMA(21) - bullish momentum"

  - name: bearish_crossover
    priority: 10
    when:
      left:
        indicator: fast_ema
      operator: "<"
      right:
        indicator: slow_ema
    outcome: HIGH_RISK
    rationale: "EMA(9) below EMA(21) - bearish momentum"
```

### Usage

```bash
# Use custom rules for risk assessment
saham analyze risk BBCA --rules-file config/my_rules.yaml

# Backtest custom rules
saham strategy backtest BBCA --rules-file config/my_rules.yaml --verbose
```

### Evaluation Order

1. Rules sorted by priority (lower number = first)
2. Same priority = file order
3. First matching rule wins
4. No match = `default_outcome`

---

## 10. Strategy Packages - The `strategy` Command

Strategy packages make strategies **first-class artifacts** - versionable, portable, and shareable.

### Why Strategy Packages?

Instead of loose YAML files scattered around, organize strategies as self-contained packages:

```
strategies/
└── momentum/
    ├── strategy.yaml        # Required: your rules
    ├── strategy.skill.yaml  # Optional: annotation sidecar (for SKILL.md generation)
    ├── SKILL.md             # Auto-generated: machine-readable documentation
    ├── README.md            # Optional: human documentation
    ├── tests/               # Optional: test cases
    └── examples/            # Optional: example usage
```

### Creating a Strategy Manually

```bash
# Initialize a new strategy package
saham strategy init momentum

# Creates: ./strategies/momentum/
#   ├── strategy.yaml (starter template)
#   └── README.md (documentation)

# Create in a custom location
saham strategy init my_strat --dir ~/trading/strategies/my_strat

# Overwrite existing
saham strategy init momentum --force
```

### Creating a Strategy from Natural Language (AI-Assisted)

Don't know YAML syntax? Describe your strategy in plain English and let AI generate it:

```bash
# Create strategy from natural language
saham strategy create "buy when RSI below 30 and EMA crossover" --name momentum

# With specific AI provider
saham strategy create "conservative RSI strategy with strict thresholds" \
    --name conservative_rsi --provider claude

# Preview without saving
saham strategy create "MACD crossover strategy" --no-save

# Use local Ollama (no API key needed)
saham strategy create "EMA crossover with 9 and 21 periods" \
    --name ema_cross --provider ollama
```

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--name` | `-n` | auto-generated | Strategy name |
| `--provider` | `-p` | mock | AI provider (deepseek/claude/openai/gemini/ollama/mock) |
| `--model` | `-m` | provider default | Model name (for Ollama) |
| `--dir` | `-d` | ./strategies/NAME | Directory to save strategy |
| `--save/--no-save` | | save | Save to file or preview only |

**Output Example:**

```
Creating strategy from intent...

Generated Strategy:
──────────────────────────────────────────────────
version: 1
name: "momentum"
description: "RSI oversold with EMA crossover strategy"

indicators:
  fast_ema:
    type: EMA
    period: 9
  slow_ema:
    type: EMA
    period: 21

default_outcome: MODERATE

signal_mapping:
  LOW_RISK: ENTER_LONG
  MODERATE: HOLD
  HIGH_RISK: EXIT_LONG

rules:
  - name: rsi_oversold
    priority: 10
    when:
      indicator: RSI
      operator: "<"
      value: 30
    outcome: LOW_RISK
    rationale: "RSI below 30 indicates oversold conditions"

  - name: bullish_ema_crossover
    priority: 10
    when:
      left:
        indicator: fast_ema
      operator: ">"
      right:
        indicator: slow_ema
    outcome: LOW_RISK
    rationale: "Fast EMA above slow EMA confirms bullish momentum"
──────────────────────────────────────────────────

Strategy saved to: ./strategies/momentum/strategy.yaml

Next steps:
  1. Run: saham strategy validate momentum
  2. Run: saham strategy backtest BBCA --strategy momentum
```

**What you can describe:**

| Natural Language | Generated Strategy |
|------------------|-------------------|
| "RSI oversold strategy" | RSI < 30 → LOW_RISK, RSI > 70 → HIGH_RISK |
| "EMA crossover with 9 and 21 periods" | EMA(9) > EMA(21) → bullish |
| "conservative RSI strategy" | Strict thresholds (25/75 instead of 30/70) |
| "momentum strategy" | RSI + EMA combination |

**Unsupported requests** (returns error):
- "strategy for BBCA" (specific stock recommendations)
- "strategy that always wins" (guaranteed outcomes)
- "predict price" (price predictions)
- "explain RSI" (non-strategy requests)

### Validating a Strategy

```bash
# Validate by name (searches standard locations)
saham strategy validate momentum

# Validate by explicit path
saham strategy validate ./strategies/momentum/strategy.yaml

# Strict mode: treat warnings as errors
saham strategy validate momentum --strict
```

**Output Example:**
```
Validating: ./strategies/momentum/strategy.yaml

Status: VALID
Name: momentum

Warnings:
  - Missing README.md (recommended)
```

### Listing Available Strategies

```bash
# List all valid strategies
saham strategy list

# Show detailed information
saham strategy list --verbose

# Include invalid strategies (for debugging)
saham strategy list --all
```

**Output Example:**
```
Found 3 strategies:

  momentum             Momentum-based EMA crossover
  conservative_rsi     RSI with strict thresholds [user]
  broken_strat         broken_strat (invalid)

Run 'saham strategy validate NAME' to check a strategy.
Run 'saham strategy backtest TICKER --strategy NAME' to use a strategy.
```

**Location Badges:**
- No badge = local (`./strategies/`)
- `[user]` = user directory (`~/.ai-saham/strategies/`)

### Using Strategies in Backtest

```bash
# By name (recommended)
saham strategy backtest BBCA --strategy momentum

# By explicit path
saham strategy backtest BBCA -S ./strategies/momentum/strategy.yaml
```

### Strategy Package vs Rules File

| Aspect | Strategy Package | Loose Rules File |
|--------|------------------|------------------|
| Organization | Folder with structure | Single YAML file |
| Documentation | README.md included | Separate or none |
| Discoverability | `saham strategy list` | Manual search |
| Sharing | Copy folder | Copy file |
| Version control | Natural (folder) | Works but scattered |

**Recommendation:** Use strategy packages for any strategy you plan to reuse or share.

### Sharing Strategies

Strategies are self-contained and easy to share:

```bash
# Share via git
git add strategies/momentum
git commit -m "Add momentum strategy"
git push

# Copy to another project
cp -r strategies/momentum ~/other-project/strategies/

# Install to user directory (available everywhere)
cp -r strategies/momentum ~/.ai-saham/strategies/
```

---

## 11. Skill Documentation - The `skill` Command

The skill system generates machine-readable documentation (SKILL.md) for strategies, indicators, and formulas. These files power the project's SKILLS_INDEX.md catalog and enable drift detection when rules change.

### Why Skill Documentation?

- **Discoverability** - SKILLS_INDEX.md catalogs all documented artifacts in one place
- **Drift Detection** - Detects when strategy rules change but documentation hasn't been regenerated
- **Machine-Readable** - SKILL.md files include structured metadata (tags, dependencies, data requirements)
- **Auto-Generated** - No manual writing needed; generated from strategy YAML + annotation sidecar

### How It Works

Each strategy can have a **sidecar annotation file** (`strategy.skill.yaml`) next to `strategy.yaml`:

```
strategies/rsi-momentum/
├── strategy.yaml           # Strategy rules (required)
├── strategy.skill.yaml     # Annotation sidecar (optional)
└── SKILL.md                # Auto-generated documentation
```

The sidecar provides human-authored context that can't be inferred from rules alone:

```yaml
# strategy.skill.yaml
description: >
  Momentum strategy combining RSI extremes with SMA trend confirmation.
  Buys oversold dips in uptrends, exits on overbought or trend breakdown.
when_to_use: >
  Trending markets where pullbacks are buying opportunities.
  Works best with liquid large-cap stocks.
tags:
  - momentum
  - rsi
  - trend-following
limitations:
  - Underperforms in range-bound/sideways markets
  - May generate false signals during trend transitions
examples:
  - "Buy BBCA on RSI oversold dip while still in uptrend"
  - "Exit when RSI overbought or price breaks below SMA50"
```

### Auto-Generation on Validate

When you run `saham strategy validate`, SKILL.md is automatically generated if a sidecar exists:

```bash
saham strategy validate rsi-momentum
```

```
Validating: strategies/rsi-momentum/strategy.yaml

Status: VALID
Name: RSI Momentum

SKILL.md: strategies/rsi-momentum/SKILL.md
```

If rules have changed since the last generation, you'll see a drift warning:

```
SKILL.md: strategies/rsi-momentum/SKILL.md
  Warning: SKILL.md is stale — rules have changed since last generation
  Warning: Rules changed — SKILL.md regenerated.
```

### Explicit Generation

Generate SKILL.md on demand for any artifact type:

```bash
# Strategy (default type)
saham skill generate rsi-momentum
saham skill generate foreign-accumulation

# Indicator plugin
saham skill generate atr --type indicator

# Formula
saham skill generate SMOOTH_RSI --type formula
```

If no sidecar exists, a placeholder SKILL.md is generated with a warning.

### Checking for Stale Documentation

Scan all strategies and report which SKILL.md files are out of date:

```bash
saham skill check
```

```
  foreign-accumulation: up to date
  rsi-momentum: STALE (run: saham skill generate rsi-momentum)

1/2 artifact(s) need regeneration.
```

This uses a hash of the strategy rules embedded in each SKILL.md to detect drift without requiring a full re-parse.

### Building the Skills Index

Generate a project-wide catalog of all SKILL.md files:

```bash
saham skill index
```

Creates `SKILLS_INDEX.md` at the project root:

```markdown
# Skills Index

## Strategies

| Name | Description | Tags | Link |
|------|-------------|------|------|
| Foreign Accumulation | Detects foreign investor accumulation... | foreign-flow, institutional | SKILL.md |
| RSI Momentum | Momentum strategy combining RSI... | momentum, rsi | SKILL.md |

## Indicators

| Name | Description | Tags | Link |
|------|-------------|------|------|
| ATR | — | — | SKILL.md |
```

### Annotating a New Strategy

To add skill documentation to any strategy:

1. Create `strategies/<name>/strategy.skill.yaml` (see sidecar format above)
2. Run `saham strategy validate <name>` — SKILL.md is auto-generated
3. Run `saham skill index` — updates the project-wide catalog

### Command Reference

| Command | Purpose | Reads | Writes |
|---------|---------|-------|--------|
| `saham skill generate NAME` | Generate SKILL.md | strategy.yaml + sidecar | SKILL.md |
| `saham skill generate NAME --type indicator` | Generate for indicator | plugin + sidecar | SKILL.md |
| `saham skill generate NAME --type formula` | Generate for formula | formula + sidecar | SKILL.md |
| `saham skill check` | Report stale/missing docs | strategy.yaml + SKILL.md | Nothing |
| `saham skill index` | Rebuild catalog | All SKILL.md files | SKILLS_INDEX.md |

---

## 12. AI-Enhanced Analysis (Optional)

AI is **OFF by default**. The system works completely without AI. Use AI for:
- Learning what indicators mean
- Getting a second opinion
- Explaining complex market conditions
- **Translating natural language to formulas** (new!)

### Enabling AI Explanation

```bash
# Add --explain to risk assessment
saham analyze risk BBCA --explain

# Specify provider
saham analyze risk BBCA --explain --provider ollama

# Use specific model
saham analyze risk BBCA --explain --provider ollama --model llama3:8b
```

### AI Providers

| Provider | Requires | Best For |
|----------|----------|----------|
| `deepseek` | `DEEPSEEK_API_KEY` | Default provider, cost-effective |
| `claude` | `ANTHROPIC_API_KEY` | High-quality explanations |
| `openai` | `OPENAI_API_KEY` | Widely available |
| `gemini` | `GOOGLE_API_KEY` | Good free tier |
| `ollama` | Local server | Privacy, no API costs |
| `mock` | Nothing | Testing |

**Default provider is `deepseek`.** Set `DEEPSEEK_API_KEY` in your environment.

### Setting Up Ollama (Local AI)

```bash
# Install Ollama (macOS)
brew install ollama

# Start server
ollama serve

# Pull a model (one time)
ollama pull llama3:8b

# Use with saham
saham analyze risk BBCA --explain --provider ollama --model llama3:8b
```

### AI for Sentiment Classification

```bash
# Default: keyword-based (faster, offline)
saham analyze sentiment BBCA

# AI-powered (more nuanced)
saham analyze sentiment BBCA --ai-classify
saham analyze sentiment BBCA --ai-classify --provider ollama
```

### AI Formula Translator (CLI)

Don't know formula syntax? Describe what you want in plain English:

```bash
saham indicator create "smoothed RSI with 14-period and 10-day smoothing" --name SMOOTH_RSI
saham indicator create "MACD line using 12 and 26 period EMAs" --name MACD --provider deepseek
saham indicator create "average true range over 14 days" --name ATR14 --no-save
```

**Examples of what you can ask:**

| Natural Language | Resulting Formula |
|------------------|-------------------|
| "smoothed RSI with 10-day smoothing" | `SMA(RSI(14), 10)` |
| "MACD line with 12 and 26 EMAs" | `EMA(CLOSE, 12) - EMA(CLOSE, 26)` |
| "average true range over 14 days" | `ATR(14)` |
| "price as percentage of 50-day SMA" | `CLOSE / SMA(CLOSE, 50) * 100` |

**Unsupported requests** return `UNSUPPORTED`:
- "Should I buy BBCA?" (trading advice)
- "Will the price go up?" (predictions)
- "Explain what RSI means" (not a formula)

---

## 13. Indicator Management Commands

Create, list, and manage custom indicators from the command line.

### `indicator create` - Create from Natural Language

Use AI to translate a description into a formula:

```bash
# Basic usage (saves to config/formulas.yaml)
saham indicator create "smoothed RSI with 14-period and 10-day smoothing" --name SMOOTH_RSI

# Specify AI provider
saham indicator create "MACD line" --name MACD --provider claude

# Use local Ollama
saham indicator create "average true range" --name ATR14 --provider ollama

# Don't save (just see the formula)
saham indicator create "price distance from 50-day SMA" --no-save
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--name` | `-n` | auto-generated | Indicator name (uppercase) |
| `--provider` | `-p` | mock | AI provider (deepseek/claude/openai/gemini/ollama/mock) |
| `--model` | `-m` | provider default | Model name |
| `--save/--no-save` | | save | Save formula to storage |
| `--formulas` | | config/formulas.yaml | Custom storage path |

### `indicator list` - View All Indicators

See built-in, plugin, and custom indicators:

```bash
# List all indicators
saham indicator list

# Show formula expressions
saham indicator list --formulas
```

**Output example:**
```
Built-in Indicators:
----------------------------------------
  EMA          Exponential Moving Average   (period: 20)
  RSI          Relative Strength Index      (period: 14)
  SMA          Simple Moving Average        (period: 20)

Plugin Indicators:
----------------------------------------
  ATR          (period: 14)

Custom Formulas:
----------------------------------------
  SMOOTH_RSI   = SMA(RSI(14), 10)
  MACD         = EMA(CLOSE, 12) - EMA(CLOSE, 26)

Total available: 6
```

### `indicator show-formula` - View Formula Details

See the full details of a saved formula:

```bash
saham indicator show SMOOTH_RSI
```

**Output:**
```
Name:    SMOOTH_RSI
Formula: SMA(RSI(14), 10)
Intent:  smoothed RSI with 14-period and 10-day smoothing
Created: 2025-01-27 10:30:45
```

### `indicator delete` - Remove Custom Formula

Delete a saved formula (built-ins cannot be deleted):

```bash
# With confirmation prompt
saham indicator delete SMOOTH_RSI

# Skip confirmation
saham indicator delete SMOOTH_RSI --force
```

---

## 14. Batch Data Update - The `data update` Command

Keep your local data fresh with a single command. Fetches candles + broker flow
for an entire universe and pre-warms all Stockbit enrichment caches.

```bash
# Update all LQ45 stocks (candles + broker flow)
saham data update --universe lq45

# Update explicitly listed tickers
saham data update BBCA BBRI BMRI

# Refresh only already-cached tickers
saham data update --universe cached

# Force refresh all (ignore cache)
saham data update --universe lq45 --refresh

# Broker flow only (skip candles)
saham data update --universe lq45 --broker-only

# Use shorter history
saham data update --universe lq45 --days 30
```

**Why use this?** This replaces the old `saham fetch TICKER` workflow — fetches
everything for an entire universe in one pass. Run daily before morning screening.

**Pre-warms all Stockbit caches:**
- Analyst consensus (buy/hold/sell counts, price targets)
- Insider activity (director/commissioner transactions, 90-day window)
- Seasonality (monthly return %, win rate, 5-year history)
- Corporate action calendar (dividend, rights issue, RUPS dates)
- Shareholding composition (institutional/individual split)
- Bandar detector (institutional operator accumulation/distribution score)
- Company fundamentals (P/E, ROE, Piotroski F-Score, quality gate)

Each provider respects its own TTL (daily, 7-day, or session-based). No cache
is re-fetched unless stale — `saham data update` is safe to run multiple times.

**Design rule:** Analysis commands (`swing analyze`, `swing screen`) are
read-only — they never call external APIs. Only `saham data update` fetches live
data. This guarantees consistent results: running analysis twice with the same
cached data produces identical output.

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--universe` | `-u` | | Named universe: lq45, idx80, idxcomp100, cached |
| `--days` | `-d` | 90 | Days of history to fetch |
| `--candles-only` | | false | Skip broker flow fetch |
| `--broker-only` | | false | Skip candles fetch |
| `--provider` | | yahoo | Candles provider: yahoo or idx |
| `--refresh` | `-r` | false | Force refresh all |

---

## 15. Foreign Accumulation Screener - The `screen accumulation` Command

Screen stocks for institutional foreign accumulation patterns. Detects stocks being quietly bought by foreign investors over multiple days.

### Single-Window Mode

```bash
# Screen LQ45 with 7-day window (default)
saham screen accumulation --universe lq45

# 30-day window
saham screen accumulation --universe idx80 --window 30

# Specific tickers
saham screen accumulation BBCA BBRI BMRI --window 7
```

### Multi-Window Mode

Compare scores across 7d, 30d, and 90d windows side-by-side:

```bash
saham screen accumulation --universe lq45 --multi
saham screen accumulation --universe lq45 --multi --sort-by 30d
```

**Pattern labels:**
- `sustained` — Score ≥60 on all 3 windows (highest conviction)
- `building` — Strong recent, weaker long-term
- `fresh rotation` — Strong 7d only; very recent
- `coiled spring` — Squeeze + score ≥60 (compressed, ready to break)
- `long-term only` — Strong 90d, weak recent
- `weak` — No window scores ≥60

### Enhanced Output Signals

The screener enriches every candidate with additional signals from live Stockbit
data (requires login). Run `saham data update --universe lq45` to pre-warm the
cache for all signals in one pass.

| Signal | Indicator | Source | Example |
|--------|-----------|--------|---------|
| Corporate Action Risk | ⚠ DIVIDEND RISK / ⚠ RIGHTS ISSUE / ⚠ RUPS | Stockbit corp action calendar | `⚠ DIVIDEND RISK` |
| Seasonality | Monthly avg return + win rate (5-year) | Stockbit seasonality API | `SEASONAL +0.9% (60%wr, 5y)` |
| Insider Activity | ⭐ INSIDER BUY — director/commissioner transactions (90d) | Stockbit insider API | `⭐ INSIDER BUY: John Doe (Comm) BUY 500,000 @ 1,200` |
| Analyst Consensus | 📊 Buy/Hold/Sell counts + price target upside | Stockbit analyst ratings | `📊 ANALYST: 35B 2H \| target Rp8,827 (+40.7%)` |
| Shareholding Composition | 🏦 Institutional/individual split + top holder | Stockbit shareholder API | `🏦 HOLDING: DWIMURIA 54.9% \| Inst 31.9% \| Individual 8.7%` |
| Bandar Detector | 🔍 Institutional operator accumulation/distribution signal (-9 to +9) | Stockbit market detectors | `🔍 BANDAR: Score +5 (Acc, top1 47%)` |
| Company Fundamentals | 📈 P/E, ROE, Piotroski F-Score, quality gate | Stockbit keystats | `📈 FUNDAM: P/E 18.3, ROE 21.2%, F-Score 7, quality=True` |
| Broker Detail | Per-broker buy/sell attribution | Stockbit broker data | `─ MANDIRI SEKURITAS BUY 50.0B` |

Corporate action flags, insider activity, analyst consensus, shareholding
composition, bandar detection, and fundamentals appear in the screener table
and `swing analyze` output. Seasonality scores are used as tiebreakers when
accumulation scores are equal.

### Filters

```bash
# Score threshold
saham screen accumulation --universe lq45 --min-score 50 --top 10

# Only where foreigners are underwater (bought higher than today)
saham screen accumulation --universe lq45 --vwap-only

# Only Bollinger Band squeeze setups
saham screen accumulation --universe lq45 --squeeze-only

# Show per-broker detail (requires Stockbit data)
saham screen accumulation --universe lq45 --granular

# Show score component breakdown
saham screen accumulation --universe lq45 --breakdown

# Column reference guide
saham screen accumulation --guide
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--universe` | `-u` | | Universe: lq45, idx80, idxcomp100, cached |
| `--window` | `-w` | 7 | Analysis window in days |
| `--min-streak` | | 0 | Minimum consecutive buy days |
| `--min-score` | | 0.0 | Minimum composite score (0-120) |
| `--vwap-only` | | false | Only underwater foreign positions |
| `--squeeze-only` | | false | Only BB squeeze stocks |
| `--top` | | 20 | Show top N results |
| `--multi` | | false | Multi-window side-by-side |
| `--sort-by` | | avg | Sort: avg, max, 7d, 30d, 90d |
| `--format` | | table | Output format: table or json |
| `--guide` | | false | Column reference guide |

### Historical Audit

Replay accumulation signals historically and measure forward returns:

```bash
saham screen accumulation audit --universe idx80 --preset foreign-bounce
saham screen accumulation audit --universe lq45 --window 7 --min-score 70
```

### Logging to Journal

```bash
saham trade swing log --ticker BBRI --window 7
```

---

## 16. Intraday Pre-Open Screener - The `trade intraday` Command

A complete pre-market screening to opening-auction confirmation workflow.

### Step 1: Pre-Open Screen

```bash
# Fast mode (no order book, ~15s)
saham trade intraday pre-open \
  --movers-json '[{"ticker":"BBCA","iev":150000}]' \
  --fast

# Normal mode with order book data
saham trade intraday pre-open \
  --movers-json '[{"ticker":"BBCA","iev":150000}]' \
  --order-books-json '{"BBCA":{"price":8900,"volume":50000}}'
```

### Step 2: Confirm at Opening

After the opening auction clears, check which candidates actually trigger:

```bash
saham trade intraday confirm-open --opening-json '{"BBCA":9050,"BMRI":5875}'
```

Emits deterministic ENTER / WAIT / SKIP decisions based on entry ranges from the pre-open screen.

### Step 3: Log & Review

```bash
# Log to paper trade journal
saham trade intraday log

# Review hit rate
saham trade intraday review --horizon 5

# Record actual outcome
saham trade intraday outcome BBCA --entry 9000 --exit 9500 --result target
```

### Command Summary

| Command | Purpose |
|---------|---------|
| `saham trade intraday pre-open` | Pre-market movers screener |
| `saham trade intraday confirm-open` | Confirm against actual opening prices |
| `saham trade intraday log` | Append to paper trade journal |
| `saham trade intraday review` | Review journal accuracy |
| `saham trade intraday outcome` | Record actual trade outcome |

---

## 17. Opening Session Learning Loop - The `trade opening` Command

A daily learning loop for opening scalping: snapshot predictions at 08:57, track
orderbook prices every 5 minutes from 09:00–09:30, grade accuracy, and tune
thresholds via AI.

### Why This Exists

The pre-open screener (`trade intraday pre-open`) makes predictions about where
stocks will open. The opening session loop closes the feedback cycle by
measuring how accurate those predictions were and recommending config changes.

### Step 1: Capture Pre-Open Snapshot

```bash
# Live at 08:57 WIB (auto-window)
saham trade opening snapshot

# Manual dry-run anytime
saham trade opening snapshot --force --date 2026-06-17
```

Saves to `data/opening/YYYYMMDD/snapshot.json`:
- IEV, IEP, gap%, entry range, ATR-based stop for each candidate
- Market regime and NCP lock status
- Pre-computed verdict and reason codes

### Step 2: Track Every 5 Minutes

```bash
# Live loop 09:00–09:30 (auto-window)
saham trade opening track

# With real-time broker attribution (requires Stockbit login)
saham trade opening track --broker-confirm

# Manual dry-run with explicit tickers
saham trade opening track --force BBCA BBRI BMRI
```

Saves to `data/opening/YYYYMMDD/track_HHMM.json`:
- Best bid/offer price and volume each interval
- Gap% relative to prev close over time
- In-range / out-of-range status per ticker
- Full order book depth: `bid_pressure_ratio` (total bid/offer across all levels), `depth_ratio_5` (top-5 levels)
- Live foreign net: `fnet_intraday` (IDR), `fbuy_intraday`, `fsell_intraday` for the session
- `broker_signal` (if `--broker-confirm`): institutional absorption ratio, dominant side, net lot

Order book data is always captured (no flag needed). Use `--broker-confirm` to
also fetch institutional running-trade ticks (~2s per ticker).

### Step 3: Grade Accuracy

```bash
saham trade opening grade
```

Produces `grade.json` with deterministic accuracy report:
- Entry range hit-rate (% of tickers opening inside predicted range)
- Gap band accuracy: was the ATR band correctly calibrated?
- Stop distance safety: were stops wide enough?
- Trend classification accuracy: BULLISH/NEUTRAL/BEARISH vs actual move
- Institutional absorption rate (if `--broker-confirm` was used during track)
- Overall grade: A/B/C/D/F with per-ticker breakdown

### Step 4: Generate AI Prompt

```bash
# Save to file
saham trade opening prompt

# Print to stdout (pipe to pbcopy on macOS)
saham trade opening prompt --print | pbcopy
```

Generates a structured AI prompt containing today's predictions, actual outcomes,
and accuracy metrics — ready to paste into Claude, ChatGPT, or DeepSeek.

### Step 5: Tune via AI

```bash
# Requires DEEPSEEK_API_KEY
saham trade opening tune

# With explicit API key
saham trade opening tune --api-key sk-...
```

Calls DeepSeek with today's grade and the current config. Returns:
- Recommended threshold changes (min_history_days, gap thresholds, RSI bands)
- Per-ticker specific tuning suggestions
- Updated YAML config snippet ready to apply

### Data Structure

```
data/opening/
└── 2026-06-17/
    ├── snapshot.json     # 08:57 predictions
    ├── track_0900.json   # 09:00 orderbook
    ├── track_0905.json   # 09:05 orderbook
    ├── ...
    ├── track_0930.json   # 09:30 orderbook
    ├── grade.json        # Accuracy report
    ├── prompt.md         # AI prompt
    ├── tune.json         # AI recommendations
    └── tune.md           # Human-readable recommendations
```

### Command Summary

| Command | Timing | Purpose |
|---------|--------|---------|
| `saham trade opening snapshot` | 08:57 | Capture predictions |
| `saham trade opening track` | 09:00–09:30 | Track price convergence |
| `saham trade opening grade` | 09:30+ | Compute accuracy |
| `saham trade opening prompt` | anytime | Generate AI prompt |
| `saham trade opening tune` | anytime | Recommend config changes |

---

## 18. Swing Trade Workflow - The `trade swing` Command

Unified analysis combining accumulation, risk, sizing, backtest, and sentiment in one command.

```bash
# Full analysis
saham trade swing BBRI

# With position sizing
saham trade swing BBRI --capital 10000000

# With preset strategy gates
saham trade swing BBRI --preset foreign-bounce --capital 10000000

# Conservative profile, skip sentiment
saham trade swing BBRI --profile conservative --no-sentiment

# Compare with market regime context
saham trade swing BBRI --with-regime
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--profile` | `-p` | balanced | Risk profile |
| `--strategy` | `-S` | foreign-accumulation | Backtest strategy |
| `--preset` | | | Swing preset: foreign-bounce |
| `--capital` | `-c` | | Capital (enables sizing) |
| `--risk-pct` | | 1.0 | % of capital at risk |
| `--no-sentiment` | | false | Skip sentiment |
| `--no-backtest` | | false | Skip backtest |
| `--with-regime` | | false | Add regime context |

### Swing Backtest

Walk-forward portfolio backtest for the swing workflow:

```bash
saham trade swing backtest --universe idx80 --preset foreign-bounce
saham trade swing backtest --universe lq45 --capital 50000000 --max-positions 3
```

### Swing Compare

Compare regime-filtered variants side-by-side:

```bash
saham trade swing compare --universe idx80
saham trade swing compare --universe lq45 --variants baseline,sideways_only
```

### Swing Size

ATR-based position sizing calculator:

```bash
saham trade swing size BBRI --capital 10000000
saham trade swing size BBRI --capital 10000000 --risk-pct 2 --entry 4825
```

---

## 19. Market Regime - The `analyze regime` Command

Show deterministic IHSG market regime context for swing trading.

```bash
# Today's regime
saham analyze regime

# Specific date
saham analyze regime --as-of 2026-06-01

# Custom universe and benchmark
saham analyze regime --universe idx80 --benchmark ^JKSE
```

**Regime labels:** `BULLISH` (strong), `SIDEWAYS` (mixed), `WEAK` (declining), `RISK_OFF` (bearish)

Computed from: benchmark SMA20/SMA50 position, breadth (% of universe above SMA20), breadth change, and foreign flow breadth.

---

## 20. Terminal Charts - The `analyze chart` Command

Plot ASCII charts in your terminal (requires `pip install plotext`).

```bash
# Price chart with SMA overlay
saham analyze chart price BBCA
saham analyze chart price BBCA --sma 20 --ema 9 --days 120

# RSI with overbought/oversold bands
saham analyze chart rsi BBCA
saham analyze chart rsi BBCA --period 9 --days 120

# Volume bars
saham analyze chart volume BBCA
saham analyze chart volume BBCA --days 30
```

---

## 21. Data Health Check - The `data status` Command

Quick health probe for all data providers and tables:

```bash
saham data status
```

Reports:
- Latest data dates for IDX, Yahoo, broker, Stockbit
- Row counts across all database tables
- Provider health checks (IDX, Yahoo, Stockbit sessions)
- Data staleness warnings (e.g., "last IDX update: 5 days ago")

---

## 22. Stockbit Session Management - The `data stockbit` Command

Manage Stockbit browser sessions for automated data fetching.

```bash
# Open browser to log in (saves session cookies)
saham data stockbit login

# Check session health
saham data stockbit status

# Capture API traffic to identify endpoints
saham data stockbit spy
saham data stockbit spy --target orderbook --ticker BBRI

# Smoke-test the adapter
saham data stockbit test
saham data stockbit test --no-headless

# Fetch top IEV movers + live orderbook snapshots
saham data stockbit fetch-top5 --top 5

# Open interactive headed browser with saved session
saham data stockbit browse
```

| Command | Purpose |
|---------|---------|
| `saham data stockbit login` | Save browser session (Playwright) |
| `saham data stockbit status` | Check session health |
| `saham data stockbit spy` | Capture API traffic for calibration |
| `saham data stockbit test` | Smoke-test live adapter |
| `saham data stockbit fetch-top5` | Top IEV movers + orderbook snapshots |
| `saham data stockbit browse` | Interactive headed browser session |

---

## 22. Side-by-Side Comparison - The `analyze compare` Command

Quickly compare risk levels across multiple tickers:

```bash
saham analyze compare BBCA BBRI BMRI
saham analyze compare BBCA TLKM --profile conservative
```

---

## 23. Complete Workflow Examples

### Conservative Investor Workflow

Goal: Identify low-risk entry points for long-term holdings.

```bash
# Step 1: Get data (2 years for perspective)
saham data update BBCA --days 730

# Step 2: Check long-term trend
saham indicator compute SMA BBCA --period 200

# Step 3: Risk assessment with strict thresholds
saham analyze risk BBCA --profile conservative

# Step 4: Verify with all profiles
saham analyze risk BBCA --all

# Step 5: Check news context
saham analyze risk BBCA --with-sentiment
```

**Decision Framework:**
- All profiles agree on LOW_RISK → Strong buy signal
- Conservative shows LOW_RISK, others MODERATE → Decent entry
- Any profile shows HIGH_RISK → Wait for better entry

### Active Trader Workflow

Goal: Find short-term momentum opportunities.

```bash
# Step 1: Fresh data
saham data update BBRI --days 365 --refresh

# Step 2: Fast indicators
saham indicator snapshot BBRI --sma 10 --ema 9 --rsi 7

# Step 3: Aggressive profile for early signals
saham analyze risk BBRI --profile aggressive

# Step 4: Get AI explanation
saham analyze risk BBRI --profile aggressive --explain --provider ollama

# Step 5: Current sentiment
saham analyze sentiment BBRI --days 1
```

### Strategy Developer Workflow

Goal: Build and test a custom trading strategy.

```bash
# Step 1: Get enough historical data
saham data update TLKM --days 730

# Step 2: Create a strategy package
saham strategy init my_strategy

# Step 3: Edit the strategy in your editor
vim strategies/my_strategy/strategy.yaml
# ... define your indicators and rules ...

# Step 4: Validate the strategy
saham strategy validate my_strategy

# Step 5: Test rules on current data
saham analyze risk TLKM --rules-file strategies/my_strategy/strategy.yaml

# Step 6: Backtest on historical data
saham strategy backtest TLKM --strategy my_strategy --start 2023-01-01 --verbose

# Step 7: Iterate until metrics are acceptable
# Step 8: Share or version control your strategy
git add strategies/my_strategy
git commit -m "Add my_strategy"
```

### Custom Formula Workflow

Goal: Create a custom indicator and use it in trading rules.

```bash
# Step 1: Create custom formula using AI
saham indicator create "smoothed RSI with 14-period and 10-day smoothing" \
    --name SMOOTH_RSI --provider ollama

# Step 2: Verify it works
saham indicator compute SMOOTH_RSI BBCA --tail 10

# Step 3: Create a rules file that uses it (no definition needed!)
cat > config/smooth_rules.yaml << 'EOF'
version: 1
name: smooth_rsi_strategy
default_outcome: MODERATE

rules:
  - name: oversold
    when:
      indicator: SMOOTH_RSI   # Uses saved formula!
      operator: "<"
      value: 30
    outcome: LOW_RISK
    rationale: "Smoothed RSI indicates oversold"

  - name: overbought
    when:
      indicator: SMOOTH_RSI
      operator: ">"
      value: 70
    outcome: HIGH_RISK
    rationale: "Smoothed RSI indicates overbought"

signal_mapping:
  LOW_RISK: ENTER_LONG
  MODERATE: HOLD
  HIGH_RISK: EXIT_LONG
EOF

# Step 4: Run risk assessment
saham analyze risk BBCA --rules-file config/smooth_rules.yaml

# Step 5: Backtest the strategy
saham strategy backtest BBCA --rules-file config/smooth_rules.yaml --verbose

# Step 6: List all your custom formulas
saham indicator list --formulas
```

**Key insight:** Once you create a formula with `saham indicator create`, it's saved globally and can be used in any rules file without redefining it.

### Foreign Flow Analysis Workflow

Goal: Analyze foreign investor behavior and build a foreign flow strategy.

```bash
# Step 1: Fetch broker data (IDX provider - no auth needed)
saham data broker fetch BBCA --days 90
saham data broker fetch BBRI --days 90
saham data broker fetch BMRI --days 90

# Step 2: Analyze foreign flow patterns
saham data broker flow BBCA --days 20
saham data broker flow BBRI --days 20

# Step 3: Check top brokers (requires Stockbit session provider)
saham data broker fetch BBCA --provider stockbit-session --days 30
saham data broker top BBCA --date 2025-01-27

# Step 4: Fetch price data for backtesting
saham data update BBCA --days 365
saham data update BBRI --days 365

# Step 5: Use the pre-built foreign accumulation strategy
saham strategy backtest BBCA --strategy foreign-accumulation --verbose

# Step 6: Or create your own strategy
saham strategy init my_flow_strategy
# Edit to use FOREIGN_FLOW indicators
vim strategies/my_flow_strategy/strategy.yaml
saham strategy validate my_flow_strategy
saham strategy backtest BBCA --strategy my_flow_strategy
```

**Key Insights:**
- Foreign net buy > 50B for 3+ days often precedes price moves
- Consecutive buy days matter more than single-day spikes
- Watch for divergence between foreign flow and price
- IDX provider is sufficient for flow trend analysis; Stockbit adds broker-level detail

---

## 24. Command Reference (Quick Lookup)

| Command | Purpose | Key Options |
|---------|---------|-------------|
| `saham version` | Show version | — |
| `saham data update` | Batch data update (candles + broker) | `--universe`, `--days`, `--broker-provider`, `--refresh` |
| `saham indicator compute SMA TICKER` | Simple Moving Average | `--period`, `--field`, `--days` |
| `saham indicator compute EMA TICKER` | Exponential Moving Average | `--period`, `--field`, `--days` |
| `saham indicator compute RSI TICKER` | Relative Strength Index | `--period`, `--days` |
| `saham indicator compute INDICATOR TICKER` | Compute any indicator | `--period`, `--days`, `--tail`, `--db` |
| `saham indicator snapshot TICKER` | All indicators combined | `--sma`, `--ema`, `--rsi`, `--days`, `--format` |
| `saham analyze compare TICKER TICKER...` | Side-by-side risk comparison | `--profile`, `--sma`, `--rsi` |
| `saham analyze risk TICKER` | Risk assessment | `--profile`, `--all`, `--rules-file`, `--explain`, `--with-sentiment`, `--trend`, `--format` |
| `saham analyze sentiment TICKER` | News sentiment | `--days`, `--max`, `--ai-classify`, `--news-provider`, `--no-ai` |
| `saham analyze audit` | Audit sentiment accuracy | — |
| `saham data broker status` | Check all provider status | — |
| `saham data broker fetch TICKER` | Fetch broker summary data | `--days`, `--start`, `--end`, `--refresh`, `--provider` |
| `saham data broker flow TICKER` | View foreign flow summary | `--days` |
| `saham data broker top TICKER` | View top brokers | `--date` |
| `saham data broker import FILE` | Import broker data from CSV | `--preview`, `--mapping`, `--on-error` |
| `saham data broker mappings` | List available CSV mappings | — |
| `saham strategy init NAME` | Create strategy package | `--dir`, `--force` |
| `saham strategy create INTENT` | Create strategy from natural language | `--name`, `--provider`, `--save/--no-save` |
| `saham strategy validate NAME` | Validate strategy (auto-generates SKILL.md) | `--strict` |
| `saham strategy list` | List available strategies | `--verbose`, `--all` |
| `saham skill generate NAME` | Generate SKILL.md for an artifact | `--type` (strategy/indicator/formula) |
| `saham skill check` | Report stale/missing SKILL.md files | — |
| `saham skill index` | Rebuild SKILLS_INDEX.md catalog | — |
| `saham strategy backtest TICKER` | Strategy backtesting | `--strategy`/`--rules-file`, `--start`, `--end`, `--capital`, `--verbose`, `--format` |
| `saham indicator create` | Create formula from natural language | `--name`, `--provider`, `--save/--no-save` |
| `saham indicator list` | List all indicators | `--formulas` |
| `saham indicator show NAME` | Show formula details | — |
| `saham indicator delete NAME` | Delete custom formula | `--force` |
| `saham trade swing screen` | Foreign accumulation screener | `--universe`, `--window`, `--multi`, `--format` |
| `saham trade swing audit` | Historical accumulation audit | `--universe`, `--preset`, `--simulate-exits` |
| `saham trade intraday pre-open` | Pre-open market screener | `--movers-json`, `--fast`, `--top` |
| `saham trade intraday confirm-open` | Confirm at opening auction | `--opening-json` |
| `saham trade intraday log` | Log confirmation to journal | — |
| `saham trade intraday review` | Review paper trade journal | `--horizon` |
| `saham trade intraday outcome` | Record actual trade outcome | `--entry`, `--exit`, `--result` |
| `saham trade swing analyze TICKER` | Unified swing analysis | `--capital`, `--preset`, `--with-regime` |
| `saham trade swing backtest` | Portfolio walk-forward backtest | `--universe`, `--capital`, `--allow-regimes` |
| `saham trade swing compare` | Compare regime variants | `--universe`, `--variants` |
| `saham trade swing size TICKER` | ATR position sizing | `--capital`, `--risk-pct`, `--entry` |
| `saham analyze regime` | Market regime context | `--universe`, `--as-of`, `--format` |
| `saham analyze chart price TICKER` | Price chart with overlays | `--sma`, `--ema`, `--days`, `--width` |
| `saham analyze chart rsi TICKER` | RSI chart | `--period`, `--days` |
| `saham analyze chart volume TICKER` | Volume bar chart | `--days` |
| `saham data universe list` | List ticker universes | — |
| `saham data stockbit login` | Stockbit browser login | `--timeout` |
| `saham data stockbit status` | Check session health | — |
| `saham data stockbit test` | Smoke-test adapter | `--ticker`, `--no-headless` |

---

## Appendix A: Why Offline-First Matters

1. **Reproducibility** - Same data = same results
2. **Speed** - No network latency for cached analysis
3. **Privacy** - Your portfolio analysis stays local
4. **Reliability** - Works during internet outages
5. **Cost** - No ongoing API fees for basic analysis

Data is cached at `./data.db` (configurable with `--db`). Use `--refresh` to update when needed.

---

## Appendix B: Glossary

| Term | Definition |
|------|------------|
| **OHLCV** | Open, High, Low, Close, Volume - daily trading data |
| **SMA** | Simple Moving Average - average of last N prices |
| **EMA** | Exponential Moving Average - weighted average favoring recent prices |
| **RSI** | Relative Strength Index - momentum oscillator (0-100) |
| **Overbought** | RSI > 70 (or profile threshold) - may be due for pullback |
| **Oversold** | RSI < 30 (or profile threshold) - may be due for bounce |
| **Period** | Number of days used in indicator calculation |
| **Candle** | One day's OHLCV data |
| **Drawdown** | Peak-to-trough decline during backtesting |
| **Profit Factor** | Total wins divided by total losses |
| **Foreign Flow** | Net buying/selling by foreign investors (ASING) |
| **Broker Summary** | Daily breakdown of which brokers bought/sold a stock |
| **Accumulation** | Pattern of sustained buying (foreign net buy > 0) |
| **Distribution** | Pattern of sustained selling (foreign net sell) |

---

## Appendix C: Troubleshooting

### "No cached data found"

```
Error: No cached data found for BBCA
Tip: Run 'saham data update BBCA --days 365' first to download data.
```

**Solution:** Fetch data first with `saham data update TICKER --days 365`

### "Database not found"

```
Error: Database not found at /path/to/data.db
```

**Solution:** Run `saham data update` for any ticker to create the database

### "Network connection failed"

```
Error: Network connection failed.
Tip: Check your internet connection and try again.
```

**Solution:**
- Check internet connection
- Use cached data with already-fetched tickers
- Try `--refresh` later when connection is restored

### "Invalid profile"

```
Error: Invalid profile 'aggresive'. Must be one of: conservative, balanced, aggressive
```

**Solution:** Check spelling of profile name

### "Rules file not found"

```
Error: Rules file not found: config/my_rules.yaml
```

**Solution:** Verify the path is correct, or copy from example:
```bash
cp config/custom_rules.yaml.example config/my_rules.yaml
```

### "Strategy not found"

```
Error: Strategy 'momentum' not found.

Searched:
  - ./momentum/strategy.yaml
  - ./strategies/momentum/strategy.yaml
  - ~/.ai-saham/strategies/momentum/strategy.yaml

Tip: Use 'saham strategy init momentum' to create a new strategy.
```

**Solution:** The strategy doesn't exist in any search location. Options:

1. **Create the strategy:**
   ```bash
   saham strategy init momentum
   ```

2. **Check spelling:** Strategy names are case-sensitive

3. **Use explicit path:** If the file is elsewhere:
   ```bash
   saham strategy backtest BBCA --strategy ./path/to/strategy.yaml
   ```

4. **List available strategies:**
   ```bash
   saham strategy list
   ```

### "Strategy already exists"

```
Error: Strategy already exists at strategies/momentum/strategy.yaml
Use --force to overwrite.
```

**Solution:** Either use a different name or add `--force`:
```bash
saham strategy init momentum --force
```

### "Unknown indicator" in rules

```
Error: Rule references undefined indicator 'SMOOTH_RSI'.
Define it in the 'indicators' section, use a built-in, or register a formula.
```

**Solution:** The indicator isn't defined anywhere. Options:

1. **Create and save the formula:**
   ```bash
   saham indicator create "smoothed RSI" --name SMOOTH_RSI --provider mock
   ```

2. **Define it in the rules file:**
   ```yaml
   indicators:
     smooth_rsi:
       formula: "SMA(RSI(14), 10)"
   ```

3. **Use a built-in instead:** RSI, SMA, EMA, ATR

Check available indicators with:
```bash
saham indicator list
```

### "AI explanation unavailable"

```
AI explanation unavailable: DEEPSEEK_API_KEY not set
Tip: Set the appropriate API key environment variable.
```

**Solution:**
- Set DeepSeek API key (default): `export DEEPSEEK_API_KEY=sk-...`
- Set Claude API key: `export ANTHROPIC_API_KEY=sk-...`
- Or use local Ollama: `--provider ollama`
- Or use mock for testing: `--provider mock`

### "Stockbit session not found"

```
No session found.
Run: saham data stockbit login
```

**Solution:** Stockbit browser session cookies are not saved. Use the new browser-based login:

1. Install dependencies: `pip install -e ".[browser]" && playwright install chromium`
2. Login: `saham data stockbit login`
3. Check: `saham data stockbit status`

### "Stockbit session expired"

```
Session may be expired — re-run login.
```

**Solution:** Browser sessions can expire. Refresh with:
```bash
saham data stockbit login
```

Or use IDX provider (no auth needed):
```bash
saham data broker fetch BBCA
```

### "IDX API returned 403 Forbidden"

```
Error: IDX API returned 403 Forbidden.
```

**Solution:** The IDX API may be temporarily unavailable or blocking requests. Wait a few minutes and retry. If persistent, the API endpoint may have changed.

### "No broker data found"

```
No data found. Run 'saham data broker fetch BBCA' first.
```

**Solution:** Fetch broker data before viewing:
```bash
saham data broker fetch BBCA --days 30
saham data broker flow BBCA
```

---

**DISCLAIMER:** This tool provides technical analysis only, not financial advice. Always do your own research and consult qualified professionals before making investment decisions.
re making investment decisions.
isions.
