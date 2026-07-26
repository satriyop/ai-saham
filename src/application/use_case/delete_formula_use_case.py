"""
Delete a stored formula.

Layer: Application (Use Case)

Owns the deletion policy: built-in indicators are protected, and existence is
checked before committing. The adapter handles only user confirmation (a UI
concern) and error formatting.
"""

from dataclasses import dataclass
from enum import Enum

from src.application.dto.stored_formula import StoredFormula
from src.application.ports.formula_store import FormulaStore
from src.application.services.indicator_registry import BUILTIN_NAMES


class DeleteEligibility(str, Enum):
    """Whether a named formula may be deleted."""

    DELETABLE = "deletable"
    NOT_FOUND = "not_found"
    BUILTIN_PROTECTED = "builtin_protected"


@dataclass(frozen=True)
class DeleteFormulaPreview:
    name: str
    eligibility: DeleteEligibility
    formula: StoredFormula | None


class DeleteFormulaUseCase:
    def __init__(self, store: FormulaStore) -> None:
        self._store = store

    def preview(self, name: str) -> DeleteFormulaPreview:
        """Decide whether ``name`` can be deleted, without mutating anything."""
        name_upper = name.upper()
        if name_upper in BUILTIN_NAMES:
            return DeleteFormulaPreview(
                name=name_upper,
                eligibility=DeleteEligibility.BUILTIN_PROTECTED,
                formula=None,
            )
        if not self._store.exists(name_upper):
            return DeleteFormulaPreview(
                name=name_upper,
                eligibility=DeleteEligibility.NOT_FOUND,
                formula=None,
            )
        return DeleteFormulaPreview(
            name=name_upper,
            eligibility=DeleteEligibility.DELETABLE,
            formula=self._store.get(name_upper),
        )

    def commit(self, name: str) -> bool:
        """Delete ``name``; return True if it existed. May raise
        FormulaStoreError, which the adapter maps to an error message."""
        return self._store.delete(name.upper())
