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

## 12. Code Convention

### File Size Rules

- Python files <= 400 LOC are preferred.
- 401-700 LOC requires a clear single responsibility.
- > 700 LOC requires an extraction plan before adding more behavior.
- > 1000 LOC is a merge blocker unless the task is explicitly a temporary characterization/test fixture file.
- Tests follow the same thresholds; split by behavior, not by arbitrary line count.

### Filename Responsibility Rules

- File name must answer: "What responsibility lives here?"
- Use suffixes consistently:
  - `_use_case.py` for application use-case entry points.
  - `_engine.py` for first-class reusable decision engines.
  - `_builder.py` for assembling immutable evidence/DTOs from inputs.
  - `_calculator.py` or `_metrics.py` for pure computations.
  - `_parser.py` for external payload/string parsing.
  - `_repository.py` for persistence implementations.
  - `_provider.py` for external/live/cached data provider implementations.
  - `_display.py` for CLI rendering only.
  - `_commands.py` for CLI command registration only.
  - `_factory.py` for dependency construction/wiring.
  - `_validator.py`, `_applier.py`, `_verifier.py` only when the file does exactly that role.
- Avoid generic names such as `bootstrap.py`, `utils.py`, `helpers.py`, `workflow.py`, `loader.py`, or `commands.py` when the module has a more specific responsibility.

### Extraction Rules

- Extract by stable responsibility, not by private helper grouping.
- Preserve public request/response contracts during extraction.
- Keep compatibility imports temporarily when renaming widely imported modules.
- First extraction target in a large use case should be DTOs and serialization, because they reduce scan burden without altering behavior.
- Second extraction target should be pure calculators/parsers, because they are easiest to characterize with tests.
- Do not extract a new abstraction unless the filename and public API make the next change easier to locate.

### Adapter Rules

- Adapter files must not own:
  - cache freshness policy
  - fetch/backfill/refresh/retry decisions
  - persistence orchestration beyond dependency wiring
  - scoring thresholds
  - business status calculation
  - provider-specific behavior beyond choosing the adapter/provider
- Adapter files may own:
  - Typer command definitions
  - option parsing
  - request DTO construction
  - dependency wiring
  - use-case invocation
  - output rendering
  - exception-to-user-message mapping

### Display Rules

- Display modules render facts; they do not decide facts.
- Any label derived from thresholds must either:
  - consume a label already computed by application/domain, or
  - clearly be named as presentation-only and backed by config/response metadata.
- Display defaults must not drift from engine/use-case config.

### DTO and Serialization Rules

- DTOs used by multiple functions/classes in a large workflow belong in `src/application/dto/`.
- `to_dict()` schema methods should live near DTO definitions unless they are adapter-specific.
- Persisted JSON/CSV/schema fields require compatibility notes before rename.
- New machine-facing outputs must include explicit names; avoid generic `score`, `status`, or `verdict` unless the artifact contract defines them.

### Infrastructure Provider Rules

- Provider files split by external capability, not by vendor alone once they exceed 700 LOC.
- Raw payload parsers should be separate from network/browser clients.
- Browser lifecycle must not share a file with HTTP payload parsers unless the file is small and strictly cohesive.
- Provider class names and filenames must match the dominant mechanism: `playwright_*` for browser, `stockbit_api_*` or `stockbit_http_*` for HTTP/token API.

### Test Organization Rules

- Split tests by behavior contract.
- Test file name must map to the production responsibility being protected.
- Prefer focused fixtures over one global mega-fixture.
- Characterization tests are required before extracting files above 1000 LOC.

---

## Final Acknowledgement

Before proceeding, the agent must internally acknowledge:

"I am operating under the Prompt Contract, Definition of Done, Task Template, and AI Agent Pre-Flight Checklist."
