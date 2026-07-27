"""
Persist an AI-generated formula.

Layer: Application (Use Case)

Owns the post-translation workflow that previously lived in the CLI adapter:
- name-generation policy when the caller did not supply a name,
- registering the formula in the in-memory registry,
- persisting it to the store,
- the decision that register/save failures are non-fatal warnings.

The AI translation itself is a separate use case
(CreateIndicatorFromIntentUseCase); this use case is deterministic.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.application.ports.formula_store import FormulaStore, FormulaStoreError
from src.application.services.indicator_registry import IndicatorRegistry

if TYPE_CHECKING:
    from src.application.formula.ast_nodes import ASTNode


@dataclass(frozen=True)
class PersistGeneratedFormulaRequest:
    formula: str
    ast: "ASTNode | None"
    intent: str
    requested_name: str | None
    save: bool = True


@dataclass(frozen=True)
class PersistGeneratedFormulaResponse:
    name: str
    auto_generated: bool
    register_attempted: bool
    registered: bool
    register_error: str | None
    save_attempted: bool
    saved: bool
    save_error: str | None


class PersistGeneratedFormulaUseCase:
    def __init__(self, store: FormulaStore, registry: IndicatorRegistry) -> None:
        self._store = store
        self._registry = registry

    def execute(self, request: PersistGeneratedFormulaRequest) -> PersistGeneratedFormulaResponse:
        auto_generated = not request.requested_name
        name = (request.requested_name or self._auto_name(request.formula)).upper()

        register_attempted = request.ast is not None
        registered = False
        register_error: str | None = None
        if register_attempted:
            try:
                self._registry.register_formula(name, request.ast)
                registered = True
            except Exception as e:  # registration is best-effort, non-fatal
                register_error = str(e)

        save_attempted = request.save and bool(request.formula)
        saved = False
        save_error: str | None = None
        if save_attempted:
            try:
                self._store.save(name=name, formula=request.formula, intent=request.intent)
                saved = True
            except FormulaStoreError as e:  # persistence failure is non-fatal
                save_error = str(e)

        return PersistGeneratedFormulaResponse(
            name=name,
            auto_generated=auto_generated,
            register_attempted=register_attempted,
            registered=registered,
            register_error=register_error,
            save_attempted=save_attempted,
            saved=saved,
            save_error=save_error,
        )

    @staticmethod
    def _auto_name(formula: str) -> str:
        formula_clean = formula.replace("(", "_").replace(")", "")
        formula_clean = formula_clean.replace(",", "_").replace(" ", "")
        return f"CUSTOM_{formula_clean[:20]}".upper()
