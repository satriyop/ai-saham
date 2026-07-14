"""
Use case for creating a new strategy package (strategy.yaml + README.md).

Layer: Application
"""

from pathlib import Path

from src.application.dto.strategy_package import (
    CreateStrategyPackageRequest,
    CreateStrategyPackageResponse,
)
from src.application.services.strategy_package_templates import (
    README_TEMPLATE,
    STRATEGY_TEMPLATE,
)
from src.domain.ports.strategy_package_writer import StrategyPackageWriter


class InvalidStrategyPackageName(ValueError):
    """Raised when a strategy package name is not usable."""


class StrategyPackageAlreadyExists(FileExistsError):
    """Raised when a strategy.yaml already exists and force was not requested."""


class StrategyPackageWriteError(OSError):
    """Raised when the strategy package directory or strategy.yaml cannot be written.

    ``stage`` and ``path`` let the adapter reproduce the exact CLI message per
    failure point without re-deriving directory-resolution policy itself.
    """

    def __init__(self, stage: str, message: str, path: Path) -> None:
        super().__init__(message)
        self.stage = stage
        self.path = path


class CreateStrategyPackageUseCase:
    """Creates a strategy package on disk via an injected writer port."""

    def __init__(self, writer: StrategyPackageWriter) -> None:
        self._writer = writer

    def execute(
        self, request: CreateStrategyPackageRequest
    ) -> CreateStrategyPackageResponse:
        name = request.name

        if "/" in name or "\\" in name:
            raise InvalidStrategyPackageName(
                "Strategy name cannot contain path separators."
            )

        if name.endswith(".yaml"):
            raise InvalidStrategyPackageName(
                "Strategy name should not end with .yaml."
            )

        target_dir = request.directory if request.directory else Path("strategies") / name

        strategy_yaml = target_dir / "strategy.yaml"
        readme_md = target_dir / "README.md"

        if strategy_yaml.exists() and not request.force:
            raise StrategyPackageAlreadyExists(str(strategy_yaml))

        try:
            self._writer.ensure_directory(target_dir)
        except PermissionError as e:
            raise StrategyPackageWriteError("directory_permission", str(e), target_dir) from e
        except OSError as e:
            raise StrategyPackageWriteError("directory", str(e), target_dir) from e

        try:
            self._writer.write_strategy(strategy_yaml, STRATEGY_TEMPLATE.format(name=name))
        except OSError as e:
            raise StrategyPackageWriteError("strategy", str(e), strategy_yaml) from e

        readme_written = True
        readme_warning: str | None = None
        try:
            self._writer.write_readme(
                readme_md,
                README_TEMPLATE.format(name=name, description="Strategy description"),
            )
        except OSError as e:
            readme_written = False
            readme_warning = str(e)

        return CreateStrategyPackageResponse(
            name=name,
            target_dir=target_dir,
            strategy_path=strategy_yaml,
            readme_path=readme_md,
            readme_written=readme_written,
            readme_warning=readme_warning,
        )
