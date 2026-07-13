"""Backward-compatible import facade for the rules YAML loader.

New code should import RulesYamlLoader from
src.infrastructure.config.rules_yaml_loader.

Compatibility surface:
- Canonical import(s):
  - RulesYamlLoader, YamlConfigLoader, DEFAULT_LOCATIONS ->
    src.infrastructure.config.rules_yaml_loader
- Allowed contents:
  - imports and __all__ only. No new implementation may be added here.
- Expiry:
  - remove after tests/scripts stop importing
    src.infrastructure.config.yaml_loader.
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
