# AI Agent Pre-Flight Checklist

This checklist must be followed **before** an AI agent writes or modifies any code in this repository.

If any item cannot be satisfied, the agent must stop and state why.

---

## 1. Context Awareness

* I have read `README.md`
* I have read `DEFINITION_OF_DONE.md`
* I have read `PROMPT_CONTRACT.md`
* I understand the system is analysis-first, not trading

---

## 2. Scope Validation

* I understand what is being asked
* I understand what is **not** being asked
* I am not adding features outside scope
* I am not redesigning architecture unless explicitly requested

---

## 3. Architecture Check

* Core logic remains independent of adapters
* No new mandatory external services are introduced
* No AI dependency is introduced into the domain layer
* Local-first assumptions are preserved
* I verified indicator initialization follows industry standard (SMA seed, warm-up, no shortcut seeding) 


---

## 4. Determinism & Safety

* The feature works without AI enabled
* Outputs are reproducible
* Configuration is explicit
* Failure modes are handled

---

## 5. Risk Profile Discipline

* Risk profile behavior is explicit
* No silent overrides of risk settings
* Conservative behavior remains conservative

---

## 6. Testing Readiness

* Core logic is testable
* No network access is required for tests
* Test data can be local or generated

---

## 7. Documentation Intent

* Changes will be explainable to a human
* Configuration and usage will be documented
* Limitations will be stated

---

## 8. Self-Check Before Proceeding

The agent must be able to answer:

* What layer am I modifying?
* Why does this belong here?
* How does this comply with DoD?
* How does this work without AI?

If any answer is unclear, stop.

---

## Final Acknowledgement

Before proceeding, the agent must internally acknowledge:

"I am operating under the Prompt Contract and Definition of Done."
