# ADR-060: Read-only TUI context agent

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — 2026-08-02  
**Date:** 2026-08-02  
**Amends:** [ADR-051](ADR-051-tui-opencode-cockpit-clean-break.md)  
**Depends on:** [ADR-002](ADR-002-rule-first-ai-optional-design.md),
[ADR-003](ADR-003-hexagonal-ports-adapters-architecture.md),
[ADR-040](ADR-040-manual-dependency-injection-and-composition-roots.md), and
[ADR-042](ADR-042-deterministic-champion-and-optional-model-challengers.md)  
**Implementation roadmap:**
[`docs/roadmap/roadmap_tui_ai_agent_implementation.md`](../roadmap/roadmap_tui_ai_agent_implementation.md)

## Context

ADR-051 intentionally shipped the Textual daily cockpit without AI chat. The
cockpit now has a prompt rail and display-only `idle | agent | cli` modes, but
`CockpitApp.on_input_submitted()` only reports `not wired yet`.

The repository also has purpose-specific AI integrations for risk explanation,
formula/strategy translation, sentiment, and pre-open research. Those contracts
do not provide a conversational orchestrator, typed context envelope, agent
tool registry, session contract, or provider-neutral agent model port. One
legacy researcher also constructs a concrete Anthropic client inside the
application layer; that is not precedent for new code.

The first TUI AI slice must add useful explanation without turning model prose
into a second decision engine or widening the prompt into a command shell.

## Decision

### Product boundary

The first implementation is an optional, one-turn, read-only assistant for the
currently visible **accumulation Judge** result.

It may:

- receive the exact `AccumulationCandidate` already held by the selected board
  row;
- project that candidate into a bounded, typed context containing canonical
  Action/Signal/Risk facts plus freshness, warnings, provenance, and explicitly
  labelled diagnostic fields;
- ask one configured model to explain that context in response to the
  operator's question;
- render the answer as non-authoritative agent commentary.

It may not call tools in this first slice. It may not fetch, recompute, query a
repository, execute a CLI command, persist a conversation, or perform a write.

Pre-open, ticker browse, broker browse, plan, paper, and other cockpit surfaces
remain unchanged until separately activated by a follow-up task using the same
contract.

### Layer ownership

```text
CockpitApp prompt / transcript                         Adapter
        |
        | AgentTurnRequest + exact selected candidate
        v
ExplainAccumulationCandidateUseCase                  Application
  - input bounds
  - candidate -> immutable context projection
  - authority-preserving system prompt
  - typed success/unavailable/failure result
        |
        v
AgentModelPort                                        Application port
        |
        v
configured provider adapter                          Infrastructure
```

- Domain remains free of conversation and provider contracts.
- Application owns request validation, context projection, authority wording,
  budgets, and failure semantics.
- Infrastructure owns SDK/HTTP calls, credentials, timeouts, provider/model
  identity, usage extraction, and provider-error normalization.
- TUI owns input, worker dispatch, cancellation/late-result rejection, and
  rendering only.
- A channel-neutral infrastructure composition factory constructs the concrete
  provider adapter. The TUI composition root calls that factory and injects the
  application use case. No service locator or DI framework is introduced.

### Required application contract

The implementation task must define immutable equivalents of:

```text
AgentTurnRequest
  user_text
  visible_accumulation_candidate

AgentAccumulationContext
  schema_id = tui_agent.accum_judge.v1
  context_reference
  ticker
  as_of
  immutable TradeSetup facts
  immutable Signal facts and decision constraints
  immutable Risk facts when available
  immutable AccumScoreBreakdown facts
  raw typed rationale facts
  immutable setup readiness / diagnostic setup phase / freshness
  immutable setup+flow availability and source dates
  ordered warnings

AgentTurnResult
  status: SUCCESS | UNAVAILABLE | FAILED
  answer
  context_reference
  provider
  model
  response_id
  warnings
  usage
  error_message
```

The projection contains typed values, not the Rich/Textual-rendered Judge text.
It contains no open-ended mapping and does not duplicate the adapter-owned
deterministic `format_action_why()` sentence. Instead, it carries unmodified
TradeSetup, Signal, Risk, constraint, readiness, and coverage rationale fields
so the model can explain them without becoming a second display-policy owner.
Sector macro, named setup evaluations, setup history, raw indicators, candles,
news/enrichment payloads, gate audits, and unrestricted candidate serialization
are excluded from the v1 schema.

Ticker and snapshot-date identities across the required TradeSetup,
SignalAssessment, and AccumScoreBreakdown must agree; RiskAssessment must agree
when present. Mismatch is an invariant failure. `as_of` is the TradeSetup
snapshot date.

`context_reference` is a deterministic digest of the exact turn projection. It
is a turn-local integrity/reference value, not a replacement for canonical
observation, evidence, or policy identities.

The model port accepts structured request data and returns a normalized typed
response. Provider-specific response objects never cross into the application
or TUI.

### Configuration and availability

- Existing `ai.enabled` remains the global opt-in and stays `false` by default.
- Existing provider resolution selects the requested provider using the current
  precedence: explicit argument, non-empty `AI_PROVIDER`, then `ai.provider`.
- The first implementation task may support only `deepseek` through a new
  agent-specific infrastructure adapter. Any other configured provider returns
  typed `UNAVAILABLE`; it does not silently switch providers.
- The initial DeepSeek model identity is explicit (`deepseek-v4-flash`), with
  thinking disabled, temperature `0.0`, a ten-second timeout, and SDK retries
  disabled. The exact returned model identity must accompany every success.
- Missing credentials, disabled AI, unsupported provider, and absent full
  candidate context are normal `UNAVAILABLE` states.
- No AI dependency, credential, local model, or network access is required to
  launch or use the deterministic cockpit.
- Composition represents disabled AI, unsupported provider, and missing
  credential as distinct typed availability reasons. Expected availability
  states never make cockpit construction raise and never construct a provider
  client when disabled or missing credentials.

### Authority and grounding invariants

1. The deterministic candidate and `TradeSetup.action` are computed before the
   agent runs and are never changed by it.
2. Model output is commentary only and never enters `SignalEngine`,
   `RiskEngine`, `MarketContextEngine`, `AssessTradeSetupUseCase`, sizing,
   execution, observation selection, labels, tuning, or evidence promotion.
3. Production evidence, diagnostic evidence, and corpus retain ADR-057 meaning.
   The model may explain their labels but cannot change their authority.
4. Missing, stale, limited, partial, or unavailable facts remain explicit. The
   projection and answer must not neutral-fill or reconstruct them.
5. The system prompt must tell the model to use only supplied structured facts,
   avoid buy/sell recommendations, preserve the exact canonical Action, and
   identify missing context.
6. Text embedded in news, warnings, rationale, or other projected content is
   untrusted data, never an instruction or authorization source.
7. The adapter must render deterministic facts and agent commentary as separate
   visual regions. Agent prose must not use canonical verdict styling.
8. No silent provider fallback, model fallback, retries after unknown state, or
   CLI/shell parsing is permitted.

### Failure and worker semantics

- Empty or over-limit questions fail validation before a provider call.
- Auth failure, timeout, rate limit, malformed response, provider unavailability,
  and unexpected provider failure map to stable typed results.
- Contract/invariant/programmer errors are `FAILED`, not ordinary missing data.
- Submitting a turn must not block the Textual event loop.
- Before dispatch, the TUI captures generation, originating Judge stage, ticker,
  and exact `row.source` object identity. Navigation, cancellation, focus
  change, re-judge, refresh, or a newer submission invalidates that lineage. A
  late response cannot paint into another ticker, another stage, or a newer
  candidate object for the same ticker. The adapter displays the returned
  context reference but does not re-project application context.
- Failure leaves the underlying Judge result visible and usable.

### Cockpit placement

The adapter mounts one compact `AgentCommentary` region immediately after
`JudgeDesk` inside `#stage-scroll`. It is visible only with an accumulation
Judge, remains visually non-authoritative, and never replaces or mutates the
Judge. Prompt metadata discloses `remote · deepseek` before a remote submission.

### Future channel reuse

The application use case and model port are channel-neutral. A future Telegram
adapter may reuse `ExplainAccumulationCandidateUseCase` only after a separately
approved application workflow or allowlisted read tool obtains the exact full
canonical `AccumulationCandidate`. Telegram text, ticker strings, cached board
scalars, and rendered output are not substitutes for that candidate.

This ADR does not authorize or specify Telegram transport, sender
authentication/allowlisting, polling versus webhook delivery, channel/session
identity, rate limits, message splitting, commands, persistence, or writes.
Those concerns require their own roadmap/task and, where authority or durable
identity is involved, an ADR amendment. A Telegram adapter must remain thin and
must not directly query SQLite, call market providers, recompute scoring, or
construct model clients.

## Do Not Interpret This As

- Do not implement a general agent tool loop in the first slice.
- Do not implement `cli` prompt mode or execute prompt text.
- Do not add direct SQLite, filesystem, browser, shell, MCP, or provider access
  to the TUI or model.
- Do not reuse rendered Judge text as the model's authoritative context.
- Do not widen `AIExplainer` into a conversational/tool-calling interface.
- Do not copy provider SDK imports into application code.
- Do not persist transcripts, inferred preferences, audit rows, or result
  payloads in this slice.
- Do not restore a full-screen chat route; the daily cockpit remains the owning
  product surface.
- Do not make AI availability affect board loading, Judge rendering, planning,
  fetch, paper logging, or deterministic command behavior.

## Consequences

### Positive

- The prompt rail gains one useful, bounded capability with a complete vertical
  architecture seam.
- The first model adapter can be replaced without changing TUI or application
  policy.
- Exact canonical results remain primary and operable offline.
- Later read tools and additional surfaces can reuse the turn/result contract
  after separate tasks prove their context projections.

### Costs and follow-up

- V1 answers only questions about a full accumulation Judge candidate.
- Snapshot-limited rows must be re-judged locally before the assistant is
  available; the agent cannot invent missing candidate context.
- Multi-turn memory, agent tools, additional providers, durable audit, and
  consequential actions remain future work.
- Provider model identifiers are external capability contracts and must be
  re-verified against official provider documentation before implementation.

## Implementation status

Decision accepted and contract-hardened after the 2026-08-02 readiness re-vet;
runtime implementation is tracked by
[`tasks/backlog/implement_tui_agent_accum_judge_phase1.md`](../../tasks/backlog/implement_tui_agent_accum_judge_phase1.md).
