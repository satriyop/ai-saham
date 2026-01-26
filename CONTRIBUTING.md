# Contributing to AI-Saham

Thank you for your interest in contributing to AI-Saham! This document provides
guidelines and instructions for contributing.

## Code of Conduct

Be respectful and constructive. We're all here to build great software.

## Getting Started

### Prerequisites

- Python 3.11+
- Git

### Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/anthropics/ai-saham.git
   cd ai-saham
   ```

2. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

4. Verify setup:
   ```bash
   pytest tests/
   ```

## Architecture Overview

AI-Saham follows **hexagonal architecture** (ports and adapters):

```
src/
├── domain/           # Pure business logic, no external dependencies
│   ├── entities/     # Core domain objects (Candle, Stock)
│   ├── value_objects/# Immutable domain values (RiskAssessment, Sentiment)
│   ├── indicators/   # Technical indicator calculations
│   ├── ports/        # Abstract interfaces (Protocol classes)
│   ├── rules/        # Risk assessment rule sets
│   └── services/     # Pure domain services
│
├── application/      # Use cases orchestrating domain logic
│   └── use_case/     # Business operations
│
├── infrastructure/   # External system implementations
│   ├── data_providers/  # Market data fetching
│   ├── persistence/     # Data storage
│   ├── ai/              # AI integrations
│   └── sentiment/       # News sentiment analyzers
│
└── adapters/         # User-facing interfaces
    └── cli/          # Command-line interface
```

### Key Principles

1. **Domain purity**: Domain layer has zero external dependencies
2. **Ports and adapters**: Infrastructure implements domain ports
3. **Local-first**: System must work fully offline
4. **Deterministic by default**: AI is optional enhancement, not requirement

## Making Changes

### Branching Strategy

1. Create a feature branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes following the coding standards below

3. Submit a pull request to `main`

### Coding Standards

#### Python Style

- Follow PEP 8
- Use type hints for function signatures
- Use `ruff` for linting and formatting:
  ```bash
  ruff check src/ tests/
  ruff format src/ tests/
  ```

#### Domain Layer Rules

- **No external imports** in `src/domain/`
- Use `Protocol` for ports (not ABC where possible)
- Use frozen dataclasses for value objects
- Use `Decimal` for financial values, never `float`

#### Testing Requirements

- All domain logic must have unit tests
- Use pytest for testing
- Run full test suite before submitting:
  ```bash
  pytest tests/ -v
  ```

### Commit Messages

Follow conventional commits format:

```
type(scope): description

[optional body]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code change that neither fixes nor adds
- `test`: Adding or updating tests
- `docs`: Documentation changes
- `chore`: Maintenance tasks

Examples:
```
feat(sentiment): add keyword classifier for Indonesian headlines
fix(cli): handle network timeout gracefully
refactor(domain): extract common indicator logic
test(risk): add edge cases for conservative profile
docs: update README with sentiment examples
```

## Pull Request Process

1. **Update tests**: Add tests for new functionality
2. **Update documentation**: Update README if needed
3. **Run CI locally**: Ensure all tests and lints pass
4. **Write clear PR description**: Explain what and why

### PR Checklist

- [ ] Tests added/updated
- [ ] All tests passing (`pytest tests/`)
- [ ] Linting passes (`ruff check src/ tests/`)
- [ ] Documentation updated if needed
- [ ] Commit messages follow conventions

## Adding New Features

### Adding a New Indicator

1. Create indicator function in `src/domain/indicators/`
2. Add tests in `tests/domain/`
3. Create use case in `src/application/use_case/`
4. Add CLI command in `src/adapters/cli/main.py`

### Adding a New Data Provider

1. Create provider in `src/infrastructure/data_providers/`
2. Implement `MarketDataProvider` protocol
3. Add tests in `tests/infrastructure/`
4. Register in factory if applicable

### Adding AI Provider

1. Create explainer in `src/infrastructure/ai/`
2. Extend `BaseExplainer` class
3. Add to `ExplainerFactory`
4. Add tests

## Questions?

Open an issue for questions or discussions about contributing.
