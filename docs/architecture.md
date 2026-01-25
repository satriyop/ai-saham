# Architecture Overview

AI Saham follows **Hexagonal Architecture** (also known as Ports & Adapters) to ensure clean separation of concerns and long-term maintainability.

---

## Core Principle

> Domain logic is pure and framework-agnostic. External systems never leak into the domain.

The architecture enforces a strict dependency rule: **inner layers know nothing about outer layers**.

---

## Layer Diagram

```
                    +---------------------------+
                    |        Adapters           |
                    |  CLI | Bot | Web | API    |
                    +---------------------------+
                               |
                               v
                    +---------------------------+
                    |       Application         |
                    |  Use Cases & DTOs         |
                    +---------------------------+
                               |
                               v
                    +---------------------------+
                    |         Domain            |
                    |  Entities | Indicators    |
                    |  Ports | Rules            |
                    +---------------------------+
                               ^
                               |
                    +---------------------------+
                    |      Infrastructure       |
                    |  Yahoo | SQLite | AI      |
                    +---------------------------+
```

---

## Layer Responsibilities

### Domain Layer (`src/domain/`)

The innermost layer contains pure business logic with **zero external dependencies**.

| Component | Responsibility |
|-----------|----------------|
| `entities/` | Core business objects (Candle, Stock, IndicatorSnapshot) |
| `indicators/` | Technical indicator calculations (SMA, EMA, RSI) |
| `ports/` | Interfaces for external systems (MarketDataProvider, Repository) |
| `rules/` | Risk assessment rules by profile |

**Key rule:** Domain code must be testable without any infrastructure.

### Application Layer (`src/application/`)

Orchestrates domain logic to fulfill user requests.

| Component | Responsibility |
|-----------|----------------|
| `use_case/` | Business operations (FetchMarketData, ComputeSMA, AssessRisk) |

**Key rule:** Use cases depend only on domain ports, never on concrete implementations.

### Infrastructure Layer (`src/infrastructure/`)

Implements domain ports with concrete external systems.

| Component | Responsibility |
|-----------|----------------|
| `data_providers/` | Market data fetching (Yahoo Finance) |
| `persistence/` | Data storage (SQLite repositories) |
| `ai/` | AI integrations (future: Claude, Gemini) |

**Key rule:** Infrastructure implements domain interfaces, never the reverse.

### Adapter Layer (`src/adapters/`)

Entry points for user interaction.

| Component | Responsibility |
|-----------|----------------|
| `cli/` | Typer-based command-line interface |
| `bot/` | Telegram/WhatsApp bots (stubs) |
| `web/` | REST API (stub) |

**Key rule:** Adapters wire up dependencies and translate user input to use case requests.

---

## Dependency Rules

1. **Domain depends on nothing** - Pure Python, no external libraries
2. **Application depends on Domain** - Use cases use domain entities and ports
3. **Infrastructure depends on Domain** - Implements domain ports
4. **Adapters depend on all** - Wires everything together

**Forbidden dependencies:**
- Domain -> Infrastructure (use ports instead)
- Domain -> Adapters (domain doesn't know about CLI)
- Infrastructure -> Adapters (infrastructure is independent)

---

## Example: Fetch Market Data Flow

```
CLI Adapter                 Application              Domain                Infrastructure
-----------                 -----------              ------                --------------
fetch BBCA
     |
     v
  Create request
     |
     +----------------> FetchMarketDataUseCase
                              |
                              v
                        provider.fetch()
                              |
                              +-----------------------------------> YahooFinanceProvider
                              |                                           |
                              |                                           v
                              |                                    HTTP request
                              |                                           |
                              v                                           |
                        repository.save() <--------------+----------------+
                              |                          |
                              +------------------------->|
                              |                          v
                              |                   SQLiteRepository
                              v
                        Return response
                              |
     <------------------------+
     |
  Display results
```

---

## Testing Strategy

| Layer | Test Type | Dependencies |
|-------|-----------|--------------|
| Domain | Unit tests | None (pure functions) |
| Application | Integration tests | Mock ports |
| Infrastructure | Integration tests | Real external systems |
| Adapters | E2E tests | Full system |

---

## Adding New Features

1. **Define domain entities** if new business concepts are needed
2. **Define ports** if new external integrations are required
3. **Implement use case** orchestrating domain logic
4. **Implement infrastructure** if new external systems
5. **Add adapter command** to expose to users

Always start from the domain and work outward.
