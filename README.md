# Stock Analysis CLI (Local-First)

## Overview

This project is a **local-first, production-grade CLI application for stock analysis**.

It is designed to be:

* Deterministic and reproducible
* Useful without AI by default
* Extensible to AI-enhanced analysis
* Easy to install and run
* Portable to bots, web, and mobile interfaces

The initial market focus is **Indonesia Stock Exchange (IDX)**, with a clear path to global markets.

---

## What This Project Is

* A **stock analysis tool**, not a trading bot
* Rule-based by default (technical indicators, deterministic logic)
* Offline-first (no cloud services required to start)
* Architected with **Hexagonal (Ports & Adapters)** principles
* Designed for auditability and long-term maintainability

---

## What This Project Is NOT

* ❌ An automated trading or execution system
* ❌ An AI-only or black-box analyzer
* ❌ A real-time, high-frequency trading platform
* ❌ Dependent on external APIs or internet access

---

## Key Design Principles

* **Local-first**: runs fully offline by default
* **Deterministic core**: same input + config → same output
* **AI as optional advisor**: OFF by default, never the sole decision maker
* **Clear separation of concerns**: domain logic is pure and framework-agnostic

---

## High-Level Architecture

```
Domain (pure logic)
  ├─ Analysis & Rules
  ├─ Models
  └─ Ports (interfaces)

Adapters
  ├─ CLI
  ├─ Market Data Providers
  ├─ Storage (SQLite / DuckDB)
  └─ AI (optional)
```

External systems never leak into the domain.

---

## Installation

Requires Python 3.11+.

```bash
# Clone the repository
git clone <repository-url>
cd ai-saham

# Install dependencies
pip install -e .

# Or with development dependencies
pip install -e ".[dev]"
```

---

## Usage

### Fetch Market Data

Fetch daily OHLCV data for an IDX stock ticker:

```bash
# Basic usage - fetches 1 year of data
saham fetch BBCA

# Fetch 2 years of data
saham fetch BBRI --days 730

# Force refresh (bypass cache)
saham fetch TLKM --refresh

# Custom database location
saham fetch ASII --db /path/to/custom.db
```

### Calculate SMA (Simple Moving Average)

Calculate SMA over cached market data:

```bash
# Basic usage - SMA(20) on close prices
saham sma BBCA

# Custom period
saham sma BBRI --period 50

# Different price field
saham sma TLKM --period 20 --field open

# Analyze more history
saham sma ASII --period 200 --days 730
```

**Options:**
- `--period, -p`: SMA period (default: 20)
- `--field, -f`: Price field - open/high/low/close (default: close)
- `--days, -d`: Days of history to analyze (default: 365)

**Note:** Requires cached data. Run `saham fetch <TICKER>` first.

### Calculate EMA (Exponential Moving Average)

Calculate EMA over cached market data with professional-grade SMA-seeded initialization:

```bash
# Basic usage - EMA(20) on close prices
saham ema BBCA

# Custom period
saham ema BBRI --period 50

# Different price field
saham ema TLKM --period 12 --field high

# Analyze more history
saham ema ASII --period 200 --days 730
```

**Options:**
- `--period, -p`: EMA period (default: 20)
- `--field, -f`: Price field - open/high/low/close (default: close)
- `--days, -d`: Days of history to display (default: 365)

**Implementation Details:**
- Uses SMA-seeded initialization (matches TradingView, Bloomberg, TA-Lib)
- Smoothing multiplier: k = 2 / (period + 1)
- Warm-up buffer handling ensures converged values (2× period)

**Note:** Requires cached data. Run `saham fetch <TICKER>` first.

### How Caching Works

1. **First run**: Data is fetched from Yahoo Finance and cached locally
2. **Subsequent runs**: Data is served from local cache (fast, offline)
3. **With `--refresh`**: Cache is bypassed and fresh data is fetched

Data is stored in `~/.ai-saham/data.db` by default.

---

## Configuration

Default settings in `config/default.yaml`:

| Setting | Default | Description |
|---------|---------|-------------|
| `market.suffix` | `.JK` | Ticker suffix for IDX |
| `market.default_days` | `365` | Default history to fetch |
| `storage.db_path` | `~/.ai-saham/data.db` | SQLite database path |
| `ai.enabled` | `false` | AI features (future) |

---

## Limitations

* **Daily data only** - no intraday or real-time streaming
* **IDX market only** - designed for Indonesia Stock Exchange
* **Yahoo Finance** - data may be delayed; unofficial source
* **Internet required** for first fetch (offline after caching)
* **Indicator partial results** - SMA/EMA values start after `period` candles are available

---

## Development Philosophy

* Build vertical slices
* Prefer clarity over cleverness
* Test domain logic
* Avoid premature optimization
* If AI disappears tomorrow, the system must still be valuable

---

## AI Development Notes

This repository is developed with AI assistance.

Agent behavior is governed by:

* `CLAUDE.md` – architectural authority
* `GEMINI.md` – implementation assistance
* `CURSOR.md` – editor-level pair programming

These files are part of the system design.

---

## License

License to be determined.
