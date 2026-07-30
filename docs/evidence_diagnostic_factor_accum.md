# Accum journey — evidence, diagnostic evidence, and enter factors

Operator / architecture inventory of **what can influence enter vs not-enter** for one ticker on the accumulation journey (`screen accum` → optional `plan swing` / judgment desk).

**Related:** [ADR-030](adr/ADR-030-accumulation-screener-evidence-split.md) · [ADR-043](adr/ADR-043-score-naming-vocabulary.md) · [ADR-054](adr/ADR-054-screen-judge-plan-structure-contract.md) · [ADR-057](adr/ADR-057-evidence-diagnostic-evidence-corpus-vocabulary.md) · [ADR-058](adr/ADR-058-setup-phase-ledger-production-memory.md) · [signal_engine_evidence_model.md](signal_engine_evidence_model.md) · [building_block_swing_trade.md](building_block_swing_trade.md)

**Sibling scoring lab:** offline policy/factor tournaments live in `ml-saham` ([BOUNDARY.md](../BOUNDARY.md)); this doc is about **live product judgment**, not corpus cohort evaluate.

---

## 1. Decision composition (final Action)

```text
eligible on screen?
  → Accum score (flow book)
  → Signal score + flags + DecisionPolicy (+ setup readiness)
  → Risk gates (hard block)
  → TradeSetup.action = final Action
```

| Action | Meaning |
|--------|---------|
| **ENTER** | Signal wants enter; risk open |
| **WATCH** | Interesting; not enter |
| **AVOID** | Weak signal |
| **BLOCKED_STRUCTURAL** | Structural risk hard fail |
| **BLOCKED_EXECUTION** | Execution / bandar hard fail |

Composer (`AssessTradeSetupUseCase`): **risk block first**, else signal `entry_quality` → Action.

**Evidence vocabulary (ADR-057):**

| Kind | Role |
|------|------|
| **Production evidence** | May move score / Action / readiness |
| **Diagnostic evidence** | Explains only; must not set Action on the accum desk |
| **Corpus** | Learning observations/labels; not live Action |

---

## 2. Journey stages (what can veto)

| Stage | What it decides | Can block ENTER? |
|-------|-----------------|------------------|
| Pre-eval skip | Not enough broker / net-buy days | Yes (no candidate) |
| Structural filter | Cap / Piotroski floors (if enabled) | Yes |
| Accum score filter | `min_accum_score` | Yes if enabled and threshold &gt; 0 |
| Signal score filter | `min_signal_score` | Yes if enabled (default **off**) |
| Signal + flags + DecisionPolicy | ENTER / WATCH / AVOID | Yes |
| Setup readiness | Caps ENTER when family known | Yes (often WATCH on screen) |
| RiskEngine | BLOCKED_* | Yes (overrides signal) |
| TradeSetup | Final Action | Yes |
| Diagnostic panels / plan structure / alpha_trigger | Explain / size / structure | **No** (policy A) |

### Screen path fact (important)

Default **universe / single-ticker screen** builds **flow-only** canonical signal evidence (`setup=None` on the production attach path). Market context is **display-only** and is **not** injected into DecisionPolicy on screen (B-MCE-display / policy A).

Named setups may still run for **family / diagnostic fit**; missing full setup evidence often → readiness **UNAVAILABLE → WATCH**.

`plan swing` **inherits** screen Action unless re-judge flags (e.g. market context / technical gate) are explicitly used.

---

## 3. Hard filters (eligibility)

| Factor | Code / config | Default | Role |
|--------|---------------|---------|------|
| Min foreign net-buy days | `min_net_buy_days` | **2** | Skip ticker |
| Broker window | `window_days` | **7** (also 30/90) | Lookback for flow metrics |
| Usable broker rows | evaluator | — | Skip bad/missing data |
| Market-cap floor | `min_market_cap_idr` | **0 (off)** | Hard reject if enabled |
| Piotroski floor | `min_piotroski` | **0 (off)** | Hard reject if enabled |
| Min Accum score | `min_accum_score` + enabled | **0** (enabled but zero) | Board filter if raised |
| Min Signal score | `min_signal_score` + enabled | **off** | Board filter if enabled |

Config home: `config/accumulation_screener.yaml` + `AccumulationScreenRequest`.

---

## 4. Accum score (discovery book, 0–100)

**Owner:** `ScoreAccumUseCase` · **name:** Accum (not Signal) — ADR-039 / ADR-043.

**Role:** Soft ranking and **flow evidence** inputs. Not the final Action alone.

| Key | Factor | Default weight | Notes |
|-----|--------|----------------|-------|
| `cons` | Consistency (net-buy day ratio) | **33.3** | Required for a scored candidate |
| `streak` | Consecutive buy streak | **25.0** | Required |
| `vwap` | Price vs foreign VWAP discount | **16.7** | Optional / may be missing |
| `rsi` | RSI headroom | **8.3** | Soft |
| `flow` | Foreign % of turnover | **8.3** | Soft |
| `bb` | BB squeeze (width percentile) | **8.3, disabled** | Setup/phase diagnostic; not default score |
| `inst` | BCI (Tier‑1 concentration) | cluster **12.5** / stable **4.2** | Soft |
| Sector breadth bonus | Peer net-buy breadth | +**10** if ≥ **60%** peers (min peers **3**) | Soft add-on |

**BCI inputs:** Tier‑1 broker list; `bci_cluster_min_count` **3**; `bci_stable_min_count` **1**.

**Display-only Accum language** (not Action authority): enter-ish ~**58.3**, watch ~**33.3** of max — board/pattern helpers only.

---

## 5. Production signal evidence (canonical)

### 5.1 Flow confirmation group (production)

**Builder:** flow confirmation from Accum breakdown (+ optional bandar).  
**Config weight:** `evidence_groups.flow_confirmation` (default **0.40**). On screen, often the **only** attached group → renormalized base.

| Factor | Role | Moves Action? |
|--------|------|---------------|
| Sub-signals `cons`, `streak`, `vwap`, `flow`, `inst` | Soft group strength | Yes (score) |
| Bandar `broad_score` (if present) | Soft blend | Yes |
| Component coverage | Authority fraction | Yes (coverage floors) |
| Group cap (~**0.80**) | Caps flow contribution | Yes |

RSI/BB are **not** in the production flow group (Accum `bb` sleeve disabled by default).

### 5.2 Setup quality group (production when attached)

**Builder:** setup evidence from named `SetupEvaluation`.  
**Weight:** **0.60** when attached.  
**Screen discovery:** usually **not** attached.

| Match | Score points (group) |
|-------|----------------------|
| MATCH | 100 |
| PARTIAL | 60 |
| NO_MATCH | 20 |

### 5.3 Production flags (score penalties)

| Flag | Rough trigger | Penalty |
|------|---------------|---------|
| `VALUATION_STRETCHED` | Forward PE stretched | −10 |
| `ANALYST_BEARISH` | Low analyst buy % | −8 |
| `INSIDER_SELLING` | Net insider selling | −12 |

Config: `config/signal_engine.yaml` → `flags`.

### 5.4 Classification → preliminary entry quality

| Score | Class | Direction |
|-------|-------|-----------|
| ≥ **70** | STRONG | ENTER |
| ≥ **45** | MODERATE | WATCH |
| else | WEAK | AVOID |

Config: `signal_engine.classification.strong_min_score` / `moderate_min_score`.

### 5.5 DecisionPolicy (caps; does not re-score raw)

Can demote ENTER → WATCH / AVOID:

| Factor | Role on **default screen** |
|--------|----------------------------|
| Regime max decision / enter allowed | Defaults act like **RISK_ON** (MCE not policy-wired on screen) |
| Regime enter / watch thresholds | Floors on quality |
| `min_signal_authority_coverage` | Coverage floor (~**0.70** ENTER on RISK_ON) |
| Setup × regime matrix | When family + regime known |
| Setup readiness | See §7 |
| `gate_tightening` / low regime confidence | Only if MCE production-wired |

**Legacy regime conditioning** of score: diagnostic only.  
**Regime size multiplier:** sizing (plan), not Action.

---

## 6. Named setups (fit / family / readiness)

**Config:** `config/swing_setups.yaml` · **Evaluator:** `EvaluateSwingSetupUseCase`.

On screen: primarily **family detection + diagnostic fit**. Do not treat MATCH alone as ENTER authority when setup evidence is not production-attached.

| Setup id | Family | Entry authority | Typical gates |
|----------|--------|-----------------|---------------|
| `foreign-bounce` | accumulation | Yes from **BREAKOUT_CONFIRMATION** | Min Accum, VWAP discount, trend SIDE, flow, max RSI |
| `coiled-spring` | breakout | Yes from **BREAKOUT_CONFIRMATION** | Min Accum, max BB pctile, flow, max RSI |
| `smart-money-confirmed` | confirmation | **No** (`entry_authority: false`) | Accum + smart-flow / share gates |
| `pullback-continuation` | pullback | Yes from **BREAKOUT_CONFIRMATION** | Min Accum, trend UP, flow, RSI band, VWAP |

Smart-money detail often unavailable on board → honest **NO_MATCH** for that setup.

---

## 7. Setup phase and readiness

**Detector:** `SetupPhaseDetector` · **Readiness:** `SetupPhaseReadinessEvaluator` · **History:** phase ledger (ADR-058).

### Phases (illustrative)

| Phase | Rough meaning | Enter impact |
|-------|---------------|--------------|
| ACCUMULATION | Constructive build | Usually not enter phase alone |
| COMPRESSION | Squeeze / coil | Usually not enter phase alone |
| BREAKOUT_CONFIRMATION | Main enter-capable phase for most families | Required for many families |
| DISTRIBUTION | Selling / distribution | → often INELIGIBLE / AVOID path |
| FAILED | Structure failed | → AVOID path |
| EXHAUSTION | Extended | → WATCH cap |

Example phase inputs (config-driven): distribution bandar score, drawdown / support break, RSI + extension, BB width pctile, volume dry-up → expansion, sequence vs family `required_sequence`.

### Readiness outcomes (high level)

| Situation | Typical cap |
|-----------|-------------|
| No setup family | No readiness cap (flow-only OK) |
| DISTRIBUTION / FAILED | AVOID path |
| EXHAUSTION | WATCH |
| Family known but **no setup evidence** | UNAVAILABLE → **WATCH** (common on screen) |
| PARTIAL / incomplete | WATCH |
| NO_MATCH / no entry authority / wrong phase / bad sequence | WATCH / not ENTER |
| READY | No readiness demotion |

Most families only allow enter from **BREAKOUT_CONFIRMATION**.

---

## 8. Risk gates (hard Action override)

**Config:** `config/risk_engine.yaml`.

| Gate | Tier | Default trigger (approx.) | Action |
|------|------|---------------------------|--------|
| Fundamental | Structural | Piotroski ≤ **3** | BLOCKED_STRUCTURAL |
| Liquidity | Structural | Cap &lt; **1T IDR** (turnover rules when data present) | BLOCKED_STRUCTURAL |
| Free float | Structural | Free float &lt; **15%** | BLOCKED_STRUCTURAL |
| Bandar | Execution | 5d Small/Big distribution labels | BLOCKED_EXECUTION |
| Technical | Execution | Bearish indicator agreement | **Opt-in** re-judge only |

Structural evaluated before execution. Triggered gate **overrides** signal ENTER.

---

## 9. Diagnostic evidence (never Action authority on accum desk)

Under ADR-057 these **explain** or feed parallel projections; they must not be treated as the Action source of truth on default screen/plan structure.

| Producer / bag | Examples | Notes |
|----------------|----------|-------|
| Market context (MCE) | VIX, EIDO vs IHSG, USD/IDR, IDX trend, breadth, foreign regime | **Display** on screen; not DecisionPolicy input by default |
| Institutional accumulation | Multi-track foreign/domestic | Diagnostic producer |
| Sector context | Peer-relative sector | Diagnostic / alpha slot |
| Sector-macro | Routed macro drivers per universe group (ADR-053); panel on `screen accum TICKER` + full view ticker | Diagnostic; never Action |
| Company quality | Valuation, analyst, insider, seasonality bag | Diagnostic; some fields also feed **production flags** when mapped |
| Alpha/Trigger | Parallel projection | Not TradeSetup path |
| Strategy / sentiment panels | Optional `--full` style | Diagnostic |
| Multi-window pattern labels | Coiled spring / sustained / … | Ranking language |
| Corp action near-date flags | Dividend / rights / RUPS windows | Display risk flags (not RiskEngine gate) |
| Resistance flag | Near resistance | Display |
| Screen judgment diagnostic bag | ADR-054 S1 side-bag | Display / explain only |
| Plan structure fields | Horizon, stop, target, lots | Structure desk; does not re-Action unless re-judge |

---

## 10. Enrichment → engines (data sources)

| Enrichment | Typically feeds |
|------------|-----------------|
| Broker summaries / foreign flow | Accum score, flow group |
| Bandar detector | Flow blend, bandar risk gate, phase DISTRIBUTION |
| Fundamentals (Piotroski, mcap) | Screen structural filter, fundamental/liquidity risk |
| Shareholding free float | Free-float risk |
| Insider net activity | Flag + CQ diagnostic |
| Analyst / forward PE | Flags + CQ diagnostic |
| Seasonality | CQ diagnostic |
| Sector notation | Sector / peer diagnostics |
| Top brokers / Tier‑1 lists | BCI + smart-money setup |
| Candles | RSI, BB, VWAP, trend, technical gate (if enabled) |

---

## 11. Config cheat-sheet (Action-relevant)

| Area | Path | Defaults that often matter |
|------|------|----------------------------|
| Accum components / filters | `config/accumulation_screener.yaml` | Weights; min_net_buy_days **2**; min_accum often **0** |
| Signal classification | `config/signal_engine.yaml` | strong **70**, moderate **45** |
| Flags | `signal_engine.flags` | Penalties can drop below 70 |
| Decision policy | `signal_engine.decision_policy` | Coverage floors; regime tables |
| Risk | `config/risk_engine.yaml` | Piotroski **3**, mcap **1T**, free float **15%** |
| Setups + phase | `config/swing_setups.yaml` | Per-setup gates; phase thresholds |
| MCE | `config/market_context_engine.yaml` | Display factors on screen |
| CQ / institutional | `company_quality_context.yaml`, `institutional_accumulation.yaml` | Diagnostic producers |

---

## 12. Practical “why not ENTER?” checklist

1. **No candidate** — `&lt; min_net_buy_days` or missing broker/candles.  
2. **Structural screen reject** — mcap / Piotroski if enabled.  
3. **Accum filter** — if `min_accum_score` raised.  
4. **Signal &lt; ~70** after flags (or policy demotion) → not preliminary ENTER.  
5. **DecisionPolicy** — coverage / readiness / regime (if wired).  
6. **Setup readiness** — family without setup evidence → **WATCH** (common on discovery).  
7. **Risk** — Piotroski / mcap / free float / bandar distribution → **BLOCKED_***.  
8. **Not the reason alone:** MCE panel, CQ/sector-macro bags, alpha_trigger, multi-window labels, display Accum thresholds, plan sizing, strategy/sentiment panels.

---

## 13. Code map

| Layer | Primary locations |
|-------|-------------------|
| Screen workflow | `application/use_case/run_accumulation_screen_workflow_use_case.py`, `accumulation_screen_use_case.py` |
| Eval / enrich / Accum score | `accumulation_candidate_*`, `score_accum_use_case.py` |
| Evidence builders | `flow_confirmation_evidence_builder.py`, setup / candidate evidence builders |
| Signal | `assess_signal_evidence_use_case.py`, `decision_policy.py`, `signal_engine.py` |
| Phase / readiness | `setup_phase_detector.py`, `setup_phase_readiness_evaluator.py`, phase ledger (ADR-058) |
| Risk / Action | `assess_risk_use_case.py`, domain risk gates, `assess_trade_setup_use_case.py` |
| Named setups | `evaluate_swing_setup_use_case.py`, `config/swing_setups.yaml` |
| Display labels | `adapters/shared/score_display_labels.py` |

---

## 14. Non-goals of this document

- Pre-open auction journey (separate building block).  
- Corpus path labels / learning evaluate (see ADR-056, [BOUNDARY.md](../BOUNDARY.md)).  
- ml-saham challenge metrics (excess IC, WIN/LOSE).  
- Guaranteeing every config default forever — **live YAML wins** when this doc drifts; prefer code + config for thresholds.

When in doubt: **production evidence + risk + readiness move Action; diagnostic explains.**
