"""Semantic classification for swing tuning config targets.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.services.swing_tuning_config_paths import TuningConfigPath


@dataclass(frozen=True)
class TuningTargetClassification:
    """Derived semantic classification for one YAML tuning target."""

    target_family: str
    target_kind: str
    target_parameter: str

    @classmethod
    def from_path(
        cls,
        target_path: TuningConfigPath | None,
    ) -> TuningTargetClassification:
        if target_path is None:
            return cls(
                target_family="unknown",
                target_kind="unknown",
                target_parameter="unknown",
            )
        return cls(
            target_family=_classify_tuning_target_family(target_path),
            target_kind=_classify_tuning_target_kind(target_path),
            target_parameter=_tuning_target_parameter(target_path),
        )

    def to_dict(self) -> dict:
        return {
            "target_family": self.target_family,
            "target_kind": self.target_kind,
            "target_parameter": self.target_parameter,
        }


def _classify_tuning_target_family(target_path: TuningConfigPath) -> str:
    file_name = target_path.file_path.rsplit("/", maxsplit=1)[-1]
    stem = file_name.rsplit(".", maxsplit=1)[0]
    return {
        "signal_engine": "signal_engine",
        "swing_risk_policy": "risk_policy",
        "swing_setups": "swing_setup",
        "market_context_engine": "market_context",
    }.get(stem, stem or "unknown")


def _classify_tuning_target_kind(target_path: TuningConfigPath) -> str:
    document_path = target_path.document_path
    leaf = _tuning_target_parameter(target_path)
    segments = document_path.split(".")
    if "classification" in segments:
        return "classification"
    if "gates" in segments:
        return "gate"
    if "weights" in segments or leaf.endswith("_weight") or leaf == "weight":
        return "weight"
    if _is_exit_rule_parameter(leaf, segments):
        return "exit_rule"
    if _is_threshold_parameter(leaf):
        return "threshold"
    return "unknown"


def _tuning_target_parameter(target_path: TuningConfigPath) -> str:
    return target_path.document_path.rsplit(".", maxsplit=1)[-1] or "unknown"


def _is_threshold_parameter(parameter: str) -> bool:
    return (
        parameter.startswith(("min_", "max_"))
        or parameter.endswith(("_threshold", "_min", "_max", "_score"))
        or "max_failed_gates" in parameter
    )


def _is_exit_rule_parameter(
    parameter: str,
    segments: list[str],
) -> bool:
    exit_terms = (
        "exit",
        "take_profit",
        "stop_loss",
        "trailing_stop",
        "max_hold",
    )
    return any(term in parameter for term in exit_terms) or any(
        term in segment for segment in segments for term in exit_terms
    )
