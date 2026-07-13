"""
Port for universe config store.

Layer: Application (Port)
"""

from pathlib import Path
from typing import Protocol


class UniverseConfigStore(Protocol):
    """Port for universe config storage and retrieval."""

    @property
    def config_path(self) -> Path:
        """The path to the configuration file."""
        ...

    def load_raw(self) -> dict:
        """Load configuration as raw dict."""
        ...

    def save_raw(self, data: dict, *, updated: str) -> None:
        """Save configuration."""
        ...
