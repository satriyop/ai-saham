"""
Regression coverage for the SignalEngine composition root boundary.

Proves malformed archived signal_engine.factors.* config cannot participate in
canonical engine construction, and that no legacy weight resolver is imported
or invoked through the factory module (RETIRE-LEGACY-SIX-FACTOR-BASELINE Slice 1).
"""

from __future__ import annotations

from src.application.services.signal_engine import SignalEngine
from src.application.services.signal_engine_config import SignalEngineConfig
from src.infrastructure.composition import signal_engine_factory

_MALFORMED_RAW_CONFIG = {
    "signal_engine": {
        "factors": {
            "legacy_invalid": {
                "enabled": True,
                "weight": "not-a-number",
            }
        }
    }
}


def test_signal_engine_factory_never_calls_legacy_weight_resolver(monkeypatch):
    recorded_calls = []

    def _fake_load_raw():
        return _MALFORMED_RAW_CONFIG

    def _fake_resolve(cfg):
        recorded_calls.append(cfg)
        return SignalEngineConfig()

    monkeypatch.setattr(
        signal_engine_factory, "load_signal_engine_config_raw", _fake_load_raw
    )
    monkeypatch.setattr(
        signal_engine_factory, "resolve_signal_engine_config", _fake_resolve
    )

    engine = signal_engine_factory.create_signal_engine(
        db_path="unused.db", with_enrichment=False
    )

    assert isinstance(engine, SignalEngine)
    assert len(recorded_calls) == 1
    assert recorded_calls[0] is _MALFORMED_RAW_CONFIG


def test_signal_engine_factory_has_no_legacy_weight_resolver_reference():
    assert not hasattr(signal_engine_factory, "_resolve_signal_weights")
