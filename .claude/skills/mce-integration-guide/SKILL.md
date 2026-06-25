# MarketContextEngine Integration Guide

**Scope:** Any task that wires `MarketContextEngine` into a new CLI command, workflow use case,
or service, OR that migrates a caller from the legacy `MarketRegimeUseCase`.

**ADR reference:** ADR-029 (commit a72f764). MCE is the third first-class engine pillar alongside
`RiskEngine` and `SignalEngine`.

---

## Canonical Construction Pattern

Copy this block verbatim when wiring MCE into a new caller. All five constructor parameters
are required for full factor coverage.

```python
from dataclasses import replace as dc_replace
from src.application.services.market_context_engine import MarketContextEngine
from src.application.services.universe_loader import resolve_tickers
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.config.market_context_config import load_market_context_config
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_context_repository import SQLiteMarketContextRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

# 1. Resolve universe BEFORE constructing — empty universe disables idx_breadth + foreign_flow
tickers = resolve_tickers(
    universe=APP_CFG.analysis.regime_universe,
    explicit=[],
    db_path=db_path,
)

# 2. Load config; apply benchmark override if the caller exposes --benchmark
cfg = load_market_context_config()
if benchmark and benchmark != cfg.idx_trend.benchmark_ticker:
    cfg = dc_replace(cfg, idx_trend=dc_replace(cfg.idx_trend, benchmark_ticker=benchmark))

# 3. Construct with all repos — context_repository enables caching/persistence
engine = MarketContextEngine(
    market_repository=SQLiteMarketRepository(db_path=db_path),
    config=cfg,
    universe=tickers,
    broker_repository=SQLiteBrokerRepository(db_path=db_path),
    context_repository=SQLiteMarketContextRepository(db_path=db_path),
)

# 4. Evaluate
context = engine.evaluate(as_of_date=as_of_date)   # returns MarketContext
```

---

## What `MarketContext` Contains

```python
@dataclass(frozen=True)
class MarketContext:
    regime: MarketRegime            # Enum: RISK_ON | NEUTRAL | RISK_OFF | VOLATILE
    conviction: float               # 0.0–1.0 weighted factor score
    factors: tuple[ContextFactor]   # per-factor detail (name, value, score, label, rationale)
    as_of_date: date
    staleness_warning: str | None   # set when last candle > 1 business day before as_of_date
    coverage_warning: str | None    # set when < threshold% of universe tickers have data
    signal_multiplier: float        # 1.0 (RISK_ON) … 0.4 (RISK_OFF)
    gate_tightening: bool           # True when regime warrants tighter gate (VOLATILE or RISK_OFF)
```

**Helpers in `view_market_context_display.py` (use these, don't re-implement):**

| Helper | Returns |
|---|---|
| `REGIME_DISPLAY_LABEL[regime.value]` | Human-readable label ("Bull Market", etc.) |
| `context_conviction_score(ctx)` | `round(ctx.conviction * 7)` — int 0–7 |
| `context_factor_value(ctx, "idx_breadth")` | float or None |
| `context_warnings(ctx)` | list of non-None warning strings |
| `context_regime_style(ctx)` | Rich color string ("green", "yellow", "red") |

**Sidecar serialization:** `context.to_dict()` returns a dict with `"regime"` key — compatible
with the sidecar JSON format read by `trade_intraday_commands.py`.

---

## MCE Vocabulary

MCE produces these regime strings — use them everywhere (config, dicts, filters):

| Value | Meaning | gate_tightening |
|---|---|---|
| `RISK_ON` | Strong bull conditions | False |
| `NEUTRAL` | Mixed / sideways | False |
| `VOLATILE` | High volatility / fear | **True** |
| `RISK_OFF` | Broad market weakness | **True** |

**Legacy vocab (MarketRegimeUseCase):** BULLISH / SIDEWAYS / WEAK / RISK_OFF — these only appear
in old sidecar files. Lookup tables (`_REGIME_TARGETS`, YAML `preset_targets`) must carry both sets.

---

## Wiring Checklist — Do All 5 Before Marking a Task Complete

- [ ] `universe=` resolved via `resolve_tickers(APP_CFG.analysis.regime_universe, ...)`
- [ ] `benchmark=` flag forwarded via `dc_replace(cfg, idx_trend=dc_replace(cfg.idx_trend, ...))`
      (only needed when the command exposes `--benchmark`)
- [ ] If `RiskEngine.assess_all_profiles()` is called, `market_context=` is passed explicitly
      (it does not share post-processing with `assess()` — see pitfalls §15)
- [ ] All string-comparison gates and filters use MCE vocab (VOLATILE, not WEAK)
- [ ] Sidecar reader validates against `_KNOWN_REGIMES` set and fails-closed to `"RISK_OFF"`

---

## Regime Gate Post-Processing

`gate_tightening=True` on `MarketContext` means the regime is VOLATILE or RISK_OFF and all
HIGH_RISK assessments should be blocked by an injected gate label.

**In `RiskEngine.assess()` / `assess_with_context()` / `assess_request()`:** handled automatically
via `_apply_regime_gate()`.

**In `RiskEngine.assess_all_profiles()`:** must pass `market_context=` explicitly. The method
applies the same logic inline since the return type (`AssessAllProfilesResponse`) differs from
`AssessRiskResponse`.

**Direct call sites that bypass `RiskEngine`:** if code calls `AssessRiskUseCase.execute()` directly
(e.g., in `SwingAnalysisWorkflowUseCase`), the regime gate is NOT applied automatically. This is
intentional — the workflow uses a raw `AssessRiskUseCase` for flexibility. For regime gate support
in new workflows, use `RiskEngine` instead.

---

## Migration from `MarketRegimeUseCase`

When replacing `MarketRegimeUseCase` calls with MCE:

1. **Replace the import** — `from ...market_regime_use_case import MarketRegimeResponse` →
   `from src.domain.value_objects.market_context import MarketContext`

2. **Replace field access** — old fields no longer exist on `MarketContext`:

   | Old `MarketRegimeResponse` | New `MarketContext` |
   |---|---|
   | `.label` (BULLISH etc.) | `.regime.value` (RISK_ON etc.) |
   | `.score` (0–7 int) | `context_conviction_score(ctx)` |
   | `.breadth_above_sma20_pct` | `context_factor_value(ctx, "idx_breadth")` |
   | `.warnings` (list) | `context_warnings(ctx)` |
   | `.foreign_flow_breadth_pct` | not equivalent — drop from compact display |
   | `.benchmark_return_20d_pct` | not equivalent — drop from compact display |

3. **Update sidecar format** — old sidecar key was `"label"`; new key is `"regime"`. Reader should
   handle both: `raw = d.get("regime") or d.get("label")`.

4. **Update the contract test** — add `"market_regime_use_case"` and `"market_regime_use_case.py"`
   to `REMOVED_SOURCE_REFERENCE_PATTERNS` in `tests/adapters/cli/test_command_contract.py`.

5. **Grep all vocab sites** — search for `BULLISH`, `SIDEWAYS`, `WEAK` across `src/`, `config/`,
   `tests/` and update to MCE vocab before closing the PR.
