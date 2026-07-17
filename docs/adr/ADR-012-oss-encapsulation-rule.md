# ADR-012: OSS Encapsulation Rule

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted
**Date:** Not recorded (legacy decision)
**Current implementation:** Aligned — third-party integrations remain outside the pure domain boundary.
**Decision**
Third-party libraries must be wrapped behind ports/adapters.

**Implications**

* No direct imports inside domain.

**Rationale**
Replaceability and stability.
