"""
Port for reading strategy documents.

Layer: Application (Port)
"""

from pathlib import Path
from typing import Any, Mapping, Protocol


class StrategyDocumentReader(Protocol):
    """Port for reading strategy configurations."""

    def read_strategy(self, path: Path) -> Mapping[str, Any]:
        """Read strategy configuration from a file.

        Raises:
            Exception: On reading/parsing errors.
        """
        ...
