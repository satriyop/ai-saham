# CLI Reference

Compact, agent-optimized command reference. One `##` block per command.

Tutorial & workflows → `CLI_GUIDE.md`
Troubleshooting → `CLI_TROUBLESHOOTING.md`

## Command-family consistency

Verb dictionary (ADR-050): first token is the behavior contract.

| Family | Role | Writes learning DB? | Final action words? |
|--------|------|---------------------|---------------------|
| **`screen`** | Live multi-candidate discovery | **No** | provisional only |
| **`inspect`** | Live single-subject capability/evidence lens | **No** | **No** |
| **`plan`** | Live TradeSetup / trade plan (`plan swing`) | **No** | **Yes** |
| **`assess`** | Frozen-plan confirmation (`assess pre-open`) | **No** | relative to frozen plan |
| **`research`** | Learning corpus (capture/labels/evaluate/…) | **Yes** | no |
| **`backtest`** | Offline historical performance sim | **No** | no live action |
| **`trade`** | Human paper notebook | paper journal only | paper only |
| **`policy`** | Guarded setup-config lifecycle | policy tables | no |
| **`audit`** | Offline data quality / sentiment accuracy | audit stores may write | no |

Learning scenarios (pre-open, accum) share the same research/trade shape:

| Family | Role |
|--------|------|
| **`research <scenario> capture`** | Save decisions (observations) |
| **`research pre-open track`** | Opening samples linked to observation |
| **`research <scenario> labels`** | Outcomes on saved decisions |
| **`research <scenario> evaluate`** | Cohort summary over labels |


Examples:

- Live open: `saham screen pre-open` → no observation write  
- **Save decisions:** `saham research pre-open capture`  
- Same-day learning: `track` → `labels` → `evaluate` / `status`  
- Post-open assess: `saham assess pre-open`  
- Paper notebook: `saham trade pre-open log --observation-id … --opening-snapshot-id …`
- Live accum: `saham screen accum` → no observation write  

Do **not** auto-write observations from live `screen`.  
**Retired:** `research pre-open grade|prompt|tune`, `trade confirm`, `trade pre-open log (intraday type removed)`.
Operator runbook: `docs/runbook_pre_open.md`.

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

Launch the optional OpenCode-style daily cockpit (requires `pip install -e ".[tui]"`).

Keyboard-first local cockpit: `Ctrl+P` commands, layout B (main + sidebar).
See `docs/design/tui-cockpit-opencode.md` and ADR-051.

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

## saham inspect risk

Rule-based risk assessment using deterministic gates. Returns OPEN (no gate fired) or BLOCKED (gate name).

```
saham inspect risk TICKER [OPTIONS]
saham inspect risk BBCA
saham inspect risk BBCA --all --explain
saham inspect risk BBCA --rules-file config/my_rules.yaml
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

## # retired: analyze compare

Side-by-side risk comparison across multiple tickers.

```
# retired: analyze compare TICKER TICKER...
# retired: analyze compare BBCA BBRI BMRI
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--sma` | | 20 | SMA period |
| `--rsi` | | 14 | RSI period |

---

## saham inspect sentiment

News sentiment analysis with keyword or AI classification.

```
saham inspect sentiment TICKER [OPTIONS]
saham inspect sentiment BBCA
saham inspect sentiment BBCA --days 7 --ai-classify
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

## saham audit sentiment

Audit past sentiment predictions against actual price moves (1, 3, 5 trading days).

```
saham audit sentiment [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--db` | ./data.db | SQLite database path |

---

## saham inspect regime

Show deterministic IHSG market regime context (BULLISH, SIDEWAYS, WEAK, RISK_OFF).

```
saham inspect regime [OPTIONS]
saham inspect regime
saham inspect regime --as-of 2026-06-01 --verbose
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

## saham plan swing

Unified swing analysis — verdict-first with SignalEngine + RiskEngine, optional setup gates, market context, and position sizing.

```
saham plan swing TICKER [OPTIONS]
saham plan swing BBRI
saham plan swing BBRI --setup foreign-bounce --capital 10000000 --full
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

## ~~saham analyze swing-compare~~ (retired ADR-050)

Removed. No replacement route.


## saham inspect signal accum

Live read-only SignalEngine inspection for the **accumulation-flow** contract only
(same boundary as `screen accum`). Not pre-open auction signal; not swing
TradeSetup (`plan swing`).

```
saham inspect signal accum TICKER [OPTIONS]
saham inspect signal accum BBCA
saham inspect signal accum BBCA --window-days 30 --as-of 2026-07-27 --format json
```

| Option | Default | Description |
|--------|---------|-------------|
| `--window-days` | 7 | Accumulation window sessions |
| `--as-of` | today | Point-in-time as-of date |
| `--format` | table | Output format: table, json |
| `--db` | ./data.db | SQLite database path |

Retired: bare `saham inspect signal TICKER` (must name the purpose: `accum`).

---

## ~~saham inspect chart~~ (retired)

Terminal ASCII charts (`inspect chart price|rsi|volume`) are **removed**.
Use `saham indicator compute|snapshot` for values. Charts belong in TUI/Web later.

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

## ~~saham view market-context~~ (retired)

Use **`saham inspect regime`** for MCE/regime (sole public command).

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

## saham research pre-open labels

Generate immutable **open_30m** outcome labels from saved observations + track
snapshots (SQLite). Fail closed without capture. Cohort evaluation is a separate
command (`research pre-open evaluate`).

```
saham research pre-open labels [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--compatibility-id` | auto if unique | Exact cohort identity |
| `--db` | config | Learning SQLite path |
| `--format` | table | table or json |

---

## saham research pre-open evaluate

Evaluate a compatible pre-open label cohort (reads labels only; never rereads tracks).

```
saham research pre-open evaluate [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--compatibility-id` | auto if unique | Exact cohort identity |
| `--db` | config | Learning SQLite path |
| `--format` | table | table or json |

---

## saham research pre-open status

Inspect learning lifecycle readiness for pre-open observations / tracks / labels.

```
saham research pre-open status [OPTIONS]
```

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

## saham research accum evaluate

Historical accumulation audit — replay accumulation signals and measure forward returns.

```
saham research accum evaluate [OPTIONS]
saham research accum evaluate --universe idx80 --setup foreign-bounce
saham research accum evaluate --universe lq45 --window 7 --min-score 70
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

## saham assess pre-open

Post-open assessment of an immutable NCP pre-open plan (read-only).
Reads `learning_observations` + linked track snapshots — no live prices, no journal write.

```
saham assess pre-open [OPTIONS]
saham assess pre-open --session 2026-06-18
saham assess pre-open --observation-id OBS --opening-snapshot-id SNAP
saham assess pre-open --format json
```

| Option | Default | Description |
|--------|---------|-------------|
| `--session` | today (IDX) | Session date YYYY-MM-DD |
| `--observation-id` | — | Exact observation id (required if multiple cohorts) |
| `--opening-snapshot-id` | earliest open-window | Exact linked track snapshot id |
| `--format` | table | table or json |
| `--db` | config | Learning SQLite path |

---

## saham trade (paper notebook only)

```
saham trade pre-open log|outcome|review
saham trade accum log|review
```

Not paper: `saham research` (corpus), `saham policy accum` (config lifecycle),
`saham plan swing --capital` (sizing).

---

## saham trade pre-open log

Log post-open assess rows to the pre-open paper notebook (immutable IDs).

```
saham trade pre-open log --observation-id OBS --opening-snapshot-id SNAP
```

| Option | Default | Description |
|--------|---------|-------------|
| `--observation-id` | required | Learning observation id from assess pre-open |
| `--opening-snapshot-id` | required | Opening track snapshot id |
| `--journal` | config | Pre-open CSV journal path |
| `--db` | config | SQLite database path |

---

## saham trade pre-open outcome

Record the actual fill on a pre-open paper journal row.

```
saham trade pre-open outcome TICKER --entry 9000 --exit 9500 --result target
```

| Option | Default | Description |
|--------|---------|-------------|
| `--entry` | required | Actual entry price |
| `--exit` | required | Actual exit price |
| `--result` | manual | target, stop, manual, breakeven |
| `--date` | today | Confirmed date YYYY-MM-DD |
| `--notes` | — | Execution notes |
| `--journal` | config | Pre-open CSV journal path |

---

## saham trade pre-open review

Review pre-open paper journal buckets (manual outcome preferred; else daily OHLC proxy).

```
saham trade pre-open review [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--journal` | config | Pre-open CSV journal path |
| `--db` | config | SQLite database path |

---

## saham trade accum log

Log an accumulation candidate to the accum paper journal.

```
saham trade accum log --ticker BBRI --window 7
saham trade accum log --ticker BBRI --from-analysis --with-regime
```

| Option | Default | Description |
|--------|---------|-------------|
| `--ticker` / `-t` | required | Ticker symbol |
| `--window` / `-w` | 7 | Accumulation window in sessions |
| `--from-analysis` | false | Record setup match, gates, plan |
| `--setup` | foreign-bounce | Setup name with --from-analysis |
| `--with-regime` | false | Include market regime label |
| `--journal` | config | Accum CSV journal path |
| `--db` | config | SQLite database path |

---

## saham trade accum review

Review accum paper journal forward returns.

```
saham trade accum review [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--horizon` | 10 | Forward trading days |
| `--min-foreign-flow-score` | 0 | Minimum score filter |
| `--journal` | config | Accum CSV journal path |
| `--db` | config | SQLite database path |

---


## saham backtest screen accum

Offline historical replay of accumulation **screen filters** + forward/exit stats.
Not corpus (`research accum evaluate`). Not portfolio book.

```
saham backtest screen accum [TICKERS...] [OPTIONS]
saham backtest screen accum --universe lq45 --setup foreign-bounce --start 2026-01-01
```

See `config/accumulation_audit.yaml` setup presets. Fetch market data first.

---

## saham backtest portfolio swing

Offline **portfolio** walk-forward for a named swing setup (capital, risk, slots, costs).
Not live `plan swing`. After sim: `policy accum tune|review|validate|apply`.

```
saham backtest portfolio swing [TICKERS...] [OPTIONS]
saham backtest portfolio swing --universe lq45 --setup foreign-bounce --start 2025-01-01
```

Retired public path: `policy accum backtest` → use this command.

---
## saham policy accum

Guarded setup-config lifecycle (not paper, not research corpus).

```
saham policy accum tune|review|validate|apply|status
saham backtest portfolio swing --universe lq45 --setup foreign-bounce
saham policy accum tune --universe lq45
saham policy accum validate PROPOSAL_ID
saham policy accum apply PROPOSAL_ID --yes
saham policy accum status
```

Retired under `trade`: flat `log`/`outcome`/`review`, `size`, `swing *`,
`backtest-intraday`, `migrate-journal`, and legacy `*-tuning-*` / `backtest-swing`
command names.
