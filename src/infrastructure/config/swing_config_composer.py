"""
YAML loading and configuration composition.

Layer: Infrastructure
"""

from pathlib import Path
from typing import Any

import yaml


def _read_yaml(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        return {}


def _merge_section(data: dict, raw: dict, key: str) -> None:
    section = raw.get(key)
    if isinstance(section, dict):
        data[key] = section


def read_single_swing_config(config_path: Path | None) -> dict:
    return _read_yaml(config_path) if config_path else {}


def read_split_swing_config(
    accumulation_screener_path: Path,
    swing_setups_path: Path,
    swing_targets_path: Path,
    swing_risk_policy_path: Path,
) -> dict:
    data: dict[str, Any] = {}

    accumulation_raw = _read_yaml(accumulation_screener_path)
    accumulation = accumulation_raw.get("accumulation_screener") or accumulation_raw
    if isinstance(accumulation, dict):
        for key in ("screener", "sector_breadth", "broker_quality", "verdicts"):
            _merge_section(data, accumulation, key)

    for path, keys in (
        (
            swing_setups_path,
            ("setups", "setup_targets", "resistance", "corporate_actions", "setup_phase"),
        ),
        (
            swing_targets_path,
            ("setups", "setup_targets", "resistance", "corporate_actions"),
        ),
        (
            swing_risk_policy_path,
            ("setups", "setup_targets", "resistance", "corporate_actions"),
        ),
    ):
        raw = _read_yaml(path)
        for key in keys:
            _merge_section(data, raw, key)

    return data
