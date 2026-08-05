"""Authority firewall: sector macro must not enter Signal/Risk scoring (ADR-053)."""

from pathlib import Path

import yaml

from src.application.services import signal_alpha_trigger_projection as projection_mod
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)


def test_candidate_observation_schema_version_pin():
    """ADR-068 schema 13: the write-only ``config_hash`` payload field is gone."""
    assert CANDIDATE_OBSERVATION_SCHEMA_VERSION == 13


def test_alpha_trigger_projection_does_not_import_sector_macro():
    source = Path(projection_mod.__file__).read_text(encoding="utf-8")
    assert "SectorMacroContext" not in source
    assert "sector_macro" not in source


def test_signal_engine_yaml_has_no_sector_macro_group():
    path = Path("config/signal_engine.yaml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    se = raw.get("signal_engine") or raw
    alpha = se.get("alpha_trigger") or {}
    groups = alpha.get("group_weights") or {}
    assert "sector_macro" not in groups
    assert "sector_macro_context" not in groups
    route = alpha.get("route_fractions") or {}
    for horizon, mapping in route.items():
        if isinstance(mapping, dict):
            assert "sector_macro" not in mapping, horizon
            assert "sector_macro_context" not in mapping, horizon


def test_mce_commodity_composite_still_disabled():
    path = Path("config/market_context_engine.yaml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    mce = raw.get("market_context_engine") or raw
    commodity = (mce.get("factors") or {}).get("commodity_composite") or {}
    assert commodity.get("enabled") is False
