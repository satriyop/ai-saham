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
    from src.domain.entities.broker_flow import (
        BrokerDailyFlow,
        BrokerSummary,
        ForeignFlowPoint,
    )
    from src.domain.entities.candle import Candle
    from src.domain.ports.broker_data_repository import BrokerDataRepository
    from src.domain.ports.market_data_repository import MarketDataRepository

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
    """Preloaded macro series candles keyed by series ticker (e.g. MTF=F)."""

    series_candles: dict[str, tuple["Candle", ...]]


class CandidateEvidenceDataLoader:
    """Loads point-in-time repository data shared across evidence assemblers."""

    def __init__(
        self,
        market_repository: "MarketDataRepository",
        broker_repository: "BrokerDataRepository",
    ) -> None:
        self._market_repo = market_repository
        self._broker_repo = broker_repository

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
    ) -> SectorMacroContextInputs:
        """Load macro series candles bounded by snapshot_date (PIT-safe)."""
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
        return SectorMacroContextInputs(series_candles=series_candles)
