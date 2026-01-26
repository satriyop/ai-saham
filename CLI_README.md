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
```

**What just happened?**
1. `version` - Confirmed the CLI is installed
2. `fetch` - Downloaded 1 year of daily price data for Bank Central Asia (BBCA)
3. `risk --all` - Analyzed the stock using 3 different risk tolerance profiles

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

### 4.4 Combining Indicators - The `indicators` Command

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

## 7. Backtesting - The `backtest` Command

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
# Backtest with custom rules (rules file required)
saham backtest BBCA --rules-file config/custom_rules.yaml.example

# Specify date range
saham backtest BBRI -r rules.yaml --start 2024-01-01 --end 2024-12-31

# Different starting capital
saham backtest TLKM -r rules.yaml --capital 50000000

# See individual trades
saham backtest ASII -r rules.yaml --verbose
```

### Key Options

| Option | Purpose | Example |
|--------|---------|---------|
| `--rules-file` / `-r` | Strategy rules (required) | `-r my_rules.yaml` |
| `--start` | Start date | `--start 2024-01-01` |
| `--end` | End date | `--end 2024-12-31` |
| `--capital` | Initial capital (IDR) | `--capital 50000000` |
| `--verbose` | Show each trade | Debug your strategy |

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

## 8. Custom Rules DSL

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

### Built-in Indicators

These are always available without definition:

| Name | Default Period | Access As |
|------|---------------|-----------|
| RSI | 14 | `indicator: RSI` |
| SMA | 20 | `indicator: SMA` |
| EMA | 20 | `indicator: EMA` |

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

## 9. AI-Enhanced Analysis (Optional)

AI is **OFF by default**. The system works completely without AI. Use AI for:
- Learning what indicators mean
- Getting a second opinion
- Explaining complex market conditions

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

---

## 10. Complete Workflow Examples

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

# Step 2: Create rules file (use example as template)
cp config/custom_rules.yaml.example config/my_strategy.yaml

# Step 3: Edit rules in your editor
# ... define your indicators and rules ...

# Step 4: Test rules on current data
saham risk TLKM --rules-file config/my_strategy.yaml

# Step 5: Backtest on historical data
saham backtest TLKM -r config/my_strategy.yaml --start 2023-01-01 --verbose

# Step 6: Iterate until metrics are acceptable
```

---

## 11. Command Reference (Quick Lookup)

| Command | Purpose | Key Options |
|---------|---------|-------------|
| `saham version` | Show version | — |
| `saham fetch TICKER` | Download OHLCV data | `--days`, `--refresh`, `--db` |
| `saham sma TICKER` | Simple Moving Average | `--period`, `--field`, `--days` |
| `saham ema TICKER` | Exponential Moving Average | `--period`, `--field`, `--days` |
| `saham rsi TICKER` | Relative Strength Index | `--period`, `--days` |
| `saham indicators TICKER` | All indicators combined | `--sma`, `--ema`, `--rsi`, `--days` |
| `saham risk TICKER` | Risk assessment | `--profile`, `--all`, `--rules-file`, `--explain`, `--with-sentiment` |
| `saham sentiment TICKER` | News sentiment | `--days`, `--max`, `--ai-classify` |
| `saham backtest TICKER` | Strategy backtesting | `--rules-file` (required), `--start`, `--end`, `--capital`, `--verbose` |

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

### "AI explanation unavailable"

```
AI explanation unavailable: ANTHROPIC_API_KEY not set
Tip: Set the appropriate API key environment variable.
```

**Solution:**
- Set API key: `export ANTHROPIC_API_KEY=sk-...`
- Or use local Ollama: `--provider ollama`
- Or use mock for testing: `--provider mock`

---

**DISCLAIMER:** This tool provides technical analysis only, not financial advice. Always do your own research and consult qualified professionals before making investment decisions.
