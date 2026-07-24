# ADR-045: View Browse Parity — CLI, TUI, and Table/JSON Output

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted  
**Date:** 2026-07-24  
**Depends on:** [ADR-044](ADR-044-view-subject-taxonomy-ticker-vs-desk.md)  
**Related:** [ADR-003](ADR-003-hexagonal-ports-adapters-architecture.md), [ADR-011](ADR-011-offline-capable-cli-as-primary-interface.md), [ADR-020](ADR-020-cli-adapter-file-naming-convention.md), [ADR-040](ADR-040-manual-dependency-injection-and-composition-roots.md), [ADR-046](ADR-046-cli-response-envelope.md)  
**Current implementation:** CLI table/json and application use cases for stock/desk browse are implemented; TUI screens may lag UI but must not invent parallel policy when added.

### Context

ADR-044 defines **what** view commands mean (ticker vs desk, verb glossary).  
Without a separate adapter contract:

* CLI and future TUI can drift on ranking fallbacks, scope labels, and empty-cache behavior.
* Agents and scripts need a stable **machine-readable** output shape.
* File and layer ownership for `view_*` modules needs an explicit rule for implementors.

This ADR defines **how** browse features are implemented and exported across adapters.

### Decision

#### 1. Single source of browse policy

For every ADR-044 deep-dive verb:

* **Application use cases** (or shared pure helpers they own) decide:
  - cache selection and empty/missing outcomes
  - stock top-brokers summary vs tracked `broker_daily_flow` fallback
  - desk ranking / aggregation over `broker_daily_flow`
  - foreign vs local classification from configured `foreign_broker_codes` when type is not stored on the row
* **Adapters** (CLI, TUI) only:
  - parse input / UI events
  - compose dependencies (manual DI / composition roots)
  - call use cases
  - render table UI **or** serialize the shared envelope to JSON
  - map errors and exit codes

Adapters MUST NOT reimplement browse ranking, fallback, or scope policy in screens or Typer bodies.

#### 2. CLI ↔ TUI parity definition

Parity means: for the same subject, verb, and resolved window/as-of inputs, CLI and TUI produce the **same semantic result** (data, status, source/scope notes).  

Presentation may differ (Rich tables vs TUI widgets).  
TUI MUST NOT import CLI display modules (`view_*_display.py`).  
TUI SHOULD call the same use cases via composition roots (ADR-040).

TUI may ship screens later than CLI; when a screen is added for an existing verb, it must reuse the application path rather than a second policy implementation.

#### 3. Table and JSON output (CLI browse verbs)

Every `view ticker` and `view broker` browse/meta verb that returns user-visible browse data MUST support:

```text
--format table   # default
--format json
```

Rules:

* Invalid `--format` → exit code **2** with a clear error.
* Missing/empty cache → non-success exit (typically **1**) and a human message in table mode; JSON SHOULD use envelope `status` of `missing` or `empty` when structured (stock axis already uses shared helpers; desk axis follows the same envelope on success paths).
* Default format remains **table** for interactive use.

#### 4. Shared JSON envelope (view specialization of ADR-046)

Machine output uses the CLI-wide envelope in [ADR-046](ADR-046-cli-response-envelope.md).
View stock/desk specialization:

```text
subject:   { kind: "ticker" | "desk", id: string }
verb:      string          # e.g. top-brokers, top-stocks, show, flow
as_of:     date | null
window:    { days?, from_date?, to_date? } | null
source:    string | null   # e.g. broker_summaries, broker_daily_flow, foreign_flow_points
scope:     string | null   # e.g. full, tracked_brokers, universe, meta
scope_note: string | null  # human-readable scope caveat when needed
status:    "ok" | "empty" | "missing"
fetch_hint: string | null
data:      object | array  # verb-specific payload
```

* `subject.kind` MUST be `ticker` for stock deep-dives and `desk` for desk/meta broker verbs (meta may use synthetic ids such as `status`, `universe`, `*`).
* Numeric money fields in `data` SHOULD be strings when sourced from `Decimal` to avoid float drift.
* Envelope builders live in **application** (or a thin application DTO module); CLI only dumps JSON.

Versioning: additive fields in `data` are allowed without a new ADR; **removing/renaming envelope top-level keys** is owned by ADR-046 (amend that ADR). View-only `subject.kind` / verb glossary changes stay here or in ADR-044.

#### 5. Adapter file ownership (with ADR-020)

New browse modules follow ADR-020 command-tree ownership:

| Surface | File prefix examples |
|---------|----------------------|
| Stock deep-dives | `view_ticker_*_commands.py`, `view_ticker_*_display.py` |
| Desk deep-dives | `view_broker_desk_*` |
| Desk universe scan | `view_broker_top_foreign_*` |
| Broker meta | `view_broker_status_*`, `view_broker_list_*`, `view_broker_mappings_*` |
| Shared CLI format helpers | thin `view_*_contract_cli.py` adapters only |

Application use cases should be named for the subject/verb (e.g. `view_ticker_top_brokers_use_case.py`, `view_broker_desk_top_stocks_use_case.py`) so agents find them by search.

#### 6. Checklist for new browse features

Before merging a new ADR-044 verb or material change:

1. Application use case (or documented reuse of an existing one).
2. CLI path registered under the correct axis.
3. `--format table` and `--format json` both work.
4. Command-contract / CLI tests cover the path.
5. If TUI exposes the verb: same use case via composition; no parallel policy.

### Rationale

* Hexagonal layering already forbids policy in adapters; browse features are a common place this leaks.
* A shared envelope gives scripts, agents, and future TUI export one contract.
* Splitting this from ADR-044 keeps product language stable while adapter mechanics evolve.

### Implications

* CLI display code stays presentation-only.
* TUI implementors treat application use cases as the API, not CLI modules.
* Expanding JSON `data` shapes is free within a verb; envelope renames are not.
* Composition roots should expose factories for stock/desk view use cases when TUI needs them.

### Explicit non-goals

* ADR-044 verb meanings and clean-break command list (owned there).
* Visual design of TUI tabs or Rich styling.
* Fetch pipeline redesign.
* Guaranteeing every TUI panel exists on day one.

### Agent one-liner

```text
View browse policy lives in application use cases.
CLI and TUI only compose and render.
CLI browse verbs support --format table|json with the shared subject/verb envelope
(view: ADR-045; CLI-wide envelope authority: ADR-046).
Command meanings: ADR-044.
```
