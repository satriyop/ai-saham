# ADR-018: CLI Command Depth — `view` Sub-Group Exceptions

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted (amended)  
**Date:** Not recorded (legacy decision); amended 2026-07-24  
**Amended by:** [ADR-044](ADR-044-view-subject-taxonomy-ticker-vs-desk.md)  
**Related:** [ADR-045](ADR-045-view-browse-parity-cli-tui-json-table.md)  
**Current implementation:** Implemented — `view ticker …` and `view broker …` are the approved three-level trees under `view`; live help is authoritative for verbs.

### Decision

The CLI follows a "max 2 levels" depth rule (`saham <group> <command>`).

**Approved exceptions at 3 levels under `view`:**

```text
saham view ticker <verb> …
saham view broker <verb> …
```

These sub-groups exist because browse modes are numerous and must stay grouped by **subject** (stock vs desk/meta), not flattened into a polluted `view` top-level namespace.

**Subject meanings, verb glossary, and clean-break command list:** see **ADR-044**.  
Do not use this ADR as a command catalog.

### Legacy note (superseded command list)

Earlier text listed stock-centric paths such as `view broker flow|top|history|distribution <TICKER>`.  
Those paths are **retired**. Stock deep-dives live under `view ticker …`. Desk deep-dives use `view broker <verb> <CODE>` (plus meta verbs without a stock ticker).

### Rationale

Broker/stock browse data has many display modes. Flattening to `saham view flow`, `saham view top`, etc. would pollute `view` and lose subject grouping. A single `broker` bag that also took tickers was ambiguous; ADR-044 splits subjects while keeping three-level depth for both axes.

### Implications

* No additional `view` sub-groups beyond `ticker` and `broker` without a new ADR.
* New stock browse commands are added under `view ticker`, not at bare `view` level (except the dashboard shorthand `view <TICKER>` → `ticker show`).
* New desk browse commands are added under `view broker`.
* All other `saham` command groups remain at max 2 levels unless a separate ADR grants an exception.
* Adapter/JSON/TUI parity for these commands: **ADR-045**.
