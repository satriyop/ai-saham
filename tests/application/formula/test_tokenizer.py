"""Tests for the formula tokenizer."""

import pytest

from src.application.formula.exceptions import FormulaTokenError
from src.application.formula.tokenizer import Token, TokenType, tokenize


class TestTokenize:
    """Tests for the tokenize function."""

    def test_simple_identifier(self) -> None:
        """Test tokenizing a single identifier."""
        tokens = list(tokenize("RSI"))
        assert len(tokens) == 2
        assert tokens[0] == Token(TokenType.IDENTIFIER, "RSI", 0)
        assert tokens[1].type == TokenType.EOF

    def test_simple_number(self) -> None:
        """Test tokenizing a single number."""
        tokens = list(tokenize("14"))
        assert len(tokens) == 2
        assert tokens[0] == Token(TokenType.NUMBER, "14", 0)
        assert tokens[1].type == TokenType.EOF

    def test_decimal_number(self) -> None:
        """Test tokenizing a decimal number."""
        tokens = list(tokenize("0.5"))
        assert len(tokens) == 2
        assert tokens[0] == Token(TokenType.NUMBER, "0.5", 0)
        assert tokens[1].type == TokenType.EOF

    def test_function_call(self) -> None:
        """Test tokenizing a simple function call."""
        tokens = list(tokenize("RSI(14)"))
        assert len(tokens) == 5
        assert tokens[0] == Token(TokenType.IDENTIFIER, "RSI", 0)
        assert tokens[1] == Token(TokenType.LPAREN, "(", 3)
        assert tokens[2] == Token(TokenType.NUMBER, "14", 4)
        assert tokens[3] == Token(TokenType.RPAREN, ")", 6)
        assert tokens[4].type == TokenType.EOF

    def test_function_with_two_args(self) -> None:
        """Test tokenizing function with two arguments."""
        tokens = list(tokenize("SMA(CLOSE, 20)"))
        assert len(tokens) == 7
        assert tokens[0] == Token(TokenType.IDENTIFIER, "SMA", 0)
        assert tokens[1] == Token(TokenType.LPAREN, "(", 3)
        assert tokens[2] == Token(TokenType.IDENTIFIER, "CLOSE", 4)
        assert tokens[3] == Token(TokenType.COMMA, ",", 9)
        assert tokens[4] == Token(TokenType.NUMBER, "20", 11)
        assert tokens[5] == Token(TokenType.RPAREN, ")", 13)
        assert tokens[6].type == TokenType.EOF

    def test_nested_function(self) -> None:
        """Test tokenizing nested function calls."""
        tokens = list(tokenize("SMA(RSI(14), 10)"))
        expected_types = [
            TokenType.IDENTIFIER,  # SMA
            TokenType.LPAREN,  # (
            TokenType.IDENTIFIER,  # RSI
            TokenType.LPAREN,  # (
            TokenType.NUMBER,  # 14
            TokenType.RPAREN,  # )
            TokenType.COMMA,  # ,
            TokenType.NUMBER,  # 10
            TokenType.RPAREN,  # )
            TokenType.EOF,
        ]
        assert [t.type for t in tokens] == expected_types

    def test_binary_operators(self) -> None:
        """Test tokenizing arithmetic operators."""
        tokens = list(tokenize("1 + 2 - 3 * 4 / 5"))
        expected_types = [
            TokenType.NUMBER,
            TokenType.PLUS,
            TokenType.NUMBER,
            TokenType.MINUS,
            TokenType.NUMBER,
            TokenType.STAR,
            TokenType.NUMBER,
            TokenType.SLASH,
            TokenType.NUMBER,
            TokenType.EOF,
        ]
        assert [t.type for t in tokens] == expected_types

    def test_complex_formula(self) -> None:
        """Test tokenizing a complex formula."""
        formula = "EMA(CLOSE, 12) - EMA(CLOSE, 26)"
        tokens = list(tokenize(formula))
        expected_types = [
            TokenType.IDENTIFIER,  # EMA
            TokenType.LPAREN,
            TokenType.IDENTIFIER,  # CLOSE
            TokenType.COMMA,
            TokenType.NUMBER,  # 12
            TokenType.RPAREN,
            TokenType.MINUS,
            TokenType.IDENTIFIER,  # EMA
            TokenType.LPAREN,
            TokenType.IDENTIFIER,  # CLOSE
            TokenType.COMMA,
            TokenType.NUMBER,  # 26
            TokenType.RPAREN,
            TokenType.EOF,
        ]
        assert [t.type for t in tokens] == expected_types

    def test_parenthesized_expression(self) -> None:
        """Test tokenizing parenthesized expressions."""
        tokens = list(tokenize("(SMA(CLOSE, 10) + SMA(CLOSE, 20)) / 2"))
        # Count tokens (should include all parens)
        paren_count = sum(1 for t in tokens if t.type in (TokenType.LPAREN, TokenType.RPAREN))
        assert paren_count == 6  # 3 pairs

    def test_whitespace_handling(self) -> None:
        """Test that whitespace is properly ignored."""
        tokens1 = list(tokenize("SMA(CLOSE,20)"))
        tokens2 = list(tokenize("SMA( CLOSE , 20 )"))

        # Should have same token types and values
        assert [t.type for t in tokens1] == [t.type for t in tokens2]
        assert [t.value for t in tokens1] == [t.value for t in tokens2]

    def test_underscore_in_identifier(self) -> None:
        """Test identifiers with underscores."""
        tokens = list(tokenize("smooth_rsi"))
        assert tokens[0] == Token(TokenType.IDENTIFIER, "smooth_rsi", 0)

    def test_identifier_with_numbers(self) -> None:
        """Test identifiers containing numbers."""
        tokens = list(tokenize("RSI14"))
        assert tokens[0] == Token(TokenType.IDENTIFIER, "RSI14", 0)

    def test_empty_string(self) -> None:
        """Test tokenizing empty string."""
        tokens = list(tokenize(""))
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.EOF

    def test_whitespace_only(self) -> None:
        """Test tokenizing whitespace-only string."""
        tokens = list(tokenize("   "))
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.EOF


class TestTokenizerErrors:
    """Tests for tokenizer error handling."""

    def test_unexpected_character(self) -> None:
        """Test error on unexpected character."""
        with pytest.raises(FormulaTokenError) as exc_info:
            list(tokenize("SMA(CLOSE, 20) @ 5"))

        assert "Unexpected character '@'" in str(exc_info.value)
        assert exc_info.value.character == "@"
        assert exc_info.value.position == 15

    def test_invalid_character_at_start(self) -> None:
        """Test error on invalid character at start."""
        with pytest.raises(FormulaTokenError) as exc_info:
            list(tokenize("@RSI"))

        assert exc_info.value.position == 0

    def test_special_characters_rejected(self) -> None:
        """Test that various special characters are rejected."""
        invalid_chars = ["@", "#", "$", "%", "^", "&", "!", "?", "|", "\\"]

        for char in invalid_chars:
            with pytest.raises(FormulaTokenError):
                list(tokenize(f"RSI{char}14"))


class TestTokenPositions:
    """Tests for token position tracking."""

    def test_positions_are_correct(self) -> None:
        """Test that token positions are accurate."""
        #           0123456789012345
        formula = "SMA(CLOSE, 20)"
        tokens = list(tokenize(formula))

        assert tokens[0].position == 0  # SMA
        assert tokens[1].position == 3  # (
        assert tokens[2].position == 4  # CLOSE
        assert tokens[3].position == 9  # ,
        assert tokens[4].position == 11  # 20
        assert tokens[5].position == 13  # )

    def test_eof_position(self) -> None:
        """Test that EOF position is at end of string."""
        formula = "ABC"
        tokens = list(tokenize(formula))
        assert tokens[-1].type == TokenType.EOF
        assert tokens[-1].position == 3
