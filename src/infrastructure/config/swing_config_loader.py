"""
YAML loading and split-config composition for swing workflow calibration.

Layer: Infrastructure
"""

from pathlib import Path

from src.application.dto.swing_config import SwingConfig
from src.infrastructure.config.app_config import AppConfig, load_app_config
from src.infrastructure.config.swing_broker_quality_config_parser import (
    parse_broker_quality_fields,
)
from src.infrastructure.config.swing_config_composer import (
    read_single_swing_config,
    read_split_swing_config,
)
from src.infrastructure.config.swing_config_primitives import (
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


def load_swing_config(
    config_path: Path | None = None,
    config: AppConfig | None = None,
) -> SwingConfig:
    """Load swing workflow calibration params from YAML. Returns defaults on any error."""
    defaults = SwingConfig()
    try:
        if config_path:
            data = read_single_swing_config(config_path)
        else:
            app_cfg = config or load_app_config()
            data = read_split_swing_config(
                accumulation_screener_path=Path(app_cfg.config_paths.accumulation_screener),
                swing_setups_path=Path(app_cfg.config_paths.swing_setups),
                swing_targets_path=Path(app_cfg.config_paths.swing_targets),
                swing_risk_policy_path=Path(app_cfg.config_paths.swing_risk_policy),
            )
    except Exception:
        return defaults

    try:
        setups = data.get("setups") or {}
        vd = data.get("verdicts") or {}
        vd_sig = vd.get("signals") or {}
        resistance = data.get("resistance") or {}
        corporate_actions = data.get("corporate_actions") or {}
        setup_phase = data.get("setup_phase") or {}
        sc = data.get("screener") or {}
        sb = data.get("sector_breadth") or {}

        # Parse sections using specialized parsers
        bq_fields = parse_broker_quality_fields(data, defaults)
        family_fields = parse_setup_family_fields(data, defaults)
        setup_phase_config = parse_setup_phase_config(setup_phase, setups, defaults)
        setup_targets = parse_setup_targets(data.get("setup_targets"), defaults)

        return SwingConfig(
            min_market_cap_idr=int_or_default(
                sc, "min_market_cap_idr", defaults.min_market_cap_idr
            ),
            enter_min_score=float_or_default(
                vd, "enter_min_score", defaults.enter_min_score
            ),
            watch_min_score=float_or_default(
                vd, "watch_min_score", defaults.watch_min_score
            ),
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
            sector_breadth_enabled=bool_or_default(
                sb, "enabled", defaults.sector_breadth_enabled
            ),
            sector_breadth_threshold=float_or_default(
                sb, "breadth_threshold", defaults.sector_breadth_threshold
            ),
            sector_breadth_bonus_pts=float_or_default(
                sb, "bonus_pts", defaults.sector_breadth_bonus_pts
            ),
            sector_breadth_min_tickers=int_or_default(
                sb, "min_tickers_for_breadth", defaults.sector_breadth_min_tickers
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
        if "invalid setup phase name" in str(exc):
            raise
        return defaults
    except Exception:
        return defaults
