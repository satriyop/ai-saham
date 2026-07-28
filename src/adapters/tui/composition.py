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
    build_screen_accum_request,
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
        plan_runner = _LocalPlanRunner(screen_deps, config)
    if fetch_previewer is None:
        fetch_previewer = _build_fetch_previewer(db_path)
    if fetch_runner is None:
        fetch_runner = _build_fetch_runner(db_path)

    return CockpitApp(
        accum_loader=accum_loader,
        preopen_loader=preopen_loader,
        plan_runner=plan_runner,
        fetch_previewer=fetch_previewer,
        fetch_runner=fetch_runner,
        ticker_detail_loader=ticker_detail_loader,
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


# ── Plan (local screen-based summary — no broker order) ────


class _LocalPlanRunner:
    """Confirm path: re-score single ticker via accum screen; surface action."""

    def __init__(self, deps: ScreenDeps, config: Any) -> None:
        self._deps = deps
        self._config = config
        self._lock = Lock()
        self._use_case = None

    def __call__(self, ticker: str) -> Any:
        with self._lock:
            if self._use_case is None:
                self._use_case = self._deps.build_accum_workflow_use_case()
            use_case = self._use_case

        universe = (self._config.analysis.universe or "lq45").lower()
        # Same request shape as screen accum; top=5 is a plan-path override only.
        request = build_screen_accum_request(
            tickers=[ticker.upper()],
            universe_label=universe,
            universe_name=universe,
            top=5,
        )
        result = use_case.execute(request)
        projection = result.single_projection
        if projection is None or not projection.candidates:
            return type("R", (), {"summary": "no local setup · cache thin"})()
        cand = projection.candidates[0]
        action = "—"
        if cand.trade_setup is not None and cand.trade_setup.action is not None:
            action = getattr(cand.trade_setup.action, "value", str(cand.trade_setup.action))
        score = getattr(cand, "accum_score", None)
        score_s = f"{float(score):.0f}" if isinstance(score, (int, float)) else "—"
        return type(
            "R",
            (),
            {"summary": f"local {action} · accum {score_s} · no broker order"},
        )()


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
