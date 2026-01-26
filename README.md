# AI Saham - Stock Analysis CLI

[![CI](https://github.com/anthropics/ai-saham/actions/workflows/ci.yml/badge.svg)](https://github.com/anthropics/ai-saham/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A **local-first, production-grade CLI application** for stock analysis focused on the Indonesia Stock Exchange (IDX).

## Features

- **Technical Indicators** - SMA, EMA, RSI with professional-grade calculations
- **Risk Assessment** - Three built-in profiles (conservative, balanced, aggressive)
- **Custom Rules DSL** - Define your own rules via YAML configuration
- **AI Explanations** - Get AI-powered insights (Claude, OpenAI, Gemini, Ollama)
- **News Sentiment** - Analyze news headlines with keyword or AI classification
- **Offline-First** - Works without internet after initial data fetch
- **Local Storage** - SQLite database for cached market data
- **Hexagonal Architecture** - Clean separation of domain, application, and infrastructure

---

## Quick Start

```bash
# Fetch stock data
saham fetch BBCA

# View all indicators
saham indicators BBCA

# Assess risk with all profiles
saham risk BBCA --all

# Get AI explanation
saham risk BBCA --explain --provider ollama

# Analyze news sentiment
saham sentiment BBCA
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
```

---

## CLI Commands

### `saham fetch` - Fetch Market Data

Fetch daily OHLCV data for an IDX stock ticker from Yahoo Finance.

```bash
saham fetch BBCA                    # Fetch 1 year of data
saham fetch BBRI --days 730         # Fetch 2 years
saham fetch TLKM --refresh          # Force refresh cache
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--days` | `-d` | 365 | Days of history to fetch |
| `--refresh` | `-r` | false | Bypass cache, fetch fresh data |
| `--db` | | ~/.ai-saham/data.db | Custom database path |

---

### `saham sma` - Simple Moving Average

```bash
saham sma BBCA                      # SMA(20) on close
saham sma BBRI --period 50          # Custom period
saham sma TLKM --field open         # Different price field
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--period` | `-p` | 20 | SMA period |
| `--field` | `-f` | close | Price field (open/high/low/close) |
| `--days` | `-d` | 365 | Days of history |

---

### `saham ema` - Exponential Moving Average

Uses SMA-seeded initialization (matches TradingView, Bloomberg).

```bash
saham ema BBCA                      # EMA(20) on close
saham ema BBRI --period 50          # Custom period
```

Options same as `sma` command.

---

### `saham rsi` - Relative Strength Index

Uses Wilder's smoothed moving average.

```bash
saham rsi BBCA                      # RSI(14)
saham rsi BBRI --period 7           # Shorter period
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--period` | `-p` | 14 | RSI period |
| `--days` | `-d` | 365 | Days of history |

**RSI Interpretation:** >70 overbought, <30 oversold, 30-70 neutral

---

### `saham indicators` - All Indicators Combined

Calculate SMA, EMA, and RSI together with aligned dates.

```bash
saham indicators BBCA               # Default periods
saham indicators BBRI --sma 50 --ema 50 --rsi 7
```

| Option | Default | Description |
|--------|---------|-------------|
| `--sma` | 20 | SMA period |
| `--ema` | 20 | EMA period |
| `--rsi` | 14 | RSI period |
| `--days` | 365 | Days of history |

---

### `saham risk` - Risk Assessment

Assess risk using rule-based evaluation with optional AI explanation.

```bash
# Built-in profiles
saham risk BBCA                           # Balanced (default)
saham risk BBRI --profile conservative
saham risk TLKM --all                     # Compare all profiles

# Custom rules
saham risk BBCA --rules-file config/my_rules.yaml

# With AI explanation
saham risk BBCA --explain
saham risk BBCA --explain --provider ollama
saham risk BBCA --explain --provider ollama --model llama3:8b

# With sentiment
saham risk BBCA --with-sentiment
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--profile` | `-p` | balanced | Risk profile |
| `--all` | `-a` | false | Show all profiles |
| `--rules-file` | `-r` | | Custom YAML rules (overrides --profile) |
| `--explain` | `-e` | false | Generate AI explanation |
| `--provider` | | claude | AI provider |
| `--model` | `-m` | | Model name (for Ollama) |
| `--with-sentiment` | `-s` | false | Include news sentiment |

**Risk Profiles:**

| Profile | Description |
|---------|-------------|
| `conservative` | Strict thresholds, requires indicators to agree |
| `balanced` | Standard thresholds, majority rules |
| `aggressive` | Wide thresholds, single indicator can signal |

**Risk Levels:** `HIGH_RISK`, `MODERATE`, `LOW_RISK`

---

### `saham sentiment` - News Sentiment Analysis

Fetch and analyze news sentiment for a stock.

```bash
saham sentiment BBCA                      # Keyword classification (default)
saham sentiment BBRI --days 7             # More days
saham sentiment TLKM --ai-classify        # AI classification
saham sentiment ASII --ai-classify --provider ollama --model llama3
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--days` | `-d` | 3 | Days of news (1-30) |
| `--max` | | 20 | Max headlines (1-50) |
| `--ai-classify` | | false | Use AI for classification |
| `--provider` | | | AI provider for classification |
| `--model` | `-m` | | Model name |

**Sentiment Levels:** `POSITIVE`, `NEUTRAL`, `NEGATIVE`

---

### `saham version` - Version Info

```bash
saham version
```

---

## AI Providers

For `--explain` and `--ai-classify` features:

| Provider | Environment Variable | Default Model |
|----------|---------------------|---------------|
| `claude` | `ANTHROPIC_API_KEY` | claude-3-haiku |
| `openai` | `OPENAI_API_KEY` | gpt-3.5-turbo |
| `gemini` | `GOOGLE_API_KEY` | gemini-pro |
| `ollama` | (local, no key) | qwen2.5-coder:1.5b |
| `mock` | (none) | (for testing) |

```bash
# Set API key
export ANTHROPIC_API_KEY=sk-...

# Or use local Ollama
ollama serve  # In another terminal
saham risk BBCA --explain --provider ollama
```

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

Define custom indicator instances with specific periods:

```yaml
version: 1
name: "ema_crossover"
default_outcome: MODERATE

# Define custom indicators with specific periods
indicators:
  fast_ema:
    type: EMA
    period: 9
  slow_ema:
    type: EMA
    period: 21
  rsi_short:
    type: RSI
    period: 7

rules:
  # EMA crossover strategy
  - name: bullish_crossover
    priority: 10
    when:
      left:
        indicator: fast_ema   # EMA(9)
      operator: ">"
      right:
        indicator: slow_ema   # EMA(21)
    outcome: LOW_RISK
    rationale: "EMA(9) > EMA(21) - bullish momentum"

  # Short RSI for faster signals
  - name: short_rsi_oversold
    priority: 20
    when:
      indicator: rsi_short    # RSI(7)
      operator: "<"
      value: 25
    outcome: LOW_RISK
    rationale: "RSI(7) < 25 - oversold"
```

**Usage:**
```bash
saham risk BBCA --rules-file config/my_rules.yaml
```

**Built-in indicators** (always available): `RSI` (14), `SMA` (20), `EMA` (20)
**Supported types:** `RSI`, `SMA`, `EMA`
**Supported operators:** `<`, `<=`, `>`, `>=`, `==`, `!=`

---

## Architecture

```
src/
├── domain/                    # Pure business logic (no dependencies)
│   ├── entities/              # Stock, Candle, AnalysisResult
│   ├── indicators/            # SMA, EMA, RSI, MACD calculations
│   ├── ports/                 # Interfaces
│   │   ├── market_data_provider.py
│   │   ├── market_data_repository.py
│   │   ├── ai_explainer.py
│   │   ├── news_provider.py
│   │   └── headline_classifier.py
│   ├── rules/                 # Risk assessment rules
│   │   ├── rule_engine.py
│   │   ├── conservative.py
│   │   ├── balanced.py
│   │   └── aggressive.py
│   ├── value_objects/         # Immutable domain objects
│   │   ├── indicator_snapshot.py
│   │   ├── risk_assessment.py
│   │   └── sentiment.py
│   └── services/              # Domain services
│
├── application/               # Use cases
│   ├── use_case/
│   │   ├── fetch_market_data.py
│   │   ├── compute_sma.py
│   │   ├── compute_ema.py
│   │   ├── compute_rsi.py
│   │   ├── aggregate_indicators.py
│   │   ├── assess_risk.py
│   │   ├── explain_risk.py
│   │   └── fetch_sentiment.py
│   ├── rules/                 # Custom rules DSL
│   │   ├── schema.py
│   │   └── interpreter.py
│   └── dto/                   # Data transfer objects
│
├── infrastructure/            # External implementations
│   ├── data_providers/
│   │   └── yahoo.py           # Yahoo Finance adapter
│   ├── persistence/
│   │   └── sqlite_market_repository.py
│   ├── ai/                    # AI explainers
│   │   ├── factory.py
│   │   ├── claude_explainer.py
│   │   ├── openai_explainer.py
│   │   ├── gemini_explainer.py
│   │   ├── ollama_explainer.py
│   │   └── mock_explainer.py
│   ├── sentiment/             # Sentiment analysis
│   │   ├── factory.py
│   │   ├── google_news_provider.py
│   │   ├── keyword_classifier.py
│   │   └── ai_classifier.py
│   └── config/
│       └── yaml_loader.py     # Custom rules loader
│
└── adapters/                  # User interfaces
    ├── cli/                   # Typer CLI (main interface)
    ├── bot/                   # Telegram, WhatsApp (stubs)
    └── web/                   # REST API (stub)
```

**Key Principle:** Domain logic is pure and framework-agnostic. External systems never leak into the domain.

---

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Claude API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `GOOGLE_API_KEY` | Google/Gemini API key |
| `AI_PROVIDER` | Default AI provider |
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

**Project Stats:** 81 source files, 29 test files

---

## Data Storage

- **Location:** `~/.ai-saham/data.db` (SQLite)
- **Content:** Cached OHLCV candles per ticker
- **Refresh:** Use `--refresh` flag to update

---

## Limitations

- **Daily data only** - No intraday or real-time streaming
- **IDX market focus** - Designed for Indonesia Stock Exchange
- **Yahoo Finance source** - Data may be delayed; unofficial source
- **Internet required** for first fetch and sentiment (offline for cached analysis)

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
