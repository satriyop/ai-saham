"""Resolve accumulation production policies once for corpus wiring.

Layer: Adapter (composition). Owns config I/O; application owns the typed
bundle and engines/use cases consume the resulting objects by identity.
"""

from __future__ import annotations

from pathlib import Path

from src.application.services.accumulation_production_policy_bundle import (
    AccumulationProductionPolicyBundle,
)
from src.application.services.engine_bootstrap.risk_config_resolvers import (
    resolve_risk_gates,
)
from src.application.services.engine_bootstrap.signal_scoring_config_resolver import (
    resolve_signal_engine_config,
)
from src.application.use_case.score_accum_use_case import AccumScorePolicy
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.engine_config_loader import load_engine_config
from src.infrastructure.config.signal_engine_config_loader import (
    load_signal_engine_config_raw,
)


def resolve_accumulation_production_policy_bundle(
    *,
    accum_score_policy: AccumScorePolicy,
    risk_config_path: Path | None = None,
) -> AccumulationProductionPolicyBundle:
    """Load Signal/Risk config once and freeze the typed production policy set.

    ``accum_score_policy`` must be the same instance later injected into the
    accumulation screen / ScoreAccum path (typically
    ``load_accumulation_screener_config().accum_score_policy``).
    """
    cfg = load_app_config()
    signal_engine_config = resolve_signal_engine_config(load_signal_engine_config_raw())
    path = risk_config_path or Path(cfg.config_paths.risk_engine)
    structural, execution = resolve_risk_gates(load_engine_config(path))
    return AccumulationProductionPolicyBundle(
        accum_score_policy=accum_score_policy,
        signal_engine_config=signal_engine_config,
        structural_gates=tuple(structural),
        execution_gates=tuple(execution),
    )
