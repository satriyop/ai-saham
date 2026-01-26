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
