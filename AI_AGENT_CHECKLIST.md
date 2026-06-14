# AI Agent Pre-Flight Checklist

This checklist must be followed **before** an AI agent writes or modifies any code in this repository.

If any item cannot be satisfied, the agent must stop and state why.

---

## 1. Context Awareness

* I have read `README.md`
* I have read `PROMPT_CONTRACT.md`
* I have read `DEFINITION_OF_DONE.md`
* I have read `TASK_TEMPLATE.md`
* I have read my agent-specific contract, if present (`CLAUDE.md`, `GEMINI.md`, `AGENTS.md`, etc.)
* I understand the system is analysis-first, not trading

---

## 2. Scope Validation

* I understand what is being asked
* I understand what is **not** being asked
* I am not adding features outside scope
* I am not redesigning architecture unless explicitly requested
* I will ask for clarification if the task violates `TASK_TEMPLATE.md`

---

## 3. Layer Plan

Before implementation, the agent must state:

```md
Layer plan:
- Domain:
- Application:
- Infrastructure:
- Adapter:
```

Each touched layer must have a clear reason. If a layer is not touched, state `not touched`.

---

## 4. Architecture Check

* Core logic remains independent of adapters
* Domain remains free of I/O, providers, repositories, CLI, UI, and AI
* Application use cases own non-trivial workflow and orchestration
* Infrastructure implements ports and external integrations
* Adapters only parse input, call use cases, format output, and map errors
* No new mandatory external services are introduced
* No AI dependency is introduced into the domain layer
* Local-first assumptions are preserved
* I verified indicator initialization follows industry standard when indicators are involved

---

## 5. Adapter Thinness Check

Adapters may:

* Parse CLI/UI/API input
* Construct application use-case requests
* Select infrastructure implementations for wiring
* Call application use cases
* Format output
* Map exceptions to user-facing errors

Adapters must not contain:

* Cache freshness policy
* Fetch, backfill, refresh, or retry decision logic
* Persistence orchestration beyond dependency wiring
* Business status calculation
* Provider-specific behavioral branching beyond adapter selection
* Risk, indicator, sentiment, sizing, screening, or strategy policy

If an adapter needs any forbidden logic, create or reuse an application use case.

---

## 6. Determinism & Safety

* The feature works without AI enabled
* Outputs are reproducible for the same inputs, config, and data
* Configuration is explicit
* Failure modes are handled explicitly
* No hidden global state is introduced

---

## 7. Risk Profile Discipline

* Risk profile behavior is explicit when analysis behavior is touched
* No silent overrides of risk settings
* Conservative behavior remains conservative
* Conservative, Balanced, and Aggressive profiles remain compatible

---

## 8. Data & Persistence

* I know what data is read
* I know what data is written
* I know where data is persisted
* Local-first persistence is preserved
* Schema changes, if any, are explicit and justified

---

## 9. Testing Readiness

* Core/application logic is testable outside the CLI
* Tests do not require network access
* Test data can be local or generated
* Adapter tests do not substitute for application use-case tests when workflow logic changes

---

## 10. Documentation Intent

* Changes will be explainable to a human
* Configuration and usage will be documented when user-facing behavior changes
* Limitations and assumptions will be stated

---

## 11. Self-Check Before Proceeding

The agent must be able to answer:

* What layer am I modifying?
* Why does this belong here?
* Does any adapter contain policy that belongs in application?
* How does this comply with DoD?
* How does this work without AI?

If any answer is unclear, stop.

---

## Final Acknowledgement

Before proceeding, the agent must internally acknowledge:

"I am operating under the Prompt Contract, Definition of Done, Task Template, and AI Agent Pre-Flight Checklist."
