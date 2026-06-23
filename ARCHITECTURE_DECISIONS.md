# Architecture Decisions Record (ADR)

This document records **high-impact, cross-cutting architectural decisions** that define the structure, behavior, and long-term direction of this system.

These decisions are considered **binding** unless explicitly superseded by a new recorded decision.

---

## ADR-001: Deterministic-First Core

**Decision**
The core system must be deterministic by default.

**Implications**

* Given the same inputs and configuration, outputs must be identical.
* No hidden randomness or implicit state.
* Time, network, and AI variability must not affect core results.

**Rationale**
Trustworthy financial analysis requires reproducibility and auditability.

---

## ADR-002: Rule-First, AI-Optional Design

**Decision**
Rule-based logic is the primary decision mechanism. AI is an optional enhancement layer.

**Implications**

* System must work fully without AI enabled.
* AI may assist explanation, exploration, or augmentation.
* AI must not be the sole source of truth.

**Rationale**
Prevents hallucinated or non-auditable decisions.

---

## ADR-003: Hexagonal (Ports & Adapters) Architecture

**Decision**
The system follows Ports & Adapters (Hexagonal) architecture.

**Implications**

* Domain depends on nothing.
* Application orchestrates domain.
* Infrastructure implements ports.
* Adapters expose interfaces (CLI, bot, web).

**Rationale**
Ensures replaceability and long-term maintainability.

---

## ADR-004: Pure Domain Layer

**Decision**
Domain layer contains only business logic and domain models.

**Implications**

* No I/O, database, network, or AI calls.
* Fully unit-testable.

**Rationale**
Keeps reasoning isolated and stable.

---

## ADR-005: Local-First Persistence

**Decision**
System persists data locally by default.

**Implications**

* SQLite or DuckDB.
* Offline-capable after initial fetch.
* No mandatory cloud dependency.

**Rationale**
Reliability and user control.

---

## ADR-006: Market Data Provider Abstraction

**Decision**
All market data access goes through provider ports.

**Implications**

* Yahoo Finance, IDX APIs, or paid feeds are swappable.
* Domain never references specific providers.

**Rationale**
Avoid vendor lock-in.

---

## ADR-007: Indicator Initialization & Warm-Up Policy

**Decision**
Indicators must follow industry-standard initialization.

**Rules**

* No shortcut seeding (e.g., EMA first-price seed).
* SMA seed required where applicable.
* Indicators assume sufficient data.
* Warm-up handled in application/use-case layer.
* User-facing results exclude warm-up region.

**Rationale**
Matches TradingView / TA-Lib behavior and avoids start-point bias.

---

## ADR-008: Decoupled Fetch vs Analyze Data

**Decision**
Fetched data volume may exceed analyzed output.

**Implications**

* Over-fetch for correctness.
* Slice for presentation.

**Rationale**
Preserves mathematical integrity without burdening users.

---

## ADR-009: Config-Driven Behavior

**Decision**
Behavior differences are controlled via configuration, not code.

**Implications**

* Risk profiles
* Thresholds
* AI enable/disable

**Rationale**
Promotes flexibility without branching logic.

---

## ADR-010: Risk Profiles as Policy Layer

**Decision**
Risk profiles map analysis results to qualitative interpretation.

**Implications**

* Conservative, Balanced, Aggressive.
* No prediction or trading execution.

**Rationale**
Separates math from policy.

---

## ADR-011: Offline-Capable CLI as Primary Interface

**Decision**
CLI is the primary interface for Day-1.

**Implications**

* Bots, web, and mobile reuse same core.

**Rationale**
Fast iteration and automation.

---

## ADR-012: OSS Encapsulation Rule

**Decision**
Third-party libraries must be wrapped behind ports/adapters.

**Implications**

* No direct imports inside domain.

**Rationale**
Replaceability and stability.

---

## ADR-013: AI Agent Governance

**Decision**
AI development must follow Prompt Contract, DoD, and Task Template.

**Implications**

* No direct coding without task spec.
* Determinism-first.

**Rationale**
Prevents drift and chaos.

---

## ADR-014: Full-AI Mode (Explicit Bypass Mode) — DEFERRED

**Status:** Deferred — not implemented. Config stub at `config/full_ai.yaml` is empty (1 line, filename only). No code references exist.

**Decision**
The system may support a future **Full-AI Mode** where AI-generated analysis can bypass rule-based logic.

**Implications**

* Full-AI Mode must be explicitly enabled via configuration.
* Default mode remains deterministic, rule-first.
* Full-AI output must be clearly labeled as probabilistic.
* Rule-based and Full-AI modes must coexist without breaking architecture.

**Rationale**
Allows experimentation with advanced AI reasoning while preserving system trust and stability.

---

## ADR-015: Sentiment Analysis Classification

**Decision**
Sentiment analysis is classified into two categories:

* Deterministic sentiment (rule-based, keyword matching)
* AI-based sentiment (probabilistic, LLM-assisted)

**Implications**

* Deterministic sentiment lives in `infrastructure/sentiment/keyword_classifier.py`.
* `domain/indicators/sentiment_score.py` exists as a placeholder stub (0 lines) — deterministic sentiment was designed for but never placed in the domain layer.
* AI-based sentiment lives in `infrastructure/sentiment/ai_classifier.py` + `infrastructure/ai/sentiment_analyzer.py`.
* Composite provider (`infrastructure/sentiment/composite_provider.py`) merges multiple news sources.
* News sources (`google_news_provider.py`, `cnbc_indonesia_provider.py`, `kontan_provider.py`) are swappable implementations.
* Domain rules must not depend on raw text or LLM outputs.
* Sentiment is contextual input, not a source of truth.

**Rationale**
Prevents misuse of sentiment while enabling future expansion.

---

## ADR-016: Formula DSL (Domain-Specific Language for Indicators)

**Decision**
Define indicator logic using a custom AST-based formula language instead of hardcoded Python functions or third-party expression evaluators.

**Components** (all in `application/formula/`)

* `ast_nodes.py` — Node types representing formula operations (SMA, EMA, RSI, arithmetic, comparison).
* `tokenizer.py` — Lexer converting formula strings into tokens.
* `parser.py` — Parser building AST from token stream.
* `evaluator.py` — Recursive AST evaluator against candle data, supporting all core indicators.
* `validator.py` — Formula validation before evaluation.
* `application/rules/interpreter.py` — Runtime interpreter connecting formula evaluation to rule conditions.

**Implications**

* Formulas are portable: can be stored, shared, and versioned independently of code.
* Formulas can be generated by AI (`FormulaTranslator` port + `infrastructure/ai/formula_translator.py`) from natural language.
* Custom indicators (user-defined formulas) are stored in `config/formulas.yaml`.
* Formula validation is decoupled from evaluation: invalid formulas fail early.
* New indicator functions must be registered in both the evaluator and the validator.

**Rationale over alternatives**

| Alternative | Rejected because |
|-------------|------------------|
| SymPy / eval() | Security risk, no domain-specific indicator support |
| Hardcoded indicator functions per use case | Duplication, no user extensibility |
| Pandas-only expressions | Tight coupling to pandas, doesn't support the rule DSL |

**Rationale**
A custom DSL provides composability, safety (no eval()), and AI-generatability while keeping the domain layer pure.

---

## ADR-017: Plugin-Based Indicator Registration

**Decision**
Indicators can be registered at runtime via auto-discovered plugin files, not just hardcoded in `domain/indicators/`.

**Components**

* `domain/ports/indicator_plugin.py` — Port defining the plugin interface.
* `infrastructure/plugins/indicator_loader.py` — Loader that scans `plugins/` directories at startup.
* `application/services/indicator_registry.py` — Central registry making all indicators (built-in, plugin, formula) available to analysis.

**Implications**

* Plugin files live in `plugins/` at project root or custom path.
* Each plugin must implement the `IndicatorPlugin` port interface.
* Plugins can include a `.skill.yaml` sidecar for self-documentation.
* Plugins are auto-discovered once at startup and registered in the `IndicatorRegistry`.
* Built-in indicators (`domain/indicators/sma.py`, `ema.py`, `rsi.py`) are also registered through the same registry for uniform access.
* The registry is used by the formula evaluator, CLI commands, and rule interpreter.

**Rationale**
Enables third-party indicator development without modifying core code. Maintains the hexagonal architecture boundary by keeping plugin integration behind the `IndicatorPlugin` port.

---

## ADR-018: CLI Command Depth — `saham view broker` Exception

**Decision**
The CLI follows a "max 2 levels" depth rule (`saham <group> <command>`). The `saham view broker` sub-group is an explicit, documented exception at 3 levels (`saham view broker <subcommand>`).

**Affected commands**
`saham view broker status|flow|top|history|top-foreign|mappings`

**Rationale**
Broker data has multiple distinct display modes (flow, top buyers/sellers, history, foreign activity, mappings) that are all conceptually under one data source. Flattening these to `saham view flow`, `saham view top`, etc. would pollute the `view` namespace and lose the broker grouping signal. The `broker` sub-group is the right structural cut; the depth cost is accepted.

**Implications**
* No other `view` sub-groups may be introduced without a new ADR.
* New broker display commands are added under `view broker`, not at `view` level.
* All other `saham` command groups remain at max 2 levels.

---

## ADR-019: Unified Fetch Timestamp (`fetched_at: datetime`) on Cached Domain Value Objects

**Decision**
Every domain value object backed by a SQLite cache carries `fetched_at: datetime | None = None`.
Set to `datetime.now()` at fetch time, serialised as an ISO datetime string in the existing
`fetched_date` SQLite column, and round-tripped through `_read_cache()`.
Consumers derive `.date()` for day precision or `.strftime("%Y-%m")` for month precision.

**Implications**

* Single field name and type across all cached snapshot objects.
* No per-consumer ambiguity about data age — callers do not need to know which providers
  used `date` vs `datetime` granularity in storage.
* SQLite column names remain unchanged (`fetched_date` TEXT) — no schema migrations needed
  for the 6 existing providers; only `seasonality_cache` received a new `fetched_at` column.
* TTL checks use `substr(fetched_date, 1, 10)` or `datetime.fromisoformat()` to handle both
  old date-only strings and new ISO datetime strings in the same column, ensuring backward
  compatibility with rows cached before this change.

**Exceptions**

* `BandarDetectorSnapshot.session_date: date` — the session date is the semantic key for
  immutable end-of-day data, not a cache freshness indicator. Not changed.
* List-row objects (`InsiderTransaction`, `CorporateActionEvent`) — individual records are
  time-series data; the provider manages the batch fetch marker in SQLite. Not changed.
* API data dates (`AnalystConsensus.last_updated`, `ShareholdingComposition.report_date`) —
  these are response dates (when the API last updated the data), distinct from `fetched_at`
  (when we retrieved and cached it). Both coexist on the same object.

**Rationale**
A uniform `datetime` field gives callers full information (date, time) in one field without
forcing them to know the storage granularity of any particular provider. It also closes the
round-trip gap where three providers (`analyst`, `shareholding`, `seasonality`) stored the
timestamp in SQLite but never materialised it onto the returned domain object.

---

## ADR-020: CLI Adapter File Naming Convention

**Decision**
CLI command implementation files are named after their position in the command tree:
`{top_command}_{sub_command}_commands.py` for command files and
`{top_command}_{sub_command}_display.py` for display/formatting files.

Examples: `saham analyze swing` → `analyze_swing_commands.py`; `saham analyze regime` → `analyze_regime_commands.py`; swing-specific trade tools (`backtest-swing`, `size`) → `trade_swing_commands.py`.

**Rationale**
A flat CLI adapter directory becomes unreadable as the command surface grows. Embedding the command hierarchy in the filename makes ownership visible without opening the file, and prevents the silent mixed-group problem where one file serves both `saham analyze` and `saham trade` commands.

**Implications**

* New command files must follow this convention from creation.
* A file serving only one command group gets exactly one prefix segment (e.g., `analyze_swing_commands.py`).
* A display file paired with a command file mirrors its prefix (e.g., `analyze_swing_display.py`).
* Legacy cross-group files (`accumulation_commands.py`, `intraday_workflow_commands.py`) are grandfathered until explicitly refactored — do not rename them inline with feature work.
* Existing display files with the old naming (`swing_display.py`, `swing_analysis_display.py`, etc.) will be renamed in a dedicated pass.

**Exceptions**

* Files serving multiple top-level groups (legacy cross-group modules) keep their current names until explicitly split.
* Shared infrastructure not tied to a specific command (e.g., a `_swing_helpers.py`) may omit the top-command prefix.

---

## ADR-021: Strict Boundary Enforcement & Infrastructure Decoupling (Hexagonal Audit Clean-Up)

**Decision**
Strictly decouple pure business logic in domain and application layers from concrete infrastructure libraries (such as `sqlite3`, `PyYAML`, news scrapers, and filesystem annotation readers) by placing all database access and system-level operations behind abstract port interfaces.

**Implications**

* Domain and application use cases must never directly import database drivers, read config files from the filesystem, or hash rules directory files directly.
* Introduce dedicated port interfaces inside `application/ports/` and `domain/ports/` (e.g. `RulesLoader`, `UniverseSummaryProvider`, `AnnotationReader`, `RulesHasher`, `UniverseLoader`).
* Keep concrete library drivers encapsulated inside `infrastructure/` implementations mapping to these ports.

**Rationale**
Ensures that workflow and policy definitions remain pure and unpolluted by third-party drivers or implementation decisions. It protects the system from vendor lock-in, enables easy mocking in test suites, and lets us swap out persistence providers (e.g., SQLite to DuckDB) without modifying core business rules.

---

## ADR-022: IDX Regular Market Price Floor (Rp 50) Enforcements

**Decision**
Enforce the absolute Rp 50 regular market price floor in all pre-open and intraday trade calculations.

**Implications**

* Calculated stop losses are capped at Rp 50.
* Candidate pre-open screening must automatically filter out and skip tickers whose previous closing price is <= 50 or projected Indicative Equilibrium Price (IEP) <= 50.
* Ensure warning logs are generated when a candidate is excluded due to the price floor.

**Rationale**
Stocks trading at the Rp 50 floor price (e.g. GOTO) represent highly illiquid tickers ("gocian" stocks) with large seller queues and no committed buyers. Filtering them out at the start of the screening loop prevents the model from generating impossible stop-loss prices, preserves the mathematical validity of target risk-reward metrics, and reduces risk exposure to illiquid floor-locked assets.

---

*End of Architecture Decisions Record.*
