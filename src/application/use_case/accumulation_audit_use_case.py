"""
Historical audit for the foreign accumulation screener.

Replays accumulation signals over historical dates and measures forward
returns from local cached market and broker data.

Layer: Application
Depends on: Domain ports and accumulation screen use case
AI usage: None
"""

from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Protocol

from src.application.dto.accumulation_audit import (
    AccumulationAuditClaimStamp,
    AccumulationAuditPolicy,
    AccumulationAuditRequest,
    AccumulationAuditResponse,
    AccumulationAuditSkipLedger,
    AuditBucketPolicy,
    AuditGroupStat,
    AuditRecord,
    ExitSimulationStat,
)
from src.application.dto.accumulation_screen import (
    AccumulationCandidate,
    AccumulationDerivedFeaturePolicy,
    AccumulationScreenRequest,
)
from src.application.dto.signal_evidence_execution_context import (
    SignalEvidenceExecutionContext,
)
from src.application.ports.rules_loader import RulesLoader
from src.application.services.accumulation_audit_exit_simulator import (
    AccumulationAuditExitSimulator,
)
from src.application.services.accumulation_audit_record_builder import (
    AccumulationAuditRecordBuilder,
)
from src.application.services.accumulation_audit_statistics import (
    AccumulationAuditStatisticsBuilder,
)
from src.application.services.accumulation_broker_quality_classifier import (
    AccumulationBrokerQualityClassifier,
)
from src.application.services.accumulation_screen_factory import (
    create_accumulation_screen_use_case,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSessionResolver,
)
from src.application.use_case.accumulation_screen_use_case import AccumulationScreenUseCase
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.idx_market import IDX_TIMEZONE, MARKET_CLOSE

if TYPE_CHECKING:
    from src.application.services.signal_engine import SignalEngine

# Compatibility re-exports: tests and adapters historically imported DTOs
# from this module. Keep these import-only; implementations live in the
# DTO/service modules above.
__all__ = [
    "AccumulationAuditClaimStamp",
    "AccumulationAuditPolicy",
    "AccumulationAuditRequest",
    "AccumulationAuditResponse",
    "AccumulationAuditSkipLedger",
    "AuditBucketPolicy",
    "AuditGroupStat",
    "AuditRecord",
    "ExitSimulationStat",
    "AccumulationAuditUseCase",
]


class _ScreenRunner(Protocol):
    def execute(self, request: AccumulationScreenRequest, *, execution_context=None): ...


class AccumulationAuditUseCase:
    """
    Replay the accumulation screener and measure forward performance.

    The use case is deterministic and offline: it reads local repositories only.
    It intentionally uses the current ticker universe supplied by the caller, so
    users should treat historical results as current-universe replay unless they
    provide historical universe snapshots.

    DQ-008 lean: prefers an injected screen use case built via
    ``create_accumulation_screen_use_case`` (same factory as live screen) so
    scoring shares the accumulation-flow path. Outcomes remain DESCRIPTIVE
    raw-market measurements — not net-executable or promotion-grade OOS.
    """

    def __init__(
        self,
        broker_repository: BrokerDataRepository,
        market_repository: MarketDataRepository,
        indicator_registry: Any,
        rules_loader: RulesLoader,
        signal_engine: "SignalEngine",
        derived_feature_policy: AccumulationDerivedFeaturePolicy | None = None,
        *,
        screen_use_case: AccumulationScreenUseCase | None = None,
        accum_score_policy: Any | None = None,
    ) -> None:
        self._broker_repo = broker_repository
        self._market_repo = market_repository
        self._derived_features = derived_feature_policy or AccumulationDerivedFeaturePolicy()
        self._session_resolver = EffectiveMarketSessionResolver(market_repository)
        self._screen: _ScreenRunner = screen_use_case or create_accumulation_screen_use_case(
            broker_repository=broker_repository,
            market_repository=market_repository,
            indicator_registry=indicator_registry,
            rules_loader=rules_loader,
            signal_engine=signal_engine,
            accum_score_policy=accum_score_policy,
            derived_feature_policy=self._derived_features,
            # Historical lean: no live Stockbit enricher / risk funnel.
            stockbit_providers=None,
            risk_use_case=None,
        )
        self._broker_quality_classifier = AccumulationBrokerQualityClassifier(broker_repository)
        self._record_builder = AccumulationAuditRecordBuilder(
            market_repository=market_repository,
            broker_quality_classifier=self._broker_quality_classifier,
        )
        self._statistics_builder = AccumulationAuditStatisticsBuilder()
        self._exit_simulator = AccumulationAuditExitSimulator(market_repository)

    def execute(self, request: AccumulationAuditRequest) -> AccumulationAuditResponse:
        """Run the historical replay audit."""
        tickers = [t.upper().strip() for t in request.tickers if t.strip()]
        if not tickers:
            raise ValueError("At least one ticker is required")
        if request.start_date > request.end_date:
            raise ValueError("start_date must be on or before end_date")
        if request.horizon_days < 1:
            raise ValueError("horizon_days must be positive")
        self._validate_policy(request.policy)
        if request.simulate_exits:
            self._validate_exit_simulation_request(request)

        replay_dates = self._replay_dates(tickers, request.start_date, request.end_date)
        records: list[AuditRecord] = []
        screen_pass = 0
        screen_rejected_flow = 0
        screen_rejected_signal = 0
        screen_insufficient_data = 0
        audit_filter_excluded = 0
        skipped_no_forward_data = 0

        for signal_date in replay_dates:
            effective_session = self._session_resolver.resolve(
                run_at=datetime.combine(signal_date, MARKET_CLOSE, tzinfo=IDX_TIMEZONE)
            )
            execution_context = SignalEvidenceExecutionContext(
                effective_session=effective_session,
                source_availability_use_case=None,
            )
            screen_response = self._screen.execute(
                AccumulationScreenRequest(
                    tickers=tickers,
                    window_days=request.window_days,
                    min_net_buy_days=request.min_net_buy_days,
                    min_accum_score=request.min_accum_score,
                    min_accum_score_enabled=True,
                    rsi_period=self._derived_features.rsi_period,
                    sma_period=self._derived_features.trend_sma_period,
                    as_of_date=signal_date,
                ),
                execution_context=execution_context,
            )

            observation_candidates = list(
                getattr(screen_response, "observation_candidates", ()) or ()
            )
            total_checked = int(getattr(screen_response, "total_tickers_checked", len(tickers)))
            screen_insufficient_data += max(0, total_checked - len(observation_candidates))
            for observation in observation_candidates:
                result = getattr(observation, "screen_result", "")
                if result == "pass":
                    screen_pass += 1
                elif result == "rejected_flow":
                    screen_rejected_flow += 1
                elif result == "rejected_signal":
                    screen_rejected_signal += 1
                else:
                    # Unknown reject class — keep visible via rejected_flow bucket.
                    screen_rejected_flow += 1

            for candidate in screen_response.candidates:
                exclusion = self._filter_exclusion_reason(candidate, request, signal_date)
                if exclusion is not None:
                    audit_filter_excluded += 1
                    continue
                record = self._record_builder.build(
                    candidate=candidate,
                    signal_date=signal_date,
                    horizon_days=request.horizon_days,
                    policy=request.policy,
                )
                if record is None:
                    skipped_no_forward_data += 1
                    continue
                records.append(record)

        claim_stamp = AccumulationAuditClaimStamp()
        skip_ledger = AccumulationAuditSkipLedger(
            screen_pass=screen_pass,
            screen_rejected_flow=screen_rejected_flow,
            screen_rejected_signal=screen_rejected_signal,
            screen_insufficient_data=screen_insufficient_data,
            audit_filter_excluded=audit_filter_excluded,
            skipped_no_forward_data=skipped_no_forward_data,
            included_records=len(records),
        )
        warnings = [
            claim_stamp.survivorship_warning,
            claim_stamp.setup_contract_note,
            claim_stamp.source_availability_note,
            claim_stamp.overlapping_horizon_note,
            (
                "evaluation_role=DESCRIPTIVE; outcome_basis=raw_market; "
                "costs_modeled=false — not promotion-grade OOS or net-executable"
            ),
        ]

        return AccumulationAuditResponse(
            start_date=request.start_date,
            end_date=request.end_date,
            window_days=request.window_days,
            total_replay_dates=len(replay_dates),
            total_tickers=len(tickers),
            total_records=len(records),
            skipped_no_forward_data=skipped_no_forward_data,
            records=records,
            group_stats=self._statistics_builder.build(records, request.policy),
            exit_simulations=(
                self._exit_simulator.simulate(records, request) if request.simulate_exits else []
            ),
            warnings=warnings,
            skip_ledger=skip_ledger,
            claim_stamp=claim_stamp,
        )

    def _validate_policy(self, policy: AccumulationAuditPolicy) -> None:
        """Validate tunable measurement policy values."""
        if any(horizon <= 0 for horizon in policy.forward_return_horizons):
            raise ValueError("forward_return_horizons must contain positive days")
        if policy.forward_fetch_buffer_days < 0:
            raise ValueError("forward_fetch_buffer_days cannot be negative")
        if policy.exit_fetch_buffer_days < 0:
            raise ValueError("exit_fetch_buffer_days cannot be negative")
        if policy.broker_quality_window_sessions <= 0:
            raise ValueError("broker_quality_window_sessions must be positive")
        if policy.same_day_exit_priority not in {"stop_first", "target_first"}:
            raise ValueError("same_day_exit_priority must be stop_first or target_first")

    def _validate_exit_simulation_request(
        self,
        request: AccumulationAuditRequest,
    ) -> None:
        """Validate exit simulation parameter grids."""
        if not request.take_profit_pcts:
            raise ValueError("take_profit_pcts is required when simulate_exits is enabled")
        if not request.stop_loss_pcts:
            raise ValueError("stop_loss_pcts is required when simulate_exits is enabled")
        if not request.max_hold_days:
            raise ValueError("max_hold_days is required when simulate_exits is enabled")
        if any(v <= 0 for v in request.take_profit_pcts):
            raise ValueError("take_profit_pcts must be positive")
        if any(v <= 0 for v in request.stop_loss_pcts):
            raise ValueError("stop_loss_pcts must be positive")
        if any(v <= 0 for v in request.max_hold_days):
            raise ValueError("max_hold_days must be positive")

    def _filter_exclusion_reason(
        self,
        candidate: AccumulationCandidate,
        request: AccumulationAuditRequest,
        signal_date: date,
    ) -> str | None:
        """Return audit-filter exclusion reason, or None if the candidate passes."""
        if request.min_vwap_disc_pct is not None:
            if candidate.vwap_discount_pct is None:
                return "audit_filter_vwap_missing"
            if candidate.vwap_discount_pct < request.min_vwap_disc_pct:
                return "audit_filter_vwap"

        if request.trend is not None:
            if candidate.trend.upper() != request.trend.upper():
                return "audit_filter_trend"

        if request.min_flow_pct is not None:
            if candidate.avg_flow_ratio is None:
                return "audit_filter_flow_missing"
            if candidate.avg_flow_ratio < request.min_flow_pct:
                return "audit_filter_flow"

        if request.require_rsi and candidate.rsi is None:
            return "audit_filter_rsi_missing"

        if request.max_rsi is not None:
            if candidate.rsi is None:
                return "audit_filter_rsi_missing"
            if candidate.rsi > request.max_rsi:
                return "audit_filter_rsi_max"

        if request.min_rsi is not None:
            if candidate.rsi is None:
                return "audit_filter_rsi_missing"
            if candidate.rsi < request.min_rsi:
                return "audit_filter_rsi_min"

        if request.max_bb_width_pctile is not None:
            if candidate.bb_width_pctile is None:
                return "audit_filter_bb_missing"
            if candidate.bb_width_pctile > request.max_bb_width_pctile:
                return "audit_filter_bb"

        if request.broker_quality is not None:
            quality = self._broker_quality_classifier.classify(
                ticker=candidate.ticker,
                signal_date=signal_date,
                window_sessions=request.policy.broker_quality_window_sessions,
            )
            if quality.lower() != request.broker_quality.lower():
                return "audit_filter_broker_quality"

        return None

    def _replay_dates(
        self,
        tickers: list[str],
        start_date: date,
        end_date: date,
    ) -> list[date]:
        """Build the union of available trading dates in the audit range."""
        dates: set[date] = set()
        for ticker in tickers:
            candles = self._market_repo.get_candles(
                ticker,
                start_date=start_date,
                end_date=end_date,
            )
            dates.update(c.date for c in candles)
        return sorted(dates)
