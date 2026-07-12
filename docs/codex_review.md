# Independent Review of the IDX Signal, Risk, Market Context, and Learning Engines

**Review date:** 2026-07-12  
**Scope:** Current implementation, configuration, tests, and local SQLite evidence for the signal engine, risk engine, market context engine (MCE), swing backtest, forward-label workflow, and tuning guardrails.  
**Purpose:** Decision-support research for IDX screening and analysis. This is not a claim of investment performance and not financial advice.

## Executive verdict

The application has a stronger software and governance foundation than most personal stock screeners: deterministic execution, explicit evidence authority, point-in-time provider interfaces, separate signal/risk responsibilities, reproducible fingerprints, missing-data visibility, and human-gated tuning are all good decisions.

The weakness is empirical, not architectural. The current rules contain many plausible hypotheses, but most weights and thresholds have not yet earned predictive authority. The local database has only about one year of candles, forward labels cover 102 signal dates and 45 tickers, and there are only two persisted regime observations with no 10-day IHSG forward labels. That is insufficient to establish robustness across IDX bull, bear, commodity, currency, election, rate, liquidity, and crisis regimes.

The app should therefore be described today as a **deterministic research and ranking system with an early validation loop**, not an accurate prediction engine. Its next high-impact milestone is not another indicator. It is a leakage-safe, point-in-time research dataset and validation framework that can prove whether each feature adds out-of-sample value after realistic IDX costs and execution constraints.

## What was inspected

The review treated code as current behavior and documentation as intent, following the repository audit rule. Main surfaces included:

- `src/application/services/signal_engine.py` and `assess_signal_evidence_use_case.py`
- `src/application/services/risk_engine.py` and the configured domain risk gates
- `src/application/services/market_context_engine.py` and factor scorers
- accumulation screening, setup evidence, flow evidence, and TradeSetup composition
- swing backtest simulation, position building, exit handling, attribution, and statistics
- forward-label, candidate-observation, regime-observation, and tuning workflows
- `config/signal_engine.yaml`, `risk_engine.yaml`, `market_context_engine.yaml`, `swing_backtest.yaml`, `swing_setups.yaml`, and related configs
- relevant ADRs and signal-refactor design/audit documents
- `data/db/data.db`, inspected read-only

Local evidence snapshot:

| Data | Rows | Tickers | Date coverage |
|---|---:|---:|---|
| Daily candles | 75,339 | 312 | 2025-07-07 to 2026-07-11 |
| Daily broker flow | 498,044 | 303 | 2025-07-07 to 2026-07-10 |
| Candidate observations | 18,499 | 80 | 2026-01-02 to 2026-07-10 |
| Signal forward labels | 5,760 | 45 | 2026-01-02 to 2026-06-15 |
| Regime observations | 2 | market-level | 2026-07-06 to 2026-07-09 |

All 5,760 current forward labels are `SWING_10D`. They span 102 signal dates. This is useful for pipeline testing and early diagnostics, but observations are strongly correlated by date, ticker, sector, and overlapping 10-day horizons; 5,760 rows must not be interpreted as 5,760 independent trials.

## What is good

### 1. The engine boundaries are conceptually sound

Separating “is there positive opportunity evidence?” from “is this instrument or execution state disqualified?” is correct. Signal and risk are not opposites, and the code does not make a strong signal erase structural risk. TradeSetup is the explicit composition boundary.

The MCE is also upstream context rather than a second stock picker. That is directionally correct, especially for IDX, where currency, foreign participation, breadth, and commodity cycles can change the payoff of the same ticker setup.

### 2. Deterministic-first and local-first are genuine strengths

The system can be replayed, audited, and operated without AI. AI does not own scores, risk, persistence, or automatic tuning. That makes research errors traceable and avoids a non-reproducible narrative layer becoming the decision source.

### 3. The production signal path improved beyond the original six-factor score

The canonical path now aggregates structured evidence groups—setup quality and flow confirmation—rather than blindly neutral-filling every absent factor. Missing groups are excluded from the denominator and reduce confidence. This is much better than treating “unknown” as a fabricated score of 50.

The explicit evidence states, coverage, conviction, fingerprints, rationale, and decision constraints are excellent observability features. Keeping market/company-quality evidence diagnostic until promotion is proven is also good governance.

### 4. Point-in-time intent is visible throughout the implementation

Historical calls carry `as_of_date`; browser-backed fundamentals/shareholding paths explicitly avoid fetching live data during backtests; observation fingerprints preserve the inputs used; and corporate-action date semantics are documented. These are important anti-lookahead foundations.

### 5. Risk gates are explainable and operationally useful

Liquidity, free float, fundamental distress, distribution state, and optional technical gates are transparent. Configurable missing-data actions and structural versus execution blocks are useful distinctions. For a human screening workflow, “why excluded?” is often more valuable than a false probability.

### 6. Tuning has unusually good mutation guardrails

The tuning workflow is dry-run/human-review oriented, bounds parameter moves, validates patch paths, demands declared walk-forward provenance, separates diagnostic-ready from patch-eligible evidence, and rejects absent OOS summaries. These controls materially reduce accidental self-optimization.

### 7. Some IDX-specific mechanics are already modeled

The code knows the Rp50 floor and 100-share lot, uses transaction-value liquidity rather than share volume alone, recognizes free-float risk, includes foreign flow, and models conservative stop-first ordering when daily OHLC cannot resolve which barrier occurred first.

IDX officially uses 100-share round lots, price-dependent tick sizes, and auto-rejection bands. Those mechanics make nominal-price and liquidity-aware execution modeling essential, not cosmetic ([IDX trading mechanism](https://www.idx.co.id/id/produk-layanan/jam-dan-mekanisme-perdagangan/)).

## What is weak or unsafe to infer

### 1. The sample cannot validate the current complexity

One year cannot represent IDX history. It excludes the Asian Financial Crisis, GFC, taper tantrum, 2015 commodity/China shock, 2018 EM/USD stress, COVID crash/rebound, several election cycles, and multiple BI rate regimes. Even a much simpler model would be difficult to validate on the present window; the current number of thresholds and interactions makes false discovery more likely.

The two regime observations mean MCE accuracy is effectively unmeasured. Current MCE thresholds are expert priors, not empirically validated IDX regime probabilities.

### 2. A score is not currently a calibrated probability

`70` means a weighted evidence result and policy threshold; it does not mean a 70% chance of success. `confidence` is primarily evidence coverage/conviction, not statistically calibrated forecast confidence. UI and documentation should keep those concepts distinct.

The engine should report empirical outcome rates and uncertainty for score/setup/regime buckets only after adequate OOS samples. Until then, labels such as ENTER/WATCH are policy classifications, not forecast probabilities.

### 3. Equal-looking weights and hard thresholds lack marginal-value proof

The canonical 60/40 setup/flow split and regime thresholds are understandable priors, but the review found no decisive OOS ablation showing that 60/40 dominates simpler alternatives. The same applies to setup thresholds, flow cutoffs, MCE factor weights, VIX anchors, EIDO-relative-return cutoffs, USD/IDR cutoffs, and risk thresholds.

Foreign flow is economically plausible for Indonesia. Recent peer-reviewed evidence reports higher excess returns for firms experiencing foreign net purchases and highlights the relevance of foreign trading in a thin, information-asymmetric market ([Economic Modelling, 2024](https://doi.org/10.1016/j.econmod.2024.106730)). But this supports testing the factor, not assuming that the app’s exact lookbacks, transformations, or weights are optimal.

### 4. The backtest execution assumption is optimistic

Signals use the completed same-day candle and enter at that same close. Unless every required signal input is demonstrably available before the closing auction and the order can participate at the modeled close, this creates implementation shortfall or lookahead. A safer default is next-session open/VWAP with configurable slippage, while same-close becomes a labeled upper-bound scenario.

The current flat 20 bps cost does not respond to spread, tick size, participation rate, liquidity bucket, volatility, or limit states. Daily OHLC also cannot model queue position, partial fill, locked limit moves, gaps through stops, or call-auction execution. IDX research has documented unusual closing-period activity and closing-price manipulation concerns, even though pre-closing auctions reduced them ([Saputra & Prijadi](https://repository.umy.ac.id/handle/123456789/10529)).

### 5. Survivorship and universe bias are explicitly present

The backtest warns that it uses the supplied current universe rather than historical membership. This can exclude delisted, suspended, failed, renamed, and formerly eligible stocks while including later winners before they belonged to an index/universe. It is a material bias, especially when evaluating liquidity and quality gates.

### 6. Corporate actions and total-return semantics need stronger proof

The repository has corporate-action infrastructure, but the review did not find end-to-end proof that every historical candle/return, stop, target, volume, share count, free float, and fundamental field is consistently point-in-time adjusted. Splits, reverse splits, rights issues, special dividends, warrants, and ticker changes can corrupt labels and technical features if only prices are adjusted.

### 7. Risk gates mix different kinds of decisions

Fundamental distress, liquidity, and free float can be sensible suitability constraints, but a universal hard block may discard strategies whose payoff varies by universe. Piotroski cutoffs also have sector/accounting comparability issues, notably for banks and financials. Free-float percentages and market-cap floors should be tested by sector and liquidity regime rather than assumed universally optimal.

Missing risk data defaults mostly to `skip`. That preserves coverage but can make poorly covered stocks appear OPEN. For analysis, unknown should remain a first-class state; for actionable output, critical missing structural data should cap the decision or size unless explicitly overridden.

### 8. MCE contains plausible but partly redundant global proxies

VIX, EIDO, USD/IDR, IHSG trend, breadth, and foreign flow can all reflect the same global risk-off shock. A weighted sum may double-count that common latent factor. EIDO’s US trading hours, currency exposure, fees, holdings differences, and stale/lead-lag timing also require explicit timestamp alignment.

Commodity context is disabled despite its importance to major IDX sectors. A single market-wide commodity composite would still be too coarse: coal, CPO, nickel, gold, oil, and their USD/IDR interaction affect issuers differently. Sector-relative context is preferable.

### 9. Tuning validates artifacts more than statistical truth

The patch validator checks dates, minimum trade counts, profit factor, average return, drawdown regression, regime concentration, bounds, and provenance fields. That is good process safety, but a payload declaring `walk_forward_enforced: true` is not proof of leakage-safe experimental construction.

Thirty OOS trades are too few for stable optimization, particularly with overlapping positions and many parameters. Current evidence-strength logic uses sample count and bucket return spread without uncertainty, clustered dependence, multiple-testing correction, turnover, or benchmark-relative performance. A large spread can be noise.

### 10. The learning target is not yet decision-theoretic

Hit rate, average return, profit factor, and raw bucket spread are not enough. A useful prediction must specify horizon, entry timing, exit policy, benchmark, costs, and loss asymmetry. The local labels show why: both target and stop can occur within a 10-day path, and a close-return label can disagree with a tradable barrier outcome. Model selection should optimize net utility under the actual execution policy, not one convenient label.

## Highest-impact improvements, in order

### P0 — Build a credible point-in-time research dataset

Target at least 8–12 years initially, preferably 15+, across all historically eligible IDX equities and delisted names. Preserve daily membership for each configured universe/index and effective-dated:

- OHLCV, transaction value, suspension/FCA/board status, and limit-state flags;
- shares outstanding, free float, sector/industry, ticker changes, and listing/delisting;
- splits, rights issues, dividends, warrants, mergers, and other corporate actions;
- foreign buy/sell and broker-flow fields with their publication timestamps;
- fundamentals, estimates, analyst data, shareholding, and insider events with both period date and first-available timestamp;
- BI rate, USD/IDR, yield/credit proxies, commodity series, IHSG/index membership, breadth, and market-wide foreign flow.

Add automated point-in-time integrity tests: no record available after decision time, no future-restated fundamental used early, adjusted-return reconciliation, duplicate/gap checks, and delisted-name coverage.

**Why this is highest impact:** no scoring refinement can compensate for a narrow or biased truth set.

### P0 — Replace one split with purged, embargoed walk-forward evaluation

Use rolling or expanding training windows and untouched future test windows. Purge observations whose 10-day label overlaps the test boundary and embargo adjacent dates. Group evaluation by date and ticker; compute uncertainty with date-clustered bootstrap or block bootstrap.

Keep a final lockbox period that tuning never sees. Record every trial, not only winners, and control the number of explored configurations. Report confidence intervals and probability of outperforming the baseline, not only point estimates.

### P0 — Fix execution realism before judging alpha

Make next-session open or a feasible VWAP the default entry. Retain same-close only when signal timestamps prove auction eligibility. Model:

- price-band tick rounding and 100-share lots;
- bid/ask or conservative spread estimates;
- liquidity/volatility/participation-dependent slippage;
- broker fees and sell taxes as actually applicable;
- gaps through stops, unfilled orders, partial fills, suspensions, auto-rejection, and FCA states;
- capacity: order value as a fraction of median transaction value.

Run sensitivity scenarios (optimistic/base/stressed). Reject strategies whose edge disappears under modest cost changes.

### P1 — Define precise forecast targets and calibrate them

For each horizon, predict separate quantities rather than one overloaded score:

1. probability target is hit before stop;
2. probability of positive benchmark-relative return after costs;
3. expected net return;
4. expected adverse excursion/drawdown;
5. probability of fill at the modeled price.

Calibrate probabilities on OOS predictions using isotonic or logistic calibration only when sample size supports it. Track Brier score, log loss, calibration slope/intercept, reliability curves, ranking IC/AUC, and net portfolio utility. Keep the existing evidence score as an interpretable rank until calibration is proven.

### P1 — Establish hard baselines and ablations

Every engine version should compete against:

- do nothing/cash and IHSG;
- equal-weight eligible universe;
- simple 6–12 month momentum with liquidity filter;
- simple 20/50-day trend and volatility sizing;
- foreign-flow-only;
- setup-only;
- previous production config.

Remove or demote any factor that fails incremental OOS ablation after costs. Test interactions only after main effects survive. Simpler models should win ties.

### P1 — Separate alpha, risk, and execution more strictly

Retain three outputs:

- **Expected edge:** benchmark-relative, horizon-specific forecast;
- **Risk/suitability:** distress, liquidity, free float, event/data-quality uncertainty;
- **Execution feasibility:** spread, tick/limit state, capacity, timing, stop feasibility.

MCE should primarily change expected base rate, exposure budget, and risk—not silently transform an otherwise uncalibrated stock score. Unknown critical inputs should produce explicit `INSUFFICIENT_DATA`, not implicit OPEN.

### P1 — Rebuild MCE as validated state probabilities

Start with a small transparent model: IHSG trend/volatility, breadth, aggregate foreign flow, USD/IDR, and liquidity. Standardize each feature relative to its own rolling history rather than using timeless absolute thresholds. Output probabilities for risk-on/neutral/risk-off/stress plus transition uncertainty.

Test whether VIX and EIDO add incremental information after local features and correct timestamp alignment. Add sector-specific commodity context outside the market-wide regime. Do not promote MCE to sizing authority until several historical transitions validate it.

### P1 — Make IDX cross-sectional structure explicit

Score within liquidity, size, sector, and price/tick buckets or neutralize exposures. Otherwise the engine may merely rediscover “large liquid banks” or “commodity beta.” Track sector concentration, beta, size, liquidity, price level, and foreign-ownership exposure. Use sector-relative valuation and financial-sector-specific quality definitions.

### P2 — Upgrade the tuning decision rule

Require economically material OOS improvement and uncertainty bounds, not just minimum profit factor. Add:

- minimum independent date clusters and ticker breadth;
- deflated Sharpe or equivalent multiple-testing-aware evidence;
- bootstrap confidence intervals for delta versus production;
- turnover/capacity and stress-cost checks;
- monotonicity/stability across folds and adjacent parameter values;
- champion/challenger shadow deployment and rollback triggers;
- parameter freeze periods to prevent continuous chasing.

Tune families of related parameters jointly only with nested validation. Never use the final lockbox to choose thresholds.

### P2 — Improve portfolio construction

Ranking accuracy does not automatically produce a good portfolio. Replace first-available slot filling with explicit selection under constraints: expected edge, risk, correlation, sector cap, single-name cap, liquidity/capacity, and regime exposure budget. Size by volatility and stop distance with portfolio-level heat limits; stress correlated gaps because five nominal positions can be one commodity or bank bet.

## If starting over: independent engine design

I would build fewer engines and fewer thresholds at first, around one event-time research contract.

### 1. Point-in-time feature store and event ledger

Every datum would have `effective_at`, `known_at`, source, revision, and quality status. A decision at time *t* could access only records with `known_at <= t`. Corporate actions, universe membership, board/FCA/suspension state, and delistings would be first-class events.

### 2. Candidate eligibility engine

This would contain only hard, explainable constraints: tradability, data sufficiency, minimum capacity, suspension/FCA policy, price floor, event hazards, and strategy-specific suitability. It would return ELIGIBLE, INELIGIBLE, or UNKNOWN with reasons. Piotroski would normally be a feature or strategy-specific constraint, not a universal market-timing gate.

### 3. Horizon-specific alpha model

Begin with regularized logistic/linear models or monotonic gradient boosting—not an LLM and not a large hand score. Inputs would be a deliberately small set:

- medium-term momentum and short-term reversal;
- volatility-normalized trend/setup state;
- abnormal transaction value and liquidity change;
- foreign-flow surprise scaled by liquidity/free float;
- broker concentration/persistence features only after manipulation/leakage checks;
- sector-relative valuation/quality with reporting lags;
- market/sector regime and event flags.

Training would use nested purged walk-forward validation, sample weights for correlated observations, and probability calibration. The model card would list coverage, calibration, feature stability, failure regimes, capacity, and valid universe.

### 4. Risk forecast engine

This would estimate downside separately: gap/limit risk, expected adverse excursion, volatility, liquidity/capacity, accounting/event uncertainty, and correlation contribution. It would not collapse all risk into the first gate that fires, though hard disqualifiers would remain.

### 5. Decision and portfolio policy

Enter only when expected net utility is positive after base-rate, cost, and uncertainty penalties. The policy would choose among ENTER/WATCH/AVOID/INSUFFICIENT_DATA, allocate a portfolio risk budget, and log the counterfactual reason for every rejected candidate.

### 6. Execution simulator

Orders would use feasible next-session timing, tick/lot rounding, spread/slippage/capacity models, and explicit unfilled/limit/suspension states. Daily bars could support a conservative baseline; serious intraday strategies would require order-book or interval data.

### 7. Monitoring and learning

Each production prediction would be immutable. Monitoring would track calibration drift, feature drift, coverage, outcome by sector/liquidity/regime, execution shortfall, and champion/challenger deltas. Retraining or parameter promotion would be scheduled and evidence-gated, never triggered merely because recent returns disappointed.

## A practical 90-day sequence

1. **Weeks 1–3:** freeze new scoring knobs; document score-versus-probability semantics; add next-open/base/stressed execution scenarios; audit all point-in-time joins.
2. **Weeks 2–6:** ingest longer candle, membership, delisting, corporate-action, and flow history; build dataset integrity reports.
3. **Weeks 5–8:** implement purged rolling walk-forward evaluation, clustered uncertainty, baselines, and ablation reports.
4. **Weeks 7–10:** evaluate the current production engine unchanged; identify which evidence groups genuinely add OOS value by universe and regime.
5. **Weeks 9–12:** introduce one calibrated challenger model and shadow it; do not replace production until lockbox and stressed-cost criteria pass.

## Bottom line

Keep the architecture, guardrails, evidence objects, and human-gated promotion process. Do not keep assuming the numerical rules are correct merely because they are transparent and well tested in software.

The largest attainable accuracy improvement will come from **better historical truth, leakage-safe experimental design, calibrated targets, and realistic IDX execution**. Only after those foundations exist should the team decide whether foreign flow, broker accumulation, setup quality, company quality, or market regime deserves more or less authority.

