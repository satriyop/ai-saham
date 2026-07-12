from __future__ import annotations

from datetime import date

from src.application.dto.swing_config import SwingConfig
from src.application.services.signal_observation_request_builder import (
    BuildSignalObservationScreenRequest,
)
from src.domain.value_objects.market_context import MarketContext, MarketRegime
from src.infrastructure.config.accumulation_screener_config import (
    AccumulationScreenerConfig,
    ScoreFilterConfig,
)


def test_builder_maps_swing_and_accumulation_config_to_screen_request():
    swing_config = SwingConfig(
        min_market_cap_idr=500_000_000_000,
        tier1_broker_codes=frozenset({"AK", "BK"}),
        bci_cluster_min_count=4,
        bci_stable_min_count=2,
        sector_breadth_enabled=True,
        sector_breadth_threshold=0.7,
        sector_breadth_bonus_pts=8.0,
        sector_breadth_min_tickers=5,
        resistance_gate_enabled=False,
        resistance_headroom_min_pct=6.5,
        ex_date_warning_days=14,
    )
    accumulation_config = AccumulationScreenerConfig(
        min_foreign_flow_score=ScoreFilterConfig(enabled=True, value=55.0),
        min_signal_score=ScoreFilterConfig(enabled=False, value=42.0),
    )

    request = BuildSignalObservationScreenRequest.from_configs(
        swing_config=swing_config,
        accumulation_screener_config=accumulation_config,
        min_net_buy_days=3,
        min_piotroski=6,
        strategy_name="williams-r-bounce",
    ).build(tickers=["BBCA"], window_days=30)

    assert request.tickers == ["BBCA"]
    assert request.window_days == 30
    assert request.min_net_buy_days == 3
    assert request.min_foreign_flow_score == 55.0
    assert request.min_foreign_flow_score_enabled is True
    assert request.min_signal_score == 42.0
    assert request.min_signal_score_enabled is False
    assert request.min_piotroski == 6
    assert request.tier1_broker_codes == frozenset({"AK", "BK"})
    assert request.bci_cluster_min_count == 4
    assert request.bci_stable_min_count == 2
    assert request.min_market_cap_idr == 500_000_000_000
    assert request.resistance_gate_enabled is False
    assert request.resistance_headroom_min_pct == 6.5
    assert request.ex_date_warning_days == 14
    assert request.sector_breadth_enabled is True
    assert request.sector_breadth_threshold == 0.7
    assert request.sector_breadth_bonus_pts == 8.0
    assert request.sector_breadth_min_tickers == 5
    assert request.strategy_name == "williams-r-bounce"


def test_builder_can_disable_score_filters_for_multi_observation_capture():
    builder = BuildSignalObservationScreenRequest.from_configs(
        swing_config=SwingConfig(),
        accumulation_screener_config=AccumulationScreenerConfig(
            min_foreign_flow_score=ScoreFilterConfig(enabled=True, value=70.0),
            min_signal_score=ScoreFilterConfig(enabled=True, value=45.0),
        ),
        min_net_buy_days=1,
    )

    request = builder.with_score_filters_disabled().build(
        tickers=["BBCA"],
        window_days=7,
    )

    assert request.min_foreign_flow_score == 0.0
    assert request.min_foreign_flow_score_enabled is False
    assert request.min_signal_score == 0.0
    assert request.min_signal_score_enabled is False


def test_builder_passes_market_context_through_by_identity():
    builder = BuildSignalObservationScreenRequest.from_configs(
        swing_config=SwingConfig(),
        accumulation_screener_config=AccumulationScreenerConfig(
            min_foreign_flow_score=ScoreFilterConfig(enabled=True, value=70.0),
            min_signal_score=ScoreFilterConfig(enabled=True, value=45.0),
        ),
        min_net_buy_days=1,
    )
    as_of = date(2026, 6, 1)
    market_context = MarketContext(
        regime=MarketRegime.RISK_ON,
        conviction=0.6,
        factors=(),
        signal_multiplier=1.0,
        gate_tightening=False,
        as_of_date=as_of,
        regime_confidence=0.8,
        regime_stability="STABLE",
        days_in_regime=6,
    )

    request = builder.build(
        tickers=["BBCA"],
        window_days=7,
        as_of_date=as_of,
        market_context=market_context,
    )

    assert request.market_context is market_context


def test_builder_defaults_market_context_to_none_when_not_supplied():
    builder = BuildSignalObservationScreenRequest.from_configs(
        swing_config=SwingConfig(),
        accumulation_screener_config=AccumulationScreenerConfig(
            min_foreign_flow_score=ScoreFilterConfig(enabled=True, value=70.0),
            min_signal_score=ScoreFilterConfig(enabled=True, value=45.0),
        ),
        min_net_buy_days=1,
    )

    request = builder.build(tickers=["BBCA"], window_days=7)

    assert request.market_context is None
