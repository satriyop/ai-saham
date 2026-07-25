# CLI Reference

Compact, agent-optimized command reference. One `##` block per command.

Tutorial & workflows → `CLI_GUIDE.md`
Troubleshooting → `CLI_TROUBLESHOOTING.md`

## Command-family consistency

Same shape for every screen scenario (pre-open, accum, …):

| Family | Role | Writes research corpus? |
|--------|------|-------------------------|
| **`screen`** | **Live** discovery / operator display | **No** observation rows |
| **`research <scenario> capture`** | **Save decisions** into `candidate_observations` | **Yes** (explicit corpus write) |
| **`research <scenario> labels`** | **Outcomes** joined to saved decisions | Labels/artifacts only |
| **`research pre-open` same-day** | **track / grade / prompt / tune** after capture | Day files under `data/opening/` (not multi-day corpus) |

Examples:

- Live open: `saham screen pre-open` → no DB observation write  
- **Save decisions:** `saham research pre-open capture`  
- Same-day follow-through: `saham research pre-open track|grade|prompt|tune`  
- Session outcomes: `saham research pre-open labels` (`open_30m`)  
- Live accum: `saham screen accum` → no observation write  
- Accum corpus: `saham research signal capture` → `… labels`

Do **not** auto-write observations from live `screen`.  
Do **not** use day-file exports as a second decision source for grade/labels.  
There is **no** top-level `learn` group.

---

## saham version

Show version and build information.

```
saham version
```

---

## saham today

Read-only daily briefing — market regime, top accumulation candidates, and opening watchlist.

```
saham today [OPTIONS]
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--universe` | `-u` | lq45 | Universe name |
| `--top` | `-n` | 10 | Number of top candidates to show |
| `--date` | `-d` | today | Briefing date (YYYY-MM-DD) |

---

## saham tui

Launch the optional terminal research workspace (requires `pip install -e ".[tui]"`).

```
saham tui
```

---

## saham audit data manifest

DQ-001 baseline manifest — database/config/code identity snapshot.

```
saham audit data manifest [TICKERS...] [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--format` | table | Output format: table, json |
| `--db` | ./data.db | SQLite database path |

---

## saham audit data source-contracts

DQ-001A source-field contract audit for core database tables.

```
saham audit data source-contracts [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--format` | table | Output format: table, json |
| `--db` | ./data.db | SQLite database path |

---

## saham audit data reconcile-sources

DQ-001B source reconciliation — OHLC invariants, arithmetic identities, cross-table foreign-flow overlaps.

```
saham audit data reconcile-sources [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--format` | table | Output format: table, json |
| `--db` | ./data.db | SQLite database path |

---

## saham audit data contract-gate

DQ-CONTRACT-GATE — combine source-contracts + reconcile-sources into PASS/FAIL. Exits non-zero on FAIL.

```
saham audit data contract-gate [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--format` | table | Output format: table, json |
| `--db` | ./data.db | SQLite database path |

---

## saham audit data seasonality-cleanup-plan

DQ-001G dry-run cleanup plan for invalid seasonality_cache rows. Read-only, exits 0.

```
saham audit data seasonality-cleanup-plan [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--format` | table | Output format: table, json |
| `--db` | ./data.db | SQLite database path |

---

## saham audit data candidate-observation-identity

DQ-001I identity audit for candidate_observations — legacy vs canonical rows, duplicate identity groups.

```
saham audit data candidate-observation-identity [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--format` | json | Output format: table, json |
| `--db` | ./data.db | SQLite database path |

---

## saham audit data repair-seasonality-cache

DQ-001H quarantine invalid seasonality_cache rows. Default mode is dry-run.

```
saham audit data repair-seasonality-cache [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--dry-run` | true | Report only, no mutation |
| `--apply` | false | Apply mode: quarantine + delete |
| `--format` | json | Output format: table, json |
| `--db` | required for --apply | SQLite database path |

---

## saham audit data repair-candidate-observations

DQ-001J quarantine legacy candidate_observations rows. Default mode is dry-run.

```
saham audit data repair-candidate-observations [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--dry-run` | true | Report only, no mutation |
| `--apply` | false | Apply mode: quarantine + delete |
| `--format` | json | Output format: table, json |
| `--db` | required for --apply | SQLite database path |

---

## saham audit data repair-signal-forward-labels

DQ-001L quarantine orphan signal_forward_labels rows. Default mode is dry-run.

```
saham audit data repair-signal-forward-labels [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--dry-run` | true | Report only, no mutation |
| `--apply` | false | Apply mode: quarantine + delete |
| `--format` | json | Output format: table, json |
| `--db` | required for --apply | SQLite database path |

---

## saham fetch market

Batch data update — candles + broker flow for a universe or explicit tickers. Pre-warms all Stockbit enrichment caches.

```
saham fetch market [OPTIONS]
saham fetch market --universe lq45
saham fetch market BBCA BBRI BMRI
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--universe` | `-u` | — | Named universe: lq45, idx80, idxcomp100, cached |
| `--days` | `-d` | 365 | Days of history to fetch |
| `--candles-only` | | false | Skip broker flow fetch |
| `--broker-only` | | false | Skip candles fetch |
| `--provider` | | yahoo | Candle provider: yahoo, idx |
| `--broker-provider` | | auto | Broker provider: idx, stockbit |
| `--no-meta` | | false | Skip sector/industry metadata |
| `--no-enrichment` | | false | Skip Stockbit enrichment |
| `--refresh` | `-r` | false | Force refresh all |
| `--db` | | ./data.db | SQLite database path |

---

## saham fetch enrichment-history

Store a point-in-time enrichment snapshot for a universe, used by signal backfill replay.

```
saham fetch enrichment-history [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--universe` | — | Universe name |

---

## saham fetch broker

Fetch broker summary data (foreign flow) for a ticker.

```
saham fetch broker TICKER [OPTIONS]
saham fetch broker BBCA
saham fetch broker BBRI --days 90 --provider stockbit
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--days` | `-d` | 30 | Number of days to fetch |
| `--start` | `-s` | — | Start date (YYYY-MM-DD) |
| `--end` | `-e` | — | End date (YYYY-MM-DD) |
| `--refresh` | `-r` | false | Force refresh from provider |
| `--provider` | `-P` | idx | Data provider: idx, stockbit |
| `--db` | | ./data.db | SQLite database path |

---

## saham fetch broker-history

Fetch foreign flow history for a ticker via Stockbit.

```
saham fetch broker-history TICKER [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--days` | 30 | Number of days |

---

## saham fetch broker-top-foreign

Universe scan for stocks with the strongest foreign flow.

```
saham fetch broker-top-foreign [OPTIONS]
```

No options beyond `--db`.

---

## saham fetch broker-import

Import broker data from a CSV file.

```
saham fetch broker-import FILE [OPTIONS]
saham fetch broker-import data.csv
saham fetch broker-import data.csv --preview
saham fetch broker-import data.csv --mapping rti_export
```

| Option | Default | Description |
|--------|---------|-------------|
| `--preview` | false | Preview without importing |
| `--mapping` | auto | Column mapping: (auto), simple, detailed, or custom name |
| `--on-error` | skip | Error handling: skip, fail, report |

---

## saham fetch calendar

Fetch the market-wide Stockbit corporate action calendar (dividends, rights issues, RUPS).

```
saham fetch calendar [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--days` | 365 | Lookahead window |

---

## saham fetch iev

Capture pre-open IEV (Indicative Equilibrium Value) mover rankings via Stockbit.

```
saham fetch iev [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--top-n` | 20 | Number of top movers |
| `--no-headless` | false | Run browser in headed mode |

---

## saham fetch status

Health check for all data providers and database tables.

```
saham fetch status
```

---

## saham fetch audit

Local data quality audit — volume unit consistency, candle provenance, date gaps, value integrity.

```
saham fetch audit [TICKERS...] [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--db` | ./data.db | SQLite database path |

---

## saham fetch universe list

List all configured universes with ticker counts.

```
saham fetch universe list
```

---

## saham fetch universe update

Refresh universe membership from the Stockbit Exodus API.

```
saham fetch universe update [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--universe` | — | Specific universe to update (omit = all) |
| `--discover` | false | Discover and import new sectors |

---

## saham fetch universe inspect

Explore Stockbit sectors and subsectors for universe creation.

```
saham fetch universe inspect [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--sector` | — | Sector name to inspect |
| `--subsector` | — | Subsector name |

---

## saham fetch universe create

Create a custom universe from a Stockbit sector or subsector.

```
saham fetch universe create NAME [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--sector` | — | Sector name |
| `--subsector` | — | Subsector name |

---

## saham fetch stockbit login

Open a Playwright browser window to log in to Stockbit and save the persistent session profile.

```
saham fetch stockbit login [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--timeout` | 120 | Login timeout in seconds |

---

## saham fetch stockbit status

Check Stockbit browser session health.

```
saham fetch stockbit status
```

---

## saham fetch stockbit spy

Capture Stockbit API traffic to identify endpoints for integration. Use headed mode to interact and observe network requests.

```
saham fetch stockbit spy [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--target` | — | Endpoint target to spy on |
| `--ticker` | — | Ticker to scope the spy |

---

## saham fetch stockbit test

Smoke-test the Stockbit adapter against live data.

```
saham fetch stockbit test [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--ticker` | BBCA | Ticker to test against |
| `--no-headless` | false | Run browser in headed mode |

---

## saham fetch stockbit browse

Open an interactive headed browser with the saved Stockbit session.

```
saham fetch stockbit browse
```

---

## saham fetch stockbit fetch-top5

Fetch top IEV movers and live orderbook snapshots.

```
saham fetch stockbit fetch-top5 [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--top` | 5 | Number of top movers |
| `--no-headless` | false | Run browser in headed mode |

---

## saham indicator compute

Compute any technical indicator for a stock.

```
saham indicator compute INDICATOR TICKER [OPTIONS]
saham indicator compute RSI BBCA
saham indicator compute SMA BBCA --period 50
saham indicator compute SMOOTH_RSI BBCA --tail 10
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--period` | `-p` | 14 | Period (ignored for formula indicators) |
| `--days` | `-d` | 365 | Days of history to load |
| `--tail` | `-t` | 30 | Show last N values |
| `--db` | | ./data.db | SQLite database path |

---

## saham indicator snapshot

Multi-indicator snapshot for a ticker (SMA + EMA + RSI aligned by date).

```
saham indicator snapshot TICKER [OPTIONS]
saham indicator snapshot BBCA
saham indicator snapshot BBRI --sma 50 --ema 50 --rsi 7
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--sma` | | 20 | SMA period |
| `--ema` | | 20 | EMA period |
| `--rsi` | | 14 | RSI period |
| `--days` | `-d` | 365 | Days of history |
| `--format` | | table | Output format: table, json |
| `--db` | | ./data.db | SQLite database path |

---

## saham indicator create

Create a custom formula from natural language using AI.

```
saham indicator create INTENT [OPTIONS]
saham indicator create "smoothed RSI" --name SMOOTH_RSI
saham indicator create "MACD line" --name MACD --provider claude --no-save
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--name` | `-n` | auto-generated | Formula name (uppercase) |
| `--provider` | `-p` | mock | AI provider: deepseek, claude, openai, gemini, ollama, mock |
| `--model` | `-m` | provider default | Model name |
| `--save/--no-save` | | save | Save to formulas file |
| `--formulas` | | config/formulas.yaml | Custom formulas path |

---

## saham indicator list

List all available indicators — built-in, plugin, and custom formulas.

```
saham indicator list [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--formulas` | false | Show formula expressions |

---

## saham indicator show

Show details for a saved formula.

```
saham indicator show NAME
saham indicator show SMOOTH_RSI
```

---

## saham indicator delete

Delete a saved custom formula. Built-in indicators cannot be deleted.

```
saham indicator delete NAME [OPTIONS]
saham indicator delete SMOOTH_RSI
saham indicator delete SMOOTH_RSI --force
```

| Option | Default | Description |
|--------|---------|-------------|
| `--force` | false | Skip confirmation prompt |

---

## saham analyze risk

Rule-based risk assessment using deterministic gates. Returns OPEN (no gate fired) or BLOCKED (gate name).

```
saham analyze risk TICKER [OPTIONS]
saham analyze risk BBCA
saham analyze risk BBCA --all --explain
saham analyze risk BBCA --rules-file config/my_rules.yaml
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--rules-file` | `-r` | — | Path to custom YAML rules file |
| `--sma` | | 20 | SMA period |
| `--ema` | | 20 | EMA period |
| `--rsi` | | 14 | RSI period |
| `--explain` | `-e` | false | Generate AI explanation |
| `--provider` | | deepseek | AI provider |
| `--model` | `-m` | provider default | Model name |
| `--with-sentiment` | `-s` | false | Include news sentiment context |
| `--news-provider` | | composite | News source |
| `--no-ai` | | false | Disable AI sentiment classifier |
| `--trend` | | 0 | Show risk trend over last N days |
| `--format` | | table | Output format: table, json |
| `--db` | | ./data.db | SQLite database path |

---

## saham analyze compare

Side-by-side risk comparison across multiple tickers.

```
saham analyze compare TICKER TICKER...
saham analyze compare BBCA BBRI BMRI
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--sma` | | 20 | SMA period |
| `--rsi` | | 14 | RSI period |

---

## saham analyze sentiment

News sentiment analysis with keyword or AI classification.

```
saham analyze sentiment TICKER [OPTIONS]
saham analyze sentiment BBCA
saham analyze sentiment BBCA --days 7 --ai-classify
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--days` | `-d` | 3 | Days of news to fetch |
| `--max` | | 20 | Maximum headlines to analyze |
| `--no-ai` | | false | Offline keyword classification |
| `--provider` | | — | AI provider for classification |
| `--model` | `-m` | provider default | Model name |
| `--news-provider` | | composite | News source: composite, google, kontan, cnbc, mock |
| `--db` | | ./data.db | SQLite database path |

---

## saham analyze audit

Audit past sentiment predictions against actual price moves (1, 3, 5 trading days).

```
saham analyze audit [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--db` | ./data.db | SQLite database path |

---

## saham analyze regime

Show deterministic IHSG market regime context (BULLISH, SIDEWAYS, WEAK, RISK_OFF).

```
saham analyze regime [OPTIONS]
saham analyze regime
saham analyze regime --as-of 2026-06-01 --verbose
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--universe` | `-u` | idx80 | Universe for breadth context |
| `--benchmark` | | ^JKSE | Benchmark ticker |
| `--as-of` | | today | Regime date (YYYY-MM-DD) |
| `--verbose` | `-v` | false | Show score bar and rationale per factor |
| `--format` | | table | Output format: table, json |
| `--db` | | ./data.db | SQLite database path |

---

## saham analyze swing

Unified swing analysis — verdict-first with SignalEngine + RiskEngine, optional setup gates, market context, and position sizing.

```
saham analyze swing TICKER [OPTIONS]
saham analyze swing BBRI
saham analyze swing BBRI --setup foreign-bounce --capital 10000000 --full
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--strategy` | `-S` | none | Optional backtest strategy name |
| `--setup` | | none | Setup lens: foreign-bounce, coiled-spring, smart-money-confirmed, pullback-continuation |
| `--window` | `-w` | 7 | Accumulation window in broker sessions |
| `--flow-window` | | 30 | Broker-flow detail window |
| `--capital` | `-c` | — | Capital in IDR (enables sizing) |
| `--risk-pct` | | 1.0 | % of capital at risk per trade |
| `--entry` | | — | Entry price override |
| `--atr-mult` | | 1.5 | ATR multiplier for stop |
| `--rr` | | 2.0 | Reward:risk ratio |
| `--with-sentiment` | | false | Include news sentiment evidence |
| `--with-flow-detail` | | false | Include broker flow attribution |
| `--with-signal-detail` | | false | Include SignalEngine factor detail |
| `--with-risk-detail` | | false | Include RiskEngine gate detail |
| `--with-market-context` | | false | Include MarketContextEngine preview |
| `--with-market-detail` | | false | Full MCE factor detail |
| `--with-technical-gate` | | false | Enable SMA/EMA/RSI execution gate |
| `--explain` | | false | Shortcut for signal + risk + market detail |
| `--full` | | false | All optional evidence except named setup |
| `--no-sentiment` | | false | Deprecated no-op |
| `--sentiment-verbose` | | false | Show sentiment provider errors |
| `--no-backtest` | | false | Deprecated compatibility |
| `--no-refresh` | | false | Disable auto single-ticker refresh |
| `--force-refresh` | | false | Force provider refresh |
| `--regime-universe` | | — | Universe for regime breadth |
| `--benchmark` | | ^JKSE | Benchmark ticker for regime |
| `--risk-strategy` | | — | Risk strategy for alternative gate config |
| `--format` | | table | Output format: table, json |
| `--db` | | ./data.db | SQLite database path |

---

## saham analyze swing-compare

Compare regime-filtered swing variants side-by-side.

```
saham analyze swing-compare [OPTIONS]
saham analyze swing-compare --universe idx80
saham analyze swing-compare --universe lq45 --variants baseline,sideways_only
```

| Option | Default | Description |
|--------|---------|-------------|
| `--universe` | idx80 | Universe to scan |
| `--variants` | baseline,risk_off,sideways_only | Comma-separated regime variants |

---

## saham analyze signal inspect

Live read-only SignalEngine inspection for a ticker — see every factor score.

```
saham analyze signal inspect TICKER [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--format` | table | Output format: table, json |
| `--db` | ./data.db | SQLite database path |

---

## saham analyze chart price

Plot an ASCII price chart in the terminal with optional SMA/EMA overlays.

```
saham analyze chart price TICKER [OPTIONS]
saham analyze chart price BBCA
saham analyze chart price BBCA --sma 20 --ema 9 --days 120
```

| Option | Default | Description |
|--------|---------|-------------|
| `--sma` | — | SMA period overlay |
| `--ema` | — | EMA period overlay |
| `--days` | 365 | Days of data |
| `--width` | 80 | Chart width in characters |

---

## saham analyze chart rsi

Plot an ASCII RSI chart in the terminal with overbought/oversold bands.

```
saham analyze chart rsi TICKER [OPTIONS]
saham analyze chart rsi BBCA --period 9 --days 120
```

| Option | Default | Description |
|--------|---------|-------------|
| `--period` | 14 | RSI period |
| `--days` | 365 | Days of data |

---

## saham analyze chart volume

Plot ASCII volume bars in the terminal.

```
saham analyze chart volume TICKER [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--days` | 365 | Days of data |

---

## saham view TICKER

Read-only ticker dashboard — all cached data in 12 panels. Same as `saham view ticker show TICKER`.

```
saham view BBCA
```

---

## saham view ticker show

Explicit ticker dashboard view (identical to `saham view TICKER`).

```
saham view ticker show TICKER
saham view ticker show BBCA
```

---

## saham view ticker flow

View foreign net flow summary for a ticker.

```
saham view ticker flow TICKER [OPTIONS]
saham view ticker flow BBCA
saham view ticker flow BBRI --days 20
```

| Option | Default | Description |
|--------|---------|-------------|
| `--days` | 10 | Trading days to show |

---

## saham view ticker top-brokers

View top brokers (buyers/sellers) for a ticker on a specific date.

```
saham view ticker top-brokers TICKER [OPTIONS]
saham view ticker top-brokers BBCA
saham view ticker top-brokers BBRI --date 2025-01-15
```

| Option | Default | Description |
|--------|---------|-------------|
| `--date` | latest | Broker session date (YYYY-MM-DD) |

---

## saham view ticker foreign-history

View foreign flow time-series data for a ticker.

```
saham view ticker foreign-history TICKER [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--days` | 30 | Trading days to show |
| `--source` | idx | Data source: idx, stockbit |

---

## saham view ticker distribution

View cross-broker counterparty matrix for a ticker (requires cached Stockbit data).

```
saham view ticker distribution TICKER
saham view ticker distribution BBCA
```

---

## saham view universe

List all configured universes with ticker counts (no name argument), or show market-wide snapshot for a named universe.

```
saham view universe
saham view universe lq45
saham view universe lq45 --sort flow --top 10
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--sort` | `-s` | flow | Sort by: flow, change, volume, ticker |
| `--top` | `-n` | all | Show only top N rows |
| `--date` | `-d` | latest | Show data as of this date (YYYY-MM-DD) |

---

## saham view market-context

Show cross-market regime context — VIX, EIDO, USD/IDR, IDX breadth — from local cache.

```
saham view market-context [OPTIONS]
saham view market-context --date 2026-06-01 --verbose
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--date` | | today | Context date (YYYY-MM-DD) |
| `--universe` | `-u` | (config) | Universe for breadth factor |
| `--verbose` | `-v` | false | Show score bar and rationale |
| `--format` | | table | Output format: table, json |
| `--db` | | ./data.db | SQLite database path |

---

## saham view broker show

Show desk-level info for a tracked broker.

```
saham view broker show CODE
saham view broker show YP
```

---

## saham view broker top-stocks

Show top stocks traded by a broker desk.

```
saham view broker top-stocks CODE [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--limit` | 10 | Number of stocks |

---

## saham view broker flow

Show broker desk foreign flow timeline.

```
saham view broker flow CODE [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--days` | 10 | Trading days |

---

## saham view broker history

Show broker activity history.

```
saham view broker history CODE [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--days` | 10 | Trading days |

---

## saham view broker status

Check health status of all data providers (IDX, Stockbit).

```
saham view broker status
```

---

## saham view broker top-foreign

View stocks with the strongest foreign flow by period.

```
saham view broker top-foreign [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--days` | 30 | Period in days |
| `--date` | latest | As-of date |
| `--limit` | 10 | Number of stocks |

---

## saham view broker mappings

List available CSV column mappings for `saham fetch broker-import`.

```
saham view broker mappings
```

---

## saham view broker list

List all tracked brokers.

```
saham view broker list
```

---

## saham screen accum

**Live** foreign accumulation screener — rank stocks by institutional accumulation
evidence (SignalAssessment 0–100). **Does not** write research observations —
use `research signal capture` for corpus decisions (`--save` is watchlist only).

```
saham screen accum [OPTIONS]
saham screen accum --universe lq45
saham screen accum --universe idx80 --window 30 --multi
saham screen accum --universe lq45 --save morning-watch
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--universe` | `-u` | — | Universe: lq45, idx80, idxcomp100, cached |
| `--window` | `-w` | 7 | Analysis window in broker sessions (7, 30, 90) |
| `--min-streak` | | 0 | Minimum consecutive buy days |
| `--min-foreign-flow-score` | | config | Minimum accum score (0-100) |
| `--min-signal-score` | | config | Minimum SignalEngine score (0-100) |
| `--min-piotroski` | | — | Minimum Piotroski F-score filter |
| `--vwap-only` | | false | Only underwater foreign positions |
| `--squeeze-only` | | false | Only BB squeeze stocks |
| `--top` | | 20 | Show top N results |
| `--multi` | | false | Multi-window side-by-side (7, 30, 90) |
| `--windows` | | 7,30,90 | Windows for --multi |
| `--sort-by` | | avg | Sort for --multi: avg, max, 7s, 30s, 90s |
| `--top-broker` | | false | Show top broker-code detail |
| `--explain` | | false | Show scoring definitions |
| `--strategy` | `-S` | — | Optional backtest strategy for signal context |
| `--save` | | none | Persist to named watchlist |
| `--format` | | table | Output format: table, json |
| `--guide` | | false | Column reference guide |
| `--db` | | ./data.db | SQLite database path |

---

## saham screen pre-open

**Live** pre-market movers screener (opening auction workflow). **Does not** write
`candidate_observations` — save decisions with `research pre-open capture`.

Regime context and default-gate risk annotation are **always-on** (non-blocking).
Use `--no-regime` / `--no-risk` to opt out.

```
saham screen pre-open [OPTIONS]
saham screen pre-open --movers-json '[{"ticker":"BBCA","iev":150000}]'
```

| Option | Default | Description |
|--------|---------|-------------|
| `--movers-json` | [] | JSON array of pre-open movers |
| `--fast` | false | Fast mode (no order book, ~15s) |
| `--order-books-json` | — | JSON map of order book data |
| `--top` | 10 | Top N candidates |
| `--no-regime` | false | Skip always-on market regime context |
| `--no-risk` | false | Skip always-on default-gate risk annotation |
| `--regime-universe` | from config | Universe for regime breadth |
| `--benchmark` | from config | Benchmark ticker for regime |

---

## saham screen watchlist

List saved screener watchlists or show tickers in a named one.

```
saham screen watchlist
saham screen watchlist morning-watch
```

| Option | Default | Description |
|--------|---------|-------------|
| `--format` | table | Output format: table, json |
| `--db` | ./data.db | SQLite database path |

---

## saham screen compare

Diff a saved watchlist against a fresh screener run. Shows new/dropped tickers and signal changes.

```
saham screen compare NAME [OPTIONS]
saham screen compare morning-watch
saham screen compare morning-watch --universe lq45 --top 30
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--universe` | `-u` | same as saved | Universe to screen now |
| `--window` | `-w` | 7 | Broker-session window |
| `--top` | | 20 | Top N results |
| `--format` | | table | Output format: table, json |
| `--db` | | ./data.db | SQLite database path |

---

## saham research pre-open capture

**Sole decision write** for the opening learning loop. Saves into
`candidate_observations` (workflow `screen_pre_open`, contract `pre-open-open-30m`)
and same-run ops packaging (`data/opening/YYYYMMDD/ops_session.json` + trade-confirm
sidecar). Symmetric to `research signal capture` for accumulation-discovery.

**Live `screen pre-open` does not write observations.** There is no top-level `learn` group.

```
saham research pre-open capture [OPTIONS]
saham research pre-open capture --session 2026-06-18 --movers-json '...'
```

| Option | Default | Description |
|--------|---------|-------------|
| `--session` | today | Session date YYYY-MM-DD |
| `--movers-json` | — | Pre-fetched movers (offline capture) |
| `--fast` | false | Skip order books |
| `--db` | config | SQLite path |
| `--format` | table | table or json |

---

## saham research pre-open track

Track orderbook prices every 5 minutes from 09:00–09:30 WIB for tickers from
**saved pre-open observations**. Saves `data/opening/YYYYMMDD/track_HHMM.json`.

Requires prior `research pre-open capture` (or explicit tickers with `--force`).

```
saham research pre-open track [OPTIONS]
saham research pre-open track --broker-confirm   # include institutional tick data
saham research pre-open track --force BBCA BBRI  # manual dry-run
```

| Option | Default | Description |
|--------|---------|-------------|
| `--force` | false | Run outside live trading window |
| `--broker-confirm` | false | Include institutional running-trade ticks |
| `--date` | today | Date for retrospective tracking |
| `--db` | ./data.db | SQLite database path |

---

## saham research pre-open grade

**Same-day ops** session scorecard (not multi-day corpus labels). Joins **saved
DB observations only** (`screen_pre_open`) to `track_*.json` prices. Fail closed
without capture. Champion metrics: plan + signal bands + screen_result / TradeSetup
slices. PRIME strata are **legacy secondary**. Does not recompute signal scores.
Writes `grade.json` + `grade.md` for tune/prompt.
For `open_30m` corpus outcomes use `research pre-open labels`.

```
saham research pre-open grade [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--date` | today | Grade date (YYYY-MM-DD) |
| `--db` | config | SQLite path for saved observations |

---

## saham research pre-open labels

Generate **open_30m** outcome labels from **saved** pre-open observations + tracks
(session-horizon twin of `research signal labels`). Fail closed without capture.
Writes `data/opening/YYYYMMDD/open_30m_labels.json`.

Not `research signal labels` (multi-day horizons only).

```
saham research pre-open labels [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--date` | today | Session date (YYYY-MM-DD) |
| `--db` | config | SQLite path for saved observations |
| `--no-persist` | false | Compute only; do not write JSON |

---

## saham research pre-open tune

Generate AI config tuning recommendations from today's grade via DeepSeek.

```
saham research pre-open tune [OPTIONS]
saham research pre-open tune --allow-invalid-snapshot
```

| Option | Default | Description |
|--------|---------|-------------|
| `--allow-invalid-snapshot` | false | Tune from low-confidence/out-of-window snapshot |
| `--api-key` | DEEPSEEK_API_KEY | DeepSeek API key |

---

## saham research pre-open prompt

Generate a structured AI prompt from today's predictions and accuracy metrics. Pipe to clipboard or save.

```
saham research pre-open prompt [OPTIONS]
saham research pre-open prompt | pbcopy
```

| Option | Default | Description |
|--------|---------|-------------|
| `--print` | false | Print to stdout instead of saving |

---

## saham research signal capture

**Save decisions** — persist canonical candidate observations for one trading
session (accum research corpus). Live `screen accum` does not write observations.

```
saham research signal capture [OPTIONS]
saham research signal capture --contract accumulation-discovery --universe lq45 --session 2026-07-21
```

| Option | Default | Description |
|--------|---------|-------------|
| `--contract` | — | Signal contract name |
| `--universe` | — | Universe name |
| `--session` | today | Session date (YYYY-MM-DD) |
| `--format` | json | Output format |
| `--db` | ./data.db | SQLite database path |

---

## saham research signal backfill

Backfill signal observations for historical dates.

```
saham research signal backfill [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--contract` | — | Signal contract name |
| `--universe` | — | Universe name |
| `--db` | ./data.db | SQLite database path |

---

## saham research signal labels

**Outcomes** — generate forward labels for saved decisions (observations).

```
saham research signal labels [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--session` | — | Session date |
| `--db` | ./data.db | SQLite database path |

---

## saham research signal replay

Replay signal assessment historically to evaluate performance.

```
saham research signal replay [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--contract` | — | Signal contract name |
| `--universe` | — | Universe name |
| `--db` | ./data.db | SQLite database path |

---

## saham research signal readiness

Signal readiness diagnostics — check if the signal pipeline is fully populated.

```
saham research signal readiness [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--db` | ./data.db | SQLite database path |

---

## saham research accumulation evaluate

Historical accumulation audit — replay accumulation signals and measure forward returns.

```
saham research accumulation evaluate [OPTIONS]
saham research accumulation evaluate --universe idx80 --setup foreign-bounce
saham research accumulation evaluate --universe lq45 --window 7 --min-score 70
```

| Option | Default | Description |
|--------|---------|-------------|
| `--universe` | idx80 | Universe name |
| `--setup` | foreign-bounce | Setup lens |
| `--window` | 7 | Accumulation window |
| `--min-score` | 0 | Minimum score threshold |
| `--simulate-exits` | false | Apply exit rules |

---

## saham strategy init

Create a new strategy package with starter template.

```
saham strategy init NAME [OPTIONS]
saham strategy init momentum
saham strategy init my_strat --dir ~/trading/strategies/my_strat
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--dir` | `-d` | ./strategies/NAME | Directory to create strategy in |
| `--force` | `-f` | false | Overwrite existing strategy |

---

## saham strategy validate

Validate a strategy package (auto-generates SKILL.md if sidecar exists).

```
saham strategy validate NAME [OPTIONS]
saham strategy validate momentum
saham strategy validate ./strategies/momentum/strategy.yaml --strict
```

| Option | Default | Description |
|--------|---------|-------------|
| `--strict` | false | Treat warnings as errors |

---

## saham strategy list

List all available strategies.

```
saham strategy list [OPTIONS]
saham strategy list --verbose
saham strategy list --all
```

| Option | Default | Description |
|--------|---------|-------------|
| `--verbose` | false | Show detailed information |
| `--all` | false | Include invalid strategies |

---

## saham strategy create

Create a strategy from natural language using AI.

```
saham strategy create INTENT [OPTIONS]
saham strategy create "buy when RSI below 30 and EMA crossover" --name momentum
saham strategy create "conservative RSI strategy" --name conservative_rsi --provider claude
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--name` | `-n` | auto-generated | Strategy name |
| `--provider` | `-p` | mock | AI provider: deepseek, claude, openai, gemini, ollama, mock |
| `--model` | `-m` | provider default | Model name |
| `--dir` | `-d` | ./strategies/NAME | Directory to save strategy |
| `--save/--no-save` | | save | Save to file or preview only |

---

## saham strategy backtest

Backtest a strategy against historical data.

```
saham strategy backtest TICKER [OPTIONS]
saham strategy backtest BBCA --strategy momentum
saham strategy backtest BBRI -S momentum --start 2024-01-01 --end 2024-12-31
saham strategy backtest BBCA --rules-file config/custom_rules.yaml.example --capital 50000000
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--strategy` | `-S` | — | Strategy name or path |
| `--rules-file` | `-r` | — | Path to rules YAML (backward-compatible) |
| `--start` | `-s` | — | Start date (YYYY-MM-DD) |
| `--end` | `-e` | — | End date (YYYY-MM-DD) |
| `--capital` | `-c` | — | Initial capital in IDR |
| `--verbose` | `-v` | false | Show trade-by-trade output |
| `--format` | | table | Output format: table, json |
| `--db` | | ./data.db | SQLite database path |

---

## saham strategy skill generate

Generate SKILL.md for a strategy, indicator, or formula artifact.

```
saham strategy skill generate NAME [OPTIONS]
saham strategy skill generate rsi-momentum
saham strategy skill generate atr --type indicator
saham strategy skill generate SMOOTH_RSI --type formula
```

| Option | Default | Description |
|--------|---------|-------------|
| `--type` | strategy | Artifact type: strategy, indicator, formula |

---

## saham strategy skill check

Report which strategies have stale SKILL.md files (rules changed since last generation).

```
saham strategy skill check
```

---

## saham strategy skill index

Rebuild the project-wide SKILLS_INDEX.md catalog.

```
saham strategy skill index
```

---

## saham trade confirm

Confirm pre-open screening candidates against actual opening auction prices.

```
saham trade confirm [OPTIONS]
saham trade confirm --opening-json '{"BBCA":9050,"BMRI":5875}'
saham trade confirm --track-file data/opening/20260617/track_0900.json
```

| Option | Default | Description |
|--------|---------|-------------|
| `--opening-json` | — | JSON map of ticker→opening price |
| `--track-file` | — | Learn tracking file for auto-resolve |

---

## saham trade log

Log a paper-trade decision to the journal.

```
saham trade log --type TYPE [OPTIONS]
saham trade log --type swing --ticker BBRI --window 7
saham trade log --type intraday
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--type` | | required | Journal type: swing, intraday |
| `--ticker` | | — | Ticker(s) for swing log |
| `--window` | `-w` | 7 | Window for swing log |

---

## saham trade review intraday

Review intraday confirmation journal.

```
saham trade review intraday [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--journal` | ./trades.jsonl | Journal file path |
| `--db` | ./data.db | SQLite database path |

---

## saham trade review swing

Review swing accumulation trade journal.

```
saham trade review swing [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--horizon` | 20 | Review horizon in days |
| `--min-score` | — | Minimum score filter |
| `--journal` | ./trades.jsonl | Journal file path |
| `--db` | ./data.db | SQLite database path |

---

## saham trade outcome

Record the actual outcome of a paper trade.

```
saham trade outcome TICKER [OPTIONS]
saham trade outcome BBCA --entry 9000 --exit 9500 --result target
```

| Option | Default | Description |
|--------|---------|-------------|
| `--entry` | — | Entry price |
| `--exit` | — | Exit price |
| `--result` | — | Outcome: target, stop, manual |

---

## saham trade size

ATR-based position sizing calculator.

```
saham trade size TICKER [OPTIONS]
saham trade size BBRI --capital 10000000
saham trade size BBRI --capital 10000000 --risk-pct 2 --entry 4825
```

| Option | Default | Description |
|--------|---------|-------------|
| `--capital` | required | Capital in IDR |
| `--risk-pct` | 1.0 | % of capital at risk per trade |
| `--entry` | — | Entry price override |

---

## saham trade backtest-swing

Walk-forward portfolio backtest for the swing workflow.

```
saham trade backtest-swing [OPTIONS]
saham trade backtest-swing --universe idx80 --setup foreign-bounce
saham trade backtest-swing --universe lq45 --capital 50000000 --max-positions 3
```

| Option | Default | Description |
|--------|---------|-------------|
| `--universe` | idx80 | Universe to backtest |
| `--setup` | foreign-bounce | Setup lens |
| `--capital` | — | Capital in IDR |
| `--max-positions` | — | Maximum concurrent positions |
| `--allow-regimes` | — | Comma-separated allowed regimes |

---

## saham trade backtest-intraday

Walk-forward backtest for the intraday pre-open workflow using daily OHLC as proxy.

```
saham trade backtest-intraday [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--universe` | idx80 | Universe to backtest |
| `--start` | — | Start date |
| `--end` | — | End date |

---

## saham trade tune-swing

Swing tuning review — generate config tuning recommendations from backtest attribution.

```
saham trade tune-swing [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--universe` | idx80 | Universe |
| `--setup` | foreign-bounce | Setup lens |
| `--start` | — | Start date |
| `--end` | — | End date |

---

## saham trade tuning-status

Read-only status of the swing tuning loop — latest review, pending patches, applied changes.

```
saham trade tuning-status
```

---

## saham trade review-tuning-swing

Review saved swing tuning run results.

```
saham trade review-tuning-swing [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--limit` | 10 | Number of recent reviews to show |

---

## saham trade validate-tuning-patch

Validate an exported swing tuning patch JSON file for schema correctness.

```
saham trade validate-tuning-patch [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--file` | required | Path to tuning patch JSON |

---

## saham trade apply-tuning-patch

Dry-run or explicitly apply an exported tuning patch to the runtime config.

```
saham trade apply-tuning-patch [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--file` | required | Path to tuning patch JSON |
| `--apply` | false | Apply mode (default is dry-run) |
| `--dry-run` | true | Report changes without applying |

---

## saham trade migrate-journal

One-time migration of CSV-format trade journals to JSONL format.

```
saham trade migrate-journal [OPTIONS]
```
