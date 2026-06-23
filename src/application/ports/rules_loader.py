"""
RulesLoader port interface - interface for loading custom rules.

Layer: Application
"""

from abc import ABC, abstractmethod
from pathlib import Path

from src.application.rules.schema import RuleSet
from src.application.services.indicator_registry import IndicatorRegistry


class RulesLoader(ABC):
    """Port interface for loading and parsing rule configurations."""

    @classmethod
    @abstractmethod
    def load(
        cls,
        path: Path | str | None = None,
        registry: IndicatorRegistry | None = None,
    ) -> RuleSet:
        """Load and validate a rules file and return a RuleSet.

        Args:
            path: Path to the YAML file.
            registry: Optional IndicatorRegistry for validating indicator references.

        Returns:
            Validated RuleSet ready for interpretation.
        """
        pass

    @classmethod
    @abstractmethod
    def load_from_string(
        cls,
        content: str,
        registry: IndicatorRegistry | None = None,
        source_name: str = "<generated>",
    ) -> RuleSet:
        """Load and validate rules from a YAML string.

        Args:
            content: YAML string content.
            registry: Optional IndicatorRegistry for validating indicator references.
            source_name: Source identifier for error messages.

        Returns:
            Validated RuleSet ready for interpretation.
        """
        pass
