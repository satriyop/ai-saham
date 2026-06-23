"""
RulesHasher port - interface for computing and comparing strategy rules hashes.

Layer: Application
"""

from abc import ABC, abstractmethod
from pathlib import Path


class RulesHasher(ABC):
    """Port interface for strategy rules hash computations for drift detection."""

    @abstractmethod
    def compute_hash(self, strategy_path: Path) -> str:
        """Compute hash of indicators + rules sections for strategy.yaml.

        Args:
            strategy_path: Path to strategy.yaml.

        Returns:
            Hex-encoded hash string.
        """
        pass

    @abstractmethod
    def extract_stored_hash(self, skill_md_path: Path) -> str | None:
        """Extract stored rules_hash from an existing SKILL.md.

        Args:
            skill_md_path: Path to SKILL.md.

        Returns:
            Stored hash or None if not found.
        """
        pass

    @abstractmethod
    def is_stale(self, strategy_path: Path, skill_md_path: Path) -> bool:
        """Check if SKILL.md is stale relative to its strategy.

        Args:
            strategy_path: Path to strategy.yaml.
            skill_md_path: Path to SKILL.md.

        Returns:
            True if stale and needs regeneration.
        """
        pass
