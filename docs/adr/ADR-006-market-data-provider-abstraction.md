# ADR-006: Market Data Provider Abstraction

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted
**Date:** Not recorded (legacy decision)
**Current implementation:** Aligned — live market access is implemented behind provider ports.
**Decision**
All market data access goes through provider ports.

**Implications**

* Yahoo Finance, IDX APIs, or paid feeds are swappable.
* Domain never references specific providers.

**Rationale**
Avoid vendor lock-in.
