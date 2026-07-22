# Conversational Agent Architecture

**Status:** Brainstorming note — not an ADR or implementation plan

**Date:** 2026-07-14

## Question

AI Saham is primarily a CLI application whose workflows are invoked manually.
What would be the best architecture for an interactive agent backed by OpenAI,
DeepSeek, Claude, Ollama, or another model provider?

## Recommendation

The best design is a **conversational control plane over the existing
deterministic application**, not an AI layer embedded inside SignalEngine,
RiskEngine, or MarketContextEngine.

An agent is not merely an LLM endpoint. It is the combination of:

```text
conversation
    + reasoning model
    + typed application tools
    + permission policy
    + session memory
    + audit trail
```

The existing ports-and-adapters structure is a strong foundation. Engines and
application use cases remain authoritative; the agent helps the user select,
sequence, and understand them.

## Recommended shape

```text
CLI / Web Chat / Telegram / Mobile
                 |
                 v
        Conversation Adapter
                 |
                 v
      Agent Orchestrator (Application)
      - conversation state
      - tool selection
      - approval workflow
      - context budgeting
      - response grounding
                 |
       +---------+----------+
       |                    |
       v                    v
  LLM Gateway          Typed Tool Registry
  infrastructure       application contracts
  - OpenAI             - get_daily_briefing
  - Claude             - check_data_status
  - DeepSeek           - screen_accumulation
  - Ollama             - analyze_swing
  - fallback/router    - assess_risk
                       - explain_signal
                       - refresh_market_data
                       - run_backtest
                       - propose_tuning_review
                                |
                                v
                    Existing application use cases
                                |
              +-----------------+----------------+
              |                 |                |
              v                 v                v
        SignalEngine       RiskEngine       MarketContextEngine
              |                 |                |
              +-----------------+----------------+
                                |
                                v
                     SQLite / journals / providers
```

The agent should call typed application capabilities. It should not:

- execute arbitrary shell commands;
- construct CLI strings;
- query SQLite directly;
- calculate its own stock scores;
- reinterpret diagnostic evidence as production evidence;
- edit YAML directly;
- bypass tuning, evidence-promotion, signal, or risk validators.

The CLI and conversational interface should be sibling adapters over the same
application layer.

The probabilistic model should operate inside a deterministic execution
envelope:

```text
Agent Execution Envelope
├── Context Manager
├── Model Capability Registry
├── Provider and Failure Policy
├── Typed Tool Result Envelope
├── Permission and Approval Policy
└── Preference Service
```

Model intelligence is replaceable. Context policy, authorization, execution
state, failure semantics, and provenance remain deterministic application
concerns.

## Principal components

### Agent Orchestrator

The orchestrator owns the conversational workflow:

- interpreting user intent;
- selecting registered tools;
- executing tools and inspecting structured results;
- requesting missing information;
- grounding the final answer in tool output;
- requesting approval before consequential actions.

Tool sequencing, approval rules, retries, and workflow state are application
policy, so they belong in the application layer. The orchestrator should not
contain provider-specific OpenAI, Claude, DeepSeek, or Ollama code.

### Context manager

Context management must be model-aware, deterministic-first, and
provenance-preserving. It should not simply retain the newest tokens.

| Priority | Content | Compression rule |
|---|---|---|
| P0 | System policy, permissions, current user request | Never summarize or truncate |
| P1 | Pending approvals, executed actions, current failures | Preserve exactly in structured form |
| P2 | Engine verdicts, freshness, warnings, provenance | Preserve authoritative fields exactly |
| P3 | Supporting evidence and earlier tool results | Project relevant fields and retain references |
| P4 | Conversation history | Summarize older turns |
| P5 | Raw payloads, candles, news, verbose diagnostics | Store outside context and include references/excerpts |

Recency is useful, but relevance and authority take precedence. An older
explicit user preference may matter more than a recent verbose payload.

Tools should expose two representations of a result:

```text
ToolResult
├── canonical_result       # complete typed result, stored locally
├── context_projection     # compact authoritative representation
├── result_reference       # stable identifier for rehydration
└── provenance
```

For example, a 500-stock screen should not place every row into model context.
Its projection can contain the universe, as-of date, warnings, applied filters,
distribution statistics, and leading candidates. A later question about a
specific row can retrieve it through a read-only result lookup tool.

Context compression should proceed in this order:

1. Remove redundant display formatting.
2. Convert tool output into compact typed projections.
3. Remove fields irrelevant to the current question.
4. Replace older raw results with stable references.
5. Summarize older conversational turns.
6. Ask the user to narrow scope if the safe working set still does not fit.

Silent arbitrary truncation is forbidden. LLM summaries may compress
conversation, but they must not rewrite engine values, dates, approvals,
permissions, or failures.

Each model registration should declare an effective context profile:

```text
effective_context_budget
reserved_output_tokens
reserved_tool_tokens
max_tool_schema_tokens
max_result_projection_tokens
max_history_tokens
```

Small-context Ollama models receive narrower projections or perform more
retrieval turns; they do not receive weakened policies or omitted warnings.

### Typed Tool Registry

This is the most important boundary. Each tool should have:

- a stable name and narrow business purpose;
- typed input and output schemas;
- a read/write classification;
- required permissions;
- timeout, budget, and retry limits;
- explicit freshness behavior;
- audit metadata and provenance.

For example:

```text
analyze_swing
Input:
  ticker
  as_of_date?
  include_market_context
  include_diagnostics

Output:
  data_freshness
  signal_assessment
  risk_assessment
  market_context
  trade_setup
  warnings
  provenance
```

Prefer business capabilities such as `analyze_swing` over CLI-shaped tools such
as `execute_command("saham analyze swing ...")`. This prevents coupling to Typer
syntax and preserves application boundaries.

Every execution should use a common result envelope:

```text
ToolExecutionResult
├── status: SUCCESS | PARTIAL | FAILED | UNKNOWN
├── data
├── warnings
├── errors
├── freshness
├── provenance
├── retryable
├── side_effect_status
└── result_reference
```

`UNKNOWN` differs from `FAILED`: the system cannot establish what happened,
which matters especially after a timeout around a write.

Error and partial-result rules should be deterministic:

- stop a dependency branch when a required upstream tool fails;
- allow independent branches to continue;
- retry only classified retryable errors on safe/idempotent operations;
- surface deterministic validation errors instead of reasoning around them;
- prohibit claims such as “current” or “latest” when freshness is unknown;
- name missing components explicitly in any partial response;
- fail closed after a write with unknown completion state.

The response composer can still produce a useful partial answer, but it must
make the boundary visible:

```text
Available:
- Candle data through 2026-07-13
- Signal and risk assessments completed

Unavailable:
- Broker-flow enrichment timed out
- Accumulation confirmation could not be established

Conclusion:
The setup has technical support, but the institutional-flow conclusion is
incomplete. Do not treat the WATCH verdict as flow-confirmed.
```

### Provider-neutral LLM gateway

The application should depend on a normalized model port rather than a specific
vendor SDK. Conceptually:

```text
AgentModelPort
- generate(messages, tools, response_schema)
- continue_with_tool_results(...)
- capabilities()
- estimate_usage(...)
```

Infrastructure adapters can implement the port for OpenAI, Anthropic Claude,
DeepSeek, Ollama, or future providers. The normalized contract should expose:

- messages;
- tool calls;
- structured responses;
- token usage;
- finish reason;
- retryable versus terminal errors.

Provider-specific response objects should not leak into application workflows.

No provider should be permanently privileged at the architecture level.
Selection should be driven by measured capability:

- tool-selection accuracy;
- structured-output reliability;
- Indonesian and English comprehension;
- latency and cost;
- privacy requirements;
- context-window needs.

Ollama can provide a privacy/offline path, but a local model should pass the same
tool-use evaluation suite before receiving equivalent permissions.

### Model capability registry and evaluation

Capability and authorization are separate:

> An evaluation can show that a model requests tools correctly. It never
> authorizes the requested action.

Each provider/model/version should be tested against a fixed suite:

| Category | Representative assertion |
|---|---|
| Tool selection | Chooses `analyze_swing`, not a refresh, for a read-only question |
| Argument accuracy | Produces schema-valid ticker/date/options without invented values |
| No-tool judgment | Answers conceptual questions without unnecessary calls |
| Multi-tool sequencing | Checks freshness before making a current-market claim |
| Permission compliance | Requests approval instead of attempting a durable write |
| Error recovery | Does not fabricate results after timeout or validation failure |
| Partial-result reasoning | Separates successful engine output from unavailable enrichment |
| Structured output | Produces valid tool calls and response schemas consistently |
| Injection resistance | Ignores instructions embedded in news or scraped content |
| Context pressure | Retains verdicts, warnings, provenance, and approvals after compression |
| Ambiguity handling | Requests clarification when ticker or action is materially ambiguous |
| Idempotency awareness | Does not repeat a possibly completed write after an uncertain timeout |

The suite should include happy paths, adversarial cases, stale data, malformed
tool results, provider errors, conflicting evidence, and insufficient context.

A model can then receive a capability profile such as:

```text
CHAT_ONLY
READ_TOOL_ELIGIBLE
MULTI_TOOL_READ_ELIGIBLE
WRITE_REQUEST_ELIGIBLE
```

`WRITE_REQUEST_ELIGIBLE` means only that the model may propose/request a write.
The deterministic permission policy and user still authorize it.

Certification must be tied to provider, exact model identifier/version, tool
schema version, system-prompt version, evaluation-suite version, date, score,
and failure categories. Relevant model, prompt, or schema changes require
revalidation. Unknown local models should begin as `CHAT_ONLY` or tightly
constrained read-only models.

### Provider failure and fallback contract

The LLM gateway should normalize failures instead of exposing provider-specific
exceptions:

```text
AUTH_FAILURE
RATE_LIMITED
TIMEOUT_BEFORE_RESPONSE
TIMEOUT_AFTER_TOOL_REQUEST
INVALID_STRUCTURED_OUTPUT
CAPABILITY_NOT_AVAILABLE
CONTEXT_OVERFLOW
PROVIDER_UNAVAILABLE
UNKNOWN_COMPLETION_STATE
```

Suggested semantics:

- authentication failure fails visibly rather than trying unrelated providers;
- context overflow triggers deterministic compression/narrowing before retry;
- invalid structured output permits only a limited same-provider repair;
- rate limit or outage allows cross-provider fallback only under explicit user
  or session policy;
- unknown write completion fails closed and is never automatically repeated;
- consequential operations do not switch models midway;
- read-only research may fall back when capability and privacy requirements are
  equivalent, but the change is disclosed.

A fallback model must have the required validated capability, an equal or lower
authority ceiling, compatible schemas, sufficient context, and an acceptable
data-handling policy. Fallback must never elevate permissions.

Provider changes belong in the audit trail and user-visible response, for
example:

> Claude was unavailable before any tool ran. Read-only analysis continued with
> OpenAI under the configured fallback policy.

For uncertain consequential actions, the response should instead say:

> The provider became unavailable after proposing the journal update. Nothing
> is known to have been written, so the action was not retried through another
> provider.

### Permission and approval policy

Prompts alone are not a sufficient authorization mechanism. A deterministic
policy should decide whether a requested tool may execute.

| Level | Examples | Suggested behavior |
|---|---|---|
| Read-only | status, today, view, analyze, screen | May run automatically |
| Cache refresh | fetch candles, broker flow, enrichment | May run under an explicit session policy |
| Durable journal write | confirm trade, log outcome, save watchlist | Explain intent and request confirmation |
| Config proposal | produce tuning patch artifact | Proposal only; no authority change |
| Config mutation | apply a validated patch | Explicit confirmation plus existing validators |
| Forbidden | arbitrary SQL/shell, guardrail bypass | Never exposed to the model |

The model may request a tool, but deterministic policy owns authorization.

### Grounded response composer

Responses should clearly separate engine facts, deterministic interpretation,
and model commentary:

```text
Engine result:
  Signal 74, WATCH, Risk OPEN

Deterministic interpretation:
  Entry is capped because coverage is below the configured threshold.

Agent commentary:
  This may be worth monitoring if flow confirmation improves.
```

Important claims should retain provenance:

- tool and engine used;
- observation/as-of date;
- data freshness;
- configuration version or hash;
- evidence authority;
- ticker and universe;
- stable result or observation identifier.

The agent must not silently blend its opinion into an engine verdict.

### Conversation and memory store

Two forms of memory are useful.

**Session memory** can hold:

- recent conversation;
- current ticker or universe;
- temporary user questions;
- relevant tool results.

**Durable preferences** can hold explicitly approved facts:

- default universe;
- preferred capital and risk budget;
- response language;
- notification preferences.

The model should not autonomously infer and persist trading preferences. Durable
memory should be typed, visible, editable, and explicitly accepted by the user.
Full raw conversations need not be retained when structured audit data is
sufficient.

Preference editing should go through explicit application capabilities,
regardless of whether the interface is chat, CLI, or a config editor:

```text
list_preferences
propose_preference_change
confirm_preference_change
delete_preference
```

For example:

```text
User:
Use IDX80 as my default universe from now on.

Agent:
Proposed preference change:
  analysis.default_universe
  LQ45 -> IDX80
  Scope: this user
  Persistence: durable

Apply this change?
```

Only the deterministic preference service performs the write after approval.

| Preference category | Example | Suggested authority |
|---|---|---|
| Presentation | language, verbosity, table style | Low-risk confirmation or explicit auto-save policy |
| Workflow default | universe, default horizon | Explicit confirmation |
| Financial parameter | capital, risk percentage | Explicit confirmation with a prominent diff |
| Permission policy | automatic refresh permission | Strong confirmation, narrow scope, optional expiry |
| Engine/config threshold | signal weight, risk gate | Not a preference; existing tuning/config guardrails apply |

Stored preferences should include owner/scope, typed key/value, timestamps,
source interface, confirmation record, version, and optional expiry. The model
may propose changes but never writes the preference store directly.

### Scheduler and notification service

Proactive operation should remain separate from free-form agent reasoning:

```text
Scheduler/Event Trigger
    |
    v
Deterministic workflow
    |
    v
Saved result/event
    |
    v
Notification adapter
    |
    v
"LQ45 refresh completed. Three candidates need review."
```

The scheduler should invoke known workflows rather than wake an unconstrained
LLM and ask it to decide what to do. The conversational agent can explain the
result when the user responds.

This division suits IDX session timing, including:

- pre-open collection;
- opening snapshot and tracking;
- post-open grading;
- end-of-day refresh;
- accumulation screening;
- forward labeling and readiness reporting.

### Audit and observability

An interaction audit should capture:

- user request;
- selected model and provider;
- requested, approved, denied, and executed tools;
- normalized tool inputs;
- result references or hashes;
- data as-of date;
- prompt/template version;
- model response;
- token usage, cost, and latency;
- final answer;
- any durable state change.

Secrets and sensitive raw payloads must be redacted.

## Research versus operations authority

It is useful to distinguish two authority profiles even if they share one chat
interface.

The **research agent** can:

- answer questions;
- inspect local data and freshness;
- run screeners;
- compare stocks;
- analyze signal, risk, and market context;
- explain evidence;
- run read-only backtests;
- identify stale or missing inputs.

The **operations agent** can additionally request:

- data refreshes;
- saved watchlists;
- paper-trade journal entries;
- tuning artifacts;
- explicit application of validated configuration changes.

Research should be the default. Operations authority should be elevated per
action rather than granted permanently to a conversation.

## Example interaction

```text
User:
What should I focus on this morning?

Agent:
1. Calls get_data_status.
2. Calls get_daily_briefing.
3. Finds broker data is stale.
4. Does not pretend the screen is current.

Agent:
Market candles are current, but broker-flow data is one session behind.
The preliminary candidates are BBCA, BBRI, and TLKM, but their accumulation
ranking should not be treated as current.

Would you like me to refresh broker data?

User:
Yes.

Agent:
1. Permission policy accepts the explicitly requested refresh.
2. Calls refresh_broker_data.
3. Calls screen_accumulation.
4. Calls analyze_swing for the top candidates.
5. Explains dated engine results and evidence coverage.
```

Freshness and deterministic tools constrain the conversation. The model does
not replace missing information with plausible narrative.

An unhappy-path interaction should be equally explicit:

```text
Agent:
1. Data status succeeds: candles are current.
2. Signal analysis succeeds.
3. Broker enrichment times out.
4. Risk input validation reports missing free-float data.
5. Dependent accumulation confirmation stops; independent results remain.

Response:
Signal analysis completed, but the full verdict is incomplete. Broker flow
timed out and structural risk could not be validated because free-float data is
missing. No refresh or durable write was attempted. The result is partial, not
a current trade recommendation.
```

## MCP and direct tool calling

MCP can be a useful external interface, but should not become the core business
abstraction:

```text
Application Tool Registry
       |
       +--> embedded conversational agent
       |
       +--> MCP server adapter
       |
       +--> HTTP API adapter
```

This would allow Codex, Claude Desktop, or other MCP clients to invoke the same
capabilities while application contracts remain owned by AI Saham.

For one embedded agent, direct provider tool calling is simpler. MCP becomes
more valuable when several external agent clients need discovery and access to
the same controlled tool set.

## Untrusted market content

News, company profiles, broker notes, filings, and scraped web content must be
treated as untrusted data. They may contain instruction-like text or prompt
injection.

Retrieved content should be placed in clearly delimited data fields and must
never be allowed to:

- redefine system instructions;
- authorize or request tools;
- expose credentials;
- approve a durable write;
- change evidence authority;
- influence permission policy.

Authorization must come from deterministic policy and explicit user intent,
never from retrieved content.

## Designs to avoid

- A chatbot that shells out to `saham` internally.
- One broad `analyze_anything` tool.
- Direct model access to SQLite.
- Model-owned scoring weights or evidence promotion.
- Durable trading memory inferred without explicit consent.
- Scheduled automation driven by unconstrained model reasoning.
- Natural-language model output fed into deterministic engines as trusted data.
- Separate business logic for CLI and chat.
- Silent provider fallback that changes semantics or permissions.
- Selecting cheaper models for consequential operations without capability
  validation.

## Preferred conceptual outcome

> One deterministic analysis platform, several thin interfaces, and one
> permissioned conversational orchestrator.

The engines continue deciding what configured evidence means. The agent decides
which questions to ask, invokes approved application capabilities, combines
their structured outputs, explains conflicts, and highlights missing
information.

This provides the usability of an interactive agent without turning the stock
analysis system into a probabilistic black box.
