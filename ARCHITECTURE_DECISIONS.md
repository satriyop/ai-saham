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

## ADR-014: Full-AI Mode (Explicit Bypass Mode)

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

* Deterministic sentiment (indicator-like, rule-based)
* AI-based sentiment (probabilistic, LLM-assisted)

**Implications**

* Deterministic sentiment lives in `domain/indicators`.
* AI-based sentiment lives in `infrastructure/sentiment`.
* Domain rules must not depend on raw text or LLM outputs.
* Sentiment is contextual input, not a source of truth.

**Rationale**
Prevents misuse of sentiment while enabling future expansion.

---

*End of Architecture Decisions Record.*
