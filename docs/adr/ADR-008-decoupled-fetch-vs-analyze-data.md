# ADR-008: Decoupled Fetch vs Analyze Data

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted
**Date:** Not recorded (legacy decision)
**Current implementation:** Aligned — fetch volume and displayed analysis windows remain separate concerns.
**Decision**
Fetched data volume may exceed analyzed output.

**Implications**

* Over-fetch for correctness.
* Slice for presentation.

**Rationale**
Preserves mathematical integrity without burdening users.
