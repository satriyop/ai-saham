from decimal import Decimal
from pathlib import Path

from src.application.dto.swing_config import SwingConfig
from src.infrastructure.config.swing_broker_quality_config_parser import parse_broker_quality_fields
from src.infrastructure.config.swing_config_composer import read_single_swing_config
from src.infrastructure.config.swing_config_primitives import (
    bool_or_default,
    broker_codes_or_default,
    float_or_default,
    int_or_default,
    phase_names_or_default,
    str_or_default,
)
from src.infrastructure.config.swing_setup_family_config_parser import parse_setup_family_fields
from src.infrastructure.config.swing_targets_config_parser import parse_setup_targets


def test_primitives_float():
    d = {"val": 4.5}
    assert float_or_default(d, "val", 1.0) == 4.5
    assert float_or_default(d, "missing", 1.0) == 1.0


def test_primitives_int():
    d = {"val": 4}
    assert int_or_default(d, "val", 1) == 4
    assert int_or_default(d, "missing", 1) == 1


def test_primitives_str():
    d = {"val": "hello"}
    assert str_or_default(d, "val", "default") == "hello"
    assert str_or_default(d, "missing", "default") == "default"


def test_primitives_bool():
    d = {"val": True}
    assert bool_or_default(d, "val", False) is True
    assert bool_or_default(d, "missing", False) is False


def test_primitives_phases():
    d = {"phases": ["accumulation", " compression "]}
    assert phase_names_or_default(d, "phases", ()) == ("ACCUMULATION", "COMPRESSION")
    assert phase_names_or_default(d, "missing", ("DEFAULT",)) == ("DEFAULT",)


def test_primitives_brokers():
    d = {"brokers": ["ak", " zp "]}
    assert broker_codes_or_default(d, ()) == ("AK", "ZP")
    assert broker_codes_or_default({}, ("KZ",)) == ("KZ",)


def test_parse_setup_targets():
    defaults = SwingConfig()
    raw = {
        "risk_on": {
            "take_profit_pct": 10.0,
            "stop_loss_pct": 5.0,
        }
    }
    parsed = parse_setup_targets(raw, defaults)
    assert parsed["risk_on"].take_profit_pct == Decimal("10.0")
    assert parsed["risk_on"].stop_loss_pct == Decimal("5.0")


def test_parse_broker_quality_fields():
    defaults = SwingConfig()
    data = {
        "broker_quality": {
            "smart_money": {
                "brokers": ["ak"],
                "weight": 2.0,
            },
            "noise": {
                "brokers": ["yp"],
                "weight": 0.2,
            },
            "smart_share_threshold_pct": 55.0,
        }
    }
    fields = parse_broker_quality_fields(data, defaults)
    assert fields["smart_money_brokers"] == ("AK",)
    assert fields["noise_brokers"] == ("YP",)
    assert fields["smart_weight"] == Decimal("2.0")
    assert fields["noise_weight"] == Decimal("0.2")
    assert fields["smart_share_threshold_pct"] == 55.0


def test_parse_setup_family_fields():
    defaults = SwingConfig()
    data = {
        "setups": {
            "foreign-bounce": {
                "enabled": False,
                "family": "bounce",
                "entry_authority": False,
                "can_enter_from_phases": ["accumulation"],
                "gates": {
                    "min_accum_score": 50.0,
                },
            }
        }
    }
    fields = parse_setup_family_fields(data, defaults)
    assert fields["foreign_bounce_enabled"] is False
    assert fields["foreign_bounce_family"] == "bounce"
    assert fields["foreign_bounce_entry_authority"] is False
    assert fields["foreign_bounce_can_enter_from_phases"] == ("ACCUMULATION",)
    assert fields["gate_min_accum_score"] == 50.0


def test_read_single_swing_config_non_existent():
    assert read_single_swing_config(Path("non_existent_file.yaml")) == {}
