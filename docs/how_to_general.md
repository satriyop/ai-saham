 Phase 1 — Get Market Data (do this first, once)

 saham update BBCA --days 730        # Downloads 2yr OHLCV + broker flow, cached to data.db
 saham broker fetch BBCA --days 90  # Foreign flow via IDX public API (no auth)
 saham broker fetch BBCA --provider stockbit-session --days 90  # Richer per-broker detail (session needed)

 ---
 Phase 2 — Technical Indicators

 # Composite view (all at once)
 saham indicators BBCA --sma 20 --ema 20 --rsi 14

 # Individual indicators
 saham sma BBCA --period 20
 saham sma BBCA --period 50         # Trend direction (above/below SMA50)
 saham sma BBCA --period 200        # Long-term trend
 saham ema BBCA --period 20
 saham rsi BBCA --period 14

 # Plugin indicators
 saham compute ATR BBCA --period 14  # Volatility / stop sizing
 saham compute FOREIGN_FLOW BBCA    # 3-day net foreign flow

 # Custom formula indicator
 saham create-indicator "RSI smoothed with EMA of period 3" --name SMOOTH_RSI         # Uses deepseek (default)
 saham create-indicator "MACD line" --name MACD --provider claude                       # Or specify another provider
 saham compute SMOOTH_RSI BBCA

 ---
 Phase 3 — Risk Assessment

 # Single profile
 saham risk BBCA                            # balanced (default)
 saham risk BBCA --profile conservative
 saham risk BBCA --profile aggressive

 # All profiles side-by-side
 saham risk BBCA --all

 # Custom rules (your own YAML logic)
 saham risk BBCA --rules-file config/conservative.yaml

 # With AI explanation (default provider: deepseek)
 saham risk BBCA --explain                            # Uses deepseek (default)
 saham risk BBCA --explain --provider claude           # Or specify another provider

 # With news sentiment appended
 saham risk BBCA --with-sentiment

 ---
 Phase 4 — Broker & Foreign Flow Analysis

 saham broker flow BBCA --days 30    # Daily foreign net flow table
 saham broker top BBCA               # Top 5 buyers + sellers today
 saham broker top BBCA --date 2024-01-15  # Historical snapshot

 ---
 Phase 5 — Sentiment

 saham sentiment BBCA                          # Keyword classifier (offline-capable after fetch)
 saham sentiment BBCA --days 7 --max 30        # Wider window
 saham sentiment BBCA --ai-classify                          # Uses deepseek (default)
 saham sentiment BBCA --ai-classify --provider claude         # Or specify another provider

 ---
 Phase 6 — Backtest with a Strategy

 saham backtest BBCA --strategy rsi-momentum --capital 100000000
 saham backtest BBCA --strategy foreign-accumulation
 saham backtest BBCA --strategy rsi-momentum --start 2023-01-01 --end 2024-01-01 --verbose

 ---
 Phase 7 — Intraday Pre-Open Screening (if BBCA appears in morning movers)

 # Step 1: Run screener with browser automation
 saham intraday pre-open --with-ai

 # Step 2: Pass JSON data directly (skip browser)
 saham intraday pre-open \
   --movers-json '[{"ticker":"BBCA","iev":180000}]' \
   --order-books-json '{"BBCA":{"price":8875,"volume":300000}}'

 # Step 3: After opening auction, confirm entry decision
 saham intraday confirm-open \
   --opening-json '{"BBCA":{"open":8875,"high":8925,"low":8850,"close":8900}}'

 ---
 Phase 8 — Strategy / Indicator Authoring

 saham strategy list                            # See available strategies
 saham strategy validate rsi-momentum           # Check YAML correctness
 saham strategy create "Buy on RSI dip below 30 when above SMA50"            # Uses deepseek (default)
 saham strategy create "EMA crossover with 9 and 21" --provider claude          # Or specify another provider
 saham list-indicators                          # See all indicators available

 ---
 Phase 9 — Swing Trade Analysis

 # Full composite view (accumulation + risk + sizing + backtest + sentiment)
 saham swing analyze BBCA --capital 100000000

 # Position sizing based on ATR
 saham swing size BBCA --capital 100000000 --risk-pct 1 --entry 8875

 # Walk-forward backtest across universe
 saham swing backtest --universe idx30 --capital 100000000 --with-regime

 # Compare regime variants side-by-side
 saham swing compare --universe idx30 --variants bull,neutral,bear

 # Accumulation screener (same as screen accumulation)
 saham swing screen --universe idx30 --window 5

 ---
 Phase 10 — Market Regime Context

 # Current regime across universe
 saham regime --universe idx30

 # Regime as of a specific date
 saham regime --universe idx30 --as-of 2024-06-01 --format json

 ---
 Phase 11 — Terminal Charts

 saham chart price BBCA --sma 20 --ema 50     # Price + moving averages
 saham chart rsi BBCA --period 14              # RSI with overbought/oversold
 saham chart volume BBCA                       # Daily volume bars

 ---
 Phase 12 — Batch Data & Universe Management

 saham update --universe idx30 --days 365      # Batch fetch all idx30 tickers
 saham update --broker-only                    # Update broker data only
 saham universe list                           # List available universes
 saham universe update --universe custom       # Update universe stock list

 ---
