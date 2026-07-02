"""Read-only YAML path helpers for swing tuning contracts.

Intent:
    Parse, expand, validate, and resolve allowlisted tuning config paths.
    This module never mutates YAML and never generates applyable diffs.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

_SETUP_GATES_WILDCARD_PATH = "setups.*.gates"
_SETUP_PARTIAL_MAX_FAILED_GATES_WILDCARD_PATH = "setups.*.partial_max_failed_gates"


@dataclass(frozen=True)
class TuningConfigPath:
    """Structured YAML path target for future config diff generation."""

    raw: str
    file_path: str
    document_path: str

    def to_dict(self) -> dict:
        return {
            "raw": self.raw,
            "file_path": self.file_path,
            "document_path": self.document_path,
        }


@dataclass(frozen=True)
class TuningConfigValueResolution:
    """Read-only result of resolving a tuning config path."""

    target_path: TuningConfigPath
    resolved: bool
    current_value: object | None = None
    unresolved_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "target_path": self.target_path.to_dict(),
            "resolved": self.resolved,
            "current_value": self.current_value,
            "unresolved_reason": self.unresolved_reason,
        }


def parse_tuning_config_path(raw_path: str) -> TuningConfigPath:
    """Parse a tuning target path in file.yaml:document.path format."""
    file_path, separator, document_path = raw_path.partition(":")
    if not separator or not file_path.strip() or not document_path.strip():
        raise ValueError(
            "Tuning config path must use 'file.yaml:document.path' format."
        )
    normalized_file_path = file_path.strip()
    if not normalized_file_path.endswith((".yaml", ".yml")):
        raise ValueError("Tuning config path file must end with .yaml or .yml.")
    return TuningConfigPath(
        raw=raw_path,
        file_path=normalized_file_path,
        document_path=document_path.strip(),
    )


def expand_tuning_config_paths(
    raw_path: str,
    config_root: Path | str = Path("."),
) -> tuple[str, ...]:
    """Expand allowlisted wildcard tuning paths into concrete YAML paths."""
    parsed_path = parse_tuning_config_path(raw_path)
    if "*" not in parsed_path.document_path:
        return (parsed_path.raw,)

    if parsed_path.file_path != "config/swing_setups.yaml":
        return (parsed_path.raw,)

    if parsed_path.document_path == _SETUP_GATES_WILDCARD_PATH:
        return _expand_swing_setup_gate_paths(parsed_path, config_root)

    if parsed_path.document_path == _SETUP_PARTIAL_MAX_FAILED_GATES_WILDCARD_PATH:
        return _expand_swing_setup_partial_gate_paths(parsed_path, config_root)

    return (parsed_path.raw,)


def validate_tuning_target_paths(summary) -> tuple[str, ...]:
    """Validate all tuning target YAML paths and return normalized raw paths."""
    parsed_paths: list[str] = []
    for target in summary.tuning_targets:
        for yaml_path in target.yaml_paths:
            parsed_paths.append(parse_tuning_config_path(yaml_path).raw)
    return tuple(parsed_paths)


def resolve_tuning_config_value(
    target_path: TuningConfigPath,
    config_root: Path | str = Path("."),
) -> TuningConfigValueResolution:
    """Resolve a concrete YAML tuning path without mutating config."""
    if "*" in target_path.document_path:
        return TuningConfigValueResolution(
            target_path=target_path,
            resolved=False,
            unresolved_reason="wildcard_path_not_resolved",
        )

    root = Path(config_root)
    yaml_path = root / target_path.file_path
    if not yaml_path.exists():
        return TuningConfigValueResolution(
            target_path=target_path,
            resolved=False,
            unresolved_reason="config_file_not_found",
        )

    with yaml_path.open(encoding="utf-8") as fh:
        document = yaml.safe_load(fh) or {}

    current: object = document
    for part in target_path.document_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return TuningConfigValueResolution(
                target_path=target_path,
                resolved=False,
                unresolved_reason="document_path_not_found",
            )
        current = current[part]

    return TuningConfigValueResolution(
        target_path=target_path,
        resolved=True,
        current_value=current,
    )


def _expand_swing_setup_gate_paths(
    target_path: TuningConfigPath,
    config_root: Path | str,
) -> tuple[str, ...]:
    document = _load_yaml_document(target_path.file_path, config_root)
    setups = document.get("setups") if isinstance(document, dict) else None
    if not isinstance(setups, dict):
        return (target_path.raw,)

    expanded_paths: list[str] = []
    for setup_name, setup_config in setups.items():
        if not isinstance(setup_config, dict):
            continue
        gates = setup_config.get("gates")
        if not isinstance(gates, dict):
            continue
        for gate_name in gates:
            expanded_paths.append(
                f"{target_path.file_path}:setups.{setup_name}.gates.{gate_name}"
            )
    return tuple(expanded_paths) or (target_path.raw,)


def _expand_swing_setup_partial_gate_paths(
    target_path: TuningConfigPath,
    config_root: Path | str,
) -> tuple[str, ...]:
    document = _load_yaml_document(target_path.file_path, config_root)
    setups = document.get("setups") if isinstance(document, dict) else None
    if not isinstance(setups, dict):
        return (target_path.raw,)

    expanded_paths = tuple(
        f"{target_path.file_path}:setups.{setup_name}.partial_max_failed_gates"
        for setup_name, setup_config in setups.items()
        if isinstance(setup_config, dict)
        and "partial_max_failed_gates" in setup_config
    )
    return expanded_paths or (target_path.raw,)


def _load_yaml_document(
    file_path: str,
    config_root: Path | str,
) -> dict:
    yaml_path = Path(config_root) / file_path
    if not yaml_path.exists():
        return {}
    with yaml_path.open(encoding="utf-8") as fh:
        document = yaml.safe_load(fh) or {}
    return document if isinstance(document, dict) else {}
