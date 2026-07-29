# ADR-054: Screen judges candidates; Plan designs trade structure

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)

**Status:** Accepted — product/CLI contract; implementation phased (see §7)
**Date:** 2026-07-28
**Depends on:** [ADR-011](ADR-011-offline-capable-cli-as-primary-interface.md),
[ADR-026](ADR-026-risk-plus-signal-pipeline-composition.md),
[ADR-031](ADR-031-swing-setup-evaluation-boundary.md),
[ADR-032](ADR-032-analyze-swing-verdict-boundary.md),
[ADR-033](ADR-033-workflow-composition-artifact-boundaries.md),
[ADR-047](ADR-047-scenario-adoption-seam-for-signal-risk-mce.md),
[ADR-050](ADR-050-cli-verb-contracts.md)
**Amends:** ADR-032 (command role of `plan swing`), ADR-033 (artifact ownership
table), ADR-050 (§1 verb table and §4 operational path for `plan` / `screen`)
**Does not change:** SignalEngine / RiskEngine / MCE scoring formulas; evidence
authority promotion; learning table contracts (ADR-049)

## Context

Operators currently experience two overlapping “analysis” surfaces for swing:

```text
saham screen accum --universe …   # discovery board
saham screen accum TICKER         # already deepens, but not full plan depth
saham plan swing TICKER           # full Signal+Risk→TradeSetup + evidence + sizing
```

That makes `plan` read as **another analysis focus**, not a distinct product job.
The desired workflow is:

```text
1. screen universe  →  choose candidates
2. screen ticker    →  deep-dive / judge the candidate
3. plan             →  investigate trade *structure* for the chosen candidate
4. trade            →  paper journal / outcome
```

Product language frozen here:

> **Screen finds and judges candidates.**  
> **Plan designs the trade structure of a chosen candidate.**

“Structure” means horizon, invalidation (stop), profit-taking, R:R path, and
related geometry — not a second universe screener and not a second independent
ENTER/WATCH/AVOID story.

## Decision

### 1. Binding slogan and verb jobs

| Verb | Product job (invariant after this ADR) |
|------|----------------------------------------|
| `screen` | Live discovery **and** single-subject **judgment** of candidates (evidence + engines → provisional/final display of action when composed) |
| `plan` | Live **trade-structure investigation** for an already-chosen candidate (horizon, stops, targets, sizing-as-consequence-of-structure) |
| `inspect` | Single capability/evidence lens; **no** ENTER/WATCH/AVOID (unchanged ADR-050) |
| `assess` | Confirm a **frozen** plan against later reality (unchanged) |
| `trade` | Human paper notebook only (unchanged) |

Agent one-liners (replace the ADR-050 `plan` / `screen` lines):

```text
screen  = rank many OR deep-judge one candidate; no learning write
plan    = design trade structure for a chosen candidate (horizon / SL / TP / geometry)
inspect = explain one capability; no action words
assess  = confirm frozen plan after a later fact
trade   = paper notebook only
```

### 2. Operational path (binding)

```text
screen accum --universe …     →  shortlist
screen accum TICKER           →  deep judgment (analysis desk)
plan swing TICKER …           →  structure design for that choice
trade accum log …             →  paper journal (optional)
research accum …              →  corpus only (optional)
```

**Forbidden product reading:** `plan swing` as “I need a second analysis because
screen was shallow.” After migration, single-ticker `screen accum` **is** the
analysis desk.

### 3. `screen` ownership (judgment)

`saham screen accum` owns:

| Mode | Behavior |
|------|----------|
| Universe / list | Cheap discovery: rank, filters, multi-window; pattern match board; signal/risk/phase when composed |
| **Explicit ticker(s)** | **Deep judgment** — full analysis stack that today lives largely under `plan swing` *as analysis* |

Screen **must** own (single-ticker depth, phased):

- Accum score + breakdown  
- SignalEngine assessment (discovery and/or swing purpose as already wired)  
- RiskEngine gates  
- Setup phase + named setup MATCH/PARTIAL/NO_MATCH + primary family + readiness  
- Decision why / constraint reasons  
- Optional evidence: flow detail, strategy/backtest panel, sentiment, market context  
- Data refresh for the requested ticker when needed for judgment  
- Composed `TradeSetup.action` when signal + risk are both present (same composer as today; ADR-026)

Screen **must not** own as its primary job:

- Capital-led lot sizing as the headline product  
- Horizon optimization / multi-horizon structure comparison as the headline product  
- “I am planning to trade this size” commitment language (that is `plan` / `trade`)

Universe mode stays performance-bounded: expensive panels stay **single-ticker
or explicit opt-in**, never silently on for full LQ45.

### 4. `plan` ownership (structure investigation)

`saham plan swing` owns **structure design** for a **chosen** candidate:

| Structure question | Examples (non-exhaustive) |
|--------------------|---------------------------|
| Horizon | Which swing horizon fits this family/phase? Compare allowed horizons |
| Invalidation | Stop: ATR, % from entry, structure break, setup-phase failure |
| Profit taking | Single TP, partials, regime-adaptive targets (`swing_targets.yaml`) |
| Geometry | R:R path; whether structure matches validated backtest params |
| Entry framing | How entry relates to phase/setup (not re-running screen ranking) |
| Risk budget | Capital / % risk **after** structure is fixed (sizing is consequence) |

Canonical artifact evolution:

| Phase | Plan’s primary artifact |
|-------|-------------------------|
| **Current (pre-migration)** | Still emits full analysis + `TradeSetup` (ADR-032/033 legacy) |
| **Target** | `SwingTradeStructure` (or equivalently named structure DTO) **plus** a **referenced** screen judgment / `TradeSetup.action` — plan does not invent a competing action story |

Until `SwingTradeStructure` exists in code, plan may keep composing `TradeSetup`
for action display **only if** it reuses the same judgment path as single-ticker
screen (shared application composer). It must not score with a second hidden
policy.

Plan **must not**:

- Run multi-candidate discovery  
- Re-rank universes  
- Become the only place operators can see pattern match / signal / risk  
- Silently disagree with screen’s judgment for the same inputs without an explicit
  documented reason (e.g. different as-of or missing data)

### 5. Authority and non-contradiction rule

```text
Judgment (action words):
  SignalAssessment + RiskAssessment
    → AssessTradeSetupUseCase
    → TradeSetup.action

  Owned for operators by: screen accum (single-ticker deep mode is canonical
  analysis surface after migration).

Structure (horizon / SL / TP / lots):
  Chosen candidate identity + judgment snapshot
    → plan swing structure services
    → structure fields (targets, stops, horizon, sizing)

  Must not override TradeSetup.action via setup gates, sentiment, or backtest
  panels (ADR-031 / ADR-032 still hold for evidence modules).
```

Setup evaluation remains **pattern fit** (MATCH/PARTIAL/NO_MATCH) only (ADR-031).
It is shown on screen; plan may **consume** primary family / match to select
structure templates, not to rename the action.

### 6. Vocabulary (extends ADR-050 §4)

| Token | Kind | Meaning |
|-------|------|---------|
| `accum` | discovery method / corpus scenario | foreign-flow screening; purpose `ACCUMULATION_DISCOVERY` |
| `swing` | trade horizon + structure/plan family | multi-day; structure + `TradeSetup` for swing |
| `screen` | verb | judge candidates (many or one) |
| `plan` | verb | design structure for a chosen candidate |

`plan swing` remains correctly named: structure is for the **swing horizon**,
using accumulation evidence as input — not “plan accum.”

### 7. Migration plan (phased; no big-bang)

Implementation status at ADR accept: **contract only**. Code still has plan as
analysis+structure until slices land.

| Slice | Goal | Exit criteria |
|-------|------|----------------|
| **S0** | This ADR + index links | Accepted contract |
| **S1** | Single-ticker `screen accum TICKER` gains remaining plan **analysis** depth (evidence panels, refresh parity, TradeSetup display parity) | Operator can deep-judge without `plan swing` for analysis |
| **S2** | `plan swing` help/docs reframe as structure; warn or guide when used without structure flags / capital / horizon intent | Product messaging matches slogan |
| **S3** | Extract shared judgment composer used by screen single-ticker and plan (no dual policy) | Same inputs → same `TradeSetup.action` |
| **S4** | Plan focuses UI/JSON on structure fields; analysis panels thin or link “see screen” | Structure is plan’s headline |
| **S5** | Optional: typed `SwingTradeStructure` artifact + journal handoff fields | Structure is first-class, not only display |

Clean-break renames of public paths are **not** required by this ADR. Retiring
analysis-only use of `plan swing` is behavioral, not necessarily a CLI delete.

### 8. Layer plan

| Layer | Role |
|-------|------|
| Domain | Unchanged engines; future structure VOs if introduced |
| Application | Shared judgment composition; plan structure services (horizon/targets/sizing) |
| Infrastructure | Existing config (`swing_setups.yaml`, `swing_targets.yaml`) remains config-driven |
| Adapter | `screen_accum_*` = judgment UI; `plan_swing_*` = structure UI; thin wiring only |

### 9. Consequences

**Positive**

- One analysis desk (`screen`); one structure desk (`plan`)  
- Matches operator sequence: shortlist → deep-dive → design trade → journal  
- Reduces “why did plan disagree with screen?” once S3 lands  
- Keeps `plan` meaningful instead of a clone of screen  

**Negative / costs**

- Single-ticker screen becomes heavier (acceptable; universe mode stays light)  
- Temporary dual surface during S1–S4  
- Docs (`how_to_swing_trading.md`, building blocks) must be updated in S1–S2  

**Rejected alternatives**

| Alternative | Why rejected |
|-------------|--------------|
| Delete `plan swing` immediately | Loses structure home; forces sizing into screen |
| Keep plan as full second analysis forever | Verb overload; ADR-050 failure mode returns |
| Put structure on every universe row | Latency and noise; structure needs a *chosen* name |
| Rename to `plan accum` | Re-teaches accumulation as trade authority (ADR-050 §4) |

## Related commands (target mental model)

```text
saham screen accum --universe lq45 --top 10
saham screen accum BBCA                    # deep judgment
saham plan swing BBCA --capital …          # structure (+ sizing)
saham trade accum log …                    # paper notebook
```

## Current implementation note

| Slice | Status |
|-------|--------|
| **S0** (this ADR) | Done |
| **S1** judgment desk | **Complete 2026-07-29** — baseline (Judgment strip, `trade_setup`, pattern board, refresh) + **analysis merge**: explicit-ticker `--setup` / `--with-flow-detail` / `--with-sentiment` / `--full` via shared deep-evidence service (no Action mutation; structure stays plan-only); universe/multi hard-reject deep flags |
| **S2** plan messaging | **Shipped 2026-07-28** — structure-desk help/footers/docs |
| **S3** judgment authority | **Shipped 2026-07-28** — default plan Action inherits screen `candidate.trade_setup`; recompute only with explicit flags |
| **S4** structure-first UI | **Shipped 2026-07-29** — Structure panel first; detail with `--full` |
| **S5** swing_trade_plan | **Shipped 2026-07-29** — typed `swing_trade_plan` artifact on plan swing (JSON + `journals/plans/TICKER_latest.json`); `trade accum log --from-plan` freezes geometry |
| **Policy A** (MCE) | **Locked** — screen MCE remains **display-only**; plan never recomputes Action via MCE/TechnicalGate; plan CLI is **structure-only** (analysis flags stripped). B-MCE into DecisionPolicy is a separate future task if wanted. |

**Trust this ADR for product contract; trust live `--help` and code for shipped depth.**
Verify with source before claiming a later slice is done.
