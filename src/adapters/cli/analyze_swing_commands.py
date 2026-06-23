"""
CLI implementation functions for saham analyze swing commands.

Public command registration lives in lifecycle routers:
  saham analyze swing
  saham analyze swing-compare

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

from src.adapters.cli.analyze_swing_broker_display import (
    BrokerDetail,
    BrokerQualityNote,
    FlowDetail,
    build_broker_detail,
    build_broker_quality_note,
    build_flow_detail,
)
from src.adapters.cli.analyze_swing_display import (
    SwingDisplayConfig,
    display_swing_compare,
)
from src.application.services.bootstrap import create_indicator_registry
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
from src.application.use_case.market_regime import MarketRegimeResponse
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
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.config.user_config import get_swing_default
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository
from src.infrastructure.sentiment import SentimentFactory

DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)
_W = 70  # display width

FOREIGN_BOUNCE_PRESET = "foreign-bounce"
FOREIGN_BOUNCE_MAX_HOLD_DAYS = 10

# Legacy constants kept for backtest use — actual analyze/screen uses resolve_preset_targets()
FOREIGN_BOUNCE_TAKE_PROFIT = Decimal("5")
FOREIGN_BOUNCE_STOP_LOSS = Decimal("5")

_SWING_SCREENER_CONFIG_PATH = Path(APP_CFG.storage.swing_config)


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
    from src.infrastructure.browser.stockbit_providers import StockbitProviders
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
    from src.adapters.cli.analyze_swing_display import print_swing_output

    print_swing_output(
        ticker=ticker,
        today=today,
        profile=profile,
        strategy_name=strategy_name,
        data_freshness=data_freshness,
        flow_detail=flow_detail,
        broker_detail=broker_detail,
        window=window,
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
        sentiment_verbose=sentiment_verbose,
        no_backtest=no_backtest,
        no_sentiment=no_sentiment,
        strategy_risk_level=strategy_risk_level,
        strategy_risk_name=strategy_risk_name,
        config=_DISPLAY_CONFIG,
    )


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
        typer.Option("--window", "-w", help="Accumulation analysis window in broker sessions"),
    ] = APP_CFG.swing.window,
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
        typer.Option("--risk-pct", help="% of capital at risk per trade"),
    ] = APP_CFG.swing.risk_pct,
    entry_price: Annotated[
        Optional[float],
        typer.Option("--entry", help="Entry price in IDR (default: latest close)"),
    ] = None,
    atr_mult: Annotated[
        float,
        typer.Option("--atr-mult", help="ATR multiplier for stop distance"),
    ] = APP_CFG.swing.atr_mult,
    rr: Annotated[
        float,
        typer.Option("--rr", help="Reward:risk ratio for target"),
    ] = APP_CFG.swing.rr,
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
    ] = APP_CFG.analysis.regime_universe,
    benchmark: Annotated[
        str,
        typer.Option("--benchmark", help="Benchmark ticker for regime context"),
    ] = APP_CFG.analysis.benchmark,
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
        build_broker_quality_note=lambda broker_detail, preset_eval: build_broker_quality_note(
            broker_detail,
            preset_eval,
            smart_sell_min_share_pct=_SC.smart_sell_min_share_pct,
        ),
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
    ] = APP_CFG.trading.capital,
    risk_pct: Annotated[
        float,
        typer.Option("--risk-pct", help="% of capital risked per trade", min=0.01),
    ] = APP_CFG.swing.risk_pct,
    max_positions: Annotated[
        int,
        typer.Option("--max-positions", help="Maximum concurrent open positions", min=1),
    ] = 5,
    take_profit: Annotated[
        float,
        typer.Option("--take-profit", help="Take-profit percentage", min=0.01),
    ] = APP_CFG.swing.take_profit,
    stop_loss: Annotated[
        float,
        typer.Option("--stop-loss", help="Stop-loss percentage", min=0.01),
    ] = APP_CFG.swing.stop_loss,
    max_hold: Annotated[
        int,
        typer.Option("--max-hold", help="Maximum holding period in trading days", min=1),
    ] = APP_CFG.swing.max_hold,
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
    ] = APP_CFG.analysis.benchmark,
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


