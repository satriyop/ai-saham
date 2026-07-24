# ADR-044: View Subject Taxonomy — Ticker Axis vs Desk Axis

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted  
**Date:** 2026-07-24  
**Amends:** [ADR-018](ADR-018-cli-command-depth-saham-view-broker-exception.md)  
**Related:** [ADR-011](ADR-011-offline-capable-cli-as-primary-interface.md), [ADR-020](ADR-020-cli-adapter-file-naming-convention.md), [ADR-045](ADR-045-view-browse-parity-cli-tui-json-table.md)  
**Current implementation:** Implemented — live `saham view --help` is authoritative for exact flags; this ADR owns subject/verb meaning.

### Context

`saham view broker` originally mixed two products under one group:

1. **Stock-centric** deep-dives (`flow` / `top` / `history` / `distribution` with a **ticker** argument).
2. **Universe / meta** tools (`top-foreign`, `status`, `mappings`).

That overloading made command language ambiguous (`top` vs `top-foreign`), encouraged agent invention of dual-mode arguments, and blocked a clean desk-centric surface (what is broker `AK` doing across stocks?).

A clean-break redesign split subjects. This ADR records the **product taxonomy** only. Adapter parity, JSON envelopes, and TUI reuse are **ADR-045**.

### Decision

#### 1. Two deep-dive subjects under `view`

| Subject | Canonical path | Argument |
|---------|----------------|----------|
| **Ticker (stock)** | `saham view ticker <verb> <TICKER>` | IDX stock symbol (e.g. `BBCA`) |
| **Desk (broker code)** | `saham view broker <verb> <CODE>` | Tracked desk code (e.g. `AK`) |

Dashboard shorthand (ticker only):

```text
saham view <TICKER>  ≡  saham view ticker show <TICKER>
```

No dual-mode resolution of a bare token as “ticker or desk.” No aliases from the retired stock-under-`view broker` paths.

#### 2. Verb glossary (non-interchangeable)

| Verb | Axis | Meaning | Primary data |
|------|------|---------|--------------|
| `show` | ticker | Stock cached dashboard | multi-cache dashboard |
| `show` | desk | Desk overview for one code | `broker_daily_flow` |
| `top-brokers` | ticker | Top **desks in** this stock | `broker_summaries` tops; else rank `broker_daily_flow` with tracked scope note |
| `top-stocks` | desk | Top **stocks for** this desk | `broker_daily_flow` |
| `flow` | ticker | Multi-day **foreign** summary table for the stock | `broker_summaries` |
| `flow` | desk | Desk **net by day** across cached tickers | `broker_daily_flow` |
| `foreign-history` | ticker | Daily **foreign net** series only | `foreign_flow_points` |
| `history` | desk | Desk time series (optional pin `--ticker`) | `broker_daily_flow` |
| `distribution` | ticker only | Cross-broker counterparty matrix for the stock | `broker_distribution_cache` |
| `top-foreign` | broker meta (no CODE) | Universe ranking of stocks by foreign-desk scan | `foreign_flow_snapshots` |
| `status` / `mappings` / `list` | broker meta | Provider status, CSV mappings, tracked codes | config / runtime |

Hard rules:

- **`top-brokers` ≠ `top-stocks` ≠ `top-foreign`.**
- **`foreign-history` ≠ desk `history`.** Foreign-history never presents local desk rows as its series.
- Desk rankings and desk series are **tracked-broker scope only** and MUST surface that in user-facing copy / scope metadata.

#### 3. Clean break (retired paths)

These forms MUST NOT exist and MUST NOT be reintroduced as aliases:

```text
saham view broker flow <TICKER>
saham view broker top <TICKER>
saham view broker history <TICKER>
saham view broker distribution <TICKER>
```

Replacements:

| Retired | Replacement |
|---------|-------------|
| `view broker top <TICKER>` | `view ticker top-brokers <TICKER>` |
| `view broker flow <TICKER>` | `view ticker flow <TICKER>` |
| `view broker history <TICKER>` | `view ticker foreign-history <TICKER>` |
| `view broker distribution <TICKER>` | `view ticker distribution <TICKER>` |

#### 4. Command depth (amends ADR-018)

- Default CLI depth remains max two levels (`saham <group> <command>`).
- **Approved 3-level exceptions under `view`:** `view ticker <verb> …` and `view broker <verb> …`.
- Further `view` sub-groups require a new ADR.
- ADR-018’s obsolete ticker-centric command list is retired; **this ADR owns the glossary.**

#### 5. Agent / docs one-liner

```text
Stock deep-dives:  saham view ticker <verb> <TICKER>
Desk deep-dives:   saham view broker <verb> <CODE>
Stock overview:    saham view <TICKER>
Universe foreign:  saham view broker top-foreign
```

### Rationale

- Separates **stock analysis** (primary product) from **desk surveillance** (secondary axis) without dual-mode parsers.
- Fixed command tokens are discoverable via `--help` and safer for agents than dynamic `view BBCA top`.
- Explicit verb names prevent conflating market foreign series, tracked desk books, and universe scans.
- Clean break matches solo-maintainer preference and avoids permanent alias debt.

### Implications

* New stock broker deep-dives land under `view ticker`, not `view broker`.
* New desk features land under `view broker` with a **CODE** argument (except meta verbs).
* File names should follow ADR-020 with `view_ticker_*` / `view_broker_desk_*` / meta prefixes (see ADR-045).
* CLI/TUI/JSON mechanics for these verbs: **ADR-045**.
* Live help and command-contract tests enforce the tree; this ADR enforces **meaning**.

### Explicit non-goals

* JSON envelope schema and `--format` rules (ADR-045).
* TUI screen layout and widgets (ADR-045 + roadmap).
* Fetch command renames (`fetch broker-top-foreign` stays).
* Desk `distribution` product.
* Dynamic subject-as-command sugar (`view BBCA top-brokers` as contract).
