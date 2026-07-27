"""Composition root for the optional daily cockpit TUI.

Infrastructure imports stay confined here. Screens receive injected callables
and controllers only.

Layer: Adapter composition root
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Lock
from typing import Any

from src.adapters.composition.screen_deps import ScreenDeps, build_screen_deps
from src.adapters.tui.controllers.board_controller import BoardController
from src.adapters.tui.main import CockpitApp
from src.adapters.tui.presenters.accum_presenter import AccumPresenter
from src.application.use_case.run_accumulation_screen_workflow_use_case import (
    RunAccumulationScreenWorkflowRequest,
)
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

    if accum_loader is None:
        screen_deps = build_screen_deps(db_path)
        accum_loader = _ScreenAccumLoader(screen_deps, config)

    accum_controller = BoardController(accum_loader)
    accum_presenter = AccumPresenter()

    # Phase 3/4 loaders: optional thin wiring (may stay None until those phases).
    preopen_controller = BoardController(preopen_loader) if preopen_loader else None

    return CockpitApp(
        accum_loader=accum_loader,
        preopen_loader=preopen_loader,
        plan_runner=plan_runner,
        fetch_previewer=fetch_previewer,
        fetch_runner=fetch_runner,
        ticker_detail_loader=ticker_detail_loader,
        accum_controller=accum_controller,
        preopen_controller=preopen_controller,
        accum_presenter=accum_presenter,
        preopen_presenter=None,
    )


create_cockpit_app = create_tui_app


class _ScreenAccumLoader:
    """Lazy, serialized accumulation screen runner (CLI-parity request defaults)."""

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
            # Honest empty — no invented universe
            return _EmptyAccumResult()

        request = RunAccumulationScreenWorkflowRequest(
            tickers=tickers,
            universe_label=universe,
            universe_name=universe,
            window=7,
            min_streak=0,
            min_accum_score=None,
            min_signal_score=None,
            min_piotroski=0,
            strategy_name=None,
            include_strategy_overlay=False,
            multi=False,
            windows=[],
            top=40,
            save_name=None,
            save_enabled=False,
            vwap_only=False,
            squeeze_only=False,
            sort_by="signal",
            as_of_date=None,
        )
        return use_case.execute(request)


class _EmptyAccumResult:
    single_projection = type("P", (), {"candidates": (), "window_days": 7, "data_as_of": {}})()
    multi_projection = None
    warnings: tuple[str, ...] = ("No tickers in local universe/cache",)


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
