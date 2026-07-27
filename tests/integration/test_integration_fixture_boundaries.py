"""
Guards against global integration fixtures hiding infrastructure composition.

registry_with_formulas must stay a pure application-layer fixture built from
IndicatorRegistry directly. Formula-storage/composition integration must be
opted into explicitly via registry_loaded_from_formula_storage.
"""

import ast
from pathlib import Path

CONFTEST = Path("tests/integration/conftest.py")


def test_integration_conftest_does_not_module_import_indicator_composition_factory():
    tree = ast.parse(CONFTEST.read_text(encoding="utf-8"))
    forbidden = "src.infrastructure.composition.indicator_registry_factory"

    for node in tree.body:
        assert not (isinstance(node, ast.ImportFrom) and node.module == forbidden), (
            "tests/integration/conftest.py must not module-import create_indicator_registry"
        )


def test_registry_with_formulas_fixture_is_pure_application_registry():
    source = CONFTEST.read_text(encoding="utf-8")
    tree = ast.parse(source)

    fixture_node = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "registry_with_formulas"
    )

    names = {node.id for node in ast.walk(fixture_node) if isinstance(node, ast.Name)}

    assert "IndicatorRegistry" in names
    assert "FormulaStorage" not in names
    assert "create_indicator_registry" not in names


def test_create_indicator_registry_only_used_inside_formula_storage_fixture():
    tree = ast.parse(CONFTEST.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name == "registry_loaded_from_formula_storage":
            continue
        names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        assert "create_indicator_registry" not in names, (
            f"create_indicator_registry must only be used inside "
            f"registry_loaded_from_formula_storage, found in {node.name}"
        )
