"""Tests for the formula validator."""

import pytest

from src.application.formula.exceptions import FormulaValidationError
from src.application.formula.parser import parse
from src.application.formula.validator import (
    build_dependency_graph,
    extract_dependencies,
    topological_sort,
    validate_formula_references,
    validate_formulas,
)


class TestExtractDependencies:
    """Tests for the extract_dependencies function."""

    def test_simple_function(self) -> None:
        """Test extracting dependencies from simple function."""
        ast = parse("RSI(14)")
        deps = extract_dependencies(ast)
        assert deps == {"RSI"}

    def test_function_with_series(self) -> None:
        """Test that series fields are not counted as dependencies."""
        ast = parse("SMA(CLOSE, 20)")
        deps = extract_dependencies(ast)
        assert deps == {"SMA"}
        assert "CLOSE" not in deps

    def test_nested_functions(self) -> None:
        """Test extracting dependencies from nested functions."""
        ast = parse("SMA(RSI(14), 10)")
        deps = extract_dependencies(ast)
        assert deps == {"SMA", "RSI"}

    def test_binary_operation(self) -> None:
        """Test extracting dependencies from binary operation."""
        ast = parse("EMA(CLOSE, 12) - EMA(CLOSE, 26)")
        deps = extract_dependencies(ast)
        assert deps == {"EMA"}

    def test_number_only(self) -> None:
        """Test that number-only expression has no dependencies."""
        ast = parse("42")
        deps = extract_dependencies(ast)
        assert deps == set()

    def test_series_only(self) -> None:
        """Test that series-only expression has no dependencies."""
        ast = parse("CLOSE")
        deps = extract_dependencies(ast)
        assert deps == set()

    def test_series_multiplication(self) -> None:
        """Test CLOSE * VOLUME has no indicator dependencies."""
        ast = parse("CLOSE * VOLUME")
        deps = extract_dependencies(ast)
        assert deps == set()

    def test_complex_formula(self) -> None:
        """Test extracting dependencies from complex formula."""
        ast = parse("(SMA(RSI(14), 10) + EMA(CLOSE, 20)) / 2")
        deps = extract_dependencies(ast)
        assert deps == {"SMA", "RSI", "EMA"}


class TestBuildDependencyGraph:
    """Tests for the build_dependency_graph function."""

    def test_single_formula_no_deps(self) -> None:
        """Test graph with single formula that has no formula dependencies."""
        formulas = {"A": parse("SMA(CLOSE, 20)")}
        graph = build_dependency_graph(formulas)
        assert graph == {"A": set()}

    def test_formula_depends_on_another(self) -> None:
        """Test graph where formula A depends on formula B."""
        formulas = {
            "A": parse("SMA(B, 10)"),  # A depends on B
            "B": parse("RSI(14)"),  # B has no formula dependencies
        }
        graph = build_dependency_graph(formulas)
        assert graph == {"A": {"B"}, "B": set()}

    def test_multiple_independent_formulas(self) -> None:
        """Test graph with independent formulas."""
        formulas = {
            "A": parse("SMA(CLOSE, 20)"),
            "B": parse("EMA(CLOSE, 20)"),
        }
        graph = build_dependency_graph(formulas)
        assert graph == {"A": set(), "B": set()}

    def test_chain_dependencies(self) -> None:
        """Test graph with chain: A -> B -> C."""
        formulas = {
            "A": parse("SMA(B, 10)"),
            "B": parse("EMA(C, 10)"),
            "C": parse("RSI(14)"),
        }
        graph = build_dependency_graph(formulas)
        assert graph == {"A": {"B"}, "B": {"C"}, "C": set()}


class TestTopologicalSort:
    """Tests for the topological_sort function."""

    def test_single_node(self) -> None:
        """Test sorting single node."""
        graph = {"A": set()}
        order = topological_sort(graph)
        assert order == ["A"]

    def test_two_nodes_no_deps(self) -> None:
        """Test sorting two independent nodes."""
        graph = {"A": set(), "B": set()}
        order = topological_sort(graph)
        # Alphabetical order when no dependencies
        assert order == ["A", "B"]

    def test_simple_dependency(self) -> None:
        """Test sorting with simple dependency."""
        graph = {"A": {"B"}, "B": set()}
        order = topological_sort(graph)
        # B must come before A
        assert order.index("B") < order.index("A")

    def test_chain(self) -> None:
        """Test sorting chain: A -> B -> C."""
        graph = {"A": {"B"}, "B": {"C"}, "C": set()}
        order = topological_sort(graph)
        assert order.index("C") < order.index("B")
        assert order.index("B") < order.index("A")

    def test_diamond(self) -> None:
        """Test sorting diamond: A -> B, A -> C, B -> D, C -> D."""
        graph = {
            "A": {"B", "C"},
            "B": {"D"},
            "C": {"D"},
            "D": set(),
        }
        order = topological_sort(graph)
        assert order.index("D") < order.index("B")
        assert order.index("D") < order.index("C")
        assert order.index("B") < order.index("A")
        assert order.index("C") < order.index("A")

    def test_circular_reference_detected(self) -> None:
        """Test that circular reference raises error."""
        graph = {"A": {"B"}, "B": {"A"}}
        with pytest.raises(FormulaValidationError) as exc_info:
            topological_sort(graph)
        assert "Circular reference" in str(exc_info.value)

    def test_self_reference_detected(self) -> None:
        """Test that self-reference raises error."""
        graph = {"A": {"A"}}
        with pytest.raises(FormulaValidationError) as exc_info:
            topological_sort(graph)
        assert "Circular reference" in str(exc_info.value)

    def test_larger_cycle_detected(self) -> None:
        """Test that larger cycles are detected."""
        graph = {"A": {"B"}, "B": {"C"}, "C": {"A"}}
        with pytest.raises(FormulaValidationError) as exc_info:
            topological_sort(graph)
        assert "Circular reference" in str(exc_info.value)
        # Error should include cycle path
        assert exc_info.value.cycle is not None


class TestValidateFormulaReferences:
    """Tests for the validate_formula_references function."""

    def test_valid_references(self) -> None:
        """Test validation passes with valid references."""
        ast = parse("SMA(RSI(14), 10)")
        available = {"SMA", "RSI"}
        # Should not raise
        validate_formula_references(ast, available)

    def test_unknown_indicator(self) -> None:
        """Test error on unknown indicator reference."""
        ast = parse("UNKNOWN(14)")
        available = {"SMA", "RSI"}
        with pytest.raises(FormulaValidationError) as exc_info:
            validate_formula_references(ast, available)
        assert "Unknown indicator" in str(exc_info.value)
        assert "UNKNOWN" in str(exc_info.value)

    def test_partial_unknown(self) -> None:
        """Test error when some references are unknown."""
        ast = parse("SMA(UNKNOWN(14), 10)")
        available = {"SMA", "RSI"}
        with pytest.raises(FormulaValidationError) as exc_info:
            validate_formula_references(ast, available)
        assert "UNKNOWN" in str(exc_info.value)

    def test_formula_name_in_error(self) -> None:
        """Test that formula name appears in error message."""
        ast = parse("BAD(14)")
        available = {"SMA"}
        with pytest.raises(FormulaValidationError) as exc_info:
            validate_formula_references(ast, available, formula_name="MY_FORMULA")
        assert "MY_FORMULA" in str(exc_info.value)


class TestValidateFormulas:
    """Tests for the validate_formulas function."""

    def test_valid_formulas(self) -> None:
        """Test validation with valid formulas."""
        formulas = {
            "SMOOTH_RSI": parse("SMA(RSI(14), 10)"),
        }
        available = {"SMA", "RSI"}
        order = validate_formulas(formulas, available)
        assert order == ["SMOOTH_RSI"]

    def test_formula_referencing_formula(self) -> None:
        """Test formula that references another formula."""
        formulas = {
            "A": parse("SMA(B, 10)"),
            "B": parse("RSI(14)"),
        }
        available = {"SMA", "RSI"}
        order = validate_formulas(formulas, available)
        # B must be computed before A
        assert order.index("B") < order.index("A")

    def test_circular_reference_error(self) -> None:
        """Test error on circular formula references."""
        formulas = {
            "A": parse("SMA(B, 10)"),
            "B": parse("EMA(A, 10)"),
        }
        available = {"SMA", "EMA"}
        with pytest.raises(FormulaValidationError) as exc_info:
            validate_formulas(formulas, available)
        assert "Circular reference" in str(exc_info.value)

    def test_unknown_indicator_error(self) -> None:
        """Test error on unknown indicator in formula."""
        formulas = {
            "MY_INDICATOR": parse("UNKNOWN(14)"),
        }
        available = {"SMA", "RSI"}
        with pytest.raises(FormulaValidationError) as exc_info:
            validate_formulas(formulas, available)
        assert "Unknown indicator" in str(exc_info.value)

    def test_empty_formulas(self) -> None:
        """Test validation of empty formula dict."""
        order = validate_formulas({}, {"SMA", "RSI"})
        assert order == []

    def test_complex_dependency_chain(self) -> None:
        """Test validation with complex dependency chain."""
        formulas = {
            "D": parse("SMA(C, 5)"),
            "C": parse("EMA(B, 10)"),
            "B": parse("SMA(A, 15)"),
            "A": parse("RSI(14)"),
        }
        available = {"SMA", "EMA", "RSI"}
        order = validate_formulas(formulas, available)

        # Verify order: A before B before C before D
        assert order.index("A") < order.index("B")
        assert order.index("B") < order.index("C")
        assert order.index("C") < order.index("D")
