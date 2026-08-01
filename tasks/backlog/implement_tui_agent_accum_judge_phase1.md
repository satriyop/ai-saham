# Implement TUI Agent Phase 1 — Accumulation Judge Explanation

Status: `READY` after the shared-worktree start gate below is cleared

Source:

- ADR-060
- `docs/roadmap/roadmap_tui_ai_agent_implementation.md`, Phase 1

## 1. Task Metadata

- Task type: Feature
- Priority: Medium
- Semantic classification: `NON_SEMANTIC` — adds optional commentary over an
  already-computed candidate; canonical signal, risk, Action, evidence
  authority, config identity, observations, labels, and persistence are
  unchanged.
- AI usage: AI-assisted, optional, non-authoritative, and bypassable.
- Chosen decision: implement one-turn explanation for a full accumulation Judge
  candidate only. Implement this option only.

## 2. Shared-worktree start gate

At task creation, the following expected implementation files or their close
design/tests have unrelated uncommitted changes:

- `src/adapters/tui/main.py`
- `docs/design/tui-cockpit-opencode.md`
- `docs/design/tui-cockpit-opencode.html`
- multiple `tests/adapters/tui/test_*.py` files

Before editing, run `git status --short`. Do not start implementation until the
owner has committed those changes or explicitly identified the exact lines/files
that this task may edit. Never clean, restore, stash, or overwrite them.

## 3. Problem Statement

The shipped cockpit contains a prominent prompt rail, but prompt submission is
display-only and reports `not wired yet`. Users cannot ask for a plain-language
explanation of the exact deterministic accumulation Judge result they are
already reviewing.

Connecting the prompt directly to an existing provider would put context
selection, authority wording, failure behavior, and vendor response handling in
the adapter. Existing `AIExplainer` is risk-specific and existing AI research
code is not an agent-grade application boundary.

## 4. Desired Outcome

When a full accumulation Judge is visible and the operator submits a non-empty
question in `agent` mode:

1. The TUI sends the question and exact selected `AccumulationCandidate` to an
   injected application use case in a worker.
2. Application code creates a bounded immutable projection from that candidate.
3. A provider-neutral model port receives only the question, system policy, and
   structured projection.
4. The TUI renders the answer as **Agent commentary**, alongside provider/model,
   as-of/context reference, and warnings.
5. The existing Judge remains visible and authoritative.

When AI is disabled, credentials are missing, the provider is unsupported, the
row is snapshot-limited, or no accumulation Judge is visible, the TUI shows a
typed honest unavailable state and performs no provider call.

## 5. Non-Goals

- No agent tools or multi-tool loop.
- No multi-turn history or summarization.
- No pre-open, ticker, broker, plan, paper, health, palette, or board-summary
  agent context.
- No prompt `cli` mode or arbitrary command execution.
- No refresh/fetch, paper log, watchlist, preference, config, strategy, formula,
  tuning, observation, label, or other write.
- No conversation/audit/result persistence or schema change.
- No direct SQLite, filesystem, browser, shell, MCP, CLI, or market-provider
  access.
- No provider fallback and no additional provider adapter beyond DeepSeek.
- No change to Signal/Risk/MCE/TradeSetup behavior or evidence authority.

## 6. Hard Invariants

1. `TradeSetup.action` from the selected candidate remains the only Action.
2. The use case consumes the exact in-memory `row.source` candidate. It must not
   re-run screen, re-query SQLite, or reconstruct an equivalent candidate.
3. Snapshot-limited rows (`row.source is None`) are unavailable. Operator copy
   directs the user to `j` re-judge; it never sends board scalars as though they
   were a full candidate.
4. The model receives a structured application projection, never Rich/Textual
   Judge output and never unrestricted `candidate.to_dict()`.
5. Production facts, diagnostic context, missing values, warnings, freshness,
   and provenance remain separately labelled.
6. Model prose cannot be consumed by any deterministic workflow or write path.
7. AI-disabled and provider-failure behavior cannot delay or degrade normal
   cockpit operation.
8. A late worker result is accepted only when its generation, ticker, context
   reference, and originating Judge stage still match.

## 7. Architecture Impact Assessment

- Domain: not touched.
- Application: new agent DTOs, port, projection service, and one-turn use case.
- Infrastructure: one DeepSeek agent-model adapter and composition wiring.
- Adapter: prompt submission, transcript/commentary widget, worker lifecycle,
  and presentation.
- New dependency: No. Reuse the existing OpenAI-compatible client dependency.
- Determinism affected: No. The model output is optional commentary only.
- Persistence affected: No.
- CLI behavior affected: No.
- Configuration behavior: reuse `ai.enabled` and `ai.provider`; both existing
  fields retain their current meaning. No scoring/material config identity
  change.
- Adapter-owned orchestration/policy: No.

```md
Layer plan:
- Domain: not touched
- Application: request/result/context DTOs, projection, model port, one-turn use case
- Infrastructure: DeepSeek transport adapter and provider error normalization
- Adapter: injected runner, worker dispatch, transcript rendering only
```

## 8. Exact File Boundary

Expected new files:

- `src/application/dto/tui_agent.py`
- `src/application/ports/agent_model.py`
- `src/application/services/agent_accumulation_context.py`
- `src/application/use_case/run_tui_agent_turn_use_case.py`
- `src/infrastructure/ai/deepseek_agent_model.py`
- `src/adapters/tui/widgets/agent_commentary.py`
- `tests/application/services/test_agent_accumulation_context.py`
- `tests/application/use_case/test_run_tui_agent_turn_use_case.py`
- `tests/infrastructure/ai/test_deepseek_agent_model.py`
- `tests/adapters/tui/test_agent_commentary.py`

Expected existing files:

- `src/application/ports/__init__.py`
- `src/adapters/tui/composition.py`
- `src/adapters/tui/main.py`
- `src/adapters/tui/widgets/__init__.py`
- focused existing TUI tests only when needed for prompt/late-result wiring
- `docs/design/tui-cockpit-opencode.md`
- `docs/design/tui-cockpit-opencode.html` only if the accepted rendered frame
  cannot be documented truthfully without updating the mock

Do not edit unrelated dirty files. Any expansion beyond this list must be
reported before editing.

## 9. Exact Application Contracts

### DTOs

Use frozen dataclasses and enums. Equivalent naming requires updating this task
before implementation; do not silently invent a different transport.

```text
AgentTurnStatus = SUCCESS | UNAVAILABLE | FAILED

AgentTurnRequest
  user_text: str
  candidate: AccumulationCandidate

AgentVisibleAccumulationContext
  context_reference: str
  ticker: str
  as_of: date | None
  action: str
  signal_score: float | None
  signal_strength: str | None
  accum_score: float
  accum_breakdown: mapping
  risk_status: str | None
  risk_gate: str | None
  why: tuple[str, ...]
  setup_readiness: mapping | None
  setup_phase: mapping | None
  freshness: mapping | None
  warnings: tuple[str, ...]
  provenance: mapping
  diagnostic_context: mapping

AgentModelRequest
  system_policy: str
  user_text: str
  context: AgentVisibleAccumulationContext
  max_output_tokens: int

AgentModelResponse
  text: str
  provider: str
  model: str
  response_id: str | None
  input_tokens: int | None
  output_tokens: int | None

AgentTurnResult
  status: AgentTurnStatus
  answer: str
  context_reference: str | None
  provider: str | None
  model: str | None
  response_id: str | None
  warnings: tuple[str, ...]
  input_tokens: int | None
  output_tokens: int | None
  error_message: str | None
```

Successful results require non-empty `answer`, `context_reference`, `provider`,
and `model`, with no `error_message`. Unavailable/failed results require an
empty answer and non-empty operator-safe `error_message`. Reject contradictory
states in `__post_init__`.

### Context projection

`build_agent_accumulation_context(candidate)` is pure and performs no IO.

- Extract Signal from `candidate.signal_assessment` without recalculation.
- Extract Action from `candidate.trade_setup.action`; missing TradeSetup makes
  the context unavailable rather than inventing Action.
- Extract risk only from `candidate.risk_assessment`.
- Extract Accum values from the candidate and its existing breakdown.
- Extract Why/readiness through application-owned typed fields. Do not import
  `src.adapters.shared.decision_display` into application.
- Put sector macro, named setup evaluations, and similar non-Action material
  under `diagnostic_context`, labelled diagnostic.
- Include date/source/availability identities already carried by the candidate.
  Do not query for more provenance.
- Omit raw candles, unrestricted news text, full database rows, secrets, and
  objects that cannot be serialized deterministically.
- Compute `context_reference` as `sha256:<lowercase hex>` over canonical JSON of
  the projection excluding `context_reference` itself.

### Model port and failures

`AgentModelPort.generate(request) -> AgentModelResponse` is an application
protocol. Define typed application exceptions for authentication, timeout,
rate-limit, unavailable/capability, malformed response, and generic transport
failure.

The application use case maps expected provider exceptions to stable turn
statuses. It does not catch invariant/programmer errors from context projection
as ordinary unavailable data.

### Use case policy

`RunTuiAgentTurnUseCase` receives:

- `model: AgentModelPort | None`;
- typed policy containing `enabled`, `max_question_chars`, and
  `max_output_tokens`.

Lock initial values:

- `max_question_chars = 2_000`;
- `max_output_tokens = 500`;
- one provider call per turn;
- no retry and no fallback.

The system policy requires concise Indonesian or English matching the question,
exact preservation of canonical Action/numbers/dates, explicit missing-data
statements, no buy/sell recommendation, no invented facts, and clear separation
of deterministic facts from commentary.

## 10. Infrastructure Contract

Implement `DeepSeekAgentModel` using the existing OpenAI-compatible SDK:

- credential: `DEEPSEEK_API_KEY`;
- endpoint: `https://api.deepseek.com`;
- model: `deepseek-chat`;
- timeout: 10 seconds;
- temperature: deterministic minimum supported by the API;
- no SDK retry;
- response text must be non-empty;
- return exact provider/model/response ID and usage when available;
- never log or return the API key or raw credential-bearing client state.

Composition behavior:

- `ai.enabled: false` -> inject no model; use case returns `UNAVAILABLE` without
  importing/constructing the provider client.
- `ai.enabled: true` + `ai.provider: deepseek` -> construct
  `DeepSeekAgentModel`.
- any other configured provider -> typed `UNAVAILABLE` stating that TUI agent
  Phase 1 supports DeepSeek only.
- never fall back to mock or another real provider in production composition.

## 11. TUI Contract

- Add an optional injected `agent_turn_runner`; no runner keeps current cockpit
  startup functional.
- `agent` mode submits only while a full accumulation Judge is visible.
- `idle` mode remains non-executing. `cli` mode remains explicitly unwired.
- Run the agent turn off the UI thread.
- Show a compact commentary region under/adjacent to the Judge without replacing
  or unmasking the Judge body.
- Render: `Agent commentary`, answer, `provider · model`, context/as-of, warnings,
  and unavailable/error copy.
- Do not style the commentary as Action/Signal/Risk or reuse verdict mast colors
  as authority.
- A second submit cancels/invalidates the first generation.
- `Esc` while a turn is loading cancels/invalidates the turn before normal
  navigation; a late result is ignored.
- Navigating away, changing focused ticker, re-judging, or refreshing invalidates
  the visible commentary and any in-flight turn.
- Never place the full prompt or model answer in notifications, logs, sidebar,
  or status text.

## 12. Missing and Failure States

| Condition | Required result/UI behavior |
|---|---|
| AI disabled | `UNAVAILABLE`: `AI is disabled in config` |
| No runner/model | `UNAVAILABLE`; deterministic Judge unchanged |
| Wrong stage | local adapter message: open an accumulation Judge first; no use-case call |
| Snapshot-limited row | unavailable: `Press j to re-judge for full context`; no model call |
| Empty question | validation message; no model call |
| Question over 2,000 chars | validation message; no model call |
| Missing TradeSetup/Action | `UNAVAILABLE`; no model call |
| Unsupported provider | `UNAVAILABLE`; name provider; no fallback |
| Missing/invalid credential | `UNAVAILABLE`; never expose credential value |
| Timeout/rate limit/provider outage | `UNAVAILABLE` with stable concise copy |
| Malformed/empty response | `FAILED` |
| Projection invariant violation | `FAILED`; do not call provider |
| Navigation/newer generation | discard late response with no paint |

## 13. Negative Tests

- AI disabled constructs/calls no provider.
- Snapshot row with `source=None` calls no use case/model.
- Candidate without `trade_setup` calls no model.
- Provider cannot change the candidate, Action, or any application input.
- Prompt and candidate text cannot inject a tool call because no tool contract is
  exposed.
- Rendered Judge text is never passed to the model.
- Candidate projection contains no raw candles, secrets, or arbitrary object
  repr.
- Unsupported provider does not fall back.
- Timeout does not retry.
- Empty/malformed provider output cannot render as success.
- Late response for ticker A cannot paint after navigation to ticker B.
- Agent answer cannot be passed to plan, paper, screen, observation, label, or
  config workflows.

## 14. Acceptance Criteria

- [ ] ADR-060 contracts are implemented exactly.
- [ ] A full accumulation Judge can receive one grounded agent explanation.
- [ ] Deterministic facts and Agent commentary are visibly separate.
- [ ] AI-disabled, unsupported, missing-key, limited-row, timeout, malformed,
      cancellation, and late-result behavior match the table above.
- [ ] No tool, write, persistence, CLI, shell, SQLite, or provider access exists
      outside the permitted model adapter.
- [ ] Existing deterministic TUI/CLI behavior is unchanged without AI.
- [ ] No direct infrastructure import exists under domain/application.
- [ ] No unrelated worktree changes are touched or staged.
- [ ] Focused tests, TUI tests, full suite, architecture tests, Ruff gates, and
      `git diff --check` pass on the final code state.

## 15. Verification

Run after the final edit:

```bash
.venv/bin/python -m pytest \
  tests/application/services/test_agent_accumulation_context.py \
  tests/application/use_case/test_run_tui_agent_turn_use_case.py \
  tests/infrastructure/ai/test_deepseek_agent_model.py \
  tests/adapters/tui/test_agent_commentary.py -q
.venv/bin/python -m pytest tests/architecture/test_layer_boundaries.py -q
.venv/bin/python -m pytest -m tui
.venv/bin/python -m pytest
ruff check src/ tests/
ruff format --check src/ tests/
git diff --check
```

Provider calls must be mocked/recorded offline. A live DeepSeek smoke test is
optional and never replaces contract tests.

## 16. Do Not Interpret This As

- Do not implement the full conversational roadmap.
- Do not support every cockpit surface in this task.
- Do not add a general tool registry “for later.”
- Do not parse or execute natural language as CLI.
- Do not expose a broad `analyze` tool or direct repositories.
- Do not treat AI prose as diagnostic evidence, production evidence, corpus, or
  a challenger Action.
- Do not silently weaken missing/failure states to make a demo answer appear.
- Do not preserve a late response because its ticker string happens to match;
  generation and context reference must also match.

## 17. Completion Record

- Completed date:
- Commit:
- Files changed:
- Focused tests:
- TUI tests:
- Full suite:
- Ruff check / format:
- Architecture tests:
- `git diff --check`:
- Shared-worktree ownership resolution:

