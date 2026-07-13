"""
Historical audit for the foreign accumulation screener.

Replays accumulation signals over historical dates and measures forward
returns from local cached market and broker data.

Layer: Application
Depends on: Domain ports and accumulation screen use case
AI usage: None
"""

from datetime import date
from typing import Any

from src.application.dto.accumulation_audit import (
    AccumulationAuditPolicy,
    AccumulationAuditRequest,
    AccumulationAuditResponse,
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
from src.application.use_case.accumulation_screen_use_case import AccumulationScreenUseCase
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository

# Compatibility re-exports: tests and adapters historically imported DTOs
# from this module. Keep these import-only; implementations live in the
# DTO/service modules above.
__all__ = [
    "AccumulationAuditPolicy",
    "AccumulationAuditRequest",
    "AccumulationAuditResponse",
    "AuditBucketPolicy",
    "AuditGroupStat",
    "AuditRecord",
    "ExitSimulationStat",
    "AccumulationAuditUseCase",
]


class AccumulationAuditUseCase:
    """
    Replay the accumulation screener and measure forward performance.

    The use case is deterministic and offline: it reads local repositories only.
    It intentionally uses the current ticker universe supplied by the caller, so
    users should treat historical results as current-universe replay unless they
    provide historical universe snapshots.
    """

    def __init__(
        self,
        broker_repository: BrokerDataRepository,
        market_repository: MarketDataRepository,
        indicator_registry: Any,
        rules_loader: RulesLoader,
        derived_feature_policy: AccumulationDerivedFeaturePolicy | None = None,
    ) -> None:
        self._broker_repo = broker_repository
        self._market_repo = market_repository
        self._derived_features = derived_feature_policy or AccumulationDerivedFeaturePolicy()
        self._screen = AccumulationScreenUseCase(
            broker_repository=broker_repository,
            market_repository=market_repository,
            indicator_registry=indicator_registry,
            rules_loader=rules_loader,
            derived_feature_policy=self._derived_features,
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
        skipped_no_forward_data = 0

        for signal_date in replay_dates:
            screen_response = self._screen.execute(
                AccumulationScreenRequest(
                    tickers=tickers,
                    window_days=request.window_days,
                    min_net_buy_days=request.min_net_buy_days,
                    min_foreign_flow_score=request.min_foreign_flow_score,
                    min_foreign_flow_score_enabled=True,
                    rsi_period=self._derived_features.rsi_period,
                    sma_period=self._derived_features.trend_sma_period,
                    as_of_date=signal_date,
                )
            )

            for candidate in screen_response.candidates:
                if not self._passes_filters(candidate, request, signal_date):
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

        warnings = [
            "Audit uses the supplied current universe; "
            "historical index membership is not reconstructed."
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
                self._exit_simulator.simulate(records, request)
                if request.simulate_exits else []
            ),
            warnings=warnings,
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

    def _passes_filters(
        self,
        candidate: AccumulationCandidate,
        request: AccumulationAuditRequest,
        signal_date: date,
    ) -> bool:
        """Apply audit-only strict filters to a replayed candidate."""
        if request.min_vwap_disc_pct is not None:
            if candidate.vwap_discount_pct is None:
                return False
            if candidate.vwap_discount_pct < request.min_vwap_disc_pct:
                return False

        if request.trend is not None:
            if candidate.trend.upper() != request.trend.upper():
                return False

        if request.min_flow_pct is not None:
            if candidate.avg_flow_ratio is None:
                return False
            if candidate.avg_flow_ratio < request.min_flow_pct:
                return False

        if request.require_rsi and candidate.rsi is None:
            return False

        if request.max_rsi is not None:
            if candidate.rsi is None:
                return False
            if candidate.rsi > request.max_rsi:
                return False

        if request.min_rsi is not None:
            if candidate.rsi is None:
                return False
            if candidate.rsi < request.min_rsi:
                return False

        if request.max_bb_width_pctile is not None:
            if candidate.bb_width_pctile is None:
                return False
            if candidate.bb_width_pctile > request.max_bb_width_pctile:
                return False

        if request.broker_quality is not None:
            quality = self._broker_quality_classifier.classify(
                ticker=candidate.ticker,
                signal_date=signal_date,
                window_sessions=request.policy.broker_quality_window_sessions,
            )
            if quality.lower() != request.broker_quality.lower():
                return False

        return True

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
