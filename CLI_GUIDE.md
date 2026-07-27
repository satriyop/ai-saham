# Learning Stock Analysis with AI Saham — Tutorial Guide

> Progressive guide: teaches stock analysis concepts alongside CLI usage.
> For compact command reference → `CLI_REFERENCE.md`
> For troubleshooting → `CLI_TROUBLESHOOTING.md`

---

## 1. Understanding Stock Data

Before analyzing, you need data. The `fetch market` command downloads **OHLCV data** (Open, High, Low, Close, Volume) and **broker flow data** (foreign buy/sell).

### What is OHLCV?

Each trading day produces these 5 values:

| Field | Meaning | Why It Matters |
|-------|---------|----------------|
| **Open** | First trade price | Shows where market opened |
| **High** | Highest price | Shows buyer strength |
| **Low** | Lowest price | Shows seller pressure |
| **Close** | Last trade price | Most important — where it ended |
| **Volume** | Shares traded | Shows conviction behind moves |

### Data Sources

Two candle providers: `yahoo` (default, Yahoo Finance) and `idx` (IDX public API, no auth).

```bash
saham fetch market BBCA --days 365
saham fetch market BBCA --days 365 --provider idx
```

---

## 2. Technical Indicators

Technical indicators transform raw price data into actionable signals.

### SMA — Simple Moving Average

Smooths out price noise by averaging the last N closing prices.

- Price above SMA → Bullish tendency
- Price below SMA → Bearish tendency

**Period Guide:**

| Period | Timeframe | Use Case |
|--------|-----------|----------|
| 10 | 2 weeks | Short-term trading |
| 20 | 1 month | Default analysis |
| 50 | ~2.5 months | Medium-term trend |
| 200 | ~10 months | Long-term trend |

```bash
saham indicator compute SMA BBCA          # 20-day (default)
saham indicator compute SMA BBCA --period 50
saham indicator compute SMA BBCA --period 200
```

### EMA — Exponential Moving Average

Like SMA but gives more weight to recent prices. Reacts faster to price changes. Matches TradingView calculations.

| Scenario | Better Choice | Why |
|----------|---------------|-----|
| Swing trading | EMA | Faster reaction to reversals |
| Long-term investing | SMA | Less whipsaw on noise |
| Crossover strategies | Both | EMA crosses SMA = signal |

```bash
saham indicator compute EMA BBCA           # 20-day (default)
saham indicator compute EMA BBCA --period 9
```

### RSI — Relative Strength Index

Measures momentum on a scale of 0–100.

- **> 70:** Overbought — buyers may be exhausted
- **< 30:** Oversold — sellers may be exhausted
- **30–70:** Neutral territory

```bash
saham indicator compute RSI BBCA           # 14-day (default)
saham indicator compute RSI BBCA --period 7
saham indicator compute RSI BBCA --period 21
```

### Combined Snapshot

When multiple indicators agree, signals are stronger.

```bash
saham indicator snapshot BBCA
saham indicator snapshot BBRI --sma 50 --ema 50 --rsi 7
```

| SMA Trend | EMA Trend | RSI | Interpretation |
|-----------|-----------|-----|----------------|
| Price > SMA | Price > EMA | > 50 | Strong bullish alignment |
| Price < SMA | Price < EMA | < 50 | Strong bearish alignment |
| Mixed | Mixed | ~50 | No clear signal |

### Custom Formulas

Create indicators using mathematical expressions:

```bash
saham indicator create "smoothed RSI with 14-period and 10-day smoothing" --name SMOOTH_RSI
saham indicator create "MACD line using 12 and 26 period EMAs" --name MACD
```

Formula syntax: `SMA(series, period)`, `EMA(series, period)`, `RSI(period)`, `ATR(period)`,
`OPEN`, `HIGH`, `LOW`, `CLOSE`, `VOLUME`, `+`, `-`, `*`, `/`, `( )`

---

## 3. Risk Assessment

Converts indicator values into actionable assessments using rule-based evaluation.

### Risk Gate Status

- **OPEN** — No configured gate fired (favorable)
- **BLOCKED (gate: Name)** — A risk gate triggered

### Built-in Risk Profiles

Three built-in profiles with different threshold sensitivity:

| Profile | RSI Overbought | RSI Oversold | Best For |
|---------|---------------|--------------|----------|
| **conservative** | > 75 | < 25 | Long-term investing |
| **balanced** | > 70 | < 30 | General analysis |
| **aggressive** | > 65 | < 35 | Active trading |

```bash
saham inspect risk BBCA                    # balanced (default)
saham inspect risk BBCA --all              # all three profiles
saham inspect risk BBCA --with-sentiment   # include news context
saham inspect risk BBCA --trend 20         # risk history over 20 days
saham inspect risk BBCA --format json
```

---

## 4. News Sentiment

Sentiment analysis adds context to price movements by analyzing news headlines. Sentiment does NOT affect risk assessment — it's supplementary information only.

```bash
saham inspect sentiment BBCA               # last 3 days, keyword-classified
saham inspect sentiment BBCA --days 7
saham inspect sentiment BBCA --news-provider google
saham inspect sentiment BBCA --no-ai       # offline keyword mode
```

### Audit Sentiment Accuracy

Checks whether past POSITIVE/NEUTRAL/NEGATIVE classifications were correct after 1, 3, and 5 trading days.

```bash
saham audit sentiment
```

---

## 5. Broker Data & Foreign Flow

Foreign investor flow is one of the most watched metrics in the Indonesian market.

### Why Foreign Flow Matters in IDX

| Metric | What It Tells You |
|--------|-------------------|
| **Foreign Net Buy** | Foreigners accumulating — often bullish |
| **Foreign Net Sell** | Foreigners distributing — potential weakness |
| **Consecutive Buy Days** | Sustained accumulation |
| **Top Brokers** | Which brokers drive the flow |

### Data Providers

| Provider | Auth Required | Data |
|----------|--------------|------|
| **idx** (default) | None | Foreign flow (lots + estimated values) |
| **stockbit** | Browser session (Playwright) | Foreign flow (exact values) + top broker breakdown |

### Workflow

```bash
# 1. Fetch broker data
saham fetch broker BBCA --days 90

# 2. View foreign flow
saham view ticker flow BBCA --days 20

# 3. Top brokers for a date
saham view ticker top-brokers BBCA --date 2025-01-15
```

### Foreign Flow Indicators in Strategies

| Indicator | Description |
|-----------|-------------|
| `FOREIGN_FLOW` | Rolling sum of foreign net value |
| `FOREIGN_FLOW_RATIO` | Foreign flow as % of total value |
| `CONSECUTIVE_FOREIGN_BUY` | Count of consecutive buy days |

### Stockbit Setup

```bash
pip install -e ".[browser]"
playwright install chromium
saham fetch stockbit login
saham fetch stockbit status
saham fetch stockbit test
```

---

## 6. Ticker Dashboard

Read-only view of everything cached about a stock (12 panels). Never fetches from the network.

```bash
saham view BBCA
```

**Panels:** Identity & notation, price & valuation, analyst consensus, ownership,
bandar signal, company profile, recent candles, corporate actions, insider activity,
seasonality, IEV snapshots, sentiment.

Any panel shows "not cached" if data hasn't been fetched yet.

---

## 7. Market Regime

| Regime | Meaning |
|--------|---------|
| **BULLISH** | Strong upward trend |
| **SIDEWAYS** | Mixed, no clear direction |
| **WEAK** | Declining |
| **RISK_OFF** | Bearish — reduce exposure |

Computed from: benchmark SMA20/SMA50 position, breadth (% of universe above SMA20),
breadth change, and foreign flow breadth.

```bash
saham inspect regime
saham inspect regime --as-of 2026-06-01 --verbose
```

---

## 8. Market Context

Cross-market regime context from local cache: VIX, EIDO, USD/IDR, IDX breadth.

```bash
saham view market-context
saham view market-context --date 2026-06-01 --verbose
```

---

## 9. Backtesting

Backtesting tests a strategy on historical data before risking real capital.

### How It Works

1. Replay historical candles chronologically
2. Apply your rules to each candle
3. Generate buy/sell signals
4. Calculate hypothetical returns

### Signal Mapping

| Risk Level | Trade Action |
|------------|--------------|
| LOW_RISK | ENTER_LONG |
| MODERATE | HOLD |
| HIGH_RISK | EXIT_LONG |

```bash
saham strategy backtest BBCA --strategy momentum
saham strategy backtest BBRI -S momentum --start 2024-01-01 --end 2024-12-31
saham strategy backtest BBCA --strategy momentum --capital 50000000 --verbose
```

### Key Metrics

| Metric | What It Tells You | Good Value |
|--------|-------------------|------------|
| Total Return | Overall performance | Positive, beats benchmark |
| Max Drawdown | Worst peak-to-trough drop | Lower is better |
| Win Rate | % profitable trades | > 50% |
| Profit Factor | Gross profit / gross loss | > 1.5 good, > 2 excellent |

### Warning Signs

- Max Drawdown > -30%: Strategy may be too risky
- Win Rate high but Profit Factor low: Small wins, big losses
- Total Trades < 10: Not statistically significant

---

## 10. Custom Rules DSL

Encode your investment philosophy into YAML.

### Basic Structure

```yaml
version: 1
name: "my_strategy"
description: "My personal trading approach"
default_outcome: MODERATE

indicators:
  fast_rsi:
    type: RSI
    period: 7

rules:
  - name: oversold_entry
    priority: 10
    when:
      indicator: fast_rsi
      operator: "<"
      value: 25
    outcome: LOW_RISK
    rationale: "RSI(7) below 25 suggests oversold"
```

### Condition Types

| Type | Syntax |
|------|--------|
| Indicator vs Value | `indicator: RSI`, `operator: "<"`, `value: 30` |
| Indicator vs Indicator | `left: {indicator: fast_ema}`, `operator: ">"`, `right: {indicator: slow_ema}` |
| Compound AND | `all: [condition1, condition2, ...]` |
| Price Field | `indicator: CLOSE` (also: OPEN, HIGH, LOW, VOLUME) |

### Example: EMA Crossover

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

### Evaluation Order

1. Rules sorted by priority (lower number = first)
2. Same priority = file order
3. First matching rule wins
4. No match = `default_outcome`

---

## 11. Strategy Packages

First-class, versionable, portable strategy artifacts.

```
strategies/momentum/
├── strategy.yaml          # Required: your rules
├── strategy.skill.yaml    # Optional: annotation sidecar
├── SKILL.md               # Auto-generated documentation
├── README.md              # Optional: human documentation
├── tests/                 # Optional: test cases
└── examples/              # Optional: usage examples
```

```bash
saham strategy init momentum
saham strategy validate momentum
saham strategy list
```

### AI-Assisted Strategy Creation

```bash
saham strategy create "buy when RSI below 30 and EMA crossover" --name momentum
saham strategy create "conservative RSI strategy" --name conservative_rsi --provider claude
saham strategy create "MACD crossover strategy" --no-save   # preview only
```

### Skill Documentation

Skill system generates machine-readable SKILL.md for strategies.

```bash
saham strategy skill generate rsi-momentum
saham strategy skill generate atr --type indicator
saham strategy skill check         # find stale docs
saham strategy skill index         # rebuild catalog
```

### Strategy Resolution Order

When using `--strategy NAME`:

1. `./NAME/strategy.yaml`
2. `./strategies/NAME/strategy.yaml`
3. `~/.ai-saham/strategies/NAME/strategy.yaml`

If path contains `/` or ends in `.yaml`, used directly.

---

## 12. AI-Enhanced Analysis (Optional)

AI is OFF by default. Use it for explanations, sentiment classification, and strategy/formula generation.

### AI Providers

| Provider | Env Variable | Best For |
|----------|-------------|----------|
| `deepseek` | `DEEPSEEK_API_KEY` | Default, cost-effective |
| `claude` | `ANTHROPIC_API_KEY` | High-quality explanations |
| `openai` | `OPENAI_API_KEY` | Widely available |
| `gemini` | `GOOGLE_API_KEY` | Good free tier |
| `ollama` | Local server | Privacy, no API costs |
| `mock` | Nothing | Testing |

Default provider is `deepseek`.

```bash
saham inspect risk BBCA --explain
saham inspect risk BBCA --explain --provider ollama --model llama3:8b
saham inspect sentiment BBCA --ai-classify --provider claude
```

### Local Ollama Setup

```bash
brew install ollama
ollama serve
ollama pull llama3:8b
saham inspect risk BBCA --explain --provider ollama --model llama3:8b
```

---

## 13. Swing Analysis

Verdict-first swing analysis composing SignalEngine + RiskEngine into the final TradeSetup.

### Swing Setups

| Setup | Question Answered |
|-------|-------------------|
| `foreign-bounce` | Foreign accumulation while price is below foreign VWAP in a range |
| `coiled-spring` | Accumulation plus compressed volatility |
| `smart-money-confirmed` | Smart-money broker flow dominates noise |
| `pullback-continuation` | Uptrend pullback with foreign-flow support |

```bash
saham plan swing BBRI
saham plan swing BBRI --setup foreign-bounce --capital 10000000
saham plan swing BBRI --full                           # all evidence
saham plan swing BBRI --with-technical-gate             # enable technical gate
saham plan swing BBRI --with-market-context             # market context preview
```

---

## 14. Pre-Open Workflow

### Step 1: Pre-Open Screen

```bash
saham screen pre-open --movers-json '[{"ticker":"BBCA","iev":150000}]'
```

### Step 2: Post-open assess (after capture + track)

```bash
saham research pre-open capture
saham research pre-open track
saham assess pre-open --session YYYY-MM-DD
```

### Step 3: Log & Review (paper notebook)

```bash
saham trade pre-open log \
  --observation-id OBS --opening-snapshot-id SNAP
saham trade pre-open review
saham trade pre-open outcome BBCA --entry 9000 --exit 9500 --result target
```

---

## 15. Opening Session Learning Loop

Full operator path: [`docs/runbook_pre_open.md`](docs/runbook_pre_open.md).

```bash
# Cron-owned learning (also install via ./install_cron.sh)
saham research pre-open capture
saham research pre-open track
saham research pre-open labels
saham research pre-open evaluate
saham research pre-open status

# Human post-open (not cron; not a learning label)
saham assess pre-open --session YYYY-MM-DD
saham trade pre-open log --observation-id … --opening-snapshot-id …
```

Retired: `research pre-open grade|prompt|tune`, `trade confirm`.

---

## 16. Foreign Accumulation Screener

Screen stocks for institutional foreign accumulation patterns.

```bash
# Single window (default 7 days)
saham screen accum --universe lq45

# Multi-window comparison (7, 30, 90 days)
saham screen accum --universe lq45 --multi

# Filters
saham screen accum --universe lq45 --min-foreign-flow-score 60 --top 10
saham screen accum --universe lq45 --vwap-only
saham screen accum --universe lq45 --squeeze-only
saham screen accum --universe lq45 --save morning-watch
```

### Pattern Labels

| Label | Meaning |
|-------|---------|
| `sustained` | Score ≥60 on all 3 windows |
| `building` | Strong recent, weaker long-term |
| `fresh rotation` | Strong 7d only |
| `coiled spring` | Squeeze + score ≥60 |
| `long-term only` | Strong 90d, weak recent |
| `weak` | No window scores ≥60 |

### Watchlist Persistence

```bash
saham screen accum --universe lq45 --save morning-watch
saham screen watchlist                          # list saved
saham screen watchlist morning-watch            # show entries
saham screen compare morning-watch              # diff against fresh screen
```

---

## 17. Terminal Charts

ASCII charts for terminal use (requires `pip install plotext`).

```bash
saham inspect chart price BBCA --sma 20 --ema 9 --days 120
saham inspect chart rsi BBCA --period 9 --days 120
saham inspect chart volume BBCA --days 30
```

---

## 18. Complete Workflow Examples

### Conservative Investor Workflow

```bash
# Step 1: Get 2 years of data
saham fetch market BBCA --days 730

# Step 2: Check long-term trend
saham indicator compute SMA BBCA --period 200

# Step 3: Risk assessment
saham inspect risk BBCA
saham inspect risk BBCA --all          # compare all profiles

# Step 4: Check news context
saham inspect risk BBCA --with-sentiment
```

### Active Trader Workflow

```bash
# Step 1: Fresh data
saham fetch market BBRI --days 365 --refresh

# Step 2: Fast indicators
saham indicator snapshot BBRI --sma 10 --ema 9 --rsi 7

# Step 3: Risk + AI explanation
saham inspect risk BBRI --explain --provider ollama

# Step 4: Sentiment
saham inspect sentiment BBRI --days 1
```

### Strategy Developer Workflow

```bash
# Step 1: Historical data
saham fetch market TLKM --days 730

# Step 2: Create strategy package
saham strategy init my_strategy

# Step 3: Edit strategy.yaml in your editor, then validate
saham strategy validate my_strategy

# Step 4: Backtest
saham strategy backtest TLKM --strategy my_strategy --start 2023-01-01 --verbose

# Step 5: Iterate
# Step 6: Share
git add strategies/my_strategy
git commit -m "Add my_strategy"
```

### Foreign Flow Analysis

```bash
# 1. Fetch broker data
saham fetch broker BBCA --days 90

# 2. View flow patterns
saham view ticker flow BBCA --days 20

# 3. Top brokers
saham view ticker top-brokers BBCA

# 4. Backtest foreign accumulation strategy
saham strategy backtest BBCA --strategy foreign-accumulation --verbose
```

---

## Appendix A: Why Offline-First Matters

1. **Reproducibility** — Same data = same results
2. **Speed** — No network latency for cached analysis
3. **Privacy** — Your portfolio analysis stays local
4. **Reliability** — Works during internet outages
5. **Cost** — No ongoing API fees for basic analysis

Data is cached at `./data.db` (configurable with `--db`). Use `--refresh` to update.

---

## Appendix B: Glossary

| Term | Definition |
|------|------------|
| **OHLCV** | Open, High, Low, Close, Volume — daily trading data |
| **SMA** | Simple Moving Average — average of last N prices |
| **EMA** | Exponential Moving Average — weighted average favoring recent prices |
| **RSI** | Relative Strength Index — momentum oscillator (0-100) |
| **Overbought** | RSI > 70 — may be due for pullback |
| **Oversold** | RSI < 30 — may be due for bounce |
| **Period** | Number of days used in indicator calculation |
| **Candle** | One day's OHLCV data |
| **Drawdown** | Peak-to-trough decline during backtesting |
| **Profit Factor** | Total wins divided by total losses |
| **Foreign Flow** | Net buying/selling by foreign investors (ASING) |
| **Broker Summary** | Daily breakdown of which brokers bought/sold |
| **Accumulation** | Pattern of sustained buying |
| **Distribution** | Pattern of sustained selling |

---

**DISCLAIMER:** This tool provides technical analysis only, not financial advice.
Always do your own research and consult qualified professionals before making
investment decisions.
