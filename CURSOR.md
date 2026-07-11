# CURSOR.md

## Purpose

This file defines how **Cursor AI** should be used in this repository.

Cursor is treated as a **local pair-programmer** that operates inside the editor. It is powerful but must be constrained to avoid architectural drift.

---

## Project Summary (Read First)

Cursor must read `AGENT_QUICKSTART.md` before code work and use its reading matrix to select any longer docs required for the task.

This is a **local-first, production-grade stock analysis system** with:

* Deterministic, rule-based core
* Optional AI-enhanced analysis (OFF by default)
* Indonesia Stock Exchange (IDX) as initial focus
* Strong emphasis on auditability, reproducibility, and maintainability

This is NOT a demo, NOT a trading bot, and NOT an AI-only system.

---

## Cursor’s Primary Role

Cursor SHOULD be used for:

* Implementing code inside an already-defined structure
* Completing functions and modules
* Refactoring for clarity and safety
* Writing unit tests
* Navigating and explaining existing code

Cursor SHOULD NOT be used for:

* Designing architecture from scratch
* Making cross-cutting architectural decisions
* Introducing new frameworks or patterns without approval

If unsure, Cursor should ask or defer.

---

## Architectural Rules (STRICT)

### 1. Hexagonal Architecture

* Domain layer is pure Python
* No IO, no HTTP, no DB, no AI calls in domain
* Adapters handle all external interaction

Violations must be flagged, not implemented.

---

### 2. Local-First Guarantee

* System must run fully offline
* SQLite is the default persistence layer
* DuckDB may be used for analytics
* No hard dependency on cloud APIs

Cursor must never assume internet access.

---

### 3. Deterministic Core

* Rule engine must be predictable
* Same input + config → same output
* AI may enhance explanations, not replace logic

---

## Data & Storage Expectations

* All market data accessed via `MarketDataProvider`
* No hardcoded providers
* Persistence logic isolated in storage adapters

Cursor should prefer simple SQL or SQLAlchemy Core.

---

## Risk, Signal, And Evidence Guardrails

Cursor must preserve the current decision boundaries:

* SignalEngine assesses evidence.
* RiskEngine blocks unsafe setups.
* TradeSetup owns setup/action verdicts.
* Market context, setup policy, and evidence authority must remain explicit and configurable.

Diagnostic evidence must not become authoritative without the promotion guardrails required by the current design docs and validators.

---

## Testing Discipline

Cursor MUST:

* Add or update unit tests when modifying domain logic
* Keep tests deterministic
* Mock adapters and external services

Skipping tests requires explicit justification.

---

## Cursor-Specific Workflow Guidance

Recommended usage:

1. Select a file or function
2. Ask Cursor to explain existing logic
3. Request incremental changes
4. Run tests after changes

Avoid large, blind rewrites.

---

## Forbidden Actions

Cursor MUST NOT:

* Inline API calls into domain logic
* Store secrets in code
* Bypass persistence for convenience
* Add trading execution logic

---

## Output Style

Cursor-generated code should:

* Be explicit and readable
* Favor simple constructs
* Include comments where intent is non-obvious

---

## Guardrail Principle

> "Fast assistance is useful only if the system stays correct."

If a request risks violating:

* Architecture
* Auditability
* Reproducibility

Cursor should stop and warn.
