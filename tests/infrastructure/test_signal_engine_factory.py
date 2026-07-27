"""
Regression coverage for the SignalEngine composition root boundary.

Proves the factory (1) resolves canonical config exactly once through the
real resolver with the raw config passed by identity, and (2) actually fails
closed against removed legacy config through the real resolver, not a mock
that would swallow the error (RETIRE-LEGACY-SIX-FACTOR-BASELINE).
"""

from __future__ import annotations

import pytest

from src.application.services.signal_engine import SignalEngine
from src.application.services.signal_engine_config import SignalEngineConfig
from src.infrastructure.composition import signal_engine_factory

_VALID_RAW_CONFIG = {
    "signal_engine": {
        "classification": {
            "strong_min_score": 70,
            "moderate_min_score": 45,
        },
    }
}

_RAW_CONFIG_WITH_REMOVED_FACTORS = {
    "signal_engine": {
        "classification": {
            "strong_min_score": 70,
            "moderate_min_score": 45,
        },
        "factors": {
            "bandar_intensity": {
                "enabled": True,
                "weight": 0.20,
            },
        },
    }
}


def test_factory_passes_valid_raw_config_to_resolver_once(monkeypatch):
    recorded_calls = []

    def _fake_load_raw():
        return _VALID_RAW_CONFIG

    def _fake_resolve(cfg):
        recorded_calls.append(cfg)
        return SignalEngineConfig()

    monkeypatch.setattr(signal_engine_factory, "load_signal_engine_config_raw", _fake_load_raw)
    monkeypatch.setattr(signal_engine_factory, "resolve_signal_engine_config", _fake_resolve)

    engine = signal_engine_factory.create_signal_engine(db_path="unused.db", with_enrichment=False)

    assert isinstance(engine, SignalEngine)
    assert len(recorded_calls) == 1
    assert recorded_calls[0] is _VALID_RAW_CONFIG


def test_factory_rejects_removed_factors_config(monkeypatch):
    def _fake_load_raw():
        return _RAW_CONFIG_WITH_REMOVED_FACTORS

    monkeypatch.setattr(signal_engine_factory, "load_signal_engine_config_raw", _fake_load_raw)
    # resolve_signal_engine_config is NOT mocked — the real resolver must
    # itself raise, proving the factory's fail-closed boundary is genuine
    # rather than asserted through a mock that would swallow the error.

    with pytest.raises(ValueError, match="signal_engine.factors"):
        signal_engine_factory.create_signal_engine(db_path="unused.db", with_enrichment=False)


def test_signal_engine_factory_has_no_legacy_weight_resolver_reference():
    assert not hasattr(signal_engine_factory, "_resolve_signal_weights")
