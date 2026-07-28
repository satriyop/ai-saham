"""Shared repository data loading for evidence-family assemblers.

Layer: Application

Both `SwingAnalysisEvidenceBuilder` and `AccumulationCandidateEvidenceBuilder`
need the same broker/candle windows to assemble institutional accumulation,
ticker profile, and sector context evidence. This loader centralizes those
repository calls so the two coordinators stop duplicating the fetch logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

from src.application.services.swing_analysis_market_helpers import (
    benchmark_return_from_repository,
)

if TYPE_CHECKING:
    from src.application.ports.macro_calendar_repository import MacroCalendarRepository
    from src.domain.entities.broker_flow import (
        BrokerDailyFlow,
        BrokerSummary,
        ForeignFlowPoint,
    )
    from src.domain.entities.candle import Candle
    from src.domain.ports.broker_data_repository import BrokerDataRepository
    from src.domain.ports.market_data_repository import MarketDataRepository
    from src.domain.value_objects.policy_rate_step import PolicyRateStep

_FLOW_WINDOW_DAYS = 45


@dataclass(frozen=True)
class InstitutionalEvidenceInputs:
    candles: tuple["Candle", ...]
    broker_daily_flows: tuple["BrokerDailyFlow", ...]
    foreign_flow_points: tuple["ForeignFlowPoint", ...]
    broker_summaries: tuple["BrokerSummary", ...]


@dataclass(frozen=True)
class TickerProfileEvidenceInputs:
    candles: tuple["Candle", ...]
    broker_daily_flows: tuple["BrokerDailyFlow", ...]
    broker_summaries: tuple["BrokerSummary", ...]


@dataclass(frozen=True)
class SectorContextInputs:
    ticker_candles: tuple["Candle", ...]
    peer_candles: dict[str, list["Candle"]]
    ihsg_20d_return: float | None


@dataclass(frozen=True)
class SectorMacroContextInputs:
    """Preloaded macro series candles + optional policy steps (P2a)."""

    series_candles: dict[str, tuple["Candle", ...]]
    policy_steps: dict[str, tuple["PolicyRateStep", ...]] | None = None


class CandidateEvidenceDataLoader:
    """Loads point-in-time repository data shared across evidence assemblers."""

    def __init__(
        self,
        market_repository: "MarketDataRepository",
        broker_repository: "BrokerDataRepository",
        macro_calendar_repository: "MacroCalendarRepository | None" = None,
    ) -> None:
        self._market_repo = market_repository
        self._broker_repo = broker_repository
        self._macro_calendar_repo = macro_calendar_repository

    def load_institutional_inputs(
        self,
        *,
        ticker: str,
        snapshot_date: date,
        candles: tuple | list | None = None,
    ) -> InstitutionalEvidenceInputs:
        start_date = snapshot_date - timedelta(days=_FLOW_WINDOW_DAYS)
        resolved_candles = (
            tuple(candles)
            if candles is not None
            else tuple(self._market_repo.get_candles(ticker, end_date=snapshot_date))
        )
        return InstitutionalEvidenceInputs(
            candles=resolved_candles,
            broker_daily_flows=tuple(
                self._broker_repo.get_broker_daily_flows(
                    ticker, start_date=start_date, end_date=snapshot_date
                )
            ),
            foreign_flow_points=tuple(
                self._broker_repo.get_foreign_flow_points(
                    ticker, start_date=start_date, end_date=snapshot_date
                )
            ),
            broker_summaries=tuple(
                self._broker_repo.get_broker_summaries(
                    ticker, start_date=start_date, end_date=snapshot_date
                )
            ),
        )

    def load_ticker_profile_inputs(
        self,
        *,
        ticker: str,
        snapshot_date: date,
        candles: tuple | list | None = None,
    ) -> TickerProfileEvidenceInputs:
        start_date = snapshot_date - timedelta(days=_FLOW_WINDOW_DAYS)
        resolved_candles = (
            tuple(candles)
            if candles is not None
            else tuple(self._market_repo.get_candles(ticker, end_date=snapshot_date))
        )
        return TickerProfileEvidenceInputs(
            candles=resolved_candles,
            broker_daily_flows=tuple(
                self._broker_repo.get_broker_daily_flows(
                    ticker, start_date=start_date, end_date=snapshot_date
                )
            ),
            broker_summaries=tuple(
                self._broker_repo.get_broker_summaries(
                    ticker, start_date=start_date, end_date=snapshot_date
                )
            ),
        )

    def load_sector_context_inputs(
        self,
        *,
        ticker: str,
        snapshot_date: date,
        sector: str | None,
        peer_tickers: tuple[str, ...] | list[str],
        benchmark: str,
        ticker_candles: tuple | list | None = None,
    ) -> SectorContextInputs:
        resolved_ticker_candles = (
            tuple(ticker_candles)
            if ticker_candles is not None
            else tuple(self._market_repo.get_candles(ticker, end_date=snapshot_date))
        )
        peer_candles: dict[str, list] = {}
        for peer in peer_tickers:
            try:
                pc = self._market_repo.get_candles(peer, end_date=snapshot_date)
                if pc:
                    peer_candles[peer] = list(pc)
            except Exception:
                pass
        ihsg_20d_return = benchmark_return_from_repository(
            self._market_repo,
            benchmark=benchmark,
            end_date=snapshot_date,
            lookback=20,
            min_valid=18,
        )
        return SectorContextInputs(
            ticker_candles=resolved_ticker_candles,
            peer_candles=peer_candles,
            ihsg_20d_return=ihsg_20d_return,
        )

    def load_sector_macro_context_inputs(
        self,
        *,
        series_tickers: tuple[str, ...] | list[str],
        snapshot_date: date,
        policy_series: tuple[str, ...] | list[str] = (),
        policy_lookback_days: int = 180,
        as_of_fetched_at: str | None = None,
    ) -> SectorMacroContextInputs:
        """Load macro series candles + optional BI policy steps (PIT-safe)."""
        series_candles: dict[str, tuple] = {}
        for series in series_tickers:
            key = str(series).upper().strip()
            if not key:
                continue
            try:
                candles = self._market_repo.get_candles(key, end_date=snapshot_date)
                series_candles[key] = tuple(candles) if candles else ()
            except Exception:
                series_candles[key] = ()

        policy_steps: dict[str, tuple] = {}
        if policy_series and self._macro_calendar_repo is not None:
            from src.application.services.policy_rate_steps import (
                BI_RATE_SERIES_KEY,
                macro_events_to_policy_steps,
            )
            from src.domain.value_objects.macro_calendar_event import MacroEventCategory

            from_date = snapshot_date - timedelta(days=max(1, int(policy_lookback_days)))
            try:
                events = self._macro_calendar_repo.get_events_in_window(
                    from_date=from_date,
                    to_date=snapshot_date,
                    categories=(MacroEventCategory.BI_RATE,),
                    as_of_fetched_at=as_of_fetched_at,
                )
                steps = macro_events_to_policy_steps(events)
            except Exception:
                steps = ()
            for series in policy_series:
                key = str(series).upper().strip()
                if key == BI_RATE_SERIES_KEY:
                    policy_steps[key] = steps
                else:
                    policy_steps[key] = ()
        elif policy_series:
            for series in policy_series:
                key = str(series).upper().strip()
                if key:
                    policy_steps[key] = ()

        return SectorMacroContextInputs(
            series_candles=series_candles,
            policy_steps=policy_steps or None,
        )
