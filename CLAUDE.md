# CLAUDE.md

## Agent & SubAgent
- Always use model Opus for Planning & Implementation.
- Always use model Haiku for code/file exploration, use sub agents for everytime you need to explore the code
- Always use model Opus to think edge case when crafting test code, but use Sonnet sub agents to write the test code. When test code failed switch back to use model Opus to fix the implementation. in loop until all test code is passed.
- When execute test code, use subagent, do not pollute context
- Offer to create skills if you find some insight that will potentially help you to work more effectively in upcoming task, skills should be project scope not user scope. Use Skill creator plugin to create the skill.

## Required Pre-Implementation Workflow

Before Claude writes or modifies code, Claude MUST read and comply with:

- `AGENT_QUICKSTART.md`
- This `CLAUDE.md`

Claude must then use the reading matrix in `AGENT_QUICKSTART.md` to select the longer docs required for the task. Do not load every governance document by default when the task does not require it.

Claude must then state:

```md
Layer plan:
- Domain:
- Application:
- Infrastructure:
- Adapter:
```

Each touched layer must have a concrete reason. If a layer is not touched, state `not touched`.

Claude must stop before implementation if:

- The task does not satisfy `TASK_TEMPLATE.md`
- The layer plan is unclear
- The implementation would place workflow or policy inside an adapter
- The implementation would bypass deterministic-first behavior
- The implementation would bypass risk, persistence, AI, or architecture guardrails

Do not proceed by silently making a "small" exception. Ask for clarification or request an explicit architecture decision update.

## Purpose
This file instructs **Claude Code** how to behave as a disciplined senior engineer while developing this project. Claude should treat this repository as a **real financial software product**, not a prototype or demo.

🚨 Important: What NOT to do
Do not:
- merge domain + infrastructure
- put AI logic in rules
- let adapters talk to databases directly
- skip configs and hardcode behavior
- put cache freshness, fetch/backfill/refresh decisions, persistence orchestration, or business status calculation in adapters

---

## Project Summary
This project is a deterministic computational artifact runtime with AI-assisted authoring.
We believe AI should not generate opaque code that runs unchecked. Instead, AI should translate human intent into constrained, versioned, and machine-verifiable artifacts that are compiled, validated, and executed by a deterministic engine. AI-Saham turns natural language into safe computational building blocks—indicators, formulas, rules, and strategies—that can be tested, reasoned about, and reproduced. Stock analysis is our first domain, but our true mission is to provide a portable policy and strategy runtime where humans express intent, AI proposes artifacts, and the system—not the model—decides what is allowed to run.

We are building a **local-first, developer first, production-grade composable engine analyser with CLI application for stock analysis** with the following characteristics:
* “Composable stock analysis engine for developers, traders, and fintech teams — starting with Indonesia. Terraform for market analysis.
* Make strategies first-class, shareable artifacts.
* Default: deterministic, rule-based technical analysis
* Optional: AI-enhanced analysis (OFF by default)
* Initial market: **Indonesia Stock Exchange (IDX)**
* Future-ready: global markets, bots, web, mobile
* Designed for maintainability, auditability, and extensibility

This is **AI-assisted quantitative research environment, composable analysis engine**, not an automated AI trading bot.

There are three distinct roles in architecture:

1) Author : Who proposes artifacts.

2) Validator : Who decides if artifacts are acceptable.

3) Executor : Who runs artifacts.

In our project:
- AI = Author
- Engine = Validator + Executor
- YAML = Contract between them

**This separation is sacred.**

---

## Non-Negotiable Architecture Principles

### 1. Hexagonal Architecture (Ports & Adapters)

* Domain logic must be framework-agnostic
* CLI, AI, database, and data providers are adapters
* No adapter may leak into the domain
* Registry as Single Authority: The registry already knows how to dispatch to built-in, plugin, or formula.
* Non-trivial workflow belongs in `application/use_case`, not in adapters

**Rule:** If domain logic depends on an external library, the design is wrong.

**Adapter thinness rule:** CLI, bot, web, and AI adapters may parse input, select dependencies, call use cases, format output, and map errors. They must not own cache policy, fetch strategy, backfill strategy, retry decisions, persistence decisions, business status calculation, or analysis policy. If such logic is needed, create or reuse an application use case.

```
User Intent
   ↓
AI generates strategy.yaml (+ indicator definitions if needed)
   ↓
Engine validates (schema + semantics)
   ↓
If valid → usable
If invalid → rejected
```
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

#### AI Mode OFF
* Claude MUST ensure the system is useful without AI.
* OFF by default
* AI acts as an **advisor**, not a decision maker
* AI output must be explainable and traceable

#### AI Mode ON
* Claude will prioritize AI LLM as first class citizen to
* SKILL.md and SKILLS_INDEX.md are always disposable artifacts, Must be regeneratable, Never manually edited.
* AI → YAML → Validator → Registry → Runtime
* A compiler where AI writes source code
---

### 5. Risk, Signal, And Evidence Guardrails

Claude must preserve the current decision boundaries:

* SignalEngine assesses evidence.
* RiskEngine blocks unsafe setups.
* TradeSetup owns setup/action verdicts.
* Market context, setup policy, and evidence authority must remain explicit and configurable.

Diagnostic evidence MUST NOT become authoritative without the promotion guardrails required by the current design docs and validators.

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

### Before Coding

Claude MUST:

1. Confirm the task's scope and non-goals.
2. Confirm `AGENT_QUICKSTART.md` compliance and any task-specific `AI_AGENT_CHECKLIST.md` items that apply.
3. State the layer plan.
4. Identify whether adapters are touched.
5. If adapters are touched, explicitly state why the adapter remains thin.
6. Identify persistence, determinism, AI, risk/signal, and evidence-authority impact.

### Layer Placement

Claude MUST place behavior according to these boundaries:

* Domain: pure business logic, entities, value objects, indicators, rule primitives.
* Application: use cases, orchestration, cache/fetch policy, workflow decisions, deterministic analysis flow.
* Infrastructure: provider, repository, browser, filesystem, API, database, and AI implementations behind ports.
* Adapter: CLI/UI/API parsing, dependency wiring, use-case calls, output formatting, and error mapping.

If code decides what data to fetch, when to fetch it, whether cached data is fresh, how to backfill, or what a persistence result means, it belongs in application, not the adapter.

### Code Quality

* Prefer clarity over cleverness
* Small, composable functions
* Explicit types where useful

### Testing

* Domain logic MUST be unit-tested
* Application workflow/policy MUST be unit-tested when changed
* Adapters may be lightly tested
* Do not skip tests for "speed"
* CLI tests do not replace application use-case tests for workflow behavior

### Lint (Ruff)

* Follow the Lint Gate in `AGENT_QUICKSTART.md` — mandatory agent close criterion
* Touched Python under `src/`/`tests/`: `ruff check` + `ruff format --check` on
  those paths until whole-repo baseline is restored
* After `tasks/backlog/restore_repository_ruff_baseline.md`: whole-repo Ruff
  as CI
* Do not weaken Ruff config, add blanket ignores, or unreviewed repo-wide autofix

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


