"""
Daily briefing use case for the CLI `today` command.

Layer: Application
AI usage: None
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from src.application.services.universe_loader import load_universe
from src.application.dto.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenRequest,
)
from src.application.use_case.accumulation_screen_use_case import AccumulationScreenUseCase
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.value_objects.market_context import MarketContext
from src.domain.ports.market_data_repository import MarketDataRepository


@dataclass(frozen=True)
class DataFreshnessItem:
    ticker: str
    first_date: date | None
    latest_date: date | None


@dataclass(frozen=True)
class OpeningBriefingCandidate:
    ticker: str
    opening_setup: str
    iev: int | None = None
    iep: int | None = None
    trend: str | None = None
    foreign_flow_score: float | None = None


@dataclass(frozen=True)
class DailyBriefingRequest:
    universe: str = "lq45"
    top: int = 3
    as_of_date: date | None = None
    opening_data_dir: Path = Path("data/opening")
    universe_config_path: Path = Path("config/universes.yaml")


@dataclass(frozen=True)
class DailyBriefingResponse:
    as_of_date: date
    universe: str
    universe_count: int
    data_freshness: list[DataFreshnessItem]
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
        regime_use_case,
        accumulation_use_case: AccumulationScreenUseCase,
    ) -> None:
        self._market_repo = market_repository
        self._regime_uc = regime_use_case
        self._accumulation_uc = accumulation_use_case

    def execute(self, request: DailyBriefingRequest) -> DailyBriefingResponse:
        from datetime import timedelta
        as_of = request.as_of_date or date.today()
        # Roll back to the most recent trading session if it's a weekend and date was defaulted
        if request.as_of_date is None:
            while as_of.weekday() >= 5:
                as_of -= timedelta(days=1)
        warnings: list[str] = []

        try:
            universe_tickers = load_universe(request.universe, request.universe_config_path)
        except Exception as exc:
            universe_tickers = []
            warnings.append(f"Universe unavailable: {exc}")

        freshness = self._data_freshness(universe_tickers, as_of)
        stale_count = sum(1 for item in freshness if item.latest_date != as_of)

        if stale_count > 0:
            warnings.append(
                f"Local cache is stale for {stale_count}/{len(universe_tickers)} tickers. "
                f"Run 'saham fetch market --universe {request.universe}' to fetch latest data."
            )

        regime = None
        if universe_tickers:
            try:
                regime = self._regime_uc.evaluate(as_of_date=as_of)
            except Exception as exc:
                warnings.append(f"Regime unavailable: {exc}")

        opening_candidates = self._opening_candidates(request, as_of, warnings)
        accumulation_candidates: list[AccumulationCandidate] = []
        if universe_tickers:
            try:
                response = self._accumulation_uc.execute(
                    AccumulationScreenRequest(
                        tickers=universe_tickers,
                        window_days=7,
                        as_of_date=as_of,
                    )
                )
                accumulation_candidates = response.candidates[: request.top]
            except Exception as exc:
                warnings.append(f"Accumulation screen unavailable: {exc}")

        return DailyBriefingResponse(
            as_of_date=as_of,
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
        as_of: date,
    ) -> list[DataFreshnessItem]:
        items: list[DataFreshnessItem] = []
        for ticker in tickers:
            try:
                date_range = self._market_repo.get_date_range(ticker)
            except Exception:
                date_range = None
            if date_range is None:
                items.append(DataFreshnessItem(ticker=ticker, first_date=None, latest_date=None))
            else:
                items.append(
                    DataFreshnessItem(
                        ticker=ticker,
                        first_date=date_range[0],
                        latest_date=date_range[1],
                    )
                )
        return items

    def _opening_candidates(
        self,
        request: DailyBriefingRequest,
        as_of: date,
        warnings: list[str],
    ) -> list[OpeningBriefingCandidate]:
        path = request.opening_data_dir / as_of.strftime("%Y%m%d") / "snapshot.json"
        if not path.exists():
            warnings.append(f"No opening snapshot at {path}")
            return []

        try:
            data = json.loads(path.read_text())
        except Exception as exc:
            warnings.append(f"Opening snapshot unreadable: {exc}")
            return []

        captured_at = data.get("captured_at")
        if captured_at:
            try:
                captured_date = datetime.fromisoformat(captured_at).date()
                if captured_date != as_of:
                    warnings.append(f"Opening snapshot capture date is {captured_date.isoformat()}")
            except ValueError:
                warnings.append("Opening snapshot capture timestamp is invalid")

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
        return candidates[: request.top]
