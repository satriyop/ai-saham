"""Pure typed semantic-contract registry — deterministic hash resolution.

Layer: Application (pure, stateless; no I/O, no persistence)
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping

from src.domain.value_objects.signal_artifact_identity import (
    SemanticCompatibilityDimensions,
)
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
    SIGNAL_FORWARD_LABEL_SCHEMA_VERSION,
)
from src.domain.value_objects.signal_semantic_contract import (
    SemanticContractDefinition,
)
from src.domain.value_objects.signal_forward_label import SignalLabelHorizon
from src.domain.value_objects.alpha_trigger_score import EvidenceRegistration


def _fail(value: object, msg: str) -> None:
    raise ValueError(msg)


def _reject_strategy_enabled(strategy_name: str | None) -> None:
    if strategy_name is not None:
        raise ValueError(
            "strategy-enabled artifacts are unsupported until strategy-package "
            "identity is implemented"
        )


def _canonicalize_unordered_strings(
    value: object,
    path: str,
    casefold,
) -> list[str]:
    """Canonicalize an explicitly-unordered string collection before hashing.

    Reordering, duplicate members, whitespace, and case-only differences must
    not change identity; adding, removing, or replacing a member must.
    """
    if not isinstance(value, (list, tuple)):
        _fail(
            value,
            f"{path}: unordered normalization path must be a list or tuple, "
            f"got {type(value).__name__}",
        )
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            _fail(
                item,
                f"{path}: unordered normalization member must be a string, "
                f"got {type(item).__name__}",
            )
        cleaned = casefold(item.strip())
        if not cleaned:
            _fail(
                item,
                f"{path}: unordered normalization member must not be empty "
                "after normalization",
            )
        normalized.append(cleaned)
    return sorted(set(normalized))


def _canonicalize_unordered_integers(value: object, path: str) -> list[int]:
    """Canonicalize an explicitly-unordered integer-window collection.

    [20, 30] == [30, 20]; [20, 30] != [20, 30, 20]; [20, 30] != [20]. Strings
    and floats are not silently cast — only actual ints are accepted, and bool
    (an int subclass) is explicitly rejected.
    """
    if not isinstance(value, (list, tuple)):
        _fail(
            value,
            f"{path}: unordered integer normalization path must be a list "
            f"or tuple, got {type(value).__name__}",
        )
    normalized: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            _fail(
                item,
                f"{path}: unordered integer normalization member must be an "
                f"int, got {type(item).__name__}",
            )
        normalized.append(item)
    return sorted(normalized)


_COMMODITY_COMPONENT_ALLOWED_KEYS = frozenset({"ticker", "weight"})
_COMMODITY_COMPONENT_ROLES = ("cpo", "coal")


def _classify_commodity_role(ticker: str) -> str:
    """Match the current runtime parser's classification exactly:
    load_market_context_config() treats a case-sensitive "KO" substring in
    the ticker as the CPO leg; every other ticker is the coal leg."""
    return "cpo" if "KO" in ticker else "coal"


def _canonicalize_commodity_components(value: object, path: str) -> list[dict[str, object]]:
    """Canonicalize commodity_composite.components by runtime role.

    Specialized to the current two-leg (cpo, coal) parser contract, not a
    generic object-list sorter: exactly one cpo and one coal component are
    required, ticker/weight are preserved verbatim (both affect runtime
    configuration), and unsupported keys fail closed rather than being
    silently ignored.
    """
    if not isinstance(value, (list, tuple)):
        _fail(
            value,
            f"{path}: commodity component normalization path must be a list "
            f"or tuple, got {type(value).__name__}",
        )

    classified: dict[str, dict[str, object]] = {}
    for i, item in enumerate(value):
        if not isinstance(item, dict):
            _fail(
                item,
                f"{path}[{i}]: commodity component must be a mapping, "
                f"got {type(item).__name__}",
            )
        extra_keys = set(item.keys()) - _COMMODITY_COMPONENT_ALLOWED_KEYS
        if extra_keys:
            _fail(
                item,
                f"{path}[{i}]: commodity component has unsupported keys "
                f"{sorted(extra_keys)!r}",
            )
        if "ticker" not in item or "weight" not in item:
            _fail(
                item,
                f"{path}[{i}]: commodity component must have exactly "
                "'ticker' and 'weight' keys",
            )
        ticker = item["ticker"]
        if not isinstance(ticker, str) or not ticker.strip():
            _fail(ticker, f"{path}[{i}].ticker: must be a non-empty string")
        weight = item["weight"]
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            _fail(
                weight,
                f"{path}[{i}].weight: must be a finite int or float, "
                f"got {type(weight).__name__}",
            )
        if isinstance(weight, float) and (math.isnan(weight) or math.isinf(weight)):
            _fail(weight, f"{path}[{i}].weight: must be finite")

        role = _classify_commodity_role(ticker)
        if role in classified:
            _fail(ticker, f"{path}: duplicate {role!r} role component")
        classified[role] = {
            "role": role,
            "ticker": ticker,
            "weight": float(weight),
        }

    for required_role in _COMMODITY_COMPONENT_ROLES:
        if required_role not in classified:
            _fail(value, f"{path}: missing required {required_role!r} role component")

    return [classified[role] for role in sorted(classified)]


def _require_json_compatible(value: object, path: str) -> None:
    if isinstance(value, str):
        return
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            _fail(value, f"{path}: non-finite float not allowed")
        return
    if isinstance(value, (type(None),)):
        return
    if isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            _require_json_compatible(item, f"{path}[{i}]")
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                _fail(value, f"{path}.key({k!r}): dict key must be str")
            _require_json_compatible(v, f"{path}.{k}")
        return
    _fail(value, f"{path}: unsupported type {type(value).__name__}")


def _canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _sha256_hex(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        _canonical_json(payload).encode("utf-8"),
    ).hexdigest()


class SignalSemanticContractRegistry:
    """Pure registry that resolves SemanticCompatibilityDimensions.

    Every method is deterministic given identical inputs.
    No I/O, no persistence, no side effects.
    """

    def __init__(self, definition: SemanticContractDefinition) -> None:
        if not isinstance(definition, SemanticContractDefinition):
            raise TypeError("definition must be SemanticContractDefinition")
        self._definition = definition

    @property
    def definition(self) -> SemanticContractDefinition:
        return self._definition

    def resolve_observation(
        self,
        *,
        observation_contract: str,
        setup_family: str | None,
        strategy_name: str | None,
        material_config_values: Mapping[str, object],
        authority_registrations: Mapping[str, EvidenceRegistration],
    ) -> SemanticCompatibilityDimensions:
        if observation_contract != self._definition.observation_contract:
            _fail(
                observation_contract,
                f"unknown observation_contract {observation_contract!r}; "
                f"expected {self._definition.observation_contract!r}",
            )
        _reject_strategy_enabled(strategy_name)

        evaluation_horizon = self._resolve_evaluation_horizon(material_config_values)
        paths = self._definition.material_paths_for(
            setup_family=setup_family,
            evaluation_horizon=evaluation_horizon,
        )
        material_hash = self._hash_material_config(
            paths, material_config_values,
        )
        authority_hash = self._hash_authority_registrations(
            self._definition.authority_registration_names,
            authority_registrations,
        )

        return SemanticCompatibilityDimensions(
            observation_contract=observation_contract,
            setup_family=setup_family,
            evidence_contract_version=self._definition.evidence_contract_version,
            observation_schema_version=self._definition.observation_schema_version,
            label_schema_version=None,
            semantic_engine_version=self._definition.semantic_engine_version,
            material_config_hash=material_hash,
            authority_registrations_hash=authority_hash,
            execution_label_policy_version=None,
        )

    def resolve_label(
        self,
        *,
        observation_contract: str,
        setup_family: str | None,
        strategy_name: str | None,
        horizon: SignalLabelHorizon,
        material_config_values: Mapping[str, object],
        authority_registrations: Mapping[str, EvidenceRegistration],
    ) -> SemanticCompatibilityDimensions:
        if observation_contract != self._definition.observation_contract:
            _fail(
                observation_contract,
                f"unknown observation_contract {observation_contract!r}; "
                f"expected {self._definition.observation_contract!r}",
            )
        _reject_strategy_enabled(strategy_name)

        evaluation_horizon = self._resolve_evaluation_horizon(material_config_values)
        paths = self._definition.material_paths_for(
            setup_family=setup_family,
            evaluation_horizon=evaluation_horizon,
        )
        material_hash = self._hash_material_config(
            paths, material_config_values,
        )
        authority_hash = self._hash_authority_registrations(
            self._definition.authority_registration_names,
            authority_registrations,
        )
        label_policy_version = self._definition.label_policy_version(
            horizon.value,
        )

        return SemanticCompatibilityDimensions(
            observation_contract=observation_contract,
            setup_family=setup_family,
            evidence_contract_version=self._definition.evidence_contract_version,
            observation_schema_version=self._definition.observation_schema_version,
            label_schema_version=self._definition.label_schema_version,
            semantic_engine_version=self._definition.semantic_engine_version,
            material_config_hash=material_hash,
            authority_registrations_hash=authority_hash,
            execution_label_policy_version=label_policy_version,
        )

    def _resolve_evaluation_horizon(
        self,
        material_config_values: Mapping[str, object],
    ) -> str:
        path = "signal_engine.alpha_trigger.default_horizon"
        if path not in material_config_values:
            _fail(
                path,
                f"missing required material config path {path!r}",
            )
        value = material_config_values[path]
        if not isinstance(value, str):
            _fail(
                value,
                f"{path}: must be a string, got {type(value).__name__}",
            )
        known_horizons = [
            h for h, _ in self._definition.material_config_paths_by_evaluation_horizon
        ]
        if value not in known_horizons:
            _fail(
                value,
                f"{path}: unknown evaluation horizon {value!r}; known: {known_horizons}",
            )
        return value

    def _hash_material_config(
        self,
        declared_paths: tuple[str, ...],
        values: Mapping[str, object],
    ) -> str:
        upper_paths = set(self._definition.unordered_upper_string_config_paths)
        lower_paths = set(self._definition.unordered_lower_string_config_paths)
        integer_paths = set(self._definition.unordered_integer_config_paths)
        commodity_paths = set(self._definition.commodity_component_config_paths)

        selected: dict[str, object] = {}
        for path in declared_paths:
            if path not in values:
                _fail(
                    path,
                    f"missing required material config path {path!r}",
                )
            val = values[path]
            _require_json_compatible(val, path)
            if path in upper_paths:
                val = _canonicalize_unordered_strings(val, path, str.upper)
            elif path in lower_paths:
                val = _canonicalize_unordered_strings(val, path, str.lower)
            elif path in integer_paths:
                val = _canonicalize_unordered_integers(val, path)
            elif path in commodity_paths:
                val = _canonicalize_commodity_components(val, path)
            selected[path] = val

        return _sha256_hex(selected)

    @staticmethod
    def _hash_authority_registrations(
        declared_names: tuple[str, ...],
        registrations: Mapping[str, EvidenceRegistration],
    ) -> str:
        for name in declared_names:
            if name not in registrations:
                _fail(
                    name,
                    f"missing required authority registration {name!r}",
                )

        selected: dict[str, object] = {}
        for name in sorted(declared_names):
            reg = registrations[name]
            if not isinstance(reg, EvidenceRegistration):
                raise TypeError(
                    f"authority registration {name!r} must be an "
                    f"EvidenceRegistration, got {type(reg).__name__}"
                )
            if reg.evidence_name != name:
                _fail(
                    reg.evidence_name,
                    f"authority registration key {name!r} does not match "
                    f"registration.evidence_name {reg.evidence_name!r}",
                )
            selected[name] = {
                "evidence_name": reg.evidence_name,
                "status": reg.status.value,
                "low_weight_cap": reg.low_weight_cap,
            }

        return _sha256_hex(selected)
