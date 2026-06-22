"""
Application-wide defaults — loaded from config/default.yaml, overlaid by config/user.yaml.

Priority (highest wins):
  CLI flag  >  config/user.yaml  >  config/default.yaml  >  dataclass fallbacks

Edit config/default.yaml to change shipped IDX defaults.
Edit config/user.yaml (gitignored) to override with personal preferences.
Pass a CLI flag to override for a single run.

Layer: Infrastructure
"""

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml

_PROJECT_ROOT = Path(__file__).parents[3]
_DEFAULT_PATH = _PROJECT_ROOT / "config" / "default.yaml"
_USER_PATH = _PROJECT_ROOT / "config" / "user.yaml"


# ── Sub-configs ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MarketConfig:
    provider: str = "yahoo"
    suffix: str = ".JK"
    default_days: int = 365


@dataclass(frozen=True)
class StorageConfig:
    db_path: str = "data.db"
    accum_journal: str = "journals/accumulation.csv"
    trade_journal: str = "journals/trades.jsonl"
    stockbit_profile_dir: str = ".stockbit_profile"
    stockbit_session_file: str = "stockbit_session.json"
    intraday_sidecar: str = "journals/.last-session.json"
    intraday_confirmation: str = "journals/.last-confirmation.json"
    intraday_confirmation_journal: str = "journals/intraday-confirmations.csv"
    opening_data_dir: str = "data/opening"
    pre_open_config: str = "config/pre_open_screener.yaml"
    swing_config: str = "config/swing_screener.yaml"


@dataclass(frozen=True)
class BrokerConfig:
    provider: str = "idx"
    default_days: int = 30


@dataclass(frozen=True)
class AnalysisConfig:
    risk_profile: str = "balanced"
    benchmark: str = "^JKSE"
    universe: str = "lq45"
    regime_universe: str = "idx80"
    format: str = "table"


@dataclass(frozen=True)
class TradingConfig:
    capital: int = 100_000_000
    risk_pct: float = 1.0


@dataclass(frozen=True)
class SwingDefaults:
    window: int = 7
    take_profit: float = 5.0
    stop_loss: float = 5.0
    max_hold: int = 10
    atr_mult: float = 1.5
    rr: float = 2.0
    min_score: float = 70.0
    capital: int | None = None  # personal capital — set in user.yaml; None disables position sizing
    risk_pct: float = 1.0


@dataclass(frozen=True)
class BacktestConfig:
    start_date: str = "2026-01-01"
    cost_bps: float = 20.0


@dataclass(frozen=True)
class FetchConfig:
    default_days: int = 90          # fetch window (distinct from analysis default_days)
    meta_ttl_days: int = 30         # stock-meta cache freshness (days)
    start_tolerance_days: int = 7   # acceptable gap at start of a cached date range
    end_tolerance_days: int = 7     # acceptable gap at end of a cached date range


@dataclass(frozen=True)
class AiConfig:
    enabled: bool = False
    provider: str = "deepseek"  # deepseek | claude | openai | gemini | ollama


@dataclass(frozen=True)
class AppConfig:
    market: MarketConfig = field(default_factory=MarketConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    broker: BrokerConfig = field(default_factory=BrokerConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    swing: SwingDefaults = field(default_factory=SwingDefaults)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    fetch: FetchConfig = field(default_factory=FetchConfig)
    ai: AiConfig = field(default_factory=AiConfig)


# ── Loader ─────────────────────────────────────────────────────────────────

def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. override wins on conflicts."""
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def _read_yaml(path: Path, *, optional: bool = False) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except FileNotFoundError:
        if optional:
            return {}
        raise
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {path}: {e}") from e


def _build(section: dict, cls: type) -> Any:
    """Construct a frozen dataclass from a dict, ignoring unknown keys."""
    known = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in section.items() if k in known})


def load_app_config() -> AppConfig:
    base = _read_yaml(_DEFAULT_PATH)
    user = _read_yaml(_USER_PATH, optional=True)
    cfg = _deep_merge(base, user)

    return AppConfig(
        market=_build(cfg.get("market", {}), MarketConfig),
        storage=_build(cfg.get("storage", {}), StorageConfig),
        broker=_build(cfg.get("broker", {}), BrokerConfig),
        analysis=_build(cfg.get("analysis", {}), AnalysisConfig),
        trading=_build(cfg.get("trading", {}), TradingConfig),
        swing=_build(cfg.get("swing", {}), SwingDefaults),
        backtest=_build(cfg.get("backtest", {}), BacktestConfig),
        fetch=_build(cfg.get("fetch", {}), FetchConfig),
        ai=_build(cfg.get("ai", {}), AiConfig),
    )


APP_CFG: AppConfig = load_app_config()
