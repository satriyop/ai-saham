"""
Integration tests for formula workflow.

Tests the complete flow:
1. Create indicator from intent
2. Persist formula to storage
3. Reload on startup
4. Use formula in computation

Uses mock provider and temporary storage.
"""

import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.application.services.bootstrap import create_indicator_registry
from src.application.services.indicator_registry import IndicatorRegistry
from src.application.use_case.create_indicator_from_intent_use_case import (
    CreateIndicatorFromIntentRequest,
    CreateIndicatorFromIntentUseCase,
)
from src.domain.entities.candle import Candle
from src.infrastructure.ai.formula_translator import FormulaTranslatorAdapter
from src.infrastructure.persistence.formula_storage import FormulaStorage

# --- Fixtures ---


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def formulas_path(temp_dir):
    """Create temporary formulas file path."""
    return temp_dir / "formulas.yaml"


@pytest.fixture
def storage(formulas_path):
    """Create storage with temp path."""
    return FormulaStorage(path=formulas_path)


@pytest.fixture
def sample_candles():
    """Create sample candles for testing."""
    from datetime import timedelta

    base_date = date(2024, 1, 1)
    return [
        Candle(
            ticker="TEST",
            date=base_date + timedelta(days=i),
            open=Decimal(f"{1000 + i * 10}"),
            high=Decimal(f"{1100 + i * 10}"),
            low=Decimal(f"{900 + i * 10}"),
            close=Decimal(f"{1050 + i * 10}"),
            volume=100000 + i * 1000,
        )
        for i in range(50)  # 50 days of data
    ]


# --- Tests ---


class TestFormulaWorkflowIntegration:
    """Test complete formula workflow."""

    def test_create_and_persist_workflow(self, storage):
        """Create indicator, validate, and persist."""
        # 1. Create registry
        registry = IndicatorRegistry()
        available = registry.get_available_indicators()

        # 2. Create translator with mock provider
        translator = FormulaTranslatorAdapter(provider="mock")

        # 3. Create use case
        use_case = CreateIndicatorFromIntentUseCase(
            translator=translator,
            available_functions=available,
        )

        # 4. Translate intent
        response = use_case.execute(
            CreateIndicatorFromIntentRequest(
                intent="smoothed RSI with 14 period",
                indicator_name="SMOOTH_RSI",
            )
        )

        assert response.success
        assert response.formula == "SMA(RSI(14), 10)"
        assert response.ast is not None

        # 5. Register in memory
        registry.register_formula("SMOOTH_RSI", response.ast)
        assert registry.is_registered("SMOOTH_RSI")

        # 6. Persist to storage
        storage.save("SMOOTH_RSI", response.formula, intent="smoothed RSI")
        assert storage.exists("SMOOTH_RSI")

    def test_reload_formulas_on_startup(self, storage, formulas_path):
        """Formulas should be reloaded on registry creation."""
        # 1. Save formula to storage
        storage.save("MY_RSI", "RSI(14)", intent="14-day RSI")

        # 2. Create new registry with formula loading
        registry = create_indicator_registry(
            formula_storage=storage,
            load_formulas=True,
        )

        # 3. Verify formula is registered
        assert registry.is_registered("MY_RSI")
        assert "MY_RSI" in registry.list_formulas()

    def test_compute_persisted_formula(self, storage, sample_candles):
        """Should be able to compute a persisted formula."""
        # 1. Save formula to storage
        storage.save("SMOOTH_RSI", "SMA(RSI(14), 10)")

        # 2. Create registry with formulas
        registry = create_indicator_registry(
            formula_storage=storage,
            load_formulas=True,
        )

        # 3. Compute formula
        result = registry.compute("SMOOTH_RSI", sample_candles, period=0)

        # 4. Verify result
        assert len(result) > 0
        assert all(isinstance(v, Decimal) for _, v in result)

    def test_skip_formula_loading(self, storage, formulas_path):
        """Should skip formula loading when disabled."""
        # 1. Save formula to storage
        storage.save("MY_RSI", "RSI(14)")

        # 2. Create registry WITHOUT formula loading
        registry = create_indicator_registry(
            formula_storage=storage,
            load_formulas=False,
        )

        # 3. Verify formula is NOT registered
        assert not registry.is_registered("MY_RSI")

    def test_invalid_formula_skipped(self, storage):
        """Invalid formulas should be skipped with warning."""
        # 1. Save invalid formula (will fail to parse)
        storage._save_raw({
            "formulas": {
                "INVALID": {
                    "formula": "INVALID_SYNTAX(((",
                    "intent": "bad formula",
                    "created": "2024-01-01T00:00:00",
                },
                "VALID": {
                    "formula": "RSI(14)",
                    "intent": "valid formula",
                    "created": "2024-01-01T00:00:00",
                },
            }
        })

        # 2. Create registry - should skip invalid
        registry = create_indicator_registry(
            formula_storage=storage,
            load_formulas=True,
        )

        # 3. Valid formula should be loaded
        assert registry.is_registered("VALID")

        # 4. Invalid formula should be skipped
        assert not registry.is_registered("INVALID")

    def test_full_workflow_end_to_end(self, temp_dir, sample_candles):
        """Test complete workflow from intent to computation."""
        formulas_path = temp_dir / "formulas.yaml"
        storage = FormulaStorage(path=formulas_path)

        # --- Phase 1: Create and persist ---

        # Create registry
        registry = IndicatorRegistry()

        # Translate intent
        translator = FormulaTranslatorAdapter(provider="mock")
        use_case = CreateIndicatorFromIntentUseCase(
            translator=translator,
            available_functions=registry.get_available_indicators(),
        )

        response = use_case.execute(
            CreateIndicatorFromIntentRequest(
                intent="14-day RSI",
                indicator_name="MY_RSI",
            )
        )

        assert response.success

        # Persist
        storage.save("MY_RSI", response.formula, intent="14-day RSI")

        # --- Phase 2: Simulate restart ---

        # Create fresh registry that loads from storage
        new_registry = create_indicator_registry(
            formula_storage=storage,
            load_formulas=True,
        )

        # --- Phase 3: Use formula ---

        # Verify formula is available
        assert new_registry.is_registered("MY_RSI")

        # Compute
        result = new_registry.compute("MY_RSI", sample_candles, period=0)

        # Verify computation
        assert len(result) > 0

        # RSI should be bounded 0-100
        for dt, value in result:
            assert Decimal("0") <= value <= Decimal("100")


class TestBootstrapWithFormulas:
    """Test bootstrap integration with formula loading."""

    def test_default_storage_path(self, temp_dir, monkeypatch):
        """Default storage path should be project-local formulas.yaml."""
        # Change to temp directory so project-local path resolves there
        monkeypatch.chdir(temp_dir)

        # Create registry with default loading
        # This should look for formulas.yaml in project root
        registry = create_indicator_registry(
            load_formulas=True,
        )

        # Should work without errors even with no formulas
        assert registry is not None
        assert registry.is_registered("SMA")  # Built-in

    def test_custom_storage_path(self, temp_dir):
        """Should use custom storage path when provided."""
        # Create storage at custom path
        custom_path = temp_dir / "custom" / "formulas.yaml"
        storage = FormulaStorage(path=custom_path)
        storage.save("CUSTOM", "RSI(14)")

        # Create registry with custom storage
        registry = create_indicator_registry(
            formula_storage=storage,
            load_formulas=True,
        )

        assert registry.is_registered("CUSTOM")
