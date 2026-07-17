# ADR-040: Manual Dependency Injection And Composition Roots

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)
**Status:** Accepted
**Date:** 2026-07-13
**Current implementation:** Dependency wiring remains explicit in composition roots/factories; adapters do not own workflow policy and no container framework is required.

### Context

The codebase already follows ports-and-adapters architecture and uses explicit
constructor injection in the main engines and workflows. Some legacy modules
previously blurred the boundary by letting application services construct
concrete infrastructure dependencies. That makes tests harder, hides vendor
coupling, and invites adapter/application drift.

### Decision

The canonical DI style is explicit manual dependency injection. The project
does not use a DI framework or service locator.

Rules:

1. Domain objects remain pure and never depend on infrastructure.
2. Application use cases/services receive dependencies through constructors,
   request objects, typed bundles, ports/protocols, typed config/policy objects,
   or narrow callables.
3. Application code must not construct concrete SQLite, Stockbit, browser,
   filesystem, HTTP, or YAML-loader implementations.
4. Infrastructure composition roots under `src/infrastructure/composition/`
   and thin CLI workflow factories own concrete wiring.
5. `src/application/*factory*.py` and `src/application/*bootstrap*.py` files are
   pure assembly/compatibility helpers only. They must not become concrete
   infrastructure composition roots.
6. Narrow callables are acceptable for small one-off seams. Repeated callable
   bundles should become a port or typed dependency bundle.

### Consequences

- Engine and workflow construction remains explicit and testable without a
  framework.
- New provider/repository/config-loader wiring belongs outside application
  policy modules.
- Architecture tests enforce the no-application-infrastructure boundary and
  guard application factory/bootstrap modules against concrete composition-root
  drift.
