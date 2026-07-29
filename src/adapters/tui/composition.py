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
from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.main import CockpitApp
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
) -> CockpitApp:
    """Build cockpit with real local loaders unless tests inject fakes."""
    config = load_app_config()
    db_path = Path(config.storage.db_path)
    screen_deps = build_screen_deps(db_path)

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
        accum_controller=BoardController(accum_loader),
        preopen_controller=BoardController(
            preopen_loader,
            empty_when=_preopen_empty,
        ),
        accum_presenter=AccumPresenter(),
        preopen_presenter=PreOpenPresenter(),
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

    def __call__(self, ticker: str) -> str:
        with self._lock:
            from src.adapters.cli.view_ticker_display import format_ticker_dashboard_text
            from src.application.dto.ticker_dashboard import GetTickerDashboardRequest
            from src.infrastructure.composition.view_ticker_deps import build_view_ticker_deps

            deps = build_view_ticker_deps(self._db_path)
            dashboard = deps.dashboard.execute(
                GetTickerDashboardRequest(ticker=str(ticker).upper(), brief=False)
            )
            return format_ticker_dashboard_text(dashboard)


# ── View broker (list → show → deep-dives) ──────────────────


def _broker_repo_and_foreign(db_path: Path):
    from src.infrastructure.config.institutional_accumulation_config_loader import (
        load_institutional_accumulation_config,
    )
    from src.infrastructure.persistence.sqlite_broker_repository import (
        SQLiteBrokerRepository,
    )

    foreign = load_institutional_accumulation_config().foreign_broker_codes
    return SQLiteBrokerRepository(db_path), foreign


class _BrokerListLoader:
    """Tracked desks + multi-session pulse from broker_daily_flow (cache-only).

    Radar columns: AsOf, DayNet, Net5, Streak, #, Top — not config codes only.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = Lock()

    def __call__(self) -> list[Any]:
        with self._lock:
            from decimal import Decimal
            from types import SimpleNamespace

            from src.adapters.cli.view_broker_desk_display import format_value
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
            rows: list[Any] = []
            for code in sb.tracked_broker_codes:
                code_u = str(code).upper()
                btype = classify_desk_type(code_u, foreign or ia.foreign_broker_codes)
                if btype == BrokerType.FOREIGN:
                    label = "Foreign"
                elif btype == BrokerType.LOCAL:
                    label = "Local"
                else:
                    label = "unknown"

                flows = repo.get_broker_daily_flows_by_code(code_u)
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

    Returns SimpleNamespace(text=..., jump_ticker=...) for TUI hub + ``v`` jump.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = Lock()

    def __call__(self, code: str) -> Any:
        with self._lock:
            from types import SimpleNamespace

            from src.adapters.cli.view_broker_desk_display import format_desk_show_text
            from src.application.use_case.view_broker_desk_show_use_case import (
                ViewBrokerDeskShowRequest,
                ViewBrokerDeskShowUseCase,
            )

            repo, foreign = _broker_repo_and_foreign(self._db_path)
            result = ViewBrokerDeskShowUseCase(repo, foreign_broker_codes=foreign).execute(
                ViewBrokerDeskShowRequest(broker_code=str(code).upper())
            )
            if result is None:
                return SimpleNamespace(
                    text=(
                        f"{code.upper()}\n\n"
                        "no broker_daily_flow for this desk · run broker fetch first"
                    ),
                    jump_ticker=None,
                )
            jump = None
            if result.top_buy_stocks:
                jump = str(result.top_buy_stocks[0].ticker).upper()
            elif result.top_sell_stocks:
                jump = str(result.top_sell_stocks[0].ticker).upper()
            body = format_desk_show_text(result)
            # Multi-session pulse (same pure helper as list Net5 / streak)
            from src.adapters.cli.view_broker_desk_display import format_value
            from src.application.services.broker_desk_from_daily_flow import (
                desk_session_pulse,
            )

            flows = repo.get_broker_daily_flows_by_code(str(code).upper())
            pulse = desk_session_pulse(flows) if flows else None
            if pulse is not None:
                d1 = "—"
                if pulse.delta1 is not None:
                    sign = "+" if pulse.delta1 > 0 else ""
                    d1 = f"{sign}{format_value(pulse.delta1)}"
                pulse_line = (
                    f"\npulse: DayNet {format_value(pulse.day_net)} · "
                    f"Net5 {format_value(pulse.net5)} "
                    f"({pulse.sessions_in_net5}s) · buy-streak {pulse.buy_streak} · Δ1 {d1}\n"
                )
                # Insert after header block (after scope_note line in format_desk_show_text)
                parts = body.split("\n", 4)
                if len(parts) >= 4:
                    body = (
                        "\n".join(parts[:4])
                        + pulse_line
                        + ("\n".join(parts[4:]) if len(parts) > 4 else "")
                    )
                else:
                    body = body + pulse_line
            return SimpleNamespace(text=body, jump_ticker=jump)


class _BrokerDeepLoader:
    """top-stocks / flow / history text loaders (CLI use cases)."""

    def __init__(self, db_path: Path, page: str) -> None:
        self._db_path = db_path
        self._page = page  # top | flow | history
        self._lock = Lock()

    def __call__(self, code: str) -> str:
        with self._lock:
            from src.adapters.cli.view_broker_desk_display import (
                format_desk_flow_text,
                format_desk_history_text,
                format_desk_top_stocks_text,
            )
            from src.application.use_case.view_broker_desk_flow_use_case import (
                ViewBrokerDeskFlowRequest,
                ViewBrokerDeskFlowUseCase,
            )
            from src.application.use_case.view_broker_desk_history_use_case import (
                ViewBrokerDeskHistoryRequest,
                ViewBrokerDeskHistoryUseCase,
            )
            from src.application.use_case.view_broker_desk_top_stocks_use_case import (
                ViewBrokerDeskTopStocksRequest,
                ViewBrokerDeskTopStocksUseCase,
            )

            code_u = str(code).upper()
            repo, foreign = _broker_repo_and_foreign(self._db_path)
            empty = f"{code_u}\n\nno broker_daily_flow for this desk · run broker fetch first"
            if self._page == "top":
                result = ViewBrokerDeskTopStocksUseCase(repo, foreign_broker_codes=foreign).execute(
                    ViewBrokerDeskTopStocksRequest(broker_code=code_u, limit=20)
                )
                return format_desk_top_stocks_text(result) if result else empty
            if self._page == "flow":
                result = ViewBrokerDeskFlowUseCase(repo, foreign_broker_codes=foreign).execute(
                    ViewBrokerDeskFlowRequest(broker_code=code_u, days=10)
                )
                return format_desk_flow_text(result) if result else empty
            if self._page == "history":
                result = ViewBrokerDeskHistoryUseCase(repo, foreign_broker_codes=foreign).execute(
                    ViewBrokerDeskHistoryRequest(broker_code=code_u, days=30)
                )
                return format_desk_history_text(result) if result else empty
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

        from src.adapters.cli.plan_swing_command_config import load_plan_swing_command_config
        from src.adapters.cli.plan_swing_workflow_factory import create_plan_swing_workflow
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
            return type(
                "R",
                (),
                {"summary": f"structure {ticker_u} · no local candles · fetch market first"},
            )()
        except Exception as exc:
            return type("R", (), {"summary": f"structure error · {exc}"})()

        trade_setup = response.trade_setup
        if trade_setup is None and response.verdict is not None:
            trade_setup = response.verdict.trade_setup
        action = "—"
        if trade_setup is not None and trade_setup.action is not None:
            action = getattr(trade_setup.action, "value", str(trade_setup.action))

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
        plan_note = ""
        if plan.is_complete:
            plans_dir = plans_dir_from_journal_path(PathType(self._config.storage.accum_journal))
            save_swing_trade_plan(plan, plans_dir)
            plan_note = f" · plan {plan.plan_id[:8]}"

        chosen = response.setup_sizing or response.sizing
        if chosen is not None and getattr(chosen, "lots", None):
            entry = getattr(chosen, "entry_price", None)
            stop = getattr(chosen, "stop_price", None)
            target = getattr(chosen, "target_price", None)
            lots = getattr(chosen, "lots", None)
            summary = (
                f"structure {action} · entry {_fmt_price(entry)} · "
                f"stop {_fmt_price(stop)} · target {_fmt_price(target)} · "
                f"{lots} lots{plan_note} · no order"
            )
        elif capital is None:
            summary = (
                f"structure {action} · no capital · "
                f"set swing.capital in user.yaml or CLI --capital · no order"
            )
        else:
            summary = f"structure {action} · sizing incomplete · no order"

        return type("R", (), {"summary": summary})()


def _fmt_price(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return str(value)


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
