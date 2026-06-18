"""
CLI commands for the swing trade command family.

Commands (all under `saham swing`):
  saham swing analyze TICKER   — unified 5-section composite view
  saham swing size    TICKER   — ATR-based position sizing calculator
  saham swing backtest         — portfolio walk-forward backtest
  saham swing compare          — compare variants across market regimes
  saham swing screen           — accumulation screener (find candidates)
  saham swing audit            — audit accumulation broker data
  saham swing log              — log a candidate to the journal
  saham swing review           — review journal performance

Top-level:
  saham regime                 — market regime (standalone)

Layer: Adapter
"""

import json
import logging
from contextlib import contextmanager, nullcontext, redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
from typing import Annotated, Optional

import yaml

import typer

from src.application.rules.exceptions import StrategyNotFoundError
from src.application.services.bootstrap import create_indicator_registry
from src.application.services.position_sizer import (
    PercentSizingResult,
    SizingResult,
    compute_percent_position_size,
    compute_position_size,
)
from src.application.services.strategy_loader import StrategyLoader
from src.application.services.universe_loader import (
    UniverseNotFoundError,
    resolve_tickers,
)
from src.application.use_case.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenRequest,
    AccumulationScreenUseCase,
)
from src.application.use_case.assess_risk import AssessRiskRequest, AssessRiskUseCase
from src.application.use_case.backtest import BacktestRequest, BacktestUseCase
from src.application.use_case.fetch_sentiment import (
    FetchSentimentRequest,
    FetchSentimentUseCase,
)
from src.application.use_case.market_regime import (
    MarketRegimeRequest,
    MarketRegimeResponse,
    MarketRegimeUseCase,
)
from src.application.use_case.swing_backtest import (
    DEFAULT_SWING_COST_BPS,
    FOREIGN_BOUNCE_PRESET as BACKTEST_FOREIGN_BOUNCE_PRESET,
)
from src.application.use_case.swing_backtest import (
    SwingBacktestRequest,
    SwingBacktestResponse,
    SwingBacktestUseCase,
)
from src.application.use_case.accumulation_screen import resolve_preset_targets
from src.infrastructure.config.user_config import get_swing_default
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository
from src.infrastructure.sentiment import SentimentFactory
from src.infrastructure.browser.stockbit_analyst import StockbitAnalystConsensusProvider
from src.infrastructure.browser.stockbit_bandar import StockbitBandarDetectorProvider
from src.infrastructure.browser.stockbit_corp_action import StockbitCorporateActionRepository
from src.infrastructure.browser.stockbit_insider import StockbitInsiderActivityProvider
from src.infrastructure.browser.stockbit_seasonality import StockbitSeasonalityProvider
from src.infrastructure.browser.stockbit_shareholding import StockbitShareholdingProvider

DEFAULT_DB_PATH = Path("data.db")
_W = 70  # display width

FOREIGN_BOUNCE_PRESET = "foreign-bounce"
FOREIGN_BOUNCE_MAX_HOLD_DAYS = 10

# Legacy constants kept for backtest use — actual analyze/screen uses resolve_preset_targets()
FOREIGN_BOUNCE_TAKE_PROFIT = Decimal("5")
FOREIGN_BOUNCE_STOP_LOSS = Decimal("5")

_SWING_SCREENER_CONFIG_PATH = Path("config/swing_screener.yaml")


def _load_swing_screener_config() -> dict:
    """Load swing_screener.yaml if it exists; return empty dict on missing file."""
    try:
        import yaml
        with open(_SWING_SCREENER_CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}

SWING_COMPARE_VARIANTS: dict[str, tuple[str, ...]] = {
    "baseline": (),
    "sideways_only": ("SIDEWAYS", "BULLISH"),
    "weak_plus": ("WEAK", "SIDEWAYS", "BULLISH"),
}

# _SwingConfig and loader live in infrastructure to avoid circular imports.
from src.infrastructure.config.swing_config import SwingConfig as _SwingConfig  # noqa: E402
from src.infrastructure.config.swing_config import load_swing_config as _load_swing_screener_config_typed  # noqa: E402


# Load from config/swing_screener.yaml; fall back to _SwingConfig defaults on any error.
_SC = _load_swing_screener_config_typed()

SMART_MONEY_BROKERS = set(_SC.smart_money_brokers)
NOISE_BROKERS       = set(_SC.noise_brokers)


def _make_stockbit_providers(db_path: Path) -> "StockbitProviders":
    """Return all Stockbit providers sharing one authenticated session."""
    from src.adapters.cli.accumulation_commands import StockbitProviders
    try:
        from src.infrastructure.browser.playwright_stockbit import StockbitPlaywrightBrokerProvider
        provider = StockbitPlaywrightBrokerProvider()
        if not provider.is_authenticated():
            return StockbitProviders.unavailable()
        return StockbitProviders(
            corp_repo=StockbitCorporateActionRepository(broker_provider=provider, db_path=db_path),
            season_prov=StockbitSeasonalityProvider(broker_provider=provider),
            insider_prov=StockbitInsiderActivityProvider(broker_provider=provider),
            analyst_prov=StockbitAnalystConsensusProvider(broker_provider=provider),
            shareholding_prov=StockbitShareholdingProvider(broker_provider=provider, db_path=db_path),
            bandar_prov=StockbitBandarDetectorProvider(broker_provider=provider, db_path=db_path),
        )
    except Exception:
        return StockbitProviders.unavailable()
BROKER_WEIGHTS: dict[str, Decimal] = {
    **{code: _SC.smart_weight for code in SMART_MONEY_BROKERS},
    **{code: _SC.noise_weight for code in NOISE_BROKERS},
}


@dataclass(frozen=True)
class PresetGate:
    label: str
    passed: bool
    actual: str
    required: str


@dataclass(frozen=True)
class PresetEvaluation:
    name: str
    passed: bool
    classification: str
    gates: tuple[PresetGate, ...]
    failed_reasons: tuple[str, ...]


@dataclass(frozen=True)
class BrokerQualityNote:
    """Non-authoritative named-broker confirmation note for preset review."""

    level: str
    message: str

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "message": self.message,
        }


@dataclass(frozen=True)
class DataFreshness:
    """Cached source data dates used by a swing analysis run."""

    as_of_date: date
    candle_start: date | None
    candle_end: date | None
    broker_start: date | None
    broker_end: date | None
    warnings: tuple[str, ...]
    refresh_actions: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "as_of_date": self.as_of_date.isoformat(),
            "candles_from": self.candle_start.isoformat() if self.candle_start else None,
            "candles_through": self.candle_end.isoformat() if self.candle_end else None,
            "broker_flow_from": self.broker_start.isoformat() if self.broker_start else None,
            "broker_flow_through": self.broker_end.isoformat() if self.broker_end else None,
            "refresh_actions": list(self.refresh_actions),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class FlowDetail:
    """Broker-flow detail for the current ticker over recent broker sessions."""

    window_sessions: int
    available_sessions: int
    from_date: date | None
    through_date: date | None
    total_net_flow: Decimal
    buy_sessions: int
    sell_sessions: int
    consecutive_buy_sessions: int
    avg_flow_ratio_pct: float | None
    latest_net_flow: Decimal | None
    latest_flow_ratio_pct: float | None
    latest_date: date | None

    def to_dict(self) -> dict:
        return {
            "window_sessions": self.window_sessions,
            "available_sessions": self.available_sessions,
            "from": self.from_date.isoformat() if self.from_date else None,
            "through": self.through_date.isoformat() if self.through_date else None,
            "total_net_flow": str(self.total_net_flow),
            "buy_sessions": self.buy_sessions,
            "sell_sessions": self.sell_sessions,
            "consecutive_buy_sessions": self.consecutive_buy_sessions,
            "avg_flow_ratio_pct": self.avg_flow_ratio_pct,
            "latest_net_flow": (
                str(self.latest_net_flow) if self.latest_net_flow is not None else None
            ),
            "latest_flow_ratio_pct": self.latest_flow_ratio_pct,
            "latest_date": self.latest_date.isoformat() if self.latest_date else None,
        }


@dataclass(frozen=True)
class BrokerDetailLine:
    broker_code: str
    broker_name: str
    broker_type: str
    net_value: Decimal
    active_sessions: int

    def to_dict(self) -> dict:
        return {
            "broker_code": self.broker_code,
            "broker_name": self.broker_name,
            "broker_type": self.broker_type,
            "net_value": str(self.net_value),
            "active_sessions": self.active_sessions,
        }


@dataclass(frozen=True)
class BrokerDetail:
    """Named broker confirmation context from Stockbit-style broker summaries."""

    window_sessions: int
    detail_sessions: int
    through_date: date
    source: str
    top_buyers: tuple[BrokerDetailLine, ...]
    top_sellers: tuple[BrokerDetailLine, ...]
    top_buyer_share_pct: float | None
    top_seller_share_pct: float | None
    smart_flow: Decimal
    noise_flow: Decimal
    neutral_flow: Decimal
    weighted_net_flow: Decimal
    smart_share_pct: float | None
    broker_weight_quality: str
    quality: str

    def to_dict(self) -> dict:
        return {
            "window_sessions": self.window_sessions,
            "detail_sessions": self.detail_sessions,
            "through": self.through_date.isoformat(),
            "source": self.source,
            "top_buyers": [row.to_dict() for row in self.top_buyers],
            "top_sellers": [row.to_dict() for row in self.top_sellers],
            "top_buyer_share_pct": self.top_buyer_share_pct,
            "top_seller_share_pct": self.top_seller_share_pct,
            "smart_flow": str(self.smart_flow),
            "noise_flow": str(self.noise_flow),
            "neutral_flow": str(self.neutral_flow),
            "weighted_net_flow": str(self.weighted_net_flow),
            "smart_share_pct": self.smart_share_pct,
            "broker_weight_quality": self.broker_weight_quality,
            "quality": self.quality,
        }


# ─── formatting helpers ──────────────────────────────────────────────────────

def _style_risk(level: str) -> str:
    if level == "LOW_RISK":
        return typer.style(level, fg=typer.colors.GREEN, bold=True)
    if level == "HIGH_RISK":
        return typer.style(level, fg=typer.colors.RED, bold=True)
    return typer.style(level, fg=typer.colors.YELLOW, bold=True)


def _style_trend(trend: str) -> str:
    if trend == "UP":
        return typer.style(trend, fg=typer.colors.GREEN)
    if trend == "DOWN":
        return typer.style(trend, fg=typer.colors.RED)
    return typer.style(trend, fg=typer.colors.YELLOW)


def _style_sentiment_call(call: str) -> str:
    if call == "POSITIVE":
        return typer.style(call, fg=typer.colors.GREEN, bold=True)
    if call == "NEGATIVE":
        return typer.style(call, fg=typer.colors.RED, bold=True)
    return typer.style(call, fg=typer.colors.YELLOW, bold=True)


def _style_score(s: float) -> str:
    if s >= _SC.enter_min_score:
        return typer.style(f"{s:.1f}", fg=typer.colors.GREEN, bold=True)
    if s >= _SC.watch_min_score:
        return typer.style(f"{s:.1f}", fg=typer.colors.YELLOW)
    return typer.style(f"{s:.1f}", fg=typer.colors.WHITE)


def _style_bb(pctile: float) -> str:
    pct_int = int(pctile * 100)
    if pctile <= 0.20:
        return typer.style(f"{pct_int}%", fg=typer.colors.GREEN)
    if pctile <= 0.40:
        return typer.style(f"{pct_int}%", fg=typer.colors.YELLOW)
    return f"{pct_int}%"


def _style_winrate(wr: Decimal) -> str:
    v = float(wr)
    if v >= 55:
        return typer.style(f"{v:.1f}%", fg=typer.colors.GREEN)
    if v >= 45:
        return typer.style(f"{v:.1f}%", fg=typer.colors.YELLOW)
    return typer.style(f"{v:.1f}%", fg=typer.colors.RED)


def _sep(char: str = "=") -> None:
    typer.echo(char * _W)


def _section_header(title: str, right: str = "") -> None:
    styled = typer.style(title, bold=True)
    if right:
        gap = max(1, _W - len(title) - len(right) - 2)
        typer.echo(f"{styled}{' ' * gap}{right}")
    else:
        typer.echo(styled)


def _signal_label(c: AccumulationCandidate) -> str:
    if c.bb_width_pctile is not None and c.bb_width_pctile <= _SC.coiled_spring_bb_pctile and c.score >= _SC.coiled_spring_min_score:
        return "coiled spring"
    if c.score >= _SC.strong_min_score and c.consecutive_streak >= _SC.strong_min_streak:
        return "strong"
    if c.score >= _SC.building_min_score and c.consecutive_streak >= _SC.building_min_streak:
        return "building"
    if c.score >= _SC.enter_min_score:
        return "high score"
    if c.score >= _SC.watch_min_score:
        return "moderate"
    return "weak"


def _fmt_optional_float(value: float | None, suffix: str = "") -> str:
    return "missing" if value is None else f"{value:.1f}{suffix}"


def _evaluate_foreign_bounce(
    accum: AccumulationCandidate | None,
) -> PresetEvaluation:
    """Evaluate audited foreign-bounce gates for one accumulation candidate."""
    if accum is None:
        return PresetEvaluation(
            name=FOREIGN_BOUNCE_PRESET,
            passed=False,
            classification="AVOID",
            gates=(
                PresetGate(
                    label="broker flow data",
                    passed=False,
                    actual="missing",
                    required="available",
                ),
            ),
            failed_reasons=("No accumulation/broker-flow candidate available",),
        )

    gates = (
        PresetGate(
            label="score",
            passed=accum.score >= _SC.gate_min_score,
            actual=f"{accum.score:.1f}",
            required=f">= {_SC.gate_min_score:.0f}",
        ),
        PresetGate(
            label="fvwap%",
            passed=accum.vwap_discount_pct is not None and accum.vwap_discount_pct >= _SC.gate_min_vwap_discount_pct,
            actual=_fmt_optional_float(accum.vwap_discount_pct, "%"),
            required=f">= +{_SC.gate_min_vwap_discount_pct:.0f}%",
        ),
        PresetGate(
            label="trend",
            passed=accum.trend == _SC.gate_required_trend,
            actual=accum.trend,
            required=_SC.gate_required_trend,
        ),
        PresetGate(
            label="flow_pct",
            passed=accum.avg_flow_ratio is not None and accum.avg_flow_ratio >= _SC.gate_min_flow_ratio_pct,
            actual=_fmt_optional_float(accum.avg_flow_ratio, "%"),
            required=f">= +{_SC.gate_min_flow_ratio_pct:.0f}%",
        ),
        PresetGate(
            label="RSI present",
            passed=accum.rsi is not None,
            actual=_fmt_optional_float(accum.rsi),
            required="present",
        ),
        PresetGate(
            label="RSI",
            passed=accum.rsi is not None and accum.rsi <= _SC.gate_max_rsi,
            actual=_fmt_optional_float(accum.rsi),
            required=f"<= {_SC.gate_max_rsi:.0f}",
        ),
    )
    failed = tuple(
        f"{gate.label}: {gate.actual} (required {gate.required})"
        for gate in gates
        if not gate.passed
    )
    passed = not failed
    if passed:
        classification = "ENTER"
    elif accum.score >= _SC.gate_min_score or len(failed) <= _SC.watch_max_failed_gates:
        classification = "WATCH"
    else:
        classification = "AVOID"

    return PresetEvaluation(
        name=FOREIGN_BOUNCE_PRESET,
        passed=passed,
        classification=classification,
        gates=gates,
        failed_reasons=failed,
    )


def _style_gate(passed: bool) -> str:
    label = "PASS" if passed else "FAIL"
    color = typer.colors.GREEN if passed else typer.colors.RED
    return typer.style(label, fg=color, bold=True)


def _style_classification(value: str) -> str:
    if value == "ENTER":
        return typer.style(value, fg=typer.colors.GREEN, bold=True)
    if value == "WATCH":
        return typer.style(value, fg=typer.colors.YELLOW, bold=True)
    return typer.style(value, fg=typer.colors.RED, bold=True)


def _format_failed_gates_summary(preset_eval: PresetEvaluation) -> str:
    return "Failed gates: " + "; ".join(preset_eval.failed_reasons)


def _build_broker_quality_note(
    broker_detail: BrokerDetail | None,
    preset_eval: PresetEvaluation | None,
) -> BrokerQualityNote | None:
    """Build a display-only broker-quality note without changing preset gates."""
    if broker_detail is None or preset_eval is None:
        return None

    smart_flow = broker_detail.smart_flow
    noise_flow = broker_detail.noise_flow
    quality = broker_detail.broker_weight_quality

    if smart_flow < Decimal("0"):
        return BrokerQualityNote(
            level="warning",
            message=(
                "Broker quality warning: smart-money selling conflicts with "
                "the accumulation setup."
            ),
        )

    if preset_eval.classification == "ENTER" and (
        quality == "noisy accumulation"
        or (noise_flow > Decimal("0") and noise_flow > smart_flow)
    ):
        return BrokerQualityNote(
            level="warning",
            message=(
                "Broker quality warning: accumulation is noise-led; require "
                "stronger chart confirmation."
            ),
        )

    if preset_eval.classification == "WATCH" and smart_flow > Decimal("0"):
        return BrokerQualityNote(
            level="support",
            message=(
                "Broker quality support: smart-money buying supports "
                "watchlist priority."
            ),
        )

    if preset_eval.classification == "ENTER" and smart_flow > Decimal("0"):
        return BrokerQualityNote(
            level="support",
            message=(
                "Broker quality support: smart-money buying confirms the "
                "preset setup."
            ),
        )

    return None


def _fmt_pct(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "N/A"
    return f"{value:+.2f}%" if signed else f"{value:.1f}%"


def _fmt_date(value: date | None) -> str:
    return value.isoformat() if value else "missing"


def _fmt_money_short(value: Decimal) -> str:
    abs_value = abs(value)
    if abs_value >= Decimal("1000000000000"):
        return f"{value / Decimal('1000000000000'):.2f}T"
    if abs_value >= Decimal("1000000000"):
        return f"{value / Decimal('1000000000'):.2f}B"
    if abs_value >= Decimal("1000000"):
        return f"{value / Decimal('1000000'):.2f}M"
    if abs_value >= Decimal("1000"):
        return f"{value / Decimal('1000'):.2f}K"
    return f"{value:.2f}"


def _fmt_money_short_signed(value: Decimal) -> str:
    sign = "+" if value > Decimal("0") else ""
    return f"{sign}{_fmt_money_short(value)}"


def _fmt_broker_detail_lines(lines: tuple[BrokerDetailLine, ...]) -> str:
    if not lines:
        return "none"
    parts = []
    for line in lines[:3]:
        parts.append(
            f"{line.broker_code} {_fmt_money_short(line.net_value)} "
            f"({line.active_sessions}s)"
        )
    return ", ".join(parts)


def _expected_weekday_data_date(as_of_date: date) -> date:
    """Latest regular weekday session expected for a given analysis date."""
    if as_of_date.weekday() == 5:  # Saturday
        return as_of_date - timedelta(days=1)
    if as_of_date.weekday() == 6:  # Sunday
        return as_of_date - timedelta(days=2)
    return as_of_date


def _weekday_session_lag(latest: date | None, as_of_date: date) -> int | None:
    """Count regular weekday sessions from latest data through expected date."""
    if latest is None:
        return None
    expected = _expected_weekday_data_date(as_of_date)
    if latest >= expected:
        return 0
    current = latest + timedelta(days=1)
    lag = 0
    while current <= expected:
        if current.weekday() < 5:
            lag += 1
        current += timedelta(days=1)
    return lag


def _build_data_freshness(
    ticker: str,
    as_of_date: date,
    market_repo: SQLiteMarketRepository,
    broker_repo: SQLiteBrokerRepository,
    refresh_actions: tuple[str, ...] = (),
) -> DataFreshness:
    candle_range = market_repo.get_date_range(ticker)
    broker_range = broker_repo.get_date_range(ticker)
    candle_start, candle_end = candle_range if candle_range else (None, None)
    broker_start, broker_end = broker_range if broker_range else (None, None)

    warnings: list[str] = []
    if candle_end is None:
        warnings.append(f"No cached candle data for {ticker}.")
    else:
        lag = _weekday_session_lag(candle_end, as_of_date)
        if lag and lag > 0:
            warnings.append(
                f"Latest candle is {lag} trading session(s) before expected data date "
                f"({_expected_weekday_data_date(as_of_date)})."
            )

    if broker_end is None:
        warnings.append(f"No cached broker flow data for {ticker}.")
    else:
        lag = _weekday_session_lag(broker_end, as_of_date)
        if lag and lag > 0:
            warnings.append(
                f"Latest broker flow is {lag} trading session(s) before expected data date "
                f"({_expected_weekday_data_date(as_of_date)})."
            )

    if candle_end and broker_end and candle_end != broker_end:
        warnings.append(
            f"Candle date ({candle_end}) and broker flow date ({broker_end}) differ."
        )
    for action in refresh_actions:
        if "ERR:" in action:
            warnings.append(f"Refresh issue: {action}")

    return DataFreshness(
        as_of_date=as_of_date,
        candle_start=candle_start,
        candle_end=candle_end,
        broker_start=broker_start,
        broker_end=broker_end,
        warnings=tuple(warnings),
        refresh_actions=refresh_actions,
    )


def _build_flow_detail(
    ticker: str,
    broker_repo: SQLiteBrokerRepository,
    window_sessions: int,
    as_of_date: date,
) -> FlowDetail | None:
    summaries = broker_repo.get_broker_summaries(ticker, end_date=as_of_date)
    summaries = summaries[-window_sessions:]
    if not summaries:
        return None

    total_net_flow = sum(
        (summary.foreign_net_value for summary in summaries),
        Decimal("0"),
    )
    buy_sessions = sum(1 for summary in summaries if summary.is_foreign_accumulating)
    sell_sessions = len(summaries) - buy_sessions

    consecutive_buy_sessions = 0
    for summary in reversed(summaries):
        if summary.is_foreign_accumulating:
            consecutive_buy_sessions += 1
        else:
            break

    ratios = [float(summary.foreign_flow_ratio) for summary in summaries]
    latest = summaries[-1]
    return FlowDetail(
        window_sessions=window_sessions,
        available_sessions=len(summaries),
        from_date=summaries[0].date,
        through_date=latest.date,
        total_net_flow=total_net_flow,
        buy_sessions=buy_sessions,
        sell_sessions=sell_sessions,
        consecutive_buy_sessions=consecutive_buy_sessions,
        avg_flow_ratio_pct=(sum(ratios) / len(ratios)) if ratios else None,
        latest_net_flow=latest.foreign_net_value,
        latest_flow_ratio_pct=float(latest.foreign_flow_ratio),
        latest_date=latest.date,
    )


def _broker_line_sort_key(line: BrokerDetailLine) -> Decimal:
    return abs(line.net_value)


def _broker_tier(code: str) -> str:
    code_upper = code.upper()
    if code_upper in SMART_MONEY_BROKERS:
        return "smart"
    if code_upper in NOISE_BROKERS:
        return "noise"
    return "neutral"


def _broker_weight(code: str) -> Decimal:
    return BROKER_WEIGHTS.get(code.upper(), Decimal("1.0"))


def _smart_share_pct(
    smart_flow: Decimal,
    noise_flow: Decimal,
    neutral_flow: Decimal,
) -> float | None:
    total = abs(smart_flow) + abs(noise_flow) + abs(neutral_flow)
    if total == Decimal("0"):
        return None
    return round(float(abs(smart_flow) / total * Decimal("100")), 1)


def _broker_weight_quality(
    smart_flow: Decimal,
    noise_flow: Decimal,
    neutral_flow: Decimal,
    latest_net_flow: Decimal,
    smart_share_pct: float | None,
) -> str:
    if latest_net_flow < Decimal("0") and smart_flow < Decimal("0"):
        return "smart distribution"
    if latest_net_flow < Decimal("0") and smart_flow > Decimal("0"):
        return "smart distribution watch"
    if smart_flow > Decimal("0") and (smart_share_pct or 0) >= _SC.smart_share_threshold_pct:
        return "smart accumulation"
    if noise_flow > Decimal("0") and smart_flow <= Decimal("0"):
        return "noisy accumulation"
    if smart_flow > Decimal("0"):
        return "smart support"
    if smart_flow < Decimal("0"):
        return "smart selling pressure"
    if neutral_flow > Decimal("0"):
        return "neutral accumulation"
    return "neutral detail"


def _build_broker_detail_from_daily_flows(
    ticker: str,
    daily_flows: list,
    window_sessions: int,
    as_of_date: date | None,
) -> BrokerDetail | None:
    """Build BrokerDetail from real per-day per-broker flow records."""
    # Determine the window: latest N distinct trading dates
    all_dates = sorted({f.date for f in daily_flows}, reverse=True)
    window_dates = set(all_dates[:window_sessions])
    window_flows = [f for f in daily_flows if f.date in window_dates]
    if not window_flows:
        return None

    buyer_values: dict[str, Decimal] = {}
    buyer_names: dict[str, str] = {}
    buyer_sessions: dict[str, set] = {}
    seller_values: dict[str, Decimal] = {}
    seller_names: dict[str, str] = {}
    seller_sessions: dict[str, set] = {}
    smart_flow = Decimal("0")
    noise_flow = Decimal("0")
    neutral_flow = Decimal("0")
    weighted_net_flow = Decimal("0")

    def add_weighted_flow(code: str, signed_value: Decimal) -> None:
        nonlocal smart_flow, noise_flow, neutral_flow, weighted_net_flow
        tier = _broker_tier(code)
        if tier == "smart":
            smart_flow += signed_value
        elif tier == "noise":
            noise_flow += signed_value
        else:
            neutral_flow += signed_value
        weighted_net_flow += signed_value * _broker_weight(code)

    for f in window_flows:
        if f.net_value > Decimal("0"):
            buyer_values[f.broker_code] = buyer_values.get(f.broker_code, Decimal("0")) + f.net_value
            buyer_names[f.broker_code] = f.broker_name
            buyer_sessions.setdefault(f.broker_code, set()).add(f.date)
            add_weighted_flow(f.broker_code, f.net_value)
        elif f.net_value < Decimal("0"):
            seller_values[f.broker_code] = seller_values.get(f.broker_code, Decimal("0")) + abs(f.net_value)
            seller_names[f.broker_code] = f.broker_name
            seller_sessions.setdefault(f.broker_code, set()).add(f.date)
            add_weighted_flow(f.broker_code, f.net_value)

    buyers = tuple(sorted(
        (
            BrokerDetailLine(
                broker_code=code,
                broker_name=buyer_names.get(code, code),
                broker_type="unknown",
                net_value=value,
                active_sessions=len(buyer_sessions.get(code, set())),
            )
            for code, value in buyer_values.items()
        ),
        key=_broker_line_sort_key,
        reverse=True,
    )[:5])
    sellers = tuple(sorted(
        (
            BrokerDetailLine(
                broker_code=code,
                broker_name=seller_names.get(code, code),
                broker_type="unknown",
                net_value=-value,
                active_sessions=len(seller_sessions.get(code, set())),
            )
            for code, value in seller_values.items()
        ),
        key=_broker_line_sort_key,
        reverse=True,
    )[:5])

    total_buy = sum(buyer_values.values(), Decimal("0"))
    total_sell = sum(seller_values.values(), Decimal("0"))
    top_buyer_share = (
        round(float(abs(buyers[0].net_value) / total_buy * Decimal("100")), 1)
        if buyers and total_buy > Decimal("0") else None
    )
    top_seller_share = (
        round(float(abs(sellers[0].net_value) / total_sell * Decimal("100")), 1)
        if sellers and total_sell > Decimal("0") else None
    )

    through_date = max(f.date for f in window_flows)
    smart_share = _smart_share_pct(smart_flow, noise_flow, neutral_flow)
    broker_weight_quality = _broker_weight_quality(
        smart_flow=smart_flow,
        noise_flow=noise_flow,
        neutral_flow=neutral_flow,
        latest_net_flow=smart_flow + noise_flow + neutral_flow,
        smart_share_pct=smart_share,
    )

    if not buyers:
        quality = "no buyer detail"
    elif top_buyer_share is not None and top_buyer_share >= 60:
        quality = "concentrated accumulation"
    elif len(buyers) >= 3 and len(window_dates) >= 3:
        quality = "broad accumulation"
    elif smart_flow < Decimal("0"):
        quality = "recent distribution"
    else:
        quality = "limited accumulation detail"

    return BrokerDetail(
        window_sessions=window_sessions,
        detail_sessions=len(window_dates),
        through_date=through_date,
        source="stockbit",
        top_buyers=buyers,
        top_sellers=sellers,
        top_buyer_share_pct=top_buyer_share,
        top_seller_share_pct=top_seller_share,
        smart_flow=smart_flow,
        noise_flow=noise_flow,
        neutral_flow=neutral_flow,
        weighted_net_flow=weighted_net_flow,
        smart_share_pct=smart_share,
        broker_weight_quality=broker_weight_quality,
        quality=quality,
    )


def _build_broker_detail(
    ticker: str,
    broker_repo: SQLiteBrokerRepository,
    window_sessions: int = 5,
    as_of_date: date | None = None,
) -> BrokerDetail | None:
    # Prefer broker_daily_flow — real per-day per-broker data, never aggregates.
    # Fall back to broker_summaries only when daily flow is unavailable.
    daily_flows = (
        broker_repo.get_broker_daily_flows(ticker, end_date=as_of_date)
        if hasattr(broker_repo, "get_broker_daily_flows")
        else []
    )

    if daily_flows:
        return _build_broker_detail_from_daily_flows(
            ticker, daily_flows, window_sessions, as_of_date
        )

    # Legacy fallback: broker_summaries (period aggregates from marketdetectors)
    summaries = broker_repo.get_broker_summaries(ticker, end_date=as_of_date)
    detail_summaries = [
        summary
        for summary in summaries
        if summary.top_buyers or summary.top_sellers
    ][-window_sessions:]
    if not detail_summaries:
        return None

    buyer_values: dict[str, Decimal] = {}
    buyer_names: dict[str, str] = {}
    buyer_types: dict[str, str] = {}
    buyer_sessions: dict[str, set[date]] = {}
    seller_values: dict[str, Decimal] = {}
    seller_names: dict[str, str] = {}
    seller_types: dict[str, str] = {}
    seller_sessions: dict[str, set[date]] = {}
    smart_flow = Decimal("0")
    noise_flow = Decimal("0")
    neutral_flow = Decimal("0")
    weighted_net_flow = Decimal("0")

    def add_weighted_flow(code: str, signed_value: Decimal) -> None:
        nonlocal smart_flow, noise_flow, neutral_flow, weighted_net_flow
        tier = _broker_tier(code)
        if tier == "smart":
            smart_flow += signed_value
        elif tier == "noise":
            noise_flow += signed_value
        else:
            neutral_flow += signed_value
        weighted_net_flow += signed_value * _broker_weight(code)

    for summary in detail_summaries:
        for tx in summary.top_buyers:
            if tx.net_value > Decimal("0"):
                buyer_values[tx.broker_code] = (
                    buyer_values.get(tx.broker_code, Decimal("0")) + tx.net_value
                )
                buyer_names[tx.broker_code] = tx.broker_name
                buyer_types[tx.broker_code] = tx.broker_type.value
                buyer_sessions.setdefault(tx.broker_code, set()).add(summary.date)
                add_weighted_flow(tx.broker_code, tx.net_value)
        for tx in summary.top_sellers:
            if tx.net_value < Decimal("0"):
                signed_value = tx.net_value
                seller_values[tx.broker_code] = (
                    seller_values.get(tx.broker_code, Decimal("0")) + abs(signed_value)
                )
                seller_names[tx.broker_code] = tx.broker_name
                seller_types[tx.broker_code] = tx.broker_type.value
                seller_sessions.setdefault(tx.broker_code, set()).add(summary.date)
                add_weighted_flow(tx.broker_code, signed_value)

    buyers = tuple(sorted(
        (
            BrokerDetailLine(
                broker_code=code,
                broker_name=buyer_names.get(code, code),
                broker_type=buyer_types.get(code, "unknown"),
                net_value=value,
                active_sessions=len(buyer_sessions.get(code, set())),
            )
            for code, value in buyer_values.items()
        ),
        key=_broker_line_sort_key,
        reverse=True,
    )[:5])
    sellers = tuple(sorted(
        (
            BrokerDetailLine(
                broker_code=code,
                broker_name=seller_names.get(code, code),
                broker_type=seller_types.get(code, "unknown"),
                net_value=-value,
                active_sessions=len(seller_sessions.get(code, set())),
            )
            for code, value in seller_values.items()
        ),
        key=_broker_line_sort_key,
        reverse=True,
    )[:5])

    total_buy = sum(buyer_values.values(), Decimal("0"))
    total_sell = sum(seller_values.values(), Decimal("0"))
    top_buyer_share = (
        round(float(abs(buyers[0].net_value) / total_buy * Decimal("100")), 1)
        if buyers and total_buy > Decimal("0")
        else None
    )
    top_seller_share = (
        round(float(abs(sellers[0].net_value) / total_sell * Decimal("100")), 1)
        if sellers and total_sell > Decimal("0")
        else None
    )

    latest = detail_summaries[-1]
    smart_share = _smart_share_pct(
        smart_flow=smart_flow,
        noise_flow=noise_flow,
        neutral_flow=neutral_flow,
    )
    broker_weight_quality = _broker_weight_quality(
        smart_flow=smart_flow,
        noise_flow=noise_flow,
        neutral_flow=neutral_flow,
        latest_net_flow=latest.foreign_net_value,
        smart_share_pct=smart_share,
    )
    if latest.foreign_net_value < Decimal("0"):
        quality = "recent distribution"
    elif top_buyer_share is not None and top_buyer_share >= 60:
        quality = "concentrated accumulation"
    elif len(buyers) >= 3 and len(detail_summaries) >= 3:
        quality = "broad accumulation"
    elif buyers:
        quality = "limited accumulation detail"
    else:
        quality = "no buyer detail"

    return BrokerDetail(
        window_sessions=window_sessions,
        detail_sessions=len(detail_summaries),
        through_date=latest.date,
        source=latest.source,
        top_buyers=buyers,
        top_sellers=sellers,
        top_buyer_share_pct=top_buyer_share,
        top_seller_share_pct=top_seller_share,
        smart_flow=smart_flow,
        noise_flow=noise_flow,
        neutral_flow=neutral_flow,
        weighted_net_flow=weighted_net_flow,
        smart_share_pct=smart_share,
        broker_weight_quality=broker_weight_quality,
        quality=quality,
    )


def _auto_refresh_swing_data(
    ticker: str,
    db_path: Path,
    force_refresh: bool,
) -> tuple[str, ...]:
    """Refresh only the requested ticker for swing analysis."""
    from src.adapters.cli.update_commands import (
        _create_broker_provider,
        _fetch_broker,
        _fetch_candles,
    )

    actions: list[str] = []
    candles_status = _fetch_candles(
        ticker=ticker,
        days=365,
        db_path=db_path,
        provider_name="yahoo",
        refresh=force_refresh,
    )
    actions.append(f"candles={candles_status}")

    broker_provider, broker_provider_name = _create_broker_provider(None)
    broker_status = _fetch_broker(
        ticker=ticker,
        days=90,
        db_path=db_path,
        broker_provider=broker_provider,
        refresh=force_refresh,
    )
    actions.append(f"broker({broker_provider_name})={broker_status}")

    return tuple(actions)


@contextmanager
def _quiet_sentiment_fetch(enabled: bool):
    """Suppress optional sentiment provider noise in composite swing output."""
    if not enabled:
        with nullcontext():
            yield
        return

    previous_disable = logging.root.manager.disable
    sink = StringIO()
    try:
        logging.disable(logging.CRITICAL)
        with redirect_stdout(sink), redirect_stderr(sink):
            yield
    finally:
        logging.disable(previous_disable)


def _fetch_swing_sentiment(
    ticker: str,
    sentiment_verbose: bool,
):
    """Fetch optional sentiment context without leaking provider noise by default."""
    try:
        with _quiet_sentiment_fetch(enabled=not sentiment_verbose):
            news_provider = SentimentFactory.create_news_provider()
            classifier = SentimentFactory.create_classifier(use_ai=False)
            sent_uc = FetchSentimentUseCase(
                news_provider=news_provider,
                classifier=classifier,
            )
            response = sent_uc.execute(FetchSentimentRequest(
                ticker=ticker,
                max_headlines=20,
                days=3,
            ))
        return response, response.warning
    except Exception as exc:
        if sentiment_verbose:
            return None, f"Sentiment fetch failed: {exc}"
        return None, "News unavailable (provider fetch failed)."


def _parse_regime_filter(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    regimes = tuple(part.strip().upper() for part in value.split(",") if part.strip())
    valid = {"BULLISH", "SIDEWAYS", "WEAK", "RISK_OFF"}
    invalid = [regime for regime in regimes if regime not in valid]
    if invalid:
        raise typer.BadParameter(
            "--allow-regimes must contain only: BULLISH, SIDEWAYS, WEAK, RISK_OFF"
        )
    return regimes


def _parse_compare_variants(value: str) -> tuple[str, ...]:
    variants = tuple(part.strip().lower() for part in value.split(",") if part.strip())
    if not variants:
        raise typer.BadParameter("--variants must contain at least one variant")
    invalid = [variant for variant in variants if variant not in SWING_COMPARE_VARIANTS]
    if invalid:
        available = ", ".join(SWING_COMPARE_VARIANTS)
        raise typer.BadParameter(
            f"Unknown variants: {', '.join(invalid)}. Available: {available}"
        )
    return variants


def _display_swing_compare(
    rows: list[tuple[str, SwingBacktestResponse]],
    start_date: date,
    end_date: date,
    universe_label: str,
) -> None:
    typer.echo("")
    typer.echo(typer.style("=" * 102, fg=typer.colors.CYAN))
    typer.echo(typer.style("SWING BACKTEST COMPARISON", fg=typer.colors.CYAN, bold=True))
    typer.echo(typer.style("=" * 102, fg=typer.colors.CYAN))
    cost_bps = rows[0][1].cost_bps if rows else Decimal("0")
    typer.echo(
        f"Universe: {universe_label} | Period: {start_date} to {end_date} | "
        f"Cost: {float(cost_bps):g} bps one-way"
    )
    typer.echo("")
    typer.echo(
        f"{'VARIANT':<16} {'REGIMES':<24} {'TRADES':>7} {'RETURN':>9} "
        f"{'MAX_DD':>9} {'WIN':>8} {'PF':>8} {'SKIP_REG':>9} {'EXPOSURE':>9}"
    )
    typer.echo("-" * 102)
    for name, response in rows:
        regimes = SWING_COMPARE_VARIANTS[name]
        regime_label = "all" if not regimes else ",".join(regimes)
        profit_factor = (
            "INF" if response.profit_factor == float("inf")
            else "N/A" if response.profit_factor is None
            else f"{response.profit_factor:.2f}"
        )
        typer.echo(
            f"{name:<16} {regime_label:<24} {response.trade_count:>7} "
            f"{_fmt_pct(response.total_return_pct, True):>9} "
            f"{_fmt_pct(response.max_drawdown_pct, True):>9} "
            f"{_fmt_pct(response.win_rate_pct):>8} "
            f"{profit_factor:>8} "
            f"{response.skipped_by_regime:>9} "
            f"{_fmt_pct(response.exposure_pct):>9}"
        )
    typer.echo("")
    typer.echo("DISCLAIMER: Historical simulation only. Not trading advice.")
    typer.echo(typer.style("=" * 102, fg=typer.colors.CYAN))


def _display_swing_backtest(response: SwingBacktestResponse, show_trades: int) -> None:
    typer.echo("")
    typer.echo(typer.style("=" * 86, fg=typer.colors.CYAN))
    typer.echo(typer.style("WALK-FORWARD SWING BACKTEST", fg=typer.colors.CYAN, bold=True))
    typer.echo(typer.style("=" * 86, fg=typer.colors.CYAN))
    typer.echo(
        f"Preset: {response.preset} | Period: {response.start_date} to {response.end_date}"
    )
    typer.echo(f"Cost: {float(response.cost_bps):g} bps one-way, applied on entry and exit")
    typer.echo(
        "Read as: the workflow scans each replay date, opens eligible signals within "
        "portfolio limits, then exits by TP/SL/max-hold."
    )
    typer.echo("")
    typer.echo(f"{'METRIC':<24} {'VALUE':>18}")
    typer.echo("-" * 46)
    typer.echo(f"{'Initial capital':<24} {float(response.initial_capital):>18,.0f}")
    typer.echo(f"{'Final equity':<24} {float(response.final_equity):>18,.0f}")
    typer.echo(f"{'Total return':<24} {_fmt_pct(response.total_return_pct, True):>18}")
    typer.echo(f"{'Max drawdown':<24} {_fmt_pct(response.max_drawdown_pct, True):>18}")
    typer.echo(f"{'Trades':<24} {response.trade_count:>18}")
    typer.echo(f"{'Win rate':<24} {_fmt_pct(response.win_rate_pct):>18}")
    typer.echo(f"{'Avg trade return':<24} {_fmt_pct(response.avg_trade_return_pct, True):>18}")
    profit_factor = (
        "INF" if response.profit_factor == float("inf")
        else "N/A" if response.profit_factor is None
        else f"{response.profit_factor:.2f}"
    )
    typer.echo(f"{'Profit factor':<24} {profit_factor:>18}")
    typer.echo(f"{'Exposure days':<24} {_fmt_pct(response.exposure_pct):>18}")
    typer.echo("")
    typer.echo(
        f"Skipped: no_cash={response.skipped_no_cash}, "
        f"duplicate={response.skipped_duplicate}, "
        f"no_forward_data={response.skipped_no_forward_data}, "
        f"regime={response.skipped_by_regime}"
    )

    if response.regime_stats:
        typer.echo("")
        typer.echo("PERFORMANCE BY ENTRY REGIME")
        typer.echo("-" * 86)
        typer.echo(
            f"{'REGIME':<12} {'TRADES':>8} {'AVG_RET':>10} "
            f"{'WIN':>8} {'TOTAL_PNL':>16}"
        )
        for stat in response.regime_stats:
            typer.echo(
                f"{stat.regime:<12} {stat.count:>8} "
                f"{_fmt_pct(stat.avg_return_pct, True):>10} "
                f"{_fmt_pct(stat.win_rate_pct):>8} "
                f"{float(stat.total_pnl):>16,.0f}"
            )

    if show_trades > 0 and response.trades:
        typer.echo("")
        typer.echo("RECENT TRADES")
        typer.echo("-" * 86)
        typer.echo(
            f"{'ENTRY':<10} {'EXIT':<10} {'TICKER':<7} {'LOTS':>6} "
            f"{'RET':>9} {'PNL':>14} {'DAYS':>5} {'REASON':<10}"
        )
        for trade in response.trades[-show_trades:]:
            typer.echo(
                f"{trade.entry_date:%Y-%m-%d} {trade.exit_date:%Y-%m-%d} "
                f"{trade.ticker:<7} {trade.lots:>6} "
                f"{_fmt_pct(trade.net_return_pct, True):>9} "
                f"{float(trade.pnl):>14,.0f} {trade.holding_days:>5} "
                f"{trade.exit_reason:<10}"
            )

    if response.warnings:
        typer.echo("")
        typer.echo("WARNINGS")
        typer.echo("-" * 40)
        for warning in response.warnings:
            typer.echo(f"  ! {warning}")

    typer.echo("")
    typer.echo("DISCLAIMER: Historical simulation only. Not trading advice.")
    typer.echo(typer.style("=" * 86, fg=typer.colors.CYAN))


def _display_regime(response: MarketRegimeResponse) -> None:
    typer.echo("")
    typer.echo(typer.style("=" * 76, fg=typer.colors.CYAN))
    typer.echo(typer.style("MARKET REGIME", fg=typer.colors.CYAN, bold=True))
    typer.echo(typer.style("=" * 76, fg=typer.colors.CYAN))
    typer.echo(f"Date: {response.as_of_date} | Label: {response.label} | Score: {response.score}/7")
    typer.echo("")
    typer.echo(f"{'METRIC':<30} {'VALUE':>16}")
    typer.echo("-" * 48)
    close = "N/A" if response.benchmark_close is None else f"{float(response.benchmark_close):,.2f}"
    sma20 = "N/A" if response.benchmark_sma20 is None else f"{float(response.benchmark_sma20):,.2f}"
    sma50 = "N/A" if response.benchmark_sma50 is None else f"{float(response.benchmark_sma50):,.2f}"
    typer.echo(f"{response.benchmark_ticker + ' close':<30} {close:>16}")
    typer.echo(f"{'Benchmark SMA20':<30} {sma20:>16}")
    typer.echo(f"{'Benchmark SMA50':<30} {sma50:>16}")
    typer.echo(
        f"{'Benchmark 5d return':<30} "
        f"{_fmt_pct(response.benchmark_return_5d_pct, True):>16}"
    )
    typer.echo(
        f"{'Benchmark 20d return':<30} "
        f"{_fmt_pct(response.benchmark_return_20d_pct, True):>16}"
    )
    typer.echo(f"{'Breadth above SMA20':<30} {_fmt_pct(response.breadth_above_sma20_pct):>16}")
    typer.echo(f"{'Breadth change 5d':<30} {_fmt_pct(response.breadth_change_5d_pct, True):>16}")
    typer.echo(f"{'Foreign flow breadth':<30} {_fmt_pct(response.foreign_flow_breadth_pct):>16}")
    typer.echo(f"{'Universe evaluated':<30} {response.breadth_count:>16}/{response.universe_count}")
    typer.echo(
        f"{'Flow evaluated':<30} "
        f"{response.foreign_flow_count:>16}/{response.universe_count}"
    )
    if response.warnings:
        typer.echo("")
        typer.echo("WARNINGS")
        typer.echo("-" * 40)
        for warning in response.warnings:
            typer.echo(f"  ! {warning}")
    typer.echo(typer.style("=" * 76, fg=typer.colors.CYAN))


def _print_swing_output(
    ticker: str,
    today: date,
    profile: str,
    strategy_name: str,
    data_freshness: DataFreshness,
    flow_detail: FlowDetail | None,
    broker_detail: BrokerDetail | None,
    window: int,
    accum: "AccumulationCandidate | None",
    risk_resp,
    atr_value: "Decimal | None",
    sizing: "SizingResult | None",
    preset_eval: "PresetEvaluation | None",
    preset_sizing: "PercentSizingResult | None",
    broker_quality_note: BrokerQualityNote | None,
    market_regime: "MarketRegimeResponse | None",
    capital: "int | None",
    backtest_result,
    sentiment_resp,
    sentiment_warning: str | None,
    sentiment_verbose: bool,
    no_backtest: bool,
    no_sentiment: bool,
    strategy_risk_level: str | None = None,
    strategy_risk_name: str | None = None,
) -> None:
    typer.echo("")
    _sep("=")
    typer.echo(typer.style(
        f"SWING VIEW — {ticker} · {today} · profile={profile}",
        fg=typer.colors.BRIGHT_WHITE, bold=True,
    ))
    _sep("=")

    # ── DATA FRESHNESS ──────────────────────────────────────────────────────
    typer.echo("")
    _section_header("DATA")
    typer.echo(
        f"  Analysis date  {_fmt_date(data_freshness.as_of_date)}   "
        f"Candles through  {_fmt_date(data_freshness.candle_end)}   "
        f"Broker flow through  {_fmt_date(data_freshness.broker_end)}"
    )
    if market_regime is not None:
        typer.echo(f"  Regime as of   {_fmt_date(market_regime.as_of_date)}")
    if data_freshness.refresh_actions:
        typer.echo("  Refresh        " + "; ".join(data_freshness.refresh_actions))
    if data_freshness.warnings:
        for warning in data_freshness.warnings[:3]:
            typer.echo(typer.style(f"  ! {warning}", fg=typer.colors.YELLOW))

    # ── ACCUMULATION ─────────────────────────────────────────────────────────
    typer.echo("")
    if accum:
        label = _signal_label(accum)
        _section_header(
            f"ACCUMULATION ({window} sessions)",
            f"signal: {typer.style(label, bold=label in ('strong', 'coiled spring'))}",
        )
        flow_str = (
            f"{accum.avg_flow_ratio:+.1f}%"
            if accum.avg_flow_ratio is not None else "—"
        )
        fvwap_str = (
            f"{accum.vwap_discount_pct:+.1f}%"
            if accum.vwap_discount_pct is not None else "—"
        )
        vwap_pct_str = (
            typer.style(f"{accum.vwap_pct:+.1f}%", fg=typer.colors.GREEN)
            if accum.vwap_pct is not None and accum.vwap_pct < 0
            else (f"{accum.vwap_pct:+.1f}%" if accum.vwap_pct is not None else "—")
        )
        bb_str = _style_bb(accum.bb_width_pctile) if accum.bb_width_pctile is not None else "—"
        net_str = f"{accum.net_buy_days}/{accum.total_days}"

        typer.echo(
            f"  Score  {_style_score(accum.score)}   "
            f"STREAK  {accum.consecutive_streak}s   "
            f"NET_DAYS  {net_str}   "
            f"FLOW%  {flow_str}"
        )
        typer.echo(
            f"  F_VWAP%  {fvwap_str}    "
            f"VWAP%  {vwap_pct_str}    "
            f"BB%ILE  {bb_str}    "
            f"TREND  {_style_trend(accum.trend)}"
        )
        if accum.score_breakdown:
            bd = accum.score_breakdown
            typer.echo(typer.style(
                f"  [cons={bd.get('cons',0):.1f} streak={bd.get('streak',0):.1f}"
                f" vwap={bd.get('vwap',0):.1f} rsi={bd.get('rsi',0):.1f}"
                f" flow={bd.get('flow',0):.1f} bb={bd.get('bb',0):.1f}]",
                fg=typer.colors.BRIGHT_BLACK,
            ))
        # Corp action risk flags
        if accum.dividend_risk:
            typer.echo(typer.style("  ⚠ DIVIDEND RISK — ex-date within hold window", fg=typer.colors.YELLOW))
        if accum.rights_issue_risk:
            typer.echo(typer.style("  ⚠ RIGHTS ISSUE — dilution risk within hold window", fg=typer.colors.YELLOW))
        for rups_detail in accum.upcoming_rups:
            typer.echo(typer.style(f"  ★ RUPS upcoming — {rups_detail}", fg=typer.colors.CYAN))
        # Seasonality signal
        if accum.seasonal_edge is not None:
            se = accum.seasonal_edge
            se_color = typer.colors.GREEN if se.is_tailwind else (typer.colors.RED if se.is_headwind else typer.colors.WHITE)
            typer.echo(typer.style(
                f"  SEASONAL  {se.label}  (score {se.score:+.2f})",
                fg=se_color,
            ))
        # Insider buying flag
        if accum.insider_buying:
            for label in accum.recent_insider_buys:
                typer.echo(typer.style(f"  ⭐ INSIDER BUY — {label}", fg=typer.colors.CYAN))

        # Analyst consensus
        if accum.analyst_consensus is not None:
            ac = accum.analyst_consensus
            if ac.is_bullish and (ac.upside_pct or 0) >= 10:
                ac_color = typer.colors.GREEN
            elif ac.sell_count > ac.buy_count:
                ac_color = typer.colors.RED
            else:
                ac_color = typer.colors.WHITE
            typer.echo(typer.style(f"  📊 ANALYST: {ac.label}", fg=ac_color))

        # Shareholding composition
        if accum.shareholding is not None:
            sh = accum.shareholding
            sh_color = typer.colors.CYAN if sh.institution_pct >= 30.0 else typer.colors.WHITE
            typer.echo(typer.style(f"  🏦 HOLDING: {sh.label}", fg=sh_color))

        # Bandar detector — Stockbit's institutional operator accumulation signal
        if accum.bandar_detector is not None:
            bd = accum.bandar_detector
            if bd.accumulation_score >= 4:
                bd_color = typer.colors.GREEN
            elif bd.is_accumulating:
                bd_color = typer.colors.YELLOW
            elif bd.is_distributing:
                bd_color = typer.colors.RED
            else:
                bd_color = typer.colors.WHITE
            typer.echo(typer.style(f"  🔍 BANDAR: {bd.label}", fg=bd_color))
    else:
        _section_header(f"ACCUMULATION ({window} sessions)")
        typer.echo(typer.style(
            f"  No broker flow data. Run: saham broker fetch {ticker}",
            fg=typer.colors.BRIGHT_BLACK,
            ))

    # ── BROKER FLOW DETAIL (institutional desk proxy — 10 codes, not all-foreign) ──────────
    typer.echo("")
    if flow_detail:
        _section_header(
            f"FLOW DETAIL ({flow_detail.window_sessions} sessions)",
            f"through: {_fmt_date(flow_detail.through_date)} · institutional desk",
        )
        typer.echo(
            f"  Range  {_fmt_date(flow_detail.from_date)} → "
            f"{_fmt_date(flow_detail.through_date)}   "
            f"Sessions  {flow_detail.available_sessions}/{flow_detail.window_sessions}"
        )
        typer.echo(
            f"  Net    {_fmt_money_short(flow_detail.total_net_flow)} IDR   "
            f"BUY/SELL  {flow_detail.buy_sessions}/{flow_detail.sell_sessions}   "
            f"STREAK  {flow_detail.consecutive_buy_sessions}s"
        )
        latest_flow = (
            _fmt_money_short(flow_detail.latest_net_flow)
            if flow_detail.latest_net_flow is not None else "N/A"
        )
        typer.echo(
            f"  Avg FLOW%  {_fmt_pct(flow_detail.avg_flow_ratio_pct, True)}   "
            f"Latest  {latest_flow} "
            f"({_fmt_pct(flow_detail.latest_flow_ratio_pct, True)})"
        )
    else:
        _section_header("FLOW DETAIL")
        typer.echo(typer.style(
            f"  No broker flow data. Run: saham broker fetch {ticker}",
            fg=typer.colors.BRIGHT_BLACK,
        ))

    # ── NAMED BROKER DETAIL ────────────────────────────────────────────────
    if broker_detail:
        typer.echo("")
        _section_header(
            f"BROKER DETAIL ({broker_detail.detail_sessions}/{broker_detail.window_sessions} sessions)",
            f"through: {_fmt_date(broker_detail.through_date)} · {broker_detail.source}",
        )
        typer.echo(f"  Top buyers       {_fmt_broker_detail_lines(broker_detail.top_buyers)}")
        typer.echo(f"  Top sellers      {_fmt_broker_detail_lines(broker_detail.top_sellers)}")
        typer.echo(
            f"  Smart flow       {_fmt_money_short_signed(broker_detail.smart_flow)} IDR   "
            f"Noise flow  {_fmt_money_short_signed(broker_detail.noise_flow)} IDR"
        )
        smart_share = (
            f"{broker_detail.smart_share_pct:.1f}%"
            if broker_detail.smart_share_pct is not None else "N/A"
        )
        typer.echo(
            f"  Weighted net     {_fmt_money_short_signed(broker_detail.weighted_net_flow)} IDR   "
            f"Smart share  {smart_share}"
        )
        buyer_share = (
            f"{broker_detail.top_buyer_share_pct:.1f}%"
            if broker_detail.top_buyer_share_pct is not None else "N/A"
        )
        seller_share = (
            f"{broker_detail.top_seller_share_pct:.1f}%"
            if broker_detail.top_seller_share_pct is not None else "N/A"
        )
        typer.echo(
            f"  Concentration    top buyer {buyer_share}; top seller {seller_share}"
        )
        typer.echo(
            f"  Quality          {broker_detail.quality}; "
            f"{broker_detail.broker_weight_quality}"
        )

    # ── PRESET GATES ────────────────────────────────────────────────────────
    if preset_eval is not None:
        typer.echo("")
        _section_header(
            f"PRESET — {preset_eval.name}",
            f"final: {_style_classification(preset_eval.classification)}",
        )
        for gate in preset_eval.gates:
            typer.echo(
                f"  {_style_gate(gate.passed):<14} "
                f"{gate.label:<15} actual={gate.actual:<10} required={gate.required}"
            )
        if preset_eval.passed:
            typer.echo(typer.style(
                "  Tested plan: TP +5%, SL -5%, max hold 10 trading days.",
                fg=typer.colors.BRIGHT_BLACK,
            ))
        else:
            typer.echo(typer.style(
                f"  {_format_failed_gates_summary(preset_eval)}",
                fg=typer.colors.BRIGHT_BLACK,
            ))
        if broker_quality_note is not None:
            note_color = (
                typer.colors.YELLOW
                if broker_quality_note.level == "warning"
                else typer.colors.CYAN
            )
            typer.echo(typer.style(
                f"  {broker_quality_note.message}",
                fg=note_color,
            ))

    # ── MARKET REGIME ───────────────────────────────────────────────────────
    if market_regime is not None:
        typer.echo("")
        _section_header("MARKET REGIME", market_regime.label)
        typer.echo(
            f"  Breadth SMA20  {_fmt_pct(market_regime.breadth_above_sma20_pct)}   "
            f"5d change  {_fmt_pct(market_regime.breadth_change_5d_pct, True)}"
        )
        typer.echo(
            f"  Benchmark 20d  {_fmt_pct(market_regime.benchmark_return_20d_pct, True)}   "
            f"Foreign flow breadth  {_fmt_pct(market_regime.foreign_flow_breadth_pct)}"
        )

    # ── RISK CONFIRMATION ────────────────────────────────────────────────────
    typer.echo("")
    if risk_resp:
        r = risk_resp.assessment
        snap = r.indicators
        _section_header(
            "RISK CONFIRMATION",
            f"verdict: {_style_risk(r.risk_level_name)}  conf: {r.confidence}/100",
        )
        typer.echo(
            f"  SMA20  {float(snap.sma):>10,.0f}   "
            f"EMA20  {float(snap.ema):>10,.0f}   "
            f"RSI14  {float(snap.rsi):>5.1f}"
        )
        for reason in r.rationale_list[:3]:
            typer.echo(typer.style(f"  · {reason}", fg=typer.colors.BRIGHT_BLACK))
    else:
        _section_header("RISK CONFIRMATION")
        typer.echo(typer.style(
            "  Insufficient candle data for risk assessment.",
            fg=typer.colors.BRIGHT_BLACK,
        ))

    # ── STRATEGY RISK GATE ──────────────────────────────────────────────────
    if strategy_risk_level is not None:
        typer.echo("")
        _strat_color = {
            "LOW_RISK": typer.colors.GREEN,
            "HIGH_RISK": typer.colors.RED,
            "MODERATE": typer.colors.YELLOW,
        }.get(strategy_risk_level, typer.colors.WHITE)
        _strat_sym = {"LOW_RISK": "↑", "HIGH_RISK": "↓", "MODERATE": "~"}.get(
            strategy_risk_level, "?"
        )
        _section_header(
            f"STRATEGY GATE ({strategy_risk_name})",
            typer.style(f"{_strat_sym} {strategy_risk_level}", fg=_strat_color, bold=True),
        )
        if strategy_risk_level == "HIGH_RISK":
            typer.echo(typer.style(
                f"  ⚠ Strategy '{strategy_risk_name}' signals HIGH_RISK — "
                "overrides preset to AVOID.",
                fg=typer.colors.RED,
            ))
        elif strategy_risk_level == "LOW_RISK":
            typer.echo(typer.style(
                f"  ✓ Strategy '{strategy_risk_name}' confirms entry signal.",
                fg=typer.colors.GREEN,
            ))
        else:
            typer.echo(typer.style(
                f"  ~ Strategy '{strategy_risk_name}' is neutral — no override.",
                fg=typer.colors.BRIGHT_BLACK,
            ))

    # ── SIZING ───────────────────────────────────────────────────────────────
    show_sizing = capital is not None and not (
        preset_eval is not None and not preset_eval.passed
    )
    if show_sizing:
        typer.echo("")
        if preset_sizing and preset_sizing.lots > 0:
            _section_header("PRESET SIZING")
            typer.echo(
                f"  Entry   {float(preset_sizing.entry_price):>10,.0f}   "
                f"Stop  {float(preset_sizing.stop_price):>10,.0f}  "
                f"({float(preset_sizing.stop_pct):+.2f}%)   "
                f"Target  {float(preset_sizing.target_price):>10,.0f}  "
                f"({float(preset_sizing.target_pct):+.2f}%)"
            )
            actual_risk = Decimal(str(preset_sizing.shares)) * preset_sizing.stop_distance
            typer.echo(
                f"  Position  {preset_sizing.lots} lots = "
                f"{preset_sizing.shares:,} shares   "
                f"Cost  {float(preset_sizing.position_cost):,.0f} IDR  "
                f"({float(preset_sizing.capital_used_pct):.1f}% of capital)"
            )
            typer.echo(
                f"  Risk    {float(actual_risk):>12,.0f} IDR   "
                f"Max hold  {FOREIGN_BOUNCE_MAX_HOLD_DAYS} trading days"
            )
            if atr_value is not None and atr_value > 0:
                stop_to_atr = preset_sizing.stop_distance / atr_value
                note = f"5% stop = {float(stop_to_atr):.2f}× ATR14"
                if stop_to_atr < Decimal("1"):
                    note += " (tight vs daily volatility)"
                typer.echo(typer.style(f"  ({note})", fg=typer.colors.BRIGHT_BLACK))
        elif preset_sizing and preset_sizing.lots == 0:
            _section_header("PRESET SIZING")
            typer.echo(typer.style(
                "  INSUFFICIENT CAPITAL: cannot fill 1 lot with 5% stop sizing.",
                fg=typer.colors.RED,
            ))
        elif sizing and sizing.lots > 0:
            _section_header("SIZING")
            typer.echo(
                f"  Entry   {float(sizing.entry_price):>10,.0f}   "
                f"Stop  {float(sizing.stop_price):>10,.0f}  ({float(sizing.stop_pct):+.2f}%)   "
                f"Target  {float(sizing.target_price):>10,.0f}  ({float(sizing.target_pct):+.2f}%)"
            )
            actual_risk = Decimal(str(sizing.shares)) * sizing.stop_distance
            actual_reward = actual_risk * sizing.reward_risk_ratio
            typer.echo(
                f"  Position  {sizing.lots} lots = {sizing.shares:,} shares   "
                f"Cost  {float(sizing.position_cost):,.0f} IDR  "
                f"({float(sizing.capital_used_pct):.1f}% of capital)"
            )
            typer.echo(
                f"  Risk    {float(actual_risk):>12,.0f} IDR   "
                f"Reward  {float(actual_reward):>12,.0f} IDR"
            )
            typer.echo(typer.style(
                f"  (ATR14={float(atr_value):.0f} · stop={float(sizing.atr_multiplier):.1f}×ATR"
                f" · RR={float(sizing.reward_risk_ratio):.1f})",
                fg=typer.colors.BRIGHT_BLACK,
            ))
        elif sizing and sizing.lots == 0:
            _section_header("SIZING")
            typer.echo(typer.style(
                "  INSUFFICIENT CAPITAL: cannot fill 1 lot at this position size.",
                fg=typer.colors.RED,
            ))
            typer.echo(typer.style(
                f"  (Need ≥ {sizing.shares + 100} shares × {float(sizing.entry_price):,.0f} = "
                f"{float((Decimal(str(sizing.shares + 100)) * sizing.entry_price)):,.0f} IDR)",
                fg=typer.colors.BRIGHT_BLACK,
            ))
        else:
            _section_header("SIZING")
            typer.echo(typer.style(
                "  Cannot size position — ATR unavailable.",
                fg=typer.colors.BRIGHT_BLACK,
            ))

    # ── HISTORY ──────────────────────────────────────────────────────────────
    typer.echo("")
    if backtest_result is not None and backtest_result.trade_count > 0:
        r = backtest_result
        _section_header(
            "HISTORY",
            f"({strategy_name})  {r.trade_count} trades",
        )
        typer.echo(
            f"  Win rate  {_style_winrate(r.win_rate)}   "
            f"Profit factor  {float(r.profit_factor):.2f}   "
            f"Max DD  {float(r.max_drawdown_pct):.1f}%"
        )
        if r.avg_win and r.avg_loss:
            typer.echo(
                f"  Avg win  {float(r.avg_win):>12,.0f} IDR   "
                f"Avg loss  {float(r.avg_loss):>12,.0f} IDR"
            )
    elif backtest_result is not None and backtest_result.trade_count == 0:
        _section_header("HISTORY", f"({strategy_name})")
        typer.echo(typer.style(
            "  No trades triggered in available history (needs more broker data).",
            fg=typer.colors.BRIGHT_BLACK,
        ))
        typer.echo(typer.style(
            f"  Tip: saham backtest {ticker} --strategy {strategy_name} --verbose",
            fg=typer.colors.BRIGHT_BLACK,
        ))
    elif not no_backtest:
        _section_header("HISTORY")
        typer.echo(typer.style(
            f"  Could not run backtest. Run: saham update {ticker} --days 730",
            fg=typer.colors.BRIGHT_BLACK,
        ))

    # ── SENTIMENT ────────────────────────────────────────────────────────────
    if not no_sentiment:
        typer.echo("")
        if sentiment_resp and not sentiment_resp.warning:
            snap = sentiment_resp.snapshot
            call = snap.overall_sentiment.value.upper()
            _section_header(
                "SENTIMENT (3d)",
                f"call: {_style_sentiment_call(call)}",
            )
            typer.echo(
                f"  {snap.total_count} headlines   "
                f"(+{snap.positive_count} / ={snap.neutral_count} / -{snap.negative_count})   "
                f"confidence  {snap.confidence_pct}%"
            )
        else:
            _section_header("SENTIMENT (3d)")
            message = sentiment_warning or "News unavailable (no network or fetch failed)."
            typer.echo(typer.style(
                f"  {message}",
                fg=typer.colors.BRIGHT_BLACK,
            ))
            if not sentiment_verbose:
                typer.echo(typer.style(
                    "  Use --sentiment-verbose to show provider details.",
                    fg=typer.colors.BRIGHT_BLACK,
                ))

    # ── SUMMARY ──────────────────────────────────────────────────────────────
    typer.echo("")
    _sep("=")
    summary_parts = []
    if accum:
        summary_parts.append(f"Score {accum.score:.1f}")
    if risk_resp:
        summary_parts.append(risk_resp.assessment.risk_level_name)
    if backtest_result and backtest_result.trade_count > 0:
        summary_parts.append(f"{float(backtest_result.win_rate):.0f}% WR")
    if sentiment_resp and not sentiment_resp.warning:
        summary_parts.append(
            sentiment_resp.snapshot.overall_sentiment.value.lower() + " news"
        )

    if summary_parts:
        typer.echo("SUMMARY: " + typer.style(" · ".join(summary_parts), bold=True))
    else:
        typer.echo("SUMMARY: insufficient data for assessment")

    # Strategy gate overrides ENTER → AVOID if HIGH_RISK
    strategy_override = (
        strategy_risk_level == "HIGH_RISK"
        and preset_eval is not None
        and preset_eval.passed
    )

    if preset_eval is not None:
        if strategy_override:
            typer.echo(typer.style(
                f"PLAN:  AVOID (strategy gate: '{strategy_risk_name}' signals HIGH_RISK "
                "— preset passed but technical signal says exit).",
                fg=typer.colors.RED,
                bold=True,
            ))
        elif preset_eval.passed and preset_sizing and preset_sizing.lots > 0:
            typer.echo(
                f"PLAN:  ENTER setup passed. Consider {preset_sizing.lots} lots at "
                f"{float(preset_sizing.entry_price):,.0f}; TP "
                f"{float(preset_sizing.target_price):,.0f}; SL "
                f"{float(preset_sizing.stop_price):,.0f}; max hold "
                f"{FOREIGN_BOUNCE_MAX_HOLD_DAYS} trading days."
            )
        elif preset_eval.passed:
            typer.echo("PLAN:  ENTER setup passed. Add --capital to compute lot size.")
        elif preset_eval.classification == "WATCH":
            typer.echo(
                "PLAN:  WATCH only. Preset is close but not fully confirmed; "
                "wait for failed gates to improve."
            )
        else:
            typer.echo("PLAN:  AVOID. Preset gates are not aligned.")
    elif sizing and sizing.lots > 0:
        typer.echo(
            f"PLAN:  Sized scenario: {sizing.lots} lots at {float(sizing.entry_price):,.0f}.  "
            f"Stop {float(sizing.stop_price):,.0f}.  "
            f"Target {float(sizing.target_price):,.0f}."
        )
    elif sizing and sizing.lots == 0:
        typer.echo("PLAN:  Position too small for 1 lot — reduce entry or increase capital.")
    elif capital and not atr_value:
        typer.echo(
            "PLAN:  Fetch more data to enable position sizing "
            f"(run saham update {ticker} --days 90)."
        )

    _sep("=")
    typer.echo(typer.style(
        "DISCLAIMER: Analysis only, not trading advice.",
        fg=typer.colors.BRIGHT_BLACK,
    ))
    typer.echo("")


# ─── swing command ───────────────────────────────────────────────────────────

def swing(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBRI)")],
    profile: Annotated[
        str,
        typer.Option("--profile", "-p", help="Risk profile: balanced/conservative/aggressive"),
    ] = "balanced",
    strategy: Annotated[
        str,
        typer.Option(
            "--strategy",
            "-S",
            help="Backtest strategy name (default: foreign-accumulation)",
        ),
    ] = "foreign-accumulation",
    preset: Annotated[
        Optional[str],
        typer.Option("--preset", help="Swing preset to evaluate (default: foreign-bounce)"),
    ] = "foreign-bounce",
    window: Annotated[
        int,
        typer.Option("--window", "-w", help="Accumulation analysis window in broker sessions (default: 7)"),
    ] = 7,
    flow_window: Annotated[
        int,
        typer.Option("--flow-window", help="Broker-flow detail window in broker sessions", min=1),
    ] = 30,
    capital: Annotated[
        Optional[int],
        typer.Option("--capital", "-c", help="Capital in IDR — enables position sizing block"),
    ] = None,
    risk_pct: Annotated[
        float,
        typer.Option("--risk-pct", help="% of capital at risk per trade (default: 1.0)"),
    ] = 1.0,
    entry_price: Annotated[
        Optional[float],
        typer.Option("--entry", help="Entry price in IDR (default: latest close)"),
    ] = None,
    atr_mult: Annotated[
        float,
        typer.Option("--atr-mult", help="ATR multiplier for stop distance (default: 1.5)"),
    ] = 1.5,
    rr: Annotated[
        float,
        typer.Option("--rr", help="Reward:risk ratio for target (default: 2.0)"),
    ] = 2.0,
    no_sentiment: Annotated[
        bool,
        typer.Option("--no-sentiment", help="Skip news sentiment (offline mode)"),
    ] = False,
    sentiment_verbose: Annotated[
        bool,
        typer.Option("--sentiment-verbose", help="Show sentiment provider errors/noise"),
    ] = False,
    no_backtest: Annotated[
        bool,
        typer.Option("--no-backtest", help="Skip historical backtest"),
    ] = False,
    auto_refresh: Annotated[
        bool,
        typer.Option(
            "--auto-refresh/--no-refresh",
            help="Refresh this ticker's candles and broker flow before analysis",
        ),
    ] = True,
    force_refresh: Annotated[
        bool,
        typer.Option("--force-refresh", help="Force provider refresh even if cached data is fresh"),
    ] = False,
    with_regime: Annotated[
        bool,
        typer.Option("--with-regime", help="Add market regime context"),
    ] = False,
    regime_universe: Annotated[
        str,
        typer.Option("--regime-universe", help="Universe for breadth context"),
    ] = "idx80",
    benchmark: Annotated[
        str,
        typer.Option("--benchmark", help="Benchmark ticker for regime context"),
    ] = "^JKSE",
    risk_strategy: Annotated[
        Optional[str],
        typer.Option(
            "--risk-strategy",
            help=(
                "Strategy to use as additional risk gate. "
                "If strategy signals HIGH_RISK, overrides preset to AVOID. "
                "Example: --risk-strategy williams-r-bounce"
            ),
        ),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Unified composite swing trade analysis for a single stock.

    Combines: accumulation signal, risk confirmation, position sizing,
    historical backtest, and news sentiment in one command.

    Replaces the 5–6 command morning workflow:
      saham swing screen, saham risk, saham compute ATR,
      saham backtest, saham sentiment — all in one.

    Examples:
        saham swing analyze BBRI
        saham swing analyze BBRI --preset foreign-bounce --capital 10000000
        saham swing analyze BBRI --capital 10000000 --risk-pct 1
        saham swing analyze BBRI --profile conservative --no-sentiment
        saham swing analyze BBRI --no-refresh --no-backtest --no-sentiment
        saham swing analyze BBRI --no-backtest --no-sentiment
        saham swing analyze BBRI --force-refresh
        saham swing analyze BBRI --capital 10000000 --entry 4825 --rr 2.5
    """
    resolved_db = db_path or DEFAULT_DB_PATH
    ticker_upper = ticker.upper()
    today = date.today()

    if capital is None:
        _cfg = get_swing_default("capital")
        if _cfg is not None:
            capital = int(_cfg)

    preset_name = preset.lower() if preset else None
    if preset_name is not None and preset_name != FOREIGN_BOUNCE_PRESET:
        typer.echo(
            f"Unknown swing preset '{preset}'. Available presets: {FOREIGN_BOUNCE_PRESET}",
            err=True,
        )
        raise typer.Exit(1)

    market_repo = SQLiteMarketRepository(db_path=resolved_db)
    broker_repo = SQLiteBrokerRepository(resolved_db)
    registry = create_indicator_registry(
        broker_repository=broker_repo,
        market_repository=market_repo,
    )

    refresh_actions: tuple[str, ...] = ()
    if auto_refresh:
        refresh_actions = _auto_refresh_swing_data(
            ticker=ticker_upper,
            db_path=resolved_db,
            force_refresh=force_refresh,
        )
    else:
        refresh_actions = ("disabled",)

    data_freshness = _build_data_freshness(
        ticker=ticker_upper,
        as_of_date=today,
        market_repo=market_repo,
        broker_repo=broker_repo,
        refresh_actions=refresh_actions,
    )
    flow_detail = _build_flow_detail(
        ticker=ticker_upper,
        broker_repo=broker_repo,
        window_sessions=flow_window,
        as_of_date=today,
    )
    broker_detail = _build_broker_detail(
        ticker=ticker_upper,
        broker_repo=broker_repo,
        window_sessions=5,
        as_of_date=today,
    )

    candles = market_repo.get_candles(ticker_upper)
    if not candles:
        typer.echo(
            f"No data for {ticker_upper}. Run: saham update {ticker_upper} --days 365",
            err=True,
        )
        raise typer.Exit(1)

    latest_close = candles[-1].close

    # ── Accumulation ─────────────────────────────────────────────────────────
    accum_candidate: AccumulationCandidate | None = None
    try:
        _sb = _make_stockbit_providers(resolved_db)
        accum_uc = AccumulationScreenUseCase(
            broker_repository=broker_repo,
            market_repository=market_repo,
            corporate_action_repo=_sb.corp_repo,
            seasonality_provider=_sb.season_prov,
            insider_activity_provider=_sb.insider_prov,
            analyst_consensus_provider=_sb.analyst_prov,
            shareholding_provider=_sb.shareholding_prov,
            bandar_detector_provider=_sb.bandar_prov,
        )
        accum_resp = accum_uc.execute(AccumulationScreenRequest(
            tickers=[ticker_upper],
            window_days=window,
            min_net_buy_days=0,
            min_score=0.0,
            tier1_broker_codes=_SC.tier1_broker_codes,
        ))
        if accum_resp.candidates:
            accum_candidate = accum_resp.candidates[0]
    except Exception:
        pass

    # ── Risk ─────────────────────────────────────────────────────────────────
    risk_resp = None
    try:
        risk_uc = AssessRiskUseCase(repository=market_repo, registry=registry)
        risk_resp = risk_uc.execute(AssessRiskRequest(
            ticker=ticker_upper,
            profile=profile,
        ))
    except Exception:
        pass

    # ── Strategy risk gate ───────────────────────────────────────────────────
    strategy_risk_level: str | None = None
    strategy_risk_name: str | None = risk_strategy
    if risk_strategy:
        try:
            strat_loader = StrategyLoader(registry=registry)
            rules_path = strat_loader.resolve(risk_strategy)
            strat_risk_uc = AssessRiskUseCase(repository=market_repo, registry=registry)
            strat_resp = strat_risk_uc.execute(AssessRiskRequest(
                ticker=ticker_upper,
                rules_file=rules_path,
            ))
            strategy_risk_level = strat_resp.assessment.risk_level_name
        except StrategyNotFoundError:
            typer.echo(f"⚠ Risk strategy '{risk_strategy}' not found — gate skipped.", err=True)
        except Exception:
            pass

    # ── ATR ──────────────────────────────────────────────────────────────────
    atr_value: Decimal | None = None
    try:
        atr_values = registry.compute("ATR", candles, 14)
        if atr_values:
            atr_value = atr_values[-1][1]  # registry returns (date, value) tuples
    except Exception:
        pass

    # ── Position sizing ───────────────────────────────────────────────────────
    sizing: SizingResult | None = None
    preset_eval: PresetEvaluation | None = None
    preset_sizing: PercentSizingResult | None = None
    if preset_name == FOREIGN_BOUNCE_PRESET:
        preset_eval = _evaluate_foreign_bounce(accum_candidate)
    broker_quality_note = _build_broker_quality_note(
        broker_detail=broker_detail,
        preset_eval=preset_eval,
    )

    # Preset sizing is deferred — computed after market regime is fetched so
    # resolve_preset_targets() can use the regime-specific TP/SL from swing_screener.yaml.
    _preset_entry_dec: Decimal | None = None
    if capital is not None and preset_eval is not None and preset_eval.passed:
        _preset_entry_dec = Decimal(str(entry_price)) if entry_price else latest_close
    elif capital is not None and atr_value and preset_eval is None:
        try:
            entry_dec = Decimal(str(entry_price)) if entry_price else latest_close
            sizing = compute_position_size(
                entry=entry_dec,
                atr=atr_value,
                capital=Decimal(str(capital)),
                risk_pct=Decimal(str(risk_pct)) / Decimal("100"),
                atr_multiplier=Decimal(str(atr_mult)),
                reward_risk=Decimal(str(rr)),
            )
        except ValueError:
            pass

    # ── Backtest ─────────────────────────────────────────────────────────────
    backtest_result = None
    if not no_backtest:
        try:
            loader = StrategyLoader(registry=registry)
            rules_path = loader.resolve(strategy)
            bt_uc = BacktestUseCase(repository=market_repo, registry=registry)
            bt_resp = bt_uc.execute(BacktestRequest(
                ticker=ticker_upper,
                rules_file=rules_path,
                initial_capital=Decimal("100000000"),
            ))
            backtest_result = bt_resp.result
        except (StrategyNotFoundError, Exception):
            pass

    # ── Sentiment ─────────────────────────────────────────────────────────────
    sentiment_resp = None
    sentiment_warning: str | None = None
    if not no_sentiment:
        sentiment_resp, sentiment_warning = _fetch_swing_sentiment(
            ticker=ticker_upper,
            sentiment_verbose=sentiment_verbose,
        )

    # ── Market regime ───────────────────────────────────────────────────────
    market_regime: MarketRegimeResponse | None = None
    if with_regime:
        try:
            regime_tickers = resolve_tickers(
                universe=regime_universe,
                explicit=[],
                db_path=resolved_db,
            )
            regime_uc = MarketRegimeUseCase(
                market_repository=market_repo,
                broker_repository=broker_repo,
            )
            market_regime = regime_uc.execute(MarketRegimeRequest(
                universe=regime_tickers,
                benchmark_ticker=benchmark,
                as_of_date=today,
                breadth_sma_period=_SC.regime_breadth_sma_period,
                benchmark_sma_fast=_SC.regime_benchmark_sma_fast,
                benchmark_sma_slow=_SC.regime_benchmark_sma_slow,
            ))
        except Exception:
            pass

    # Deferred preset sizing: now that regime is known, resolve TP/SL and compute sizing.
    _swing_config = _load_swing_screener_config()
    _regime_label = market_regime.label if market_regime else None
    _tp_pct, _sl_pct = resolve_preset_targets(_regime_label, _swing_config)
    if _preset_entry_dec is not None and capital is not None:
        try:
            preset_sizing = compute_percent_position_size(
                entry=_preset_entry_dec,
                capital=Decimal(str(capital)),
                risk_pct=Decimal(str(risk_pct)) / Decimal("100"),
                stop_loss_pct=_sl_pct,
                take_profit_pct=_tp_pct,
            )
        except ValueError:
            pass

    if output_format == "json":
        data_out = data_freshness.to_dict()
        if market_regime is not None:
            data_out["regime_as_of"] = market_regime.as_of_date.isoformat()
        out: dict = {
            "ticker": ticker_upper,
            "date": str(today),
            "profile": profile,
            "data": data_out,
            "flow_detail": flow_detail.to_dict() if flow_detail else None,
            "broker_detail": broker_detail.to_dict() if broker_detail else None,
            "broker_quality_note": (
                broker_quality_note.to_dict() if broker_quality_note else None
            ),
            "accumulation": {
                "score": accum_candidate.score if accum_candidate else None,
                "streak": accum_candidate.consecutive_streak if accum_candidate else None,
                "trend": accum_candidate.trend if accum_candidate else None,
                "flow_pct": accum_candidate.avg_flow_ratio if accum_candidate else None,
                "vwap_disc_pct": accum_candidate.vwap_discount_pct if accum_candidate else None,
                "bb_width_pctile": accum_candidate.bb_width_pctile if accum_candidate else None,
                "dividend_risk": accum_candidate.dividend_risk if accum_candidate else False,
                "rights_issue_risk": accum_candidate.rights_issue_risk if accum_candidate else False,
                "upcoming_rups": accum_candidate.upcoming_rups if accum_candidate else [],
                "seasonal_score": (
                    accum_candidate.seasonal_edge.score
                    if accum_candidate and accum_candidate.seasonal_edge else None
                ),
                "seasonal_label": (
                    accum_candidate.seasonal_edge.label
                    if accum_candidate and accum_candidate.seasonal_edge else None
                ),
                "insider_buying": accum_candidate.insider_buying if accum_candidate else False,
                "recent_insider_buys": accum_candidate.recent_insider_buys if accum_candidate else [],
                "analyst_consensus": (
                    accum_candidate.analyst_consensus.to_dict()
                    if accum_candidate and accum_candidate.analyst_consensus else None
                ),
                "shareholding": (
                    accum_candidate.shareholding.to_dict()
                    if accum_candidate and accum_candidate.shareholding else None
                ),
                "bandar_detector": (
                    accum_candidate.bandar_detector.to_dict()
                    if accum_candidate and accum_candidate.bandar_detector else None
                ),
            },
            "preset": {
                "name": preset_eval.name if preset_eval else None,
                "passed": preset_eval.passed if preset_eval else None,
                "classification": preset_eval.classification if preset_eval else None,
                "failed_reasons": list(preset_eval.failed_reasons) if preset_eval else [],
                "plan": {
                    "take_profit_pct": float(_tp_pct) if preset_eval else None,
                    "stop_loss_pct": float(_sl_pct) if preset_eval else None,
                    "regime": _regime_label,
                    "max_hold_days": FOREIGN_BOUNCE_MAX_HOLD_DAYS
                    if preset_eval else None,
                },
            },
            "risk": {
                "level": risk_resp.assessment.risk_level_name if risk_resp else None,
                "confidence": risk_resp.assessment.confidence if risk_resp else None,
                "sma20": float(risk_resp.assessment.indicators.sma) if risk_resp else None,
                "ema20": float(risk_resp.assessment.indicators.ema) if risk_resp else None,
                "rsi14": float(risk_resp.assessment.indicators.rsi) if risk_resp else None,
            },
            "sizing": {
                "entry": float(
                    preset_sizing.entry_price if preset_sizing
                    else sizing.entry_price
                ) if (preset_sizing or sizing) else None,
                "stop": float(
                    preset_sizing.stop_price if preset_sizing
                    else sizing.stop_price
                ) if (preset_sizing or sizing) else None,
                "target": float(
                    preset_sizing.target_price if preset_sizing
                    else sizing.target_price
                ) if (preset_sizing or sizing) else None,
                "lots": (
                    preset_sizing.lots if preset_sizing
                    else sizing.lots if sizing else None
                ),
                "atr": float(atr_value) if atr_value else None,
            },
            "backtest": {
                "win_rate": float(backtest_result.win_rate) if backtest_result else None,
                "profit_factor": float(backtest_result.profit_factor) if backtest_result else None,
                "max_drawdown_pct": (
                    float(backtest_result.max_drawdown_pct)
                    if backtest_result else None
                ),
                "trade_count": backtest_result.trade_count if backtest_result else None,
            },
            "sentiment": {
                "call": (
                    sentiment_resp.snapshot.overall_sentiment.value
                    if sentiment_resp and not sentiment_resp.warning else None
                ),
                "warning": sentiment_warning,
                "total_headlines": (
                    sentiment_resp.snapshot.total_count
                    if sentiment_resp and not sentiment_resp.warning else None
                ),
                "confidence_pct": (
                    sentiment_resp.snapshot.confidence_pct
                    if sentiment_resp and not sentiment_resp.warning else None
                ),
            },
            "market_regime": market_regime.to_dict() if market_regime else None,
        }
        typer.echo(json.dumps(out, indent=2, default=str))
        return

    _print_swing_output(
        ticker=ticker_upper,
        today=today,
        profile=profile,
        strategy_name=strategy,
        data_freshness=data_freshness,
        flow_detail=flow_detail,
        broker_detail=broker_detail,
        window=window,
        accum=accum_candidate,
        risk_resp=risk_resp,
        atr_value=atr_value,
        sizing=sizing,
        preset_eval=preset_eval,
        preset_sizing=preset_sizing,
        broker_quality_note=broker_quality_note,
        market_regime=market_regime,
        capital=capital,
        backtest_result=backtest_result,
        sentiment_resp=sentiment_resp,
        sentiment_warning=sentiment_warning,
        sentiment_verbose=sentiment_verbose,
        no_backtest=no_backtest,
        no_sentiment=no_sentiment,
        strategy_risk_level=strategy_risk_level,
        strategy_risk_name=strategy_risk_name,
    )


# ─── swing backtest command ──────────────────────────────────────────────────

def swing_backtest(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option("--universe", "-u", help="Universe: lq45, idx80, idxcomp100, cached"),
    ] = None,
    preset: Annotated[
        str,
        typer.Option("--preset", help="Swing preset to validate"),
    ] = BACKTEST_FOREIGN_BOUNCE_PRESET,
    start: Annotated[
        str,
        typer.Option("--start", help="Backtest start date, YYYY-MM-DD"),
    ] = "2026-01-01",
    end: Annotated[
        Optional[str],
        typer.Option("--end", help="Backtest end date, YYYY-MM-DD (default: today)"),
    ] = None,
    capital: Annotated[
        int,
        typer.Option("--capital", "-c", help="Initial capital in IDR", min=1),
    ] = 100_000_000,
    risk_pct: Annotated[
        float,
        typer.Option("--risk-pct", help="% of capital risked per trade", min=0.01),
    ] = 1.0,
    max_positions: Annotated[
        int,
        typer.Option("--max-positions", help="Maximum concurrent open positions", min=1),
    ] = 5,
    take_profit: Annotated[
        float,
        typer.Option("--take-profit", help="Take-profit percentage", min=0.01),
    ] = 5.0,
    stop_loss: Annotated[
        float,
        typer.Option("--stop-loss", help="Stop-loss percentage", min=0.01),
    ] = 5.0,
    max_hold: Annotated[
        int,
        typer.Option("--max-hold", help="Maximum holding period in trading days", min=1),
    ] = 10,
    cost_bps: Annotated[
        float,
        typer.Option(
            "--cost-bps",
            help="One-way transaction cost in basis points (20 ~= 0.20%)",
            min=0,
        ),
    ] = float(DEFAULT_SWING_COST_BPS),
    with_regime: Annotated[
        bool,
        typer.Option("--with-regime", help="Group trades by entry-date market regime"),
    ] = False,
    allow_regimes: Annotated[
        Optional[str],
        typer.Option(
            "--allow-regimes",
            help="Comma-separated entry regimes allowed to open trades",
        ),
    ] = None,
    benchmark: Annotated[
        str,
        typer.Option("--benchmark", help="Benchmark ticker for regime context"),
    ] = "^JKSE",
    show_trades: Annotated[
        int,
        typer.Option("--show-trades", help="Number of recent trades to print", min=0),
    ] = 20,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Walk-forward backtest for the deterministic swing workflow.

    This validates the full daily process: scan, apply preset gates, rank
    candidates, open only within portfolio limits, avoid duplicate positions,
    and exit by TP/SL/max-hold. It reads local cached market and broker data.
    """
    preset_name = preset.lower()
    if preset_name != BACKTEST_FOREIGN_BOUNCE_PRESET:
        typer.echo(
            f"Unknown swing preset '{preset}'. "
            f"Available presets: {BACKTEST_FOREIGN_BOUNCE_PRESET}",
            err=True,
        )
        raise typer.Exit(1)

    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end) if end else date.today()
    except ValueError as e:
        typer.echo(f"Error: invalid date format: {e}", err=True)
        raise typer.Exit(1)

    resolved_db = db_path or DEFAULT_DB_PATH
    try:
        ticker_list = resolve_tickers(
            universe=universe,
            explicit=list(tickers) if tickers else [],
            db_path=resolved_db,
        )
    except (UniverseNotFoundError, FileNotFoundError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if not ticker_list:
        typer.echo(
            "No tickers to backtest. Specify --universe or provide ticker arguments.",
            err=True,
        )
        raise typer.Exit(1)

    try:
        allowed_regimes = _parse_regime_filter(allow_regimes)
    except typer.BadParameter as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(
        f"Backtesting {len(ticker_list)} tickers | {start_date} to {end_date} | "
        f"preset={preset_name} | max positions={max_positions}..."
    )

    use_case = SwingBacktestUseCase(
        broker_repository=SQLiteBrokerRepository(resolved_db),
        market_repository=SQLiteMarketRepository(db_path=resolved_db),
    )
    try:
        response = use_case.execute(SwingBacktestRequest(
            tickers=ticker_list,
            start_date=start_date,
            end_date=end_date,
            preset=preset_name,
            capital=Decimal(str(capital)),
            risk_pct=Decimal(str(risk_pct)) / Decimal("100"),
            max_positions=max_positions,
            take_profit_pct=Decimal(str(take_profit)),
            stop_loss_pct=Decimal(str(stop_loss)),
            max_hold_days=max_hold,
            cost_bps=Decimal(str(cost_bps)),
            include_regime=with_regime or bool(allowed_regimes),
            benchmark_ticker=benchmark,
            allowed_regimes=allowed_regimes,
        ))
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if output_format == "json":
        typer.echo(json.dumps({
            "preset": response.preset,
            "start_date": response.start_date.isoformat(),
            "end_date": response.end_date.isoformat(),
            "initial_capital": str(response.initial_capital),
            "cost_bps": str(response.cost_bps),
            "final_equity": str(response.final_equity),
            "total_return_pct": response.total_return_pct,
            "max_drawdown_pct": response.max_drawdown_pct,
            "trade_count": response.trade_count,
            "win_rate_pct": response.win_rate_pct,
            "avg_trade_return_pct": response.avg_trade_return_pct,
            "profit_factor": response.profit_factor,
            "exposure_pct": response.exposure_pct,
            "skipped_no_cash": response.skipped_no_cash,
            "skipped_duplicate": response.skipped_duplicate,
            "skipped_no_forward_data": response.skipped_no_forward_data,
            "skipped_by_regime": response.skipped_by_regime,
            "warnings": response.warnings,
            "regime_stats": [stat.to_dict() for stat in response.regime_stats],
            "regime_by_date": {
                key.isoformat(): value.to_dict()
                for key, value in response.regime_by_date.items()
            },
            "trades": [trade.to_dict() for trade in response.trades],
            "equity_curve": [point.to_dict() for point in response.equity_curve],
        }, indent=2, default=str))
        return

    _display_swing_backtest(response, show_trades=show_trades)


def swing_compare(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option("--universe", "-u", help="Universe: lq45, idx80, idxcomp100, cached"),
    ] = None,
    variants: Annotated[
        str,
        typer.Option(
            "--variants",
            help="Comma-separated variants: baseline, sideways_only, weak_plus",
        ),
    ] = "baseline,sideways_only,weak_plus",
    preset: Annotated[
        str,
        typer.Option("--preset", help="Swing preset to validate"),
    ] = BACKTEST_FOREIGN_BOUNCE_PRESET,
    start: Annotated[
        str,
        typer.Option("--start", help="Backtest start date, YYYY-MM-DD"),
    ] = "2026-01-01",
    end: Annotated[
        Optional[str],
        typer.Option("--end", help="Backtest end date, YYYY-MM-DD (default: today)"),
    ] = None,
    capital: Annotated[
        int,
        typer.Option("--capital", "-c", help="Initial capital in IDR", min=1),
    ] = 100_000_000,
    risk_pct: Annotated[
        float,
        typer.Option("--risk-pct", help="% of capital risked per trade", min=0.01),
    ] = 1.0,
    max_positions: Annotated[
        int,
        typer.Option("--max-positions", help="Maximum concurrent open positions", min=1),
    ] = 5,
    take_profit: Annotated[
        float,
        typer.Option("--take-profit", help="Take-profit percentage", min=0.01),
    ] = 5.0,
    stop_loss: Annotated[
        float,
        typer.Option("--stop-loss", help="Stop-loss percentage", min=0.01),
    ] = 5.0,
    max_hold: Annotated[
        int,
        typer.Option("--max-hold", help="Maximum holding period in trading days", min=1),
    ] = 10,
    cost_bps: Annotated[
        float,
        typer.Option(
            "--cost-bps",
            help="One-way transaction cost in basis points (20 ~= 0.20%)",
            min=0,
        ),
    ] = float(DEFAULT_SWING_COST_BPS),
    benchmark: Annotated[
        str,
        typer.Option("--benchmark", help="Benchmark ticker for regime context"),
    ] = "^JKSE",
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Compare swing backtest regime variants side-by-side.

    Variants use the same portfolio simulation as `saham swing-backtest`;
    only the allowed entry regimes differ.
    """
    preset_name = preset.lower()
    if preset_name != BACKTEST_FOREIGN_BOUNCE_PRESET:
        typer.echo(
            f"Unknown swing preset '{preset}'. "
            f"Available presets: {BACKTEST_FOREIGN_BOUNCE_PRESET}",
            err=True,
        )
        raise typer.Exit(1)

    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end) if end else date.today()
        variant_names = _parse_compare_variants(variants)
    except ValueError as e:
        typer.echo(f"Error: invalid date format: {e}", err=True)
        raise typer.Exit(1)
    except typer.BadParameter as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    resolved_db = db_path or DEFAULT_DB_PATH
    try:
        ticker_list = resolve_tickers(
            universe=universe,
            explicit=list(tickers) if tickers else [],
            db_path=resolved_db,
        )
    except (UniverseNotFoundError, FileNotFoundError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if not ticker_list:
        typer.echo(
            "No tickers to compare. Specify --universe or provide ticker arguments.",
            err=True,
        )
        raise typer.Exit(1)

    typer.echo(
        f"Comparing {len(variant_names)} variants over {len(ticker_list)} tickers | "
        f"{start_date} to {end_date}..."
    )

    use_case = SwingBacktestUseCase(
        broker_repository=SQLiteBrokerRepository(resolved_db),
        market_repository=SQLiteMarketRepository(db_path=resolved_db),
    )
    rows: list[tuple[str, SwingBacktestResponse]] = []
    try:
        for variant in variant_names:
            allowed_regimes = SWING_COMPARE_VARIANTS[variant]
            response = use_case.execute(SwingBacktestRequest(
                tickers=ticker_list,
                start_date=start_date,
                end_date=end_date,
                preset=preset_name,
                capital=Decimal(str(capital)),
                risk_pct=Decimal(str(risk_pct)) / Decimal("100"),
                max_positions=max_positions,
                take_profit_pct=Decimal(str(take_profit)),
                stop_loss_pct=Decimal(str(stop_loss)),
                max_hold_days=max_hold,
                cost_bps=Decimal(str(cost_bps)),
                include_regime=True,
                benchmark_ticker=benchmark,
                allowed_regimes=allowed_regimes,
            ))
            rows.append((variant, response))
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if output_format == "json":
        typer.echo(json.dumps({
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "ticker_count": len(ticker_list),
            "variants": [
                {
                    "name": name,
                    "allowed_regimes": list(SWING_COMPARE_VARIANTS[name]),
                    "cost_bps": str(response.cost_bps),
                    "total_return_pct": response.total_return_pct,
                    "max_drawdown_pct": response.max_drawdown_pct,
                    "trade_count": response.trade_count,
                    "win_rate_pct": response.win_rate_pct,
                    "profit_factor": response.profit_factor,
                    "exposure_pct": response.exposure_pct,
                    "skipped_by_regime": response.skipped_by_regime,
                }
                for name, response in rows
            ],
        }, indent=2, default=str))
        return

    _display_swing_compare(
        rows=rows,
        start_date=start_date,
        end_date=end_date,
        universe_label=universe or "explicit",
    )


def regime(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols for breadth context"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option("--universe", "-u", help="Universe: lq45, idx80, idxcomp100, cached"),
    ] = "idx80",
    benchmark: Annotated[
        str,
        typer.Option("--benchmark", help="Benchmark ticker, e.g. ^JKSE"),
    ] = "^JKSE",
    as_of: Annotated[
        Optional[str],
        typer.Option("--as-of", help="Regime date, YYYY-MM-DD (default: today)"),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Show deterministic IHSG market regime context for swing trading.

    Uses local cached benchmark candles, universe breadth, and broker flow data.
    """
    resolved_db = db_path or DEFAULT_DB_PATH
    try:
        regime_date = date.fromisoformat(as_of) if as_of else date.today()
    except ValueError as e:
        typer.echo(f"Error: invalid date format: {e}", err=True)
        raise typer.Exit(1)

    try:
        ticker_list = resolve_tickers(
            universe=universe,
            explicit=list(tickers) if tickers else [],
            db_path=resolved_db,
        )
    except (UniverseNotFoundError, FileNotFoundError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if not ticker_list:
        typer.echo(
            "No tickers for regime breadth. Specify --universe or ticker arguments.",
            err=True,
        )
        raise typer.Exit(1)

    use_case = MarketRegimeUseCase(
        market_repository=SQLiteMarketRepository(db_path=resolved_db),
        broker_repository=SQLiteBrokerRepository(resolved_db),
    )
    try:
        response = use_case.execute(MarketRegimeRequest(
            universe=ticker_list,
            benchmark_ticker=benchmark,
            as_of_date=regime_date,
            breadth_sma_period=_SC.regime_breadth_sma_period,
            benchmark_sma_fast=_SC.regime_benchmark_sma_fast,
            benchmark_sma_slow=_SC.regime_benchmark_sma_slow,
        ))
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if output_format == "json":
        typer.echo(json.dumps(response.to_dict(), indent=2, default=str))
        return

    _display_regime(response)


# ─── size command ─────────────────────────────────────────────────────────────

def size(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBRI)")],
    capital: Annotated[
        Optional[int],
        typer.Option("--capital", "-c", help="Total capital in IDR (default: from config/user.yaml)", min=1),
    ] = None,
    risk_pct: Annotated[
        float,
        typer.Option("--risk-pct", help="% of capital at risk per trade (default: 1.0)"),
    ] = 1.0,
    entry_price: Annotated[
        Optional[float],
        typer.Option("--entry", help="Entry price in IDR (default: latest close)"),
    ] = None,
    atr_mult: Annotated[
        float,
        typer.Option("--atr-mult", help="ATR multiplier for stop distance (default: 1.5)"),
    ] = 1.5,
    rr: Annotated[
        float,
        typer.Option("--rr", help="Reward:risk ratio for target (default: 2.0)"),
    ] = 2.0,
    atr_period: Annotated[
        int,
        typer.Option("--atr-period", help="ATR period (default: 14)", min=2),
    ] = 14,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    ATR-based position sizing calculator for IDX swing trades.

    Computes stop price (1.5 × ATR below entry), target (2× risk/reward),
    and exact lot count from fixed-fractional capital risk.

    Examples:
        saham swing size BBRI --capital 10000000
        saham swing size BBRI --capital 10000000 --risk-pct 2 --entry 4825
        saham swing size BBRI --capital 50000000 --risk-pct 1 --rr 2.5
        saham swing size BBRI --capital 10000000 --atr-mult 2.0
    """
    resolved_db = db_path or DEFAULT_DB_PATH
    ticker_upper = ticker.upper()
    today = date.today()

    if capital is None:
        _cfg = get_swing_default("capital")
        if _cfg is not None:
            capital = int(_cfg)
    if capital is None:
        typer.echo(
            "Error: --capital is required. Pass it as a flag or set swing.capital in config/user.yaml.",
            err=True,
        )
        raise typer.Exit(1)

    market_repo = SQLiteMarketRepository(db_path=resolved_db)
    registry = create_indicator_registry()

    candles = market_repo.get_candles(ticker_upper)
    if not candles:
        typer.echo(
            f"No data for {ticker_upper}. Run: saham update {ticker_upper} --days 365",
            err=True,
        )
        raise typer.Exit(1)

    latest_close = candles[-1].close

    # Compute ATR
    atr_value: Decimal | None = None
    try:
        atr_values = registry.compute("ATR", candles, atr_period)
        if atr_values:
            atr_value = atr_values[-1][1]  # registry returns (date, value) tuples
    except Exception as e:
        typer.echo(f"Error computing ATR: {e}", err=True)
        raise typer.Exit(1)

    if not atr_value or atr_value <= 0:
        typer.echo(
            f"Cannot compute ATR({atr_period}) for {ticker_upper} — insufficient data.", err=True
        )
        typer.echo(f"Tip: Run: saham update {ticker_upper} --days 90", err=True)
        raise typer.Exit(1)

    entry_dec = Decimal(str(entry_price)) if entry_price else latest_close

    try:
        result = compute_position_size(
            entry=entry_dec,
            atr=atr_value,
            capital=Decimal(str(capital)),
            risk_pct=Decimal(str(risk_pct)) / Decimal("100"),
            atr_multiplier=Decimal(str(atr_mult)),
            reward_risk=Decimal(str(rr)),
        )
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if output_format == "json":
        out = {
            "ticker": ticker_upper,
            "date": str(today),
            "entry": float(result.entry_price),
            "atr": float(result.atr),
            "atr_period": atr_period,
            "atr_multiplier": float(result.atr_multiplier),
            "stop_price": float(result.stop_price),
            "stop_distance": float(result.stop_distance),
            "stop_pct": float(result.stop_pct),
            "target_price": float(result.target_price),
            "target_pct": float(result.target_pct),
            "reward_risk_ratio": float(result.reward_risk_ratio),
            "capital": float(result.capital),
            "risk_pct": risk_pct,
            "risk_amount": float(result.risk_amount),
            "reward_amount": float(result.reward_amount),
            "lots": result.lots,
            "shares": result.shares,
            "position_cost": float(result.position_cost),
            "capital_used_pct": float(result.capital_used_pct),
        }
        typer.echo(json.dumps(out, indent=2))
        return

    # ── Table output ──────────────────────────────────────────────────────────
    typer.echo("")
    _sep("=")
    typer.echo(typer.style(
        f"POSITION SIZE — {ticker_upper} · {today}",
        fg=typer.colors.BRIGHT_WHITE, bold=True,
    ))
    _sep("=")

    typer.echo("")
    typer.echo(typer.style("INPUTS", bold=True))
    typer.echo(
        f"  Capital            {capital:>18,} IDR"
    )
    typer.echo(
        f"  Risk per trade     {risk_pct:>17.2f} %  =  {float(result.risk_amount):>12,.0f} IDR"
    )
    entry_src = "latest close" if not entry_price else "specified"
    typer.echo(
        f"  Entry ({entry_src})   {float(entry_dec):>18,.0f}"
    )
    typer.echo(
        f"  ATR({atr_period:>2})           {float(atr_value):>18.2f}"
    )
    typer.echo(
        f"  ATR multiplier     {float(result.atr_multiplier):>18.1f}×"
    )
    typer.echo(
        f"  Reward : Risk      {float(result.reward_risk_ratio):>18.1f}"
    )

    typer.echo("")
    typer.echo(typer.style("STOP", bold=True))
    typer.echo(
        f"  Stop price         {float(result.stop_price):>18,.0f}"
    )
    typer.echo(
        f"  Stop distance      {float(result.stop_distance):>18,.0f}  per share"
    )
    typer.echo(
        f"  Stop %             {float(result.stop_pct):>18.2f} %"
    )

    typer.echo("")
    typer.echo(typer.style("TARGET", bold=True))
    typer.echo(
        f"  Target price       {float(result.target_price):>18,.0f}"
    )
    typer.echo(
        f"  Target %           {float(result.target_pct):>18.2f} %"
    )

    typer.echo("")
    typer.echo(typer.style("POSITION", bold=True))
    if result.lots == 0:
        typer.echo(typer.style(
            f"  INSUFFICIENT CAPITAL — cannot fill 1 lot.\n"
            f"  Need at least {100 * float(entry_dec):,.0f} IDR for 1 lot "
            f"(stop = {float(result.stop_distance):.0f}/share).",
            fg=typer.colors.RED,
        ))
    else:
        typer.echo(
            f"  Raw shares         {int(result.risk_amount / result.stop_distance):>18}"
        )
        typer.echo(
            f"  Round lots         {result.lots:>18}  lots = {result.shares:,} shares"
        )
        typer.echo(
            f"  Position cost      {float(result.position_cost):>18,.0f}  IDR  "
            f"({float(result.capital_used_pct):.1f}% of capital)"
        )
        actual_risk = Decimal(str(result.shares)) * result.stop_distance
        actual_reward = actual_risk * result.reward_risk_ratio
        typer.echo(
            f"  Actual risk        {float(actual_risk):>18,.0f}  IDR  "
            f"(vs target {float(result.risk_amount):,.0f})"
        )
        typer.echo(
            f"  Actual reward      {float(actual_reward):>18,.0f}  IDR"
        )

    typer.echo("")
    _sep("=")
    if result.lots > 0:
        typer.echo(typer.style(
            f"ACTION: Buy {result.lots} lots at {float(entry_dec):,.0f}.  "
            f"Stop {float(result.stop_price):,.0f}.  "
            f"Target {float(result.target_price):,.0f}.",
            bold=True,
        ))
    _sep("=")
    typer.echo(typer.style(
        "DISCLAIMER: Analysis only, not trading advice.",
        fg=typer.colors.BRIGHT_BLACK,
    ))
    typer.echo("")


# ─── swing typer family ──────────────────────────────────────────────────────

from src.adapters.cli.accumulation_commands import (  # noqa: E402
    accumulation_audit,
    accumulation_log,
    accumulation_review,
    accumulation_run,
)

swing_app = typer.Typer(
    name="swing",
    help="Swing trading workflow — screen, analyze, size, backtest, and journal.",
    no_args_is_help=True,
)
swing_app.command("analyze")(swing)
swing_app.command("backtest")(swing_backtest)
swing_app.command("compare")(swing_compare)
swing_app.command("size")(size)
swing_app.command("screen")(accumulation_run)
swing_app.command("audit")(accumulation_audit)
swing_app.command("log")(accumulation_log)
swing_app.command("review")(accumulation_review)
