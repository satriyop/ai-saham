"""
Show a single stored formula.

Layer: Application (Use Case)

Owns the persistence read and the not-found decision (including which names to
offer as alternatives), so the adapter only formats the result.
"""

from dataclasses import dataclass

from src.application.dto.stored_formula import StoredFormula
from src.application.ports.formula_store import FormulaStore


@dataclass(frozen=True)
class ShowFormulaResponse:
    requested_name: str
    formula: StoredFormula | None
    available_names: list[str]

    @property
    def found(self) -> bool:
        return self.formula is not None


class ShowFormulaUseCase:
    def __init__(self, store: FormulaStore) -> None:
        self._store = store

    def execute(self, name: str) -> ShowFormulaResponse:
        stored = self._store.get(name)
        if stored is None:
            return ShowFormulaResponse(
                requested_name=name.upper(),
                formula=None,
                available_names=self._store.list_names(),
            )
        return ShowFormulaResponse(
            requested_name=stored.name,
            formula=stored,
            available_names=[],
        )
