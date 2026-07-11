"""RS policy reasons for setup phase detection.

Layer: Application
Depends on: setup_phase_config + domain factor_evidence.
"""

from __future__ import annotations

from typing import Any

from src.application.services.setup_phase_config import SetupPhaseConfig
from src.domain.value_objects.factor_evidence import Freshness


def setup_phase_rs_policy_reasons(
    *,
    setup_evidence: Any | None,
    setup_family: str | None,
    cfg: SetupPhaseConfig,
    passed_gates: dict[str, bool],
) -> list[str]:
    policy = cfg.rs_policy_for(setup_family)
    if policy is None:
        return []
    freshness = getattr(setup_evidence, "rs_freshness", None)
    rs = getattr(setup_evidence, "rs_vs_ihsg_5d", None)
    if freshness != Freshness.FRESH or rs is None:
        return ["rs_policy_unavailable"]
    support_reclaim = passed_gates.get("fvwap%", False)
    if rs <= policy.hard_exclude_below:
        return [
            "rs_policy_hard_exclude: "
            f"RS {rs:.2f} <= {policy.hard_exclude_below:.2f}; "
            f"max_decision={policy.hard_exclude_max_decision}"
        ]
    if rs <= policy.lag_warning_below:
        exception = (
            " with support reclaim exception"
            if support_reclaim
            and not policy.mean_reversion_exception_requires_support_reclaim
            else ""
        )
        return [
            "rs_policy_warning: "
            f"RS {rs:.2f} <= {policy.lag_warning_below:.2f}; "
            f"max_decision={policy.warning_max_decision}{exception}"
        ]
    return ["rs_policy_passed"]
