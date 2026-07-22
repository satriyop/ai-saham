# Engine Factor Inventory And ML Proving Map

Status: research inventory (non-authoritative for promotion or production config)  
Date: 2026-07-22  
Scope: SignalEngine, RiskEngine, MarketContextEngine (MCE), plus Accum / foreign-flow score as Signal feeder  
Related: `docs/roadmap/roadmap_to_machine_learning.md`, `docs/research/s6_bci_authority_spike.md`, `docs/signal_evidence_authority.md`

## 0. Objective

Prove each factor that influences Signal, Risk, and Market Context with data —
not treat YAML defaults as truth.

This document answers three questions:

1. What factors/evidence/parameters currently influence those engines?
2. Which are still arbitrary (design defaults) but act as if authoritative?
3. How would a separate ML/proving application categorize them?

**Important architectural stance (unchanged):** deterministic engines remain
Validator + Executor. ML is an offline Author/challenger that proposes
thresholds, weights, and feature importance — never opaque score authority
inside domain runtime until a promotion lane certifies it.

---

## 1. System map (how the three engines interact)

```text
Raw market / broker / enrichment
        │
        ▼
Derived features + ScoreForeignFlow (Accum feeder)
        │
        ├──────────────► Setup gates ──► SetupEvidence (match_strength)
        │
        └──────────────► FlowConfirmationEvidence (capped_strength + Bandar)
                │
                ▼
        SignalEvidenceGroupScorer (setup 60% + flow 40%)
                │  + do-no-harm flags
                │  + classification thresholds
                ▼
        DecisionPolicy (regime × setup × readiness × authority coverage)
                │
                ▼
        EntryQuality ENTER / WATCH / AVOID  ──┐
                                              ├──► TradeSetup
        RiskEngine (gates → OPEN / BLOCKED) ──┘

MarketContextEngine ──► regime + gate_tightening + confidence/stability
        │                      │
        ├─► DecisionPolicy.regime_policy
        ├─► SignalEvidenceGroupScorer gate_tightening (ENTER→WATCH)
        └─► RiskEngine regime overlay (optional; often preview-only)
```

Accum / foreign-flow score is **not** a fourth “engine,” but it is the largest
upstream feeder into Signal setup gates and the flow group. Proving Signal
without proving Accum components is incomplete.

---

## 2. Factor inventory — what exists and what it does

Legend:

| Authority label | Meaning |
|-----------------|---------|
| **PROD-SCORE** | Changes canonical signal score |
| **PROD-POLICY** | Caps ENTER/WATCH/AVOID or OPEN/BLOCKED without changing raw score |
| **PROD-GATE** | Pass/fail contributes to setup match or risk block |
| **FEEDER** | Upstream input into PROD paths |
| **DIAG** | Diagnostic / Alpha-Trigger / panels; weight 0 for authority |
| **DISPLAY** | Screen/CLI only |
| **DEAD** | Config claims a behavior code does not implement |

---

### 2.1 Accum / foreign-flow feeder (`ScoreForeignFlowUseCase`)

Config: `config/accumulation_screener.yaml` → `evidence.components.*`

| Factor | Config / code | Role | Authority |
|--------|---------------|------|-----------|
| `consistency` (net_buy_ratio) | weight 33.3 | Fraction of window sessions with net foreign buy | FEEDER → flow group `cons` |
| `streak` (consecutive buy days) | weight 25.0, τ=7 | Exponential saturation of buy streak | FEEDER → `streak` |
| `vwap_discount` | weight 16.7, saturate 10% | How far price is below foreign VWAP | FEEDER → `vwap` + setup gate input |
| `foreign_flow_ratio` | weight 8.3, saturate 20% | Net foreign share of turnover | FEEDER → `flow` + setup gate |
| `rsi_headroom` | weight 8.3, tent 25/40/75 | RSI “entry headroom” in composite Accum score | FEEDER to composite only — **excluded** from flow group sub-signals |
| `bb_squeeze` | weight 8.3, tight/loose 0.20/0.40 | BB width percentile squeeze | **Disabled** (`enabled: false`); DIAG for setup/phase |
| `bci` / institutional | CLUSTER 12.5 / STABLE 4.2 | Tier-1 broker net-buyer count → label | FEEDER → `inst` |
| BCI label inputs | `broker_quality.tier1.*`, cluster_min=3, stable_min=1 | Count of Tier-1 desks with `net_lot > 0` | FEEDER |
| `bci_absorption_ratio` | computed in evaluator | Tier-1 buy vs aggregate sell when window net negative | **DIAG only** (not scored) |
| Sector breadth bonus | `sector_breadth.bonus_pts`, threshold 0.60, min peers 3 | Adds points to foreign_flow_score when peers net-buy | FEEDER (inflates score; not a Signal evidence group) |
| Smart/noise broker lists | `broker_quality.smart_money` / `noise` | Used by smart-money setup gates & tracked broker display | FEEDER / DISPLAY |

**Derived feature inputs** (`derived_features`): RSI(14), trend SMA(20) ±2%, BB(20)/history(60), market VWAP period(20), window net_buy_ratio / streak / avg_flow_ratio / vwap_discount_pct.

---

### 2.2 SignalEngine — PRODUCTION score path

Config: `config/signal_engine.yaml`, `config/swing_setups.yaml`

#### Setup quality group (weight **0.60**)

| Factor | What it does | Authority |
|--------|--------------|-----------|
| `SetupMatch` → `match_strength` | MATCH=100 / PARTIAL=60 / NO_MATCH=20 | PROD-SCORE |
| `partial_max_failed_gates` | Failed-gate budget for PARTIAL (2 for most setups; 1 for smart-money) | PROD-GATE |
| foreign-bounce gates | score≥58.3, fvwap≥3%, trend=SIDE, flow%≥5, RSI≤60 | PROD-GATE |
| coiled-spring gates | score≥50, BB%ile≤0.20, flow%≥3, RSI≤65 | PROD-GATE |
| smart-money gates | score≥50, smart_flow≥0, smart_share≥30%, noise_share≤60%, no smart net sell | PROD-GATE |
| pullback gates | score≥45.8, fvwap≥−2%, trend=UP, flow%≥2, RSI 40–65 | PROD-GATE |
| SetupEvidence extras (BB, RSI, resistance, volume_trend, benchmark excess) | Attached for panels / diagnostics | DIAG (not in match_strength) |

#### Flow confirmation / institutional_flow group (weight **0.40**)

| Factor | What it does | Authority |
|--------|--------------|-----------|
| Flow sub-signals `cons, streak, vwap, flow, inst` | Renormalized available-weight average → `flow_strength` | PROD-SCORE |
| Bandar broad score (−12..+12) | Normalized and averaged with flow_strength | PROD-SCORE |
| Group cap **0.80** | Caps uncapped flow strength before ×100 | PROD-SCORE |
| `component_coverage` | Available / enabled weight → authority fraction | PROD-POLICY (via authority coverage) |
| `confirmation_status` | CONFIRMED / WATCH_ZONE / WEAK from score + flow direction | PROD for phase/Alpha trigger; **not** DecisionPolicy ENTER predicate today |
| `flow_direction` | POSITIVE / NEGATIVE / FLAT | PROD (phase DISTRIBUTION + confirmation) |

#### Aggregation, flags, classification

| Factor | Threshold / weight | Authority |
|--------|--------------------|-----------|
| Group weights setup/flow | 0.60 / 0.40 | PROD-SCORE |
| Missing both groups | neutral score 50 | PROD-SCORE |
| `valuation_stretched` | forward PE > 50 → −10 | PROD-SCORE |
| `analyst_bearish` | buy% < 0.20 → −8 | PROD-SCORE |
| `insider_selling` | net_buy_ratio < −0.30 → −12 | PROD-SCORE |
| Classification STRONG/MODERATE/WEAK | score ≥70 / ≥45 | PROD-SCORE → preliminary ENTER/WATCH/AVOID |
| `gate_tightening` from MCE | ENTER → WATCH before DecisionPolicy | PROD-POLICY |

#### DecisionPolicy (caps only)

| Factor | What it does | Authority |
|--------|--------------|-----------|
| `regime_policy` per RISK_ON/NEUTRAL/RISK_OFF/VOLATILE | enter_allowed, enter/watch thresholds, authority floors, size multipliers | PROD-POLICY |
| `setup_regime_policy` matrix | Setup family × regime → max_decision | PROD-POLICY |
| `allowed_if_flow_confirmation_strong` | YAML action for foreign_bounce × RISK_OFF | **DEAD** — does not inspect flow strength; RISK_OFF `enter_allowed=false` still wins |
| Setup phase readiness | DISTRIBUTION/FAILED→AVOID; EXHAUSTION→WATCH; phase not in `can_enter_from_phases`→INELIGIBLE; PARTIAL/NO_MATCH caps | PROD-POLICY |
| Regime confidence / stability | confidence < 0.35 or TRANSITIONING → ENTER→WATCH | PROD-POLICY |
| `signal_authority_coverage` floors | 0.70 / 0.70 / 0.80 / 1.00 by regime | PROD-POLICY |

#### Setup phase detector (feeds readiness)

| Threshold | Value | Use |
|-----------|-------|-----|
| distribution bandar min | −4 | DISTRIBUTION |
| failed drawdown / support break | −7% / −3% | FAILED |
| exhaustion RSI / extension | 72 / 8% | EXHAUSTION |
| compression BB | 0.20 | COMPRESSION |
| breakout reclaim / close above | 0.0 / 0.0 | BREAKOUT_CONFIRMATION |
| volume dry-up / expansion | 0.50 / 1.50 | Volume trigger |
| `accumulation_min_flow_score` | 50.0 | **Config placeholder — not wired** |

---

### 2.3 SignalEngine — DIAGNOSTIC / parallel paths

| Factor group | Config | Role | Authority |
|--------------|--------|------|-----------|
| Alpha/Trigger projection | `alpha_trigger.*` | Parallel blend; horizons TACTICAL_3D / SWING_10D / ACCUM_20D | DIAG |
| Sector context | `config/sector_context.yaml` | Sector vs IHSG, peer breadth, ticker RS | DIAG |
| Company quality context | `config/company_quality_context.yaml` | Valuation / analyst / insider / seasonality axes | DIAG (flags above are PROD) |
| Legacy regime conditioning | `regime_conditioning.*` | Multiplies legacy score only | DIAG → `legacy_conditioned_score` |
| InstitutionalAccumulationEvidence | IA builder | Rich broker microstructure diagnostics | DIAG (never feeds Signal/DecisionPolicy) |
| Strategy evidence / ticker profile fields in fingerprint | various | Captured for research | DIAG / research |

---

### 2.4 RiskEngine

Config: `config/risk_engine.yaml`

| Gate / parameter | Default | Behavior | Authority |
|------------------|---------|----------|-----------|
| FundamentalGate (Piotroski) | fire if F ≤ 3 | Structural block | PROD-GATE |
| LiquidityGate market-cap floor | 1T IDR | Structural block | PROD-GATE |
| LiquidityGate median tx | 5B IDR/day over 20 sessions | Structural block | PROD-GATE |
| FreeFloatGate | free float < 15% | Structural block | PROD-GATE |
| BandarGate | 5d label in {Small Dist, Big Dist} | Execution block | PROD-GATE |
| TechnicalGate | opt-in; RSI OB/OS 70/30; agreement≥2 | Execution block | PROD-GATE (optional) |
| `missing_data_action` | **skip** for all default gates | Missing inputs → pass | PROD-GATE (fail-open) |
| Indicator periods | SMA/EMA 20, RSI 14, history 365 | Snapshot for technical path | FEEDER |
| MCE regime overlay | if `gate_tightening` and enabled | Inject `regime:{REGIME}` structural block | PROD-GATE (when MCE passed) |

**Note:** Canonical swing risk path often runs with `market_context=None`; regime block is frequently preview-only. That split is itself a proving/ops concern.

---

### 2.5 MarketContextEngine

Config: `config/market_context_engine.yaml`

| Factor | Weight | What it scores | Authority |
|--------|--------|----------------|-----------|
| VIX | 0.20 | Global risk appetite (anchors 15/20/25/35) | PROD (conviction) |
| EIDO vs IHSG | 0.20 | 5d ETF lead/lag | PROD |
| USD/IDR | 0.15 | 5d rupiah strength (inverted) | PROD |
| IDX trend (IHSG vs SMA50/20) | 0.15 | Local trend | PROD |
| IDX breadth (% above SMA20) | 0.15 | Universe participation | PROD (unavailable if empty universe) |
| Foreign flow (universe aggregate) | 0.15 | Net foreign vs baseline | PROD (unavailable if empty universe) |
| Commodity composite | disabled | CPO/coal | DIAG / off |
| Regime thresholds | ≥0.65 RISK_ON, ≤0.35 RISK_OFF, else NEUTRAL | Classification | PROD-POLICY |
| VIX > 35 | VOLATILE override | Hard regime | PROD-POLICY |
| `regime_effects.*.gate_tightening` | true for RISK_OFF/VOLATILE | Tightens Signal + optional Risk | PROD-POLICY |
| `signal_multiplier` | 0.60 / 0.50 off/volatile | Stored metadata; **not** applied to canonical score | DISPLAY/metadata |
| Regime confidence / stability | distance-to-boundary; STABLE if ≥5 days | DecisionPolicy caps | PROD-POLICY |

---

## 3. What is still arbitrary but treated as authoritative

These are **design defaults** with production effect. Some have partial research
support; none are fully certified via purged walk-forward promotion.

### 3.1 Highest “taken for granted” list (by impact)

| Item | Current value | Why arbitrary | Treated as |
|------|---------------|---------------|------------|
| Setup/flow group weights | 60 / 40 | Design blend; not OOS-optimized | PROD-SCORE |
| MATCH/PARTIAL/NO_MATCH → 100/60/20 | Fixed map | Coarse ordinal; no continuous calibration | PROD-SCORE |
| Foreign-flow component weights | 33.3 / 25 / 16.7 / 8.3 / 8.3 / 12.5 | Heuristic budget to 100 | PROD via feeder |
| VWAP saturate_at | 10% | Aligns with scoring saturation; gate still 3% | PROD feeder |
| foreign-bounce `min_vwap_discount_pct` | **3%** | Design default; quarantine spike suggests cliff nearer 8–10% in RISK_OFF only | PROD-GATE |
| `min_foreign_flow_score` per setup | 58.3 / 50 / 50 / 45.8 | ~7/12 and ~6/12 of 100-scale heuristics | PROD-GATE |
| Flow group cap | 0.80 | Hardcoded; prevents flow dominating | PROD-SCORE |
| Classification 70 / 45 | ENTER/WATCH cutoffs | Untuned against labels | PROD-SCORE |
| DecisionPolicy regime thresholds | 70/72 enter; 45/60/65 watch; authority 0.70–1.00 | Policy design | PROD-POLICY |
| Setup × regime matrix | foreign_bounce “strong flow” in RISK_OFF | Partially **DEAD** | Config authority without code truth |
| BCI CLUSTER points without flow sign | +12.5 always | Contradicted by S6 spike when aggregate flow negative | PROD feeder |
| Bandar label → ±2 mapping & average with flow | equal weight with flow_strength | Unproven blend | PROD-SCORE |
| Broker lists (tier1 / smart / noise) | Fixed codes | Institutional folklore until validated | PROD feeder / gates |
| Risk Piotroski ≤3, float <15%, cap <1T, median tx <5B | IDX heuristics | Fail-open on missing data amplifies arbitrariness | PROD-GATE |
| Risk `missing_data_action: skip` | Fail-open | Convenience ≠ safety | PROD-GATE |
| MCE factor weights | 20/20/15/15/15/15 | US-proxy heavy; IDX breadth/flow often unavailable | PROD regime |
| MCE regime cutoffs 0.65 / 0.35 | Symmetric bands | Untuned for IDX regimes | PROD-POLICY |
| VIX > 35 → VOLATILE | Global rule | May mislabel local IDX shocks | PROD-POLICY |
| Phase thresholds (RSI 72, BB 0.20, volume 0.50/1.50, …) | Lifecycle design | Partially wired; some unused | PROD-POLICY via readiness |
| Do-no-harm flag cutoffs (PE 50, buy% 0.20, insider −0.30) | Conservative guesses | Penalties applied to score | PROD-SCORE |
| Label SUCCESS thresholds (SWING_10D +4% / −4% stop) | Contract defaults | Defines “proven” itself | Research truth target |

### 3.2 Partially evidenced (not certified)

| Item | Evidence status |
|------|-----------------|
| Deep VWAP ≥8–10% | Quarantine spike (bearish window): cumulative edge appears; regime-confounded; not canonical OOS |
| BCI CLUSTER + negative flow | S6 spike: weak/harmful; absorption diagnostic added but not scored |
| Sector/company quality | DIAG only; parked promotion lane |
| MCE regime predictive of IHSG forward returns | `regime_observations` has 5/10/20d IHSG returns — usable for regime calibration, underused |

### 3.3 Explicit non-authority (good)

| Item | Status |
|------|--------|
| Alpha/Trigger DIAG groups | weight 0 for authority |
| InstitutionalAccumulationEvidence | never feeds Signal/DecisionPolicy |
| Legacy `regime_conditioning` | diagnostic score only |
| Screen Disc% color tiers / `--sort-by vwap` | display UX only |
| Quarantine observation tables | excluded from canonical promotion |

---

## 4. Database reality check (what we can prove today)

Primary DB: `data/db/data.db` (approx counts as of 2026-07-22 inventory).

| Asset | Rows | Use for proving |
|-------|------|-----------------|
| `candidate_observations` | ~2,565 | Canonical `screen_accum` snapshots; `payload_json.sub_signal_fingerprint` (~120 keys) |
| `signal_forward_labels` | ~2,565 | 1:1 `SWING_10D` raw-market SUCCESS/FAILURE/NEUTRAL + returns/MAE/MFE |
| `regime_observations` | ~203 | Daily regime + IHSG forward 5/10/20d |
| `market_context_snapshots` | ~204 | Factor-level MCE JSON per day |
| Quarantine obs/labels | ~19k / ~5.7k | Audit only — **not** for promotion |
| Raw tables | candles, broker_daily_flow, bandar, enrichment caches | Recompute factors / expand features |

### Gaps that block “prove everything”

1. **No persisted RiskAssessment time-series** (only partial gate fields in TradeSetup payload).
2. **Single workflow cohort** (`screen_accum`); named swing-setup captures parked.
3. **Only SWING_10D labels** generated (TACTICAL_3D / ACCUM_20D defined but empty).
4. **No screen-rejected control population** (`contains_control_population=false`).
5. **Raw-market labels only** (no net-executable IDX costs/limits/fills).
6. **Short date span** for canonical panel (~2026-06-02 → 2026-07-03) — thin for walk-forward.
7. Bandar / BCI / VWAP proving often needs **recompute from broker_daily_flow** when fingerprint lacks the exact gate input.

---

## 5. Theoretical ML / stats that can help (without replacing the engine)

Goal: **prove and calibrate factors**, then propose config patches — not train a
black-box that silently overrides Signal/Risk/MCE.

### 5.1 Methods by problem type

| Problem | Suitable methods | Output artifact |
|---------|------------------|-----------------|
| Is factor X predictive of SWING_10D SUCCESS / return? | Univariate IC, bucketed hit-rate, mutual information, isotonic calibration | Factor report + keep/kill/weaken |
| What threshold is less arbitrary? | Threshold sweep with purged CV; bootstrap CIs; regime-stratified sweeps | Proposed YAML value + uncertainty |
| Which weights among correlated flow components? | Elastic net / ridge on **linear** score reconstruction; Shapley on additive components; constrained optimization (weights ≥0, sum=100) | Proposed weight vector |
| Interactions (e.g. VWAP × regime × flow sign) | Rule lists, GAMs, shallow trees / rulefit, mutual information 2-way | Interaction policies for DecisionPolicy |
| Regime quality | Ordinal models or threshold learning on IHSG forward returns; hysteresis search | MCE cutoffs + dwell days |
| Risk gate value | Counterfactual: blocked vs would-have-traded forward outcomes; cost of fail-open | Fail-closed recommendations |
| Multi-factor ranking challenger | Gradient boosting / logistic on fingerprint — **shadow only** | Challenger score vs deterministic baseline |
| Causal / regime-shift robustness | Purged walk-forward, combinatorial purged CV (Lopez de Prado-style), adversarial validation | Promotion dossier |

### 5.2 What ML should **not** do here

- Replace SetupMatch with an opaque neural score inside domain.
- Promote sector/company evidence without the parked promotion lane.
- Optimize on quarantine labels and ship to production.
- Tune on the same window used as final holdout.
- Treat SUCCESS labels as executable P&L.

### 5.3 Recommended proving stack (separate application)

```text
Feature store (read-only from data.db + recomputes)
    → Experiment runner (purged WF, regime strata)
    → Reports (factor cards)
    → Proposed config diffs (YAML patches)
    → Human + promotion lane review
    → Optional shadow challenger (never default authority)
```

Ports: read observations/labels/regimes; write experiment artifacts only.
No write path into SignalEngine/RiskEngine/MCE runtime configs without review.

---

## 6. Categorization for a “proving-only” ML application

Organize work as **proving packages**, not as one mega-model.

### Package A — Accum / flow feeder (feeds Signal)

| ID | Factor family | Prove what | Primary labels | Data source |
|----|---------------|------------|----------------|-------------|
| A1 | consistency / streak / flow% / VWAP / BCI / RSI headroom | Marginal contribution to SWING_10D; weight necessity | `signal_forward_labels` | fingerprint + candidate payload + broker recompute |
| A2 | BCI direction / absorption | CLUSTER conditional on aggregate flow sign | same | S6 methodology, canonical join |
| A3 | Sector breadth bonus | Does bonus improve or dilute? | same | payload (`sector_breadth_pct` / `sector_breadth_bonus` now in `to_dict()`; re-screen for exact values) |
| A4 | Broker list quality | Tier1/smart/noise membership predictive? | same + broker_daily_flow | payload (`top_brokers`, BCI) + optional daily-flow recompute |

**ML tools:** threshold sweeps, constrained linear models, ablation of components.

### Package B — Setup / Signal score & policy

| ID | Factor family | Prove what | Labels | Notes |
|----|---------------|------------|--------|-------|
| B1 | match_strength map 100/60/20 | Ordinal calibration vs returns | SWING_10D | May need named-setup captures |
| B2 | Setup gate thresholds | Each gate’s ROC / precision at MATCH | SWING_10D + setup fields | Start with foreign-bounce VWAP/RSI/score; card recomputes MATCH from YAML |
| B3 | Group weights 60/40 | Reweight search under non-negative constraint | SWING_10D | Hold out by date |
| B4 | Flow cap 0.80 + Bandar blend | Cap sensitivity; Bandar equal-weight vs flow-only | SWING_10D | |
| B5 | Classification 70/45 | Decision curve / utility vs ENTER rate | SWING_10D | |
| B6 | DecisionPolicy regime floors | Authority coverage & enter thresholds by regime | join regime_observations | card: `factor_card_regime_policy.py` |
| B7 | Setup×regime matrix | Especially dead “strong flow” RISK_OFF path | regime-stratified | Fix code vs delete config first |
| B8 | Phase readiness thresholds | DISTRIBUTION/EXHAUSTION/BREAKOUT rules | phase fields in fingerprint | |

**ML tools:** rule mining, calibration plots, constrained optimization, policy evaluation (off-policy if actions recorded).

### Package C — RiskEngine

| ID | Factor family | Prove what | Labels | Gap |
|----|---------------|------------|--------|-----|
| C1 | Fundamental / liquidity / free-float / bandar gates | Do blocked names underperform would-be entries? | Need counterfactual captures | **Persist gate evaluations** |
| C2 | Fail-open vs fail-closed | Cost of skip-on-missing | Need missingness flags in panel | Capture GateContext completeness |
| C3 | Regime risk overlay | Does regime block save capital in RISK_OFF? | regime + labels | Ensure MCE passed into risk path |

**ML tools:** survival / drawdown analysis, policy value estimation; less “predict SUCCESS,” more “avoid disasters.”

### Package D — MarketContextEngine

| ID | Factor family | Prove what | Labels | Data |
|----|---------------|------------|--------|------|
| D1 | Each MCE factor | Predictive of IHSG 5/10/20d and of ticker SUCCESS conditional on regime | `regime_observations`, `market_context_snapshots` | Ready now |
| D2 | Factor weights | Reweight VIX/EIDO vs IDX breadth/flow | same | |
| D3 | Regime cutoffs + hysteresis | Stability vs predictive power tradeoff | same | |
| D4 | VOLATILE VIX override | False positive rate for IDX-local shocks | same | |

**ML tools:** regime classifiers, change-point detection, weight learning with coverage penalties.

### Package E — Diagnostic challengers (never auto-promote)

| ID | Factor family | Prove what |
|----|---------------|------------|
| E1 | Sector context | Incremental AUC / IC beyond PROD groups |
| E2 | Company quality axes | Same |
| E3 | InstitutionalAccumulationEvidence (IA_*) | Same |
| E4 | Full fingerprint GBDT challenger | Shadow ranker vs deterministic score |

Promotion only via parked evidence promotion lane after OOS dossier.

### Package F — Outcome definition sensitivity (meta)

| ID | Prove what |
|----|------------|
| F1 | SUCCESS thresholds (±4% etc.) sensitivity |
| F2 | Multi-horizon consistency (generate TACTICAL_3D / ACCUM_20D) |
| F3 | Net-executable labels when parked contract lands |

Without F, “proven factor” means “predicts our chosen label contract,” not “makes money after costs.”

---

## 7. Suggested proving priority (opinionated)

Given current DB + income use-case:

1. **A1–A2** (flow components + BCI direction) — highest scoring honesty, data mostly ready  
2. **D1–D3** (MCE calibration on regime_observations) — small N but clean daily panel  
3. **B2 / B6** (setup gates + regime policy), with VWAP as regime-stratified study — not blind 3→10  
4. **C1–C2** after persisting risk gate outcomes  
5. **E\*** only as challengers  
6. Expand canonical observation date range + multi-horizon labels before trusting any weight optimization

---

## 8. Clarifying questions for the product owner

These change how the proving app and “proven” definition should be built:

1. **Outcome definition:** Is `SWING_10D` raw-market SUCCESS the primary truth for now, or do you want return IC / MAE / custom utility (e.g. prefer avoiding large losers over maximizing hit rate)?
2. **Scope of “engines”:** Confirm Accum feeder is in-scope for proving (recommended). Exclude IA / Alpha-Trigger from production authority until Package E?
3. **ML app posture:** Offline batch lab that only emits YAML patch proposals + reports (recommended), or also a live shadow challenger score beside CLI?
4. **Regime conditioning:** Accept that some factors (deep VWAP, BCI) may be **conditionally** proven (e.g. RISK_OFF only) rather than globally true?
5. **Risk proving investment:** Are you willing to add persistence of full `RiskAssessment` / GateContext into observations as a prerequisite for Package C?
6. **Data expansion:** Prefer lengthening the canonical backfill window first, or starting experiments on the current ~2.5k panel knowing power is limited?

---

## 9. File / config anchors

| Area | Paths |
|------|-------|
| Signal config | `config/signal_engine.yaml`, `config/swing_setups.yaml` |
| Accum feeder | `config/accumulation_screener.yaml`, `src/application/use_case/score_foreign_flow_use_case.py` |
| Decision policy | `src/application/services/decision_policy.py` |
| Risk | `config/risk_engine.yaml`, `src/domain/rules/*_gate.py` |
| MCE | `config/market_context_engine.yaml`, `src/application/services/market_context_factor_scorers.py` |
| Authority rules | `docs/signal_evidence_authority.md` |
| ML destination (non-authoritative) | `docs/roadmap/roadmap_to_machine_learning.md` |
| Prior spike | `docs/research/s6_bci_authority_spike.md` |

---

## 10. Factor proving lab charter (scaffold)

Offline lab lives at `research/` (see `research/README.md`). It is Mode A only.

| Rule | Detail |
|------|--------|
| Layout | `research/lab/` panel loaders, `research/scripts/` cards, `research/artifacts/` outputs |
| Deps | Optional `[project.optional-dependencies] research` / `research/requirements.txt` — not default install |
| First scripts | `factor_card_vwap_buckets.py`, `factor_card_bci_flow_sign.py`, `factor_card_accum_components.py`, `factor_card_sector_breadth.py`, `factor_card_broker_lists.py`, `factor_card_setup_gates.py`, `factor_card_regime_policy.py`, `factor_card_mce_factors.py` under `research/scripts/` |
| Forbidden | Lab code must not be imported by `src/`; no auto-writes to production YAML |
| Authority | Factor cards propose; humans + promotion lane decide |

```bash
.venv/bin/python research/scripts/factor_card_vwap_buckets.py
```

---

## 11. One-sentence summary

Every production knob above is a **hypothesis encoded as YAML**; the proving app’s job is to turn those hypotheses into **accepted / rejected / regime-conditional / still-uncertain** cards with walk-forward evidence — while the deterministic engine stays the only runtime authority until a promotion lane says otherwise.
