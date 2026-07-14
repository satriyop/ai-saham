"""
Port for writing strategy package files to storage.

Layer: Domain
"""

from pathlib import Path
from typing import Protocol


class StrategyPackageWriter(Protocol):
    """Writes strategy package artifacts (directory, strategy.yaml, README.md)."""

    def ensure_directory(self, path: Path) -> None: ...

    def write_strategy(self, path: Path, content: str) -> None: ...

    def write_readme(self, path: Path, content: str) -> None: ...
