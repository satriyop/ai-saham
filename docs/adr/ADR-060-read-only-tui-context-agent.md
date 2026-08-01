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
RunTuiAgentTurnUseCase                                Application
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
- The TUI composition root may construct the concrete provider adapter and
  inject the use case. No service locator or DI framework is introduced.

### Required application contract

The implementation task must define immutable equivalents of:

```text
AgentTurnRequest
  user_text
  visible_accumulation_candidate

AgentVisibleAccumulationContext
  context_reference
  ticker
  as_of
  action
  signal_score / signal_strength
  accum_score / accum_breakdown
  risk_status / risk_gate
  why
  setup_readiness
  setup_phase
  freshness
  warnings
  provenance
  diagnostic_context

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
`context_reference` is a deterministic digest of the exact turn projection. It
is a turn-local integrity/reference value, not a replacement for canonical
observation, evidence, or policy identities.

The model port accepts structured request data and returns a normalized typed
response. Provider-specific response objects never cross into the application
or TUI.

### Configuration and availability

- Existing `ai.enabled` remains the global opt-in and stays `false` by default.
- Existing `ai.provider` selects the requested provider.
- The first implementation task may support only `deepseek` through a new
  agent-specific infrastructure adapter. Any other configured provider returns
  typed `UNAVAILABLE`; it does not silently switch providers.
- The initial DeepSeek model identity is explicit (`deepseek-chat`) and must be
  returned in every successful result.
- Missing credentials, disabled AI, unsupported provider, and absent full
  candidate context are normal `UNAVAILABLE` states.
- No AI dependency, credential, local model, or network access is required to
  launch or use the deterministic cockpit.

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
- Navigation, cancellation, or a newer submission invalidates the earlier
  generation. A late response cannot paint into another ticker or stage.
- Failure leaves the underlying Judge result visible and usable.

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
- The cockpit design document and implementation files currently have unrelated
  worktree edits; the Phase 1 task may not start until their ownership is
  resolved without overwriting those changes.

## Implementation status

Decision accepted; runtime implementation is tracked by
[`tasks/backlog/implement_tui_agent_accum_judge_phase1.md`](../../tasks/backlog/implement_tui_agent_accum_judge_phase1.md).

