# ADR-001: Deterministic-First Core

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted
**Date:** Not recorded (legacy decision)
**Current implementation:** Aligned — deterministic-first remains a repository-wide invariant.
**Decision**
The core system must be deterministic by default.

**Implications**

* Given the same inputs and configuration, outputs must be identical.
* No hidden randomness or implicit state.
* Time, network, and AI variability must not affect core results.

**Rationale**
Trustworthy financial analysis requires reproducibility and auditability.
