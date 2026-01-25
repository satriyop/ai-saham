# CLAUDE.md

## Agent & SubAgent
- Always use model Opus for Planning & Implementation.
- Always use model Haiku for code/file exploration, use sub agents for everytime you need to explore the code
- Use model Sonnet as sub agent for creating test in paralel, but switch immediately to Opus for implementation.
- When execute test code, use subagent, do not pollute context
- Offer to create skills if you find some insight that will potentially help you to work more effectively in upcoming task, skills should be project scope not user scope. Use Skill creator plugin to create the skill.

## Purpose

This file instructs **Claude Code** how to behave as a disciplined senior engineer while developing this project. Claude should treat this repository as a **real financial software product**, not a prototype or demo.

🚨 Important: What NOT to do

Do not:
- merge domain + infrastructure
- put AI logic in rules
- let adapters talk to databases directly
- skip configs and hardcode behavior

---

## Project Summary

We are building a **local-first, production-grade CLI application for stock analysis** with the following characteristics:

* Default: deterministic, rule-based technical analysis
* Optional: AI-enhanced analysis (OFF by default)
* Initial market: **Indonesia Stock Exchange (IDX)**
* Future-ready: global markets, bots, web, mobile
* Designed for maintainability, auditability, and extensibility

This is **analysis software**, not an automated trading bot.

---

## Non-Negotiable Architecture Principles

### 1. Hexagonal Architecture (Ports & Adapters)

* Domain logic must be framework-agnostic
* CLI, AI, database, and data providers are adapters
* No adapter may leak into the domain

**Rule:** If domain logic depends on an external library, the design is wrong.

---

### 2. Local-First & Offline-First

* The system MUST run fully offline by default
* No cloud services required to start
* SQLite is the default database
* DuckDB may be used for analytical workloads

---

### 3. Market Data Abstraction

All market data MUST go through a `MarketDataProvider` interface.

Examples:

* IDX CSV provider
* Yahoo Finance provider
* Alpha Vantage provider

Claude MUST NOT hardcode any data provider.

---

### 4. Analysis Strategy

#### Default Mode (Mandatory)

* Deterministic
* Rule-based
* Uses technical indicators (SMA, RSI, MACD, Bollinger Bands, ATR, etc.)

#### AI Mode (Optional)

* OFF by default
* AI acts as an **advisor**, not a decision maker
* AI output must be explainable and traceable

Claude MUST ensure the system is useful without AI.

---

### 5. Risk Profiles

The system must support multiple analysis profiles:

* Conservative: rule-heavy, confirmation-based
* Balanced: rules + AI insight
* Aggressive: AI-weighted, fewer constraints

Risk profiles MUST be configuration-driven and MUST NOT break architecture.

---

### 6. Reproducibility & Auditability

Every analysis MUST:

* Be reproducible with the same data + config
* Store indicator results
* Log rule evaluations
* Track AI contribution (if enabled)

No hidden state. No silent decisions.

---

## Development Rules for Claude

### Code Quality

* Prefer clarity over cleverness
* Small, composable functions
* Explicit types where useful

### Testing

* Domain logic MUST be unit-tested
* Adapters may be lightly tested
* Do not skip tests for "speed"

### Incremental Delivery

Claude should:

1. Build vertical slices
2. Ensure each slice is runnable
3. Avoid premature optimization

---

## Forbidden Actions

Claude MUST NOT:

* Hardcode API keys
* Embed AI calls into domain logic
* Assume continuous internet access
* Build trading execution logic
* Skip persistence for convenience

---

## Expected Output Style

Claude should:

* Explain architectural decisions briefly
* Ask clarifying questions ONLY when required
* Prefer implementation over discussion

If uncertain, Claude should choose the **simpler, safer** design.

---

## Guiding Principle

> "If AI disappears tomorrow, this system must still be valuable."




