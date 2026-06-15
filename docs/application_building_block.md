# Application Building Blocks

This document maps every component of AI Saham into a three-tier hierarchy: **Big** (subsystems), **Medium** (modules), and **Small** (individual components). Use this as a reference to understand how pieces connect and where to make changes.

---

## Layer Architecture (Hexagonal)

```
                    +---------------------------------------+
                    |             Adapters  (11 modules)    |
                    |  CLI | Bot (stub) | Web (stub)        |
                    +---------------------------------------+
                                    |
                                    v
                    +---------------------------------------+
                    |        Application Layer              |
                    |  22 use cases | 11 services | 4 ports |
                    |  Formula DSL (6 files) | Rules (3)    |
                    |  DTOs (2)                              |
                    +---------------------------------------+
                                    |
                                    v
                    +---------------------------------------+
                    |         Domain Layer (Pure Python)    |
                    |  5 entities | 11 value objects        |
                    |  5 indicators | 2 services (1 stub)   |
                    |  13 ports | 5 rules                    |
                    +---------------------------------------+
                                    ^
                                    |
                    +---------------------------------------+
                    |      Infrastructure Layer             |
                    |  4 data providers | 8 persistence     |
                    |  15 AI files | 8 sentiment            |
                    |  2 browser | 3 config/csv             |
                    |  1 plugin loader | 4 skill            |
                    +---------------------------------------+
```

---

### Internal Layer Breakdown

The same layers with their actual components visible:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CLI LAYER (17 modules)                       │
│  main.py (groups)                                                   │
│  data_commands.py (update, broker, stockbit, universe)              │
│  indicator_commands.py (compute, snapshot, create, list)            │
│  analyze_commands.py (risk, compare, sentiment, audit, regime)      │
│  trade_commands.py (swing, intraday)                                │
│  strategy_commands.py (init, create, backtest, list)                │
│  skill_commands.py (generate, index, check)                         │
│  + implementation files (accumulation, broker, chart, screen, etc)  │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│                     APPLICATION LAYER                               │
│  ┌─────────────────┐  ┌──────────────────┐  ┌───────────────────┐   │
│  │  22 Use Cases   │  │  11 Services     │  │  Formula Engine   │   │
│  │                 │  │                  │  │  Tokenizer Parser │   │
│  │ FetchMarketData │  │ IndicatorRegistry│  │  Evaluator Valid. │   │
│  │ AssessRisk      │  │ UniverseLoader   │  └───────────────────┘   │
│  │ Backtest        │  │ StrategyLoader   │  ┌───────────────────┐   │
│  │ SwingBacktest   │  │ PositionSizer    │  │  Rule Engine      │   │
│  │ MarketRegime    │  │ SkillGenerator   │  │  Schema Interp.   │   │
│  │ PreOpenScreen   │  │ PaperJournal     │  └───────────────────┘   │
│  │ FetchSentiment  │  │ Bootstrap        │  ┌───────────────────┐   │
│  │ CreateIndicator │  │ GroupMapping     │  │  4 App Ports      │   │
│  │ ... (22 total)  │  │ ...              │  │ FormulaTranslator │   │
│  └─────────────────┘  └──────────────────┘  │ StrategyTranslator│   │
│                                             │ IndicatorPlugin   │   │
│                                             │ SkillWriter       │   │
│                                             └───────────────────┘   │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│                       DOMAIN LAYER (Pure Python)                    │
│  ┌────────────-──┐  ┌────────────────────┐  ┌──────────────────┐    │
│  │  Entities     │  │  Value Objects     │  │  13 Ports        │    │
│  │  Candle       │  │  RiskAssessment    │  │  MarketDataProv. │    │
│  │  BacktestTrade│  │  RiskSignal        │  │  BrokerDataProv. │    │
│  │  BrokerSumm.  │  │  IndicatorSnapshot │  │  AIExplainer     │    │
│  │  BrokerTrans. │  │  JournalEntry      │  │  NewsProvider    │    │
│  │               │  │  BacktestResult    │  │  HeadlineClassif │    │
│  │               │  │  TradeAction       │  │  SentimentRepo   │    │
│  │               │  │  ScreenerResult    │  │  JournalStore    │    │
│  │               │  │  Sentiment         │  │  CsvBrokerParser │    │
│  │               │  │  SkillAnnotation   │  │  ...             │    │
│  └──────────────-┘  └────────────────────┘  └──────────────────┘    │
│  ┌──────────────-┐  ┌────────────────────┐  ┌──────────────────┐    │
│  │  Indicators   │  │  Services          │  │  Rules           │    │
│  │  sma.py       │  │  analyze_stock     │  │  BaseRule        │    │
│  │  ema.py       │  │  backtest_engine   │  │  Conservative    │    │
│  │  rsi.py       │  │                    │  │  Balanced        │    │
│  │  (2 stubs)    │  │  (1 stub)          │  │  Aggressive      │    │
│  └──────────────-┘  └────────────────────┘  │  RuleEngine      │    │
│                                             └──────────────────┘    │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│                    INFRASTRUCTURE LAYER                             │
│  ┌──────────────────┐  ┌───────────────────┐  ┌────────────────┐    │
│  │ Data Providers   │  │ Persistence       │  │ AI Adapters    │    │
│  │ YahooFinance     │  │ SQLiteMarketRepo  │  │ DeepSeek       │    │
│  │ IdxMarketData    │  │ SQLiteBrokerRepo  │  │ Claude         │    │
│  │ IdxBrokerData    │  │ SentimentRepo     │  │ OpenAI         │    │
│  │ StockbitBroker   │  │ FormulaStorage    │  │ Gemini         │    │
│  │                  │  │ CSV JournalWriter │  │ Ollama         │    │
│  │                  │  │ AccumJournalWriter│  │ Mock           │    │
│  └──────────────────┘  └───────────────────┘  │ + Factory      │    │
│  ┌──────────────────┐  ┌───────────────────┐  └────────────────┘    │
│  │ Sentiment        │  │ Browser           │  ┌────────────────┐    │
│  │ GoogleNews       │  │ PlaywrightStockbit│  │ AI Translators │    │
│  │ CNBC Indonesia   │  │ StockbitBrowser   │  │ FormulaTrans.  │    │
│  │ Kontan           │  └───────────────────┘  │ StrategyTrans. │    │
│  │ CompositeProv.   │  ┌───────────────────┐  │ SentimentAnal. │    │
│  │ KeywordClassif.  │  │ CSV Pipeline      │  └────────────────┘    │
│  │ AIClassifier     │  │ FormatDetector    │  ┌────────────────┐    │
│  │ Deduplication    │  │ MappingLoader     │  │ Config/Skill   │    │
│  └──────────────────┘  │ BrokerCsvAdapter  │  │ YAMLLoader     │    │
│                        └───────────────────┘  │ AnnotationRead │    │
│                        ┌───────────────────┐  │ IndexWriter    │    │
│                        │ Plugin Loader     │  │ MarkdownWriter │    │
│                        │ IndicatorLoader   │  │ RulesHasher    │    │
│                        └───────────────────┘  └────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Building Block Tiers

### 🏛️ BIG — Subsystems (10)

| # | Subsystem | Purpose | Entry Points | Key Files |
|---|-----------|---------|--------------|-----------|
| 1 | **CLI Router** | Routes user commands to use cases via nested groups. Parses flags, wires dependencies, displays output. | `saham <group> <cmd>` | `main.py`, `data_commands.py`, `trade_commands.py`, etc (17 files) |
| 2 | **Data Ingestion** | Fetches, caches, and serves OHLCV + broker + news data from external sources. | `fetch`, `data update`, `data broker fetch`, `analyze sentiment` | `yahoo.py`, `idx_market.py`, `idx.py`, `stockbit.py`, 6 sentiment providers, SQLite repos |
| 3 | **Analysis Core** | Deterministic indicator computation, risk profiling, and composite analysis. | `sma`, `ema`, `rsi`, `indicator compute`, `analyze risk`, `indicator snapshot`, `analyze compare` | `sma.py`, `ema.py`, `rsi.py`, `indicator_registry.py`, 3 rule profiles, `rule_engine.py` |
| 4 | **Screening Suite** | Multi-dimensional stock screening for accumulation patterns, pre-open movers, and swing candidates. | `trade swing screen`, `trade intraday pre-open` | `accumulation_screen.py`, `screen_commands.py`, `pre_open_screen.py` |
| 5 | **Strategy System** | Authoring, validation, loading, and execution of versioned strategy packages. | `strategy init/create/validate/list`, `strategy backtest` | `strategy_loader.py`, 3 strategy YAMLs, `strategy_commands.py` |
| 6 | **Formula DSL** | Custom indicator language with tokenizer, parser, evaluator, and validator. Supports nesting and series operations. | `indicator create`, `show-formula`, `indicator compute <formula>` | 6 files in `application/formula/`, `formula_storage.py` |
| 7 | **AI Integration** | 6 AI providers for explanation, formula translation, strategy creation, and sentiment classification. | `--explain`, `--ai-classify`, `indicator create`, `strategy create` | `factory.py`, 6 explainers, 2 translators, `sentiment_analyzer.py` |
| 8 | **Backtest Engine** | Signal generation from rules/strategies and portfolio simulation (single + walk-forward). | `strategy backtest`, `trade swing backtest` | `backtest_engine.py` (domain), `swing_backtest.py` (app), `backtest.py` (use case) |
| 9 | **Trading Workflow** | End-to-end trade lifecycle: pre-open screen → confirm at auction → journal → review → outcome. | `trade intraday *`, `trade swing analyze`, `trade swing size` | `screen_commands.py` (1532 lines), `position_sizer.py`, 3 journal services |
| 10 | **Persistence** | All data storage: SQLite (market, broker, sentiment), CSV journals, YAML config, formula storage. | All commands via `--db`, `--formulas-file`, `--journal` | 3 SQLite repos, 3 CSV writers, `formula_storage.py`, `yaml_loader.py` |

---

### 🧱 MEDIUM — Modules (25+)

Each Big block decomposes into Medium modules:

#### Data Ingestion

| Module | File(s) | Lines | What It Does |
|--------|---------|-------|-------------|
| Yahoo Finance Provider | `infrastructure/data_providers/yahoo.py` | ~80 | OHLCV via yfinance, auto-appends `.JK` |
| IDX Market Provider | `infrastructure/data_providers/idx_market.py` | ~120 | OHLCV via IDX TradingSummary API |
| IDX Broker Provider | `infrastructure/data_providers/idx.py` | ~322 | Foreign flow from IDX (estimated values) |
| Stockbit Session Broker Provider | `infrastructure/browser/playwright_stockbit.py` | ~170 | Foreign flow via Stockbit browser session |
| Stockbit Browser | `infrastructure/browser/playwright_stockbit.py` | ~1828 | Playwright automation for Stockbit session |
| Google News Provider | `infrastructure/sentiment/google_news_provider.py` | ~251 | RSS news fetcher with ID context |
| CNBC Indonesia Provider | `infrastructure/sentiment/cnbc_indonesia_provider.py` | ~129 | RSS news fetcher ticker-filtered |
| Kontan Provider | `infrastructure/sentiment/kontan_provider.py` | ~133 | RSS news fetcher from kontan.co.id |
| Composite News Provider | `infrastructure/sentiment/composite_provider.py` | ~60 | Merges + deduplicates all news sources |
| Keyword Classifier | `infrastructure/sentiment/keyword_classifier.py` | ~220 | Bilingual keyword-based sentiment |
| AI Classifier | `infrastructure/sentiment/ai_classifier.py` | ~210 | LLM-based sentiment with catalyst taxonomy |
| Sentiment Factory | `infrastructure/sentiment/factory.py` | ~50 | Provider + classifier selection |
| Deduplication | `infrastructure/sentiment/deduplication.py` | ~60 | Headline dedup via normalized comparison |

#### Analysis Core

| Module | File(s) | Lines | What It Does |
|--------|---------|-------|-------------|
| SMA | `domain/indicators/sma.py` | ~40 | Simple moving average (sliding window) |
| EMA | `domain/indicators/ema.py` | ~40 | SMA-seeded exponential moving average |
| RSI | `domain/indicators/rsi.py` | ~50 | Wilder's smoothed RSI |
| Indicator Registry | `application/services/indicator_registry.py` | ~200 | Unified registry: built-in + plugin + formula |
| Conservative Rules | `domain/rules/conservative.py` | ~80 | Requires both RSI + trend agreement, 25/75 thresholds |
| Balanced Rules | `domain/rules/balanced.py` | ~80 | Majority rules, 30/70 thresholds |
| Aggressive Rules | `domain/rules/aggressive.py` | ~80 | Either indicator triggers, 40/60 thresholds |
| Rule Engine | `domain/rules/rule_engine.py` | ~60 | Profile evaluation orchestrator |
| YAML Rule Interpreter | `application/rules/interpreter.py` + `schema.py` | ~450 | Custom YAML rule evaluation with priority |
| Group Mapping | `application/services/group_mapping.py` | ~100 | Stock sector/group classification |

#### Formula DSL

| Module | File(s) | Lines | What It Does |
|--------|---------|-------|-------------|
| AST Nodes | `application/formula/ast_nodes.py` | ~80 | Node types (Number, Identifier, FunctionCall, BinOp) |
| Tokenizer | `application/formula/tokenizer.py` | ~223 | Lexer: numbers, identifiers, operators, parens |
| Parser | `application/formula/parser.py` | ~274 | Recursive descent with operator precedence |
| Evaluator | `application/formula/evaluator.py` | ~491 | Series-to-series computation, scalar broadcasting |
| Validator | `application/formula/validator.py` | ~80 | Formula validation before eval |
| Exceptions | `application/formula/exceptions.py` | ~20 | Formula-specific error types |
| AI Formula Translator | `infrastructure/ai/formula_translator.py` | ~448 | NL-to-formula via LLM |
| Formula Storage | `infrastructure/persistence/formula_storage.py` | ~100 | YAML-based formula persistence |

#### AI Integration

| Module | File(s) | Lines | What It Does |
|--------|---------|-------|-------------|
| Base Explainer | `infrastructure/ai/base_explainer.py` | ~40 | Abstract base with prompt system |
| DeepSeek Explainer | `infrastructure/ai/deepseek_explainer.py` | ~60 | DeepSeek API adapter |
| Claude Explainer | `infrastructure/ai/claude_explainer.py` | ~60 | Claude API adapter |
| OpenAI Explainer | `infrastructure/ai/openai_explainer.py` | ~60 | OpenAI API adapter |
| Gemini Explainer | `infrastructure/ai/gemini_explainer.py` | ~60 | Gemini API adapter |
| Ollama Explainer | `infrastructure/ai/ollama_explainer.py` | ~60 | Local Ollama adapter |
| Mock Explainer | `infrastructure/ai/mock_explainer.py` | ~40 | Deterministic mock for testing |
| Factory | `infrastructure/ai/factory.py` | ~100 | Provider selection + instantiation |
| Strategy Translator | `infrastructure/ai/strategy_translator.py` + prompt | ~200 | NL-to-strategy-YAML |
| Sentiment Analyzer | `infrastructure/ai/sentiment_analyzer.py` | ~80 | AI sentiment classification |

#### Backtest Engine

| Module | File(s) | Lines | What It Does |
|--------|---------|-------|-------------|
| Domain Backtest Engine | `domain/services/backtest_engine.py` | ~200 | All-in-long simulation, drawdown, P&L |
| Backtest Use Case | `application/use_case/backtest.py` | ~250 | Signal generation + engine orchestration |
| Swing Backtest | `application/use_case/swing_backtest.py` | ~664 | Walk-forward portfolio backtest with regime awareness |

#### Trading Workflow

| Module | File(s) | Lines | What It Does |
|--------|---------|-------|-------------|
| Pre-Open Screen Use Case | `application/use_case/pre_open_screen.py` | ~400 | 10-step pre-open analysis |
| Intraday Confirm Use Case | `application/use_case/confirm_intraday_open.py` | ~100 | Opening auction confirmation |
| Position Sizer | `application/services/position_sizer.py` | ~150 | ATR-based position sizing |
| Paper Trade Journal | `application/services/paper_trade_journal.py` | ~120 | Trade journal management |
| Intraday Conf Journal | `application/services/intraday_confirmation_journal.py` | ~80 | Confirmation journal |
| Accumulation Journal | `application/services/accumulation_journal.py` | ~80 | Accumulation candidate journal |
| Intraday Backtest | `application/use_case/intraday_backtest.py` | ~100 | Intraday strategy evaluation |

#### Persistence

| Module | File(s) | Lines | What It Does |
|--------|---------|-------|-------------|
| SQLite Market Repository | `infrastructure/persistence/sqlite_market_repository.py` | ~200 | Candle CRUD |
| SQLite Broker Repository | `infrastructure/persistence/sqlite_broker_repository.py` | ~250 | BrokerSummary CRUD |
| Sentiment Repository | `infrastructure/persistence/sentiment_repository.py` | ~120 | Sentiment record persistence |
| Journal CSV Writer | `infrastructure/persistence/journal_csv_writer.py` | ~80 | Trade journal CSV |
| Accumulation CSV Writer | `infrastructure/persistence/accumulation_journal_csv_writer.py` | ~80 | Accumulation journal CSV |
| Intraday Conf CSV | `infrastructure/persistence/intraday_confirmation_csv.py` | ~60 | Confirmation CSV |
| SQLite Base | `infrastructure/persistence/sqlite.py` | ~60 | DB setup + schema |

#### Plugin System

| Module | File(s) | Lines | What It Does |
|--------|---------|-------|-------------|
| Indicator Plugin Port | `application/ports/indicator_plugin.py` | ~30 | Plugin interface |
| Plugin Loader | `infrastructure/plugins/indicator_loader.py` | ~100 | Auto-discovers plugins at startup |
| ATR Plugin | `plugins/indicators/atr.py` | ~50 | Average True Range |
| MACD Plugin | `plugins/indicators/macd.py` | ~60 | MACD line/signal/histogram |
| Bollinger Bands Plugin | `plugins/indicators/bollinger_bands.py` | ~50 | Upper/lower/middle bands |
| Ichimoku Plugin | `plugins/indicators/ichimoku.py` | ~70 | Ichimoku Cloud components |
| Stochastic Plugin | `plugins/indicators/stochastic.py` | ~50 | %K/%D lines |
| Foreign Flow Plugin | `plugins/indicators/foreign_flow.py` | ~120 | Foreign buy ratio/streak |
| Foreign VWAP Plugin | `plugins/indicators/foreign_vwap.py` | ~40 | Foreign VWAP vs price |

#### Skill / Self-Documentation

| Module | File(s) | Lines | What It Does |
|--------|---------|-------|-------------|
| Skill Generator | `application/services/skill_generator.py` | ~338 | SKILL.md auto-generation |
| Annotation Reader | `infrastructure/skill/annotation_reader.py` | ~100 | Extract `@skill` annotations from Python |
| Index Writer | `infrastructure/skill/index_writer.py` | ~100 | Build SKILLS_INDEX.md |
| Markdown Writer | `infrastructure/skill/markdown_writer.py` | ~80 | Write formatted skill files |
| Rules Hasher | `infrastructure/skill/rules_hasher.py` | ~50 | Hash-based drift detection |

---

### 🧩 SMALL — Individual Components

#### Domain Entities (5)

| Entity | File | Fields | Purpose |
|--------|------|--------|---------|
| `Candle` | `domain/entities/candle.py` | ticker, date, open, high, low, close, volume | OHLCV data point |
| `BacktestTrade` | `domain/entities/backtest_trade.py` | entry_date, exit_date, entry_price, exit_price, quantity, pnl | Single round-trip trade |
| `BrokerSummary` | `domain/entities/broker_flow.py` | ticker, date, foreign_buy, foreign_sell, total_volume, top_buyers, top_sellers | Foreign flow snapshot |
| `AnalysisResult` | `domain/entities/analysis_result.py` | *(stub)* | Placeholder |
| `Stock` | `domain/entities/stock.py` | *(stub)* | Placeholder |

#### Domain Value Objects (11)

| Value Object | File | Purpose |
|-------------|------|---------|
| `RiskAssessment` | `domain/value_objects/risk_assessment.py` | Risk profile evaluation result |
| `RiskSignal` | `domain/value_objects/risk_signal.py` | Individual rule signal |
| `IndicatorSnapshot` | `domain/value_objects/indicator_snapshot.py` | Point-in-time indicator state |
| `JournalEntry` | `domain/value_objects/journal_entry.py` | Paper trade record |
| `AccumulationJournalEntry` | `domain/value_objects/accumulation_journal_entry.py` | Accumulation candidate record |
| `BacktestResult` | `domain/value_objects/backtest_result.py` | Aggregate backtest metrics |
| `TradeAction` | `domain/value_objects/trade_action.py` | Buy/sell/hold signal |
| `ScreenerResult` | `domain/value_objects/screener_result.py` | Pre-open screen output |
| `IntradayConfirmation` | `domain/value_objects/intraday_confirmation.py` | Confirmation decision |
| `Sentiment` | `domain/value_objects/sentiment.py` | Classified headline + score |
| `SkillAnnotation` | `domain/value_objects/skill_annotation.py` | Skill metadata from code |

#### Domain Ports (13)

| Port | File | Implemented By |
|------|------|---------------|
| `MarketDataProvider` | `domain/ports/market_data_provider.py` | YahooFinanceProvider, IdxMarketDataProvider |
| `MarketDataRepository` | `domain/ports/market_data_repository.py` | SQLiteMarketRepository |
| `BrokerDataProvider` | `domain/ports/broker_data_provider.py` | IdxBrokerDataProvider, StockbitPlaywrightBrokerProvider |
| `BrokerDataRepository` | `domain/ports/broker_data_repository.py` | SQLiteBrokerRepository |
| `BrowserDataProvider` | `domain/ports/browser_data_provider.py` | StockbitBrowser |
| `AIExplainer` | `domain/ports/ai_explainer.py` | 6 explainer implementations |
| `NewsProvider` | `domain/ports/news_provider.py` | GoogleNews, CNBC, Kontan |
| `HeadlineClassifier` | `domain/ports/headline_classifier.py` | KeywordClassifier, AIClassifier |
| `SentimentRepository` | `domain/ports/sentiment_repository.py` | SentimentRepository (SQLite) |
| `JournalStore` | `domain/ports/journal_store.py` | PaperTradeJournal |
| `AccumulationJournalStore` | `domain/ports/accumulation_journal_store.py` | AccumulationJournal |
| `CsvBrokerParser` | `domain/ports/csv_broker_parser.py` | BrokerCsvAdapter |
| `Persistence` | `domain/ports/persistence.py` | *(stub)* |

#### Application Use Cases (22)

| Use Case | File | Input | Output |
|----------|------|-------|--------|
| `FetchMarketDataUseCase` | `use_case/fetch_market_data.py` | ticker, days, refresh | candles + source metadata |
| `ComputeSMAUseCase` | `use_case/compute_sma.py` | ticker, period, field | SMA values |
| `ComputeEMAUseCase` | `use_case/compute_ema.py` | ticker, period, field | EMA values |
| `ComputeRSIUseCase` | `use_case/compute_rsi.py` | ticker, period | RSI values |
| `AggregateIndicatorsUseCase` | `use_case/aggregate_indicators.py` | ticker, periods | Combined indicator table |
| `AssessRiskUseCase` | `use_case/assess_risk.py` | ticker, profile, rules | Risk assessment |
| `ExplainRiskUseCase` | `use_case/explain_risk.py` | risk assessment, provider | AI explanation |
| `RunAnalysisUseCase` | `use_case/run_analysis.py` | ticker | Full analysis pipeline |
| `BacktestUseCase` | `use_case/backtest.py` | ticker, strategy, capital | Trade log + metrics |
| `SwingBacktestUseCase` | `use_case/swing_backtest.py` | universe, capital, preset | Portfolio report |
| `MarketRegimeUseCase` | `use_case/market_regime.py` | universe, as_of | Regime context |
| `PreOpenScreenUseCase` | `use_case/pre_open_screen.py` | movers, order books, caps | Screened candidates |
| `ConfirmIntradayOpenUseCase` | `use_case/confirm_intraday_open.py` | opening data, session | ENTER/WAIT/SKIP |
| `FetchSentimentUseCase` | `use_case/fetch_sentiment.py` | ticker, days, classifier | Sentiment summary |
| `AuditSentimentUseCase` | `use_case/audit_sentiment.py` | ticker | Accuracy audit |
| `FetchBrokerDataUseCase` | `use_case/fetch_broker_data.py` | ticker, date range | BrokerSummary list |
| `ImportBrokerDataUseCase` | `use_case/import_broker_data.py` | file, format | Imported summaries |
| `AccumulationScreenUseCase` | `use_case/accumulation_screen.py` | universe, window | Scored stock list |
| `AccumulationAuditUseCase` | `use_case/accumulation_audit.py` | universe, preset | Audit report |
| `CreateIndicatorFromIntentUseCase` | `use_case/create_indicator_from_intent.py` | intent, provider | Formula string |
| `CreateStrategyFromIntentUseCase` | `use_case/create_strategy_from_intent.py` | intent, provider | Strategy YAML |
| `IntradayBacktestUseCase` | `use_case/intraday_backtest.py` | ticker, strategy | Performance report |

#### Application Services (11)

| Service | File | Purpose |
|---------|------|---------|
| `IndicatorRegistry` | `services/indicator_registry.py` | Centralizes all indicators (built-in + plugin + formula) |
| `UniverseLoader` | `services/universe_loader.py` | Resolves ticker lists from named universes |
| `StrategyLoader` | `services/strategy_loader.py` | Loads and validates strategy YAML files |
| `PositionSizer` | `services/position_sizer.py` | ATR-based position sizing |
| `SkillGenerator` | `services/skill_generator.py` | Auto-generates SKILL.md from artifacts |
| `PaperTradeJournal` | `services/paper_trade_journal.py` | CSV-based trade journal management |
| `AccumulationJournal` | `services/accumulation_journal.py` | CSV-based accumulation candidate journal |
| `IntradayConfirmationJournal` | `services/intraday_confirmation_journal.py` | CSV-based confirmation journal |
| `Bootstrap` | `services/bootstrap.py` | System initialization |
| `GroupMapping` | `services/group_mapping.py` | Stock sector/group classification |
| `AIResearch` | `services/ai_research.py` | AI research orchestration |

#### Application Ports (4)

| Port | File | Purpose |
|------|------|---------|
| `FormulaTranslator` | `ports/formula_translator.py` | NL-to-formula interface |
| `StrategyTranslator` | `ports/strategy_translator.py` | NL-to-strategy interface |
| `IndicatorPlugin` | `ports/indicator_plugin.py` | Plugin indicator interface |
| `SkillWriter` | `ports/skill_writer.py` | Skill file writing interface |

#### Application Formula DSL (6)

| Component | File | Purpose |
|-----------|------|---------|
| AST Nodes | `formula/ast_nodes.py` | Node types for formula operations |
| Tokenizer | `formula/tokenizer.py` | Lexer (string → token stream) |
| Parser | `formula/parser.py` | Recursive descent (token stream → AST) |
| Evaluator | `formula/evaluator.py` | AST → series computation |
| Validator | `formula/validator.py` | AST validation |
| Exceptions | `formula/exceptions.py` | Formula-specific errors |

#### Application Rules (3)

| Component | File | Purpose |
|-----------|------|---------|
| Schema | `rules/schema.py` | YAML rule schema definitions |
| Interpreter | `rules/interpreter.py` | Runtime rule evaluation engine |
| Exceptions | `rules/exceptions.py` | Rule-specific errors |

#### Infrastructure Data Providers (4)

| Provider | File | Port | Auth | Data Type |
|----------|------|------|------|-----------|
| `YahooFinanceProvider` | `data_providers/yahoo.py` | MarketDataProvider | No | OHLCV |
| `IdxMarketDataProvider` | `data_providers/idx_market.py` | MarketDataProvider | No | OHLCV |
| `IdxBrokerDataProvider` | `data_providers/idx.py` | BrokerDataProvider | No | Foreign flow (estimated) |
| `StockbitPlaywrightBrokerProvider` | `browser/playwright_stockbit.py` | BrokerDataProvider | Browser session | Foreign flow (exact + per-broker) |

#### Infrastructure AI (15 files)

| File | Purpose |
|------|---------|
| `ai/base_explainer.py` | Abstract base class |
| `ai/deepseek_explainer.py` | DeepSeek implementation |
| `ai/claude_explainer.py` | Claude implementation |
| `ai/openai_explainer.py` | OpenAI implementation |
| `ai/gemini_explainer.py` | Gemini implementation |
| `ai/ollama_explainer.py` | Ollama (local) implementation |
| `ai/mock_explainer.py` | Mock for testing |
| `ai/factory.py` | Provider selection + creation |
| `ai/claude.py` | Legacy Claude adapter |
| `ai/gemini.py` | Legacy Gemini adapter |
| `ai/formula_translator.py` | NL-to-formula via LLM |
| `ai/formula_translator_prompt.py` | Prompt template for formula translation |
| `ai/strategy_translator.py` | NL-to-strategy via LLM |
| `ai/strategy_translator_prompt.py` | Prompt template for strategy translation |
| `ai/sentiment_analyzer.py` | AI sentiment classification |

#### Infrastructure Sentiment (8 files)

| File | Purpose |
|------|---------|
| `sentiment/google_news_provider.py` | Google News RSS fetcher |
| `sentiment/cnbc_indonesia_provider.py` | CNBC Indonesia RSS fetcher |
| `sentiment/kontan_provider.py` | Kontan RSS fetcher |
| `sentiment/composite_provider.py` | Merges multiple news sources |
| `sentiment/keyword_classifier.py` | Rule-based sentiment with bilingual keywords |
| `sentiment/ai_classifier.py` | LLM-based sentiment classifier |
| `sentiment/deduplication.py` | Headline deduplication |
| `sentiment/mock_provider.py` | Mock for testing |

#### Infrastructure Persistence (8 files)

| File | Purpose |
|------|---------|
| `persistence/sqlite.py` | DB setup + schema migration |
| `persistence/sqlite_market_repository.py` | Candle CRUD |
| `persistence/sqlite_broker_repository.py` | BrokerSummary CRUD |
| `persistence/sentiment_repository.py` | Sentiment record persistence |
| `persistence/journal_csv_writer.py` | Trade journal CSV |
| `persistence/accumulation_journal_csv_writer.py` | Accumulation CSV |
| `persistence/intraday_confirmation_csv.py` | Confirmation CSV |
| `persistence/formula_storage.py` | Formula YAML persistence |

#### Infrastructure Browser (2 files)

| File | Purpose |
|------|---------|
| `browser/playwright_stockbit.py` | Playwright automation for Stockbit (1828 lines) |
| `browser/stockbit_browser.py` | Browser session management |

#### Infrastructure Config/CSV (4 files)

| File | Purpose |
|------|---------|
| `config/yaml_loader.py` | YAML config loading |
| `config/user_config.py` | User configuration management |
| `csv/format_detector.py` | Auto-detect CSV format |
| `csv/mapping_loader.py` | Column mapping loader |
| `csv/broker_csv_adapter.py` | CSV broker data parser |

#### Infrastructure Skill (4 files)

| File | Purpose |
|------|---------|
| `skill/annotation_reader.py` | Extract `@skill` annotations from source |
| `skill/index_writer.py` | Build SKILLS_INDEX.md |
| `skill/markdown_writer.py` | Write formatted SKILL.md files |
| `skill/rules_hasher.py` | Hash-based drift detection |

#### Infrastructure Plugins (1)

| File | Purpose |
|------|---------|
| `plugins/indicator_loader.py` | Auto-discovers plugin indicators |

#### Adapter CLI Modules (17)

| Module | File | Group / Commands |
|--------|------|------------------|
| Main | `cli/main.py` | Top-level group definitions (data, indicator, analyze, strategy, trade, skill) |
| Data Router | `cli/data_commands.py` | `saham data [update, broker, stockbit, universe]` |
| Indicator Router| `cli/indicator_commands.py` | `saham indicator [compute, snapshot, create, list, show, delete]` |
| Analyze Router | `cli/analyze_commands.py` | `saham analyze [risk, compare, sentiment, audit, regime, chart]` |
| Trade Router | `cli/trade_commands.py` | `saham trade [swing, intraday]` |
| Strategy Router | `cli/strategy_commands.py` | `saham strategy [init, create, validate, list, backtest]` |
| Skill Router | `cli/skill_commands.py` | `saham skill [generate, check, index]` |
| Broker Impl | `cli/broker_commands.py` | Implementation of broker flow logic |
| Screen Impl | `cli/screen_commands.py` | Implementation of intraday logic (1829 lines) |
| Swing Impl | `cli/swing_commands.py` | Implementation of swing/unified logic |
| Sentiment Impl | `cli/sentiment_commands.py` | Implementation of sentiment logic |
| Stockbit Impl | `cli/stockbit_commands.py` | Implementation of session management |
| Chart Impl | `cli/chart_commands.py` | Implementation of ASCII charts |
| Update Impl | `cli/update_commands.py` | Implementation of batch update logic |
| Accumulation | `cli/accumulation_commands.py` | Implementation of accumulation screen logic |

#### Plugin Indicators (8)

| Plugin | File | What It Computes |
|--------|------|-----------------|
| ATR | `plugins/indicators/atr.py` | Average True Range |
| MACD | `plugins/indicators/macd.py` | MACD line, signal line, histogram |
| Bollinger Bands | `plugins/indicators/bollinger_bands.py` | Upper, middle, lower bands |
| Ichimoku | `plugins/indicators/ichimoku.py` | Conversion, base, span A/B, lagging |
| Stochastic | `plugins/indicators/stochastic.py` | %K, %D lines |
| Foreign Flow | `plugins/indicators/foreign_flow.py` | Foreign buy ratio, streak, consecutive buys |
| Foreign VWAP | `plugins/indicators/foreign_vwap.py` | Foreign VWAP vs current price |
| Template | `plugins/indicators/_template.py` | Plugin authoring template |

#### Strategies (3)

| Strategy | File | Approach |
|----------|------|----------|
| RSI Momentum | `strategies/rsi-momentum/strategy.yaml` | RSI extremes + SMA trend filter |
| Foreign Accumulation | `strategies/foreign-accumulation/strategy.yaml` | Foreign flow patterns + RSI confirmation |
| Test Sentiment | `strategies/test-sentiment/strategy.yaml` | Sentiment rule integration test |

#### Stubs (3)

| File | Status | Notes |
|------|--------|-------|
| `domain/entities/analysis_result.py` | Empty stub | Placeholder, not implemented |
| `domain/entities/stock.py` | Empty stub | Placeholder, not implemented |
| `domain/services/analyze_stock.py` | Empty stub | Placeholder, not implemented |

---

## Data Flow Between Blocks

```
                    ┌──────────────────────────────────────────────────┐
                    │               CLI Adapter Layer                  │
                    │  Parses args, wires deps, calls use case,       │
                    │  formats output                                  │
                    └──────────┬───────────────────────────────────────┘
                               │
                    ┌──────────▼───────────────────────────────────────┐
                    │           Application Layer                      │
                    │  ┌─────────────────┐   ┌─────────────────┐     │
                    │  │   Use Case      │──►│   Service       │     │
                    │  │  (orchestrates) │   │  (cross-cutting)│     │
                    │  └────────┬────────┘   └─────────────────┘     │
                    │           │                                     │
                    │  ┌────────▼────────┐                            │
                    │  │  Formula DSL   │  (if indicator computation) │
                    │  │  tokenizer →   │                            │
                    │  │  parser →      │                            │
                    │  │  evaluator     │                            │
                    │  └─────────────────┘                            │
                    └──────────┬───────────────────────────────────────┘
                               │
                    ┌──────────▼───────────────────────────────────────┐
                    │            Domain Layer                         │
                    │  Entities ← Value Objects ← Indicators ← Rules │
                    │         ↕                                       │
                    │       Ports (interfaces only)                   │
                    └──────────┬───────────────────────────────────────┘
                               │
                    ┌──────────▼───────────────────────────────────────┐
                    │         Infrastructure Layer                    │
                    │  ┌──────────┐ ┌────────┐ ┌──────────────────┐  │
                    │  │ Data     │ │ AI     │ │ Persistence      │  │
                    │  │ Providers│ │Adapters│ │ SQLite + CSV +   │  │
                    │  │ Yahoo   │ │ DeepS  │ │ YAML             │  │
                    │  │ IDX     │ │ Claude │ └──────────────────┘  │
                    │  │ Stockbit│ │ Ollama │ ┌──────────────────┐  │
                    │  │ News Sr │ │ ...    │ │ Browser(Playwr.) │  │
                    │  └──────────┘ └────────┘ └──────────────────┘  │
                    └──────────────────────────────────────────────────┘
```

---

## Dependency Graph — Which Block Uses Which

```
CLI ───┬─── Use Case ─── Domain Port ─── Infrastructure
        │
        ├─── Service ─── Domain Entity/Value Object
        │
        ├─── Use Case ─── Service ─── Domain Port
        │
        ├─── Use Case ─── Formula DSL (application layer)
        │
        └─── Use Case ─── Domain Service (backtest_engine)
                               │
                               └─── Domain Entity/Value Object
```

### Concrete example: `saham analyze risk BBCA --explain`

Read-heavy flow — indicators from cache, AI optional.

```
CLI: main.py (parse --explain, --provider)
  │
  ▼
UseCase: AssessRiskUseCase (compute indicators, evaluate rules)
  │         │
  │         ├── Domain Port: MarketDataRepository      ← interface
  │         │     └── Infra: SQLiteMarketRepository    ← implementation
  │         │
  │         ├── Domain: sma.py → ema.py → rsi.py       ← pure functions
  │         │
  │         ├── Domain Rules: RuleEngine → Conservative/Balanced/Aggressive
  │         │
  │         └── Domain Value Object: RiskAssessment
  │
  ▼
UseCase: ExplainRiskUseCase
  │
  ├── Domain Port: AIExplainer                        ← interface
  │     └── Infra: DeepSeekExplainer (via Factory)    ← implementation
  │
  └── Domain Entity: RiskAssessment
```

### Concrete example: `saham data update BBCA --days 365 --provider idx`

Write-heavy flow — external API → cache.

```
CLI: main.py (parse --provider idx)
  │
  ▼
UseCase: FetchMarketDataUseCase
  │
  ├── Domain Port: MarketDataRepository       ← check cache first
  │     └── Infra: SQLiteMarketRepository
  │
  ├── Domain Port: MarketDataProvider         ← fetch from external
  │     └── Infra: IdxMarketDataProvider      ← IDX public API
  │
  ├── Domain Entity: Candle                   ← returned data
  │
  └── Infra: SQLiteMarketRepository.save()    ← persist to cache
```

### Concrete example: `saham indicator create "RSI smoothed with EMA of period 3"`

AI-heavy flow — NL → formula → validate → store.

```
CLI: main.py (parse intent, --provider default=deepseek)
  │
  ▼
UseCase: CreateIndicatorFromIntentUseCase
  │
  ├── App Port: FormulaTranslator             ← interface
  │     └── Infra: AI FormulaTranslator       ← DeepSeek/Claude/etc.
  │           └── Prompt Template             ← formula_translator_prompt.py
  │
  ├── Application: Formula DSL
  │     ├── tokenizer.py                      ← lex intent
  │     ├── parser.py                         ← build AST
  │     ├── validator.py                      ← check validity
  │     └── evaluator.py                      ← test compute
  │
  └── Infra: FormulaStorage                   ← persist to formulas.yaml
```

---

## Source File Summary

| Layer | Files | Lines (approx) |
|-------|-------|----------------|
| Domain | 42 | ~2,500 |
| Application | 37 | ~6,500 |
| Infrastructure | 53 | ~9,000 |
| Adapters | 14 | ~6,500 |
| Plugins | 9 | ~600 |
| Strategies | 5 | ~300 |
| **Total** | **160+** | **~25,400** |

---

## Key Architectural Rules

1. **Domain is pure** — zero external imports (stdlib only: `dataclasses`, `Decimal`, `date`, `Enum`). No network, no AI, no database.
2. **Use Cases orchestrate** — never contain business logic, only coordinate domain + infrastructure.
3. **Infrastructure implements ports** — never the reverse. Use case never imports infrastructure directly.
4. **Adapters are thin** — parse input, wire deps, call use case, format output. No business logic.
5. **Formula DSL is in Application layer** — not domain (it's a tool for composing indicators, not a business concept).
6. **AI is purely Infrastructure** — behind `AIExplainer`, `FormulaTranslator`, `StrategyTranslator` ports. Swappable, optional, testable.
