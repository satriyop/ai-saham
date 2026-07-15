"""
Daily briefing use case for the CLI `today` command.

Layer: Application
AI usage: None
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from src.application.dto.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenRequest,
)
from src.application.ports.universe_config_loader import UniverseConfigLoader
from src.application.services.data_freshness_service import compute_data_freshness
from src.application.services.universe_loader import load_universe
from src.application.use_case.accumulation_screen_use_case import AccumulationScreenUseCase
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.value_objects.data_freshness_status import (
    DataFreshnessStatus,
    SourceFreshnessState,
)

if TYPE_CHECKING:
    from src.domain.value_objects.market_context import MarketContext
from src.domain.ports.market_data_repository import MarketDataRepository


@dataclass(frozen=True)
class BriefingDataFreshnessItem:
    ticker: str
    freshness: DataFreshnessStatus


@dataclass(frozen=True)
class OpeningBriefingCandidate:
    ticker: str
    opening_setup: str
    iev: int | None = None
    iep: int | None = None
    trend: str | None = None
    foreign_flow_score: float | None = None


@dataclass(frozen=True)
class OpeningBriefingSnapshot:
    candidates: list[OpeningBriefingCandidate]
    snapshot_date: date | None


@dataclass(frozen=True)
class DailyBriefingRequest:
    universe: str = "lq45"
    top: int = 3
    as_of_date: date | None = None
    opening_data_dir: Path = Path("data/opening")
    universe_config_path: Path = Path("config/universes.yaml")


@dataclass(frozen=True)
class DailyBriefingResponse:
    live_session_date: date
    latest_completed_eod_date: date | None
    opening_snapshot_date: date | None
    is_historical: bool
    universe: str
    universe_count: int
    data_freshness: list[BriefingDataFreshnessItem]
    stale_count: int
    regime: "MarketContext | None" = None
    opening_candidates: list[OpeningBriefingCandidate] = field(default_factory=list)
    accumulation_candidates: list[AccumulationCandidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class DailyBriefingUseCase:
    """Build a deterministic, read-only start-of-day summary from local data."""

    def __init__(
        self,
        market_repository: MarketDataRepository,
        broker_repository: BrokerDataRepository,
        regime_use_case,
        accumulation_use_case: AccumulationScreenUseCase,
        universe_loader: UniverseConfigLoader,
    ) -> None:
        self._market_repo = market_repository
        self._broker_repo = broker_repository
        self._regime_uc = regime_use_case
        self._accumulation_uc = accumulation_use_case
        self._universe_loader = universe_loader

    def execute(self, request: DailyBriefingRequest) -> DailyBriefingResponse:
        from datetime import timedelta
        is_historical = request.as_of_date is not None
        live_session_date = request.as_of_date or date.today()

        # Roll back to the most recent trading session if it's a weekend and date was defaulted
        if not is_historical:
            while live_session_date.weekday() >= 5:
                live_session_date -= timedelta(days=1)

        warnings: list[str] = []

        try:
            universe_tickers = load_universe(
                request.universe,
                self._universe_loader,
                request.universe_config_path,
            )
        except Exception as exc:
            universe_tickers = []
            warnings.append(f"Universe unavailable: {exc}")

        freshness = self._data_freshness(universe_tickers, live_session_date)

        stale_count = sum(
            1
            for item in freshness
            if item.freshness.candle_state
            in {
                SourceFreshnessState.STALE,
                SourceFreshnessState.MISSING,
                SourceFreshnessState.UNKNOWN,
            }
        )

        if stale_count > 0:
            warnings.append(
                f"Local cache is stale for {stale_count}/{len(universe_tickers)} tickers. "
                f"Run 'saham fetch market --universe {request.universe}' to fetch latest data."
            )

        if freshness:
            latest_completed_eod_date = freshness[0].freshness.expected_latest_eod
        else:
            synthetic = compute_data_freshness(
                candle_as_of=None,
                broker_as_of=None,
                screen_date=live_session_date,
            )
            latest_completed_eod_date = synthetic.expected_latest_eod

        regime = None
        accumulation_candidates: list[AccumulationCandidate] = []

        if latest_completed_eod_date is None:
            warnings.append(
                "Latest completed EOD date is unavailable. "
                "Skipping market regime and accumulation screen."
            )
        else:
            if universe_tickers:
                try:
                    regime = self._regime_uc.evaluate(as_of_date=latest_completed_eod_date)
                except Exception as exc:
                    warnings.append(f"Regime unavailable: {exc}")

                try:
                    response = self._accumulation_uc.execute(
                        AccumulationScreenRequest(
                            tickers=universe_tickers,
                            window_days=7,
                            as_of_date=latest_completed_eod_date,
                        )
                    )
                    accumulation_candidates = response.candidates[: request.top]
                except Exception as exc:
                    warnings.append(f"Accumulation screen unavailable: {exc}")

        snapshot = self._opening_snapshot(request, live_session_date, warnings)
        opening_candidates = snapshot.candidates
        opening_snapshot_date = snapshot.snapshot_date

        return DailyBriefingResponse(
            live_session_date=live_session_date,
            latest_completed_eod_date=latest_completed_eod_date,
            opening_snapshot_date=opening_snapshot_date,
            is_historical=is_historical,
            universe=request.universe,
            universe_count=len(universe_tickers),
            data_freshness=freshness,
            stale_count=stale_count,
            regime=regime,
            opening_candidates=opening_candidates,
            accumulation_candidates=accumulation_candidates,
            warnings=warnings,
        )

    def _data_freshness(
        self,
        tickers: list[str],
        live_session_date: date,
    ) -> list[BriefingDataFreshnessItem]:
        items: list[BriefingDataFreshnessItem] = []
        for ticker in tickers:
            try:
                market_range = self._market_repo.get_date_range(ticker)
                candle_as_of = market_range[1] if market_range else None
            except Exception:
                candle_as_of = None

            try:
                broker_range = self._broker_repo.get_date_range(ticker)
                broker_as_of = broker_range[1] if broker_range else None
            except Exception:
                broker_as_of = None

            freshness_status = compute_data_freshness(
                candle_as_of=candle_as_of,
                broker_as_of=broker_as_of,
                screen_date=live_session_date,
            )
            items.append(
                BriefingDataFreshnessItem(
                    ticker=ticker,
                    freshness=freshness_status,
                )
            )
        return items

    def _opening_snapshot(
        self,
        request: DailyBriefingRequest,
        live_session_date: date,
        warnings: list[str],
    ) -> OpeningBriefingSnapshot:
        path = request.opening_data_dir / live_session_date.strftime("%Y%m%d") / "snapshot.json"
        if not path.exists():
            warnings.append(f"No opening snapshot at {path}")
            return OpeningBriefingSnapshot(candidates=[], snapshot_date=None)

        try:
            data = json.loads(path.read_text())
        except Exception as exc:
            warnings.append(f"Opening snapshot unreadable: {exc}")
            return OpeningBriefingSnapshot(candidates=[], snapshot_date=None)

        snapshot_date = None
        if "captured_at" not in data:
            snapshot_date = live_session_date
        else:
            captured_at = data["captured_at"]
            if captured_at is None:
                snapshot_date = live_session_date
            else:
                try:
                    captured_date = datetime.fromisoformat(str(captured_at)).date()
                    snapshot_date = captured_date
                    if captured_date != live_session_date:
                        warnings.append(
                            f"Opening snapshot capture date is {captured_date.isoformat()}"
                        )
                except ValueError:
                    warnings.append("Opening snapshot capture timestamp is invalid")
                    snapshot_date = None

        candidates = [
            OpeningBriefingCandidate(
                ticker=str(row.get("ticker", "")).upper(),
                opening_setup=str(row.get("opening_setup", "?")),
                iev=row.get("iev"),
                iep=row.get("iep"),
                trend=row.get("trend"),
                foreign_flow_score=row.get("foreign_flow_score", row.get("accum_score")),
            )
            for row in data.get("candidates", [])
            if row.get("ticker")
        ]
        return OpeningBriefingSnapshot(
            candidates=candidates[: request.top],
            snapshot_date=snapshot_date,
        )
