"""Formula-specific exceptions.

Application layer - Formula parsing and evaluation exceptions.

This module provides a hierarchy of exceptions for the formula engine:
- FormulaError: Base exception for all formula-related errors
- FormulaTokenError: Errors during lexical analysis
- FormulaParseError: Errors during parsing
- FormulaValidationError: Errors during semantic validation
- FormulaEvaluationError: Errors during formula evaluation
"""

from __future__ import annotations


class FormulaError(Exception):
    """Base exception for all formula-related errors.

    All formula exceptions inherit from this class, allowing callers
    to catch all formula errors with a single except clause if desired.

    Example:
        try:
            ast = parser.parse(formula_text)
        except FormulaError as e:
            print(f"Formula error: {e}")
    """

    pass


class FormulaTokenError(FormulaError):
    """Error during lexical analysis (tokenization).

    Raised when the tokenizer encounters an unexpected character
    or invalid token in the formula string.

    Attributes:
        position: The character position where the error occurred.
        character: The unexpected character (if applicable).

    Example:
        >>> tokenize("SMA(CLOSE, 20) @ 5")
        FormulaTokenError: Unexpected character '@' at position 15
    """

    def __init__(
        self, message: str, *, position: int | None = None, character: str | None = None
    ) -> None:
        super().__init__(message)
        self.position = position
        self.character = character


class FormulaParseError(FormulaError):
    """Error during parsing.

    Raised when the parser encounters unexpected tokens or invalid
    grammar structure in the formula.

    Attributes:
        position: The token position where the error occurred.
        expected: What the parser expected to find.
        found: What was actually found.

    Example:
        >>> parse("SMA(CLOSE, )")
        FormulaParseError: Expected expression, found ')' at position 11
    """

    def __init__(
        self,
        message: str,
        *,
        position: int | None = None,
        expected: str | None = None,
        found: str | None = None,
    ) -> None:
        super().__init__(message)
        self.position = position
        self.expected = expected
        self.found = found


class FormulaValidationError(FormulaError):
    """Error during semantic validation.

    Raised when a formula is syntactically valid but semantically invalid,
    such as referencing undefined indicators or creating circular references.

    Attributes:
        indicator_name: The indicator name involved (if applicable).
        cycle: The cycle path for circular reference errors.

    Example:
        >>> validate({"A": "B", "B": "A"})
        FormulaValidationError: Circular reference detected: A -> B -> A
    """

    def __init__(
        self,
        message: str,
        *,
        indicator_name: str | None = None,
        cycle: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.indicator_name = indicator_name
        self.cycle = cycle


class FormulaEvaluationError(FormulaError):
    """Error during formula evaluation.

    Raised when an error occurs while computing formula values,
    such as type mismatches or computation failures.

    Attributes:
        formula_name: The formula being evaluated.
        node_type: The AST node type where the error occurred.

    Example:
        >>> evaluator.compute(ast, candles)
        FormulaEvaluationError: Cannot divide series of different lengths
    """

    def __init__(
        self,
        message: str,
        *,
        formula_name: str | None = None,
        node_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.formula_name = formula_name
        self.node_type = node_type
