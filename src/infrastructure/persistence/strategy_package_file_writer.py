"""
Filesystem implementation of the strategy package writer port.

Layer: Infrastructure
"""

from pathlib import Path


class StrategyPackageFileWriter:
    """Writes strategy package artifacts to the local filesystem."""

    def ensure_directory(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def write_strategy(self, path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")

    def write_readme(self, path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")
