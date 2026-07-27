# ADR-050: CLI Verb Contracts (`plan` / `inspect` / `assess`)

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — implementation landed 2026-07-27
**Date:** 2026-07-27
**Depends on:** [ADR-011](ADR-011-offline-capable-cli-as-primary-interface.md),
[ADR-020](ADR-020-cli-adapter-file-naming-convention.md),
[ADR-025](ADR-025-signalengine-architecture.md),
[ADR-032](ADR-032-analyze-swing-verdict-boundary.md),
[ADR-033](ADR-033-workflow-composition-artifact-boundaries.md),
[ADR-049](ADR-049-database-owned-learning-pipeline-clean-break.md)
**Amends:** ADR-020 (examples), ADR-032 (command path), ADR-033 (command table),
ADR-049 (public CLI family tree)
**Current implementation:** Not yet on the public tree. Live `saham --help` still
exposes the pre-rename `analyze …` surface until implementation slices land.
Trust this ADR for target contracts; trust live help for shipped paths.

## Context

ADR-049 and the 2026-07-27 CLI clean break made three families predictable:

| Family | Job |
|--------|-----|
| `screen` | live discovery, no learning write |
| `research` | corpus / ML feeder only |
| `trade` | human paper notebook only |
| `policy` | guarded setup-config lifecycle only |

The remaining overload is **`analyze`**, which currently means three different
jobs depending on the second token:

1. live capability lens (`risk`, `sentiment`, `regime`, `signal accum`)
2. live authoritative `TradeSetup` composition (`swing`)
3. frozen-plan post-open confirmation (`pre-open`)

Agents and operators cannot infer behavior from the verb alone. That violates
the product goal that **the first command token is the behavior contract**.

Rejected path: keep expanding `analyze` (including a peer `analyze accumulation`).
That deepens the overload instead of finishing the family grammar.

## Decision

### 1. Closed top-level verb dictionary

Public CLI top-level verbs have fixed jobs. New commands must fit one row.
If a command does not fit, rename it; do not stretch an existing verb.

| Verb | Meaning (invariant) | Learning DB write? | Final action words? | Typical input |
|------|---------------------|--------------------|---------------------|---------------|
| `fetch` | ingest external data into local store | no (market data only) | no | universe / ticker |
| `screen` | live multi-candidate discovery / ranking | **no** | provisional display only; never final swing authority | universe / list |
| `inspect` | live single-subject capability / evidence lens | **no** | **no** | ticker / as-of |
| `plan` | live authoritative trade plan composition | **no** | **yes** (`TradeSetup.action` and plan fields) | ticker |
| `assess` | confirm a **frozen** plan against later reality | **no** | **yes**, relative to frozen plan only | observation / session ids |
| `research` | learning corpus lifecycle | **yes** | no | scenario |
| `trade` | human paper notebook | paper journal only | paper only; not engine authority | scenario |
| `policy` | guarded YAML proposal / apply lifecycle | policy tables | no live trading | scenario |
| `view` | browse already-stored local facts | no | no | ticker / desk |
| `audit` | offline integrity **or** historical accuracy audit | audit stores may write | no live trade action | scope |
| `indicator` / `strategy` | named artifact authoring collections | n/a | no | name |
| `today` / `tui` / `version` | entry / meta | no | no | — |

Agent-facing one-liners:

```text
screen   = rank many; write nothing learning-related
inspect  = explain one subject/capability; no ENTER/WATCH/AVOID
plan     = produce live TradeSetup + plan fields
assess   = confirm frozen plan after a later fact
research = corpus write/read only
trade    = paper notebook only
policy   = config lifecycle only
audit    = offline integrity / historical accuracy
view     = browse stored facts
```

### 2. Target public tree (post clean break)

```text
saham fetch …
saham screen pre-open|accum …
saham inspect risk|sentiment|regime|signal accum …
saham plan swing TICKER
saham assess pre-open …
saham research pre-open|accum …
saham trade pre-open|accum …
saham policy accum …
saham audit data …
saham audit sentiment
saham view …
saham indicator …
saham strategy …
saham today
saham tui
saham version
```

### 3. Rename / retire map

| Current public path | Target | Notes |
|---------------------|--------|-------|
| `analyze swing` | **`plan swing`** | Sole live `TradeSetup` authority for swing horizon |
| `analyze pre-open` | **`assess pre-open`** | Frozen observation + track; stdout only |
| `analyze risk` | **`inspect risk`** | Live capability lens |
| `analyze sentiment` | **`inspect sentiment`** | Live capability lens |
| `analyze regime` | **`inspect regime`** | Live capability lens |
| `analyze signal inspect` | **`inspect signal accum`** | Accumulation-flow SignalEngine inspect only (not pre-open/swing) |
| `analyze chart …` / `inspect chart …` | **retired** | Terminal charts removed; TUI owns charts later; values via `indicator` |
| `analyze audit` | **`audit sentiment`** | Historical sentiment accuracy (see §5) |
| `analyze swing-compare` | **retired** | Removed; no alias |
| `analyze compare` | **retired** | Multi-ticker risk compare removed; no alias |
| entire `analyze` top-level group | **retired** | No alias after clean break |

### 4. Why the second token is `swing`, not `accum`

Operational path is often:

```text
screen accum  →  plan swing  →  (optional) trade accum log / research accum …
```

That does **not** make the plan command “about accum.”

Vocabulary (binding):

| Token | Kind | Meaning |
|-------|------|---------|
| `accum` | evidence / discovery **method** + corpus scenario | foreign/institutional flow screening, observation purpose `ACCUMULATION_DISCOVERY` |
| `swing` | trade **horizon** + plan artifact | multi-day setup; signal purpose `SWING_TRADE_SETUP`; canonical artifact `TradeSetup` |
| `pre-open` | session **horizon** / auction scenario | NCP plan + post-open assess |

`plan swing` is correct because:

1. ADR-025 separates `evaluate_accumulation_discovery()` from
   `evaluate_swing_trade_setup()`.
2. ADR-032 / ADR-033 make `TradeSetup` the swing final-action artifact.
3. Accumulation evidence is an **input** to swing planning, not the plan’s
   identity. Renaming to `plan accum` would re-teach “accumulation authorizes
   the trade,” which this grammar exists to prevent.
4. Paper/corpus families correctly keep `accum` where the scenario is discovery
   or accumulation-learning (`screen accum`, `research accum`, `trade accum`,
   `policy accum`). Asymmetry with `plan swing` is intentional.

Deferred product (not this ADR): a live accumulation **evidence** drilldown
belongs under `inspect …` (e.g. future `inspect accum` / `inspect flow`), never
under `plan`.

### 5. Sentiment historical audit placement

Current: `saham analyze audit` runs `AuditSentimentUseCase` — retrospective
accuracy of logged sentiment vs price moves at 1/3/5 sessions, and **writes**
sentiment audit rows.

| Candidate home | Fit? | Why |
|----------------|------|-----|
| `inspect …` | **No** | `inspect` is live lens, no final action, and must not become a batch accuracy writer |
| `research …` | **No** | Not the learning-observation corpus (`learning_*` tables / ADR-049 purposes) |
| top-level `audit` | **Yes** | Offline, retrospective, accuracy/integrity style; family already owns non-live audit work |

**Decision:** `saham audit sentiment`

Keep data-quality commands under the existing `audit data …` sub-tree:

```text
saham audit data …        # DQ / source / contract / repair (existing)
saham audit sentiment     # historical sentiment prediction accuracy
```

Help text must state that `audit sentiment` is **not** a live trade input and
does not affect `plan swing` authority.

### 6. Clean break and ADR-020 file ownership

- **No aliases** for retired `analyze …`, `analyze swing-compare`, or
  `analyze compare` routes.
- When a public command moves, **rename adapter files in the same change** so
  filename ownership matches the tree (ADR-020):

| Target command | Adapter ownership examples |
|----------------|----------------------------|
| `plan swing` | `plan_commands.py`, `plan_swing_commands.py`, `plan_swing_display.py`, `plan_swing_*` |
| `assess pre-open` | `assess_commands.py`, `assess_pre_open_commands.py`, `assess_pre_open_display.py` |
| `inspect risk` | `inspect_commands.py`, `inspect_risk_commands.py`, … |
| `inspect sentiment` | `inspect_sentiment_commands.py`, … |
| `inspect regime` | `inspect_regime_commands.py`, … |
| `inspect signal accum` | `inspect_signal_commands.py` (group) + `inspect_signal_accum_commands.py` |
| ~~`inspect chart`~~ | **retired** (no adapter) |
| `audit sentiment` | `audit_sentiment_commands.py` (alongside existing `audit_commands.py` / data nodes) |

Retired modules for removed compare surfaces are deleted, not aliased.

Application/domain module names (e.g. `swing_analysis_workflow_use_case.py`)
are **not** required to rename in the first CLI slice unless a focused
application cleanup is in scope. Public CLI path and `src/adapters/cli/`
ownership are mandatory.

### 7. Authority boundaries (unchanged engine semantics)

This ADR is a **CLI grammar / adapter ownership** decision. It does not change:

- SignalEngine / RiskEngine / MCE scoring
- `AssessTradeSetupUseCase` composition
- evidence authority or promotion rules
- learning table contracts

Binding product rules after rename:

```text
plan swing:
  canonical SignalAssessment + RiskAssessment
    → AssessTradeSetupUseCase
    → TradeSetup.action   # sole live swing action authority

inspect *:
  may display scores, gates, charts, provenance
  must not emit final TradeSetup action as command authority

assess pre-open:
  frozen learning observation + linked track snapshot
    → post-open gates
    → ENTER/WAIT/SKIP_* relative to that plan only
  not a learning label write; paper log remains trade pre-open log

screen / research / trade / policy:
  keep ADR-049 family jobs
```

Semantic classification for implementation: **`NON_SEMANTIC`** when fixture
parity proves `TradeSetup`, signal, risk, and plan fields unchanged aside from
command path / help / adapter filenames. Escalate if any calculation, evidence
authority, or JSON artifact meaning changes.

### 8. Rejected alternatives

| Option | Why rejected |
|--------|--------------|
| Keep overloaded `analyze` | Verb does not predict behavior |
| `decide swing` | Sounds like bot execution; product is analysis software |
| `evaluate swing` | Collides with `research … evaluate` cohort study |
| `plan accum` | Collapses method vs horizon; teaches wrong authority |
| Alias dual-path (`analyze` + `plan`) | Violates clean-break policy used for trade/research/policy |
| Put sentiment accuracy under `inspect` | Inspect is live non-action; accuracy job writes audit rows |
| Keep `swing-compare` / `analyze compare` | Explicitly retired as low-value surface area |

## Implementation slices (not done by accepting this ADR)

1. **Docs + tests contract:** this ADR, `ARCHITECTURE_DECISIONS.md`,
   `CLI_REFERENCE.md` family table, hierarchy negative tests for retired routes.
2. **`plan swing`:** mount command, rename `analyze_swing_*` adapters, parity
   fixtures for TradeSetup outputs, delete `analyze swing` / swing-compare.
3. **`assess pre-open`:** rename from `analyze pre-open`, keep database-id
   contract, delete old route.
4. **`inspect *` lenses:** risk, sentiment, regime, signal accum; chart retired;
   delete `analyze` group; move sentiment historical audit to `audit sentiment`.
5. **Operator docs / runbooks / examples:** scrub old paths; no dual docs.
6. Full offline suite + `git diff --check`; commit only task-owned files.

## Consequences

- First CLI token is a stable behavior contract for humans and agents.
- `plan` is the only live swing action surface; `inspect` cannot quietly grow
  ENTER/WATCH/AVOID authority.
- `assess` is reserved for frozen-plan confirmation (pre-open), not live
  ticker recomputation.
- `accum` vs `swing` vocabulary stays explicit across families.
- Adapter filenames track the public tree (ADR-020) on each move.
- Temporary agent/docs drift is expected until slices land; live help remains
  authoritative for what is shipped today.

## Amendment notes for older ADRs

When implementation lands, amend in the same PR (or immediately after):

- **ADR-032:** command path `analyze swing` → `plan swing` (verdict rule unchanged).
- **ADR-033:** command/artifact table rows for plan / assess / inspect / retired compare.
- **ADR-049:** public CLI section adds `plan` / `inspect` / `assess`; retires
  `analyze` as a family bucket.
- **ADR-020:** examples refreshed to `plan_*`, `inspect_*`, `assess_*`.

## Amendment (CLI surface cleanup)

- Help panel for `view`/`audit` is **Browse** (not "Inspect") to avoid clash with verb `inspect`.
- **`inspect chart` retired** (hard break). Numeric path: `indicator compute|snapshot`. Charts later in TUI.
- **`view market-context` retired** (hard break). Sole MCE/regime CLI: **`inspect regime`**.
- **Broker-top jobs:** `fetch broker-top-foreign` writes cache; `view broker top-foreign` browses cache.
- TUI/Web mapping (stable product surface):

| CLI | TUI/Web resource |
|-----|------------------|
| `inspect regime` | Regime / MCE panel |
| `inspect signal accum` | Signal explain drawer |
| `inspect risk` | Risk explain drawer |
| `plan swing` | Decision page |
| `view ticker.*` / `view broker.*` | Browse tables |
| `fetch broker-top-foreign` | Data job |
| `view broker top-foreign` | Ranking table from cache |
| ~~`inspect chart`~~ | TUI chart component later |
