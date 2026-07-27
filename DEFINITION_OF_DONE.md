# Definition of Done (DoD)

This document defines the **minimum acceptable quality bar** for all features, modules, and changes in this repository.

If an item does **not** meet this Definition of Done, it is **not complete**, even if it works.

---

## 1. Functional Correctness

A feature is considered done when:

* It performs the behavior described in its task or specification
* Inputs and outputs are deterministic for the same data and configuration
* Errors are handled explicitly (no silent failures)
* Edge cases are handled or clearly documented

---

## 2. Determinism & Reproducibility

The system must:

* Produce the same results when run with the same inputs, config, and data
* Separate deterministic logic from probabilistic (AI) logic
* Allow AI-based analysis to be disabled without breaking functionality
* Log all parameters that influence results

---

## 3. Architecture & Boundaries

A feature is done only if:

* Core domain logic does NOT depend on:

  * CLI
  * UI
  * External APIs
  * AI models
* Adapters (CLI, bot, web, etc.) depend on the core — never the reverse
* AI modules are optional and swappable
* Rule-based logic continues to function independently
* Adapters remain thin: non-trivial workflow, cache policy, fetch strategy,
  persistence decisions, and business status calculations live in the
  application layer
* Application behavior is testable without invoking the CLI/UI adapter

---

## 4. Risk Profile Compliance

Each analysis feature must:

* Declare which risk profiles it supports:

  * Conservative
  * Balanced
  * Aggressive
* Behave predictably for each profile
* Never override risk settings silently
* Allow future "full AI" mode without breaking existing profiles

---

## 5. Data & Persistence

If data is involved:

* Data schema is explicit and versioned
* Local-first storage is supported
* Reads and writes are idempotent where applicable
* No hidden remote dependencies are introduced

---

## 6. AI Usage Rules

If AI is used:

* AI output must never be the single source of truth
* AI decisions must be explainable or traceable
* Prompts are versioned and documented
* The system still works when AI is disabled

---

## 7. Testing Requirements

A feature is done when:

* Core logic has automated tests
* Tests do not require network access
* Tests are deterministic and repeatable
* Test data is committed or generated locally

---

## 7b. Lint Requirements (Ruff)

A code change is done when:

* Touched Python under `src/` and `tests/` passes `ruff check` and
  `ruff format --check` under the current `pyproject.toml` rule set (see
  Lint Gate in `AGENT_QUICKSTART.md`)
* After the repository-wide baseline is restored
  (`tasks/backlog/restore_repository_ruff_baseline.md`), whole-repo
  `ruff check src/ tests/` and `ruff format --check src/ tests/` pass
* Ruff config is not weakened to land the change (no new blanket ignores or
  drive-by `# noqa` outside an explicit lint task)

---

## 8. Documentation

Every completed feature must include:

* A short description of what it does
* Configuration options (if any)
* Example usage
* Known limitations or assumptions

---

## 9. Performance & Footprint

The feature must:

* Be lightweight enough for CLI usage
* Avoid unnecessary background processes
* Start fast and shut down cleanly
* Not introduce large dependencies without justification

---

## 10. Agent Compatibility

All work must:

* Be understandable by AI coding agents
* Avoid implicit assumptions
* Follow patterns already present in the codebase
* Pass review against README.md and agent contracts

---

## Final Rule

If a feature cannot clearly answer:
"How does this work without AI, and how does AI enhance it?"

Then it is **not done**.
