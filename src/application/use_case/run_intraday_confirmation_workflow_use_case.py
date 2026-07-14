"""
RunIntradayConfirmationWorkflowUseCase — orchestrates the `saham trade confirm`
command workflow: sidecar/track-file loading, opening-price resolution,
post-open confirmation, and confirmation-sidecar persistence.

Layer: Application

This use case owns command-workflow orchestration only. It does not own the
deterministic post-open gating rules, which remain in
ConfirmIntradayOpenUseCase.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from src.domain.ports.order_book_provider import OrderBookProvider
    from src.domain.ports.running_trade_provider import RunningTradeProvider

from src.application.dto.intraday_confirmation_workflow import (
    RunIntradayConfirmationWorkflowRequest,
    RunIntradayConfirmationWorkflowResult,
)
from src.application.services.intraday_confirmation_session_store import (
    load_intraday_confirmation_candidates,
    load_intraday_confirmation_tickers,
    load_opening_prices_from_track_file,
    load_pre_open_market_regime,
    write_intraday_confirmation_sidecar,
)
from src.application.services.pre_open_screen_config import PreOpenScreenConfig
from src.application.use_case.confirm_intraday_open_use_case import (
    ConfirmIntradayOpenRequest,
    ConfirmIntradayOpenUseCase,
)
from src.application.use_case.resolve_opening_prices_use_case import (
    OpeningPriceObservation,
    ResolveOpeningPricesRequest,
    ResolveOpeningPricesUseCase,
)

# Event names emitted through on_event(event, payload). The adapter switches
# on these to reproduce the exact CLI output ordering without any printing
# happening inside application code.
EVENT_STARTED = "started"
EVENT_MANUAL_PRICES = "manual_prices"
EVENT_TRACK_PRICES = "track_prices"
EVENT_AUTO_RESOLUTION_NEEDED = "auto_resolution_needed"
EVENT_OBSERVATION = "observation"
EVENT_RESOLUTION_SUMMARY = "resolution_summary"
EVENT_REGIME_WARNING = "regime_warning"


class IntradayAutoResolutionUnavailable(RuntimeError):
    """Raised when live auto-resolution is needed but no provider is available."""


class IntradayTrackFileParseError(ValueError):
    """Raised when a supplied track file exists but cannot be parsed."""


ProviderFactory = Callable[[], tuple["RunningTradeProvider | None", "OrderBookProvider | None"]]


class RunIntradayConfirmationWorkflowUseCase:
    """Orchestrates the intraday confirmation command workflow end to end."""

    def __init__(
        self,
        *,
        provider_factory: ProviderFactory | None = None,
        pre_open_config: PreOpenScreenConfig,
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        """provider_factory is invoked at most once, and only when live
        auto-resolution is actually needed — never eagerly. This keeps
        fully-manual/track-file confirmations free of any Stockbit
        session/provider construction.
        """
        self._provider_factory = provider_factory
        self._pre_open_config = pre_open_config
        self._on_event = on_event

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        if self._on_event is not None:
            self._on_event(event, payload)

    def execute(
        self, request: RunIntradayConfirmationWorkflowRequest
    ) -> RunIntradayConfirmationWorkflowResult:
        if not request.sidecar_path.exists():
            raise FileNotFoundError(request.sidecar_path)

        screened_at, tickers = load_intraday_confirmation_tickers(request.sidecar_path)
        self._emit(
            EVENT_STARTED,
            {
                "tickers": tickers,
                "screened_at": screened_at,
                "sidecar_path": request.sidecar_path,
            },
        )

        if request.manual_prices:
            self._emit(EVENT_MANUAL_PRICES, {"count": len(request.manual_prices)})

        track_prices: dict[str, OpeningPriceObservation] = {}
        if request.track_file is not None:
            if not request.track_file.exists():
                raise FileNotFoundError(request.track_file)
            try:
                track_prices = load_opening_prices_from_track_file(
                    request.track_file, tickers
                )
            except Exception as e:
                raise IntradayTrackFileParseError(str(e)) from e

        if track_prices:
            self._emit(EVENT_TRACK_PRICES, {"count": len(track_prices)})

        missing_resolved = [
            t for t in tickers
            if t not in request.manual_prices and t not in track_prices
        ]
        auto_needed = (
            request.live_auto_resolution_enabled
            and request.track_file is None
            and bool(missing_resolved)
        )

        running_trade_provider: "RunningTradeProvider | None" = None
        order_book_provider: "OrderBookProvider | None" = None
        if auto_needed:
            self._emit(EVENT_AUTO_RESOLUTION_NEEDED, {"missing": missing_resolved})
            if self._provider_factory is not None:
                running_trade_provider, order_book_provider = self._provider_factory()
            if running_trade_provider is None or order_book_provider is None:
                raise IntradayAutoResolutionUnavailable(
                    "No authenticated Stockbit profile for auto confirm. "
                    "Run `saham fetch stockbit login` or "
                    "pass --opening-json / --track-file."
                )

        resolver = ResolveOpeningPricesUseCase(
            running_trade_provider=running_trade_provider,
            order_book_provider=order_book_provider,
            on_observation=lambda index, total, observation: self._emit(
                EVENT_OBSERVATION,
                {"index": index, "total": total, "observation": observation},
            ),
        )
        observations = resolver.execute(
            ResolveOpeningPricesRequest(
                tickers=tickers,
                run_date=screened_at,
                manual_prices=request.manual_prices,
                track_prices=track_prices,
            )
        )

        resolved_count = sum(1 for obs in observations.values() if obs.price is not None)
        unresolved = [obs for obs in observations.values() if obs.price is None]
        self._emit(
            EVENT_RESOLUTION_SUMMARY,
            {
                "resolved_count": resolved_count,
                "total": len(tickers),
                "unresolved": unresolved,
            },
        )

        opening_prices = {
            t: o.price for t, o in observations.items() if o.price is not None
        }
        screened_at, candidates, extras = load_intraday_confirmation_candidates(
            request.sidecar_path, opening_prices, observations,
        )

        regime_val, regime_warning = load_pre_open_market_regime(request.sidecar_path)
        warnings: tuple[str, ...] = ()
        if regime_warning:
            self._emit(EVENT_REGIME_WARNING, {"warning": regime_warning})
            warnings = (regime_warning,)
            regime_val = "RISK_OFF"

        po_config = self._pre_open_config
        confirm_use_case = ConfirmIntradayOpenUseCase()
        confirm_result = confirm_use_case.execute(
            ConfirmIntradayOpenRequest(
                candidates=candidates,
                run_date=screened_at,
                max_stop_pct=request.max_stop_pct,
                tick_friction_gate=po_config.tick_friction_gate,
                min_target_ticks=po_config.min_target_ticks,
                min_stop_ticks=po_config.min_stop_ticks,
                regime=regime_val,
                regime_gate_enabled=po_config.regime_gate_enabled,
                tighten_in_regimes=tuple(po_config.tighten_in_regimes),
                gap_pct_tightening_factor=Decimal(str(po_config.gap_pct_tightening_factor)),
                require_backed_in_weak=po_config.require_backed_in_weak,
            )
        )

        write_intraday_confirmation_sidecar(
            confirm_result.confirmations,
            confirm_result.confirmed_date,
            confirm_result.max_stop_pct,
            request.output_path,
        )

        return RunIntradayConfirmationWorkflowResult(
            observations=observations,
            confirmations=confirm_result.confirmations,
            confirmed_date=confirm_result.confirmed_date,
            max_stop_pct=confirm_result.max_stop_pct,
            extras=extras,
            warnings=warnings,
            output_path=request.output_path,
        )
