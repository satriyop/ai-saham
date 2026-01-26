"""
Application bootstrap utilities.

Provides functions for initializing application services with plugins.
"""

import logging

from src.application.services.indicator_registry import IndicatorRegistry
from src.infrastructure.plugins.indicator_loader import IndicatorPluginLoader

logger = logging.getLogger(__name__)


def create_indicator_registry(plugin_dir: str | None = None) -> IndicatorRegistry:
    """
    Create an IndicatorRegistry with plugins loaded from filesystem.

    Discovers plugins from the specified directory (or default plugins/indicators/)
    and registers them. Gracefully handles missing directories and invalid plugins.

    Args:
        plugin_dir: Optional path to plugin directory. None uses default.

    Returns:
        IndicatorRegistry with built-in indicators and discovered plugins
    """
    from pathlib import Path

    registry = IndicatorRegistry()

    # Load plugins
    loader = IndicatorPluginLoader(Path(plugin_dir) if plugin_dir else None)
    plugins = loader.discover()

    # Register each plugin
    for plugin_class in plugins:
        try:
            registry.register_plugin(plugin_class)
            logger.debug(f"Registered plugin: {plugin_class.name}")
        except Exception as e:
            logger.warning(f"Failed to register plugin {plugin_class.name}: {e}")

    return registry
