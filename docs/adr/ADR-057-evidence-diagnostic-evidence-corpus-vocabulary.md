# ADR-057: Evidence, diagnostic evidence, and corpus vocabulary

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted  
**Date:** 2026-07-29  
**Depends on:** [ADR-041](ADR-041-canonical-signal-evidence-input-boundary.md),
[ADR-042](ADR-042-deterministic-champion-and-optional-model-challengers.md),
[ADR-043](ADR-043-score-naming-vocabulary.md),
[ADR-049](ADR-049-database-owned-learning-pipeline-clean-break.md),
[ADR-054](ADR-054-screen-judge-plan-structure-contract.md)  
**Amends:** operator/docs language around “evidence”; does **not** rename domain
types in a big bang (legacy `*Evidence` engine types remain until explicit
cleanup)

## Context

The word **evidence** was overloaded:

1. Live engine inputs that can change scoring / `TradeSetup.action`
2. Real but non-authoritative panels/readouts (flow detail, display-only MCE, …)
3. Stored learning material (observations, labels)

That made phrases like “analysis evidence” easy to misread as either
**production authority** or **learning corpus**.

## Decision

### 1. Binding three-way vocabulary

| Term | Meaning | Affects live Action / scoring? |
|------|---------|--------------------------------|
| **Evidence** (unqualified / production) | Real data used by live engines for scoring or gates (Signal, Risk, and Market Context **only when** it is wired into DecisionPolicy / canonical signal input) | **Yes** (or may) |
| **Diagnostic evidence** | Real data that something happened; shown for diagnosis; **not** production authority | **No** |
| **Corpus** | Evidence **stored** for learning (observations, labels, offline evaluate) | **No** for live Action |

One-line rule:

```text
If it can change Action / scoring  → evidence (production)
If it is real but must not change Action → diagnostic evidence
If it is saved for later learning  → corpus
```

### 2. Promotion is explicit

Diagnostic evidence does **not** become production evidence by renaming a
panel or a flag. Promotion requires the existing authority path (validators,
out-of-sample where required, ADR/task) — same spirit as ADR-041 / ADR-042.

Example (policy A, current):

- Screen MCE panel = **diagnostic evidence**
- Plan does **not** recompute Action via MCE/TechnicalGate
- A future “B-MCE into DecisionPolicy” task may promote MCE to **production
  evidence** on screen only after explicit acceptance

### 3. Operator-facing language

Prefer:

- **evidence** — only for production/engine authority  
- **diagnostic evidence** — real, non-production panels/readouts  
- **corpus** / **learning corpus** / **observation** — research storage  

Avoid (operator copy / new docs):

- “analysis evidence” as a product term (ambiguous)  
- Calling corpus rows bare “evidence” without “corpus” / “learning”  

### 4. Code / type names

- New code: name something `evidence` only if it participates in scoring or
  DecisionPolicy; use `diagnostic` in names/docs for non-authority readouts.
- Existing domain types (`*Evidence` builders that feed SignalEngine) stay
  **production evidence** by role; no forced mass rename in this ADR.
- Agents and humans must not invent a fourth category without amending this ADR.

### 5. Relation to screen / plan (ADR-054)

| Surface | Production evidence | Diagnostic evidence | Structure |
|---------|---------------------|---------------------|-----------|
| `screen accum` | Signal/risk (and composed Action) | Optional panels; display-only MCE under policy A | No |
| `plan swing` | Inherits Action (no recompute) | Not a second analysis desk | Capital / SL / TP / lots |
| `research` | — | — | Corpus writes |

## Consequences

- Agents use this glossary in CLI help, TUI copy, ADRs, and task write-ups.
- Policy A (MCE display-only on screen; plan structure-only) is consistent with
  this vocabulary.
- Mass renames of historical identifiers are optional follow-ups, not required
  to accept this ADR.

## Binding entry for agents

Also summarized in `AGENT_QUICKSTART.md` (mandatory every task).
