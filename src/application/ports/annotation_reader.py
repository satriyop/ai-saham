"""
AnnotationReader port - interface for reading skill annotations.

Layer: Application
"""

from abc import ABC, abstractmethod
from pathlib import Path

from src.domain.value_objects.skill_annotation import SkillAnnotation


class AnnotationReader(ABC):
    """Port interface for reading skill annotations from sidecar YAML files."""

    @abstractmethod
    def read(self, path: Path) -> SkillAnnotation | None:
        """Read a single-artifact .skill.yaml file.

        Args:
            path: Path to the .skill.yaml file.

        Returns:
            Parsed SkillAnnotation, or None if the file does not exist.
        """
        pass

    @abstractmethod
    def read_formula_annotations(self, path: Path) -> dict[str, SkillAnnotation]:
        """Read a multi-formula .skill.yaml file.

        Args:
            path: Path to formulas.skill.yaml.

        Returns:
            Dict mapping formula name to its annotation.
        """
        pass
