# Implement TUI Agent Phase 1 — Accumulation Judge Explanation

Status: `READY` — re-vetted and contract-hardened on 2026-08-02

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

The unrelated TUI/design work that blocked this task at creation was committed
in `8abb8ba0`. The 2026-08-02 re-vet found a clean worktree and a green focused
baseline.

This does not waive the per-run ownership check. Before implementation, run
`git status --short`; preserve any new unrelated changes and report any overlap
with the file boundary below. Never clean, restore, stash, or overwrite shared
worktree changes.

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
- No Telegram adapter, bot transport, sender authentication, webhook/polling,
  channel session, or Telegram command in Phase 1. The application seam is
  channel-neutral only so a separately approved adapter can reuse it later.
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
8. Before dispatch, the adapter captures the generation, ticker, originating
   Judge stage, and exact `row.source` object identity. A late worker result is
   accepted only while all four still match. The returned `context_reference`
   is displayed and tested as projection integrity; it is not a value the
   adapter can know before the application builds the projection.

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

- `src/application/dto/accumulation_agent.py`
- `src/application/ports/agent_model.py`
- `src/application/services/agent_accumulation_context.py`
- `src/application/use_case/explain_accumulation_candidate_use_case.py`
- `src/infrastructure/ai/deepseek_agent_model.py`
- `src/infrastructure/composition/agent_model.py`
- `src/adapters/tui/widgets/agent_commentary.py`
- `tests/application/services/test_agent_accumulation_context.py`
- `tests/application/use_case/test_explain_accumulation_candidate_use_case.py`
- `tests/infrastructure/ai/test_deepseek_agent_model.py`
- `tests/infrastructure/composition/test_agent_model.py`
- `tests/adapters/tui/test_agent_commentary.py`

Expected existing files:

- `src/application/ports/__init__.py`
- `src/adapters/tui/composition.py`
- `src/adapters/tui/main.py`
- `src/adapters/tui/theme.py`
- `src/adapters/tui/widgets/__init__.py`
- `tests/adapters/tui/test_visual_parity_contracts.py`
- `tests/adapters/tui/test_finish_cockpit_slices.py`
- focused additional existing TUI tests only when needed for lifecycle wiring
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

AgentAccumulationContext
  schema_id: str
  context_reference: str
  ticker: str
  as_of: date
  trade_setup: AgentTradeSetupFacts
  signal: AgentSignalFacts
  risk: AgentRiskFacts | None
  accumulation: AgentAccumulationFacts
  rationale: AgentDecisionRationale
  setup_readiness: AgentSetupReadinessFacts | None
  setup_phase_diagnostic: AgentSetupPhaseFacts | None
  freshness: AgentFreshnessFacts | None
  source_availability: tuple[AgentSourceAvailabilityFacts, ...]
  source_dates: AgentSourceDates
  warnings: tuple[str, ...]

AgentModelRequest
  system_policy: str
  user_text: str
  context: AgentAccumulationContext
  max_output_tokens: int

AgentModelResponse
  text: str
  provider: str
  model: str
  response_id: str | None
  finish_reason: str | None
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

AgentModelUnavailableReason =
  DISABLED | UNSUPPORTED_PROVIDER | MISSING_CREDENTIAL

AgentTurnPolicy
  enabled: bool
  configured_provider: str
  model_unavailable_reason: AgentModelUnavailableReason | None
  max_question_chars: int
  max_output_tokens: int
```

Successful results require non-empty `answer`, `context_reference`, `provider`,
and `model`, with no `error_message`. Unavailable/failed results require an
empty answer and non-empty operator-safe `error_message`. Reject contradictory
states in `__post_init__`.

### Context projection

`build_agent_accumulation_context(candidate)` is pure and performs no IO.

- `schema_id` is exactly `tui_agent.accum_judge.v1`.
- Require `trade_setup`, `signal_assessment.assessment`, and
  `accum_score_breakdown`; absence is typed `UNAVAILABLE` and makes no model
  call. Risk, readiness, setup phase, freshness, and source availability remain
  explicitly optional.
- Require ticker equality across candidate, TradeSetup, SignalAssessment, and
  AccumScoreBreakdown. Require snapshot-date equality across TradeSetup,
  SignalAssessment, AccumScoreBreakdown, and RiskAssessment when risk exists.
  Any mismatch is an invariant failure and makes no model call.
- `as_of` is exactly `trade_setup.snapshot_date`; it is never inferred from the
  latest source date.
- `AgentTradeSetupFacts` copies exactly: snapshot date, Action, signal score,
  raw signal score, signal strength, blocking gates, regime, signal multiplier,
  gate tightening, and TradeSetup rationale.
- `AgentSignalFacts` copies exactly: identity purpose/policy contract, ticker,
  snapshot date, score, strength, entry quality, ordered breakdown pairs,
  rationale, authority coverage, coverage warning, and every
  `DecisionConstraints` field when present, plus `availability_enforcement`.
- `AgentRiskFacts` copies exactly: snapshot date, derived `OPEN|BLOCKED`, fired
  gate, structural flag, gate confidence, and rationale. It excludes the raw
  indicator snapshot.
- `AgentAccumulationFacts` copies exactly from `AccumScoreBreakdown`: ticker,
  snapshot date, score/max score, component coverage, missing components,
  ordered component records (`key`, points, max points, status), net-buy ratio,
  streak, VWAP discount, RSI, flow ratio, BB-width percentile, BCI label, and
  Tier-1 count. It does not call unrestricted `candidate.to_dict()`.
- `AgentDecisionRationale` transports the unmodified TradeSetup rationale,
  Signal rationale, Risk rationale, decision-constraint reasons, and coverage
  warning as separate fields. It does **not** recreate the adapter-owned
  `format_action_why()` sentence. The model may explain these labelled facts;
  the deterministic Judge continues using shared `decision_display`.
- Readiness copies exactly its family, status, current phase, missing inputs,
  and failed requirements. Setup phase is labelled diagnostic and copies the
  current/previous phase, age, detection strength, input coverage, sequence
  validity, reasons, unavailable-evidence reasons, and volume-trigger fields;
  history is excluded from v1.
- Freshness copies exactly the seven `DataFreshnessStatus` fields. Each setup or
  flow availability group copies `evidence_group`, `all_authoritative`,
  `settled_authority_fraction`, `unassessed_contributors`, and its ordered
  assessments. Each assessment copies `source_family`, `decision_at`,
  `observed_through`, `available_at`, `expected_available_at`, status,
  `is_authoritative`, reason, and notes. Groups are ordered setup then flow;
  assessment order is preserved. Source dates copy the candidate's latest
  candle, broker, and broker-daily-flow dates.
- `warnings` is a stable de-duplicated tuple, in this order: coverage warning;
  readiness missing inputs; readiness failed requirements; setup-phase
  unavailable-evidence reasons; unassessed contributor names; then reason and
  notes from non-current or non-authoritative source assessments. These are
  copied strings, not newly formatted display-policy sentences.
- V1 excludes sector-macro context, named setup evaluations, setup history,
  gate-audit payloads, raw indicators, candles, unrestricted news/enrichment,
  full database rows, secrets, and arbitrary object representations. Adding
  any excluded field requires updating this task and the schema ID first.
- All context DTOs are frozen dataclasses containing scalars, enums/dates, other
  frozen DTOs, and tuples only. No mutable or open-ended `dict`/`Mapping` field
  may cross the model port.
- Serialize the projection excluding `context_reference` with
  `json.dumps(payload, sort_keys=True, separators=(",", ":"),
  ensure_ascii=False, allow_nan=False)`, encode UTF-8, and compute
  `context_reference` as `sha256:<lowercase hex>`. Dates use ISO `YYYY-MM-DD`;
  enums use `.value`; tuples serialize as JSON arrays; absent optionals are
  explicit JSON `null`. Do not import the learning-artifact canonicalizer.

### Model port and failures

`AgentModelPort.generate(request) -> AgentModelResponse` is an application
protocol. Define typed application exceptions for authentication, timeout,
rate-limit, unavailable/capability, malformed response, and generic transport
failure.

The application use case maps expected provider exceptions to stable turn
statuses. It does not catch invariant/programmer errors from context projection
as ordinary unavailable data.

### Use case policy

`ExplainAccumulationCandidateUseCase` receives:

- `model: AgentModelPort | None`;
- `AgentTurnPolicy` containing `enabled`, normalized `configured_provider`,
  typed `model_unavailable_reason`, `max_question_chars`, and
  `max_output_tokens`.

The use case contains no Textual, Telegram, chat ID, widget, transport, or
message-formatting type. The TUI adapter supplies its exact `row.source`
candidate. A future adapter must acquire the same full candidate through a
separately approved application-owned workflow before calling this use case.

Policy invariants:

- disabled requires `model is None` and reason `DISABLED`;
- enabled with a model requires no unavailable reason;
- enabled without a model requires `UNSUPPORTED_PROVIDER` or
  `MISSING_CREDENTIAL`;
- unsupported-provider copy names `configured_provider`; credential copy never
  includes the credential value.

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

Provider capability was re-verified on 2026-08-02 against the official
[DeepSeek API guide](https://api-docs.deepseek.com/guides/function_calling/)
and [Chat Completions contract](https://api-docs.deepseek.com/api/create-chat-completion).
Re-verify those sources immediately before implementation because model IDs are
an external capability contract.

- credential: `DEEPSEEK_API_KEY`;
- endpoint: `https://api.deepseek.com`;
- model: `deepseek-v4-flash`;
- thinking: explicitly disabled with
  `extra_body={"thinking": {"type": "disabled"}}`;
- timeout: 10 seconds;
- temperature: exactly `0.0`;
- OpenAI client `max_retries=0` and one Chat Completions request per turn;
- pass no tools and set `tool_choice="none"`;
- missing choices or empty text is malformed. `stop` is normal success;
  `length` may return success with exact warning
  `Model answer reached the output limit`; `tool_calls`/`content_filter` is
  malformed and `insufficient_system_resource` is provider-unavailable;
- return exact response model, response ID, finish reason, and usage when
  available; provider is exactly `deepseek`;
- never log or return the API key or raw credential-bearing client state.

Composition behavior:

- Resolve provider using existing `resolve_ai_provider()` precedence: explicit
  argument, then non-empty `AI_PROVIDER`, then `ai.provider`; normalize lowercase.
- `ai.enabled: false` -> inject no model; use case returns `UNAVAILABLE` without
  importing/constructing the provider client; policy reason is `DISABLED`.
- `ai.enabled: true` + `ai.provider: deepseek` -> construct
  `DeepSeekAgentModel` only when `DEEPSEEK_API_KEY` is non-empty.
- missing `DEEPSEEK_API_KEY` -> inject no model with reason
  `MISSING_CREDENTIAL`; cockpit construction must not raise.
- any other configured provider -> typed `UNAVAILABLE` stating that TUI agent
  Phase 1 supports DeepSeek only; policy reason is `UNSUPPORTED_PROVIDER`.
- never fall back to mock or another real provider in production composition.

## 11. TUI Contract

- Add an optional injected `agent_turn_runner`; no runner keeps current cockpit
  startup functional.
- `agent` mode submits only while a full accumulation Judge is visible.
- `idle` mode remains non-executing. `cli` mode remains explicitly unwired.
- Run the agent turn off the UI thread.
- Mount `AgentCommentary` immediately after `JudgeDesk` inside `#stage-scroll`.
  It is displayed only for an accumulation Judge and never replaces, overlays,
  or mutates `JudgeDesk`.
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
- Before a remote request, prompt metadata identifies `remote · deepseek` when
  the provider is available; it must not imply local inference.

Worker lineage is exact:

1. Capture generation, stage ID, ticker, and the exact `row.source` object.
2. Pass that same object in `AgentTurnRequest`; never copy or reconstruct it.
3. On completion require the captured generation to remain current, the Judge
   stage to remain active, the focused ticker to match, and
   `current_row.source is captured_source`.
4. Re-judge, refresh, focus change, navigation, Esc, or a newer submission
   invalidates the generation and clears commentary.
5. Render the returned context reference, but do not re-project in the adapter.

Responsive acceptance is executable, not taste-based: headless tests cover
loading, success with a long bounded answer, unavailable, and failed states at
`80x24` and `120x40`. At both sizes the deterministic Judge remains visible,
commentary is keyboard-scrollable, metadata is not color-only, and no answer or
warning overlaps the prompt/status rows. Below `80x24`, existing resize guidance
remains authoritative.

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
- Disabled AI and missing credentials construct no OpenAI client; cockpit
  composition still succeeds.
- Provider resolution tests prove explicit argument > non-empty `AI_PROVIDER` >
  `ai.provider`; unsupported env override does not fall back to config.
- Timeout does not retry.
- The DeepSeek request pins model, thinking-disabled body, temperature,
  timeout, no tools, and zero SDK retries.
- Empty/malformed provider output cannot render as success.
- Late response for ticker A cannot paint after navigation to ticker B.
- Late response cannot paint after re-judging the same ticker with a different
  `row.source` object.
- Agent answer cannot be passed to plan, paper, screen, observation, label, or
  config workflows.

## 14. Acceptance Criteria

- [ ] ADR-060 contracts are implemented exactly.
- [ ] A full accumulation Judge can receive one grounded agent explanation.
- [ ] Deterministic facts and Agent commentary are visibly separate.
- [ ] `80x24` and `120x40` headless acceptance covers loading, long answer,
      unavailable, and failed commentary without obscuring the Judge.
- [ ] AI-disabled, unsupported, missing-key, limited-row, timeout, malformed,
      cancellation, and late-result behavior match the table above.
- [ ] No tool, write, persistence, CLI, shell, SQLite, or provider access exists
      outside the permitted model adapter.
- [ ] Existing deterministic TUI/CLI behavior is unchanged without AI.
- [ ] No direct infrastructure import exists under domain/application.
- [ ] Every dedicated Phase 1 agent test module declares
      `pytestmark = pytest.mark.agent`; TUI mount/drive tests also receive the
      independent cost-based `tui` marker.
- [ ] The `agent` slice is fully offline; no test selected only by `agent`
      requires credentials or network access.
- [ ] No unrelated worktree changes are touched or staged.
- [ ] Focused tests, TUI tests, full suite, architecture tests, Ruff gates, and
      `git diff --check` pass on the final code state.

## 15. Verification

Run after the final edit:

```bash
.venv/bin/python -m pytest \
  tests/application/services/test_agent_accumulation_context.py \
  tests/application/use_case/test_explain_accumulation_candidate_use_case.py \
  tests/infrastructure/ai/test_deepseek_agent_model.py \
  tests/infrastructure/composition/test_agent_model.py \
  tests/adapters/tui/test_agent_commentary.py -q
.venv/bin/python -m pytest tests/architecture/test_layer_boundaries.py -q
.venv/bin/python -m pytest -m "agent and not tui"
.venv/bin/python -m pytest -m "agent and tui"
.venv/bin/python -m pytest -m agent
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
  generation, stage, and exact source-object identity must also match.

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
