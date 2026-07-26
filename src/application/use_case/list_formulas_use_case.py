"""
List custom formulas and available indicators.

Layer: Application (Use Case)

Owns the persistence read for stored formulas and pairs it with the indicator
registry so an adapter can render the catalogue without touching storage.
"""

from dataclasses import dataclass
from pathlib import Path

from src.application.dto.stored_formula import StoredFormula
from src.application.ports.formula_store import FormulaStore
from src.application.services.indicator_registry import IndicatorRegistry


@dataclass(frozen=True)
class ListFormulasResponse:
    stored_formulas: dict[str, StoredFormula]
    registry: IndicatorRegistry
    formulas_path: Path


class ListFormulasUseCase:
    def __init__(
        self,
        store: FormulaStore,
        registry: IndicatorRegistry,
        formulas_path: Path,
    ) -> None:
        self._store = store
        self._registry = registry
        self._formulas_path = formulas_path

    def execute(self) -> ListFormulasResponse:
        return ListFormulasResponse(
            stored_formulas=self._store.load_all(),
            registry=self._registry,
            formulas_path=self._formulas_path,
        )
