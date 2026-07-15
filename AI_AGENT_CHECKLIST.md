# AI Agent Pre-Flight Checklist

This checklist must be followed **before** an AI agent writes or modifies any code in this repository.

Start with `AGENT_QUICKSTART.md`. Use this checklist as the detailed code-change checklist, not as a reason to load every long document for every task.

If any item cannot be satisfied, the agent must stop and state why.

---

## 1. Context Awareness

* I have read `AGENT_QUICKSTART.md`
* I have read my agent-specific contract, if present (`CLAUDE.md`, `GEMINI.md`, `AGENTS.md`, etc.)
* I have selected required task-specific docs from the `AGENT_QUICKSTART.md` reading matrix
* For code changes, I have read `DEFINITION_OF_DONE.md` and relevant `PROMPT_CONTRACT.md` sections
* For architecture, persistence, scoring, signal, risk, tuning, strategy, market context, or evidence-promotion changes, I have read relevant ADR/design/config docs
* For CLI/output/workflow changes, I have read relevant README/CLI docs
* I understand the system is analysis-first, not trading

---

## 2. Required Reading By Task Type

Use the smallest reading set that fully covers the task:

* Documentation-only: read the edited docs and referenced docs; read code only when the docs make code claims
* Local bugfix/refactor: read the touched code, focused tests, `DEFINITION_OF_DONE.md`, and relevant checklist sections
* Shared engine/risk/signal/tuning/persistence/config: read relevant ADR/design docs, configs, use cases, and tests
* CLI/output/workflow: read relevant README/CLI docs, adapter code, workflow/use case code, and command contract tests
* Architecture or boundary changes: read `ARCHITECTURE_DECISIONS.md`, relevant design docs, architecture tests, and affected layer contracts
* Ambiguous or new feature work: read `TASK_TEMPLATE.md` before implementing

If a required source is stale or contradicts code, trust the code for audit findings and document the mismatch.

---

## 3. Scope Validation

* I understand what is being asked
* I understand what is **not** being asked
* I am not adding features outside scope
* I am not redesigning architecture unless explicitly requested
* I will ask for clarification if the task violates `TASK_TEMPLATE.md`

---

## 4. Layer Plan

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

## 5. Architecture Check

* Core logic remains independent of adapters
* Domain remains free of I/O, providers, repositories, CLI, UI, and AI
* Application use cases own non-trivial workflow and orchestration
* Infrastructure implements ports and external integrations
* Adapters only parse input, call use cases, format output, and map errors
* Dependencies are injected manually through constructors, request objects, typed bundles, ports, or narrow callables
* Application use cases/services do not construct concrete SQLite, Stockbit, browser, filesystem, HTTP, or YAML-loader implementations
* If drafting instructions for another agent, follow the strict handoff harness in `AGENT_QUICKSTART.md`
* Runtime-only provider/session construction is lazy when the dependency is only needed for an optional branch
* No new mandatory external services are introduced
* No AI dependency is introduced into the domain layer
* Local-first assumptions are preserved
* I verified indicator initialization follows industry standard when indicators are involved

---

## 6. Adapter Thinness Check

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

## 7. Determinism & Safety

* The feature works without AI enabled
* Outputs are reproducible for the same inputs, config, and data
* Configuration is explicit
* Failure modes are handled explicitly
* No hidden global state is introduced

---

## 8. Shared Worktree And Git Safety

* I inspected `git status --short` before editing or git operations
* I know which dirty files are unrelated and will leave them untouched
* I will stage and commit only files owned by the current task
* I will not run `git reset`, `git checkout --`, `git restore`, `git clean`, broad stash commands, or equivalent destructive cleanup without explicit user approval and file scope
* If unrelated changes block the task, I will stop and report the conflict

---

## 9. Risk And Signal Guardrail Discipline

* SignalEngine, RiskEngine, TradeSetup, market context, setup policy, and evidence authority impact is explicit when analysis behavior is touched
* No silent overrides of risk, signal, setup, tuning, or evidence-promotion settings
* Blocking risk gates remain separate from bullish signal scoring
* Diagnostic evidence remains non-authoritative unless promotion guardrails are explicitly satisfied

---

## 10. Data & Persistence

* I know what data is read
* I know what data is written
* I know where data is persisted
* Local-first persistence is preserved
* Schema changes, if any, are explicit and justified

---

## 11. Testing Readiness

* Core/application logic is testable outside the CLI
* Tests do not require network access
* Test data can be local or generated
* Adapter tests do not substitute for application use-case tests when workflow logic changes

---

## 12. Documentation Intent

* Changes will be explainable to a human
* Configuration and usage will be documented when user-facing behavior changes
* Limitations and assumptions will be stated

---

## 13. Self-Check Before Proceeding

The agent must be able to answer:

* What layer am I modifying?
* Why does this belong here?
* Does any adapter contain policy that belongs in application?
* How does this comply with DoD?
* How does this work without AI?

If any answer is unclear, stop.

---

## 14. Code Convention

### File Size Rules

- Python files <= 400 LOC are preferred.
- 401-700 LOC requires a clear single responsibility.
- Production Python files above 550 LOC require an extraction plan before adding new behavior, even if they are below the 700 LOC threshold.
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
- When a file is split, the old file may remain only as a compatibility facade; it must not keep implementation logic.
- Compatibility facades must name the canonical replacement import path and may only re-export/delegate.
- First extraction target in a large use case should be DTOs and serialization, because they reduce scan burden without altering behavior.
- Second extraction target should be pure calculators/parsers, because they are easiest to characterize with tests.
- Use cases own workflow orchestration only; extract calculators, parsers, serializers, evidence builders, simulators, statistics, and persistence stores when they become independent scan targets.
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
- CLI command files over 300 LOC require proof they are still thin. If they
  resolve universes, run secondary use cases, save follow-up artifacts, or
  classify statuses, extract an application workflow.
- CLI command modules must not own workflow policy. If a command computes run
  guards, default precedence, multi-step orchestration, persistence schema, or
  secondary use-case calls, extract an application workflow use case.
- CLI command groups must split independently searchable responsibilities once
  they diverge. Status/session checks, display rendering, provider factories,
  and cached query commands should live in named modules instead of one broad
  command file.
- Broad CLI command files should split by public command responsibility first.
  Keep any remaining router/facade implementation-free, and move repeated
  adapter-only error/status rendering into named display/helper modules.
- Adapters must not import private application helpers. If a helper is needed
  outside its module, promote a public application service or move the
  composition outward.
- Adapter modules must not import private helpers from sibling command modules.
  Shared adapter-only behavior belongs in a public, named adapter helper,
  display module, or factory module.
- Shared dependency graphs must be explicit typed bundles or factories, not
  repeated ad hoc wiring or service-locator functions.

### Composition and Config Rules

- Manual dependency injection is the canonical pattern. Do not introduce a DI
  framework or service locator.
- Stable dependencies that cross a layer boundary should be expressed as
  application/domain ports or typed policy/config objects.
- Narrow callables are acceptable for tiny seams, but repeated callable bundles
  should become a port or typed dependency bundle.
- Application-layer modules must not be composition roots for concrete
  infrastructure. Composition belongs in adapters or infrastructure factories;
  application receives ports, typed configs, and callables.
- Do not eagerly construct concrete providers/sessions in adapter factories
  when a use case can determine they are unnecessary. Pass a lazy callable or
  narrow factory and invoke it only after the workflow proves the optional
  dependency is needed.
- Architecture allowlists are temporary debt, not accepted design. Each entry
  needs a cleanup owner, canonical replacement path, and a test preventing new
  usage.
- No module-level loaded config objects in CLI/display modules. Load config once
  per command invocation or pass it through typed command config objects.
- Import-time config objects are hidden global state. Infrastructure providers
  must receive runtime config from composition roots, not copy loaded YAML
  values into module-level constants.

### Display Rules

- Display modules render facts; they do not decide facts.
- Display modules may be large only when every function renders one cohesive
  surface. If unrelated panels share only scalar formatting helpers, split by
  panel family and move shared scalar formatting into a narrow display
  formatter module.
- Any label derived from thresholds must either:
  - consume a label already computed by application/domain, or
  - clearly be named as presentation-only and backed by config/response metadata.
- Display defaults must not drift from engine/use-case config.

### DTO and Serialization Rules

- DTOs used by multiple functions/classes in a large workflow belong in `src/application/dto/`.
- `to_dict()` schema methods should live near DTO definitions unless they are adapter-specific.
- Persisted JSON/CSV/schema fields require compatibility notes before rename.
- Domain value objects must not become persisted-schema warehouses. Large persisted fingerprints/snapshots must split field groups by schema section and keep serialization compatibility explicit.
- Persisted schema builders should split by schema section once they exceed 400 LOC.
- New machine-facing outputs must include explicit names; avoid generic `score`, `status`, or `verdict` unless the artifact contract defines them.
- Journal/store services should remain persistence-facing facades. Move DTOs,
  `to_dict()` schemas, raw-record summarization, comparison policy, and
  post-action measurement/attribution into named DTO/service modules once those
  concerns become independently searchable.

### Infrastructure Provider Rules

- Provider files split by external capability, not by vendor alone once they exceed 700 LOC.
- Raw payload parsers should be separate from network/browser clients.
- Parser modules must separate confirmed payload parsers from exploratory recursive fallback scanners. Fallback/search helpers must be named as fallback behavior, not canonical parsing.
- Browser lifecycle must not share a file with HTTP payload parsers unless the file is small and strictly cohesive.
- Provider class names and filenames must match the dominant mechanism: `playwright_*` for browser, `stockbit_api_*` or `stockbit_http_*` for HTTP/token API.
- Point-in-time cache providers must reuse shared cache primitives for fetched-date filtering, freshness checks, safe read/write handling, and schema update wrappers when semantics match. Provider-specific PIT rules must remain explicit.
- Provider files must separate endpoint orchestration, payload parsing, PIT cache
  store, and schema migration once any two of those responsibilities exceed one
  screen.
- Shared mutable infrastructure state must be explicit and injectable.
  Module-level registries, connection caches, and session stores are allowed
  only when immutable, test-resettable, or wrapped in an injected lifecycle
  object.
- Multi-provider AI adapters must split orchestration from provider transport.
  Keep prompt flow and retry logic in the adapter, provider SDK/HTTP calls in a
  client module, output canonicalization in an output module, and mock keyword
  templates in a mock-template module.

### Policy Module Rules

- Tuning and signal policy modules must split value selection, target classification, interpretation, and report assembly once those responsibilities are independently reviewable.
- Builder modules should describe one output shape. If a builder also contains
  ranking policy, source normalization, note/message policy, and fallback
  aggregation, split those responsibilities into named services.
- Evidence builders should compose by evidence family. Repeated point-in-time
  candle/broker/peer/benchmark loading belongs in a shared data-loader
  collaborator; per-family request construction belongs in named assembler
  services, not duplicated inside each coordinator.

### Repository and Config Rules

- Repository modules above 700 LOC must split schema/migration, row mapping, and table-family stores.
- Application must not import infrastructure config classes directly.
- Infrastructure may load and parse config; application consumes application/domain config models.

### Test Organization Rules

- Split tests by behavior contract.
- Test file name must map to the production responsibility being protected.
- Prefer focused fixtures over one global mega-fixture.
- Characterization tests are required before extracting files above 1000 LOC.
- Placeholder tests are not allowed; every collected test must assert real behavior or contract.
- Tests must not hide architecture violations by relying on global bootstrap
  fixtures. Pure tests construct pure services; integration tests name the
  infrastructure they exercise.
- Tests must use `monkeypatch.setattr(...)` or fixtures for temporary global
  replacement. Do not manually assign module globals and restore them in
  `finally` blocks.

---

## 15. Architecture Boundary Guard

- I ran `pytest tests/architecture/test_layer_boundaries.py`
- I did not introduce new application/domain imports from infrastructure or adapters
- If config/policy is needed by application, the consumed policy type lives in application, not infrastructure
- I did not add or expand an architecture allowlist entry

---

## Final Acknowledgement

Before proceeding on a code task, the agent must internally acknowledge:

"I am operating under the Agent Quickstart, Prompt Contract, Definition of Done, Task Template, and AI Agent Pre-Flight Checklist."
