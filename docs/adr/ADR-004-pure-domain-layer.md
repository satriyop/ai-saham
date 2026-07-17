# ADR-004: Pure Domain Layer

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted
**Date:** Not recorded (legacy decision)
**Current implementation:** Aligned — domain remains free of infrastructure and I/O dependencies.
**Decision**
Domain layer contains only business logic and domain models.

**Implications**

* No I/O, database, network, or AI calls.
* Fully unit-testable.

**Rationale**
Keeps reasoning isolated and stable.
