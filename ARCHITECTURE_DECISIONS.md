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

* Risk profiles
* Thresholds
* AI enable/disable

**Rationale**
Promotes flexibility without branching logic.

---

## ADR-010: Risk Profiles as Policy Layer

**Decision**
Risk profiles map analysis results to qualitative interpretation. Three built-in profiles exist: Conservative, Balanced, Aggressive. All profile thresholds and gate trigger levels must be config-driven, not hardcoded.

**Built-in Profiles**

| Profile | RSI High-Risk | RSI Low-Risk | EMA/SMA Min Divergence | Decision Logic |
|---------|--------------|-------------|----------------------|----------------|
| Conservative | > 75 | < 25 | ≥ 1.0% | Both RSI and trend must agree |
| Balanced | > 70 | < 30 | ≥ 0% | Majority rules |
| Aggressive | > 60 | < 40 | ≥ 0.1% | Either can signal |

**Implications**

* No prediction or trading execution — profiles are interpretive policy only.
* Profile thresholds (RSI high/low, EMA/SMA divergence minimum) MUST be readable from `config/risk_engine.yaml`. Python constants are compile-time defaults only; YAML values override at startup.
* Gate trigger thresholds (Piotroski F-score cutoff, market cap floor, liquidity floor, free float minimum, bandar distribution score threshold) MUST be configurable per profile in `config/risk_engine.yaml`.
* Each gate MUST declare an `enabled: bool` field in the YAML config. A gate with `enabled: false` is skipped entirely from the pipeline — no evaluation, no block decision. This supports backtesting, A/B comparison, and T2 Tuner proposals without code changes. See ADR-024 Engine Configurability Contract for the full gate YAML schema.
* A profile configuration YAML schema MUST be validated at startup via `yaml_loader.py`. Invalid config aborts startup with a clear error, not a silent fallback.
* Custom profiles (user-defined YAML) are supported. Custom profile names are strings; built-in profiles use the `RiskProfile` enum.
* Gate thresholds may be tightened based on market regime (RISK_OFF/WEAK) — see ADR-026 for regime integration rules.

**Rationale**
Separates math from policy. Config-driven thresholds enable the learning loop (ADR-027) to propose adjustments without requiring code changes, and enable calibration for IDX market specifics (ADR-028) without forking profiles.

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
- `assess(ticker, profile, as_of_date)` — self-fetches enrichment via injected providers
- `assess_with_context(ticker, profile, gate_context)` — pipeline path, avoids N+1 in screener loops
- `assess_request(request)` — advanced path accepting full `AssessRiskRequest`
- `assess_all_profiles(request)` / `assess_trend(request, days)` — multi-profile and trend views

**Factory:** `create_risk_engine(db_path, with_enrichment)` in `src/application/services/bootstrap.py`. All gate instantiation and configuration is owned by the factory. Callers never instantiate `RiskGate` subclasses directly.

**Output:** `RiskAssessment` — `risk_level`, `confidence`, `gate_triggered`, `rationale: tuple[str, ...]`, `snapshot_date`

---

### Signal Engine

**Answers:** "How strong and well-aligned are the factors supporting entry?"

Owns: composite signal score (weighted sum of 6 factors: bandar intensity, foreign flow quality, insider activity (net buy direction), seasonality edge, analyst consensus, forward EPS valuation), preset gate evaluation, entry quality classification.

Output cadence: per session (signal factors are fast-moving).

**Interface (`src/application/services/signal_engine.py`):**
- `evaluate(ticker, as_of_date)` — self-fetches enrichment via injected providers
- `evaluate_with_context(ticker, signal_context)` — pipeline path, avoids N+1 in screener loops
- `evaluate_request(request)` — advanced path accepting full `AssessSignalRequest`

**Factory:** `create_signal_engine(db_path, with_enrichment)` in `src/application/services/bootstrap.py`. All provider injection and weight configuration is owned by the factory.

**Output:** `SignalAssessment` — `score: int (0–100)`, `strength: SignalStrength (STRONG/MODERATE/WEAK)`, `entry_quality: EntryQuality (ENTER/WATCH/AVOID)`, `breakdown: dict[str, float]`, `rationale: tuple[str, ...]`

**Signal weights** are read from `config/signal_engine.yaml`. Default weights: bandar 20%, foreign flow 20%, insider activity 20%, seasonality 15%, analyst consensus 15%, forward EPS 10%. See Engine Configurability Contract below for on/off toggle semantics.

---

### Orthogonality Rule

A strong signal does NOT imply low risk. Low risk does NOT imply a strong signal. Both engines are evaluated independently. A combined recommendation is derived by `CombinedAssessment` (see ADR-026) — neither engine reads the other's output.

---

### Engine Configurability Contract

Every component of both engines — signal factors and risk gates — MUST support individual on/off toggling and full parameter configuration via dedicated engine config files. Signal factors live in `config/signal_engine.yaml`; risk gates and profiles live in `config/risk_engine.yaml`. Screener-specific policy (resistance gates, preset TP/SL targets, corporate actions, sector breadth) stays in `config/swing_screener.yaml` — it is NOT engine config. This is what makes the engines tunable by the T2 Learning Loop (ADR-027) without code changes.

#### YAML Schema

**`config/signal_engine.yaml`**

```yaml
signal_engine:
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
  gates:
    fundamental:
      enabled: true
      piotroski_min: 4
      market_cap_floor_idr: 1_000_000_000_000
    liquidity:
      enabled: true
      median_tx_floor_idr: 5_000_000_000
    free_float:
      enabled: true
      min_free_float_pct: 15.0
    bandar:
      enabled: true
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
    breakdown: dict[str, float]        # factor name → contribution (0–1)
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
    seasonality_win_rate: float | None          # 0.0–1.0 (pct of months positive for this ticker)
    seasonality_avg_return_pct: float | None    # e.g. 2.5 = 2.5% avg monthly return this season
    analyst_buy_pct: float | None               # 0.0–1.0
    analyst_upside_pct: float | None            # e.g. 15.0 = 15% upside to consensus price target
    forward_pe: float | None                    # forward P/E ratio for valuation normalization
    sentiment: SentimentSnapshot | None         # optional: from FetchSentimentUseCase
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

* `src/application/use_case/accumulation_screen_use_case.py` — `_composite_score()` (line ~358) and `evaluate_foreign_bounce_gates()` (line ~1106) are migration targets. After migration, these functions are deleted.
* `src/application/use_case/swing_analysis_workflow_use_case.py` — signal assembly must delegate to `signal_engine.evaluate_with_context()`.
* `create_signal_engine(db_path, with_enrichment)` factory in `src/application/services/bootstrap.py` injects providers, parses `config/signal_engine.yaml` (`signal_engine.factors` block), applies `enabled` filtering, and computes renormalized weights before constructing the engine. See ADR-024 Engine Configurability Contract for the full schema and renormalization rule.
* `evaluate_with_context(ticker, SignalContext)` MUST be used by screening loops to avoid N+1 provider fetches.
* Unit tests must test `SignalEngine` in isolation with injected mock providers — no Stockbit browser in tests.
* `signal_display.py` in `src/adapters/cli/` is the only place `SignalAssessment` is formatted for CLI output.

**Implementation reference:** `docs/claude_signal_risk_230626.md` R1–R4 plan.

---

## ADR-026: Risk+Signal Pipeline Composition

_Date: 2026-06-24 · Context: Defines how SignalEngine and RiskEngine outputs combine into an action recommendation_

**Decision**
Features presenting a complete trade recommendation MUST compose both engine outputs through a `CombinedAssessment` domain value object. The composition rule is deterministic and lives in the domain layer.

**Value Object: `CombinedAssessment`** (`src/domain/value_objects/combined_assessment.py`)

```python
@dataclass(frozen=True)
class CombinedAssessment:
    signal: SignalAssessment
    risk: RiskAssessment
    action: ActionRecommendation
    reason: str
```

**Enum: `ActionRecommendation`** (`src/domain/value_objects/action_recommendation.py`)

```python
class ActionRecommendation(Enum):
    ENTER = "ENTER"     # STRONG signal + LOW_RISK
    WATCH = "WATCH"     # MODERATE signal OR MODERATE risk
    AVOID = "AVOID"     # WEAK signal
    BLOCKED = "BLOCKED" # HIGH_RISK (gate fired) — overrides any signal strength
```

**Composition Rule** (deterministic, no I/O):

```
if risk.risk_level == HIGH_RISK:
    → BLOCKED  (gate overrides; signal strength is irrelevant)
elif signal.strength == STRONG and risk.risk_level == LOW_RISK:
    → ENTER
elif signal.strength == WEAK:
    → AVOID
else:
    → WATCH
```

**Regime Modifier**
When `market_regime` is RISK_OFF or WEAK:
- ENTER is downgraded to WATCH (no new entries in a falling market)
- Gate thresholds in `RiskEngine` tighten per ADR-010 profile config

**Implications**

* `SwingAnalysisWorkflowUseCase` computes both assessments and calls `CombinedAssessment.compose(signal, risk, regime)` to produce the action.
* `AccumulationScreenUseCase` computes `CombinedAssessment` per candidate and uses it for the final ranking/display column.
* Neither engine reads the other's output. The composition is always performed by the use case, never inside an engine.
* `market_regime_use_case.py` output is fetched by the use case layer and passed as `regime: MarketRegime | None` to both engines and the composer.
* The `BLOCKED` state is the highest-priority output. No signal strength, no AI explanation, no config override can change a BLOCKED result without changing the underlying gate data.
* CLI display of `CombinedAssessment` uses `rich_display.action_cell()` — a single consistent formatter for all commands.

**Rationale**
Without a formal composition rule, every CLI command that shows both signal and risk invents its own merging logic — creating divergent action columns in `screen accum`, `analyze swing`, and future commands. A domain-level `CombinedAssessment` ensures the same ENTER/WATCH/AVOID/BLOCKED logic everywhere.

---

## ADR-027: Risk/Signal Learning Loop

_Date: 2026-06-24 · Context: Extends the pre-open learning loop pattern (already implemented) to the swing domain_

**Decision**
The system provides a four-phase learning loop for the swing domain that records engine outputs, grades forward outcomes, attributes performance to engine components, and produces AI-assisted parameter suggestions. Human approval is required at every change boundary.

**Phases**

| Phase | CLI Command | What it does |
|-------|-------------|-------------|
| Record | `swing learn record` | At trade entry, persist `CombinedAssessment` snapshot to journal |
| Grade | `swing learn grade --days N` | Fetch forward return for each recorded entry; compute WIN/LOSS/NEUTRAL |
| Attribute | `swing learn attribute` | Correlate outcomes with gate triggers and signal factor breakdown |
| Tune | `swing learn tune [--apply]` | AI T2 Tuner proposes YAML threshold diff; `--apply` writes after confirmation |

**Journal:** `journals/swing_signal_outcomes.jsonl`

```json
{
  "ticker": "BBCA",
  "entry_date": "2026-06-24",
  "entry_price": 9100,
  "signal_score": 72,
  "signal_strength": "STRONG",
  "signal_breakdown": {"bandar_intensity": 0.85, "foreign_flow_quality": 0.70, ...},
  "risk_level": "LOW_RISK",
  "risk_confidence": 100,
  "gate_triggered": null,
  "action": "ENTER",
  "outcome_date": null,
  "exit_price": null,
  "return_pct": null,
  "outcome": null
}
```

**Attribution Rules**
- Attribution requires minimum 30 graded outcomes before generating suggestions (enforce in `SwingSignalTunerUseCase`).
- Attribution is statistical correlation, not causal proof. AI tuner output must include a confidence note.
- Gate attribution: for each gate, compute `gated_win_rate` (forward return of gated candidates) vs. `passed_win_rate`. If `gated_win_rate > passed_win_rate + 10%`, the gate is being too aggressive and the threshold should consider relaxing. If a gate is routinely not triggered across 30+ outcomes and shows no correlation with outcomes, the Tuner may propose `enabled: false`.
- Factor attribution: for each factor in `signal_breakdown`, compute correlation of the factor's per-trade score with the forward return. If a factor shows consistently near-neutral contribution (factor score within ±0.1 of the 0.5 neutral baseline across 30+ outcomes), the Tuner may propose `enabled: false` to remove it from scoring. If a previously disabled factor is re-enabled and outcomes improve, the Tuner may propose keeping it enabled and increasing its weight.

**AI Tuner (T2) Constraints**
- Input: attribution summary JSON (not raw candles, not raw journal entries)
- Output: proposed YAML diff targeting `config/signal_engine.yaml` (for signal factor changes) or `config/risk_engine.yaml` (for gate changes) — never `config/swing_screener.yaml` (screener policy is not engine tuning)
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

**Current gap:** `BandarGate` uses `bandar_is_distributing: bool` (any score < 0 = distributing). Stockbit provides a -9 to +9 score; a -1 and a -9 carry very different implications.

**Rule:** `GateContext.bandar_is_distributing: bool` is replaced by `GateContext.bandar_five_day_score: int | None` (-9 to +9). `BandarGate` compares `bandar_five_day_score ≤ distribution_threshold` where `distribution_threshold` is configurable per profile in `config/risk_engine.yaml` (default: -2). Score of -1 is treated as noise and does not trigger the gate.

**Migration:** `StockbitBandarDetectorProvider` already returns the numeric score. `GateContext` construction in `bootstrap.py` must pass the score, not the boolean.

---

### Rule 6: T+2 Settlement Risk

**IDX rule:** Settlement is T+2. For thin-float stocks with high foreign ownership near the cap, large foreign exits at T can create forced selling at T+2 as counterparties scramble to cover.

**Rule:** When `free_float_pct < 20%` AND `foreign_ownership_pct > 35%`, `FreeFloatGate` adds a settlement-risk advisory to rationale (non-blocking, informational). It does not change `risk_level` unless `free_float_pct < 15%` (which already triggers HIGH_RISK).

---

**Implications**

* `src/domain/value_objects/tick_size.py` — new pure domain function
* `src/application/services/position_sizer.py` — apply `round_to_tick()` to all price levels
* `src/domain/rules/risk_gate.py` — `GateContext` adds `bandar_five_day_score`, `price_vs_upper_rejection_pct`; removes `bandar_is_distributing`
* `src/domain/rules/bandar_gate.py` — updated to compare score vs. threshold
* `src/domain/value_objects/signal_assessment.py` — `SignalContext` adds `foreign_ownership_pct`, `foreign_ownership_cap_pct`
* `src/application/services/bootstrap.py` — construct updated `GateContext` from enrichment data
* All tests referencing `GateContext(bandar_is_distributing=...)` must be updated to `bandar_five_day_score=...`

**Rationale**
Professional-grade IDX tools (Bloomberg PORT with IDX data, local tools like RTI Business, Stockbit Pro) all respect these structural constraints. Ignoring tick sizes causes computed stop-loss levels to be invalid on exchange. Ignoring auto-rejection bands creates unrealistic exit scenarios in backtest. Ignoring foreign cap saturation overstates the longevity of foreign flow signals in near-cap stocks.

---

*End of Architecture Decisions Record.*
