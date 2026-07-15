"""
Daily briefing use case for the CLI `today` command.

Layer: Application
AI usage: None
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from src.application.dto.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenRequest,
)
from src.application.ports.universe_config_loader import UniverseConfigLoader
from src.application.services.data_freshness_service import compute_data_freshness
from src.application.services.universe_loader import load_universe
from src.application.use_case.accumulation_screen_use_case import AccumulationScreenUseCase
from src.application.use_case.daily_accumulation_projection import (
    DailyAccumulationCandidate,
    DailyAccumulationProjector,
    DailyAccumulationSummary,
)
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.data_freshness_status import (
    DataFreshnessStatus,
    SourceFreshnessState,
)

if TYPE_CHECKING:
    from src.domain.value_objects.market_context import MarketContext

ReadinessStatus = Literal["READY", "PARTIAL", "NOT_READY", "UNAVAILABLE"]
OverallAuthority = Literal["READY", "PARTIAL", "NOT_READY"]

@dataclass(frozen=True)
class DataReadiness:
    dataset: str
    required_as_of: date | None
    coverage_count: int
    total_count: int
    status: ReadinessStatus
    reason: str | None = None

MIN_READY_COVERAGE_RATIO = 0.80


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
    market_wide_observations: list[OpeningBriefingCandidate]
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
    readiness_items: list[DataReadiness]
    overall_authority: OverallAuthority
    regime: "MarketContext | None" = None
    opening_candidates: list[OpeningBriefingCandidate] = field(default_factory=list)
    market_wide_opening_observations: list[OpeningBriefingCandidate] = field(default_factory=list)
    accumulation_candidates: list[AccumulationCandidate] = field(default_factory=list)
    accumulation_summary: DailyAccumulationSummary | None = None
    daily_accumulation_candidates: list[DailyAccumulationCandidate] = field(
        default_factory=list
    )
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
        if latest_completed_eod_date is not None and universe_tickers:
            try:
                regime = self._regime_uc.evaluate(as_of_date=latest_completed_eod_date)
            except Exception as exc:
                warnings.append(f"Regime unavailable: {exc}")

        snapshot = self._opening_snapshot(
            request=request,
            live_session_date=live_session_date,
            universe_tickers=universe_tickers,
            warnings=warnings,
        )
        opening_candidates = snapshot.candidates
        market_wide_opening_observations = snapshot.market_wide_observations
        opening_snapshot_date = snapshot.snapshot_date

        regime_available = regime is not None
        readiness_items = self._readiness_items(
            freshness=freshness,
            latest_completed_eod_date=latest_completed_eod_date,
            regime_available=regime_available,
            opening_snapshot_date=opening_snapshot_date,
            live_session_date=live_session_date,
        )
        overall_authority = self._overall_authority(readiness_items)

        candle_coverage_count = next(
            (item.coverage_count for item in readiness_items if item.dataset == "candles"),
            None,
        )
        data_ready = (
            candle_coverage_count
            if candle_coverage_count is not None
            else len(universe_tickers) - stale_count
        )

        accumulation_candidates: list[AccumulationCandidate] = []
        if overall_authority == "NOT_READY":
            warnings.append("Accumulation screen suppressed because data readiness is NOT_READY.")
            accumulation_summary = DailyAccumulationSummary(
                checked=len(universe_tickers),
                data_ready=data_ready,
                flow_candidates=0,
                enter_count=0,
                watch_count=0,
                blocked_count=0,
                unclassified_count=0,
            )
            daily_accumulation_candidates: list[DailyAccumulationCandidate] = []
        else:
            if overall_authority == "PARTIAL":
                warnings.append("Accumulation screen is shown with PARTIAL data readiness.")

            if latest_completed_eod_date is None:
                warnings.append(
                    "Latest completed EOD date is unavailable. "
                    "Skipping market regime and accumulation screen."
                )
            else:
                if universe_tickers:
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

            projection = DailyAccumulationProjector().project(
                candidates=accumulation_candidates,
                checked=len(universe_tickers),
                data_ready=data_ready,
            )
            accumulation_summary = projection.summary
            daily_accumulation_candidates = projection.candidates
            warnings.extend(projection.warnings)

        return DailyBriefingResponse(
            live_session_date=live_session_date,
            latest_completed_eod_date=latest_completed_eod_date,
            opening_snapshot_date=opening_snapshot_date,
            is_historical=is_historical,
            universe=request.universe,
            universe_count=len(universe_tickers),
            data_freshness=freshness,
            stale_count=stale_count,
            readiness_items=readiness_items,
            overall_authority=overall_authority,
            regime=regime,
            opening_candidates=opening_candidates,
            market_wide_opening_observations=market_wide_opening_observations,
            accumulation_candidates=accumulation_candidates,
            accumulation_summary=accumulation_summary,
            daily_accumulation_candidates=daily_accumulation_candidates,
            warnings=warnings,
        )

    def _readiness_items(
        self,
        *,
        freshness: list[BriefingDataFreshnessItem],
        latest_completed_eod_date: date | None,
        regime_available: bool,
        opening_snapshot_date: date | None,
        live_session_date: date,
    ) -> list[DataReadiness]:
        items: list[DataReadiness] = []

        # A. candles
        candle_total = len(freshness)
        candle_coverage = sum(
            1
            for item in freshness
            if item.freshness.candle_state in {
                SourceFreshnessState.READY,
                SourceFreshnessState.PENDING_EOD,
            }
        )
        candle_status = self._derive_status(candle_coverage, candle_total)
        candle_reason = None
        if candle_status == "UNAVAILABLE":
            candle_reason = "No universe tickers resolved"
        elif candle_status in ("NOT_READY", "PARTIAL"):
            candle_reason = (
                f"Only {candle_coverage}/{candle_total} "
                "tickers have current candle data"
            )

        items.append(
            DataReadiness(
                dataset="candles",
                required_as_of=latest_completed_eod_date,
                coverage_count=candle_coverage,
                total_count=candle_total,
                status=candle_status,
                reason=candle_reason,
            )
        )

        # B. broker_flow
        broker_total = len(freshness)
        broker_coverage = sum(
            1
            for item in freshness
            if item.freshness.broker_state in {
                SourceFreshnessState.READY,
                SourceFreshnessState.PENDING_EOD,
            }
        )
        broker_status = self._derive_status(broker_coverage, broker_total)
        broker_reason = None
        if broker_status == "UNAVAILABLE":
            broker_reason = "No universe tickers resolved"
        elif broker_status in ("NOT_READY", "PARTIAL"):
            broker_reason = (
                f"Only {broker_coverage}/{broker_total} "
                "tickers have current broker data"
            )

        items.append(
            DataReadiness(
                dataset="broker_flow",
                required_as_of=latest_completed_eod_date,
                coverage_count=broker_coverage,
                total_count=broker_total,
                status=broker_status,
                reason=broker_reason,
            )
        )

        # C. market_context
        market_coverage = 1 if regime_available else 0
        market_total = 1
        market_status = "READY" if regime_available else "UNAVAILABLE"
        market_reason = None if regime_available else "Market context unavailable"
        items.append(
            DataReadiness(
                dataset="market_context",
                required_as_of=latest_completed_eod_date,
                coverage_count=market_coverage,
                total_count=market_total,
                status=market_status,
                reason=market_reason,
            )
        )

        # D. opening_snapshot
        opening_coverage = 1 if opening_snapshot_date is not None else 0
        opening_total = 1
        opening_status = "READY" if opening_snapshot_date is not None else "UNAVAILABLE"
        opening_reason = (
            None if opening_snapshot_date is not None
            else "Opening snapshot unavailable"
        )
        items.append(
            DataReadiness(
                dataset="opening_snapshot",
                required_as_of=live_session_date,
                coverage_count=opening_coverage,
                total_count=opening_total,
                status=opening_status,
                reason=opening_reason,
            )
        )

        return items

    def _derive_status(self, coverage: int, total: int) -> ReadinessStatus:
        if total == 0:
            return "UNAVAILABLE"
        if coverage == total:
            return "READY"
        ratio = coverage / total
        if ratio >= MIN_READY_COVERAGE_RATIO:
            return "PARTIAL"
        return "NOT_READY"

    def _overall_authority(self, readiness_items: list[DataReadiness]) -> OverallAuthority:
        candles_status = "UNAVAILABLE"
        broker_status = "UNAVAILABLE"
        for item in readiness_items:
            if item.dataset == "candles":
                candles_status = item.status
            elif item.dataset == "broker_flow":
                broker_status = item.status

        critical_statuses = [candles_status, broker_status]
        all_statuses = [item.status for item in readiness_items]

        if "NOT_READY" in critical_statuses or "UNAVAILABLE" in critical_statuses:
            return "NOT_READY"
        elif "PARTIAL" in all_statuses or "UNAVAILABLE" in all_statuses:
            return "PARTIAL"
        else:
            return "READY"


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
        universe_tickers: list[str],
        warnings: list[str],
    ) -> OpeningBriefingSnapshot:
        path = request.opening_data_dir / live_session_date.strftime("%Y%m%d") / "snapshot.json"
        if not path.exists():
            warnings.append(f"No opening snapshot at {path}")
            return OpeningBriefingSnapshot(
                candidates=[],
                market_wide_observations=[],
                snapshot_date=None,
            )

        try:
            data = json.loads(path.read_text())
        except Exception as exc:
            warnings.append(f"Opening snapshot unreadable: {exc}")
            return OpeningBriefingSnapshot(
                candidates=[],
                market_wide_observations=[],
                snapshot_date=None,
            )

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

        universe_set = {ticker.upper() for ticker in universe_tickers}
        candidates = []
        market_wide_observations = []

        for row in data.get("candidates", []):
            ticker = row.get("ticker")
            if not ticker:
                continue
            ticker_upper = str(ticker).upper()
            candidate = OpeningBriefingCandidate(
                ticker=ticker_upper,
                opening_setup=str(row.get("opening_setup", "?")),
                iev=row.get("iev"),
                iep=row.get("iep"),
                trend=row.get("trend"),
                foreign_flow_score=row.get("foreign_flow_score", row.get("accum_score")),
            )
            if ticker_upper in universe_set:
                candidates.append(candidate)
            else:
                market_wide_observations.append(candidate)

        return OpeningBriefingSnapshot(
            candidates=candidates[: request.top],
            market_wide_observations=market_wide_observations[: request.top],
            snapshot_date=snapshot_date,
        )
