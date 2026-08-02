# Hermes Agent Integration Roadmap

**Status:** Proposed and parked — architecture and implementation tasks are not
yet authorized

**Prepared:** 2026-08-02

**Re-vetted against:** repository `3f1a3579` plus the local worktree on
2026-08-02; Hermes capabilities were checked against current official
documentation on the same date

**Depends on:** ADR-002, ADR-003, ADR-013, ADR-014, ADR-040, ADR-042, ADR-060,
ADR-061, and completion of the required Phase 2 read-tool subtasks

**Related roadmaps:**
[`roadmap_tui_ai_agent_implementation.md`](roadmap_tui_ai_agent_implementation.md)
and
[`roadmap_openclaw_integration.md`](roadmap_openclaw_integration.md)

## 1. Outcome

Integrate Hermes Agent as an optional external conversation and messaging
runtime for AI Saham. Hermes may ask questions, select from a closed set of
approved AI Saham read tools, and explain their typed results. AI Saham remains
the sole owner of market workflow, deterministic policy, result lineage,
freshness, and canonical Action.

The target flow is:

```text
Telegram / Hermes CLI / another Hermes channel
                    |
                    v
Hermes gateway + model + session                 External runtime
  - authenticates the channel user
  - chooses an exposed AI Saham tool
  - presents non-authoritative commentary
                    |
                    | MCP, closed read-only surface
                    v
AI Saham MCP adapter                             Adapter
  - protocol validation and bounded serialization
  - calls one authenticated application entry point
                    |
                    v
ExternalAgentReadGateway                         Application
  - permission profile and request budgets
  - strict typed arguments
  - tool registry and result lineage
  - stable failure/partial semantics
                    |
                    v
Existing deterministic application use cases
                    |
                    v
Canonical deterministic result ----------------> authority
Hermes answer ----------------------------------> commentary only
```

Hermes is not an implementation of AI Saham's `AgentModelPort`. It is an
external orchestrator and channel host. The integration boundary is a new thin
adapter over application-owned read capabilities, not a second provider adapter
inside the TUI agent.

## 2. Why this boundary fits Hermes

Hermes currently supports:

- consuming local stdio and remote HTTP MCP servers, with server-level tool
  filtering;
- a messaging gateway including Telegram;
- sender allowlists and DM pairing;
- persistent sessions, skills, and a broad terminal/tool runtime.

Those are useful delivery capabilities, but they also mean Hermes has much
broader authority than AI Saham should grant. The first integration therefore
uses Hermes as an MCP client and exposes only AI Saham-owned read tools. It does
not give Hermes repository access, a `saham` shell command, SQLite access,
market-provider credentials, or an unrestricted HTTP endpoint.

Official capability references:

- [Hermes MCP documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp)
- [Hermes messaging gateway](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/)
- [Hermes Telegram adapter](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/telegram)
- [Hermes security model](https://hermes-agent.nousresearch.com/docs/user-guide/security/)

External documentation is version-sensitive. The implementation task must pin
and re-verify the exact Hermes release and MCP behavior; this roadmap does not
make rolling `latest` a production dependency.

## 3. Locked architecture direction

### Domain

Not touched. Hermes, MCP, messages, sessions, and provider payloads do not enter
the domain.

### Application

Own one channel-neutral external read gateway that:

- exposes a closed subset of application-owned tools;
- validates exact typed arguments independently of MCP/Hermes validation;
- applies caller profile, tool count, timeout, result-size, and concurrency
  limits before execution;
- returns bounded typed projections with schema ID, status, freshness,
  warnings, provenance, source reference, and result reference;
- never accepts model prose as permission, context identity, or a canonical
  result;
- never calls a CLI/TUI presenter or parses rendered output.

Do not reuse the TUI `AgentTurnOrchestrator` as an MCP router. It owns a
provider-call state machine for one TUI turn. Reuse its typed projections,
canonical serialization, registry definitions, and read-tool implementations
where their contracts fit, behind a narrower external gateway use case.

### Infrastructure

Own concrete read-only composition, repository/provider adapters already
approved by tool-specific tasks, credential loading for the local gateway, and
safe protocol diagnostics. It does not decide what Hermes may call.

### Adapter

Add a thin MCP server adapter only after an integration ADR is accepted. The
adapter performs MCP handshake/schema translation, authenticates the configured
client boundary where the selected transport supports it, calls the application
gateway, and serializes its result. It contains no scoring, freshness fallback,
repository queries, model calls, or policy.

Hermes-owned configuration or skills teach Hermes when to call the tools and
how to label commentary. They do not duplicate AI Saham business rules.

## 4. Initial capability envelope

The first deployable Hermes integration is read-only and research-only.

Candidate maximum tool set:

1. `get_visible_cockpit_result` is **not exposed initially** because a Hermes
   chat has no trustworthy TUI-visible object lineage.
2. `get_ticker_dashboard` may be exposed after its ADR-061 subtask is complete
   and its cache-only behavior is proven.
3. `judge_accumulation_ticker` may be exposed last, only after its transitive
   no-write composition is proven.
4. `get_broker_desk` may be exposed after its ADR-061 subtask is complete and
   its cache-only behavior is proven.

The runtime registry is the intersection of:

```text
ADR-authorized tools
AND implemented/proven tools
AND external-agent permission profile
AND Hermes MCP include filter
```

The intersection can be empty. An inactive tool is absent from discovery; it
is not advertised and then failed at execution time.

Initial limits must be no wider than ADR-061: at most two sequential AI Saham
tool calls per inbound message, no retries, no parallel calls, a 15-second total
tool budget, and 64 KiB total serialized results. A new ADR may make the
external profile stricter. It may not silently make it broader.

## 5. Telegram and session boundary

Hermes may own Telegram transport because it already provides Telegram gateway
behavior, sender allowlists/pairing, and message interaction. AI Saham must not
add a second Telegram adapter for this deployment.

Before enabling Telegram:

- allowlist exact Telegram user IDs or use approved DM pairing; never enable an
  allow-all setting in production;
- use a dedicated bot token and secret store outside the repository;
- bind one Hermes identity/profile to the AI Saham read-only MCP toolset;
- deny Hermes terminal, filesystem, browser, cron, and unrelated MCP tools for
  that profile unless separately required outside this product integration;
- cap inbound size, concurrent turns, per-user rate, and outbound message size;
- attach a transport event/message ID to request tracing and deduplicate
  redelivery before calling AI Saham;
- label every model answer as commentary and retain exact AI Saham freshness
  and warning fields.

Hermes session memory is convenience context only. A remembered ticker, result,
or old answer is not an AI Saham `source_reference` and cannot authorize a tool.
Every tool call revalidates current typed arguments and returns fresh lineage.
AI Saham stores no transcript in the first integration.

If OpenClaw is also evaluated, do not connect the same Telegram bot token to
both gateways. One Telegram account has exactly one owning runtime.

## 6. Delivery phases

| Phase | Deliverable | Entry gate | Exit gate |
|---|---|---|---|
| H0 — Decision | Hermes integration ADR and threat model | This roadmap accepted for planning | Transport, deployment, identity, session, audit, and exact tool subset locked |
| H1 — Shared external gateway | Channel-neutral application request/result contract | At least one ADR-061 tool subtask complete | Offline contract tests prove strict validation, budgets, lineage, and no writes |
| H2 — MCP adapter | Local stdio MCP server with one read tool | H1 green; exact MCP SDK/version pinned | Schema discovery and invocation green; no CLI/SQL/repository bypass |
| H3 — Hermes profile | Pinned Hermes config plus minimal integration skill | H2 green | Only expected tools visible; malformed, extra, and unknown inputs fail closed |
| H4 — Local operator pilot | Hermes CLI against fixture/cache data | H3 green | Useful answers, bounded latency, clear partial/stale copy, deterministic app unaffected |
| H5 — Telegram pilot | Dedicated bot, allowlisted single user | H4 green; channel threat checks complete | Auth, replay, rate-limit, cancellation, splitting, and secret-redaction checks green |
| H6 — Operations | Install/update/rollback runbook | Pilot accepted | Pinned artifacts, health checks, incident steps, and disable switches rehearsed |

Each phase requires its own Task Template backlog item. H2 must start with one
tool, not the entire maximum set. A later tool is added only through its own
subtask and side-effect audit.

## 7. Implementation backlog to create after H0

- `decide_hermes_external_agent_integration.md`
- `implement_external_agent_read_gateway_foundation.md`
- `implement_ai_saham_readonly_mcp_adapter.md`
- `configure_hermes_ai_saham_read_profile.md`
- one task per tool added to the external profile
- `pilot_hermes_ai_saham_local.md`
- `pilot_hermes_ai_saham_telegram.md`
- `document_hermes_ai_saham_operations.md`

Do not create or activate all implementation tasks merely because this roadmap
exists. The ADR resolves the choices in Section 11 first.

## 8. Security and failure acceptance

The implementation must prove, with offline fakes and a disposable Hermes
profile, that:

- an unauthenticated/unpaired sender cannot reach an AI Saham call;
- unknown tools, extra arguments, malformed JSON, duplicate keys, and invalid
  ticker/broker identifiers fail before execution;
- MCP tool descriptions or result content cannot grant another permission;
- instruction-like market text remains data and cannot enable terminal, file,
  browser, network, or write tools;
- no tool path creates/migrates a database, refreshes data, updates access time,
  records an observation/ledger row, or changes any repository/file;
- missing/stale/partial facts stay explicit; Hermes cannot neutral-fill them;
- timeout, cancellation, gateway restart, and duplicated Telegram delivery do
  not cause a second execution;
- tool results over the byte budget fail closed and raw payloads are not logged;
- disabling either the AI Saham external gateway or Hermes MCP entry produces
  zero calls and leaves CLI/TUI behavior unchanged;
- the deterministic application remains usable without Hermes, its model,
  credentials, session store, or network access.

Live Telegram and model smoke tests are explicit opt-in operational checks, not
correctness gates and never part of the default test suite.

## 9. Observability and rollback

The first release records only bounded operational metadata unless a later
persistence ADR says otherwise:

- request ID and hashed/opaque caller identity;
- framework and pinned version;
- stable tool name, schema ID, status, duration, and result reference;
- source as-of/freshness and warnings;
- denial/error code with secrets and raw prompts removed.

It does not persist model prose, Telegram content, raw arguments, unrestricted
tool results, API keys, bot tokens, or full Hermes session history in AI Saham.

Rollback switches must independently disable:

1. the AI Saham external gateway;
2. the Hermes MCP server entry;
3. the Hermes Telegram account.

Rollback needs no data migration in the read-only/no-transcript release.

## 10. Non-goals

- No AI-authored Action, score, risk, sizing, evidence authority, or trade.
- No direct SQLite, CLI, shell, Python, browser, filesystem, or market-provider
  access from Hermes to AI Saham.
- No fetch, refresh, journal, paper trade, watchlist, config, tuning, label,
  corpus, promotion, or other write tool.
- No generic `analyze_anything`, SQL, command, or HTTP proxy tool.
- No implicit sharing of TUI selection or TUI session identity.
- No AI Saham transcript persistence or cross-channel identity merging.
- No reuse of Hermes security prompts as AI Saham application authorization.
- No automatic failover to OpenClaw or a second model/runtime.

## 11. Decisions required before implementation

The H0 ADR must resolve:

1. **Transport:** local stdio MCP is the recommended first pilot; HTTP MCP needs
   a separately specified authentication and network boundary.
2. **Deployment:** same non-root host/container is recommended initially;
   remote deployment adds TLS, service identity, replay protection, and network
   operations work.
3. **Model ownership:** Hermes should own the conversational model for this
   route and AI Saham should return structured facts, avoiding two model calls
   that paraphrase each other.
4. **Exact first tool:** `get_ticker_dashboard` is the preferred first candidate
   after its ADR-061 subtask proves cache-only behavior.
5. **Identity:** map each authenticated Hermes/Telegram caller to one immutable
   external-agent permission profile; do not trust a model-supplied user ID.
6. **Session retention:** Hermes may retain its own session under its policy;
   AI Saham remains stateless initially.
7. **Audit retention:** decide whether bounded metadata stays only in service
   logs or requires a new persistence ADR.
8. **Version policy:** pin Hermes, MCP SDK/protocol compatibility, and the
   integration skill/config artifact; upgrades require compatibility tests.

Until these choices are accepted and one Phase 2 tool is complete, the Hermes
integration is **not ready for runtime implementation**.

## 12. Roadmap completion criteria

- [ ] H0 integration ADR is accepted and indexed.
- [ ] All activated tasks use the Task Template and name exact file boundaries.
- [ ] The application gateway is channel/framework-neutral and has no concrete
      Hermes or MCP dependency.
- [ ] The MCP server is a thin adapter over a closed, independently validated
      application registry.
- [ ] Every exposed tool has its own transitive read-only proof.
- [ ] Hermes sees only the intended tool subset for the dedicated profile.
- [ ] Telegram sender authorization, replay, rate, and token handling are
      tested before a live pilot.
- [ ] Deterministic CLI/TUI behavior and canonical outputs remain unchanged
      with the integration enabled, disabled, or unavailable.
- [ ] Offline contract, architecture, agent, full-suite, and whole-repo Ruff
      gates pass on the implementation commit.
- [ ] Versioned install, health, update, incident, and rollback runbooks exist.

