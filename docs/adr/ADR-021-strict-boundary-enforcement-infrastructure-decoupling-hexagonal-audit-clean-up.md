# ADR-021: Strict Boundary Enforcement & Infrastructure Decoupling (Hexagonal Audit Clean-Up)

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted
**Date:** Not recorded (legacy decision)
**Current implementation:** Aligned — executable layer-boundary tests enforce the current dependency rules and allowlist.
**Decision**
Strictly decouple pure business logic in domain and application layers from concrete infrastructure libraries (such as `sqlite3`, `PyYAML`, news scrapers, and filesystem annotation readers) by placing all database access and system-level operations behind abstract port interfaces.

**Implications**

* Domain and application use cases must never directly import database drivers, read config files from the filesystem, or hash rules directory files directly.
* Introduce dedicated port interfaces inside `application/ports/` and `domain/ports/` (e.g. `RulesLoader`, `UniverseSummaryProvider`, `AnnotationReader`, `RulesHasher`, `UniverseLoader`).
* Keep concrete library drivers encapsulated inside `infrastructure/` implementations mapping to these ports.

**Rationale**
Ensures that workflow and policy definitions remain pure and unpolluted by third-party drivers or implementation decisions. It protects the system from vendor lock-in, enables easy mocking in test suites, and lets us swap out persistence providers (e.g., SQLite to DuckDB) without modifying core business rules.
