"""
Dependency wiring for formula lifecycle commands.

Layer: Adapter (composition)

Keeps infrastructure construction (FormulaStorage, indicator registry, AI
translator) out of the command module so the commands stay thin. Mirrors
``strategy_lifecycle_factory.py``.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.application.use_case.create_indicator_from_intent_use_case import (
    CreateIndicatorFromIntentUseCase,
)
from src.application.use_case.delete_formula_use_case import DeleteFormulaUseCase
from src.application.use_case.list_formulas_use_case import ListFormulasUseCase
from src.application.use_case.persist_generated_formula_use_case import (
    PersistGeneratedFormulaUseCase,
)
from src.application.use_case.show_formula_use_case import ShowFormulaUseCase
from src.infrastructure.ai.formula_translator import FormulaTranslatorAdapter
from src.infrastructure.composition.indicator_registry_factory import (
    create_indicator_registry,
)
from src.infrastructure.persistence.formula_storage import FormulaStorage

DEFAULT_FORMULAS_PATH = Path("config/formulas.yaml")


def resolve_formulas_path(formulas_path: Optional[Path]) -> Path:
    """The formulas file to read/write, defaulting to config/formulas.yaml."""
    return formulas_path or DEFAULT_FORMULAS_PATH


def create_list_formulas_use_case(
    formulas_path: Optional[Path],
) -> ListFormulasUseCase:
    resolved = resolve_formulas_path(formulas_path)
    return ListFormulasUseCase(
        store=FormulaStorage(path=resolved),
        registry=create_indicator_registry(),
        formulas_path=resolved,
    )


def create_show_formula_use_case(
    formulas_path: Optional[Path],
) -> ShowFormulaUseCase:
    return ShowFormulaUseCase(store=FormulaStorage(path=resolve_formulas_path(formulas_path)))


def create_delete_formula_use_case(
    formulas_path: Optional[Path],
) -> DeleteFormulaUseCase:
    return DeleteFormulaUseCase(store=FormulaStorage(path=resolve_formulas_path(formulas_path)))


@dataclass(frozen=True)
class FormulaAuthoringUseCases:
    """The two use cases behind ``indicator create``: AI translation followed by
    deterministic persistence, sharing one registry and store."""

    translate: CreateIndicatorFromIntentUseCase
    persist: PersistGeneratedFormulaUseCase


def create_formula_authoring_use_cases(
    provider: str,
    model: Optional[str],
    formulas_path: Optional[Path],
) -> FormulaAuthoringUseCases:
    storage = FormulaStorage(path=resolve_formulas_path(formulas_path))
    registry = create_indicator_registry()
    translator = FormulaTranslatorAdapter(provider=provider, model=model)
    translate = CreateIndicatorFromIntentUseCase(
        translator=translator,
        available_functions=registry.get_available_indicators(),
    )
    persist = PersistGeneratedFormulaUseCase(store=storage, registry=registry)
    return FormulaAuthoringUseCases(translate=translate, persist=persist)
