# ADR-003: Hexagonal (Ports & Adapters) Architecture

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted
**Date:** Not recorded (legacy decision)
**Current implementation:** Aligned — executable architecture tests enforce the layer direction.
**Decision**
The system follows Ports & Adapters (Hexagonal) architecture.

**Implications**

* Domain depends on nothing.
* Application orchestrates domain.
* Infrastructure implements ports.
* Adapters expose interfaces (CLI, bot, web).

**Rationale**
Ensures replaceability and long-term maintainability.
