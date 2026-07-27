# ADR-029: Market Context Engine (MCE) — Third First-Class Application Service

[Architecture decision index](../../ARCHITECTURE_DECISIONS.md)
**Status:** Accepted
**Date:** 2026-06-24
**Current implementation:** MCE is a first-class deterministic application service with config-backed evaluation and persistence. ADR-037 governs its canonical use in signal construction.

---

### Context

ADR-024 introduced SignalEngine and RiskEngine as first-class application services. Neither answered the macro question: *"Is the environment favorable right now?"* ADR-026 stated that gate thresholds should tighten based on `market_regime`, but left the mechanism unimplemented.

The existing `MarketRegimeUseCase` (7 binary 0/1 signals, IDX-internal only, no weighting) was too crude — a single bad candle could flip the signal, and the scores carried no graded information. It was replaced in full.

---

### Decision

**MCE is the third first-class engine pillar**, parallel to SignalEngine and RiskEngine.

| Property | SignalEngine | RiskEngine | **MarketContextEngine** |
|----------|-------------|------------|------------------------|
| Input | Per-stock enrichment | Per-stock gates | Cross-market + IDX breadth |
| Output | `AssessSignalResponse` | `AssessRiskResponse` | `MarketContext` |
| Layer | Application | Application | Application |
| Config | `signal_engine.yaml` | rule YAML | `market_context_engine.yaml` |
| Persistence | No | No | `market_context_snapshots` |

---

### Key Decisions

#### 1. MarketRegimeUseCase is superseded for user-facing regime analysis
The old 7-signal binary use case is no longer the implementation behind `saham analyze regime`. `MarketContextEngine` delegates to `BuildMarketContextUseCase` — pure computation with no IO. The engine owns all fetching for the current regime command. Legacy callers may still exist until migrated.

#### 2. Continuous 0.0–1.0 factor scoring, not binary
Each factor is scored on a continuous scale using piecewise linear interpolation. Unavailable/disabled factors are excluded and the remaining weights renormalize to 1.0 (same pattern as `AssessSignalUseCase`).

**Factors (Phase 1–2):**

| Factor | Source | Signal |
|--------|--------|--------|
| `vix` | `^VIX` candles | Global risk appetite |
| `eido` | `EIDO` vs IHSG 5d divergence | Foreign institutional view on Indonesia |
| `usd_idr` | `IDR=X` 5d % change | Rupiah pressure / capital flow |
| `idx_trend` | `^JKSE` % from SMA50 | IHSG momentum |
| `idx_breadth` | Universe % above SMA20 | Market-wide participation |
| `foreign_flow` | `BrokerDataRepository` aggregated net buy | Domestic foreign capital direction |

**Optional (off by default):** `commodity_composite` (CPO + coal).

#### 3. Output contract: `MarketContext`
```python
@dataclass(frozen=True)
class MarketContext:
    regime: MarketRegime           # RISK_ON | NEUTRAL | RISK_OFF | VOLATILE
    conviction: float              # weighted composite 0.0–1.0
    factors: tuple[ContextFactor, ...]
    signal_multiplier: float       # 0.50–1.0; consumed by SignalEngine
    gate_tightening: bool          # True → RiskEngine adds regime gate for HIGH_RISK
    as_of_date: date
    staleness_warning: str | None
    coverage_warning: str | None
```

#### 4. Integration contract (Phase 4)
Both downstream engines accept an optional `market_context` parameter:

- **SignalEngine**: `score × signal_multiplier`; ENTER→WATCH when `gate_tightening=True`; regime note appended to rationale.
- **RiskEngine**: when `gate_tightening=True` and assessment is `HIGH_RISK`, `gate_triggered = "regime:{REGIME_NAME}"` is set.

Neither engine is broken without `market_context` — it is always optional.

#### 5. Fetch via existing `saham fetch market`
Global context tickers (`^VIX`, `EIDO`, `IDR=X`) are fetched by `_fetch_global_context_tickers()` appended to `fetch_market_commands.py`. Uses `YahooFinanceProvider(market_suffix="")` — critical: the default provider appends `.JK` for IDX stocks; global tickers must bypass this. No new tables; candles go into the existing `market_data` SQLite table.

#### 6. CLI: `saham inspect regime` — documented 3-word exception
Second 3-word exception (after `saham view broker`, ADR-018). Rationale: MCE has multiple display modes (summary, verbose factor breakdown) requiring a sub-group. This exception is explicitly documented here to prevent undocumented proliferation.

`saham analyze regime` is preserved and now powered by MCE (richer output).

#### 7. Config ownership
All factor thresholds, score-label thresholds, fallback scoring policy, warning thresholds, normalization bounds, and regime effects live in `config/market_context_engine.yaml`. Each factor has `enabled: bool` and tunable thresholds — the ADR-027 learning loop can propose YAML diffs to tune thresholds without code changes.

#### 8. Persistence (Phase 5)
`SQLiteMarketContextRepository` stores one canonical snapshot per `as_of_date` (`INSERT OR REPLACE`). Factors serialized as JSON. The `MarketContextEngine` saves silently after every `evaluate()` call (failures are debug-logged, never raised — persistence is best-effort). `get_snapshot()` and `get_recent_snapshots()` allow the learning loop to replay past regime decisions.

---

### Layer Plan

| Layer | Artifact |
|-------|---------|
| Domain | `market_context.py` (value objects: `MarketContext`, `MarketRegime`, `ContextFactor`) |
| Domain (Port) | `market_context_repository.py` (Protocol) |
| Application | `build_market_context_use_case.py` (pure computation) |
| Application | `market_context_engine.py` (service — fetches, computes, persists) |
| Infrastructure | `market_context_config.py` (YAML loader + frozen dataclasses) |
| Infrastructure | `sqlite_market_context_repository.py` (SQLite persistence) |
| Adapter | `view_market_context_commands.py`, `view_market_context_display.py` |
| Adapter | `analyze_regime_commands.py` (updated to delegate to MCE) |
| Adapter | `fetch_market_commands.py` (extended: `_fetch_global_context_tickers`) |

---

### Non-Decisions

- **MarketRegimeUseCase** is kept for legacy callers (pre-open workflow, swing analysis, backtest, daily briefing). These callers migrate to MCE in a future phase; the old use case is not removed until all callers are migrated.
- `saham inspect regime` does not have a `--history` subcommand yet; `get_recent_snapshots()` is infrastructure-ready for a future `saham inspect regime history` command.
