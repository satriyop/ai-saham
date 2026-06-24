"""
CLI implementation for saham screen accum command.

Public command registration lives in lifecycle routers:
  saham screen accum

Layer: Adapter
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.services.bootstrap import create_indicator_registry
from src.application.services.broker_quality import (
    BrokerQualitySnapshot,
    compute_broker_quality_batch,
)
from src.application.services.strategy_loader import StrategyLoader, StrategyNotFoundError
from src.application.services.universe_loader import (
    UniverseNotFoundError,
    resolve_tickers,
)
from src.application.use_case.accumulation_screen_use_case import (
    AccumulationScreenRequest,
    AccumulationScreenResponse,
    AccumulationScreenUseCase,
)
from src.application.use_case.assess_risk_use_case import AssessRiskRequest, AssessRiskUseCase
from src.domain.rules.bandar_gate import BandarGate
from src.domain.rules.free_float_gate import FreeFloatGate
from src.domain.rules.fundamental_gate import FundamentalGate
from src.domain.rules.liquidity_gate import LiquidityGate
from src.infrastructure.browser.stockbit_analyst import StockbitAnalystConsensusProvider
from src.infrastructure.browser.stockbit_bandar import StockbitBandarDetectorProvider
from src.infrastructure.browser.stockbit_corp_action import StockbitCorporateActionRepository
from src.infrastructure.browser.stockbit_forward_estimates import StockbitForwardEstimatesProvider
from src.infrastructure.browser.stockbit_fundamentals import StockbitFundamentalsProvider
from src.infrastructure.browser.stockbit_insider import StockbitInsiderActivityProvider
from src.infrastructure.browser.stockbit_providers import StockbitProviders
from src.infrastructure.browser.stockbit_seasonality import StockbitSeasonalityProvider
from src.infrastructure.browser.stockbit_shareholding import StockbitShareholdingProvider
from src.infrastructure.browser.stockbit_ticker_notation import StockbitTickerNotationProvider
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.config.swing_config import load_swing_config as _load_swing_config
from src.infrastructure.config.user_config import get_swing_default
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

_SC = _load_swing_config()

DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)
DEFAULT_ACCUM_DB_PATH = DEFAULT_DB_PATH  # alias kept for external imports

FOREIGN_BOUNCE_PRESET = "foreign-bounce"

# Backward-compat alias — callers use BrokerQualitySnapshot from Application layer.
ScreenBrokerQuality = BrokerQualitySnapshot


def _make_stockbit_providers(db_path: Path) -> StockbitProviders:
    return StockbitProviders(
        corp_repo=StockbitCorporateActionRepository(broker_provider=None, db_path=db_path),
        season_prov=StockbitSeasonalityProvider(broker_provider=None, db_path=db_path),
        insider_prov=StockbitInsiderActivityProvider(broker_provider=None, db_path=db_path),
        analyst_prov=StockbitAnalystConsensusProvider(broker_provider=None, db_path=db_path),
        shareholding_prov=StockbitShareholdingProvider(broker_provider=None, db_path=db_path),
        bandar_prov=StockbitBandarDetectorProvider(broker_provider=None, db_path=db_path),
        fundamentals_prov=StockbitFundamentalsProvider(broker_provider=None, db_path=db_path),
        notation_prov=StockbitTickerNotationProvider(broker_provider=None, db_path=db_path),
        forward_estimates_prov=StockbitForwardEstimatesProvider(broker_provider=None, db_path=db_path),
    )


def _format_value(value: Decimal) -> str:
    """Format large IDR values with T/B/M suffix."""
    abs_v = abs(value)
    sign = "+" if value >= 0 else "-"
    if abs_v >= 1_000_000_000_000:
        return f"{sign}{abs_v / 1_000_000_000_000:.1f}T"
    if abs_v >= 1_000_000_000:
        return f"{sign}{abs_v / 1_000_000_000:.1f}B"
    if abs_v >= 1_000_000:
        return f"{sign}{abs_v / 1_000_000:.0f}M"
    return f"{sign}{abs_v:.0f}"


def _notation_label(snapshot) -> str:
    if snapshot is None:
        return "-"
    parts = []
    if getattr(snapshot, "codes", None):
        parts.append(",".join(snapshot.codes))
    if getattr(snapshot, "tradeable", None) is False:
        parts.append("NO-TRADE")
    status = getattr(snapshot, "status", None)
    if status and status != "STATUS_ACTIVE":
        parts.append(status.replace("STATUS_", ""))
    if getattr(snapshot, "suspend_info", None):
        parts.append("SUSP")
    if getattr(snapshot, "has_uma", None):
        parts.append("UMA")
    return "+".join(parts) if parts else "-"


def _notation_detail(snapshot) -> str:
    if snapshot is None:
        return ""
    bits = []
    label = _notation_label(snapshot)
    if label != "-":
        bits.append(label)
    if snapshot.listing_board:
        bits.append(snapshot.listing_board)
    if snapshot.haircut_percentage:
        bits.append(f"haircut={snapshot.haircut_percentage}")
    return " | ".join(bits)


def _display_results(
    response: AccumulationScreenResponse,
    universe_label: str,
    top_n: int,
    granular: bool,
    vwap_only: bool,
    squeeze_only: bool,
    show_breakdown: bool,
    strategy_signals: dict[str, str] | None = None,
    strategy_name: str | None = None,
) -> None:
    from src.adapters.cli.screen_accum_display import display_results
    display_results(
        response=response,
        universe_label=universe_label,
        top_n=top_n,
        granular=granular,
        vwap_only=vwap_only,
        squeeze_only=squeeze_only,
        show_breakdown=show_breakdown,
        strategy_signals=strategy_signals,
        strategy_name=strategy_name,
    )


def _display_multi(
    results: dict[int, AccumulationScreenResponse],
    universe_label: str,
    top_n: int,
    sort_by: str,
    squeeze_only: bool,
    screened_at: "date",
    broker_quality: dict[str, ScreenBrokerQuality] | None = None,
) -> None:
    from src.adapters.cli.screen_accum_display import display_multi
    display_multi(
        results=results,
        universe_label=universe_label,
        top_n=top_n,
        sort_by=sort_by,
        squeeze_only=squeeze_only,
        screened_at=screened_at,
        broker_quality=broker_quality,
    )


def _print_column_guide() -> None:
    from src.adapters.cli.screen_accum_display import print_column_guide
    print_column_guide()


def _run_multi(
    use_case: AccumulationScreenUseCase,
    tickers: list[str],
    windows: list[int],
    base_request: AccumulationScreenRequest,
) -> dict[int, AccumulationScreenResponse]:
    """Run screener for each window. Always min_score=0 to get full picture."""
    return {
        w: use_case.execute(AccumulationScreenRequest(
            tickers=tickers,
            window_days=w,
            min_net_buy_days=base_request.min_net_buy_days,
            min_score=0.0,
            rsi_period=base_request.rsi_period,
            sma_period=base_request.sma_period,
            tier1_broker_codes=base_request.tier1_broker_codes,
            sector_breadth_enabled=base_request.sector_breadth_enabled,
            sector_breadth_threshold=base_request.sector_breadth_threshold,
            sector_breadth_bonus_pts=base_request.sector_breadth_bonus_pts,
            sector_breadth_min_tickers=base_request.sector_breadth_min_tickers,
        ))
        for w in windows
    }


def accumulation_run(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option(
            "--universe", "-u",
            help="Universe name or 'cached' — see `saham fetch universe list`",
        ),
    ] = None,
    window: Annotated[
        int,
        typer.Option(
            "--window", "-w",
            help="Analysis window in broker sessions (7, 30, or 90)",
            min=3,
        ),
    ] = 7,
    min_streak: Annotated[
        int,
        typer.Option("--min-streak", help="Minimum consecutive buy days required", min=0),
    ] = 0,
    min_score: Annotated[
        Optional[float],
        typer.Option("--min-score", help="Minimum composite score (0–120, default: 70)", min=0),
    ] = None,
    min_piotroski: Annotated[
        int,
        typer.Option("--min-piotroski", help="Minimum Piotroski F-Score 0–9 (0 = disabled)", min=0, max=9),
    ] = 0,
    vwap_only: Annotated[
        bool,
        typer.Option("--vwap-only", help="Only show stocks where foreigners are underwater"),
    ] = False,
    squeeze_only: Annotated[
        bool,
        typer.Option("--squeeze-only", help="Only show stocks in BB squeeze (BB width pctile ≤ 20%)"),
    ] = False,
    top: Annotated[
        int,
        typer.Option("--top", help="Show top N results", min=1),
    ] = 20,
    granular: Annotated[
        bool,
        typer.Option("--granular", help="Show per-broker detail (Stockbit data required)"),
    ] = False,
    show_breakdown: Annotated[
        bool,
        typer.Option("--breakdown", help="Show per-component score breakdown under each row"),
    ] = False,
    multi: Annotated[
        bool,
        typer.Option("--multi", help="Show scores across multiple windows side-by-side"),
    ] = False,
    windows: Annotated[
        Optional[str],
        typer.Option("--windows", help="Comma-separated broker-session windows for --multi (default: 7,30,90)"),
    ] = None,
    sort_by: Annotated[
        str,
        typer.Option(
            "--sort-by",
            help=(
                "In --multi mode, sort by: avg|max|7s|30s|90s "
                "(legacy 7d/30d/90d also accepted; default: avg)"
            ),
        ),
    ] = "avg",
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = APP_CFG.analysis.format,
    guide: Annotated[
        bool,
        typer.Option("--guide", help="Print column reference guide and exit (no screen needed)"),
    ] = False,
    explain: Annotated[
        bool,
        typer.Option("--explain", help="Print column guide appended after results"),
    ] = False,
    strategy: Annotated[
        Optional[str],
        typer.Option(
            "--strategy", "-S",
            help="Show strategy signal column alongside accum score (e.g. williams-r-bounce)",
        ),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
    save_name: Annotated[
        Optional[str],
        typer.Option("--save", help="Save results to watchlist under this name (e.g. morning-watch)"),
    ] = None,
) -> None:
    """
    Screen stocks for foreign accumulation patterns.

    Scores each ticker 0–120 based on: consistency of daily foreign buying,
    consecutive buy streak, whether foreigners are underwater (VWAP vs price),
    RSI headroom, foreign flow as % of total turnover, and BB Width squeeze.

    Run `saham fetch market --universe lq45` first to ensure fresh data.

    Examples:
        saham screen accum --universe lq45
        saham screen accum --universe lq45 --window 30
        saham screen accum --universe lq45 --multi
        saham screen accum --universe lq45 --multi --sort-by 30s
        saham screen accum --universe lq45 --min-score 50 --top 10
        saham screen accum BBCA BBRI BMRI --window 7
        saham screen accum --universe lq45 --vwap-only
        saham screen accum --universe lq45 --squeeze-only
        saham screen accum --universe lq45 --granular
        saham screen accum --universe lq45 --breakdown
        saham screen accum --universe lq45 --explain
        saham screen accum --guide
        saham screen accum --universe lq45 --format json
    """
    if guide:
        _print_column_guide()
        return

    resolved_db = db_path or DEFAULT_DB_PATH

    if min_score is None:
        min_score = float(get_swing_default("min_score", 70.0))

    try:
        ticker_list = resolve_tickers(
            universe=universe,
            explicit=list(tickers) if tickers else [],
            db_path=resolved_db,
        )
    except UniverseNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if not ticker_list:
        typer.echo(
            "No tickers to screen. Specify --universe or provide ticker arguments.",
            err=True,
        )
        raise typer.Exit(1)

    universe_label = universe or f"{len(ticker_list)} tickers"

    broker_repo = SQLiteBrokerRepository(resolved_db)
    market_repo = SQLiteMarketRepository(db_path=resolved_db)
    _sb = _make_stockbit_providers(resolved_db)
    _risk_uc = AssessRiskUseCase(
        repository=market_repo,
        structural_gates=[FundamentalGate(), LiquidityGate(), FreeFloatGate()],
        execution_gates=[BandarGate()],
    )
    use_case = AccumulationScreenUseCase(
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
        forward_estimates_provider=_sb.forward_estimates_prov,
        risk_use_case=_risk_uc,
    )

    base_request = AccumulationScreenRequest(
        tickers=ticker_list,
        window_days=window,
        min_net_buy_days=max(1, min_streak),
        min_score=min_score,
        min_piotroski=min_piotroski,
        tier1_broker_codes=_SC.tier1_broker_codes,
        bci_cluster_min_count=_SC.bci_cluster_min_count,
        bci_stable_min_count=_SC.bci_stable_min_count,
        min_market_cap_idr=_SC.min_market_cap_idr,
        sector_breadth_enabled=_SC.sector_breadth_enabled,
        sector_breadth_threshold=_SC.sector_breadth_threshold,
        sector_breadth_bonus_pts=_SC.sector_breadth_bonus_pts,
        sector_breadth_min_tickers=_SC.sector_breadth_min_tickers,
    )

    if multi:
        window_list = [int(w.strip()) for w in (windows or "7,30,90").split(",")]
        if output_format != "json":
            typer.echo(
                f"Screening {len(ticker_list)} tickers | windows: "
                f"{', '.join(str(w) + ' sessions' for w in window_list)}..."
            )
        multi_results = _run_multi(use_case, ticker_list, window_list, base_request)
        screened_at = next(iter(multi_results.values())).screened_at
        broker_quality = compute_broker_quality_batch(
            tickers=ticker_list,
            broker_repo=broker_repo,
            smart_money_brokers=_SC.smart_money_brokers,
            noise_brokers=_SC.noise_brokers,
            as_of_date=screened_at,
        )

        if output_format == "json":
            by_ticker: dict = {}
            for w, resp in multi_results.items():
                for c in resp.candidates:
                    by_ticker.setdefault(c.ticker, {})[f"{w}_sessions"] = c.to_dict()
            for ticker_key, quality in broker_quality.items():
                by_ticker.setdefault(ticker_key, {})["broker_quality"] = quality.to_dict()
            typer.echo(json.dumps({
                "mode": "multi",
                "windows": [f"{w}_sessions" for w in sorted(multi_results.keys())],
                "screened_at": str(screened_at),
                "tickers": by_ticker,
            }, indent=2, default=str))
            return

        _display_multi(
            results=multi_results,
            universe_label=universe_label,
            top_n=top,
            sort_by=sort_by,
            squeeze_only=squeeze_only,
            screened_at=screened_at,
            broker_quality=broker_quality,
        )
        if explain:
            _print_column_guide()
        return

    if output_format != "json":
        typer.echo(
            f"Screening {len(ticker_list)} tickers | {window} sessions..."
        )
    response = use_case.execute(base_request)

    if min_streak > 0:
        response.candidates = [
            c for c in response.candidates if c.consecutive_streak >= min_streak
        ]

    if output_format == "json":
        data = {
            "screened_at": str(response.screened_at),
            "window_days": response.window_days,
            "total_checked": response.total_tickers_checked,
            "skipped": response.tickers_skipped,
            "provider": response.provider,
            "candidates": [c.to_dict() for c in response.candidates[:top]],
        }
        typer.echo(json.dumps(data, indent=2, default=str))
        return

    strategy_signals: dict[str, str] = {}
    if strategy:
        registry = create_indicator_registry(
            broker_repository=broker_repo,
            market_repository=market_repo,
        )
        try:
            strat_loader = StrategyLoader(registry=registry)
            rules_path = strat_loader.resolve(strategy)
            risk_uc = AssessRiskUseCase(repository=market_repo, registry=registry)
            visible = response.candidates[:top]
            for c in visible:
                try:
                    req = AssessRiskRequest(ticker=c.ticker, rules_file=rules_path)
                    res = risk_uc.execute(req)
                    strategy_signals[c.ticker] = res.assessment.risk_level_name
                except Exception:
                    strategy_signals[c.ticker] = "?"
        except StrategyNotFoundError as e:
            typer.echo(f"⚠ Strategy not found: {e}", err=True)

    _display_results(
        response=response,
        universe_label=universe_label,
        top_n=top,
        granular=granular,
        vwap_only=vwap_only,
        squeeze_only=squeeze_only,
        show_breakdown=show_breakdown,
        strategy_signals=strategy_signals or None,
        strategy_name=strategy,
    )
    if explain:
        _print_column_guide()

    if save_name:
        _save_watchlist(
            name=save_name,
            candidates=response.candidates[:top],
            universe=str(universe or ""),
            window_days=window,
            db_path=resolved_db,
        )


def _save_watchlist(
    name: str,
    candidates: list,
    universe: str,
    window_days: int,
    db_path: "Path",
) -> None:
    from datetime import datetime

    from src.domain.value_objects.screen_snapshot import ScreenSnapshotEntry
    from src.infrastructure.persistence.sqlite_watchlist_repository import SQLiteWatchlistRepository

    now = datetime.now()
    entries = [
        ScreenSnapshotEntry(
            name=name,
            saved_at=now,
            universe=universe,
            window_days=window_days,
            ticker=c.ticker,
            rank=i + 1,
            flow_score=c.score,
            composite_score=c.signal_assessment.assessment.score if c.signal_assessment else None,
            consecutive_streak=c.consecutive_streak,
            net_buy_ratio=c.net_buy_ratio,
            bci_label=c.bci_label,
        )
        for i, c in enumerate(candidates)
    ]
    repo = SQLiteWatchlistRepository(db_path)
    repo.save_snapshot(entries)
    typer.echo(
        typer.style(f"\n  ✓ Saved {len(entries)} tickers to watchlist '{name}'", fg=typer.colors.GREEN)
    )


def _make_use_case_for_compare(
    universe: str,
    window: int,
    top: int,
    db_path: "Path",
) -> "list | None":
    """Run the accumulation screen silently and return the top candidates.

    Used by `saham screen compare`. Returns None on failure.
    """
    try:
        from src.application.services.universe_loader import resolve_tickers
        ticker_list = resolve_tickers(universe=universe, explicit=[], db_path=db_path)
        if not ticker_list:
            return None

        broker_repo = SQLiteBrokerRepository(db_path)
        market_repo = SQLiteMarketRepository(db_path=db_path)
        _sb = _make_stockbit_providers(db_path)

        use_case = AccumulationScreenUseCase(
            broker_repository=broker_repo,
            market_repository=market_repo,
            seasonality_provider=_sb.season_prov,
            analyst_consensus_provider=_sb.analyst_prov,
            bandar_detector_provider=_sb.bandar_prov,
            fundamentals_provider=_sb.fundamentals_prov,
            forward_estimates_provider=_sb.forward_estimates_prov,
        )
        response = use_case.execute(AccumulationScreenRequest(
            tickers=ticker_list,
            window_days=window,
            min_net_buy_days=1,
            min_score=0.0,
            tier1_broker_codes=_SC.tier1_broker_codes,
            bci_cluster_min_count=_SC.bci_cluster_min_count,
            bci_stable_min_count=_SC.bci_stable_min_count,
        ))
        return response.candidates[:top]
    except Exception:
        return None
