 Phase 0 — Ticker Data Dashboard (read-only, uses cache)

 saham view BBCA                  # 12 panels: notation, valuation, consensus, ownership, bandar,
                                  #   corporate actions, insider activity, seasonality, IEV,
                                  #   sentiment, company profile, recent candles
 saham view ticker BBCA           # Explicit syntax (same output)

 ---
 Phase 1 — Get Market Data (do this first, once)

 saham fetch market BBCA --days 730        # Downloads 2yr OHLCV + broker flow, cached to data.db
 saham fetch broker BBCA --days 90  # Foreign flow via IDX public API (no auth)
 saham fetch broker BBCA --provider stockbit --days 90  # Richer per-broker detail (session needed)

 ---
 Phase 2 — Technical Indicators

 # Composite view (all at once)
 saham indicator snapshot BBCA --sma 20 --ema 20 --rsi 14

 # Individual indicators
 saham indicator compute SMA BBCA --period 20
 saham indicator compute SMA BBCA --period 50         # Trend direction (above/below SMA50)
 saham indicator compute SMA BBCA --period 200        # Long-term trend
 saham indicator compute EMA BBCA --period 20
 saham indicator compute RSI BBCA --period 14

 # Plugin indicators
 saham indicator compute ATR BBCA --period 14  # Volatility / stop sizing
 saham indicator compute FOREIGN_FLOW BBCA    # 3-day net foreign flow

 # Custom formula indicator
 saham indicator create "RSI smoothed with EMA of period 3" --name SMOOTH_RSI         # Uses deepseek (default)
 saham indicator create "MACD line" --name MACD --provider claude                       # Or specify another provider
 saham indicator compute SMOOTH_RSI BBCA

 ---
 Phase 3 — Risk Assessment

 # Gate-based risk assessment
 saham analyze risk BBCA

 # Custom rules (your own YAML logic)
 saham analyze risk BBCA --rules-file config/custom_rules.yaml.example

 # With AI explanation (default provider: deepseek)
 saham analyze risk BBCA --explain                            # Uses deepseek (default)
 saham analyze risk BBCA --explain --provider claude           # Or specify another provider

 # With news sentiment appended
 saham analyze risk BBCA --with-sentiment

 ---
 Phase 4 — Broker & Foreign Flow Analysis

 saham view broker flow BBCA --days 30    # Daily foreign net flow table
 saham view broker top BBCA               # Top 5 buyers + sellers today
 saham view broker top BBCA --date 2024-01-15  # Historical snapshot

 ---
 Phase 5 — Sentiment

 saham analyze sentiment BBCA                          # Keyword classifier (offline-capable after fetch)
 saham analyze sentiment BBCA --days 7 --max 30        # Wider window
 saham analyze sentiment BBCA --ai-classify                          # Uses deepseek (default)
 saham analyze sentiment BBCA --ai-classify --provider claude         # Or specify another provider

 ---
 Phase 6 — Backtest with a Strategy

 saham strategy backtest BBCA --strategy rsi-momentum --capital 100000000
 saham strategy backtest BBCA --strategy foreign-accumulation
 saham strategy backtest BBCA --strategy rsi-momentum --start 2023-01-01 --end 2024-01-01 --verbose

 ---
 Phase 7 — Intraday Pre-Open Screening (if BBCA appears in morning movers)

 # Step 1: Run screener with browser automation
 saham screen pre-open --with-ai

 # Step 2: Pass JSON data directly (skip browser)
 saham screen pre-open \
   --movers-json '[{"ticker":"BBCA","iev":180000}]' \
   --order-books-json '{"BBCA":{"price":8875,"volume":300000}}'

 # Step 3: After opening auction, confirm entry decision
 saham trade confirm \
   --opening-json '{"BBCA":{"open":8875,"high":8925,"low":8850,"close":8900}}'

 ---
 Phase 8 — Strategy / Indicator Authoring

 saham strategy list                            # See available strategies
 saham strategy validate rsi-momentum           # Check YAML correctness
 saham strategy create "Buy on RSI dip below 30 when above SMA50"            # Uses deepseek (default)
 saham strategy create "EMA crossover with 9 and 21" --provider claude          # Or specify another provider
 saham indicator list                          # See all indicators available

 ---
 Phase 9 — Swing Trade Analysis

 # Full composite view (accumulation + risk + sizing + backtest + sentiment)
 saham analyze swing BBCA --capital 100000000

 # Position sizing based on ATR
 saham trade size BBCA --capital 100000000 --risk-pct 1 --entry 8875

 # Walk-forward backtest across universe
 saham trade backtest-swing --universe idx30 --capital 100000000 --with-regime

 # Compare regime variants side-by-side
 saham analyze swing-compare --universe idx30 --variants bull,neutral,bear

 # Accumulation screener (same as screen accumulation)
 saham screen accum --universe idx30 --window 5

 ---
 Phase 10 — Market Regime Context

 # Current regime across universe
 saham analyze regime --universe idx30

 # Regime as of a specific date
 saham analyze regime --universe idx30 --as-of 2024-06-01 --format json

 ---
 Phase 11 — Terminal Charts

 saham analyze chart price BBCA --sma 20 --ema 50     # Price + moving averages
 saham analyze chart rsi BBCA --period 14              # RSI with overbought/oversold
 saham analyze chart volume BBCA                       # Daily volume bars

 ---
 Phase 12 — Batch Data & Universe Management

 saham fetch market --universe idx30 --days 365      # Batch fetch all idx30 tickers
 saham fetch market --broker-only                    # Update broker data only
 saham fetch universe list                           # List available universes
 saham fetch universe update -u lq45                 # Refresh universe from Stockbit
 saham fetch universe inspect -s 5                   # Explore sector 5 subsectors
 saham fetch universe create food_retail -s 1 -b 10  # Create custom universe from subsector

 ---
