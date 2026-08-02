"""Anti-drift: dual-surface inventory must stay complete and explicit."""

from __future__ import annotations

import ast
from pathlib import Path

from src.adapters.shared.multi_surface_inventory import (
    DUAL_SURFACE_JOBS,
    REQUIRED_DUAL_SURFACE_JOB_IDS,
    dual_surface_job_ids,
    get_dual_surface_job,
)


def test_required_dual_surface_jobs_are_all_registered():
    registered = dual_surface_job_ids()
    missing = REQUIRED_DUAL_SURFACE_JOB_IDS - registered
    assert not missing, f"dual-surface jobs missing from inventory: {sorted(missing)}"


def test_every_inventory_job_has_shared_path_and_declared_deltas_field():
    for job in DUAL_SURFACE_JOBS:
        assert job.job_id, "job_id required"
        assert job.shared_application_path.strip(), f"{job.job_id}: shared path empty"
        assert job.cli_surface.strip(), f"{job.job_id}: cli_surface empty"
        assert job.tui_surface.strip(), f"{job.job_id}: tui_surface empty"
        # intentional_deltas may be empty only if truly none — use explicit tuple
        assert isinstance(job.intentional_deltas, tuple)


def test_criterion1_named_jobs_present():
    """Plan criterion 1 job set must appear in inventory."""
    markers = (
        "UseCase",
        "build_",
        "desk_session",
        "PlanSwing",
        "PreOpen",
        "GetTicker",
        "broker_daily",
    )
    for job_id in (
        "screen-accum",
        "screen-preopen",
        "view-ticker-show",
        "view-ticker-top-brokers",
        "view-broker-list",
        "view-broker-show",
        "view-broker-top-stocks",
        "view-broker-top-matrix",
        "view-broker-flow",
        "view-broker-calendar",
        "view-broker-history",
        "plan-swing-structure",
    ):
        job = get_dual_surface_job(job_id)
        assert job is not None, job_id
        path = job.shared_application_path
        assert any(m in path for m in markers), f"{job_id}: weak shared path {path!r}"


def test_tui_package_does_not_import_cli_view_display_modules():
    """ADR-045: TUI must not import CLI view_*_display for dual-surface jobs."""
    tui_root = Path("src/adapters/tui")
    banned_substrings = (
        "adapters.cli.view_",
        "adapters.cli.view_ticker",
        "adapters.cli.view_broker",
    )
    # More precise: only view_*_display modules
    banned_modules = (
        "src.adapters.cli.view_ticker_display",
        "src.adapters.cli.view_ticker_top_brokers_display",
        "src.adapters.cli.view_broker_desk_display",
        "src.adapters.cli.view_ticker_flow_display",
        "src.adapters.cli.view_ticker_foreign_history_display",
    )
    offenders: list[str] = []
    for path in tui_root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module
                if any(mod == b or mod.startswith(b + ".") for b in banned_modules):
                    offenders.append(f"{path}:{node.lineno}: from {mod}")
                if "view_" in mod and "display" in mod and "adapters.cli" in mod:
                    offenders.append(f"{path}:{node.lineno}: from {mod}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    if any(name == b or name.startswith(b + ".") for b in banned_modules):
                        offenders.append(f"{path}: import {name}")
        # String scan for dynamic / late imports of CLI view_*_display.
        for banned in banned_substrings:
            if banned in source and "view_" in source and "_display" in source:
                # fallback string scan for dynamic patterns
                for i, line in enumerate(source.splitlines(), 1):
                    if "import" in line and "adapters.cli.view_" in line and "_display" in line:
                        offenders.append(f"{path}:{i}: {line.strip()}")
    # unique
    offenders = sorted(set(offenders))
    assert not offenders, "TUI imports CLI view_*_display:\n" + "\n".join(offenders)


def test_tui_composition_uses_shared_formatters_and_use_cases():
    """Spot-check: stock→desks / desk loaders call shared format + app use cases."""
    composition = Path("src/adapters/tui/composition.py").read_text(encoding="utf-8")
    assert "ViewTickerTopBrokersUseCase" in composition or "top_brokers.execute" in composition
    assert "view_ticker_top_brokers_rows" in composition
    assert "ViewBrokerDeskShowUseCase" in composition
    assert "view_broker_desk_text" in composition
    assert "view_ticker_dashboard_text" in composition
    assert "GetTickerDashboardRequest" in composition
    assert "src.adapters.cli.view_" not in composition


def test_ticker_dashboard_inventory_records_agent_read_projection() -> None:
    job = next(item for item in DUAL_SURFACE_JOBS if item.job_id == "view-ticker-show")

    assert "build_read_only_ticker_dashboard_use_case" in job.shared_application_path
    assert any("Agent get_ticker_dashboard" in note for note in job.intentional_deltas)
