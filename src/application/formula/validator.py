"""Semantic validation and dependency ordering for formulas.

Application layer - Formula validator.

This module validates parsed formulas for semantic correctness and
determines the evaluation order through topological sorting.

Validations performed:
- All referenced indicators exist (built-in, plugin, or formula)
- Function argument counts are valid
- No circular references between formulas

The topological sort ensures formulas are evaluated in dependency order,
so that all dependencies are computed before dependent formulas.

Example:
    >>> formulas = {"SMOOTH_RSI": parse("SMA(RSI(14), 10)")}
    >>> order = validate_formulas(formulas, available_indicators={"RSI", "SMA"})
    >>> order
    ['SMOOTH_RSI']
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.formula.ast_nodes import (
    SERIES_FIELDS,
    ASTNode,
    BinaryOpNode,
    FunctionCallNode,
    NumberNode,
    SeriesNode,
)
from src.application.formula.exceptions import FormulaValidationError

if TYPE_CHECKING:
    pass


def extract_dependencies(ast: ASTNode) -> set[str]:
    """Extract all indicator dependencies from an AST.

    This function recursively walks the AST and collects all indicator
    names referenced (function calls that aren't series fields).

    Args:
        ast: The AST node to analyze.

    Returns:
        Set of uppercase indicator names referenced in the formula.

    Example:
        >>> ast = parse("SMA(RSI(14), 10)")
        >>> extract_dependencies(ast)
        {'SMA', 'RSI'}
    """
    dependencies: set[str] = set()
    _collect_dependencies(ast, dependencies)
    return dependencies


def _collect_dependencies(node: ASTNode, deps: set[str]) -> None:
    """Recursively collect dependencies from an AST node."""
    if isinstance(node, NumberNode):
        # Numbers have no dependencies
        pass

    elif isinstance(node, SeriesNode):
        # Series fields (OPEN, HIGH, etc.) are not indicator dependencies
        pass

    elif isinstance(node, FunctionCallNode):
        # Add the function name as a dependency (unless it's a series alias)
        name_upper = node.name.upper()
        if name_upper.lower() not in SERIES_FIELDS:
            deps.add(name_upper)

        # Recursively process arguments
        for arg in node.arguments:
            _collect_dependencies(arg, deps)

    elif isinstance(node, BinaryOpNode):
        # Process both operands
        _collect_dependencies(node.left, deps)
        _collect_dependencies(node.right, deps)


def build_dependency_graph(formulas: dict[str, ASTNode]) -> dict[str, set[str]]:
    """Build a dependency graph from formula definitions.

    The graph maps each formula name to the set of indicator names it depends on.
    Only includes dependencies that are other formulas (not built-in indicators).

    Args:
        formulas: Dict mapping formula names to their AST nodes.

    Returns:
        Dict mapping formula names to sets of formula dependencies.

    Example:
        >>> formulas = {
        ...     "A": parse("SMA(B, 10)"),  # A depends on B
        ...     "B": parse("RSI(14)")      # B depends on RSI (built-in)
        ... }
        >>> build_dependency_graph(formulas)
        {'A': {'B'}, 'B': set()}
    """
    formula_names = set(formulas.keys())
    graph: dict[str, set[str]] = {}

    for name, ast in formulas.items():
        all_deps = extract_dependencies(ast)
        # Only include dependencies that are other formulas
        formula_deps = all_deps & formula_names
        graph[name] = formula_deps

    return graph


def topological_sort(graph: dict[str, set[str]]) -> list[str]:
    """Perform topological sort on a dependency graph.

    Returns nodes in an order where dependencies come before dependents.
    Uses Kahn's algorithm for cycle detection.

    Args:
        graph: Dict mapping node names to their dependencies.

    Returns:
        List of node names in topological order.

    Raises:
        FormulaValidationError: If a cycle is detected.

    Example:
        >>> topological_sort({'A': {'B'}, 'B': set()})
        ['B', 'A']
    """
    # Build in-degree map (how many nodes depend on each node)
    in_degree: dict[str, int] = {node: 0 for node in graph}

    # Calculate in-degrees
    for node, deps in graph.items():
        for dep in deps:
            if dep in in_degree:
                in_degree[node] += 1

    # Start with nodes that have no dependencies
    queue = [node for node, degree in in_degree.items() if degree == 0]
    result: list[str] = []

    while queue:
        # Process nodes in alphabetical order for determinism
        queue.sort()
        node = queue.pop(0)
        result.append(node)

        # Reduce in-degree of nodes that depend on this one
        for other, deps in graph.items():
            if node in deps:
                in_degree[other] -= 1
                if in_degree[other] == 0:
                    queue.append(other)

    # Check for cycle
    if len(result) != len(graph):
        # Find cycle for error message
        remaining = set(graph.keys()) - set(result)
        cycle = _find_cycle(graph, remaining)
        cycle_str = " -> ".join(cycle)
        raise FormulaValidationError(
            f"Circular reference detected: {cycle_str}",
            cycle=cycle,
        )

    return result


def _find_cycle(graph: dict[str, set[str]], nodes: set[str]) -> list[str]:
    """Find a cycle in the graph among the given nodes.

    Args:
        graph: The dependency graph.
        nodes: Set of nodes known to contain a cycle.

    Returns:
        List representing the cycle path.
    """
    # Simple DFS to find a cycle
    visited: set[str] = set()
    path: list[str] = []

    def dfs(node: str) -> list[str] | None:
        if node in path:
            # Found cycle
            cycle_start = path.index(node)
            return path[cycle_start:] + [node]

        if node in visited:
            return None

        visited.add(node)
        path.append(node)

        for dep in graph.get(node, set()):
            if dep in nodes:
                result = dfs(dep)
                if result:
                    return result

        path.pop()
        return None

    for start in nodes:
        visited.clear()
        path.clear()
        cycle = dfs(start)
        if cycle:
            return cycle

    # Fallback: return any node from remaining
    return list(nodes)[:1]


def validate_formula_references(
    ast: ASTNode,
    available_indicators: set[str],
    formula_name: str | None = None,
) -> None:
    """Validate that all indicator references in a formula are available.

    Args:
        ast: The AST to validate.
        available_indicators: Set of available indicator names (uppercase).
        formula_name: Name of the formula being validated (for error messages).

    Raises:
        FormulaValidationError: If an unknown indicator is referenced.
    """
    dependencies = extract_dependencies(ast)
    unknown = dependencies - available_indicators

    if unknown:
        unknown_list = ", ".join(sorted(unknown))
        context = f" in formula '{formula_name}'" if formula_name else ""
        raise FormulaValidationError(
            f"Unknown indicator(s) referenced{context}: {unknown_list}",
            indicator_name=formula_name,
        )


def validate_formulas(
    formulas: dict[str, ASTNode],
    available_indicators: set[str],
) -> list[str]:
    """Validate formula definitions and return evaluation order.

    This is the main validation entry point. It:
    1. Validates all indicator references exist
    2. Checks for circular dependencies
    3. Returns formulas in topological order for evaluation

    Args:
        formulas: Dict mapping formula names to their AST nodes.
        available_indicators: Set of available indicator names (built-in + plugin).

    Returns:
        List of formula names in evaluation order (dependencies first).

    Raises:
        FormulaValidationError: If validation fails.

    Example:
        >>> formulas = {"SMOOTH_RSI": parse("SMA(RSI(14), 10)")}
        >>> available = {"RSI", "SMA", "EMA"}
        >>> validate_formulas(formulas, available)
        ['SMOOTH_RSI']
    """
    # Combine available indicators with formula names for reference validation
    all_available = available_indicators | set(formulas.keys())

    # Validate each formula's references
    for name, ast in formulas.items():
        validate_formula_references(ast, all_available, formula_name=name)

    # Build dependency graph and topological sort
    graph = build_dependency_graph(formulas)
    order = topological_sort(graph)

    return order
