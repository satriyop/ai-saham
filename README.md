# AI Saham - Stock Analysis CLI

[![CI](https://github.com/satriyop/ai-saham/actions/workflows/ci.yml/badge.svg)](https://github.com/satriyop/ai-saham/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A **local-first, production-grade CLI application** for stock analysis focused on the Indonesia Stock Exchange (IDX).

## Features

- **Technical Indicators** - SMA, EMA, RSI, ATR with professional-grade calculations
- **Formula DSL** - Compose indicators with expressions like `SMA(RSI(14), 10)`
- **Plugin System** - Extend with custom indicators (ATR included as example)
- **Risk Assessment** - Three built-in profiles (conservative, balanced, aggressive) + trend mode
- **Custom Rules DSL** - Define your own rules via YAML configuration
- **Strategy Packages** - First-class, versionable, portable strategy artifacts
- **Skill Documentation** - Auto-generated SKILL.md with drift detection and project-wide catalog
- **AI Strategy Creator** - Describe strategies in natural language, get complete YAML
- **AI Formula Translator** - Describe indicators in natural language, get formula back
- **AI Explanations** - Get AI-powered insights (DeepSeek, Claude, OpenAI, Gemini, Ollama)
- **News Sentiment** - Analyze news headlines with keyword or AI classification + accuracy audit
- **Backtesting** - Test strategies on historical data with detailed metrics
- **Foreign Accumulation Screener** - Detect institutional accumulation across LQ45/IDX80
- **Intraday Pre-Open Screener** - Pre-market movers + order book confirmation workflow
- **Opening Session Learning Loop** - Automated snapshot→track→grade→tune cycle for opening scalping
- **Swing Trade Workflow** - Unified screen → analyze → size → backtest → journal
- **Corporate Action Risk** - Dividend/RUPS/rights issue flags from live Stockbit calendar
- **Seasonality Signal** - Monthly return % and win rate ranking per ticker (5-year history)
- **Running Trade Broker Attribution** - Real-time absorption ratio and institutional flow via `--broker-confirm`
- **Insider Activity Signal** - ⭐ INSIDER BUY flags from Stockbit director/commissioner transactions
- **Analyst Consensus** - 📊 Buy/Hold/Sell counts + price target upside from Stockbit analyst ratings
- **Shareholding Composition** - 🏦 Institutional/individual split + top controlling holder from IDX filings
- **Bandar Detector** - 🔍 Stockbit institutional operator accumulation/distribution signal (-9 to +9 score)
- **Company Fundamentals** - 📈 P/E, ROE, Piotroski F-Score, quality gate with dividend yield + YoY growth
- **Market Regime Detection** - Deterministic IHSG regime context (BULLISH/SIDEWAYS/WEAK/RISK_OFF)
- **Terminal Charts** - ASCII price/RSI/volume charts in-terminal
- **Batch Update** - Single command to refresh candles + broker flow for entire universes
- **Broker & Foreign Flow** - Track foreign investor activity from IDX (public, no auth) or Stockbit
- **Hexagonal Architecture** - Clean separation of domain, application, and infrastructure

---

## Quick Start (Daily Workflow)

```bash
# 1. Start the day: Update market data for your universe (e.g., LQ45)
saham fetch market --universe lq45

# 2. Morning (08:50 WIB): Pre-open screening + opening learning loop
saham learn snapshot                  # NCP-locked prediction at 08:57
saham learn track                     # 5-min orderbook tracking 09:00-09:30
saham learn grade                     # Accuracy report post-track

# 3. Afternoon: Screen for swing trade candidates (foreign accumulation)
saham screen accum --universe lq45 --multi

# 4. Deep Dive: Analyze a specific ticker (unified view: risk + flow + sentiment)
saham analyze swing BBRI --capital 10000000

# 5. Tune: Let AI recommend config improvements from today's accuracy
saham learn tune

# 6. Visual Check: View terminal chart
saham analyze chart price BBRI --sma 20 --ema 50
```

---

## CLI Command Hierarchy

`ai-saham` is organized around the daily analysis lifecycle.

| Group | Purpose | Key Sub-commands |
| :--- | :--- | :--- |
| **`saham today`** | Daily briefing | read-only regime + candidate summary |
| **`saham fetch`** | Data Ingestion | `market`, `broker`, `broker-import`, `broker-history`, `broker-top-foreign`, `iev`, `status`, `stockbit`, `universe` |
| **`saham screen`** | Candidate Discovery | `pre-open`, `accum` |
| **`saham learn`** | Feedback Loop | `snapshot`, `track`, `grade`, `prompt`, `tune` |
| **`saham view`** | Read-only Browsing | `broker status`, `broker flow`, `broker top`, `broker history`, `broker top-foreign`, `broker mappings` |
| **`saham indicator`**| Technical Math | `compute`, `snapshot`, `create`, `list`, `show`, `delete` |
| **`saham analyze`** | Insights & Charts | `risk`, `compare`, `sentiment`, `audit`, `regime`, `chart`, `swing`, `accum-audit`, `swing-compare` |
| **`saham strategy`** | Strategy Lifecycle| `init`, `validate`, `list`, `create`, `backtest`, `skill` |
| **`saham trade`** | Paper Trade Workspace | `confirm`, `outcome`, `size`, `backtest-swing`, `backtest-intraday`, `log intraday/swing`, `review intraday/swing` |

---

## Installation

Requires **Python 3.11+**.

### Using Virtual Environment (Recommended)

```bash
# Clone the repository
git clone <repository-url>
cd ai-saham

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install the package
pip install -e .

# Or with development dependencies
pip install -e ".[dev]"

# Optional: terminal charting
pip install plotext

# Optional: Stockbit browser automation
pip install -e ".[browser]"
playwright install chromium
```

### Verify Installation

```bash
saham version
```

---

### Server Deployment

To deploy the automated IDX morning session on a server, run the install script once
after cloning and installing the package:

```bash
./install_cron.sh                    # uses current directory as project root
./install_cron.sh /opt/ai-saham     # explicit path (for non-default deploy locations)
```

This installs 5 cron jobs (Mon–Fri, IDX calendar). The host crontab is expected
to run in `Asia/Jakarta` local time:

| Time (WIB) | Command | Purpose |
|-----------|---------|---------|
| 08:55 | `saham fetch iev` | Collect IEV pre-open snapshot |
| 08:57 | `saham learn snapshot` | NCP-locked screener prediction |
| 09:00 | `saham learn track` | 5-min orderbook tracking until 09:30 |
| 09:35 | `saham learn grade` | Compute accuracy report |
| 09:40 | `saham learn tune` | AI config recommendations |

Logs are written to `logs/` in the project directory.

The script is **idempotent** — safe to re-run after upgrades or path changes.
It removes any previous saham cron entries before installing fresh ones.

**Prerequisite:** Stockbit session must be active before the first cron run.
Run `saham fetch stockbit login` once on the server to authenticate.

---

### Manual Session Script

For interactive monitoring at the keyboard (not required for server deployments):

```bash
./loop_intraday.sh
```

This script owns Playwright from 08:45–08:55 (screen pre-open loop), then hands off
to the crontab. After 09:00 it runs `saham trade confirm` every 30s until 09:05.
The crontab and this script are designed to not conflict on the shared Stockbit
browser profile.

---

## CLI Commands




### `saham indicator compute EMA` - Exponential Moving Average

Uses SMA-seeded initialization (matches TradingView, Bloomberg).

```bash
saham indicator compute EMA BBCA            # EMA(20) on close
saham indicator compute EMA BBRI --period 50
```

---

### `saham indicator compute RSI` - Relative Strength Index

Uses Wilder's smoothed moving average.

```bash
saham indicator compute RSI BBCA            # RSI(14)
saham indicator compute RSI BBRI --period 7
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--period` | `-p` | 14 | RSI period |
| `--days` | `-d` | 365 | Days of history |

**RSI Interpretation:** >70 overbought, <30 oversold, 30-70 neutral

---

### `saham indicator compute` - Compute Any Indicator

Compute any registered indicator (built-in, plugin, or custom formula) by name. Replaces the legacy standalone `saham sma`, `saham ema`, and `saham rsi` commands.

```bash
saham indicator compute RSI BBCA              # Built-in indicator
saham indicator compute SMA BBCA --period 50  # With custom period
saham indicator compute ATR BBCA              # Plugin indicator
saham indicator compute SMOOTH_RSI BBCA       # Custom formula
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--period` | `-p` | 14 | Period (ignored for formulas) |
| `--days` | `-d` | 365 | Days of data to fetch |
| `--tail` | `-t` | 30 | Show last N values |

---

### `saham indicator snapshot` - All Indicators Combined

Calculate SMA, EMA, and RSI together with aligned dates.

```bash
saham indicator snapshot BBCA               # Default periods
saham indicator snapshot BBRI --sma 50 --ema 50 --rsi 7
saham indicator snapshot BBCA --format json  # JSON output
```

| Option | Default | Description |
|--------|---------|-------------|
| `--sma` | 20 | SMA period |
| `--ema` | 20 | EMA period |
| `--rsi` | 14 | RSI period |
| `--days` | 365 | Days of history |
| `--format` | table | Output format: `table` or `json` |

---

### `saham analyze risk` - Risk Assessment

Assess risk using rule-based evaluation with optional AI explanation.

```bash
# Built-in profiles
saham analyze risk BBCA                           # Balanced (default)
saham analyze risk BBRI --profile conservative
saham analyze risk TLKM --all                     # Compare all profiles

# Custom rules
saham analyze risk BBCA --rules-file config/my_rules.yaml

# With AI explanation
saham analyze risk BBCA --explain
saham analyze risk BBCA --explain --provider deepseek
saham analyze risk BBCA --explain --provider ollama --model llama3

# With sentiment
saham analyze risk BBCA --with-sentiment

# Risk trend over time
saham analyze risk BBCA --trend 20

# JSON output
saham analyze risk BBCA --format json
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--profile` | `-p` | balanced | Risk profile |
| `--all` | `-a` | false | Show all profiles |
| `--rules-file` | `-r` | | Custom YAML rules (overrides --profile) |
| `--explain` | `-e` | false | Generate AI explanation |
| `--provider` | | deepseek | AI provider |
| `--model` | `-m` | | Model name (for Ollama/DeepSeek) |
| `--with-sentiment` | `-s` | false | Include news sentiment |
| `--news-provider` | | composite | News source: composite, google, kontan, cnbc, mock |
| `--trend` | | 0 | Show risk trend over last N days (0=off) |
| `--format` | | table | Output format: `table` or `json` |
| `--no-ai` | | false | Disable AI, use offline keyword classification |

**Risk Profiles:**

| Profile | Description |
|---------|-------------|
| `conservative` | Strict thresholds, requires indicators to agree |
| `balanced` | Standard thresholds, majority rules |
| `aggressive` | Wide thresholds, single indicator can signal |

**Risk Levels:** `HIGH_RISK`, `MODERATE`, `LOW_RISK`

---

### `saham analyze compare` - Side-by-Side Risk Comparison

Compare risk across multiple tickers in a single table.

```bash
saham analyze compare BBCA BBRI BMRI
saham analyze compare BBCA TLKM --profile conservative
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--profile` | `-p` | balanced | Risk profile |
| `--sma` | | 20 | SMA period |
| `--rsi` | | 14 | RSI period |
| `--days` | `-d` | 365 | Days of history |

---

### `saham analyze sentiment` - News Sentiment Analysis

Fetch and analyze news sentiment for a stock.

```bash
saham analyze sentiment BBCA                      # Keyword classification (default)
saham analyze sentiment BBRI --days 7             # More days
saham analyze sentiment TLKM --ai-classify        # AI classification
saham analyze sentiment ASII --ai-classify --provider deepseek
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--days` | `-d` | 3 | Days of news (1-30) |
| `--max` | | 20 | Max headlines (1-50) |
| `--ai-classify` | | false | Use AI for classification |
| `--provider` | | | AI provider for classification |
| `--model` | `-m` | | Model name |
| `--news-provider` | | composite | News source: composite, google, kontan, cnbc, mock |
| `--no-ai` | | false | Use offline keyword classification |

**Sentiment Levels:** `POSITIVE`, `NEUTRAL`, `NEGATIVE`

### `saham analyze audit` - Sentiment Accuracy Audit

Audit past sentiment predictions against actual price moves after 1, 3, and 5 trading days.

```bash
saham analyze audit
```

---

### `saham strategy backtest` - Strategy Backtesting

Run a deterministic backtest simulation on historical data using a strategy package or rules file.

```bash
# Using strategy packages (recommended)
saham strategy backtest BBCA --strategy momentum
saham strategy backtest BBRI -S momentum --start 2024-01-01
saham strategy backtest TLKM -S ./strategies/my_strat/strategy.yaml --verbose

# Using rules file (backward compatible)
saham strategy backtest BBCA --rules-file config/custom_rules.yaml.example
saham strategy backtest BBRI -r rules.yaml --capital 50000000 --verbose

# JSON output
saham strategy backtest BBCA -S momentum --format json
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--strategy` | `-S` | | Strategy name or path (recommended) |
| `--rules-file` | `-r` | | Path to YAML rules file (alias for --strategy) |
| `--start` | `-s` | | Start date (YYYY-MM-DD) |
| `--end` | `-e` | | End date (YYYY-MM-DD) |
| `--capital` | `-c` | 100000000 | Initial capital in IDR |
| `--verbose` | `-v` | false | Show detailed trade-by-trade output |
| `--format` | | table | Output format: `table` or `json` |
| `--db` | | ./data.db | Custom database path |

**Strategy Resolution:** When using `--strategy`, names are searched in:
1. `./NAME/strategy.yaml` (current directory)
2. `./strategies/NAME/strategy.yaml` (local strategies)
3. `~/.ai-saham/strategies/NAME/strategy.yaml` (user strategies)

**Metrics Reported:**
- Total Return (%)
- Max Drawdown (%)
- Trade Count
- Win Rate (%)
- Profit Factor
- Winning/Losing Trades
- Average Win/Loss

**Note:** Requires cached data. Run `saham fetch market TICKER --days 365` first.

---

### `saham strategy` - Strategy Management

Manage strategy packages - portable, versionable strategy definitions.

#### `saham strategy init` - Create New Strategy

```bash
saham strategy init momentum                    # Create in ./strategies/momentum/
saham strategy init my_strat --dir ~/strategies # Custom location
saham strategy init test --force                # Overwrite existing
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--dir` | `-d` | ./strategies/NAME | Directory to create strategy |
| `--force` | `-f` | false | Overwrite existing strategy |

#### `saham strategy validate` - Validate Strategy

```bash
saham strategy validate momentum                        # By name
saham strategy validate ./strategies/momentum/strategy.yaml  # By path
saham strategy validate momentum --strict               # Warnings as errors
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--strict` | `-s` | false | Treat warnings as errors |

#### `saham strategy create` - Create from Natural Language

```bash
saham strategy create "RSI oversold strategy" --name my_rsi
saham strategy create "EMA crossover with 9 and 21" --name ema_cross --provider claude
saham strategy create "momentum strategy" --provider ollama --no-save
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--name` | `-n` | auto-generated | Strategy name |
| `--provider` | `-p` | mock | AI provider (deepseek/claude/openai/gemini/ollama/mock) |
| `--model` | `-m` | | Model name (for Ollama) |
| `--dir` | `-d` | ./strategies/NAME | Directory to save strategy |
| `--save/--no-save` | | save | Save to file or preview only |

#### `saham strategy list` - List Available Strategies

```bash
saham strategy list                  # List valid strategies
saham strategy list --verbose        # Show detailed info
saham strategy list --all            # Include invalid strategies
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--verbose` | `-v` | false | Show detailed information |
| `--all` | `-a` | false | Include invalid strategies |

---

### `saham fetch broker` / `saham view broker` - Broker & Foreign Flow Data

Track foreign investor activity on IDX stocks.

```bash
# Fetch foreign flow (IDX - no auth needed)
saham fetch broker BBCA --days 30

# Or use Stockbit for broker-level detail
saham fetch stockbit login
saham fetch broker BBCA --provider stockbit-session

# View foreign flow summary
saham view broker flow BBCA --days 20

# Check top brokers (requires Stockbit data)
saham view broker top BBCA

# Import from CSV (legacy path during CLI migration)
saham fetch broker-import data.csv --preview

# Check provider status
saham view broker status
```

---

### `saham fetch market` - Batch Data Update

Fetch fresh candles + broker flow data for an entire universe in one command.

```bash
saham fetch market --universe lq45              # All LQ45 stocks
saham fetch market --universe cached            # Refresh already-cached tickers
saham fetch market BBCA BBRI BMRI               # Explicit tickers
saham fetch market --universe lq45 --days 30    # Shorter history
saham fetch market --universe lq45 --broker-only
saham fetch market --universe lq45 --refresh    # Force refresh all
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--universe` | `-u` | | Named universe: lq45, idx80, idxcomp100, cached |
| `--days` | `-d` | 90 | Days of history to fetch |
| `--candles-only` | | false | Skip broker flow fetch |
| `--broker-only` | | false | Skip candles fetch |
| `--provider` | | yahoo | Candles provider: yahoo or idx |
| `--refresh` | `-r` | false | Force refresh even if cached |

---

### `saham fetch universe` - Universe Management

Manage stock universe ticker lists.

```bash
saham fetch universe list                      # List configured universes
saham fetch universe update --universe lq45    # Instructions to update universe
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--config` | | config/universes.yaml | Path to universes.yaml |

**Configured universes:** `lq45`, `idx80`, `idxcomp100`, `cached`

---

### `saham screen accum` - Foreign Accumulation Screener

Screen stocks for institutional foreign accumulation patterns.

```bash
# Single window
saham screen accum --universe lq45
saham screen accum --universe lq45 --window 30
saham screen accum BBCA BBRI BMRI --window 7

# Multi-window (7, 30, 90 broker sessions side-by-side)
saham screen accum --universe lq45 --multi
saham screen accum --universe lq45 --multi --sort-by 30s

# Filters
saham screen accum --universe lq45 --min-score 50 --top 10
saham screen accum --universe lq45 --vwap-only
saham screen accum --universe lq45 --squeeze-only
saham screen accum --universe lq45 --granular
saham screen accum --universe lq45 --breakdown

# Column reference guide
saham screen accum --guide

# JSON output
saham screen accum --universe lq45 --format json
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--universe` | `-u` | | Universe: lq45, idx80, idxcomp100, cached |
| `--window` | `-w` | 7 | Analysis window in broker sessions (7, 30, 90) |
| `--min-streak` | | 0 | Minimum consecutive buy days |
| `--min-score` | | 0.0 | Minimum composite score (0-120) |
| `--vwap-only` | | false | Only stocks where foreigners are underwater |
| `--squeeze-only` | | false | Only stocks in Bollinger Band squeeze |
| `--top` | | 20 | Show top N results |
| `--granular` | | false | Show per-broker detail (Stockbit data) |
| `--breakdown` | | false | Show per-component score breakdown |
| `--multi` | | false | Show scores across multiple windows |
| `--windows` | | 7,30,90 | Comma-separated broker-session windows for --multi |
| `--sort-by` | | avg | Sort by: avg, max, 7s, 30s, 90s. Legacy 7d/30d/90d labels are also accepted. |
| `--format` | | table | Output format: table or json |
| `--guide` | | false | Print column reference guide |
| `--explain` | | false | Print column guide after results |

**Score components (0-120 total):** consistency (40) + streak (30) + VWAP discount (20) + RSI headroom (10) + flow % (10) + BB squeeze (10) + institutional flag (5)

#### `saham analyze accum-audit` - Historical Audit

Replay accumulation signals historically and measure forward returns.

```bash
saham analyze accum-audit --universe idx80 --preset foreign-bounce
saham analyze accum-audit --universe idx80 --window 7 --min-score 70
saham analyze accum-audit --universe lq45 --simulate-exits
```

#### `saham trade log swing` - Log to Journal

```bash
saham trade log swing --ticker BBRI --window 7 --from-analysis --with-regime
```

---

### `saham screen pre-open` - Pre-Open Intraday Screener

Pre-market screening and opening-auction confirmation workflow.

```bash
# Step 1: Run pre-open screen (browser-based or manual data)
saham screen pre-open --movers-json '[{"ticker":"BBCA","iev":150000}]' --fast

# With order book data
saham screen pre-open \
  --movers-json '[{"ticker":"BBCA","iev":150000}]' \
  --order-books-json '{"BBCA":{"price":8900,"volume":50000}}'

# Step 2: Confirm after opening auction (auto via Stockbit session)
saham trade confirm

# Or override prices manually
saham trade confirm --opening-json '{"BBCA":9050,"BMRI":5875}'

# Step 3: Log to journal
saham trade log intraday

# Step 4: Review performance
saham trade review intraday --horizon 5

# Record actual outcome
saham trade outcome BBCA --entry 9000 --exit 9500 --result target
```

| Command | Purpose |
|---------|---------|
| `saham screen pre-open` | Screen movers before market open |
| `saham trade confirm` | Confirm after opening price known |
| `saham trade log intraday` | Append to paper trade journal |
| `saham trade review intraday` | Review journal hit rate |
| `saham trade outcome` | Record actual trade outcome |

---

### `saham learn` - Opening Session Learning Loop

Automated pre-open prediction → intraday tracking → accuracy grading → AI tuning loop.
Designed for the opening auction window (08:45–09:30 WIB).

```bash
# Step 1: Capture NCP-locked predictions at 08:57
saham learn snapshot

# Step 2: Track orderbook depth + foreign net every 5 minutes 09:00-09:30
saham learn track

# With broker attribution (requires Stockbit login)
saham learn track --broker-confirm

# Step 3: Grade accuracy after track completes
saham learn grade

# Step 4: Generate AI tuning prompt
saham learn prompt

# Step 5: Tune thresholds via AI recommendations
saham learn tune
```

| Command | Time | Purpose |
|---------|------|---------|
| `saham learn snapshot` | 08:57 | Pre-open screen → save predictions |
| `saham learn track` | 09:00–09:30 | 5-min orderbook + optional broker attribution (`--broker-confirm`) |
| `saham learn grade` | 09:30+ | Compute accuracy: entry range hit, gap band, stop distance, institutional absorption |
| `saham learn prompt` | anytime | Generate AI prompt from session data |
| `saham learn tune` | anytime | LLM-driven config recommendations |

All data stored in `data/opening/YYYYMMDD/`. The learning loop runs daily and
improves threshold calibration over time. Use `--broker-confirm` on `track` to
embed real-time institutional absorption ratios from Stockbit (requires login).

---

### `saham analyze swing` - Swing Trade Workflow

Unified composite swing trade analysis combining accumulation, risk, sizing, backtest, sentiment, and market regime.

```bash
# Full analysis
saham analyze swing BBRI
saham analyze swing BBRI --capital 10000000
saham analyze swing BBRI --preset foreign-bounce --capital 10000000
saham analyze swing BBRI --capital 10000000 --risk-pct 1
saham analyze swing BBRI --profile conservative --no-sentiment
saham analyze swing BBRI --no-refresh --no-backtest --no-sentiment
saham analyze swing BBRI --force-refresh
saham analyze swing BBRI --with-regime
saham analyze swing BBRI --format json
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--profile` | `-p` | balanced | Risk profile |
| `--strategy` | `-S` | foreign-accumulation | Backtest strategy name |
| `--preset` | | | Swing preset: foreign-bounce |
| `--window` | `-w` | 7 | Accumulation window in broker sessions |
| `--flow-window` | | 30 | Broker-flow detail window in broker sessions |
| `--capital` | `-c` | | Capital in IDR (enables sizing) |
| `--risk-pct` | | 1.0 | % of capital at risk per trade |
| `--entry` | | | Entry price override |
| `--atr-mult` | | 1.5 | ATR multiplier for stop |
| `--rr` | | 2.0 | Reward:risk ratio |
| `--no-sentiment` | | false | Skip news sentiment |
| `--sentiment-verbose` | | false | Show optional sentiment provider errors/noise |
| `--no-backtest` | | false | Skip historical backtest |
| `--no-refresh` | | false | Disable automatic single-ticker candle/broker refresh |
| `--force-refresh` | | false | Force provider refresh even when cached data is fresh |
| `--with-regime` | | false | Add market regime context |
| `--format` | | table | Output format: table or json |

#### `saham trade backtest-swing` - Portfolio Walk-Forward Backtest

```bash
saham trade backtest-swing --universe idx80 --preset foreign-bounce
saham trade backtest-swing --universe lq45 --capital 50000000 --max-positions 3
saham trade backtest-swing --universe idx80 --with-regime --allow-regimes BULLISH,SIDEWAYS
saham trade backtest-swing --universe idx80 --cost-bps 0  # gross/no-cost comparison
```

Default backtests include `--cost-bps 20` one-way transaction cost. Override explicitly
when testing a different broker fee assumption.

#### `saham analyze swing-compare` - Compare Regime Variants

```bash
saham analyze swing-compare --universe idx80
saham analyze swing-compare --universe lq45 --variants baseline,sideways_only
```

#### `saham trade size` - ATR Position Sizing

```bash
saham trade size BBRI --capital 10000000
saham trade size BBRI --capital 10000000 --risk-pct 2 --entry 4825
```

#### `saham screen accum` - Accumulation Screener

Alias for the accumulation screener.

#### `saham analyze accum-audit` - Accumulation Audit

Alias for the accumulation audit.

#### `saham trade log swing` / `saham trade review swing`

Aliases for accumulation journal commands.

---

### `saham analyze regime` - Market Regime

Show deterministic IHSG market regime context for swing trading.

```bash
saham analyze regime
saham analyze regime --universe idx80
saham analyze regime --benchmark ^JKSE
saham analyze regime --as-of 2026-06-01
saham analyze regime --format json
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--universe` | `-u` | idx80 | Universe for breadth context |
| `--benchmark` | | ^JKSE | Benchmark ticker |
| `--as-of` | | today | Regime date (YYYY-MM-DD) |
| `--format` | | table | Output format: table or json |

**Regime labels:** `BULLISH`, `SIDEWAYS`, `WEAK`, `RISK_OFF`

---

### `saham analyze chart` - Terminal ASCII Charts

Plot charts in-terminal (requires `pip install plotext`).

```bash
saham analyze chart price BBCA                  # Close price with SMA overlay
saham analyze chart price BBCA --sma 20 --ema 9 --days 120
saham analyze chart rsi BBCA                    # RSI with overbought/oversold bands
saham analyze chart rsi BBCA --period 9 --days 120
saham analyze chart volume BBCA                 # Daily volume bars
saham analyze chart volume BBCA --days 30
```

| Option | Default | Description |
|--------|---------|-------------|
| `--days` | 90 (price), 90 (rsi), 60 (volume) | Days of history |
| `--width` | 100 | Chart width (columns) |
| `--height` | 24 (price), 18 (rsi/volume) | Chart height (rows) |
| `--sma` (price only) | 20 | SMA period overlay |
| `--ema` (price only) | off | EMA period overlay |
| `--period` (rsi only) | 14 | RSI period |

---

### `saham fetch status` - Data Health Check

Check provider health and database freshness in one command:

```bash
saham fetch status
```

Reports latest data dates, row counts across all tables, IDX/Yahoo/Stockbit
provider status, and data staleness warnings.

---

### `saham fetch stockbit` - Stockbit Session Management

Manage Stockbit browser sessions for automated data fetching.

```bash
saham fetch stockbit login                    # Open browser for manual login
saham fetch stockbit login --timeout 180      # Longer timeout for 2FA
saham fetch stockbit status                   # Check session health
saham fetch stockbit spy                      # Capture API traffic
saham fetch stockbit spy --target orderbook --ticker BBRI
saham fetch stockbit test                     # Smoke-test the adapter
saham fetch stockbit fetch-top5 --top 5       # Top IEV movers + orderbooks
saham fetch stockbit browse                   # Interactive browser session
```

| Command | Purpose |
|---------|---------|
| `saham fetch stockbit login` | Save browser session cookies |
| `saham fetch stockbit status` | Check session health |
| `saham fetch stockbit spy` | Capture all API traffic to identify endpoints |
| `saham fetch stockbit test` | Smoke-test live adapter with saved session |
| `saham fetch stockbit fetch-top5` | Top IEV movers + live orderbook snapshots |
| `saham fetch stockbit browse` | Open headed browser with saved session |

---

### `saham strategy skill` - Skill Documentation

Auto-generate SKILL.md files for strategies, indicators, and formulas.

```bash
saham strategy validate rsi-momentum    # Auto-generates SKILL.md
saham strategy skill generate rsi-momentum       # Explicit generation
saham strategy skill generate atr --type indicator
saham strategy skill generate SMOOTH_RSI --type formula
saham strategy skill check                       # Check for stale docs
saham strategy skill index                       # Rebuild SKILLS_INDEX.md
```

### `saham indicator create` - Create Custom Formula

Create a custom indicator from natural language using AI.

```bash
saham indicator create "smoothed RSI with 14 period" --name SMOOTH_RSI
saham indicator create "MACD line" --name MACD --provider deepseek
saham indicator create "14-day RSI" --no-save
```

### `saham indicator list` - List All Indicators

```bash
saham indicator list
saham indicator list --formulas        # Show formula expressions
```

### `saham indicator show` - Show Formula Details

```bash
saham indicator show SMOOTH_RSI
```

### `saham indicator delete` - Delete Custom Formula

```bash
saham indicator delete SMOOTH_RSI
saham indicator delete MACD --force     # Skip confirmation
```

---

### `saham version` - Version Info

```bash
saham version
```

---

## AI Features

### AI Providers

For `--explain`, `--ai-classify`, formula translation, and strategy generation:

| Provider | Environment Variable | Default Model |
|----------|---------------------|---------------|
| `deepseek` | `DEEPSEEK_API_KEY` | deepseek-chat |
| `claude` | `ANTHROPIC_API_KEY` | claude-3-haiku |
| `openai` | `OPENAI_API_KEY` | gpt-3.5-turbo |
| `gemini` | `GOOGLE_API_KEY` | gemini-pro |
| `ollama` | (local, no key) | qwen2.5-coder:1.5b |
| `mock` | (none) | (for testing) |

**Default provider is `deepseek`.** No environment variable needed for Ollama or mock.

```bash
# Set API key
export DEEPSEEK_API_KEY=sk-...

# Or use local Ollama
ollama serve  # In another terminal
saham analyze risk BBCA --explain --provider ollama
```

### AI Strategy Creator

Create complete strategy YAML from natural language descriptions:

```bash
saham strategy create "buy when RSI below 30, sell when RSI above 70" --name rsi_strategy
saham strategy create "EMA crossover with 9 and 21 periods" --name ema_cross --provider claude
saham strategy create "momentum strategy" --no-save
```

### AI Formula Translator

Translate natural language descriptions into formula expressions:

```bash
saham indicator create "smoothed RSI with 14-period and 10-day smoothing" --name smooth_rsi
saham indicator create "MACD line using 12 and 26 period EMAs" --name macd --provider deepseek
```

---

## Plugin System

Extend the indicator library with custom plugins.

### Using Plugins

Plugins are auto-discovered from `plugins/` directory or `plugins/indicators/`:

```bash
plugins/
├── atr_plugin.py          # ATR indicator (included)
└── indicators/            # Additional plugin directory
```

### Creating a Plugin

```python
# plugins/my_indicator.py
from src.application.services.indicator_registry import IndicatorPlugin

class MyIndicatorPlugin(IndicatorPlugin):
    @property
    def name(self) -> str:
        return "MY_IND"

    @property
    def required_periods(self) -> int:
        return 14

    def compute(self, candles, period: int):
        # Return list of (date, Decimal) tuples
        ...
```

See `plugins/atr_plugin.py` for a complete example.

---

## Custom Rules DSL

Define custom rules in YAML format. See `config/custom_rules.yaml.example`.

### Basic Example

```yaml
version: 1
name: "my_rules"
default_outcome: MODERATE

rules:
  - name: oversold_rsi
    priority: 10
    when:
      indicator: RSI        # Uses built-in RSI(14)
      operator: "<"
      value: 30
    outcome: LOW_RISK
    rationale: "RSI below 30 - oversold"
```

### Parameterized Indicators

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
    rationale: "EMA(9) > EMA(21) - bullish momentum"
```

**Built-in indicators:** `RSI` (14), `SMA` (20), `EMA` (20)
**Price fields:** `OPEN`, `HIGH`, `LOW`, `CLOSE`, `VOLUME`
**Plugin indicators:** `ATR` and custom plugins
**Supported types:** `RSI`, `SMA`, `EMA`, plus any registered plugins
**Supported operators:** `<`, `<=`, `>`, `>=`, `==`, `!=`

### Compound Conditions & Advanced Syntax

```yaml
rules:
  - name: oversold_uptrend
    priority: 10
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
    outcome: LOW_RISK
    rationale: "RSI oversold while price above SMA50"
```

### Formula-Based Indicators

```yaml
version: 1
name: "formula_strategy"
default_outcome: MODERATE

indicators:
  smooth_rsi:
    formula: "SMA(RSI(14), 10)"
  macd_line:
    formula: "EMA(CLOSE, 12) - EMA(CLOSE, 26)"
  sma_distance:
    formula: "(CLOSE - SMA(CLOSE, 20)) / SMA(CLOSE, 20) * 100"

rules:
  - name: smooth_rsi_oversold
    when:
      indicator: smooth_rsi
      operator: "<"
      value: 30
    outcome: LOW_RISK
```

**Supported formula syntax:**
- **Series:** `OPEN`, `HIGH`, `LOW`, `CLOSE`, `VOLUME`
- **Functions:** `SMA(series, period)`, `EMA(series, period)`, `RSI(period)`, `ATR(period)`
- **Operators:** `+`, `-`, `*`, `/`
- **Parentheses:** `( )` for grouping

---

## Strategy Packages

Strategies are first-class, versionable, portable artifacts.

### Package Structure

```
strategies/
└── momentum/
    ├── strategy.yaml       # Required: strategy rules
    ├── strategy.skill.yaml # Optional: skill annotation sidecar
    ├── SKILL.md            # Auto-generated documentation
    ├── README.md           # Optional: documentation
    ├── tests/              # Optional: test cases
    └── examples/           # Optional: example usage
```

### Creating a Strategy

```bash
saham strategy init momentum
vim strategies/momentum/strategy.yaml
saham strategy validate momentum
saham strategy backtest BBCA --strategy momentum
```

### Strategy Resolution

1. **Explicit path** - If contains `/` or ends with `.yaml`
2. **Local directory** - `./momentum/strategy.yaml`
3. **Local strategies** - `./strategies/momentum/strategy.yaml`
4. **User strategies** - `~/.ai-saham/strategies/momentum/strategy.yaml`

---

## Architecture

```
src/
├── domain/                          # Pure business logic
│   ├── entities/                    # Stock, Candle, BacktestTrade
│   ├── indicators/                  # SMA, EMA, RSI calculations
│   ├── ports/                       # Interfaces
│   │   ├── market_data_provider.py
│   │   ├── market_data_repository.py
│   │   ├── ai_explainer.py
│   │   ├── news_provider.py
│   │   ├── headline_classifier.py
│   │   ├── sentiment_repository.py
│   │   ├── broker_data_provider.py
│   │   ├── browser_data_provider.py
│   │   └── csv_broker_parser.py
│   ├── rules/                       # Risk assessment rules
│   │   ├── rule_engine.py
│   │   ├── conservative.py
│   │   ├── balanced.py
│   │   └── aggressive.py
│   ├── value_objects/               # Immutable domain objects
│   │   ├── indicator_snapshot.py
│   │   ├── risk_assessment.py
│   │   ├── backtest_result.py
│   │   ├── trade_action.py
│   │   ├── skill_annotation.py
│   │   ├── sentiment.py
│   │   ├── broker_summary.py
│   │   ├── screener_result.py
│   │   └── intraday_confirmation.py
│   └── services/
│       └── backtest_engine.py
│
├── application/                      # Use cases & application services
│   ├── use_case/
│   │   ├── fetch_market_data.py
│   │   ├── refresh_market_data.py
│   │   ├── compute_sma.py
│   │   ├── compute_ema.py
│   │   ├── compute_rsi.py
│   │   ├── aggregate_indicators.py
│   │   ├── assess_risk.py
│   │   ├── explain_risk.py
│   │   ├── fetch_sentiment.py
│   │   ├── audit_sentiment.py
│   │   ├── backtest.py
│   │   ├── fetch_broker_data.py
│   │   ├── import_broker_data.py
│   │   ├── pre_open_screen.py
│   │   ├── confirm_intraday_open.py
│   │   ├── accumulation_screen.py
│   │   ├── accumulation_audit.py
│   │   ├── market_regime.py
│   │   ├── swing_backtest.py
│   │   ├── create_indicator_from_intent.py
│   │   └── create_strategy_from_intent.py
│   ├── formula/                      # Formula DSL engine
│   │   ├── tokenizer.py
│   │   ├── parser.py
│   │   ├── ast_nodes.py
│   │   ├── validator.py
│   │   └── evaluator.py
│   ├── services/
│   │   ├── indicator_registry.py
│   │   ├── strategy_loader.py
│   │   ├── skill_generator.py
│   │   ├── universe_loader.py
│   │   ├── position_sizer.py
│   │   ├── accumulation_journal.py
│   │   ├── ai_research.py
│   │   └── group_mapping.py
│   ├── ports/
│   │   ├── formula_translator.py
│   │   ├── strategy_translator.py
│   │   └── skill_writer.py
│   ├── rules/
│   │   ├── schema.py
│   │   └── interpreter.py
│   └── dto/
│
├── infrastructure/                   # External implementations
│   ├── data_providers/
│   │   ├── yahoo.py                  # Yahoo Finance
│   │   ├── idx_market.py             # IDX market data
│   │   ├── idx.py                    # IDX broker data
│   │   └── stockbit.py               # Stockbit broker data
│   ├── browser/
│   │   ├── playwright_stockbit.py    # Playwright-based automation
│   │   └── stockbit_browser.py       # Manual browser provider
│   ├── persistence/
│   │   ├── sqlite_market_repository.py
│   │   ├── sqlite_broker_repository.py
│   │   ├── formula_storage.py
│   │   ├── sentiment_repository.py
│   │   ├── intraday_confirmation_csv.py
│   │   └── accumulation_journal_csv_writer.py
│   ├── ai/
│   │   ├── factory.py
│   │   ├── deepseek_explainer.py
│   │   ├── claude_explainer.py
│   │   ├── openai_explainer.py
│   │   ├── gemini_explainer.py
│   │   ├── ollama_explainer.py
│   │   ├── formula_translator.py
│   │   ├── formula_translator_prompt.py
│   │   ├── strategy_translator.py
│   │   ├── strategy_translator_prompt.py
│   │   └── mock_explainer.py
│   ├── sentiment/
│   │   ├── factory.py
│   │   ├── google_news_provider.py
│   │   ├── keyword_classifier.py
│   │   └── ai_classifier.py
│   ├── plugins/
│   │   └── indicator_loader.py       # Plugin discovery
│   ├── skill/
│   │   ├── annotation_reader.py
│   │   ├── markdown_writer.py
│   │   ├── rules_hasher.py
│   │   └── index_writer.py
│   ├── csv/
│   │   └── adapter.py                # CSV broker data import
│   └── config/
│       └── yaml_loader.py
│
├── adapters/                         # User interfaces
│   ├── cli/
│   │   ├── main.py                   # Main CLI entry point (group definitions)
│   │   ├── fetch_commands.py         # Fetch group router
│   │   ├── fetch_market_commands.py  # (impl) Market data fetch
│   │   ├── fetch_iev_commands.py     # (impl) IEV snapshot capture
│   │   ├── view_commands.py          # View group (read-only broker views)
│   │   ├── learn_commands.py         # Learn group router
│   │   ├── learn_opening_commands.py # (impl) Opening learning loop
│   │   ├── status_commands.py        # Data health and freshness
│   │   ├── today_commands.py         # Daily briefing
│   │   ├── analyze_commands.py       # Analyze group (risk, sentiment, regime, chart)
│   │   ├── trade_commands.py         # Trade workspace router
│   │   ├── trade_intraday_commands.py# (impl) Intraday trade CLI
│   │   ├── indicator_commands.py     # Indicator group (compute, snapshot, create)
│   │   ├── strategy_commands.py      # Strategy group (init, validate, backtest)
│   │   ├── skill_commands.py         # Strategy skill implementation
│   │   ├── screen_lifecycle_commands.py   # (impl) Screen lifecycle management
│   │   ├── screen_pre_open_commands.py    # (impl) Pre-open screen CLI
│   │   ├── accumulation_commands.py  # (impl) Accumulation screen logic
│   │   ├── broker_commands.py        # (impl) Broker data logic
│   │   ├── chart_commands.py         # (impl) Chart rendering
│   │   ├── intraday_workflow_commands.py  # (impl) Shared intraday logic
│   │   ├── sentiment_commands.py     # (impl) Sentiment logic
│   │   ├── stockbit_commands.py      # (impl) Stockbit session management
│   │   ├── swing_commands.py         # (impl) Swing/unified analysis
│   │   └── update_commands.py        # (impl) Batch update logic
│   ├── bot/                          # Telegram, WhatsApp (stubs)
│   └── web/                          # REST API (stub)
│
└── plugins/                          # User plugins directory
    ├── atr_plugin.py                 # ATR indicator (example)
    └── indicators/                   # Additional plugin dir
```

**Key Principles:**
- Domain logic is pure and framework-agnostic
- External systems never leak into the domain
- AI is always optional and swappable (DeepSeek default)
- Plugins extend functionality without modifying core

---

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `DEEPSEEK_API_KEY` | DeepSeek API key (default provider) |
| `ANTHROPIC_API_KEY` | Claude API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `GOOGLE_API_KEY` | Google/Gemini API key |
| `AI_PROVIDER` | Default AI provider (default: deepseek) |
| `AI_RATE_LIMIT` | Calls per minute (default: 10) |
| `OLLAMA_HOST` | Ollama server URL |
| `OLLAMA_MODEL` | Default Ollama model |

### Config Files

| File | Description |
|------|-------------|
| `config/default.yaml` | Base configuration |
| `config/conservative.yaml` | Conservative profile |
| `config/balanced.yaml` | Balanced profile |
| `config/aggressive.yaml` | Aggressive profile |
| `config/custom_rules.yaml.example` | Custom rules template |
| `config/formulas.yaml` | Persisted custom formulas |
| `config/universes.yaml` | Ticker universe definitions |
| `config/idx_groups.yaml` | IDX sector/industry group mappings |
| `config/csv_mappings/` | CSV import column mapping definitions |

---

## Development

```bash
# Activate virtual environment
source .venv/bin/activate

# Run tests
make test

# Run tests with coverage
make test-cov

# Lint code
make lint

# Format code
make format

# Clean build artifacts
make clean
```

**Project Stats:** ~250 source files (~53k LOC), 98 test files (~26k LOC)

---

## Data Storage

- **Location:** `./data.db` (SQLite, configurable via `--db`)
- **Content:** Cached OHLCV candles, broker summaries, sentiment logs, journals
- **Refresh:** Use `--refresh` flag or `saham fetch market --universe <name>` to batch update

---

## Limitations

- **IDX market focus** - Designed for Indonesia Stock Exchange
- **Yahoo Finance / IDX source** - Data may be delayed; unofficial sources
- **Internet required** for first fetch and sentiment (offline for cached analysis)
- **Intraday data via yfinance 5-min candles** — opening session tracking uses
  Yahoo Finance intraday data, not real-time IDX feeds

---

## What This Project Is NOT

- An automated trading or execution system
- An AI-only or black-box analyzer
- A real-time, high-frequency trading platform
- Financial advice provider

**DISCLAIMER:** This tool provides analysis only, not trading advice.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
