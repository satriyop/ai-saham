# Architecture Overview

AI Saham follows **Hexagonal Architecture** (also known as Ports & Adapters) to ensure clean separation of concerns and long-term maintainability.

---

## Core Principle

> Domain logic is pure and framework-agnostic. External systems never leak into the domain.

The architecture enforces a strict dependency rule: **inner layers know nothing about outer layers**.

---

## Layer Diagram

```
                    +---------------------------------------+
                    |             Adapters                  |
                     |  CLI (35+ modules) | Bot | Web (stub)  |
                    +---------------------------------------+
                                   |
                                   v
                    +---------------------------------------+
                    |             Application               |
                    |  use_case/ (22)  |  services/ (11)    |
                    |  ports/ (4)      |  formula/ (5)      |
                    |  rules/ (3)      |  dto/              |
                    +---------------------------------------+
                                   |
                                   v
                    +---------------------------------------+
                    |               Domain                  |
                    |  entities/ (6)  |  value_objects/ (11)|
                    |  indicators/ (5)|  services/ (2)      |
                    |  ports/ (13)    |  rules/ (5)         |
                    +---------------------------------------+
                                   ^
                                   |
                    +---------------------------------------+
                    |           Infrastructure              |
                     |  data_providers/ (Yahoo, IDX)          |
                     |  browser/ (19 Stockbit providers)     |
                     |  persistence/ (SQLite + CSV + JSONL)  |
                     |  ai/ (6 providers + translators)      |
                     |  sentiment/ (3 providers + 2 classif) |
                    |  config/ | csv/ | plugins/ | skill/   |
                    +---------------------------------------+
```

---

## Layer Responsibilities

### Domain Layer (`src/domain/`)

The innermost layer contains pure business logic with **zero external dependencies** (stdlib only: `dataclasses`, `Decimal`, `date`, `Enum`).

| Directory | Responsibility | Key Files |
|-----------|----------------|-----------|
| `entities/` | Core business objects | `Candle`, `BacktestTrade`, `BrokerTransaction`, `BrokerSummary` |
| `value_objects/` | Immutable value types | `IndicatorSnapshot`, `RiskAssessment`, `RiskSignal`, `BacktestResult`, `TradeAction`, `ScreenerResult`, `Sentiment` |
| `indicators/` | Pure indicator calculations | `sma.py`, `ema.py`, `rsi.py` (pure functions over lists of floats) |
| `services/` | Domain orchestration without I/O | `analyze_stock.py`, `backtest_engine.py` |
| `ports/` | Interfaces for external systems | `MarketDataProvider`, `BrokerDataProvider`, `BrowserDataProvider`, `AIExplainer`, `NewsProvider`, `HeadlineClassifier`, `MarketDataRepository`, `BrokerDataRepository`, `SentimentRepository`, `AccumulationJournalStore`, `CsvBrokerParser` |
| `rules/` | Risk assessment profiles | Conservative, Balanced, Aggressive profiles + `RuleEngine` |

**Key rule:** Domain code must be testable without any infrastructure.

### Application Layer (`src/application/`)

Orchestrates domain logic to fulfill user requests. All I/O is abstracted behind domain ports.

| Directory | Responsibility | Key Files |
|-----------|----------------|-----------|
| `use_case/` | Business operations (22 use cases) | `FetchMarketData`, `ComputeSMA/EMA/RSI`, `AssessRisk`, `ExplainRisk`, `Backtest`, `SwingBacktest`, `MarketRegime`, `PreOpenScreen`, `FetchSentiment`, `AuditSentiment`, `FetchBrokerData`, `AccumulationScreen`, `AccumulationAudit`, `CreateIndicatorFromIntent`, `CreateStrategyFromIntent`, etc. |
| `services/` | Cross-cutting application logic | `indicator_registry.py`, `strategy_loader.py`, `universe_loader.py`, `position_sizer.py`, `skill_generator.py`, `intraday_confirmation_journal.py`, `accumulation_journal.py`, `bootstrap.py` |
| `ports/` | Application-level interfaces | `formula_translator.py`, `strategy_translator.py`, `indicator_plugin.py`, `skill_writer.py` |
| `formula/` | Formula DSL engine | `ast_nodes.py`, `tokenizer.py`, `parser.py`, `evaluator.py`, `validator.py` |
| `rules/` | Formula-based rule system | `schema.py`, `interpreter.py`, `exceptions.py` |
| `dto/` | Data transfer objects | `AnalysisRequest`, `IndicatorSnapshot` |

**Key rule:** Use cases depend only on domain ports, never on concrete implementations.

### Infrastructure Layer (`src/infrastructure/`)

Implements domain and application ports with concrete external systems.

| Directory | Responsibility | Key Files |
|-----------|----------------|-----------|
| `data_providers/` | Market data fetching | `yahoo.py` (Yahoo Finance), `yahoo_stock_meta.py` (stock metadata), `idx.py` + `idx_market.py` (IDX public API) |
| `persistence/` | Data storage | `sqlite_market_repository.py`, `sqlite_broker_repository.py`, `sentiment_repository.py`, `formula_storage.py`, CSV journal writers |
| `ai/` | AI adapters | 6 explainers (`deepseek_explainer`, `claude_explainer`, `openai_explainer`, `gemini_explainer`, `ollama_explainer`, `mock_explainer`) + `factory.py`, `formula_translator.py`, `strategy_translator.py`, `sentiment_analyzer.py` |
| `sentiment/` | News pipeline | `google_news_provider.py`, `cnbc_indonesia_provider.py`, `kontan_provider.py`, `composite_provider.py`, `keyword_classifier.py`, `ai_classifier.py`, `factory.py`, `deduplication.py` |
| `browser/` | Stockbit providers (22 files) | `playwright_stockbit.py` (broker provider, delegates to browser module), `playwright_stockbit_browser.py` (browser lifecycle + session management), `stockbit_browser.py`, `stockbit_analyst.py`, `stockbit_bandar.py`, `stockbit_broker_distribution.py`, `stockbit_company_profile.py`, `stockbit_corp_action.py`, `stockbit_earnings.py`, `stockbit_forward_estimates.py`, `stockbit_fundamentals.py`, `stockbit_insider.py`, `stockbit_market_time.py`, `stockbit_order_book.py`, `stockbit_running_trade.py`, `stockbit_running_trade_chart.py`, `stockbit_seasonality.py`, `stockbit_shareholding.py`, `stockbit_ticker_notation.py`, `stockbit_universe.py`, `stockbit_valuation.py` |
| `config/` | Configuration loading | `yaml_loader.py` |
| `csv/` | CSV import pipeline | `format_detector.py`, `mapping_loader.py`, `broker_csv_adapter.py` |
| `plugins/` | Plugin indicator loader | `indicator_loader.py` |
| `skill/` | Self-documentation system | `annotation_reader.py`, `index_writer.py`, `markdown_writer.py`, `rules_hasher.py` |

**Key rule:** Infrastructure implements domain interfaces, never the reverse.

### Adapter Layer (`src/adapters/`)

Entry points for user interaction. Thin — no business logic, only wiring.

| Directory | Responsibility | Key Files |
|-----------|----------------|-----------|
| `cli/` | Typer-based CLI (40+ modules) | `main.py`, `fetch_commands.py`, `fetch_market_commands.py`, `fetch_iev_commands.py`, `fetch_universe_commands.py`, `fetch_status_commands.py`, `fetch_audit_commands.py`, `fetch_stockbit_commands.py`, `fetch_broker_commands.py`, `fetch_broker_display.py`, `view_commands.py`, `view_ticker_display.py`, `view_universe_display.py`, `view_broker_commands.py`, `view_broker_display.py`, `learn_commands.py`, `today_commands.py`, `screen_lifecycle_commands.py`, `screen_pre_open_commands.py`, `screen_pre_open_display.py`, `screen_accum_commands.py`, `screen_accum_display.py`, `analyze_commands.py`, `analyze_swing_commands.py`, `analyze_swing_display.py`, `analyze_swing_broker_display.py`, `analyze_chart_commands.py`, `analyze_sentiment_commands.py`, `analyze_regime_commands.py`, `analyze_regime_display.py`, `analyze_accum_commands.py`, `analyze_accum_display.py`, `trade_commands.py`, `trade_intraday_commands.py`, `trade_intraday_display.py`, `trade_intraday_backtest_display.py`, `trade_swing_commands.py`, `trade_swing_display.py`, `trade_swing_size_display.py`, `trade_accum_commands.py`, `trade_accum_display.py`, `strategy_commands.py`, `strategy_skill_commands.py`, plus shared modules (`rich_display.py`, ...) |
| `bot/` | Chat bot stubs | `telegram.py`, `whatsapp.py` (docstrings only) |
| `web/` | REST API stub | `api.py` (docstring only) |

**Key rule:** Adapters wire up dependencies and translate user input to use case requests.

---

## Dependency Rules

1. **Domain depends on nothing** - Pure Python, no external libraries
2. **Application depends on Domain** - Use cases use domain entities and ports
3. **Infrastructure depends on Domain** - Implements domain ports
4. **Adapters depend on all** - Wires everything together

**Forbidden dependencies:**
- Domain -> Infrastructure (use ports instead)
- Domain -> Adapters (domain doesn't know about CLI)
- Infrastructure -> Adapters (infrastructure is independent)

---

## Data Flow Examples

### Fetch Market Data

```
CLI Adapter            Application              Domain                Infrastructure
-----------            -----------              ------                --------------
fetch BBCA
     |
     v
  Create request
     |
     +------------> FetchMarketDataUseCase
                          |
                          v
                    provider.fetch()
                          |
                          +--------------------------------> YahooFinanceProvider
                          |                                        |
                          |                                        v
                          |                                 HTTP request
                          |                                        |
                          v                                        |
                    repository.save() <------------+---------------+
                          |                        |
                          +----------------------->|
                          |                        v
                          |                 SQLiteRepository
                          v
                    Return response
                          |
     <-------------------+
     |
  Display results
```

### Broker Data Flow (Foreign Accumulation)

```
CLI Adapter            Application              Domain                Infrastructure
-----------            -----------              ------                --------------
saham fetch broker BBCA
     |
     v
  Create request
     |
      +------------> FetchBrokerDataUseCase
      |                   |
      |                   v
      |             broker_provider.fetch()
      |                   |
      |                   +--------------------------------> IDXProvider
      |                   |
      |                   v
      |             broker_repository.save()
      |                   |
      |                   v
      |             Return BrokerSummary[]
      |
saham fetch broker BBCA --provider stockbit
      |
      v
  Create request
     |
      +------------> FetchBrokerDailyFlowsUseCase
                          |
                          v
                    broker_provider.fetch_broker_daily_flows()
                          |
                          +--------------------------------> StockbitPlaywrightBrokerProvider
                          |                                        |
                          |                                        v
                          |                                 Playwright HTTP
                          |                                        |
                          v                                        |
                    broker_repository.save_broker_daily_flows()
                          |
                          v
                    Return foreign flow time-series[]
                          |
     <-------------------+
     |
  Display per-broker daily detail tables
```

### Sentiment Analysis Pipeline

```
CLI Adapter            Application              Domain                Infrastructure
-----------            -----------              ------                --------------
saham analyze sentiment BBCA
     |
     v
  Create request
     |
     +------------> FetchSentimentUseCase
                          |
                          v
                    news_provider.fetch()
                          |
                          +--------------------------------> CompositeNewsProvider
                          |                                        |
                          |                                   +---> GoogleNewsProvider
                          |                                   +---> CNBCIndonesiaProvider
                          |                                   +---> KontanProvider
                          |                                        |
                          |                                        v
                          v                                   NewsArticle[]
                    classifier.classify()
                          |
                          +--------------------------------> KeywordClassifier
                          |                                        |
                          |                          (optionally AI classifier)
                          v
                    sentiment_repository.save()
                          |
                          v
                    Return SentimentSummary
                          |
     <-------------------+
     |
  Display sentiment
```

### Natural Language → Formula Translation

```
CLI Adapter            Application              Domain                Infrastructure
-----------            -----------              ------                --------------
saham indicator create
     |
     v
  Create request
     |
     +------------> CreateIndicatorFromIntentUseCase
                          |
                          v
                    translator.translate(intent)
                          |
                          +--------------------------------> AI FormulaTranslator
                          |                                        |
                          |                                        v
                          |                                 (DeepSeek/Claude/Ollama)
                          |                                        |
                          v                                        |
                    formula_validator.validate()
                          |                                   Return formula string
                          v
                    formula_storage.save()
                          |
                          v
                    Return formula + explanation
                          |
     <-------------------+
     |
  Display formula
```

### Backtest Flow

```
CLI Adapter            Application              Domain                Infrastructure
-----------            -----------              ------                --------------
saham strategy backtest BBCA
     |
     v
  Create request
     |
     +------------> BacktestUseCase
                          |
                          v
                    market_repo.fetch_candles()
                          |
                          +--------------------------------> SQLiteMarketRepository
                          |                                        |
                          v                                        |
                    strategy_loader.load()
                          |
                          +--------------------------------> StrategyLoader
                          |                                        |
                          v                                        |
                    backtest_engine.run()
                          |                                   (pure domain service)
                          v
                    Return BacktestResult
                          |
     <-------------------+
     |
  Display trade log + metrics
```

---

## Testing Strategy

| Layer | Test Type | Count | Dependencies |
|-------|-----------|-------|--------------|
| Domain | Unit tests | ~30 | None (pure functions) |
| Application | Integration tests | ~25 | Mock ports |
| Infrastructure | Integration tests | ~25 | Real external systems (or fixtures) |
| Adapters | E2E tests | ~14 | Full system |

**Test location:** All tests in `tests/`, organized by layer.

**Key principle:** Domain tests never require network, database, or API keys. Infrastructure tests use fixtures or controlled environments.

---

## AI Provider Architecture

AI Saham supports 6 providers through a unified `AIExplainer` interface.

```
                    +------------------+
                    |  AIExplainer     |  (domain port)
                    +------------------+
                           ^
                  ________ | ________
                 /     |     |     |    \
                /      |     |     |     \
        +---------+ +------+ +----+ +----------+
        | DeepSeek| |Claude| |GPT | | Gemini   |
        +---------+ +------+ +----+ +----------+
        | Ollama  | | Mock |
        +---------+ +------+

    Factory.create(provider="deepseek")  -> DeepSeekExplainer
```

**Default provider:** `deepseek` (requires `DEEPSEEK_API_KEY` env var).

Additional AI translators beyond the explainer interface:
- `FormulaTranslator` — converts natural language to formula DSL
- `StrategyTranslator` — converts natural language to strategy YAML
- `SentimentAnalyzer` — AI-powered headline classification

---

## Plugin System for Indicators

Custom indicators can be registered via the plugin system:

```
src/
  plugins/
    my_indicator.py    <-- implements IndicatorPlugin port
    my_indicator.skill.yaml  <-- optional skill annotation
```

Plugins are auto-discovered at startup by `IndicatorLoader` and registered in the `IndicatorRegistry`, making them available to all analysis commands and the formula engine.

---

## Adding New Features

### New Indicator Provider

1. Define domain entity if needed (e.g., new indicator type in `domain/entities/`)
2. Implement indicator as pure function in `domain/indicators/`
3. (Optional) Expose via plugin in `infrastructure/plugins/`
4. Add formula function to `application/formula/evaluator.py`
5. Add CLI command or integrate into existing commands

### New News Provider

1. Implement `NewsProvider` protocol from `domain/ports/news_provider.py`
2. Add provider file in `infrastructure/sentiment/`
3. Register in `CompositeNewsProvider`

### New AI Provider

1. Implement `AIExplainer` from `domain/ports/ai_explainer.py`
2. Add provider file in `infrastructure/ai/`
3. Register in `infrastructure/ai/factory.py`

### New CLI Command

1. Add function in appropriate `adapters/cli/*_commands.py`
2. Use typer with dependency injection pattern
3. Create use case in `application/use_case/` if new business logic needed

Always start from the domain and work outward.
