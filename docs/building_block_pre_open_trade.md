# Pre-Open Trade — Building Block

End-to-end **pre-open** workflow: live screen, NCP capture, opening track, post-open assess, paper journal, and open_30m learning — deterministic engine first. Operator path: [runbook_pre_open.md](runbook_pre_open.md).

---

## Command Family

| Command | Phase | Purpose |
|---------|-------|---------|
| `saham screen pre-open` | 1 | Screen IDX morning movers → entry range, stop, trend, accumulation, FVWAP |
| `saham research pre-open capture` | 1b | Persist NCP observation (decision authority) |
| `saham research pre-open track` | 1c | Persist opening track snapshots |
| `saham analyze pre-open` | 2 | Post-open ENTER/WAIT/SKIP from observation + track (read-only) |
| `saham trade log --type pre-open` | 3 | Paper journal from exact observation + opening snapshot IDs |
| `saham trade review pre-open` | 5 | Review pre-open paper journal buckets by decision + context |
| `saham research pre-open evaluate` | 5 | Cohort outcome evaluation (labels), not post-open assess |
| `saham trade outcome` | 4 | Record actual trade result (target/stop/manual) |
| `saham trade backtest-intraday` | 6 | Walk-forward backtest of the pre-open workflow |
| `saham fetch stockbit login` | — | Login & save Stockbit browser session (prerequisite for `saham screen pre-open`) |

---

## Full Architecture Diagram

```
┌───────────────────────────────────────────────────────────────────────────┐
│                         CLI LAYER (screen_pre_open / research_pre_open / analyze_pre_open / trade_pre_open)        │
│                                                                           │
│  screen/capture/track │ analyze pre-open │ log pre-open │ review pre-open │
│  outcome   │  backtest-intraday  │  research pre-open labels/evaluate             │
│                                                                           │
│  Display: _display_results, _display_pre_open_post_open_assessments, _display_review       │
│           _display_intraday_backtest, _display_raw_movers, etc.           │
│                                                                           │
│  Helpers: _build_intraday_run_guard, _load_config, _build_data_freshness  │
│           _verdict, _signal_col, pre_open helpers   │
│           _build_ai_researcher, _build_market_regime, _decimal_or_none    │
└────────────────────────────────┬──────────────────────────────────────────┘
                                 │
                                 ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                        APPLICATION LAYER                                  │
│                                                                           │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │                         USE CASES (4)                             │   │
│  │                                                                   │   │
│  │  PreOpenScreenUseCase       10-step pre-open analysis pipeline    │   │
│  │                               (fetch movers → context → entry →   │   │
│  │                                stop → trend → accum → AI)          │   │
│  │                                                                   │   │
│  │  PreOpenPostOpenGatesUseCase  8-gate deterministic confirmation    │   │
│  │                               (deterministic, no AI, no network)  │   │
│  │                                                                   │   │
│  │  IntradayBacktestUseCase     Walk-forward replay over history     │   │
│  │                               (uses PreOpenPostOpenGatesUseCase)   │   │
│  │                                                                   │   │
│  │  MarketRegimeUseCase         Breadth + flow regime (shared)      │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                                    │                                      │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │                       SERVICES                                   │   │
│  │                                                                   │   │
│  │  PreOpenPostOpenAssessmentJournal  Confirmation journal: log + review  │   │
│  │                                + record_outcome                    │   │
│  │  OpeningGradeUseCase          Pre-open prediction validation       │   │
│  │  ClaudeTickerResearcher      AI research per ticker               │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                                                                           │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │                     VALUE OBJECTS / DTOS                          │   │
│  │                                                                   │   │
│  │  PreOpenScreenConfig     YAML-loaded tuning parameters            │   │
│  │  PreOpenScreenResult     screened_date + candidates               │   │
│  │  ScreenerCandidate       ticker, iev, entry_range, stop, trend    │   │
│  │                          rsi, sma, accum_*, foreign_vwap, ai      │   │
│  │  PreOpenPostOpenAssessment    decision + reasons + prices              │   │
│  │  PreOpenPostOpenResult  ENTER/WATCH/SKIP groups             │   │
│  │  PreOpenPaperJournalEntry  + outcome fields               │   │
│  │  IntradayBacktestRequest/Response  portfolio metrics + trades    │   │
│  │  IntradayDataFreshness    candle/broker recency + warnings        │   │
│  └───────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────┬──────────────────────────────────────────┘
                                 │
                                 ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                          DOMAIN LAYER (Pure Python)                      │
│                                                                           │
│  ┌───────────────────┐  ┌───────────────────────┐  ┌─────────────────┐  │
│  │    Entities       │  │   Value Objects       │  │     Ports       │  │
│  │                   │  │                       │  │                 │  │
│  │  Candle           │  │  MoverData            │  │ BrowserDataProv │  │
│  │  BrokerSummary    │  │  OrderBookBid         │  │ MarketDataRepo  │  │
│  │                   │  │  MoverWithOrderBook   │  │ BrokerDataRepo  │  │
│  │                   │  │  ScreenerCandidate    │  │ BrowserDataProv │  │
│  │                   │  │  PreOpenPostOpenAssessment │  │ AIExplainer     │  │
│  │                   │  │  PreOpenPostOpenDecision(Enum)│  │                 │  │
│  │                   │  │  PreOpenPaperOutcome      │  │                 │  │
│  └───────────────────┘  └───────────────────────┘  └─────────────────┘  │
└────────────────────────────────┬──────────────────────────────────────────┘
                                 │
                                 ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                       INFRASTRUCTURE LAYER                                │
│                                                                           │
│  ┌───────────────────────┐  ┌──────────────────────┐  ┌───────────────┐  │
│  │  Browser Providers   │  │  Persistence        │  │  AI           │  │
│  │                      │  │                     │  │               │  │
│  │  PlaywrightStockbit  │  │  IntradayConfirmCSV │  │  ClaudeAPI    │  │
│  │  (1848 lines)        │  │  (confirm journal)  │  │  (research)   │  │
│  │  ManualBrowserData   │  │  (intraday-         │  │               │  │
│  │  (from JSON flags)   │  │   confirmations.csv)│  │               │  │
│  │                      │  │                     │  │               │  │
│  │  StockbitBrowserInst │  │  SQLiteMarketRepo   │  │               │  │
│  │  (step-by-step plan) │  │  SQLiteBrokerRepo   │  │               │  │
│  └───────────────────────┘  └────────────────────┘  └───────────────┘  │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## End-to-End Workflow

### Phase 1: Pre-Open Screening (08:45–09:00 WIB)

```
CLI: saham screen pre-open [--movers-json ...] [--order-books-json ...]
                              [--fast] [--with-ai] [--with-regime] [--headless/--no-headless]
 │
 ├─ _build_intraday_run_guard()
 │    ├── Checks weekday → REJECT weekends
 │    └── Checks time  → WARN if outside 08:45–09:00 WIB
 │
 ├─ DATA SOURCE SELECTION:
 │    ├── If --movers-json provided:
 │    │    └── ManualBrowserDataProvider.from_json(movers, order_books)
 │    │
 │    ├── Else if Playwright available + session exists:
 │    │    └── PlaywrightStockbitProvider.fetch_preopen_movers(iev_min)
 │    │         └── Opens headless Chromium → intercepts JWT → calls Exodus IEV API
 │    │
 │    └── Else:
 │         └── StockbitBrowserInstructionsProvider → raises BrowserInteractionRequired
 │              CLI catches → _print_browser_plan() → exit with instructions
 │
 ├─ PreOpenScreenUseCase.execute():
 │    │
 │    ├── fetch movers → filter by IEV → apply top-N cap
 │    │
 │    └── For each mover ticker (10 steps):
 │         │
 │         ├── 1. _assess_context()
 │         │    ├── candles = MarketRepo.get_candles(ticker)
 │         │    ├── ATR(14)  via registry (plugin)
 │         │    ├── RSI(14)  via registry
 │         │    ├── SMA(20)  via registry
 │         │    └── prev close/high/low
 │         │
 │         ├── 2. _compute_entry_range()
 │         │    ├── atr_pct = ATR / prev_close
 │         │    ├── effective_band = clamp(atr_pct * 3, min=1%, max=5%)
 │         │    ├── range_low  = prev_close * (1 - effective_band)
 │         │    └── range_high = prev_close * (1 + effective_band)
 │         │
 │         ├── 3. fetch_order_book_best_bid()  [skip if --fast]
 │         │    └── gap% = (bid - prev_close) / prev_close * 100
 │         │
 │         ├── 4. Entry price
 │         │    ├── If bid available: entry_price_from_bid(bid, ticks_above)
 │         │    └── Else: suggested_limit_from_close(prev_close, 0.5%)
 │         │
 │         ├── 5. ATR-based stop
 │         │    └── stop = entry - (atr_mult * ATR)
 │         │    └── floored at entry * (1 - max_stop_pct) from YAML
 │         │
 │         ├── 6. _classify_trend_v2()
 │         │    ├── gap% vs effective_band → direction
 │         │    ├── RSI > 75 → BEARISH override
 │         │    ├── RSI 30-65 + gap in band → BULLISH
 │         │    └── else → NEUTRAL
 │         │
 │         ├── 7. _assess_broker_signals()
 │         │    ├── accum_score = consistency(40pts) + streak(30pts, exp τ=7)
 │         │    ├── accum_tag = BACKED(≥50), DISTRIBUTING(ratio<0.3), UNCONFIRMED
 │         │    ├── accum_streak = consecutive foreign-buy days
 │         │    ├── Foreign VWAP via plugin indicator
 │         │    └── fvwap_discount% = (vwap - price) / price * 100
 │         │
 │         ├── 8. AI research [if --with-ai]
 │         │    └── ClaudeTickerResearcher.research(ticker)
 │         │
 │         └── 9. Build ScreenerCandidate → append to candidates[]
 │
 ├─ _build_data_freshness() → candle/broker recency warnings
 ├─ _build_market_regime()  → if --with-regime
 ├─ _display_results()
 │    ├── Verdict per ticker: PRIME / WATCH / SKIP / NO_DATA
 │    ├── Signal column: accum_tag + fvwap_discount% + prev high
 │    ├── AI summaries (if --with-ai)
 │    ├── Data freshness warnings
 │    ├── Market regime context
 │    └── Action summary with opening confirmation command template
 │
 └─ _write_sidecar() → journals/.last-session.json
```

### Phase 2: Confirm at Opening Auction (09:00+)

```
CLI: saham analyze pre-open --session YYYY-MM-DD
 │
 ├─ _load_confirmation_candidates()
 │    └── Read journals/.last-session.json → PreOpenPostOpenCandidate[]
 │
 ├─ PreOpenPostOpenGatesUseCase.execute():
 │    └── For each candidate with opening_price:
 │         │
 │         ├── 1. opening_price is None?     → SKIP_INSUFFICIENT_DATA
 │         ├── 2. open > entry_range_high?   → SKIP_GAP_UP
 │         ├── 3. open < entry_range_low?    → SKIP_GAP_DOWN
 │         ├── 4. trend == BEARISH?          → SKIP_BEARISH_CONTEXT
 │         ├── 5. accum_tag == DISTRIBUTING? → SKIP_BEARISH_CONTEXT
 │         ├── 6. stop_pct > max_stop?       → SKIP_RISK_TOO_WIDE
 │         ├── 7. trend == BULLISH?          → ENTER
 │         └── 8. else                       → WAIT
 │
 ├─ _display_pre_open_post_open_assessments()
 │    └── Groups: ENTER / WATCH / SKIP with price ranges
 │
 └─ _write_confirmation_sidecar() → journals/.last-confirmation.json
```

### Phase 3: Log Confirmation to Journal

```
CLI: saham trade log --type pre-open --observation-id … --opening-snapshot-id …
 │
 └─ PreOpenPaperJournalCsvStore.append(confirmations)
      └── Writes → journals/pre_open_paper.csv
```

### Phase 4: Record Outcome

```
CLI: saham trade outcome BBCA --entry 9050 --exit 9200 --result target
 │
 └─ PreOpenPaperJournalService.record_outcome()
      └── Matches row by (confirmed_at, ticker)
      └── Updates: actual_entry_price, actual_exit_price, outcome_result, outcome_r, notes
      └── Rewrites CSV row
```

### Phase 5: Review

```
CLI: saham research pre-open labels / evaluate
 │
 └─ OpeningGradeUseCase
      ├── Reads opening snapshots and tracking files
      └── Computes pre-open prediction accuracy

CLI: saham trade review pre-open
 │
 └─ PreOpenPaperJournalService.review()
      ├── Decision buckets: ENTER / WAIT / SKIP_* (count + outcome stats)
      └── Context buckets: gap (high/medium/low), RSI (high/neutral/low),
           stop (tight/normal/wide), accum, fvwap
```

### Phase 6: Backtest (Offline Replay)

```
CLI: saham trade backtest-intraday --universe lq45 --start 2026-01-01
 │
 └─ IntradayBacktestUseCase.execute()
      │
      └── For each trading date d (daily walk-forward):
           │
           ├── 1. Build _BacktestCandidate using data as of d-1
           │    ├── candles up to d-1 from SQLiteMarketRepo
           │    ├── broker flow up to d-1 from SQLiteBrokerRepo
           │    ├── ATR(14), RSI(14), SMA(20) via IndicatorRegistry
           │    ├── entry_range, stop, trend via same functions as pre-open
           │    └── accum_score + FVWAP from broker signals
           │
           ├── 2. Simulate opening confirmation using candle.open on date d
           │    └── Reuses PreOpenPostOpenGatesUseCase logic
           │
           ├── 3. Rank ENTER candidates by (accum_score desc, fvwap desc, stop asc)
           │    └── Cap at max_daily_positions
           │
           └── 4. Simulate same-day exit:
                ├── Check candle.low <= stop  → STOP_LOSS
                ├── Check candle.high >= target → TAKE_PROFIT
                └── Fallback → candle.close
                     (conservative: if both breached, assume stop first)
      │
      Output: IntradayBacktestResponse
        ├── initial/final equity, total return %, max DD %
        ├── win_rate %, profit factor, trade_count
        ├── avg r_multiple, avg hold bars
        ├── breakdowns by exit_reason, accum_tag, fvwap, RSI, ticker
        └── recent trades table
```

---

## Confirmation Decision Gates

The `PreOpenPostOpenGatesUseCase` applies 8 deterministic gates in order:

```
┌─────────────────────┬──────────────────┬──────────────────────────────┐
│ Gate                │ Pass Condition   │ Skip Reason                  │
├─────────────────────┼──────────────────┼──────────────────────────────┤
│ 1. Opening price    │ opening != None  │ SKIP_INSUFFICIENT_DATA       │
│ 2. Entry plan       │ entry_range !=   │ SKIP_INSUFFICIENT_DATA       │
│                       None             │                              │
│ 3. Gap up           │ open <= range_hi │ SKIP_GAP_UP                  │
│ 4. Gap down         │ open >= range_lo │ SKIP_GAP_DOWN                │
│ 5. Trend            │ trend != BEARISH │ SKIP_BEARISH_CONTEXT         │
│ 6. Accumulation     │ accum !=         │ SKIP_BEARISH_CONTEXT         │
│                       DISTRIBUTING     │                              │
│ 7. Stop distance    │ stop_pct <= max  │ SKIP_RISK_TOO_WIDE           │
│ 8. Final decision   │ trend == BULLISH │ ENTER, else WAIT             │
└─────────────────────┴──────────────────┴──────────────────────────────┘
```

---

## Data Sources (Phase 1 Pre-Open)

### Browser-Retrieved (via Stockbit Playwright)

| Data | Source | Auth |
|------|--------|------|
| IEV movers | Exodus API: `/order-trade/market-mover?mover_type=IEV_TOP_GAINER` | JWT from browser |
| Order book bids | Exodus API: `/company-price-feed/v2/orderbook/companies/{ticker}` | Same JWT |
| Top-5 with orderbooks | Combined in one browser session | Same |

### Database-Retrieved (from SQLite)

| Data | Repository | Populated By |
|------|-----------|-------------|
| Candles (OHLCV) | SQLiteMarketRepository | `saham fetch market` |
| Broker flow | SQLiteBrokerRepository | `saham fetch broker` / `saham fetch market` |

### Computed (via IndicatorRegistry)

| Indicator | Source | Purpose |
|-----------|--------|---------|
| ATR(14) | `plugins/indicators/atr.py` | Entry band, stop distance |
| RSI(14) | `domain/indicators/rsi.py` | Trend classification, headroom |
| SMA(20) | `domain/indicators/sma.py` | Trend baseline |
| Foreign VWAP | `plugins/indicators/foreign_vwap.py` | Discount vs current price |
| Accum score | `pre_open_screen.py` inline | Consistency + streak |

---

## Key Files

| File | Lines | Role |
|------|-------|------|
| `adapters/cli/trade_intraday_commands.py` | ~600 | Intraday trade CLI entry points (confirm, log, review, outcome) |
| `adapters/cli/intraday_workflow_commands.py` | ~1200 | Shared display and workflow helpers behind lifecycle command modules |
| `application/use_case/pre_open_screen.py` | 611 | 10-step pre-open analysis pipeline |
| `application/use_case/pre_open_post_open_gates_use_case.py` | 254 | 8-gate deterministic confirmation |
| `application/use_case/intraday_backtest.py` | 953 | Walk-forward backtest over history |
| `application/services/pre_open_paper_journal.py` | 305 | Confirmation journal log + review + outcome |
| `application/services/ai_research.py` | 88 | Claude-based AI ticker research |
| `infrastructure/browser/playwright_stockbit.py` + `playwright_stockbit_browser.py` | 2232 combined | Playwright browser automation + session management for Stockbit |
| `infrastructure/browser/stockbit_browser.py` | 191 | Manual + instruction-based browser providers |
| `infrastructure/persistence/pre_open_paper_journal_csv.py` | 229 | Confirmation journal CSV persistence |
| `domain/ports/browser_data_provider.py` | 90 | Browser data provider interface |
| `domain/value_objects/screener_result.py` | 184 | MoverData, ScreenerCandidate, etc. |
| `domain/value_objects/pre_open_post_open_assessment.py` | 149 | PreOpenPostOpenDecision, Confirmation, Outcome |
| `config/pre_open_screener.yaml` | ~60 | Tuning parameters (IEV, ATR, accum, FVWAP) |

---

## File Dependency Graph

```
screen_pre_open_commands.py / trade_intraday_commands.py (CLI entry points)
  │
  ├── intraday_workflow_commands.py (shared helpers, ~1200 lines)
  │     │
  │     ├── PreOpenScreenUseCase
  │     ├── BrowserDataProvider (port)
  │     │     ├── PlaywrightStockbitProvider  ← real browser automation
  │     │     ├── ManualBrowserDataProvider   ← JSON flags
  │     │     └── StockbitBrowserInstructionsProvider ← printed instructions
  │     ├── MarketDataRepository (port) → SQLiteMarketRepository
  │     ├── BrokerDataRepository  (port) → SQLiteBrokerRepository
  │     ├── IndicatorRegistry → sma.py, rsi.py, atr.py, foreign_vwap.py
  │     └── AIExplainer (port, optional) → ClaudeTickerResearcher
  │
  ├── PreOpenPostOpenGatesUseCase (no deps)
  │
  ├── PreOpenPaperJournalService
  │     ├── PreOpenPaperJournalStore (protocol) → PreOpenPaperJournalCsvStore
  │     │                                             (journals/pre_open_paper.csv)
  │     └── MarketDataRepository → SQLiteMarketRepository
  │
  ├── IntradayBacktestUseCase
  │     ├── MarketDataRepository
  │     ├── BrokerDataRepository
  │     ├── IndicatorRegistry
  │     └── PreOpenPostOpenGatesUseCase
  │
  └── MarketRegimeUseCase
```

---

## Pre-Open Screen Config (`config/pre_open_screener.yaml`)

All tuning parameters loaded into `PreOpenScreenConfig` at runtime:

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `iev_min` | — | Minimum IEV volume threshold |
| `capital` | 10_000_000 | Planned position capital |
| `stop_loss_pct` | 0.05 | Fixed stop loss (5%) |
| `tick_above` | 1 | Ticks above best bid for entry |
| `fast` | false | Skip order book fetches |
| `max_gap_pct` | 0.05 | Max allowed gap % |
| `atr_multiplier` | 1.0 | ATR multiplier for stop |
| `max_stop_pct` | 0.07 | Max stop as % of entry |
| `top_n` | — | Cap number of candidates |
| `accum_min_score` | 50 | Min accum score for BACKED tag |
| `accum_window_days` | 5 | Accumulation lookback |
| `fvwap_threshold_discount` | 0.02 | Min FVWAP discount for signal |
| `rsi_overbought` | 75 | RSI overbought gate |
| `rsi_oversold` | 30 | RSI oversold gate |

---

## Architectural Rules Specific to Intraday

1. **Time-bound execution** — Pre-open runs in a specific window (08:45–09:00 WIB). Run guard enforces weekday + time constraints.

2. **Three browser data paths** — The system degrades gracefully: autonomous Playwright → manual JSON → printed browser instructions. Each path is handled by a separate implementation of `BrowserDataProvider`.

3. **Post-open assess is fully deterministic** — `PreOpenPostOpenGatesUseCase` (via `AnalyzePreOpenUseCase`) has zero AI, zero network, zero randomness. All 8 gates are hardcoded rules over frozen observation + track snapshot data.

4. **AI is read-only auxiliary** — `--with-ai` appends research summaries but never influences entry/stop/trend decisions.

5. **Paper journal is CSV/JSONL** — Pre-open paper notebook uses CSV + `trades.jsonl`. Learning observations/tracks remain SQLite (ADR-049).

6. **Backtest reuses the same logic** — `IntradayBacktestUseCase` calls the same trend/accum/confirm functions as the live pipeline, ensuring backtest accuracy.

7. **Database identity for assess** — `analyze pre-open` binds exact `observation_id` + `opening_snapshot_id`. Confirmation sidecars are not assess authority.
