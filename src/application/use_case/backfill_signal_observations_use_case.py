"""Backfill historical signal observations using the live accumulation pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Callable

from src.application.dto.signal_evidence_execution_context import (
    SignalEvidenceExecutionContext,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSessionResolver,
)
from src.application.services.lean_observation_identity import (
    LeanObservationIdentity,
)
from src.application.services.signal_evidence_execution_context_builder import (
    SignalEvidenceExecutionContextBuilder,
)
from src.application.services.signal_observation_request_builder import (
    BuildSignalObservationScreenRequest,
)
from src.application.use_case.generate_signal_forward_labels_use_case import (
    GenerateAllSignalForwardLabelsRequest,
    GenerateSignalForwardLabelsUseCase,
)
from src.application.use_case.record_accumulation_observations_use_case import (
    RecordAccumulationObservationsUseCase,
)
from src.domain.ports.candidate_observations_repository import (
    CandidateObservationsRepository,
)
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.idx_market import IDX_TIMEZONE, MARKET_CLOSE
from src.domain.value_objects.signal_forward_label import SignalLabelHorizon

if TYPE_CHECKING:
    from src.domain.value_objects.market_context import MarketContext


@dataclass(frozen=True)
class BackfillSkippedDate:
    date: date
    reason: str

    def to_dict(self) -> dict:
        return {"date": self.date.isoformat(), "reason": self.reason}


@dataclass(frozen=True)
class BackfillTickerExclusion:
    """A universe ticker that produced no persisted observation on a processed
    date (criterion 12). Machine-readable at the ticker/date capture boundary.

    Only the evaluated-vs-unavailable split is real today: the production
    backfill disables every reject gate (Slice C finding), so the sole reason a
    processed universe ticker yields no observation is that its source input was
    missing and it was never evaluated.
    """

    date: date
    ticker: str
    reason: str

    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "ticker": self.ticker,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class BackfillSignalObservationsRequest:
    tickers: tuple[str, ...]
    start_date: date
    end_date: date
    horizon: SignalLabelHorizon = SignalLabelHorizon.SWING_10D
    generate_labels: bool = False
    windows: tuple[int, ...] = (7, 30, 90)
    # Universe-membership identity (transport decided by the adapter). The
    # adapter sets this to e.g. "lq45@current"; the use case copies it onto the
    # response and derives the survivorship limitation from it. The adapter must
    # not compute the survivorship policy — only pass the universe identity.
    universe_membership_source: str = ""


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
    # DQ-003 Slice B capture-boundary reporting (criteria 12 and 13). Counts are
    # aggregated from screen results already returned this run — no re-query, no
    # persistence change. `rejected_count` is 0 by construction under the
    # production config (all reject gates disabled; see the Slice C finding), so
    # `selected_count == evaluated_count` today. `evaluated_count` cross-checks
    # `saved_observation_count`: every evaluated ticker is persisted.
    universe_size: int = 0
    evaluated_count: int = 0
    selected_count: int = 0
    rejected_count: int = 0
    unavailable_count: int = 0
    universe_membership_source: str = ""
    survivorship_limitation: str | None = None
    ticker_exclusions: tuple[BackfillTickerExclusion, ...] = field(default_factory=tuple)
    # DQ-003 Slice E candidate-only eligibility guard (criterion 11). True only
    # if at least one observation persisted THIS run carries a screen_result
    # other than "pass" (a genuine screen-rejected control). Derived from the
    # same `rejected_count` aggregation Slice B already computes — no new read,
    # no persistence change. Under the production capture path every reject gate
    # is disabled (Slice C finding), so `rejected_count == 0` and this is False:
    # the captured population is candidate-only and ineligible for screener
    # recall/precision/filter-value claims. `recall_eligibility` states that
    # reason machine-readably. A downstream recall/precision consumer (DQ-006)
    # MUST check `contains_control_population` and refuse claims while it is
    # False, pending the open design question in the Slice C finding.
    contains_control_population: bool = False
    recall_eligibility: str = "ineligible_candidate_only_no_screen_rejected_control"

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
            "universe_size": self.universe_size,
            "evaluated_count": self.evaluated_count,
            "selected_count": self.selected_count,
            "rejected_count": self.rejected_count,
            "unavailable_count": self.unavailable_count,
            "universe_membership_source": self.universe_membership_source,
            "survivorship_limitation": self.survivorship_limitation,
            "ticker_exclusions": [entry.to_dict() for entry in self.ticker_exclusions],
            "contains_control_population": self.contains_control_population,
            "recall_eligibility": self.recall_eligibility,
        }


class BackfillSignalObservationsUseCase:
    """Create historical candidate observations before optional label generation."""

    _AVAILABILITY_CALENDAR_LOOKBACK_DAYS = 14

    def __init__(
        self,
        *,
        record_observations_use_case: RecordAccumulationObservationsUseCase,
        screen_request_builder: BuildSignalObservationScreenRequest,
        market_data_repository: MarketDataRepository,
        candidate_observations_repository: CandidateObservationsRepository,
        observation_identity: LeanObservationIdentity,
        label_generation_use_case: GenerateSignalForwardLabelsUseCase | None = None,
        evaluate_market_context: "Callable[..., MarketContext] | None" = None,
        session_resolver: EffectiveMarketSessionResolver | None = None,
        evidence_context_builder: SignalEvidenceExecutionContextBuilder | None = None,
    ) -> None:
        self._record = record_observations_use_case
        self._request_builder = screen_request_builder
        self._market = market_data_repository
        self._observations = candidate_observations_repository
        # Lean DQ-003 identity resolved once by the adapter (which owns reading
        # config file contents) and stamped onto every capture context. This
        # use case never computes the hash; it only transports the resolved id.
        self._observation_identity = observation_identity
        self._labels = label_generation_use_case
        self._evaluate_market_context = evaluate_market_context
        self._session_resolver = session_resolver or EffectiveMarketSessionResolver(
            market_data_repository
        )
        self._evidence_context_builder = evidence_context_builder

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
        market_context_notes: list[str] = []
        ticker_exclusions: list[BackfillTickerExclusion] = []
        saved_count = 0
        generated_label_count = 0
        unavailable_label_count = 0
        # Capture-boundary rollups (DQ-003 Slice B). Summed per processed
        # (date, window) unit, consistent with how saved_count is summed.
        evaluated_count = 0
        selected_count = 0
        rejected_count = 0
        unavailable_count = 0

        for trading_date in trading_dates:
            if not self._has_any_ticker_candle(tickers, trading_date):
                skipped.append(
                    BackfillSkippedDate(
                        date=trading_date,
                        reason="missing_source_candles_for_universe",
                    )
                )
                continue

            market_context = None
            if self._evaluate_market_context is not None:
                try:
                    market_context = self._evaluate_market_context(
                        as_of_date=trading_date
                    )
                except Exception:
                    market_context_notes.append(
                        f"market_context_unavailable_for_{trading_date.isoformat()}"
                    )

            # One deterministic after-close session per trading_date, shared
            # across every window for that date — never resolved per
            # ticker/window. Deterministic so reruns of the same historical
            # date always produce the same provenance.
            effective_session = self._session_resolver.resolve(
                run_at=datetime.combine(trading_date, MARKET_CLOSE, tzinfo=IDX_TIMEZONE)
            )
            context = self._build_execution_context(effective_session)

            evaluated_tickers_for_date: set[str] = set()
            for window in request.windows:
                record_result = self._record.execute(
                    self._request_builder.build(
                        tickers=list(tickers),
                        window_days=int(window),
                        as_of_date=trading_date,
                        market_context=market_context,
                    ),
                    execution_context=context,
                )
                saved_count += record_result.recorded_count

                # Per-capture-unit derivations from the screen result already in
                # hand. `evaluated` = every ticker the screen evaluated;
                # `selected` = survivors (`pass`); `rejected` = evaluated minus
                # selected (0 under production config); `unavailable` = universe
                # tickers the screen could not evaluate (missing source).
                unit = record_result.response
                evaluated_unit = len(unit.observation_candidates)
                selected_unit = len(unit.candidates)
                evaluated_count += evaluated_unit
                selected_count += selected_unit
                rejected_count += evaluated_unit - selected_unit
                unavailable_count += unit.total_tickers_checked - evaluated_unit
                for observation_candidate in unit.observation_candidates:
                    evaluated_tickers_for_date.add(observation_candidate.candidate.ticker)
            processed.append(trading_date)

            # A universe ticker that produced no observation on this processed
            # date (across all windows) was never evaluated because its source
            # input was unavailable — the only real ticker-boundary exclusion
            # today (criterion 12; Slice C finding). Per-date, deduped.
            for ticker in tickers:
                if ticker not in evaluated_tickers_for_date:
                    ticker_exclusions.append(
                        BackfillTickerExclusion(
                            date=trading_date,
                            ticker=ticker,
                            reason="source_unavailable_not_evaluated",
                        )
                    )

            if request.generate_labels:
                if self._labels is None:
                    skipped.append(
                        BackfillSkippedDate(
                            date=trading_date,
                            reason="label_generation_use_case_unavailable",
                        )
                    )
                    continue
                if not self._observations.list_canonical_by_date(trading_date):
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

        # Survivorship limitation is owned by the use case, not the adapter. A
        # `@current` membership source means historical membership is
        # unavailable, so the captured universe is the current one and is
        # survivorship-biased. Building a historical-membership platform is out
        # of scope (parked; see DQ-003 deferral triggers).
        survivorship_limitation = (
            "Universe membership resolved from the current universe "
            "(historical membership unavailable); captured population is "
            "survivorship-biased and cannot support point-in-time universe "
            "claims."
            if request.universe_membership_source.endswith("@current")
            else None
        )

        # DQ-003 Slice E (criterion 11): a genuine screen-rejected control exists
        # only if at least one evaluated observation this run was not `pass`
        # (rejected_count > 0). Derived from the aggregation above — no new read.
        # A candidate-only population (rejected_count == 0) is ineligible for
        # screener recall/precision/filter-value claims; the reason is stated
        # machine-readably so a downstream consumer (DQ-006) can refuse claims.
        contains_control_population = rejected_count > 0
        recall_eligibility = (
            "eligible_contains_screen_rejected_control"
            if contains_control_population
            else "ineligible_candidate_only_no_screen_rejected_control"
        )

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
                "candidate_observations are upserted by canonical identity "
                "(ticker, snapshot_date, workflow, window_sessions, "
                "data_as_of_date, config_hash); reruns with the same identity "
                "replace the existing row rather than appending a duplicate.",
                *market_context_notes,
            ),
            universe_size=len(request.tickers),
            evaluated_count=evaluated_count,
            selected_count=selected_count,
            rejected_count=rejected_count,
            unavailable_count=unavailable_count,
            universe_membership_source=request.universe_membership_source,
            survivorship_limitation=survivorship_limitation,
            ticker_exclusions=tuple(ticker_exclusions),
            contains_control_population=contains_control_population,
            recall_eligibility=recall_eligibility,
        )

    def _build_execution_context(
        self, effective_session
    ) -> SignalEvidenceExecutionContext:
        """Build capture context with availability assessment when possible.

        Mirrors the live screen 14-day IHSG calendar window so historical
        coverage is not permanently UNKNOWN via AVAILABILITY_ASSESSOR_UNAVAILABLE.
        Identity stamps remain owned by this use case.
        """
        if self._evidence_context_builder is None:
            return SignalEvidenceExecutionContext(
                effective_session=effective_session,
                source_availability_use_case=None,
                observation_contract=self._observation_identity.observation_contract,
                semantic_compatibility_id=(
                    self._observation_identity.semantic_compatibility_id
                ),
            )

        coverage_end = (
            effective_session.latest_completed_session
            or effective_session.analysis_as_of
            or effective_session.decision_at.date()
        )
        coverage_start = coverage_end - timedelta(
            days=self._AVAILABILITY_CALENDAR_LOOKBACK_DAYS
        )
        built = self._evidence_context_builder.build(
            effective_session=effective_session,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
        )
        return replace(
            built,
            observation_contract=self._observation_identity.observation_contract,
            semantic_compatibility_id=(
                self._observation_identity.semantic_compatibility_id
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
        observations = self._observations.list_canonical_by_date(signal_date)
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
