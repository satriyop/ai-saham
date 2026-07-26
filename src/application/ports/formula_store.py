"""
Port for custom formula persistence.

Layer: Application (Port)

Use cases depend on this abstraction; infrastructure provides the concrete
implementation (e.g. a YAML-backed store). The port owns its error type so the
application never imports from infrastructure.
"""

from typing import Protocol

from src.application.dto.stored_formula import StoredFormula


class FormulaStoreError(Exception):
    """Raised when a formula store operation fails."""


class FormulaStore(Protocol):
    """Port for storing and retrieving custom formulas."""

    def get(self, name: str) -> StoredFormula | None:
        """Return the stored formula for ``name``, or None if absent."""
        ...

    def save(
        self, name: str, formula: str, intent: str | None = None
    ) -> StoredFormula:
        """Persist a formula. Raises FormulaStoreError on failure."""
        ...

    def exists(self, name: str) -> bool:
        """Return True if a formula named ``name`` is stored."""
        ...

    def delete(self, name: str) -> bool:
        """Delete ``name``; return True if it existed. Raises FormulaStoreError
        on failure."""
        ...

    def load_all(self) -> dict[str, StoredFormula]:
        """Return all stored formulas keyed by name."""
        ...

    def list_names(self) -> list[str]:
        """Return the sorted names of all stored formulas."""
        ...
