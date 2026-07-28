"""
Daily briefing use case for the CLI `today` command.

Layer: Application
AI usage: None
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from src.application.dto.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenRequest,
)
from src.application.dto.signal_evidence_execution_context import (
    SignalEvidenceExecutionContext,
)
from src.application.ports.universe_config_loader import UniverseConfigLoader
from src.application.services.data_freshness_service import compute_data_freshness
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
    EffectiveMarketSessionResolver,
)
from src.application.services.universe_loader import load_universe
from src.application.use_case.accumulation_screen_use_case import AccumulationScreenUseCase
from src.application.use_case.daily_accumulation_projection import (
    DailyAccumulationCandidate,
    DailyAccumulationProjector,
    DailyAccumulationSummary,
)
from src.application.use_case.daily_setup_lens_impact_use_case import (
    DailySetupLensImpactCandidate,
    DailySetupLensImpactRequest,
    DailySetupLensImpactResult,
    DailySetupLensImpactUseCase,
)
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.learning_artifact_repositories import (
    LearningObservationRepository,
)
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.data_freshness_status import (
    DataFreshnessStatus,
    SourceFreshnessState,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE, MARKET_CLOSE
from src.domain.value_objects.learning_artifacts import AssessmentPurpose

if TYPE_CHECKING:
    from src.application.ports.corporate_action_calendar_repository import (
        CorporateActionCalendarRepository,
    )
    from src.application.ports.iev_snapshot_repository import IEVBaselineReadPort
    from src.domain.value_objects.market_context import MarketContext

ReadinessStatus = Literal["READY", "PARTIAL", "NOT_READY", "UNAVAILABLE"]
OverallAuthority = Literal["READY", "PARTIAL", "NOT_READY"]


def _opt_str(value: object) -> str | None:
    """Normalize a corpus value (often a serialized Decimal) to str, preserving None."""
    return None if value is None else str(value)


# Forward window for the daily-briefing corporate-action calendar section.
CORP_ACTION_LOOKAHEAD_DAYS = 14


@dataclass(frozen=True)
class CorpActionBriefingRow:
    """Flattened corporate-action milestone for the daily-briefing calendar."""

    ticker: str
    event_type: str
    date_role: str
    event_date: date
    note: str | None = None


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
    accum_score: float | None = None
    # ── Pre-open decision context surfaced from the capture corpus ──
    prev_close: str | None = None
    iep_gap_pct: str | None = None
    iev_intensity: float | None = None
    bid_offer_imbalance: float | None = None
    broker_backing_score: float | None = None
    broker_backing_tag: str | None = None
    trend_signal: str | None = None
    entry_price: str | None = None
    stop_loss_price: str | None = None
    signal_score: int | None = None
    signal_strength: str | None = None
    blocking_gates: tuple[str, ...] = ()
    rationale: str | None = None
    # ── Locked-input signal (decision_iev - 08:56 NCP baseline) ──
    ncp_baseline_iev: int | None = None
    delta_iev: int | None = None


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
    daily_accumulation_candidates: list[DailyAccumulationCandidate] = field(default_factory=list)
    setup_lens_impact: DailySetupLensImpactResult | None = None
    upcoming_corp_actions: list[CorpActionBriefingRow] = field(default_factory=list)
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
        learning_observation_repository: LearningObservationRepository | None = None,
        setup_lens_impact_use_case: DailySetupLensImpactUseCase | None = None,
        session_resolver: EffectiveMarketSessionResolver | None = None,
        iev_baseline_repository: "IEVBaselineReadPort | None" = None,
        corp_action_repository: "CorporateActionCalendarRepository | None" = None,
    ) -> None:
        self._market_repo = market_repository
        self._broker_repo = broker_repository
        self._regime_uc = regime_use_case
        self._accumulation_uc = accumulation_use_case
        self._universe_loader = universe_loader
        self._learning_observation_repository = learning_observation_repository
        self._setup_lens_impact_uc = setup_lens_impact_use_case
        self._iev_baseline_repo = iev_baseline_repository
        self._corp_action_repo = corp_action_repository
        self._session_resolver = session_resolver or EffectiveMarketSessionResolver(
            market_repository
        )

    def execute(self, request: DailyBriefingRequest) -> DailyBriefingResponse:
        is_historical = request.as_of_date is not None

        if is_historical:
            # Deterministic historical decision timestamp: after-market-close
            # WIB on the requested date, so a historical daily briefing always
            # treats that date as a completed end-of-day decision rather than
            # an intraday/pre-close one.
            as_of_date = request.as_of_date
            decision_at = datetime.combine(as_of_date, MARKET_CLOSE, tzinfo=IDX_TIMEZONE)
            effective_session = self._session_resolver.resolve(run_at=decision_at)
            live_session_date = as_of_date
        else:
            # Real WIB current time-of-day (not midnight) so the resolver can
            # classify pre-open/regular/pre-closing/after-close correctly;
            # the date itself is taken from `date.today()` so this stays
            # consistent with the rest of this method's mockable time source.
            today = date.today()
            now_wib = datetime.now(IDX_TIMEZONE)
            run_at = datetime.combine(today, now_wib.time(), tzinfo=IDX_TIMEZONE)
            effective_session = self._session_resolver.resolve(run_at=run_at)
            live_session_date = today
            # On a weekend, roll back to the latest IDX session the resolver
            # can prove (cached IHSG session when available, weekday fallback
            # otherwise) rather than blindly assuming the prior Friday.
            if effective_session.market_session_name == "WEEKEND":
                live_session_date = effective_session.latest_completed_session or live_session_date

        warnings: list[str] = []

        universe_tickers = load_universe(
            request.universe,
            self._universe_loader,
            request.universe_config_path,
        )

        freshness = self._data_freshness(universe_tickers, effective_session)

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

        latest_completed_eod_date = effective_session.latest_completed_session

        regime = None
        if latest_completed_eod_date is not None and universe_tickers:
            regime = self._regime_uc.evaluate(as_of_date=latest_completed_eod_date)

        ncp_baseline: dict[str, int] = {}
        if self._iev_baseline_repo is not None:
            ncp_baseline = self._iev_baseline_repo.ncp_baseline_iev(live_session_date)

        snapshot = self._opening_snapshot(
            request=request,
            live_session_date=live_session_date,
            universe_tickers=universe_tickers,
            warnings=warnings,
            ncp_baseline=ncp_baseline,
        )
        opening_candidates = snapshot.candidates
        market_wide_opening_observations = snapshot.market_wide_observations
        opening_snapshot_date = snapshot.snapshot_date

        upcoming_corp_actions = self._upcoming_corp_actions(
            universe_tickers=universe_tickers,
            live_session_date=live_session_date,
        )

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
                    if (
                        effective_session is not None
                        and latest_completed_eod_date == effective_session.latest_completed_session
                    ):
                        resolved_session = effective_session
                    else:
                        resolved_session = self._session_resolver.resolve(
                            run_at=datetime.combine(
                                latest_completed_eod_date,
                                MARKET_CLOSE,
                                tzinfo=IDX_TIMEZONE,
                            )
                        )
                    execution_context = SignalEvidenceExecutionContext(
                        effective_session=resolved_session,
                        source_availability_use_case=None,
                    )
                    response = self._accumulation_uc.execute(
                        AccumulationScreenRequest(
                            tickers=universe_tickers,
                            window_days=7,
                            as_of_date=latest_completed_eod_date,
                        ),
                        execution_context=execution_context,
                    )
                    accumulation_candidates = response.candidates[: request.top]

            projection = DailyAccumulationProjector().project(
                candidates=accumulation_candidates,
                checked=len(universe_tickers),
                data_ready=data_ready,
            )
            accumulation_summary = projection.summary
            daily_accumulation_candidates = projection.candidates
            warnings.extend(projection.warnings)

        setup_lens_impact: DailySetupLensImpactResult | None = None
        if (
            self._setup_lens_impact_uc is not None
            and overall_authority != "NOT_READY"
            and daily_accumulation_candidates
        ):
            impact_candidates = tuple(
                DailySetupLensImpactCandidate(ticker=c.ticker, base_action=c.action)
                for c in daily_accumulation_candidates[: request.top]
            )
            setup_lens_impact = self._setup_lens_impact_uc.execute(
                DailySetupLensImpactRequest(
                    candidates=impact_candidates,
                    as_of_date=(
                        latest_completed_eod_date
                        if latest_completed_eod_date is not None
                        else live_session_date
                    ),
                )
            )

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
            setup_lens_impact=setup_lens_impact,
            upcoming_corp_actions=upcoming_corp_actions,
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
            if item.freshness.candle_state
            in {
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
                f"Only {candle_coverage}/{candle_total} tickers have current candle data"
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
            if item.freshness.broker_state
            in {
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
                f"Only {broker_coverage}/{broker_total} tickers have current broker data"
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
            None if opening_snapshot_date is not None else "Opening snapshot unavailable"
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
        effective_session: EffectiveMarketSession,
    ) -> list[BriefingDataFreshnessItem]:
        items: list[BriefingDataFreshnessItem] = []
        for ticker in tickers:
            market_range = self._market_repo.get_date_range(ticker)
            candle_as_of = market_range[1] if market_range else None

            broker_range = self._broker_repo.get_date_range(ticker)
            broker_as_of = broker_range[1] if broker_range else None

            freshness_status = compute_data_freshness(
                candle_as_of=candle_as_of,
                broker_as_of=broker_as_of,
                effective_session=effective_session,
            )
            items.append(
                BriefingDataFreshnessItem(
                    ticker=ticker,
                    freshness=freshness_status,
                )
            )
        return items

    def _upcoming_corp_actions(
        self,
        *,
        universe_tickers: list[str],
        live_session_date: date,
    ) -> list[CorpActionBriefingRow]:
        """Flatten universe corporate-action milestones in the forward window.

        Read-only calendar projection: no fetch/sync policy here (that is the
        SyncCorporateActionCalendarUseCase's job). Live-first `today` refreshes the
        calendar upstream via the fetch workflow.
        """
        if self._corp_action_repo is None or not universe_tickers:
            return []

        from_date = live_session_date
        to_date = live_session_date + timedelta(days=CORP_ACTION_LOOKAHEAD_DAYS)
        events = self._corp_action_repo.get_events_for_universe(
            tuple(ticker.upper() for ticker in universe_tickers),
            from_date=from_date,
            to_date=to_date,
        )

        rows: list[CorpActionBriefingRow] = []
        for event in events:
            for milestone in event.dates:
                if from_date <= milestone.event_date <= to_date:
                    rows.append(
                        CorpActionBriefingRow(
                            ticker=event.ticker.upper(),
                            event_type=event.event_type.value,
                            date_role=milestone.date_role.value,
                            event_date=milestone.event_date,
                            note=event.event_note,
                        )
                    )
        rows.sort(key=lambda row: (row.event_date, row.ticker))
        return rows

    def _opening_snapshot(
        self,
        request: DailyBriefingRequest,
        live_session_date: date,
        universe_tickers: list[str],
        warnings: list[str],
        ncp_baseline: dict[str, int] | None = None,
    ) -> OpeningBriefingSnapshot:
        if self._learning_observation_repository is None:
            warnings.append(
                "No database-owned pre-open observation repository is configured "
                "(run: saham research pre-open capture)"
            )
            return OpeningBriefingSnapshot(
                candidates=[],
                market_wide_observations=[],
                snapshot_date=None,
            )

        observations = self._learning_observation_repository.list_observations(
            AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION
        )
        rows = [
            dict(observation.decision_payload)
            for observation in observations
            if observation.cutoff_at.date() == live_session_date
        ]
        if not rows:
            warnings.append(
                "No database-owned pre-open observations for "
                f"{live_session_date.isoformat()} "
                "(run: saham research pre-open capture)"
            )
            return OpeningBriefingSnapshot([], [], None)

        universe_set = {ticker.upper() for ticker in universe_tickers}
        baseline = ncp_baseline or {}
        candidates = []
        market_wide_observations = []

        for row in rows:
            ticker = row.get("ticker")
            if not ticker:
                continue
            ticker_upper = str(ticker).upper()
            candidate_payload = row.get("candidate") or {}
            trade_setup = row.get("trade_setup") or {}
            action_label = trade_setup.get("action") or "?"

            decision_iev = candidate_payload.get("iev")
            baseline_iev = baseline.get(ticker_upper)
            delta_iev = (
                decision_iev - baseline_iev
                if isinstance(decision_iev, int) and isinstance(baseline_iev, int)
                else None
            )
            gates = trade_setup.get("blocking_gates") or ()

            candidate = OpeningBriefingCandidate(
                ticker=ticker_upper,
                opening_setup=str(action_label),
                iev=decision_iev,
                iep=candidate_payload.get("iep"),
                trend=candidate_payload.get("trend"),
                accum_score=candidate_payload.get("accum_score"),
                prev_close=_opt_str(candidate_payload.get("prev_close")),
                iep_gap_pct=_opt_str(candidate_payload.get("iep_gap_pct")),
                iev_intensity=candidate_payload.get("iev_intensity"),
                bid_offer_imbalance=candidate_payload.get("bid_offer_imbalance"),
                broker_backing_score=candidate_payload.get("opening_broker_backing_score"),
                broker_backing_tag=candidate_payload.get("opening_broker_backing_tag"),
                trend_signal=candidate_payload.get("trend_signal"),
                entry_price=_opt_str(candidate_payload.get("entry_price")),
                stop_loss_price=_opt_str(candidate_payload.get("stop_loss_price")),
                signal_score=trade_setup.get("signal_score"),
                signal_strength=trade_setup.get("signal_strength"),
                blocking_gates=tuple(gates),
                rationale=trade_setup.get("rationale"),
                ncp_baseline_iev=baseline_iev,
                delta_iev=delta_iev,
            )
            if ticker_upper in universe_set:
                candidates.append(candidate)
            else:
                market_wide_observations.append(candidate)

        return OpeningBriefingSnapshot(
            candidates=candidates[: request.top],
            market_wide_observations=market_wide_observations[: request.top],
            snapshot_date=live_session_date,
        )
