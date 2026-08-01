"""Composition root for the optional daily cockpit TUI.

Infrastructure imports stay confined here. Screens receive injected callables
and controllers only.

Layer: Adapter composition root
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import replace as dc_replace
from datetime import date
from pathlib import Path
from threading import Lock
from typing import Any

from src.adapters.composition.screen_accum_request import (
    DEFAULT_WINDOW,
    build_default_screen_accum_request,
)
from src.adapters.composition.screen_deps import ScreenDeps, build_screen_deps
from src.adapters.tui.board_snapshot import default_accum_snapshot_path
from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.local_cache_health import load_local_cache_health
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.plan_structure_result import PlanStructureResult
from src.adapters.tui.presenters.accum_presenter import AccumPresenter
from src.adapters.tui.presenters.preopen_presenter import PreOpenPresenter
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.universe_config_loader import YamlUniverseConfigLoader


def create_tui_app(
    *,
    accum_loader: Callable[[], Any] | None = None,
    preopen_loader: Callable[[], Any] | None = None,
    plan_runner: Callable[[str], Any] | None = None,
    fetch_previewer: Callable[[], Any] | None = None,
    fetch_runner: Callable[[], Any] | None = None,
    ticker_detail_loader: Callable[[str], Any] | None = None,
    board_snapshot_path: Path | None = None,
    ticker_judge_loader: Callable[[str], Any] | None = None,
    cache_health_loader: Callable[[], Any] | None = None,
    paper_log_runner: Callable[[str], Any] | None = None,
    phase_history_loader: Callable[[str, date], Any] | None = None,
) -> CockpitApp:
    """Build cockpit with real local loaders unless tests inject fakes."""
    config = load_app_config()
    db_path = Path(config.storage.db_path)
    screen_deps = build_screen_deps(db_path)
    universe = (config.analysis.universe or "lq45").lower()

    if accum_loader is None:
        accum_loader = _ScreenAccumLoader(screen_deps, config)
    if preopen_loader is None:
        preopen_loader = _PreOpenSnapshotLoader(db_path)
    if plan_runner is None:
        plan_runner = _LocalPlanStructureRunner(db_path, config)
    if fetch_previewer is None:
        fetch_previewer = _build_fetch_previewer(db_path)
    if fetch_runner is None:
        fetch_runner = _build_fetch_runner(db_path)
    if ticker_detail_loader is None:
        ticker_detail_loader = _ViewTickerDashboardLoader(db_path)
    if board_snapshot_path is None:
        board_snapshot_path = default_accum_snapshot_path(db_path)
    if ticker_judge_loader is None:
        ticker_judge_loader = _TickerJudgeLoader(screen_deps, config)
    if cache_health_loader is None:
        cache_health_loader = _LocalCacheHealthLoader(db_path, universe)
    if paper_log_runner is None:
        paper_log_runner = _LocalPaperLogFromPlanRunner(db_path, config)
    if phase_history_loader is None:
        phase_history_loader = _LocalPhaseHistoryLoader(db_path)

    return CockpitApp(
        accum_loader=accum_loader,
        preopen_loader=preopen_loader,
        plan_runner=plan_runner,
        fetch_previewer=fetch_previewer,
        fetch_runner=fetch_runner,
        ticker_detail_loader=ticker_detail_loader,
        broker_list_loader=_BrokerListLoader(db_path),
        broker_show_loader=_BrokerShowLoader(db_path),
        broker_top_loader=_BrokerDeepLoader(db_path, "top"),
        broker_flow_loader=_BrokerDeepLoader(db_path, "flow"),
        broker_history_loader=_BrokerDeepLoader(db_path, "history"),
        broker_matrix_loader=_BrokerDeepLoader(db_path, "matrix"),
        broker_calendar_loader=_BrokerDeepLoader(db_path, "cal"),
        ticker_desks_loader=_TickerTopBrokersLoader(db_path),
        ticker_job_loader=_TickerJobLoader(db_path),
        ticker_judge_loader=ticker_judge_loader,
        cache_health_loader=cache_health_loader,
        paper_log_runner=paper_log_runner,
        phase_history_loader=phase_history_loader,
        accum_controller=BoardController(accum_loader),
        preopen_controller=BoardController(
            preopen_loader,
            empty_when=_preopen_empty,
        ),
        accum_presenter=AccumPresenter(),
        preopen_presenter=PreOpenPresenter(),
        board_snapshot_path=board_snapshot_path,
        snapshot_universe=universe,
    )


create_cockpit_app = create_tui_app


# ── Accumulation ───────────────────────────────────────────


class _ScreenAccumLoader:
    def __init__(self, deps: ScreenDeps, config: Any) -> None:
        self._deps = deps
        self._config = config
        self._use_case = None
        self._lock = Lock()

    def __call__(self) -> Any:
        with self._lock:
            if self._use_case is None:
                self._use_case = self._deps.build_accum_workflow_use_case()
            use_case = self._use_case

        universe = (self._config.analysis.universe or "lq45").lower()
        tickers = _resolve_tickers(self._deps, universe)
        if not tickers:
            return _EmptyAccumResult()

        request = build_default_screen_accum_request(
            tickers=tickers,
            universe=universe,
        )
        return use_case.execute(request)


class _EmptyAccumResult:
    single_projection = type(
        "P", (), {"candidates": (), "window_days": DEFAULT_WINDOW, "data_as_of": {}}
    )()
    multi_projection = None
    warnings: tuple[str, ...] = ("No tickers in local universe/cache",)


class _TickerJudgeLoader:
    """Single-ticker local screen for TUI Judge re-judge (``j``).

    Uses the same request builder + workflow as board load — no TUI-only defaults.
    """

    def __init__(self, deps: ScreenDeps, config: Any) -> None:
        self._deps = deps
        self._config = config
        self._use_case = None
        self._lock = Lock()

    def __call__(self, ticker: str) -> Any:
        with self._lock:
            if self._use_case is None:
                self._use_case = self._deps.build_accum_workflow_use_case()
            use_case = self._use_case

        symbol = str(ticker or "").strip().upper()
        if not symbol:
            raise ValueError("ticker required for re-judge")
        universe = (self._config.analysis.universe or "lq45").lower()
        request = build_default_screen_accum_request(
            tickers=[symbol],
            universe=universe,
        )
        return use_case.execute(request)


# ── Pre-open (IEV snapshot only — local-first) ─────────────


@dataclass(frozen=True)
class _PreOpenSnapshotPayload:
    response: Any
    snapshot_date: date | None
    warnings: tuple[str, ...] = ()


class _PreOpenSnapshotLoader:
    """Run pre-open screen from cached IEV NCP snapshot (fetch iev), never live browser."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = Lock()

    def __call__(self) -> _PreOpenSnapshotPayload:
        with self._lock:
            return self._run()

    def _run(self) -> _PreOpenSnapshotPayload:
        from src.application.use_case.pre_open_screen_use_case import (
            PreOpenScreenRequest,
            PreOpenScreenUseCase,
        )
        from src.domain.value_objects.screener_result import MoverData
        from src.infrastructure.browser.stockbit_browser_provider import (
            ManualBrowserDataProvider,
        )
        from src.infrastructure.browser.stockbit_config_bundle import (
            load_stockbit_provider_config,
        )
        from src.infrastructure.browser.stockbit_ticker_notation import (
            StockbitTickerNotationProvider,
        )
        from src.infrastructure.composition.indicator_registry_factory import (
            create_indicator_registry,
        )
        from src.infrastructure.config.pre_open_config import load_pre_open_screen_config
        from src.infrastructure.persistence.sqlite_broker_repository import (
            SQLiteBrokerRepository,
        )
        from src.infrastructure.persistence.sqlite_iev_repository import SQLiteIEVRepository
        from src.infrastructure.persistence.sqlite_market_repository import (
            SQLiteMarketRepository,
        )

        market_repository = SQLiteMarketRepository(db_path=self._db_path)
        broker_repository = SQLiteBrokerRepository(self._db_path)
        iev_repository = SQLiteIEVRepository(self._db_path)
        snapshot_dates = iev_repository.get_snapshot_dates()
        if not snapshot_dates:
            return _PreOpenSnapshotPayload(
                response=None,
                snapshot_date=None,
                warnings=("No IEV snapshots in local cache — run: saham fetch iev",),
            )

        snapshot_date = max(snapshot_dates)
        snapshots = iev_repository.get_ncp_snapshot(snapshot_date)
        if not snapshots:
            return _PreOpenSnapshotPayload(
                response=None,
                snapshot_date=snapshot_date,
                warnings=(f"Empty NCP snapshot for {snapshot_date.isoformat()}",),
            )

        movers = [MoverData(ticker=s.ticker, iev=s.iev, iep=s.iep) for s in snapshots]
        provider = ManualBrowserDataProvider(movers=movers)
        registry = create_indicator_registry(
            broker_repository=broker_repository,
            market_repository=market_repository,
        )
        notation = StockbitTickerNotationProvider(
            api_client=None,
            db_path=self._db_path,
            stockbit_config=load_stockbit_provider_config(),
        )
        config = dc_replace(load_pre_open_screen_config(), fast_mode=True)
        response = PreOpenScreenUseCase(
            browser=provider,
            repository=market_repository,
            registry=registry,
            broker_repository=broker_repository,
            ai_explainer=None,
            ticker_notation_provider=notation,
        ).execute(PreOpenScreenRequest(config=config, run_date=snapshot_date))
        return _PreOpenSnapshotPayload(
            response=response,
            snapshot_date=snapshot_date,
            warnings=tuple(response.warnings or ()),
        )


# ── View ticker (CLI view ticker show parity — cache dashboard) ─


class _ViewTickerDashboardLoader:
    """Load GetTickerDashboardUseCase and format like ``saham view ticker show``."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = Lock()

    def __call__(self, ticker: str) -> Any:
        with self._lock:
            from src.adapters.shared.view_ticker_dashboard_text import (
                format_ticker_dashboard_text,
            )
            from src.adapters.tui.ticker_desk_model import (
                build_ticker_desk_model_from_dashboard,
            )
            from src.application.dto.ticker_dashboard import GetTickerDashboardRequest
            from src.infrastructure.composition.view_ticker_deps import build_view_ticker_deps

            deps = build_view_ticker_deps(self._db_path)
            dashboard = deps.dashboard.execute(
                GetTickerDashboardRequest(ticker=str(ticker).upper(), brief=False)
            )
            body = format_ticker_dashboard_text(dashboard)
            # Structured Harga-mast model for TickerDesk widget (not CLI paste).
            return build_ticker_desk_model_from_dashboard(dashboard, body=body)


# ── View broker (list → show → deep-dives) ──────────────────


class _TickerTopBrokersLoader:
    """Stock → desks: top-brokers ranking + stock-scoped multi-session pulse.

    Ranking: same use case as ``saham view ticker top-brokers`` (latest session).
    Net5 / Stk / Δ1: ``desk_session_pulse`` on broker_daily_flow for that stock
    only (not desk-wide across all tickers).
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = Lock()

    def __call__(self, ticker: str) -> Any:
        with self._lock:
            from types import SimpleNamespace

            from src.adapters.shared.view_ticker_top_brokers_rows import (
                PARTIAL_NETX_LEGEND,
                format_ticker_top_brokers_rows,
            )
            from src.application.services.broker_desk_from_daily_flow import (
                STOCK_DESK_NET_WINDOWS,
                desk_session_pulse,
            )
            from src.application.use_case.view_ticker_top_brokers_use_case import (
                ViewTickerTopBrokersRequest,
            )
            from src.infrastructure.composition.view_ticker_deps import build_view_ticker_deps

            ticker_u = str(ticker).upper()
            deps = build_view_ticker_deps(self._db_path)
            result = deps.top_brokers.execute(
                ViewTickerTopBrokersRequest(ticker=ticker_u, limit=10)
            )
            if result is None:
                return SimpleNamespace(
                    ticker=ticker_u,
                    as_of=None,
                    note="no broker summary · fetch market/broker first",
                    rows=(),
                )

            # Stock-scoped sessions per desk code (one repo read for the ticker).
            codes = {
                str(b.broker_code).upper()
                for b in list(result.top_buyers or ()) + list(result.top_sellers or ())
            }
            pulses: dict[str, Any] = {}
            if codes:
                repo, _foreign = _broker_repo_and_foreign(self._db_path)
                flows = repo.get_broker_daily_flows(
                    ticker_u,
                    broker_codes=sorted(codes),
                )
                by_code: dict[str, list] = {}
                for flow in flows:
                    by_code.setdefault(str(flow.broker_code).upper(), []).append(flow)
                for code in codes:
                    pulse = desk_session_pulse(
                        by_code.get(code, []),
                        net_windows=STOCK_DESK_NET_WINDOWS,
                    )
                    if pulse is not None:
                        pulses[code] = pulse

            rows = format_ticker_top_brokers_rows(
                result,
                limit=10,
                pulses=pulses,
                net_windows=STOCK_DESK_NET_WINDOWS,
            )
            base_note = result.tops_scope_note or (
                "summary tops" if result.tops_source == "summary" else "tracked flow fallback"
            )
            pulsed = sum(1 for r in rows if getattr(r, "has_pulse", False))
            partial = sum(1 for r in rows if getattr(r, "has_partial_netx", False))
            win_label = "/".join(str(w) for w in STOCK_DESK_NET_WINDOWS)
            if pulsed:
                note = f"{base_note} · Net{win_label} stock sessions ({pulsed}/{len(rows)} desks)"
                if partial:
                    # Min sessions among partial desks (clearest shortage signal).
                    min_sess = min(
                        (
                            int(getattr(r, "sessions_cached", 0) or 0)
                            for r in rows
                            if getattr(r, "has_partial_netx", False)
                        ),
                        default=0,
                    )
                    note = (
                        f"{note} · {partial} desk(s) partial NetX "
                        f"(as few as {min_sess} sessions) · {PARTIAL_NETX_LEGEND}"
                    )
            else:
                note = f"{base_note} · no multi-session flow for desks"
            return SimpleNamespace(
                ticker=result.ticker,
                as_of=result.date.isoformat(),
                note=note,
                has_partial_netx=partial > 0,
                rows=tuple(rows),
            )


class _TickerJobLoader:
    """Stock-axis ticker jobs: brokers · flow · foreign · dist · fin.

    Same deps as CLI via build_view_ticker_deps; pure formatters in
    adapters.shared.view_ticker_job_text. Brokers stays on-ticker (chip job),
    not an independent stage.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = Lock()
        self._desks = _TickerTopBrokersLoader(db_path)

    def __call__(self, job: str, ticker: str) -> Any:
        with self._lock:
            from src.adapters.shared.view_ticker_job_text import (
                empty_ticker_job,
                format_ticker_brokers_job,
                format_ticker_distribution_job,
                format_ticker_financials_job,
                format_ticker_flow_job,
                format_ticker_foreign_history_job,
            )
            from src.application.use_case.view_ticker_distribution_use_case import (
                ViewTickerDistributionRequest,
            )
            from src.application.use_case.view_ticker_financials_use_case import (
                ViewTickerFinancialsRequest,
            )
            from src.application.use_case.view_ticker_flow_use_case import (
                ViewTickerFlowRequest,
            )
            from src.application.use_case.view_ticker_foreign_history_use_case import (
                ViewTickerForeignHistoryRequest,
            )
            from src.infrastructure.composition.view_ticker_deps import build_view_ticker_deps

            ticker_u = str(ticker).upper()
            job_k = (job or "").strip().lower()
            deps = build_view_ticker_deps(self._db_path)

            if job_k == "brokers":
                # Same payload as ticker-desks radar; paint under ticker chips
                payload = self._desks(ticker_u)
                rows = list(getattr(payload, "rows", ()) or ())
                return format_ticker_brokers_job(
                    ticker_u,
                    rows,
                    as_of=getattr(payload, "as_of", None),
                    note=getattr(payload, "note", None),
                    fetch_hint=f"saham fetch market {ticker_u}",
                )

            if job_k == "flow":
                result = deps.flow.execute(ViewTickerFlowRequest(ticker=ticker_u, days=10))
                if result is None:
                    return empty_ticker_job("flow", ticker_u)
                return format_ticker_flow_job(
                    result.ticker,
                    result.summaries,
                    total_net=result.total_net_value,
                    buy_days=result.buy_days,
                    sell_days=result.sell_days,
                    window_days=result.days,
                    source=result.source,
                    as_of=result.as_of,
                    fetch_hint=result.fetch_hint,
                )

            if job_k == "foreign":
                result = deps.foreign_history.execute(
                    ViewTickerForeignHistoryRequest(ticker=ticker_u, days=30)
                )
                if result is None:
                    return empty_ticker_job("foreign", ticker_u)
                return format_ticker_foreign_history_job(
                    result.ticker,
                    result.points,
                    resolved_source=result.resolved_source,
                    window_days=result.days,
                    as_of=result.as_of,
                    fetch_hint=result.fetch_hint,
                )

            if job_k == "dist":
                result = deps.distribution.execute(ViewTickerDistributionRequest(ticker=ticker_u))
                if result is None:
                    return empty_ticker_job("dist", ticker_u)
                return format_ticker_distribution_job(
                    result.ticker,
                    result.snapshot,
                    as_of=result.as_of,
                    source=result.source,
                    fetch_hint=result.fetch_hint,
                )

            if job_k == "fin":
                results = []
                for kind in ("income", "balance", "cashflow"):
                    results.append(
                        deps.financials.execute(
                            ViewTickerFinancialsRequest(
                                ticker=ticker_u,
                                statement=kind,  # type: ignore[arg-type]
                                period_type="quarter",
                                limit=8,
                                source="yahoo",
                            )
                        )
                    )
                return format_ticker_financials_job(
                    ticker_u,
                    results,
                    fetch_hint=results[0].fetch_hint if results else None,
                )

            return empty_ticker_job(job_k or "flow", ticker_u, message="unknown job")


def _broker_repo_and_foreign(db_path: Path):
    from src.infrastructure.config.institutional_accumulation_config_loader import (
        load_institutional_accumulation_config,
    )
    from src.infrastructure.persistence.sqlite_broker_repository import (
        SQLiteBrokerRepository,
    )

    foreign = load_institutional_accumulation_config().foreign_broker_codes
    return SQLiteBrokerRepository(db_path), foreign


# List radar only needs recent sessions (Net5 / streak / Δ1). Full history
# was ~500k rows × N desks (~25s). ~45 calendar days ≈ enough trading sessions
# for Net5 + a meaningful buy-streak without hydrating half the table.
_BROKER_LIST_FLOW_LOOKBACK_DAYS = 45


class _BrokerListLoader:
    """Tracked desks + multi-session pulse from broker_daily_flow (cache-only).

    Radar columns: AsOf, DayNet, Net5, Streak, #, Top — not config codes only.

    Performance: one batch query for all tracked codes, date-bounded lookback,
    and idx_bdf_broker_date (broker_code, date).
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = Lock()

    def __call__(self) -> list[Any]:
        with self._lock:
            from datetime import date, timedelta
            from decimal import Decimal
            from types import SimpleNamespace

            from src.adapters.shared.view_number_format import format_value
            from src.application.services.broker_desk_from_daily_flow import (
                classify_desk_type,
                desk_session_pulse,
            )
            from src.domain.entities.broker_flow import BrokerType
            from src.infrastructure.config.institutional_accumulation_config_loader import (
                load_institutional_accumulation_config,
            )
            from src.infrastructure.config.stockbit_config import load_stockbit_config

            sb = load_stockbit_config()
            ia = load_institutional_accumulation_config()
            repo, foreign = _broker_repo_and_foreign(self._db_path)
            codes = [str(c).upper() for c in sb.tracked_broker_codes]
            start = date.today() - timedelta(days=_BROKER_LIST_FLOW_LOOKBACK_DAYS)
            flows_by_code = (
                repo.get_broker_daily_flows_for_codes(codes, start_date=start) if codes else {}
            )

            rows: list[Any] = []
            for code_u in codes:
                btype = classify_desk_type(code_u, foreign or ia.foreign_broker_codes)
                if btype == BrokerType.FOREIGN:
                    label = "Foreign"
                elif btype == BrokerType.LOCAL:
                    label = "Local"
                else:
                    label = "unknown"

                flows = flows_by_code.get(code_u, [])
                pulse = desk_session_pulse(flows) if flows else None
                if pulse is None:
                    rows.append(
                        SimpleNamespace(
                            code=code_u,
                            type_label=label,
                            name="—",
                            as_of="—",
                            day_net="—",
                            net5="—",
                            streak="—",
                            delta1="—",
                            day_net_sort=Decimal("0"),
                            net5_sort=Decimal("0"),
                            tickers="—",
                            top_buy="—",
                            has_data=False,
                        )
                    )
                    continue

                as_of = pulse.as_of
                day_flows = [f for f in flows if f.date == as_of]
                ticker_n = len({f.ticker.upper() for f in day_flows})
                name = (day_flows[0].broker_name or code_u) if day_flows else code_u
                by_ticker: dict[str, Decimal] = {}
                for f in day_flows:
                    t = f.ticker.upper()
                    by_ticker[t] = by_ticker.get(t, Decimal("0")) + f.net_value
                top_buy = "—"
                if by_ticker:
                    best = max(by_ticker.items(), key=lambda kv: kv[1])
                    if best[1] > 0:
                        top_buy = best[0]
                    else:
                        worst = min(by_ticker.items(), key=lambda kv: kv[1])
                        top_buy = f"−{worst[0]}"

                delta1_s = "—"
                if pulse.delta1 is not None:
                    sign = "+" if pulse.delta1 > 0 else ""
                    delta1_s = f"{sign}{format_value(pulse.delta1)}"

                rows.append(
                    SimpleNamespace(
                        code=code_u,
                        type_label=label,
                        name=str(name)[:16],
                        as_of=as_of.isoformat(),
                        day_net=format_value(pulse.day_net),
                        net5=format_value(pulse.net5),
                        streak=str(pulse.buy_streak),
                        delta1=delta1_s,
                        day_net_sort=pulse.day_net,
                        net5_sort=pulse.net5,
                        tickers=str(ticker_n),
                        top_buy=top_buy,
                        has_data=True,
                    )
                )

            # |Net5| first (short regime), then |DayNet|, empty last
            rows.sort(
                key=lambda r: (
                    0 if getattr(r, "has_data", False) else 1,
                    -abs(getattr(r, "net5_sort", Decimal("0"))),
                    -abs(getattr(r, "day_net_sort", Decimal("0"))),
                    r.code,
                )
            )
            return rows


class _BrokerShowLoader:
    """Desk show from cache — same use case as ``saham view broker show``.

    Returns SimpleNamespace(text=..., jump_ticker=..., model=BrokerDeskHomeModel)
    for structured desk home + scraper text + ``v`` jump.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = Lock()

    def __call__(self, code: str) -> Any:
        with self._lock:
            from types import SimpleNamespace

            from src.adapters.tui.broker_desk_home_model import (
                build_broker_desk_home_model,
                format_broker_desk_home_scraper_text,
            )
            from src.application.use_case.view_broker_desk_show_use_case import (
                ViewBrokerDeskShowRequest,
                ViewBrokerDeskShowUseCase,
            )

            code_u = str(code).upper()
            repo, foreign = _broker_repo_and_foreign(self._db_path)
            result = ViewBrokerDeskShowUseCase(repo, foreign_broker_codes=foreign).execute(
                ViewBrokerDeskShowRequest(broker_code=code_u)
            )
            # Multi-session pulse (same pure helper as list Net5 / streak)
            from datetime import date, timedelta

            from src.application.services.broker_desk_from_daily_flow import (
                desk_session_pulse,
            )

            start = date.today() - timedelta(days=_BROKER_LIST_FLOW_LOOKBACK_DAYS)
            flows = repo.get_broker_daily_flows_by_code(code_u, start_date=start)
            pulse = desk_session_pulse(flows) if flows else None

            model = build_broker_desk_home_model(result, pulse=pulse, code=code_u)
            body = format_broker_desk_home_scraper_text(model)
            return SimpleNamespace(
                text=body,
                jump_ticker=model.jump_ticker,
                model=model,
            )


class _BrokerDeepLoader:
    """top-stocks / top-matrix / flow / history text loaders (CLI use cases)."""

    def __init__(self, db_path: Path, page: str) -> None:
        self._db_path = db_path
        self._page = page  # top | matrix | flow | history | cal
        self._lock = Lock()

    def __call__(self, code: str) -> str:
        with self._lock:
            from src.adapters.shared.view_broker_desk_text import (
                format_desk_calendar_text,
                format_desk_flow_text,
                format_desk_history_text,
                format_desk_top_matrix_text,
                format_desk_top_stocks_text,
            )
            from src.application.use_case.view_broker_desk_calendar_use_case import (
                ViewBrokerDeskCalendarRequest,
                ViewBrokerDeskCalendarUseCase,
            )
            from src.application.use_case.view_broker_desk_flow_use_case import (
                ViewBrokerDeskFlowRequest,
                ViewBrokerDeskFlowUseCase,
            )
            from src.application.use_case.view_broker_desk_history_use_case import (
                ViewBrokerDeskHistoryRequest,
                ViewBrokerDeskHistoryUseCase,
            )
            from src.application.use_case.view_broker_desk_top_matrix_use_case import (
                ViewBrokerDeskTopMatrixRequest,
                ViewBrokerDeskTopMatrixUseCase,
            )
            from src.application.use_case.view_broker_desk_top_stocks_use_case import (
                ViewBrokerDeskTopStocksRequest,
                ViewBrokerDeskTopStocksUseCase,
            )

            code_u = str(code).upper()
            repo, foreign = _broker_repo_and_foreign(self._db_path)
            empty = f"{code_u}\n\nno broker_daily_flow for this desk · run broker fetch first"
            if self._page == "top":
                from types import SimpleNamespace

                from src.adapters.tui.broker_desk_top_model import (
                    build_broker_desk_top_model,
                    format_broker_desk_top_scraper_text,
                )

                result = ViewBrokerDeskTopStocksUseCase(repo, foreign_broker_codes=foreign).execute(
                    ViewBrokerDeskTopStocksRequest(broker_code=code_u, limit=20)
                )
                model = build_broker_desk_top_model(result, code=code_u)
                text = (
                    format_desk_top_stocks_text(result)
                    if result is not None
                    else format_broker_desk_top_scraper_text(model)
                )
                return SimpleNamespace(
                    text=text,
                    model=model,
                    jump_ticker=model.jump_ticker,
                )
            if self._page == "matrix":
                from types import SimpleNamespace

                from src.adapters.tui.broker_desk_matrix_model import (
                    build_broker_desk_matrix_model,
                    format_broker_desk_matrix_scraper_text,
                )

                result = ViewBrokerDeskTopMatrixUseCase(repo, foreign_broker_codes=foreign).execute(
                    ViewBrokerDeskTopMatrixRequest(broker_code=code_u)
                )
                model = build_broker_desk_matrix_model(result, code=code_u)
                text = (
                    format_desk_top_matrix_text(result)
                    if result is not None
                    else format_broker_desk_matrix_scraper_text(model)
                )
                return SimpleNamespace(
                    text=text,
                    model=model,
                    jump_ticker=model.jump_ticker,
                )
            if self._page == "flow":
                from types import SimpleNamespace

                from src.adapters.tui.broker_desk_flow_model import (
                    build_broker_desk_flow_model,
                    format_broker_desk_flow_scraper_text,
                )

                result = ViewBrokerDeskFlowUseCase(repo, foreign_broker_codes=foreign).execute(
                    ViewBrokerDeskFlowRequest(broker_code=code_u, days=10)
                )
                model = build_broker_desk_flow_model(result, code=code_u)
                text = (
                    format_desk_flow_text(result)
                    if result is not None
                    else format_broker_desk_flow_scraper_text(model)
                )
                return SimpleNamespace(text=text, model=model, jump_ticker=None)
            if self._page == "history":
                from types import SimpleNamespace

                from src.adapters.tui.broker_desk_history_model import (
                    build_broker_desk_history_model,
                    format_broker_desk_history_scraper_text,
                )

                result = ViewBrokerDeskHistoryUseCase(repo, foreign_broker_codes=foreign).execute(
                    ViewBrokerDeskHistoryRequest(broker_code=code_u, days=30)
                )
                model = build_broker_desk_history_model(result, code=code_u)
                text = (
                    format_desk_history_text(result)
                    if result is not None
                    else format_broker_desk_history_scraper_text(model)
                )
                return SimpleNamespace(
                    text=text,
                    model=model,
                    jump_ticker=model.jump_ticker,
                )
            if self._page == "cal":
                from types import SimpleNamespace

                from src.adapters.tui.broker_desk_calendar_model import (
                    build_broker_desk_calendar_model,
                    format_broker_desk_calendar_scraper_text,
                )

                result = ViewBrokerDeskCalendarUseCase(repo, foreign_broker_codes=foreign).execute(
                    ViewBrokerDeskCalendarRequest(broker_code=code_u)
                )
                model = build_broker_desk_calendar_model(result, code=code_u)
                text = (
                    format_desk_calendar_text(result)
                    if result is not None
                    else format_broker_desk_calendar_scraper_text(model)
                )
                return SimpleNamespace(
                    text=text,
                    model=model,
                    jump_ticker=model.jump_ticker,
                )
            return empty


# ── Plan (structure desk — same engine as CLI plan swing) ───


class _LocalPlanStructureRunner:
    """ADR-054 structure path for focused ticker (thin TUI surface).

    Runs ``PlanSwingWorkflowUseCase`` with local cache defaults — inherits
    screen judgment Action, sizes when capital is configured, persists
    ``swing_trade_plan`` when geometry is complete. Never places orders.
    """

    def __init__(self, db_path: Path, config: Any) -> None:
        self._db_path = db_path
        self._config = config
        self._lock = Lock()

    def __call__(self, ticker: str) -> Any:
        from datetime import date
        from pathlib import Path as PathType

        from src.adapters.composition.plan_swing_command_config import (
            load_plan_swing_command_config,
        )
        from src.adapters.composition.plan_swing_workflow_factory import create_plan_swing_workflow
        from src.application.dto.plan_swing import PlanSwingWorkflowRequest
        from src.application.services.swing_trade_plan_builder import build_swing_trade_plan
        from src.application.services.swing_trade_plan_store import (
            plans_dir_from_journal_path,
            save_swing_trade_plan,
        )
        from src.application.use_case.plan_swing_workflow_use_case import (
            PlanSwingDataUnavailable,
        )

        ticker_u = ticker.upper()
        with self._lock:
            cmd_cfg = load_plan_swing_command_config()
            smart = set(cmd_cfg.swing_policy.smart_money_brokers)
            noise = set(cmd_cfg.swing_policy.noise_brokers)
            weights = {
                **{c: cmd_cfg.swing_policy.smart_weight for c in smart},
                **{c: cmd_cfg.swing_policy.noise_weight for c in noise},
            }
            workflow = create_plan_swing_workflow(
                db_path=self._db_path,
                setup_name=None,
                swing_policy=cmd_cfg.swing_policy,
                plan_swing_config=cmd_cfg.plan_swing_config,
                smart_money_brokers=smart,
                noise_brokers=noise,
                broker_weights=weights,
            )

        capital = self._config.swing.capital
        if capital is None:
            capital = getattr(self._config.trading, "capital", None)

        try:
            response = workflow.execute(
                PlanSwingWorkflowRequest(
                    ticker=ticker_u,
                    today=date.today(),
                    strategy_name=None,
                    setup_name=None,
                    window=int(self._config.swing.window),
                    flow_window=int(cmd_cfg.plan_swing_config.flow_detail_window_sessions),
                    capital=int(capital) if capital is not None else None,
                    risk_pct=float(self._config.swing.risk_pct),
                    entry_price=None,
                    atr_mult=float(self._config.swing.atr_mult),
                    rr=float(self._config.swing.rr),
                    include_sentiment=False,
                    include_flow_detail=False,
                    include_signal_detail=False,
                    include_risk_detail=False,
                    include_market_detail=False,
                    sentiment_verbose=False,
                    auto_refresh=False,
                    force_refresh=False,
                    with_market_context=False,
                    regime_universe=str(self._config.analysis.regime_universe or "lq45"),
                    benchmark=str(self._config.analysis.benchmark or "IHSG"),
                    db_path=PathType(self._db_path),
                    with_technical_gate=False,
                )
            )
        except PlanSwingDataUnavailable:
            return PlanStructureResult(
                summary=f"structure {ticker_u} · no local candles · fetch market first",
                ticker=ticker_u,
                incomplete_reason="no local candles · Ctrl+P Fetch market (explicit)",
            )
        except Exception as exc:
            return PlanStructureResult(
                summary=f"structure error · {exc}",
                ticker=ticker_u,
                incomplete_reason=str(exc)[:120],
            )

        trade_setup = response.trade_setup
        if trade_setup is None and response.verdict is not None:
            trade_setup = response.verdict.trade_setup
        action = "—"
        if trade_setup is not None and trade_setup.action is not None:
            action = str(getattr(trade_setup.action, "value", str(trade_setup.action)))

        plan = build_swing_trade_plan(
            ticker=ticker_u,
            as_of=response.today,
            trade_setup=trade_setup,
            setup_eval=response.setup_eval,
            setup_name=None,
            sizing=response.sizing,
            setup_sizing=response.setup_sizing,
            capital=int(capital) if capital is not None else None,
            risk_pct=float(self._config.swing.risk_pct),
            take_profit_pct=response.take_profit_pct,
            stop_loss_pct=response.stop_loss_pct,
            max_hold_days=cmd_cfg.swing_backtest_config.max_hold_days,
            with_market_context=False,
            with_technical_gate=False,
            latest_close=response.latest_close,
        )
        plan_id_short = ""
        if plan.is_complete:
            plans_dir = plans_dir_from_journal_path(PathType(self._config.storage.accum_journal))
            save_swing_trade_plan(plan, plans_dir)
            plan_id_short = plan.plan_id[:8]

        chosen = response.setup_sizing or response.sizing
        entry_s = stop_s = target_s = lots_s = "—"
        incomplete = ""
        if chosen is not None and getattr(chosen, "lots", None):
            entry_s = _fmt_price(getattr(chosen, "entry_price", None))
            stop_s = _fmt_price(getattr(chosen, "stop_price", None))
            target_s = _fmt_price(getattr(chosen, "target_price", None))
            lots_s = str(getattr(chosen, "lots", None) or "—")
            summary = (
                f"structure {action} · entry {entry_s} · "
                f"stop {stop_s} · target {target_s} · "
                f"{lots_s} lots"
                + (f" · plan {plan_id_short}" if plan_id_short else "")
                + " · no order"
            )
        elif capital is None:
            incomplete = "no capital · set swing.capital in user.yaml or CLI --capital"
            summary = f"structure {action} · {incomplete} · no order"
        else:
            incomplete = "sizing incomplete (missing entry/stop/target/lots)"
            summary = f"structure {action} · sizing incomplete · no order"
            # Still surface any partial geometry from plan builder if present
            if plan.entry_price is not None:
                entry_s = _fmt_price(plan.entry_price)
            if plan.stop_price is not None:
                stop_s = _fmt_price(plan.stop_price)
            if plan.target_price is not None:
                target_s = _fmt_price(plan.target_price)
            if plan.lots is not None:
                lots_s = str(plan.lots)

        try:
            risk_s = f"{float(self._config.swing.risk_pct):.1f}"
        except (TypeError, ValueError, AttributeError):
            risk_s = "—"
        return PlanStructureResult(
            summary=summary,
            ticker=ticker_u,
            action=action,
            entry=entry_s,
            stop=stop_s,
            target=target_s,
            lots=lots_s,
            incomplete_reason=incomplete,
            plan_id_short=plan_id_short,
            inherits_action=True,
            no_order=True,
            risk_pct=risk_s,
            horizon="swing",
        )


def _fmt_price(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return str(value)


class _LocalPaperLogFromPlanRunner:
    """CLI-parity paper log: load ``TICKER_latest.json`` then journal workflow.

    Thin composition only — no journal schema fork. Requires complete plan on disk
    (written by plan structure runner when geometry is complete).
    """

    def __init__(self, db_path: Path, config: Any) -> None:
        self._db_path = Path(db_path)
        self._config = config
        self._lock = Lock()

    def __call__(self, ticker: str) -> Any:
        from datetime import date as date_cls

        from src.adapters.composition.trade_accum_workflow_factory import (
            create_log_accumulation_trade_workflow,
        )
        from src.adapters.tui.paper_log_result import PaperLogResult, refuse_paper_log
        from src.application.services.swing_trade_plan_store import (
            load_swing_trade_plan,
            plans_dir_from_journal_path,
            resolve_from_plan_path,
        )
        from src.application.use_case.evaluate_swing_setup_use_case import (
            FOREIGN_BOUNCE_SETUP,
        )
        from src.application.use_case.log_accumulation_trade_workflow_use_case import (
            LogAccumulationTradeWorkflowRequest,
        )
        from src.infrastructure.config.app_config import load_app_config

        ticker_u = str(ticker or "").strip().upper()
        if not ticker_u:
            return refuse_paper_log("—", "no ticker · nothing to log")

        journal_path = Path(self._config.storage.accum_journal)
        plans_dir = plans_dir_from_journal_path(journal_path)
        try:
            plan_path = resolve_from_plan_path(
                ticker=ticker_u, from_plan="latest", plans_dir=plans_dir
            )
            plan = load_swing_trade_plan(plan_path)
        except FileNotFoundError:
            return refuse_paper_log(
                ticker_u,
                "no saved plan · run structure desk (p) until complete, then log",
            )
        except (OSError, ValueError) as exc:
            return refuse_paper_log(ticker_u, f"plan load failed · {exc}")

        if plan.ticker.upper() != ticker_u:
            return refuse_paper_log(
                ticker_u,
                f"plan ticker {plan.ticker} does not match focus {ticker_u}",
            )
        if not plan.is_complete:
            return refuse_paper_log(
                ticker_u,
                plan.incomplete_reason or "plan geometry incomplete · need entry/stop/target/lots",
            )

        setup = plan.setup_name or FOREIGN_BOUNCE_SETUP
        cfg = load_app_config()
        window = int(getattr(self._config.swing, "window", 7) or 7)
        with self._lock:
            bundle = create_log_accumulation_trade_workflow(
                db_path=self._db_path,
                journal_path=journal_path,
                with_regime=False,
                regime_universe=None,
                benchmark=str(cfg.analysis.benchmark or "IHSG"),
            )
            request = LogAccumulationTradeWorkflowRequest(
                ticker=ticker_u,
                window=window,
                entry_price=plan.entry_price,
                from_analysis=True,
                setup=setup,
                with_regime=False,
                benchmark=str(cfg.analysis.benchmark or "IHSG"),
                logged_at=date_cls.today(),
                from_plan=True,
                plan_entry=plan.entry_price,
                plan_stop=plan.stop_price,
                plan_target=plan.target_price,
                plan_setup_match=plan.setup_match,
                plan_max_hold_days=plan.max_hold_days,
            )
            try:
                workflow_result = bundle.workflow.execute(request)
            except ValueError as exc:
                return refuse_paper_log(ticker_u, str(exc))
            except Exception as exc:
                return refuse_paper_log(ticker_u, f"journal write failed · {exc}")

        resp = workflow_result.response
        entry_s = _fmt_price(resp.entry_price)
        stop_s = _fmt_price(resp.planned_stop)
        target_s = _fmt_price(resp.planned_target)
        plan_id = plan.plan_id[:8] if plan.plan_id else ""
        if not resp.written:
            return PaperLogResult(
                ticker=ticker_u,
                written=False,
                message=(
                    f"already logged {ticker_u} for {workflow_result.logged_at} "
                    f"(window={window}) — no new row"
                ),
                planned_entry=entry_s,
                planned_stop=stop_s,
                planned_target=target_s,
                refused=False,
                plan_id=plan_id,
            )
        return PaperLogResult(
            ticker=ticker_u,
            written=True,
            message=(
                f"paper logged {ticker_u} · entry {entry_s} · "
                f"stop {stop_s} · target {target_s}" + (f" · plan {plan_id}" if plan_id else "")
            ),
            planned_entry=entry_s,
            planned_stop=stop_s,
            planned_target=target_s,
            refused=False,
            plan_id=plan_id,
        )


class _LocalPhaseHistoryLoader:
    """Read-only setup phase ledger rows before as_of (no network, no write).

    SQL ``list_rows_before`` is ASC oldest→newest. Applying SQL LIMIT N would
    keep the *oldest* N rows and drop recent phases — wrong for Judge display.
    Match application ``load_previous_setup_phases`` last-N: load all prior rows,
    then keep the most recent ``max_facts`` (default 20).
    """

    def __init__(self, db_path: Path, *, max_facts: int = 20) -> None:
        self._db_path = Path(db_path)
        self._max_facts = max(0, int(max_facts))

    def __call__(self, ticker: str, before_date: date) -> Any:
        from src.adapters.tui.phase_sequence import facts_from_ledger_rows
        from src.infrastructure.persistence.sqlite_setup_phase_ledger_repository import (
            SQLiteSetupPhaseLedgerRepository,
        )

        symbol = str(ticker or "").strip().upper()
        if not symbol:
            return ()
        repo = SQLiteSetupPhaseLedgerRepository(self._db_path)
        # No SQL LIMIT — ASC + LIMIT would return oldest rows only.
        rows = tuple(repo.list_rows_before(ticker=symbol, before_date=before_date))
        if self._max_facts > 0 and len(rows) > self._max_facts:
            rows = rows[-self._max_facts :]
        return facts_from_ledger_rows(rows)


class _LocalCacheHealthLoader:
    """Local SQLite date-range health for sidebar (no network)."""

    def __init__(self, db_path: Path, universe: str) -> None:
        self._db_path = Path(db_path)
        self._universe = universe

    def __call__(self) -> Any:
        from src.infrastructure.persistence.sqlite_broker_repository import (
            SQLiteBrokerRepository,
        )
        from src.infrastructure.persistence.sqlite_market_repository import (
            SQLiteMarketRepository,
        )

        market = SQLiteMarketRepository(self._db_path)
        broker = SQLiteBrokerRepository(self._db_path)

        def candle_latest():
            for sym in ("IHSG", "^JKSE", "BBCA"):
                rng = market.get_date_range(sym)
                if rng is not None:
                    return rng[1]
            return None

        def broker_latest():
            for sym in ("BBCA", "BBRI", "TLKM"):
                rng = broker.get_broker_daily_flow_date_range(sym)
                if rng is not None:
                    return rng[1]
            # Fallback: summary date range if available
            try:
                rng = broker.get_date_range("BBCA")
                if rng is not None:
                    return rng[1]
            except Exception:
                pass
            return None

        return load_local_cache_health(
            universe=self._universe,
            get_candle_latest=candle_latest,
            get_broker_latest=broker_latest,
        )


# ── Explicit fetch ─────────────────────────────────────────


def _build_fetch_previewer(db_path: Path) -> Callable[[], Any]:
    def preview() -> Any:
        from src.application.services.universe_loader import resolve_tickers
        from src.application.use_case.refresh_daily_workspace_use_case import (
            PreviewDailyWorkspaceRefreshUseCase,
            RefreshDailyWorkspaceRequest,
        )
        from src.infrastructure.composition.broker_provider_factory import (
            create_broker_provider,
        )
        from src.infrastructure.config.data_sources_config import candle_source
        from src.infrastructure.persistence.sqlite_broker_repository import (
            SQLiteBrokerRepository,
        )

        config = load_app_config()
        _, broker_name = create_broker_provider(None)
        candles_label = candle_source()

        def resolver(req: RefreshDailyWorkspaceRequest):
            tickers = resolve_tickers(
                universe=req.universe,
                explicit=list(req.tickers),
                db_path=db_path,
                loader=YamlUniverseConfigLoader(),
                repository=SQLiteBrokerRepository(db_path),
            )
            return (len(tickers), candles_label, broker_name, ())

        plan = PreviewDailyWorkspaceRefreshUseCase(resolver).execute(
            RefreshDailyWorkspaceRequest(universe=config.analysis.universe or "lq45")
        )
        summary = (
            f"Universe {plan.universe} · {plan.resolved_ticker_count} tickers · "
            f"{plan.history_days}d · candles {plan.candles_provider_label} · "
            f"broker {plan.broker_provider_label}"
        )
        return type("P", (), {"summary": summary, "plan": plan})()

    return preview


def _build_fetch_runner(db_path: Path) -> Callable[[], Any]:
    def run() -> Any:
        from src.application.use_case.fetch_market_command_workflow_use_case import (
            FetchMarketCommandWorkflowRequest,
        )
        from src.infrastructure.composition.broker_provider_factory import (
            create_broker_provider,
        )
        from src.infrastructure.composition.fetch_market.fetch_market_workflow_factory import (
            create_workflow_use_case,
        )
        from src.infrastructure.config.data_sources_config import candle_source

        config = load_app_config()
        broker_provider_obj, broker_provider_name = create_broker_provider(None)
        workflow = create_workflow_use_case(
            db_path=db_path,
            broker_provider=broker_provider_obj,
            broker_provider_name=broker_provider_name,
        )
        req = FetchMarketCommandWorkflowRequest(
            tickers=[],
            universe=config.analysis.universe or "lq45",
            days=45,
            db_path=db_path,
            candles_provider=candle_source(),
            broker_provider=broker_provider_obj,
            broker_provider_name=broker_provider_name,
            refresh=False,
            candles_only=False,
            broker_only=False,
            no_meta=False,
            no_enrichment=False,
            no_calendar=False,
            no_macro_calendar=False,
        )
        return workflow.execute(req)

    return run


def _preopen_empty(payload: Any) -> bool:
    if payload is None:
        return True
    response = getattr(payload, "response", None)
    if response is None:
        return True
    result = getattr(response, "result", None)
    candidates = getattr(result, "candidates", None) if result is not None else None
    if candidates is not None:
        return len(candidates) == 0
    return False


def _resolve_tickers(deps: ScreenDeps, universe: str) -> list[str]:
    from src.application.services.universe_loader import resolve_tickers

    try:
        return list(
            resolve_tickers(
                universe=universe,
                explicit=[],
                db_path=deps.db_path,
                loader=YamlUniverseConfigLoader(),
                repository=deps.broker_repository,
            )
        )
    except Exception:
        return []
