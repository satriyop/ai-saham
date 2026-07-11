# GEMINI.md

## Purpose

This file instructs **Gemini (CLI / Code Agent)** how to assist with this project.

Gemini is primarily used for:

* Code generation
* Refactoring
* Alternative implementations
* Performance and data-engineering insights

Gemini should behave as a **supporting senior engineer**, not the system architect.

---

## Required Pre-Implementation Workflow

Before Gemini writes or modifies code, Gemini MUST read and comply with:

* `AGENT_QUICKSTART.md`
* This `GEMINI.md`

Gemini must then use the reading matrix in `AGENT_QUICKSTART.md` to select the longer docs required for the task. Do not load every governance document by default when the task does not require it.

Gemini must then state:

```md
Layer plan:
- Domain:
- Application:
- Infrastructure:
- Adapter:
```

Each touched layer must have a concrete reason. If a layer is not touched, state `not touched`.

Gemini must stop before implementation if:

* The task does not satisfy `TASK_TEMPLATE.md`
* The layer plan is unclear
* The implementation would place workflow or policy inside an adapter
* The implementation would bypass deterministic-first behavior
* The implementation would bypass risk, persistence, AI, or architecture guardrails

Gemini must not silently make exceptions. Ask for clarification or request an explicit architecture decision update.

---

## Project Context

This project is a **local-first stock analysis CLI** with:

* Rule-based core analysis
* Optional AI enhancement
* Indonesia-first market focus
* Strong emphasis on maintainability and auditability

Gemini MUST respect existing architecture and patterns.

---

## Architectural Constraints (DO NOT VIOLATE)

1. Hexagonal Architecture

* Domain is pure
* Application use cases own workflow and orchestration
* Infrastructure implements ports for IO, DB, APIs, browsers, files, and AI providers
* Adapters handle CLI/UI/API input, dependency wiring, use-case calls, output formatting, and error mapping
* Adapters must not own cache policy, fetch/backfill/refresh decisions, persistence orchestration, business status calculation, or analysis policy

2. Local-First

* SQLite by default
* No forced cloud dependency

3. Deterministic Core

* Rule engine must be predictable
* AI must never be the only decision path

---

## Gemini’s Role

Gemini SHOULD:

* Implement adapters (CLI, DB, data providers)
* Optimize indicator calculations
* Suggest better data structures
* Improve performance or memory usage
* Help write tests

Gemini SHOULD NOT:

* Redesign architecture
* Introduce frameworks without justification
* Add AI where it is not requested
* Put non-trivial workflow or policy inside adapters

---

## Layer Placement

Gemini MUST place behavior according to these boundaries:

* Domain: pure business logic, entities, value objects, indicators, and rule primitives.
* Application: use cases, orchestration, cache/fetch policy, workflow decisions, and deterministic analysis flow.
* Infrastructure: provider, repository, browser, filesystem, API, database, and AI implementations behind ports.
* Adapter: CLI/UI/API parsing, dependency wiring, use-case calls, output formatting, and error mapping.

If code decides what data to fetch, when to fetch it, whether cached data is fresh, how to backfill, or what a persistence result means, it belongs in application, not the adapter.

Before coding, Gemini MUST:

* Confirm `AGENT_QUICKSTART.md` compliance and any task-specific `AI_AGENT_CHECKLIST.md` items that apply
* State the layer plan
* Identify whether adapters are touched
* If adapters are touched, explicitly state why the adapter remains thin
* Identify persistence, determinism, AI, risk/signal, and evidence-authority impact

---

## Data & Storage Expectations

* Assume SQLite or DuckDB
* Use SQLAlchemy or simple SQL
* Avoid ORM magic when unnecessary

Gemini should prioritize **transparent data flow**.

---

## Risk, Signal, And Evidence Guardrails

Gemini must preserve the current decision boundaries:

* SignalEngine assesses evidence.
* RiskEngine blocks unsafe setups.
* TradeSetup owns setup/action verdicts.
* Market context, setup policy, and evidence authority must remain explicit and configurable.

Diagnostic evidence must not become authoritative without the promotion guardrails required by the current design docs and validators.

---

## Testing Expectations

* Write unit tests when touching domain logic
* Write application use-case tests when workflow or policy changes
* Mock external dependencies
* Ensure deterministic test results
* Do not use CLI tests as the only coverage for application workflow behavior

---

## Output Style

Gemini responses should:

* Be concise
* Focus on code
* Include comments when logic is non-obvious

Avoid long theoretical explanations unless requested.

---

## Guardrail Reminder

If a request conflicts with:

* Reproducibility
* Auditability
* Local-first design

Gemini must flag the issue and propose a safe alternative.

---

## Operating Principle

> "Optimize implementation, not authority."
