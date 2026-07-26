"""
Tests for FormulaStorage persistence.

Verifies:
- Save, load, delete operations
- YAML file format
- Error handling
- Name case handling

Uses temporary directories for isolation.
"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from src.application.dto.stored_formula import StoredFormula
from src.infrastructure.persistence.formula_storage import FormulaStorage

# --- Fixtures ---


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def storage(temp_dir):
    """Create storage with temp path."""
    return FormulaStorage(path=temp_dir / "formulas.yaml")


# --- Tests ---


class TestFormulaStorage:
    """Test FormulaStorage operations."""

    def test_save_creates_file(self, storage):
        """Should create storage file on first save."""
        assert not storage.path.exists()

        storage.save("TEST", "SMA(CLOSE, 20)")

        assert storage.path.exists()

    def test_save_and_load(self, storage):
        """Should save and load formula."""
        storage.save("SMOOTH_RSI", "SMA(RSI(14), 10)", intent="smoothed RSI")

        formulas = storage.load_all()

        assert "SMOOTH_RSI" in formulas
        assert formulas["SMOOTH_RSI"].formula == "SMA(RSI(14), 10)"
        assert formulas["SMOOTH_RSI"].intent == "smoothed RSI"

    def test_save_uppercases_name(self, storage):
        """Should uppercase formula name in storage."""
        storage.save("smooth_rsi", "SMA(RSI(14), 10)")

        # Verify name is uppercased in storage
        assert storage.exists("SMOOTH_RSI")

        # Check raw storage has uppercase key
        formulas = storage.load_all()
        assert "SMOOTH_RSI" in formulas
        assert "smooth_rsi" not in formulas

    def test_save_overwrites_existing(self, storage):
        """Should overwrite formula with same name."""
        storage.save("TEST", "SMA(CLOSE, 10)")
        storage.save("TEST", "EMA(CLOSE, 20)")

        stored = storage.get("TEST")

        assert stored.formula == "EMA(CLOSE, 20)"

    def test_get_returns_stored_formula(self, storage):
        """Should return StoredFormula with metadata."""
        storage.save("MACD", "EMA(CLOSE, 12) - EMA(CLOSE, 26)", intent="MACD line")

        stored = storage.get("MACD")

        assert isinstance(stored, StoredFormula)
        assert stored.name == "MACD"
        assert stored.formula == "EMA(CLOSE, 12) - EMA(CLOSE, 26)"
        assert stored.intent == "MACD line"
        assert isinstance(stored.created, datetime)

    def test_get_returns_none_when_not_found(self, storage):
        """Should return None for non-existent formula."""
        result = storage.get("NONEXISTENT")
        assert result is None

    def test_get_case_insensitive(self, storage):
        """Should be case-insensitive for get."""
        storage.save("SMOOTH_RSI", "SMA(RSI(14), 10)")

        assert storage.get("smooth_rsi") is not None
        assert storage.get("SMOOTH_RSI") is not None
        assert storage.get("Smooth_Rsi") is not None

    def test_exists_returns_true_when_found(self, storage):
        """Should return True when formula exists."""
        storage.save("TEST", "SMA(CLOSE, 20)")

        assert storage.exists("TEST") is True
        assert storage.exists("test") is True  # Case insensitive

    def test_exists_returns_false_when_not_found(self, storage):
        """Should return False when formula doesn't exist."""
        assert storage.exists("NONEXISTENT") is False

    def test_delete_removes_formula(self, storage):
        """Should delete existing formula."""
        storage.save("TEST", "SMA(CLOSE, 20)")

        deleted = storage.delete("TEST")

        assert deleted is True
        assert storage.exists("TEST") is False

    def test_delete_returns_false_when_not_found(self, storage):
        """Should return False when formula doesn't exist."""
        deleted = storage.delete("NONEXISTENT")
        assert deleted is False

    def test_delete_case_insensitive(self, storage):
        """Should be case-insensitive for delete."""
        storage.save("TEST", "SMA(CLOSE, 20)")

        deleted = storage.delete("test")

        assert deleted is True
        assert storage.exists("TEST") is False

    def test_load_all_returns_empty_when_no_file(self, storage):
        """Should return empty dict when file doesn't exist."""
        formulas = storage.load_all()
        assert formulas == {}

    def test_load_all_returns_all_formulas(self, storage):
        """Should return all saved formulas."""
        storage.save("TEST1", "SMA(CLOSE, 10)")
        storage.save("TEST2", "EMA(CLOSE, 20)")
        storage.save("TEST3", "RSI(14)")

        formulas = storage.load_all()

        assert len(formulas) == 3
        assert "TEST1" in formulas
        assert "TEST2" in formulas
        assert "TEST3" in formulas

    def test_list_names_returns_sorted(self, storage):
        """Should return sorted list of formula names."""
        storage.save("ZEBRA", "SMA(CLOSE, 10)")
        storage.save("ALPHA", "EMA(CLOSE, 20)")
        storage.save("BETA", "RSI(14)")

        names = storage.list_names()

        assert names == ["ALPHA", "BETA", "ZEBRA"]

    def test_len_returns_count(self, storage):
        """Should return number of stored formulas."""
        assert len(storage) == 0

        storage.save("TEST1", "SMA(CLOSE, 10)")
        assert len(storage) == 1

        storage.save("TEST2", "EMA(CLOSE, 20)")
        assert len(storage) == 2

    def test_iteration(self, storage):
        """Should be iterable."""
        storage.save("TEST1", "SMA(CLOSE, 10)")
        storage.save("TEST2", "EMA(CLOSE, 20)")

        formulas = list(storage)

        assert len(formulas) == 2
        assert all(isinstance(f, StoredFormula) for f in formulas)

    def test_creates_parent_directories(self, temp_dir):
        """Should create parent directories if needed."""
        nested_path = temp_dir / "nested" / "deep" / "formulas.yaml"
        storage = FormulaStorage(path=nested_path)

        storage.save("TEST", "SMA(CLOSE, 20)")

        assert nested_path.exists()

    def test_yaml_format_readable(self, storage):
        """Should save in human-readable YAML format."""
        storage.save("SMOOTH_RSI", "SMA(RSI(14), 10)", intent="smoothed RSI")

        # Read raw YAML
        with open(storage.path, "r") as f:
            content = f.read()
            data = yaml.safe_load(content)

        assert "formulas" in data
        assert "SMOOTH_RSI" in data["formulas"]
        assert data["formulas"]["SMOOTH_RSI"]["formula"] == "SMA(RSI(14), 10)"
        assert data["formulas"]["SMOOTH_RSI"]["intent"] == "smoothed RSI"

    def test_handles_empty_yaml_file(self, storage):
        """Should handle empty YAML file gracefully."""
        # Create empty file
        storage.path.parent.mkdir(parents=True, exist_ok=True)
        storage.path.touch()

        formulas = storage.load_all()

        assert formulas == {}

    def test_handles_invalid_yaml(self, storage):
        """Should handle invalid YAML gracefully."""
        # Write invalid YAML
        storage.path.parent.mkdir(parents=True, exist_ok=True)
        with open(storage.path, "w") as f:
            f.write("invalid: yaml: content: [unclosed")

        formulas = storage.load_all()

        assert formulas == {}

    def test_intent_is_optional(self, storage):
        """Should handle formulas without intent."""
        storage.save("TEST", "SMA(CLOSE, 20)")  # No intent

        stored = storage.get("TEST")

        assert stored.intent is None


class TestStoredFormula:
    """Test StoredFormula dataclass."""

    def test_is_frozen(self):
        """StoredFormula should be immutable."""
        formula = StoredFormula(
            name="TEST",
            formula="SMA(CLOSE, 20)",
            intent=None,
            created=datetime.now(),
        )

        with pytest.raises(AttributeError):
            formula.name = "CHANGED"

    def test_equality(self):
        """StoredFormula should support equality."""
        now = datetime.now()
        f1 = StoredFormula(name="TEST", formula="SMA(CLOSE, 20)", intent=None, created=now)
        f2 = StoredFormula(name="TEST", formula="SMA(CLOSE, 20)", intent=None, created=now)

        assert f1 == f2
