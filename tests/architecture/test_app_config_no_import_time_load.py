"""Executable guard against import-time-loaded global AppConfig.

Config must be loaded explicitly at command/composition execution time via
load_app_config(), never captured by module import. See
docs/code-convention-audit.md finding 1.

Layer: Test (architecture guard, no runtime behavior).
"""
from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

SRC_ROOT = Path("src")


def _all_cli_module_names() -> list[str]:
    names = []
    for path in sorted(Path("src/adapters/cli").rglob("*.py")):
        if path.name == "__init__.py":
            continue
        rel = path.relative_to("src").with_suffix("")
        names.append("src." + ".".join(rel.parts))
    return names


def _iter_python_files():
    yield from SRC_ROOT.rglob("*.py")


def test_no_production_module_imports_app_cfg():
    violations = []
    for path in _iter_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "APP_CFG":
                        violations.append(f"{path}:{node.lineno}: imports APP_CFG")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[-1] == "APP_CFG":
                        violations.append(f"{path}:{node.lineno}: imports APP_CFG")

    assert not violations, "\n".join(violations)


def test_cli_adapters_do_not_import_app_cfg():
    violations = []
    for path in Path("src/adapters/cli").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "APP_CFG":
                        violations.append(f"{path}:{node.lineno}: imports APP_CFG")

    assert not violations, "\n".join(violations)


def test_no_src_line_references_app_cfg_attribute_access():
    violations = []
    for path in _iter_python_files():
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if "APP_CFG." in line or "APP_CFG:" in line or " APP_CFG " in line:
                violations.append(f"{path}:{lineno}: {line.strip()}")

    assert not violations, "\n".join(violations)


def test_importing_cli_command_modules_does_not_call_load_app_config(monkeypatch):
    """Import-time code must never resolve config — only functions/constructors do.

    Patch load_app_config() to raise, then re-import (reload) representative
    CLI modules. If any module captured config at import time, the reload
    re-executes that module-level call and raises here.
    """
    import src.infrastructure.config.app_config as app_config_module

    def _raise():
        raise AssertionError("load_app_config() must not be called at import time")

    monkeypatch.setattr(app_config_module, "load_app_config", _raise)

    module_names = _all_cli_module_names()
    failures = []
    try:
        for module_name in module_names:
            try:
                module = importlib.import_module(module_name)
                importlib.reload(module)
            except AssertionError as exc:
                failures.append(f"{module_name}: {exc}")
    finally:
        # Reloading a CLI module while load_app_config() was patched can
        # leave *any* module reachable from it (not just the CLI module
        # itself) with its locally-imported `load_app_config` name bound to
        # the raising stub — `from ... import load_app_config` captures the
        # function object, not the patched attribute, and reload executes
        # the module's imports transitively. monkeypatch only restores
        # app_config_module.load_app_config, not every module that already
        # imported it, so scan sys.modules for any module still holding the
        # stub and reload it now that the real load_app_config is restored.
        # This repairs global interpreter state for the rest of the test
        # session.
        stale = [
            name
            for name, module in list(sys.modules.items())
            if getattr(module, "load_app_config", None) is _raise
        ]
        for module_name in stale:
            importlib.reload(sys.modules[module_name])

    assert not failures, "\n".join(failures)
