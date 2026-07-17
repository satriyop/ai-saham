# ADR-014: Full-AI Mode (Explicit Bypass Mode) — REJECTED

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)
**Status:** Rejected — 2026-06-24. Config stub `config/full_ai.yaml` deleted. No code references existed.
**Date:** 2026-06-24
**Current implementation:** No full-AI bypass path exists; model output cannot directly replace deterministic risk or signal decisions.
**Amended by:** ADR-042, which permits a future full API agent only as a parallel, non-authoritative challenger and not as a bypass.

**Original decision (withdrawn)**
The system would support a future Full-AI Mode where AI-generated analysis could bypass rule-based logic.

**Why rejected**
"Bypass rule-based logic" contradicts the project's foundational philosophy: AI is the Author, the engine is the Validator+Executor, and YAML is the contract between them. A bypass mode collapses this separation. The legitimate use case this ADR was trying to address — AI-enhanced analysis — is fully covered by:
* ADR-002 T2 Tuner: AI proposes config parameter changes from historical attribution data; human approves before application
* ADR-027 Learning Loop: systematic feedback from backtest outcomes to engine parameters
* ADR-002 T3 Proposer: AI generates new strategy/formula YAML artifacts that are validated before use

**Rule**
No code path may allow AI output to bypass the deterministic rule engine. AI
output is never a direct authoritative risk or signal decision. It may be shown
only as a clearly labelled non-authoritative challenger under ADR-042, or enter
deterministic validation as an untrusted authored artifact.

ADR-042 further distinguishes authoring/validation from decision comparison. A
future API agent may emit a clearly labelled shadow assessment beside the
canonical deterministic verdict, but its output cannot feed, replace, suppress,
or override that verdict.

**Superseded by**
ADR-002 (T2 Tuner tier), ADR-027 (Learning Loop), ADR-003 (Hexagonal validation boundary).
