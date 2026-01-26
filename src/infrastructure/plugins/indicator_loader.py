"""
Indicator plugin loader - discovers and loads plugins from filesystem.

Layer: Infrastructure
Purpose: Scan plugins/indicators/ directory and load IndicatorPlugin subclasses.

Plugin discovery happens at application startup with graceful degradation
if the plugin directory doesn't exist or plugins fail to load.
"""

import importlib.util
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.ports.indicator_plugin import IndicatorPlugin

logger = logging.getLogger(__name__)

# Default plugin directory relative to project root
DEFAULT_PLUGIN_DIR = Path("plugins/indicators")

# Valid plugin name pattern: uppercase letters, digits, underscores only
VALID_NAME_PATTERN = re.compile(r"^[A-Z0-9_]+$")


class IndicatorPluginLoader:
    """
    Discovers and loads indicator plugins from filesystem.

    Scans a directory for .py files, imports them, and extracts
    IndicatorPlugin subclasses.
    """

    def __init__(self, plugin_dir: Path | None = None) -> None:
        """
        Initialize loader with plugin directory.

        Args:
            plugin_dir: Directory to scan. Defaults to plugins/indicators/
        """
        self._plugin_dir = plugin_dir or DEFAULT_PLUGIN_DIR

    def discover(self) -> list[type["IndicatorPlugin"]]:
        """
        Discover all plugin classes in the plugin directory.

        Returns empty list if directory doesn't exist (graceful degradation).

        Returns:
            List of IndicatorPlugin subclasses found
        """
        if not self._plugin_dir.exists():
            logger.debug(f"Plugin directory not found: {self._plugin_dir}")
            return []

        if not self._plugin_dir.is_dir():
            logger.warning(f"Plugin path is not a directory: {self._plugin_dir}")
            return []

        plugins: list[type["IndicatorPlugin"]] = []

        for path in self._plugin_dir.glob("*.py"):
            # Skip __init__.py and private modules
            if path.name.startswith("_"):
                continue

            plugin_class = self._load_plugin(path)
            if plugin_class is not None:
                plugins.append(plugin_class)

        logger.info(f"Discovered {len(plugins)} indicator plugin(s)")
        return plugins

    def _load_plugin(self, path: Path) -> type["IndicatorPlugin"] | None:
        """
        Load a single plugin file and extract the IndicatorPlugin subclass.

        Returns None on any error (logged as warning).

        Args:
            path: Path to .py file

        Returns:
            IndicatorPlugin subclass or None if loading failed
        """
        # Import IndicatorPlugin here to avoid circular imports
        from src.application.ports.indicator_plugin import IndicatorPlugin

        try:
            # Create module spec from file
            spec = importlib.util.spec_from_file_location(path.stem, path)
            if spec is None or spec.loader is None:
                logger.warning(f"Could not create spec for {path}")
                return None

            # Load the module
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Find IndicatorPlugin subclass in module
            for attr_name in dir(module):
                attr = getattr(module, attr_name)

                # Must be a class, subclass of IndicatorPlugin, not the ABC itself
                if not isinstance(attr, type):
                    continue
                if not issubclass(attr, IndicatorPlugin):
                    continue
                if attr is IndicatorPlugin:
                    continue

                # Validate required class attributes
                if not hasattr(attr, "name"):
                    logger.warning(
                        f"Plugin in {path} missing 'name' class attribute"
                    )
                    continue

                # Validate name format: must be uppercase letters, digits, underscores
                name = attr.name
                if not isinstance(name, str) or not VALID_NAME_PATTERN.match(name):
                    logger.warning(
                        f"Plugin in {path} has invalid name '{name}' - "
                        "must match ^[A-Z0-9_]+$"
                    )
                    continue

                if not hasattr(attr, "default_period"):
                    logger.warning(
                        f"Plugin in {path} missing 'default_period' class attribute"
                    )
                    continue

                logger.info(f"Loaded plugin: {attr.name} from {path.name}")
                return attr

            logger.warning(f"No IndicatorPlugin subclass found in {path}")
            return None

        except Exception as e:
            logger.warning(f"Failed to load plugin {path}: {e}")
            return None
