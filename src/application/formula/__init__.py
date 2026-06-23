"""Formula parsing and evaluation module.

Application layer - Composable indicator formula engine.

This module provides a deterministic formula engine for defining composite
indicators using expressions like SMA(RSI(14), 10) or EMA(CLOSE,12) - EMA(CLOSE,26).

Key components:
- AST Nodes: Immutable node types representing parsed formulas
- Tokenizer: Lexical analysis of formula strings
- Parser: Recursive descent parser producing AST
- Validator: Semantic validation and dependency ordering
- Evaluator: AST evaluation producing index-aligned values

Supported syntax:
- Series: OPEN, HIGH, LOW, CLOSE, VOLUME
- Functions: SMA(series, period), RSI(period), EMA(series, period), etc.
- Operators: + - * /
- Parentheses: ( ) for grouping

Example:
    from src.application.formula import parse, FormulaEvaluator

    ast = parse("SMA(RSI(14), 10)")
    evaluator = FormulaEvaluator(registry)
    values = evaluator.compute(ast, candle_count=100)

Security:
    No arbitrary code execution - only predefined AST nodes are supported.
    No recursion in formulas - validator prevents circular references.
    No loops - grammar has no loop constructs.
    Deterministic - same input always produces same output.
"""

from src.application.formula.ast_nodes import (
    BINARY_OPERATORS,
    SERIES_FIELDS,
    ASTNode,
    BinaryOpNode,
    FunctionCallNode,
    NumberNode,
    SeriesNode,
)
from src.application.formula.evaluator import (
    FormulaEvaluator,
    RegistrySeriesProvider,
    SeriesProvider,
)
from src.application.formula.exceptions import (
    FormulaError,
    FormulaEvaluationError,
    FormulaParseError,
    FormulaTokenError,
    FormulaValidationError,
)
from src.application.formula.parser import Parser, parse
from src.application.formula.tokenizer import Token, TokenType, tokenize
from src.application.formula.validator import (
    build_dependency_graph,
    extract_dependencies,
    topological_sort,
    validate_formula_references,
    validate_formulas,
)

__all__ = [
    # AST Nodes
    "ASTNode",
    "NumberNode",
    "SeriesNode",
    "FunctionCallNode",
    "BinaryOpNode",
    "SERIES_FIELDS",
    "BINARY_OPERATORS",
    # Exceptions
    "FormulaError",
    "FormulaTokenError",
    "FormulaParseError",
    "FormulaValidationError",
    "FormulaEvaluationError",
    # Tokenizer
    "Token",
    "TokenType",
    "tokenize",
    # Parser
    "Parser",
    "parse",
    # Validator
    "extract_dependencies",
    "build_dependency_graph",
    "topological_sort",
    "validate_formula_references",
    "validate_formulas",
    # Evaluator
    "SeriesProvider",
    "FormulaEvaluator",
    "RegistrySeriesProvider",
]
