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

# Baseline of pre-existing violations, captured before this guard existed.
# Do NOT add new entries here for code written after this guard was added —
# fix the import instead (e.g. have infrastructure return an application
# policy/dataclass object rather than have application import the loader).
BASELINE_ALLOWLIST = {
    (
        "src/application/services/engine_bootstrap/indicator_registry_factory.py",
        "src.infrastructure.persistence.formula_storage",
    ): "LEGACY: composition-root factory constructs infrastructure persistence directly; predates architecture guard. Do not copy.",
    (
        "src/application/services/engine_bootstrap/indicator_registry_factory.py",
        "src.infrastructure.plugins.indicator_loader",
    ): "LEGACY: composition-root factory wires infrastructure plugin loader directly; predates architecture guard. Do not copy.",
    (
        "src/application/services/engine_bootstrap/risk_engine_factory.py",
        "src.infrastructure.persistence.sqlite_broker_repository",
    ): "LEGACY: composition-root factory wires infrastructure repository directly; predates architecture guard. Do not copy.",
    (
        "src/application/services/engine_bootstrap/risk_engine_factory.py",
        "src.infrastructure.persistence.sqlite_market_repository",
    ): "LEGACY: composition-root factory wires infrastructure repository directly; predates architecture guard. Do not copy.",
    (
        "src/application/services/engine_bootstrap/risk_engine_factory.py",
        "src.infrastructure.config.app_config",
    ): "LEGACY: composition-root factory reads infrastructure config module directly; predates architecture guard. Do not copy.",
    (
        "src/application/services/engine_bootstrap/risk_engine_factory.py",
        "src.infrastructure.browser.stockbit_bandar",
    ): "LEGACY: composition-root factory wires infrastructure browser provider directly; predates architecture guard. Do not copy.",
    (
        "src/application/services/engine_bootstrap/risk_engine_factory.py",
        "src.infrastructure.browser.stockbit_fundamentals",
    ): "LEGACY: composition-root factory wires infrastructure browser provider directly; predates architecture guard. Do not copy.",
    (
        "src/application/services/engine_bootstrap/risk_engine_factory.py",
        "src.infrastructure.browser.stockbit_shareholding",
    ): "LEGACY: composition-root factory wires infrastructure browser provider directly; predates architecture guard. Do not copy.",
    (
        "src/application/services/engine_bootstrap/signal_config_resolvers.py",
        "src.infrastructure.config.app_config",
    ): "LEGACY: application resolver reads infrastructure config module directly; predates architecture guard. Do not copy.",
    (
        "src/application/services/engine_bootstrap/signal_engine_factory.py",
        "src.infrastructure.config.app_config",
    ): "LEGACY: composition-root factory reads infrastructure config module directly; predates architecture guard. Do not copy.",
    (
        "src/application/services/engine_bootstrap/signal_engine_factory.py",
        "src.infrastructure.browser.stockbit_analyst",
    ): "LEGACY: composition-root factory wires infrastructure browser provider directly; predates architecture guard. Do not copy.",
    (
        "src/application/services/engine_bootstrap/signal_engine_factory.py",
        "src.infrastructure.browser.stockbit_bandar",
    ): "LEGACY: composition-root factory wires infrastructure browser provider directly; predates architecture guard. Do not copy.",
    (
        "src/application/services/engine_bootstrap/signal_engine_factory.py",
        "src.infrastructure.browser.stockbit_forward_estimates",
    ): "LEGACY: composition-root factory wires infrastructure browser provider directly; predates architecture guard. Do not copy.",
    (
        "src/application/services/engine_bootstrap/signal_engine_factory.py",
        "src.infrastructure.browser.stockbit_insider",
    ): "LEGACY: composition-root factory wires infrastructure browser provider directly; predates architecture guard. Do not copy.",
    (
        "src/application/services/engine_bootstrap/signal_engine_factory.py",
        "src.infrastructure.browser.stockbit_seasonality",
    ): "LEGACY: composition-root factory wires infrastructure browser provider directly; predates architecture guard. Do not copy.",
    (
        "src/application/services/engine_bootstrap/signal_engine_factory.py",
        "src.infrastructure.persistence.sqlite_market_repository",
    ): "LEGACY: composition-root factory wires infrastructure repository directly; predates architecture guard. Do not copy.",
    (
        "src/application/services/stockbit_session.py",
        "src.infrastructure.browser.stockbit_api_client",
    ): "LEGACY: application session service wires infrastructure browser client directly; predates architecture guard. Do not copy.",
    (
        "src/application/services/stockbit_session.py",
        "src.infrastructure.browser.stockbit_broker_provider",
    ): "LEGACY: application session service wires infrastructure browser provider directly; predates architecture guard. Do not copy.",
    (
        "src/application/services/stockbit_session.py",
        "src.infrastructure.config.app_config",
    ): "LEGACY: application session service reads infrastructure config module directly; predates architecture guard. Do not copy.",
    (
        "src/application/services/strategy_loader.py",
        "src.infrastructure.config.rules_yaml_loader",
    ): "LEGACY: application loader calls infrastructure YAML loader directly; predates architecture guard. Do not copy.",
    (
        "src/application/services/universe_loader.py",
        "src.infrastructure.persistence.sqlite_broker_repository",
    ): "LEGACY: application loader constructs infrastructure repository directly; predates architecture guard. Do not copy.",
    (
        "src/application/use_case/assess_risk_use_case.py",
        "src.infrastructure.config.rules_yaml_loader",
    ): "LEGACY: application use case calls infrastructure YAML loader directly; predates architecture guard. Do not copy.",
    (
        "src/application/use_case/backtest_use_case.py",
        "src.infrastructure.config.rules_yaml_loader",
    ): "LEGACY: application use case calls infrastructure YAML loader directly; predates architecture guard. Do not copy.",
    (
        "src/application/use_case/create_strategy_from_intent_use_case.py",
        "src.infrastructure.config.rules_yaml_loader",
    ): "LEGACY: application use case calls infrastructure YAML loader directly; predates architecture guard. Do not copy.",
    (
        "src/application/use_case/opening_grade_use_case.py",
        "src.infrastructure.config.app_config",
    ): "LEGACY: application use case reads infrastructure config module directly; predates architecture guard. Do not copy.",
    (
        "src/application/use_case/view_universe_summary_use_case.py",
        "src.infrastructure.persistence.sqlite_universe_summary_provider",
    ): "LEGACY: application use case constructs infrastructure provider directly; predates architecture guard. Do not copy.",
    (
        "src/domain/rules/technical_gate.py",
        "src.application.services.indicator_evaluator",
    ): "LEGACY: TYPE_CHECKING-only forward reference for a constructor parameter hint; not a runtime import but still ast-visible. Predates architecture guard. Do not copy — prefer a domain-level Protocol port.",
}


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
    for key, reason in BASELINE_ALLOWLIST.items():
        allowed_path, allowed_import = key
        if not reason:
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
