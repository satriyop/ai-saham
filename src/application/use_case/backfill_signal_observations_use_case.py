"""Backfill historical signal observations using the live accumulation pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from src.application.services.signal_observation_request_builder import (
    BuildSignalObservationScreenRequest,
)
from src.application.use_case.accumulation_screen_use_case import AccumulationScreenUseCase
from src.application.use_case.generate_signal_forward_labels_use_case import (
    GenerateAllSignalForwardLabelsRequest,
    GenerateSignalForwardLabelsUseCase,
)
from src.domain.ports.candidate_observations_repository import (
    CandidateObservationsRepository,
)
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.signal_forward_label import SignalLabelHorizon


@dataclass(frozen=True)
class BackfillSkippedDate:
    date: date
    reason: str

    def to_dict(self) -> dict:
        return {"date": self.date.isoformat(), "reason": self.reason}


@dataclass(frozen=True)
class BackfillSignalObservationsRequest:
    tickers: tuple[str, ...]
    start_date: date
    end_date: date
    horizon: SignalLabelHorizon = SignalLabelHorizon.SWING_10D
    generate_labels: bool = False
    windows: tuple[int, ...] = (7, 30, 90)


@dataclass(frozen=True)
class BackfillSignalObservationsResponse:
    requested_date_count: int
    processed_date_count: int
    skipped_date_count: int
    saved_observation_count: int
    generated_label_count: int
    unavailable_label_count: int
    processed_dates: tuple[date, ...] = field(default_factory=tuple)
    skipped_dates: tuple[BackfillSkippedDate, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "requested_date_count": self.requested_date_count,
            "processed_date_count": self.processed_date_count,
            "skipped_date_count": self.skipped_date_count,
            "saved_observation_count": self.saved_observation_count,
            "generated_label_count": self.generated_label_count,
            "unavailable_label_count": self.unavailable_label_count,
            "processed_dates": [day.isoformat() for day in self.processed_dates],
            "skipped_dates": [entry.to_dict() for entry in self.skipped_dates],
            "notes": list(self.notes),
        }


class BackfillSignalObservationsUseCase:
    """Create historical candidate observations before optional label generation."""

    def __init__(
        self,
        *,
        accumulation_screen_use_case: AccumulationScreenUseCase,
        screen_request_builder: BuildSignalObservationScreenRequest,
        market_data_repository: MarketDataRepository,
        candidate_observations_repository: CandidateObservationsRepository,
        label_generation_use_case: GenerateSignalForwardLabelsUseCase | None = None,
    ) -> None:
        self._screen = accumulation_screen_use_case
        self._request_builder = screen_request_builder
        self._market = market_data_repository
        self._observations = candidate_observations_repository
        self._labels = label_generation_use_case

    def execute(
        self,
        request: BackfillSignalObservationsRequest,
    ) -> BackfillSignalObservationsResponse:
        if request.end_date < request.start_date:
            raise ValueError("end_date must be on or after start_date")
        if not request.tickers:
            raise ValueError("at least one ticker is required")

        tickers = tuple(ticker.upper() for ticker in request.tickers)
        trading_dates = tuple(
            _dates_from_candles(
                self._market.get_candles(
                    "IHSG",
                    start_date=request.start_date,
                    end_date=request.end_date,
                )
            )
        )
        if not trading_dates:
            trading_dates = tuple(
                _dates_from_candles(
                    self._market.get_candles(
                        tickers[0],
                        start_date=request.start_date,
                        end_date=request.end_date,
                    )
                )
            )

        processed: list[date] = []
        skipped: list[BackfillSkippedDate] = []
        saved_count = 0
        generated_label_count = 0
        unavailable_label_count = 0

        for trading_date in trading_dates:
            if not self._has_any_ticker_candle(tickers, trading_date):
                skipped.append(
                    BackfillSkippedDate(
                        date=trading_date,
                        reason="missing_source_candles_for_universe",
                    )
                )
                continue

            before_count = len(self._observations.list_all_by_date(trading_date))
            for window in request.windows:
                self._screen.execute(
                    self._request_builder.build(
                        tickers=list(tickers),
                        window_days=int(window),
                        as_of_date=trading_date,
                    )
                )
            after_count = len(self._observations.list_all_by_date(trading_date))
            saved_count += max(0, after_count - before_count)
            processed.append(trading_date)

            if request.generate_labels:
                if self._labels is None:
                    skipped.append(
                        BackfillSkippedDate(
                            date=trading_date,
                            reason="label_generation_use_case_unavailable",
                        )
                    )
                    continue
                if not self._observations.list_by_date(trading_date):
                    skipped.append(
                        BackfillSkippedDate(
                            date=trading_date,
                            reason="no_saved_observations_for_label_generation",
                        )
                    )
                    continue
                if not self._has_complete_forward_window(
                    trading_date,
                    request.horizon,
                ):
                    skipped.append(
                        BackfillSkippedDate(
                            date=trading_date,
                            reason=(
                                "insufficient_future_candles_for_"
                                f"{request.horizon.value}"
                            ),
                        )
                    )
                    continue
                label_response = self._labels.execute_all(
                    GenerateAllSignalForwardLabelsRequest(
                        signal_date=trading_date,
                        horizons=(request.horizon,),
                    )
                )
                generated_label_count += label_response.generated_count
                unavailable_label_count += label_response.unavailable_count

        return BackfillSignalObservationsResponse(
            requested_date_count=len(trading_dates),
            processed_date_count=len(processed),
            skipped_date_count=len(skipped),
            saved_observation_count=saved_count,
            generated_label_count=generated_label_count,
            unavailable_label_count=unavailable_label_count,
            processed_dates=tuple(processed),
            skipped_dates=tuple(skipped),
            notes=(
                "candidate_observations are timestamped; reruns may append raw "
                "rows while readiness uses latest per ticker to avoid duplicate "
                "ticker/day labels.",
            ),
        )

    def _has_any_ticker_candle(self, tickers: tuple[str, ...], target_date: date) -> bool:
        return any(
            any(
                candle.date == target_date
                for candle in self._market.get_candles(
                    ticker,
                    start_date=target_date,
                    end_date=target_date,
                )
            )
            for ticker in tickers
        )

    def _has_complete_forward_window(
        self,
        signal_date: date,
        horizon: SignalLabelHorizon,
    ) -> bool:
        required = horizon.trading_days
        observations = self._observations.list_by_date(signal_date)
        for observation in observations:
            candles = self._market.get_candles(
                observation.ticker,
                start_date=signal_date,
            )
            forward = [candle for candle in candles if candle.date > signal_date]
            if len(forward) >= required:
                return True
        return False


def _dates_from_candles(candles) -> list[date]:
    return sorted({candle.date for candle in candles})
