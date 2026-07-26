"""
Stored formula value object.

Layer: Application (DTO)

The canonical type for a persisted custom formula. Lives in the core so that
application ports and use cases can reference it without depending on any
infrastructure persistence implementation.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class StoredFormula:
    """A persisted formula with metadata.

    Attributes:
        name: Formula name (uppercase).
        formula: Formula expression string.
        intent: Original natural language intent (optional).
        created: Creation timestamp.
    """

    name: str
    formula: str
    intent: str | None
    created: datetime
