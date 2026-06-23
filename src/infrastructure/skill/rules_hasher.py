"""
Rules hasher for drift detection.

Computes SHA-256 hashes of strategy rule sections to detect
when a SKILL.md is stale relative to its source artifact.

Layer: Infrastructure
"""

import hashlib
import re
from pathlib import Path

import yaml

from src.application.ports.rules_hasher import RulesHasher as RulesHasherPort


class RulesHasher(RulesHasherPort):
    """Computes and compares hashes of strategy rules for drift detection."""

    _HASH_COMMENT_PATTERN = re.compile(r"<!--\s*rules_hash:\s*(\w+)\s*-->")

    def compute_hash(self, strategy_path: Path) -> str:
        """Compute SHA-256 hash of the indicators + rules sections.

        Args:
            strategy_path: Path to strategy.yaml.

        Returns:
            Hex-encoded SHA-256 hash string.
        """
        text = strategy_path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)

        # Extract the sections that affect SKILL.md content
        indicators = data.get("indicators", {})
        rules = data.get("rules", [])

        # Canonical representation for stable hashing
        canonical = yaml.dump(
            {"indicators": indicators, "rules": rules},
            default_flow_style=False,
            sort_keys=True,
        )

        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def extract_stored_hash(self, skill_md_path: Path) -> str | None:
        """Extract the rules_hash from an existing SKILL.md file.

        Args:
            skill_md_path: Path to the SKILL.md file.

        Returns:
            Stored hash string, or None if not found or file missing.
        """
        if not skill_md_path.exists():
            return None

        text = skill_md_path.read_text(encoding="utf-8")
        match = self._HASH_COMMENT_PATTERN.search(text)
        if match:
            return match.group(1)
        return None

    def is_stale(self, strategy_path: Path, skill_md_path: Path) -> bool:
        """Check if a SKILL.md is stale relative to its strategy.

        Args:
            strategy_path: Path to strategy.yaml.
            skill_md_path: Path to SKILL.md.

        Returns:
            True if the SKILL.md needs regeneration.
        """
        stored = self.extract_stored_hash(skill_md_path)
        if stored is None:
            return True

        current = self.compute_hash(strategy_path)
        return current != stored
