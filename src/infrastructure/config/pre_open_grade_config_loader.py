"""
Infrastructure-level config loader for pre-open grade config.

Layer: Infrastructure
"""

from pathlib import Path

import yaml

from src.infrastructure.config.app_config import APP_CFG


def load_pre_open_grade_config_snapshot() -> dict:
    """Load pre-open screener analysis and risk config from YAML as a snapshot."""
    try:
        path = Path(APP_CFG.config_paths.pre_open_screener)
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        analysis = data.get("analysis", {})
        risk = data.get("risk", {})
        return {
            "rsi_overbought_threshold": analysis.get("rsi_overbought_threshold"),
            "iev_intensity_unusual_threshold": analysis.get("iev_intensity_unusual_threshold"),
            "atr_range_cap_min": analysis.get("atr_range_cap_min"),
            "atr_range_cap_max": analysis.get("atr_range_cap_max"),
            "broker_backing_threshold": analysis.get("broker_backing_threshold"),
            "min_target_ticks": risk.get("min_target_ticks"),
            "tick_friction_gate": risk.get("tick_friction_gate"),
        }
    except Exception:
        return {}
