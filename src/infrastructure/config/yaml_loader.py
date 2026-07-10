"""Backward-compatible import facade for the rules YAML loader.

New code should import RulesYamlLoader from
src.infrastructure.config.rules_yaml_loader.
"""

from src.infrastructure.config.rules_yaml_loader import (
    DEFAULT_LOCATIONS,
    RulesYamlLoader,
    YamlConfigLoader,
)

__all__ = [
    "DEFAULT_LOCATIONS",
    "RulesYamlLoader",
    "YamlConfigLoader",
]
