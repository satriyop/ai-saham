# OpenClaw Integration Roadmap

**Status:** Proposed and parked — architecture and implementation tasks are not
yet authorized

**Prepared:** 2026-08-02

**Re-vetted against:** repository `3f1a3579` plus the local worktree on
2026-08-02; OpenClaw capabilities were checked against current official
documentation on the same date

**Depends on:** ADR-002, ADR-003, ADR-013, ADR-014, ADR-040, ADR-042, ADR-060,
ADR-061, and completion of the required Phase 2 read-tool subtasks

**Related roadmaps:**
[`roadmap_tui_ai_agent_implementation.md`](roadmap_tui_ai_agent_implementation.md)
and
[`roadmap_hermes_agent_integration.md`](roadmap_hermes_agent_integration.md)

## 1. Outcome

Integrate OpenClaw as an optional self-hosted conversation and messaging
gateway for AI Saham. OpenClaw may route an authenticated chat to a dedicated
agent that can call a minimal, read-only AI Saham tool set. AI Saham keeps
ownership of deterministic workflows, permissions, freshness, bounded result
projections, lineage, and canonical Action.

```text
Telegram / WebChat / another OpenClaw channel
                     |
                     v
OpenClaw Gateway + dedicated agent                 External runtime
  - channel pairing/allowlist and routing
  - model/session ownership
  - selects optional AI Saham tools
                     |
                     | managed outbound MCP
                     v
AI Saham MCP adapter                              Adapter
  - MCP protocol and bounded serialization
  - one authenticated application gateway call
                     |
                     v
ExternalAgentReadGateway                          Application
  - closed registry and caller permission profile
  - strict arguments, budgets, lineage, failures
                     |
                     v
Existing deterministic application use cases
                     |
                     v
Canonical deterministic result -----------------> authority
OpenClaw answer ---------------------------------> commentary only
```

OpenClaw is not a replacement `AgentModelPort` for the TUI. It is a separate
external orchestrator. The TUI continues using its provider-neutral application
seam; OpenClaw consumes a narrow external adapter over the same approved result
projections and read use cases.

## 2. Why this boundary fits OpenClaw

OpenClaw currently provides:

- a self-hosted Gateway that connects multiple chat channels, including core
  Telegram support;
- pairing/allowlist channel policies and per-agent/channel routing;
- an outbound MCP server registry with tool include/exclude filtering;
- native typed tool plugins and optional tool metadata;
- persistent sessions and broad built-in tools such as shell, files, browser,
  messaging, and automation.

The broad runtime must not become broad AI Saham authority. The preferred first
integration is OpenClaw's managed outbound MCP client pointed at an AI Saham
read-only MCP server. A native TypeScript tool plugin is a fallback only if a
pinned OpenClaw version cannot project the selected MCP tools into the dedicated
agent runtime; choosing that fallback requires the same application contract
and an ADR update.

Official capability references:

- [OpenClaw overview and Gateway](https://docs.openclaw.ai/)
- [OpenClaw MCP commands and outbound registry](https://docs.openclaw.ai/cli/mcp)
- [OpenClaw tools, policy, skills, and plugins](https://docs.openclaw.ai/tools)
- [OpenClaw Telegram channel](https://docs.openclaw.ai/channels/telegram)
- [OpenClaw channel access configuration](https://docs.openclaw.ai/gateway/config-channels)
- [OpenClaw security guidance](https://docs.openclaw.ai/security)

OpenClaw evolves quickly. The implementation task must pin and re-verify the
exact Gateway, MCP, plugin, and configuration contracts. Do not install or
deploy an unpinned `latest` as a production dependency.

## 3. Locked architecture direction

### Domain

Not touched. OpenClaw concepts, MCP payloads, channel IDs, messages, and sessions
do not enter the domain.

### Application

Own a framework-neutral `ExternalAgentReadGateway` (final name decided by ADR)
that:

- exposes only a closed subset of approved typed tools;
- validates caller identity/profile supplied by trusted adapter composition,
  never model arguments;
- validates exact typed tool arguments again after protocol validation;
- owns per-request tool, timeout, size, concurrency, and result budgets;
- returns bounded result DTOs with schema, status, freshness, warnings,
  provenance, source reference, and deterministic result reference;
- calls existing application entry points and never adapter presenters or CLI
  output.

Share projections, canonical serialization, and read-tool implementations with
ADR-061 where valid. Do not expose the TUI `AgentTurnOrchestrator` itself: its
two-provider-call loop is TUI conversation orchestration, while OpenClaw already
owns the conversation/model loop.

### Infrastructure

Own concrete read-only dependency wiring and transport authentication support.
It does not choose tool permissions or reconstruct missing data. Every reachable
repository/provider path must have the same transitive no-write proof required
by ADR-061.

### Adapter

Prefer one thin AI Saham MCP server adapter. It translates discovery/invocation,
authenticates the configured client boundary where supported, invokes the
application gateway, and serializes bounded results.

OpenClaw configuration owns channel routing, a dedicated agent workspace,
model selection, MCP connection details, and defense-in-depth tool filters. An
OpenClaw skill may teach usage and response labels, but must not copy scoring,
freshness, permission, or fallback policy.

If the plugin fallback is chosen, its TypeScript `execute` method remains a
thin authenticated client of the same AI Saham gateway. It must not shell out to
`saham`, open SQLite, or reimplement Python contracts.

## 4. Initial capability envelope

The first deployment is one dedicated read-only research agent.

Candidate maximum tool set:

1. Do not expose `get_visible_cockpit_result`; OpenClaw does not own a current
   TUI result object or its live lineage.
2. Expose `get_ticker_dashboard` only after its ADR-061 subtask proves cache-only
   behavior.
3. Expose `judge_accumulation_ticker` only after its explicit no-refresh/no-write
   composition is independently proven; add it last.
4. Expose `get_broker_desk` only after its cache-only subtask is complete.

Effective visibility is the intersection of:

```text
ADR-authorized tools
AND implemented/proven AI Saham registrations
AND external-agent permission profile
AND OpenClaw MCP include/exclude policy
AND dedicated-agent tool policy
```

AI Saham enforcement is authoritative. OpenClaw filters are defense in depth,
not the sole permission layer.

Limits are no wider than ADR-061: at most two sequential AI Saham calls per
inbound message, no retries or parallel calls, 15 seconds total tool time, and
64 KiB total serialized results. OpenClaw's own model/tool loop must also have a
bounded step count so it cannot repeatedly invoke separate requests to evade
the AI Saham per-message budget. The trusted adapter must propagate a stable
inbound request ID for that budget and replay boundary.

## 5. OpenClaw agent and Telegram boundary

Create a dedicated OpenClaw agent/workspace for AI Saham rather than adding the
tools to the default personal agent. Its effective tool profile must deny host
execution, elevated execution, filesystem mutation, browser, arbitrary network,
cron/automation, cross-agent delegation, and unrelated message actions unless a
separate use case explicitly needs them outside this integration.

For Telegram:

- use one dedicated bot account and route only that account to the AI Saham
  agent;
- keep DM policy at pairing or an explicit allowlist and separately restrict
  group access; do not use an open DM policy;
- store the bot token and AI Saham gateway credential outside the repository;
- map trusted OpenClaw account/channel/sender identities to one immutable AI
  Saham permission profile;
- require mention in any approved group and start with DMs for the pilot;
- cap inbound size, per-user rate, concurrent turns, and outbound splitting;
- use the inbound channel event/message identity for deduplication and tracing;
- keep AI Saham warnings, as-of values, and result references visible.

OpenClaw sessions are not canonical AI Saham state. Session history may help
conversation continuity, but remembered text cannot become a ticker validation,
source reference, freshness fact, or permission. AI Saham remains stateless in
the first release and revalidates each call.

Do not connect the same Telegram bot token to Hermes and OpenClaw. Select one
gateway owner per bot/account during pilots and production.

## 6. Delivery phases

| Phase | Deliverable | Entry gate | Exit gate |
|---|---|---|---|
| O0 — Decision | OpenClaw integration ADR and threat model | This roadmap accepted for planning | Transport, deployment, identity, session, audit, and exact tool subset locked |
| O1 — Shared external gateway | Channel-neutral application contract | At least one ADR-061 tool subtask complete | Strict validation, aggregate budgets, lineage, replay, and no-write tests green |
| O2 — MCP adapter | Local stdio MCP server with one read tool | O1 green; protocol/SDK pinned | Discovery/invocation green; no CLI/SQL/repository bypass |
| O3 — Dedicated OpenClaw agent | Pinned Gateway config, MCP filter, minimal skill | O2 green | Effective policy exposes only expected tools and denies broad runtime capabilities |
| O4 — Local Gateway pilot | WebChat/controlled local channel using fixtures/cache | O3 green | Partial/stale behavior, latency, cancellation, and deterministic independence accepted |
| O5 — Telegram pilot | Dedicated bot, paired/allowlisted single user | O4 green; channel threat checks complete | Routing, sender auth, replay, rate, splitting, and secret-redaction checks green |
| O6 — Operations | Pinned install/update/rollback runbook | Pilot accepted | Health probes, incident response, backups/state scope, and disable drills complete |

Each phase gets its own Task Template backlog item. O2 begins with one tool. The
plugin fallback cannot be introduced as an opportunistic second transport in
the same task.

## 7. Implementation backlog to create after O0

- `decide_openclaw_external_agent_integration.md`
- `implement_external_agent_read_gateway_foundation.md` (reuse the shared task
  if Hermes integration already created it)
- `implement_ai_saham_readonly_mcp_adapter.md` (reuse, do not fork a second MCP
  server)
- `configure_openclaw_ai_saham_agent.md`
- one task per external tool registration
- `pilot_openclaw_ai_saham_local.md`
- `pilot_openclaw_ai_saham_telegram.md`
- `document_openclaw_ai_saham_operations.md`

If Hermes and OpenClaw both proceed, they share the application gateway and MCP
adapter but retain separate runtime configuration, security proof, pilots, and
operations tasks.

## 8. Security and failure acceptance

The implementation must prove, with offline fakes and a disposable OpenClaw
profile, that:

- an unpaired/disallowed Telegram sender cannot reach AI Saham;
- an allowed sender routed to another agent cannot see the AI Saham tool set;
- unknown tools, extra arguments, malformed JSON, duplicate keys, and invalid
  subject identifiers fail before execution;
- OpenClaw tool policy hides all unrelated broad tools from the dedicated agent;
- model text, skills, channel messages, retrieved market content, and tool
  results cannot grant permission or enable a second tool;
- no AI Saham tool creates/migrates a database, refreshes data, writes access
  time, or changes observation, ledger, journal, cache, label, or filesystem
  state;
- missing/stale/partial data is explicit and is not replaced by browser/search,
  shell, or another OpenClaw tool;
- duplicate Telegram delivery, model repeated calls, cancellation, timeout, and
  Gateway restart cannot evade the aggregate request budget;
- oversized results fail closed, and raw prompt/tool payloads and secrets do not
  enter ordinary logs;
- disabling the AI Saham gateway, MCP entry, OpenClaw agent binding, or Telegram
  account produces zero calls and leaves CLI/TUI behavior unchanged;
- AI Saham remains operational without Node/OpenClaw, its model, channel state,
  credentials, or network access.

Live Gateway, Telegram, and model checks are explicit opt-in operational smoke
tests. Offline contract and architecture tests remain the correctness gate.

## 9. Observability and rollback

Persist no transcript or model prose in AI Saham initially. Bounded operational
metadata may include:

- request ID and opaque/hashed caller/profile identity;
- pinned OpenClaw and integration versions;
- tool/schema name, status, duration, result reference, as-of, and warnings;
- denial/failure code with raw prompts, arguments, results, and secrets removed.

OpenClaw's own session/channel storage must have a documented path, retention,
backup, deletion, and incident policy. It is external runtime state and cannot
be silently copied into AI Saham learning or audit databases.

Rollback switches independently disable:

1. AI Saham external gateway;
2. OpenClaw MCP server definition or plugin;
3. dedicated-agent channel binding;
4. Telegram account.

The first read-only/no-AI-Saham-transcript release needs no migration on
rollback.

## 10. Non-goals

- No model-authored canonical Action, signal, risk, sizing, evidence authority,
  trade, or alert decision.
- No direct SQLite, CLI, shell, filesystem, browser, generic HTTP, or market
  provider access from OpenClaw to AI Saham.
- No fetch, refresh, paper trade, journal, watchlist, configuration, tuning,
  label, corpus, promotion, or other write tool.
- No generic query, SQL, command, or workflow proxy.
- No TUI selection reconstruction from chat text.
- No cross-agent delegation or OpenClaw automation/cron for AI Saham in v1.
- No AI Saham transcript persistence or channel identity merging.
- No automatic fallback to Hermes, the TUI model, or another provider.
- No publication to ClawHub/npm before the local security and versioning
  contracts are complete.

## 11. Decisions required before implementation

The O0 ADR must resolve:

1. **Extension path:** managed outbound MCP is recommended; use a native
   TypeScript tool plugin only if a pinned compatibility spike proves MCP cannot
   serve the dedicated agent requirement.
2. **Transport:** local stdio MCP is recommended for the first pilot; HTTP MCP
   requires explicit authentication, TLS/network, and replay contracts.
3. **Deployment:** same non-root host/container first; remote deployment adds a
   separate network threat and operations scope.
4. **Model ownership:** OpenClaw owns conversation/model calls for this route;
   AI Saham returns structured deterministic facts and does not run DeepSeek
   again for the same answer.
5. **Exact first tool:** prefer `get_ticker_dashboard` after its ADR-061
   cache-only task is complete.
6. **Identity and aggregate budget:** define how trusted OpenClaw channel event,
   agent, account, chat, and sender identities become a non-forgeable AI Saham
   request/profile envelope.
7. **Session/audit retention:** OpenClaw may retain its own session under an
   explicit policy; AI Saham stays stateless until a persistence ADR.
8. **Version policy:** pin OpenClaw, Node, MCP compatibility, configuration
   schema, and any plugin/skill artifact; upgrades require compatibility tests.

Until these choices are accepted and one Phase 2 tool is complete, the OpenClaw
integration is **not ready for runtime implementation**.

## 12. Roadmap completion criteria

- [ ] O0 integration ADR is accepted and indexed.
- [ ] Activated tasks use the Task Template and exact file boundaries.
- [ ] The application gateway is framework/channel-neutral and imports neither
      OpenClaw nor MCP.
- [ ] The selected adapter is thin and the runtime exposes only a closed,
      independently validated tool subset.
- [ ] Every exposed tool has its own transitive read-only proof.
- [ ] The dedicated agent's effective tool policy denies unrelated broad tools.
- [ ] Telegram routing, sender authorization, replay, rate, token handling, and
      response splitting are tested before a live pilot.
- [ ] Deterministic CLI/TUI behavior and canonical outputs are unchanged with
      OpenClaw enabled, disabled, or unavailable.
- [ ] Offline contracts, architecture, agent, full-suite, and whole-repo Ruff
      gates pass on the implementation commit.
- [ ] Pinned install, health, update, state-retention, incident, and rollback
      runbooks exist.

