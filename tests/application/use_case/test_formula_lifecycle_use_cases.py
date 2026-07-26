"""Tests for the formula lifecycle use cases: list, show, delete, and persist
generated formulas.

Layer: Application.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from src.application.dto.stored_formula import StoredFormula
from src.application.ports.formula_store import FormulaStoreError
from src.application.services.indicator_registry import BUILTIN_NAMES
from src.application.use_case.delete_formula_use_case import (
    DeleteEligibility,
    DeleteFormulaUseCase,
)
from src.application.use_case.list_formulas_use_case import ListFormulasUseCase
from src.application.use_case.persist_generated_formula_use_case import (
    PersistGeneratedFormulaRequest,
    PersistGeneratedFormulaUseCase,
)
from src.application.use_case.show_formula_use_case import ShowFormulaUseCase


class FakeFormulaStore:
    """Minimal in-memory FormulaStore fake.

    Set ``fail_save`` / ``fail_delete`` to a FormulaStoreError instance to
    make the corresponding method raise instead of acting normally.
    """

    def __init__(
        self,
        formulas: dict[str, StoredFormula] | None = None,
    ) -> None:
        self._formulas: dict[str, StoredFormula] = dict(formulas or {})
        self.fail_save: FormulaStoreError | None = None
        self.fail_delete: FormulaStoreError | None = None
        self.save_calls: list[tuple[str, str, str | None]] = []
        self.delete_calls: list[str] = []

    def get(self, name: str) -> StoredFormula | None:
        return self._formulas.get(name.upper())

    def save(
        self, name: str, formula: str, intent: str | None = None
    ) -> StoredFormula:
        self.save_calls.append((name, formula, intent))
        if self.fail_save is not None:
            raise self.fail_save
        stored = StoredFormula(
            name=name, formula=formula, intent=intent, created=datetime.now()
        )
        self._formulas[name] = stored
        return stored

    def exists(self, name: str) -> bool:
        return name in self._formulas

    def delete(self, name: str) -> bool:
        self.delete_calls.append(name)
        if self.fail_delete is not None:
            raise self.fail_delete
        return self._formulas.pop(name, None) is not None

    def load_all(self) -> dict[str, StoredFormula]:
        return dict(self._formulas)

    def list_names(self) -> list[str]:
        return sorted(self._formulas.keys())


class FakeIndicatorRegistry:
    """Minimal fake registry exposing only register_formula().

    Set ``fail_register`` to an Exception instance to make register_formula
    raise instead of recording the call.
    """

    def __init__(self) -> None:
        self.fail_register: Exception | None = None
        self.register_calls: list[tuple[str, object]] = []

    def register_formula(self, name: str, ast: object) -> None:
        self.register_calls.append((name, ast))
        if self.fail_register is not None:
            raise self.fail_register


def _stored(name: str, formula: str = "SMA(20)", intent: str | None = None):
    return StoredFormula(
        name=name, formula=formula, intent=intent, created=datetime(2026, 1, 1)
    )


class TestListFormulasUseCase:
    def test_returns_all_stored_formulas_and_passthrough_fields(self):
        stored = {"MY_RSI": _stored("MY_RSI")}
        store = FakeFormulaStore(stored)
        registry = object()
        formulas_path = Path("/tmp/formulas.yaml")
        use_case = ListFormulasUseCase(store, registry, formulas_path)

        response = use_case.execute()

        assert response.stored_formulas == store.load_all()
        assert response.registry is registry
        assert response.formulas_path is formulas_path

    def test_returns_empty_dict_when_store_has_no_formulas(self):
        store = FakeFormulaStore()
        use_case = ListFormulasUseCase(store, object(), Path("/tmp/formulas.yaml"))

        response = use_case.execute()

        assert response.stored_formulas == {}


class TestShowFormulaUseCase:
    def test_finds_existing_formula(self):
        stored = _stored("MY_RSI")
        store = FakeFormulaStore({"MY_RSI": stored})
        use_case = ShowFormulaUseCase(store)

        response = use_case.execute("my_rsi")

        assert response.formula is stored
        assert response.requested_name == stored.name
        assert response.available_names == []
        assert response.found is True

    def test_reports_not_found_with_available_names(self):
        store = FakeFormulaStore({"MY_RSI": _stored("MY_RSI")})
        use_case = ShowFormulaUseCase(store)

        response = use_case.execute("missing")

        assert response.formula is None
        assert response.requested_name == "MISSING"
        assert response.available_names == store.list_names()
        assert response.found is False


class TestDeleteFormulaUseCasePreview:
    def test_protects_builtin_indicator_regardless_of_case(self):
        store = FakeFormulaStore()
        use_case = DeleteFormulaUseCase(store)
        builtin_name = next(iter(BUILTIN_NAMES))

        preview = use_case.preview(builtin_name.lower())

        assert preview.eligibility == DeleteEligibility.BUILTIN_PROTECTED
        assert preview.name == builtin_name
        assert preview.formula is None

    def test_reports_not_found_for_unknown_non_builtin_name(self):
        store = FakeFormulaStore()
        use_case = DeleteFormulaUseCase(store)

        preview = use_case.preview("unknown")

        assert preview.eligibility == DeleteEligibility.NOT_FOUND
        assert preview.formula is None
        assert preview.name == "UNKNOWN"

    def test_reports_deletable_for_stored_non_builtin_name(self):
        stored = _stored("MY_RSI")
        store = FakeFormulaStore({"MY_RSI": stored})
        use_case = DeleteFormulaUseCase(store)

        preview = use_case.preview("my_rsi")

        assert preview.eligibility == DeleteEligibility.DELETABLE
        assert preview.formula == stored
        assert preview.name == "MY_RSI"


class TestDeleteFormulaUseCaseCommit:
    def test_commits_deletion_and_returns_true_when_existed(self):
        store = FakeFormulaStore({"MY_RSI": _stored("MY_RSI")})
        use_case = DeleteFormulaUseCase(store)

        result = use_case.commit("my_rsi")

        assert result is True
        assert store.delete_calls == ["MY_RSI"]

    def test_commits_deletion_and_returns_false_when_absent(self):
        store = FakeFormulaStore()
        use_case = DeleteFormulaUseCase(store)

        result = use_case.commit("missing")

        assert result is False
        assert store.delete_calls == ["MISSING"]

    def test_propagates_formula_store_error(self):
        store = FakeFormulaStore({"MY_RSI": _stored("MY_RSI")})
        store.fail_delete = FormulaStoreError("disk full")
        use_case = DeleteFormulaUseCase(store)

        with pytest.raises(FormulaStoreError):
            use_case.commit("my_rsi")


class TestPersistGeneratedFormulaUseCase:
    def test_persists_with_explicit_name(self):
        store = FakeFormulaStore()
        registry = FakeIndicatorRegistry()
        use_case = PersistGeneratedFormulaUseCase(store, registry)
        request = PersistGeneratedFormulaRequest(
            formula="SMA(20)",
            ast=object(),
            intent="20-day average",
            requested_name="my_rsi",
            save=True,
        )

        response = use_case.execute(request)

        assert response.name == "MY_RSI"
        assert response.auto_generated is False
        assert response.register_attempted is True
        assert response.registered is True
        assert response.register_error is None
        assert response.save_attempted is True
        assert response.saved is True
        assert response.save_error is None
        assert [name for name, _, _ in store.save_calls] == ["MY_RSI"]
        assert [name for name, _ in registry.register_calls] == ["MY_RSI"]

    def test_auto_generates_name_when_none_requested(self):
        store = FakeFormulaStore()
        registry = FakeIndicatorRegistry()
        use_case = PersistGeneratedFormulaUseCase(store, registry)
        request = PersistGeneratedFormulaRequest(
            formula="SMA(RSI(14), 10)",
            ast=object(),
            intent="smoothed rsi",
            requested_name=None,
        )

        response = use_case.execute(request)

        assert response.auto_generated is True
        assert response.name == "CUSTOM_SMA_RSI_14_10"

    def test_registration_failure_is_non_fatal_and_save_still_proceeds(self):
        store = FakeFormulaStore()
        registry = FakeIndicatorRegistry()
        registry.fail_register = Exception("boom")
        use_case = PersistGeneratedFormulaUseCase(store, registry)
        request = PersistGeneratedFormulaRequest(
            formula="SMA(20)",
            ast=object(),
            intent="20-day average",
            requested_name="my_rsi",
        )

        response = use_case.execute(request)

        assert response.registered is False
        assert response.register_error == "boom"
        assert response.saved is True

    def test_no_ast_skips_registration_but_still_saves(self):
        store = FakeFormulaStore()
        registry = FakeIndicatorRegistry()
        use_case = PersistGeneratedFormulaUseCase(store, registry)
        request = PersistGeneratedFormulaRequest(
            formula="SMA(20)",
            ast=None,
            intent="20-day average",
            requested_name="my_rsi",
        )

        response = use_case.execute(request)

        assert response.register_attempted is False
        assert response.registered is False
        assert response.register_error is None
        assert registry.register_calls == []
        assert response.saved is True

    def test_save_failure_is_non_fatal(self):
        store = FakeFormulaStore()
        store.fail_save = FormulaStoreError("disk full")
        registry = FakeIndicatorRegistry()
        use_case = PersistGeneratedFormulaUseCase(store, registry)
        request = PersistGeneratedFormulaRequest(
            formula="SMA(20)",
            ast=object(),
            intent="20-day average",
            requested_name="my_rsi",
        )

        response = use_case.execute(request)

        assert response.saved is False
        assert response.save_error == "disk full"
        assert response.name == "MY_RSI"

    def test_save_false_skips_persistence_entirely(self):
        store = FakeFormulaStore()
        registry = FakeIndicatorRegistry()
        use_case = PersistGeneratedFormulaUseCase(store, registry)
        request = PersistGeneratedFormulaRequest(
            formula="SMA(20)",
            ast=object(),
            intent="20-day average",
            requested_name="my_rsi",
            save=False,
        )

        response = use_case.execute(request)

        assert response.save_attempted is False
        assert response.saved is False
        assert store.save_calls == []

    def test_lowercase_requested_name_is_uppercased(self):
        store = FakeFormulaStore()
        registry = FakeIndicatorRegistry()
        use_case = PersistGeneratedFormulaUseCase(store, registry)
        request = PersistGeneratedFormulaRequest(
            formula="SMA(20)",
            ast=object(),
            intent="20-day average",
            requested_name="lower",
        )

        response = use_case.execute(request)

        assert response.name == "LOWER"
