# Prompt Contract

This document defines the **binding rules** that all AI agents (Claude Code, Cursor, Gemini, etc.) must follow when working in this repository.

This contract exists to prevent architectural drift, overuse of AI, and violations of system guarantees.

This document **references and enforces** the Definition of Done (DoD).

---

## 1. Authority Hierarchy

Agents must respect the following order of authority:

1. `DEFINITION_OF_DONE.md` (quality gate)
2. `AGENT_QUICKSTART.md` (mandatory task entry point)
3. `README.md` (project intent)
4. Agent-specific contracts (AGENTS.md, CLAUDE.md, GEMINI.md, CURSOR.md)
5. Existing codebase patterns
6. Task-specific instructions

If instructions conflict, **higher authority wins**.

---

## 2. Mandatory Preflight

Before proposing or writing any code, the agent must:

* Read `AGENT_QUICKSTART.md`
* Read its own agent contract (if present)
* Use the reading matrix in `AGENT_QUICKSTART.md` to select task-specific docs
* Read `DEFINITION_OF_DONE.md`, relevant `PROMPT_CONTRACT.md` sections, and relevant `AI_AGENT_CHECKLIST.md` sections for code changes
* Read `ARCHITECTURE_DECISIONS.md` and relevant design docs for architecture, persistence, scoring, signal, risk, tuning, strategy, market context, or evidence-promotion changes
* Read relevant `README.md` or CLI docs for user-facing command/output/workflow changes

If the required task-specific docs have not been read, the agent must stop and say so. Agents should not load every long governance document for small documentation-only or command-output tasks unless the reading matrix requires it.

---

## 3. Definition of Done Enforcement

For every task, the agent must:

* Explicitly reason about DoD compliance
* Call out any DoD items that are not met
* Refuse to mark work as complete if DoD is violated
* State the layer plan before implementation:

```md
Layer plan:
- Domain:
- Application:
- Infrastructure:
- Adapter:
```

No silent compromises are allowed.

---

## 4. Determinism First Rule

Agents must:

* Prefer deterministic, rule-based logic
* Treat AI as an enhancement layer, not a foundation
* Ensure the system works fully when AI is disabled

AI-only solutions are not acceptable unless explicitly requested.

---

## 5. Architecture Protection Rules

Agents must not:

* Introduce hidden global state
* Couple domain logic to UI, CLI, or AI providers
* Introduce mandatory cloud dependencies
* Bypass risk, signal, tuning, evidence-promotion, or architecture guardrails silently
* Destroy or overwrite unrelated worktree changes with broad git cleanup commands

Any such change requires explicit approval.

## 5.1 Shared Worktree And Git Safety

Agents must treat the local checkout as shared state:

* Inspect `git status --short` before editing, committing, or running git operations
* Stage and commit only files touched for the current task
* Leave unrelated dirty files untouched
* Never run `git reset`, `git checkout --`, `git restore`, `git clean`, broad stash commands, or equivalent destructive cleanup without explicit user approval and a stated file scope
* Stop and report conflicts when unrelated changes block the task

Silent cleanup of another agent's or user's work is a contract violation.

---

## 5.2 Adapter Thinness Rule

Adapters may:

* Parse CLI, UI, bot, or API input
* Construct application use-case requests
* Select infrastructure implementations for dependency wiring
* Call application use cases
* Format output
* Map exceptions to user-facing errors

Adapters must not contain:

* Cache freshness policy
* Fetch, backfill, refresh, retry, or warm-up decision logic
* Persistence orchestration beyond dependency wiring
* Business status calculation
* Provider-specific behavioral branching beyond adapter selection
* Risk, indicator, sentiment, sizing, screening, or strategy policy

If an adapter needs any forbidden logic, the agent must create or reuse an
application use case instead. If there is uncertainty, stop and ask for
clarification before writing code.

---

## 6. Risk And Signal Guardrail Discipline

When analysis behavior is involved, the agent must:

* Declare whether SignalEngine, RiskEngine, TradeSetup, market context, setup policy, or evidence authority is affected
* Keep blocking risk gates separate from bullish signal scoring
* Avoid hard-coding subjective risk, setup, or evidence-promotion assumptions
* Preserve diagnostic evidence as non-authoritative unless promotion guardrails are explicitly satisfied

---

## 7. AI Usage Constraints

If AI is used, the agent must:

* Explain why AI is needed
* Document prompt intent and inputs
* Ensure outputs are auditable or explainable
* Preserve non-AI execution paths

---

## 8. When in Doubt

If unsure, the agent must:

* Ask for clarification
* Or choose the **simpler, more deterministic** option

Speculation is not acceptable.

---

## 9. External Libraries & OSS Discipline

If an open-source library or third-party package is used, the agent must:

- Wrap it behind a port or infrastructure adapter
- Never import it directly into domain entities, indicators, or rules
- Ensure it can be replaced without modifying domain logic

The agent must explicitly declare:
- Which OSS/library is used
- In which layer it lives
- Why it belongs in that layer

Silent or implicit OSS coupling is not allowed.

---

## 10. Persistence Awareness

For any task involving data (market data, indicators, analysis results), the agent must:

- State whether data or results are persisted
- Justify if persistence is intentionally skipped
- Use local-first persistence by default (e.g. SQLite, DuckDB)

Ephemeral, in-memory-only behavior must be explicit and justified.

---

## 11. Sentiment Handling Rule

Sentiment analysis must be classified as one of the following:

- **Deterministic sentiment** (indicator-like, reproducible)
- **AI-based sentiment** (probabilistic, LLM-assisted)

Rules:
- Deterministic sentiment belongs in `domain/indicators`
- AI-based sentiment belongs in `infrastructure/sentiment`
- Domain rules must not depend on raw text, scraped content, or LLM outputs

Sentiment is context, not truth.

---

## 12. Indicator Initialization & Warm-Up Policy

All technical indicators must follow industry-standard initialization.

Rules:

- Indicators must not use shortcut seeding (e.g., first price as EMA seed).
- Indicators requiring warm-up (EMA, RSI, MACD, ATR, etc.) must assume sufficient input data.
- Warm-up data handling belongs in the application/use-case layer.
- Fetch layer must over-fetch required candles when necessary.
- User-facing results must exclude warm-up region and show only converged values.
- Indicators must never fabricate, pad, or extrapolate initial values.

If unsure, default to TradingView / TA-Lib behavior.

---

## 13. Architecture Boundary Enforcement (Executable)

Architecture boundary enforcement is executable, not just documented.

Before finalizing code changes, agents must run:

```
pytest tests/architecture/test_layer_boundaries.py
```

Rules:

- Application and domain code must not import infrastructure or adapters.
- If application needs config values, define application-layer policy/dataclass
  objects and have infrastructure loaders return those objects.
- Infrastructure loaders may depend inward on application policy objects;
  application use cases must not import infrastructure loaders.
- A narrow, per-import `BASELINE_ALLOWLIST` inside the test file carries
  pre-existing legacy violations. Do not add new entries to it — new code
  that imports across a forbidden boundary must be fixed, not allowlisted.

---

## Reference Architecture Decisions

All work must comply with recorded decisions in `ARCHITECTURE_DECISIONS.md`.

In particular:
- ADR-014 governs Full-AI Mode behavior.
- ADR-015 governs Sentiment Analysis classification.

If a proposed change conflicts with any ADR, the agent must stop and request an explicit architecture decision update.

---

## Final Rule

If the agent cannot explain:

"How this feature complies with the Definition of Done"

Then it must **not proceed**.
