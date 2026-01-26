"""Lexical analysis (tokenization) for formula strings.

Application layer - Formula tokenizer.

This module converts formula strings into a stream of tokens for parsing.
The tokenizer recognizes:
- Numbers (integers and decimals)
- Identifiers (function names and series keywords)
- Operators (+, -, *, /)
- Punctuation (parentheses, commas)

Example:
    >>> list(tokenize("SMA(RSI(14), 10)"))
    [Token(IDENTIFIER, 'SMA', 0), Token(LPAREN, '(', 3), Token(IDENTIFIER, 'RSI', 4),
     Token(LPAREN, '(', 7), Token(NUMBER, '14', 8), Token(RPAREN, ')', 10),
     Token(COMMA, ',', 11), Token(NUMBER, '10', 13), Token(RPAREN, ')', 15),
     Token(EOF, '', 16)]
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum, auto
from typing import Iterator

from src.application.formula.exceptions import FormulaTokenError


class TokenType(Enum):
    """Token types recognized by the formula tokenizer."""

    NUMBER = auto()  # Numeric literals: 14, 20, 0.5
    IDENTIFIER = auto()  # Function names and series: SMA, RSI, CLOSE
    LPAREN = auto()  # (
    RPAREN = auto()  # )
    COMMA = auto()  # ,
    PLUS = auto()  # +
    MINUS = auto()  # -
    STAR = auto()  # *
    SLASH = auto()  # /
    EOF = auto()  # End of input


@dataclass(frozen=True)
class Token:
    """A token produced by the tokenizer.

    Attributes:
        type: The token type.
        value: The string value of the token.
        position: The character position in the input string.
    """

    type: TokenType
    value: str
    position: int

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r}, {self.position})"


# Single-character token mapping
_SINGLE_CHAR_TOKENS: dict[str, TokenType] = {
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    ",": TokenType.COMMA,
    "+": TokenType.PLUS,
    "-": TokenType.MINUS,
    "*": TokenType.STAR,
    "/": TokenType.SLASH,
}


class Tokenizer:
    """Stateful tokenizer for formula strings.

    This class maintains position state while scanning through the input
    string, producing tokens one at a time.

    Example:
        tokenizer = Tokenizer("SMA(CLOSE, 20)")
        tokens = list(tokenizer.tokenize())
    """

    def __init__(self, text: str) -> None:
        """Initialize the tokenizer.

        Args:
            text: The formula string to tokenize.
        """
        self._text = text
        self._pos = 0
        self._length = len(text)

    def tokenize(self) -> Iterator[Token]:
        """Generate tokens from the input string.

        Yields:
            Token objects in sequence, ending with EOF.

        Raises:
            FormulaTokenError: If an unexpected character is encountered.
        """
        while self._pos < self._length:
            char = self._text[self._pos]

            # Skip whitespace
            if char.isspace():
                self._pos += 1
                continue

            # Single-character tokens
            if char in _SINGLE_CHAR_TOKENS:
                yield Token(_SINGLE_CHAR_TOKENS[char], char, self._pos)
                self._pos += 1
                continue

            # Numbers (including decimals)
            if char.isdigit() or (char == "." and self._peek_digit()):
                yield self._read_number()
                continue

            # Identifiers (function names and series keywords)
            if char.isalpha() or char == "_":
                yield self._read_identifier()
                continue

            # Unknown character
            raise FormulaTokenError(
                f"Unexpected character '{char}' at position {self._pos}",
                position=self._pos,
                character=char,
            )

        # End of input
        yield Token(TokenType.EOF, "", self._pos)

    def _peek_digit(self) -> bool:
        """Check if the next character is a digit."""
        next_pos = self._pos + 1
        return next_pos < self._length and self._text[next_pos].isdigit()

    def _read_number(self) -> Token:
        """Read a numeric literal.

        Handles integers and decimal numbers.

        Returns:
            A NUMBER token.

        Raises:
            FormulaTokenError: If the number format is invalid.
        """
        start_pos = self._pos
        has_decimal = False

        while self._pos < self._length:
            char = self._text[self._pos]

            if char.isdigit():
                self._pos += 1
            elif char == "." and not has_decimal:
                has_decimal = True
                self._pos += 1
            else:
                break

        value = self._text[start_pos : self._pos]

        # Validate the number format
        try:
            Decimal(value)
        except InvalidOperation:
            raise FormulaTokenError(
                f"Invalid number format '{value}' at position {start_pos}",
                position=start_pos,
            )

        return Token(TokenType.NUMBER, value, start_pos)

    def _read_identifier(self) -> Token:
        """Read an identifier (function name or series keyword).

        Identifiers start with a letter or underscore, followed by
        letters, digits, or underscores.

        Returns:
            An IDENTIFIER token.
        """
        start_pos = self._pos

        while self._pos < self._length:
            char = self._text[self._pos]
            if char.isalnum() or char == "_":
                self._pos += 1
            else:
                break

        value = self._text[start_pos : self._pos]
        return Token(TokenType.IDENTIFIER, value, start_pos)


def tokenize(text: str) -> Iterator[Token]:
    """Tokenize a formula string.

    This is the main entry point for tokenization.

    Args:
        text: The formula string to tokenize.

    Yields:
        Token objects in sequence, ending with EOF.

    Raises:
        FormulaTokenError: If an unexpected character is encountered.

    Example:
        >>> tokens = list(tokenize("SMA(CLOSE, 20)"))
        >>> tokens[0]
        Token(IDENTIFIER, 'SMA', 0)
    """
    return Tokenizer(text).tokenize()
