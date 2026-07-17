"""
AccumulationCandidateEvaluator service.

Evaluates and builds accumulation candidate metrics.

Layer: Application
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from src.application.dto import accumulation_screen as accumulation_dto
from src.application.dto.accumulation_screen import AccumulationCandidateEvaluationResult
from src.application.services.accumulation_technical_features import (
    compute_accumulation_rsi,
    compute_accumulation_trend,
    compute_bb_squeeze,
    compute_resistance_levels,
)
from src.application.services.stats import foreign_vwap_discount_pct
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.idx_market import SHARES_PER_LOT

# Broker Concentration Index (BCI) tiers
BCI_CLUSTER = "CLUSTER"  # 3+ Tier 1 codes in window top net-buyers → +15 pts
BCI_STABLE = "STABLE"  # 1–2 Tier 1 codes                         → +5 pts
BCI_RETAIL = "RETAIL-LED"  # 0 Tier 1 codes                           → +0 pts


def _is_usable_broker_summary(summary) -> bool:
    """Return True when a broker summary is safe for accumulation metrics."""
    return (
        summary.total_value > Decimal("0")
        and summary.total_lot >= 0
        and summary.foreign_buy_lot >= 0
        and summary.foreign_sell_lot >= 0
    )


def _filter_own_rows(rows: list, *, ticker: str, today: date) -> list:
    """Defense in depth: never trust a repository's ticker/end_date scoping
    alone. A faulty reader leaking a future or foreign-ticker row must not
    reach calculations or provenance — this filter is the last line before
    either. Applied identically to candles, broker summaries, and broker
    daily flows."""
    return [row for row in rows if row.ticker == ticker and row.date <= today]


def select_broker_window(
    broker_repository: BrokerDataRepository,
    *,
    ticker: str,
    today: date,
    window_days: int,
) -> tuple[list, list]:
    """Fetch and window-select the exact broker summary/daily-flow rows for
    one ticker, identically to `AccumulationCandidateEvaluator.evaluate()`.

    Shared by the evaluator and `SwingAnalysisEvidenceBuilder` so both
    independently-computed flow evidence groups window the same way and
    never drift apart. Returns `(window_summaries, window_flows)`, both
    already future/ticker-filtered.
    """
    summaries = broker_repository.get_broker_summaries(
        ticker=ticker, start_date=None, end_date=today
    )
    summaries = _filter_own_rows(summaries, ticker=ticker, today=today)
    summaries = [s for s in summaries if _is_usable_broker_summary(s)]
    window_summaries = sorted(summaries, key=lambda s: s.date)[-window_days:]

    daily_flows = broker_repository.get_broker_daily_flows(ticker=ticker, end_date=today)
    daily_flows = _filter_own_rows(daily_flows, ticker=ticker, today=today)
    window_dates = {s.date for s in window_summaries}
    window_flows = [f for f in daily_flows if f.date in window_dates]

    return window_summaries, window_flows


class AccumulationCandidateEvaluator:
    def __init__(
        self,
        broker_repository: BrokerDataRepository,
        market_repository: MarketDataRepository,
        derived_feature_policy: accumulation_dto.AccumulationDerivedFeaturePolicy,
    ) -> None:
        self._broker_repo = broker_repository
        self._market_repo = market_repository
        self._derived_features = derived_feature_policy

    def evaluate(
        self,
        ticker: str,
        window_days: int,
        today: date,
        min_net_buy_days: int,
        rsi_period: int,
        sma_period: int,
        tier1_broker_codes: frozenset[str] = accumulation_dto.TIER1_FOREIGN_BROKERS,
        bci_cluster_min_count: int = 3,
        bci_stable_min_count: int = 1,
    ) -> AccumulationCandidateEvaluationResult | None:
        """Compute accumulation metrics for one ticker."""
        # Load all broker rows up to as_of_date, then select the latest N
        # broker sessions. Calendar-day cutoffs distort IDX windows around
        # weekends, holidays, and data-lag days.
        window_summaries, window_flows = select_broker_window(
            self._broker_repo, ticker=ticker, today=today, window_days=window_days
        )

        if not window_summaries or len(window_summaries) < min_net_buy_days:
            return None

        # Core accumulation metrics
        net_buy_days = sum(1 for s in window_summaries if s.is_foreign_accumulating)
        total_days = len(window_summaries)
        net_buy_ratio = net_buy_days / total_days if total_days > 0 else 0.0
        total_net_value = sum((s.foreign_net_value for s in window_summaries), Decimal("0"))

        # Consecutive buy streak (counting backwards from most recent)
        streak = 0
        for s in sorted(window_summaries, key=lambda x: x.date, reverse=True):
            if s.is_foreign_accumulating:
                streak += 1
            else:
                break

        # Foreign VWAP
        total_buy_value = sum((s.foreign_buy_value for s in window_summaries), Decimal("0"))
        total_buy_lots = sum(s.foreign_buy_lot for s in window_summaries)
        foreign_vwap: Decimal | None = None
        if total_buy_lots > 0:
            try:
                foreign_vwap = (total_buy_value / (total_buy_lots * SHARES_PER_LOT)).quantize(
                    Decimal("0.01")
                )
            except InvalidOperation:
                foreign_vwap = None

        # Avg foreign flow ratio (% of total daily turnover, already in BrokerSummary)
        flow_ratios = [float(s.foreign_flow_ratio) for s in window_summaries if s.total_value > 0]
        avg_flow_ratio = sum(flow_ratios) / len(flow_ratios) if flow_ratios else None

        latest_broker_date = window_summaries[-1].date if window_summaries else None

        # Load candles for price + RSI + trend + BB squeeze
        candles = self._market_repo.get_candles(ticker, end_date=today)
        candles = _filter_own_rows(candles, ticker=ticker, today=today)
        if not candles:
            current_price = Decimal("0")
            rsi = None
            trend = "SIDE"
            bb_width = None
            bb_width_pctile = None
            latest_candle_date = None
        else:
            current_price = candles[-1].close
            latest_candle_date = candles[-1].date
            rsi = compute_accumulation_rsi(candles, rsi_period)
            trend = compute_accumulation_trend(
                candles,
                sma_period,
                trend_threshold_pct=self._derived_features.trend_threshold_pct,
            )
            bb_width, bb_width_pctile = compute_bb_squeeze(
                candles,
                period=self._derived_features.bb_period,
                history=self._derived_features.bb_history,
            )

        # Resistance proximity (MA200 and 52-week high)
        ma200, week52_high, nearest_resistance_pct = compute_resistance_levels(
            candles,
            current_price,
            resistance_ma_period=self._derived_features.resistance_ma_period,
            resistance_high_period=self._derived_features.resistance_high_period,
        )

        # Foreign VWAP discount % — how far foreigners' avg buy is above current price
        vwap_discount_pct = foreign_vwap_discount_pct(foreign_vwap, current_price)

        # Market VWAP % — how far current price is from 20-day all-participant VWAP
        # Negative = price below VWAP (constructive; entering below market average cost basis)
        vwap_pct: float | None = None
        if candles:
            try:
                vwap_window = candles[-self._derived_features.market_vwap_period :]
                total_vol = sum(c.volume for c in vwap_window)
                if total_vol > 0:
                    total_tpv = sum(
                        (c.high + c.low + c.close) / Decimal("3") * c.volume for c in vwap_window
                    )
                    market_vwap = total_tpv / total_vol
                    if market_vwap > 0:
                        vwap_pct = float((current_price - market_vwap) / market_vwap * 100)
            except (InvalidOperation, ZeroDivisionError):
                pass

        # Granular broker info from per-day broker_daily_flow (Stockbit only).
        # These are real daily rows — never period aggregates.
        top_brokers: list[str] | None = None
        institutional_flag = False
        bci_label: str | None = None
        bci_tier1_count: int = 0

        latest_broker_daily_flow_date: date | None = None
        if window_flows:
            latest_broker_daily_flow_date = max(f.date for f in window_flows)
            # Aggregate net_lot per broker across the window
            from collections import defaultdict

            broker_net: dict[str, int] = defaultdict(int)
            for f in window_flows:
                broker_net[f.broker_code] += f.net_lot

            net_buyers = sorted(
                [(code, net) for code, net in broker_net.items() if net > 0],
                key=lambda x: x[1],
                reverse=True,
            )
            if net_buyers:
                top_brokers = [code for code, _ in net_buyers[:5]]
                # BCI: count all Tier 1 codes among any net-buyers (not just top 5)
                all_net_buyer_codes = {code for code, _ in net_buyers}
                bci_tier1_count = len(all_net_buyer_codes & tier1_broker_codes)
                if bci_tier1_count >= bci_cluster_min_count:
                    bci_label = BCI_CLUSTER
                elif bci_tier1_count >= bci_stable_min_count:
                    bci_label = BCI_STABLE
                else:
                    bci_label = BCI_RETAIL
                institutional_flag = bci_tier1_count > 0

        candidate = accumulation_dto.AccumulationCandidate(
            ticker=ticker,
            window_days=window_days,
            net_buy_days=net_buy_days,
            total_days=total_days,
            net_buy_ratio=net_buy_ratio,
            total_net_value=total_net_value,
            consecutive_streak=streak,
            foreign_vwap=foreign_vwap,
            current_price=current_price,
            vwap_discount_pct=vwap_discount_pct,
            rsi=rsi,
            trend=trend,
            foreign_flow_score=0.0,  # populated later by ScoreForeignFlowUseCase
            top_brokers=top_brokers,
            institutional_flag=institutional_flag,
            bci_label=bci_label,
            bci_tier1_count=bci_tier1_count,
            vwap_pct=vwap_pct,
            avg_flow_ratio=avg_flow_ratio,
            bb_width=bb_width,
            bb_width_pctile=bb_width_pctile,
            ma200=ma200,
            week52_high=week52_high,
            nearest_resistance_pct=nearest_resistance_pct,
            latest_candle_date=latest_candle_date,
            latest_broker_date=latest_broker_date,
            latest_broker_daily_flow_date=latest_broker_daily_flow_date,
        )
        return AccumulationCandidateEvaluationResult(
            candidate=candidate,
            consumed_candles=tuple(candles),
            consumed_broker_summaries=tuple(window_summaries),
            consumed_broker_daily_flows=tuple(window_flows),
            analysis_date=today,
        )
