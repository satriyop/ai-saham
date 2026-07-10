"""Utility for mutating YAML document paths using dot-notation.

Layer: Application
"""

from __future__ import annotations


def set_document_value(
    document: dict,
    document_path: str,
    value: object | None,
) -> None:
    current: object = document
    parts = document_path.split(".")
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"YAML document path not found: {document_path}")
        current = current[part]
    if not isinstance(current, dict) or parts[-1] not in current:
        raise ValueError(f"YAML document path not found: {document_path}")
    current[parts[-1]] = value


# Compatibility alias
_set_document_value = set_document_value
