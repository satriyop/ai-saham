# ADR-005: Local-First Persistence

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted
**Date:** Not recorded (legacy decision)
**Current implementation:** Aligned — SQLite and local artifacts remain the default persistence model.
**Decision**
System persists data locally by default.

**Implications**

* SQLite or DuckDB.
* Offline-capable after initial fetch.
* No mandatory cloud dependency.

**Rationale**
Reliability and user control.
