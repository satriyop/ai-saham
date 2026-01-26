"""
Exceptions for the custom rules DSL.

Provides a hierarchy of exceptions for handling various error conditions
when loading, parsing, and validating YAML rule definitions.

Layer: Application
"""


class RulesError(Exception):
    """Base exception for all rules-related errors."""

    pass


class RulesFileError(RulesError):
    """Error loading or reading a rules file.

    Raised when:
        - File does not exist
        - File cannot be read (permissions)
        - File path is invalid
    """

    pass


class RulesSchemaError(RulesError):
    """Error in rules file schema or structure.

    Raised when:
        - YAML syntax is invalid
        - Required fields are missing
        - Unknown fields are present
        - Field types are incorrect
    """

    pass


class RulesValidationError(RulesError):
    """Error validating rule content or logic.

    Raised when:
        - Unknown indicator names
        - Unknown operators
        - Invalid values (e.g., negative priority)
        - Duplicate rule names
        - Logical inconsistencies
    """

    pass


class StrategyNotFoundError(RulesError):
    """Error when a strategy cannot be found in any search path.

    Raised when:
        - Strategy name doesn't resolve to any existing path
        - Explicit path doesn't exist

    Attributes:
        strategy_name: The strategy name or path that was searched
        searched_paths: List of paths that were checked
    """

    def __init__(
        self,
        strategy_name: str,
        searched_paths: list[str] | None = None,
        message: str | None = None,
    ) -> None:
        self.strategy_name = strategy_name
        self.searched_paths = searched_paths or []

        if message:
            super().__init__(message)
        else:
            lines = [f"Strategy '{strategy_name}' not found."]
            if self.searched_paths:
                lines.append("")
                lines.append("Searched:")
                for path in self.searched_paths:
                    lines.append(f"  - {path}")
                lines.append("")
                lines.append(f"Tip: Use 'saham strategy init {strategy_name}' to create a new strategy.")
            super().__init__("\n".join(lines))
