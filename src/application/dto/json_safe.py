"""JSON-safe conversion shared by contract envelope DTO modules.

Layer: Application (pure)
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


def json_safe(value: Any) -> Any:
    """Recursively convert to JSON-serializable primitives (str fallback)."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return json_safe(value.to_dict())
    if is_dataclass(value) and not isinstance(value, type):
        return json_safe(asdict(value))
    return str(value)
