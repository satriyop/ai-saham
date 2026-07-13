"""
Strategy loader service for resolving and validating strategy packages.

Strategies are first-class, versionable, portable artifacts organized as:
    strategies/
      NAME/
        strategy.yaml   (required)
        README.md       (optional)
        tests/          (optional)
        examples/       (optional)

Search order:
1. Explicit path if contains "/" or ends with ".yaml"
2. ./NAME/strategy.yaml
3. ./strategies/NAME/strategy.yaml

Layer: Application
"""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from src.application.ports.rules_loader import RulesLoader
from src.application.rules.exceptions import (
    RulesError,
    RulesFileError,
    RulesSchemaError,
    RulesValidationError,
    StrategyNotFoundError,
)

if TYPE_CHECKING:
    from src.application.rules.schema import RuleSet
    from src.application.services.indicator_registry import IndicatorRegistry


# Local strategies directories (relative to cwd)
LOCAL_STRATEGIES_DIRS = [
    Path("."),  # ./NAME/strategy.yaml
    Path("strategies"),  # ./strategies/NAME/strategy.yaml
]


@dataclass(frozen=True)
class ValidationResult:
    """Result of strategy validation.

    Attributes:
        valid: Whether the strategy is valid
        strategy_name: Name from the strategy.yaml
        path: Resolved path to strategy.yaml
        errors: List of error messages (empty if valid)
        warnings: List of warning messages
    """

    valid: bool
    strategy_name: str | None
    path: Path
    errors: list[str]
    warnings: list[str]

    @property
    def error_summary(self) -> str:
        """Get a single-line error summary."""
        if not self.errors:
            return ""
        return "; ".join(self.errors)


@dataclass(frozen=True)
class StrategyInfo:
    """Information about an available strategy.

    Attributes:
        name: Strategy name (directory name)
        path: Path to strategy.yaml
        display_name: Name from strategy.yaml (if valid)
        description: Description from strategy.yaml (if valid)
        location: Where this strategy was found ("local" or "user")
        valid: Whether the strategy passed basic validation
    """

    name: str
    path: Path
    display_name: str | None
    description: str | None
    location: str
    valid: bool


class StrategyLoader:
    """Service for resolving, validating, and listing strategy packages.

    Strategies are searched in priority order:
    1. Explicit path if contains "/" or ends with ".yaml"
    2. ./NAME/strategy.yaml
    3. ./strategies/NAME/strategy.yaml
    """

    def __init__(
        self,
        rules_loader: RulesLoader,
        registry: "IndicatorRegistry | None" = None,
    ) -> None:
        """Initialize strategy loader.

        Args:
            rules_loader: RulesLoader port interface. Must be injected by the
                caller's adapter/composition root with a concrete
                implementation from the infrastructure layer.
            registry: Optional IndicatorRegistry for validating indicator references
        """
        self._registry = registry
        self._rules_loader = rules_loader

    def resolve(self, name_or_path: str) -> Path:
        """Resolve a strategy name or path to an actual file path.

        Args:
            name_or_path: Strategy name (e.g., "momentum") or explicit path

        Returns:
            Resolved path to strategy.yaml

        Raises:
            StrategyNotFoundError: If strategy cannot be found
        """
        # Check if this looks like an explicit path
        if self._is_explicit_path(name_or_path):
            path = Path(name_or_path)
            if path.exists():
                return path
            raise StrategyNotFoundError(
                name_or_path,
                searched_paths=[str(path)],
            )

        # Search for strategy by name
        search_paths = self._get_search_paths(name_or_path)

        for search_path in search_paths:
            if search_path.exists():
                return search_path

        raise StrategyNotFoundError(
            name_or_path,
            searched_paths=[str(p) for p in search_paths],
        )

    def validate(
        self,
        path: Path,
        strict: bool = False,
    ) -> ValidationResult:
        """Validate a strategy file.

        Args:
            path: Path to strategy.yaml
            strict: If True, treat warnings as errors

        Returns:
            ValidationResult with validation status and details
        """
        errors: list[str] = []
        warnings: list[str] = []
        strategy_name: str | None = None

        # Check file exists
        if not path.exists():
            return ValidationResult(
                valid=False,
                strategy_name=None,
                path=path,
                errors=[f"File not found: {path}"],
                warnings=[],
            )

        # Check file is readable
        if not path.is_file():
            return ValidationResult(
                valid=False,
                strategy_name=None,
                path=path,
                errors=[f"Not a file: {path}"],
                warnings=[],
            )

        # Try to load and validate
        try:
            rule_set = self._rules_loader.load(path, registry=self._registry)
            strategy_name = rule_set.name

            # Check for missing optional components
            strategy_dir = path.parent
            if not (strategy_dir / "README.md").exists():
                warnings.append("Missing README.md (recommended)")

        except RulesFileError as e:
            errors.append(f"File error: {e}")
        except RulesSchemaError as e:
            errors.append(f"Schema error: {e}")
        except RulesValidationError as e:
            errors.append(f"Validation error: {e}")
        except RulesError as e:
            errors.append(f"Error: {e}")

        # In strict mode, warnings become errors
        if strict and warnings:
            errors.extend(warnings)
            warnings = []

        return ValidationResult(
            valid=len(errors) == 0,
            strategy_name=strategy_name,
            path=path,
            errors=errors,
            warnings=warnings,
        )

    def load(self, name_or_path: str) -> "RuleSet":
        """Load a strategy and return the RuleSet.

        Convenience method that resolves and loads in one step.

        Args:
            name_or_path: Strategy name or explicit path

        Returns:
            Validated RuleSet ready for interpretation

        Raises:
            StrategyNotFoundError: If strategy cannot be found
            RulesFileError: If file cannot be read
            RulesSchemaError: If YAML syntax is invalid
            RulesValidationError: If rule content is invalid
        """
        path = self.resolve(name_or_path)
        return self._rules_loader.load(path, registry=self._registry)

    def list_available(self, include_invalid: bool = False) -> list[StrategyInfo]:
        """List all available strategies.

        Searches local and user directories for strategy packages.

        Args:
            include_invalid: If True, include strategies that fail validation

        Returns:
            List of StrategyInfo for available strategies
        """
        strategies: list[StrategyInfo] = []
        seen_names: set[str] = set()

        # Search local directories
        for base_dir in LOCAL_STRATEGIES_DIRS:
            if not base_dir.exists():
                continue
            for strategy_info in self._scan_directory(base_dir, "local"):
                if strategy_info.name not in seen_names:
                    if include_invalid or strategy_info.valid:
                        strategies.append(strategy_info)
                        seen_names.add(strategy_info.name)

        return sorted(strategies, key=lambda s: s.name)

    def _is_explicit_path(self, name_or_path: str) -> bool:
        """Check if the input looks like an explicit path.

        Args:
            name_or_path: Input string to check

        Returns:
            True if this should be treated as an explicit path
        """
        return "/" in name_or_path or name_or_path.endswith(".yaml")

    def _get_search_paths(self, name: str) -> list[Path]:
        """Get ordered list of paths to search for a strategy name.

        Args:
            name: Strategy name (without path separators)

        Returns:
            List of paths to check in priority order
        """
        paths = []

        # Local directories
        for base_dir in LOCAL_STRATEGIES_DIRS:
            paths.append(base_dir / name / "strategy.yaml")

        return paths

    def _scan_directory(self, base_dir: Path, location: str) -> list[StrategyInfo]:
        """Scan a directory for strategy packages.

        Args:
            base_dir: Directory to scan
            location: Location identifier ("local" or "user")

        Returns:
            List of StrategyInfo for strategies found
        """
        strategies = []

        if not base_dir.exists() or not base_dir.is_dir():
            return strategies

        for item in base_dir.iterdir():
            if not item.is_dir():
                continue

            strategy_yaml = item / "strategy.yaml"
            if not strategy_yaml.exists():
                continue

            # Try to get metadata from the file
            display_name = None
            description = None
            valid = False

            try:
                rule_set = self._rules_loader.load(strategy_yaml, registry=self._registry)
                display_name = rule_set.name
                description = rule_set.description
                valid = True
            except RulesError:
                # Invalid strategy - still include with limited info
                pass

            strategies.append(
                StrategyInfo(
                    name=item.name,
                    path=strategy_yaml,
                    display_name=display_name,
                    description=description,
                    location=location,
                    valid=valid,
                )
            )

        return strategies
