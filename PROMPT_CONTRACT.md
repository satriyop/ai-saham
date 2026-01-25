# Prompt Contract

This document defines the **binding rules** that all AI agents (Claude Code, Cursor, Gemini, etc.) must follow when working in this repository.

This contract exists to prevent architectural drift, overuse of AI, and violations of system guarantees.

This document **references and enforces** the Definition of Done (DoD).

---

## 1. Authority Hierarchy

Agents must respect the following order of authority:

1. `DEFINITION_OF_DONE.md` (quality gate)
2. `README.md` (project intent)
3. Agent-specific contracts (CLAUDE.md, GEMINI.md)
4. Existing codebase patterns
5. Task-specific instructions

If instructions conflict, **higher authority wins**.

---

## 2. Mandatory Pre-Read

Before proposing or writing any code, the agent must:

* Read `README.md`
* Read `DEFINITION_OF_DONE.md`
* Read its own agent contract (if present)

If this has not been done, the agent must stop and say so.

---

## 3. Definition of Done Enforcement

For every task, the agent must:

* Explicitly reason about DoD compliance
* Call out any DoD items that are not met
* Refuse to mark work as complete if DoD is violated

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
* Bypass risk profiles or guardrails silently

Any such change requires explicit approval.

---

## 6. Risk Profile Discipline

When analysis behavior is involved, the agent must:

* Declare supported risk profiles (Conservative, Balanced, Aggressive)
* Explain differences between profiles
* Avoid hard-coding subjective risk assumptions

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
