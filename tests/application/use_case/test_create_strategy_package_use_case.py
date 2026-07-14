"""
Tests for CreateStrategyPackageUseCase.

Layer: Application
"""

from pathlib import Path

import pytest

from src.application.dto.strategy_package import CreateStrategyPackageRequest
from src.application.use_case.create_strategy_package_use_case import (
    CreateStrategyPackageUseCase,
    InvalidStrategyPackageName,
    StrategyPackageAlreadyExists,
    StrategyPackageWriteError,
)


class FakeStrategyPackageWriter:
    def __init__(self, *, fail_readme: bool = False, fail_strategy: bool = False) -> None:
        self.fail_readme = fail_readme
        self.fail_strategy = fail_strategy
        self.directories: list[Path] = []
        self.strategies: dict[Path, str] = {}
        self.readmes: dict[Path, str] = {}

    def ensure_directory(self, path: Path) -> None:
        self.directories.append(path)

    def write_strategy(self, path: Path, content: str) -> None:
        if self.fail_strategy:
            raise OSError("disk full")
        self.strategies[path] = content

    def write_readme(self, path: Path, content: str) -> None:
        if self.fail_readme:
            raise OSError("readme write failed")
        self.readmes[path] = content


def test_default_target_directory_is_strategies_name():
    writer = FakeStrategyPackageWriter()
    use_case = CreateStrategyPackageUseCase(writer=writer)

    response = use_case.execute(
        CreateStrategyPackageRequest(name="momentum", directory=None, force=False)
    )

    assert response.target_dir == Path("strategies") / "momentum"


def test_explicit_directory_is_respected(tmp_path):
    writer = FakeStrategyPackageWriter()
    use_case = CreateStrategyPackageUseCase(writer=writer)
    target = tmp_path / "custom"

    response = use_case.execute(
        CreateStrategyPackageRequest(name="momentum", directory=target, force=False)
    )

    assert response.target_dir == target


def test_invalid_name_with_forward_slash_raises():
    writer = FakeStrategyPackageWriter()
    use_case = CreateStrategyPackageUseCase(writer=writer)

    with pytest.raises(InvalidStrategyPackageName):
        use_case.execute(
            CreateStrategyPackageRequest(name="my/strategy", directory=None, force=False)
        )


def test_invalid_name_with_backslash_raises():
    writer = FakeStrategyPackageWriter()
    use_case = CreateStrategyPackageUseCase(writer=writer)

    with pytest.raises(InvalidStrategyPackageName):
        use_case.execute(
            CreateStrategyPackageRequest(name="my\\strategy", directory=None, force=False)
        )


def test_yaml_suffix_raises():
    writer = FakeStrategyPackageWriter()
    use_case = CreateStrategyPackageUseCase(writer=writer)

    with pytest.raises(InvalidStrategyPackageName):
        use_case.execute(
            CreateStrategyPackageRequest(name="my_strategy.yaml", directory=None, force=False)
        )


def test_existing_strategy_without_force_raises(tmp_path):
    target = tmp_path / "existing"
    target.mkdir()
    (target / "strategy.yaml").write_text("existing content")

    writer = FakeStrategyPackageWriter()
    use_case = CreateStrategyPackageUseCase(writer=writer)

    with pytest.raises(StrategyPackageAlreadyExists):
        use_case.execute(
            CreateStrategyPackageRequest(name="existing", directory=target, force=False)
        )


def test_force_true_writes_strategy_yaml(tmp_path):
    target = tmp_path / "existing"
    target.mkdir()
    (target / "strategy.yaml").write_text("existing content")

    writer = FakeStrategyPackageWriter()
    use_case = CreateStrategyPackageUseCase(writer=writer)

    response = use_case.execute(
        CreateStrategyPackageRequest(name="existing", directory=target, force=True)
    )

    assert response.strategy_path in writer.strategies
    assert "existing" in writer.strategies[response.strategy_path]


def test_readme_write_failure_returns_warning_and_does_not_fail(tmp_path):
    writer = FakeStrategyPackageWriter(fail_readme=True)
    use_case = CreateStrategyPackageUseCase(writer=writer)

    response = use_case.execute(
        CreateStrategyPackageRequest(name="momentum", directory=tmp_path / "pkg", force=False)
    )

    assert response.readme_written is False
    assert response.readme_warning == "readme write failed"
    assert response.strategy_path in writer.strategies


def test_strategy_write_failure_raises_write_error(tmp_path):
    writer = FakeStrategyPackageWriter(fail_strategy=True)
    use_case = CreateStrategyPackageUseCase(writer=writer)

    with pytest.raises(StrategyPackageWriteError):
        use_case.execute(
            CreateStrategyPackageRequest(name="momentum", directory=tmp_path / "pkg", force=False)
        )
