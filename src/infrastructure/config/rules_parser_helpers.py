"""
Shared parsing helpers for YAML rule configuration parsers.

Layer: Infrastructure
"""

from typing import Any

from src.application.rules.exceptions import RulesSchemaError


def require_field(
    data: dict[str, Any],
    field: str,
    expected_type: type,
    context: str,
) -> None:
    """Validate that a required field exists and has correct type.

    Args:
        data: Dictionary to check
        field: Field name to require
        expected_type: Expected type of the field
        context: Context for error messages (e.g., "rule", "when")

    Raises:
        RulesSchemaError: If field missing or wrong type
    """
    if field not in data:
        raise RulesSchemaError(f"{context}: missing required field '{field}'")

    value = data[field]
    if not isinstance(value, expected_type):
        raise RulesSchemaError(
            f"{context}.{field}: expected {expected_type.__name__}, "
            f"got {type(value).__name__}"
        )
