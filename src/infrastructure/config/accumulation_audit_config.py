"""
Accumulation audit learning-policy config loaded from config/accumulation_audit.yaml.

Layer: Infrastructure
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.application.use_case.accumulation_audit_use_case import (
    AccumulationAuditPolicy,
    AuditBucketPolicy,
)
from src.infrastructure.config.app_config import AppConfig, load_app_config


def default_accumulation_audit_config_path(config: AppConfig | None = None) -> Path:
    cfg = config or load_app_config()
    return Path(cfg.config_paths.accumulation_audit)


@dataclass(frozen=True)
class AccumulationAuditConfig:
    """Complete accumulation audit config for CLI presets and policy."""

    policy: AccumulationAuditPolicy = field(default_factory=AccumulationAuditPolicy)
    setups: dict[str, dict[str, Any]] = field(default_factory=dict)


def load_accumulation_audit_config(
    config_path: Path | None = None,
) -> AccumulationAuditConfig:
    """Load accumulation audit config including setup presets."""
    path = config_path or default_accumulation_audit_config_path()
    raw = _read_yaml(path)
    root = raw.get("accumulation_audit") or raw
    if not isinstance(root, dict):
        return AccumulationAuditConfig()
    setups_raw = root.get("setups") or {}
    setups = (
        {
            str(name).lower(): values
            for name, values in setups_raw.items()
            if isinstance(values, dict)
        }
        if isinstance(setups_raw, dict)
        else {}
    )
    return AccumulationAuditConfig(
        policy=load_accumulation_audit_policy(config_path),
        setups=setups,
    )


def load_accumulation_audit_policy(
    config_path: Path | None = None,
) -> AccumulationAuditPolicy:
    """Load accumulation audit policy. Defaults keep historical behavior."""
    defaults = AccumulationAuditPolicy()
    path = config_path or default_accumulation_audit_config_path()
    raw = _read_yaml(path)
    root = raw.get("accumulation_audit") or raw
    if not isinstance(root, dict):
        return defaults

    measurement = root.get("measurement") or {}
    execution = root.get("exit_simulation") or {}
    grouping = root.get("grouping") or {}
    bucket_edges = grouping.get("bucket_edges") or {}

    return AccumulationAuditPolicy(
        forward_return_horizons=_int_tuple(
            measurement.get("forward_return_horizons"),
            defaults.forward_return_horizons,
        ),
        forward_fetch_buffer_days=_int(
            measurement,
            "forward_fetch_buffer_days",
            defaults.forward_fetch_buffer_days,
        ),
        exit_fetch_buffer_days=_int(
            execution,
            "fetch_buffer_days",
            defaults.exit_fetch_buffer_days,
        ),
        same_day_exit_priority=_str(
            execution,
            "same_day_priority",
            defaults.same_day_exit_priority,
        ),
        broker_quality_window_sessions=_int(
            grouping,
            "broker_quality_window_sessions",
            defaults.broker_quality_window_sessions,
        ),
        group_dimensions=_str_tuple(
            grouping.get("dimensions"),
            defaults.group_dimensions,
        ),
        buckets=AuditBucketPolicy(
            accum_score=_float_tuple(
                bucket_edges.get("accum_score"),
                defaults.buckets.accum_score,
            ),
            streak=_int_tuple(bucket_edges.get("streak"), defaults.buckets.streak),
            flow_pct=_float_tuple(bucket_edges.get("flow_pct"), defaults.buckets.flow_pct),
            vwap_disc_pct=_float_tuple(
                bucket_edges.get("vwap_disc_pct"),
                defaults.buckets.vwap_disc_pct,
            ),
            rsi=_float_tuple(bucket_edges.get("rsi"), defaults.buckets.rsi),
            bb_pctile=_float_tuple(
                bucket_edges.get("bb_pctile"),
                defaults.buckets.bb_pctile,
            ),
        ),
    )


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        return {}
    return data if isinstance(data, dict) else {}


def _int(data: dict[str, Any], key: str, default: int) -> int:
    return int(data[key]) if key in data else default


def _str(data: dict[str, Any], key: str, default: str) -> str:
    return str(data[key]) if key in data else default


def _float_tuple(value: Any, default: tuple[float, ...]) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)):
        return default
    parsed = tuple(float(item) for item in value)
    return parsed if parsed else default


def _int_tuple(value: Any, default: tuple[int, ...]) -> tuple[int, ...]:
    if not isinstance(value, (list, tuple)):
        return default
    parsed = tuple(int(item) for item in value)
    return parsed if parsed else default


def _str_tuple(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return default
    parsed = tuple(str(item).strip() for item in value if str(item).strip())
    return parsed if parsed else default
