# ADR-046: Shared CLI Response Envelope

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted  
**Date:** 2026-07-24  
**Depends on:** [ADR-003](ADR-003-hexagonal-ports-adapters-architecture.md), [ADR-011](ADR-011-offline-capable-cli-as-primary-interface.md), [ADR-040](ADR-040-manual-dependency-injection-and-composition-roots.md)  
**Related:** [ADR-044](ADR-044-view-subject-taxonomy-ticker-vs-desk.md), [ADR-045](ADR-045-view-browse-parity-cli-tui-json-table.md), [ADR-008](ADR-008-decoupled-fetch-vs-analyze-data.md), [ADR-033](ADR-033-workflow-composition-artifact-boundaries.md)  
**Current implementation:** Envelope is live for `view` stock/desk browse and most `screen` discovery JSON paths. Other CLI families adopt on touch. Family builders may live in separate application DTO modules until a shared module is extracted.

### Context

CLI machine output grew family by family. `view` and `screen` already share a
practical envelope vocabulary (`subject`, `verb`, `status`, `fetch_hint`,
`data`, …), but the rule lived only in ADR-045 (view browse) and in code
comments. That left three risks:

1. **Policy drift** — `analyze`, `fetch`, `trade`, and future surfaces invent
   parallel JSON shapes or dual success/error layouts.
2. **Adapter leakage** — Typer bodies assemble ad-hoc metadata instead of
   calling application envelope builders and pure renderers.
3. **Concept confusion** — response envelopes look similar to observation
   provenance or candidate-observation payloads but serve a different job.

This ADR records the **CLI-wide response envelope** as binding policy.
Family-specific product language remains in family ADRs (e.g. ADR-044/045 for
view). Implementation may still land family-by-family.

### Decision

#### 1. One envelope concept for machine-readable CLI output

When a command emits structured machine output (today: `--format json` or
equivalent JSON paths), successful and structured empty/missing outcomes use
this top-level shape:

```text
subject:    { kind: string, id: string }
verb:       string
as_of:      date-or-datetime string | null
window:     { days?, from_date?, to_date? } | null
source:     string | null
scope:      string | null
scope_note: string | null
status:     "ok" | "empty" | "missing" | "error"
fetch_hint: string | null
data:       object | array | null
```

Rules:

* Top-level keys above are the **shared contract**. Family builders MUST emit
  these keys; they MUST NOT invent alternate top-level metadata names for the
  same concepts.
* `subject.kind` is family-scoped vocabulary (examples: `ticker`, `desk`,
  `screen`, `watchlist`, `universe`). New kinds are additive when a family
  adopts the envelope; document them in the family ADR or module docstring.
* `verb` names the command intent within the family (e.g. `show`, `top-brokers`,
  `watchlist`, `compare`), not a free-form prose status.
* `status` is coarse outcome for adapters and scripts. Domain/scoring verdicts
  belong inside `data`, not as substitute top-level keys.
* `fetch_hint` is a suggested next CLI action when cache/input is missing or
  stale enough that the user should fetch; it is not a fetch policy engine.
* Numeric money / high-precision fields inside `data` SHOULD serialize
  `Decimal` as strings to avoid float drift.
* Envelope builders live in **application** DTO modules (or a future shared
  application module). Adapters only compose inputs, call use cases, dump
  JSON, and map process exit codes.

Versioning:

* **Additive** fields inside `data` do not require a new ADR.
* **Removing or renaming top-level envelope keys** requires amending this ADR.
* Optional additive top-level keys (e.g. `related_actions`) require an
  amendment when they become part of the shared contract; family-only
  experimental fields must stay inside `data` until then.

#### 2. Envelope is not observation provenance

The response envelope is a **presentation / API response structure** for CLI
(and future TUI/API adapters that reuse the same builders).

It is **not**:

* a candidate observation row
* signal-evidence or label provenance
* a substitute for material config identity, schema versions, or PIT audit
* authority for scoring, risk, or trade decisions

Observation and evidence contracts remain under their own ADRs and program
docs. Do not overload envelope fields to carry silent decision authority.

#### 3. Adopt-on-touch migration (policy global, code family-by-family)

| Family | Envelope policy | Implementation note |
|--------|-----------------|---------------------|
| `view` (ticker / desk browse) | Required | ADR-045; builders in view contract DTOs |
| `screen` (discovery) | Required for machine JSON paths that return browse/list/compare results | Partial: watchlist/compare/accum JSON enveloped; specialized subcommands (e.g. pre-open) may remain specialized until touched |
| `analyze` | Required when the path is next materially changed for JSON/export | Adopt clean-break on touch |
| `fetch` | Required when the path is next materially changed for structured result output | Adopt clean-break on touch; keep fetch/analyze separation (ADR-008) |
| `trade` and other surfaces | Same adopt-on-touch rule | No big-bang rewrite |

When a family adopts:

1. Use application builders (new shared module or family DTO module).
2. **Clean break** for that path: no dual legacy JSON layout, no silent
   translation of old top-level keys, no parallel success shapes.
3. Keep adapters thin: no cache freshness, ranking, or business status policy
   in Typer bodies.
4. Prefer the same use-case path for table and JSON (or TUI) consumers.

Big-bang rewrites of untouched families are **not** required by this ADR.

#### 4. Adapter obligations

Adapters (CLI, future TUI/API):

* parse input and wire composition roots
* call application use cases
* render table/UI **or** serialize the envelope
* map errors and exit codes

Adapters MUST NOT:

* invent a second metadata language for the same command
* recompute scope/status/fetch policy that belongs in application
* treat envelope `status` as a trade or signal verdict

#### 5. Relationship to ADR-045

ADR-045 remains the **view browse parity** decision (CLI ↔ TUI, table/json,
use-case ownership for ADR-044 verbs).

This ADR **generalizes** the envelope concept beyond view. View-specific
`subject.kind` values (`ticker` | `desk`) and browse checklist items stay in
ADR-045. Where ADR-045 and this ADR both speak about envelope top-level keys,
this ADR is the CLI-wide authority; ADR-045 specializes view adoption.

### Rationale

* Scripts, agents, and future TUI export need one metadata language.
* Recording the rule only under view invited other families to diverge.
* Adopt-on-touch avoids a risky rewrite while still forbidding dual layouts
  when a path is touched.
* Keeping provenance separate protects deterministic auditability.

### Implications

* New or materially changed JSON-emitting CLI paths must use the envelope.
* Family DTO modules may duplicate a thin builder until a shared application
  helper is extracted; vocabulary must stay aligned with this ADR.
* Exit codes remain process concerns; envelope `status` remains payload
  concerns. Table mode may still print human messages without dumping JSON.
* Pre-existing non-enveloped JSON outside adopted families is technical debt
  to clear on touch, not silent permanent exceptions.

### Explicit non-goals

* Redesigning observation, label, or evidence schemas.
* Forcing every human table panel to dump JSON metadata lines.
* Mandating TUI UI chrome or Rich styling.
* Unifying all family `data` payloads into one schema.
* Changing fetch pipelines or cache policy (owned by application use cases
  and ADR-008).

### Agent one-liner

```text
CLI machine output uses one response envelope
(subject, verb, as_of, window, source, scope, scope_note, status, fetch_hint, data).
Builders live in application; adapters only render.
Envelope ≠ observation provenance.
View/screen adopted; other families adopt clean-break on touch (ADR-046).
View product/parity details: ADR-044/045.
```
