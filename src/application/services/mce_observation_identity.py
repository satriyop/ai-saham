"""MCE / regime observation identity — config cohort tag for replay-safe snapshots.

Layer: Application (pure, deterministic, no I/O)

Mirrors lean observation identity for candidate_observations: a whole-config
hash plus run-context (universe_name, benchmark_ticker) so retuning
``market_context_engine.yaml`` forks a new cohort instead of silently
overwriting date-keyed history.

Legacy rows use ``semantic_compatibility_id == ''`` and are not canonical for
config-tuned research proving.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from src.domain.value_objects.signal_artifact_identity import SemanticCompatibilityId

MARKET_CONTEXT_REGIME_CONTRACT = "market-context-regime"
MCE_ENGINE_VERSION = "1.0"


@dataclass(frozen=True)
class MceObservationIdentity:
    """Cohort identity persisted on regime_observations / market_context_snapshots."""

    observation_contract: str
    semantic_compatibility_id: SemanticCompatibilityId
    universe_name: str
    benchmark_ticker: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.observation_contract, str)
            or not self.observation_contract.strip()
            or self.observation_contract != self.observation_contract.strip()
        ):
            raise ValueError(
                "observation_contract must be a non-empty trimmed string, got "
                f"{self.observation_contract!r}"
            )
        if not isinstance(self.semantic_compatibility_id, SemanticCompatibilityId):
            raise ValueError(
                "semantic_compatibility_id must be a SemanticCompatibilityId, got "
                f"{type(self.semantic_compatibility_id).__name__}"
            )
        if not isinstance(self.universe_name, str):
            raise ValueError("universe_name must be a str")
        if not isinstance(self.benchmark_ticker, str):
            raise ValueError("benchmark_ticker must be a str")

    @property
    def cohort_id(self) -> str:
        return str(self.semantic_compatibility_id)


def resolve_mce_semantic_compatibility_id(
    *,
    resolved_mce_config_canonical: str,
    universe_name: str,
    benchmark_ticker: str,
) -> SemanticCompatibilityId:
    """Hash MCE YAML + universe + benchmark into a compatibility cohort tag.

    ``resolved_mce_config_canonical`` is the deterministic config text (typically
    raw ``market_context_engine.yaml``). Adapter/factory owns I/O; this function
    only hashes.
    """
    if not isinstance(resolved_mce_config_canonical, str):
        raise ValueError(
            "resolved_mce_config_canonical must be a str, got "
            f"{type(resolved_mce_config_canonical).__name__}"
        )
    universe = (universe_name or "").strip().lower()
    benchmark = (benchmark_ticker or "").strip().upper()
    digest = hashlib.sha256(
        (
            resolved_mce_config_canonical
            + "\0"
            + universe
            + "\0"
            + benchmark
            + "\0"
            + MCE_ENGINE_VERSION
        ).encode("utf-8")
    ).hexdigest()
    return SemanticCompatibilityId("sha256:" + digest)


def build_mce_observation_identity(
    *,
    resolved_mce_config_canonical: str,
    universe_name: str,
    benchmark_ticker: str,
) -> MceObservationIdentity:
    return MceObservationIdentity(
        observation_contract=MARKET_CONTEXT_REGIME_CONTRACT,
        semantic_compatibility_id=resolve_mce_semantic_compatibility_id(
            resolved_mce_config_canonical=resolved_mce_config_canonical,
            universe_name=universe_name,
            benchmark_ticker=benchmark_ticker,
        ),
        universe_name=(universe_name or "").strip().lower(),
        benchmark_ticker=(benchmark_ticker or "").strip().upper(),
    )
