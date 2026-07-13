"""Executable guard for hexagonal layer boundaries.

Layer: Test (architecture guard, no runtime behavior).

Scans src/domain, src/application, src/infrastructure with the Python ast
module and fails on any forbidden cross-layer or forbidden-library import
that is not already listed in BASELINE_ALLOWLIST. New violations must not
be added to the allowlist — fix the import instead.
"""
import ast
from dataclasses import dataclass
from pathlib import Path

SRC_ROOT = Path("src")


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    imported: str
    rule: str


FORBIDDEN_LAYER_IMPORTS = {
    "src/domain": {
        "src.application": "domain must not import application",
        "src.infrastructure": "domain must not import infrastructure",
        "src.adapters": "domain must not import adapters",
    },
    "src/application": {
        "src.infrastructure": "application must not import infrastructure",
        "src.adapters": "application must not import adapters",
    },
    "src/infrastructure": {
        "src.adapters": "infrastructure must not import adapters",
    },
}

FORBIDDEN_LIBRARY_IMPORTS = {
    "src/domain": {
        "sqlite3": "domain must not import database libraries",
        "requests": "domain must not import HTTP clients",
        "httpx": "domain must not import HTTP clients",
        "typer": "domain must not import CLI libraries",
        "rich": "domain must not import display libraries",
        "yaml": "domain must not import YAML parser",
    },
    "src/application": {
        "sqlite3": "application must not import database libraries",
        "requests": "application must not import HTTP clients",
        "httpx": "application must not import HTTP clients",
        "typer": "application must not import CLI libraries",
        "rich": "application must not import display libraries",
    },
}


@dataclass(frozen=True)
class AllowlistEntry:
    """Structured cleanup debt record for a legacy boundary violation.

    Every field is required so an entry can never regress into a vague,
    unowned permanent exception (see docs/code-convention-audit.md finding 2).
    """

    reason: str
    cleanup_owner: str
    canonical_fix: str
    issue: str


_RULES_LOADER_REASON = (
    "LEGACY: application code calls infrastructure YAML loader directly; "
    "predates architecture guard."
)
_RULES_LOADER_FIX = (
    "Define an application-owned RulesSource port and have infrastructure "
    "provide the RulesYamlLoader implementation behind it, so application "
    "code depends only on the port."
)

# Baseline of pre-existing violations, captured before this guard existed.
# Do NOT add new entries here for code written after this guard was added —
# fix the import instead. Every entry is tracked cleanup debt with an owner
# and a canonical fix direction; see docs/code-convention-audit.md finding 2.
BASELINE_ALLOWLIST: dict[tuple[str, str], AllowlistEntry] = {
    (
        "src/application/services/strategy_loader.py",
        "src.infrastructure.config.rules_yaml_loader",
    ): AllowlistEntry(
        reason=_RULES_LOADER_REASON,
        cleanup_owner="rules_loader_boundary",
        canonical_fix=_RULES_LOADER_FIX,
        issue="code-convention-audit finding 2",
    ),
    (
        "src/application/use_case/backtest_use_case.py",
        "src.infrastructure.config.rules_yaml_loader",
    ): AllowlistEntry(
        reason=_RULES_LOADER_REASON,
        cleanup_owner="rules_loader_boundary",
        canonical_fix=_RULES_LOADER_FIX,
        issue="code-convention-audit finding 2",
    ),
    (
        "src/application/use_case/create_strategy_from_intent_use_case.py",
        "src.infrastructure.config.rules_yaml_loader",
    ): AllowlistEntry(
        reason=_RULES_LOADER_REASON,
        cleanup_owner="rules_loader_boundary",
        canonical_fix=_RULES_LOADER_FIX,
        issue="code-convention-audit finding 2",
    ),
    (
        "src/application/use_case/view_universe_summary_use_case.py",
        "src.infrastructure.persistence.sqlite_universe_summary_provider",
    ): AllowlistEntry(
        reason=(
            "LEGACY: application use case constructs infrastructure "
            "provider directly; predates architecture guard."
        ),
        cleanup_owner="universe_summary_boundary",
        canonical_fix=(
            "Inject a UniverseSummaryProvider port into the use case "
            "constructor and move SqliteUniverseSummaryProvider "
            "construction to adapter/composition-root wiring."
        ),
        issue="code-convention-audit finding 2",
    ),
    (
        "src/domain/rules/technical_gate.py",
        "src.application.services.indicator_evaluator",
    ): AllowlistEntry(
        reason=(
            "LEGACY: TYPE_CHECKING-only forward reference for a "
            "constructor parameter hint; not a runtime import but "
            "still ast-visible."
        ),
        cleanup_owner="technical_gate_protocol",
        canonical_fix=(
            "Replace the TYPE_CHECKING import with a domain-level "
            "Protocol port describing the indicator-evaluator "
            "interface, so domain has no reference to the application "
            "module even under TYPE_CHECKING."
        ),
        issue="code-convention-audit finding 2",
    ),
}

ALLOWLISTED_PATHS_REQUIRE_BOUNDARY_CLEANUP = frozenset(
    {
        "src/application/services/strategy_loader.py",
        "src/application/use_case/backtest_use_case.py",
        "src/application/use_case/create_strategy_from_intent_use_case.py",
        "src/application/use_case/view_universe_summary_use_case.py",
        "src/domain/rules/technical_gate.py",
    }
)


def _iter_python_files():
    for root in ("src/domain", "src/application", "src/infrastructure"):
        yield from Path(root).rglob("*.py")


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                yield node.lineno, node.module


def _matches(imported: str, forbidden: str) -> bool:
    return imported == forbidden or imported.startswith(forbidden + ".")


def _layer_for(path: Path) -> str | None:
    path_str = path.as_posix()
    for layer in FORBIDDEN_LAYER_IMPORTS:
        if path_str.startswith(layer + "/"):
            return layer
    return None


def _matching_allowlist_key(path: Path, imported: str) -> tuple[str, str] | None:
    path_str = path.as_posix()
    for key, entry in BASELINE_ALLOWLIST.items():
        allowed_path, allowed_import = key
        if not entry.reason:
            raise AssertionError(f"Allowlist entry missing reason: {key}")
        if path_str != allowed_path:
            continue
        if _matches(imported, allowed_import):
            return key
    return None


def test_layer_boundaries_do_not_drift():
    violations = []
    used_allowlist: set[tuple[str, str]] = set()

    for path in _iter_python_files():
        layer = _layer_for(path)
        if layer is None:
            continue

        rules = {}
        rules.update(FORBIDDEN_LAYER_IMPORTS.get(layer, {}))
        rules.update(FORBIDDEN_LIBRARY_IMPORTS.get(layer, {}))

        for line, imported in _imports(path):
            for forbidden, reason in rules.items():
                if not _matches(imported, forbidden):
                    continue
                key = _matching_allowlist_key(path, imported)
                if key is not None:
                    used_allowlist.add(key)
                    continue
                violations.append(
                    Violation(
                        path=path,
                        line=line,
                        imported=imported,
                        rule=reason,
                    )
                )

    assert not violations, "\n".join(
        f"{v.path}:{v.line}: {v.imported} — {v.rule}"
        for v in violations
    )

    unused = set(BASELINE_ALLOWLIST) - used_allowlist
    assert not unused, "Stale BASELINE_ALLOWLIST entries (remove them): " + ", ".join(
        f"{path}:{imported}" for path, imported in sorted(unused)
    )


_VAGUE_CANONICAL_FIX_MARKERS = ("TBD", "later", "legacy only", "unknown")


def test_boundary_allowlist_entries_are_actionable_cleanup_debt():
    for key, entry in BASELINE_ALLOWLIST.items():
        assert entry.reason, f"{key}: reason must not be empty"
        assert entry.cleanup_owner, f"{key}: cleanup_owner must not be empty"
        assert entry.canonical_fix, f"{key}: canonical_fix must not be empty"
        assert entry.issue, f"{key}: issue must not be empty"
        assert "code-convention-audit" in entry.issue, (
            f"{key}: issue must reference code-convention-audit, "
            f"got {entry.issue!r}"
        )
        lowered_fix = entry.canonical_fix.lower()
        for marker in _VAGUE_CANONICAL_FIX_MARKERS:
            assert marker.lower() not in lowered_fix, (
                f"{key}: canonical_fix must not contain vague text "
                f"{marker!r}, got {entry.canonical_fix!r}"
            )


def test_allowlisted_paths_are_explicitly_tracked():
    assert ALLOWLISTED_PATHS_REQUIRE_BOUNDARY_CLEANUP == {
        path for path, _imported in BASELINE_ALLOWLIST
    }
