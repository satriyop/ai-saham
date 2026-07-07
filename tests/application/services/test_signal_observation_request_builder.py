from __future__ import annotations

from src.application.services.signal_observation_request_builder import (
    BuildSignalObservationScreenRequest,
)
from src.infrastructure.config.accumulation_screener_config import (
    AccumulationScreenerConfig,
    ScoreFilterConfig,
)
from src.infrastructure.config.swing_config import SwingConfig


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
