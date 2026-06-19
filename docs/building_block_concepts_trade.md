# Trading Concepts

This document explains the conceptual building blocks of the trading system — what each piece is, why it exists, how they connect, and where each command fits. Use this to build a mental model before diving into the code.

---

## Complete Map

```
                    TRADING BUILDING BLOCKS
         (the "what" — end-to-end user workflows)

  ┌─────────────────────────────────────────────────────────────────────┐
  │  DATA INGESTION                    single │ universe │ batch         │
  │  saham fetch market TICKER --days N                                      │
  │  saham fetch market --universe lq45 --days N                             │
  │  saham fetch broker TICKER --provider stockbit                     │
  │             ↓ stores into ↓                                        │
  │  ┌─────────────────────────────────────────────────────────┐       │
  │  │  SQLite: candles + broker_summaries + broker_flow_points│       │
  │  └─────────────────────────────────────────────────────────┘       │
  └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │  COMPUTE — raw indicator values from stored data                    │
  │                                                                     │
  │  saham indicator compute ATR BBCA          (any registered indicator)         │
  │  saham indicator compute SMA/EMA/RSI BBCA  (dedicated compute commands)         │
  │  saham indicator snapshot BBCA          (all three built-ins at once)       │
  │  saham indicator list           (show all available)               │
  │  saham indicator create          (AI-generate formula expression)   │
  │                                                                     │
  │          unified via IndicatorRegistry.compute()                    │
  │  ┌────────────────┬────────────────┬────────────────────────┐      │
  │  │ BUILT-IN       │ PLUGIN         │ FORMULA (DSL)          │      │
  │  │ SMA, EMA, RSI  │ ATR, MACD, BB, │ user AST expressions   │      │
  │  │ Domain funcs   │ Ichimoku,      │ e.g. "RSI(14)*2"      │      │
  │  │ No deps        │ Stoch,         │ persisted in config/   │      │
  │  │                │ ForeignFlow,   │                        │      │
  │  │                │ ForeignVWAP    │                        │      │
  │  │                │ Broker-aware   │                        │      │
  │  └────────────────┴────────────────┴────────────────────────┘      │
  └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │  STRATEGIES  — reusable if/then rule files (YAML)                   │
  │                                                                     │
  │  saham strategy init NAME       (scaffold from template)            │
  │  saham strategy create INTENT   (AI-generate from natural language) │
  │  saham strategy validate NAME   (syntax + indicator refs check)     │
  │  saham strategy list            (scan ./strategies/ dir)            │
  │                                                                     │
  │  Strategies available:                                              │
  │  foreign-accumulation │ ichimoku-trend │ rsi-momentum               │
  │                                                                     │
  │  Each YAML defines:                                                 │
  │   • which indicators to compute  (IndicatorDefinition)              │
  │   • entry/exit rules             (if X > Y → LOW_RISK)             │
  │   • signal mapping               (LOW_RISK → ENTER_LONG)           │
  └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │  RISK ASSESSMENT — evaluate rules against current state             │
  │                                                                     │
  │  saham analyze risk BBCA                      (built-in profiles)           │
  │  saham analyze risk BBCA --profile aggressive                               │
  │  saham analyze risk BBCA --rules-file custom.yaml (any strategy YAML)       │
  │  saham analyze risk BBCA --all               (all 3 profiles side-by-side)  │
  │  saham analyze risk BBCA --with-sentiment    (adds news AI context)         │
  │  saham analyze compare BBCA BBRI BMRI        (side-by-side across tickers)  │
  │                                                                     │
  │  Three built-in profiles (hardcoded RuleSets, no YAML needed):      │
  │  ┌──────────────┬────────────┬──────────────┐                      │
  │  │ conservative │  balanced  │  aggressive  │                      │
  │  │ RSI>75=OB    │  RSI>70=OB │  RSI>65=OB   │                      │
  │  │ RSI<25=OS    │  RSI<30=OS │  RSI<35=OS   │                      │
  │  └──────────────┴────────────┴──────────────┘                      │
  │                                                                     │
  │  Key insight: Risk and Strategy share the SAME rule schema.         │
  │  A strategy YAML works as --rules-file for risk, and a rules        │
  │  YAML works as --strategy for backtest. Same parser, same           │
  │  interpreter (YamlRuleInterpreter).                                 │
  └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │  BACKTEST — walk-forward replay of rules on historical data         │
  │                                                                     │
  │  saham strategy backtest BBCA --strategy foreign-accumulation                │
  │  saham strategy backtest BBRI --strategy ichimoku-trend                      │
  │  saham strategy backtest TLKM --strategy rsi-momentum                        │
  │                                                                     │
  │  Flow: load YAML → resolve indicators via registry →                │
  │  compute all indicator series → evaluate each candle date →         │
  │  BacktestEngine(signals, candles) → equity curve + trade log        │
  └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │  SENTIMENT — news analysis (separate data pipeline)                 │
  │                                                                     │
  │  saham analyze sentiment BBCA               (fetch + classify news)         │
  │  saham analyze sentiment BBCA --ai-classify (AI sentiment analysis)         │
  │  saham analyze audit              (compare AI vs keyword rules)   │
  │                                                                     │
  │  Outputs that strategies can reference:                             │
  │  SENTIMENT_SCORE, SENTIMENT_LABEL, SENTIMENT_CATALYST              │
  │  → registered as built-in indicators in the strategy schema         │
  └─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ├──────────────────────────────────┐
                                    │                                  │
                                    ▼                                  ▼
  ┌────────────────────────────────────────┐  ┌──────────────────────────┐
  │  END-TO-END WORKFLOWS (multi-step)      │  │  MANAGEMENT / UTILITY   │
  │                                         │  │                         │
  │  SWING (5-20 day horizon)               │  │  SESSION / PROVIDER     │
  │  saham analyze swing BBCA               │  │  saham fetch stockbit login   │
  │    → accumulation screen                │  │  saham fetch stockbit test    │
  │    → risk assessment                    │  │  saham fetch stockbit status  │
  │    → backtest (foreign-accum preset)    │  │                             │
  │    → regime context                     │  │                         │
  │    → position sizing (ATR)              │  │  UNIVERSE               │
  │    → sentiment                          │  │  saham fetch universe list    │
  │  saham trade backtest-swing (walk-forward)    │  │                         │
  │  saham analyze swing-compare (side-by-side)     │  │  REGIME                 │
  │  saham screen accum (accum CLI)         │  │  saham analyze regime           │
  │  saham trade size (position sizing)     │  │                         │
  │                                         │  │  CHART                  │
  │  INTRADAY (minutes horizon)             │  │  saham analyze chart            │
  │  saham screen pre-open                │  │                         │
  │    → 10-step pipeline (IEV → entry →    │  │  VERSION                │
  │      stop → trend → accum → AI)         │  │  saham version          │
  │    → borrows ATR, RSI, FVWAP from       │  │                         │
  │      registry (NOT strategies)          │  └──────────────────────────┘
  │  saham trade confirm            │
  │    → 8-gate deterministic decision      │
  │  saham trade log intraday / review            │
  │  saham trade outcome         │
  │  saham trade backtest-intraday                │
  │                                         │
  │  ACCUMULATION SCREEN                    │
  │  saham screen accum              │
  │    → proprietary 120-pt scoring         │
  │    → does NOT use registry or strategies│
  │    → direct SQLite queries              │
  │  saham screen accum --multi      │
  └─────────────────────────────────────────┘  └──────────────────────────┘
```

---

## What Each Block Is and Why It Exists

### 1. Data Ingestion

| Command | What it fetches | Default days |
|---------|----------------|--------------|
| `saham fetch market TICKER` | Candles + broker flow | 90 |
| `saham fetch market --universe lq45` | Same, for 45 stocks at once | 90 |
| `saham fetch broker TICKER` | Broker flow only (legacy) | 90 |

Stores into SQLite tables: `candles` (one row per date per ticker), `broker_summaries` (per date per ticker per source), `broker_flow_points` (time-series net flow). No pre-computed aggregates — everything computed at query time.

### 2. Compute — Indicators

Three kinds, unified through `IndicatorRegistry.compute(name, candles, period)`:

| Kind | Location | Examples | Why separate? |
|------|----------|----------|---------------|
| **Built-in** | `src/domain/indicators/` | SMA, EMA, RSI | Pure functions, zero deps, always available |
| **Plugin** | `plugins/indicators/*.py` | ATR, MACD, BB, Ichimoku, Stoch, Foreign Flow, Foreign VWAP | Can depend on broker data; filesystem-discovered (drop a `.py` file to add) |
| **Formula** | `config/formulas.yaml` | User expressions like `"RSI(14) * 2 - SMA(10)"` | Power users create custom indicators without writing Python |

The registry is the single entry point. Downstream code never calls domain functions directly — it always goes through `registry.compute()`.

### 3. Strategies

A strategy is a **YAML file** that defines:
- **Which indicators to compute** — name + type (built-in, plugin, or formula) + period
- **Rules** — conditions comparing indicators to values or each other
- **Signal mapping** — what action each outcome triggers (ENTER_LONG, HOLD, EXIT_LONG)

Why YAML instead of Python? Non-developer traders can write or modify strategies without coding. The `saham strategy create` command can also generate them from natural language via AI, and `saham strategy init` scaffolds from a template.

Strategies live in `./strategies/NAME/strategy.yaml` (16 packaged strategies). Current inventory includes:
- `foreign-accumulation` — foreign flow + RSI + trend rules
- `ichimoku-trend` — Ichimoku cloud crossover rules
- `rsi-momentum` — RSI oversold/overbought momentum
- `williams-r-bounce` — Williams %R oversold bounce
- `volume-spike` — Volume spike breakout
- `test-sentiment` — sentiment-based rules
- Plus 10 more (bb-breakout, ema-crossover, foreign-ichimoku, etc.)

### 4. Risk Assessment

Two modes:

| Mode | How | What it uses |
|------|-----|-------------|
| **Built-in profiles** | Hardcoded `RuleSet` classes | Only SMA, EMA, RSI |
| **Custom rules file** | Loads any strategy YAML via `--rules-file` | Any registry indicator |

The three built-in profiles differ only in RSI thresholds:

| Profile | Overbought | Oversold |
|---------|-----------|----------|
| conservative | RSI > 75 | RSI < 25 |
| balanced | RSI > 70 | RSI < 30 |
| aggressive | RSI > 65 | RSI < 35 |

**Key insight:** Risk and Strategy use the **exact same rule schema** (`src/application/rules/schema.py`). A strategy YAML can be passed as `--rules-file` for risk assessment, and a custom rules YAML can be passed as `--strategy` for backtesting. The same parser (`YamlConfigLoader`) and interpreter (`YamlRuleInterpreter`) handle both.

### 5. Backtest

Walk-forward replay: for each candle date, compute all indicators up to that date, evaluate strategy rules, generate trade signal. `BacktestEngine` processes the action stream and produces:
- Equity curve (initial → final, max drawdown)
- Win rate, profit factor, total return
- Trade log with entry/exit prices and dates

The registry is injected so the backtest can resolve ANY indicator a strategy references, including plugins and formulas.

### 6. Sentiment

Separate news pipeline. Fetches headlines from a news provider, classifies them (keyword rules or AI), and produces three values that the strategy schema treats as built-in indicators:
- `SENTIMENT_SCORE` (numeric, -1 to 1)
- `SENTIMENT_LABEL` (BEARISH, NEUTRAL, BULLISH)
- `SENTIMENT_CATALYST` (earnings, macro, etc.)

These can be referenced in strategy YAML rules just like SMA or RSI.

### 7. End-to-End Workflows

These are the three multi-step workflows that combine multiple building blocks. Critically, **each has its own independent decision logic** — they are NOT powered by the strategy engine.

#### Swing (`saham analyze swing`)

Composite 7-section view that calls:
1. **Accumulation screen** — direct SQLite + inline scoring
2. **Risk assessment** — built-in profiles or custom rules
3. **Backtest** — against `foreign-accumulation` strategy preset
4. **Regime** — market breadth analysis
5. **Position sizing** — ATR-based capital allocation
6. **Flow detail** — per-broker breakdown (if Stockbit)
7. **Sentiment** — news context

Does NOT use strategies for its main decision. The backtest panel uses the strategy, but only as a historical reference view.

#### Intraday (`saham screen pre-open` → opening confirmation → log → outcome → review)

Pre-open pipeline has its own **10-step screening** (IEV → context → entry → stop → trend → accum → AI) and **8-gate deterministic confirmation** (trend, gap, accum, stop distance). It borrows only ATR, RSI, and FVWAP from the indicator registry. Does NOT use strategies at all.

Config comes from `config/pre_open_screener.yaml` (not a strategy YAML).

#### Accumulation Screen (`saham screen accum`)

Proprietary 120-point scoring system:
| Component | Max pts | What it measures |
|-----------|---------|-----------------|
| Consistency | 40 | % of days with net foreign buying |
| Streak | 30 | Consecutive buy days (exponential curve) |
| VWAP discount | 20 | How underwater foreigners are |
| RSI headroom | 10 | RSI near 40 (ideal entry zone) |
| Flow ratio | 10 | Foreign % of daily turnover |
| BB squeeze | 10 | Volatility compression percentile |
| Institutional | 5 | Known institutional broker present |

Does NOT use registry or strategies. Direct SQLite queries + inline computation.

---

## How They All Connect

```
SQLite DB
   │
   ├──> IndicatorRegistry
   │      ├── built-in (domain/indicators/)
   │      ├── plugin   (plugins/indicators/*.py)
   │      └── formula  (config/formulas.yaml)
   │
   ├──> StrategyLoader ──> YamlConfigLoader ──> YamlRuleInterpreter
   │      └── ./strategies/NAME/strategy.yaml
   │
   ├──> AssessRiskUseCase
   │      ├── built-in profiles (conservative/balanced/aggressive)
   │      └── custom rules (any strategy YAML via --rules-file)
   │
   ├──> BacktestUseCase
   │      └── any strategy YAML → indicator series → evaluate → engine
   │
   ├──> FetchSentimentUseCase → news provider → classified output
   │
   ├──> PreOpenScreenUseCase  (intraday, borrows ATR/RSI/FVWAP only)
   │
   ├──> AccumulationScreenUseCase  (proprietary scoring, no registry)
   │
   └──> swing analyze (composite: accum + risk + backtest + regime + sizing)
```

The three end-to-end workflows share the **SQLite database** and **indicator registry** but have completely independent decision logic. This is intentional — each has different timeframes and signal types:

| Workflow | Timeframe | Decision Logic | Uses Strategies? |
|----------|-----------|---------------|-----------------|
| Swing | 5-20 days | Accumulation + risk + backtest (reference) | Backtest panel only |
| Intraday | Minutes | 10-step screen + 8-gate confirmation | No |
| Accum screen | Trend | 120-point scoring | No |

The **strategy + backtest** system exists primarily for **custom rule development and historical validation**, not for powering the live trading workflows. Live workflows have hardcoded pipelines optimized for their specific timeframe.
