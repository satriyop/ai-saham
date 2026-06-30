# Swing Trade — Building Block

The swing trade feature is a **unified composite workflow** that combines accumulation screening, risk confirmation, position sizing, historical backtesting, market regime context, and news sentiment into a single analysis pipeline.

---

## Command Family

| Command | Purpose | Delegates To |
|---------|---------|-------------|
| `saham analyze swing TICKER` | Unified multi-section composite view | Internal orchestration |
| `saham trade size TICKER` | ATR-based position sizing calculator | `PositionSizer` service |
| `saham trade backtest-swing` | Portfolio walk-forward backtest | `SwingBacktestUseCase` |
| `saham analyze swing-compare` | Compare variants across regimes | `SwingBacktestUseCase` × N variants |
| `saham screen accum` | Accumulation screener (find candidates) | `AccumulationScreenUseCase` |
| `saham analyze accum-audit` | Audit accumulation broker data | `AccumulationAuditUseCase` |
| `saham trade log swing` | Log a candidate to journal | `AccumulationJournal` service |
| `saham trade review swing` | Review journal performance | `AccumulationJournal` + SQLite |
| `saham analyze regime` | Market regime context (standalone) | `MarketRegimeUseCase` |

---

## Full Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          CLI LAYER (lifecycle routers + swing impl)      │
│                                                                          │
│  analyze swing       trade size       trade backtest-swing                  │
│  analyze swing-compare                                                       │
│  screen accum       ───► accumulation_run                                   │
│  analyze accum-audit ───► accumulation_audit                                 │
│  trade log swing    ───► accumulation_log                                   │
│  trade review swing ───► accumulation_review                                │
│                                                                          │
│  analyze regime                                                              │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                       APPLICATION LAYER                                 │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────┐          │
│  │                     USE CASES (6)                        │          │
│  │                                                          │          │
│  │  SwingBacktestUseCase    Walk-forward portfolio sim      │          │
│  │  AccumulationScreenUC    7-dimension accumulation score  │          │
│  │  AccumulationAuditUC     Accumulation pattern audit      │          │
│  │  AssessRiskUseCase       Profile-based risk confirmation │          │
│  │  FetchSentimentUseCase   News + keyword/AI classifier   │          │
│  │  MarketRegimeUseCase     Benchmark breadth + flow regime │          │
│  │  BacktestUseCase         Single-ticker historical sim    │          │
│  └──────────────────────────────────────────────────────────┘          │
│                                    │                                    │
│  ┌──────────────────────────────────────────────────────────┐          │
│  │                    SERVICES (5)                          │          │
│  │                                                          │          │
│  │  PositionSizer         ATR-based lot sizing (pure math)  │          │
│  │  StrategyLoader        Strategy YAML -> rules file       │          │
│  │  UniverseLoader        Universe name -> ticker list      │          │
│  │  IndicatorRegistry     Central indicator lookup          │          │
│  │  AccumulationJournal   CSV candidate journal             │          │
│  └──────────────────────────────────────────────────────────┘          │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────┐          │
│  │                    VALUE OBJECTS / DTOS                  │          │
│  │                                                          │          │
│  │  AccumulationCandidate   Score, streak, vwap, RSI, BB   │          │
│  │  FlowDetail              Foreign flow stats over window  │          │
│  │  DataFreshness           Cached data date ranges        │          │
│  │  SetupEvaluation        MATCH/PARTIAL/NO_MATCH fit│          │
│  │  SwingBacktestResponse   Portfolio-level metrics        │          │
│  │  MarketRegimeResponse    Breadth + flow regime snapshot │          │
│  └──────────────────────────────────────────────────────────┘          │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         DOMAIN LAYER (Pure Python)                      │
│                                                                          │
│  ┌────────────────────┐  ┌─────────────────────┐  ┌────────────────┐   │
│  │    Entities        │  │   Value Objects     │  │    Ports       │   │
│  │                    │  │                     │  │                │   │
│  │  Candle            │  │  BacktestResult     │  │ MarketDataRepo │   │
│  │  BrokerSummary     │  │  RiskAssessment     │  │ BrokerDataRepo │   │
│  │  BacktestTrade     │  │  Sentiment          │  │                │   │
│  │                    │  │  AccJournalEntry    │  │                │   │
│  └────────────────────┘  └─────────────────────┘  └────────────────┘   │
│                                                                          │
│  ┌────────────────────┐                                                  │
│  │   Domain Service   │                                                  │
│  │                    │                                                  │
│  │  BacktestEngine    │  Pure simulation logic                          │
│  │                    │  (all-in-long, drawdown, P&L)                   │
│  └────────────────────┘                                                  │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                       INFRASTRUCTURE LAYER                              │
│                                                                          │
│  Persistence:    SQLiteMarketRepository (candles)                       │
│                  SQLiteBrokerRepository  (broker flow)                   │
│                  AccumulationJournalCsv  (candidate log)                 │
│                                                                          │
│  Sentiment:      SentimentFactory -> CompositeNewsProvider              │
│                                    -> KeywordClassifier / AIClassifier  │
│                                                                          │
│  Indicators:     IndicatorLoader -> Plugin indicators (ATR, FOREIGN_FLOW,│
│                                     Bollinger Bands, etc.)              │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## `swing analyze` — Internal Flow (Core Verdict + Evidence)

The single-ticker `saham analyze swing BBCA` command centers the core deterministic verdict on `SignalEngine + RiskEngine -> TradeSetup`. Market context, setup gates, strategy backtest, sentiment, and detailed broker attribution are optional evidence modules for human inspection and learning-loop attribution; they do not independently alter `TradeSetup.action`.

```
┌─────────────┐
│   ENTRY     │  saham analyze swing BBCA --capital 10000000
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1: Auto-refresh (optional, default: on)                  │
│  _auto_refresh_swing_data()                                     │
│    ├── _fetch_candles (Yahoo/IDX, 365d)                        │
│    └── _fetch_broker (Stockbit/IDX, 90d)                       │
│  Output: refresh_actions tuple ("candles=+5d", "broker=+3d")   │
└─────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 2: Data freshness check                                   │
│  _build_data_freshness()                                        │
│    ├── market_repo.get_date_range(ticker)                       │
│    └── broker_repo.get_date_range(ticker)                       │
│  Output: DataFreshness(candle_end, broker_end, warnings)       │
└─────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 3: Accumulation evidence for SignalEngine context        │
│  AccumulationScreenUseCase                                     │
│    ├── BrokerRepository.get_broker_summaries(window)           │
│    ├── Compute score (net_buy_ratio + streak + VWAP +          │
│    │                    RSI + flow_ratio + BB_squeeze)         │
│    └── MarketRepository for RSI + price                        │
│  Output: AccumulationCandidate(score, streak, vwap_discount,   │
│           avg_flow_ratio, bb_width_pctile, trend)              │
└─────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 4: Setup evaluation (named setup gates)                  │
│  EvaluateSwingSetupUseCase                                     │
│    ├── foreign-bounce                                          │
│    ├── coiled-spring                                           │
│    ├── smart-money-confirmed                                   │
│    └── pullback-continuation                                   │
│  Output: SetupEvaluation(MATCH/PARTIAL/NO_MATCH, failed_reasons)   │
└─────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 5: Risk confirmation                                     │
│  AssessRiskUseCase                                             │
│    ├── MarketRepository.get_candles                             │
│    ├── IndicatorRegistry.compute(SMA, EMA, RSI)                │
│    └── RuleEngine (conservative/balanced/aggressive)           │
│  Output: RiskAssessment(level, confidence, rationale)          │
└─────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 6: ATR computation                                       │
│  registry.compute("ATR", candles, 14)                          │
│    └── Plugin: plugins/indicators/atr.py                       │
│  Output: atr_value (latest ATR)                                │
└─────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 7: Position sizing                                       │
│  IF setup_eval.passed:                                        │
│    compute_percent_position_size(capital, 5% stop, 5% TP)     │
│  ELSE IF capital + atr_value:                                  │
│    compute_position_size(entry, atr, capital, risk%, mult)    │
│  Output: SizingResult(lots, entry, stop, target, risk_amount) │
└─────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 8: Strategy evidence (optional)                          │
│  IF --strategy NAME:                                           │
│    StrategyLoader -> resolve(NAME)                             │
│    BacktestUseCase(ticker, rules, capital)                     │
│  Output: BacktestResult(win_rate, profit_factor, max_dd,      │
│           trade_count)                                          │
└─────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 9: Sentiment evidence (optional)                         │
│  IF --with-sentiment:                                          │
│    SentimentFactory -> CompositeNewsProvider                   │
│                     -> KeywordClassifier                       │
│    FetchSentimentUseCase(ticker, 3d, 20 headlines)            │
│  Output: SentimentSummary(call, total, pos/neg/neu, conf%)    │
└─────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 10: Market regime (opt-in via --with-market-context)     │
│  MarketRegimeUseCase                                           │
│    ├── Benchmark close + SMA20 + SMA50                         │
│    ├── Breadth: % stocks above SMA20 + 5d change               │
│    └── Foreign flow breadth                                    │
│  Output: MarketRegimeResponse(label, score/7, benchmark_metrics│
│           breadth, foreign_flow_pct)                            │
└─────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 11: Output                                               │
│  IF --format json: JSON dump of all outputs                    │
│  IF --format table (default):                                  │
│    print_swing_rich_overview()  [always shows core panels]     │
│    ├── Verdict panel (Action, Price, Signal, Risk, Setup,      │
│    │                  Market — condensed in one compact table) │
│    ├── Signal panel (score, factor breakdown, entry quality)   │
│    ├── Risk panel (Gates: OPEN/BLOCKED, Technical: on/off)    │
│    ├── Market Context panel (regime label, signal/risk impact) │
│    ├── Plan panel (action text, sizing summary)                │
│    └── Data panel (candle/broker freshness, quality, notation) │
│                                                                  │
│  print_swing_output()  [opt-in evidence panels below core]     │
│    ├── Market Context Preview (if preview data available)      │
│    ├── SETUP EVIDENCE (MATCH/PARTIAL/NO_MATCH + gate details) │
│    ├── ENGINE DETAIL panels (signal/risk/market w/ --explain) │
│    ├── FLOW / BROKER DETAIL (w/ --with-flow-detail)            │
│    ├── STRATEGY EVIDENCE (win rate, PF, max DD w/ --strategy) │
│    └── SENTIMENT EVIDENCE (call, distribution, w/ --sentiment)│
│                                                                  │
│  RiskEngine displays OPEN (no gate) or BLOCKED (gate: Name)    │
│  instead of legacy LOW_RISK/MODERATE/HIGH_RISK labels.         │
│  Use --with-technical-gate to enable SMA/EMA/RSI gate in Risk.│
└─────────────────────────────────────────────────────────────────┘
```

---

## `swing backtest` — Portfolio Walk-Forward

```
┌─────────────┐
│   ENTRY     │  saham trade backtest-swing --universe idx30 --capital 100000000
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  UniverseLoader -> resolve_tickers(universe="idx30")           │
└─────────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  SwingBacktestUseCase.execute(request)                         │
│                                                                 │
│  For each replay date (daily from start to end):               │
│    ├── Check date vs allowed trading days                      │
│    ├── IF skipping: no_trade_today += 1                        │
│    ├── IF not --with-regime OR regime allows entry:            │
│    │     Run accumulation screener on ALL tickers              │
│    │     Sort candidates by score                              │
│    │     IF score >= threshold:                                │
│    │       Enter position at next-day close                    │
│    │       Set TP (take_profit%), SL (stop_loss%),             │
│    │         max_hold (max_hold_days)                          │
│    │     ELSE: skip_candidate_no_score += 1                    │
│    ├── ELSE: skip_by_regime += 1                               │
│    └── Manage open positions (check TP/SL/max-hold daily)      │
│                                                                 │
│  Output: SwingBacktestResponse                                 │
│    ├── total_return_pct, max_drawdown_pct                      │
│    ├── win_rate_pct, profit_factor                             │
│    ├── trade_count, avg_trade_return_pct                       │
│    ├── exposure_pct, skipped_breakdown                         │
│    ├── regime_stats (performance by entry regime)              │
│    ├── equity_curve (dates + equity + drawdown)                │
│    └── warnings (edge cases, data gaps)                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## `swing compare` — Regime Variant Comparison

```
┌─────────────┐
│   ENTRY     │  saham analyze swing-compare --universe idx30 --variants baseline,sideways_only
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  For each variant (baseline, sideways_only, weak_plus):         │
│    ├── Determine allowed regimes for this variant               │
│    ├── Run SwingBacktestUseCase with that regime filter         │
│    └── Collect response                                        │
│                                                                 │
│  Output: Side-by-side table:                                    │
│    VARIANT | REGIMES | TRADES | RETURN | MAX_DD | WIN | PF     │
│    ────────|---------|--------|--------|--------|-----|----     │
│    baseline| all     |   42   | +12.3% | -8.1%  | 57% | 1.8    │
│    sidew...| SIDE... |   28   | +15.1% | -5.2%  | 64% | 2.3    │
│    weak... | WEAK... |   17   | +7.8%  | -6.7%  | 52% | 1.4    │
└─────────────────────────────────────────────────────────────────┘
```

---

## `swing size` — ATR Position Sizing

```
┌─────────────┐
│   ENTRY     │  saham trade size BBCA --capital 10000000 --risk-pct 1
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│  1. Fetch candles from SQLiteMarketRepository                   │
│  2. Compute ATR(14) via registry.compute("ATR", candles)       │
│  3. compute_position_size()                                    │
│       entry * ATR * capital * risk_pct                          │
│       ─────────────────────────────────────                     │
│     ├── stop_price   = entry - (atr * multiplier)              │
│     ├── target_price = entry + (stop_distance * rr)            │
│     ├── risk_amount  = capital * risk_pct                      │
│     ├── raw_shares   = risk_amount / stop_distance             │
│     ├── lots         = floor(raw_shares / 100)                 │
│     ├── shares       = lots * 100                              │
│     └── position_cost = shares * entry_price                   │
│                                                                 │
│  Output: SizingResult(lots, stop, target, risk, reward)        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Scoring Components (Accumulation Screener)

The `AccumulationScreenUseCase` scores each stock on 7 dimensions (total 0–120):

| Component | Max Pts | Logic | Threshold |
|-----------|---------|-------|-----------|
| Net buy ratio (consistency) | 40 | `net_buy_days / total_days * 40` | Higher = more consistent |
| Consecutive streak | 30 | `30 * (1 - e^(-streak/7))` | 7d ≈ 63%, 14d ≈ 86% |
| VWAP discount | 20 | `min(vwap_disc%, 10) / 10 * 20` | ≥3% = good entry |
| RSI headroom | 10 | Tent function peaking at RSI=40 | 25–75 range |
| Avg foreign flow ratio | 10 | `min(ratio, 20) / 20 * 10` | ≥5% of turnover |
| Bollinger Band squeeze | 10 | 10 pts if BB width ≤ 20th pctile | Coiled spring setup |
| Institutional broker present | 5 | Bonus if Stockbit shows major broker | Bonus |

---

## Setup Gates (foreign-bounce)

The `foreign-bounce` setup checks deterministic pattern fit on accumulation candidates:

```
┌──────────┬──────────────┬───────────────┬──────────────────────┐
│ Gate     │ Pass Cond.   │ Why           │ Common Failure       │
├──────────┼──────────────┼───────────────┼──────────────────────┤
│ score    │ >= 70        │ Strong signal │ Stock not accumulated│
│ vwap_disc│ >= 3%        │ Discount entry│ Fairly priced        │
│ trend    │ == "SIDE"    │ No trend bias │ Trending up/down     │
│ flow_ratio│ >= 5%       │ Significant   │ Low foreign activity │
│ RSI present│ not None   │ Can assess    │ No data              │
│ RSI      │ <= 60        │ Room to run   │ Overbought           │
└──────────┴──────────────┴───────────────┴──────────────────────┘

Classification:
  ALL pass  → ENTER
  score>=70 or ≤2 fails → WATCH
  otherwise → AVOID
```

---

## Key Files

| File | Lines | Role |
|------|-------|------|
| `adapters/cli/analyze_swing_commands.py` + `adapters/cli/trade_swing_commands.py` | ~2000 combined | Analyze (screening + signals) and Trade (backtest + sizing + journal) sub-groups |
| `application/use_case/swing_backtest_use_case.py` | 664 | Walk-forward portfolio simulation |
| `application/use_case/accumulation_screen_use_case.py` | 434 | 7-dimension accumulation scoring |
| `application/use_case/assess_risk_use_case.py` | ~150 | Risk assessment |
| `application/use_case/build_market_context_use_case.py` | 313 | Breadth + flow market context |
| `application/use_case/fetch_sentiment_use_case.py` | ~120 | News sentiment fetching |
| `application/services/position_sizer.py` | 188 | ATR-based lot sizing (pure math) |
| `application/services/strategy_loader.py` | ~200 | Strategy YAML resolution |
| `application/services/universe_loader.py` | ~100 | Ticker list resolution |
| `strategies/foreign-accumulation/strategy.yaml` | 118 | Default strategy definition |
| `plugins/indicators/foreign_flow.py` | 120 | Foreign buy ratio/streak computation |
| `plugins/indicators/atr.py` | 50 | ATR computation |
| `plugins/indicators/bollinger_bands.py` | 50 | BB width for squeeze detection |

---

## Data Dependencies

```
analyze swing BBCA needs in SQLite:
  ├── candles.BBCA       (from: saham fetch market)
  └── broker_flow.BBCA   (from: saham fetch broker BBCA / saham fetch market)

trade backtest-swing --universe idx30 needs:
  ├── candles.*           (all universe tickers)
  └── broker_flow.*       (all universe tickers)

screen accum     needs: broker_flow.*
trade size       needs: candles.TICKER (for ATR)
analyze regime  needs: candles.* + broker_flow.* (for breadth)
```

---

## Architectural Rules Specific to Swing

1. **Swing is not a single use case** — it's an **adapter-level orchestration** that calls 6+ use cases sequentially.
2. **Every pipeline is optional and fault-tolerant** — each step is wrapped in `try/except`, so missing data doesn't crash the whole command.
3. **Regime awareness is a filter, not a signal** — market regime only blocks entries, it doesn't generate them.
4. **Setup logic is in the application layer, calibration is in config** — setup gates load from `config/swing_setups.yaml`, TP/SL targets from `config/swing_targets.yaml`, and broker-quality inputs from `config/accumulation_screener.yaml`.
5. **Position sizer is pure math** — no I/O, no ports. Works purely from Decimal inputs.
6. **Auto-refresh is the default** — every `analyze swing` refetches candles + broker data before analyzing, unless `--no-refresh`.
