# AI Saham - Stock Analysis CLI

[![CI](https://github.com/anthropics/ai-saham/actions/workflows/ci.yml/badge.svg)](https://github.com/anthropics/ai-saham/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A **local-first, production-grade CLI application** for stock analysis focused on the Indonesia Stock Exchange (IDX).

## Features

- **Technical Indicators** - SMA, EMA, RSI, ATR with professional-grade calculations
- **Formula DSL** - Compose indicators with expressions like `SMA(RSI(14), 10)`
- **Plugin System** - Extend with custom indicators (ATR included as example)
- **Risk Assessment** - Three built-in profiles (conservative, balanced, aggressive)
- **Custom Rules DSL** - Define your own rules via YAML configuration
- **AI Formula Translator** - Describe indicators in natural language, get formula back
- **AI Explanations** - Get AI-powered insights (Claude, OpenAI, Gemini, Ollama)
- **News Sentiment** - Analyze news headlines with keyword or AI classification
- **Backtesting** - Test strategies on historical data with detailed metrics
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

### `saham backtest` - Strategy Backtesting

Run a deterministic backtest simulation on historical data using custom rules.

```bash
saham backtest BBCA --rules-file config/custom_rules.yaml.example
saham backtest BBRI -r rules.yaml --start 2024-01-01
saham backtest TLKM -r rules.yaml --capital 50000000 --verbose
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--rules-file` | `-r` | (required) | Path to YAML rules file |
| `--start` | `-s` | | Start date (YYYY-MM-DD) |
| `--end` | `-e` | | End date (YYYY-MM-DD) |
| `--capital` | `-c` | 100000000 | Initial capital in IDR |
| `--verbose` | `-v` | false | Show detailed trade-by-trade output |
| `--db` | | ~/.ai-saham/data.db | Custom database path |

**Signal Mapping (customizable in YAML):**

| Risk Level | Trade Action | Description |
|------------|--------------|-------------|
| `LOW_RISK` | `ENTER_LONG` | Buy signal |
| `MODERATE` | `HOLD` | Maintain position |
| `HIGH_RISK` | `EXIT_LONG` | Sell signal |

**Metrics Reported:**
- Total Return (%)
- Max Drawdown (%)
- Trade Count
- Win Rate (%)
- Profit Factor
- Winning/Losing Trades
- Average Win/Loss

**Note:** Requires cached data. Run `saham fetch TICKER` first.

---

### `saham version` - Version Info

```bash
saham version
```

---

## AI Features

### AI Providers

For `--explain`, `--ai-classify`, and formula translation:

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

### AI Formula Translator

Translate natural language descriptions into formula expressions:

```python
from src.application.use_case.create_indicator_from_intent import (
    CreateIndicatorFromIntentRequest,
    CreateIndicatorFromIntentUseCase,
)
from src.infrastructure.ai import FormulaTranslatorFactory

# Create translator
translator = FormulaTranslatorFactory.create(provider="claude")
use_case = CreateIndicatorFromIntentUseCase(translator=translator)

# Translate intent to formula
response = use_case.execute(
    CreateIndicatorFromIntentRequest(
        intent="smoothed RSI with 14-period RSI and 10-day smoothing",
        indicator_name="smooth_rsi"
    )
)

print(response.formula)  # "SMA(RSI(14), 10)"
```

**Supported intents:**
- "smoothed RSI with 14-period and 10-day smoothing" → `SMA(RSI(14), 10)`
- "MACD line using 12 and 26 period EMAs" → `EMA(CLOSE, 12) - EMA(CLOSE, 26)`
- "average true range over 14 days" → `ATR(14)`

**Unsupported intents** (returns `UNSUPPORTED`):
- Trading advice: "should I buy BBCA?"
- Predictions: "will the price go up?"
- Non-indicator requests: "explain RSI"

---

## Plugin System

Extend the indicator library with custom plugins.

### Using Plugins

Plugins are auto-discovered from `plugins/` directory:

```bash
plugins/
└── atr_plugin.py     # ATR indicator (included)
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
**Plugin indicators** (if installed): `ATR` and custom plugins
**Supported types:** `RSI`, `SMA`, `EMA`, plus any registered plugins
**Supported operators:** `<`, `<=`, `>`, `>=`, `==`, `!=`

### Formula-Based Indicators

Define composite indicators using mathematical expressions:

```yaml
version: 1
name: "formula_strategy"
default_outcome: MODERATE

indicators:
  # Smoothed RSI - applies 10-period SMA to RSI(14)
  smooth_rsi:
    formula: "SMA(RSI(14), 10)"

  # MACD line - difference of two EMAs
  macd_line:
    formula: "EMA(CLOSE, 12) - EMA(CLOSE, 26)"

  # Price distance from SMA as percentage
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

### Signal Mapping (for Backtests)

Customize how risk levels map to trade actions:

```yaml
version: 1
name: "my_backtest_strategy"
default_outcome: MODERATE

# Custom signal mapping (optional, defaults shown)
signal_mapping:
  low_risk: ENTER_LONG    # Buy signal
  moderate: HOLD          # Maintain position
  high_risk: EXIT_LONG    # Sell signal

rules:
  # ... your rules here
```

**Available Trade Actions:** `ENTER_LONG`, `EXIT_LONG`, `HOLD`, `FLAT`

---

## Architecture

```
src/
├── domain/                    # Pure business logic (no dependencies)
│   ├── entities/              # Stock, Candle, BacktestTrade
│   ├── indicators/            # SMA, EMA, RSI calculations
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
│   │   ├── backtest_result.py
│   │   ├── trade_action.py
│   │   └── sentiment.py
│   └── services/              # Domain services
│       └── backtest_engine.py # Backtest simulation engine
│
├── application/               # Use cases & application services
│   ├── use_case/
│   │   ├── fetch_market_data.py
│   │   ├── compute_sma.py
│   │   ├── compute_ema.py
│   │   ├── compute_rsi.py
│   │   ├── aggregate_indicators.py
│   │   ├── assess_risk.py
│   │   ├── explain_risk.py
│   │   ├── fetch_sentiment.py
│   │   ├── backtest.py
│   │   └── create_indicator_from_intent.py  # AI formula translation
│   ├── formula/               # Formula DSL engine
│   │   ├── tokenizer.py       # Lexical analysis
│   │   ├── parser.py          # Recursive descent parser
│   │   ├── ast_nodes.py       # Immutable AST types
│   │   ├── validator.py       # Semantic validation
│   │   └── evaluator.py       # AST evaluation
│   ├── services/
│   │   └── indicator_registry.py  # Centralized indicator management
│   ├── ports/
│   │   └── formula_translator.py  # AI translator interface
│   ├── rules/                 # Custom rules DSL
│   │   ├── schema.py          # Includes formula support
│   │   └── interpreter.py
│   └── dto/                   # Data transfer objects
│
├── infrastructure/            # External implementations
│   ├── data_providers/
│   │   └── yahoo.py           # Yahoo Finance adapter
│   ├── persistence/
│   │   └── sqlite_market_repository.py
│   ├── ai/                    # AI adapters
│   │   ├── factory.py
│   │   ├── claude_explainer.py
│   │   ├── openai_explainer.py
│   │   ├── gemini_explainer.py
│   │   ├── ollama_explainer.py
│   │   ├── formula_translator.py       # AI formula translation
│   │   ├── formula_translator_prompt.py
│   │   └── mock_explainer.py
│   ├── sentiment/             # Sentiment analysis
│   │   ├── factory.py
│   │   ├── google_news_provider.py
│   │   ├── keyword_classifier.py
│   │   └── ai_classifier.py
│   ├── plugins/               # Plugin discovery
│   │   └── loader.py          # Auto-loads from plugins/
│   └── config/
│       └── yaml_loader.py     # Custom rules loader
│
├── adapters/                  # User interfaces
│   ├── cli/                   # Typer CLI (main interface)
│   ├── bot/                   # Telegram, WhatsApp (stubs)
│   └── web/                   # REST API (stub)
│
└── plugins/                   # User plugins directory
    └── atr_plugin.py          # ATR indicator (example)
```

**Key Principles:**
- Domain logic is pure and framework-agnostic
- External systems never leak into the domain
- AI is always optional and swappable
- Plugins extend functionality without modifying core

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

**Project Stats:** 87 source files, 32 test files

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
