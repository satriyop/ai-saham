"""
Forward-return record building for accumulation-audit replay.

Layer: Application
Depends on: MarketDataRepository port, broker quality classifier
AI usage: None
"""

from datetime import date, timedelta
from decimal import Decimal

from src.application.dto.accumulation_audit import AccumulationAuditPolicy, AuditRecord
from src.application.dto.accumulation_screen import AccumulationCandidate
from src.application.services.accumulation_broker_quality_classifier import (
    AccumulationBrokerQualityClassifier,
)
from src.application.services.stats import pct_change
from src.domain.ports.market_data_repository import MarketDataRepository


class AccumulationAuditRecordBuilder:
    """Convert replayed candidates into audit records with forward returns."""

    def __init__(
        self,
        market_repository: MarketDataRepository,
        broker_quality_classifier: AccumulationBrokerQualityClassifier,
    ) -> None:
        self._market_repo = market_repository
        self._broker_quality_classifier = broker_quality_classifier

    def build(
        self,
        candidate: AccumulationCandidate,
        signal_date: date,
        horizon_days: int,
        policy: AccumulationAuditPolicy,
    ) -> AuditRecord | None:
        """Convert a candidate into an audit record with forward returns."""
        forward = self._market_repo.get_candles(
            candidate.ticker,
            start_date=signal_date + timedelta(days=1),
            end_date=signal_date + timedelta(
                days=horizon_days + policy.forward_fetch_buffer_days
            ),
        )
        forward = [c for c in forward if c.date > signal_date]
        if not forward:
            return None

        price = candidate.current_price
        if price <= Decimal("0"):
            return None

        def nth_return(n: int) -> float | None:
            if len(forward) < n:
                return None
            return _pct_change(forward[n - 1].close, price)

        horizon = forward[:horizon_days]
        max_upside = max((_pct_change(c.close, price) for c in horizon), default=None)
        max_drawdown = min((_pct_change(c.close, price) for c in horizon), default=None)
        forward_returns = {
            horizon: nth_return(horizon)
            for horizon in policy.forward_return_horizons
        }

        return AuditRecord(
            signal_date=signal_date,
            ticker=candidate.ticker,
            accum_score=candidate.accum_score,
            streak=candidate.consecutive_streak,
            net_buy_ratio=candidate.net_buy_ratio,
            total_net_value=candidate.total_net_value,
            flow_pct=candidate.avg_flow_ratio,
            vwap_disc_pct=candidate.vwap_discount_pct,
            rsi=candidate.rsi,
            bb_pctile=candidate.bb_width_pctile,
            trend=candidate.trend,
            broker_quality=self._broker_quality_classifier.classify(
                ticker=candidate.ticker,
                signal_date=signal_date,
                window_sessions=policy.broker_quality_window_sessions,
            ),
            current_price=price,
            return_5d_pct=forward_returns.get(5),
            return_10d_pct=forward_returns.get(10),
            return_20d_pct=forward_returns.get(20),
            max_upside_pct=max_upside,
            max_drawdown_pct=max_drawdown,
            forward_returns_pct=forward_returns,
            signal_score=(
                candidate.signal_assessment.assessment.score
                if candidate.signal_assessment is not None
                else None
            ),
            signal_authority_coverage=(
                candidate.signal_assessment.signal_authority_coverage
                if candidate.signal_assessment is not None
                else None
            ),
        )


def _pct_change(value: Decimal, base: Decimal) -> float:
    return pct_change(value, base, precision=4)
