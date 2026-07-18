"""
Signal engine config resolving compatibility facade.

Historically this module owned all signal-engine config resolving. That
behavior now lives in dedicated section resolver modules:

- `signal_decision_policy_config_resolver` — decision policy resolving
- `signal_alpha_trigger_config_resolver` — alpha/trigger + evidence authority
- `signal_scoring_config_resolver` — full SignalEngineConfig composition

This module re-exports the tested-private API so existing imports keep
working unchanged. No implementation logic, no infrastructure imports.
"""

from __future__ import annotations

from src.application.services.engine_bootstrap.signal_alpha_trigger_config_resolver import (
    resolve_alpha_trigger_config as _resolve_alpha_trigger_config,
)
from src.application.services.engine_bootstrap.signal_scoring_config_resolver import (
    resolve_signal_engine_config as _resolve_signal_config,
)

__all__ = [
    "_resolve_alpha_trigger_config",
    "_resolve_signal_config",
]
