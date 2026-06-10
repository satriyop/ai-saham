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
- **Strategy Packages** - First-class, versionable, portable strategy artifacts
- **Skill Documentation** - Auto-generated SKILL.md with drift detection and project-wide catalog
- **AI Strategy Creator** - Describe strategies in natural language, get complete YAML
- **AI Formula Translator** - Describe indicators in natural language, get formula back
- **AI Explanations** - Get AI-powered insights (Claude, OpenAI, Gemini, Ollama)
- **News Sentiment** - Analyze news headlines with keyword or AI classification
- **Backtesting** - Test strategies on historical data with detailed metrics
- **Broker & Foreign Flow** - Track foreign investor activity from IDX (public, no auth) or Stockbit
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

# Create and use a strategy
saham strategy init momentum
saham backtest BBCA --strategy momentum

# Or create a strategy from natural language
saham strategy create "RSI oversold strategy" --name my_rsi --provider mock

# Fetch foreign flow data (no auth required)
saham broker fetch BBCA --days 30
saham broker flow BBCA
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

Run a deterministic backtest simulation on historical data using a strategy package or rules file.

```bash
# Using strategy packages (recommended)
saham backtest BBCA --strategy momentum
saham backtest BBRI -S momentum --start 2024-01-01
saham backtest TLKM -S ./strategies/my_strat/strategy.yaml --verbose

# Using rules file (backward compatible)
saham backtest BBCA --rules-file config/custom_rules.yaml.example
saham backtest BBRI -r rules.yaml --capital 50000000 --verbose
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--strategy` | `-S` | | Strategy name or path (recommended) |
| `--rules-file` | `-r` | | Path to YAML rules file (alias for --strategy) |
| `--start` | `-s` | | Start date (YYYY-MM-DD) |
| `--end` | `-e` | | End date (YYYY-MM-DD) |
| `--capital` | `-c` | 100000000 | Initial capital in IDR |
| `--verbose` | `-v` | false | Show detailed trade-by-trade output |
| `--db` | | ~/.ai-saham/data.db | Custom database path |

**Strategy Resolution:** When using `--strategy`, names are searched in:
1. `./NAME/strategy.yaml` (current directory)
2. `./strategies/NAME/strategy.yaml` (local strategies)
3. `~/.ai-saham/strategies/NAME/strategy.yaml` (user strategies)

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

Creates:
```
strategies/momentum/
├── strategy.yaml    # Strategy rules (required)
└── README.md        # Documentation
```

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

Use AI to generate a complete strategy from a natural language description.

```bash
saham strategy create "RSI oversold strategy" --name my_rsi
saham strategy create "EMA crossover with 9 and 21" --name ema_cross --provider claude
saham strategy create "momentum strategy" --provider ollama --no-save  # Preview only
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--name` | `-n` | auto-generated | Strategy name |
| `--provider` | `-p` | mock | AI provider (claude/openai/gemini/ollama/mock) |
| `--model` | `-m` | | Model name (for Ollama) |
| `--dir` | `-d` | ./strategies/NAME | Directory to save strategy |
| `--save/--no-save` | | save | Save to file or preview only |

**Supported intents:**
- "RSI oversold strategy" → RSI < 30 → LOW_RISK
- "EMA crossover with 9 and 21 periods" → EMA crossover rules
- "conservative RSI strategy" → Strict thresholds
- "momentum strategy" → RSI + EMA combination

**Unsupported intents** (returns error):
- Specific stock recommendations: "strategy for BBCA"
- Guaranteed outcomes: "strategy that always wins"
- Price predictions: "predict tomorrow's price"

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

**Search Locations:**
- `./strategies/` (local project)
- `~/.ai-saham/strategies/` (user-wide)

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

### AI Strategy Creator

Create complete strategy YAML from natural language descriptions:

```bash
# Create RSI-based strategy
saham strategy create "buy when RSI below 30, sell when RSI above 70" --name rsi_strategy

# Create EMA crossover strategy
saham strategy create "EMA crossover with 9 and 21 periods" --name ema_cross --provider claude

# Preview without saving
saham strategy create "momentum strategy" --no-save
```

The AI generates:
- Complete YAML structure with version, name, description
- Custom indicator definitions (if needed)
- Rules with conditions and rationales
- Signal mapping for backtesting

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
**Price fields** (always available): `OPEN`, `HIGH`, `LOW`, `CLOSE`, `VOLUME`
**Plugin indicators** (if installed): `ATR` and custom plugins
**Supported types:** `RSI`, `SMA`, `EMA`, plus any registered plugins
**Supported operators:** `<`, `<=`, `>`, `>=`, `==`, `!=`

### Compound Conditions & Advanced Syntax

Combine multiple conditions with `all:` (logical AND):

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

Use `right: {value: N}` for indicator-vs-literal in the left/right form:

```yaml
when:
  left:
    indicator: foreign_flow_3d
  operator: ">"
  right:
    value: 50000000000  # 50B IDR
```

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

## Strategy Packages

Strategies are first-class, versionable, portable artifacts. Instead of loose YAML files, organize strategies as packages.

### Package Structure

```
strategies/
└── momentum/
    ├── strategy.yaml   # Required: strategy rules
    ├── README.md       # Optional: documentation
    ├── tests/          # Optional: test cases
    └── examples/       # Optional: example usage
```

### Creating a Strategy

```bash
# Initialize new strategy
saham strategy init momentum

# Customize the rules
vim strategies/momentum/strategy.yaml

# Validate
saham strategy validate momentum

# Use in backtest
saham backtest BBCA --strategy momentum
```

### Strategy Resolution

When you reference a strategy by name (e.g., `--strategy momentum`), it's searched in priority order:

1. **Explicit path** - If contains `/` or ends with `.yaml`
2. **Local directory** - `./momentum/strategy.yaml`
3. **Local strategies** - `./strategies/momentum/strategy.yaml`
4. **User strategies** - `~/.ai-saham/strategies/momentum/strategy.yaml`

### Sharing Strategies

Strategies are self-contained packages that can be:
- Committed to version control
- Shared with team members
- Published as templates
- Tested independently

```bash
# Copy a strategy
cp -r strategies/momentum strategies/momentum-v2

# Share via git
git add strategies/momentum
git commit -m "Add momentum strategy"
```

---

### `saham skill` - Skill Documentation

Auto-generate machine-readable SKILL.md files for strategies, indicators, and formulas. Includes drift detection and a project-wide catalog.

#### Package Structure with Skill Annotation

```
strategies/rsi-momentum/
├── strategy.yaml           # Strategy rules (required)
├── strategy.skill.yaml     # Annotation sidecar (optional)
└── SKILL.md                # Auto-generated documentation
```

#### Commands

```bash
# Auto-generate SKILL.md during validation
saham strategy validate rsi-momentum

# Explicit generation
saham skill generate rsi-momentum                  # Strategy (default)
saham skill generate atr --type indicator           # Indicator plugin
saham skill generate SMOOTH_RSI --type formula      # Formula

# Check for stale documentation
saham skill check

# Rebuild project-wide catalog
saham skill index
```

| Command | Purpose |
|---------|---------|
| `saham skill generate NAME` | Generate SKILL.md for an artifact |
| `saham skill check` | Report stale/missing SKILL.md files |
| `saham skill index` | Rebuild SKILLS_INDEX.md catalog |

**Annotation sidecar** (`strategy.skill.yaml`) provides human context:

```yaml
description: "One-paragraph description"
when_to_use: "Market conditions where this applies"
tags: [momentum, rsi]
limitations: ["Known limitation"]
examples: ["Example usage"]
```

See [CLI_README.md](CLI_README.md) for detailed skill documentation guide.

---

## Broker Data & Foreign Flow

Track foreign investor activity on IDX stocks. Two data providers available:

| Provider | Auth | Data Provided |
|----------|------|---------------|
| **`idx`** (default) | None | Foreign buy/sell lots, estimated values, total volume |
| **`stockbit`** | JWT token | Exact foreign values + top broker breakdown |

```bash
# Fetch foreign flow (IDX - no auth needed)
saham broker fetch BBCA --days 30

# Or use Stockbit for broker-level detail
saham broker auth "your-stockbit-token"
saham broker fetch BBCA --provider stockbit

# View foreign flow summary
saham broker flow BBCA --days 20

# Check top brokers (requires Stockbit data)
saham broker top BBCA

# Import from CSV
saham broker import data.csv --preview

# Check provider status
saham broker status
```

See [CLI_README.md](CLI_README.md) for detailed broker data documentation.

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
│   │   ├── skill_annotation.py
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
│   │   ├── create_indicator_from_intent.py  # AI formula translation
│   │   └── create_strategy_from_intent.py   # AI strategy generation
│   ├── formula/               # Formula DSL engine
│   │   ├── tokenizer.py       # Lexical analysis
│   │   ├── parser.py          # Recursive descent parser
│   │   ├── ast_nodes.py       # Immutable AST types
│   │   ├── validator.py       # Semantic validation
│   │   └── evaluator.py       # AST evaluation
│   ├── services/
│   │   ├── indicator_registry.py  # Centralized indicator management
│   │   ├── strategy_loader.py     # Strategy package resolution
│   │   └── skill_generator.py     # SKILL.md generation orchestrator
│   ├── ports/
│   │   ├── formula_translator.py  # AI formula translator interface
│   │   ├── strategy_translator.py # AI strategy translator interface
│   │   └── skill_writer.py        # Skill documentation writer interface
│   ├── rules/                 # Custom rules DSL
│   │   ├── schema.py          # Includes formula support
│   │   └── interpreter.py
│   └── dto/                   # Data transfer objects
│
├── infrastructure/            # External implementations
│   ├── data_providers/
│   │   ├── yahoo.py           # Yahoo Finance adapter
│   │   ├── idx.py             # IDX broker data (public API, no auth)
│   │   └── stockbit.py        # Stockbit broker data (JWT auth)
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
│   │   ├── strategy_translator.py      # AI strategy generation
│   │   ├── strategy_translator_prompt.py
│   │   └── mock_explainer.py
│   ├── sentiment/             # Sentiment analysis
│   │   ├── factory.py
│   │   ├── google_news_provider.py
│   │   ├── keyword_classifier.py
│   │   └── ai_classifier.py
│   ├── plugins/               # Plugin discovery
│   │   └── loader.py          # Auto-loads from plugins/
│   ├── skill/                 # Skill documentation system
│   │   ├── annotation_reader.py  # Reads .skill.yaml sidecars
│   │   ├── markdown_writer.py    # Generates SKILL.md
│   │   ├── rules_hasher.py       # Drift detection via hash
│   │   └── index_writer.py       # Generates SKILLS_INDEX.md
│   └── config/
│       └── yaml_loader.py     # Custom rules loader
│
├── adapters/                  # User interfaces
│   ├── cli/                   # Typer CLI (main interface)
│   │   ├── main.py            # Main CLI entry point
│   │   ├── broker_commands.py    # Broker data & foreign flow
│   │   ├── strategy_commands.py  # Strategy management commands
│   │   └── skill_commands.py     # Skill documentation commands
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
