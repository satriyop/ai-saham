"""
CLI implementation functions for swing analysis and sizing commands.

Public command registration lives in lifecycle routers:
  saham analyze swing
  saham analyze swing-compare
  saham trade size
  saham trade backtest-swing

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
from typing import Annotated, Any, Optional

import typer
from rich.console import Group
from rich.text import Text

from src.adapters.cli.rich_display import compact_table, console, panel
from src.adapters.cli.swing_broker_display import (
    BrokerDetail,
    BrokerQualityNote,
    FlowDetail,
    build_broker_detail,
    build_broker_quality_note,
    build_flow_detail,
    fmt_broker_detail_lines,
    fmt_money_short,
    fmt_money_short_signed,
)
from src.adapters.cli.swing_analysis_display import (
    SwingDisplayConfig,
    format_failed_gates_summary as _format_failed_gates_summary,
    notation_detail as _notation_detail,
    notation_label as _notation_label,
    section_header as _display_section_header,
    signal_label as _display_signal_label,
    style_bb as _style_bb,
    style_risk as _style_risk,
    style_score as _display_style_score,
    style_sentiment_call as _style_sentiment_call,
    style_trend as _style_trend,
    style_winrate as _style_winrate,
    swing_plan_text as _display_swing_plan_text,
    swing_summary_parts as _swing_summary_parts,
)
from src.adapters.cli.swing_display import (
    display_regime,
    display_swing_backtest,
    display_swing_compare,
)
from src.application.services.bootstrap import create_indicator_registry
from src.application.services.position_sizer import (
    PercentSizingResult,
    SizingResult,
    compute_position_size,
)
from src.application.services.universe_loader import (
    UniverseNotFoundError,
    resolve_tickers,
)
from src.application.use_case.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenRequest,
    AccumulationScreenUseCase,
    resolve_preset_targets,
)
from src.application.use_case.fetch_sentiment import (
    FetchSentimentRequest,
    FetchSentimentUseCase,
)
from src.application.use_case.market_regime import (
    MarketRegimeRequest,
    MarketRegimeResponse,
    MarketRegimeUseCase,
)
from src.application.use_case.swing_analysis_workflow import (
    SwingAnalysisDataUnavailable,
    SwingAnalysisWorkflowRequest,
    SwingAnalysisWorkflowUseCase,
)
from src.application.use_case.swing_backtest import (
    DEFAULT_SWING_COST_BPS,
    SwingBacktestRequest,
    SwingBacktestResponse,
    SwingBacktestUseCase,
)
from src.application.use_case.swing_backtest import (
    FOREIGN_BOUNCE_PRESET as BACKTEST_FOREIGN_BOUNCE_PRESET,
)
from src.infrastructure.browser.stockbit_analyst import StockbitAnalystConsensusProvider
from src.infrastructure.browser.stockbit_bandar import StockbitBandarDetectorProvider
from src.infrastructure.browser.stockbit_corp_action import StockbitCorporateActionRepository
from src.infrastructure.browser.stockbit_fundamentals import StockbitFundamentalsProvider
from src.infrastructure.browser.stockbit_insider import StockbitInsiderActivityProvider
from src.infrastructure.browser.stockbit_seasonality import StockbitSeasonalityProvider
from src.infrastructure.browser.stockbit_shareholding import StockbitShareholdingProvider
from src.infrastructure.browser.stockbit_ticker_notation import StockbitTickerNotationProvider
from src.infrastructure.config.user_config import get_swing_default
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository
from src.infrastructure.sentiment import SentimentFactory

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

from src.infrastructure.config.swing_config import (  # noqa: E402
    load_swing_config as _load_swing_screener_config_typed,
)

# Load from config/swing_screener.yaml; fall back to _SwingConfig defaults on any error.
_SC = _load_swing_screener_config_typed()
_DISPLAY_CONFIG = SwingDisplayConfig(
    enter_min_score=_SC.enter_min_score,
    watch_min_score=_SC.watch_min_score,
    coiled_spring_bb_pctile=_SC.coiled_spring_bb_pctile,
    coiled_spring_min_score=_SC.coiled_spring_min_score,
    strong_min_score=_SC.strong_min_score,
    strong_min_streak=_SC.strong_min_streak,
    building_min_score=_SC.building_min_score,
    building_min_streak=_SC.building_min_streak,
    foreign_bounce_max_hold_days=FOREIGN_BOUNCE_MAX_HOLD_DAYS,
)

SMART_MONEY_BROKERS = set(_SC.smart_money_brokers)
NOISE_BROKERS       = set(_SC.noise_brokers)


def _make_stockbit_providers(db_path: Path) -> Any:
    """Return read-only Stockbit providers backed by SQLite cache.

    No API calls are made here. broker_provider=None means each provider
    reads from SQLite and returns None on a cache miss. The only command
    that fetches live data from Stockbit is `saham fetch market`.
    """
    from src.adapters.cli.accumulation_commands import StockbitProviders
    return StockbitProviders(
        corp_repo=StockbitCorporateActionRepository(broker_provider=None, db_path=db_path),
        season_prov=StockbitSeasonalityProvider(broker_provider=None, db_path=db_path),
        insider_prov=StockbitInsiderActivityProvider(broker_provider=None, db_path=db_path),
        analyst_prov=StockbitAnalystConsensusProvider(broker_provider=None, db_path=db_path),
        shareholding_prov=StockbitShareholdingProvider(broker_provider=None, db_path=db_path),
        bandar_prov=StockbitBandarDetectorProvider(broker_provider=None, db_path=db_path),
        fundamentals_prov=StockbitFundamentalsProvider(broker_provider=None, db_path=db_path),
        notation_prov=StockbitTickerNotationProvider(broker_provider=None, db_path=db_path),
    )
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


# ─── formatting helpers ──────────────────────────────────────────────────────

def _style_risk(level: str) -> str:
    from src.adapters.cli.swing_analysis_display import style_risk
    return style_risk(level)


def _style_trend(trend: str) -> str:
    from src.adapters.cli.swing_analysis_display import style_trend
    return style_trend(trend)


def _style_sentiment_call(call: str) -> str:
    from src.adapters.cli.swing_analysis_display import style_sentiment_call
    return style_sentiment_call(call)


def _style_score(s: float) -> str:
    return _display_style_score(s, _DISPLAY_CONFIG)


def _style_bb(pctile: float) -> str:
    from src.adapters.cli.swing_analysis_display import style_bb
    return style_bb(pctile)


def _style_winrate(wr: Decimal) -> str:
    from src.adapters.cli.swing_analysis_display import style_winrate
    return style_winrate(wr)


def _sep(char: str = "=") -> None:
    typer.echo(char * _W)


def _section_header(title: str, right: str = "") -> None:
    _display_section_header(title, right, width=_W)


def _signal_label(c: AccumulationCandidate) -> str:
    return _display_signal_label(c, _DISPLAY_CONFIG)


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


def _swing_plan_text(
    ticker: str,
    capital: int | None,
    atr_value: Decimal | None,
    sizing: SizingResult | None,
    preset_eval: PresetEvaluation | None,
    preset_sizing: PercentSizingResult | None,
    strategy_risk_level: str | None,
    strategy_risk_name: str | None,
) -> tuple[str, str]:
    return _display_swing_plan_text(
        ticker=ticker,
        capital=capital,
        atr_value=atr_value,
        sizing=sizing,
        preset_eval=preset_eval,
        preset_sizing=preset_sizing,
        strategy_risk_level=strategy_risk_level,
        strategy_risk_name=strategy_risk_name,
        config=_DISPLAY_CONFIG,
    )


def _print_swing_rich_overview(
    ticker: str,
    today: date,
    profile: str,
    strategy_name: str,
    data_freshness: DataFreshness,
    broker_detail: BrokerDetail | None,
    accum: AccumulationCandidate | None,
    risk_resp,
    atr_value: Decimal | None,
    sizing: SizingResult | None,
    preset_eval: PresetEvaluation | None,
    preset_sizing: PercentSizingResult | None,
    broker_quality_note: BrokerQualityNote | None,
    market_regime: MarketRegimeResponse | None,
    capital: int | None,
    backtest_result,
    sentiment_resp,
    sentiment_warning: str | None,
    strategy_risk_level: str | None,
    strategy_risk_name: str | None,
) -> None:
    summary_parts = _swing_summary_parts(accum, risk_resp, backtest_result, sentiment_resp)
    summary_text = " · ".join(summary_parts) if summary_parts else "insufficient data for assessment"
    plan_text, plan_style = _swing_plan_text(
        ticker,
        capital,
        atr_value,
        sizing,
        preset_eval,
        preset_sizing,
        strategy_risk_level,
        strategy_risk_name,
    )

    data_table = compact_table(show_header=False)
    data_table.add_column("Metric", style="bold")
    data_table.add_column("Value")
    data_table.add_row("Analysis date", str(today))
    data_table.add_row("Profile", profile)
    data_table.add_row("Strategy", strategy_name)
    data_table.add_row("Candles through", _fmt_date(data_freshness.candle_end))
    data_table.add_row("Broker flow through", _fmt_date(data_freshness.broker_end))
    if market_regime is not None:
        data_table.add_row("Market regime", f"{market_regime.label} ({market_regime.score}/7)")
    notation_detail = _notation_detail(accum.ticker_notation) if accum is not None else ""
    if notation_detail:
        data_table.add_row("Notation", notation_detail)

    decision = compact_table(show_header=False)
    decision.add_column("Label", style="bold")
    decision.add_column("Value")
    decision.add_row("SUMMARY", Text(summary_text, style="bold"))
    decision.add_row("PLAN", Text(plan_text, style=f"bold {plan_style}"))

    signals = compact_table()
    signals.add_column("Signal", style="bold")
    signals.add_column("Status")
    signals.add_column("Detail")
    if accum is not None:
        signals.add_row(
            "Accumulation",
            f"{accum.score:.1f}",
            f"streak {accum.consecutive_streak}s; trend {accum.trend}; flow {_fmt_pct(accum.avg_flow_ratio, True)}",
        )
    else:
        signals.add_row("Accumulation", "missing", f"Run: saham fetch broker {ticker}")
    if preset_eval is not None:
        failed = "; ".join(preset_eval.failed_reasons[:2]) if preset_eval.failed_reasons else "all gates passed"
        signals.add_row("Preset", preset_eval.classification, failed)
    if accum is not None and accum.ticker_notation is not None:
        note_status = _notation_label(accum.ticker_notation)
        if note_status != "-":
            signals.add_row("Notation", note_status, _notation_detail(accum.ticker_notation))
    if risk_resp is not None:
        r = risk_resp.assessment
        signals.add_row("Risk", r.risk_level_name, f"confidence {r.confidence}/100")
    if broker_detail is not None:
        signals.add_row("Broker quality", broker_detail.quality, broker_detail.broker_weight_quality)
    if broker_quality_note is not None:
        signals.add_row("Broker note", broker_quality_note.level, broker_quality_note.message)
    if sentiment_resp and not sentiment_resp.warning:
        snap = sentiment_resp.snapshot
        signals.add_row(
            "Sentiment",
            snap.overall_sentiment.value.upper(),
            f"{snap.total_count} headlines; confidence {snap.confidence_pct}%",
        )
    elif sentiment_warning:
        signals.add_row("Sentiment", "unavailable", sentiment_warning)
    if backtest_result is not None and backtest_result.trade_count > 0:
        signals.add_row(
            "History",
            f"{backtest_result.trade_count} trades",
            f"WR {float(backtest_result.win_rate):.1f}%; PF {float(backtest_result.profit_factor):.2f}",
        )

    sections = [
        Text("Decision", style="bold cyan"),
        decision,
        Text("Data Freshness", style="bold cyan"),
        data_table,
        Text("Signal Snapshot", style="bold cyan"),
        signals,
    ]

    chosen_sizing = preset_sizing or sizing
    if capital is not None and chosen_sizing is not None:
        sizing_table = compact_table(show_header=False)
        sizing_table.add_column("Metric", style="bold")
        sizing_table.add_column("Value")
        sizing_table.add_row("Capital", f"{capital:,.0f} IDR")
        sizing_table.add_row("Entry", f"{float(chosen_sizing.entry_price):,.0f}")
        sizing_table.add_row("Stop", f"{float(chosen_sizing.stop_price):,.0f}")
        sizing_table.add_row("Target", f"{float(chosen_sizing.target_price):,.0f}")
        sizing_table.add_row("Lots", f"{chosen_sizing.lots:,}")
        sections.extend([Text("Sizing", style="bold cyan"), sizing_table])

    warnings = list(data_freshness.warnings)
    if market_regime is not None:
        warnings.extend(market_regime.warnings)
    if warnings:
        warning_table = compact_table(show_header=False)
        warning_table.add_column("Warning")
        for warning in warnings[:5]:
            warning_table.add_row(f"- {warning}")
        sections.extend([Text("Warnings", style="bold yellow"), warning_table])

    console().print(
        panel(
            Group(*sections),
            title=f"Swing Decision - {ticker}",
            subtitle=f"{today.isoformat()} / {profile}",
        )
    )



def _fmt_pct(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "N/A"
    return f"{value:+.2f}%" if signed else f"{value:.1f}%"


def _fmt_date(value: date | None) -> str:
    return value.isoformat() if value else "missing"


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


def _auto_refresh_swing_data(
    ticker: str,
    db_path: Path,
    force_refresh: bool,
) -> tuple[str, ...]:
    """Refresh only the requested ticker for swing analysis."""
    from src.adapters.cli.fetch_market_commands import (
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
    _print_swing_rich_overview(
        ticker=ticker,
        today=today,
        profile=profile,
        strategy_name=strategy_name,
        data_freshness=data_freshness,
        broker_detail=broker_detail,
        accum=accum,
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
        strategy_risk_level=strategy_risk_level,
        strategy_risk_name=strategy_risk_name,
    )

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
        notation_detail = _notation_detail(accum.ticker_notation)
        if notation_detail:
            color = typer.colors.YELLOW if accum.ticker_notation and accum.ticker_notation.has_warning else typer.colors.WHITE
            typer.echo(typer.style(f"  NOTATION  {notation_detail}", fg=color))

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

        # Company fundamentals — P/E, ROE, NPM, Piotroski F-Score
        if accum.fundamentals is not None:
            fund = accum.fundamentals
            if fund.is_quality:
                fund_color = typer.colors.GREEN
            elif fund.roe_ttm is not None and fund.roe_ttm >= 10.0:
                fund_color = typer.colors.YELLOW
            else:
                fund_color = typer.colors.RED
            typer.echo(typer.style(f"  📈 FUNDAM: {fund.label}", fg=fund_color))
    else:
        _section_header(f"ACCUMULATION ({window} sessions)")
        typer.echo(typer.style(
            f"  No broker flow data. Run: saham fetch broker {ticker}",
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
            f"  Net    {fmt_money_short(flow_detail.total_net_flow)} IDR   "
            f"BUY/SELL  {flow_detail.buy_sessions}/{flow_detail.sell_sessions}   "
            f"STREAK  {flow_detail.consecutive_buy_sessions}s"
        )
        latest_flow = (
            fmt_money_short(flow_detail.latest_net_flow)
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
            f"  No broker flow data. Run: saham fetch broker {ticker}",
            fg=typer.colors.BRIGHT_BLACK,
        ))

    # ── NAMED BROKER DETAIL ────────────────────────────────────────────────
    if broker_detail:
        typer.echo("")
        _section_header(
            f"BROKER DETAIL ({broker_detail.detail_sessions}/{broker_detail.window_sessions} sessions)",
            f"through: {_fmt_date(broker_detail.through_date)} · {broker_detail.source}",
        )
        typer.echo(f"  Top buyers       {fmt_broker_detail_lines(broker_detail.top_buyers)}")
        typer.echo(f"  Top sellers      {fmt_broker_detail_lines(broker_detail.top_sellers)}")
        typer.echo(
            f"  Smart flow       {fmt_money_short_signed(broker_detail.smart_flow)} IDR   "
            f"Noise flow  {fmt_money_short_signed(broker_detail.noise_flow)} IDR"
        )
        smart_share = (
            f"{broker_detail.smart_share_pct:.1f}%"
            if broker_detail.smart_share_pct is not None else "N/A"
        )
        typer.echo(
            f"  Weighted net     {fmt_money_short_signed(broker_detail.weighted_net_flow)} IDR   "
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
            f"  Could not run backtest. Run: saham fetch market {ticker} --days 730",
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
    summary_parts = _swing_summary_parts(accum, risk_resp, backtest_result, sentiment_resp)

    if summary_parts:
        typer.echo("SUMMARY: " + typer.style(" · ".join(summary_parts), bold=True))
    else:
        typer.echo("SUMMARY: insufficient data for assessment")

    plan_text, plan_style = _swing_plan_text(
        ticker,
        capital,
        atr_value,
        sizing,
        preset_eval,
        preset_sizing,
        strategy_risk_level,
        strategy_risk_name,
    )
    typer.echo(typer.style(f"PLAN:  {plan_text}", fg=plan_style, bold=plan_style in {"green", "red"}))

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

    Replaces the multi-command morning workflow:
      saham screen accum, saham analyze risk, saham indicator compute,
      saham trade backtest-swing, saham analyze sentiment — all in one.

    Examples:
        saham analyze swing BBRI
        saham analyze swing BBRI --preset foreign-bounce --capital 10000000
        saham analyze swing BBRI --capital 10000000 --risk-pct 1
        saham analyze swing BBRI --profile conservative --no-sentiment
        saham analyze swing BBRI --no-refresh --no-backtest --no-sentiment
        saham analyze swing BBRI --no-backtest --no-sentiment
        saham analyze swing BBRI --force-refresh
        saham analyze swing BBRI --capital 10000000 --entry 4825 --rr 2.5
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

    def _build_accumulation_candidate(ticker: str, window: int):
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
            fundamentals_provider=_sb.fundamentals_prov,
            ticker_notation_provider=_sb.notation_prov,
        )
        accum_resp = accum_uc.execute(
            AccumulationScreenRequest(
                tickers=[ticker],
                window_days=window,
                min_net_buy_days=0,
                min_score=0.0,
                tier1_broker_codes=_SC.tier1_broker_codes,
            )
        )
        return accum_resp.candidates[0] if accum_resp.candidates else None

    workflow = SwingAnalysisWorkflowUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        registry=registry,
        refresh_data=_auto_refresh_swing_data,
        build_data_freshness=_build_data_freshness,
        build_flow_detail=build_flow_detail,
        build_broker_detail=lambda ticker, broker_repo, window_sessions=5, as_of_date=None: build_broker_detail(
            ticker=ticker,
            broker_repo=broker_repo,
            window_sessions=window_sessions,
            as_of_date=as_of_date,
            smart_money_brokers=SMART_MONEY_BROKERS,
            noise_brokers=NOISE_BROKERS,
            broker_weights=BROKER_WEIGHTS,
            smart_share_threshold_pct=_SC.smart_share_threshold_pct,
        ),
        build_accumulation_candidate=_build_accumulation_candidate,
        evaluate_preset=_evaluate_foreign_bounce,
        build_broker_quality_note=build_broker_quality_note,
        fetch_sentiment=_fetch_swing_sentiment,
        load_swing_config=_load_swing_screener_config,
        resolve_preset_targets=resolve_preset_targets,
    )
    try:
        workflow_response = workflow.execute(
            SwingAnalysisWorkflowRequest(
                ticker=ticker_upper,
                today=today,
                profile=profile,
                strategy=strategy,
                preset_name=preset_name,
                window=window,
                flow_window=flow_window,
                capital=capital,
                risk_pct=risk_pct,
                entry_price=entry_price,
                atr_mult=atr_mult,
                rr=rr,
                no_sentiment=no_sentiment,
                sentiment_verbose=sentiment_verbose,
                no_backtest=no_backtest,
                auto_refresh=auto_refresh,
                force_refresh=force_refresh,
                with_regime=with_regime,
                regime_universe=regime_universe,
                benchmark=benchmark,
                risk_strategy=risk_strategy,
                db_path=resolved_db,
            )
        )
    except SwingAnalysisDataUnavailable:
        typer.echo(
            f"No data for {ticker_upper}. Run: saham fetch market {ticker_upper} --days 365",
            err=True,
        )
        raise typer.Exit(1)

    data_freshness = workflow_response.data_freshness
    flow_detail = workflow_response.flow_detail
    broker_detail = workflow_response.broker_detail
    accum_candidate = workflow_response.accumulation_candidate
    risk_resp = workflow_response.risk_response
    strategy_risk_level = workflow_response.strategy_risk_level
    strategy_risk_name = workflow_response.strategy_risk_name
    atr_value = workflow_response.atr_value
    sizing = workflow_response.sizing
    preset_eval = workflow_response.preset_eval
    preset_sizing = workflow_response.preset_sizing
    broker_quality_note = workflow_response.broker_quality_note
    backtest_result = workflow_response.backtest_result
    sentiment_resp = workflow_response.sentiment_response
    sentiment_warning = workflow_response.sentiment_warning
    market_regime = workflow_response.market_regime
    _tp_pct = workflow_response.take_profit_pct
    _sl_pct = workflow_response.stop_loss_pct
    _regime_label = workflow_response.regime_label

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
                "fundamentals": (
                    accum_candidate.fundamentals.to_dict()
                    if accum_candidate and accum_candidate.fundamentals else None
                ),
                "ticker_notation": (
                    accum_candidate.ticker_notation.to_dict()
                    if accum_candidate and accum_candidate.ticker_notation else None
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
        typer.Option("--universe", "-u", help="Universe name or 'cached' — see `saham fetch universe list`"),
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

    display_swing_backtest(response, show_trades=show_trades)


def swing_compare(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option("--universe", "-u", help="Universe name or 'cached' — see `saham fetch universe list`"),
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

    Variants use the same portfolio simulation as `saham trade backtest-swing`;
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

    display_swing_compare(
        rows=rows,
        start_date=start_date,
        end_date=end_date,
        universe_label=universe or "explicit",
        variants_by_name=SWING_COMPARE_VARIANTS,
    )


def regime(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols for breadth context"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option("--universe", "-u", help="Universe name or 'cached' — see `saham fetch universe list`"),
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

    display_regime(response)


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
        saham trade size BBRI --capital 10000000
        saham trade size BBRI --capital 10000000 --risk-pct 2 --entry 4825
        saham trade size BBRI --capital 50000000 --risk-pct 1 --rr 2.5
        saham trade size BBRI --capital 10000000 --atr-mult 2.0
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
            f"No data for {ticker_upper}. Run: saham fetch market {ticker_upper} --days 365",
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
        typer.echo(f"Tip: Run: saham fetch market {ticker_upper} --days 90", err=True)
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
