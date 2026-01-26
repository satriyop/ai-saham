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
saham fetch BBCA

# Step 3: See risk assessment across all profiles
saham risk BBCA --all

# Step 4: Create and test a strategy
saham strategy init momentum
saham backtest BBCA --strategy momentum

# Step 5: Or create a strategy from natural language!
saham strategy create "RSI oversold strategy" --name my_rsi --provider mock
saham backtest BBCA --strategy my_rsi
```

**What just happened?**
1. `version` - Confirmed the CLI is installed
2. `fetch` - Downloaded 1 year of daily price data for Bank Central Asia (BBCA)
3. `risk --all` - Analyzed the stock using 3 different risk tolerance profiles
4. `strategy init` - Created a reusable strategy package
5. `backtest --strategy` - Tested the strategy on historical data
6. `strategy create` - Used AI to generate a complete strategy from natural language

You now have a local copy of BBCA's data and can analyze it offline anytime.

---

## 3. Understanding Stock Data - The `fetch` Command

Before analyzing, you need data. The `fetch` command downloads **OHLCV data** (Open, High, Low, Close, Volume) from Yahoo Finance.

### What is OHLCV?

Each trading day produces these 5 values:

| Field | Meaning | Why It Matters |
|-------|---------|----------------|
| **Open** | First trade price | Shows where market opened |
| **High** | Highest price | Shows buyer strength |
| **Low** | Lowest price | Shows seller pressure |
| **Close** | Last trade price | Most important - where it ended |
| **Volume** | Shares traded | Shows conviction behind moves |

### Basic Usage

```bash
# Fetch 1 year of data (default)
saham fetch BBCA

# Fetch 2 years for longer analysis
saham fetch BBRI --days 730

# Force re-download (ignore cache)
saham fetch TLKM --refresh
```

### When to Use Each Option

| Option | When to Use | Example Scenario |
|--------|-------------|------------------|
| `--days 730` | Need longer history | "Analyze 2-year trend" |
| `--refresh` | Data seems stale | "Stock moved but data unchanged" |
| `--db path/to/file.db` | Multiple portfolios | Separate DBs for different accounts |

### Output Explained

```
Fetching BBCA...

Ticker: BBCA
Source: yahoo_finance
Records: 252
Date range: 2024-01-02 to 2025-01-24

Database: /Users/you/.ai-saham/data.db

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
saham sma BBCA

# 50-day SMA (medium-term trend)
saham sma BBCA --period 50

# 200-day SMA (long-term trend)
saham sma BBCA --period 200

# SMA on a different price field
saham sma BBCA --field high
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
saham ema BBCA

# Faster EMA for active trading
saham ema BBCA --period 9

# Compare with SMA of same period
saham sma BBCA --period 20
saham ema BBCA --period 20
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
saham rsi BBCA

# Shorter period = more sensitive
saham rsi BBCA --period 7

# Longer period = smoother
saham rsi BBCA --period 21
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

### 4.4 The `compute` Command - Universal Indicator Computation

Compute **any** indicator - built-in, plugin, or custom formula - for any stock.

```bash
# Compute built-in indicators
saham compute RSI BBCA
saham compute SMA BBCA --period 50

# Compute plugin indicators
saham compute ATR BBCA --period 14

# Compute custom formulas (created via create-indicator)
saham compute SMOOTH_RSI BBCA --tail 10

# Control output
saham compute EMA BBRI --period 20 --days 180 --tail 50
```

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--period` | `-p` | 14 | Period for the indicator (ignored for formulas) |
| `--days` | `-d` | 365 | Days of data to use |
| `--tail` | `-t` | 30 | Show last N values |
| `--db` | | ~/.ai-saham/data.db | Database path |

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

### 4.5 Combining Indicators - The `indicators` Command

**Why combine?** Single indicators can give false signals. When multiple indicators agree, signals are stronger.

```bash
# See all three indicators aligned by date
saham indicators BBCA

# Custom periods for your strategy
saham indicators BBRI --sma 50 --ema 50 --rsi 7
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

## 5. Risk Assessment - The `risk` Command

The `risk` command converts indicator values into actionable assessments using rule-based evaluation.

### Three Built-in Profiles

| Profile | RSI Overbought | RSI Oversold | Decision Logic |
|---------|---------------|--------------|----------------|
| **conservative** | > 75 | < 25 | All indicators must agree |
| **balanced** | > 70 | < 30 | Majority rules |
| **aggressive** | > 65 | < 35 | Single indicator can signal |

### Basic Usage

```bash
# Balanced profile (default)
saham risk BBCA

# Conservative for retirement accounts
saham risk BBCA --profile conservative

# Compare all three profiles
saham risk BBCA --all
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
saham risk BBCA
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
saham risk BBCA --all
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

## 6. News Sentiment - The `sentiment` Command

Sentiment analysis adds context to price movements by analyzing news headlines.

**Critical Understanding:** Sentiment does NOT affect risk assessment. It's supplementary information only.

### Basic Usage

```bash
# Analyze last 3 days of news (default)
saham sentiment BBCA

# Look back further
saham sentiment BBCA --days 7

# Use AI for classification (more nuanced)
saham sentiment BBCA --ai-classify
```

### Options Explained

| Option | Purpose | When to Use |
|--------|---------|-------------|
| `--days 7` | Fetch 7 days of news | Need more context |
| `--max 30` | Limit to 30 headlines | Faster analysis |
| `--ai-classify` | Use AI instead of keywords | Need nuance (e.g., sarcasm) |
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

### Adding Sentiment to Risk Assessment

```bash
saham risk BBCA --with-sentiment
```

This adds a sentiment section to the risk output, but remember: sentiment is contextual information only and does NOT change the risk level.

---

## 7. Broker Data & Foreign Flow - The `broker` Command

Foreign investor flow is one of the most watched metrics in the Indonesian market. The `broker` command suite lets you fetch, cache, and analyze broker summary data from Stockbit.

### Why Foreign Flow Matters in IDX

| Metric | What It Tells You |
|--------|-------------------|
| **Foreign Net Buy** | Foreigners accumulating → often bullish signal |
| **Foreign Net Sell** | Foreigners distributing → potential weakness |
| **Consecutive Buy Days** | Sustained accumulation pattern |
| **Top Brokers** | Which brokers are driving the flow |

### Setting Up Authentication

Stockbit requires a JWT token from your browser session:

```bash
# Step 1: Get your token from Stockbit
# 1. Login to stockbit.com
# 2. Open DevTools (F12) → Network tab
# 3. Click any stock ticker
# 4. Filter for "exodus" requests
# 5. Copy the Bearer token from Authorization header

# Step 2: Configure the token
saham broker auth "eyJhbGciOiJSUzI1NiIsInR5cCI6..."

# Step 3: Verify it works
saham broker status
```

**Note:** Tokens expire in ~24 hours. You'll need to refresh periodically.

### Fetching Broker Data

```bash
# Fetch last 30 days (default)
saham broker fetch BBCA

# Fetch 90 days of history
saham broker fetch BBRI --days 90

# Specific date range
saham broker fetch TLKM --start 2024-01-01 --end 2024-06-30

# Force refresh from Stockbit (ignore cache)
saham broker fetch BBCA --refresh
```

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--days` | `-d` | 30 | Number of days to fetch |
| `--start` | `-s` | — | Start date (YYYY-MM-DD) |
| `--end` | `-e` | — | End date (YYYY-MM-DD) |
| `--refresh` | `-r` | false | Force refresh from Stockbit |
| `--db` | | ~/.ai-saham/data.db | Database path |

### Viewing Foreign Flow

```bash
# Show foreign flow summary
saham broker flow BBCA

# Last 20 trading days
saham broker flow BBRI --days 20
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
saham broker top BBCA

# Top brokers for specific date
saham broker top BBRI --date 2025-01-15
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
# Check if Stockbit is configured and working
saham broker status
```

**Output:**
```
Stockbit token: Configured
Validating...
Status: Connected and working
```

### Importing Broker Data from CSV

Don't have Stockbit access? Import broker data from any CSV source (RTI exports, manual downloads, spreadsheets):

```bash
# Auto-detect format and import
saham broker import data.csv

# Preview without importing
saham broker import data.csv --preview

# Use custom column mapping
saham broker import data.csv --mapping my_format

# Control error handling
saham broker import data.csv --on-error skip    # Skip invalid rows (default)
saham broker import data.csv --on-error fail    # Stop on first error
saham broker import data.csv --on-error report  # Import valid rows, report all errors
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
saham broker mappings
```

**Output:**
```
Available CSV Mappings:
----------------------------------------
  default (built-in auto-detection)
  rti_export
  stockbit_manual

Use with: saham broker import data.csv --mapping <name>
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
# 1. Set up authentication (once per day)
saham broker auth "your-token-here"

# 2. Fetch broker data
saham broker fetch BBCA --days 90

# 3. View the flow
saham broker flow BBCA

# 4. Use in backtest (requires broker data pre-loaded)
saham backtest BBCA --strategy foreign-accumulation
```

---

## 8. Backtesting - The `backtest` Command

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
saham backtest BBCA --strategy momentum
saham backtest BBRI -S momentum --start 2024-01-01 --end 2024-12-31

# Or use explicit path
saham backtest TLKM -S ./strategies/my_strat/strategy.yaml --verbose

# Backward compatible: Use rules file directly
saham backtest BBCA --rules-file config/custom_rules.yaml.example
saham backtest ASII -r rules.yaml --capital 50000000
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

Any formula created via `create-indicator` and saved to `~/.ai-saham/formulas.yaml` can be used directly in rules without re-defining them:

```yaml
# First, create your formula once:
# saham create-indicator "smoothed RSI" --name SMOOTH_RSI

# Then use it in rules.yaml - no definition needed!
version: 1
name: "smooth_rsi_strategy"
default_outcome: MODERATE

rules:
  - name: oversold
    when:
      indicator: SMOOTH_RSI   # Uses formula from ~/.ai-saham/formulas.yaml
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
saham risk BBCA --rules-file config/my_rules.yaml

# Backtest custom rules
saham backtest BBCA --rules-file config/my_rules.yaml --verbose
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
    ├── strategy.yaml   # Required: your rules
    ├── README.md       # Optional: documentation
    ├── tests/          # Optional: test cases
    └── examples/       # Optional: example usage
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
| `--provider` | `-p` | mock | AI provider (claude/openai/gemini/ollama/mock) |
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
  2. Run: saham backtest BBCA --strategy momentum
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
Run 'saham backtest TICKER --strategy NAME' to use a strategy.
```

**Location Badges:**
- No badge = local (`./strategies/`)
- `[user]` = user directory (`~/.ai-saham/strategies/`)

### Using Strategies in Backtest

```bash
# By name (recommended)
saham backtest BBCA --strategy momentum

# By explicit path
saham backtest BBCA -S ./strategies/momentum/strategy.yaml
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

## 11. AI-Enhanced Analysis (Optional)

AI is **OFF by default**. The system works completely without AI. Use AI for:
- Learning what indicators mean
- Getting a second opinion
- Explaining complex market conditions
- **Translating natural language to formulas** (new!)

### Enabling AI Explanation

```bash
# Add --explain to risk assessment
saham risk BBCA --explain

# Specify provider
saham risk BBCA --explain --provider ollama

# Use specific model
saham risk BBCA --explain --provider ollama --model llama3:8b
```

### AI Providers

| Provider | Requires | Best For |
|----------|----------|----------|
| `claude` | `ANTHROPIC_API_KEY` | High-quality explanations |
| `openai` | `OPENAI_API_KEY` | Widely available |
| `gemini` | `GOOGLE_API_KEY` | Good free tier |
| `ollama` | Local server | Privacy, no API costs |
| `mock` | Nothing | Testing |

### Setting Up Ollama (Local AI)

```bash
# Install Ollama (macOS)
brew install ollama

# Start server
ollama serve

# Pull a model (one time)
ollama pull llama3:8b

# Use with saham
saham risk BBCA --explain --provider ollama --model llama3:8b
```

### AI for Sentiment Classification

```bash
# Default: keyword-based (faster, offline)
saham sentiment BBCA

# AI-powered (more nuanced)
saham sentiment BBCA --ai-classify
saham sentiment BBCA --ai-classify --provider ollama
```

### AI Formula Translator (Programmatic)

Don't know formula syntax? Describe what you want in plain English:

```python
from src.application.use_case.create_indicator_from_intent import (
    CreateIndicatorFromIntentRequest,
    CreateIndicatorFromIntentUseCase,
)
from src.infrastructure.ai import FormulaTranslatorFactory

translator = FormulaTranslatorFactory.create(provider="ollama")
use_case = CreateIndicatorFromIntentUseCase(translator=translator)

response = use_case.execute(
    CreateIndicatorFromIntentRequest(
        intent="smoothed RSI with 14-period and 10-day smoothing"
    )
)

print(response.formula)  # "SMA(RSI(14), 10)"
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

## 12. Indicator Management Commands

Create, list, and manage custom indicators from the command line.

### `create-indicator` - Create from Natural Language

Use AI to translate a description into a formula:

```bash
# Basic usage (saves to ~/.ai-saham/formulas.yaml)
saham create-indicator "smoothed RSI with 14-period and 10-day smoothing" --name SMOOTH_RSI

# Specify AI provider
saham create-indicator "MACD line" --name MACD --provider claude

# Use local Ollama
saham create-indicator "average true range" --name ATR14 --provider ollama

# Don't save (just see the formula)
saham create-indicator "price distance from 50-day SMA" --no-save
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--name` | `-n` | auto-generated | Indicator name (uppercase) |
| `--provider` | `-p` | mock | AI provider (claude/openai/gemini/ollama/mock) |
| `--model` | `-m` | provider default | Model name |
| `--save/--no-save` | | save | Save formula to storage |
| `--formulas` | | ~/.ai-saham/formulas.yaml | Custom storage path |

### `list-indicators` - View All Indicators

See built-in, plugin, and custom indicators:

```bash
# List all indicators
saham list-indicators

# Show formula expressions
saham list-indicators --formulas
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

### `show-formula` - View Formula Details

See the full details of a saved formula:

```bash
saham show-formula SMOOTH_RSI
```

**Output:**
```
Name:    SMOOTH_RSI
Formula: SMA(RSI(14), 10)
Intent:  smoothed RSI with 14-period and 10-day smoothing
Created: 2025-01-27 10:30:45
```

### `delete-indicator` - Remove Custom Formula

Delete a saved formula (built-ins cannot be deleted):

```bash
# With confirmation prompt
saham delete-indicator SMOOTH_RSI

# Skip confirmation
saham delete-indicator SMOOTH_RSI --force
```

---

## 13. Complete Workflow Examples

### Conservative Investor Workflow

Goal: Identify low-risk entry points for long-term holdings.

```bash
# Step 1: Get data (2 years for perspective)
saham fetch BBCA --days 730

# Step 2: Check long-term trend
saham sma BBCA --period 200

# Step 3: Risk assessment with strict thresholds
saham risk BBCA --profile conservative

# Step 4: Verify with all profiles
saham risk BBCA --all

# Step 5: Check news context
saham risk BBCA --with-sentiment
```

**Decision Framework:**
- All profiles agree on LOW_RISK → Strong buy signal
- Conservative shows LOW_RISK, others MODERATE → Decent entry
- Any profile shows HIGH_RISK → Wait for better entry

### Active Trader Workflow

Goal: Find short-term momentum opportunities.

```bash
# Step 1: Fresh data
saham fetch BBRI --refresh

# Step 2: Fast indicators
saham indicators BBRI --sma 10 --ema 9 --rsi 7

# Step 3: Aggressive profile for early signals
saham risk BBRI --profile aggressive

# Step 4: Get AI explanation
saham risk BBRI --profile aggressive --explain --provider ollama

# Step 5: Current sentiment
saham sentiment BBRI --days 1
```

### Strategy Developer Workflow

Goal: Build and test a custom trading strategy.

```bash
# Step 1: Get enough historical data
saham fetch TLKM --days 730

# Step 2: Create a strategy package
saham strategy init my_strategy

# Step 3: Edit the strategy in your editor
vim strategies/my_strategy/strategy.yaml
# ... define your indicators and rules ...

# Step 4: Validate the strategy
saham strategy validate my_strategy

# Step 5: Test rules on current data
saham risk TLKM --rules-file strategies/my_strategy/strategy.yaml

# Step 6: Backtest on historical data
saham backtest TLKM --strategy my_strategy --start 2023-01-01 --verbose

# Step 7: Iterate until metrics are acceptable
# Step 8: Share or version control your strategy
git add strategies/my_strategy
git commit -m "Add my_strategy"
```

### Custom Formula Workflow

Goal: Create a custom indicator and use it in trading rules.

```bash
# Step 1: Create custom formula using AI
saham create-indicator "smoothed RSI with 14-period and 10-day smoothing" \
    --name SMOOTH_RSI --provider ollama

# Step 2: Verify it works
saham compute SMOOTH_RSI BBCA --tail 10

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
saham risk BBCA --rules-file config/smooth_rules.yaml

# Step 5: Backtest the strategy
saham backtest BBCA --rules-file config/smooth_rules.yaml --verbose

# Step 6: List all your custom formulas
saham list-indicators --formulas
```

**Key insight:** Once you create a formula with `create-indicator`, it's saved globally and can be used in any rules file without redefining it.

### Foreign Flow Analysis Workflow

Goal: Analyze foreign investor behavior and build a foreign flow strategy.

```bash
# Step 1: Set up Stockbit authentication (once per day)
# Get token from stockbit.com DevTools → Network → exodus requests
saham broker auth "eyJhbGciOiJSUzI1NiIs..."

# Step 2: Verify connection
saham broker status

# Step 3: Fetch broker data for target stocks
saham broker fetch BBCA --days 90
saham broker fetch BBRI --days 90
saham broker fetch BMRI --days 90

# Step 4: Analyze foreign flow patterns
saham broker flow BBCA --days 20
saham broker flow BBRI --days 20

# Step 5: Check top brokers on specific dates
saham broker top BBCA --date 2025-01-27

# Step 6: Fetch price data for backtesting
saham fetch BBCA --days 365
saham fetch BBRI --days 365

# Step 7: Use the pre-built foreign accumulation strategy
saham backtest BBCA --strategy foreign-accumulation --verbose

# Step 8: Or create your own strategy
saham strategy init my_flow_strategy
# Edit to use FOREIGN_FLOW indicators
vim strategies/my_flow_strategy/strategy.yaml
saham strategy validate my_flow_strategy
saham backtest BBCA --strategy my_flow_strategy
```

**Key Insights:**
- Foreign net buy > 50B for 3+ days often precedes price moves
- Consecutive buy days matter more than single-day spikes
- Watch for divergence between foreign flow and price

---

## 14. Command Reference (Quick Lookup)

| Command | Purpose | Key Options |
|---------|---------|-------------|
| `saham version` | Show version | — |
| `saham fetch TICKER` | Download OHLCV data | `--days`, `--refresh`, `--db` |
| `saham sma TICKER` | Simple Moving Average | `--period`, `--field`, `--days` |
| `saham ema TICKER` | Exponential Moving Average | `--period`, `--field`, `--days` |
| `saham rsi TICKER` | Relative Strength Index | `--period`, `--days` |
| `saham compute INDICATOR TICKER` | Compute any indicator | `--period`, `--days`, `--tail`, `--db` |
| `saham indicators TICKER` | All indicators combined | `--sma`, `--ema`, `--rsi`, `--days` |
| `saham risk TICKER` | Risk assessment | `--profile`, `--all`, `--rules-file`, `--explain`, `--with-sentiment` |
| `saham sentiment TICKER` | News sentiment | `--days`, `--max`, `--ai-classify` |
| `saham broker auth TOKEN` | Configure Stockbit token | `--validate/--no-validate` |
| `saham broker status` | Check Stockbit connection | — |
| `saham broker fetch TICKER` | Fetch broker summary data | `--days`, `--start`, `--end`, `--refresh` |
| `saham broker flow TICKER` | View foreign flow summary | `--days` |
| `saham broker top TICKER` | View top brokers | `--date` |
| `saham broker import FILE` | Import broker data from CSV | `--preview`, `--mapping`, `--on-error` |
| `saham broker mappings` | List available CSV mappings | — |
| `saham strategy init NAME` | Create strategy package | `--dir`, `--force` |
| `saham strategy create INTENT` | Create strategy from natural language | `--name`, `--provider`, `--save/--no-save` |
| `saham strategy validate NAME` | Validate strategy | `--strict` |
| `saham strategy list` | List available strategies | `--verbose`, `--all` |
| `saham backtest TICKER` | Strategy backtesting | `--strategy`/`--rules-file`, `--start`, `--end`, `--capital`, `--verbose` |
| `saham create-indicator` | Create formula from NL | `--name`, `--provider`, `--save/--no-save` |
| `saham list-indicators` | List all indicators | `--formulas` |
| `saham show-formula NAME` | Show formula details | — |
| `saham delete-indicator NAME` | Delete custom formula | `--force` |

---

## Appendix A: Why Offline-First Matters

1. **Reproducibility** - Same data = same results
2. **Speed** - No network latency for cached analysis
3. **Privacy** - Your portfolio analysis stays local
4. **Reliability** - Works during internet outages
5. **Cost** - No ongoing API fees for basic analysis

Data is cached at `~/.ai-saham/data.db`. Use `--refresh` to update when needed.

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
Tip: Run 'saham fetch BBCA' first to download data.
```

**Solution:** Fetch data first with `saham fetch TICKER`

### "Database not found"

```
Error: Database not found at /path/to/data.db
```

**Solution:** Run `saham fetch` for any ticker to create the database

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
   saham backtest BBCA --strategy ./path/to/strategy.yaml
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
   saham create-indicator "smoothed RSI" --name SMOOTH_RSI --provider mock
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
saham list-indicators
```

### "AI explanation unavailable"

```
AI explanation unavailable: ANTHROPIC_API_KEY not set
Tip: Set the appropriate API key environment variable.
```

**Solution:**
- Set API key: `export ANTHROPIC_API_KEY=sk-...`
- Or use local Ollama: `--provider ollama`
- Or use mock for testing: `--provider mock`

### "Stockbit token not configured"

```
Error: Stockbit token not configured.
Run 'saham broker auth <token>' to set your token.
```

**Solution:** You need to configure your Stockbit JWT token:

1. Login to stockbit.com in your browser
2. Open DevTools (F12) → Network tab
3. Click any stock ticker
4. Filter for "exodus" requests
5. Copy the Bearer token from the Authorization header
6. Run: `saham broker auth "your-token-here"`

### "Stockbit token expired or invalid"

```
Error: Stockbit token expired or invalid.
Please get a new token from stockbit.com
```

**Solution:** Stockbit tokens expire in ~24 hours. Get a fresh token:
```bash
# Get new token from browser DevTools
saham broker auth "new-token-here"
```

### "No broker data found"

```
No data found. Run 'saham broker fetch BBCA' first.
```

**Solution:** Fetch broker data before viewing:
```bash
saham broker fetch BBCA --days 30
saham broker flow BBCA
```

---

**DISCLAIMER:** This tool provides technical analysis only, not financial advice. Always do your own research and consult qualified professionals before making investment decisions.
