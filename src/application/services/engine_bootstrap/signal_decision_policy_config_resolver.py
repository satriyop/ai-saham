"""
Signal engine decision policy config resolving.

Pure config normalization for the decision policy section of
signal_engine.yaml: regime policy, setup/regime actions, and setup/regime
policy mapping. No engine construction, no infrastructure wiring.
"""

from __future__ import annotations

from src.application.services.signal_engine_config import (
    DecisionPolicyConfig,
    RegimeDecisionPolicyConfig,
    SetupRegimeActionConfig,
)

_ALLOWED_REGIMES = {"RISK_ON", "NEUTRAL", "RISK_OFF", "VOLATILE"}
_ALLOWED_DECISIONS = {"ENTER", "WATCH", "AVOID"}


def resolve_decision_policy_config(decision_cfg: dict) -> DecisionPolicyConfig:
    default_policy = DecisionPolicyConfig()
    if not decision_cfg:
        return default_policy

    regime_cfg = decision_cfg.get("regime_policy")
    if not isinstance(regime_cfg, dict):
        raise ValueError("signal_engine.decision_policy.regime_policy is required")

    missing = _ALLOWED_REGIMES - set(regime_cfg)
    extra = set(regime_cfg) - _ALLOWED_REGIMES
    if missing:
        raise ValueError(
            "signal_engine.decision_policy.regime_policy missing regimes: "
            + ", ".join(sorted(missing))
        )
    if extra:
        raise ValueError(
            "signal_engine.decision_policy.regime_policy has unknown regimes: "
            + ", ".join(sorted(extra))
        )

    resolved_regimes = {}
    for regime in sorted(_ALLOWED_REGIMES):
        raw = regime_cfg[regime] or {}
        decision = raw.get("max_decision")
        if decision not in _ALLOWED_DECISIONS:
            raise ValueError(
                f"Invalid max_decision for {regime}: {decision!r}"
            )
        if "min_signal_authority_coverage" not in raw:
            raise ValueError(
                "signal_engine.decision_policy.regime_policy."
                f"{regime}.min_signal_authority_coverage is required"
            )
        min_signal_authority_coverage = float(
            raw["min_signal_authority_coverage"]
        )
        if not (0.0 <= min_signal_authority_coverage <= 1.0):
            raise ValueError(
                f"signal_engine.decision_policy.regime_policy.{regime}."
                "min_signal_authority_coverage must be within [0.0, 1.0], got "
                f"{min_signal_authority_coverage!r}"
            )
        resolved_regimes[regime] = RegimeDecisionPolicyConfig(
            enter_allowed=bool(raw.get("enter_allowed", True)),
            max_decision=decision,
            regime_size_multiplier=float(raw.get("regime_size_multiplier", 1.0)),
            enter_threshold=raw.get("enter_threshold"),
            watch_threshold=int(raw.get("watch_threshold", 45)),
            min_signal_authority_coverage=min_signal_authority_coverage,
        )

    raw_actions = decision_cfg.get("setup_regime_actions", {})
    resolved_actions = dict(default_policy.setup_regime_actions)
    for name, raw in raw_actions.items():
        decision = (raw or {}).get("max_decision")
        if decision not in _ALLOWED_DECISIONS:
            raise ValueError(
                f"Invalid setup_regime_actions.{name}.max_decision: {decision!r}"
            )
        resolved_actions[name] = SetupRegimeActionConfig(max_decision=decision)

    raw_setup_policy = decision_cfg.get("setup_regime_policy", {})
    resolved_setup_policy: dict[str, dict[str, str]] = {}
    for family, by_regime in raw_setup_policy.items():
        if not isinstance(by_regime, dict):
            raise ValueError(f"setup_regime_policy.{family} must map regimes to actions")
        resolved_family: dict[str, str] = {}
        for regime, action_name in by_regime.items():
            if regime not in _ALLOWED_REGIMES:
                raise ValueError(
                    f"Invalid setup_regime_policy.{family} regime: {regime!r}"
                )
            if action_name not in resolved_actions:
                raise ValueError(
                    f"Invalid setup_regime_policy.{family}.{regime} action: "
                    f"{action_name!r}"
                )
            resolved_family[regime] = action_name
        resolved_setup_policy[family] = resolved_family

    return DecisionPolicyConfig(
        regime_policy=resolved_regimes,
        setup_regime_policy=resolved_setup_policy,
        setup_regime_actions=resolved_actions,
    )
