# AI Saham - Stock Analysis CLI

A **local-first, production-grade CLI application** for stock analysis focused on the Indonesia Stock Exchange (IDX).

## Features

- **Deterministic analysis** - Rule-based technical indicators (SMA, EMA, RSI)
- **Risk assessment** - Three risk profiles (conservative, balanced, aggressive)
- **Offline-first** - Works without internet after initial data fetch
- **Local storage** - SQLite database for cached market data
- **Extensible** - Hexagonal architecture ready for bots, web, and AI integration

---

## Quick Start

```bash
# Fetch stock data
saham fetch BBCA

# View all indicators
saham indicators BBCA

# Assess risk
saham risk BBCA --all
```

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
```

### Verify Installation

```bash
saham version
# Output: saham v0.1.0
```

---

## CLI Commands

### `saham fetch` - Fetch Market Data

Fetch daily OHLCV data for an IDX stock ticker. Data is cached locally after first fetch.

```bash
# Basic usage - fetches 1 year of data
saham fetch BBCA

# Fetch 2 years of data
saham fetch BBRI --days 730

# Force refresh (bypass cache)
saham fetch TLKM --refresh

# Custom database location
saham fetch ASII --db /path/to/custom.db
```

**Options:**
| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--days` | `-d` | 365 | Number of days of history |
| `--refresh` | `-r` | false | Force refresh from provider |
| `--db` | | ~/.ai-saham/data.db | Database path |

---

### `saham sma` - Simple Moving Average

Calculate SMA over cached market data.

```bash
saham sma BBCA                    # SMA(20) on close prices
saham sma BBRI --period 50        # Custom period
saham sma TLKM --field open       # Different price field
saham sma ASII --days 730         # More history
```

**Options:**
| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--period` | `-p` | 20 | SMA period |
| `--field` | `-f` | close | Price field (open/high/low/close) |
| `--days` | `-d` | 365 | Days of history |

---

### `saham ema` - Exponential Moving Average

Calculate EMA with SMA-seeded initialization (matches TradingView, Bloomberg).

```bash
saham ema BBCA                    # EMA(20) on close prices
saham ema BBRI --period 50        # Custom period
saham ema TLKM --field high       # Different price field
```

**Options:** Same as `sma` command.

---

### `saham rsi` - Relative Strength Index

Calculate RSI using Wilder's smoothed moving average.

```bash
saham rsi BBCA                    # RSI(14)
saham rsi BBRI --period 7         # Shorter period
saham rsi TLKM --days 180         # Less history
```

**Options:**
| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--period` | `-p` | 14 | RSI period |
| `--days` | `-d` | 365 | Days of history |

**RSI Interpretation:**
- Above 70: Potentially overbought
- Below 30: Potentially oversold
- 30-70: Neutral

---

### `saham indicators` - All Indicators

Calculate SMA, EMA, and RSI together with aligned dates.

```bash
saham indicators BBCA                          # Default periods
saham indicators BBRI --sma 50 --ema 50        # Custom SMA/EMA
saham indicators TLKM --rsi 7 --days 180       # Custom RSI
```

**Options:**
| Option | Default | Description |
|--------|---------|-------------|
| `--sma` | 20 | SMA period |
| `--ema` | 20 | EMA period |
| `--rsi` | 14 | RSI period |
| `--days` | 365 | Days of history |

---

### `saham risk` - Risk Assessment

Assess risk using deterministic, rule-based evaluation.

```bash
saham risk BBCA                       # Balanced profile (default)
saham risk BBRI --profile conservative
saham risk TLKM --all                 # Compare all profiles
```

**Risk Profiles:**

| Profile | Description |
|---------|-------------|
| `conservative` | Strict thresholds, requires indicators to agree |
| `balanced` | Standard thresholds, majority rules |
| `aggressive` | Wide thresholds, either indicator can signal |

**Risk Levels:**
- `HIGH_RISK` - Indicators suggest elevated risk
- `MODERATE` - Indicators suggest neutral conditions
- `LOW_RISK` - Indicators suggest favorable conditions

**Options:**
| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--profile` | `-p` | balanced | Risk profile |
| `--all` | `-a` | false | Show all profiles |
| `--sma` | | 20 | SMA period |
| `--ema` | | 20 | EMA period |
| `--rsi` | | 14 | RSI period |

---

### `saham version` - Version Info

```bash
saham version
```

---

## Architecture

```
src/
├── domain/              # Pure business logic (no external dependencies)
│   ├── entities/        # Stock, Candle, AnalysisResult
│   ├── indicators/      # SMA, EMA, RSI, MACD calculations
│   ├── ports/           # Interfaces (MarketDataProvider, Repository)
│   └── rules/           # Risk assessment rules by profile
│
├── application/         # Use cases orchestrating domain logic
│   ├── use_case/        # FetchMarketData, ComputeSMA, AssessRisk, etc.
│   └── dto/             # Request/Response objects
│
├── infrastructure/      # External system implementations
│   ├── data_providers/  # Yahoo Finance, IDX adapters
│   ├── persistence/     # SQLite repositories
│   ├── ai/              # Claude, Gemini integrations (optional)
│   └── sentiment/       # News, social media analyzers (future)
│
└── adapters/            # User interfaces
    ├── cli/             # Typer-based CLI (current)
    ├── bot/             # Telegram, WhatsApp (stubs)
    └── web/             # REST API (stub)
```

**Key Principle:** Domain logic is pure and framework-agnostic. External systems never leak into the domain.

---

## Configuration

Risk profiles are defined in `config/`:

| File | Description |
|------|-------------|
| `default.yaml` | Base configuration |
| `conservative.yaml` | Strict risk thresholds |
| `balanced.yaml` | Standard risk thresholds |
| `aggressive.yaml` | Wide risk thresholds |
| `full_ai.yaml` | AI-enhanced mode (future) |

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

---

## Data Storage

- **Location:** `~/.ai-saham/data.db` (SQLite)
- **Content:** Cached OHLCV candles per ticker
- **Refresh:** Use `--refresh` flag to update

---

## Offline Behavior

This CLI is designed to work **offline after initial data fetch**:

1. **First fetch requires internet** - Downloads data from Yahoo Finance
2. **All analysis works offline** - SMA, EMA, RSI, indicators, risk assessment use cached data
3. **Cache persists** - Data stored in SQLite survives restarts

**Typical workflow:**
```bash
# Online: Fetch data once
saham fetch BBCA
saham fetch BBRI
saham fetch TLKM

# Offline: Analyze anytime
saham indicators BBCA
saham risk BBRI --all
saham sma TLKM --period 50
```

**Refreshing data:**
```bash
# Re-download latest data (requires internet)
saham fetch BBCA --refresh
```

---

## Troubleshooting

### "Database not found"

```
Error: Database not found at ~/.ai-saham/data.db
```

**Solution:** Fetch data first:
```bash
saham fetch BBCA
```

### "No cached data found"

```
Error: No cached data found for XXXX
```

**Solution:** The ticker hasn't been fetched yet:
```bash
saham fetch XXXX
```

### "Insufficient data"

```
Insufficient data for BBCA
Candles available: 15
Required for SMA(200): 200
```

**Solution:** Fetch more historical data:
```bash
saham fetch BBCA --days 730 --refresh
```

### "Network connection failed"

```
Error: Network connection failed.
```

**Solutions:**
- Check your internet connection
- Try again later (Yahoo Finance may be temporarily unavailable)
- Use cached data for analysis if available

### Invalid option values

```
Error: Invalid value for '--profile': Invalid profile 'xyz'. Must be one of: conservative, balanced, aggressive
```

**Solution:** Use valid option values as shown in command help:
```bash
saham risk --help
```

---

## Risk Profile Selection Guide

Choose the right profile based on your analysis needs:

| Profile | Best For | Characteristics |
|---------|----------|-----------------|
| **conservative** | Long-term investors, risk-averse | Strict thresholds, requires multiple indicators to agree |
| **balanced** | General analysis, moderate risk tolerance | Standard thresholds, majority of indicators rules |
| **aggressive** | Active traders, higher risk tolerance | Wide thresholds, single indicator can signal |

**Quick decision guide:**

- **New to stock analysis?** Start with `balanced`
- **Prioritizing capital preservation?** Use `conservative`
- **Comfortable with higher risk for potential gains?** Try `aggressive`

**Compare all profiles at once:**
```bash
saham risk BBCA --all
```

---

## Limitations

- **Daily data only** - No intraday or real-time streaming
- **IDX market focus** - Designed for Indonesia Stock Exchange
- **Yahoo Finance source** - Data may be delayed; unofficial source
- **Internet required** for first fetch (offline after caching)

---

## What This Project Is NOT

- An automated trading or execution system
- An AI-only or black-box analyzer
- A real-time, high-frequency trading platform
- Financial advice provider

**DISCLAIMER:** This tool provides analysis only, not trading advice.

---

## License

License to be determined.
