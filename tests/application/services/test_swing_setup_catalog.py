from decimal import Decimal

from src.application.dto.swing_config import SwingConfig
from src.application.services.swing_setup_catalog import build_swing_setup_catalog_config


def test_build_swing_setup_catalog_config_maps_loaded_swing_config():
    swing_config = SwingConfig(
        foreign_bounce_enabled=False,
        gate_min_accum_score=65.0,
        coiled_spring_gate_max_bb_width_pctile=0.15,
        smart_money_confirmed_gate_min_smart_flow_idr=Decimal("1000000000"),
        pullback_continuation_gate_required_trend="SIDE",
    )

    catalog = build_swing_setup_catalog_config(swing_config)

    assert catalog.foreign_bounce.enabled is False
    assert catalog.foreign_bounce.gate_min_accum_score == 65.0
    assert catalog.coiled_spring.gate_max_bb_width_pctile == 0.15
    assert catalog.smart_money_confirmed.gate_min_smart_flow_idr == Decimal("1000000000")
    assert catalog.pullback_continuation.gate_required_trend == "SIDE"
