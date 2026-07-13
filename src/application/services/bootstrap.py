"""
Application bootstrap compatibility facade.

Historically this module owned all engine config resolving, evidence
authority validation, and factory construction for the indicator registry,
risk engine, and signal engine. That behavior now lives in the
`src.application.services.engine_bootstrap` package (pure config resolving)
and `src.infrastructure.composition` (concrete engine/registry wiring):

- `engine_bootstrap.evidence_authority_validation` — promotion record validation
- `engine_bootstrap.signal_weight_config_resolver` — signal factor weight resolving
- `engine_bootstrap.signal_archived_config_warnings` — archived config warnings
- `engine_bootstrap.signal_decision_policy_config_resolver` — decision policy resolving
- `engine_bootstrap.signal_alpha_trigger_config_resolver` — alpha/trigger resolving
- `engine_bootstrap.signal_scoring_config_resolver` — full SignalEngineConfig composition
- `engine_bootstrap.signal_config_resolvers` — signal engine config compatibility facade
- `engine_bootstrap.risk_config_resolvers` — risk engine config resolving
- `infrastructure.composition.indicator_registry_factory` — IndicatorRegistry construction
- `infrastructure.composition.risk_engine_factory` — RiskEngine construction
- `infrastructure.composition.signal_engine_factory` — SignalEngine construction

This module re-exports only the pure config-resolving API. Concrete engine
construction (create_indicator_registry, create_risk_engine,
create_signal_engine) requires infrastructure wiring and must be imported
from src.infrastructure.composition directly — application must not import
infrastructure (see tests/architecture/test_layer_boundaries.py).

Compatibility surface:
- Canonical package:
  - src.application.services.engine_bootstrap (see submodules listed above)
- Allowed contents:
  - imports and __all__ only. No new implementation may be added here.
- Expiry:
  - permanent public API unless all internal/external imports migrate to
    src.application.services.engine_bootstrap directly.
"""

from __future__ import annotations

from src.application.services.engine_bootstrap.risk_config_resolvers import (
    _resolve_indicator_evaluator_config,
    _resolve_market_context_gate,
    _resolve_risk_gates,
    _resolve_risk_indicator_defaults,
    _resolve_technical_gate_config,
)
from src.application.services.engine_bootstrap.signal_config_resolvers import (
    _resolve_signal_config,
)
from src.application.services.engine_bootstrap.signal_weight_config_resolver import (
    resolve_signal_weight_tables,
)

__all__ = [
    "resolve_signal_weight_tables",
    "_resolve_indicator_evaluator_config",
    "_resolve_market_context_gate",
    "_resolve_risk_gates",
    "_resolve_risk_indicator_defaults",
    "_resolve_signal_config",
    "_resolve_technical_gate_config",
]
