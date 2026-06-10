"""
Skill writer port.

Defines the interface for rendering and writing SKILL.md files.

Layer: Application (Port)
"""

from abc import ABC, abstractmethod
from pathlib import Path

from src.domain.value_objects.skill_annotation import SkillMetadata


class SkillWriter(ABC):
    """Port for rendering and writing skill documentation."""

    @abstractmethod
    def render_skill(self, metadata: SkillMetadata) -> str:
        """Render a SKILL.md content string from metadata.

        Args:
            metadata: Complete skill metadata for the artifact.

        Returns:
            Rendered markdown content.
        """
        ...

    @abstractmethod
    def write_skill(self, metadata: SkillMetadata, path: Path) -> None:
        """Render and write a SKILL.md file to disk.

        Args:
            metadata: Complete skill metadata for the artifact.
            path: Output path for the SKILL.md file.
        """
        ...
