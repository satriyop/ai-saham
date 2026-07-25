# AI Saham

Local-first stock analysis CLI for Indonesia Stock Exchange (IDX).

```
"Deterministic analysis first, AI explains second"
```

**What it is:** A composable stock analysis engine with rule-based analysis,
local-first design, composable indicators, strategy packages, and optional AI.

**What it is NOT:** A trading bot, financial advice, or a black box.
Every decision is traceable and auditable.

---

## Quick Start

```bash
# Check installation
saham version

# Download stock data
saham fetch market BBCA --days 365

# Risk assessment across all profiles
saham analyze risk BBCA --all

# Create and test a strategy
saham strategy init momentum
saham strategy backtest BBCA --strategy momentum

# Or create a strategy from natural language
saham strategy create "RSI oversold strategy" --name my_rsi
saham strategy backtest BBCA --strategy my_rsi
```

---

## Documentation

| File | Best For | What's Inside |
|------|----------|---------------|
| `CLI_REFERENCE.md` | **Quick lookups** — every command, syntax, options, examples | Compact per-command blocks, grep-friendly `##` headers |
| `CLI_GUIDE.md` | **Learning stock analysis** — concepts, tutorials, workflows | OHLCV, indicators, risk assessment, foreign flow, backtesting, strategies, swing analysis |
| `CLI_TROUBLESHOOTING.md` | **Error resolution** — common errors and fixes | "No cached data", "Strategy not found", "Stockbit session expired", and more |

### When to Use Each

- **I need the exact flags for `saham analyze swing`** → `CLI_REFERENCE.md`
- **I want to understand what RSI means** → `CLI_GUIDE.md`
- **`saham fetch stockbit login` failed** → `CLI_TROUBLESHOOTING.md`

---

## Command Tree

```
saham
├── version
├── today               — read-only daily briefing
├── tui                 — optional terminal research workspace
├── audit data          — DQ baseline manifest and field contracts
├── fetch               — data ingestion (market, broker, stockbit, universe)
├── indicator           — technical indicators (compute, snapshot, create, list)
├── analyze             — live analysis (risk, sentiment, regime, swing, chart)
├── view                — read-only local data browsing
├── screen              — candidate discovery (accumulation, pre-open)
├── learn               — opening session journal (snapshot, track, grade, tune)
├── research            — research corpus and offline evaluation
├── strategy            — strategy management (init, validate, backtest)
└── trade               — paper trading workspace
```

See `CLI_REFERENCE.md` for every command with syntax, options, and examples.

---

## Core Philosophy

- **Deterministic analysis first** — Every result is reproducible and explainable
- **Local-first design** — Works offline after initial data fetch
- **Composable indicators** — Combine SMA, EMA, RSI in custom rules
- **Strategy packages** — First-class, versionable, portable strategy artifacts
- **Optional AI** — Get explanations, but never depend on them
