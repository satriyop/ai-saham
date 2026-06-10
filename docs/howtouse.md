 Phase 1 — Get Market Data (do this first, once)

 saham fetch BBCA --days 730        # Downloads 2yr OHLCV, cached to data.db
 saham broker fetch BBCA --days 90  # Foreign flow via IDX public API (no auth)
 saham broker fetch BBCA --provider stockbit --days 90  # Richer per-broker detail (auth needed)

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
 saham create-indicator "RSI smoothed with EMA of period 3" --name SMOOTH_RSI --provider claude
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

 # With AI explanation
 saham risk BBCA --explain --provider claude

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
 saham sentiment BBCA --ai-classify --provider claude  # AI-powered classification

 ---
 Phase 6 — Backtest with a Strategy

 saham backtest BBCA --strategy rsi-momentum --capital 100000000
 saham backtest BBCA --strategy foreign-accumulation
 saham backtest BBCA --strategy rsi-momentum --start 2023-01-01 --end 2024-01-01 --verbose

 ---
 Phase 7 — Pre-Open Screening (if BBCA appears in morning movers)

 # Step 1: Print browser action plan
 saham screen pre-open

 # Step 2: Claude navigates Stockbit → extracts JSON
 # Step 3: Feed data back
 saham screen pre-open \
   --movers-json '[{"ticker":"BBCA","iev":180000}]' \
   --order-books-json '{"BBCA":{"price":8875,"volume":300000}}' \
   --with-ai

 ---
 Phase 8 — Strategy / Indicator Authoring

 saham strategy list                            # See available strategies
 saham strategy validate rsi-momentum           # Check YAML correctness
 saham strategy create "Buy on RSI dip below 30 when above SMA50" --provider claude
 saham list-indicators                          # See all indicators available

 ---
