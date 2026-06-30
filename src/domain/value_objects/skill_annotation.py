"""
Skill annotation value objects.

Defines types for skill documentation sidecar metadata.
Annotations are semantic only — no logic, thresholds, or formulas.

Layer: Domain
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ArtifactType(Enum):
    """Type of artifact that can have skill annotations."""

    STRATEGY = "STRATEGY"
    INDICATOR = "INDICATOR"
    FORMULA = "FORMULA"

    @classmethod
    def parse(cls, value: str) -> "ArtifactType":
        """Parse canonical uppercase and legacy lowercase artifact types."""
        normalized = value.strip().upper().replace("-", "_")
        for artifact_type in cls:
            if normalized in {artifact_type.name, artifact_type.value}:
                return artifact_type
        valid = [artifact_type.value for artifact_type in cls]
        raise ValueError(f"Invalid artifact type '{value}'. Must be one of: {valid}")


@dataclass(frozen=True)
class SkillAnnotation:
    """Semantic annotation for an artifact.

    Read from a sidecar .skill.yaml file. Contains only descriptive
    metadata — never logic, thresholds, or formulas.

    Attributes:
        description: What this artifact does.
        when_to_use: When/why to use this artifact.
        tags: Optional categorization tags.
        limitations: Optional known limitations.
        examples: Optional usage examples.
    """

    description: str
    when_to_use: str
    tags: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate required fields are non-empty."""
        if not self.description or not self.description.strip():
            raise ValueError("SkillAnnotation.description must not be empty")
        if not self.when_to_use or not self.when_to_use.strip():
            raise ValueError("SkillAnnotation.when_to_use must not be empty")


@dataclass(frozen=True)
class DriftInfo:
    """Tracks whether a SKILL.md is stale relative to its source artifact.

    Attributes:
        rules_hash: Current SHA-256 hash of the artifact's rules section.
        is_stale: Whether the stored hash differs from the current hash.
        stored_hash: Hash previously embedded in the SKILL.md file (None if no SKILL.md).
    """

    rules_hash: str
    is_stale: bool
    stored_hash: str | None


@dataclass(frozen=True)
class SkillMetadata:
    """Complete metadata for generating a SKILL.md file.

    Combines artifact identification, sidecar annotations, and
    auto-detected metadata into a single generation input.

    Attributes:
        artifact_type: Type of artifact (strategy, indicator, formula).
        artifact_name: Human-readable name.
        artifact_path: Path to the source artifact file.
        annotation: Parsed sidecar annotation (None if missing).
        cli_usage: CLI command examples for this artifact.
        dependencies: Indicator/formula names this artifact depends on.
        data_requirements: Data sources needed (e.g., "broker_flow", "ohlcv").
        rules_summary: Brief description of each rule.
        drift: Drift detection info (None for non-strategy artifacts).
    """

    artifact_type: ArtifactType
    artifact_name: str
    artifact_path: Path
    annotation: SkillAnnotation | None
    cli_usage: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    data_requirements: tuple[str, ...] = ()
    rules_summary: tuple[str, ...] = ()
    drift: DriftInfo | None = None
