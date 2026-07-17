"""Input collection phase for swing analysis workflow.

Layer: Application

Owns auto-refresh, data freshness, optional flow/broker detail, candle
loading, accumulation-candidate build, and market-context evaluation.
Extracted from `SwingAnalysisWorkflowUseCase` to keep the use case as
orchestration only.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSessionResolver,
)
from src.application.services.evidence_source_availability_assembler import (
    EvidenceSourceAvailabilityAssembler,
)
from src.application.services.swing_analysis_workflow_state import (
    SwingAnalysisWorkflowState,
)
from src.application.use_case.assess_source_availability_use_case import (
    AssessSourceAvailabilityUseCase,
)
from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar
from src.domain.value_objects.benchmark_symbol import canonicalize_ticker
from src.domain.value_objects.idx_market import IDX_TIMEZONE, MARKET_CLOSE

if TYPE_CHECKING:
    from src.application.dto import swing_analysis as swing_analysis_dto
    from src.domain.ports.broker_data_repository import BrokerDataRepository
    from src.domain.ports.market_data_repository import MarketDataRepository
    from src.domain.value_objects.market_context import MarketContext


class SwingAnalysisDataUnavailable(Exception):
    """Raised when a ticker has no local candle data for swing analysis."""

    def __init__(self, ticker: str) -> None:
        super().__init__(ticker)
        self.ticker = ticker


class SwingAnalysisInputCollector:
    """Collects raw inputs needed before decision composition."""

    def __init__(
        self,
        market_repository: "MarketDataRepository",
        broker_repository: "BrokerDataRepository",
        refresh_data: Callable[..., tuple[str, ...]],
        build_data_freshness: Callable[..., Any],
        build_flow_detail: Callable[..., Any],
        build_broker_detail: Callable[..., Any],
        build_accumulation_candidate: Callable[..., Any | None],
        evaluate_market_context: Callable[..., "MarketContext"] | None,
        session_resolver: EffectiveMarketSessionResolver | None = None,
        trading_session_calendar_loader: (
            Callable[[date, date], "KnownTradingSessionCalendar | None"] | None
        ) = None,
    ) -> None:
        self._market_repo = market_repository
        self._broker_repo = broker_repository
        self._refresh_data = refresh_data
        self._build_data_freshness = build_data_freshness
        self._build_flow_detail = build_flow_detail
        self._build_broker_detail = build_broker_detail
        self._build_accumulation_candidate = build_accumulation_candidate
        self._trading_session_calendar_loader = trading_session_calendar_loader
        self._evaluate_market_context = evaluate_market_context
        self._session_resolver = session_resolver or EffectiveMarketSessionResolver(
            market_repository
        )

    def collect(
        self, request: "swing_analysis_dto.SwingAnalysisWorkflowRequest"
    ) -> SwingAnalysisWorkflowState:
        warnings: list[str] = []

        refresh_actions = ("disabled",)
        if request.auto_refresh:
            refresh_actions = self._refresh_data(
                ticker=request.ticker,
                db_path=request.db_path,
                force_refresh=request.force_refresh,
            )

        # Resolved once per workflow execution (single ticker per request),
        # never per-ticker or per-provider. `request.today` doubling as an
        # explicit as-of date (tests/backtests) vs. the live default is
        # distinguished by comparing it against the real current date: a
        # live run gets real WIB wall-clock time-of-day so the resolver can
        # classify pre-open/regular/pre-closing/after-close; an explicit
        # historical date gets a deterministic after-close WIB decision
        # timestamp, treating that date as a completed EOD decision.
        real_today = date.today()
        if request.today == real_today:
            now_wib = datetime.now(IDX_TIMEZONE)
            run_at = datetime.combine(real_today, now_wib.time(), tzinfo=IDX_TIMEZONE)
        else:
            run_at = datetime.combine(request.today, MARKET_CLOSE, tzinfo=IDX_TIMEZONE)
        effective_session = self._session_resolver.resolve(run_at=run_at)

        data_freshness = self._build_data_freshness(
            ticker=request.ticker,
            effective_session=effective_session,
            market_repo=self._market_repo,
            broker_repo=self._broker_repo,
            refresh_actions=refresh_actions,
        )
        needs_broker_detail = request.include_flow_detail or request.setup_name is not None
        flow_detail = None
        if request.include_flow_detail:
            flow_detail = self._build_flow_detail(
                ticker=request.ticker,
                broker_repo=self._broker_repo,
                window_sessions=request.flow_window,
                as_of_date=request.today,
            )
        broker_detail = None
        if needs_broker_detail:
            broker_detail = self._build_broker_detail(
                ticker=request.ticker,
                broker_repo=self._broker_repo,
                window_sessions=5,
                as_of_date=request.today,
            )

        # Bounded by request.today: this is the same candle series later
        # passed as-is into the setup-evidence/phase-detector builders (see
        # SwingAnalysisOptionalEvidenceRunner.build_evidence), so an
        # unbounded read here would let a historical `--date` replay
        # consume (and score) candles dated after the decision date it
        # claims to represent — the exact leakage DQ-002G's temporal-leakage
        # tests guard against elsewhere in this codebase.
        candles = self._market_repo.get_candles(request.ticker, end_date=request.today)
        if not candles:
            raise SwingAnalysisDataUnavailable(request.ticker)
        latest_close = candles[-1].close

        accumulation_candidate = None
        try:
            accumulation_candidate = self._build_accumulation_candidate(
                ticker=request.ticker,
                window=request.window,
                as_of_date=request.today,
            )
        except Exception as exc:
            warnings.append(f"Accumulation unavailable: {exc}")

        # DQ-002 Blocker 2 (shadow mode, partial — analyze swing only): one
        # bounded trading-session calendar and one
        # AssessSourceAvailabilityUseCase, resolved once per workflow
        # execution and reused across both evidence-group assessments below —
        # never constructed per-ticker or per-source. The calendar window is
        # the minimal range that can prove every session gap this decision
        # actually needs — min(observed source date)..latest_completed_session
        # — not an arbitrary fixed lookback, since a wider window is both
        # unnecessary and more likely to hit an unrelated gap elsewhere in
        # the range and fail closed for no reason. A calendar the loader
        # cannot prove (missing loader, or a real gap in the underlying
        # candle data — a known limitation until blocker 1's holiday
        # handling improves) falls back to an empty calendar rather than a
        # weekday fallback, so every session-aligned assessment fails closed
        # to UNKNOWN instead of silently assuming 0 sessions apart.
        setup_source_availability = None
        flow_source_availability = None
        if accumulation_candidate is not None:
            try:
                latest_broker_date = getattr(
                    accumulation_candidate, "latest_broker_date", None
                )
                latest_broker_daily_flow_date = getattr(
                    accumulation_candidate, "latest_broker_daily_flow_date", None
                )
                observed_dates = [
                    d
                    for d in (
                        max((c.date for c in candles), default=None),
                        latest_broker_date,
                        latest_broker_daily_flow_date,
                    )
                    if d is not None
                ]
                coverage_end = effective_session.latest_completed_session or request.today
                coverage_start = min(observed_dates) if observed_dates else coverage_end
                calendar = None
                if self._trading_session_calendar_loader is not None:
                    calendar = self._trading_session_calendar_loader(
                        coverage_start, coverage_end
                    )
                if calendar is None:
                    calendar = KnownTradingSessionCalendar(
                        sessions=(),
                        coverage_start=coverage_start,
                        coverage_end=coverage_end,
                    )
                availability_assembler = EvidenceSourceAvailabilityAssembler(
                    AssessSourceAvailabilityUseCase(calendar=calendar)
                )
                (
                    setup_source_availability,
                    flow_source_availability,
                ) = availability_assembler.assess_setup_and_flow(
                    effective_session=effective_session,
                    candidate=accumulation_candidate,
                    candles=candles,
                )
            except Exception as exc:
                warnings.append(f"Source availability assessment unavailable: {exc}")

        market_regime = None
        if request.with_market_context:
            try:
                if self._evaluate_market_context is None:
                    raise RuntimeError("Market context evaluator is not configured.")
                market_regime = self._evaluate_market_context(
                    db_path=request.db_path,
                    as_of_date=request.today,
                    universe=request.regime_universe,
                    benchmark=canonicalize_ticker(request.benchmark),
                )
            except Exception as exc:
                warnings.append(f"Market regime unavailable: {exc}")

        return SwingAnalysisWorkflowState(
            warnings=warnings,
            refresh_actions=refresh_actions,
            data_freshness=data_freshness,
            flow_detail=flow_detail,
            broker_detail=broker_detail,
            candles=candles,
            latest_close=latest_close,
            accumulation_candidate=accumulation_candidate,
            effective_session=effective_session,
            market_regime=market_regime,
            setup_source_availability=setup_source_availability,
            flow_source_availability=flow_source_availability,
        )
