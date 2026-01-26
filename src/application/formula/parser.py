"""Recursive descent parser for formula expressions.

Application layer - Formula parser.

This module parses tokenized formula strings into Abstract Syntax Trees (AST).
The parser implements a recursive descent algorithm with standard operator
precedence rules.

Grammar:
    expression    = term (('+' | '-') term)*
    term          = factor (('*' | '/') factor)*
    factor        = NUMBER | SERIES | function_call | '(' expression ')'
    function_call = IDENTIFIER '(' arguments? ')'
    arguments     = expression (',' expression)*

SERIES keywords: OPEN, HIGH, LOW, CLOSE, VOLUME

Operator precedence (lowest to highest):
    1. + - (additive)
    2. * / (multiplicative)

Example:
    >>> from src.application.formula.parser import parse
    >>> ast = parse("SMA(RSI(14), 10)")
    >>> ast
    FunctionCallNode(name='SMA', arguments=(FunctionCallNode(name='RSI', ...), NumberNode(...)))
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterator

from src.application.formula.ast_nodes import (
    SERIES_FIELDS,
    ASTNode,
    BinaryOpNode,
    FunctionCallNode,
    NumberNode,
    SeriesNode,
)
from src.application.formula.exceptions import FormulaParseError
from src.application.formula.tokenizer import Token, TokenType, tokenize


class Parser:
    """Recursive descent parser for formula expressions.

    This parser converts a stream of tokens into an AST representation.
    It implements standard operator precedence through recursive descent.

    Example:
        parser = Parser(tokenize("EMA(CLOSE, 12) - EMA(CLOSE, 26)"))
        ast = parser.parse()
    """

    def __init__(self, tokens: Iterator[Token]) -> None:
        """Initialize the parser.

        Args:
            tokens: Iterator of Token objects (typically from tokenize()).
        """
        self._tokens = tokens
        self._current: Token | None = None
        self._advance()

    def _advance(self) -> Token | None:
        """Move to the next token.

        Returns:
            The previous current token, or None if at start.
        """
        previous = self._current
        try:
            self._current = next(self._tokens)
        except StopIteration:
            # Create synthetic EOF if iterator exhausted
            pos = previous.position + len(previous.value) if previous else 0
            self._current = Token(TokenType.EOF, "", pos)
        return previous

    def _check(self, token_type: TokenType) -> bool:
        """Check if current token matches the given type."""
        return self._current is not None and self._current.type == token_type

    def _match(self, *types: TokenType) -> Token | None:
        """Match and consume current token if it matches any given type.

        Args:
            *types: Token types to match.

        Returns:
            The matched token, or None if no match.
        """
        for token_type in types:
            if self._check(token_type):
                return self._advance()
        return None

    def _expect(self, token_type: TokenType, message: str) -> Token:
        """Expect and consume a specific token type.

        Args:
            token_type: The expected token type.
            message: Error message if token doesn't match.

        Returns:
            The consumed token.

        Raises:
            FormulaParseError: If current token doesn't match.
        """
        if self._check(token_type):
            return self._advance()  # type: ignore

        current = self._current
        raise FormulaParseError(
            f"{message} at position {current.position if current else 'unknown'}",
            position=current.position if current else None,
            expected=token_type.name,
            found=current.value if current else "EOF",
        )

    def parse(self) -> ASTNode:
        """Parse the token stream into an AST.

        Returns:
            The root AST node.

        Raises:
            FormulaParseError: If the formula is syntactically invalid.
        """
        ast = self._parse_expression()

        # Ensure all tokens consumed
        if not self._check(TokenType.EOF):
            current = self._current
            raise FormulaParseError(
                f"Unexpected token '{current.value}' at position {current.position}",
                position=current.position if current else None,
                found=current.value if current else "EOF",
            )

        return ast

    def _parse_expression(self) -> ASTNode:
        """Parse an expression (additive operations).

        expression = term (('+' | '-') term)*
        """
        left = self._parse_term()

        while True:
            op_token = self._match(TokenType.PLUS, TokenType.MINUS)
            if not op_token:
                break

            operator = "+" if op_token.type == TokenType.PLUS else "-"
            right = self._parse_term()
            left = BinaryOpNode(operator=operator, left=left, right=right)

        return left

    def _parse_term(self) -> ASTNode:
        """Parse a term (multiplicative operations).

        term = factor (('*' | '/') factor)*
        """
        left = self._parse_factor()

        while True:
            op_token = self._match(TokenType.STAR, TokenType.SLASH)
            if not op_token:
                break

            operator = "*" if op_token.type == TokenType.STAR else "/"
            right = self._parse_factor()
            left = BinaryOpNode(operator=operator, left=left, right=right)

        return left

    def _parse_factor(self) -> ASTNode:
        """Parse a factor (atoms and grouped expressions).

        factor = NUMBER | SERIES | function_call | '(' expression ')'
        """
        # Parenthesized expression
        if self._match(TokenType.LPAREN):
            expr = self._parse_expression()
            self._expect(TokenType.RPAREN, "Expected ')' after expression")
            return expr

        # Number literal
        if self._check(TokenType.NUMBER):
            token = self._advance()
            return NumberNode(value=Decimal(token.value))  # type: ignore

        # Identifier (series keyword or function call)
        if self._check(TokenType.IDENTIFIER):
            token = self._advance()
            name = token.value.upper()  # type: ignore

            # Check if it's a function call
            if self._check(TokenType.LPAREN):
                return self._parse_function_call(name)

            # Check if it's a series keyword
            if name.lower() in SERIES_FIELDS:
                return SeriesNode(field=name)

            # Bare identifier (indicator reference without parentheses)
            # Treat as function call with no arguments
            return FunctionCallNode(name=name, arguments=())

        # Error: unexpected token
        current = self._current
        raise FormulaParseError(
            f"Expected expression, found '{current.value}' at position {current.position}",
            position=current.position if current else None,
            expected="expression",
            found=current.value if current else "EOF",
        )

    def _parse_function_call(self, name: str) -> FunctionCallNode:
        """Parse a function call.

        function_call = IDENTIFIER '(' arguments? ')'
        arguments = expression (',' expression)*

        Args:
            name: The function name (already consumed).

        Returns:
            A FunctionCallNode.
        """
        self._expect(TokenType.LPAREN, f"Expected '(' after function name '{name}'")

        arguments: list[ASTNode] = []

        # Parse arguments if present
        if not self._check(TokenType.RPAREN):
            arguments.append(self._parse_expression())

            while self._match(TokenType.COMMA):
                arguments.append(self._parse_expression())

        self._expect(TokenType.RPAREN, f"Expected ')' after arguments for '{name}'")

        return FunctionCallNode(name=name, arguments=tuple(arguments))


def parse(text: str) -> ASTNode:
    """Parse a formula string into an AST.

    This is the main entry point for parsing formulas.

    Args:
        text: The formula string to parse.

    Returns:
        The root AST node representing the formula.

    Raises:
        FormulaParseError: If the formula is syntactically invalid.
        FormulaTokenError: If the formula contains invalid characters.

    Example:
        >>> ast = parse("SMA(CLOSE, 20)")
        >>> isinstance(ast, FunctionCallNode)
        True
        >>> ast.name
        'SMA'
    """
    return Parser(tokenize(text)).parse()
