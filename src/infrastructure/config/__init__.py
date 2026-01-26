"""
Configuration loading infrastructure.

Provides adapters for loading configuration from various sources
(YAML files, environment variables, etc.)

Layer: Infrastructure
"""

from src.infrastructure.config.yaml_loader import YamlConfigLoader

__all__ = ["YamlConfigLoader"]
