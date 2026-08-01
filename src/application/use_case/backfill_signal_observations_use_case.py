"""Backfill historical signal observations using the live accumulation pipeline."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

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
from src.application.use_case.record_accumulation_observations_use_case import (
    RecordAccumulationObservationsUseCase,
)
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.idx_market import IDX_TIMEZONE, MARKET_CLOSE
from src.domain.value_objects.learning_artifacts import (
    ACCUM_POPULATION_NAME,
    AccumPopulationBinding,
)

if TYPE_CHECKING:
    from src.domain.value_objects.market_context import MarketContext

# Membership resolver: (as_of_date) -> sorted/uppercase-ready ticker sequence.
MembershipResolver = Callable[[date], Sequence[str]]


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
    start_date: date
    end_date: date
    windows: tuple[int, ...] = (7, 30, 90)
    # Universe-membership identity (transport decided by the adapter). The
    # adapter sets this to e.g. "lq45@pit"; the use case copies it onto the
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
    # `universe_size` is the distinct union of PIT members across processed dates
    # (range union), not a single-day membership count.
    universe_size: int = 0
    evaluated_count: int = 0
    selected_count: int = 0
    rejected_count: int = 0
    unavailable_count: int = 0
    universe_membership_source: str = ""
    survivorship_limitation: str | None = None
    ticker_exclusions: tuple[BackfillTickerExclusion, ...] = field(default_factory=tuple)
    # DQ-003 Slice E eligibility guard (criterion 11). True only if this run
    # produced at least one evaluated non-pass (``rejected_count > 0``).
    #
    # Production capture **neutralizes score/structural reject gates** so the
    # persisted set is the PIT-tradable, broker-observable population (negative-
    # inclusive by forward labels). Therefore ``rejected_count`` is usually 0
    # **by design**, not by missing data. That means:
    # - suitable for path/outcome and factor studies on the broker-observable set
    # - **not** a complete screen-reject census for classical screener
    #   recall/precision/filter-value claims
    #
    # Consumers MUST check ``contains_control_population`` / ``recall_eligibility``
    # and refuse screen-reject recall claims while ineligible. Do **not** "fix"
    # by re-enabling capture reject gates without a named consumer and the
    # filter-replay contract (see tasks/backlog/parked_screen_filter_replay_contract.md).
    # ``contains_control_population`` alone is also insufficient for full
    # denominator completeness (parked historical eligible-universe work).
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


def survivorship_limitation_for_source(
    universe_membership_source: str,
    *,
    pit_window_sessions: int,
) -> str | None:
    """Derive survivorship disclosure from membership identity (use-case policy)."""
    source = universe_membership_source.strip()
    if source.endswith("@current"):
        return (
            "Universe membership resolved from the current universe "
            "(historical membership unavailable); captured population is "
            "survivorship-biased and cannot support point-in-time universe "
            "claims."
        )
    if source.endswith("@pit"):
        universe_key = source[: -len("@pit")]
        n = pit_window_sessions
        if universe_key == "cached":
            return (
                "Board-wide tradable-universe PIT: tickers with a candle in "
                f"the last {n} trading sessions ending at the observation date. "
                "Not historical index/eligible membership — names delisted "
                "before the local ingestion window remain absent."
            )
        return (
            "Tradable-universe PIT: named universe ∩ tickers with a candle in the "
            f"last {n} trading sessions ending at the observation date. Not historical "
            f"index/eligible membership — names dropped from today's {universe_key} list, and "
            "names delisted before the local ingestion window, remain absent."
        )
    return None


class BackfillSignalObservationsUseCase:
    """Create historical candidate observations before optional label generation.

    Membership is re-derived per trading date via ``membership_resolver`` (PIT
    tradable universe). The adapter must not pass a fixed ticker list as
    membership authority.
    """

    # Broker SESSION_ALIGNED lag is 1; keep a few proven sessions so LATE vs
    # CURRENT remains measurable without a 14-calendar-day window that
    # commonly includes IDX holidays and disables the assessor.
    _AVAILABILITY_CALENDAR_MAX_SESSIONS = 5
    _AVAILABILITY_CALENDAR_PROBE_DAYS = 45

    def __init__(
        self,
        *,
        record_observations_use_case: RecordAccumulationObservationsUseCase,
        screen_request_builder: BuildSignalObservationScreenRequest,
        market_data_repository: MarketDataRepository,
        observation_identity: LeanObservationIdentity,
        membership_resolver: MembershipResolver,
        pit_window_sessions: int,
        named_universe_tickers: Sequence[str],
        producer_source_revision: str,
        population_name: str = "lq45",
        evaluate_market_context: Callable[..., MarketContext] | None = None,
        session_resolver: EffectiveMarketSessionResolver | None = None,
        evidence_context_builder: SignalEvidenceExecutionContextBuilder | None = None,
    ) -> None:
        if pit_window_sessions < 1:
            raise ValueError(f"pit_window_sessions must be >= 1, got {pit_window_sessions}")
        if not producer_source_revision or not str(producer_source_revision).strip():
            raise ValueError("producer_source_revision must be non-empty")
        named = tuple(
            sorted({str(t).strip().upper() for t in named_universe_tickers if str(t).strip()})
        )
        if not named:
            raise ValueError("named_universe_tickers must be non-empty for population binding")
        # Challenge-corpus backfill/capture only persists lq45 authority.
        # Reject unsupported --universe names before any session loop/write.
        if population_name != ACCUM_POPULATION_NAME:
            raise ValueError(
                f"unsupported population_name={population_name!r}; "
                f"accumulation challenge corpus requires "
                f"population_name={ACCUM_POPULATION_NAME!r}"
            )
        self._record = record_observations_use_case
        self._request_builder = screen_request_builder
        self._market = market_data_repository
        # Lean DQ-003 identity resolved once by the adapter (which owns reading
        # config file contents) and stamped onto every capture context. This
        # use case never computes the hash; it only transports the resolved id.
        self._observation_identity = observation_identity
        self._membership_resolver = membership_resolver
        self._pit_window_sessions = pit_window_sessions
        self._named_universe_tickers = named
        self._producer_source_revision = str(producer_source_revision).strip()
        self._population_name = population_name
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

        # Trading-date axis is IHSG only — do not fall back to a universe
        # member (would circularly depend on membership and reintroduce bias).
        trading_dates = tuple(
            _dates_from_candles(
                self._market.get_candles(
                    "IHSG",
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
        membership_union: set[str] = set()

        if not trading_dates:
            market_context_notes.append("ihsg_calendar_unavailable")

        for trading_date in trading_dates:
            tickers = tuple(ticker.upper() for ticker in self._membership_resolver(trading_date))
            if not tickers:
                skipped.append(
                    BackfillSkippedDate(
                        date=trading_date,
                        reason="empty_pit_membership",
                    )
                )
                continue

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
                    market_context = self._evaluate_market_context(as_of_date=trading_date)
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
            # ADR-056: screen each window, then merge into one session observation
            # per ticker (features_by_window). Do not persist per-window rows.
            window_results: dict = {}
            for window in request.windows:
                screen_request = self._request_builder.build(
                    tickers=list(tickers),
                    window_days=int(window),
                    as_of_date=trading_date,
                    market_context=market_context,
                )
                response = self._record.screen(
                    screen_request,
                    execution_context=context,
                )
                window_results[int(window)] = (
                    screen_request,
                    list(response.observation_candidates),
                )

                unit = response
                evaluated_unit = len(unit.observation_candidates)
                selected_unit = len(unit.candidates)
                # Count evaluations across windows; saved_count is ticker-sessions.
                evaluated_count += evaluated_unit
                selected_count += selected_unit
                rejected_count += evaluated_unit - selected_unit
                unavailable_count += unit.total_tickers_checked - evaluated_unit
                for observation_candidate in unit.observation_candidates:
                    evaluated_tickers_for_date.add(observation_candidate.candidate.ticker)

            population_binding = AccumPopulationBinding.create(
                membership_tickers=tickers,
                named_universe_tickers=self._named_universe_tickers,
                membership_session=trading_date,
                pit_tradable_lookback_sessions=self._pit_window_sessions,
                producer_source_revision=self._producer_source_revision,
                population_name=self._population_name,
            )
            saved_count += self._record.persist_multi_window(
                window_results=window_results,
                snapshot_date=trading_date,
                execution_context=context,
                universe_tickers=list(tickers),
                population_binding=population_binding,
                canonical_window=7,
            )
            processed.append(trading_date)
            membership_union.update(tickers)

            # A universe ticker that produced no observation on this processed
            # date (across all windows) was never evaluated because its source
            # input was unavailable — the only real ticker-boundary exclusion
            # today (criterion 12; Slice C finding). Per-date PIT set only.
            for ticker in tickers:
                if ticker not in evaluated_tickers_for_date:
                    ticker_exclusions.append(
                        BackfillTickerExclusion(
                            date=trading_date,
                            ticker=ticker,
                            reason="source_unavailable_not_evaluated",
                        )
                    )

        # Survivorship limitation is owned by the use case, not the adapter.
        survivorship_limitation = survivorship_limitation_for_source(
            request.universe_membership_source,
            pit_window_sessions=self._pit_window_sessions,
        )

        # DQ-003 Slice E (criterion 11): screen-reject control presence this run.
        # Capture policy usually yields rejected_count == 0 by design (gates
        # neutralized). That is stamped, not silently papered over.
        contains_control_population = rejected_count > 0
        recall_eligibility = (
            "eligible_contains_screen_rejected_control"
            if contains_control_population
            else "ineligible_candidate_only_no_screen_rejected_control"
        )
        recall_note = (
            "recall_eligibility=eligible_contains_screen_rejected_control "
            f"(rejected_count={rejected_count})"
            if contains_control_population
            else (
                "recall_eligibility=ineligible_candidate_only_no_screen_rejected_control: "
                "capture neutralizes score/structural reject gates "
                f"(rejected_count={rejected_count}); corpus is broker-observable / "
                "outcome-negative-inclusive, not a screen-reject census. "
                "Refuse screener recall/precision/filter-value claims until a named "
                "filter-replay consumer is activated "
                "(tasks/backlog/parked_screen_filter_replay_contract.md)."
            )
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
                "ADR-056: one learning_observation per ticker-session with "
                "features_by_window[7|30|90]; identity is window_id=TICKER:YYYY-MM-DD "
                "and horizon_contract=accum_10d. Reruns with the same identity and "
                "digest are idempotent; digest changes raise an immutable conflict.",
                recall_note,
                *market_context_notes,
            ),
            universe_size=len(membership_union),
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

    def _build_execution_context(self, effective_session) -> SignalEvidenceExecutionContext:
        """Build capture context with availability assessment when possible.

        Uses a gap-free IHSG session window (not a fixed 14-calendar-day
        lookback) so IDX holidays inside a long calendar span do not disable
        the availability assessor via unexplained weekday gaps.
        Identity stamps remain owned by this use case.
        """
        if self._evidence_context_builder is None:
            return SignalEvidenceExecutionContext(
                effective_session=effective_session,
                source_availability_use_case=None,
                observation_contract=self._observation_identity.observation_contract,
                semantic_compatibility_id=(self._observation_identity.semantic_compatibility_id),
            )

        coverage_end = (
            effective_session.latest_completed_session
            or effective_session.analysis_as_of
            or effective_session.decision_at.date()
        )
        coverage_start = self._resolve_availability_calendar_start(coverage_end)
        built = self._evidence_context_builder.build(
            effective_session=effective_session,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
        )
        return replace(
            built,
            observation_contract=self._observation_identity.observation_contract,
            semantic_compatibility_id=(self._observation_identity.semantic_compatibility_id),
        )

    def _resolve_availability_calendar_start(self, coverage_end: date) -> date:
        from src.application.services.availability_calendar_window import (
            resolve_gap_free_availability_calendar_start,
        )

        probe_start = coverage_end - timedelta(days=self._AVAILABILITY_CALENDAR_PROBE_DAYS)
        candles = self._market.get_candles(
            "IHSG",
            start_date=probe_start,
            end_date=coverage_end,
        )
        sessions = tuple(sorted({candle.date for candle in candles}))
        return resolve_gap_free_availability_calendar_start(
            sessions=sessions,
            coverage_end=coverage_end,
            max_sessions=self._AVAILABILITY_CALENDAR_MAX_SESSIONS,
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


def _dates_from_candles(candles) -> list[date]:
    return sorted({candle.date for candle in candles})
