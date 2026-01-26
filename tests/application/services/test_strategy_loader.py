"""
Tests for StrategyLoader service.

Verifies:
- Path resolution (name vs explicit path)
- Strategy validation
- List available strategies
- Error messages with searched paths

All tests run offline with no external dependencies.
"""

import tempfile
from pathlib import Path

import pytest

from src.application.rules.exceptions import (
    StrategyNotFoundError,
    RulesSchemaError,
)
from src.application.services.strategy_loader import (
    StrategyLoader,
    ValidationResult,
    StrategyInfo,
)


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def loader():
    """Create StrategyLoader without registry."""
    return StrategyLoader()


def create_strategy_package(
    base_dir: Path,
    name: str,
    content: str | None = None,
    with_readme: bool = True,
) -> Path:
    """Create a strategy package in the given directory."""
    strategy_dir = base_dir / name
    strategy_dir.mkdir(parents=True, exist_ok=True)

    if content is None:
        content = f'''version: 1
name: "{name}"
description: "Test strategy"
default_outcome: MODERATE

rules:
  - name: test_rule
    when:
      indicator: RSI
      operator: "<"
      value: 30
    outcome: LOW_RISK
'''

    (strategy_dir / "strategy.yaml").write_text(content, encoding="utf-8")

    if with_readme:
        (strategy_dir / "README.md").write_text(f"# {name}\n", encoding="utf-8")

    return strategy_dir


# ============================================================================
# StrategyNotFoundError Tests
# ============================================================================


class TestStrategyNotFoundError:
    """Test StrategyNotFoundError formatting."""

    def test_error_message_includes_strategy_name(self):
        """Error message should include the strategy name."""
        error = StrategyNotFoundError("my_strategy")
        assert "my_strategy" in str(error)
        assert "not found" in str(error)

    def test_error_message_includes_searched_paths(self):
        """Error message should list searched paths."""
        error = StrategyNotFoundError(
            "my_strategy",
            searched_paths=[
                "./my_strategy/strategy.yaml",
                "./strategies/my_strategy/strategy.yaml",
            ],
        )
        message = str(error)
        assert "Searched:" in message
        assert "./my_strategy/strategy.yaml" in message
        assert "./strategies/my_strategy/strategy.yaml" in message

    def test_error_message_includes_tip(self):
        """Error message should include helpful tip."""
        error = StrategyNotFoundError(
            "my_strategy",
            searched_paths=["./path"],
        )
        assert "saham strategy init" in str(error)


# ============================================================================
# StrategyLoader.resolve() Tests
# ============================================================================


class TestStrategyLoaderResolve:
    """Test StrategyLoader.resolve() method."""

    def test_resolve_explicit_yaml_path(self, temp_dir, loader):
        """Should resolve explicit .yaml path."""
        strategy_file = temp_dir / "my_rules.yaml"
        strategy_file.write_text("version: 1\nname: test", encoding="utf-8")

        result = loader.resolve(str(strategy_file))
        assert result == strategy_file

    def test_resolve_explicit_path_with_slash(self, temp_dir, loader):
        """Should resolve path containing slash."""
        strategy_dir = temp_dir / "strategies" / "test"
        strategy_dir.mkdir(parents=True)
        strategy_file = strategy_dir / "strategy.yaml"
        strategy_file.write_text("version: 1\nname: test", encoding="utf-8")

        # Path with slash should be treated as explicit
        result = loader.resolve(str(strategy_file))
        assert result == strategy_file

    def test_resolve_strategy_name_in_local_dir(self, temp_dir, loader, monkeypatch):
        """Should find strategy in ./NAME/strategy.yaml."""
        # Create strategy directly in working directory
        monkeypatch.chdir(temp_dir)
        create_strategy_package(temp_dir, "momentum")

        result = loader.resolve("momentum")
        assert result.name == "strategy.yaml"
        assert "momentum" in str(result)

    def test_resolve_strategy_name_in_strategies_dir(self, temp_dir, loader, monkeypatch):
        """Should find strategy in ./strategies/NAME/strategy.yaml."""
        monkeypatch.chdir(temp_dir)
        strategies_dir = temp_dir / "strategies"
        create_strategy_package(strategies_dir, "test_strat")

        result = loader.resolve("test_strat")
        assert result.name == "strategy.yaml"
        assert "test_strat" in str(result)

    def test_resolve_nonexistent_raises_error(self, temp_dir, loader, monkeypatch):
        """Should raise StrategyNotFoundError for nonexistent strategy."""
        monkeypatch.chdir(temp_dir)

        with pytest.raises(StrategyNotFoundError) as exc_info:
            loader.resolve("nonexistent")

        error = exc_info.value
        assert error.strategy_name == "nonexistent"
        assert len(error.searched_paths) > 0

    def test_resolve_explicit_path_not_found_raises_error(self, loader):
        """Should raise error for explicit path that doesn't exist."""
        with pytest.raises(StrategyNotFoundError) as exc_info:
            loader.resolve("/nonexistent/path/strategy.yaml")

        assert "/nonexistent/path/strategy.yaml" in exc_info.value.searched_paths


# ============================================================================
# StrategyLoader.validate() Tests
# ============================================================================


class TestStrategyLoaderValidate:
    """Test StrategyLoader.validate() method."""

    def test_validate_valid_strategy(self, temp_dir, loader):
        """Should return valid result for valid strategy."""
        create_strategy_package(temp_dir, "valid")
        path = temp_dir / "valid" / "strategy.yaml"

        result = loader.validate(path)

        assert result.valid is True
        assert result.strategy_name == "valid"
        assert len(result.errors) == 0

    def test_validate_missing_file(self, temp_dir, loader):
        """Should return invalid for missing file."""
        path = temp_dir / "nonexistent" / "strategy.yaml"

        result = loader.validate(path)

        assert result.valid is False
        assert "not found" in result.errors[0].lower()

    def test_validate_invalid_yaml_schema(self, temp_dir, loader):
        """Should return invalid for schema errors."""
        strategy_dir = temp_dir / "invalid"
        strategy_dir.mkdir()
        (strategy_dir / "strategy.yaml").write_text("not: valid: yaml: {")

        result = loader.validate(strategy_dir / "strategy.yaml")

        assert result.valid is False
        assert any("schema" in e.lower() or "syntax" in e.lower() for e in result.errors)

    def test_validate_missing_readme_warning(self, temp_dir, loader):
        """Should warn about missing README.md."""
        create_strategy_package(temp_dir, "no_readme", with_readme=False)
        path = temp_dir / "no_readme" / "strategy.yaml"

        result = loader.validate(path)

        assert result.valid is True
        assert any("README" in w for w in result.warnings)

    def test_validate_strict_mode_fails_on_warnings(self, temp_dir, loader):
        """In strict mode, warnings should become errors."""
        create_strategy_package(temp_dir, "strict_test", with_readme=False)
        path = temp_dir / "strict_test" / "strategy.yaml"

        result = loader.validate(path, strict=True)

        assert result.valid is False
        assert any("README" in e for e in result.errors)


# ============================================================================
# StrategyLoader.load() Tests
# ============================================================================


class TestStrategyLoaderLoad:
    """Test StrategyLoader.load() method."""

    def test_load_returns_ruleset(self, temp_dir, loader, monkeypatch):
        """Should return RuleSet for valid strategy."""
        monkeypatch.chdir(temp_dir)
        create_strategy_package(temp_dir, "loadable")

        rule_set = loader.load("loadable")

        assert rule_set.name == "loadable"
        assert len(rule_set.rules) > 0

    def test_load_nonexistent_raises_error(self, temp_dir, loader, monkeypatch):
        """Should raise StrategyNotFoundError for nonexistent."""
        monkeypatch.chdir(temp_dir)

        with pytest.raises(StrategyNotFoundError):
            loader.load("nonexistent")


# ============================================================================
# StrategyLoader.list_available() Tests
# ============================================================================


class TestStrategyLoaderListAvailable:
    """Test StrategyLoader.list_available() method."""

    def test_list_empty_when_no_strategies(self, temp_dir, loader, monkeypatch):
        """Should return empty list when no strategies exist."""
        monkeypatch.chdir(temp_dir)

        result = loader.list_available()

        assert result == []

    def test_list_finds_local_strategies(self, temp_dir, loader, monkeypatch):
        """Should find strategies in ./strategies/ directory."""
        monkeypatch.chdir(temp_dir)
        strategies_dir = temp_dir / "strategies"
        create_strategy_package(strategies_dir, "strat_a")
        create_strategy_package(strategies_dir, "strat_b")

        result = loader.list_available()

        names = [s.name for s in result]
        assert "strat_a" in names
        assert "strat_b" in names

    def test_list_includes_strategy_info(self, temp_dir, loader, monkeypatch):
        """Should include StrategyInfo with metadata."""
        monkeypatch.chdir(temp_dir)
        strategies_dir = temp_dir / "strategies"
        create_strategy_package(strategies_dir, "detailed")

        result = loader.list_available()

        assert len(result) == 1
        info = result[0]
        assert isinstance(info, StrategyInfo)
        assert info.name == "detailed"
        assert info.display_name == "detailed"
        assert info.valid is True
        assert info.location == "local"

    def test_list_excludes_invalid_by_default(self, temp_dir, loader, monkeypatch):
        """Should exclude invalid strategies by default."""
        monkeypatch.chdir(temp_dir)
        strategies_dir = temp_dir / "strategies"
        create_strategy_package(strategies_dir, "valid_one")

        # Create invalid strategy
        invalid_dir = strategies_dir / "invalid_one"
        invalid_dir.mkdir()
        (invalid_dir / "strategy.yaml").write_text("not: valid: {")

        result = loader.list_available(include_invalid=False)

        names = [s.name for s in result]
        assert "valid_one" in names
        assert "invalid_one" not in names

    def test_list_includes_invalid_when_requested(self, temp_dir, loader, monkeypatch):
        """Should include invalid strategies when requested."""
        monkeypatch.chdir(temp_dir)
        strategies_dir = temp_dir / "strategies"
        create_strategy_package(strategies_dir, "valid_one")

        # Create invalid strategy
        invalid_dir = strategies_dir / "invalid_one"
        invalid_dir.mkdir()
        (invalid_dir / "strategy.yaml").write_text("not: valid: {")

        result = loader.list_available(include_invalid=True)

        names = [s.name for s in result]
        assert "valid_one" in names
        assert "invalid_one" in names


# ============================================================================
# ValidationResult Tests
# ============================================================================


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_error_summary_empty_when_valid(self):
        """Error summary should be empty for valid result."""
        result = ValidationResult(
            valid=True,
            strategy_name="test",
            path=Path("test.yaml"),
            errors=[],
            warnings=[],
        )
        assert result.error_summary == ""

    def test_error_summary_joins_errors(self):
        """Error summary should join multiple errors."""
        result = ValidationResult(
            valid=False,
            strategy_name=None,
            path=Path("test.yaml"),
            errors=["Error 1", "Error 2"],
            warnings=[],
        )
        assert "Error 1" in result.error_summary
        assert "Error 2" in result.error_summary
