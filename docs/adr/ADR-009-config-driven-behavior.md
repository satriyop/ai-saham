# ADR-009: Config-Driven Behavior

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — scope clarified
**Date:** Not recorded (legacy decision)
**Current implementation:** Evolved — tunable policy belongs in config, while invariants and validation remain code-owned.
**Decision**
Behavior differences are controlled via configuration, not code.

**Implications**

* Risk gates
* Thresholds
* AI enable/disable

**Rationale**
Promotes flexibility without branching logic.
