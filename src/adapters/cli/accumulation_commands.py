"""
CLI commands for foreign accumulation screening and universe management.

Commands:
  saham screen accum  — scan stocks for foreign accumulation patterns
  saham trade log swing     — log a candidate to the trade journal
  saham trade review swing  — review journal forward returns
  saham fetch universe list              — show configured ticker universes
  saham fetch universe update            — refresh universe lists from IDX (future)

Layer: Adapter
"""

import csv
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.services.bootstrap import create_indicator_registry
from src.application.services.strategy_loader import StrategyLoader, StrategyNotFoundError
from src.application.services.universe_loader import (
    UniverseNotFoundError,
    resolve_tickers,
)
from src.application.use_case.assess_risk import AssessRiskRequest, AssessRiskUseCase
from src.application.use_case.accumulation_audit import (
    AccumulationAuditRequest,
    AccumulationAuditResponse,
    AccumulationAuditUseCase,
)
from src.application.use_case.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenRequest,
    AccumulationScreenResponse,
    AccumulationScreenUseCase,
)
from src.application.use_case.market_regime import (
    MarketRegimeRequest,
    MarketRegimeUseCase,
)
from src.infrastructure.persistence.sqlite_broker_repository import (
    SQLiteBrokerRepository,
)
from src.infrastructure.config.user_config import get_swing_default
from src.infrastructure.browser.stockbit_analyst import StockbitAnalystConsensusProvider
from src.infrastructure.browser.stockbit_bandar import StockbitBandarDetectorProvider
from src.infrastructure.browser.stockbit_corp_action import StockbitCorporateActionRepository
from src.infrastructure.browser.stockbit_fundamentals import StockbitFundamentalsProvider
from src.infrastructure.browser.stockbit_insider import StockbitInsiderActivityProvider
from src.infrastructure.browser.stockbit_seasonality import StockbitSeasonalityProvider
from src.infrastructure.browser.stockbit_shareholding import StockbitShareholdingProvider
from src.infrastructure.browser.stockbit_ticker_notation import StockbitTickerNotationProvider
from src.infrastructure.config.swing_config import load_swing_config as _load_swing_screener_config_typed

_SC = _load_swing_screener_config_typed()
from src.infrastructure.persistence.sqlite_market_repository import (
    SQLiteMarketRepository,
)


class StockbitProviders:
    """Holds all optional Stockbit providers sharing one authenticated session."""
    __slots__ = ("corp_repo", "season_prov", "insider_prov", "analyst_prov", "shareholding_prov", "bandar_prov", "fundamentals_prov", "notation_prov")

    def __init__(
        self,
        corp_repo: "StockbitCorporateActionRepository | None",
        season_prov: "StockbitSeasonalityProvider | None",
        insider_prov: "StockbitInsiderActivityProvider | None",
        analyst_prov: "StockbitAnalystConsensusProvider | None" = None,
        shareholding_prov: "StockbitShareholdingProvider | None" = None,
        bandar_prov: "StockbitBandarDetectorProvider | None" = None,
        fundamentals_prov: "StockbitFundamentalsProvider | None" = None,
        notation_prov: "StockbitTickerNotationProvider | None" = None,
    ) -> None:
        self.corp_repo = corp_repo
        self.season_prov = season_prov
        self.insider_prov = insider_prov
        self.analyst_prov = analyst_prov
        self.shareholding_prov = shareholding_prov
        self.bandar_prov = bandar_prov
        self.fundamentals_prov = fundamentals_prov
        self.notation_prov = notation_prov

    @classmethod
    def unavailable(cls) -> "StockbitProviders":
        return cls(corp_repo=None, season_prov=None, insider_prov=None,
                   analyst_prov=None, shareholding_prov=None, bandar_prov=None,
                   fundamentals_prov=None, notation_prov=None)


def _make_stockbit_providers(db_path: Path) -> "StockbitProviders":
    """Return read-only Stockbit providers backed by SQLite cache.

    No API calls are made here. broker_provider=None means each provider
    reads from SQLite and returns None on a cache miss. The only command
    that fetches live data from Stockbit is `saham fetch market`.
    """
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


DEFAULT_DB_PATH = Path("data.db")
FOREIGN_BOUNCE_PRESET = "foreign-bounce"
FOREIGN_BOUNCE_TAKE_PROFIT = Decimal("5")
FOREIGN_BOUNCE_STOP_LOSS = Decimal("5")
FOREIGN_BOUNCE_MAX_HOLD_DAYS = 10
# Broker tier sets are loaded from config/swing_screener.yaml via _SC.
# (Previously hardcoded here with stale CS entry — now driven by config.)

# Table widths
_TABLE_WIDTH = 93
_SEP_WIDTH = 91


@dataclass(frozen=True)
class ScreenBrokerQuality:
    """Compact named-broker context for screener output."""

    label: str
    smart_flow: Decimal
    noise_flow: Decimal
    neutral_flow: Decimal
    sessions: int
    through_date: date
    source: str

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "smart_flow": str(self.smart_flow),
            "noise_flow": str(self.noise_flow),
            "neutral_flow": str(self.neutral_flow),
            "sessions": self.sessions,
            "through": self.through_date.isoformat(),
            "source": self.source,
        }


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


def _broker_tier(code: str) -> str:
    code_upper = code.upper()
    if code_upper in _SC.smart_money_brokers:
        return "smart"
    if code_upper in _SC.noise_brokers:
        return "noise"
    return "neutral"


def _screen_broker_quality_label(
    smart_flow: Decimal,
    noise_flow: Decimal,
    neutral_flow: Decimal,
) -> str:
    """Return a compact label for named-broker flow composition."""
    positive_total = sum(
        value
        for value in (smart_flow, noise_flow, neutral_flow)
        if value > Decimal("0")
    )
    negative_total = sum(
        abs(value)
        for value in (smart_flow, noise_flow, neutral_flow)
        if value < Decimal("0")
    )

    if negative_total > positive_total:
        if smart_flow < Decimal("0") and abs(smart_flow) >= abs(noise_flow):
            return "smart-"
        if noise_flow < Decimal("0"):
            return "noise-"
        return "dist"

    if smart_flow > Decimal("0") and smart_flow >= noise_flow and smart_flow >= neutral_flow:
        return "smart+"
    if noise_flow > Decimal("0") and noise_flow >= smart_flow and noise_flow >= neutral_flow:
        return "noise+"
    if neutral_flow != Decimal("0"):
        return "mixed"
    return "n/a"


def _build_screen_broker_quality(
    ticker: str,
    broker_repo: SQLiteBrokerRepository,
    as_of_date: date | None = None,
    window_sessions: int = 5,
) -> ScreenBrokerQuality | None:
    """
    Summarize named top-broker rows for screener context.

    This uses all named top buyers/sellers returned by Stockbit summaries.
    It is separate from aggregate foreign-flow scoring.
    """
    summaries = broker_repo.get_broker_summaries(ticker, end_date=as_of_date)
    detail_summaries = [
        summary for summary in summaries if summary.top_buyers or summary.top_sellers
    ][-window_sessions:]
    if not detail_summaries:
        return None

    smart_flow = Decimal("0")
    noise_flow = Decimal("0")
    neutral_flow = Decimal("0")

    def add_flow(code: str, signed_value: Decimal) -> None:
        nonlocal smart_flow, noise_flow, neutral_flow
        tier = _broker_tier(code)
        if tier == "smart":
            smart_flow += signed_value
        elif tier == "noise":
            noise_flow += signed_value
        else:
            neutral_flow += signed_value

    for summary in detail_summaries:
        for tx in summary.top_buyers:
            if tx.net_value > Decimal("0"):
                add_flow(tx.broker_code, tx.net_value)
        for tx in summary.top_sellers:
            if tx.net_value < Decimal("0"):
                add_flow(tx.broker_code, tx.net_value)

    latest = detail_summaries[-1]
    return ScreenBrokerQuality(
        label=_screen_broker_quality_label(smart_flow, noise_flow, neutral_flow),
        smart_flow=smart_flow,
        noise_flow=noise_flow,
        neutral_flow=neutral_flow,
        sessions=len(detail_summaries),
        through_date=latest.date,
        source=latest.source,
    )


def _broker_quality_by_ticker(
    tickers: list[str],
    broker_repo: SQLiteBrokerRepository,
    as_of_date: date | None,
) -> dict[str, ScreenBrokerQuality]:
    quality: dict[str, ScreenBrokerQuality] = {}
    for ticker in tickers:
        item = _build_screen_broker_quality(
            ticker=ticker,
            broker_repo=broker_repo,
            as_of_date=as_of_date,
        )
        if item:
            quality[ticker.upper()] = item
    return quality


def _fmt_score(s: float | None) -> str:
    """Format a score with color for table cells."""
    if s is None:
        return typer.style("   —  ", fg=typer.colors.BRIGHT_BLACK)
    if s >= _SC.enter_min_score:
        return typer.style(f"{s:>6.1f}", fg=typer.colors.GREEN)
    if s >= _SC.watch_min_score:
        return typer.style(f"{s:>6.1f}", fg=typer.colors.YELLOW)
    return typer.style(f"{s:>6.1f}", fg=typer.colors.WHITE)


def _classify_pattern(
    windows: list[int],
    candidates_by_window: dict[int, "AccumulationCandidate | None"],
) -> str:
    """Label the multi-window pattern for a ticker."""
    threshold = _SC.coiled_spring_min_score
    hot = [w for w in windows if candidates_by_window.get(w) and candidates_by_window[w].score >= threshold]

    # Coiled spring: any window with squeeze + strong score
    for w in windows:
        c = candidates_by_window.get(w)
        if c and c.score >= threshold and c.bb_width_pctile is not None and c.bb_width_pctile <= _SC.coiled_spring_bb_pctile:
            return "coiled spring"

    if not hot:
        return "weak"
    if set(hot) == set(windows):
        return "sustained"
    if min(windows) in hot and max(windows) not in hot:
        return "fresh rotation"
    if max(windows) in hot and min(windows) not in hot:
        return "long-term only"
    if min(windows) in hot and len(hot) >= 2:
        return "building"
    return "mixed"



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

def _fmt_optional_float(value: float | None, suffix: str = "") -> str:
    return "missing" if value is None else f"{value:.1f}{suffix}"


def _foreign_bounce_decision(
    candidate: AccumulationCandidate | None,
) -> tuple[str, tuple[str, ...]]:
    if candidate is None:
        return "AVOID", ("No accumulation/broker-flow candidate available",)

    gates = (
        (
            "score",
            candidate.score >= _SC.gate_min_score,
            f"{candidate.score:.1f}",
            f">= {_SC.gate_min_score:.0f}",
        ),
        (
            "vwap_disc_pct",
            candidate.vwap_discount_pct is not None
            and candidate.vwap_discount_pct >= _SC.gate_min_vwap_discount_pct,
            _fmt_optional_float(candidate.vwap_discount_pct, "%"),
            f">= +{_SC.gate_min_vwap_discount_pct:.0f}%",
        ),
        (
            "trend",
            candidate.trend == _SC.gate_required_trend,
            candidate.trend,
            _SC.gate_required_trend,
        ),
        (
            "flow_pct",
            candidate.avg_flow_ratio is not None and candidate.avg_flow_ratio >= _SC.gate_min_flow_ratio_pct,
            _fmt_optional_float(candidate.avg_flow_ratio, "%"),
            f">= +{_SC.gate_min_flow_ratio_pct:.0f}%",
        ),
        (
            "RSI present",
            candidate.rsi is not None,
            _fmt_optional_float(candidate.rsi),
            "present",
        ),
        (
            "RSI",
            candidate.rsi is not None and candidate.rsi <= _SC.gate_max_rsi,
            _fmt_optional_float(candidate.rsi),
            f"<= {_SC.gate_max_rsi:.0f}",
        ),
    )
    failed = tuple(
        f"{label}: {actual} (required {required})"
        for label, passed, actual, required in gates
        if not passed
    )
    if not failed:
        return "ENTER", failed
    if candidate.score >= _SC.gate_min_score or len(failed) <= _SC.watch_max_failed_gates:
        return "WATCH", failed
    return "AVOID", failed


def _percent_plan(entry: Decimal) -> tuple[Decimal, Decimal]:
    stop = entry * (Decimal("1") - FOREIGN_BOUNCE_STOP_LOSS / Decimal("100"))
    target = entry * (Decimal("1") + FOREIGN_BOUNCE_TAKE_PROFIT / Decimal("100"))
    return stop, target

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
    from src.adapters.cli.accumulation_display import display_results
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
    from src.adapters.cli.accumulation_display import display_multi
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
    from src.adapters.cli.accumulation_display import print_column_guide
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
    ] = "table",
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

    # Resolve tickers
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
    )

    base_request = AccumulationScreenRequest(
        tickers=ticker_list,
        window_days=window,
        min_net_buy_days=max(1, min_streak),
        min_score=min_score,
        tier1_broker_codes=_SC.tier1_broker_codes,
    )

    # --- Multi-window mode ---
    if multi:
        window_list = [int(w.strip()) for w in (windows or "7,30,90").split(",")]
        if output_format != "json":
            typer.echo(
                f"Screening {len(ticker_list)} tickers | windows: "
                f"{', '.join(str(w) + ' sessions' for w in window_list)}..."
            )
        multi_results = _run_multi(use_case, ticker_list, window_list, base_request)
        screened_at = next(iter(multi_results.values())).screened_at
        broker_quality = _broker_quality_by_ticker(
            tickers=ticker_list,
            broker_repo=broker_repo,
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

    # --- Single-window mode ---
    if output_format != "json":
        typer.echo(
            f"Screening {len(ticker_list)} tickers | {window} sessions..."
        )
    response = use_case.execute(base_request)

    # Apply streak filter post-scoring
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

    # Optional strategy signal column
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


def _display_audit_summary(response: AccumulationAuditResponse, top_groups: int) -> None:
    from src.adapters.cli.accumulation_audit_display import display_audit_summary
    display_audit_summary(response=response, top_groups=top_groups)


def _write_audit_csv(response: AccumulationAuditResponse, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [r.to_dict() for r in response.records]
    fieldnames = list(rows[0].keys()) if rows else [
        "signal_date", "ticker", "score", "streak", "net_buy_ratio",
        "total_net_value", "flow_pct", "vwap_disc_pct", "rsi", "bb_pctile",
        "trend", "broker_quality", "current_price", "return_5d_pct", "return_10d_pct",
        "return_20d_pct", "max_upside_pct", "max_drawdown_pct",
    ]
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _parse_float_grid(value: str, option_name: str) -> tuple[float, ...]:
    try:
        parsed = tuple(float(part.strip()) for part in value.split(",") if part.strip())
    except ValueError as e:
        raise typer.BadParameter(f"{option_name} must be comma-separated numbers") from e
    if not parsed or any(item <= 0 for item in parsed):
        raise typer.BadParameter(f"{option_name} must contain positive numbers")
    return parsed


def _parse_int_grid(value: str, option_name: str) -> tuple[int, ...]:
    try:
        parsed = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    except ValueError as e:
        raise typer.BadParameter(f"{option_name} must be comma-separated integers") from e
    if not parsed or any(item <= 0 for item in parsed):
        raise typer.BadParameter(f"{option_name} must contain positive integers")
    return parsed


AUDIT_PRESETS = {
    "foreign-bounce": {
        "universe": "idx80",
        "window": 7,
        "min_score": 70.0,
        "min_net_buy_days": 2,
        "min_vwap_disc": 3.0,
        "trend": "SIDE",
        "min_flow_pct": 5.0,
        "require_rsi": True,
        "max_rsi": 60.0,
        "simulate_exits": True,
        "take_profits": "4,5,6",
        "stop_losses": "3,5,7",
        "max_holds": "3,5,7,10",
    },
}


def accumulation_audit(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option("--universe", "-u", help="Universe name or 'cached' — see `saham fetch universe list`"),
    ] = None,
    preset: Annotated[
        Optional[str],
        typer.Option("--preset", help="Audit preset: foreign-bounce"),
    ] = None,
    start: Annotated[
        str,
        typer.Option("--start", help="Audit start date, YYYY-MM-DD"),
    ] = "2026-01-01",
    end: Annotated[
        Optional[str],
        typer.Option("--end", help="Audit end date, YYYY-MM-DD (default: today)"),
    ] = None,
    window: Annotated[
        Optional[int],
        typer.Option("--window", "-w", help="Accumulation window in broker sessions", min=3),
    ] = None,
    min_score: Annotated[
        Optional[float],
        typer.Option("--min-score", help="Minimum composite score to audit", min=0),
    ] = None,
    min_net_buy_days: Annotated[
        Optional[int],
        typer.Option("--min-net-buy-days", help="Minimum foreign net-buy days", min=1),
    ] = None,
    min_vwap_disc: Annotated[
        Optional[float],
        typer.Option(
            "--min-vwap-disc",
            help="Require VWAP discount at least this percent",
        ),
    ] = None,
    trend: Annotated[
        Optional[str],
        typer.Option("--trend", help="Require trend bucket: UP, SIDE, or DOWN"),
    ] = None,
    min_flow_pct: Annotated[
        Optional[float],
        typer.Option("--min-flow-pct", help="Require average foreign flow percent"),
    ] = None,
    require_rsi: Annotated[
        bool,
        typer.Option("--require-rsi", help="Exclude signals with missing RSI"),
    ] = False,
    max_rsi: Annotated[
        Optional[float],
        typer.Option("--max-rsi", help="Require RSI at or below this value"),
    ] = None,
    simulate_exits: Annotated[
        Optional[bool],
        typer.Option("--simulate-exits", help="Run TP/SL/max-hold exit grid"),
    ] = None,
    take_profits: Annotated[
        Optional[str],
        typer.Option("--take-profits", help="Comma-separated take-profit percentages"),
    ] = None,
    stop_losses: Annotated[
        Optional[str],
        typer.Option("--stop-losses", help="Comma-separated stop-loss percentages"),
    ] = None,
    max_holds: Annotated[
        Optional[str],
        typer.Option("--max-holds", help="Comma-separated max holding days"),
    ] = None,
    horizon: Annotated[
        int,
        typer.Option("--horizon", help="Forward horizon for max up/down metrics", min=5),
    ] = 20,
    output_path: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="Write raw audit records to CSV"),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
    top_groups: Annotated[
        int,
        typer.Option("--top-groups", help="Number of grouped summary rows to print", min=1),
    ] = 80,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Replay accumulation signals historically and measure forward returns.

    This command is deterministic and offline. It uses cached local candles and
    broker summaries only; run `saham fetch market --universe <name>` first.
    """
    resolved_db = db_path or DEFAULT_DB_PATH

    preset_name = preset.lower() if preset else None
    preset_values = {}
    if preset_name is not None:
        if preset_name not in AUDIT_PRESETS:
            typer.echo(
                f"Error: unknown preset '{preset}'. "
                f"Available presets: {', '.join(AUDIT_PRESETS)}",
                err=True,
            )
            raise typer.Exit(1)
        preset_values = AUDIT_PRESETS[preset_name]

    universe = universe or preset_values.get("universe")
    window = window if window is not None else int(preset_values.get("window", 7))
    min_score = (
        min_score if min_score is not None
        else float(preset_values.get("min_score", 40.0))
    )
    min_net_buy_days = (
        min_net_buy_days if min_net_buy_days is not None
        else int(preset_values.get("min_net_buy_days", 2))
    )
    min_vwap_disc = (
        min_vwap_disc if min_vwap_disc is not None
        else preset_values.get("min_vwap_disc")
    )
    trend = trend or preset_values.get("trend")
    min_flow_pct = (
        min_flow_pct if min_flow_pct is not None
        else preset_values.get("min_flow_pct")
    )
    require_rsi = require_rsi or bool(preset_values.get("require_rsi", False))
    max_rsi = max_rsi if max_rsi is not None else preset_values.get("max_rsi")
    simulate_exits = (
        simulate_exits if simulate_exits is not None
        else bool(preset_values.get("simulate_exits", False))
    )
    take_profits = take_profits or str(preset_values.get("take_profits", "4,5,6"))
    stop_losses = stop_losses or str(preset_values.get("stop_losses", "3,5,7"))
    max_holds = max_holds or str(preset_values.get("max_holds", "3,5,7,10"))

    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end) if end else date.today()
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
            "No tickers to audit. Specify --universe or provide ticker arguments.",
            err=True,
        )
        raise typer.Exit(1)

    trend_filter = trend.upper() if trend else None
    if trend_filter is not None and trend_filter not in {"UP", "SIDE", "DOWN"}:
        typer.echo("Error: --trend must be one of: UP, SIDE, DOWN", err=True)
        raise typer.Exit(1)

    filter_parts = []
    if min_vwap_disc is not None:
        filter_parts.append(f"VWAP>={min_vwap_disc:g}%")
    if trend_filter is not None:
        filter_parts.append(f"trend={trend_filter}")
    if min_flow_pct is not None:
        filter_parts.append(f"flow>={min_flow_pct:g}%")
    if require_rsi:
        filter_parts.append("RSI present")
    if max_rsi is not None:
        filter_parts.append(f"RSI<={max_rsi:g}")
    if simulate_exits:
        filter_parts.append("exit simulation")
    filter_label = f" | filters: {', '.join(filter_parts)}" if filter_parts else ""

    try:
        take_profit_grid = _parse_float_grid(take_profits, "--take-profits")
        stop_loss_grid = _parse_float_grid(stop_losses, "--stop-losses")
        max_hold_grid = _parse_int_grid(max_holds, "--max-holds")
    except typer.BadParameter as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if output_format != "json":
        typer.echo(
            f"Auditing {len(ticker_list)} tickers | {start_date} to {end_date} | "
            f"{window} sessions | min score {min_score:g}{filter_label}..."
        )

    use_case = AccumulationAuditUseCase(
        broker_repository=SQLiteBrokerRepository(resolved_db),
        market_repository=SQLiteMarketRepository(db_path=resolved_db),
    )
    response = use_case.execute(
        AccumulationAuditRequest(
            tickers=ticker_list,
            start_date=start_date,
            end_date=end_date,
            window_days=window,
            min_net_buy_days=min_net_buy_days,
            min_score=min_score,
            horizon_days=horizon,
            min_vwap_disc_pct=min_vwap_disc,
            trend=trend_filter,
            min_flow_pct=min_flow_pct,
            require_rsi=require_rsi,
            max_rsi=max_rsi,
            simulate_exits=simulate_exits,
            take_profit_pcts=take_profit_grid,
            stop_loss_pcts=stop_loss_grid,
            max_hold_days=max_hold_grid,
        )
    )

    if output_path is not None:
        _write_audit_csv(response, output_path)
        typer.echo(f"Wrote {response.total_records} audit records to {output_path}")

    if output_format == "json":
        typer.echo(json.dumps({
            "start_date": response.start_date.isoformat(),
            "end_date": response.end_date.isoformat(),
            "window_days": response.window_days,
            "total_replay_dates": response.total_replay_dates,
            "total_tickers": response.total_tickers,
            "total_records": response.total_records,
            "skipped_no_forward_data": response.skipped_no_forward_data,
            "warnings": response.warnings,
            "group_stats": [s.to_dict() for s in response.group_stats],
            "exit_simulations": [s.to_dict() for s in response.exit_simulations],
        }, indent=2, default=str))
        return

    _display_audit_summary(response, top_groups=top_groups)


# ---------------------------------------------------------------------------
# Accumulation trade journal commands
# ---------------------------------------------------------------------------

DEFAULT_ACCUM_JOURNAL_PATH = Path("journals/accumulation.csv")
DEFAULT_TRADE_JOURNAL_PATH = Path("journals/trades.jsonl")


def _accumulation_log_impl(
    ticker: str,
    window: int,
    entry_price: Optional[float],
    from_analysis: bool,
    preset: str,
    with_regime: bool,
    regime_universe: Optional[str],
    benchmark: str,
    journal_path: Path,
    db_path: Path,
) -> None:
    """Core swing log logic — called by both the legacy subcommand and the unified trade log."""
    from src.application.services.accumulation_journal import AccumulationJournalService
    from src.infrastructure.persistence.accumulation_journal_csv_writer import (
        AccumulationJournalCsvWriter,
    )
    from src.infrastructure.persistence.trade_journal_jsonl_writer import (
        TradeJournalJsonlWriter,
        swing_candidate_to_record,
    )

    ticker_upper = ticker.upper()
    logged_at = date.today()
    preset_name = preset.lower()
    if from_analysis and preset_name != FOREIGN_BOUNCE_PRESET:
        typer.echo(
            f"Unknown swing preset '{preset}'. Available presets: {FOREIGN_BOUNCE_PRESET}",
            err=True,
        )
        raise typer.Exit(1)

    broker_repo = SQLiteBrokerRepository(db_path)
    market_repo = SQLiteMarketRepository(db_path=db_path)
    _sb = _make_stockbit_providers(db_path)

    # Run single-ticker screen to get candidate
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
    )
    response = use_case.execute(AccumulationScreenRequest(
        tickers=[ticker_upper],
        window_days=window,
        min_score=0.0,
        min_net_buy_days=0,
        tier1_broker_codes=_SC.tier1_broker_codes,
    ))
    candidate = next((c for c in response.candidates if c.ticker == ticker_upper), None)

    # Compute multi-window pattern (7, 30, 90)
    pattern: str | None = None
    try:
        windows = [7, 30, 90]
        multi = {
            w: use_case.execute(AccumulationScreenRequest(
                tickers=[ticker_upper],
                window_days=w,
                min_score=0.0,
                min_net_buy_days=0,
                tier1_broker_codes=_SC.tier1_broker_codes,
            ))
            for w in windows
        }
        candidates_by_window = {
            w: next((c for c in resp.candidates if c.ticker == ticker_upper), None)
            for w, resp in multi.items()
        }
        pattern = _classify_pattern(windows, candidates_by_window)
    except Exception:
        pass  # pattern stays None if multi-window fails

    # Resolve entry price
    resolved_entry: Decimal
    if entry_price is not None:
        resolved_entry = Decimal(str(entry_price))
    elif candidate is not None:
        try:
            today = date.today()
            candles = market_repo.get_candles(
                ticker_upper,
                start_date=today.replace(month=1, day=1),
                end_date=today,
            )
            resolved_entry = candles[-1].close if candles else Decimal("0")
        except Exception:
            resolved_entry = Decimal("0")
    else:
        typer.echo(
            f"Warning: no accumulation data for {ticker_upper} in the last {window} broker sessions. "
            "Logging with score=0.",
            err=True,
        )
        resolved_entry = Decimal("0")

    classification: str | None = None
    failed_gates: tuple[str, ...] = ()
    planned_entry: Decimal | None = None
    planned_stop: Decimal | None = None
    planned_target: Decimal | None = None
    max_hold_days: int | None = None
    regime: str | None = None
    journal_preset: str | None = None

    if from_analysis:
        journal_preset = preset_name
        classification, failed_gates = _foreign_bounce_decision(candidate)
        planned_entry = resolved_entry
        planned_stop, planned_target = _percent_plan(resolved_entry)
        max_hold_days = FOREIGN_BOUNCE_MAX_HOLD_DAYS

        if with_regime:
            try:
                regime_tickers = resolve_tickers(
                    universe=regime_universe,
                    explicit=[],
                    db_path=db_path,
                )
                regime_uc = MarketRegimeUseCase(
                    market_repository=market_repo,
                    broker_repository=broker_repo,
                )
                regime_response = regime_uc.execute(MarketRegimeRequest(
                    universe=regime_tickers,
                    benchmark_ticker=benchmark,
                    as_of_date=logged_at,
                ))
                regime = regime_response.label
            except Exception as exc:
                typer.echo(
                    f"Warning: could not compute market regime for journal row: {exc}",
                    err=True,
                )

    store = AccumulationJournalCsvWriter(journal_path)
    service = AccumulationJournalService(store=store, repository=market_repo)

    count = service.log_candidate(
        ticker=ticker_upper,
        entry_price=resolved_entry,
        window_days=window,
        candidate=candidate,
        logged_at=logged_at,
        pattern=pattern,
        preset=journal_preset,
        classification=classification,
        failed_gates=failed_gates,
        regime=regime,
        planned_entry=planned_entry,
        planned_stop=planned_stop,
        planned_target=planned_target,
        max_hold_days=max_hold_days,
    )

    if count == 0:
        typer.echo(
            f"Already logged {ticker_upper} for {logged_at} (window={window} sessions) — "
            f"no new row added ({journal_path})"
        )
    else:
        # Dual-write to unified trades.jsonl
        jsonl_store = TradeJournalJsonlWriter(journal_path.parent / "trades.jsonl")
        jsonl_store.append(swing_candidate_to_record(
            ticker=ticker_upper,
            logged_at=logged_at,
            window_days=window,
            entry_price=resolved_entry,
            candidate=candidate,
            pattern=pattern,
            preset=journal_preset,
            decision=classification,
            failed_gates=failed_gates,
            regime=regime,
            planned_entry=planned_entry,
            planned_stop=planned_stop,
            planned_target=planned_target,
            max_hold_days=max_hold_days,
        ))

        score_str = f"{candidate.score:.1f}" if candidate else "0.0"
        pattern_str = f" | pattern: {pattern}" if pattern else ""
        decision_str = (
            f" | preset={journal_preset} | decision={classification}"
            if from_analysis
            else ""
        )
        plan_str = (
            f" | plan entry={planned_entry:,.0f} stop={planned_stop:,.0f} "
            f"target={planned_target:,.0f} hold={max_hold_days}d"
            if from_analysis
            and planned_entry is not None
            and planned_stop is not None
            and planned_target is not None
            and max_hold_days is not None
            else ""
        )
        regime_str = f" | regime={regime}" if regime else ""
        typer.echo(
            f"Logged {ticker_upper} | {logged_at} | window={window} sessions | "
            f"score={score_str}{pattern_str}{decision_str}{regime_str}{plan_str} → {journal_path}"
        )
        if from_analysis and failed_gates:
            typer.echo("Failed gates:")
            for gate in failed_gates:
                typer.echo(f"  - {gate}")


def accumulation_log(
    ticker: Annotated[
        str,
        typer.Option("--ticker", "-t", help="Ticker symbol to log (e.g. BBRI)"),
    ],
    window: Annotated[
        int,
        typer.Option("--window", "-w", help="Accumulation window in broker sessions", min=3),
    ] = 7,
    entry_price: Annotated[
        Optional[float],
        typer.Option("--entry-price", help="Entry price override (default = latest close)"),
    ] = None,
    from_analysis: Annotated[
        bool,
        typer.Option(
            "--from-analysis",
            help="Record preset decision, failed gates, and trade plan fields",
        ),
    ] = False,
    preset: Annotated[
        str,
        typer.Option("--preset", help="Swing preset to journal with --from-analysis"),
    ] = FOREIGN_BOUNCE_PRESET,
    with_regime: Annotated[
        bool,
        typer.Option("--with-regime", help="Include market regime label in journal row"),
    ] = False,
    regime_universe: Annotated[
        Optional[str],
        typer.Option("--regime-universe", help="Universe for regime breadth"),
    ] = "lq45",
    benchmark: Annotated[
        str,
        typer.Option("--benchmark", help="Benchmark ticker for regime context"),
    ] = "^JKSE",
    journal: Annotated[
        Optional[Path],
        typer.Option("--journal", help="Journal CSV path"),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Log an accumulation candidate to the trade journal.

    Runs the accumulation screen for TICKER and appends one row to the
    journal CSV. Idempotent: re-running for the same (date, ticker, window)
    never duplicates rows.

    Example:
        saham trade log swing --ticker BBRI --window 7
        saham trade log swing --ticker BBCA --entry-price 9450
        saham trade log swing --ticker BBRI --from-analysis --with-regime
    """
    _accumulation_log_impl(
        ticker=ticker,
        window=window,
        entry_price=entry_price,
        from_analysis=from_analysis,
        preset=preset,
        with_regime=with_regime,
        regime_universe=regime_universe,
        benchmark=benchmark,
        journal_path=journal or DEFAULT_ACCUM_JOURNAL_PATH,
        db_path=db_path or DEFAULT_DB_PATH,
    )


def accumulation_review(
    horizon: Annotated[
        int,
        typer.Option("--horizon", help="Trading days forward for max/min window", min=1),
    ] = 10,
    min_score: Annotated[
        float,
        typer.Option("--min-score", help="Only include entries with score ≥ this"),
    ] = 0.0,
    journal: Annotated[
        Optional[Path],
        typer.Option("--journal", help="Journal CSV path"),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Review accumulation trade journal: forward returns by score and pattern.

    Fetches actual forward closes from the local database and computes
    what the accumulation score thresholds actually delivered.

    Example:
        saham trade review swing
        saham trade review swing --horizon 10 --min-score 70
    """
    from src.application.services.accumulation_journal import AccumulationJournalService
    from src.infrastructure.persistence.accumulation_journal_csv_writer import (
        AccumulationJournalCsvWriter,
    )

    journal_path = journal or DEFAULT_ACCUM_JOURNAL_PATH
    resolved_db = db_path or DEFAULT_DB_PATH

    if not journal_path.exists():
        typer.echo(
            f"No journal found at '{journal_path}'.\n"
            "Run `saham trade log swing --ticker BBRI` first.",
            err=True,
        )
        raise typer.Exit(1)

    market_repo = SQLiteMarketRepository(db_path=resolved_db)
    store = AccumulationJournalCsvWriter(journal_path)
    service = AccumulationJournalService(store=store, repository=market_repo)

    typer.echo(f"Reviewing journal ({journal_path}) | horizon={horizon}d ...")
    report = service.review(horizon_days=horizon)

    from src.adapters.cli.accumulation_journal_display import display_journal_review

    display_journal_review(
        report=report,
        journal_path=journal_path,
        horizon=horizon,
        min_score=min_score,
    )
