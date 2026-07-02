# AI Saham - Stock Analysis CLI

[![CI](https://github.com/satriyop/ai-saham/actions/workflows/ci.yml/badge.svg)](https://github.com/satriyop/ai-saham/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A **local-first, production-grade CLI application** for stock analysis focused on the Indonesia Stock Exchange (IDX).

## Features

- **Technical Indicators** - SMA, EMA, RSI, ATR with professional-grade calculations
- **Formula DSL** - Compose indicators with expressions like `SMA(RSI(14), 10)`
- **Plugin System** - Extend with custom indicators (ATR included as example)
- **Risk Assessment** - Configured risk gates with OPEN/BLOCKED status + trend mode
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
- **Market Context Engine** - Deterministic cross-market context using RISK_ON/NEUTRAL/RISK_OFF/VOLATILE regimes
- **Ticker Notation Context** - Stockbit special notation/status badges cached locally for swing and pre-open views
- **Terminal Charts** - ASCII price/RSI/volume charts in-terminal
- **Batch Update** - Single command to refresh candles + broker flow for entire universes
- **Broker & Foreign Flow** - Track foreign investor activity from IDX (public, no auth) or Stockbit
- **Broker History & Top Foreign** - View broker-level flow history and top foreign traders across tickers
- **Candle Provenance** - Each candle records its source provider (yahoo/idx) with idempotent deduplication
- **Enrichment Cache** - Analyst consensus, insider trades, fundamentals, corporate actions, forward estimates, company profiles, and earnings history cached with TTL-based refresh
- **Data Quality Audit** - `saham fetch audit` detects degraded broker summaries, candle provenance gaps, enrichment coverage gaps, and stale core data (using `pending-eod`/`ready`/`bf+` status labels; read-only)
- **Accumulation Audit** - Replay accumulation signals historically and measure forward returns
- **Ticker Dashboard** - Read-only, cached-data dashboard via `saham view BBCA` showing notation, valuation, consensus, ownership, bandar signal, company profile, recent candles, corporate actions, insider activity, seasonality, IEV, and sentiment
- **Universe Overview** - Market-wide view via `saham view universe lq45` showing price, foreign flow, and sector context per ticker
- **Signal Assessment** - `saham screen accum` scores each ticker 0–100 via `SignalEngine` (bandar, foreign flow, insider activity, seasonality, analyst consensus, forward valuation) with STRONG/MODERATE/WEAK rating
- **Earnings History** - Quarterly earnings beat/miss streak from Stockbit `/earnings` endpoint, surfaced in swing analysis and enrichment cache
- **Valuation Metrics** - P/E and EPS TTM from Stockbit, cached alongside fundamentals
- **Watchlist Persistence** - `saham screen accum --save NAME` persists screener results; `saham screen watchlist` / `saham screen compare` to review and diff against fresh runs
- **Cross-Broker Distribution** - `saham view broker distribution TICKER` shows counterparty flow breakdown across brokers
- **Risk Engine** - Application-layer `RiskEngine` service wrapping rule-based risk gates (fundamental, liquidity, free float, bandar) with self-contained enrichment fetch; used by `analyze risk` and swing/accumulation workflows
- **Data Status Labels** - Staleness replaced with contextual labels (`pending-eod` during market hours, `ready`, `bf+` for backfill, `✓` for aggregation up-to-date)
- **Regime-Aware Backtesting** - Swing backtests can group/filter entries by MarketContextEngine regime and use regime-specific setup exits
- **IDX Floor Price Filter** - Rp 50 minimum price filter applied during IDX data ingestion
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
| **`saham today`** | Daily briefing | `--universe`, `--top`, `--date` |
| **`saham version`** | Version info | (no subcommands) |
| **`saham fetch`** | Data Ingestion | `market`, `broker`, `broker-import`, `broker-history`, `broker-top-foreign`, `iev`, `status`, `audit`, `stockbit login/status/spy/test/browse/fetch-top5`, `universe list/update/inspect/create` |
| **`saham screen`** | Candidate Discovery | `pre-open`, `accum`, `watchlist`, `compare` |
| **`saham learn`** | Feedback Loop | `snapshot`, `track`, `grade`, `prompt`, `tune` |
| **`saham view`** | Read-only Browsing | `broker status/flow/top/history/top-foreign/distribution/mappings`, `market-context`, `ticker TICKER` (or just `BBCA`), `universe` |
| **`saham indicator`**| Technical Math | `compute`, `snapshot`, `create`, `list`, `show`, `delete` |
| **`saham analyze`** | Insights & Charts | `risk`, `compare`, `sentiment`, `audit`, `regime`, `chart price/rsi/volume`, `swing`, `accum-audit`, `swing-compare` |
| **`saham strategy`** | Strategy Lifecycle| `init`, `validate`, `list`, `create`, `backtest`, `skill generate/check/index` |
| **`saham trade`** | Paper Trade Workspace | `confirm`, `outcome`, `size`, `backtest-swing`, `tune-swing`, `backtest-intraday`, `log`, `migrate-journal`, `review intraday/swing` |

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

Assess risk using configured deterministic gates with optional AI explanation.

```bash
# Gate-based risk assessment
saham analyze risk BBCA

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
| `--rules-file` | `-r` | | Custom YAML rules |
| `--explain` | `-e` | false | Generate AI explanation |
| `--provider` | | deepseek | AI provider |
| `--model` | `-m` | | Model name (for Ollama/DeepSeek) |
| `--with-sentiment` | `-s` | false | Include news sentiment |
| `--news-provider` | | composite | News source: composite, google, kontan, cnbc, mock |
| `--trend` | | 0 | Show risk trend over last N days (0=off) |
| `--format` | | table | Output format: `table` or `json` |
| `--no-ai` | | false | Disable AI, use offline keyword classification |

**Risk Status:** `OPEN`, `BLOCKED`

**Risk Gates:** fundamental, liquidity, free float, bandar, optional technical gate, optional market-context gate.

---

### `saham analyze compare` - Side-by-Side Risk Comparison

Compare risk across multiple tickers in a single table.

```bash
saham analyze compare BBCA BBRI BMRI
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
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
saham fetch broker BBCA --provider stockbit

# Fetch broker-level flow history (Stockbit, requires auth)
saham fetch broker-history BBCA --days 60

# Universe scan for top foreign-flow stocks (Stockbit)
saham fetch broker-top-foreign

# View foreign flow summary
saham view broker flow BBCA --days 20
saham view broker history BBCA          # Per-broker time series
saham view broker top-foreign           # Top foreign stocks across universe

# Check top brokers (requires Stockbit data)
saham view broker top BBCA

# Cross-broker distribution matrix (Stockbit data)
saham view broker distribution BBCA

# Cross-market regime context (VIX, EIDO, USD/IDR)
saham view market-context

# Import from CSV (legacy path during CLI migration)
saham fetch broker-import data.csv --preview

# Check provider status
saham view broker status

# Ticker dashboard — read-only view of all cached data
saham view BBCA                     # Everything we know about BBCA
saham view ticker BBCA              # Explicit syntax (same as above)

# Universe overview — price, flow, and sector at a glance
saham view universe                 # List all universes with ticker counts
saham view universe lq45            # Market-wide view for LQ45
saham view universe lq45 --sort flow  # Sort by net foreign flow
saham view universe lq45 --top 10    # Top 10 tickers only
saham view universe lq45 --date 2026-06-01  # Show data as of a specific date
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--date` | | today | Context date, YYYY-MM-DD |
| `--universe` | `-u` | (config) | Universe for idx_breadth factor |
| `--verbose` | `-v` | false | Show score bar and full rationale per factor |
| `--format` | | table | Output format: table or json |
| `--db` | | | SQLite database path |

---

### `saham fetch market` - Batch Data Update

Fetch fresh candles + broker flow data for an entire universe in one command. Progress is streamed in real-time with per-ticker status callbacks.

```bash
saham fetch market --universe lq45              # All LQ45 stocks
saham fetch market --universe cached            # Refresh already-cached tickers
saham fetch market BBCA BBRI BMRI               # Explicit tickers
saham fetch market --universe lq45 --days 30    # Shorter history
saham fetch market --universe lq45 --broker-only
saham fetch market --universe lq45 --refresh    # Force refresh all
saham fetch market BBCA --broker-provider stockbit --days 30  # Use Stockbit broker provider
saham fetch market --universe lq45 --no-meta    # Skip metadata fetch
saham fetch market --universe lq45 --no-enrichment  # Skip enrichment fetch
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--universe` | `-u` | | Named universe: lq45, idx80, idxcomp100, cached |
| `--days` | `-d` | 90 | Days of history to fetch |
| `--candles-only` | | false | Skip broker flow fetch |
| `--broker-only` | | false | Skip candles fetch |
| `--provider` | | (from config) | Candles provider: yahoo or idx |
| `--broker-provider` | | auto | Broker provider: idx or stockbit (auto-detected) |
| `--no-meta` | | false | Skip sector/industry metadata fetch |
| `--no-enrichment` | | false | Skip Stockbit enrichment fetch |
| `--refresh` | `-r` | false | Force refresh even if cached |
| `--db` | | | SQLite database path |

---

### `saham fetch universe` - Universe Management

Manage stock universe ticker lists. Requires an active Stockbit session for `update`, `inspect`, and `create`.

```bash
# List configured universes with ticker counts and last-updated dates
saham fetch universe list

# Update from Stockbit Exodus API
saham fetch universe update --universe lq45          # Specific universe
saham fetch universe update                          # All universes
saham fetch universe update --discover               # List available universes without updating

# Explore Stockbit sectors and create custom universes
saham fetch universe inspect                         # List all sectors
saham fetch universe inspect --sector 5              # Subsectors of sector 5
saham fetch universe inspect --sector 5 --subsector 49  # Companies in subsector 49

# Create a custom universe from a sector/subsector
saham fetch universe create food_retail -s 1 -b 10
saham fetch universe create consumer_primer -s 1
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--config` | | config/universes.yaml | Path to universes.yaml |
| `--universe`/`-u` | | all | Universe name for update |
| `--discover` | | false | List available universes from Stockbit |
| `--sector`/`-s` | | required | Sector ID for inspect/create |
| `--subsector`/`-b` | | none | Subsector ID for inspect/create |

**Configured universes:** `lq45`, `idx80`, `idxcomp100`, `cached`, plus any custom universes created via `fetch universe create`

---

### `saham screen accum` - Foreign Accumulation Screener

Screen stocks for institutional foreign accumulation patterns. Results are split into verdict, foreign-flow score, signal, risk, and data coverage panels.

```bash
# Single window
saham screen accum --universe lq45
saham screen accum --universe lq45 --window 30
saham screen accum BBCA BBRI BMRI --window 7

# Multi-window (7, 30, 90 broker sessions side-by-side)
saham screen accum --universe lq45 --multi
saham screen accum --universe lq45 --multi --sort-by 30s

# Filters
saham screen accum --universe lq45 --min-foreign-flow-score 50 --top 10
saham screen accum --universe lq45 --min-signal-score 55 --top 10
saham screen accum --universe lq45 --vwap-only
saham screen accum --universe lq45 --squeeze-only
saham screen accum --universe lq45 --top-broker
saham screen accum --universe lq45 --explain

# Save to watchlist for later comparison
saham screen accum --universe lq45 --save morning-watch

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
| `--min-foreign-flow-score` | | config | Minimum composite foreign-flow score (0-120 soft cap) |
| `--min-signal-score` | | disabled/config | Optional minimum SignalEngine score (0-100) |
| `--min-piotroski` | | | Minimum Piotroski F-score filter |
| `--strategy` | `-S` | | Optional backtest strategy for signal context |
| `--vwap-only` | | false | Only stocks where foreigners are underwater |
| `--squeeze-only` | | false | Only stocks in Bollinger Band squeeze |
| `--top` | | 20 | Show top N results |
| `--top-broker` | | false | Show top broker-code detail and BCI label when available |
| `--multi` | | false | Show scores across multiple windows |
| `--windows` | | 7,30,90 | Comma-separated broker-session windows for --multi |
| `--sort-by` | | avg | Sort by: avg, max, 7s, 30s, 90s. Legacy 7d/30d/90d labels are also accepted. |
| `--format` | | table | Output format: table or json |
| `--save` | | none | Save results to watchlist (e.g. `--save morning-watch`) |
| `--guide` | | false | Print column reference guide and exit |
| `--explain` | | false | Append run context and scoring definitions after results |
| `--db` | | | SQLite database path |

**Foreign Flow Score (0-120 soft cap):** consistency, streak, VWAP discount, RSI headroom, flow %, BB squeeze, and BCI. Thresholds and weights are configured in `config/accumulation_screener.yaml`.

**SignalAssessment score (0-100, via SignalEngine):** bandar intensity, foreign flow quality, insider net buy ratio, seasonality win rate, analyst buy consensus, and forward PE valuation. Weights, classification thresholds, missing-data policy, enrichment lookbacks, input mapping, and factor scoring thresholds are configured in `config/signal_engine.yaml`.

#### `saham screen watchlist` - Saved Snapshots

List all saved watchlists or show tickers in a named list. Watchlists are created via `saham screen accum --save NAME`.

```bash
saham screen watchlist                  # List all saved watchlists
saham screen watchlist morning-watch    # Show tickers in 'morning-watch'
```

#### `saham screen compare` - Diff Against Fresh Run

Compare a saved watchlist against a fresh screener run. Shows: new entries, dropped tickers, and signal strength changes.

```bash
saham screen compare morning-watch                          # Compare using saved universe
saham screen compare morning-watch --universe lq45 --top 30  # Override universe and limit
```

#### `saham analyze accum-audit` - Historical Audit

Replay accumulation signals historically and measure forward returns.

```bash
saham analyze accum-audit --universe idx80 --setup foreign-bounce
saham analyze accum-audit --universe idx80 --setup coiled-spring
saham analyze accum-audit --universe idx80 --setup smart-money-confirmed
saham analyze accum-audit --universe idx80 --setup pullback-continuation
saham analyze accum-audit --universe idx80 --window 7 --min-foreign-flow-score 70
saham analyze accum-audit --universe lq45 --simulate-exits
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--universe` | `-u` | | Universe: lq45, idx80, idxcomp100, cached |
| `--setup` | | | Audit setup: foreign-bounce, coiled-spring, smart-money-confirmed, pullback-continuation |
| `--start` | | 2026-01-01 | Audit start date, YYYY-MM-DD |
| `--end` | | today | Audit end date, YYYY-MM-DD |
| `--window` | `-w` | | Accumulation window in broker sessions |
| `--min-foreign-flow-score` | | | Minimum composite foreign-flow score to audit |
| `--min-net-buy-days` | | | Minimum foreign net-buy days |
| `--min-vwap-disc` | | | Require VWAP discount at least this percent |
| `--trend` | | | Require trend bucket: UP, SIDE, or DOWN |
| `--min-flow-pct` | | | Require average foreign flow percent |
| `--require-rsi` | | false | Exclude signals with missing RSI |
| `--max-rsi` | | | Require RSI at or below this value |
| `--min-rsi` | | | Require RSI at or above this value |
| `--max-bb-width-pctile` | | | Require BB width percentile at or below this value |
| `--broker-quality` | | | Require broker-quality bucket, e.g. smart+ |
| `--simulate-exits` | | | Run TP/SL/max-hold exit grid |
| `--take-profits` | | | Comma-separated take-profit percentages |
| `--stop-losses` | | | Comma-separated stop-loss percentages |
| `--max-holds` | | | Comma-separated max holding days |
| `--horizon` | | 20 | Forward horizon for max up/down metrics |
| `--output` | `-o` | | Write raw audit records to CSV |
| `--top-groups` | | 80 | Number of grouped summary rows to print |
| `--format` | | table | Output format: table or json |
| `--db` | | | SQLite database path |

#### `saham trade log --type swing` - Log to Journal

```bash
saham trade log --type swing --ticker BBRI --window 7 --from-analysis --with-regime
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
saham trade log --type intraday

# Step 4: Review performance
saham trade review intraday

# Record actual outcome
saham trade outcome BBCA --entry 9000 --exit 9500 --result target
```

Pre-open output uses `opening_setup` (`PRIME`, `WATCH`, `SKIP`) for the
opening-session plan. This is not a swing `TradeSetup` verdict. Broker-flow
diagnostics use opening broker-backing fields such as
`opening_broker_backing_score` and `opening_broker_backing_tag`.
Use `--risk-strategy NAME` to add an optional strategy/rules risk-status column.

| Command | Purpose |
|---------|---------|
| `saham screen pre-open` | Screen movers before market open |
| `saham trade confirm` | Confirm after opening price known |
| `saham trade log --type intraday` | Append to paper trade journal |
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

Verdict-first swing analysis composing `SignalEngine + RiskEngine` into the final `TradeSetup`. RiskEngine now reports `OPEN` (no gate fired) or `BLOCKED (gate: Name)` instead of legacy risk levels. MarketContextEngine is optional preview/enrichment via `--with-market-context` while engine thresholds are still being tuned. An optional `--with-technical-gate` enables the SMA/EMA/RSI technical execution gate (off by default). Setup gates, strategy backtest, sentiment, market context, and detailed broker attribution are opt-in evidence.

```bash
saham analyze swing BBRI
saham analyze swing BBRI --capital 10000000
saham analyze swing BBRI --setup foreign-bounce --capital 10000000
saham analyze swing BBRI --setup coiled-spring --capital 10000000
saham analyze swing BBRI --setup smart-money-confirmed --capital 10000000
saham analyze swing BBRI --setup pullback-continuation --capital 10000000
saham analyze swing BBRI --capital 10000000 --risk-pct 1
saham analyze swing BBRI --strategy foreign-accumulation
saham analyze swing BBRI --with-sentiment --with-flow-detail
saham analyze swing BBRI --with-technical-gate
saham analyze swing BBRI --explain
saham analyze swing BBRI --full
saham analyze swing BBRI --no-refresh
saham analyze swing BBRI --force-refresh
saham analyze swing BBRI --with-market-context
saham analyze swing BBRI --format json
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--strategy` | `-S` | none | Optional strategy/backtest evidence name |
| `--setup` | | none | Optional swing setup lens: foreign-bounce, coiled-spring, smart-money-confirmed, pullback-continuation |
| `--window` | `-w` | 7 | Accumulation window in broker sessions |
| `--flow-window` | | 30 | Broker-flow detail window in broker sessions |
| `--capital` | `-c` | | Capital in IDR (enables sizing) |
| `--risk-pct` | | 1.0 | % of capital at risk per trade |
| `--entry` | | | Entry price override |
| `--atr-mult` | | 1.5 | ATR multiplier for stop |
| `--rr` | | 2.0 | Reward:risk ratio |
| `--with-sentiment` | | false | Include news sentiment evidence |
| `--with-flow-detail` | | false | Include broker flow and attribution evidence |
| `--with-signal-detail` | | false | Include SignalEngine factor detail |
| `--with-risk-detail` | | false | Include RiskEngine indicator/gate detail |
| `--with-market-context` | | false | Show MarketContextEngine preview/enrichment without changing final `TradeSetup` |
| `--with-market-detail` | | false | Include full MCE factor detail when market context is enabled |
| `--explain` | | false | Shortcut for signal, risk, and market detail |
| `--full` | | false | Include all optional evidence except named setup; uses `foreign-accumulation` for strategy evidence when `--strategy` is omitted |
| `--sentiment-verbose` | | false | Show optional sentiment provider errors/noise |
| `--no-refresh` | | false | Disable automatic single-ticker candle/broker refresh |
| `--force-refresh` | | false | Force provider refresh even when cached data is fresh |
| `--with-technical-gate` | | false | Enable the optional TechnicalGate (SMA/EMA/RSI execution gate). Off by default. Adds "Technical" row to engine summary. |
| `--regime-universe` | | | Universe for regime breadth context |
| `--benchmark` | | ^JKSE | Benchmark ticker for regime |
| `--format` | | table | Output format: table or json |
| `--db` | | | SQLite database path |

#### `saham trade backtest-swing` - Portfolio Walk-Forward Backtest

```bash
saham trade backtest-swing --universe idx80 --setup foreign-bounce
saham trade backtest-swing --universe idx80 --setup coiled-spring
saham trade backtest-swing --universe idx80 --setup pullback-continuation
saham trade backtest-swing --universe lq45 --capital 50000000 --max-positions 3
saham trade backtest-swing --universe idx80 --with-regime --allow-regimes RISK_ON,NEUTRAL
saham trade backtest-swing --universe idx80 --cost-bps 0  # gross/no-cost comparison
saham trade backtest-swing --universe idx80 --with-attribution
saham trade backtest-swing --universe idx80 --with-tuning-plan
saham trade backtest-swing --universe idx80 --with-tuning-proposal
saham trade backtest-swing --universe idx80 --with-tuning-diff
```

Default backtests include `--cost-bps 20` one-way transaction cost. Override explicitly
when testing a different broker fee assumption.

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--universe` | `-u` | | Universe name (lq45, idx80, idxcomp100, cached) |
| `--setup` | | foreign-bounce | Swing setup: foreign-bounce, coiled-spring, smart-money-confirmed, pullback-continuation |
| `--start` | | (config) | Backtest start date, YYYY-MM-DD |
| `--end` | | today | Backtest end date, YYYY-MM-DD |
| `--capital` | `-c` | (config) | Initial capital in IDR |
| `--risk-pct` | | (config) | % of capital risked per trade |
| `--max-positions` | | 5 | Maximum concurrent open positions |
| `--take-profit` | | (config) | Take-profit percentage |
| `--stop-loss` | | (config) | Stop-loss percentage |
| `--max-hold` | | (config) | Maximum holding period in trading days |
| `--cost-bps` | | (config) | One-way transaction cost in basis points |
| `--with-regime` | | false | Group trades by entry-date market regime |
| `--allow-regimes` | | | Comma-separated entry regimes allowed |
| `--benchmark` | | ^JKSE | Benchmark ticker for regime context |
| `--show-trades` | | 20 | Number of recent trades to print |
| `--with-attribution` | | false | Show deterministic grouped attribution summary for manual tuning |
| `--with-tuning-plan` | | false | Show deterministic tuning readiness plan; no AI or YAML changes |
| `--with-tuning-proposal` | | false | Show deterministic dry-run tuning proposal targets; no YAML diff |
| `--with-tuning-diff` | | false | Show guarded dry-run tuning config diff draft; no apply |
| `--format` | | table | Output format: table or json |
| `--db` | | | SQLite database path |

Swing setup gates are deterministic and configurable in `config/swing_setups.yaml`:

Backtest JSON includes a deterministic attribution summary for tuning. Its
intent is learning/reporting only: grouped setup, signal, risk, and regime
statistics must not be used as live entry logic. Completed-trade attribution is
reported under `group_stats`; screened-candidate forward-return attribution is
reported under `candidate_group_stats` to reduce survivorship bias from setup
and risk candidates that were not opened as portfolio trades. Attribution score
buckets are reporting-only and configurable in `config/swing_backtest.yaml`.
The `tuning_targets` block is the deterministic allowlist that maps each
attribution dimension to the YAML files and fields it may influence.
The `sample_quality` block is the deterministic readiness gate; tuner proposals
must not act on summaries marked `INSUFFICIENT_SAMPLE`.
Use `--with-tuning-plan` to print the readiness preflight explicitly. It reports
whether changes may be proposed, which evidence scopes are allowed, and which
config families are in scope. It does not create an AI proposal, YAML diff, or
config mutation.
Use `--with-tuning-proposal` to print the next dry-run handoff contract. It
lists evidence-backed config targets that may be reviewed, plus rejected targets
and reasons in JSON output. It still does not choose parameter values, generate
YAML diffs, run AI, or mutate config. Proposal candidates include deterministic
`priority`, `evidence_strength`, sample count, and return-spread fields so review
targets are ranked before any future tuning engine proposes values.
Use `--with-tuning-diff` to print the guarded config-diff schema for future
tuners. Current output resolves `current_value` for concrete YAML paths and
rejects wildcard paths such as `setups.*.gates`. It may select `proposed_value`
only for numeric non-boolean thresholds when evidence strength is HIGH and the
path has an unambiguous min/max direction. It never applies changes, runs AI, or
mutates config. JSON output includes parsed target path fields (`file_path`,
`document_path`, `raw`) and a machine-readable `value_selection_policy`
explaining whether a deterministic value was selected or why `proposed_value`
remains unset.

#### `saham trade tune-swing` - Deterministic Swing Tuning Review

```bash
saham trade tune-swing --universe idx80 --setup foreign-bounce
saham trade tune-swing --universe lq45 --with-regime --format json
saham trade tune-swing --universe idx80 --save
saham trade review-tuning-swing
```

Runs the same walk-forward replay as `backtest-swing`, then emits attribution,
readiness, proposal-target, and guarded config-diff review artifacts in one
place. This command is review-only: it does not call AI, does not apply YAML
changes, and does not mutate configuration. Use `--save` to append the review
artifact to `journals/swing_tuning_reviews.jsonl`; use `--journal PATH` to
override that path for one run. Use `saham trade review-tuning-swing` to inspect
saved review runs without replaying the backtest.

Attribution dimensions map to these primary tuning files:

| Attribution dimension | Primary config target |
|-----------------------|-----------------------|
| `trade_setup_action`, `signal_strength`, `signal_score_bucket`, `signal_factor_bucket` | `config/signal_engine.yaml` |
| `risk_status`, `risk_gate` | `config/risk_engine.yaml` |
| `setup_gate` | `config/swing_setups.yaml` |
| `regime` | `config/market_context_engine.yaml`, `config/swing_targets.yaml` |
| execution assumptions, reporting buckets | `config/swing_backtest.yaml` |

| Setup | Question Answered |
|-------|-------------------|
| `foreign-bounce` | Is foreign accumulation happening while price is still below foreign VWAP in a range? |
| `coiled-spring` | Is accumulation happening while volatility is compressed enough for a potential expansion? |
| `smart-money-confirmed` | Is broker attribution led by smart-money flow rather than noise flow? |
| `pullback-continuation` | Is an uptrend pullback still supported by foreign flow and RSI headroom? |

#### `saham trade backtest-intraday` - Intraday Proxy Simulation

```bash
saham trade backtest-intraday --universe idx80 --start 2026-01-01
saham trade backtest-intraday BBCA BBRI --include-wait
```

This command is a daily-OHLC proxy simulation, not an exact intraday replay.
It builds candidates from prior-session data, uses `candle.open` as the opening
auction proxy, and exits using the same day's high/low/close. If stop and target
are both touched in the daily candle, the simulation assumes the stop was hit
first. Saved IEV/NCP snapshots are applied only for dates where they exist;
otherwise the full requested universe is screened. Live confirmation gates such
as tick-friction and regime tightening are not replayed in this proxy.

Use it to sanity-check whether the intraday idea has broad historical expectancy,
not to validate exact auction execution, slippage, bid/offer path, or minute-level
timing.

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

#### `saham trade log --type swing` / `saham trade review swing`

Aliases for accumulation journal commands.

---

### `saham analyze regime` - Market Regime

Show deterministic cross-market context for swing trading.

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
| `--verbose` | `-v` | false | Show score bar and rationale per factor |
| `--format` | | table | Output format: table or json |
| `--db` | | | SQLite database path |

**Regime labels:** `RISK_ON`, `NEUTRAL`, `RISK_OFF`, `VOLATILE`

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

### `saham fetch audit` - Local Data Quality Audit

Audit cached SQLite data without network access or data mutation:

```bash
saham fetch audit
saham fetch audit BBCA BBRI
```

Reports stale core data, degraded Stockbit broker summary rows, unsafe broker
denominators, candle provenance gaps, and enrichment coverage. It is a
diagnostic report only; it does not repair or refresh data.

---

### `saham fetch stockbit` - Stockbit Session Management

Manage the Stockbit JWT token and browser session. Browser is used only for
`login`, `spy`, and `browse` — all data commands use the persisted token via httpx.

```bash
saham fetch stockbit login                    # Open browser for manual login (saves JWT)
saham fetch stockbit login --timeout 180      # Longer timeout for 2FA
saham fetch stockbit status                   # Check session health
saham fetch stockbit spy                      # Capture API traffic
saham fetch stockbit spy --target orderbook --ticker BBRI
saham fetch stockbit test                     # Smoke-test movers + orderbook (no browser)
saham fetch stockbit test --ticker BMRI       # Use different ticker for orderbook test
saham fetch stockbit fetch-top5 --top 5       # Top IEV movers + orderbooks
saham fetch stockbit browse                   # Interactive browser session
```

| Command | Purpose |
|---------|---------|
| `saham fetch stockbit login` | Open browser once to save JWT to `.stockbit_profile/token.json` |
| `saham fetch stockbit status` | Check token age and session health |
| `saham fetch stockbit spy` | Capture API traffic to identify endpoints |
| `saham fetch stockbit test` | Smoke-test movers + orderbook via persisted JWT (no browser) |
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
│   ├── entities/                    # Stock, Candle, BrokerFlow, StockMeta
│   ├── indicators/                  # SMA, EMA, RSI, MACD calculations
│   │   ├── indicator_context.py     # Enriched context for indicator evaluation
│   │   └── indicator_reading.py     # IndicatorReading measurement language
│   ├── ports/                       # Interfaces (38 provider/repository ports)
│   │   ├── broker_data_provider.py / broker_data_repository.py
│   │   ├── market_data_provider.py / market_data_repository.py
│   │   ├── ai_explainer.py / ai_analyzer.py
│   │   ├── news_provider.py / headline_classifier.py
│   │   ├── analyst_consensus_provider.py
│   │   ├── bandar_detector_provider.py
│   │   ├── broker_distribution_provider.py
│   │   ├── browser_data_provider.py
│   │   ├── company_profile_provider.py
│   │   ├── earnings_provider.py / forward_estimates_provider.py
│   │   ├── fundamentals_provider.py
│   │   ├── insider_activity_provider.py
│   │   ├── intraday_broker_chart_provider.py
│   │   ├── market_status_provider.py
│   │   ├── order_book_provider.py
│   │   ├── running_trade_provider.py / running_trade_chart_provider.py
│   │   ├── seasonality_provider.py
│   │   ├── shareholding_provider.py
│   │   ├── stock_meta_provider.py / stock_meta_repository.py
│   │   ├── system_status_provider.py
│   │   ├── ticker_notation_provider.py / ticker_notation_repository.py
│   │   ├── valuation_provider.py
│   │   ├── accumulation_journal_store.py / trade_journal_store.py
│   │   ├── csv_broker_parser.py / persistence.py
│   │   └── sentiment_repository.py
│   ├── rules/                       # Risk assessment gates
│   │   ├── risk_gate.py             # Abstract gate interface + context
│   │   ├── technical_gate.py        # Optional RSI/EMA/SMA execution gate
│   │   ├── fundamental_gate.py      # P/E, ROE, Piotroski F-Score, quality gate
│   │   ├── bandar_gate.py           # Stockbit operator accumulation/distribution score
│   │   ├── liquidity_gate.py        # Volume + turnover ratio checks
│   │   ├── free_float_gate.py       # Free float ratio filter
│   │   └── base_rule.py
│   ├── services/
│   │   ├── analyze_stock.py
│   │   ├── backtest_engine.py
│   │   └── trading_calendar.py
│   └── value_objects/               # Immutable domain objects (34)
│       ├── risk_assessment.py / risk_signal.py
│       ├── backtest_result.py / screener_result.py
│       ├── sentiment.py
│       ├── market_context.py / trade_setup.py
│       ├── indicator_snapshot.py / intraday_confirmation.py
│       ├── analyst_consensus.py / company_fundamentals.py
│       ├── company_profile.py
│       ├── signal_assessment.py
│       ├── earnings_record.py / forward_estimates.py
│       ├── insider_transaction.py / bandar_detector_snapshot.py
│       ├── intraday_broker_chart.py
│       ├── market_status.py / idx_market.py
│       ├── order_book_snapshot.py
│       ├── running_trade_chart.py / running_trade_signal.py
│       ├── screen_snapshot.py / accumulation_journal_entry.py
│       ├── seasonal_edge.py / ticker_notation.py
│       ├── shareholding_composition.py / corporate_action_event.py
│       ├── tick_size.py / trade_action.py
│       ├── valuation_metrics.py / broker_distribution.py
│       └── skill_annotation.py
│
├── application/                      # Use cases & application services
│   ├── ports/                         # Application port interfaces
│   │   ├── annotation_reader.py
│   │   ├── rules_hasher.py
│   │   ├── rules_loader.py
│   │   └── universe_summary_provider.py
│   ├── use_case/                      # All use cases follow *_use_case.py naming
│   │   ├── fetch_market_data_use_case.py
│   │   ├── refresh_market_data_use_case.py
│   │   ├── fetch_broker_data_use_case.py
│   │   ├── fetch_broker_daily_flows_use_case.py
│   │   ├── fetch_market_refresh_use_case.py
│   │   ├── refresh_broker_data_use_case.py
│   │   ├── refresh_stockbit_enrichment_use_case.py
│   │   ├── compute_sma_use_case.py / compute_ema_use_case.py / compute_rsi_use_case.py
│   │   ├── aggregate_indicators_use_case.py
│   │   ├── assess_risk_use_case.py / explain_risk_use_case.py
│   │   ├── fetch_sentiment_use_case.py / audit_sentiment_use_case.py
│   │   ├── backtest_use_case.py / swing_backtest_use_case.py
│   │   ├── pre_open_screen_use_case.py / pre_open_workflow_use_case.py
│   │   ├── confirm_intraday_open_use_case.py / intraday_backtest_use_case.py
│   │   ├── accumulation_screen_use_case.py / accumulation_audit_use_case.py
│   │   ├── market_regime_use_case.py
│   │   ├── data_quality_audit_use_case.py
│   │   ├── data_update_status_use_case.py
│   │   ├── daily_briefing_use_case.py
│   │   ├── analyze_running_trade_use_case.py
│   │   ├── swing_analysis_workflow_use_case.py
│   │   ├── assess_signal_use_case.py
│   │   ├── assess_trade_setup_use_case.py
│   │   ├── score_foreign_flow_use_case.py
│   │   ├── evaluate_swing_setup_use_case.py
│   │   ├── build_market_context_use_case.py
│   │   ├── opening_snapshot_use_case.py / opening_track_use_case.py
│   │   ├── opening_grade_use_case.py / opening_prompt_use_case.py
│   │   ├── opening_tune_use_case.py
│   │   ├── create_indicator_from_intent_use_case.py
│   │   ├── create_strategy_from_intent_use_case.py
│   │   ├── import_broker_data_use_case.py
│   │   ├── log_swing_candidate_use_case.py
│   │   ├── compare_screen_snapshots_use_case.py
│   │   ├── resolve_opening_prices_use_case.py
│   │   ├── fetch_stock_meta_use_case.py
│   │   ├── get_system_status_use_case.py
│   │   ├── run_analysis_use_case.py
│   │   └── view_universe_summary_use_case.py
│   ├── formula/                      # Formula DSL engine
│   │   ├── tokenizer.py / parser.py / ast_nodes.py
│   │   ├── validator.py / evaluator.py
│   ├── services/
│   │   ├── risk_engine.py            # First-class risk assessment (ADR-024)
│   │   ├── signal_engine.py          # First-class signal assessment (ADR-025)
│   │   ├── market_context_engine.py  # First-class market context (ADR-029)
│   │   ├── indicator_registry.py
│   │   ├── indicator_evaluator.py    # Evaluates indicators from config
│   │   ├── strategy_loader.py
│   │   ├── skill_generator.py
│   │   ├── universe_loader.py
│   │   ├── position_sizer.py
│   │   ├── accumulation_journal.py
│   │   ├── ai_research.py
│   │   ├── bootstrap.py              # App initialization + plugin loading
│   │   ├── broker_quality.py
│   │   ├── group_mapping.py
│   │   └── intraday_confirmation_journal.py
│   ├── ports/
│   │   ├── formula_translator.py
│   │   ├── strategy_translator.py
│   │   ├── skill_writer.py
│   │   └── corporate_action_repository.py
│   ├── rules/
│   │   ├── schema.py
│   │   └── interpreter.py
│   └── dto/
│
├── infrastructure/                   # External implementations
│   ├── data_providers/
│   │   ├── yahoo.py                  # Yahoo Finance
│   │   ├── yahoo_stock_meta.py       # Yahoo stock metadata
│   │   ├── idx.py                    # IDX broker data
│   │   ├── idx_market.py             # IDX market data
│   │   ├── stockbit_historical.py    # Stockbit historical candles
│   │   └── fallback_provider.py      # Provider fallback chain
│   ├── browser/                      # Stockbit enrichment providers (24 files)
│   │   ├── playwright_stockbit_provider.py  # Broker provider (delegates to browser module)
│   │   ├── playwright_stockbit_browser.py   # Browser lifecycle + session management
│   │   ├── stockbit_analyst.py
│   │   ├── stockbit_bandar.py
│   │   ├── stockbit_browser_provider.py
│   │   ├── stockbit_broker_distribution.py
│   │   ├── stockbit_company_profile.py
│   │   ├── stockbit_corp_action.py
│   │   ├── stockbit_earnings.py
│   │   ├── stockbit_forward_estimates.py
│   │   ├── stockbit_fundamentals.py
│   │   ├── stockbit_insider.py
│   │   ├── stockbit_intraday_broker_chart.py
│   │   ├── stockbit_market_time.py
│   │   ├── stockbit_order_book.py
│   │   ├── stockbit_providers.py
│   │   ├── stockbit_running_trade.py
│   │   ├── stockbit_running_trade_chart.py
│   │   ├── stockbit_seasonality.py
│   │   ├── stockbit_shareholding.py
│   │   ├── stockbit_ticker_notation.py
│   │   ├── stockbit_universe.py
│   │   └── stockbit_valuation.py
│   ├── persistence/
│   │   ├── sqlite.py                 # Core SQLite repository
│   │   ├── sqlite_market_repository.py
│   │   ├── sqlite_broker_repository.py
│   │   ├── sqlite_stock_meta_repository.py
│   │   ├── sqlite_data_quality_audit.py
│   │   ├── sqlite_data_update_status.py
│   │   ├── sqlite_iev_repository.py
│   │   ├── sqlite_watchlist_repository.py
│   │   ├── sqlite_system_status_provider.py
│   │   ├── sqlite_market_context_repository.py
│   │   ├── formula_storage.py
│   │   ├── sentiment_repository.py
│   │   ├── intraday_confirmation_csv.py
│   │   ├── accumulation_journal_csv_writer.py
│   │   ├── iev_json_sidecar.py
│   │   ├── trade_journal_jsonl_writer.py
│   │   └── swing_tuning_review_jsonl_writer.py
│   ├── ai/
│   │   ├── factory.py                # AI provider factory + rate limiter wrapper
│   │   ├── deepseek_explainer.py
│   │   ├── claude_explainer.py
│   │   ├── openai_explainer.py
│   │   ├── gemini_explainer.py
│   │   ├── ollama_explainer.py
│   │   ├── formula_translator.py / prompt.py
│   │   ├── strategy_translator.py / prompt.py
│   │   ├── sentiment_analyzer.py
│   │   └── mock_explainer.py
│   ├── sentiment/
│   │   ├── factory.py                # Multi-source provider factory
│   │   ├── google_news_provider.py
│   │   ├── cnbc_indonesia_provider.py
│   │   ├── kontan_provider.py
│   │   ├── composite_provider.py     # Composite across sources
│   │   ├── deduplication.py
│   │   ├── keyword_classifier.py
│   │   ├── ai_classifier.py
│   │   └── mock_provider.py
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
│       ├── swing_config.py           # Swing policy configuration
│       └── yaml_loader.py
│
├── adapters/                         # User interfaces
│   ├── cli/
│   │   ├── main.py                   # CLI entry point (group definitions)
│   │   ├── fetch_commands.py         # Fetch group router
│   │   ├── fetch_market_commands.py
│   │   ├── fetch_iev_commands.py
│   │   ├── fetch_universe_commands.py
│   │   ├── fetch_status_commands.py
│   │   ├── fetch_audit_commands.py
│   │   ├── fetch_stockbit_commands.py
│   │   ├── fetch_broker_commands.py / fetch_broker_display.py
│   │   ├── view_commands.py          # Read-only broker views + ticker dashboard
│   │   ├── view_ticker_display.py    # Read-only ticker dashboard display
│   │   ├── view_universe_display.py
│   │   ├── view_broker_commands.py / view_broker_display.py
│   │   ├── learn_commands.py         # Learning loop group commands
│   │   ├── today_commands.py
│   │   ├── analyze_commands.py
│   │   ├── analyze_swing_commands.py / analyze_swing_display.py
│   │   ├── analyze_swing_broker_display.py
│   │   ├── analyze_chart_commands.py
│   │   ├── analyze_sentiment_commands.py
│   │   ├── analyze_regime_commands.py / analyze_regime_display.py
│   │   ├── analyze_accum_commands.py / analyze_accum_display.py
│   │   ├── trade_commands.py
│   │   ├── trade_swing_commands.py / trade_swing_display.py
│   │   ├── trade_swing_size_display.py
│   │   ├── trade_intraday_commands.py / trade_intraday_display.py
│   │   ├── trade_intraday_backtest_display.py
│   │   ├── trade_accum_commands.py / trade_accum_display.py
│   │   ├── indicator_commands.py
│   │   ├── strategy_commands.py / strategy_skill_commands.py
│   │   ├── screen_pre_open_commands.py / screen_pre_open_display.py
│   │   ├── screen_lifecycle_commands.py
│   │   ├── screen_accum_commands.py / screen_accum_display.py
│   │   └── rich_display.py           # Shared Rich rendering
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
- Rule-first, AI-optional — risk gates and rules do the work; AI explains
- RiskEngine, SignalEngine, and MarketContextEngine are first-class application services
- Complete trade verdicts are composed through TradeSetup / AssessTradeSetupUseCase
- AI is always optional and swappable (DeepSeek default)
- Plugins extend functionality without modifying core

**Workflow Artifacts:**

| Command | Primary output | Interpretation |
|---------|----------------|----------------|
| `saham analyze swing TICKER` | `TradeSetup` | Final swing verdict from `SignalEngine + RiskEngine` |
| `saham screen accum` | `AccumulationCandidate` | Ranked discovery result; action appears only when signal and risk are both available |
| `saham screen pre-open` | `PreOpenScreenResult` | Intraday pre-open plan with conditional entry ranges |
| `saham trade confirm` | `IntradayConfirmationResult` | Post-open ENTER/WAIT/SKIP decision using actual opening price |
| `saham trade backtest-swing` | `SwingBacktestResponse` | Historical walk-forward performance artifact |
| `saham trade tune-swing` | `swing_tuning_review` | Deterministic attribution-to-config review artifact; no apply |
| `saham trade review-tuning-swing` | `swing_tuning_review_history` | Read-only summary of saved tuning review artifacts |
| `saham trade backtest-intraday` | `IntradayBacktestResponse` | Daily-OHLC intraday proxy simulation artifact |
| `saham analyze accum-audit` | `AccumulationAuditResponse` | Learning/audit artifact for forward-return behavior |

JSON outputs and command sidecars include `schema_version` and `artifact_type`
at the root. Explicit fields such as `foreign_flow_score`, `signal_score`, and
`risk_status` are canonical; new machine-facing outputs should avoid ambiguous
score/status aliases.
For `saham analyze swing --format json`, grouped `verdict`, `evidence`, and
`diagnostics` are canonical.

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
| `config/default.yaml` | Authoritative CLI defaults source (overridable by `config/user.yaml` and CLI flags) |
| `config/user.yaml.example` | Template for personal config overrides |
| `config/stockbit.yaml` | Stockbit browser profile and session configuration |
| `config/custom_rules.yaml.example` | Custom rules DSL template |
| `config/formulas.yaml` | Persisted custom formulas |
| `config/universes.yaml` | Ticker universe definitions |
| `config/idx_groups.yaml` | IDX sector/industry group mappings |
| `config/risk_engine.yaml` | Risk gate enablement, thresholds, confidence/missing-data policy, indicator defaults, technical-gate tuning, and market-context gate policy |
| `config/signal_engine.yaml` | Signal factor enablement, weights, classification thresholds, missing-data policy, enrichment lookbacks, input mapping, and factor scoring thresholds |
| `config/market_context_engine.yaml` | Market context factors, thresholds, VIX score anchors, scoring labels/fallbacks, warning policy, and regime effects |
| `config/accumulation_screener.yaml` | Accumulation discovery policy (filters, sector breadth, broker quality, BCI, evidence weights, and derived feature windows) |
| `config/accumulation_audit.yaml` | Accumulation-audit learning policy: setup presets, forward-return horizons, exit simulation assumptions, grouping dimensions, and bucket edges |
| `config/swing_setups.yaml` | Named swing setup gates |
| `config/swing_targets.yaml` | Regime-adaptive TP/SL targets |
| `config/swing_backtest.yaml` | Swing backtest portfolio defaults and execution assumptions, including cost, max hold, forward lookahead, and same-day stop/target priority |
| `config/analyze_swing.yaml` | Analyze-swing workflow defaults for auto-refresh windows, sentiment lookback, flow-detail window, and permissive single-ticker candidate construction |
| `config/swing_risk_policy.yaml` | Swing risk overlays outside RiskEngine (resistance, corporate action warning) |
| `config/pre_open_screener.yaml` | Pre-open screener rules and thresholds |
| `config/atr_rules.yaml.example` | ATR-based risk rule template |
| `config/csv_mappings/` | CSV import column mapping definitions |

Config file locations are centralized under `config_paths:` in `config/default.yaml`;
override that section in `config/user.yaml` when using personal config copies.

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

**Project Stats:** 325 source files (~62k LOC), 148 test files (~36k LOC)

---

## Data Storage

- **Location:** `data/db/data.db` (SQLite, configurable via `--db` or `config/default.yaml`)
- **Content:** Cached OHLCV candles (with source provenance), broker summaries, sentiment logs, trade journals, swing tuning review journals, Stockbit enrichment cache (analyst consensus, insider trades, fundamentals, corporate actions, forward estimates, company profiles, shareholding, seasonality)
- **Refresh:** Use `--refresh` flag or `saham fetch market --universe <name>` to batch update
- **Enrichment TTL:** Enrichment data auto-refreshes on a per-column TTL basis (daily for price data, weekly for fundamentals, monthly for shareholding)

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
