"""Canonical request builder for persisted signal observation screens."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import TYPE_CHECKING, Any

from src.application.dto.accumulation_screen import AccumulationScreenRequest
from src.application.services.accumulation_screen_hard_filter_policy import (
    AccumulationScreenHardFilterPolicy,
    resolve_accumulation_screen_hard_filter_policy,
)

if TYPE_CHECKING:
    from src.domain.value_objects.market_context import MarketContext


@dataclass(frozen=True)
class BuildSignalObservationScreenRequest:
    """Build accumulation screen requests for live and historical observations."""

    min_net_buy_days: int
    min_accum_score: float
    min_accum_score_enabled: bool
    min_signal_score: float
    min_signal_score_enabled: bool
    min_piotroski: int
    tier1_broker_codes: frozenset[str]
    bci_cluster_min_count: int
    bci_stable_min_count: int
    min_market_cap_idr: int
    resistance_gate_enabled: bool
    resistance_headroom_min_pct: float
    ex_date_warning_days: int
    sector_breadth_enabled: bool
    sector_breadth_threshold: float
    sector_breadth_bonus_pts: float
    sector_breadth_min_tickers: int
    strategy_name: str | None = None

    @classmethod
    def from_configs(
        cls,
        *,
        swing_policy: Any,
        accumulation_screener_config: Any,
        min_net_buy_days: int,
        min_accum_score: float | None = None,
        min_signal_score: float | None = None,
        min_piotroski: int = 0,
        strategy_name: str | None = None,
        disable_score_filters: bool = False,
        hard_filter_policy: AccumulationScreenHardFilterPolicy | None = None,
    ) -> "BuildSignalObservationScreenRequest":
        """Build from typed configs.

        When ``hard_filter_policy`` is supplied it is the authority for the four
        hard-filter knobs (production snapshot object). Optional CLI overrides
        and ``disable_score_filters`` apply only when constructing without a
        pre-resolved policy, or when neutralizing a derived capture request.
        """
        if hard_filter_policy is None:
            hard_filter_policy = resolve_accumulation_screen_hard_filter_policy(
                swing_policy=swing_policy,
                accumulation_screener_config=accumulation_screener_config,
                min_accum_score=min_accum_score,
                min_signal_score=min_signal_score,
                min_piotroski=min_piotroski,
            )
        elif min_accum_score is not None or min_signal_score is not None or min_piotroski != 0:
            # Explicit policy is the authority; overrides must not silently diverge.
            raise ValueError(
                "hard_filter_policy cannot be combined with score/piotroski overrides; "
                "resolve a new policy object instead"
            )

        accum_score = hard_filter_policy.min_accum_score
        foreign_flow_enabled = hard_filter_policy.min_accum_score_enabled
        signal_score = hard_filter_policy.min_signal_score
        signal_score_enabled = hard_filter_policy.min_signal_score_enabled
        if disable_score_filters:
            accum_score = 0.0
            foreign_flow_enabled = False
            signal_score = 0.0
            signal_score_enabled = False

        return cls(
            min_net_buy_days=max(1, int(min_net_buy_days)),
            min_accum_score=accum_score,
            min_accum_score_enabled=foreign_flow_enabled,
            min_signal_score=signal_score,
            min_signal_score_enabled=signal_score_enabled,
            min_piotroski=int(hard_filter_policy.min_piotroski),
            tier1_broker_codes=frozenset(swing_policy.tier1_broker_codes),
            bci_cluster_min_count=int(swing_policy.bci_cluster_min_count),
            bci_stable_min_count=int(swing_policy.bci_stable_min_count),
            min_market_cap_idr=int(hard_filter_policy.min_market_cap_idr),
            resistance_gate_enabled=bool(swing_policy.resistance_gate_enabled),
            resistance_headroom_min_pct=float(swing_policy.resistance_headroom_min_pct),
            ex_date_warning_days=int(swing_policy.ex_date_warning_days),
            sector_breadth_enabled=bool(swing_policy.sector_breadth_enabled),
            sector_breadth_threshold=float(swing_policy.sector_breadth_threshold),
            sector_breadth_bonus_pts=float(swing_policy.sector_breadth_bonus_pts),
            sector_breadth_min_tickers=int(swing_policy.sector_breadth_min_tickers),
            strategy_name=strategy_name,
        )

    def with_score_filters_disabled(self) -> "BuildSignalObservationScreenRequest":
        return replace(
            self,
            min_accum_score=0.0,
            min_accum_score_enabled=False,
            min_signal_score=0.0,
            min_signal_score_enabled=False,
        )

    def build(
        self,
        *,
        tickers: list[str],
        window_days: int,
        as_of_date: date | None = None,
        market_context: "MarketContext | None" = None,
    ) -> AccumulationScreenRequest:
        return AccumulationScreenRequest(
            tickers=tickers,
            window_days=int(window_days),
            min_net_buy_days=self.min_net_buy_days,
            min_accum_score=self.min_accum_score,
            min_accum_score_enabled=self.min_accum_score_enabled,
            min_signal_score=self.min_signal_score,
            min_signal_score_enabled=self.min_signal_score_enabled,
            min_piotroski=self.min_piotroski,
            tier1_broker_codes=self.tier1_broker_codes,
            bci_cluster_min_count=self.bci_cluster_min_count,
            bci_stable_min_count=self.bci_stable_min_count,
            min_market_cap_idr=self.min_market_cap_idr,
            resistance_gate_enabled=self.resistance_gate_enabled,
            resistance_headroom_min_pct=self.resistance_headroom_min_pct,
            ex_date_warning_days=self.ex_date_warning_days,
            sector_breadth_enabled=self.sector_breadth_enabled,
            sector_breadth_threshold=self.sector_breadth_threshold,
            sector_breadth_bonus_pts=self.sector_breadth_bonus_pts,
            sector_breadth_min_tickers=self.sector_breadth_min_tickers,
            strategy_name=self.strategy_name,
            as_of_date=as_of_date,
            market_context=market_context,
        )
