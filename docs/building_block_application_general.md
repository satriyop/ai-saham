# Application Building Blocks

This document maps every component of AI Saham into a three-tier hierarchy: **Big** (subsystems), **Medium** (modules), and **Small** (individual components). Use this as a reference to understand how pieces connect and where to make changes.

---

## Layer Architecture (Hexagonal)

```
                    +---------------------------------------+
                    |             Adapters  (21 modules)    |
                    |  CLI | Bot (stub) | Web (stub)        |
                    +---------------------------------------+
                                    |
                                    v
                    +---------------------------------------+
                    |        Application Layer              |
                    |  38 use cases | 10 services | 5 ports |
                    |  Formula DSL (6 files) | Rules (3)    |
                    |  DTOs (2)                             |
                    +---------------------------------------+
                                    |
                                    v
                    +---------------------------------------+
                    |         Domain Layer (Pure Python)    |
                    |  7 entities | 21 value objects        |
                    |  5 indicators | 2 services (1 stub)   |
                    |  24 ports | 6 rules                   |
                    +---------------------------------------+
                                    ^
                                    |
                    +---------------------------------------+
                    |      Infrastructure Layer             |
                    |  5 data providers | 11 persistence    |
                    |  15 AI files | 11 sentiment           |
                    |  13 browser | 3 config + 3 csv        |
                    |  1 plugin loader | 4 skill            |
                    +---------------------------------------+
```

---

### Internal Layer Breakdown

The same layers with their actual components visible:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CLI LAYER (21 modules)                       │
│  main.py (groups)                                                   │
│  fetch_commands.py (fetch group router)                             │
│  fetch_market_commands.py (market data fetch impl)                  │
│  fetch_iev_commands.py (IEV snapshot capture impl)                  │
│  view_commands.py (read-only broker views)                          │
│  research_commands.py (pre-open track/grade under research)           │
│  today_commands.py (daily briefing)                                  │
│  fetch_status_commands.py (data health check)                        │
│  indicator_commands.py (compute, snapshot, create, list)            │
│  analyze_commands.py (risk, compare, sentiment, audit, regime)      │
│  trade_commands.py (trade group router)                             │
│  trade_intraday_commands.py (intraday trade CLI impl)               │
│  strategy_commands.py (init, create, backtest, list)                │
│  strategy_skill_commands.py (strategy skill implementation)         │
│  screen_lifecycle_commands.py (screen lifecycle helper)             │
│  screen_pre_open_commands.py (pre-open screen CLI impl)             │
│  + impl files (analyze_chart, analyze_sentiment, fetch_stockbit,       │
│    analyze_swing, trade_swing)                                       │
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
│  │  BrokerTrans. │  │  AccumJournalEntry │  │  NewsProvider    │    │
│  │               │  │  BacktestResult    │  │  HeadlineClassif │    │
│  │               │  │  TradeAction       │  │  SentimentRepo   │    │
│  │               │  │  ScreenerResult    │  │  AccumJournalStore│    │
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
| 1 | **CLI Router** | Routes user commands to use cases via lifecycle groups. Parses flags, wires dependencies, displays output. | `saham <group> <cmd>` | `main.py`, `fetch_commands.py`, `trade_commands.py`, etc |
| 2 | **Data Ingestion** | Fetches, caches, and serves OHLCV + broker + news data from external sources. | `fetch market`, `fetch broker`, `fetch stockbit`, `fetch iev`, `analyze sentiment` | `yahoo.py`, `idx_market.py`, `idx.py`, `playwright_stockbit.py`, `playwright_stockbit_browser.py`, 20 Stockbit specialized providers, 6 sentiment providers, SQLite repos |
| 3 | **Analysis Core** | Deterministic indicator computation, risk profiling, and composite analysis. | `indicator compute`, `indicator snapshot`, `analyze risk`, `analyze compare` | `sma.py`, `ema.py`, `rsi.py`, `indicator_registry.py`, 3 rule profiles, `rule_engine.py` |
| 4 | **Screening Suite** | Multi-dimensional stock screening for accumulation patterns, pre-open movers, and swing candidates. | `screen accum`, `screen pre-open` | `accumulation_screen_use_case.py`, `screen_accum_commands.py`, `pre_open_screen_use_case.py`, `screen_pre_open_commands.py` |
| 5 | **Strategy System** | Authoring, validation, loading, and execution of versioned strategy packages. | `strategy init/create/validate/list`, `strategy backtest` | `strategy_loader.py`, 3 strategy YAMLs, `strategy_commands.py` |
| 6 | **Formula DSL** | Custom indicator language with tokenizer, parser, evaluator, and validator. Supports nesting and series operations. | `indicator create`, `indicator show`, `indicator compute <formula>` | 6 files in `application/formula/`, `formula_storage.py` |
| 7 | **AI Integration** | 6 AI providers for explanation, formula translation, strategy creation, and sentiment classification. | `--explain`, `--ai-classify`, `indicator create`, `strategy create` | `factory.py`, 6 explainers, 2 translators, `sentiment_analyzer.py` |
| 8 | **Backtest Engine** | Signal generation from rules/strategies and portfolio simulation (single + walk-forward). | `strategy backtest`, `trade backtest-swing` | `backtest_engine.py` (domain), `swing_backtest.py` (app), `backtest.py` (use case) |
| 9 | **Trading Workflow** | End-to-end trade lifecycle: pre-open capture/track → assess pre-open → journal → review → outcome. | `screen pre-open`, `assess pre-open`, `trade log`, `trade review`, `plan swing`, `trade size` | `analyze_pre_open_commands.py`, `position_sizer.py`, journal services |
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
| Stockbit Playwright Broker Provider | `infrastructure/browser/playwright_stockbit.py` (delegates browser lifecycle to `playwright_stockbit_browser.py`) | ~2000 | Broker provider + browser session management for Stockbit |
| Stockbit Analyst Consensus | `infrastructure/browser/stockbit_analyst.py` | ~86 | Analyst ratings + price targets |
| Stockbit Bandar Detector | `infrastructure/browser/stockbit_bandar.py` | ~177 | Institutional operator accumulation signal |
| Stockbit Company Profile | `infrastructure/browser/stockbit_company_profile.py` | ~94 | Sector, industry, market cap |
| Stockbit Forward Estimates | `infrastructure/browser/stockbit_forward_estimates.py` | ~137 | EPS estimates, revenue forecasts |
| Stockbit Fundamentals | `infrastructure/browser/stockbit_fundamentals.py` | ~150 | P/E, ROE, Piotroski F-Score |
| Stockbit Insider Activity | `infrastructure/browser/stockbit_insider.py` | ~152 | Director/commissioner transaction flags |
| Stockbit Seasonality | `infrastructure/browser/stockbit_seasonality.py` | ~114 | Monthly return/win rate |
| Stockbit Shareholding | `infrastructure/browser/stockbit_shareholding.py` | ~161 | Institutional/individual split |
| Stockbit Corp Action | `infrastructure/browser/stockbit_corp_action.py` | ~171 | Dividend/RUPS/rights issue calendar |
| Stockbit Ticker Notation | `infrastructure/browser/stockbit_ticker_notation.py` | ~126 | Special notation/status badges |
| Stockbit Order Book | `infrastructure/browser/stockbit_order_book.py` | ~154 | Level 2 order book data |
| Stockbit Running Trade | `infrastructure/browser/stockbit_running_trade.py` | ~144 | Real-time institutional absorption |
| Stockbit Market Time | `infrastructure/browser/stockbit_market_time.py` | ~135 | Market operating status |
| Stockbit Universe | `infrastructure/browser/stockbit_universe.py` | ~110 | Ticker universe definitions |
| Stockbit Browser | `infrastructure/browser/stockbit_browser.py` | ~157 | Manual browser session management |
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
| Backtest Use Case | `application/use_case/backtest_use_case.py` | ~250 | Signal generation + engine orchestration |
| Swing Backtest | `application/use_case/swing_backtest_use_case.py` | ~664 | Walk-forward portfolio backtest with regime awareness |

#### Trading Workflow

| Module | File(s) | Lines | What It Does |
|--------|---------|-------|-------------|
| Pre-Open Screen Use Case | `application/use_case/pre_open_screen_use_case.py` | ~400 | 10-step pre-open analysis |
| Intraday Confirm Use Case | `application/use_case/pre_open_post_open_gates_use_case.py` | ~100 | Opening auction confirmation |
| Position Sizer | `application/services/position_sizer.py` | ~150 | ATR-based position sizing |
| Intraday Conf Journal | `application/services/pre_open_paper_journal.py` | ~80 | Confirmation journal |
| Accumulation Journal | `application/services/accumulation_journal.py` | ~80 | Accumulation candidate journal |
| Intraday Backtest | `application/use_case/intraday_backtest_use_case.py` | ~100 | Intraday strategy evaluation |

#### Persistence

| Module | File(s) | Lines | What It Does |
|--------|---------|-------|-------------|
| SQLite Market Repository | `infrastructure/persistence/sqlite_market_repository.py` | ~200 | Candle CRUD |
| SQLite Broker Repository | `infrastructure/persistence/sqlite_broker_repository.py` | ~250 | BrokerSummary CRUD |
| Sentiment Repository | `infrastructure/persistence/sentiment_repository.py` | ~120 | Sentiment record persistence |
| Accumulation CSV Writer | `infrastructure/persistence/accumulation_journal_csv_writer.py` | ~80 | Accumulation journal CSV |
| Intraday Conf CSV | `infrastructure/persistence/pre_open_paper_journal_csv.py` | ~60 | Confirmation CSV |
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

#### Domain Entities (7)

| Entity | File | Fields | Purpose |
|--------|------|--------|---------|
| `Candle` | `domain/entities/candle.py` | ticker, date, open, high, low, close, volume | OHLCV data point |
| `BacktestTrade` | `domain/entities/backtest_trade.py` | entry_date, exit_date, entry_price, exit_price, quantity, pnl | Single round-trip trade |
| `BrokerSummary` | `domain/entities/broker_flow.py` | ticker, date, foreign_buy, foreign_sell, total_volume, top_buyers, top_sellers | Foreign flow snapshot |
| `AnalysisResult` | `domain/entities/analysis_result.py` | *(stub)* | Placeholder |
| `Stock` | `domain/entities/stock.py` | *(stub)* | Placeholder |
| `StockMeta` | `domain/entities/stock_meta.py` | ticker, sector, industry, exchange | Stock metadata |
| `TradeTick` | `domain/entities/trade_tick.py` | time, price, volume, side | Intraday trade tick |

#### Domain Value Objects (21)

| Value Object | File | Purpose |
|-------------|------|---------|
| `RiskAssessment` | `domain/value_objects/risk_assessment.py` | Risk profile evaluation result |
| `RiskSignal` | `domain/value_objects/risk_signal.py` | Individual rule signal |
| `IndicatorSnapshot` | `domain/value_objects/indicator_snapshot.py` | Point-in-time indicator state |
| `AccumulationJournalEntry` | `domain/value_objects/accumulation_journal_entry.py` | Accumulation candidate record |
| `BacktestResult` | `domain/value_objects/backtest_result.py` | Aggregate backtest metrics |
| `TradeAction` | `domain/value_objects/trade_action.py` | Buy/sell/hold signal |
| `ScreenerResult` | `domain/value_objects/screener_result.py` | Pre-open screen output |
| `PreOpenPostOpenAssessment` | `domain/value_objects/pre_open_post_open_assessment.py` | Confirmation decision |
| `Sentiment` | `domain/value_objects/sentiment.py` | Classified headline + score |
| `SkillAnnotation` | `domain/value_objects/skill_annotation.py` | Skill metadata from code |
| `AnalystConsensus` | `domain/value_objects/analyst_consensus.py` | Analyst ratings + price target |
| `BandarDetectorSnapshot` | `domain/value_objects/bandar_detector_snapshot.py` | Bandar accumulation/distribution signal |
| `CompanyFundamentals` | `domain/value_objects/company_fundamentals.py` | P/E, ROE, Piotroski F-Score |
| `CorporateActionEvent` | `domain/value_objects/corporate_action_event.py` | Dividend/RUPS/rights issue |
| `InsiderTransaction` | `domain/value_objects/insider_transaction.py` | Director/commissioner trades |
| `MarketStatus` | `domain/value_objects/market_status.py` | Market operating status |
| `OrderBookSnapshot` | `domain/value_objects/order_book_snapshot.py` | Order book level 2 data |
| `RunningTradeSignal` | `domain/value_objects/running_trade_signal.py` | Real-time institutional absorption |
| `SeasonalEdge` | `domain/value_objects/seasonal_edge.py` | Monthly return/win rate ranking |
| `ShareholdingComposition` | `domain/value_objects/shareholding_composition.py` | Institutional/individual split |
| `TickSize` | `domain/value_objects/tick_size.py` | IDX tick size table |

#### Domain Ports (24)

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
| `AccumulationJournalStore` | `domain/ports/accumulation_journal_store.py` | AccumulationJournal |
| `CsvBrokerParser` | `domain/ports/csv_broker_parser.py` | BrokerCsvAdapter |
| `Persistence` | `domain/ports/persistence.py` | *(stub)* |
| `AnalystConsensusProvider` | `domain/ports/analyst_consensus_provider.py` | StockbitAnalyst |
| `BandarDetectorProvider` | `domain/ports/bandar_detector_provider.py` | StockbitBandar |
| `FundamentalsProvider` | `domain/ports/fundamentals_provider.py` | StockbitFundamentals |
| `InsiderActivityProvider` | `domain/ports/insider_activity_provider.py` | StockbitInsider |
| `MarketStatusProvider` | `domain/ports/market_status_provider.py` | StockbitMarketTime |
| `OrderBookProvider` | `domain/ports/order_book_provider.py` | StockbitOrderBook |
| `RunningTradeProvider` | `domain/ports/running_trade_provider.py` | StockbitRunningTrade |
| `SeasonalityProvider` | `domain/ports/seasonality_provider.py` | StockbitSeasonality |
| `ShareholdingProvider` | `domain/ports/shareholding_provider.py` | StockbitShareholding |
| `StockMetaProvider` | `domain/ports/stock_meta_provider.py` | YahooStockMeta |
| `StockMetaRepository` | `domain/ports/stock_meta_repository.py` | SQLiteStockMeta |

#### Application Use Cases (38)

| Use Case | File | Input | Output |
|----------|------|-------|--------|
| `RefreshMarketDataUseCase` | `use_case/refresh_market_data_use_case.py` | ticker, days, refresh | candles + source metadata |
| `ComputeSMAUseCase` | `use_case/compute_sma_use_case.py` | ticker, period, field | SMA values |
| `ComputeEMAUseCase` | `use_case/compute_ema_use_case.py` | ticker, period, field | EMA values |
| `ComputeRSIUseCase` | `use_case/compute_rsi_use_case.py` | ticker, period | RSI values |
| `AggregateIndicatorsUseCase` | `use_case/aggregate_indicators_use_case.py` | ticker, periods | Combined indicator table |
| `AssessRiskUseCase` | `use_case/assess_risk_use_case.py` | ticker, profile, rules | Risk assessment |
| `ExplainRiskUseCase` | `use_case/explain_risk_use_case.py` | risk assessment, provider | AI explanation |
| `BacktestUseCase` | `use_case/backtest_use_case.py` | ticker, strategy, capital | Trade log + metrics |
| `SwingBacktestUseCase` | `use_case/swing_backtest_use_case.py` | universe, capital, preset | Portfolio report |
| `BuildMarketContextUseCase` | `use_case/build_market_context_use_case.py` | universe, as_of | Market context factors |
| `PreOpenScreenUseCase` | `use_case/pre_open_screen_use_case.py` | movers, order books, caps | Screened candidates |
| `PreOpenPostOpenGatesUseCase` | `use_case/pre_open_post_open_gates_use_case.py` | opening data, session | ENTER/WAIT/SKIP |
| `FetchSentimentUseCase` | `use_case/fetch_sentiment_use_case.py` | ticker, days, classifier | Sentiment summary |
| `AuditSentimentUseCase` | `use_case/audit_sentiment_use_case.py` | ticker | Accuracy audit |
| `FetchBrokerDataUseCase` | `use_case/fetch_broker_data_use_case.py` | ticker, date range | BrokerSummary list |
| `ImportBrokerDataUseCase` | `use_case/import_broker_data_use_case.py` | file, format | Imported summaries |
| `AccumulationScreenUseCase` | `use_case/accumulation_screen_use_case.py` | universe, window | Scored stock list |
| `AccumulationAuditUseCase` | `use_case/accumulation_audit_use_case.py` | universe, preset | Audit report |
| `CreateIndicatorFromIntentUseCase` | `use_case/create_indicator_from_intent_use_case.py` | intent, provider | Formula string |
| `CreateStrategyFromIntentUseCase` | `use_case/create_strategy_from_intent_use_case.py` | intent, provider | Strategy YAML |
| `IntradayBacktestUseCase` | `use_case/intraday_backtest_use_case.py` | ticker, strategy | Performance report |
| `FetchMarketRefreshUseCase` | `use_case/fetch_market_refresh_use_case.py` | universe, days | Batch refresh |
| `RefreshBrokerDataUseCase` | `use_case/refresh_broker_data_use_case.py` | ticker, date range | Refreshed broker data |
| `FetchBrokerDailyFlowsUseCase` | `use_case/fetch_broker_daily_flows_use_case.py` | ticker, days | Foreign flow time-series |
| `RecordPreOpenObservationsUseCase` | `use_case/record_pre_open_observations_use_case.py` | — | Save pre-open decisions + ops export |
| `OpeningTrackUseCase` | `use_case/opening_track_use_case.py` | — | Orderbook tracking |
| `OpeningGradeUseCase` | `use_case/opening_grade_use_case.py` | — | Accuracy report |
| `OpeningPromptUseCase` | `use_case/opening_prompt_use_case.py` | session | AI prompt |
| `OpeningTuneUseCase` | `use_case/opening_tune_use_case.py` | — | Config recommendations |
| `DailyBriefingUseCase` | `use_case/daily_briefing_use_case.py` | universe, date | Briefing summary |
| `SwingAnalysisWorkflowUseCase` | `use_case/swing_analysis_workflow_use_case.py` | ticker, capital | Composite swing view |
| `PreOpenWorkflowUseCase` | `use_case/pre_open_workflow_use_case.py` | movers, config | Pre-open orchestration |
| `ResolveOpeningPricesUseCase` | `use_case/resolve_opening_prices_use_case.py` | session | Opening prices |
| `DataUpdateStatusUseCase` | `use_case/data_update_status_use_case.py` | — | Health check |
| `FetchStockMetaUseCase` | `use_case/fetch_stock_meta_use_case.py` | ticker | Sector/industry metadata |
| `AnalyzeRunningTradeUseCase` | `use_case/analyze_running_trade_use_case.py` | ticker | Running trade attribution |

#### Application Services (10)

| Service | File | Purpose |
|---------|------|---------|
| `IndicatorRegistry` | `services/indicator_registry.py` | Centralizes all indicators (built-in + plugin + formula) |
| `UniverseLoader` | `services/universe_loader.py` | Resolves ticker lists from named universes |
| `StrategyLoader` | `services/strategy_loader.py` | Loads and validates strategy YAML files |
| `PositionSizer` | `services/position_sizer.py` | ATR-based position sizing |
| `SkillGenerator` | `services/skill_generator.py` | Auto-generates SKILL.md from artifacts |
| `AccumulationJournal` | `services/accumulation_journal.py` | CSV-based accumulation candidate journal |
| `PreOpenPostOpenAssessmentJournal` | `services/pre_open_paper_journal.py` | CSV-based confirmation journal |
| `Bootstrap` | `services/bootstrap.py` | System initialization |
| `GroupMapping` | `services/group_mapping.py` | Stock sector/group classification |
| `AIResearch` | `services/ai_research.py` | AI research orchestration |

#### Application Ports (5)

| Port | File | Purpose |
|------|------|---------|
| `FormulaTranslator` | `ports/formula_translator.py` | NL-to-formula interface |
| `StrategyTranslator` | `ports/strategy_translator.py` | NL-to-strategy interface |
| `IndicatorPlugin` | `ports/indicator_plugin.py` | Plugin indicator interface |
| `SkillWriter` | `ports/skill_writer.py` | Skill file writing interface |
| `CorporateActionRepository` | `ports/corporate_action_repository.py` | Corporate action event persistence |

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
| `StockbitPlaywrightBrokerProvider` | `browser/playwright_stockbit.py` | BrokerDataProvider | Browser session (via `playwright_stockbit_browser.py`) | Foreign flow (exact + per-broker) |

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

#### Infrastructure Persistence (14 files)

| File | Purpose |
|------|---------|
| `persistence/sqlite.py` | Core SQLite repository (DB setup + schema) |
| `persistence/sqlite_market_repository.py` | Candle CRUD |
| `persistence/sqlite_broker_repository.py` | BrokerSummary CRUD |
| `persistence/sqlite_stock_meta_repository.py` | Stock metadata CRUD |
| `persistence/sqlite_data_quality_audit.py` | Data quality diagnostic queries |
| `persistence/sqlite_data_update_status.py` | Last-refresh tracking per ticker |
| `persistence/sqlite_iev_repository.py` | IEV snapshot read/write |
| `persistence/sqlite_system_status_provider.py` | Provider health + staleness |
| `persistence/sentiment_repository.py` | Sentiment record persistence |
| `persistence/accumulation_journal_csv_writer.py` | Accumulation CSV |
| `persistence/pre_open_paper_journal_csv.py` | Confirmation CSV |
| `persistence/formula_storage.py` | Formula YAML persistence |
| `persistence/iev_json_sidecar.py` | IEV JSON sidecar management |
| `persistence/trade_journal_jsonl_writer.py` | Unified trade journal (JSONL) |

#### Infrastructure Browser (22 files)

| File | Purpose |
|------|---------|
| `browser/playwright_stockbit.py` | Broker provider (delegates browser lifecycle) |
| `browser/playwright_stockbit_browser.py` | Browser automation + session management |
| `browser/stockbit_browser.py` | Manual browser session management |
| `browser/stockbit_analyst.py` | Analyst ratings + price targets |
| `browser/stockbit_bandar.py` | Institutional operator accumulation signal |
| `browser/stockbit_broker_distribution.py` | Cross-broker counterparty matrix |
| `browser/stockbit_company_profile.py` | Sector, industry, market cap |
| `browser/stockbit_corp_action.py` | Dividend/RUPS/rights issue calendar |
| `browser/stockbit_earnings.py` | Quarterly earnings beat/miss history |
| `browser/stockbit_forward_estimates.py` | EPS estimates, revenue forecasts |
| `browser/stockbit_fundamentals.py` | P/E, ROE, Piotroski F-Score |
| `browser/stockbit_insider.py` | Director/commissioner transaction flags |
| `browser/stockbit_intraday_broker_chart.py` | Intraday broker chart data |
| `browser/stockbit_market_time.py` | Market operating status |
| `browser/stockbit_order_book.py` | Level 2 order book data |
| `browser/stockbit_running_trade.py` | Real-time institutional absorption |
| `browser/stockbit_running_trade_chart.py` | Running trade chart data |
| `browser/stockbit_seasonality.py` | Monthly return/win rate |
| `browser/stockbit_shareholding.py` | Institutional/individual split |
| `browser/stockbit_ticker_notation.py` | Special notation/status badges |
| `browser/stockbit_universe.py` | Ticker universe definitions |
| `browser/stockbit_valuation.py` | P/E TTM, EPS TTM valuation metrics |

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

#### Adapter CLI Modules (21)

| Module | File | Group / Commands |
|--------|------|------------------|
| Main | `cli/main.py` | Top-level lifecycle group definitions |
| Fetch Router | `cli/fetch_commands.py` | `saham fetch [market, broker, broker-import, broker-history, broker-top-foreign, iev, stockbit, universe (list/update/create/inspect), status]` |
| Data Fetch (market) | `cli/fetch_market_commands.py` | Implementation of market data fetch |
| IEV Capture | `cli/fetch_iev_commands.py` | Implementation of IEV snapshot capture |
| View Router | `cli/view_commands.py` | `saham view broker [flow, top, history, top-foreign, distribution, mappings, status]` plus `saham view TICKER` (shorthand: `saham view BBCA`), `saham view universe` |
| Research pre-open session | `cli/research_pre_open_*_commands.py` | `research pre-open` capture/track/grade/labels/prompt/tune |
| Today Briefing | `cli/today_commands.py` | `saham today` daily briefing |
| Status Impl | `cli/fetch_status_commands.py` | `saham fetch status` |
| Indicator Router| `cli/indicator_commands.py` | `saham indicator [compute, snapshot, create, list, show, delete]` |
| Analyze Router | `cli/analyze_commands.py` | `saham analyze [risk, compare, sentiment, audit, regime, chart, swing, swing-compare, signal]` |
| Research Router | `cli/research_commands.py` | `saham research [signal, accumulation]` |
| Trade Router | `cli/trade_commands.py` | `saham trade [confirm, log, review, size, outcome, backtest-swing, backtest-intraday]` |
| Trade (intraday) | `cli/trade_intraday_commands.py` | Implementation of intraday trade CLI |
| Strategy Router | `cli/strategy_commands.py` | `saham strategy [init, create, validate, list, backtest, skill]` |
| Skill Impl | `cli/strategy_skill_commands.py` | `saham strategy skill [generate, check, index]` |
| Screen Lifecycle | `cli/screen_lifecycle_commands.py` | Screen lifecycle management helper (watchlist, compare) |
| Screen (pre-open) | `cli/screen_pre_open_commands.py` | Implementation of pre-open screen CLI |
| Broker Impl | `cli/broker_commands.py` | Implementation of broker flow logic |
| Screen Impl | `cli/intraday_workflow_commands.py` | Shared intraday workflow implementation |
| Swing Analyze | `cli/analyze_swing_commands.py` | Swing analysis commands (includes analyze_swing_display.py, analyze_swing_broker_display.py) |
| Swing Trade | `cli/trade_swing_commands.py` | Swing trade lifecycle (includes trade_swing_display.py, trade_swing_size_display.py) |
| Sentiment Impl | `cli/analyze_sentiment_commands.py` | Implementation of sentiment logic |
| Stockbit Impl | `cli/fetch_stockbit_commands.py` | Implementation of session management |
| Chart Impl | `cli/analyze_chart_commands.py` | Implementation of ASCII charts |
| Data Quality | `cli/fetch_audit_commands.py` | `saham fetch audit` data quality diagnostic |
| Screen Accumulation | `cli/screen_accum_commands.py` | Implementation of accumulation screen CLI |
| Screen Accumulation Display | `cli/screen_accum_display.py` | Rich-formatted accumulation screen output |
| Analyze Accumulation Audit | `cli/analyze_accum_commands.py` | Historical accumulation audit CLI |
| Analyze Accumulation Display | `cli/analyze_accum_display.py` | Rich-formatted accumulation audit output |
| Broker Display | `cli/broker_display.py` | Rich-formatted broker tables |
| Swing Analyze Display | `cli/analyze_swing_display.py` | Rich-formatted swing analysis output |
| Swing Broker Display | `cli/analyze_swing_broker_display.py` | Rich-formatted broker attribution |
| Swing Trade Display | `cli/trade_swing_display.py` | Rich-formatted swing trade output |
| Swing Size Display | `cli/trade_swing_size_display.py` | Rich-formatted position sizing |
| Regime Display | `cli/analyze_regime_display.py` | Rich-formatted market regime output |
| View Ticker Display | `cli/view_ticker_display.py` | Rich-formatted ticker dashboard |
| View Universe Display | `cli/view_universe_display.py` | Rich-formatted universe overview |
| Intraday Pre-Open Display | `cli/intraday_pre_open_display.py` | Rich-formatted pre-open table |
| Pre-open post-open display | `cli/trade_pre_open_display.py` / `analyze_pre_open_display.py` | Rich-formatted post-open assess + paper review |
| Intraday Backtest Display | `cli/intraday_backtest_display.py` | Rich-formatted intraday backtest |
| Accumulation Journal Display | `cli/accumulation_journal_display.py` | Rich-formatted journal review |
| Rich Display Utilities | `cli/rich_display.py` | Shared Rich render helpers |
| Fetch Universe | `cli/fetch_universe_commands.py` | Universe management commands |

#### Plugin Indicators (13)

| Plugin | File | What It Computes |
|--------|------|-----------------|
| ATR | `plugins/indicators/atr.py` | Average True Range |
| MACD | `plugins/indicators/macd.py` | MACD line, signal line, histogram |
| Bollinger Bands | `plugins/indicators/bollinger_bands.py` | Upper, middle, lower bands |
| Ichimoku | `plugins/indicators/ichimoku.py` | Conversion, base, span A/B, lagging |
| Stochastic | `plugins/indicators/stochastic.py` | %K, %D lines |
| Foreign Flow | `plugins/indicators/foreign_flow.py` | Foreign buy ratio, streak, consecutive buys |
| Foreign VWAP | `plugins/indicators/foreign_vwap.py` | Foreign VWAP vs current price |
| MFI | `plugins/indicators/mfi.py` | Money Flow Index |
| OBV | `plugins/indicators/obv.py` | On-Balance Volume |
| Relative Strength | `plugins/indicators/relative_strength.py` | RS rating vs benchmark |
| Volume Ratio | `plugins/indicators/volume_ratio.py` | Volume vs average ratio |
| VWAP | `plugins/indicators/vwap.py` | Volume-Weighted Average Price |
| Williams %R | `plugins/indicators/williams_r.py` | Williams %R oscillator |
| Template | `plugins/indicators/_template.py` | Plugin authoring template |

#### Strategies (16)

| Strategy | File | Approach |
|----------|------|----------|
| BB Breakout | `strategies/bb-breakout/strategy.yaml` | Bollinger Band breakout |
| BB Mean Reversion | `strategies/bb-mean-reversion/strategy.yaml` | Bollinger Band reversion |
| EMA Crossover | `strategies/ema-crossover/strategy.yaml` | EMA 9/21 crossover |
| Foreign Accumulation | `strategies/foreign-accumulation/strategy.yaml` | Foreign flow patterns + RSI confirmation |
| Foreign Ichimoku | `strategies/foreign-ichimoku/strategy.yaml` | Foreign flow + Ichimoku cloud |
| Ichimoku MACD | `strategies/ichimoku-macd/strategy.yaml` | Ichimoku + MACD confluence |
| Ichimoku Trend | `strategies/ichimoku-trend/strategy.yaml` | Ichimoku cloud crossover |
| MACD Foreign Flow | `strategies/macd-foreign-flow/strategy.yaml` | MACD + foreign flow divergence |
| MFI Oversold | `strategies/mfi-oversold/strategy.yaml` | MFI oversold bounce |
| OBV Trend | `strategies/obv-trend/strategy.yaml` | OBV divergence trend |
| RS Momentum | `strategies/rs-momentum/strategy.yaml` | Relative strength momentum |
| RSI Momentum | `strategies/rsi-momentum/strategy.yaml` | RSI extremes + SMA trend filter |
| Stochastic Trend | `strategies/stochastic-trend/strategy.yaml` | Stochastic + trend filter |
| Test Sentiment | `strategies/test-sentiment/strategy.yaml` | Sentiment rule integration test |
| Volume Spike | `strategies/volume-spike/strategy.yaml` | Volume spike breakout |
| Williams %R Bounce | `strategies/williams-r-bounce/strategy.yaml` | Williams %R oversold bounce |

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

### Concrete example: `saham inspect risk BBCA --explain`

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

### Concrete example: `saham fetch market BBCA --days 365 --provider idx`

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
| Domain | 64 | ~5,200 |
| Application | 64 | ~16,300 |
| Infrastructure | 63 | ~15,800 |
| Adapters | 29 | ~13,300 |
| Plugins | 13 | ~1,300 |
| Strategies | 16 | ~1,200 |
| **Total** | **~250** | **~53,000** |

---

## Key Architectural Rules

1. **Domain is pure** — zero external imports (stdlib only: `dataclasses`, `Decimal`, `date`, `Enum`). No network, no AI, no database.
2. **Use Cases orchestrate** — never contain business logic, only coordinate domain + infrastructure.
3. **Infrastructure implements ports** — never the reverse. Use case never imports infrastructure directly.
4. **Adapters are thin** — parse input, wire deps, call use case, format output. No business logic.
5. **Formula DSL is in Application layer** — not domain (it's a tool for composing indicators, not a business concept).
6. **AI is purely Infrastructure** — behind `AIExplainer`, `FormulaTranslator`, `StrategyTranslator` ports. Swappable, optional, testable.
