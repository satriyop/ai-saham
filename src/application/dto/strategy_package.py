"""
DTOs for strategy package creation.

Layer: Application
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CreateStrategyPackageRequest:
    """Request to create a new strategy package."""

    name: str
    directory: Path | None
    force: bool


@dataclass(frozen=True)
class CreateStrategyPackageResponse:
    """Result of creating a new strategy package."""

    name: str
    target_dir: Path
    strategy_path: Path
    readme_path: Path
    readme_written: bool
    readme_warning: str | None = None
