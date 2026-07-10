"""Canonical request builder for persisted signal observation screens."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import TYPE_CHECKING, Any

from src.application.dto.accumulation_screen import AccumulationScreenRequest

if TYPE_CHECKING:
    from src.domain.value_objects.market_context import MarketContext


@dataclass(frozen=True)
class BuildSignalObservationScreenRequest:
    """Build accumulation screen requests for live and historical observations."""

    min_net_buy_days: int
    min_foreign_flow_score: float
    min_foreign_flow_score_enabled: bool
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
        swing_config: Any,
        accumulation_screener_config: Any,
        min_net_buy_days: int,
        min_foreign_flow_score: float | None = None,
        min_signal_score: float | None = None,
        min_piotroski: int = 0,
        strategy_name: str | None = None,
        disable_score_filters: bool = False,
    ) -> "BuildSignalObservationScreenRequest":
        if disable_score_filters:
            foreign_flow_score = 0.0
            foreign_flow_enabled = False
            signal_score = 0.0
            signal_score_enabled = False
        else:
            foreign_filter = accumulation_screener_config.min_foreign_flow_score
            signal_filter = accumulation_screener_config.min_signal_score
            foreign_flow_enabled = bool(foreign_filter.enabled)
            signal_score_enabled = bool(signal_filter.enabled)
            if min_foreign_flow_score is None:
                foreign_flow_score = float(foreign_filter.value)
            else:
                foreign_flow_score = float(min_foreign_flow_score)
                foreign_flow_enabled = True
            if min_signal_score is None:
                signal_score = float(signal_filter.value)
            else:
                signal_score = float(min_signal_score)
                signal_score_enabled = True

        return cls(
            min_net_buy_days=max(1, int(min_net_buy_days)),
            min_foreign_flow_score=foreign_flow_score,
            min_foreign_flow_score_enabled=foreign_flow_enabled,
            min_signal_score=signal_score,
            min_signal_score_enabled=signal_score_enabled,
            min_piotroski=int(min_piotroski),
            tier1_broker_codes=frozenset(swing_config.tier1_broker_codes),
            bci_cluster_min_count=int(swing_config.bci_cluster_min_count),
            bci_stable_min_count=int(swing_config.bci_stable_min_count),
            min_market_cap_idr=int(swing_config.min_market_cap_idr),
            resistance_gate_enabled=bool(swing_config.resistance_gate_enabled),
            resistance_headroom_min_pct=float(swing_config.resistance_headroom_min_pct),
            ex_date_warning_days=int(swing_config.ex_date_warning_days),
            sector_breadth_enabled=bool(swing_config.sector_breadth_enabled),
            sector_breadth_threshold=float(swing_config.sector_breadth_threshold),
            sector_breadth_bonus_pts=float(swing_config.sector_breadth_bonus_pts),
            sector_breadth_min_tickers=int(swing_config.sector_breadth_min_tickers),
            strategy_name=strategy_name,
        )

    def with_score_filters_disabled(self) -> "BuildSignalObservationScreenRequest":
        return replace(
            self,
            min_foreign_flow_score=0.0,
            min_foreign_flow_score_enabled=False,
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
            min_foreign_flow_score=self.min_foreign_flow_score,
            min_foreign_flow_score_enabled=self.min_foreign_flow_score_enabled,
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
