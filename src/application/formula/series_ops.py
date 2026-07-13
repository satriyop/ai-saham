"""Binary series arithmetic for formula evaluation.

This module provides pure arithmetic operations on Decimal series,
with support for scalar broadcasting, end-alignment, and division-by-zero
handling. It contains no AST logic or registry adapter code.
"""

from __future__ import annotations

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


def apply_binary_op(
    operator: str,
    left: list[Decimal],
    right: list[Decimal],
) -> list[Decimal]:
    """Apply a binary operator to two series.

    Series are aligned from the end, so shorter series are matched
    to the end of the longer series.

    Special cases:
    - Scalar (single element) is broadcast to match other series length
    - Division by zero returns Decimal("0") and logs warning

    Args:
        operator: The operator (+, -, *, /).
        left: Left operand series.
        right: Right operand series.

    Returns:
        Result series.
    """
    if len(left) == 1 and len(right) > 1:
        left = left * len(right)
    elif len(right) == 1 and len(left) > 1:
        right = right * len(left)

    result_len = min(len(left), len(right))
    if result_len == 0:
        return []

    left_aligned = left[-result_len:]
    right_aligned = right[-result_len:]

    result: list[Decimal] = []

    for l_val, r_val in zip(left_aligned, right_aligned):
        if operator == "+":
            result.append(l_val + r_val)
        elif operator == "-":
            result.append(l_val - r_val)
        elif operator == "*":
            result.append(l_val * r_val)
        elif operator == "/":
            if r_val == 0:
                logger.warning("Division by zero in formula evaluation, using 0")
                result.append(Decimal("0"))
            else:
                result.append(l_val / r_val)

    return result
