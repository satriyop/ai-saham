"""
Port for universe config loader.

Layer: Application (Port)

Provides a Protocol for reading universe configuration files without coupling the
application layer to YAML libraries or direct filesystem operations.
"""

from pathlib import Path
from typing import Protocol


class UniverseConfigLoader(Protocol):
    """Port for reading universe configuration dict."""

    def load_config(self, path: Path) -> dict:
        """Load universe config as a dictionary.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        ...
