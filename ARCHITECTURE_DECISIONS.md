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
Rule-based logic is the primary decision mechanism. AI is an optional enhancement layer operating in three distinct tiers.

**AI Tiers**

| Tier | Role | Scope | Status |
|------|------|-------|--------|
| T1 Explainer | Narrate pre-computed engine results in natural language | `ExplainRiskUseCase`, `ExplainSignalUseCase` | Implemented |
| T2 Tuner | Propose engine parameter changes from historical attribution data | `SwingSignalTunerUseCase` | Planned (ADR-027) |
| T3 Proposer | Generate new strategy/formula/gate artifacts from natural language | `CreateStrategyFromIntentUseCase`, `CreateIndicatorFromIntentUseCase` | Implemented |

**Implications**

* System must work fully without AI enabled. All tiers are optional and must fail gracefully without propagating exceptions to the caller.
* T1 Explainer: AI reads a pre-computed `RiskAssessment` or `SignalAssessment` and returns a narrative. It does not influence scores or levels.
* T2 Tuner: AI reads historical attribution summaries (gate hit rates, signal accuracy, forward return correlations) and proposes a YAML config diff. Proposed changes require explicit human approval (`--apply` flag + confirmation). AI never applies changes autonomously.
* T3 Proposer: AI generates YAML artifacts (strategies, formulas). Artifacts are validated by the engine before use. AI output is not trusted until it passes engine validation.
* AI must not be the sole source of truth for any engine output.

**Rationale**
Prevents hallucinated or non-auditable decisions. The three-tier model captures the legitimate spectrum of AI assistance — from passive narration to active-but-human-gated parameter suggestion — without opening the door to autonomous decisions. See ADR-014 (REJECTED) for why "Full-AI Mode" (unconstrained bypass) was rejected.

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

* Risk gates
* Thresholds
* AI enable/disable

**Rationale**
Promotes flexibility without branching logic.

---

## ADR-010: Risk Gates as Policy Layer

**Decision**
Risk assessment is gate-based. A configured gate either fires or it does not,
producing `BLOCKED` or `OPEN`. Conservative/balanced/aggressive risk profiles
are retired from the current application because they no longer affect gate
outcomes.

**Implications**

* No prediction or trading execution — gates are deterministic policy only.
* Gate trigger thresholds (Piotroski F-score cutoff, market cap floor, liquidity floor, free float minimum, bandar distribution labels, technical gate thresholds) MUST be configurable in `config/risk_engine.yaml`.
* Each gate MUST declare an `enabled: bool` field in the YAML config. A gate with `enabled: false` is skipped entirely from the pipeline — no evaluation, no block decision. This supports backtesting, A/B comparison, and T2 Tuner proposals without code changes. See ADR-024 Engine Configurability Contract for the full gate YAML schema.
* Risk-engine YAML schema MUST be validated at startup via `yaml_loader.py`. Invalid config aborts startup with a clear error, not a silent fallback.
* Gate thresholds may be tightened based on market context (RISK_OFF/VOLATILE) — see ADR-029 for MarketContextEngine regime labels and integration rules.

**Implementation status (2026-06-29)**
`config/risk_engine.yaml` controls gate enablement and gate thresholds through
`create_risk_engine()`. The risk profile/sensitivity path and `--all` profile
comparison are removed.

**Rationale**
Separates math from policy. Config-driven thresholds enable the learning loop (ADR-027) to propose adjustments without requiring code changes, and enable calibration for IDX market specifics (ADR-028) without maintaining duplicate profile paths.

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

## ADR-014: Full-AI Mode (Explicit Bypass Mode) — REJECTED

**Status:** Rejected — 2026-06-24. Config stub `config/full_ai.yaml` deleted. No code references existed.

**Original decision (withdrawn)**
The system would support a future Full-AI Mode where AI-generated analysis could bypass rule-based logic.

**Why rejected**
"Bypass rule-based logic" contradicts the project's foundational philosophy: AI is the Author, the engine is the Validator+Executor, and YAML is the contract between them. A bypass mode collapses this separation. The legitimate use case this ADR was trying to address — AI-enhanced analysis — is fully covered by:
* ADR-002 T2 Tuner: AI proposes config parameter changes from historical attribution data; human approves before application
* ADR-027 Learning Loop: systematic feedback from backtest outcomes to engine parameters
* ADR-003 T3 Proposer: AI generates new strategy/formula YAML artifacts that are validated before use

**Rule**
No code path may allow AI output to bypass the deterministic rule engine. AI output is always input to a validator, never a direct output to the user as a risk or signal decision.

**Superseded by**
ADR-002 (T2 Tuner tier), ADR-027 (Learning Loop), ADR-003 (Hexagonal validation boundary).

---

## ADR-015: Sentiment Analysis Classification

**Decision**
Sentiment analysis is classified into two categories:

* Deterministic sentiment (rule-based, keyword matching)
* AI-based sentiment (probabilistic, LLM-assisted)

**Implications**

* Deterministic sentiment lives in `infrastructure/sentiment/keyword_classifier.py`.
* Empty domain placeholder files are not kept; deterministic sentiment was designed for but never placed in the domain layer.
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

Date naming convention:

* `snapshot_date` — the date a computed assessment/evidence snapshot represents.
* `session_date` — an exchange trading session key for immutable market-session data.
* `report_date` — an issuer/API filing or reporting date.
* `as_of_date` — a caller-supplied evaluation cutoff date, especially for replay/backtest.
* `fetched_at` — the timestamp when data was retrieved and cached.

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
* Legacy cross-group files are not the target shape. Split them when a focused command-group cleanup is already in scope; do not rename them as incidental churn in unrelated feature work.
* Accumulation and swing command/display files already follow this convention (`screen_accum_commands.py`, `trade_accum_commands.py`, `analyze_accum_commands.py`, `analyze_swing_display.py`, `trade_swing_display.py`).

**Exceptions**

* Files serving multiple top-level groups may keep their current names until a dedicated split is made.
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

## ADR-023: Codebase Directory and Use Case File Naming Standards

**Decision**
Establish strict layout and naming standards for the data directory structure, journals, and application use case files.

**Directory Structure Standards**
To separate concerns and avoid polluting the repository root:
* Databases must live under `data/db/` (e.g., `data/db/data.db`).
* Interactive sessions, temporary screeners, and state markers must live under `data/session/` (e.g., `data/session/.last-session.json`, `data/session/.last-confirmation.json`).
* Miscellaneous raw payloads, spy outputs, and developer debug dumps must live under `data/debug/`.
* Running trade/order book tracking files must be organized under `data/opening/YYYYMMDD/` for the opening session loop.
* Journal files (e.g., `journals/intraday_confirmations.csv`, `journals/pre_open.csv`, `journals/trades.jsonl`) must be stored under the `journals/` directory and use snake_case naming.

**File Naming Standards**
* **Application Layer**: To explicitly identify the layer and purpose of business logic modules, all use case files under `src/application/use_case/` must use the suffix `_use_case.py` (e.g., `pre_open_screen_use_case.py`, `assess_risk_use_case.py`).
* **CLI Adapters**: Command modules and formatting displays follow the `{top_group}_{sub_group}_commands.py` and `{top_group}_{sub_group}_display.py` conventions established in ADR-020.

**Rationale**
Standardizing use case suffixes prevents namespace collisions, preserves hexagonal architecture visibility, and aligns with professional clean-architecture conventions. Isolating databases, session state files, and debug files under structured subdirectories under `data/` prevents repository pollution and ensures predictable local-first state storage.

---

## ADR-024: Signal Engine and Risk Engine as First-Class Application Services

_Date: 2026-06-23 · Revised: 2026-06-24 · Context: crystallised from AGY risk methodology improvements (Phases A–E); Signal Engine architecture added in revision_

**Decision**
Signal Engine and Risk Engine are designated first-class application services with distinct, orthogonal responsibilities. Neither is an implementation detail of a CLI adapter or a use-case function body. Both must exist as symmetric, injectable, independently testable services.

---

### Risk Engine

**Answers:** "Are there conditions that block or disqualify acting on this stock?"

Owns: 3-tier gate pipeline (structural → technical rules → execution), Piotroski-based fundamental quality, liquidity screening, float structure, bandar distribution conflict detection.

Output cadence: per week / per quarter (gate inputs are slow-moving).

**Interface (`src/application/services/risk_engine.py`):**
- `assess(ticker, as_of_date)` — self-fetches enrichment via injected providers
- `assess_with_context(ticker, gate_context)` — pipeline path, avoids N+1 in screener loops
- `assess_request(request)` — advanced path accepting full `AssessRiskRequest`
- `assess_trend(request, days)` — trend view

**Factory:** `create_risk_engine(db_path, with_enrichment)` in `src/application/services/bootstrap.py`. All gate instantiation and configuration is owned by the factory. Callers never instantiate `RiskGate` subclasses directly.

**Output:** `RiskAssessment` — `risk_level_name`, `confidence`, `gate_triggered`, `rationale: tuple[str, ...]`, `snapshot_date`

---

### Signal Engine

**Answers:** "How strong and well-aligned are the factors supporting entry?"

Owns: composite signal score (weighted sum of 6 factors: bandar intensity, foreign flow quality, insider activity (net buy direction), seasonality edge, analyst consensus, forward EPS valuation) and entry quality classification. Screener-specific setup gates remain in screener policy, not in SignalEngine.

Output cadence: per session (signal factors are fast-moving).

**Interface (`src/application/services/signal_engine.py`):**
- `evaluate(ticker, as_of_date)` — self-fetches enrichment via injected providers
- `evaluate_with_context(ticker, signal_context)` — pipeline path, avoids N+1 in screener loops
- `evaluate_request(request)` — advanced path accepting full `AssessSignalRequest`

**Factory:** `create_signal_engine(db_path, with_enrichment)` in `src/application/services/bootstrap.py`. All provider injection and weight configuration is owned by the factory.

**Output:** `SignalAssessment` — `score: int (0–100)`, `strength: SignalStrength (STRONG/MODERATE/WEAK)`, `entry_quality: EntryQuality (ENTER/WATCH/AVOID)`, `breakdown: tuple[tuple[str, float], ...]`, `rationale: tuple[str, ...]`

**Signal policy** is read from `config/signal_engine.yaml`: factor enablement, weights, classification thresholds, missing-data defaults, enrichment lookbacks, upstream input mapping, and factor-internal scoring thresholds. Default weights: bandar 20%, foreign flow 20%, insider activity 20%, seasonality 15%, analyst consensus 15%, forward EPS 10%. See Engine Configurability Contract below for on/off toggle semantics.

---

### Orthogonality Rule

A strong signal does NOT imply low risk. Low risk does NOT imply a strong signal. Both engines are evaluated independently. A combined verdict is derived by `AssessTradeSetupUseCase` into a `TradeSetup` value object (see ADR-026) — neither engine reads the other's output.

---

### Engine Configurability Contract

Every component of both engines — signal factors and risk gates — MUST support individual on/off toggling and full parameter configuration via dedicated engine config files. Signal factors live in `config/signal_engine.yaml`; risk gates and profiles live in `config/risk_engine.yaml`. Workflow policy stays outside engine config: accumulation discovery in `config/accumulation_screener.yaml`, accumulation audit/learning measurement in `config/accumulation_audit.yaml`, setup gates in `config/swing_setups.yaml`, regime targets in `config/swing_targets.yaml`, swing backtest execution assumptions in `config/swing_backtest.yaml`, analyze-swing workflow defaults in `config/analyze_swing.yaml`, and swing overlays in `config/swing_risk_policy.yaml`.

#### YAML Schema

**`config/signal_engine.yaml`**

```yaml
signal_engine:
  classification:
    strong_min_score: 70
    moderate_min_score: 45
  missing_data:
    neutral_score: 50.0
    coverage_warning_missing_factors: 3
  enrichment:
    insider_lookback_days: 90
  input_mapping:
    foreign_flow_score:
      max_score: 120.0
      clamp: true
  scoring:
    bandar:
      mandatory_signal_count: 3
      signal_score_unit: 2
      default_max_range: 6
    seasonality:
      tailwind_min_avg_return_pct: 0.0
      tailwind_min_win_rate_pct: 50.0
    analyst:
      buy_score_max_points: 60.0
      upside_score_max_points: 40.0
      upside_cap_pct: 30.0
    forward_pe:
      very_cheap_pe: 10.0
      cheap_pe: 15.0
      fair_pe: 20.0
      expensive_pe: 30.0
  factors:
    bandar_intensity:
      enabled: true
      weight: 0.20
    foreign_flow_quality:
      enabled: true
      weight: 0.20
    insider_activity:
      enabled: true
      weight: 0.20
    seasonality_edge:
      enabled: true
      weight: 0.15
    analyst_consensus:
      enabled: true
      weight: 0.15
    forward_valuation:
      enabled: true
      weight: 0.10
```

**`config/risk_engine.yaml`**

```yaml
risk_engine:
  indicators:
    sma_period: 20
    ema_period: 20
    rsi_period: 14
    history_days: 365
  market_context_gate:
    enabled: true
    block_when_gate_tightening: true
  gates:
    fundamental:
      enabled: true
      piotroski_min: 4
      missing_data_action: skip
      triggered_confidence: 100
    liquidity:
      enabled: true
      market_cap_floor_idr: 1_000_000_000_000
      median_tx_floor_idr: 5_000_000_000
      missing_data_action: skip
      triggered_confidence: 100
    free_float:
      enabled: true
      min_free_float_pct: 15.0
      missing_data_action: skip
      triggered_confidence: 100
    bandar:
      enabled: true
      distribution_labels: ["Small Dist", "Big Dist"]
      missing_data_action: skip
      triggered_confidence: 80
    technical:
      block_when_bearish: true
      missing_data_action: skip
      evaluator:
        rsi_overbought: 70.0
        rsi_oversold: 30.0
```

#### On/Off Semantics

| Engine | Component disabled | Effect |
|--------|--------------------|--------|
| Signal | factor `enabled: false` | Factor excluded from scoring; its weight redistributes to remaining enabled factors (see renormalization rule) |
| Risk | gate `enabled: false` | Gate skipped entirely; pipeline continues to the next gate as if the gate does not exist |

**`enabled: false` is NOT the same as `weight: 0`.** A weight-zero factor still participates in normalization, consuming 0% of the score range but affecting no outcome. A disabled factor is removed from the active set entirely, allowing the remaining factors to own the full 0–100 range.

#### Weight Renormalization Rule (Signal Engine)

When one or more signal factors are disabled, the engine renormalizes the declared weights of the active factors so their sum equals 1.0:

```
effective_weight(f) = declared_weight(f) / sum(declared_weight(g) for g in enabled_factors)
```

**Example:** If `forward_valuation` (10%) is disabled, the remaining five factors divide by 0.90 — bandar becomes 22.2%, foreign flow 22.2%, insider activity 22.2%, seasonality 16.7%, analyst consensus 16.7%. Score range stays 0–100.

#### Factory Responsibility

`create_signal_engine()` and `create_risk_engine()` in `src/application/services/bootstrap.py` are the sole owners of config loading. They parse the YAML, apply `enabled` filtering, compute renormalized weights, and inject resolved configuration into the engine. No use case or adapter reads engine config YAML directly.

#### Swappability Rule

A new signal factor is added to `AssessSignalUseCase` as a scoring method and declared in the YAML schema. Enabling it via `enabled: true` brings it into the scoring pipeline without any other code change. Factors are swappable at the YAML level; their implementation is in the use case.

---

**Implications**

* `AccumulationScreenUseCase` MUST delegate signal scoring to `signal_engine.evaluate_with_context()` — inline `_composite_score()` at line ~358 is a migration target, not a long-term design.
* `SwingAnalysisWorkflowUseCase` MUST accept both engines via injection, not instantiate gates directly.
* CLI adapters call `engine.assess_request()` / `engine.evaluate_request()`, never manually wire gates or providers.
* `*_with_context()` MUST be used by all screening pipelines to avoid N+1 provider fetches. Callers build the context once from pre-loaded candidate data.
* The unified display layer (`risk_display.py`, `signal_display.py`) is the only place either engine's output is formatted for CLI. Use cases and engines return domain objects, not strings.

**Rationale**
AGY risk Phases A–E revealed that per-adapter gate wiring produces silent failure modes (missing gates, `Risk=—` display). A centralised `RiskEngine` service with factory eliminated this class of bug. The same pattern must apply to the Signal Engine to prevent a parallel class of silent failures where signal scoring logic silently diverges across `AccumulationScreenUseCase`, `SwingAnalysisWorkflowUseCase`, and future commands. See ADR-025 for full Signal Engine specification.

---

## ADR-025: SignalEngine Architecture

_Date: 2026-06-24 · Context: Signal Engine formalized as first-class service, parallel to RiskEngine (ADR-024)_

**Decision**
`SignalEngine` is a first-class application service in `src/application/services/signal_engine.py`. It is the sole owner of all signal scoring logic. No use case, adapter, or CLI command may compute a composite signal score outside this service.

**Value Object: `SignalAssessment`** (`src/domain/value_objects/signal_assessment.py`)

```python
@dataclass(frozen=True)
class SignalAssessment:
    ticker: str
    score: int                         # 0–100 weighted composite
    strength: SignalStrength           # STRONG / MODERATE / WEAK
    entry_quality: EntryQuality        # ENTER / WATCH / AVOID
    breakdown: tuple[tuple[str, float], ...]  # factor name/value pairs; use breakdown_dict for dict access
    rationale: tuple[str, ...]         # ordered explanations
    snapshot_date: date
```

```python
class SignalStrength(Enum):
    STRONG = "STRONG"
    MODERATE = "MODERATE"
    WEAK = "WEAK"

class EntryQuality(Enum):
    ENTER = "ENTER"       # score ≥ enter_threshold (default 65) AND strength STRONG
    WATCH = "WATCH"       # score ≥ watch_threshold (default 40) OR strength MODERATE
    AVOID = "AVOID"       # score < watch_threshold OR strength WEAK
```

**Signal Context: `SignalContext`** (parallel to `GateContext` for RiskEngine)

```python
@dataclass(frozen=True)
class SignalContext:
    ticker: str
    snapshot_date: date
    bandar_broad_score: float | None            # 0–(6+optional)*2, mapped to 0–1 by engine
    bandar_max_range: int                       # denominator for bandar_broad_score normalization
    foreign_flow_quality: float | None          # 0.0–1.0 (from accumulation stream)
    insider_net_buy_ratio: float | None         # -1.0 to 1.0 (negative = net selling, positive = net buying)
    seasonality_win_rate: float | None          # 0.0–100.0 (pct of months positive for this ticker)
    seasonality_avg_return_pct: float | None    # e.g. 2.5 = 2.5% avg monthly return this season
    analyst_buy_pct: float | None               # 0.0–1.0
    analyst_upside_pct: float | None            # e.g. 15.0 = 15% upside to consensus price target
    forward_pe: float | None                    # forward P/E ratio for valuation normalization
```

**`piotroski_f_score` is intentionally absent from `SignalContext`.** It remains in `GateContext` (RiskEngine path only). Passing it to SignalEngine would re-introduce the double-counting problem that `insider_activity` was added to solve.

**Signal Factors and Default Weights** (configurable via `config/signal_engine.yaml`; full on/off toggle semantics in ADR-024 Engine Configurability Contract):

| Factor | Default Weight | Enabled | Source |
|--------|---------------|---------|--------|
| `bandar_intensity` | 20% | true | `bandar_broad_score` mapped to 0–1 |
| `foreign_flow_quality` | 20% | true | accumulation stream `flow_quality` (0.0–1.0) |
| `insider_activity` | 20% | true | `insider_net_buy_ratio`: net insider buy value / total tx value (positive = accumulating) |
| `seasonality_edge` | 15% | true | `seasonality_win_rate` and `seasonality_avg_return_pct` |
| `analyst_consensus` | 15% | true | `analyst_buy_pct` × 0.6 + `analyst_upside_pct` normalized × 0.4 |
| `forward_valuation` | 10% | true | `forward_pe` normalized against sector median |

**Why `piotroski_quality` was removed:** The Piotroski F-score already gates at the `fundamental_gate` in RiskEngine (F-score ≤ 3 → HIGH_RISK). Using the same score as a 20% quality factor in SignalEngine double-counts the same underlying data across both engines. `insider_activity` replaces it — insider net buy direction is a distinct entry-opportunity signal not captured by any RiskEngine gate, providing genuine additive signal.

**Implications**

* `src/application/use_case/accumulation_screen_use_case.py` delegates SignalAssessment scoring to `signal_engine.evaluate_with_context()`. Foreign-flow scoring is separate `ForeignFlowScoreBreakdown` context and the public screen filter is `--min-foreign-flow-score`; see ADR-030.
* `src/application/use_case/swing_analysis_workflow_use_case.py` reuses the candidate SignalAssessment when available, otherwise delegates to `signal_engine.evaluate_with_context()` or `signal_engine.evaluate()`.
* `create_signal_engine(db_path, with_enrichment)` factory in `src/application/services/bootstrap.py` injects providers, parses `config/signal_engine.yaml` (`signal_engine.factors` block), applies `enabled` filtering, and computes renormalized weights before constructing the engine. See ADR-024 Engine Configurability Contract for the full schema and renormalization rule.
* `evaluate_with_context(ticker, SignalContext)` MUST be used by screening loops to avoid N+1 provider fetches.
* Unit tests must test `SignalEngine` in isolation with injected mock providers — no Stockbit browser in tests.
* `signal_display.py` in `src/adapters/cli/` is the only place `SignalAssessment` is formatted for CLI output.

**Implementation reference:** `docs/claude_signal_risk_230626.md` R1–R4 plan.

---

## ADR-026: Risk+Signal Pipeline Composition

_Date: 2026-06-24 · Updated: 2026-06-25 · Context: Defines how SignalEngine and RiskEngine outputs combine into an action verdict_

**Decision**
Features presenting a complete trade recommendation MUST compose both engine outputs through a `TradeSetup` domain value object, produced by `AssessTradeSetupUseCase`. The composition rule is deterministic and lives in the application layer (use case), not the domain value object itself.

> **Implementation note:** The original plan named `CombinedAssessment` / `ActionRecommendation`. During implementation the design evolved: (1) composition logic belongs in an application use case, not a static domain method; (2) `BLOCKED` was split into two distinct states to separate structural disqualifiers (permanent, skip entirely) from execution-quality gates (re-check if market conditions change).

**Value Object: `TradeSetup`** (`src/domain/value_objects/trade_setup.py`)

```python
@dataclass(frozen=True)
class TradeSetup:
    ticker: str
    snapshot_date: date
    action: SetupAction
    signal_score: int                    # final 0-100 score from SignalAssessment
    signal_score_raw: int                # pre-regime score, when available
    signal_strength: SignalStrength      # from SignalAssessment
    risk_level: RiskLevel                # from RiskAssessment
    blocking_gates: tuple[str, ...]      # gate labels; empty when not BLOCKED_*
    regime: MarketRegime | None          # None when MCE not used
    signal_multiplier: float             # 1.0 = no MCE impact; <1.0 = headwind
    gate_tightening: bool                # True when regime tightened gates
    rationale: str
```

**Enum: `SetupAction`** (`src/domain/value_objects/trade_setup.py`)

```python
class SetupAction(Enum):
    ENTER             = "ENTER"              # STRONG signal + LOW_RISK [+ favorable regime]
    WATCH             = "WATCH"              # MODERATE signal OR MODERATE risk
    AVOID             = "AVOID"              # WEAK signal
    BLOCKED_EXECUTION = "BLOCKED_EXECUTION"  # execution-quality gate fired (re-check later)
    BLOCKED_STRUCTURAL= "BLOCKED_STRUCTURAL" # structural gate fired (skip entirely)
```

**BLOCKED split rationale**

`gate_is_structural: bool | None` on `RiskAssessment` carries the gate type:
- `True` → structural gate (e.g. FundamentalGate, LiquidityGate, FreeFloatGate, or MCE regime gate when applied by RiskEngine) → `BLOCKED_STRUCTURAL`: the instrument is fundamentally unsuitable right now.
- `False` → execution gate (e.g. BandarGate) → `BLOCKED_EXECUTION`: the current execution/flow environment is poor; conditions may change.
- `None` → no gate triggered (normal path).

**Composition Rule** (`AssessTradeSetupUseCase`, deterministic, no I/O):

```
if any gate triggered and gate_is_structural == True:
    → BLOCKED_STRUCTURAL
elif any gate triggered and gate_is_structural == False:
    → BLOCKED_EXECUTION
elif signal.entry_quality == ENTER:
    → ENTER
elif signal.entry_quality == WATCH:
    → WATCH
elif signal.strength == WEAK:
    → AVOID
else:
    → WATCH
```

**MCE Regime Modifier**
`MarketContextEngine` output is optional. Current code records `regime`, `signal_multiplier`, and `gate_tightening` in `TradeSetup` when the caller supplies `market_context`.

Engine-level adjustment is owned by the engines, not by `AssessTradeSetupUseCase`:
- `SignalEngine.evaluate(..., market_context=...)` applies `score × signal_multiplier` and caps ENTER to WATCH when `gate_tightening=True`.
- `RiskEngine.assess(..., market_context=...)` marks HIGH_RISK assessments with a `regime:{REGIME}` structural gate when `gate_tightening=True`.

Callers that compute signal/risk before market context is available may still pass market context to `AssessTradeSetupUseCase`; in that case the regime is recorded in the verdict rationale, but signal/risk scores are not retroactively recomputed.

**Implications**

* `AssessTradeSetupUseCase` (`src/application/use_case/assess_trade_setup_use_case.py`) is the single composition point. It is stateless — instantiated inline as `AssessTradeSetupUseCase().execute(request)`.
* `SwingAnalysisWorkflowUseCase` computes `trade_setup` after signal, risk, and `market_regime` are all resolved. Current implementation passes `market_context=market_regime` to the composer for verdict context; engine-level MCE adjustment requires passing the same context into `SignalEngine`/`RiskEngine` before composition.
* `AccumulationScreenUseCase` computes `trade_setup` per candidate inside `_run_risk_funnel()` — the only scope where `AssessRiskResponse` (not just `RiskAssessment`) is still in scope. No `market_context` (screener doesn't use MCE).
* `SwingAnalysisWorkflowResponse.trade_setup` and `AccumulationCandidate.trade_setup` are both `TradeSetup | None` (None when signal or risk are absent).
* CLI display: color-coded action cell (bold green=ENTER, yellow=WATCH, red=AVOID, bold red=BLOCKED_*) in both `screen accum` table and `analyze swing` Panel 1 Signal Snapshot.
* `TradeSetup.to_dict()` is the canonical serialization for JSON output and the ADR-027 learning journal.

**Rationale**
Without a formal composition rule, every CLI command that shows both signal and risk invents its own merging logic — creating divergent action columns in `screen accum`, `analyze swing`, and future commands. `AssessTradeSetupUseCase` ensures the same ENTER/WATCH/AVOID/BLOCKED logic everywhere. The BLOCKED split enables the learning loop (ADR-027) to attribute outcomes separately: structural blocks have no actionable signal, execution blocks may yield profitable retries.

---

## ADR-027: Risk/Signal Learning Loop

_Date: 2026-06-24 · Context: Extends the pre-open learning loop pattern (already implemented) to the swing domain_

**Decision**
The system provides a four-phase learning loop for the swing domain that records engine outputs, grades forward outcomes, attributes performance to engine components, and produces AI-assisted parameter suggestions. Human approval is required at every change boundary.

**Phases**

| Phase | CLI Command | What it does |
|-------|-------------|-------------|
| Record | `swing learn record` | At trade entry, persist `TradeSetup` snapshot to journal |
| Grade | `swing learn grade --days N` | Fetch forward return for each recorded entry; compute WIN/LOSS/NEUTRAL |
| Attribute | `swing learn attribute` | Correlate outcomes with gate triggers and signal factor breakdown |
| Tune | `swing learn tune [--apply]` | AI T2 Tuner proposes YAML threshold diff; `--apply` writes after confirmation |

**Journal:** `journals/swing_signal_outcomes.jsonl`

```json
{
  "ticker": "BBCA",
  "entry_date": "2026-06-24",
  "entry_price": 9100,
  "action": "ENTER",
  "signal_score": 72,
  "signal_score_raw": 72,
  "signal_strength": "STRONG",
  "risk_status": "OPEN",
  "blocking_gates": [],
  "regime": null,
  "signal_multiplier": 1.0,
  "gate_tightening": false,
  "rationale": "STRONG signal, LOW_RISK. No active gates.",
  "signal_breakdown": {"bandar_intensity": 0.85, "foreign_flow_quality": 0.70, ...},
  "risk_confidence": 100,
  "outcome_date": null,
  "exit_price": null,
  "return_pct": null,
  "outcome": null
}
```

Note: the top-level fields mirror `TradeSetup.to_dict()` exactly; `signal_breakdown` and `risk_confidence` are appended from the underlying engine assessments. The journal record is immutable after writing — outcome fields are populated by `swing learn grade`.

**Attribution Rules**
- Attribution requires minimum 30 graded outcomes before generating suggestions (enforce in `SwingSignalTunerUseCase`).
- Attribution is statistical correlation, not causal proof. AI tuner output must include a confidence note.
- The attribution summary must include `sample_quality`, a deterministic readiness
  gate with minimum sample size, completed-trade count, candidate-observation
  count, readiness booleans, status, and explanatory notes. Tuner implementations
  must not propose YAML changes from `INSUFFICIENT_SAMPLE` summaries.
- Swing backtest attribution has two scopes: completed portfolio trades
  (`group_stats`) and screened-candidate forward-return observations
  (`candidate_group_stats`). Candidate observations exist to reduce
  survivorship bias when tuning setup and risk gates; they must not be treated
  as executed trades or live entry logic.
- The attribution summary must include `tuning_targets`, a deterministic
  allowlist mapping each emitted attribution dimension to its source field,
  source scope, YAML target paths, allowed use, and warning if the evidence is
  biased. Tuner implementations must reject dimensions not present in this map.
- Gate attribution: for each gate, compute `gated_win_rate` (forward return of gated candidates) vs. `passed_win_rate`. If `gated_win_rate > passed_win_rate + 10%`, the gate is being too aggressive and the threshold should consider relaxing. If a gate is routinely not triggered across 30+ outcomes and shows no correlation with outcomes, the Tuner may propose `enabled: false`.
- Factor attribution: for each factor in `signal_breakdown`, compute correlation of the factor's per-trade score with the forward return. If a factor shows consistently near-neutral contribution (factor score within ±0.1 of the 0.5 neutral baseline across 30+ outcomes), the Tuner may propose `enabled: false` to remove it from scoring. If a previously disabled factor is re-enabled and outcomes improve, the Tuner may propose keeping it enabled and increasing its weight.

**AI Tuner (T2) Constraints**
- Input: attribution summary JSON (not raw candles, not raw journal entries)
- Output: proposed YAML diff targeting only deterministic tuning files that map
  directly to attribution dimensions:
  `config/signal_engine.yaml` for signal factor/classification changes,
  `config/risk_engine.yaml` for risk gate changes,
  `config/swing_setups.yaml` for setup gate changes,
  `config/market_context_engine.yaml` / `config/swing_targets.yaml` for regime
  context and regime-adaptive exit changes, and `config/swing_backtest.yaml`
  for replay assumptions and reporting buckets.
- AI never reads current config directly — the use case provides a structured summary
- Proposed diffs may include: numeric threshold adjustments (gate thresholds, signal weights), and component enable/disable toggles (`enabled: true/false` per factor or gate). The full Engine Configurability Contract in ADR-024 defines all valid diff targets.
- `--apply` flag writes proposed changes after user confirmation prompt; without `--apply`, proposals are printed only
- Applied changes are recorded in `journals/swing_tuning_log.jsonl` with timestamp, source attribution, and which parameters changed

**Implications**

* `src/application/services/swing_signal_journal.py` — new service, owns journal read/write
* `src/application/use_case/swing_signal_tuner_use_case.py` — new use case, AI T2 Tuner
* CLI: `src/adapters/cli/swing_learn_commands.py`, `swing_learn_display.py`
* Persistence: `journals/swing_signal_outcomes.jsonl`, `journals/swing_tuning_log.jsonl`
* `SwingBacktestUseCase` must apply `RiskEngine` gate evaluation during walk-forward simulation (see also ADR-026) to produce gate attribution data in `BacktestResult`
* The `grade` phase fetches forward returns from cached candle data — no new network calls required
* Minimum sample size of 30 outcomes is a domain rule, not a config value

**Rationale**
The pre-open learning loop (`learn snapshot → track → grade → tune`) is the best adaptive infrastructure in the codebase. The same four-phase pattern applied to the swing domain closes the gap between backtested performance and live engine calibration. AI's T2 Tuner role (propose, not apply) keeps humans in the loop while leveraging AI's ability to read statistical patterns across many trades.

---

## ADR-028: IDX Market Microstructure Rules

_Date: 2026-06-24 · Context: Indonesia Stock Exchange structural constraints that must be enforced in domain logic_

**Decision**
Domain and application layer logic must respect six IDX-specific market microstructure constraints. These are enforced as domain value object functions or gate context fields, never as adapter-layer heuristics.

---

### Rule 1: Tick Size Compliance

**IDX tick table (Regulation No. KEP-00066/BEI/07-2020):**

| Price Range (Rp) | Tick Size (Rp) |
|------------------|----------------|
| < 200 | 1 |
| 200 – 499 | 2 |
| 500 – 1,999 | 5 |
| 2,000 – 4,999 | 10 |
| ≥ 5,000 | 25 |

**Rule:** All computed price levels (entry, stop loss, target) from `PositionSizer` MUST be rounded to the nearest valid tick using `round_to_tick(price)` (round down for stops, round up for targets to be conservative).

**Implementation:** `src/domain/value_objects/tick_size.py` — pure function, no I/O. Used by `src/application/services/position_sizer.py`.

---

### Rule 2: Price Floor (existing — ADR-022)

Rp 50 absolute floor. No changes — already enforced.

---

### Rule 3: Auto-Rejection Band Proximity

**IDX rule:** Orders outside ±35% of previous close are auto-rejected (price ≥ Rp 200) or ±25% (price < Rp 200).

**Rule:** `GateContext` MUST carry `price_vs_upper_rejection_pct: float | None` (% distance to upper rejection band). When a stock has moved ≥ 25% intraday, `LiquidityGate` adds an advisory rationale note (non-blocking). Proximity ≥ 30% of the band is a MODERATE downgrade advisory.

---

### Rule 4: Foreign Ownership Cap Saturation

**IDX rule:** Most stocks cap foreign ownership at 49%. Banking and strategic sectors have lower sector-specific caps.

**Rule:** `SignalContext` MUST carry `foreign_ownership_pct: float | None` and `foreign_ownership_cap_pct: float | None`. When `foreign_ownership_pct / foreign_ownership_cap_pct > 0.92` (within 8% of cap) AND the primary signal driver is foreign flow (`foreign_flow_quality` is the top-contributing factor), the `SignalEngine` attenuates the foreign flow weight by 50% and adds a cap-proximity note to rationale.

**Source:** `StockbitShareholdingProvider` → `foreign_ownership_pct`. `foreign_ownership_cap_pct` is a sector lookup table (hardcoded: 49% default, 33% for media/banking where applicable).

---

### Rule 5: Bandar Score Granularity

**Current state:** `BandarGate` uses `five_day_accdist` label matching. The stale `bandar_is_distributing` boolean has been removed from `GateContext` because it did not affect gate behavior.

**Future rule:** `GateContext` may add `bandar_five_day_score: int | None` (-9 to +9). `BandarGate` should compare `bandar_five_day_score ≤ distribution_threshold` where `distribution_threshold` is configurable in `config/risk_engine.yaml` (default: -2). Score of -1 is treated as noise and does not trigger the gate.

**Migration:** `StockbitBandarDetectorProvider` already returns label data. Numeric score wiring remains a future enhancement; until then, label matching remains authoritative.

---

### Rule 6: T+2 Settlement Risk

**IDX rule:** Settlement is T+2. For thin-float stocks with high foreign ownership near the cap, large foreign exits at T can create forced selling at T+2 as counterparties scramble to cover.

**Rule:** When `free_float_pct < 20%` AND `foreign_ownership_pct > 35%`, `FreeFloatGate` adds a settlement-risk advisory to rationale (non-blocking, informational). It does not change `risk_level` unless `free_float_pct < 15%` (which already triggers HIGH_RISK).

---

**Implications**

* `src/domain/value_objects/tick_size.py` — new pure domain function
* `src/application/services/position_sizer.py` — apply `round_to_tick()` to all price levels
* `src/domain/rules/risk_gate.py` — `GateContext` removed `bandar_is_distributing`; future work may add `bandar_five_day_score`, `price_vs_upper_rejection_pct`
* `src/domain/rules/bandar_gate.py` — currently label-based; future work may compare numeric score vs. threshold
* `src/domain/value_objects/signal_assessment.py` — `SignalContext` adds `foreign_ownership_pct`, `foreign_ownership_cap_pct`
* `src/application/services/bootstrap.py` — construct updated `GateContext` from enrichment data
* Tests must not reference removed `GateContext(bandar_is_distributing=...)`

**Rationale**
Professional-grade IDX tools (Bloomberg PORT with IDX data, local tools like RTI Business, Stockbit Pro) all respect these structural constraints. Ignoring tick sizes causes computed stop-loss levels to be invalid on exchange. Ignoring auto-rejection bands creates unrealistic exit scenarios in backtest. Ignoring foreign cap saturation overstates the longevity of foreign flow signals in near-cap stocks.

---

---

## ADR-029: Market Context Engine (MCE) — Third First-Class Application Service

**Status:** Accepted
**Date:** 2026-06-24

---

### Context

ADR-024 introduced SignalEngine and RiskEngine as first-class application services. Neither answered the macro question: *"Is the environment favorable right now?"* ADR-026 stated that gate thresholds should tighten based on `market_regime`, but left the mechanism unimplemented.

The existing `MarketRegimeUseCase` (7 binary 0/1 signals, IDX-internal only, no weighting) was too crude — a single bad candle could flip the signal, and the scores carried no graded information. It was replaced in full.

---

### Decision

**MCE is the third first-class engine pillar**, parallel to SignalEngine and RiskEngine.

| Property | SignalEngine | RiskEngine | **MarketContextEngine** |
|----------|-------------|------------|------------------------|
| Input | Per-stock enrichment | Per-stock gates | Cross-market + IDX breadth |
| Output | `AssessSignalResponse` | `AssessRiskResponse` | `MarketContext` |
| Layer | Application | Application | Application |
| Config | `signal_engine.yaml` | rule YAML | `market_context_engine.yaml` |
| Persistence | No | No | `market_context_snapshots` |

---

### Key Decisions

#### 1. MarketRegimeUseCase is superseded for user-facing regime analysis
The old 7-signal binary use case is no longer the implementation behind `saham analyze regime`. `MarketContextEngine` delegates to `BuildMarketContextUseCase` — pure computation with no IO. The engine owns all fetching for the current regime command. Legacy callers may still exist until migrated.

#### 2. Continuous 0.0–1.0 factor scoring, not binary
Each factor is scored on a continuous scale using piecewise linear interpolation. Unavailable/disabled factors are excluded and the remaining weights renormalize to 1.0 (same pattern as `AssessSignalUseCase`).

**Factors (Phase 1–2):**

| Factor | Source | Signal |
|--------|--------|--------|
| `vix` | `^VIX` candles | Global risk appetite |
| `eido` | `EIDO` vs IHSG 5d divergence | Foreign institutional view on Indonesia |
| `usd_idr` | `IDR=X` 5d % change | Rupiah pressure / capital flow |
| `idx_trend` | `^JKSE` % from SMA50 | IHSG momentum |
| `idx_breadth` | Universe % above SMA20 | Market-wide participation |
| `foreign_flow` | `BrokerDataRepository` aggregated net buy | Domestic foreign capital direction |

**Optional (off by default):** `commodity_composite` (CPO + coal).

#### 3. Output contract: `MarketContext`
```python
@dataclass(frozen=True)
class MarketContext:
    regime: MarketRegime           # RISK_ON | NEUTRAL | RISK_OFF | VOLATILE
    conviction: float              # weighted composite 0.0–1.0
    factors: tuple[ContextFactor, ...]
    signal_multiplier: float       # 0.50–1.0; consumed by SignalEngine
    gate_tightening: bool          # True → RiskEngine adds regime gate for HIGH_RISK
    as_of_date: date
    staleness_warning: str | None
    coverage_warning: str | None
```

#### 4. Integration contract (Phase 4)
Both downstream engines accept an optional `market_context` parameter:

- **SignalEngine**: `score × signal_multiplier`; ENTER→WATCH when `gate_tightening=True`; regime note appended to rationale.
- **RiskEngine**: when `gate_tightening=True` and assessment is `HIGH_RISK`, `gate_triggered = "regime:{REGIME_NAME}"` is set.

Neither engine is broken without `market_context` — it is always optional.

#### 5. Fetch via existing `saham fetch market`
Global context tickers (`^VIX`, `EIDO`, `IDR=X`) are fetched by `_fetch_global_context_tickers()` appended to `fetch_market_commands.py`. Uses `YahooFinanceProvider(market_suffix="")` — critical: the default provider appends `.JK` for IDX stocks; global tickers must bypass this. No new tables; candles go into the existing `market_data` SQLite table.

#### 6. CLI: `saham view market-context` — documented 3-word exception
Second 3-word exception (after `saham view broker`, ADR-018). Rationale: MCE has multiple display modes (summary, verbose factor breakdown) requiring a sub-group. This exception is explicitly documented here to prevent undocumented proliferation.

`saham analyze regime` is preserved and now powered by MCE (richer output).

#### 7. Config ownership
All factor thresholds, score-label thresholds, fallback scoring policy, warning thresholds, normalization bounds, and regime effects live in `config/market_context_engine.yaml`. Each factor has `enabled: bool` and tunable thresholds — the ADR-027 learning loop can propose YAML diffs to tune thresholds without code changes.

#### 8. Persistence (Phase 5)
`SQLiteMarketContextRepository` stores one canonical snapshot per `as_of_date` (`INSERT OR REPLACE`). Factors serialized as JSON. The `MarketContextEngine` saves silently after every `evaluate()` call (failures are debug-logged, never raised — persistence is best-effort). `get_snapshot()` and `get_recent_snapshots()` allow the learning loop to replay past regime decisions.

---

### Layer Plan

| Layer | Artifact |
|-------|---------|
| Domain | `market_context.py` (value objects: `MarketContext`, `MarketRegime`, `ContextFactor`) |
| Domain (Port) | `market_context_repository.py` (Protocol) |
| Application | `build_market_context_use_case.py` (pure computation) |
| Application | `market_context_engine.py` (service — fetches, computes, persists) |
| Infrastructure | `market_context_config.py` (YAML loader + frozen dataclasses) |
| Infrastructure | `sqlite_market_context_repository.py` (SQLite persistence) |
| Adapter | `view_market_context_commands.py`, `view_market_context_display.py` |
| Adapter | `analyze_regime_commands.py` (updated to delegate to MCE) |
| Adapter | `fetch_market_commands.py` (extended: `_fetch_global_context_tickers`) |

---

### Non-Decisions

- **MarketRegimeUseCase** is kept for legacy callers (pre-open workflow, swing analysis, backtest, daily briefing). These callers migrate to MCE in a future phase; the old use case is not removed until all callers are migrated.
- `saham view market-context` does not have a `--history` subcommand yet; `get_recent_snapshots()` is infrastructure-ready for a future `saham view market-context history` command.

---

## ADR-030: Accumulation Screener Evidence Split

**Status:** Accepted
**Date:** 2026-06-25
**Amended by:** ADR-039 (2026-07-09) — `foreign_flow_score` scale changed from 0-120 to 0-100. Wherever this ADR says "0-120" below, read "0-100"; see ADR-039 for the full calibration table and rationale.

### Context

`screen accum` had one ambiguous `score` that mixed several questions:
- Is there deterministic foreign-flow score evidence?
- Is the enriched ticker attractive according to SignalEngine?
- Is the setup tradable after RiskEngine gates?
- Is the data fresh and complete enough to trust the result?

This made `--min-score` arbitrary because users could not tell which question it filtered. It also made the CLI table overloaded: one score and one row tried to explain evidence, signal, risk, and data coverage.

### Decision

Do **not** promote ScreenEngine to a first-class engine. Screening remains an application use case because it is an orchestration workflow over repositories and existing engines. The reusable artifact is **Foreign Flow Score Breakdown**, not a new engine pillar.

`AccumulationScreenUseCase` now delegates deterministic foreign-flow scoring to `ScoreForeignFlowUseCase`, which returns the domain value object `ForeignFlowScoreBreakdown`. The candidate-level field is `foreign_flow_score`; generic `score` is not used for the application object.

`screen accum` replaces the public `--min-score` option with explicit filters:
- `--min-foreign-flow-score`: threshold for deterministic foreign-flow score, 0-120 (rescaled to 0-100 by ADR-039).
- `--min-signal-score`: optional threshold for SignalEngine score, 0–100.

Default thresholds and component weights live in `config/accumulation_screener.yaml` so the learning loop can tune policy by YAML diff instead of code changes.

### Screen Questions

The screener answers separate questions and displays them separately:

| Panel | Question | Owner |
|-------|----------|-------|
| Verdict | What should I do with this candidate now? | `TradeSetup` composition |
| Foreign Flow Score | Is foreign flow accumulating deterministically? | `ScoreForeignFlowUseCase` |
| Signal | Is the enriched setup attractive? | `SignalEngine` |
| Risk | Is the setup blocked or degraded by gates? | `RiskEngine` |
| Data Coverage | Is the data fresh and complete enough? | Screen adapter/use case metadata |

### Layer Plan

| Layer | Artifact |
|-------|----------|
| Domain | `ForeignFlowScoreBreakdown` value object |
| Application | `ScoreForeignFlowUseCase` |
| Application | `AccumulationScreenUseCase` orchestration over evidence, signal, risk, and trade setup |
| Infrastructure | `accumulation_screener_config.py` YAML loader |
| Infrastructure | `config/accumulation_screener.yaml` thresholds and component weights |
| Adapter | `screen_accum_commands.py` explicit filter options |
| Adapter | `screen_accum_display.py` multi-panel display |

### Rationale

SignalEngine, RiskEngine, and MarketContextEngine are first-class because they each expose reusable decision services with stable input/output contracts. A screen is different: it selects, enriches, filters, sorts, and displays candidates for a workflow. Making ScreenEngine first-class would duplicate orchestration rather than clarify a decision boundary.

The boundary that matters for learning is the scoring artifact. `ForeignFlowScoreBreakdown` is deterministic, replayable, and has tuneable components; it can be correlated with outcomes without conflating SignalEngine or RiskEngine behavior.

### Compatibility

Application services read `AccumulationCandidate.foreign_flow_score`. JSON output should use explicit fields such as `foreign_flow_score`; ambiguous `score` aliases are not part of new contracts.

---

## ADR-031: Swing Setup Evaluation Boundary

**Status:** Accepted
**Date:** 2026-06-25

### Context

The swing workflow previously exposed `--preset foreign-bounce` and returned a setup-like result using `ENTER`, `WATCH`, and `AVOID`. That duplicated final-action vocabulary already owned by `TradeSetup` (ADR-026), and the foreign-bounce gate policy lived in the CLI adapter.

### Decision

Rename the concept from **preset** to **setup** and make setup evaluation an application-layer deterministic policy.

Setup evaluation answers only:

> Does this candidate fit the named setup?

Setup evaluation returns:

| Result | Meaning |
|--------|---------|
| `MATCH` | All setup gates pass |
| `PARTIAL` | Candidate is close enough to track, but at least one gate failed |
| `NO_MATCH` | Candidate does not fit the setup |

Final trading action remains exclusively owned by `TradeSetup.action` (`ENTER`, `WATCH`, `AVOID`, `BLOCKED_EXECUTION`, `BLOCKED_STRUCTURAL`).

The initial setup catalog is:

| Setup | Question Answered | Required Evidence |
|-------|-------------------|-------------------|
| `foreign-bounce` | Is foreign accumulation happening while price is still below foreign VWAP in a range? | accumulation candidate |
| `coiled-spring` | Is accumulation happening while volatility is compressed enough for a potential expansion? | accumulation candidate with BB width percentile |
| `smart-money-confirmed` | Is broker attribution led by smart-money flow rather than noise flow? | accumulation candidate plus broker-detail attribution |
| `pullback-continuation` | Is an uptrend pullback still supported by foreign flow and RSI headroom? | accumulation candidate |

All setup gate thresholds and enable flags must be configurable through `config/swing_setups.yaml`. Code-level defaults are deterministic fallbacks only. Calibration and future learning should propose YAML changes, not code edits.

### Layer Plan

| Layer | Artifact |
|-------|----------|
| Domain | `SetupEvaluation`, `SetupGate`, `SetupMatch` value objects |
| Application | `EvaluateSwingSetupUseCase` for named setup policy |
| Infrastructure | `config/swing_setups.yaml` setup gates; `config/swing_targets.yaml` regime TP/SL targets |
| Adapter | CLI `--setup`, setup JSON/display formatting only |

### Rationale

Setup evaluation is not a first-class engine like SignalEngine, RiskEngine, or MarketContextEngine. It is a named pattern-fit check for a workflow. Making it an engine would overstate its scope and duplicate orchestration boundaries.

Keeping setup policy in application code satisfies adapter thinness: CLI adapters parse `--setup`, wire dependencies, and format results; they do not own gate policy or business classification.

### Compatibility

This is a breaking rename. Public CLI flags, JSON fields, and journal fields use:

| Old | New |
|-----|-----|
| `--preset` | `--setup` |
| JSON `preset` | JSON `setup` |
| journal `preset` | journal `setup` |
| journal `classification` | journal `setup_match` |

### Setup Entry Authority Metadata

Each setup in `config/swing_setups.yaml` must declare:

| Field | Purpose |
|-------|---------|
| `family` | Canonical setup family used for target filter matching |
| `entry_authority` | Whether this setup may independently produce `ENTER` |
| `can_enter_from_phases` | Setup phases that satisfy the entry authority gate |

`SetupEvaluation` remains pattern-fit evidence only — it answers "does this candidate fit the named setup?" and returns `MATCH`/`PARTIAL`/`NO_MATCH`. It does not decide final action.

`DecisionPolicy` consumes `entry_authority` metadata from the resolved setup configuration. A setup with `entry_authority: false` (e.g. `smart-money-confirmed`) cannot independently create `ENTER` even if `SetupEvaluation` returns `MATCH`. Such setups may contribute evidence, rationale, or conviction to the final verdict, but the final action remains the exclusive responsibility of `SignalEngine + DecisionPolicy -> TradeSetup`.

This ensures that confirmation-only patterns complement the decision without bypassing the authority chain.

---

## ADR-032: `analyze swing` Verdict Boundary

**Status:** Accepted
**Date:** 2026-06-26

### Context

`saham analyze swing` had grown into a composite command where strategy backtest, sentiment, setup gates, broker attribution, and risk/signal outputs appeared together. That made it easy to confuse inspection evidence with the authoritative trade verdict.

### Decision

The current core decision basis for `saham analyze swing TICKER` is exclusively:

```text
SignalEngine + RiskEngine -> TradeSetup
```

`TradeSetup.action` is the authoritative final action. This follows ADR-026 (`TradeSetup` composition) and ADR-031 (setup evaluation answers only setup fit).

MarketContextEngine remains deterministic, but it is not yet tuned enough to be an authoritative input to `TradeSetup.action`. Until SignalEngine, RiskEngine, and MCE thresholds are calibrated, MCE is exposed as optional preview/enrichment evidence via `--with-market-context` / `--with-market-detail`. Its preview may show how signal/risk/trade setup would change under regime adjustment, but it does not change the canonical `TradeSetup`.

Evidence modules are optional and do not independently alter the verdict:

| Module | Purpose |
|--------|---------|
| `--setup NAME` | Named setup fit evidence (`MATCH`/`PARTIAL`/`NO_MATCH`) |
| `--strategy NAME` | Strategy/backtest evidence panel |
| `--with-sentiment` | News sentiment context |
| `--with-flow-detail` | Broker flow and attribution detail |
| `--with-signal-detail` | Signal factor detail |
| `--with-risk-detail` | Risk indicator/gate detail |
| `--with-market-context` | MCE what-if preview/enrichment |
| `--with-market-detail` | Full MCE factor detail when context is enabled |

Default output remains verdict-first and concise: latest price, data freshness, SignalEngine summary, RiskEngine summary, final `TradeSetup`, and why/blockers.

### Learning Loop

Evidence modules exist for user inspection and ADR-027 learning-loop attribution. Near-term tuning priority is SignalEngine and RiskEngine. Future MCE promotion to an authoritative `TradeSetup` input requires calibrated YAML/configurable parameters and a follow-up ADR update; until then, tuning must not add hidden MCE decision branches in CLI or workflow code.

### Compatibility

`--strategy` defaults to none. `--strategy NAME` enables strategy evidence. `--full` includes strategy evidence using `foreign-accumulation` when no explicit strategy is provided. `--with-market-context` enables optional MCE preview/enrichment. Old `--with-regime` / `--no-regime`, `--no-backtest`, and `--no-sentiment` flags are not part of the `analyze swing` command.

---

## ADR-033: Workflow Composition Artifact Boundaries

**Status:** Accepted
**Date:** 2026-06-28

### Context

The CLI now exposes several deterministic workflows that reuse overlapping data:
broker flow, candles, enrichment, signal, risk, market context, setup gates, and
historical replay. Reuse is useful, but a generic workflow wrapper would blur
which output is an actionable verdict and which output is evidence, discovery, a
session confirmation, or a learning artifact.

### Decision

Public commands stay explicit. Shared behavior should be extracted only at
small contract boundaries, not by collapsing commands behind a generic mode.

Canonical artifact ownership:

| Command | Workflow family | Canonical artifact | Meaning |
|---------|-----------------|--------------------|---------|
| `saham analyze swing TICKER` | Single-ticker swing decision | `TradeSetup` | Authoritative swing action from `SignalEngine + RiskEngine` |
| `saham screen accum` | Candidate discovery | `AccumulationCandidate` with optional `TradeSetup` | Ranked candidates; final action exists only when both signal and risk are present |
| `saham screen pre-open` | Intraday pre-open planning | `PreOpenScreenResult` | Conditional pre-open candidate list and entry ranges |
| `saham trade confirm` | Intraday post-open confirmation | `IntradayConfirmationResult` | ENTER/WAIT/SKIP decision after actual opening price is known |
| `saham trade backtest-swing` | Historical replay | `SwingBacktestResponse` | Walk-forward performance artifact, not a live verdict |
| `saham trade backtest-intraday` | Historical proxy simulation | `IntradayBacktestResponse` | Daily-OHLC proxy performance artifact, not exact intraday replay |
| `saham analyze accum-audit` | Learning/audit replay | `AccumulationAuditResponse` | Forward-return audit of foreign-flow score evidence |
| `saham trade log --type swing` | Journal continuation | `LogSwingCandidateResponse` | Persistence outcome for a logged candidate |

Composition rules:

* `TradeSetup` is the only final swing trade verdict wording.
* Any command that shows a complete swing action from signal and risk must call
  `AssessTradeSetupUseCase`.
* `SetupEvaluation`, strategy evidence, sentiment, broker detail, and market
  context preview are evidence modules. They must not independently overwrite
  `TradeSetup.action`.
* Pre-open and intraday confirmation use their own session artifacts. They must
  not reuse `TradeSetup` wording unless the full swing signal/risk contract is
  actually composed.
* Backtest and audit commands produce learning artifacts. They may replay the
  same deterministic rules, but their outputs are performance observations, not
  current recommendations.

JSON contract rules:

* JSON outputs and command sidecars should include `schema_version` and
  `artifact_type` at the root.
* New machine-facing fields should use explicit artifact names such as
  `foreign_flow_score`, `signal_score`, `risk_status`, `opening_broker_backing_score`, or
  `trade_setup.action`.
* Opening-session artifacts use `opening_setup` for PRIME/WATCH/SKIP labels;
  they must not use generic `verdict` unless they compose a `TradeSetup`.
* `saham analyze swing --format json` treats grouped `verdict`, `evidence`, and
  `diagnostics` as canonical. It does not emit top-level aliases such as
  `trade_setup`, `signal_assessment`, `accumulation`, `risk`, or `data`.

### Layering

Adapters may parse flags, construct infrastructure dependencies, call use cases,
format display, and write command sidecars. Workflow policy and composition
belong in application use cases. Infrastructure factories are preferred when a
command needs a configured engine, repository bundle, or provider bundle.

### Consequences

This keeps the user-facing command model explicit while still allowing shared
internals. Future refactors should add narrow services such as provider bundles,
config factories, display DTOs, or composition contract tests before introducing
larger workflow abstractions.

---

## ADR-034: Date Field Semantics

**Status:** Accepted
**Date:** 2026-06-29

### Context

The codebase intentionally carries several date names that look similar but
answer different questions. Renaming all of them to one generic field would hide
important anti-lookahead and data provenance rules.

### Decision

Date fields keep these meanings:

| Field | Meaning |
|-------|---------|
| `snapshot_date` | Date of the evaluated point-in-time snapshot or workflow assessment. |
| `session_date` | Exchange trading session date for session-bound market data. |
| `report_date` | Publisher or filing date for reported data, such as IDX shareholding composition. |
| `as_of_date` | Replay/query boundary: only use data available on or before this date. |
| `fetched_at` | Cache/ingestion timestamp, not a market or filing date. |

New domain and application contracts should choose the most specific name from
this table. Do not standardize these fields mechanically unless the data meaning
is actually the same.

### Consequences

Backtest and replay paths can continue to use `as_of_date` as an availability
guard, while source-specific value objects retain their own provenance dates.
This avoids confusing `report_date` with cache freshness and avoids treating
session data as if it were a generic workflow snapshot.

---

## ADR-035: Port Method Naming Convention

### Context

The codebase intentionally has both provider ports and repository ports. Their
method prefixes look inconsistent unless the source boundary is explicit.

### Decision

Port method prefixes distinguish data source boundaries:

| Prefix | Meaning | Examples |
|--------|---------|----------|
| `fetch_*` | Obtain data from a live/external provider or an interaction boundary. May perform network/browser/API work. | `MarketDataProvider.fetch_daily_ohlcv`, `BrokerDataProvider.fetch_broker_summary`, `NewsProvider.fetch_headlines` |
| `get_*` | Read from local repositories, caches, deterministic services, or enrichment providers that expose cached/as-of semantics. | `MarketDataRepository.get_candles`, `BrokerDataRepository.get_broker_summaries`, `ShareholdingProvider.get_composition` |

`MarketDataProvider.fetch_daily_ohlcv()` and `MarketDataRepository.get_candles()`
are not competing names for one operation: the provider crosses an external
source boundary; the repository reads persisted/cache-backed candles.

### Guidance

New live provider ports should use `fetch_*`. New repository/cache ports should
use `get_*`. If a provider exposes historical/as-of cached enrichment behind the
interface, `get_*` is acceptable when the caller is not asking it to perform a
fresh external fetch. Do not mechanically rename existing ports unless the
boundary meaning is wrong.

---

## ADR-036: Persisted JWT Token Store Replaces Playwright-per-invocation for Stockbit Data Fetching

### Context

Every CLI command that fetched live Stockbit data previously launched a headless Chromium
browser to intercept a Bearer JWT from outgoing request headers, then closed the browser
immediately after. The token was cached in-process for 30 minutes but never persisted to
disk. The next CLI invocation started a new browser — even if the previous token was still
valid (RS256 JWTs typically expire after 8–24 hours).

All 21 Stockbit data providers already used pure `httpx` calls (`_exodus_get`). The browser
was the sole reason Playwright was a runtime dependency for data workflows.

### Decision

1. **`StockbitTokenStore`** persists the JWT to `.stockbit_profile/token.json`. Validity
   uses the `exp` claim from the JWT payload (base64-decoded, no signature verify); falls
   back to `fetched_at + 8h` when `exp` is absent. Write is atomic (`tmp + os.replace`,
   chmod 0600).

2. **`StockbitApiClient`** is a thin authenticated HTTP client: `get(url, params) → dict | None`.
   On 401 it triggers one browser refresh via `extract_exodus_token()` then retries once
   (`already_refreshed` guard prevents infinite loops). It never exposes the token to callers.

3. **One shared `api_client` per CLI invocation.** `create_stockbit_api_client()` builds the
   instance; CLI adapters extract it once and inject it into all providers in the same command.
   This reproduces the old in-process cache benefit without a 30-minute timer.

4. **Playwright is retained** only for interactive commands (`login`, `spy`, `browse`) and the
   `extract_exodus_token()` helper called by `StockbitApiClient` on 401. No data-fetch path
   touches a browser directly.

5. **`StockbitBrokerProvider`** replaces `StockbitPlaywrightBrokerProvider`. The old class is
   deleted. All 21 data providers take `api_client: StockbitApiClient | None` instead of
   `broker_provider`.

### Consequences

- **First invocation** after `saham fetch stockbit login`: zero browser launches for data.
- **Token expired mid-session**: one silent browser launch (< 5s) then all subsequent calls
  in the same process use the refreshed token.
- **Offline / no Playwright**: the `api_client.get()` returns `None`; all providers fall back
  to their DB cache path. System remains fully usable offline.
- **Testing**: tests patch `StockbitApiClient.get` (instance method on the class) rather than
  the removed `_exodus_get` module-level function.

### Skills

- `stockbit-api-explorer` — how to add providers, endpoint patterns, test patterns
- `codebase-known-pitfalls` — `fetch_json` latent bug, single api_client rule, removed symbols

---

## ADR-037: MarketContext Promotes from Preview-Only to Canonical Signal Input

**Status:** Accepted — supersedes ADR-032 signal-preview constraint
**Date:** 2026-07-03

### Context

ADR-032 designated `--with-market-context` as preview/enrichment only: "it does not change the
canonical `TradeSetup`." That was the correct constraint in June 2026 when MCE thresholds were
uncalibrated and regime parameters were not yet config-backed.

Phase 5 of the SignalEngine staged-evidence refactor completes the missing calibration
prerequisites:

- Regime conditioning is fully config-backed (`config/signal_engine.yaml:
  signal_engine.regime_conditioning.*`).
- Conditioning is deterministic and auditable: notes appear in `rationale`, markers appear in
  `breakdown`, visible in `--diagnostic`.
- Conditioning is applied BEFORE group renormalization (not as a blunt post-score scalar
  multiply), making it semantically precise: RISK_OFF discounts weak setup evidence (PARTIAL/
  NO_MATCH tier); NEUTRAL discounts weak flow; VOLATILE applies general discounts to both groups.
- `gate_tightening` (ENTER→WATCH cap) is exposed as a per-`MarketContext` field, independently
  configurable from score discounts.

### Decision

When `--with-market-context` is enabled, `MarketContext` is now an explicit evidence conditioning
input to `AssessSignalEvidenceUseCase`, not a post-score adjustment. This means:

1. **The canonical signal score IS affected by regime conditioning** when
   `--with-market-context` is supplied. Canonical `TradeSetup` action may differ with vs without
   MCE.

2. **`market_context_signal_preview` is now the same object as `signal_assessment`** (the
   canonical regime-conditioned signal). The preview/delta concept for the signal no longer
   applies — the signal itself IS the regime-conditioned signal. The MCE preview panel remains
   meaningful for the *risk* side: `market_context_risk_preview` and
   `market_context_trade_setup_preview` still show the what-if effect of regime-adjusted risk gates.

3. **The `--with-market-context` flag remains optional and off-by-default.** Without it,
   `market_regime=None` is passed to the signal use case, which applies no conditioning.
   The system remains fully functional without MCE.

4. **ADR-032's preview-only constraint is superseded for signal only.** Risk-side preview
   (regime-adjusted gates) remains a preview; it does not change `risk_response` (the canonical
   risk assessment). Only the canonical signal score is now regime-influenced.

### Boundary

```
--with-market-context present:
  market_regime → AssessSignalEvidenceRequest.market_context
      → regime conditioning applied to group scores (canonical)
      → gate_tightening cap applied (canonical)
  canonical TradeSetup = f(regime-conditioned signal, canonical risk)
  MCE preview TradeSetup = f(same signal, regime-adjusted risk preview)

--with-market-context absent:
  market_regime = None → no conditioning → identical to pre-Phase-5 behavior
```

### Consequences

- The CLI display "Signal impact" line in the MARKET CONTEXT PREVIEW panel is retired (signal
  preview == canonical signal; no delta to show). The panel remains for the risk preview and
  TradeSetup action preview.
- The panel subtitle is updated from "evidence only — does not change final TradeSetup" to
  "regime conditioning in canonical signal · risk preview via MCE".
- The workflow test `test_swing_workflow_canonical_trade_setup_unaffected_by_market_context`
  is retired; the new contract is "regime conditioning is forwarded to signal engine when
  market_context is supplied."

### Learning Loop Note

MCE thresholds (weak_flow_threshold, weak_setup_threshold, discounts) are now config-backed
and tunable via `config/signal_engine.yaml` without code changes. Calibration of these values
proceeds in the `trade tune signal` workflow.

---

## ADR-038: Point-in-Time Enrichment And Conservative Derived Fundamentals

**Status:** Accepted
**Date:** 2026-07-08

### Context

Historical backtesting and walk-forward calibration require that all input signals represent the exact state of information available as of a specific historical date (`as_of_date`), with zero look-ahead leakages.
While candles and broker flows are naturally historical time-series, other corporate/valuation metrics (fundamentals, shareholding structure, analyst consensus, estimates, etc.) are typically retrieved from external APIs as "latest snapshots."

To support valid historical signal replay, we previously converted several single-row cache tables (e.g., `company_fundamentals` and `shareholding_composition`) to multi-row Point-in-Time (PIT) structures. However, since the external data vendor (Stockbit) only returns current state for many endpoints, we have admitted derived historical fundamentals (backfilled from key ratio trends) but need strict rules governing their availability, contents, and fallback logic to protect backtest validity.

### Decision

1. **PIT Capable Enrichment Caches:**
   All tables storing data relevant for signal replay must use a time-series/PIT format (storing one row per `(ticker, fetched_date)` or `(ticker, fetched_at)`) rather than overwriting a single `ticker` row with the latest snapshot. This applies to the following tables:
   - `company_fundamentals`
   - `shareholding_composition`
   - `analyst_cache`
   - `forward_estimates_cache`
   - `ticker_notation_cache`
   - `stock_meta`
   - `company_profile_cache`
   - `seasonality_cache`
   - `earnings_cache`

2. **PIT Replay Constraints:**
   When replaying signals historically (during backtest or backfill), providers must only load cache entries where `fetched_date <= as_of_date` (or `fetched_at <= as_of_date` or `COALESCE(report_date, fetched_date) <= as_of_date`). Any entries fetched after `as_of_date` are future data and must be ignored. If no valid row exists on or before the replay date, the metric is marked unavailable (`None`/`UNKNOWN`).

3. **Authoritative Live Snapshots:**
   Live-fetched snapshots remain the authoritative source of truth for the current date. Fresh API requests store the exact payload returned by the vendor with the current timestamp.

4. **Conservative Derived Fundamentals Availability:**
   Derived historical fundamental rows backfilled from quarterly trend summaries may be generated or populated (e.g., during historical backfill or data import), but their publication date must be conservatively estimated as `period_end_date + 60 days` to reflect typical corporate reporting lag in the IDX. Derived rows must never be read if the replay `as_of_date` is before this availability date.

5. **Derivation Boundaries:**
   Derived fundamental rows are restricted to the fields actually present in historical trend payloads, currently:
   - `net_profit_margin`
   - `revenue_yoy_growth`

   Derived rows must **never** fabricate or guess values for other fundamentals that are only available in live snapshots, including `market_cap_idr`, `piotroski_f_score`, PE/PBV, ROE, or dividend yield. These fields must remain `NULL` in derived rows.

6. **Protection of Live Refreshes:**
   Derived rows must not suppress live cache refreshes. The cache freshness check must ensure that a recently written derived row containing a future/recent date does not trick the system into believing a live snapshot is fresh. Freshness checks must target genuine live-fetched rows.

7. **Zero Authority Scope:**
   This record governs data ingestion and replay integrity. It does not promote company-quality evidence, nor does it modify SignalEngine scoring authority. Company-quality context remains diagnostic with zero scoring weight.

### Consequences

- Historical observations backfilled prior to the start of local EOD snapshots will correctly resolve to `tp_market_cap_bucket: UNKNOWN` and `piotroski_f_score = None`, leaving them ineligible for setup-specific targets that filter on market cap (e.g. `large_cap`).
- The system remains offline-capable for backtesting, but requires live cron observations to run going forward to naturally accumulate the mature `large_cap` labels required to unblock Phase I calibration.

---

## ADR-039: Foreign Flow Score Rescale to 0-100 (Amends ADR-030)

**Status:** Accepted
**Date:** 2026-07-09

### Context

ADR-030 established the accumulation screener's composite `foreign_flow_score` on a 0-120 "soft cap" scale. This coexists with SignalEngine's unrelated `SignalAssessment.score`, which has always been 0-100. Showing two differently-scaled scores side by side in `screen accum` output (and in `analyze swing`, `saham today`) was a recurring source of confusion — the same-looking number means different things depending on which panel it's in.

### Decision

`foreign_flow_score` and every threshold tuned against it are rescaled from 0-120 to 0-100, via a **proportional-preserve conversion** (divide by 1.2, round to 1 decimal). This is a deliberate calibration exercise, not a mechanical global find-replace: every consumer was individually identified, verified against the live code, and converted so that pass/fail behavior for every existing candidate is unchanged (before rounding).

#### Calibration table (old → new)

| Item | Old | New |
|---|---|---|
| `ForeignFlowScorePolicy.max_score` / `signal_engine.yaml` `input_mapping.foreign_flow_score.max_score` | 120.0 | 100.0 |
| `consistency.weight` | 40.0 | 33.3 |
| `streak.weight` | 30.0 | 25.0 |
| `vwap_discount.weight` | 20.0 | 16.7 |
| `rsi_headroom.weight` | 10.0 | 8.3 |
| `foreign_flow_ratio.weight` | 10.0 | 8.3 |
| `bb_squeeze.weight` (stays disabled — see BB ownership fix, same-day prior change) | 10.0 | 8.3 |
| `bci.cluster_points` | 15.0 | 12.5 |
| `bci.stable_points` | 5.0 | 4.2 |
| Accumulation screener display: enter/watch/coiled-spring minimums | 70.0 / 40.0 / 60.0 | 58.3 / 33.3 / 50.0 |
| Setup gates: foreign-bounce / coiled-spring / smart-money-confirmed / pullback-continuation | 70 / 60 / 60 / 55 | 58.3 / 50.0 / 50.0 / 45.8 |
| Audit bucket edges (`accumulation_audit.yaml`, `AuditBucketPolicy`) | [40, 70] | [33.3, 58.3] |
| `swing_config.py` verdict thresholds (enter/watch/strong/building/coiled-spring) | 70 / 40 / 70 / 60 / 60 | 58.3 / 33.3 / 58.3 / 50.0 / 50.0 |
| `today_commands.py` display color thresholds (previously unconfigured literals) | 80 / 60 | 66.7 / 50.0 |
| `analyze_swing_display.py` fallback `SwingDisplayConfig` (pre-existing drift from `swing_config.py`'s canonical defaults, not introduced by this ADR — converted proportionally but not unified) | 70 / 50 / 70 / 80 / 60 | 58.3 / 41.7 / 58.3 / 66.7 / 50.0 |
| `accumulation_journal.py` bucket labels | 70 / 40 | 58.3 / 33.3 |
| `config/default.yaml`, `app_config.py` `SwingDefaults.min_foreign_flow_score` (verified dead/unused — `get_swing_default()` is only ever called with key `"capital"`) | 70.0 | 58.3 |
| `config/user.yaml.example` (template, not live-loaded) | 70 | 58.3 |

Explicitly **out of scope** — different score system, not touched: `SignalClassificationConfig` in `assess_signal_use_case.py` (`strong_min_score=70`, `moderate_min_score=45`) classifies the unrelated 0-100 `SignalAssessment.score`, despite confusingly similar field names to the accumulation screener's own thresholds.

#### Historical data: untouched, not migrated

No migration script rewrites persisted SQLite/JSON/CSV records. `ForeignFlowScoreBreakdown.to_dict()` already stores `max_score` alongside every score, so old records (max_score=120.0) remain self-describing. `AccumulationAuditUseCase.execute` always recomputes `foreign_flow_score` live via `ScoreForeignFlowUseCase` — it never reconstructs a `ForeignFlowScoreBreakdown` from a persisted historical record, and `SignalEngine.foreign_flow_quality_from_foreign_flow_score()` has no per-candidate max_score parameter, so no code path feeds a historical 0-120 score through the new 0-100 config divisor.

#### Accepted limitations (documented, not fixed)

1. **Watchlist repository** (`sqlite_watchlist_repository.py`) stores `flow_score` with no `max_score`/schema-version tracking. Not changed — the feature is unused. Watchlists saved before vs. after this rescale may not compare meaningfully.
2. **Previously-exported audit artifacts** (JSON/CSV from `analyze accum-audit --output`) remain on their era's scale; the new bucket edges must not be applied retroactively to them.
3. **Accumulation journal review** (`AccumulationJournalService.review()`) buckets *persisted* `AccumulationJournalEntry.foreign_flow_score` values, not live-recomputed ones. Entries logged before this rescale may report a different bucket **label** than when they were originally logged — labels only, no data loss or rewrite.

### Rationale

A proportional-preserve conversion was chosen over ad hoc recalibration because it requires no new trading-calibration judgment calls — every gate and bucket continues to admit/reject the same candidates it did before, just expressed on a scale consistent with SignalEngine. Rounding to 1 decimal introduces a documented, narrow edge case: a candidate scoring exactly at an old boundary (e.g. precisely 70.0) maps to 58.33, but the new gate is 58.3 — a hairline case where an exact-boundary candidate could flip classification. This is accepted as the cost of round numbers over floating-point exactness.

### Consequences

- `screen accum`, `analyze swing`, and `saham today` now show `foreign_flow_score` and `signal_score` on the same 0-100 scale, removing the dual-scale confusion that motivated this change.
- Full implementation tracker and file-by-file inventory: `docs/screen_refactor.md`.

---

*End of Architecture Decisions Record.*
