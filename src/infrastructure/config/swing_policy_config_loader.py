"""
YAML loading and split-config composition for swing workflow calibration.

Layer: Infrastructure
"""

import logging
from pathlib import Path

from src.application.dto.swing_policy_config import SwingPolicyConfig
from src.infrastructure.config.app_config import AppConfig, load_app_config
from src.infrastructure.config.swing_broker_quality_config_parser import (
    parse_broker_quality_fields,
)
from src.infrastructure.config.swing_policy_config_composer import (
    read_single_swing_policy_config,
    read_split_swing_policy_config,
)
from src.infrastructure.config.swing_policy_config_primitives import (
    bool_or_default,
    float_or_default,
    int_or_default,
)
from src.infrastructure.config.swing_setup_family_config_parser import (
    parse_setup_family_fields,
)
from src.infrastructure.config.swing_setup_phase_config_parser import (
    parse_setup_phase_config,
)
from src.infrastructure.config.swing_targets_config_parser import (
    parse_setup_targets,
)

logger = logging.getLogger(__name__)


def load_swing_policy_config(
    config_path: Path | None = None,
    config: AppConfig | None = None,
) -> SwingPolicyConfig:
    """Load swing workflow calibration params from YAML. Returns defaults on any error."""
    defaults = SwingPolicyConfig()
    try:
        if config_path:
            data = read_single_swing_policy_config(config_path)
        else:
            app_cfg = config or load_app_config()
            data = read_split_swing_policy_config(
                accumulation_screener_path=Path(app_cfg.config_paths.accumulation_screener),
                swing_setups_path=Path(app_cfg.config_paths.swing_setups),
                swing_targets_path=Path(app_cfg.config_paths.swing_targets),
                swing_risk_policy_path=Path(app_cfg.config_paths.swing_risk_policy),
            )
    except Exception:
        logger.warning("Could not read swing config; falling back to defaults", exc_info=True)
        return defaults

    try:
        setups = data.get("setups") or {}
        vd = data.get("verdicts") or {}
        vd_sig = vd.get("signals") or {}
        resistance = data.get("resistance") or {}
        corporate_actions = data.get("corporate_actions") or {}
        setup_phase = data.get("setup_phase") or {}
        sc = data.get("screener") or {}
        if "sector_breadth" in data:
            raise ValueError(
                "accumulation_screener.sector_breadth is retired by ADR-062; "
                "remove the block from config (group-breadth score bonus is not "
                "production policy)"
            )

        # Parse sections using specialized parsers
        bq_fields = parse_broker_quality_fields(data, defaults)
        family_fields = parse_setup_family_fields(data, defaults)
        setup_phase_config = parse_setup_phase_config(setup_phase, setups, defaults)
        setup_targets = parse_setup_targets(data.get("setup_targets"), defaults)

        return SwingPolicyConfig(
            min_market_cap_idr=int_or_default(
                sc, "min_market_cap_idr", defaults.min_market_cap_idr
            ),
            enter_min_score=float_or_default(vd, "enter_min_score", defaults.enter_min_score),
            watch_min_score=float_or_default(vd, "watch_min_score", defaults.watch_min_score),
            strong_min_score=float_or_default(
                vd_sig, "strong_min_score", defaults.strong_min_score
            ),
            strong_min_streak=int_or_default(
                vd_sig, "strong_min_streak", defaults.strong_min_streak
            ),
            building_min_score=float_or_default(
                vd_sig, "building_min_score", defaults.building_min_score
            ),
            building_min_streak=int_or_default(
                vd_sig, "building_min_streak", defaults.building_min_streak
            ),
            coiled_spring_bb_pctile=float_or_default(
                vd_sig, "coiled_spring_bb_pctile", defaults.coiled_spring_bb_pctile
            ),
            coiled_spring_min_score=float_or_default(
                vd_sig, "coiled_spring_min_score", defaults.coiled_spring_min_score
            ),
            resistance_gate_enabled=bool_or_default(
                resistance, "enabled", defaults.resistance_gate_enabled
            ),
            resistance_headroom_min_pct=float_or_default(
                resistance, "headroom_min_pct", defaults.resistance_headroom_min_pct
            ),
            ex_date_warning_days=int_or_default(
                corporate_actions, "ex_date_warning_days", defaults.ex_date_warning_days
            ),
            setup_targets=setup_targets,
            setup_phase_config=setup_phase_config,
            **bq_fields,
            **family_fields,
        )
    except ValueError as exc:
        msg = str(exc)
        if "invalid setup phase name" in msg or "sector_breadth is retired" in msg:
            raise
        logger.warning(
            "Swing config contains invalid values; falling back to defaults",
            exc_info=True,
        )
        return defaults
    except (AttributeError, TypeError, NameError):
        # These are programmer errors (a renamed field, a bad kwarg), never bad
        # operator config — the *_or_default primitives already absorb bad user
        # values. Swallowing them here silently voids the entire config file with
        # no signal (see: accumulation_min_flow_score rename). Fail loud instead.
        raise
    except Exception:
        logger.warning(
            "Unexpected error loading swing config; falling back to defaults",
            exc_info=True,
        )
        return defaults
